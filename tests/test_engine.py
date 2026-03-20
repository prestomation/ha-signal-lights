"""Unit tests for the Signal Lights engine.

Pure Python — no Home Assistant dependencies required.
Run with: python -m pytest tests/test_engine.py -v
"""

import time
from unittest.mock import patch

import pytest

# Import engine module directly (no HA dependencies) to avoid __init__.py
# pulling in HA-specific imports like StaticPathConfig
import sys
import os
import importlib.util

_engine_path = os.path.join(
    os.path.dirname(__file__), "..", "custom_components", "signal_lights", "engine.py"
)
_spec = importlib.util.spec_from_file_location("signal_lights_engine", _engine_path)
_engine_mod = importlib.util.module_from_spec(_spec)
sys.modules["signal_lights_engine"] = _engine_mod  # register before exec for dataclass compat
_spec.loader.exec_module(_engine_mod)

Signal = _engine_mod.Signal
LightConfig = _engine_mod.LightConfig
ActiveSignal = _engine_mod.ActiveSignal
SignalEngine = _engine_mod.SignalEngine
generate_template_from_trigger = _engine_mod.generate_template_from_trigger
validate_trigger_config = _engine_mod.validate_trigger_config


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def engine():
    """Return a fresh SignalEngine instance."""
    return SignalEngine()


@pytest.fixture
def sample_lights():
    """Return a list of sample light configs."""
    return [
        LightConfig(entity_id="light.desk_lamp", brightness=255),
        LightConfig(entity_id="light.floor_lamp", brightness=128),
        LightConfig(entity_id="light.bedroom", brightness=200),
    ]


@pytest.fixture
def sample_signals():
    """Return a list of sample signals with varying sort_orders."""
    return [
        Signal(
            name="critical_alert",
            color=(255, 0, 0),
            trigger_type="event",
            template="{{ true }}",
            duration=30,
            sort_order=0,
        ),
        Signal(
            name="door_open",
            color=(255, 165, 0),
            trigger_type="condition",
            template="{{ is_state('binary_sensor.door', 'on') }}",
            sort_order=1,
        ),
        Signal(
            name="low_battery",
            color=(255, 255, 0),
            trigger_type="condition",
            template="{{ states('sensor.battery') | int < 20 }}",
            sort_order=4,
        ),
        Signal(
            name="person_home",
            color=(255, 0, 255),
            trigger_type="event",
            template="{{ is_state('person.a', 'home') }}",
            duration=60,
            sort_order=2,
        ),
    ]


# ---------------------------------------------------------------------------
# Signal priority ordering (by sort_order)
# ---------------------------------------------------------------------------


class TestSignalPriority:
    """Test signal priority ordering by sort_order."""

    def test_lowest_sort_order_wins(self, engine, sample_lights, sample_signals):
        """Lower sort_order should win over higher."""
        engine.set_lights(sample_lights)
        engine.set_signals(sample_signals)

        # Activate low-priority signal first (sort_order=4)
        engine.activate_signal("low_battery")
        winner = engine.get_global_winner()
        assert winner.name == "low_battery"

        # Activate higher-priority signal (sort_order=1)
        engine.activate_signal("door_open")
        winner = engine.get_global_winner()
        assert winner.name == "door_open"

        # Activate highest-priority signal (sort_order=0)
        engine.activate_signal("critical_alert")
        winner = engine.get_global_winner()
        assert winner.name == "critical_alert"

    def test_sort_order_determines_winner(self, engine, sample_lights):
        """Sort_order alone determines which signal wins."""
        signals = [
            Signal(name="alpha", color=(255, 0, 0),
                   trigger_type="condition", template="", sort_order=2),
            Signal(name="beta", color=(0, 255, 0),
                   trigger_type="condition", template="", sort_order=1),
        ]
        engine.set_lights(sample_lights)
        engine.set_signals(signals)

        engine.activate_signal("alpha")
        engine.activate_signal("beta")

        winner = engine.get_global_winner()
        assert winner.name == "beta"  # lower sort_order wins

    def test_deactivation_promotes_next(self, engine, sample_lights, sample_signals):
        """When the winning signal is deactivated, the next one takes over."""
        engine.set_lights(sample_lights)
        engine.set_signals(sample_signals)

        engine.activate_signal("critical_alert")  # sort_order=0
        engine.activate_signal("door_open")       # sort_order=1
        engine.activate_signal("low_battery")     # sort_order=4

        assert engine.get_global_winner().name == "critical_alert"

        engine.deactivate_signal("critical_alert")
        assert engine.get_global_winner().name == "door_open"

        engine.deactivate_signal("door_open")
        assert engine.get_global_winner().name == "low_battery"


