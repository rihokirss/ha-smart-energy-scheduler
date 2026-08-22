"""Home Assistant API contract tests for the sectioned device form."""

from __future__ import annotations

import pytest

pytest.importorskip("homeassistant")

from custom_components.smart_energy_scheduler.config_flow import _device_schema
from custom_components.smart_energy_scheduler.config_flow_helpers import (
    DEVICE_SECTION_COLLAPSED,
    DEVICE_SECTIONS,
    clean_config_data,
    flatten_device_input,
)
from custom_components.smart_energy_scheduler.const import DEFAULT_HEAT_PUMP


def test_device_schema_uses_native_sections_and_preserves_flat_storage() -> None:
    flat_defaults = dict(DEFAULT_HEAT_PUMP)
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
