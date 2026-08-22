"""Pure helpers for Smart Energy Scheduler config flows."""

from __future__ import annotations

from typing import Any

from .const import (
    CONF_ALWAYS_OFF_ABOVE,
    CONF_ALWAYS_ON_BELOW,
    CONF_MAX_HOURS,
    CONF_MIN_HOURS,
)

SECTION_DEVICE = "device"
SECTION_SCHEDULE = "schedule"
SECTION_POWER = "power"
SECTION_PRICE_LIMITS = "price_limits"
SECTION_WEATHER = "weather"
SECTION_ADVANCED = "advanced"

DEVICE_SECTIONS = (
    SECTION_DEVICE,
    SECTION_SCHEDULE,
    SECTION_POWER,
    SECTION_PRICE_LIMITS,
    SECTION_WEATHER,
    SECTION_ADVANCED,
)

DEVICE_SECTION_COLLAPSED = {
    SECTION_DEVICE: False,
    SECTION_SCHEDULE: False,
    SECTION_POWER: True,
    SECTION_PRICE_LIMITS: True,
    SECTION_WEATHER: True,
    SECTION_ADVANCED: True,
}


def flatten_device_input(data: dict[str, Any]) -> dict[str, Any]:
    """Flatten sectioned form data while tolerating legacy flat input."""
    flattened = {key: value for key, value in data.items() if key not in DEVICE_SECTIONS}
    for section_key in DEVICE_SECTIONS:
        section_data = data.get(section_key)
        if isinstance(section_data, dict):
            flattened.update(section_data)
    return flattened


def clean_config_data(data: dict[str, Any]) -> dict[str, Any]:
    """Remove empty optional selectors from config entry storage."""
    return {key: value for key, value in data.items() if value not in (None, "")}


def device_config_error(data: dict[str, Any]) -> str | None:
    """Validate relationships which selectors cannot express."""
    if float(data[CONF_MIN_HOURS]) > float(data[CONF_MAX_HOURS]):
        return "invalid_hour_limits"
    always_on = data.get(CONF_ALWAYS_ON_BELOW)
    always_off = data.get(CONF_ALWAYS_OFF_ABOVE)
    if always_on is not None and always_off is not None and float(always_on) >= float(always_off):
        return "invalid_price_limits"
    return None
