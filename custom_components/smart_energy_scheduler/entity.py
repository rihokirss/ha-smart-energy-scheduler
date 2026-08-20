"""Shared scheduler entity base."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SmartEnergyCoordinator


class SchedulerEntity(CoordinatorEntity[SmartEnergyCoordinator]):
    """Base for one scheduler device entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SmartEnergyCoordinator,
        entry: ConfigEntry,
        subentry: ConfigSubentry,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self.subentry = subentry
        self.device_id = subentry.subentry_id
        self._attr_unique_id = f"{entry.entry_id}_{self.device_id}_{key}"
        self._attr_config_subentry_id = self.device_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}:{self.device_id}")},
            entry_type=DeviceEntryType.SERVICE,
            name=subentry.title,
            manufacturer="Smart Energy Scheduler",
            model="Scheduled load",
        )

    @property
    def runtime_state(self):
        """Return mutable state for this device."""
        return self.coordinator.states[self.device_id]