# ---------------------------------------------------------------------------
# Event signal expiry
# ---------------------------------------------------------------------------


class TestEventSignalExpiry:
    """Test event signal expiration behavior."""

    def test_event_signal_expires_after_duration(self, engine, sample_lights):
        """Event signals should expire after their duration."""
        signal = Signal(
            name="flash",
            color=(255, 0, 0),
            trigger_type="event",
            template="",
            duration=5,
            sort_order=0,
        )
        engine.set_lights(sample_lights)
        engine.set_signals([signal])

        now = time.monotonic()
        engine.activate_signal("flash", now=now)
        assert engine.get_queue_depth() == 1

        # Check the active signal's expiry
        active = engine.get_active_signals()
        assert len(active) == 1
        assert active[0].expires_at == pytest.approx(now + 5, abs=1)

    def test_expired_signal_is_cleaned_up(self, engine, sample_lights):
        """Expired event signals should be removed on cleanup."""
        signal = Signal(
            name="flash",
            color=(255, 0, 0),
            trigger_type="event",
            template="",
            duration=1,
            sort_order=0,
        )
        engine.set_lights(sample_lights)
        engine.set_signals([signal])

        now = time.monotonic()
        engine.activate_signal("flash", now=now)
        assert engine.get_queue_depth() == 1

        # Force the active signal's expiry time to be in the past
        engine._active[0].expires_at = time.monotonic() - 1

        expired = engine.cleanup_expired()
        assert "flash" in expired
        assert engine.get_queue_depth() == 0

    def test_condition_signal_does_not_expire(self, engine, sample_lights):
        """Condition signals should never auto-expire."""
        signal = Signal(
            name="persistent",
            color=(0, 255, 0),
            trigger_type="condition",
            template="",
            sort_order=0,
        )
        engine.set_lights(sample_lights)
        engine.set_signals([signal])

        engine.activate_signal("persistent")
        active = engine.get_active_signals()
        assert len(active) == 1
        assert active[0].expires_at is None
        assert not active[0].is_expired

    def test_expiry_promotes_next_signal(self, engine, sample_lights):
        """When an event signal expires, the next sort_order takes over."""
        signals = [
            Signal(name="urgent", color=(255, 0, 0),
                   trigger_type="event", template="", duration=5, sort_order=0),
            Signal(name="background", color=(0, 0, 255),
                   trigger_type="condition", template="", sort_order=1),
        ]
        engine.set_lights(sample_lights)
        engine.set_signals(signals)

        now = time.monotonic()
        engine.activate_signal("urgent", now=now)
        engine.activate_signal("background", now=now)

        assert engine.get_global_winner().name == "urgent"

        # Expire the urgent signal
        for active in engine._active:
            if active.signal.name == "urgent":
                active.expires_at = time.monotonic() - 1
                break

        engine.cleanup_expired()
        assert engine.get_global_winner().name == "background"


# ---------------------------------------------------------------------------
# Condition signal activation/deactivation
# ---------------------------------------------------------------------------


