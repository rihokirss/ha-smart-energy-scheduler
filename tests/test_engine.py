"""Tests for pricing, weather, solar allocation, and scheduling."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.smart_energy_scheduler.engine import (
    aggregate_hourly,
    build_plans,
    merge_solar_forecast,
    output_should_be_on,
    parse_nordpool_response,
    weather_target_hours,
)
from custom_components.smart_energy_scheduler.models import (
    HourPrice,
    PlanningDevice,
    QuarterPrice,
    TariffConfig,
)

TALLINN = ZoneInfo("Europe/Tallinn")


def tariff(**changes) -> TariffConfig:
    values = {
        "buy_margin": 2.44,
        "sell_margin": -4.5,
        "vat_fraction": 0.22,
        "network_day": 36.9,
        "network_night": 21.0,
        "day_start": time(7),
        "day_end": time(22),
        "weekend_night": True,
    }
    return TariffConfig(**(values | changes))


def quarter_series(start: datetime, count: int, price: float = 100.0):
    return [
        QuarterPrice(
            start + timedelta(minutes=15 * i), start + timedelta(minutes=15 * (i + 1)), price
        )
        for i in range(count)
    ]


def test_parse_nordpool_multi_area_response() -> None:
    payload = {
        "multiAreaEntries": [
            {
                "deliveryStart": "2026-08-20T00:00:00Z",
                "deliveryEnd": "2026-08-20T00:15:00Z",
                "entryPerArea": {"EE": 42.5, "FI": 40.0},
            }
        ]
    }
    result = parse_nordpool_response(payload, "EE")
    assert len(result) == 1
    assert result[0].market_eur_mwh == 42.5


def test_parse_nordpool_missing_day_response_is_empty() -> None:
    assert parse_nordpool_response(None, "EE") == []


def test_four_quarters_are_duration_weighted() -> None:
    start = datetime(2026, 8, 20, 4, tzinfo=UTC)  # 07:00 Tallinn
    quarters = [
        QuarterPrice(
            start + timedelta(minutes=15 * i), start + timedelta(minutes=15 * (i + 1)), price
        )
        for i, price in enumerate((10, 20, 30, 40))
    ]
    result = aggregate_hourly(quarters, tariff(), TALLINN)
    assert len(result) == 1
    assert result[0].market_eur_mwh == 25
    assert result[0].import_eur_mwh == pytest.approx((25 + 2.44 + 36.9) * 1.22)
    assert result[0].export_eur_mwh == pytest.approx(20.5)


def test_tariff_is_applied_per_quarter_before_hourly_average() -> None:
    start = datetime(2026, 8, 20, 4, tzinfo=UTC)  # 07:00 local
    result = aggregate_hourly(quarter_series(start, 4), tariff(day_start=time(7, 30)), TALLINN)[0]
    expected = ((100 + 2.44 + 21.0) * 1.22 + (100 + 2.44 + 36.9) * 1.22) / 2
    assert result.import_eur_mwh == pytest.approx(expected)


def test_weekend_uses_night_tariff() -> None:
    saturday = datetime(2026, 8, 22, 9, tzinfo=TALLINN).astimezone(UTC)
    result = aggregate_hourly(quarter_series(saturday, 4), tariff(), TALLINN)[0]
    assert result.import_eur_mwh == pytest.approx((100 + 2.44 + 21.0) * 1.22)


@pytest.mark.parametrize(
    ("day", "expected"),
    [(date(2026, 3, 29), 23), (date(2026, 10, 25), 25)],
)
def test_dst_days_keep_absolute_hours(day: date, expected: int) -> None:
    local_start = datetime.combine(day, time(), tzinfo=TALLINN)
    local_end = datetime.combine(day + timedelta(days=1), time(), tzinfo=TALLINN)
    count = round((local_end.astimezone(UTC) - local_start.astimezone(UTC)).total_seconds() / 900)
    result = aggregate_hourly(quarter_series(local_start.astimezone(UTC), count), tariff(), TALLINN)
    assert len(result) == expected
    assert len({slot.start.timestamp() for slot in result}) == expected


def test_weather_target_uses_apparent_temperature_and_clamps() -> None:
    assert weather_target_hours(9, 6, 0, 0.5, 3, 24) == 12
    assert weather_target_hours(9, 6, -50, 0.5, 3, 24) == 24
    assert weather_target_hours(9, 6, 50, 0.5, 3, 24) == 3
    assert weather_target_hours(9, 6, None, 0.5, 3, 24) == 9


def test_solar_forecasts_are_summed_and_base_load_removed() -> None:
    start = datetime(2026, 8, 20, 10, tzinfo=TALLINN)
    hours = [HourPrice(start, start + timedelta(hours=1), 50, 100, 45)]
    merge_solar_forecast(
        hours,
        [{start.isoformat(): 800}, {start.isoformat(): 700}],
        base_load_w=500,
    )
    assert hours[0].pv_wh == 1500
    assert hours[0].surplus_wh == 1000


def test_shared_pv_is_not_double_counted() -> None:
    start = datetime(2026, 8, 20, 10, tzinfo=TALLINN)
    hours = [
        HourPrice(start, start + timedelta(hours=1), 50, 100, 40, pv_wh=2000, base_load_wh=500)
    ]
    devices = [
        PlanningDevice("first", "First", 1000, time(), time(), 1, 1, 1),
        PlanningDevice("second", "Second", 1000, time(), time(), 1, 1, 2),
    ]
    targets = {device.device_id: {start.date(): 1} for device in devices}
    plans = build_plans(hours, devices, targets)
    assert plans["first"].hours[0].allocated_solar_wh == 1000
    assert plans["second"].hours[0].allocated_solar_wh == 500


def test_minimum_on_and_off_runs_are_enforced() -> None:
    start = datetime(2026, 8, 20, tzinfo=TALLINN)
    hours = [
        HourPrice(start + timedelta(hours=i), start + timedelta(hours=i + 1), price, price, price)
        for i, price in enumerate((1, 2, 100, 100, 3, 4, 100, 100))
    ]
    device = PlanningDevice("load", "Load", 1000, time(), time(), 2, 2, 1)
    plan = build_plans(hours, [device], {"load": {start.date(): 4}})["load"]
    states = [slot.active for slot in plan.hours]
    assert plan.valid
    assert states == [True, True, False, False, True, True, False, False]


def test_unsatisfiable_constraints_return_invalid_plan() -> None:
    start = datetime(2026, 8, 20, tzinfo=TALLINN)
    hours = [HourPrice(start, start + timedelta(hours=1), 1, 1, 1)]
    device = PlanningDevice("load", "Load", 1000, time(), time(), 2, 1, 1)
    plan = build_plans(hours, [device], {"load": {start.date(): 1}})["load"]
    assert not plan.valid
    assert plan.error == "constraints_unsatisfiable"


def test_current_hour_can_be_locked_across_recalculation() -> None:
    start = datetime(2026, 8, 20, tzinfo=TALLINN)
    hours = [
        HourPrice(
            start + timedelta(hours=i),
            start + timedelta(hours=i + 1),
            price,
            price,
            price,
        )
        for i, price in enumerate((100, 1, 2))
    ]
    device = PlanningDevice("load", "Load", 1000, time(), time(), 1, 1, 1)
    plan = build_plans(
        hours,
        [device],
        {"load": {start.date(): 1}},
        {"load": {start.timestamp(): True}},
    )["load"]
    assert plan.valid
    assert [slot.active for slot in plan.hours] == [True, False, False]


@pytest.mark.parametrize(
    ("active", "inverted", "physical_on"),
    [(True, False, True), (False, False, False), (True, True, False), (False, True, True)],
)
def test_explicit_output_mapping(active: bool, inverted: bool, physical_on: bool) -> None:
    assert output_should_be_on(active, inverted) is physical_on
