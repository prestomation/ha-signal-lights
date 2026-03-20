"""Signal evaluation engine — pure Python, no HA dependencies.

This module contains the core logic for evaluating which signal should be
active for each light. It's deliberately free of Home Assistant imports so
that it can be unit-tested without any HA test infrastructure.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Input validation patterns (prevent template injection)
# ---------------------------------------------------------------------------

_ENTITY_ID_RE = re.compile(r'^[a-z0-9_]+\.[a-z0-9_]+$')

# Characters that could escape Jinja2 string literals or inject arbitrary templates
_STATE_FORBIDDEN_CHARS = frozenset("'\"{}\\/")


def _validate_entity_id(entity_id: str) -> str | None:
    """Return error string if entity_id is invalid, else None."""
    if not _ENTITY_ID_RE.match(entity_id):
        return (
            f"entity_id '{entity_id}' is invalid "
            "(must match domain.object_id with lowercase alphanumeric/underscore only)"
        )
    return None


def _validate_state_value(state: str) -> str | None:
    """Return error string if state value contains forbidden chars, else None."""
    bad = [c for c in state if c in _STATE_FORBIDDEN_CHARS]
    if bad:
        return f"state value contains forbidden characters: {bad!r}"
    return None


# ---------------------------------------------------------------------------
# Trigger mode helpers
# ---------------------------------------------------------------------------

TRIGGER_MODES = ("entity_equals", "entity_on", "numeric_threshold", "template")


def validate_trigger_config(trigger_mode: str, trigger_config: dict[str, Any]) -> list[str]:
    """Validate trigger_config for the given trigger_mode.

    Returns a list of error strings. An empty list means the config is valid.
    """
    errors: list[str] = []

    if trigger_mode == "entity_equals":
        entity_id = str(trigger_config.get("entity_id", "")).strip()
        if not entity_id:
            errors.append("entity_id is required for entity_equals mode")
        else:
            err = _validate_entity_id(entity_id)
            if err:
                errors.append(err)
        state = str(trigger_config.get("state", "")).strip()
        if not state:
            errors.append("state is required for entity_equals mode")
        else:
            err = _validate_state_value(state)
            if err:
                errors.append(err)

    elif trigger_mode == "entity_on":
        entity_id = str(trigger_config.get("entity_id", "")).strip()
        if not entity_id:
            errors.append("entity_id is required for entity_on mode")
        else:
            err = _validate_entity_id(entity_id)
            if err:
                errors.append(err)

    elif trigger_mode == "numeric_threshold":
        entity_id = str(trigger_config.get("entity_id", "")).strip()
        if not entity_id:
            errors.append("entity_id is required for numeric_threshold mode")
        else:
            err = _validate_entity_id(entity_id)
            if err:
                errors.append(err)
        threshold = trigger_config.get("threshold")
        if threshold is None:
            errors.append("threshold is required for numeric_threshold mode")
        else:
            try:
                float(threshold)
            except (TypeError, ValueError):
                errors.append(f"threshold must be numeric, got: {threshold!r}")
        direction = trigger_config.get("direction")
        if direction not in ("above", "below"):
            errors.append(
                f"direction must be 'above' or 'below', got: {direction!r}"
            )

    elif trigger_mode == "template":
        if not str(trigger_config.get("template", "")).strip():
            errors.append("template is required for template mode")

    return errors


def generate_template_from_trigger(trigger_mode: str, trigger_config: dict[str, Any]) -> str:
    """Generate a Jinja2 template string from a trigger mode and config.

    Returns the template string, or empty string if mode is unrecognised.
    Raises ValueError if trigger_config is invalid for the given mode.

    The entity_id and state values are validated before interpolation to
    prevent Jinja2 template injection attacks.
    """
    errors = validate_trigger_config(trigger_mode, trigger_config)
    if errors:
        raise ValueError(
            f"Invalid trigger config for mode '{trigger_mode}': {'; '.join(errors)}"
        )

    if trigger_mode == "entity_equals":
        entity_id = trigger_config.get("entity_id", "")
        state = trigger_config.get("state", "")
        # Both validated above — safe to interpolate
        return f"{{{{ is_state('{entity_id}', '{state}') }}}}"

    if trigger_mode == "entity_on":
        entity_id = trigger_config.get("entity_id", "")
        return f"{{{{ is_state('{entity_id}', 'on') }}}}"

    if trigger_mode == "numeric_threshold":
        entity_id = trigger_config.get("entity_id", "")
        threshold = trigger_config.get("threshold", 0)
        direction = trigger_config.get("direction", "above")
        op = ">" if direction == "above" else "<"
        return f"{{{{ states('{entity_id}') | float(0) {op} {threshold} }}}}"

    if trigger_mode == "template":
        return trigger_config.get("template", "")

    return ""


@dataclass
class Signal:
    """A single signal definition."""

    name: str
    color: tuple[int, int, int]  # RGB
    trigger_type: str  # "event" or "condition"
    template: str  # Jinja2 template string
    duration: int = 0  # seconds, event type only
    light_filter: list[str] = field(default_factory=list)  # empty = all lights
    sort_order: int = 0  # position in priority list (lower = higher priority)
    trigger_mode: str = "template"  # entity_equals, entity_on, numeric_threshold, template
    trigger_config: dict[str, Any] = field(default_factory=dict)

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

    Priority is determined by sort_order (lower = higher priority).
    """

    def __init__(self) -> None:
        """Initialise with empty signal and light lists."""
        self._signals: list[Signal] = []
        self._lights: list[LightConfig] = []
        self._active: list[ActiveSignal] = []
        self._sorted_cache: list[ActiveSignal] | None = None
        self._signal_index: dict[str, Signal] = {}

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
        self._signal_index = {s.name: s for s in self._signals}
        self._invalidate_cache()

    def set_lights(self, lights: list[LightConfig]) -> None:
        """Replace the light configuration."""
        self._lights = list(lights)

    def _invalidate_cache(self) -> None:
        """Invalidate the sorted active signals cache."""
        self._sorted_cache = None

    def _get_sorted_active(self) -> list[ActiveSignal]:
        """Return sorted active signals, rebuilding cache if dirty."""
        if self._sorted_cache is None:
            self._sorted_cache = sorted(
                self._active, key=lambda a: a.signal.sort_order
            )
        return self._sorted_cache

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
        self._invalidate_cache()
        return True

    def deactivate_signal(self, signal_name: str) -> bool:
        """Deactivate a signal by name (for condition becoming false or dismiss).

        Returns True if the signal was found and deactivated.
        """
        before = len(self._active)
        self._active = [a for a in self._active if a.signal.name != signal_name]
        if len(self._active) < before:
            self._invalidate_cache()
            return True
        return False

    def dismiss_signal(self, signal_name: str) -> bool:
        """Dismiss a signal (manual dismissal via service call)."""
        return self.deactivate_signal(signal_name)

    def cleanup_expired(self) -> list[str]:
        """Remove expired event signals. Returns names of expired signals."""
        expired = [a.signal.name for a in self._active if a.is_expired]
        if expired:
            self._active = [a for a in self._active if not a.is_expired]
            self._invalidate_cache()
        return expired

    def get_active_signals(self) -> list[ActiveSignal]:
        """Return currently active (non-expired) signals, sorted by sort_order."""
        self.cleanup_expired()
        return list(self._get_sorted_active())

    def get_winning_signal_for_light(self, light_entity_id: str) -> Signal | None:
        """Return the highest-priority active signal that applies to a light."""
        self.cleanup_expired()
        for active in self._get_sorted_active():
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
        self.cleanup_expired()
        active = self._get_sorted_active()
        return active[0].signal if active else None

    def get_queue_depth(self) -> int:
        """Return the number of currently active signals."""
        return len(self.get_active_signals())

    def _find_signal(self, name: str) -> Signal | None:
        """Find a signal by name using the index for O(1) lookup."""
        return self._signal_index.get(name)
