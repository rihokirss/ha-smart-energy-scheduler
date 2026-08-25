"""Tests for pricing, weather, solar allocation, and scheduling."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.smart_energy_scheduler.engine import (
    aggregate_hourly,
    apply_solar_window_fallback,
    build_plans,
    distribute_hour_energy,
    forecast_window_average,
    is_complete_price_day,
    is_day_tariff,
    is_estonian_public_holiday,
    legacy_wind_chill,
    merge_solar_forecast,
    month_in_range,
    output_should_be_on,
    parse_nordpool_response,
    price_intervals,
    protect_minimum_cycle,
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
        "vat_fraction": 0.24,
        "network_day": 75.3,
        "network_night": 43.5,
        "day_start": time(7),
        "day_end": time(22),
        "weekend_night": True,
        "network_includes_vat": True,
        "holiday_country": "EE",
    }
    return TariffConfig(**(values | changes))


def quarter_series(start: datetime, count: int, price: float = 100.0):
    return [
        QuarterPrice(
            start + timedelta(minutes=15 * i), start + timedelta(minutes=15 * (i + 1)), price
        )
        for i in range(count)
    ]


def test_hourly_solar_energy_is_distributed_over_quarter_slots() -> None:
    start = datetime(2026, 8, 20, 10, tzinfo=TALLINN)
    quarters = quarter_series(start, 4)
    hours = aggregate_hourly(quarters, tariff(), TALLINN)
    slots = price_intervals(quarters, tariff(), TALLINN)
    merge_solar_forecast(hours, [{start.isoformat(): 4000}], 400)

    distribute_hour_energy(hours, slots)

    assert [slot.pv_wh for slot in slots] == [1000, 1000, 1000, 1000]
    assert [slot.base_load_wh for slot in slots] == [100, 100, 100, 100]


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


def test_complete_price_day_accepts_normal_and_dst_slot_counts() -> None:
    start = datetime(2026, 8, 20, tzinfo=UTC)

    assert is_complete_price_day(quarter_series(start, 96))
    assert is_complete_price_day(quarter_series(start, 92))
    assert is_complete_price_day(quarter_series(start, 100))


def test_complete_price_day_rejects_partial_or_gapped_response() -> None:
    start = datetime(2026, 8, 20, tzinfo=UTC)
    gapped = quarter_series(start, 96)
    gapped[40] = QuarterPrice(
        gapped[40].start + timedelta(minutes=15),
        gapped[40].end + timedelta(minutes=15),
        gapped[40].market_eur_mwh,
    )

    assert not is_complete_price_day(quarter_series(start, 95))
    assert not is_complete_price_day(gapped)


def test_parse_nordpool_missing_day_response_is_empty() -> None:
    assert parse_nordpool_response(None, "EE") == []


def test_four_quarters_are_duration_weighted() -> None:
    start = datetime(2026, 8, 19, 4, tzinfo=UTC)  # 07:00 Tallinn
    quarters = [
        QuarterPrice(
            start + timedelta(minutes=15 * i), start + timedelta(minutes=15 * (i + 1)), price
        )
        for i, price in enumerate((10, 20, 30, 40))
    ]
    result = aggregate_hourly(quarters, tariff(), TALLINN)
    assert len(result) == 1
    assert result[0].market_eur_mwh == 25
    assert result[0].import_eur_mwh == pytest.approx((25 + 2.44) * 1.24 + 75.3)
    assert result[0].export_eur_mwh == pytest.approx(20.5)


def test_tariff_is_applied_per_quarter_before_hourly_average() -> None:
    start = datetime(2026, 8, 19, 4, tzinfo=UTC)  # 07:00 local
    result = aggregate_hourly(quarter_series(start, 4), tariff(day_start=time(7, 30)), TALLINN)[0]
    energy = (100 + 2.44) * 1.24
    expected = (energy + 43.5 + energy + 75.3) / 2
    assert result.import_eur_mwh == pytest.approx(expected)


def test_weekend_uses_night_tariff() -> None:
    saturday = datetime(2026, 8, 22, 9, tzinfo=TALLINN).astimezone(UTC)
    result = aggregate_hourly(quarter_series(saturday, 4), tariff(), TALLINN)[0]
    assert result.import_eur_mwh == pytest.approx((100 + 2.44) * 1.24 + 43.5)


def test_vat_inclusive_network_fee_is_not_taxed_twice() -> None:
    start = datetime(2026, 8, 19, 9, tzinfo=TALLINN).astimezone(UTC)
    result = aggregate_hourly(quarter_series(start, 4), tariff(), TALLINN)[0]
    assert result.import_eur_mwh == pytest.approx((100 + 2.44) * 1.24 + 75.3)


def test_vat_exclusive_network_fee_can_still_be_configured() -> None:
    start = datetime(2026, 8, 19, 9, tzinfo=TALLINN).astimezone(UTC)
    result = aggregate_hourly(
        quarter_series(start, 4),
        tariff(network_day=60.725806, network_includes_vat=False),
        TALLINN,
    )[0]
    assert result.import_eur_mwh == pytest.approx((100 + 2.44) * 1.24 + 75.3)


@pytest.mark.parametrize(
    "holiday",
    [date(2026, 2, 24), date(2026, 4, 3), date(2026, 6, 23), date(2026, 8, 20)],
)
def test_estonian_public_holidays_use_night_tariff(holiday: date) -> None:
    assert is_estonian_public_holiday(holiday)
    moment = datetime.combine(holiday, time(12), tzinfo=TALLINN)
    assert not is_day_tariff(moment, tariff())


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


def test_weather_uses_rolling_next_12_hour_average_like_previous_yaml() -> None:
    now = datetime(2026, 1, 15, 10, 30, tzinfo=TALLINN)
    samples = [
        (now.replace(minute=0) + timedelta(hours=index + 1), float(index)) for index in range(24)
    ]
    average = forecast_window_average(samples, now.date(), now, TALLINN, 12, 0)
    assert average == pytest.approx(sum(range(12)) / 12)


def test_forecast_lead_reacts_to_later_cold_for_high_inertia() -> None:
    now = datetime(2026, 1, 15, 10, tzinfo=TALLINN)
    samples = [(now + timedelta(hours=index), 5.0 if index < 6 else -10.0) for index in range(24)]
    immediate = forecast_window_average(samples, now.date(), now, TALLINN, 12, 0)
    shifted = forecast_window_average(samples, now.date(), now, TALLINN, 12, 6)
    assert immediate == pytest.approx(-2.5)
    assert shifted == pytest.approx(-10.0)


def test_legacy_wind_chill_matches_previous_yaml_formula() -> None:
    expected = 13.2 + 0.6215 * 16.7 - 11.37 * 6.88**0.16 + 0.3965 * 16.7 * 6.88**0.16
    assert legacy_wind_chill(16.7, 6.88) == pytest.approx(expected)


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


def test_solar_fallback_matches_previous_month_and_sun_offsets() -> None:
    day = date(2026, 8, 20)
    hours = [
        HourPrice(
            datetime.combine(day, time(hour), tzinfo=TALLINN),
            datetime.combine(day, time(hour), tzinfo=TALLINN) + timedelta(hours=1),
            50,
            100,
            45,
        )
        for hour in range(24)
    ]
    applied = apply_solar_window_fallback(
        hours,
        {
            day: (
                datetime.combine(day, time(5, 30), tzinfo=TALLINN),
                datetime.combine(day, time(21), tzinfo=TALLINN),
            )
        },
        base_load_w=500,
        controlled_load_w=2500,
        start_month=3,
        end_month=9,
        sunrise_delay_h=3,
        sunset_advance_h=2,
    )
    assert applied == 10
    assert hours[8].pv_wh == 0
    assert hours[9].pv_wh == 3000
    assert hours[9].surplus_wh == 2500
    assert hours[18].pv_wh == 3000
    assert hours[19].pv_wh == 0


def test_solar_fallback_is_disabled_outside_previous_month_range() -> None:
    day = date(2026, 2, 20)
    start = datetime.combine(day, time(12), tzinfo=TALLINN)
    hours = [HourPrice(start, start + timedelta(hours=1), 50, 100, 45)]
    applied = apply_solar_window_fallback(
        hours,
        {day: (start - timedelta(hours=6), start + timedelta(hours=6))},
        base_load_w=500,
        controlled_load_w=2500,
        start_month=3,
        end_month=9,
        sunrise_delay_h=3,
        sunset_advance_h=2,
    )
    assert applied == 0
    assert hours[0].pv_wh == 0
    assert hours[0].base_load_wh == 500


def test_solar_fallback_month_range_can_wrap_new_year() -> None:
    assert month_in_range(12, 10, 2)
    assert month_in_range(1, 10, 2)
    assert not month_in_range(6, 10, 2)


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


def test_locked_quarter_expands_completed_daily_target_to_minimum_run() -> None:
    start = datetime(2026, 8, 20, tzinfo=TALLINN)
    slots = [
        HourPrice(
            start + timedelta(minutes=15 * i),
            start + timedelta(minutes=15 * (i + 1)),
            100,
            100,
            100,
        )
        for i in range(8)
    ]
    device = PlanningDevice(
        "load", "Load", 1000, time(), time(), 1, 1, 1, planning_step_minutes=15
    )

    plan = build_plans(
        slots,
        [device],
        {"load": {start.date(): 0}},
        forced_states={"load": {start.timestamp(): True}},
    )["load"]

    assert plan.valid
    assert plan.target_hours[start.date()] == 1
    assert [slot.active for slot in plan.hours] == [True, True, True, True, False, False, False, False]


def test_mid_slot_cycle_start_does_not_credit_a_full_quarter() -> None:
    start = datetime(2026, 8, 20, tzinfo=TALLINN)
    slots = [
        HourPrice(
            start + timedelta(minutes=15 * i),
            start + timedelta(minutes=15 * (i + 1)),
            100,
            100,
            100,
        )
        for i in range(8)
    ]
    device = PlanningDevice(
        "load", "Load", 1000, time(), time(), 1, 1, 1, planning_step_minutes=15
    )

    plan = build_plans(
        slots,
        [device],
        {"load": {start.date(): 0}},
        forced_states={"load": {start.timestamp(): True}},
        initial_states={"load": (True, -1)},
    )["load"]

    assert plan.valid
    assert plan.target_hours[start.date()] == 1.25
    assert [slot.active for slot in plan.hours] == [
        True,
        True,
        True,
        True,
        True,
        False,
        False,
        False,
    ]


def test_device_always_on_price_expands_daily_target() -> None:
    start = datetime(2026, 8, 20, tzinfo=TALLINN)
    hours = [
        HourPrice(
            start + timedelta(hours=i),
            start + timedelta(hours=i + 1),
            price,
            price,
            price,
        )
        for i, price in enumerate((-20, -10, 100, 200))
    ]
    device = PlanningDevice(
        "load", "Load", 1000, time(), time(), 1, 1, 1, always_on_below_eur_mwh=0
    )
    plan = build_plans(hours, [device], {"load": {start.date(): 1}})["load"]

    assert plan.valid
    assert plan.target_hours[start.date()] == 2
    assert [slot.active for slot in plan.hours] == [True, True, False, False]
    assert plan.hours[0].reason == "below_always_on_price"


def test_always_on_price_expands_run_to_device_minimum() -> None:
    start = datetime(2026, 8, 20, tzinfo=TALLINN)
    prices = (100, -10, -10)
    hours = [
        HourPrice(
            start + timedelta(hours=i),
            start + timedelta(hours=i + 1),
            price,
            price,
            price,
        )
        for i, price in enumerate(prices)
    ]
    device = PlanningDevice(
        "load", "Load", 1000, time(), time(), 2, 1, 1, always_on_below_eur_mwh=0
    )
    plan = build_plans(hours, [device], {"load": {start.date(): 1}})["load"]

    assert plan.valid
    assert plan.target_hours[start.date()] == 2
    assert plan.hours[1].active


def test_always_on_threshold_checks_every_slot_in_minimum_block() -> None:
    start = datetime(2026, 8, 20, tzinfo=TALLINN)
    hours = [
        HourPrice(
            start + timedelta(hours=i),
            start + timedelta(hours=i + 1),
            price,
            price,
            price,
        )
        for i, price in enumerate((40, 40, 60, 60))
    ]
    device = PlanningDevice(
        "load", "Load", 1000, time(), time(), 2, 1, 1, always_on_below_eur_mwh=50
    )
    plan = build_plans(hours, [device], {"load": {start.date(): 1}})["load"]

    assert plan.valid
    assert plan.target_hours[start.date()] == 2
    assert [slot.active for slot in plan.hours] == [True, True, False, False]


def test_isolated_cheap_slot_does_not_create_expensive_minimum_run() -> None:
    start = datetime(2026, 8, 20, tzinfo=TALLINN)
    hours = [
        HourPrice(
            start + timedelta(hours=i),
            start + timedelta(hours=i + 1),
            price,
            price,
            price,
        )
        for i, price in enumerate((60, 40, 60))
    ]
    device = PlanningDevice(
        "load", "Load", 1000, time(), time(), 2, 1, 1, always_on_below_eur_mwh=50
    )
    plan = build_plans(hours, [device], {"load": {start.date(): 0}})["load"]

    assert plan.valid
    assert plan.target_hours[start.date()] == 0
    assert not any(slot.active for slot in plan.hours)


def test_device_always_off_price_caps_weather_target() -> None:
    start = datetime(2026, 8, 20, tzinfo=TALLINN)
    prices = (10, 20, 100, 200)
    hours = [
        HourPrice(
            start + timedelta(hours=i),
            start + timedelta(hours=i + 1),
            price,
            price,
            price,
        )
        for i, price in enumerate(prices)
    ]
    device = PlanningDevice(
        "load", "Load", 1000, time(), time(), 1, 1, 1, always_off_above_eur_mwh=50
    )
    plan = build_plans(
        hours,
        [device],
        {"load": {start.date(): 4}},
        minimum_targets={"load": {start.date(): 1}},
    )["load"]

    assert plan.valid
    assert plan.target_hours[start.date()] == 2
    assert [slot.active for slot in plan.hours] == [True, True, False, False]
    assert plan.hours[2].reason == "above_always_off_price"


def test_maximum_price_drops_weather_hours_that_cannot_form_a_safe_run() -> None:
    start = datetime(2026, 8, 20, tzinfo=TALLINN)
    prices = (10, 500, 10, 500)
    hours = [
        HourPrice(
            start + timedelta(hours=i),
            start + timedelta(hours=i + 1),
            price,
            price,
            price,
        )
        for i, price in enumerate(prices)
    ]
    device = PlanningDevice(
        "load", "Load", 1000, time(), time(), 2, 1, 1, always_off_above_eur_mwh=100
    )
    plan = build_plans(
        hours,
        [device],
        {"load": {start.date(): 4}},
        minimum_targets={"load": {start.date(): 0}},
    )["load"]

    assert plan.valid
    assert plan.target_hours[start.date()] == 0
    assert not any(slot.active for slot in plan.hours)


def test_daily_minimum_can_override_always_off_price() -> None:
    start = datetime(2026, 8, 20, tzinfo=TALLINN)
    prices = (10, 100, 200)
    hours = [
        HourPrice(
            start + timedelta(hours=i),
            start + timedelta(hours=i + 1),
            price,
            price,
            price,
        )
        for i, price in enumerate(prices)
    ]
    device = PlanningDevice(
        "load", "Load", 1000, time(), time(), 1, 1, 1, always_off_above_eur_mwh=50
    )
    plan = build_plans(
        hours,
        [device],
        {"load": {start.date(): 3}},
        minimum_targets={"load": {start.date(): 3}},
    )["load"]

    assert plan.valid
    assert [slot.active for slot in plan.hours] == [True, True, True]
    assert plan.hours[1].reason == "minimum_hours_override"


def test_quarter_hour_device_selects_cheapest_rolling_hour() -> None:
    start = datetime(2026, 8, 20, tzinfo=TALLINN)
    prices = (100, 1, 1, 1, 1, 100, 100, 100)
    slots = [
        HourPrice(
            start + timedelta(minutes=15 * i),
            start + timedelta(minutes=15 * (i + 1)),
            price,
            price,
            price,
        )
        for i, price in enumerate(prices)
    ]
    device = PlanningDevice("load", "Load", 1000, time(), time(), 1, 1, 1, planning_step_minutes=15)

    plan = build_plans(slots, [device], {"load": {start.date(): 1}})["load"]

    assert plan.valid
    active = [slot.start for slot in plan.hours if slot.active]
    assert active == [start + timedelta(minutes=15 * i) for i in range(1, 5)]


def test_optimizer_keeps_costly_quarter_between_cheaper_blocks() -> None:
    """A short costly bridge can be cheaper than enforcing a separate cycle."""
    start = datetime(2026, 8, 20, tzinfo=TALLINN)
    prices = (1, 1, 1, 1, 80, 1, 1, 1, 1, 500, 500, 500)
    slots = [
        HourPrice(
            start + timedelta(minutes=15 * i),
            start + timedelta(minutes=15 * (i + 1)),
            price,
            price,
            price,
        )
        for i, price in enumerate(prices)
    ]
    device = PlanningDevice(
        "load", "Load", 1000, time(), time(), 1, 1, 1, planning_step_minutes=15
    )

    plan = build_plans(slots, [device], {"load": {start.date(): 2}})["load"]

    assert plan.valid
    assert plan.hours[4].active
    assert [index for index, slot in enumerate(plan.hours) if slot.active] == list(range(1, 9))


def test_forced_cheap_blocks_expand_target_to_bridge_short_off_gap() -> None:
    """Forced cheap runs remain one safe cycle when the OFF gap is too short."""
    start = datetime(2026, 8, 20, tzinfo=TALLINN)
    prices = (10, 10, 10, 10, 80, 10, 10, 10, 10)
    slots = [
        HourPrice(
            start + timedelta(minutes=15 * i),
            start + timedelta(minutes=15 * (i + 1)),
            price,
            price,
            price,
        )
        for i, price in enumerate(prices)
    ]
    device = PlanningDevice(
        "load",
        "Load",
        1000,
        time(),
        time(),
        1,
        1,
        1,
        planning_step_minutes=15,
        always_on_below_eur_mwh=50,
    )

    plan = build_plans(slots, [device], {"load": {start.date(): 0}})["load"]

    assert plan.valid
    assert plan.target_hours[start.date()] == 2.25
    assert all(slot.active for slot in plan.hours)


def test_hour_grid_device_cannot_start_on_quarter_hour() -> None:
    start = datetime(2026, 8, 20, tzinfo=TALLINN)
    prices = (100, 1, 1, 1, 1, 100, 100, 100)
    slots = [
        HourPrice(
            start + timedelta(minutes=15 * i),
            start + timedelta(minutes=15 * (i + 1)),
            price,
            price,
            price,
        )
        for i, price in enumerate(prices)
    ]
    device = PlanningDevice("load", "Load", 1000, time(), time(), 1, 1, 1, planning_step_minutes=60)

    plan = build_plans(slots, [device], {"load": {start.date(): 1}})["load"]

    assert plan.valid
    active = [slot.start for slot in plan.hours if slot.active]
    assert active == [start + timedelta(minutes=15 * i) for i in range(4)]


def test_quarter_hour_maximum_price_rejects_an_extreme_inside_run() -> None:
    start = datetime(2026, 8, 20, tzinfo=TALLINN)
    prices = (1, 1, 500, 1, 1)
    slots = [
        HourPrice(
            start + timedelta(minutes=15 * i),
            start + timedelta(minutes=15 * (i + 1)),
            price,
            price,
            price,
        )
        for i, price in enumerate(prices)
    ]
    device = PlanningDevice(
        "load",
        "Load",
        1000,
        time(),
        time(),
        1,
        1,
        1,
        planning_step_minutes=15,
        always_off_above_eur_mwh=100,
    )

    plan = build_plans(
        slots,
        [device],
        {"load": {start.date(): 1}},
        minimum_targets={"load": {start.date(): 0}},
    )["load"]

    assert plan.valid
    assert not any(slot.active for slot in plan.hours)


def test_quarter_hour_initial_run_is_not_restarted_on_recalculation() -> None:
    start = datetime(2026, 8, 20, tzinfo=TALLINN)
    slots = [
        HourPrice(
            start + timedelta(minutes=15 * i),
            start + timedelta(minutes=15 * (i + 1)),
            10,
            10,
            10,
        )
        for i in range(4)
    ]
    device = PlanningDevice("load", "Load", 1000, time(), time(), 1, 1, 1, planning_step_minutes=15)

    plan = build_plans(
        slots,
        [device],
        {"load": {start.date(): 0.5}},
        initial_states={"load": (True, 2)},
    )["load"]

    assert plan.valid
    assert [slot.active for slot in plan.hours] == [True, True, False, False]


@pytest.mark.parametrize(
    ("active", "inverted", "physical_on"),
    [(True, False, True), (False, False, False), (True, True, False), (False, True, True)],
)
def test_explicit_output_mapping(active: bool, inverted: bool, physical_on: bool) -> None:
    assert output_should_be_on(active, inverted) is physical_on


def test_failure_transition_respects_minimum_off_time() -> None:
    now = datetime(2026, 8, 20, 3, tzinfo=TALLINN)

    desired, safe_at = protect_minimum_cycle(
        True,
        False,
        now - timedelta(minutes=45),
        now,
        min_on_hours=1,
        min_off_hours=1,
    )

    assert desired is False
    assert safe_at == now + timedelta(minutes=15)


def test_failure_transition_is_allowed_after_minimum_cycle() -> None:
    now = datetime(2026, 8, 20, 3, 15, tzinfo=TALLINN)

    desired, safe_at = protect_minimum_cycle(
        True,
        False,
        now - timedelta(hours=1),
        now,
        min_on_hours=1,
        min_off_hours=1,
    )

    assert desired is True
    assert safe_at is None
