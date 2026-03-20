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
                "name": "Tess arrives home",
                "priority": 1,
                "color": [255, 0, 255],
                "trigger_type": "event",
                "template": "{{ is_state('person.tess', 'home') }}",
                "duration": 60,
                "light_filter": [],
                "sort_order": 0
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

_LOGGER = logging.getLogger(__name__)


class SignalLightsStore:
    """Local JSON storage for Signal Lights configuration."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialise (does not touch disk — call load() after creation)."""
        self._hass = hass
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data: dict[str, Any] = {"lights": [], "signals": []}

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
            l for l in self._data["lights"] if l["entity_id"] != entity_id
        ]
        if len(self._data["lights"]) < before:
            await self.save()
            return True
        return False

    # -----------------------------------------------------------------------
    # Signals
    # -----------------------------------------------------------------------

    def get_signals(self) -> list[dict[str, Any]]:
        """Return the list of signal definitions."""
        return list(self._data["signals"])

    async def set_signals(self, signals: list[dict[str, Any]]) -> None:
        """Replace the entire signals list and persist."""
        self._data["signals"] = signals
        await self.save()

    async def add_signal(self, signal: dict[str, Any]) -> None:
        """Add a signal definition."""
        # Auto-assign sort_order if not set
        if "sort_order" not in signal:
            max_order = max(
                (s.get("sort_order", 0) for s in self._data["signals"]),
                default=-1,
            )
            signal["sort_order"] = max_order + 1
        self._data["signals"].append(signal)
        await self.save()

    async def remove_signal(self, name: str) -> bool:
        """Remove a signal by name. Returns True if found."""
        before = len(self._data["signals"])
        self._data["signals"] = [
            s for s in self._data["signals"] if s["name"] != name
        ]
        if len(self._data["signals"]) < before:
            await self.save()
            return True
        return False

    def get_signal_by_name(self, name: str) -> dict[str, Any] | None:
        """Find a signal by name."""
        for signal in self._data["signals"]:
            if signal["name"] == name:
                return signal
        return None
