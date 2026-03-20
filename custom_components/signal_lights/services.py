"""Service handlers for Signal Lights."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .coordinator import SignalLightsCoordinator

_LOGGER = logging.getLogger(__name__)

TRIGGER_SIGNAL_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
    }
)

DISMISS_SIGNAL_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
    }
)

REFRESH_SCHEMA = vol.Schema({})


def _get_coordinator(hass: HomeAssistant) -> SignalLightsCoordinator:
    """Return the active coordinator for the single entry."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        coord = getattr(entry, "runtime_data", None)
        if isinstance(coord, SignalLightsCoordinator):
            return coord
    raise RuntimeError("No active Signal Lights coordinator found")


async def async_register_services(hass: HomeAssistant) -> None:
    """Register all Signal Lights services."""

    async def handle_trigger_signal(call: ServiceCall) -> None:
        """Handle signal_lights.trigger_signal."""
        coord = _get_coordinator(hass)
        name = call.data["name"]
        result = await coord.async_trigger_signal(name)
        if not result:
            _LOGGER.warning(
                "signal_lights.trigger_signal: signal '%s' not found", name
            )

    hass.services.async_register(
        DOMAIN, "trigger_signal", handle_trigger_signal, schema=TRIGGER_SIGNAL_SCHEMA
    )

    async def handle_dismiss_signal(call: ServiceCall) -> None:
        """Handle signal_lights.dismiss_signal."""
        coord = _get_coordinator(hass)
        name = call.data["name"]
        result = await coord.async_dismiss_signal(name)
        if not result:
            _LOGGER.warning(
                "signal_lights.dismiss_signal: signal '%s' not found or not active",
                name,
            )

    hass.services.async_register(
        DOMAIN, "dismiss_signal", handle_dismiss_signal, schema=DISMISS_SIGNAL_SCHEMA
    )

    async def handle_refresh(call: ServiceCall) -> None:
        """Handle signal_lights.refresh."""
        coord = _get_coordinator(hass)
        await coord.async_refresh_signals()

    hass.services.async_register(
        DOMAIN, "refresh", handle_refresh, schema=REFRESH_SCHEMA
    )


async def async_unregister_services(hass: HomeAssistant) -> None:
    """Unregister all Signal Lights services."""
    for service in ("trigger_signal", "dismiss_signal", "refresh"):
        hass.services.async_remove(DOMAIN, service)