class TestConditionSignals:
    """Test condition signal behavior."""

    def test_condition_activate_deactivate(self, engine, sample_lights):
        """Condition signals activate and deactivate cleanly."""
        signal = Signal(
            name="door_open",
            color=(255, 165, 0),
            trigger_type="condition",
            template="",
            sort_order=0,
        )
        engine.set_lights(sample_lights)
        engine.set_signals([signal])

        # Not active initially
        assert engine.get_queue_depth() == 0
        assert engine.get_global_winner() is None

        # Activate
        engine.activate_signal("door_open")
        assert engine.get_queue_depth() == 1
        assert engine.get_global_winner().name == "door_open"

        # Deactivate
        engine.deactivate_signal("door_open")
        assert engine.get_queue_depth() == 0
        assert engine.get_global_winner() is None

    def test_double_activate_is_idempotent(self, engine, sample_lights):
        """Activating an already-active signal should not create duplicates."""
        signal = Signal(
            name="alert",
            color=(255, 0, 0),
            trigger_type="condition",
            template="",
            sort_order=0,
        )
        engine.set_lights(sample_lights)
        engine.set_signals([signal])

        engine.activate_signal("alert")
        engine.activate_signal("alert")
        assert engine.get_queue_depth() == 1

    def test_deactivate_nonexistent_returns_false(self, engine):
        """Deactivating a signal that isn't active returns False."""
        assert engine.deactivate_signal("nonexistent") is False


# ---------------------------------------------------------------------------
# Per-light filtering
# ---------------------------------------------------------------------------


class TestPerLightFiltering:
    """Test per-light signal filtering."""

    def test_signal_applies_to_all_lights_by_default(self, engine, sample_lights):
        """A signal with no light_filter applies to all lights."""
        signal = Signal(
            name="global_alert",
            color=(255, 0, 0),
            trigger_type="condition",
            template="",
            sort_order=0,
        )
        engine.set_lights(sample_lights)
        engine.set_signals([signal])
        engine.activate_signal("global_alert")

        states = engine.evaluate()
        for light in sample_lights:
            assert states[light.entity_id] is not None
            assert states[light.entity_id]["rgb_color"] == (255, 0, 0)

    def test_signal_filtered_to_specific_lights(self, engine, sample_lights):
        """A signal with light_filter only applies to specified lights."""
        signals = [
            Signal(
                name="desk_only",
                color=(0, 255, 0),
                trigger_type="condition",
                template="",
                light_filter=["light.desk_lamp"],
                sort_order=0,
            ),
        ]
        engine.set_lights(sample_lights)
        engine.set_signals(signals)
        engine.activate_signal("desk_only")

        states = engine.evaluate()
        assert states["light.desk_lamp"] is not None
        assert states["light.desk_lamp"]["rgb_color"] == (0, 255, 0)
        assert states["light.floor_lamp"] is None
        assert states["light.bedroom"] is None

    def test_different_signals_for_different_lights(self, engine, sample_lights):
        """Different lights can show different signals based on filters."""
        signals = [
            Signal(
                name="desk_alert",
                color=(255, 0, 0),
                trigger_type="condition",
                template="",
                light_filter=["light.desk_lamp"],
                sort_order=0,
            ),
            Signal(
                name="bedroom_alert",
                color=(0, 0, 255),
                trigger_type="condition",
                template="",
                light_filter=["light.bedroom"],
                sort_order=1,
            ),
        ]
        engine.set_lights(sample_lights)
        engine.set_signals(signals)
        engine.activate_signal("desk_alert")
        engine.activate_signal("bedroom_alert")

        states = engine.evaluate()
        assert states["light.desk_lamp"]["rgb_color"] == (255, 0, 0)
        assert states["light.bedroom"]["rgb_color"] == (0, 0, 255)
        assert states["light.floor_lamp"] is None  # No signal applies

    def test_filtered_signal_falls_through_to_global(self, engine, sample_lights):
        """A light not in a filter falls through to the next matching signal."""
        signals = [
            Signal(
                name="desk_specific",
                color=(255, 0, 0),
                trigger_type="condition",
                template="",
                light_filter=["light.desk_lamp"],
                sort_order=0,
            ),
            Signal(
                name="global_background",
                color=(0, 255, 0),
                trigger_type="condition",
                template="",
                sort_order=1,
            ),
        ]
        engine.set_lights(sample_lights)
        engine.set_signals(signals)
        engine.activate_signal("desk_specific")
        engine.activate_signal("global_background")

        states = engine.evaluate()
        # desk_lamp gets the higher-priority desk-specific signal
        assert states["light.desk_lamp"]["rgb_color"] == (255, 0, 0)
        # Other lights get the global background signal
        assert states["light.floor_lamp"]["rgb_color"] == (0, 255, 0)
        assert states["light.bedroom"]["rgb_color"] == (0, 255, 0)


