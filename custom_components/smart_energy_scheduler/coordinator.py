"""Data collection, planning, persistence, and output control."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.energy.data import async_get_manager
from homeassistant.components.energy.websocket_api import async_get_energy_platforms
from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import (
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    SUN_EVENT_SUNRISE,
    SUN_EVENT_SUNSET,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_component import DATA_INSTANCES
from homeassistant.helpers.storage import Store
from homeassistant.helpers.sun import get_astral_event_date
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ALWAYS_OFF_ABOVE,
    CONF_ALWAYS_ON_BELOW,
    CONF_AREA,
    CONF_BASE_HOURS,
    CONF_BASE_LOAD_W,
    CONF_BUY_MARGIN,
    CONF_CURRENCY,
    CONF_DAY_END,
    CONF_DAY_START,
    CONF_ENABLED,
    CONF_FAILURE_MODE,
    CONF_FEEDBACK_ENTITY,
    CONF_HOURS_PER_DEGREE,
    CONF_INVERTED,
    CONF_LEGACY_WIND_CHILL,
    CONF_MAX_HOURS,
    CONF_MIN_HOURS,
    CONF_MIN_OFF_HOURS,
    CONF_MIN_ON_HOURS,
    CONF_NETWORK_DAY,
    CONF_NETWORK_INCLUDES_VAT,
    CONF_NETWORK_NIGHT,
    CONF_NOMINAL_POWER_W,
    CONF_POWER_MULTIPLIER,
    CONF_POWER_SENSOR,
    CONF_PREHEAT_HOURS,
    CONF_REFERENCE_TEMPERATURE,
    CONF_SELL_MARGIN,
    CONF_SHADOW_MODE,
    CONF_SOLAR_FALLBACK_ENABLED,
    CONF_SOLAR_FALLBACK_END_MONTH,
    CONF_SOLAR_FALLBACK_START_MONTH,
    CONF_SOLAR_FALLBACK_SUNRISE_DELAY_H,
    CONF_SOLAR_FALLBACK_SUNSET_ADVANCE_H,
    CONF_SOLAR_PRIORITY,
    CONF_TARGET_ENTITY,
    CONF_USE_WEATHER,
    CONF_VAT,
    CONF_WEATHER_ENTITY,
    CONF_WEATHER_LOOKAHEAD_HOURS,
    CONF_WEEKEND_NIGHT,
    CONF_WINDOW_END,
    CONF_WINDOW_START,
    DOMAIN,
    EVENT_PLAN_UPDATED,
    FAILURE_FORCE_OFF,
    FAILURE_FORCE_ON,
    OVERRIDE_AUTO,
    OVERRIDE_OFF,
    OVERRIDE_ON,
    STORAGE_KEY,
    STORAGE_VERSION,
    SUBENTRY_DEVICE,
)
from .engine import (
    aggregate_hourly,
    apply_solar_window_fallback,
    build_plans,
    forecast_window_average,
    is_in_window,
    legacy_wind_chill,
    merge_solar_forecast,
    output_should_be_on,
    parse_datetime,
    parse_nordpool_response,
    weather_target_hours,
)
from .models import DevicePlan, DeviceRuntimeState, HourPrice, PlanningDevice, TariffConfig

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class SchedulerData:
    """Coordinator payload exposed to entities and websocket clients."""

    generated_at: datetime
    hours: list[HourPrice] = field(default_factory=list)
    plans: dict[str, DevicePlan] = field(default_factory=dict)
    temperatures: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    solar_source: str = "none"
    error: str | None = None


class SmartEnergyCoordinator(DataUpdateCoordinator[SchedulerData]):
    """Coordinate the shared price, weather, solar, and device plan."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=15),
        )
        self.entry = entry
        self.timezone = dt_util.get_time_zone(hass.config.time_zone) or dt_util.UTC
        self.states: dict[str, DeviceRuntimeState] = {}
        self._store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry.entry_id}")
        self._apply_lock = asyncio.Lock()

    @property
    def device_subentries(self) -> list[ConfigSubentry]:
        """Return configured scheduler devices."""
        return list(self.entry.get_subentries_of_type(SUBENTRY_DEVICE))

    async def async_load_state(self) -> None:
        """Restore overrides and runtime counters."""
        stored = await self._store.async_load() or {}
        for subentry in self.device_subentries:
            raw = stored.get("devices", {}).get(subentry.subentry_id, {})
            observation_source = self._observation_source(subentry)
            source_changed = raw.get("observation_source") != observation_source
            override_until = raw.get("override_until")
            last_accounted = raw.get("last_accounted_at")
            actual_hours = {
                key: float(value) for key, value in raw.get("actual_hours_by_day", {}).items()
            }
            # Runtime accumulated with another feedback source is not comparable.
            # In particular, changing from a master permit switch to compressor
            # feedback must not make the new device look as if it already ran.
            if source_changed:
                actual_hours.pop(dt_util.now().astimezone(self.timezone).date().isoformat(), None)
            self.states[subentry.subentry_id] = DeviceRuntimeState(
                enabled=bool(raw.get("enabled", subentry.data.get(CONF_ENABLED, True))),
                override=raw.get("override", OVERRIDE_AUTO),
                override_until=parse_datetime(override_until) if override_until else None,
                actual_hours_by_day=actual_hours,
                observation_source=observation_source,
                last_active=None if source_changed else raw.get("last_active"),
                last_accounted_at=(
                    None
                    if source_changed
                    else parse_datetime(last_accounted)
                    if last_accounted
                    else None
                ),
                reason=raw.get("reason", "restored"),
                locked_hour_start=(
                    None
                    if source_changed
                    else parse_datetime(raw["locked_hour_start"])
                    if raw.get("locked_hour_start")
                    else None
                ),
                locked_active=None if source_changed else raw.get("locked_active"),
            )

    async def async_save_state(self) -> None:
        """Persist small mutable state; the plan itself is recalculated."""
        await self._store.async_save(
            {
                "devices": {
                    device_id: {
                        "enabled": state.enabled,
                        "override": state.override,
                        "override_until": state.override_until.isoformat()
                        if state.override_until
                        else None,
                        "actual_hours_by_day": state.actual_hours_by_day,
                        "observation_source": state.observation_source,
                        "last_active": state.last_active,
                        "last_accounted_at": state.last_accounted_at.isoformat()
                        if state.last_accounted_at
                        else None,
                        "reason": state.reason,
                        "locked_hour_start": state.locked_hour_start.isoformat()
                        if state.locked_hour_start
                        else None,
                        "locked_active": state.locked_active,
                    }
                    for device_id, state in self.states.items()
                }
            }
        )

    @staticmethod
    def _observation_source(subentry: ConfigSubentry) -> str:
        """Return a stable key for the source used to count actual runtime."""
        data = subentry.data
        if power_sensor := data.get(CONF_POWER_SENSOR):
            return f"power:{power_sensor}:{float(data.get(CONF_POWER_MULTIPLIER, 1))}"
        if feedback := data.get(CONF_FEEDBACK_ENTITY):
            return f"feedback:{feedback}"
        return f"target:{data[CONF_TARGET_ENTITY]}:{bool(data[CONF_INVERTED])}"

    def _tariff(self) -> TariffConfig:
        data = self.entry.data
        day_start = dt_util.parse_time(data[CONF_DAY_START])
        day_end = dt_util.parse_time(data[CONF_DAY_END])
        if day_start is None or day_end is None:
            raise ValueError("Invalid day/night tariff time")
        return TariffConfig(
            buy_margin=float(data[CONF_BUY_MARGIN]),
            sell_margin=float(data[CONF_SELL_MARGIN]),
            vat_fraction=float(data[CONF_VAT]) / 100,
            network_day=float(data[CONF_NETWORK_DAY]),
            network_night=float(data[CONF_NETWORK_NIGHT]),
            day_start=day_start,
            day_end=day_end,
            weekend_night=bool(data[CONF_WEEKEND_NIGHT]),
            network_includes_vat=bool(data.get(CONF_NETWORK_INCLUDES_VAT, False)),
            holiday_country=str(data.get(CONF_AREA) or "").upper() or None,
        )

    async def _async_fetch_prices(self, day: date) -> Any:
        """Fetch raw Day-Ahead prices through the installed Nord Pool integration."""
        if not self.hass.services.has_service("nordpool", "hourly"):
            raise RuntimeError("nordpool.hourly service is not available")
        return await self.hass.services.async_call(
            "nordpool",
            "hourly",
            {
                "date": day.isoformat(),
                "area": [self.entry.data[CONF_AREA]],
                "currency": self.entry.data[CONF_CURRENCY],
            },
            blocking=True,
            return_response=True,
        )

    async def _async_fetch_solar(self) -> list[Mapping[str, float]]:
        """Read the same Forecast.Solar series used by Energy Dashboard."""
        manager = await async_get_manager(self.hass)
        if manager.data is None:
            return []
        entry_ids: set[str] = set()
        for source in manager.data.get("energy_sources", []):
            if source.get("type") == "solar":
                entry_ids.update(source.get("config_entry_solar_forecast") or [])
        platforms = await async_get_energy_platforms(self.hass)
        result: list[Mapping[str, float]] = []
        for entry_id in entry_ids:
            config_entry = self.hass.config_entries.async_get_entry(entry_id)
            if config_entry is None or config_entry.domain not in platforms:
                continue
            forecast = await platforms[config_entry.domain](self.hass, entry_id)
            if forecast and isinstance(forecast.get("wh_hours"), Mapping):
                result.append(forecast["wh_hours"])
        return result

    async def _async_fetch_weather(
        self,
    ) -> tuple[list[tuple[datetime, float]], list[tuple[datetime, float]], list[str]]:
        """Return provider and legacy wind-adjusted forecast samples."""
        entity_id = self.entry.data.get(CONF_WEATHER_ENTITY)
        if not entity_id:
            return [], [], ["weather_entity_not_configured"]
        component = self.hass.data.get(DATA_INSTANCES, {}).get("weather")
        entity = component.get_entity(entity_id) if component else None
        if entity is None:
            raise RuntimeError(f"Weather entity {entity_id} is not loaded")
        native_forecasts = await entity.async_forecast_hourly()
        forecasts = entity._convert_forecast(native_forecasts or [])  # noqa: SLF001
        samples: list[tuple[datetime, float]] = []
        legacy_samples: list[tuple[datetime, float]] = []
        fallback_used = False
        for item in forecasts:
            stamp = item.get("datetime")
            if not stamp:
                continue
            value = item.get("apparent_temperature")
            if value is None:
                value = item.get("temperature")
                fallback_used = value is not None or fallback_used
            if value is not None:
                parsed_stamp = parse_datetime(stamp).astimezone(self.timezone)
                samples.append((parsed_stamp, float(value)))
                temperature = item.get("temperature")
                wind_speed = item.get("wind_speed")
                legacy_value = (
                    legacy_wind_chill(float(temperature), float(wind_speed))
                    if temperature is not None and wind_speed is not None
                    else float(value)
                )
                legacy_samples.append((parsed_stamp, legacy_value))
        warnings = ["weather_apparent_temperature_fallback"] if fallback_used else []
        return samples, legacy_samples, warnings

    async def _async_update_data(self) -> SchedulerData:
        """Fetch inputs and calculate a complete, non-commanding plan."""
        now = dt_util.now().astimezone(self.timezone)
        shadow_mode = bool(self.entry.data[CONF_SHADOW_MODE])
        warnings: list[str] = []
        await self.async_account_actual(now)
        # Shadow mode never changes the physical output, so there is no begun
        # scheduler cycle to protect. A transient startup failure must not pin
        # the current hour to the configured failure state on the preview chart.
        if shadow_mode:
            for state in self.states.values():
                state.locked_hour_start = None
                state.locked_active = None
        try:
            price_days = [
                now.date() - timedelta(days=1),
                now.date(),
                now.date() + timedelta(days=1),
            ]
            price_payloads = await asyncio.gather(
                *(self._async_fetch_prices(day) for day in price_days),
                return_exceptions=True,
            )
            quarters = []
            for day, payload in zip(price_days, price_payloads, strict=True):
                if isinstance(payload, asyncio.CancelledError):
                    raise payload
                if isinstance(payload, Exception):
                    if day > now.date() and "next_day_prices_pending" not in warnings:
                        warnings.append("next_day_prices_pending")
                    elif day == now.date():
                        warnings.append("current_day_prices_unavailable")
                    continue
                parsed = parse_nordpool_response(payload, self.entry.data[CONF_AREA])
                if not parsed:
                    if day > now.date() and "next_day_prices_pending" not in warnings:
                        warnings.append("next_day_prices_pending")
                    elif day == now.date():
                        warnings.append("current_day_prices_unavailable")
                    continue
                quarters.extend(parsed)
            unique_quarters = {(quarter.start, quarter.end): quarter for quarter in quarters}
            hours = aggregate_hourly(unique_quarters.values(), self._tariff(), self.timezone)
            # Expose both local calendar days so the chart starts at today's
            # midnight. Planning still only receives current/future hours.
            floor_now = now.replace(minute=0, second=0, microsecond=0)
            horizon_start = floor_now.timestamp()
            planning_days = {now.date(), now.date() + timedelta(days=1)}
            hours = [hour for hour in hours if hour.start.date() in planning_days]
            if not hours:
                raise RuntimeError("Nord Pool returned no usable price slots")
            tomorrow = now.date() + timedelta(days=1)
            tomorrow_start = datetime.combine(tomorrow, datetime.min.time(), tzinfo=self.timezone)
            tomorrow_end = datetime.combine(
                tomorrow + timedelta(days=1), datetime.min.time(), tzinfo=self.timezone
            )
            expected_tomorrow_hours = round(
                (tomorrow_end.timestamp() - tomorrow_start.timestamp()) / 3600
            )
            received_tomorrow_hours = sum(hour.start.date() == tomorrow for hour in hours)
            if received_tomorrow_hours != expected_tomorrow_hours:
                hours = [hour for hour in hours if hour.start.date() != tomorrow]
                if "next_day_prices_pending" not in warnings:
                    warnings.append("next_day_prices_pending")
            planning_hours = [
                hour
                for hour in hours
                if horizon_start <= hour.start.timestamp() < horizon_start + 48 * 3600
            ]
            if not planning_hours:
                raise RuntimeError("Nord Pool returned no future price slots")
        except Exception as err:  # noqa: BLE001 - input failure is represented in HA
            _LOGGER.warning("Unable to build price horizon: %s", err)
            return SchedulerData(generated_at=now, error=f"price_data: {err}")

        solar_missing = False
        solar: list[Mapping[str, float]] = []
        try:
            solar = await self._async_fetch_solar()
            if not any(provider for provider in solar):
                warnings.append("solar_forecast_missing")
                solar_missing = True
        except Exception as err:  # noqa: BLE001
            warnings.append(f"solar_forecast_error: {err}")
            solar_missing = True
        merge_solar_forecast(hours, solar, float(self.entry.data[CONF_BASE_LOAD_W]))
        solar_source = "price_only" if solar_missing else "forecast"

        try:
            (
                weather_samples,
                legacy_weather_samples,
                weather_warnings,
            ) = await self._async_fetch_weather()
            warnings.extend(weather_warnings)
        except Exception as err:  # noqa: BLE001
            weather_samples = []
            legacy_weather_samples = []
            warnings.append(f"weather_forecast_error: {err}")

        planning_devices: list[PlanningDevice] = []
        targets: dict[str, dict[date, int]] = {}
        minimum_targets: dict[str, dict[date, int]] = {}
        required_hours: dict[str, dict[date, int]] = {}
        apparent_temperatures: dict[str, dict[date, float]] = {}
        available_days = sorted({hour.start.date() for hour in planning_hours})
        for subentry in self.device_subentries:
            data = subentry.data
            device_id = subentry.subentry_id
            window_start = dt_util.parse_time(data[CONF_WINDOW_START])
            window_end = dt_util.parse_time(data[CONF_WINDOW_END])
            if window_start is None or window_end is None:
                warnings.append(f"invalid_work_window:{device_id}")
                continue
            nominal_power = float(data[CONF_NOMINAL_POWER_W])
            if (power_entity := data.get(CONF_POWER_SENSOR)) and (
                power_state := self.hass.states.get(power_entity)
            ) is not None:
                try:
                    observed_power = float(power_state.state) * float(
                        data.get(CONF_POWER_MULTIPLIER, 1)
                    )
                    if observed_power > 10:
                        nominal_power = observed_power
                except (TypeError, ValueError):
                    pass
            planning_devices.append(
                PlanningDevice(
                    device_id=device_id,
                    name=subentry.title,
                    nominal_power_w=nominal_power,
                    window_start=window_start,
                    window_end=window_end,
                    min_on_hours=int(data[CONF_MIN_ON_HOURS]),
                    min_off_hours=int(data[CONF_MIN_OFF_HOURS]),
                    solar_priority=int(data[CONF_SOLAR_PRIORITY]),
                    always_on_below_eur_mwh=(
                        float(data[CONF_ALWAYS_ON_BELOW]) if CONF_ALWAYS_ON_BELOW in data else None
                    ),
                    always_off_above_eur_mwh=(
                        float(data[CONF_ALWAYS_OFF_ABOVE])
                        if CONF_ALWAYS_OFF_ABOVE in data
                        else None
                    ),
                )
            )
            target_by_day: dict[date, int] = {}
            minimum_by_day: dict[date, int] = {}
            required_by_day: dict[date, int] = {}
            apparent_by_day: dict[date, float] = {}
            for day in available_days:
                apparent = (
                    forecast_window_average(
                        legacy_weather_samples
                        if data.get(CONF_LEGACY_WIND_CHILL, True)
                        else weather_samples,
                        day,
                        now,
                        self.timezone,
                        float(data.get(CONF_WEATHER_LOOKAHEAD_HOURS, 12)),
                        float(data.get(CONF_PREHEAT_HOURS, 0)),
                    )
                    if data[CONF_USE_WEATHER]
                    else None
                )
                if apparent is not None:
                    apparent_by_day[day] = apparent
                target = weather_target_hours(
                    float(data[CONF_BASE_HOURS]),
                    float(data[CONF_REFERENCE_TEMPERATURE]),
                    apparent,
                    float(data[CONF_HOURS_PER_DEGREE]),
                    float(data[CONF_MIN_HOURS]),
                    float(data[CONF_MAX_HOURS]),
                )
                required_by_day[day] = target
                actual = self.states[device_id].actual_hours_by_day.get(day.isoformat(), 0.0)
                available = sum(
                    is_in_window(hour.start, window_start, window_end)
                    for hour in planning_hours
                    if hour.start.date() == day
                )
                remaining = max(0, round(target - actual)) if day == now.date() else target
                minimum = round(float(data[CONF_MIN_HOURS]))
                minimum_remaining = (
                    max(0, round(minimum - actual)) if day == now.date() else minimum
                )
                state = self.states[device_id]
                current_hour = now.replace(minute=0, second=0, microsecond=0)
                if (
                    day == now.date()
                    and not shadow_mode
                    and state.locked_active
                    and state.locked_hour_start is not None
                    and state.locked_hour_start.timestamp() == current_hour.timestamp()
                ):
                    remaining = max(1, remaining)
                target_by_day[day] = min(remaining, available)
                minimum_by_day[day] = min(minimum_remaining, available)
            targets[device_id] = target_by_day
            minimum_targets[device_id] = minimum_by_day
            required_hours[device_id] = required_by_day
            apparent_temperatures[device_id] = apparent_by_day

        if solar_missing and self.entry.data.get(CONF_SOLAR_FALLBACK_ENABLED, True):
            try:
                sun_events: dict[date, tuple[datetime | None, datetime | None]] = {}
                for day in {hour.start.date() for hour in hours}:
                    sun_events[day] = (
                        get_astral_event_date(self.hass, SUN_EVENT_SUNRISE, day),
                        get_astral_event_date(self.hass, SUN_EVENT_SUNSET, day),
                    )
                fallback_hours = apply_solar_window_fallback(
                    hours,
                    sun_events,
                    float(self.entry.data[CONF_BASE_LOAD_W]),
                    sum(device.nominal_power_w for device in planning_devices),
                    int(self.entry.data.get(CONF_SOLAR_FALLBACK_START_MONTH, 3)),
                    int(self.entry.data.get(CONF_SOLAR_FALLBACK_END_MONTH, 9)),
                    float(self.entry.data.get(CONF_SOLAR_FALLBACK_SUNRISE_DELAY_H, 3)),
                    float(self.entry.data.get(CONF_SOLAR_FALLBACK_SUNSET_ADVANCE_H, 2)),
                )
                if fallback_hours:
                    solar_source = "fallback"
                    warnings.append("solar_fallback_active")
                else:
                    warnings.append("solar_fallback_no_active_hours")
            except Exception as err:  # noqa: BLE001
                warnings.append(f"solar_fallback_error: {err}")
        elif solar_missing:
            warnings.append("solar_fallback_disabled")

        current_hour = now.replace(minute=0, second=0, microsecond=0)
        forced_states: dict[str, dict[float, bool]] = {}
        if not shadow_mode:
            for subentry in self.device_subentries:
                state = self.states[subentry.subentry_id]
                if (
                    state.locked_hour_start is not None
                    and state.locked_active is not None
                    and state.locked_hour_start.timestamp() == current_hour.timestamp()
                ):
                    forced_states[subentry.subentry_id] = {
                        current_hour.timestamp(): state.locked_active
                    }
        plans = build_plans(
            planning_hours,
            planning_devices,
            targets,
            forced_states,
            minimum_targets,
        )
        for subentry in self.device_subentries:
            plan = plans.get(subentry.subentry_id)
            if plan is None:
                continue
            missing_weather = bool(subentry.data[CONF_USE_WEATHER]) and any(
                day not in apparent_temperatures.get(subentry.subentry_id, {})
                for day in available_days
            )
            if missing_weather:
                plan.valid = False
                plan.error = "weather_forecast_missing"
                plan.hours = []
        for device_id, plan in plans.items():
            state = self.states[device_id]
            plan.required_hours = required_hours.get(device_id, {})
            plan.apparent_temperatures = apparent_temperatures.get(device_id, {})
            state.next_transition = self._next_transition_in_plan(plan, now)
            if not shadow_mode and (
                state.locked_hour_start is None
                or state.locked_hour_start.timestamp() != current_hour.timestamp()
            ):
                for hour in plan.hours:
                    if hour.start.timestamp() == current_hour.timestamp():
                        state.locked_hour_start = current_hour
                        state.locked_active = hour.active
                        break
        data = SchedulerData(
            generated_at=now,
            hours=hours,
            plans=plans,
            temperatures={
                day.isoformat(): value
                for day, value in next(iter(apparent_temperatures.values()), {}).items()
            },
            warnings=warnings,
            solar_source=solar_source,
        )
        return data

    def _observed_active(self, subentry: ConfigSubentry) -> bool | None:
        """Resolve physical activity from power, feedback, or target state."""
        data = subentry.data
        power_entity = data.get(CONF_POWER_SENSOR)
        if power_entity and (state := self.hass.states.get(power_entity)) is not None:
            try:
                return float(state.state) * float(data.get(CONF_POWER_MULTIPLIER, 1)) > 10.0
            except (TypeError, ValueError):
                pass
        feedback = data.get(CONF_FEEDBACK_ENTITY)
        if (
            feedback
            and (state := self.hass.states.get(feedback)) is not None
            and state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE)
        ):
            return state.state in ("on", "open", "opening", "heat", "heating", "active")
        state = self.hass.states.get(data[CONF_TARGET_ENTITY])
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return None
        output_on = state.state == "on"
        return not output_on if data[CONF_INVERTED] else output_on

    async def async_account_actual(self, now: datetime | None = None) -> None:
        """Integrate observed run time, splitting correctly at local midnight."""
        now = now or dt_util.now().astimezone(self.timezone)
        for subentry in self.device_subentries:
            state = self.states.setdefault(subentry.subentry_id, DeviceRuntimeState())
            active = self._observed_active(subentry)
            if state.last_accounted_at and state.last_active:
                cursor = state.last_accounted_at.astimezone(self.timezone)
                end = now.astimezone(self.timezone)
                # Ignore implausibly large gaps; HA was not observing the device then.
                if timedelta(0) <= end - cursor <= timedelta(hours=1):
                    while cursor < end:
                        midnight = datetime.combine(
                            cursor.date() + timedelta(days=1),
                            datetime.min.time(),
                            tzinfo=self.timezone,
                        )
                        segment_end = min(end, midnight)
                        key = cursor.date().isoformat()
                        state.actual_hours_by_day[key] = (
                            state.actual_hours_by_day.get(key, 0.0)
                            + (segment_end - cursor).total_seconds() / 3600
                        )
                        cursor = segment_end
            state.last_active = active
            state.last_accounted_at = now
            cutoff = now.date() - timedelta(days=7)
            state.actual_hours_by_day = {
                key: value
                for key, value in state.actual_hours_by_day.items()
                if date.fromisoformat(key) >= cutoff
            }
        await self.async_save_state()

    def planned_active(self, device_id: str, moment: datetime | None = None) -> bool | None:
        """Return the plan state for the absolute current hour."""
        if not self.data or (plan := self.data.plans.get(device_id)) is None:
            return None
        moment = (moment or dt_util.now()).astimezone(self.timezone)
        for hour in plan.hours:
            if hour.start.timestamp() <= moment.timestamp() < hour.start.timestamp() + 3600:
                return hour.active
        return None

    async def async_apply_outputs(self) -> None:
        """Apply plan/override safely; never issue toggle commands."""
        async with self._apply_lock:
            now = dt_util.now().astimezone(self.timezone)
            for subentry in self.device_subentries:
                data = subentry.data
                state = self.states[subentry.subentry_id]
                if (
                    state.override != OVERRIDE_AUTO
                    and state.override_until
                    and now >= state.override_until
                ):
                    state.override = OVERRIDE_AUTO
                    state.override_until = None
                if not state.enabled:
                    state.reason = "disabled"
                    continue
                if state.override == OVERRIDE_ON:
                    desired = True
                    reason = "override_on"
                elif state.override == OVERRIDE_OFF:
                    desired = False
                    reason = "override_off"
                else:
                    desired = self.planned_active(subentry.subentry_id, now)
                    reason = "schedule"
                    if desired is None:
                        failure = data[CONF_FAILURE_MODE]
                        if failure == FAILURE_FORCE_ON:
                            desired, reason = True, "failure_force_on"
                        elif failure == FAILURE_FORCE_OFF:
                            desired, reason = False, "failure_force_off"
                        else:
                            state.reason = "failure_keep"
                            continue
                        if not self.entry.data[CONF_SHADOW_MODE]:
                            current_hour = now.replace(minute=0, second=0, microsecond=0)
                            state.locked_hour_start = current_hour
                            state.locked_active = desired
                state.reason = "shadow_" + reason if self.entry.data[CONF_SHADOW_MODE] else reason
                state.next_transition = self._next_transition(subentry.subentry_id, now)
                if self.entry.data[CONF_SHADOW_MODE]:
                    continue
                await self._async_set_target(subentry, bool(desired))
            await self.async_save_state()
            if self.data is not None:
                # Publish only after overrides, failure behavior, expiry, and the
                # resulting output reason have all been applied. The Lovelace
                # subscription must not remain stale until the next recalculation.
                self.hass.bus.async_fire(EVENT_PLAN_UPDATED, self.as_dict())

    async def _async_set_target(self, subentry: ConfigSubentry, active: bool) -> None:
        """Set an explicit state using generic HA turn_on/turn_off services."""
        data = subentry.data
        target = data[CONF_TARGET_ENTITY]
        current = self.hass.states.get(target)
        if current is None or current.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            self.states[subentry.subentry_id].reason = "target_unavailable"
            return
        output_on = output_should_be_on(active, bool(data[CONF_INVERTED]))
        if (current.state == "on") == output_on:
            return
        await self.hass.services.async_call(
            "homeassistant",
            "turn_on" if output_on else "turn_off",
            {"entity_id": target},
            blocking=True,
        )

    def _next_transition(self, device_id: str, now: datetime) -> datetime | None:
        if not self.data or (plan := self.data.plans.get(device_id)) is None:
            return None
        return self._next_transition_in_plan(plan, now)

    @staticmethod
    def _next_transition_in_plan(plan: DevicePlan, now: datetime) -> datetime | None:
        """Return the next planned ON/OFF boundary in one device plan."""
        current = plan.active_at(now)
        if current is None:
            return None
        for hour in plan.hours:
            if hour.start.timestamp() > now.timestamp() and hour.active != current:
                return hour.start
        return None

    async def async_set_override(
        self, device_id: str, mode: str, until: datetime | None = None
    ) -> None:
        """Set a device override and apply it immediately."""
        if device_id not in self.states:
            raise ValueError(f"Unknown scheduler device {device_id}")
        state = self.states[device_id]
        state.override = mode
        state.override_until = until if mode != OVERRIDE_AUTO else None
        await self.async_apply_outputs()

    def as_dict(self, data: SchedulerData | None = None) -> dict[str, Any]:
        """Serialize the 48-hour plan for frontend and diagnostics."""
        data = data or self.data
        if data is None:
            return {"entry_id": self.entry.entry_id, "ready": False}
        return {
            "entry_id": self.entry.entry_id,
            "generated_at": data.generated_at.isoformat(),
            "shadow_mode": self.entry.data[CONF_SHADOW_MODE],
            "error": data.error,
            "warnings": data.warnings,
            "solar_source": data.solar_source,
            "temperatures": data.temperatures,
            "diagnostics": {
                "grid_power": self._numeric_state(self.entry.data.get("grid_power_sensor")),
                "pv_power": self._numeric_state(self.entry.data.get("pv_power_sensor")),
            },
            "hours": [
                {
                    "start": hour.start.isoformat(),
                    "market_eur_mwh": round(hour.market_eur_mwh, 4),
                    "import_eur_mwh": round(hour.import_eur_mwh, 4),
                    "export_eur_mwh": round(hour.export_eur_mwh, 4),
                    "pv_wh": round(hour.pv_wh, 1),
                    "base_load_wh": round(hour.base_load_wh, 1),
                    "surplus_wh": round(hour.surplus_wh, 1),
                }
                for hour in data.hours
            ],
            "devices": {
                subentry.subentry_id: {
                    "name": subentry.title,
                    "target_entity": subentry.data[CONF_TARGET_ENTITY],
                    "inverted": subentry.data[CONF_INVERTED],
                    "feedback_entity": subentry.data.get(CONF_FEEDBACK_ENTITY),
                    "power_sensor": subentry.data.get(CONF_POWER_SENSOR),
                    "power_multiplier": subentry.data.get(CONF_POWER_MULTIPLIER, 1),
                    "settings": {
                        CONF_BASE_HOURS: float(subentry.data[CONF_BASE_HOURS]),
                        CONF_MIN_HOURS: float(subentry.data[CONF_MIN_HOURS]),
                        CONF_MAX_HOURS: float(subentry.data[CONF_MAX_HOURS]),
                        CONF_ALWAYS_ON_BELOW: (
                            float(subentry.data[CONF_ALWAYS_ON_BELOW])
                            if CONF_ALWAYS_ON_BELOW in subentry.data
                            else None
                        ),
                        CONF_ALWAYS_OFF_ABOVE: (
                            float(subentry.data[CONF_ALWAYS_OFF_ABOVE])
                            if CONF_ALWAYS_OFF_ABOVE in subentry.data
                            else None
                        ),
                        CONF_REFERENCE_TEMPERATURE: float(
                            subentry.data[CONF_REFERENCE_TEMPERATURE]
                        ),
                        CONF_HOURS_PER_DEGREE: float(subentry.data[CONF_HOURS_PER_DEGREE]),
                        CONF_WEATHER_LOOKAHEAD_HOURS: float(
                            subentry.data.get(CONF_WEATHER_LOOKAHEAD_HOURS, 12)
                        ),
                        CONF_PREHEAT_HOURS: float(subentry.data.get(CONF_PREHEAT_HOURS, 0)),
                        CONF_LEGACY_WIND_CHILL: bool(
                            subentry.data.get(CONF_LEGACY_WIND_CHILL, True)
                        ),
                    },
                    "state": {
                        "enabled": self.states[subentry.subentry_id].enabled,
                        "override": self.states[subentry.subentry_id].override,
                        "override_until": self.states[
                            subentry.subentry_id
                        ].override_until.isoformat()
                        if self.states[subentry.subentry_id].override_until
                        else None,
                        "actual_hours_by_day": self.states[
                            subentry.subentry_id
                        ].actual_hours_by_day,
                        "next_transition": self.states[
                            subentry.subentry_id
                        ].next_transition.isoformat()
                        if self.states[subentry.subentry_id].next_transition
                        else None,
                        "reason": self.states[subentry.subentry_id].reason,
                        "observed_active": self._observed_active(subentry),
                    },
                    "plan": data.plans.get(subentry.subentry_id).as_dict()
                    if subentry.subentry_id in data.plans
                    else None,
                }
                for subentry in self.device_subentries
            },
        }

    def _numeric_state(self, entity_id: str | None) -> float | None:
        """Read an optional diagnostics sensor without affecting planning."""
        if not entity_id or (state := self.hass.states.get(entity_id)) is None:
            return None
        try:
            return float(state.state)
        except (TypeError, ValueError):
            return None
