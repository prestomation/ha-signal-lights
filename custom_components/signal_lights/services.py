"""Service handlers for Signal Lights."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .coordinator import SignalLightsCoordinator
from .engine import generate_template_from_trigger

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

ADD_LIGHT_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Optional("brightness", default=255): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=255)
        ),
    }
)

REMOVE_LIGHT_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
    }
)

ADD_SIGNAL_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Optional("priority", default=0): vol.Coerce(int),
        vol.Required("color"): vol.All(
            [vol.Coerce(int)], vol.Length(min=3, max=3)
        ),
        vol.Required("trigger_type"): vol.In(["event", "condition"]),
        vol.Optional("trigger_mode", default="template"): vol.In(
            ["entity_equals", "entity_on", "numeric_threshold", "template"]
        ),
        vol.Optional("trigger_config", default={}): dict,
        vol.Optional("template", default=""): cv.string,
        vol.Optional("duration", default=0): vol.Coerce(int),
        vol.Optional("light_filter", default=[]): [cv.entity_id],
    }
)

REMOVE_SIGNAL_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
    }
)

REORDER_SIGNALS_SCHEMA = vol.Schema(
    {
        vol.Required("order"): [cv.string],
    }
)

CONFIGURE_NOTIFICATIONS_SCHEMA = vol.Schema(
    {
        vol.Required("enabled"): cv.boolean,
        vol.Optional("targets", default=[]): [cv.string],
    }
)


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

    # -----------------------------------------------------------------------
    # Configuration management services
    # -----------------------------------------------------------------------

    async def handle_add_light(call: ServiceCall) -> None:
        """Handle signal_lights.add_light."""
        coord = _get_coordinator(hass)
        entity_id = call.data["entity_id"]
        brightness = call.data.get("brightness", 255)
        await coord.store.add_light(entity_id, brightness)
        await coord.async_reload_config()
        _LOGGER.info("Signal Lights: added light %s (brightness %d)", entity_id, brightness)

    hass.services.async_register(
        DOMAIN, "add_light", handle_add_light, schema=ADD_LIGHT_SCHEMA
    )

    async def handle_remove_light(call: ServiceCall) -> None:
        """Handle signal_lights.remove_light."""
        coord = _get_coordinator(hass)
        entity_id = call.data["entity_id"]
        removed = await coord.store.remove_light(entity_id)
        if removed:
            await coord.async_reload_config()
            _LOGGER.info("Signal Lights: removed light %s", entity_id)
        else:
            _LOGGER.warning("Signal Lights: light %s not found", entity_id)

    hass.services.async_register(
        DOMAIN, "remove_light", handle_remove_light, schema=REMOVE_LIGHT_SCHEMA
    )

    async def handle_add_signal(call: ServiceCall) -> None:
        """Handle signal_lights.add_signal."""
        coord = _get_coordinator(hass)
        trigger_mode = call.data.get("trigger_mode", "template")
        trigger_config = call.data.get("trigger_config", {})
        template = call.data.get("template", "")

        # Generate template from trigger mode if not raw template
        if trigger_mode != "template" and not template:
            template = generate_template_from_trigger(trigger_mode, trigger_config)

        signal_def = {
            "name": call.data["name"],
            "color": list(call.data["color"]),
            "trigger_type": call.data["trigger_type"],
            "trigger_mode": trigger_mode,
            "trigger_config": trigger_config,
            "template": template,
            "duration": call.data.get("duration", 0),
            "light_filter": call.data.get("light_filter", []),
        }
        await coord.store.add_signal(signal_def)
        await coord.async_reload_config()
        _LOGGER.info("Signal Lights: added signal '%s'", signal_def["name"])

    hass.services.async_register(
        DOMAIN, "add_signal", handle_add_signal, schema=ADD_SIGNAL_SCHEMA
    )

    async def handle_remove_signal(call: ServiceCall) -> None:
        """Handle signal_lights.remove_signal."""
        coord = _get_coordinator(hass)
        name = call.data["name"]
        removed = await coord.store.remove_signal(name)
        if removed:
            await coord.async_reload_config()
            _LOGGER.info("Signal Lights: removed signal '%s'", name)
        else:
            _LOGGER.warning("Signal Lights: signal '%s' not found", name)

    hass.services.async_register(
        DOMAIN, "remove_signal", handle_remove_signal, schema=REMOVE_SIGNAL_SCHEMA
    )

    async def handle_reorder_signals(call: ServiceCall) -> None:
        """Handle signal_lights.reorder_signals."""
        coord = _get_coordinator(hass)
        ordered_names = call.data["order"]
        await coord.store.reorder_signals(ordered_names)
        await coord.async_reload_config()
        _LOGGER.info("Signal Lights: reordered signals: %s", ordered_names)

    hass.services.async_register(
        DOMAIN, "reorder_signals", handle_reorder_signals, schema=REORDER_SIGNALS_SCHEMA
    )

    async def handle_configure_notifications(call: ServiceCall) -> None:
        """Handle signal_lights.configure_notifications."""
        coord = _get_coordinator(hass)
        enabled = call.data["enabled"]
        targets = call.data.get("targets", [])
        await coord.store.set_notification_config(enabled, targets)
        await coord.async_reload_config()
        _LOGGER.info(
            "Signal Lights: notifications %s, targets: %s",
            "enabled" if enabled else "disabled",
            targets,
        )

    hass.services.async_register(
        DOMAIN,
        "configure_notifications",
        handle_configure_notifications,
        schema=CONFIGURE_NOTIFICATIONS_SCHEMA,
    )


async def async_unregister_services(hass: HomeAssistant) -> None:
    """Unregister all Signal Lights services."""
    for service in (
        "trigger_signal", "dismiss_signal", "refresh",
        "add_light", "remove_light", "add_signal", "remove_signal",
        "reorder_signals", "configure_notifications",
    ):
        hass.services.async_remove(DOMAIN, service)
