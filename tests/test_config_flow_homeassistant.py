"""Home Assistant API contract tests for the sectioned device form."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

pytest.importorskip("homeassistant")

from custom_components.smart_energy_scheduler.config_flow import (
    SmartEnergySchedulerConfigFlow,
    _device_schema,
)
from custom_components.smart_energy_scheduler.config_flow_helpers import (
    DEVICE_SECTION_COLLAPSED,
    DEVICE_SECTIONS,
    clean_config_data,
    flatten_device_input,
)
from custom_components.smart_energy_scheduler.const import DEFAULT_HEAT_PUMP

vol = pytest.importorskip("voluptuous")


def test_device_schema_uses_native_sections_and_preserves_flat_storage() -> None:
    flat_defaults = dict(DEFAULT_HEAT_PUMP) | {"target_entity": "switch.heat_pump"}
    schema = _device_schema(flat_defaults)

    assert tuple(key.schema for key in schema.schema) == DEVICE_SECTIONS

    sectioned = {}
    for key, section_value in schema.schema.items():
        section_key = key.schema
        assert section_value.options == {
            "collapsed": DEVICE_SECTION_COLLAPSED[section_key]
        }
        sectioned[section_key] = section_value.schema({})

    validated = schema(sectioned)
    stored = clean_config_data(flatten_device_input(validated))
    assert set(stored) == set(flat_defaults)
    assert stored["target_entity"] == flat_defaults["target_entity"]
    assert stored["planning_step_minutes"] == str(
        flat_defaults["planning_step_minutes"]
    )


def test_new_device_requires_explicit_target_selection() -> None:
    schema = _device_schema({})
    device_section = next(iter(schema.schema.values())).schema

    with pytest.raises(vol.MultipleInvalid) as error:
        device_section({})

    assert any(
        isinstance(item, vol.RequiredFieldInvalid) and item.path == ["target_entity"]
        for item in error.value.errors
    )
    assert device_section({"target_entity": "switch.boiler"})["target_entity"] == "switch.boiler"


def test_initial_setup_creates_scheduler_without_sample_devices() -> None:
    flow = SmartEnergySchedulerConfigFlow()
    flow.context = {"source": "user"}
    user_input = {"area": "EE", "tariff_confirmed": True, "shadow_mode": True}

    with patch.object(flow, "_async_current_entries", return_value=[]):
        result = asyncio.run(flow.async_step_user(user_input))

    assert result["type"] == "create_entry"
    assert result["data"] == user_input
    assert not result["subentries"]
