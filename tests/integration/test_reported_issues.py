"""Integration regression tests for reported GitHub issues.

Issue #13 — "Can't save changes on the Lovelace card":
    1. `update_signal` accepted a changed trigger_config but never regenerated
       the stored Jinja2 template, so the engine kept firing on the OLD
       trigger — edits silently had no effect.
    2. Validation failures in add/update handlers only logged a warning and
       returned; the service call still reported success, so the card showed
       no error and the user saw "Save does nothing".

Issue #12 — "Not able to add signal":
    Submitting the card's add form with a broken entity picker produced a
    cryptic voluptuous error. The backend must reject bad input with a clear,
    user-readable error message (surfaced as the card's error toast).

These run against a real HA instance in Docker and use the WebSocket API —
the exact transport the Lovelace card uses.
"""

import pytest

from conftest import get_signal


@pytest.fixture
def signal(ws, unique_name):
    """Create an entity_equals signal via the service API; remove it after."""
    result = ws.call_service("signal_lights", "add_signal", {
        "name": unique_name,
        "color": [255, 0, 0],
        "trigger_type": "condition",
        "trigger_mode": "entity_equals",
        "trigger_config": {"entity_id": "binary_sensor.front_door", "state": "on"},
        "template": "",
        "duration": 0,
    })
    assert result["success"], f"add_signal failed: {result}"
    yield unique_name
    ws.call_service("signal_lights", "remove_signal", {"name": unique_name})


class TestIssue13UpdateSignal:
    """Editing a signal from the card must actually take effect."""

    def test_add_signal_generates_template(self, ws, signal):
        sig = get_signal(ws, signal)
        assert sig is not None
        assert "binary_sensor.front_door" in sig["template"]

    def test_update_trigger_config_regenerates_template(self, ws, signal):
        """Changing the entity in the edit form must update the template.

        The card sends trigger_mode + trigger_config (no template) — exactly
        this payload. The stored template drives the engine, so it must be
        regenerated from the new config.
        """
        result = ws.call_service("signal_lights", "update_signal", {
            "name": signal,
            "trigger_mode": "entity_equals",
            "trigger_config": {"entity_id": "binary_sensor.back_door", "state": "on"},
        })
        assert result["success"], f"update_signal failed: {result}"

        sig = get_signal(ws, signal)
        assert sig["trigger_config"]["entity_id"] == "binary_sensor.back_door"
        assert "binary_sensor.back_door" in sig["template"], (
            "template was not regenerated from the new trigger_config — "
            f"engine still fires on the old trigger: {sig['template']}"
        )

    def test_update_to_numeric_threshold_regenerates_template(self, ws, signal):
        result = ws.call_service("signal_lights", "update_signal", {
            "name": signal,
            "trigger_mode": "numeric_threshold",
            "trigger_config": {
                "entity_id": "sensor.temperature",
                "threshold": 30,
                "direction": "above",
            },
        })
        assert result["success"], f"update_signal failed: {result}"

        sig = get_signal(ws, signal)
        assert "sensor.temperature" in sig["template"]
        assert ">" in sig["template"]

    def test_update_color_only_keeps_template(self, ws, signal):
        """A color-only edit (card still sends mode+config) must save the
        color and keep a working template."""
        before = get_signal(ws, signal)
        result = ws.call_service("signal_lights", "update_signal", {
            "name": signal,
            "color": [0, 255, 0],
            "trigger_type": "condition",
            "trigger_mode": "entity_equals",
            "trigger_config": {"entity_id": "binary_sensor.front_door", "state": "on"},
            "duration": 0,
        })
        assert result["success"], f"update_signal failed: {result}"

        sig = get_signal(ws, signal)
        assert sig["color"] == [0, 255, 0]
        assert sig["template"] == before["template"]

    def test_rename_via_new_name(self, ws, signal, unique_name):
        new_name = f"{unique_name}_renamed"
        result = ws.call_service("signal_lights", "update_signal", {
            "name": signal,
            "new_name": new_name,
        })
        assert result["success"], f"update_signal rename failed: {result}"
        try:
            assert get_signal(ws, signal) is None
            assert get_signal(ws, new_name) is not None
        finally:
            # rename back so the fixture teardown can clean up
            ws.call_service("signal_lights", "update_signal", {
                "name": new_name,
                "new_name": signal,
            })


