"""WebSocket commands for the Lovelace card."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, EVENT_PLAN_UPDATED


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/get_plan", vol.Optional("entry_id"): str}
)
@websocket_api.async_response
async def ws_get_plan(hass, connection, msg) -> None:
    """Return one or every configured plan."""
    runtimes = hass.data.get(DOMAIN, {})
    if entry_id := msg.get("entry_id"):
        runtime = runtimes.get(entry_id)
        if runtime is None:
            connection.send_error(msg["id"], "not_found", "Scheduler entry not found")
            return
        connection.send_result(msg["id"], runtime.as_dict())
        return
    connection.send_result(msg["id"], [runtime.as_dict() for runtime in runtimes.values()])


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/subscribe_plan", vol.Optional("entry_id"): str}
)
@websocket_api.async_response
async def ws_subscribe_plan(hass, connection, msg) -> None:
    """Subscribe to recalculated plans."""
    entry_id = msg.get("entry_id")

    @callback
    def forward(event) -> None:
        payload = event.data
        if entry_id is None or payload.get("entry_id") == entry_id:
            connection.send_event(msg["id"], payload)

    connection.subscriptions[msg["id"]] = hass.bus.async_listen(EVENT_PLAN_UPDATED, forward)
    connection.send_result(msg["id"])


@callback
def async_register(hass: HomeAssistant) -> None:
    """Register integration websocket commands once."""
    websocket_api.async_register_command(hass, ws_get_plan)
    websocket_api.async_register_command(hass, ws_subscribe_plan)