# ---------------------------------------------------------------------------
# Empty queue → lights off
# ---------------------------------------------------------------------------


class TestEmptyQueue:
    """Test behavior when no signals are active."""

    def test_no_signals_all_lights_off(self, engine, sample_lights):
        """When no signals are active, all lights should turn off."""
        engine.set_lights(sample_lights)
        engine.set_signals([])

        states = engine.evaluate()
        for light in sample_lights:
            assert states[light.entity_id] is None

    def test_all_signals_deactivated_lights_off(self, engine, sample_lights):
        """After all signals are deactivated, lights should turn off."""
        signal = Signal(
            name="temp",
            color=(255, 0, 0),
            trigger_type="condition",
            template="",
            sort_order=0,
        )
        engine.set_lights(sample_lights)
        engine.set_signals([signal])

        engine.activate_signal("temp")
        states = engine.evaluate()
        assert all(s is not None for s in states.values())

        engine.deactivate_signal("temp")
        states = engine.evaluate()
        assert all(s is None for s in states.values())

    def test_empty_queue_depth_is_zero(self, engine):
        """Queue depth should be 0 with no active signals."""
        assert engine.get_queue_depth() == 0

    def test_global_winner_is_none(self, engine):
        """Global winner should be None with no active signals."""
        assert engine.get_global_winner() is None


# ---------------------------------------------------------------------------
# Brightness per light
# ---------------------------------------------------------------------------


class TestBrightness:
    """Test that per-light brightness is respected."""

    def test_brightness_included_in_state(self, engine):
        """Light brightness should be included in the evaluate result."""
        lights = [
            LightConfig(entity_id="light.dim", brightness=50),
            LightConfig(entity_id="light.bright", brightness=255),
        ]
        signal = Signal(
            name="alert",
            color=(255, 0, 0),
            trigger_type="condition",
            template="",
            sort_order=0,
        )
        engine.set_lights(lights)
        engine.set_signals([signal])
        engine.activate_signal("alert")

        states = engine.evaluate()
        assert states["light.dim"]["brightness"] == 50
        assert states["light.bright"]["brightness"] == 255


# ---------------------------------------------------------------------------
# Dismiss signal (service)
# ---------------------------------------------------------------------------


class TestDismissSignal:
    """Test the dismiss_signal method."""

    def test_dismiss_active_signal(self, engine, sample_lights, sample_signals):
        """Dismissing an active signal removes it."""
        engine.set_lights(sample_lights)
        engine.set_signals(sample_signals)

        engine.activate_signal("door_open")
        assert engine.get_queue_depth() == 1

        result = engine.dismiss_signal("door_open")
        assert result is True
        assert engine.get_queue_depth() == 0

    def test_dismiss_nonexistent_signal(self, engine):
        """Dismissing a signal that isn't active returns False."""
        result = engine.dismiss_signal("nonexistent")
        assert result is False


# ---------------------------------------------------------------------------
# Activate unknown signal
# ---------------------------------------------------------------------------


class TestActivateUnknown:
    """Test activating a signal that doesn't exist in configuration."""

    def test_activate_unknown_returns_false(self, engine):
        """Activating a signal not in the configuration returns False."""
        result = engine.activate_signal("nonexistent")
        assert result is False


# ---------------------------------------------------------------------------
# Signal.applies_to_light
# ---------------------------------------------------------------------------


