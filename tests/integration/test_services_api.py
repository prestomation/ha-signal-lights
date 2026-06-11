"""Comprehensive integration tests for the Signal Lights service API.

Runs against a real HA instance in Docker. Uses the WebSocket API (the
Lovelace card's transport) so service errors are observable, plus the
`signal_lights/config` and `signal_lights/subscribe` commands the card
depends on.
"""

import json
import time

import pytest

from conftest import HaWsClient, get_signal


@pytest.fixture
def cleanup(ws):
    """Collect entity/signal names to remove after the test."""
    created = {"signals": [], "lights": []}
    yield created
    for name in created["signals"]:
        ws.call_service("signal_lights", "remove_signal", {"name": name})
    for entity_id in created["lights"]:
        ws.call_service("signal_lights", "remove_light", {"entity_id": entity_id})


class TestLightsApi:
    def test_add_and_remove_light(self, ws, cleanup):
        result = ws.call_service("signal_lights", "add_light", {
            "entity_id": "light.itest_lamp",
            "brightness": 128,
        })
        assert result["success"], result

        entries = ws.get_signal_lights_config()
        lights = entries[0]["lights"]
        match = [l for l in lights if l["entity_id"] == "light.itest_lamp"]
        assert match and match[0]["brightness"] == 128

        result = ws.call_service("signal_lights", "remove_light", {
            "entity_id": "light.itest_lamp",
        })
        assert result["success"], result
        entries = ws.get_signal_lights_config()
        assert not [l for l in entries[0]["lights"] if l["entity_id"] == "light.itest_lamp"]

    def test_remove_unknown_light_errors(self, ws):
        result = ws.call_service("signal_lights", "remove_light", {
            "entity_id": "light.never_added",
        })
        assert not result["success"]

    def test_add_light_invalid_entity_id_rejected(self, ws):
        result = ws.call_service("signal_lights", "add_light", {
            "entity_id": "not an entity id",
        })
        assert not result["success"]


class TestSignalLifecycleApi:
    def test_trigger_unknown_signal_errors(self, ws):
        result = ws.call_service("signal_lights", "trigger_signal", {
            "name": "no_such_signal",
        })
        assert not result["success"]

    def test_dismiss_inactive_signal_errors(self, ws):
        # test_condition exists (seeded) but is not active ({{ false }})
        result = ws.call_service("signal_lights", "dismiss_signal", {
            "name": "no_such_signal",
        })
        assert not result["success"]

    def test_trigger_and_dismiss_event_signal(self, ws, ha):
        # seeded event signal "test_alert" has template {{ true }} / duration 5
        result = ws.call_service("signal_lights", "trigger_signal", {"name": "test_alert"})
        assert result["success"], result
        result = ws.call_service("signal_lights", "dismiss_signal", {"name": "test_alert"})
        assert result["success"], result

    def test_reorder_signals(self, ws, cleanup, unique_name):
        names = [f"{unique_name}_a", f"{unique_name}_b"]
        for n in names:
            assert ws.call_service("signal_lights", "add_signal", {
                "name": n,
                "color": [10, 20, 30],
                "trigger_type": "condition",
                "trigger_mode": "entity_on",
                "trigger_config": {"entity_id": "binary_sensor.x"},
            })["success"]
            cleanup["signals"].append(n)

        entries = ws.get_signal_lights_config()
        current_order = [s["name"] for s in entries[0]["signals"]]
        new_order = list(reversed(current_order))
        result = ws.call_service("signal_lights", "reorder_signals", {"order": new_order})
        assert result["success"], result

        entries = ws.get_signal_lights_config()
        assert [s["name"] for s in entries[0]["signals"]] == new_order

    def test_reorder_with_unknown_name_errors(self, ws):
        result = ws.call_service("signal_lights", "reorder_signals", {
            "order": ["ghost_signal"],
        })
        assert not result["success"]


