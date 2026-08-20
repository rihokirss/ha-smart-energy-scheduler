"""Automation enable switches."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SmartEnergyConfigEntry
from .entity import SchedulerEntity

DESCRIPTION = SwitchEntityDescription(
    key="automatic_control",
    translation_key="automatic_control",
    icon="mdi:calendar-clock",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmartEnergyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    for subentry in entry.runtime_data.device_subentries:
        async_add_entities(
            [SchedulerAutomationSwitch(entry.runtime_data, entry, subentry)],
            config_subentry_id=subentry.subentry_id,
        )


class SchedulerAutomationSwitch(SchedulerEntity, SwitchEntity):
    """Enable/disable scheduler commands for a device."""

    entity_description = DESCRIPTION

    def __init__(self, coordinator, entry, subentry) -> None:
        super().__init__(coordinator, entry, subentry, DESCRIPTION.key)

    @property
    def is_on(self) -> bool:
        return self.runtime_state.enabled

    async def async_turn_on(self, **kwargs) -> None:
        self.runtime_state.enabled = True
        await self.coordinator.async_save_state()
        await self.coordinator.async_apply_outputs()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self.runtime_state.enabled = False
        self.runtime_state.reason = "disabled"
        await self.coordinator.async_save_state()
        self.async_write_ha_state()
