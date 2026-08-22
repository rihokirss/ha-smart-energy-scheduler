"""Runtime-adjustable daily hour settings."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SmartEnergyConfigEntry
from .const import (
    CONF_BASE_HOURS,
    CONF_HOURS_PER_DEGREE,
    CONF_MAX_HOURS,
    CONF_MIN_HOURS,
    CONF_PREHEAT_HOURS,
    CONF_REFERENCE_TEMPERATURE,
    CONF_WEATHER_LOOKAHEAD_HOURS,
    DEFAULT_HEAT_PUMP,
)
from .entity import SchedulerEntity


@dataclass(frozen=True, kw_only=True)
class SchedulerNumberDescription(NumberEntityDescription):
    config_key: str


DESCRIPTIONS = (
    SchedulerNumberDescription(
        key="base_hours",
        translation_key="base_hours",
        config_key=CONF_BASE_HOURS,
        native_min_value=0,
        native_max_value=25,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.HOURS,
        mode=NumberMode.BOX,
    ),
    SchedulerNumberDescription(
        key="minimum_hours",
        translation_key="minimum_hours",
        config_key=CONF_MIN_HOURS,
        native_min_value=0,
        native_max_value=25,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.HOURS,
        mode=NumberMode.BOX,
    ),
    SchedulerNumberDescription(
        key="maximum_hours",
        translation_key="maximum_hours",
        config_key=CONF_MAX_HOURS,
        native_min_value=0,
        native_max_value=25,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.HOURS,
        mode=NumberMode.BOX,
    ),
    SchedulerNumberDescription(
        key="reference_temperature",
        translation_key="reference_temperature",
        config_key=CONF_REFERENCE_TEMPERATURE,
        native_min_value=-30,
        native_max_value=30,
        native_step=0.5,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        mode=NumberMode.BOX,
    ),
    SchedulerNumberDescription(
        key="hours_per_degree",
        translation_key="hours_per_degree",
        config_key=CONF_HOURS_PER_DEGREE,
        native_min_value=0,
        native_max_value=5,
        native_step=0.1,
        native_unit_of_measurement="h/°C",
        mode=NumberMode.BOX,
    ),
    SchedulerNumberDescription(
        key="weather_lookahead_hours",
        translation_key="weather_lookahead_hours",
        config_key=CONF_WEATHER_LOOKAHEAD_HOURS,
        native_min_value=1,
        native_max_value=48,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.HOURS,
        mode=NumberMode.BOX,
    ),
    SchedulerNumberDescription(
        key="preheat_hours",
        translation_key="preheat_hours",
        config_key=CONF_PREHEAT_HOURS,
        native_min_value=0,
        native_max_value=24,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.HOURS,
        mode=NumberMode.BOX,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmartEnergyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    for subentry in entry.runtime_data.device_subentries:
        async_add_entities(
            [
                SchedulerHoursNumber(entry.runtime_data, entry, subentry, description)
                for description in DESCRIPTIONS
            ],
            config_subentry_id=subentry.subentry_id,
        )


class SchedulerHoursNumber(SchedulerEntity, NumberEntity):
    """Persist an hour-setting directly into the device subentry."""

    entity_description: SchedulerNumberDescription

    def __init__(self, coordinator, entry, subentry, description) -> None:
        super().__init__(coordinator, entry, subentry, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float:
        return float(
            self.subentry.data.get(
                self.entity_description.config_key,
                DEFAULT_HEAT_PUMP[self.entity_description.config_key],
            )
        )

    async def async_set_native_value(self, value: float) -> None:
        data = dict(self.subentry.data)
        data[self.entity_description.config_key] = value
        self.hass.config_entries.async_update_subentry(self.entry, self.subentry, data=data)
        self.async_write_ha_state()
