"""Planned activity binary sensors."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SmartEnergyConfigEntry
from .entity import SchedulerEntity

DESCRIPTION = BinarySensorEntityDescription(
    key="scheduled_active",
    translation_key="scheduled_active",
    icon="mdi:calendar-check",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmartEnergyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    for subentry in entry.runtime_data.device_subentries:
        async_add_entities(
            [SchedulerActiveBinarySensor(entry.runtime_data, entry, subentry)],
            config_subentry_id=subentry.subentry_id,
        )


class SchedulerActiveBinarySensor(SchedulerEntity, BinarySensorEntity):
    """Whether the current local hour is scheduled active."""

    entity_description = DESCRIPTION

    def __init__(self, coordinator, entry, subentry) -> None:
        super().__init__(coordinator, entry, subentry, DESCRIPTION.key)

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.planned_active(self.device_id)
