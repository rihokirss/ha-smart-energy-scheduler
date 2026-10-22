"""UI configuration for Smart Energy Scheduler."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector

from .config_flow_helpers import (
    DEVICE_SECTION_COLLAPSED,
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
    CONF_GRID_POWER_SENSOR,
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
    CONF_PLANNING_STEP_MINUTES,
    CONF_POWER_MULTIPLIER,
    CONF_POWER_SENSOR,
    CONF_PREHEAT_HOURS,
    CONF_PV_POWER_SENSOR,
    CONF_REFERENCE_TEMPERATURE,
    CONF_SELL_MARGIN,
    CONF_SHADOW_MODE,
    CONF_SOLAR_FALLBACK_ENABLED,
    CONF_SOLAR_FALLBACK_END_MONTH,
    CONF_SOLAR_FALLBACK_START_MONTH,
    CONF_SOLAR_FALLBACK_SUNRISE_DELAY_H,
    CONF_SOLAR_FALLBACK_SUNSET_ADVANCE_H,
    CONF_SOLAR_PRIORITY,
    CONF_SOLAR_WINTER_ENABLED,
    CONF_SOLAR_WINTER_END_DAY,
    CONF_SOLAR_WINTER_END_MONTH,
    CONF_SOLAR_WINTER_START_DAY,
    CONF_SOLAR_WINTER_START_MONTH,
    CONF_TARGET_ENTITY,
    CONF_TARIFF_CONFIRMED,
    CONF_USE_WEATHER,
    CONF_VAT,
    CONF_WEATHER_ENTITY,
    CONF_WEATHER_LOOKAHEAD_HOURS,
    CONF_WEEKEND_NIGHT,
    CONF_WINDOW_END,
    CONF_WINDOW_START,
    DEFAULT_HEAT_PUMP,
    DEFAULT_MAIN,
    DOMAIN,
    FAILURE_FORCE_OFF,
    FAILURE_FORCE_ON,
    FAILURE_KEEP,
    SUBENTRY_DEVICE,
)


def _number(minimum: float, maximum: float, step: float = 0.1, unit: str | None = None):
    config = selector.NumberSelectorConfig(
        min=minimum,
        max=maximum,
        step=step,
        mode=selector.NumberSelectorMode.BOX,
    )
    if unit is not None:
        config["unit_of_measurement"] = unit
    return selector.NumberSelector(config)


def _main_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Build the global tariff/source form."""
    fields: dict[Any, Any] = {
        vol.Required(CONF_AREA, default=defaults.get(CONF_AREA, "EE")): str,
        vol.Required(CONF_CURRENCY, default=defaults.get(CONF_CURRENCY, "EUR")): str,
        vol.Required(CONF_BUY_MARGIN, default=defaults.get(CONF_BUY_MARGIN, 2.44)): _number(
            -500, 500, 0.01, "EUR/MWh"
        ),
        vol.Required(CONF_SELL_MARGIN, default=defaults.get(CONF_SELL_MARGIN, -4.5)): _number(
            -500, 500, 0.01, "EUR/MWh"
        ),
        vol.Required(CONF_VAT, default=defaults.get(CONF_VAT, 24.0)): _number(0, 100, 0.1, "%"),
        vol.Required(CONF_NETWORK_DAY, default=defaults.get(CONF_NETWORK_DAY, 75.3)): _number(
            0, 1000, 0.1, "EUR/MWh"
        ),
        vol.Required(CONF_NETWORK_NIGHT, default=defaults.get(CONF_NETWORK_NIGHT, 43.5)): _number(
            0, 1000, 0.1, "EUR/MWh"
        ),
        vol.Required(
            CONF_NETWORK_INCLUDES_VAT,
            default=defaults.get(CONF_NETWORK_INCLUDES_VAT, True),
        ): selector.BooleanSelector(),
        vol.Required(
            CONF_DAY_START, default=defaults.get(CONF_DAY_START, "07:00:00")
        ): selector.TimeSelector(),
        vol.Required(
            CONF_DAY_END, default=defaults.get(CONF_DAY_END, "22:00:00")
        ): selector.TimeSelector(),
        vol.Required(
            CONF_WEEKEND_NIGHT, default=defaults.get(CONF_WEEKEND_NIGHT, True)
        ): selector.BooleanSelector(),
        vol.Optional(
            CONF_WEATHER_ENTITY, default=defaults.get(CONF_WEATHER_ENTITY)
        ): selector.EntitySelector(selector.EntitySelectorConfig(domain="weather")),
        vol.Required(CONF_BASE_LOAD_W, default=defaults.get(CONF_BASE_LOAD_W, 500.0)): _number(
            0, 50000, 10, "W"
        ),
        vol.Required(
            CONF_SOLAR_FALLBACK_ENABLED,
            default=defaults.get(CONF_SOLAR_FALLBACK_ENABLED, True),
        ): selector.BooleanSelector(),
        vol.Required(
            CONF_SOLAR_FALLBACK_START_MONTH,
            default=defaults.get(CONF_SOLAR_FALLBACK_START_MONTH, 3),
        ): _number(1, 12, 1),
        vol.Required(
            CONF_SOLAR_FALLBACK_END_MONTH,
            default=defaults.get(CONF_SOLAR_FALLBACK_END_MONTH, 9),
        ): _number(1, 12, 1),
        vol.Required(
            CONF_SOLAR_FALLBACK_SUNRISE_DELAY_H,
            default=defaults.get(CONF_SOLAR_FALLBACK_SUNRISE_DELAY_H, 3.0),
        ): _number(0, 12, 0.5, "h"),
        vol.Required(
            CONF_SOLAR_FALLBACK_SUNSET_ADVANCE_H,
            default=defaults.get(CONF_SOLAR_FALLBACK_SUNSET_ADVANCE_H, 2.0),
        ): _number(0, 12, 0.5, "h"),
        vol.Required(
            CONF_SOLAR_WINTER_ENABLED,
            default=defaults.get(CONF_SOLAR_WINTER_ENABLED, False),
        ): selector.BooleanSelector(),
        vol.Required(
            CONF_SOLAR_WINTER_START_MONTH,
            default=defaults.get(CONF_SOLAR_WINTER_START_MONTH, 10),
        ): _number(1, 12, 1),
        vol.Required(
            CONF_SOLAR_WINTER_START_DAY,
            default=defaults.get(CONF_SOLAR_WINTER_START_DAY, 15),
        ): _number(1, 31, 1),
        vol.Required(
            CONF_SOLAR_WINTER_END_MONTH,
            default=defaults.get(CONF_SOLAR_WINTER_END_MONTH, 2),
        ): _number(1, 12, 1),
        vol.Required(
            CONF_SOLAR_WINTER_END_DAY,
            default=defaults.get(CONF_SOLAR_WINTER_END_DAY, 15),
        ): _number(1, 31, 1),
        vol.Optional(
            CONF_GRID_POWER_SENSOR, default=defaults.get(CONF_GRID_POWER_SENSOR)
        ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
        vol.Optional(
            CONF_PV_POWER_SENSOR, default=defaults.get(CONF_PV_POWER_SENSOR)
        ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
        vol.Required(
            CONF_SHADOW_MODE, default=defaults.get(CONF_SHADOW_MODE, True)
        ): selector.BooleanSelector(),
        vol.Required(
            CONF_TARIFF_CONFIRMED, default=defaults.get(CONF_TARIFF_CONFIRMED, False)
        ): selector.BooleanSelector(),
    }
    # Optional entity selectors must not receive None as a frontend default.
    fields = {
        (
            vol.Optional(key.schema)
            if isinstance(key, vol.Optional) and key.default() is None
            else key
        ): value
        for key, value in fields.items()
    }
    return vol.Schema(fields)


def _without_empty_optional_defaults(fields: dict[Any, Any]) -> dict[Any, Any]:
    """Remove empty defaults which the frontend cannot render for optional selectors."""
    return {
        (
            vol.Optional(key.schema)
            if isinstance(key, vol.Optional) and key.default() in (None, "")
            else key
        ): value
        for key, value in fields.items()
    }


def _device_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Build one device form with native collapsible sections."""
    device_fields: dict[Any, Any] = {
        vol.Required("name", default=defaults.get("name", "Seade")): str,
        vol.Required(
            CONF_TARGET_ENTITY, default=defaults.get(CONF_TARGET_ENTITY)
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["switch", "input_boolean", "light"])
        ),
        vol.Required(
            CONF_INVERTED, default=defaults.get(CONF_INVERTED, False)
        ): selector.BooleanSelector(),
        vol.Required(
            CONF_ENABLED, default=defaults.get(CONF_ENABLED, True)
        ): selector.BooleanSelector(),
    }
    schedule_fields: dict[Any, Any] = {
        vol.Required(
            CONF_WINDOW_START, default=defaults.get(CONF_WINDOW_START, "00:00:00")
        ): selector.TimeSelector(),
        vol.Required(
            CONF_WINDOW_END, default=defaults.get(CONF_WINDOW_END, "00:00:00")
        ): selector.TimeSelector(),
        vol.Required(CONF_BASE_HOURS, default=defaults.get(CONF_BASE_HOURS, 3.0)): _number(
            0, 25, 1, "h"
        ),
        vol.Required(CONF_MIN_HOURS, default=defaults.get(CONF_MIN_HOURS, 1.0)): _number(
            0, 25, 1, "h"
        ),
        vol.Required(CONF_MAX_HOURS, default=defaults.get(CONF_MAX_HOURS, 24.0)): _number(
            0, 25, 1, "h"
        ),
        vol.Required(
            CONF_PLANNING_STEP_MINUTES,
            default=str(defaults.get(CONF_PLANNING_STEP_MINUTES, 60)),
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=["60", "15"],
                mode=selector.SelectSelectorMode.DROPDOWN,
                translation_key="planning_step_minutes",
            )
        ),
        vol.Required(CONF_MIN_ON_HOURS, default=defaults.get(CONF_MIN_ON_HOURS, 1)): _number(
            1, 24, 1, "h"
        ),
        vol.Required(CONF_MIN_OFF_HOURS, default=defaults.get(CONF_MIN_OFF_HOURS, 1)): _number(
            1, 24, 1, "h"
        ),
    }
    power_fields: dict[Any, Any] = {
        vol.Optional(
            CONF_FEEDBACK_ENTITY, default=defaults.get(CONF_FEEDBACK_ENTITY)
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["binary_sensor", "switch", "input_boolean"])
        ),
        vol.Optional(
            CONF_POWER_SENSOR, default=defaults.get(CONF_POWER_SENSOR)
        ): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
        vol.Required(
            CONF_POWER_MULTIPLIER, default=defaults.get(CONF_POWER_MULTIPLIER, 1.0)
        ): _number(0.001, 1000, 0.001),
        vol.Required(
            CONF_NOMINAL_POWER_W, default=defaults.get(CONF_NOMINAL_POWER_W, 1000.0)
        ): _number(1, 100000, 10, "W"),
    }
    price_fields: dict[Any, Any] = {
        vol.Optional(CONF_ALWAYS_ON_BELOW, default=defaults.get(CONF_ALWAYS_ON_BELOW)): _number(
            0, 1000, 1, "EUR/MWh"
        ),
        vol.Optional(CONF_ALWAYS_OFF_ABOVE, default=defaults.get(CONF_ALWAYS_OFF_ABOVE)): _number(
            0, 1000, 1, "EUR/MWh"
        ),
    }
    weather_fields: dict[Any, Any] = {
        vol.Required(
            CONF_USE_WEATHER, default=defaults.get(CONF_USE_WEATHER, False)
        ): selector.BooleanSelector(),
        vol.Required(
            CONF_LEGACY_WIND_CHILL,
            default=defaults.get(CONF_LEGACY_WIND_CHILL, True),
        ): selector.BooleanSelector(),
        vol.Required(
            CONF_REFERENCE_TEMPERATURE, default=defaults.get(CONF_REFERENCE_TEMPERATURE, 6.0)
        ): _number(-50, 50, 0.5, "°C"),
        vol.Required(
            CONF_HOURS_PER_DEGREE, default=defaults.get(CONF_HOURS_PER_DEGREE, 0.5)
        ): _number(0, 5, 0.1, "h/°C"),
        vol.Required(
            CONF_WEATHER_LOOKAHEAD_HOURS,
            default=defaults.get(CONF_WEATHER_LOOKAHEAD_HOURS, 12),
        ): _number(1, 48, 1, "h"),
        vol.Required(CONF_PREHEAT_HOURS, default=defaults.get(CONF_PREHEAT_HOURS, 0)): _number(
            0, 24, 1, "h"
        ),
    }
    advanced_fields: dict[Any, Any] = {
        vol.Required(CONF_SOLAR_PRIORITY, default=defaults.get(CONF_SOLAR_PRIORITY, 1)): _number(
            1, 100, 1
        ),
        vol.Required(
            CONF_FAILURE_MODE, default=defaults.get(CONF_FAILURE_MODE, FAILURE_KEEP)
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[FAILURE_FORCE_ON, FAILURE_FORCE_OFF, FAILURE_KEEP],
                translation_key="failure_mode",
            )
        ),
    }
    fields_by_section = {
        SECTION_DEVICE: device_fields,
        SECTION_SCHEDULE: schedule_fields,
        SECTION_POWER: power_fields,
        SECTION_PRICE_LIMITS: price_fields,
        SECTION_WEATHER: weather_fields,
        SECTION_ADVANCED: advanced_fields,
    }
    return vol.Schema(
        {
            vol.Required(section_key): section(
                vol.Schema(_without_empty_optional_defaults(fields)),
                {"collapsed": DEVICE_SECTION_COLLAPSED[section_key]},
            )
            for section_key, fields in fields_by_section.items()
        }
    )


class SmartEnergySchedulerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure global sources and tariffs."""

    VERSION = 1
    MINOR_VERSION = 0

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_DEVICE: DeviceSubentryFlow}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Create the scheduler and its initial heat-pump device."""
        errors: dict[str, str] = {}
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            if not user_input[CONF_TARIFF_CONFIRMED]:
                errors[CONF_TARIFF_CONFIRMED] = "tariff_not_confirmed"
            else:
                heat_pump = dict(DEFAULT_HEAT_PUMP)
                return self.async_create_entry(
                    title="Smart Energy Scheduler",
                    data=clean_config_data(user_input),
                    subentries=[
                        {
                            "subentry_type": SUBENTRY_DEVICE,
                            "title": heat_pump.pop("name"),
                            "data": heat_pump,
                            "unique_id": "heat_pump",
                        }
                    ],
                )
        defaults = DEFAULT_MAIN | (user_input or {})
        return self.async_show_form(
            step_id="user", data_schema=_main_schema(defaults), errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit shared settings."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input[CONF_TARIFF_CONFIRMED]:
                errors[CONF_TARIFF_CONFIRMED] = "tariff_not_confirmed"
            else:
                self.hass.config_entries.async_update_entry(
                    entry, data=clean_config_data(user_input)
                )
                return self.async_abort(reason="reconfigure_successful")
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_main_schema(dict(entry.data) | (user_input or {})),
            errors=errors,
        )


class DeviceSubentryFlow(ConfigSubentryFlow):
    """Add and edit independently scheduled devices."""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        if user_input is not None:
            device_data = flatten_device_input(user_input)
            if not (error := device_config_error(device_data)):
                name = device_data.pop("name")
                entry = self._get_entry()
                self.hass.config_entries.async_schedule_reload(entry.entry_id)
                return self.async_create_entry(title=name, data=clean_config_data(device_data))
            return self.async_show_form(
                step_id="user",
                data_schema=_device_schema(device_data),
                errors={"base": error},
            )
        return self.async_show_form(step_id="user", data_schema=_device_schema({}), errors={})

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        entry = self._get_entry()
        subentry = self._get_reconfigure_subentry()
        if user_input is not None:
            device_data = flatten_device_input(user_input)
            if not (error := device_config_error(device_data)):
                name = device_data.pop("name")
                return self.async_update_and_abort(
                    entry, subentry, title=name, data=clean_config_data(device_data)
                )
            return self.async_show_form(
                step_id="reconfigure",
                data_schema=_device_schema(device_data),
                errors={"base": error},
            )
        defaults = dict(subentry.data) | {"name": subentry.title}
        return self.async_show_form(
            step_id="reconfigure", data_schema=_device_schema(defaults), errors={}
        )