class TestIssue13SilentFailures:
    """Failed saves must surface an error to the caller (the card's toast),
    not silently report success."""

    def test_update_with_invalid_trigger_config_errors(self, ws, signal):
        """entity_equals without a state is invalid — the card user must see
        an error, not a successful no-op."""
        result = ws.call_service("signal_lights", "update_signal", {
            "name": signal,
            "trigger_mode": "entity_equals",
            "trigger_config": {"entity_id": "binary_sensor.back_door"},
        })
        assert not result["success"], (
            "update_signal with invalid trigger_config reported success — "
            "the card shows no error and the user sees 'Save does nothing'"
        )
        # And the stored signal must be untouched
        sig = get_signal(ws, signal)
        assert sig["trigger_config"]["entity_id"] == "binary_sensor.front_door"

    def test_update_unknown_signal_errors(self, ws):
        result = ws.call_service("signal_lights", "update_signal", {
            "name": "does_not_exist_anywhere",
            "color": [1, 2, 3],
        })
        assert not result["success"]

    def test_rename_to_existing_name_errors(self, ws, signal, unique_name):
        other = f"{unique_name}_other"
        assert ws.call_service("signal_lights", "add_signal", {
            "name": other,
            "color": [0, 0, 255],
            "trigger_type": "condition",
            "trigger_mode": "entity_on",
            "trigger_config": {"entity_id": "binary_sensor.side_door"},
        })["success"]
        try:
            result = ws.call_service("signal_lights", "update_signal", {
                "name": signal,
                "new_name": other,
            })
            assert not result["success"]
        finally:
            ws.call_service("signal_lights", "remove_signal", {"name": other})


class TestIssue12AddSignal:
    """Adding a signal with bad input must produce a clear error."""

    def test_add_duplicate_name_errors(self, ws, signal):
        result = ws.call_service("signal_lights", "add_signal", {
            "name": signal,
            "color": [255, 0, 0],
            "trigger_type": "condition",
            "trigger_mode": "entity_on",
            "trigger_config": {"entity_id": "binary_sensor.front_door"},
        })
        assert not result["success"], (
            "duplicate add_signal reported success — card user gets no feedback"
        )

    def test_add_with_missing_entity_errors_clearly(self, ws, unique_name):
        """The card submit with a broken picker sends entity_id '' — the
        error must mention the entity so the user can act on it."""
        result = ws.call_service("signal_lights", "add_signal", {
            "name": unique_name,
            "color": [255, 0, 0],
            "trigger_type": "condition",
            "trigger_mode": "entity_equals",
            "trigger_config": {"entity_id": "", "state": "on"},
            "template": "",
            "duration": 0,
        })
        assert not result["success"]
        message = result.get("error", {}).get("message", "").lower()
        assert "entity" in message
        # Nothing half-created
        assert get_signal(ws, unique_name) is None

    def test_add_with_template_mode_and_no_template_errors(self, ws, unique_name):
        result = ws.call_service("signal_lights", "add_signal", {
            "name": unique_name,
            "color": [255, 0, 0],
            "trigger_type": "condition",
            "trigger_mode": "template",
            "template": "",
        })
        assert not result["success"]
        assert get_signal(ws, unique_name) is None

    def test_add_valid_signal_succeeds_and_appears_in_card_config(self, ws, unique_name):
        """Happy path: the exact payload the card's add form sends."""
        result = ws.call_service("signal_lights", "add_signal", {
            "name": unique_name,
            "color": [0, 128, 255],
            "trigger_type": "event",
            "trigger_mode": "entity_equals",
            "trigger_config": {"entity_id": "person.tess", "state": "home"},
            "template": "",
            "duration": 60,
        })
        assert result["success"], f"add_signal failed: {result}"
        try:
            sig = get_signal(ws, unique_name)
            assert sig is not None
            assert sig["trigger_config"]["entity_id"] == "person.tess"
            assert "person.tess" in sig["template"]
            assert sig["duration"] == 60
        finally:
            ws.call_service("signal_lights", "remove_signal", {"name": unique_name})
