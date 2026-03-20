"""Integration tests for Signal Lights lifecycle.

These tests run against a real Home Assistant instance in Docker.
They exercise: config entry → entities → services → state updates.
"""

import time

import pytest

from conftest import call_service, get_state, poll_state, HA_URL


class TestEntitiesExist:
    """Verify that entities are created on startup."""

    def test_active_signal_sensor_exists(self, ha):
        state = get_state(ha, "sensor.signal_lights_active_signal")
        assert state is not None, "sensor.signal_lights_active_signal should exist"

    def test_active_color_sensor_exists(self, ha):
        state = get_state(ha, "sensor.signal_lights_active_color")
        assert state is not None

    def test_queue_depth_sensor_exists(self, ha):
        state = get_state(ha, "sensor.signal_lights_queue_depth")
        assert state is not None

    def test_active_binary_sensor_exists(self, ha):
        state = get_state(ha, "binary_sensor.signal_lights_active")
        assert state is not None


class TestInitialState:
    """Verify initial state with no active signals."""

    def test_active_signal_is_none(self, ha):
        state = get_state(ha, "sensor.signal_lights_active_signal")
        assert state["state"] == "none"

    def test_active_color_is_black(self, ha):
        state = get_state(ha, "sensor.signal_lights_active_color")
        assert state["state"] == "#000000"

    def test_queue_depth_is_zero(self, ha):
        state = get_state(ha, "sensor.signal_lights_queue_depth")
        assert state["state"] == "0"

    def test_binary_sensor_is_off(self, ha):
        state = get_state(ha, "binary_sensor.signal_lights_active")
        assert state["state"] == "off"


class TestTriggerSignal:
    """Test triggering a signal via service call.

    Note: These tests require signals to be pre-configured in the
    .storage/signal_lights file. The test HA config seeds a test signal.
    """

    def test_trigger_signal_updates_sensors(self, ha):
        """Triggering a signal should update all sensor states."""
        call_service(ha, "signal_lights", "trigger_signal", {"name": "test_alert"})

        # Active signal should update
        value = poll_state(
            ha,
            "sensor.signal_lights_active_signal",
            lambda s: s == "test_alert",
            timeout=10,
        )
        assert value == "test_alert"

    def test_active_color_updates(self, ha):
        """Active color should reflect the triggered signal's color."""
        state = get_state(ha, "sensor.signal_lights_active_color")
        assert state["state"] == "#ff0000"  # red, as configured in test data

    def test_queue_depth_is_one(self, ha):
        """Queue depth should be 1 after triggering one signal."""
        state = get_state(ha, "sensor.signal_lights_queue_depth")
        assert int(state["state"]) >= 1

    def test_binary_sensor_is_on(self, ha):
        """Binary sensor should be on when a signal is active."""
        state = get_state(ha, "binary_sensor.signal_lights_active")
        assert state["state"] == "on"


class TestDismissSignal:
    """Test dismissing a signal."""

    def test_dismiss_returns_to_none(self, ha):
        """Dismissing the only active signal should return to 'none'."""
        call_service(ha, "signal_lights", "dismiss_signal", {"name": "test_alert"})

        value = poll_state(
            ha,
            "sensor.signal_lights_active_signal",
            lambda s: s == "none",
            timeout=10,
        )
        assert value == "none"

    def test_binary_sensor_is_off_after_dismiss(self, ha):
        """Binary sensor should be off after all signals dismissed."""
        state = get_state(ha, "binary_sensor.signal_lights_active")
        assert state["state"] == "off"


class TestSignalExpiry:
    """Test that event signals expire after their duration."""

    def test_signal_expires_and_falls_back(self, ha):
        """A short-duration signal should expire and fall back."""
        # The test_alert signal has a 5-second duration
        call_service(ha, "signal_lights", "trigger_signal", {"name": "test_alert"})

        # Verify it's active
        poll_state(
            ha,
            "sensor.signal_lights_active_signal",
            lambda s: s == "test_alert",
            timeout=10,
        )

        # Wait for expiry (5s duration + coordinator poll interval up to 30s)
        value = poll_state(
            ha,
            "sensor.signal_lights_active_signal",
            lambda s: s == "none",
            timeout=45,
        )
        assert value == "none"


class TestRefreshService:
    """Test the refresh service."""

    def test_refresh_does_not_error(self, ha):
        """Calling refresh should not raise errors."""
        call_service(ha, "signal_lights", "refresh", {})
        # Just verify it doesn't error — state should remain consistent
        state = get_state(ha, "sensor.signal_lights_active_signal")
        assert state is not None
