"""Lightweight contracts for coordinator state publication."""

from pathlib import Path


def test_control_state_is_published_after_outputs_are_applied() -> None:
    """WebSocket subscribers receive the final override and reason state."""
    source = (
        Path(__file__).parents[1] / "custom_components/smart_energy_scheduler/coordinator.py"
    ).read_text()
    apply_start = source.index("    async def async_apply_outputs")
    override_start = source.index("    async def async_set_override")
    apply_source = source[apply_start:override_start]

    assert "await self.async_save_state()" in apply_source
    assert "self.hass.bus.async_fire(EVENT_PLAN_UPDATED, self.as_dict())" in apply_source
    assert apply_source.index("await self.async_save_state()") < apply_source.index(
        "self.hass.bus.async_fire(EVENT_PLAN_UPDATED, self.as_dict())"
    )


def test_override_service_datetime_type_cannot_be_shadowed_by_platform() -> None:
    """Loading the datetime platform must not replace the datetime class."""
    source = (
        Path(__file__).parents[1] / "custom_components/smart_energy_scheduler/__init__.py"
    ).read_text()

    assert "from datetime import datetime as dt_datetime" in source
    assert "isinstance(until, dt_datetime)" in source


def test_planned_and_remaining_hour_sensors_use_distinct_calculations() -> None:
    source = (
        Path(__file__).parents[1] / "custom_components/smart_energy_scheduler/sensor.py"
    ).read_text()

    assert "def _remaining" in source
    assert "def _planned" in source
    assert "round(_actual(entity) + _remaining(entity))" in source
    remaining_block = source[source.index('key="remaining_hours"') :]
    assert "value_fn=_remaining" in remaining_block


def test_price_refresh_uses_persistent_cache_and_serial_nordpool_calls() -> None:
    source = (
        Path(__file__).parents[1] / "custom_components/smart_energy_scheduler/coordinator.py"
    ).read_text()

    assert "self._price_cache" in source
    assert 'stored.get("price_cache", [])' in source
    assert '"price_cache": [' in source
    assert '"complete_price_days": sorted(self._complete_price_days)' in source
    assert "for day in price_days:" in source
    assert "if day_key in self._complete_price_days:" in source
    assert "_NEXT_DAY_PRICE_FETCH_TIME = time(13, 30)" in source
    assert "if local_time >= _NEXT_DAY_PRICE_FETCH_TIME:" in source
    assert "asyncio.gather(" not in source
    assert 'warnings.append("price_cache_used")' in source


def test_failure_output_respects_minimum_cycle_before_switching() -> None:
    source = (
        Path(__file__).parents[1] / "custom_components/smart_energy_scheduler/coordinator.py"
    ).read_text()
    apply_start = source.index("    async def async_apply_outputs")
    override_start = source.index("    async def async_set_override")
    apply_source = source[apply_start:override_start]

    assert "protect_minimum_cycle(" in apply_source
    assert '"failure_wait_min_on"' in apply_source
    assert '"failure_wait_min_off"' in apply_source
