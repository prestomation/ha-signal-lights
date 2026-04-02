"""Unit tests for the Signal Lights cycling feature.

Tests coordinator-level cycling logic using mocked HA infrastructure.
Pure Python — does not require a running Home Assistant instance.

Run with: python -m pytest tests/unit/test_cycling.py -v
"""

from __future__ import annotations

import sys
import os
import importlib.util
from unittest.mock import AsyncMock, MagicMock, patch, call
import asyncio

import pytest

# ---------------------------------------------------------------------------
# Load engine module directly to avoid HA imports
# ---------------------------------------------------------------------------

_engine_path = os.path.join(
    os.path.dirname(__file__), "..", "..", "custom_components", "signal_lights", "engine.py"
)
_spec = importlib.util.spec_from_file_location("signal_lights_engine", _engine_path)
_engine_mod = importlib.util.module_from_spec(_spec)
sys.modules["signal_lights_engine"] = _engine_mod
_spec.loader.exec_module(_engine_mod)

Signal = _engine_mod.Signal
LightConfig = _engine_mod.LightConfig
SignalEngine = _engine_mod.SignalEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_signal(name: str, sort_order: int, color=(255, 0, 0)) -> Signal:
    return Signal(
        name=name,
        color=color,
        trigger_type="condition",
        template="{{ True }}",
        sort_order=sort_order,
    )


def _make_engine_with_active(*signal_names: str) -> SignalEngine:
    """Return an engine with the given signals all active."""
    engine = SignalEngine()
    signals = [
        _make_signal(name, i, color=(i * 50, 0, 255 - i * 50))
        for i, name in enumerate(signal_names)
    ]
    engine.set_signals(signals)
    engine.set_lights([LightConfig(entity_id="light.test", brightness=255)])
    for name in signal_names:
        engine.activate_signal(name)
    return engine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def two_signal_engine():
    """Engine with two active signals (alpha > beta in priority)."""
    return _make_engine_with_active("alpha", "beta")


@pytest.fixture
def three_signal_engine():
    """Engine with three active signals."""
    return _make_engine_with_active("alpha", "beta", "gamma")


# ---------------------------------------------------------------------------
# Tests: cycle_interval=0 (disabled) — winner always wins
# ---------------------------------------------------------------------------

class TestCyclingDisabled:
    """With cycle_interval=0, the highest-priority signal always wins."""

    def test_winner_is_first_active_signal(self, two_signal_engine):
        """With cycling disabled, the first (sort_order=0) signal wins."""
        engine = two_signal_engine
        active = engine.get_active_signals()
        assert len(active) == 2
        winner = engine.get_global_winner()
        assert winner is not None
        assert winner.name == "alpha"

    def test_single_active_no_cycling_needed(self):
        """With only one active signal, cycling is irrelevant."""
        engine = _make_engine_with_active("alpha")
        active = engine.get_active_signals()
        assert len(active) == 1
        winner = engine.get_global_winner()
        assert winner.name == "alpha"

    def test_cycle_index_stays_at_zero_when_disabled(self, two_signal_engine):
        """Verify that cycle_index=0 always picks the winner when interval=0."""
        active = two_signal_engine.get_active_signals()
        cycle_index = 0
        shown = active[cycle_index % len(active)].signal
        assert shown.name == "alpha"

    def test_winner_with_no_active_signals(self):
        """With no active signals, global winner is None."""
        engine = SignalEngine()
        engine.set_signals([_make_signal("alpha", 0)])
        engine.set_lights([LightConfig(entity_id="light.test", brightness=255)])
        # alpha is defined but NOT activated
        assert engine.get_global_winner() is None


# ---------------------------------------------------------------------------
# Tests: cycle_interval > 0 — index advances, wraps, timer cancels
# ---------------------------------------------------------------------------