class TestSignalApplies:
    """Test Signal.applies_to_light method."""

    def test_empty_filter_applies_to_all(self):
        """Empty light_filter means signal applies to all lights."""
        signal = Signal(
            name="test", color=(0, 0, 0),
            trigger_type="condition", template="",
        )
        assert signal.applies_to_light("light.any")

    def test_filter_includes_light(self):
        """Signal with filter applies to lights in the filter."""
        signal = Signal(
            name="test", color=(0, 0, 0),
            trigger_type="condition", template="",
            light_filter=["light.specific"],
        )
        assert signal.applies_to_light("light.specific")
        assert not signal.applies_to_light("light.other")


# ---------------------------------------------------------------------------
# Trigger mode template generation
# ---------------------------------------------------------------------------


class TestTriggerModes:
    """Test generate_template_from_trigger for all trigger modes."""

    def test_entity_equals_generates_template(self):
        """entity_equals mode generates is_state template."""
        template = generate_template_from_trigger(
            "entity_equals",
            {"entity_id": "binary_sensor.back_door", "state": "on"},
        )
        assert template == "{{ is_state('binary_sensor.back_door', 'on') }}"

    def test_entity_on_generates_template(self):
        """entity_on mode generates is_state(..., 'on') template."""
        template = generate_template_from_trigger(
            "entity_on",
            {"entity_id": "switch.porch_light"},
        )
        assert template == "{{ is_state('switch.porch_light', 'on') }}"

    def test_numeric_threshold_above_generates_template(self):
        """numeric_threshold above generates > comparison template."""
        template = generate_template_from_trigger(
            "numeric_threshold",
            {"entity_id": "sensor.temperature", "threshold": 30, "direction": "above"},
        )
        assert template == "{{ states('sensor.temperature') | float(0) > 30 }}"

    def test_numeric_threshold_below_generates_template(self):
        """numeric_threshold below generates < comparison template."""
        template = generate_template_from_trigger(
            "numeric_threshold",
            {"entity_id": "sensor.battery_level", "threshold": 20, "direction": "below"},
        )
        assert template == "{{ states('sensor.battery_level') | float(0) < 20 }}"

    def test_template_mode_passes_through(self):
        """template mode returns the raw template string."""
        raw = "{{ states('sensor.x') | int > 5 }}"
        template = generate_template_from_trigger(
            "template",
            {"template": raw},
        )
        assert template == raw

    def test_unknown_mode_returns_empty(self):
        """Unknown trigger mode returns empty string."""
        template = generate_template_from_trigger("unknown_mode", {})
        assert template == ""

    def test_entity_equals_missing_fields_raises_value_error(self):
        """entity_equals with missing fields raises ValueError."""
        with pytest.raises(ValueError, match="entity_id is required"):
            generate_template_from_trigger("entity_equals", {})


# ---------------------------------------------------------------------------
# Signal with trigger_mode and trigger_config
# ---------------------------------------------------------------------------


class TestSignalTriggerMode:
    """Test Signal dataclass with trigger_mode and trigger_config."""

    def test_signal_stores_trigger_mode(self):
        """Signal should store trigger_mode."""
        signal = Signal(
            name="test",
            color=(255, 0, 0),
            trigger_type="condition",
            template="{{ is_state('sensor.x', 'on') }}",
            trigger_mode="entity_equals",
            trigger_config={"entity_id": "sensor.x", "state": "on"},
        )
        assert signal.trigger_mode == "entity_equals"
        assert signal.trigger_config == {"entity_id": "sensor.x", "state": "on"}

    def test_signal_defaults_to_template_mode(self):
        """Signal should default to template trigger mode."""
        signal = Signal(
            name="test",
            color=(255, 0, 0),
            trigger_type="condition",
            template="{{ true }}",
        )
        assert signal.trigger_mode == "template"
        assert signal.trigger_config == {}


# ---------------------------------------------------------------------------
# Sort order based ordering
# ---------------------------------------------------------------------------


