"""Signal Lights integration for Home Assistant.

A priority queue of colored light signals. Register physical HA light entities
as notification outputs. Define signals with colors, priorities, and triggers.
The engine evaluates which signal is highest priority and pushes that color
to the registered lights.

Services:
  signal_lights.trigger_signal         — Manually fire an event signal by name
  signal_lights.dismiss_signal         — Dismiss an active signal
  signal_lights.refresh                — Force re-evaluation of all signals
  signal_lights.add_light              — Register a light entity
  signal_lights.remove_light           — Unregister a light entity
  signal_lights.add_signal             — Add a signal definition
  signal_lights.remove_signal          — Remove a signal definition
  signal_lights.reorder_signals        — Reorder signals by name list
  signal_lights.configure_notifications — Configure notification settings
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, PLATFORMS, URL_BASE, CARD_VERSION

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
from .coordinator import SignalLightsCoordinator
from .services import async_register_services, async_unregister_services
from .store import SignalLightsStore

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Frontend registration helpers
# ---------------------------------------------------------------------------


class SignalLightsCardRegistration:
    """Handles registering the Signal Lights card as a Lovelace resource."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    @property
    def _resource_mode(self) -> str:
        """Return the Lovelace resource mode."""
        lovelace = self.hass.data.get("lovelace")
        if lovelace is None:
            return "yaml"
        if hasattr(lovelace, "resource_mode"):
            return lovelace.resource_mode
        if hasattr(lovelace, "mode"):
            return lovelace.mode
        return "yaml"

    @property
    def _resources(self):
        lovelace = self.hass.data.get("lovelace")
        if lovelace is None:
            return None
        if hasattr(lovelace, "resources"):
            return lovelace.resources
        return None

    async def async_register(self) -> None:
        """Register static path and add to Lovelace resources."""
        await self._register_static_path()
        if self._resource_mode == "storage":
            await self._ensure_resources_loaded()
            await self._register_lovelace_resource()

    async def _register_static_path(self) -> None:
        frontend_dir = Path(__file__).parent / "frontend"
        try:
            await self.hass.http.async_register_static_paths(
                [StaticPathConfig(URL_BASE, str(frontend_dir), False)]
            )
            _LOGGER.debug("Registered static path %s -> %s", URL_BASE, frontend_dir)
        except RuntimeError:
            _LOGGER.debug("Static path %s already registered", URL_BASE)

    async def _ensure_resources_loaded(self) -> None:
        resources = self._resources
        if resources and not resources.loaded:
            await resources.async_load()

    async def _register_lovelace_resource(self) -> None:
        resources = self._resources
        if resources is None:
            return
        card_url = f"{URL_BASE}/signal-lights-card.js?v={CARD_VERSION}"
        existing = [r for r in resources.async_items() if URL_BASE in r.get("url", "")]
        if not existing:
            await resources.async_create_item({"res_type": "module", "url": card_url})
            _LOGGER.info("Auto-registered Signal Lights card resource: %s", card_url)
        else:
            for r in existing:
                if r.get("url") != card_url:
                    try:
                        await resources.async_update_item(
                            r["id"], {"res_type": "module", "url": card_url}
                        )
                        _LOGGER.info("Updated Signal Lights card resource to %s", card_url)
                    except Exception as err:  # noqa: BLE001
                        _LOGGER.warning(
                            "Signal Lights: failed to update Lovelace resource: %s", err
                        )

    async def async_unregister(self) -> None:
        """Remove the card from Lovelace resources on unload."""
        if self._resource_mode != "storage":
            return
        resources = self._resources
        if resources is None:
            return
        to_remove = [r for r in resources.async_items() if URL_BASE in r.get("url", "")]
        for r in to_remove:
            try:
                await resources.async_delete_item(r["id"])
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning(
                    "Signal Lights: failed to remove Lovelace resource: %s", err
                )


async def _ensure_frontend_registered(hass: HomeAssistant) -> None:
    """Register frontend resources."""
    reg = SignalLightsCardRegistration(hass)
    await reg.async_register()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Signal Lights from a config entry."""
    # Register frontend resources
    await _ensure_frontend_registered(hass)

    store = SignalLightsStore(hass, entry.entry_id)
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
