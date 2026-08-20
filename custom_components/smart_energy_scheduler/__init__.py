"""Smart Energy Scheduler integration."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import voluptuous as vol
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    OVERRIDE_AUTO,
    OVERRIDE_OFF,
    OVERRIDE_ON,
    PLATFORMS,
    SERVICE_RECALCULATE,
    SERVICE_SET_OVERRIDE,
)
from .coordinator import SmartEnergyCoordinator
from .websocket import async_register as async_register_websocket

type SmartEnergyConfigEntry = ConfigEntry[SmartEnergyCoordinator]

OVERRIDE_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Required("mode"): vol.In([OVERRIDE_AUTO, OVERRIDE_ON, OVERRIDE_OFF]),
        vol.Optional("until"): cv.datetime,
        vol.Optional("entry_id"): cv.string,
    }
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register shared HTTP, services, and websocket APIs."""
    hass.data.setdefault(DOMAIN, {})
    async_register_websocket(hass)
    card_path = Path(__file__).parent / "frontend" / "smart-energy-scheduler-card.js"
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                f"/{DOMAIN}/smart-energy-scheduler-card.js",
                str(card_path),
                cache_headers=False,
            )
        ]
    )

    async def recalculate(call: ServiceCall) -> None:
        runtimes = hass.data[DOMAIN]
        selected = (
            [runtimes[call.data["entry_id"]]] if call.data.get("entry_id") else runtimes.values()
        )
        for runtime in selected:
            await runtime.async_request_refresh()
            await runtime.async_apply_outputs()

    async def set_override(call: ServiceCall) -> None:
        runtimes = hass.data[DOMAIN]
        candidates = (
            [runtimes[call.data["entry_id"]]] if call.data.get("entry_id") else runtimes.values()
        )
        until = call.data.get("until")
        if isinstance(until, datetime) and until.tzinfo is None:
            until = dt_util.as_local(until)
        for runtime in candidates:
            if call.data["device_id"] in runtime.states:
                await runtime.async_set_override(call.data["device_id"], call.data["mode"], until)
                return
        raise ValueError("Scheduler device not found")

    hass.services.async_register(DOMAIN, SERVICE_RECALCULATE, recalculate)
    hass.services.async_register(DOMAIN, SERVICE_SET_OVERRIDE, set_override, schema=OVERRIDE_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: SmartEnergyConfigEntry) -> bool:
    """Set up one scheduler."""
    coordinator = SmartEnergyCoordinator(hass, entry)
    entry.runtime_data = coordinator
    hass.data[DOMAIN][entry.entry_id] = coordinator
    await coordinator.async_load_state()
    await coordinator.async_refresh()

    @callback
    def apply_after_refresh() -> None:
        hass.async_create_task(coordinator.async_apply_outputs())

    entry.async_on_unload(coordinator.async_add_listener(apply_after_refresh))
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    if hass.state is not CoreState.running:

        @callback
        def refresh_after_start(_event) -> None:
            """Recalculate once late-loaded weather/energy providers are ready."""
            hass.async_create_task(coordinator.async_request_refresh())

        entry.async_on_unload(
            hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, refresh_after_start)
        )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await coordinator.async_apply_outputs()
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload after main or subentry configuration changes."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: SmartEnergyConfigEntry) -> bool:
    """Unload without touching controlled outputs."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_save_state()
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