class TestSortOrderOnly:
    """Test that ordering is purely by sort_order."""

    def test_sort_order_determines_ordering(self, engine, sample_lights):
        """sort_order alone determines which signal wins."""
        signals = [
            Signal(name="low_order", color=(255, 0, 0),
                   trigger_type="condition", template="", sort_order=0),
            Signal(name="high_order", color=(0, 255, 0),
                   trigger_type="condition", template="", sort_order=1),
        ]
        engine.set_lights(sample_lights)
        engine.set_signals(signals)

        engine.activate_signal("low_order")
        engine.activate_signal("high_order")

        # sort_order=0 wins
        winner = engine.get_global_winner()
        assert winner.name == "low_order"


# ---------------------------------------------------------------------------
# Trigger config validation
# ---------------------------------------------------------------------------


class TestTriggerValidation:
    """Test validate_trigger_config for all trigger modes."""

    # --- entity_equals ---

    def test_entity_equals_valid(self):
        """entity_equals with all required fields returns no errors."""
        errors = validate_trigger_config(
            "entity_equals",
            {"entity_id": "binary_sensor.door", "state": "on"},
        )
        assert errors == []

    def test_entity_equals_missing_entity_id(self):
        """entity_equals without entity_id returns an error."""
        errors = validate_trigger_config("entity_equals", {"state": "on"})
        assert any("entity_id" in e for e in errors)

    def test_entity_equals_empty_entity_id(self):
        """entity_equals with empty entity_id returns an error."""
        errors = validate_trigger_config("entity_equals", {"entity_id": "", "state": "on"})
        assert any("entity_id" in e for e in errors)

    def test_entity_equals_missing_state(self):
        """entity_equals without state returns an error."""
        errors = validate_trigger_config("entity_equals", {"entity_id": "binary_sensor.door"})
        assert any("state" in e for e in errors)

    def test_entity_equals_empty_state(self):
        """entity_equals with empty state returns an error."""
        errors = validate_trigger_config(
            "entity_equals", {"entity_id": "binary_sensor.door", "state": ""}
        )
        assert any("state" in e for e in errors)

    def test_entity_equals_both_missing(self):
        """entity_equals with no fields returns two errors."""
        errors = validate_trigger_config("entity_equals", {})
        assert len(errors) == 2

    # --- entity_on ---

    def test_entity_on_valid(self):
        """entity_on with entity_id returns no errors."""
        errors = validate_trigger_config("entity_on", {"entity_id": "switch.fan"})
        assert errors == []

    def test_entity_on_missing_entity_id(self):
        """entity_on without entity_id returns an error."""
        errors = validate_trigger_config("entity_on", {})
        assert any("entity_id" in e for e in errors)

    def test_entity_on_empty_entity_id(self):
        """entity_on with empty entity_id returns an error."""
        errors = validate_trigger_config("entity_on", {"entity_id": "  "})
        assert any("entity_id" in e for e in errors)

    # --- numeric_threshold ---

    def test_numeric_threshold_valid(self):
        """numeric_threshold with all valid fields returns no errors."""
        errors = validate_trigger_config(
            "numeric_threshold",
            {"entity_id": "sensor.temp", "threshold": 30, "direction": "above"},
        )
        assert errors == []

    def test_numeric_threshold_valid_below(self):
        """numeric_threshold with direction=below is valid."""
        errors = validate_trigger_config(
            "numeric_threshold",
            {"entity_id": "sensor.battery", "threshold": 20.5, "direction": "below"},
        )
        assert errors == []

    def test_numeric_threshold_missing_entity_id(self):
        """numeric_threshold without entity_id returns an error."""
        errors = validate_trigger_config(
            "numeric_threshold",
            {"threshold": 30, "direction": "above"},
        )
        assert any("entity_id" in e for e in errors)

    def test_numeric_threshold_missing_threshold(self):
        """numeric_threshold without threshold returns an error."""
        errors = validate_trigger_config(
            "numeric_threshold",
            {"entity_id": "sensor.temp", "direction": "above"},
        )
        assert any("threshold" in e for e in errors)

    def test_numeric_threshold_non_numeric_threshold(self):
        """numeric_threshold with non-numeric threshold returns an error."""
        errors = validate_trigger_config(
            "numeric_threshold",
            {"entity_id": "sensor.temp", "threshold": "hot", "direction": "above"},
        )
        assert any("threshold" in e and "numeric" in e for e in errors)

    def test_numeric_threshold_invalid_direction(self):
        """numeric_threshold with invalid direction returns an error."""
        errors = validate_trigger_config(
            "numeric_threshold",
            {"entity_id": "sensor.temp", "threshold": 30, "direction": "sideways"},
        )
        assert any("direction" in e for e in errors)

    def test_numeric_threshold_all_missing(self):
        """numeric_threshold with empty config returns multiple errors."""
        errors = validate_trigger_config("numeric_threshold", {})
        assert len(errors) >= 3  # entity_id, threshold, direction

    # --- template ---

    def test_template_valid(self):
        """template mode with non-empty template returns no errors."""
        errors = validate_trigger_config(
            "template", {"template": "{{ is_state('sensor.x', 'on') }}"}
        )
        assert errors == []

    def test_template_missing_key(self):
        """template mode with no template key returns an error."""
        errors = validate_trigger_config("template", {})
        assert any("template" in e for e in errors)

    def test_template_empty_string(self):
        """template mode with empty template string returns an error."""
        errors = validate_trigger_config("template", {"template": ""})
        assert any("template" in e for e in errors)

    def test_template_whitespace_only(self):
        """template mode with whitespace-only template returns an error."""
        errors = validate_trigger_config("template", {"template": "   "})
        assert any("template" in e for e in errors)

    # --- generate_template_from_trigger raises ValueError ---

    def test_generate_raises_for_invalid_entity_equals(self):
        """generate_template_from_trigger raises ValueError for invalid entity_equals."""
        with pytest.raises(ValueError):
            generate_template_from_trigger("entity_equals", {})

    def test_generate_raises_for_invalid_entity_on(self):
        """generate_template_from_trigger raises ValueError for invalid entity_on."""
        with pytest.raises(ValueError):
            generate_template_from_trigger("entity_on", {"entity_id": ""})

    def test_generate_raises_for_invalid_numeric_threshold(self):
        """generate_template_from_trigger raises ValueError for invalid numeric_threshold."""
        with pytest.raises(ValueError):
            generate_template_from_trigger("numeric_threshold", {})

    def test_generate_raises_for_invalid_template(self):
        """generate_template_from_trigger raises ValueError for empty template mode."""
        with pytest.raises(ValueError):
            generate_template_from_trigger("template", {"template": ""})

    def test_generate_succeeds_for_valid_entity_equals(self):
        """generate_template_from_trigger returns correct template for valid config."""
        result = generate_template_from_trigger(
            "entity_equals", {"entity_id": "binary_sensor.door", "state": "on"}
        )
        assert result == "{{ is_state('binary_sensor.door', 'on') }}"

    def test_generate_succeeds_for_valid_entity_on(self):
        """generate_template_from_trigger returns correct template for valid entity_on."""
        result = generate_template_from_trigger(
            "entity_on", {"entity_id": "switch.fan"}
        )
        assert result == "{{ is_state('switch.fan', 'on') }}"

    def test_generate_succeeds_for_valid_numeric_threshold(self):
        """generate_template_from_trigger returns correct template for valid numeric."""
        result = generate_template_from_trigger(
            "numeric_threshold",
            {"entity_id": "sensor.temp", "threshold": 30, "direction": "above"},
        )
        assert result == "{{ states('sensor.temp') | float(0) > 30 }}"

    def test_generate_succeeds_for_valid_template(self):
        """generate_template_from_trigger returns raw template for template mode."""
        raw = "{{ states('sensor.x') | int > 5 }}"
        result = generate_template_from_trigger("template", {"template": raw})
        assert result == raw
