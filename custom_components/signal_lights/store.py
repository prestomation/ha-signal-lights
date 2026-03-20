"""Local JSON storage for Signal Lights.

Persists light registrations and signal definitions to HA's .storage directory.

Storage file: .storage/signal_lights
Shape:
    {
        "lights": [
            {"entity_id": "light.desk_lamp", "brightness": 255},
            ...
        ],
        "signals": [
            {
                "name": "Back door open",
                "sort_order": 0,
                "color": [255, 0, 0],
                "trigger_type": "condition",
                "trigger_mode": "entity_equals",
                "trigger_config": {"entity_id": "binary_sensor.back_door", "state": "on"},
                "template": "{{ is_state('binary_sensor.back_door', 'on') }}",
                "duration": 0,
                "light_filter": []
            },
            ...
        ]
    }
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_VERSION
from .engine import generate_template_from_trigger, validate_trigger_config

_LOGGER = logging.getLogger(__name__)


class SignalLightsStore:
    """Local JSON storage for Signal Lights configuration."""

    def __init__(self, hass: HomeAssistant, entry_id: str | None = None) -> None:
        """Initialise (does not touch disk — call load() after creation).

        entry_id: the config entry ID — used to build a per-entry storage key
        (signal_lights_{entry_id}). When None (legacy / tests), falls back to
        the plain STORAGE_KEY so existing data is preserved.
        """
        self._hass = hass
        storage_key = f"{STORAGE_KEY}_{entry_id}" if entry_id else STORAGE_KEY
        self._store: Store = Store(hass, STORAGE_VERSION, storage_key)
        self._data: dict[str, Any] = {"lights": [], "signals": []}

    def _normalize_signal(self, sig: dict, index: int) -> None:
        """Apply all default values and migrations to a signal dict in-place.

        This is the single source of truth for signal defaults/migrations.
        It is called both during load() and add_signal() to keep stored data
        consistent.
        """
        # Sort order default
        if "sort_order" not in sig:
            sig["sort_order"] = index
        # Trigger mode/config defaults
        sig.setdefault("trigger_mode", "template")
        sig.setdefault("trigger_config", {})
        sig.setdefault("template", "")
        sig.setdefault("trigger_type", "condition")
        sig.setdefault("color", [255, 255, 255])
        sig.setdefault("duration", 0)
        sig.setdefault("light_filter", [])
        # Silently drop legacy priority field
        sig.pop("priority", None)

    async def load(self) -> None:
        """Load configuration from disk."""
        raw = await self._store.async_load()
        if raw is None:
            self._data = {"lights": [], "signals": []}
            _LOGGER.debug("Signal Lights: no existing store found, starting fresh")
        else:
            self._data = raw
            _LOGGER.debug(
                "Signal Lights: loaded %d lights, %d signals",
                len(self._data.get("lights", [])),
                len(self._data.get("signals", [])),
            )
        # Ensure expected keys
        self._data.setdefault("lights", [])
        self._data.setdefault("signals", [])
        self._data.setdefault("notifications", {"enabled": False, "targets": []})

        # Normalise all signals (sets defaults, drops priority, etc.)
        for i, sig in enumerate(self._data["signals"]):
            self._normalize_signal(sig, i)

        # Validate and attempt to recover signals on load
        for sig in self._data["signals"]:
            trigger_mode = sig.get("trigger_mode", "template")
            template = sig.get("template", "")
            trigger_config = sig.get("trigger_config", {})

            # Try to regenerate template if missing for non-template modes
            if trigger_mode != "template" and not template:
                errors = validate_trigger_config(trigger_mode, trigger_config)
                if not errors:
                    try:
                        regenerated = generate_template_from_trigger(trigger_mode, trigger_config)
                        sig["template"] = regenerated
                        _LOGGER.debug(
                            "Signal Lights: regenerated template for signal '%s'", sig.get("name", "?")
                        )
                    except ValueError as err:
                        _LOGGER.warning(
                            "Signal Lights: signal '%s' has empty template and invalid trigger config — "
                            "it will not fire: %s",
                            sig.get("name", "?"), err,
                        )
                else:
                    _LOGGER.warning(
                        "Signal Lights: signal '%s' has empty template and invalid trigger config — "
                        "it will not fire: %s",
                        sig.get("name", "?"), "; ".join(errors),
                    )

    async def save(self) -> None:
        """Persist configuration to disk."""
        await self._store.async_save(self._data)

    # -----------------------------------------------------------------------
    # Lights
    # -----------------------------------------------------------------------

    def get_lights(self) -> list[dict[str, Any]]:
        """Return the list of registered lights."""
        return list(self._data["lights"])

    async def set_lights(self, lights: list[dict[str, Any]]) -> None:
        """Replace the entire lights list and persist."""
        self._data["lights"] = lights
        await self.save()

    async def add_light(self, entity_id: str, brightness: int = 255) -> None:
        """Add a light if not already registered."""
        for light in self._data["lights"]:
            if light["entity_id"] == entity_id:
                return
        self._data["lights"].append({
            "entity_id": entity_id,
            "brightness": brightness,
        })
        await self.save()

    async def remove_light(self, entity_id: str) -> bool:
        """Remove a light by entity_id. Returns True if found."""
        before = len(self._data["lights"])
        self._data["lights"] = [
            light for light in self._data["lights"] if light["entity_id"] != entity_id
        ]
        if len(self._data["lights"]) < before:
            await self.save()
            return True
        return False

    # -----------------------------------------------------------------------
    # Signals
    # -----------------------------------------------------------------------

    def get_signals(self) -> list[dict[str, Any]]:
        """Return the list of signal definitions, sorted by sort_order."""
        return sorted(self._data["signals"], key=lambda s: s.get("sort_order", 0))

    async def set_signals(self, signals: list[dict[str, Any]]) -> None:
        """Replace the entire signals list and persist."""
        self._data["signals"] = signals
        await self.save()

    async def add_signal(self, signal: dict[str, Any]) -> None:
        """Add a signal definition. Auto-assigns sort_order (appended to end)."""
        # Auto-assign sort_order — always append to end
        max_order = max(
            (s.get("sort_order", 0) for s in self._data["signals"]),
            default=-1,
        )
        signal["sort_order"] = max_order + 1
        # Apply all defaults/normalisations (also drops legacy priority)
        self._normalize_signal(signal, signal["sort_order"])
        self._data["signals"].append(signal)
        await self.save()

    async def remove_signal(self, name: str) -> bool:
        """Remove a signal by name. Returns True if found."""
        before = len(self._data["signals"])
        self._data["signals"] = [
            s for s in self._data["signals"] if s["name"] != name
        ]
        if len(self._data["signals"]) < before:
            # Re-index sort_order after removal
            self._reindex_sort_order()
            await self.save()
            return True
        return False

    async def update_signal(self, name: str, updates: dict) -> bool:
        """Find a signal by name, apply updates dict, and save. Returns True if found."""
        for sig in self._data["signals"]:
            if sig["name"] == name:
                sig.update(updates)
                await self.save()
                return True
        return False

    async def reorder_signals(self, ordered_names: list[str]) -> None:
        """Reorder signals by a list of signal names. Re-indexes sort_order."""
        name_to_signal = {s["name"]: s for s in self._data["signals"]}
        reordered = []
        for name in ordered_names:
            if name in name_to_signal:
                reordered.append(name_to_signal.pop(name))
        # Append any signals not in the ordered list (shouldn't happen, but safe)
        for sig in name_to_signal.values():
            reordered.append(sig)
        self._data["signals"] = reordered
        self._reindex_sort_order()
        await self.save()

    def _reindex_sort_order(self) -> None:
        """Re-index sort_order values sequentially."""
        for i, sig in enumerate(self._data["signals"]):
            sig["sort_order"] = i

    def get_signal_by_name(self, name: str) -> dict[str, Any] | None:
        """Find a signal by name."""
        for signal in self._data["signals"]:
            if signal["name"] == name:
                return signal
        return None

    # -----------------------------------------------------------------------
    # Notifications
    # -----------------------------------------------------------------------

    def get_notification_config(self) -> dict[str, Any]:
        """Return the notification configuration."""
        return dict(self._data.get("notifications", {"enabled": False, "targets": []}))

    async def set_notification_config(
        self, enabled: bool, targets: list[str]
    ) -> None:
        """Update notification configuration and persist."""
        self._data["notifications"] = {"enabled": enabled, "targets": targets}
        await self.save()
