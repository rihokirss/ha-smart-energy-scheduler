"""Pure pricing and planning engine."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime, time, timedelta
from math import isfinite
from typing import Any

from .models import (
    DevicePlan,
    HourPrice,
    PlannedHour,
    PlanningDevice,
    QuarterPrice,
    TariffConfig,
)


def parse_datetime(value: Any) -> datetime:
    """Parse an ISO timestamp and require timezone information."""
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError(f"Timestamp has no timezone: {value}")
    return result


def parse_nordpool_response(payload: Any, area: str) -> list[QuarterPrice]:
    """Normalize known nordpool.hourly response variants."""
    found: list[QuarterPrice] = []

    def walk(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                walk(item)
            return
        if not isinstance(value, Mapping):
            return

        start = value.get("deliveryStart") or value.get("start") or value.get("timestamp")
        end = value.get("deliveryEnd") or value.get("end")
        per_area = value.get("entryPerArea") or value.get("areas")
        price: Any = None
        if isinstance(per_area, Mapping):
            price = per_area.get(area)
            if isinstance(price, Mapping):
                price = price.get("price") or price.get("value")
        if price is None and value.get("area") in (None, area):
            price = value.get("price") or value.get("value") or value.get(area)
        if start is not None and price is not None:
            parsed_start = parse_datetime(start)
            parsed_end = (
                parse_datetime(end) if end is not None else parsed_start + timedelta(minutes=15)
            )
            numeric = float(price)
            if isfinite(numeric):
                found.append(QuarterPrice(parsed_start, parsed_end, numeric))
            return
        for nested in value.values():
            if isinstance(nested, (Mapping, list)):
                walk(nested)

    walk(payload)
    unique = {(item.start, item.end): item for item in found}
    return sorted(unique.values(), key=lambda item: item.start)


def is_day_tariff(moment: datetime, tariff: TariffConfig) -> bool:
    """Return whether a slot uses the day network tariff."""
    if tariff.weekend_night and moment.weekday() >= 5:
        return False
    local_time = moment.timetz().replace(tzinfo=None)
    if tariff.day_start == tariff.day_end:
        return True
    if tariff.day_start < tariff.day_end:
        return tariff.day_start <= local_time < tariff.day_end
    return local_time >= tariff.day_start or local_time < tariff.day_end


def aggregate_hourly(
    quarters: Iterable[QuarterPrice], tariff: TariffConfig, timezone: Any
) -> list[HourPrice]:
    """Aggregate arbitrary price intervals into local clock hours by duration."""
    buckets: dict[datetime, list[tuple[float, float, float, float]]] = defaultdict(list)
    for quarter in quarters:
        local_start = quarter.start.astimezone(timezone)
        # Absolute UTC keys keep both repeated local hours during the DST fallback.
        key = quarter.start.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
        duration_h = max(0.0, (quarter.end - quarter.start).total_seconds() / 3600)
        if duration_h:
            network = (
                tariff.network_day if is_day_tariff(local_start, tariff) else tariff.network_night
            )
            import_price = (quarter.market_eur_mwh + tariff.buy_margin + network) * (
                1 + tariff.vat_fraction
            )
            export_price = quarter.market_eur_mwh + tariff.sell_margin
            buckets[key].append((quarter.market_eur_mwh, import_price, export_price, duration_h))

    result: list[HourPrice] = []
    for utc_start in sorted(buckets):
        values = buckets[utc_start]
        total_h = sum(duration for _, _, _, duration in values)
        market = sum(price * duration for price, _, _, duration in values) / total_h
        import_price = sum(price * duration for _, price, _, duration in values) / total_h
        export_price = sum(price * duration for _, _, price, duration in values) / total_h
        start = utc_start.astimezone(timezone)
        result.append(
            HourPrice(
                start=start,
                end=(utc_start + timedelta(hours=1)).astimezone(timezone),
                market_eur_mwh=market,
                import_eur_mwh=import_price,
                export_eur_mwh=export_price,
            )
        )
    return result


def merge_solar_forecast(
    hours: Sequence[HourPrice], forecasts: Iterable[Mapping[str, float]], base_load_w: float
) -> None:
    """Sum Forecast.Solar providers into matching absolute hours."""
    solar: dict[datetime, float] = defaultdict(float)
    for provider in forecasts:
        for stamp, value in provider.items():
            instant = parse_datetime(stamp)
            solar[instant] += max(0.0, float(value))
    for hour in hours:
        hour.pv_wh = sum(
            value
            for stamp, value in solar.items()
            if hour.start.timestamp() <= stamp.timestamp() < hour.end.timestamp()
        )
        hour.base_load_wh = max(0.0, base_load_w)


def weather_target_hours(
    base_hours: float,
    reference_temperature: float,
    average_apparent_temperature: float | None,
    hours_per_degree: float,
    minimum: float,
    maximum: float,
) -> int:
    """Calculate and clamp the daily whole-hour target."""
    target = base_hours
    if average_apparent_temperature is not None:
        target += (reference_temperature - average_apparent_temperature) * hours_per_degree
    return round(max(minimum, min(maximum, target)))


def is_in_window(moment: datetime, start: time, end: time) -> bool:
    """Check a local hour against a possibly overnight allowed window."""
    current = moment.timetz().replace(tzinfo=None)
    if start == end:
        return True
    if start < end:
        return start <= current < end
    return current >= start or current < end


def output_should_be_on(active: bool, inverted: bool) -> bool:
    """Map logical device activity to an explicit physical output state."""
    return active != inverted


def _effective_cost(
    hour: HourPrice, power_w: float, remaining_solar_wh: float
) -> tuple[float, float]:
    energy = max(1.0, power_w)
    solar = min(energy, max(0.0, remaining_solar_wh))
    grid = energy - solar
    cost = (solar * hour.export_eur_mwh + grid * hour.import_eur_mwh) / energy
    return cost, solar


def _optimize_binary_sequence(
    hours: Sequence[HourPrice],
    costs: Sequence[float],
    targets: Mapping[date, int],
    device: PlanningDevice,
    forced_states: Mapping[float, bool] | None = None,
) -> list[bool] | None:
    """Dynamic program enforcing target counts and minimum runs."""
    days = sorted(targets)
    day_index = {day: index for index, day in enumerate(days)}
    # (counts, on, capped_run) -> (cost, path)
    states: dict[tuple[tuple[int, ...], bool, int], tuple[float, tuple[bool, ...]]] = {
        ((0,) * len(days), False, max(1, device.min_off_hours)): (0.0, ())
    }
    for idx, hour in enumerate(hours):
        next_states: dict[tuple[tuple[int, ...], bool, int], tuple[float, tuple[bool, ...]]] = {}
        local_day = hour.start.date()
        target_index = day_index.get(local_day)
        allowed = target_index is not None and is_in_window(
            hour.start, device.window_start, device.window_end
        )
        for (counts, was_on, run), (total_cost, path) in states.items():
            forced = (forced_states or {}).get(hour.start.timestamp())
            choices = (forced,) if forced is not None else ((False, True) if allowed else (False,))
            for turn_on in choices:
                if turn_on and not allowed:
                    continue
                if turn_on != was_on:
                    required = device.min_on_hours if was_on else device.min_off_hours
                    if run < required:
                        continue
                    new_run = 1
                else:
                    cap = device.min_on_hours if turn_on else device.min_off_hours
                    new_run = min(max(1, cap), run + 1)
                new_counts = list(counts)
                if turn_on:
                    assert target_index is not None
                    new_counts[target_index] += 1
                    if new_counts[target_index] > targets[local_day]:
                        continue
                key = (tuple(new_counts), turn_on, new_run)
                candidate = (total_cost + (costs[idx] if turn_on else 0.0), path + (turn_on,))
                if key not in next_states or candidate[0] < next_states[key][0]:
                    next_states[key] = candidate
        states = next_states

    expected = tuple(targets[day] for day in days)
    candidates = []
    for (counts, on, run), value in states.items():
        if counts != expected:
            continue
        if on and run < device.min_on_hours:
            continue
        candidates.append(value)
    return list(min(candidates, key=lambda item: item[0])[1]) if candidates else None


def build_plans(
    hours: Sequence[HourPrice],
    devices: Sequence[PlanningDevice],
    targets: Mapping[str, Mapping[date, int]],
    forced_states: Mapping[str, Mapping[float, bool]] | None = None,
) -> dict[str, DevicePlan]:
    """Plan devices in solar priority order without double-counting PV."""
    remaining_solar = {hour.start: hour.surplus_wh for hour in hours}
    result: dict[str, DevicePlan] = {}
    for device in sorted(devices, key=lambda item: (item.solar_priority, item.device_id)):
        device_targets = dict(targets.get(device.device_id, {}))
        priced = [
            _effective_cost(hour, device.nominal_power_w, remaining_solar[hour.start])
            for hour in hours
        ]
        sequence = _optimize_binary_sequence(
            hours,
            [item[0] for item in priced],
            device_targets,
            device,
            (forced_states or {}).get(device.device_id),
        )
        if sequence is None:
            result[device.device_id] = DevicePlan(
                device_id=device.device_id,
                target_hours=device_targets,
                valid=False,
                error="constraints_unsatisfiable",
            )
            continue
        plan = DevicePlan(device_id=device.device_id, target_hours=device_targets)
        for hour, active, (cost, potential_solar) in zip(hours, sequence, priced, strict=True):
            allocated = potential_solar if active else 0.0
            if active:
                remaining_solar[hour.start] = max(0.0, remaining_solar[hour.start] - allocated)
            plan.hours.append(
                PlannedHour(
                    start=hour.start,
                    active=active,
                    effective_eur_mwh=cost,
                    import_eur_mwh=hour.import_eur_mwh,
                    export_eur_mwh=hour.export_eur_mwh,
                    allocated_solar_wh=allocated,
                    reason="solar" if allocated else "price",
                )
            )
        result[device.device_id] = plan
    return result
