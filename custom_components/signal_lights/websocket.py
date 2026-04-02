"""WebSocket API for Signal Lights."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register all Signal Lights WebSocket commands."""
    websocket_api.async_register_command(hass, ws_get_config)
    websocket_api.async_register_command(hass, ws_subscribe_updates)


def _build_entry_snapshots(domain_data: dict, entry_id_filter: str | None = None) -> list[dict]:
    """Build a list of entry snapshots from domain_data.

    hass.data[DOMAIN] contains only coordinator objects keyed by entry_id
    (global sentinels live in hass.data[DOMAIN_GLOBAL]). No isinstance filter needed.

    Args:
        domain_data: hass.data[DOMAIN] — all values are coordinators.
        entry_id_filter: If set, only include this entry_id; otherwise include all.

    Returns:
        List of entry snapshot dicts suitable for WS responses/events.

    Note:
        MAX_ENTRIES is intentionally tiny, so rebuilding all entries on each
        coordinator update is not a performance concern.
    """
    result = []
    for eid, coord in domain_data.items():
        if entry_id_filter and eid != entry_id_filter:
            continue
        try:
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
                "cycle_interval": active_data.get("cycle_interval", 0),
                "cycle_index": active_data.get("cycle_index", 0),
            })
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Signal Lights: error building snapshot for entry %s", eid)
            continue
    return result


@websocket_api.websocket_command({
    vol.Required("type"): "signal_lights/config",
    vol.Optional("entry_id"): str,
})
@websocket_api.require_admin
@callback
def ws_get_config(hass, connection, msg):
    """Return full config and state for all Signal Lights entries (or a specific one).

    Protocol:
        Request:  { type: "signal_lights/config", entry_id?: string }
        Response: result — list of entry snapshot objects (see _build_entry_snapshots).

    This is a one-shot request/response — no subscription; use
    signal_lights/subscribe for live updates.
    """
    entry_id_filter = msg.get("entry_id")
    domain_data = hass.data.get(DOMAIN, {})
    connection.send_result(msg["id"], _build_entry_snapshots(domain_data, entry_id_filter))


@websocket_api.websocket_command({
    vol.Required("type"): "signal_lights/subscribe",
    vol.Optional("entry_id"): str,
})
@websocket_api.require_admin
@callback
def ws_subscribe_updates(hass, connection, msg):
    """Subscribe to Signal Lights state updates.

    Protocol:
        Request:  { type: "signal_lights/subscribe", entry_id?: string }
        Response: result — initial list of entry snapshots (same shape as
                  signal_lights/config response).
        Events:   Each coordinator data change fires an event_message containing
                  the full snapshot list. _on_update is called per-coordinator
                  but always sends the full snapshot for all matching entries
                  (intentional — MAX_ENTRIES is tiny and this simplifies the
                  client contract).

    The frontend uses hass.connection.subscribeMessage(callback, msg) which
    delivers the result payload as the first call to callback, then subsequent
    event_message payloads as further calls.

    Unsubscription:
        Stored in connection.subscriptions[msg["id"]]; called by HA when the
        WS connection closes or the client unsubscribes.
    """
    entry_id_filter = msg.get("entry_id")
    domain_data = hass.data.get(DOMAIN, {})

    # Send the initial snapshot as the result payload.
    # HA's subscribeMessage() resolves its promise with this result AND fires
    # the callback for subsequent event_messages. By including data in the result,
    # we avoid the event_message delivery delay on busy HA instances.
    # The JS card handles the initial data from the subscribeMessage callback parameter.
    initial_data = _build_entry_snapshots(domain_data, entry_id_filter)
    connection.send_result(msg["id"], initial_data)

    # Subscribe to coordinator updates
    unsubs = []

    def _unsubscribe() -> None:
        for unsub in unsubs:
            unsub()
        unsubs.clear()

    for eid, coord in domain_data.items():
        if entry_id_filter and eid != entry_id_filter:
            continue

        @callback
        def _on_update(_coord=coord):
            """Send update when coordinator data changes.

            Called per-coordinator; intentionally sends the full snapshot for
            all matching entries (not just the changed entry). _coord is
            captured but unused because we always rebuild the full list.
            """
            try:
                connection.send_message(
                    websocket_api.event_message(
                        msg["id"],
                        _build_entry_snapshots(domain_data, entry_id_filter),
                    )
                )
            except Exception:  # noqa: BLE001
                # Connection likely closed — defer cleanup to avoid calling
                # _unsubscribe from within listener dispatch.
                hass.loop.call_soon(_unsubscribe)

        unsubs.append(coord.async_add_listener(_on_update))

    connection.subscriptions[msg["id"]] = _unsubscribe
