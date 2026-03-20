"""WebSocket API for Signal Lights."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .coordinator import SignalLightsCoordinator

_LOGGER = logging.getLogger(__name__)


def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register all Signal Lights WebSocket commands."""
    websocket_api.async_register_command(hass, ws_get_config)
    websocket_api.async_register_command(hass, ws_subscribe_updates)


@websocket_api.websocket_command({
    vol.Required("type"): "signal_lights/config",
    vol.Optional("entry_id"): str,
})
@callback
def ws_get_config(hass, connection, msg):
    """Return full config and state for all Signal Lights entries (or a specific one)."""
    entry_id_filter = msg.get("entry_id")
    domain_data = hass.data.get(DOMAIN, {})
    result = []
    for eid, coord in domain_data.items():
        if not isinstance(coord, SignalLightsCoordinator):
            continue
        if entry_id_filter and eid != entry_id_filter:
            continue
        active_data = coord.data or {}
        result.append({
            "entry_id": eid,
            "title": coord.entry_title,
            "signals": coord.store.get_signals(),
            "lights": coord.store.get_lights(),
            "notifications": coord.store.get_notification_config(),
            "active_signal": active_data.get("active_signal", "none"),
            "active_color": active_data.get("active_color", "#000000"),
            "active_signal_names": active_data.get("active_signal_names", []),
            "queue_depth": active_data.get("queue_depth", 0),
            "is_active": active_data.get("is_active", False),
            "signal_errors": active_data.get("signal_errors", {}),
        })
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command({
    vol.Required("type"): "signal_lights/subscribe",
    vol.Optional("entry_id"): str,
})
@callback
def ws_subscribe_updates(hass, connection, msg):
    """Subscribe to Signal Lights state updates.

    Sends the full config+state whenever the coordinator data changes.
    """
    entry_id_filter = msg.get("entry_id")
    domain_data = hass.data.get(DOMAIN, {})

    def _build_update():
        result = []
        for eid, coord in domain_data.items():
            if not isinstance(coord, SignalLightsCoordinator):
                continue
            if entry_id_filter and eid != entry_id_filter:
                continue
            active_data = coord.data or {}
            result.append({
                "entry_id": eid,
                "title": coord.entry_title,
                "signals": coord.store.get_signals(),
                "lights": coord.store.get_lights(),
                "notifications": coord.store.get_notification_config(),
                "active_signal": active_data.get("active_signal", "none"),
                "active_color": active_data.get("active_color", "#000000"),
                "active_signal_names": active_data.get("active_signal_names", []),
                "queue_depth": active_data.get("queue_depth", 0),
                "is_active": active_data.get("is_active", False),
                "signal_errors": active_data.get("signal_errors", {}),
            })
        return result

    # Send initial state
    connection.send_result(msg["id"], _build_update())

    # Subscribe to coordinator updates
    unsubs = []
    for eid, coord in domain_data.items():
        if not isinstance(coord, SignalLightsCoordinator):
            continue
        if entry_id_filter and eid != entry_id_filter:
            continue

        @callback
        def _on_update(coord_eid=eid):
            """Send update when coordinator data changes."""
            try:
                connection.send_message(
                    websocket_api.event_message(msg["id"], _build_update())
                )
            except Exception:  # noqa: BLE001
                pass  # connection closed

        unsubs.append(coord.async_add_listener(_on_update))

    @callback
    def _unsubscribe():
        for unsub in unsubs:
            unsub()

    connection.subscriptions[msg["id"]] = _unsubscribe
