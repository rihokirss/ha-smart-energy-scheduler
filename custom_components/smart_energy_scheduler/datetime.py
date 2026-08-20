"""Override expiry datetime entity."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.datetime import DateTimeEntity, DateTimeEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SmartEnergyConfigEntry
from .const import OVERRIDE_AUTO
from .entity import SchedulerEntity

DESCRIPTION = DateTimeEntityDescription(
    key="override_until",
    translation_key="override_until",
    icon="mdi:timer-sand-complete",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmartEnergyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    for subentry in entry.runtime_data.device_subentries:
        async_add_entities(
            [SchedulerOverrideUntil(entry.runtime_data, entry, subentry)],
            config_subentry_id=subentry.subentry_id,
        )


class SchedulerOverrideUntil(SchedulerEntity, DateTimeEntity):
    """End timestamp for the current forced mode."""

    entity_description = DESCRIPTION

    def __init__(self, coordinator, entry, subentry) -> None:
        super().__init__(coordinator, entry, subentry, DESCRIPTION.key)

    @property
    def native_value(self) -> datetime | None:
        return self.runtime_state.override_until

    async def async_set_value(self, value: datetime) -> None:
        self.runtime_state.override_until = value
        if self.runtime_state.override != OVERRIDE_AUTO:
            await self.coordinator.async_apply_outputs()
        await self.coordinator.async_save_state()
        self.async_write_ha_state()