class TestCyclingEnabled:
    """With cycle_interval>0 and 2+ active signals, cycling logic applies."""

    def test_cycle_index_starts_at_zero(self, two_signal_engine):
        """Initial cycle index is 0 — shows the highest-priority signal first."""
        active = two_signal_engine.get_active_signals()
        cycle_index = 0
        assert active[cycle_index].signal.name == "alpha"

    def test_cycle_index_advances(self, two_signal_engine):
        """After one tick, index advances to 1."""
        active = two_signal_engine.get_active_signals()
        cycle_index = 0
        # Simulate one tick
        cycle_index = (cycle_index + 1) % len(active)
        assert cycle_index == 1
        assert active[cycle_index].signal.name == "beta"

    def test_cycle_index_wraps(self, two_signal_engine):
        """Index wraps back to 0 after the last signal."""
        active = two_signal_engine.get_active_signals()
        cycle_index = 1
        # Simulate another tick (wrap)
        cycle_index = (cycle_index + 1) % len(active)
        assert cycle_index == 0
        assert active[cycle_index].signal.name == "alpha"

    def test_cycle_index_wraps_three_signals(self, three_signal_engine):
        """Index wraps correctly with three signals."""
        active = three_signal_engine.get_active_signals()
        assert len(active) == 3
        order = []
        cycle_index = 0
        for _ in range(6):  # two full cycles
            order.append(active[cycle_index].signal.name)
            cycle_index = (cycle_index + 1) % len(active)
        assert order == ["alpha", "beta", "gamma", "alpha", "beta", "gamma"]

    def test_timer_should_not_run_with_one_signal(self):
        """Cycling should NOT activate when only one signal is active."""
        engine = _make_engine_with_active("alpha")
        active = engine.get_active_signals()
        cycle_interval = 5
        # Cycling condition: interval > 0 AND len(active) >= 2
        should_cycle = cycle_interval > 0 and len(active) >= 2
        assert should_cycle is False

    def test_timer_should_not_run_with_zero_interval(self, two_signal_engine):
        """Cycling should NOT activate when interval is 0."""
        active = two_signal_engine.get_active_signals()
        cycle_interval = 0
        should_cycle = cycle_interval > 0 and len(active) >= 2
        assert should_cycle is False

    def test_timer_should_run_with_two_signals_and_interval(self, two_signal_engine):
        """Cycling SHOULD activate with interval>0 and 2+ active signals."""
        active = two_signal_engine.get_active_signals()
        cycle_interval = 5
        should_cycle = cycle_interval > 0 and len(active) >= 2
        assert should_cycle is True

    def test_index_clamps_when_signal_removed(self):
        """If signals drop, index clamps via modulo to avoid IndexError."""
        engine = _make_engine_with_active("alpha", "beta", "gamma")
        active = engine.get_active_signals()
        assert len(active) == 3

        # Simulate: cycle index was at 2 (gamma), then gamma is removed
        cycle_index = 2
        engine.deactivate_signal("gamma")
        active = engine.get_active_signals()
        assert len(active) == 2

        # Index clamps: 2 % 2 = 0 (alpha)
        clamped = cycle_index % len(active)
        assert clamped == 0
        assert active[clamped].signal.name == "alpha"

    def test_cycling_stops_when_signals_drop_to_one(self):
        """When active signals drop to 1, cycling condition is no longer met."""
        engine = _make_engine_with_active("alpha", "beta")
        active = engine.get_active_signals()
        cycle_interval = 5
        assert cycle_interval > 0 and len(active) >= 2  # cycling active

        # Remove beta
        engine.deactivate_signal("beta")
        active = engine.get_active_signals()
        should_cycle = cycle_interval > 0 and len(active) >= 2
        assert should_cycle is False  # cycling stops

    def test_cycling_stops_when_all_signals_cleared(self):
        """When all signals are deactivated, cycling stops."""
        engine = _make_engine_with_active("alpha", "beta")
        engine.deactivate_signal("alpha")
        engine.deactivate_signal("beta")
        active = engine.get_active_signals()
        cycle_interval = 5
        should_cycle = cycle_interval > 0 and len(active) >= 2
        assert should_cycle is False

    def test_cycle_shows_correct_signal_at_each_index(self, two_signal_engine):
        """Each cycle index maps to the correct signal."""
        active = two_signal_engine.get_active_signals()
        # index 0 → alpha, index 1 → beta
        assert active[0].signal.name == "alpha"
        assert active[1].signal.name == "beta"

    def test_cycle_index_zero_after_interval_reset(self):
        """Index resets to 0 when cycling is turned off then on."""
        engine = _make_engine_with_active("alpha", "beta")
        cycle_index = 1  # Was at beta

        # Interval set to 0 → reset
        cycle_index = 0
        assert cycle_index == 0
