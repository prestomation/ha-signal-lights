"""Diagnostics support for Signal Lights."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_loaded_integration

from .const import DOMAIN
from .coordinator import SignalLightsCoordinator

_LOGGER = logging.getLogger(__name__)

TO_REDACT: set[str] = set()


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for the Signal Lights config entry."""
    coordinator: SignalLightsCoordinator = entry.runtime_data
    store = coordinator.store

    # Integration version, read from the loaded integration (no file I/O)
    version = async_get_loaded_integration(hass, DOMAIN).version
    integration_version = str(version) if version is not None else "unknown"

    # Engine state
    active_signals = coordinator.engine.get_active_signals()

    return {
        "config_entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "integration_version": integration_version,
        "lights": store.get_lights(),
        "signals": store.get_signals(),
        "active_signals": [a.signal.name for a in active_signals],
        "queue_depth": len(active_signals),
    }
