"""Tests for the sectioned device config flow data contract."""

from __future__ import annotations

import json
from pathlib import Path

from custom_components.smart_energy_scheduler.config_flow_helpers import (
    DEVICE_SECTION_COLLAPSED,
    DEVICE_SECTIONS,
    SECTION_ADVANCED,
    SECTION_DEVICE,
    SECTION_POWER,
    SECTION_PRICE_LIMITS,
    SECTION_SCHEDULE,
    SECTION_WEATHER,
    clean_config_data,
    device_config_error,
    flatten_device_input,
)

INTEGRATION_DIR = (
    Path(__file__).parents[1] / "custom_components" / "smart_energy_scheduler"
)

SECTION_FIELDS = {
    SECTION_DEVICE: {"name", "target_entity", "inverted", "enabled"},
    SECTION_SCHEDULE: {
        "window_start",
        "window_end",
        "base_hours",
        "min_hours",
        "max_hours",
        "planning_step_minutes",
        "min_on_hours",
        "min_off_hours",
    },
    SECTION_POWER: {
        "feedback_entity",
        "power_sensor",
        "power_multiplier",
        "nominal_power_w",
    },
    SECTION_PRICE_LIMITS: {
        "always_on_below_eur_mwh",
        "always_off_above_eur_mwh",
    },
    SECTION_WEATHER: {
        "use_weather",
        "legacy_wind_chill",
        "reference_temperature",
        "hours_per_degree",
        "weather_lookahead_hours",
        "preheat_hours",
    },
    SECTION_ADVANCED: {"solar_priority", "failure_mode"},
}


def test_sectioned_input_is_flattened_and_cleaned_for_storage() -> None:
    sectioned = {
        SECTION_DEVICE: {
            "name": "Boiler",
            "target_entity": "switch.boiler",
            "inverted": False,
            "enabled": True,
        },
        SECTION_SCHEDULE: {"min_hours": 2, "max_hours": 5},
        SECTION_POWER: {"feedback_entity": "", "power_sensor": None},
        SECTION_PRICE_LIMITS: {"always_on_below_eur_mwh": 20},
        SECTION_WEATHER: {"use_weather": False},
        SECTION_ADVANCED: {"failure_mode": "keep"},
    }

    flattened = flatten_device_input(sectioned)
    assert not set(DEVICE_SECTIONS) & flattened.keys()
    assert flattened["name"] == "Boiler"
    assert flattened["min_hours"] == 2
    assert flattened["always_on_below_eur_mwh"] == 20

    cleaned = clean_config_data(flattened)
    assert "feedback_entity" not in cleaned
    assert "power_sensor" not in cleaned


def test_flattening_tolerates_existing_flat_data() -> None:
    existing = {"name": "Heat pump", "min_hours": 3, "max_hours": 24}
    assert flatten_device_input(existing) == existing


def test_device_relationship_validation() -> None:
    assert device_config_error({"min_hours": 5, "max_hours": 4}) == "invalid_hour_limits"
    assert (
        device_config_error(
            {
                "min_hours": 1,
                "max_hours": 4,
                "always_on_below_eur_mwh": 50,
                "always_off_above_eur_mwh": 50,
            }
        )
        == "invalid_price_limits"
    )
    assert device_config_error({"min_hours": 1, "max_hours": 4}) is None


def test_section_order_and_initial_collapsed_state() -> None:
    assert tuple(DEVICE_SECTION_COLLAPSED) == DEVICE_SECTIONS
    assert DEVICE_SECTION_COLLAPSED == {
        SECTION_DEVICE: False,
        SECTION_SCHEDULE: False,
        SECTION_POWER: True,
        SECTION_PRICE_LIMITS: True,
        SECTION_WEATHER: True,
        SECTION_ADVANCED: True,
    }


def test_translations_and_icons_cover_every_section_and_field() -> None:
    for relative_path in ("strings.json", "translations/en.json", "translations/et.json"):
        content = json.loads((INTEGRATION_DIR / relative_path).read_text())
        steps = content["config_subentries"]["device"]["step"]
        for step_name in ("user", "reconfigure"):
            sections = steps[step_name]["sections"]
            assert tuple(sections) == DEVICE_SECTIONS
            for section_key, expected_fields in SECTION_FIELDS.items():
                assert set(sections[section_key]["data"]) == expected_fields

    icons = json.loads((INTEGRATION_DIR / "icons.json").read_text())
    icon_steps = icons["config_subentries"]["device"]["step"]
    for step_name in ("user", "reconfigure"):
        assert tuple(icon_steps[step_name]["sections"]) == DEVICE_SECTIONS
