"""Constants for Smart Energy Scheduler."""

from __future__ import annotations

DOMAIN = "smart_energy_scheduler"
NAME = "Smart Energy Scheduler"
SUBENTRY_DEVICE = "device"
PLATFORMS = ["binary_sensor", "datetime", "number", "select", "sensor", "switch"]

CONF_AREA = "area"
CONF_CURRENCY = "currency"
CONF_BUY_MARGIN = "buy_margin"
CONF_SELL_MARGIN = "sell_margin"
CONF_VAT = "vat"
CONF_NETWORK_DAY = "network_day"
CONF_NETWORK_NIGHT = "network_night"
CONF_DAY_START = "day_start"
CONF_DAY_END = "day_end"
CONF_WEEKEND_NIGHT = "weekend_night"
CONF_WEATHER_ENTITY = "weather_entity"
CONF_BASE_LOAD_W = "base_load_w"
CONF_GRID_POWER_SENSOR = "grid_power_sensor"
CONF_PV_POWER_SENSOR = "pv_power_sensor"
CONF_SHADOW_MODE = "shadow_mode"
CONF_TARIFF_CONFIRMED = "tariff_confirmed"

CONF_TARGET_ENTITY = "target_entity"
CONF_INVERTED = "inverted"
CONF_FEEDBACK_ENTITY = "feedback_entity"
CONF_POWER_SENSOR = "power_sensor"
CONF_POWER_MULTIPLIER = "power_multiplier"
CONF_NOMINAL_POWER_W = "nominal_power_w"
CONF_WINDOW_START = "window_start"
CONF_WINDOW_END = "window_end"
CONF_BASE_HOURS = "base_hours"
CONF_MIN_HOURS = "min_hours"
CONF_MAX_HOURS = "max_hours"
CONF_MIN_ON_HOURS = "min_on_hours"
CONF_MIN_OFF_HOURS = "min_off_hours"
CONF_USE_WEATHER = "use_weather"
CONF_REFERENCE_TEMPERATURE = "reference_temperature"
CONF_HOURS_PER_DEGREE = "hours_per_degree"
CONF_SOLAR_PRIORITY = "solar_priority"
CONF_FAILURE_MODE = "failure_mode"
CONF_ENABLED = "enabled"

FAILURE_FORCE_ON = "force_on"
FAILURE_FORCE_OFF = "force_off"
FAILURE_KEEP = "keep"
OVERRIDE_AUTO = "auto"
OVERRIDE_ON = "on"
OVERRIDE_OFF = "off"

DEFAULT_MAIN = {
    CONF_AREA: "EE",
    CONF_CURRENCY: "EUR",
    CONF_BUY_MARGIN: 2.44,
    CONF_SELL_MARGIN: -4.50,
    CONF_VAT: 22.0,
    CONF_NETWORK_DAY: 36.9,
    CONF_NETWORK_NIGHT: 21.0,
    CONF_DAY_START: "07:00:00",
    CONF_DAY_END: "22:00:00",
    CONF_WEEKEND_NIGHT: True,
    CONF_BASE_LOAD_W: 500.0,
    CONF_SHADOW_MODE: True,
}

DEFAULT_HEAT_PUMP = {
    "name": "Soojuspump",
    CONF_TARGET_ENTITY: "switch.sonoff_1001208b81_1",
    CONF_INVERTED: False,
    CONF_POWER_MULTIPLIER: 1.0,
    CONF_NOMINAL_POWER_W: 2500.0,
    CONF_WINDOW_START: "00:00:00",
    CONF_WINDOW_END: "00:00:00",
    CONF_BASE_HOURS: 9.0,
    CONF_MIN_HOURS: 3.0,
    CONF_MAX_HOURS: 24.0,
    CONF_MIN_ON_HOURS: 1,
    CONF_MIN_OFF_HOURS: 1,
    CONF_USE_WEATHER: True,
    CONF_REFERENCE_TEMPERATURE: 6.0,
    CONF_HOURS_PER_DEGREE: 0.5,
    CONF_SOLAR_PRIORITY: 1,
    CONF_FAILURE_MODE: FAILURE_FORCE_ON,
    CONF_ENABLED: True,
}

EVENT_PLAN_UPDATED = f"{DOMAIN}_plan_updated"
SERVICE_RECALCULATE = "recalculate"
SERVICE_SET_OVERRIDE = "set_override"
STORAGE_KEY = DOMAIN
STORAGE_VERSION = 1