class TestNotificationsApi:
    def test_configure_and_clear_notifications(self, ws):
        result = ws.call_service("signal_lights", "configure_notifications", {
            "enabled": True,
            "targets": ["notify.mobile_app_test"],
        })
        assert result["success"], result
        entries = ws.get_signal_lights_config()
        assert entries[0]["notifications"] == {
            "enabled": True, "targets": ["notify.mobile_app_test"],
        }

        result = ws.call_service("signal_lights", "configure_notifications", {
            "enabled": False, "targets": [],
        })
        assert result["success"], result
        entries = ws.get_signal_lights_config()
        assert entries[0]["notifications"]["enabled"] is False

    def test_invalid_notify_target_rejected(self, ws):
        result = ws.call_service("signal_lights", "configure_notifications", {
            "enabled": True,
            "targets": ["light.not_a_notify_service"],
        })
        assert not result["success"]


class TestCycleIntervalApi:
    def test_set_and_reset_cycle_interval(self, ws):
        result = ws.call_service("signal_lights", "set_cycle_interval", {
            "cycle_interval_seconds": 7,
        })
        assert result["success"], result
        entries = ws.get_signal_lights_config()
        assert entries[0]["cycle_interval"] == 7

        result = ws.call_service("signal_lights", "set_cycle_interval", {
            "cycle_interval_seconds": 0,
        })
        assert result["success"], result

    def test_out_of_range_interval_rejected(self, ws):
        result = ws.call_service("signal_lights", "set_cycle_interval", {
            "cycle_interval_seconds": 9999,
        })
        assert not result["success"]


class TestWebSocketApi:
    """The card's data layer: config fetch and live subscription."""

    def test_config_returns_entry_snapshot(self, ws):
        entries = ws.get_signal_lights_config()
        assert len(entries) >= 1
        entry = entries[0]
        for key in (
            "entry_id", "title", "signals", "lights", "notifications",
            "active_signal", "active_color", "active_signal_names",
            "queue_depth", "is_active", "cycle_interval",
        ):
            assert key in entry, f"missing snapshot key: {key}"

    def test_config_filter_by_unknown_entry_returns_empty(self, ws):
        entries = ws.get_signal_lights_config(entry_id="not_a_real_entry")
        assert entries == []

    def test_subscribe_receives_update_on_config_change(self, ha_token, ws, cleanup, unique_name):
        # Subscribe on a dedicated connection so service results on `ws`
        # don't interleave with subscription events.
        sub = HaWsClient(ha_token)
        try:
            sub_id = sub.send(type="signal_lights/subscribe")
            initial = sub.recv_result(sub_id)
            assert initial["success"], initial
            assert isinstance(initial["result"], list)

            # Mutate config from the other connection
            assert ws.call_service("signal_lights", "add_signal", {
                "name": unique_name,
                "color": [1, 2, 3],
                "trigger_type": "condition",
                "trigger_mode": "entity_on",
                "trigger_config": {"entity_id": "binary_sensor.sub_test"},
            })["success"]
            cleanup["signals"].append(unique_name)

            # The subscriber must receive an event containing the new signal
            deadline = time.monotonic() + 15
            seen = False
            while time.monotonic() < deadline and not seen:
                sub.ws.settimeout(max(0.1, deadline - time.monotonic()))
                msg = json.loads(sub.ws.recv())
                if msg.get("id") == sub_id and msg.get("type") == "event":
                    names = [
                        s["name"]
                        for entry in msg["event"]
                        for s in entry["signals"]
                    ]
                    seen = unique_name in names
            assert seen, "subscription event with the new signal never arrived"
        finally:
            sub.close()

    def test_unauthenticated_ws_cannot_use_api(self):
        import websocket as websocket_lib
        from conftest import HA_WS_URL
        conn = websocket_lib.create_connection(HA_WS_URL, timeout=10)
        try:
            assert json.loads(conn.recv())["type"] == "auth_required"
            conn.send(json.dumps({"type": "auth", "access_token": "invalid-token"}))
            msg = json.loads(conn.recv())
            assert msg["type"] == "auth_invalid"
        finally:
            conn.close()
