"""Runtime-adjustable daily hour settings."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SmartEnergyConfigEntry
from .const import CONF_BASE_HOURS, CONF_MAX_HOURS, CONF_MIN_HOURS
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
        return float(self.subentry.data[self.entity_description.config_key])

    async def async_set_native_value(self, value: float) -> None:
        data = dict(self.subentry.data)
        data[self.entity_description.config_key] = value
        self.hass.config_entries.async_update_subentry(self.entry, self.subentry, data=data)
        self.async_write_ha_state()
