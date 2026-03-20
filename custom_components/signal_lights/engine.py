"""Signal evaluation engine — pure Python, no HA dependencies.

This module contains the core logic for evaluating which signal should be
active for each light. It's deliberately free of Home Assistant imports so
that it can be unit-tested without any HA test infrastructure.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Signal:
    """A single signal definition."""

    name: str
    priority: int  # lower = higher priority
    color: tuple[int, int, int]  # RGB
    trigger_type: str  # "event" or "condition"
    template: str  # Jinja2 template string
    duration: int = 0  # seconds, event type only
    light_filter: list[str] = field(default_factory=list)  # empty = all lights
    sort_order: int = 0  # for tie-breaking within same priority

    def applies_to_light(self, light_entity_id: str) -> bool:
        """Return True if this signal applies to the given light."""
        if not self.light_filter:
            return True
        return light_entity_id in self.light_filter


@dataclass
class LightConfig:
    """A registered light output."""

    entity_id: str
    brightness: int = 255  # 0-255


@dataclass
class ActiveSignal:
    """A signal that is currently active (condition is true or event fired)."""

    signal: Signal
    activated_at: float  # time.monotonic() timestamp
    expires_at: float | None = None  # None for condition signals

    @property
    def is_expired(self) -> bool:
        """Check if an event signal has expired."""
        if self.expires_at is None:
            return False
        return time.monotonic() >= self.expires_at


class SignalEngine:
    """Evaluates signal priorities and determines light states.

    This is the core evaluation engine. It maintains a list of active signals
    and determines what color each light should display.
    """

    def __init__(self) -> None:
        """Initialise with empty signal and light lists."""
        self._signals: list[Signal] = []
        self._lights: list[LightConfig] = []
        self._active: list[ActiveSignal] = []

    @property
    def signals(self) -> list[Signal]:
        """Return the configured signals."""
        return list(self._signals)

    @property
    def lights(self) -> list[LightConfig]:
        """Return the configured lights."""
        return list(self._lights)

    def set_signals(self, signals: list[Signal]) -> None:
        """Replace the signal configuration."""
        self._signals = list(signals)

    def set_lights(self, lights: list[LightConfig]) -> None:
        """Replace the light configuration."""
        self._lights = list(lights)

    def activate_signal(self, signal_name: str, now: float | None = None) -> bool:
        """Activate a signal by name (for event triggers or manual trigger).

        Returns True if the signal was found and activated, False otherwise.
        """
        now = now if now is not None else time.monotonic()
        signal = self._find_signal(signal_name)
        if signal is None:
            return False

        # Don't double-activate
        for active in self._active:
            if active.signal.name == signal_name and not active.is_expired:
                return True

        expires_at = None
        if signal.trigger_type == "event" and signal.duration > 0:
            expires_at = now + signal.duration

        self._active.append(ActiveSignal(
            signal=signal,
            activated_at=now,
            expires_at=expires_at,
        ))
        return True

    def deactivate_signal(self, signal_name: str) -> bool:
        """Deactivate a signal by name (for condition becoming false or dismiss).

        Returns True if the signal was found and deactivated.
        """
        before = len(self._active)
        self._active = [a for a in self._active if a.signal.name != signal_name]
        return len(self._active) < before

    def dismiss_signal(self, signal_name: str) -> bool:
        """Dismiss a signal (manual dismissal via service call)."""
        return self.deactivate_signal(signal_name)

    def cleanup_expired(self) -> list[str]:
        """Remove expired event signals. Returns names of expired signals."""
        expired = [a.signal.name for a in self._active if a.is_expired]
        self._active = [a for a in self._active if not a.is_expired]
        return expired

    def get_active_signals(self) -> list[ActiveSignal]:
        """Return currently active (non-expired) signals, sorted by priority then sort_order."""
        self.cleanup_expired()
        return sorted(
            self._active,
            key=lambda a: (a.signal.priority, a.signal.sort_order),
        )

    def get_winning_signal_for_light(self, light_entity_id: str) -> Signal | None:
        """Return the highest-priority active signal that applies to a light."""
        for active in self.get_active_signals():
            if active.signal.applies_to_light(light_entity_id):
                return active.signal
        return None

    def evaluate(self) -> dict[str, dict[str, Any] | None]:
        """Evaluate all lights and return desired states.

        Returns a dict of {light_entity_id: state_dict_or_None}.
        state_dict has keys: rgb_color (tuple), brightness (int).
        None means the light should be turned off.
        """
        result: dict[str, dict[str, Any] | None] = {}
        for light in self._lights:
            winner = self.get_winning_signal_for_light(light.entity_id)
            if winner is None:
                result[light.entity_id] = None
            else:
                result[light.entity_id] = {
                    "rgb_color": winner.color,
                    "brightness": light.brightness,
                    "signal_name": winner.name,
                }
        return result

    def get_global_winner(self) -> Signal | None:
        """Return the overall highest-priority active signal (ignoring per-light filters)."""
        active = self.get_active_signals()
        return active[0].signal if active else None

    def get_queue_depth(self) -> int:
        """Return the number of currently active signals."""
        return len(self.get_active_signals())

    def _find_signal(self, name: str) -> Signal | None:
        """Find a signal by name."""
        for signal in self._signals:
            if signal.name == name:
                return signal
        return None
