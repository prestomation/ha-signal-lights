"""Signal Lights integration for Home Assistant.

A priority queue of colored light signals. Register physical HA light entities
as notification outputs. Define signals with colors, priorities, and triggers.
The engine evaluates which signal is highest priority and pushes that color
to the registered lights.

Services:
  signal_lights.trigger_signal  — Manually fire an event signal by name
  signal_lights.dismiss_signal  — Dismiss an active signal
  signal_lights.refresh         — Force re-evaluation of all signals
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import SignalLightsCoordinator
from .services import async_register_services, async_unregister_services
from .store import SignalLightsStore

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Global integration setup hook (config-flow only integration)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Signal Lights from a config entry."""
    store = SignalLightsStore(hass)
    await store.load()

    coordinator = SignalLightsCoordinator(hass, entry, store)
    await coordinator.async_setup()
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_register_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: SignalLightsCoordinator = entry.runtime_data
    await coordinator.async_shutdown()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Remove services only when the last entry is unloaded
    remaining = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.entry_id != entry.entry_id
    ]
    if not remaining:
        await async_unregister_services(hass)

    return unload_ok
