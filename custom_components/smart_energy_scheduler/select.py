"""Timed manual override selects."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SmartEnergyConfigEntry
from .const import OVERRIDE_AUTO, OVERRIDE_OFF, OVERRIDE_ON
from .entity import SchedulerEntity

DESCRIPTION = SelectEntityDescription(
    key="override",
    translation_key="override",
    options=[OVERRIDE_AUTO, OVERRIDE_ON, OVERRIDE_OFF],
    icon="mdi:gesture-tap-button",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmartEnergyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    for subentry in entry.runtime_data.device_subentries:
        async_add_entities(
            [SchedulerOverrideSelect(entry.runtime_data, entry, subentry)],
            config_subentry_id=subentry.subentry_id,
        )


class SchedulerOverrideSelect(SchedulerEntity, SelectEntity):
    """Select automatic, forced-on, or forced-off mode."""

    entity_description = DESCRIPTION

    def __init__(self, coordinator, entry, subentry) -> None:
        super().__init__(coordinator, entry, subentry, DESCRIPTION.key)

    @property
    def current_option(self) -> str:
        return self.runtime_state.override

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_override(
            self.device_id, option, self.runtime_state.override_until
        )
        self.async_write_ha_state()
