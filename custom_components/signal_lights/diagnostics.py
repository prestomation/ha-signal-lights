"""Diagnostics support for Signal Lights."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

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

    # Integration version
    integration_version = "unknown"
    manifest_path = Path(__file__).parent / "manifest.json"
    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        integration_version = manifest_data.get("version", "unknown")
    except (OSError, json.JSONDecodeError):
        pass

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
