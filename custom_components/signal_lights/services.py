"""Service handlers for Signal Lights."""

from __future__ import annotations

import logging
import re

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .coordinator import SignalLightsCoordinator
from .engine import generate_template_from_trigger, validate_trigger_config

_LOGGER = logging.getLogger(__name__)

# Count limits
MAX_SIGNALS = 50
MAX_LIGHTS = 20
MAX_TARGETS = 10

# Restrict notification targets to the notify.* domain
_NOTIFY_TARGET_RE = re.compile(r'^notify\.[a-z0-9_]+$')


def _validate_notify_target(value: str) -> str:
    """Voluptuous validator: ensure a notify target matches notify.* domain."""
    if not _NOTIFY_TARGET_RE.match(value):
        raise vol.Invalid(
            f"Notify target '{value}' is invalid — must match notify.<service_name> "
            "(lowercase alphanumeric/underscore only)"
        )
    return value


TRIGGER_SIGNAL_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Optional("config_entry_id"): cv.string,
    }
)

DISMISS_SIGNAL_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Optional("config_entry_id"): cv.string,
    }
)

REFRESH_SCHEMA = vol.Schema(
    {
        vol.Optional("config_entry_id"): cv.string,
    }
)

ADD_LIGHT_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Optional("brightness", default=255): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=255)
        ),
        vol.Optional("config_entry_id"): cv.string,
    }
)

REMOVE_LIGHT_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Optional("config_entry_id"): cv.string,
    }
)

# Structured sub-schema for trigger_config — validates entity_id when present
_TRIGGER_CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional("entity_id"): cv.entity_id,
        vol.Optional("state"): cv.string,
        vol.Optional("threshold"): vol.Coerce(float),
        vol.Optional("direction"): vol.In(["above", "below"]),
        vol.Optional("template"): cv.string,
    },
    extra=vol.ALLOW_EXTRA,
)

ADD_SIGNAL_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Required("color"): vol.All(
            [vol.Coerce(int)], vol.Length(min=3, max=3)
        ),
        vol.Required("trigger_type"): vol.In(["event", "condition"]),
        vol.Optional("trigger_mode", default="template"): vol.In(
            ["entity_equals", "entity_on", "numeric_threshold", "template"]
        ),
        vol.Optional("trigger_config", default={}): _TRIGGER_CONFIG_SCHEMA,
        vol.Optional("template", default=""): cv.string,
        vol.Optional("duration", default=0): vol.Coerce(int),
        vol.Optional("light_filter", default=[]): [cv.entity_id],
        vol.Optional("config_entry_id"): cv.string,
    }
)

REMOVE_SIGNAL_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Optional("config_entry_id"): cv.string,
    }
)

REORDER_SIGNALS_SCHEMA = vol.Schema(
    {
        vol.Required("order"): [cv.string],
        vol.Optional("config_entry_id"): cv.string,
    }
)

CONFIGURE_NOTIFICATIONS_SCHEMA = vol.Schema(
    {
        vol.Required("enabled"): cv.boolean,
        vol.Optional("targets", default=[]): [_validate_notify_target],
        vol.Optional("config_entry_id"): cv.string,
    }
)


def _get_coordinator(
    hass: HomeAssistant, entry_id: str | None = None
) -> SignalLightsCoordinator | None:
    """Return the active coordinator for the requested entry.

    - If entry_id is given, look up that specific entry.
    - If entry_id is None and exactly one entry exists, return it (backward compat).
    - If entry_id is None and multiple entries exist, log an error with the available
      entry IDs and return None.
    """
    entries = hass.config_entries.async_entries(DOMAIN)
    coords = []
    for entry in entries:
        coord = getattr(entry, "runtime_data", None)
        if isinstance(coord, SignalLightsCoordinator):
            coords.append((entry.entry_id, entry.title, coord))

    if entry_id is not None:
        for eid, _title, coord in coords:
            if eid == entry_id:
                return coord
        _LOGGER.error(
            "Signal Lights: config_entry_id '%s' not found. Available: %s",
            entry_id,
            [f"{eid} ({title})" for eid, title, _ in coords],
        )
        return None

    if len(coords) == 1:
        return coords[0][2]

    if len(coords) == 0:
        return None

    # Multiple entries and no entry_id specified
    _LOGGER.error(
        "Signal Lights: multiple setups exist — specify config_entry_id. Available: %s",
        [f"{eid} ({title})" for eid, title, _ in coords],
    )
    return None


async def async_register_services(hass: HomeAssistant) -> None:
    """Register all Signal Lights services."""

    async def handle_trigger_signal(call: ServiceCall) -> None:
        """Handle signal_lights.trigger_signal."""
        entry_id = call.data.get("config_entry_id")
        coord = _get_coordinator(hass, entry_id)
        if coord is None:
            _LOGGER.warning("Signal Lights: no active coordinator — ignoring service call")
            return
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
        entry_id = call.data.get("config_entry_id")
        coord = _get_coordinator(hass, entry_id)
        if coord is None:
            _LOGGER.warning("Signal Lights: no active coordinator — ignoring service call")
            return
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
        entry_id = call.data.get("config_entry_id")
        coord = _get_coordinator(hass, entry_id)
        if coord is None:
            _LOGGER.warning("Signal Lights: no active coordinator — ignoring service call")
            return
        await coord.async_refresh_signals()

    hass.services.async_register(
        DOMAIN, "refresh", handle_refresh, schema=REFRESH_SCHEMA
    )

    # -----------------------------------------------------------------------
    # Configuration management services
    # -----------------------------------------------------------------------

    async def handle_add_light(call: ServiceCall) -> None:
        """Handle signal_lights.add_light."""
        entry_id = call.data.get("config_entry_id")
        coord = _get_coordinator(hass, entry_id)
        if coord is None:
            _LOGGER.warning("Signal Lights: no active coordinator — ignoring service call")
            return

        # Enforce count limit
        current_lights = coord.store.get_lights()
        if len(current_lights) >= MAX_LIGHTS:
            _LOGGER.error(
                "Signal Lights: cannot add light — limit of %d lights reached", MAX_LIGHTS
            )
            return

        entity_id = call.data["entity_id"]
        brightness = call.data.get("brightness", 255)

        # Check uniqueness across ALL entries — a light can only belong to one setup
        all_entries = hass.config_entries.async_entries(DOMAIN)
        for other_entry in all_entries:
            other_coord = getattr(other_entry, "runtime_data", None)
            if not isinstance(other_coord, SignalLightsCoordinator):
                continue
            if other_coord is coord:
                continue
            for registered_light in other_coord.store.get_lights():
                if registered_light["entity_id"] == entity_id:
                    _LOGGER.error(
                        "Signal Lights: light '%s' is already registered in setup '%s' (%s) — "
                        "remove it there first before adding to '%s'",
                        entity_id,
                        other_entry.title,
                        other_entry.entry_id,
                        coord._entry.title,
                    )
                    return

        await coord.store.add_light(entity_id, brightness)
        await coord.async_reload_config()
        _LOGGER.info("Signal Lights: added light %s (brightness %d)", entity_id, brightness)

    hass.services.async_register(
        DOMAIN, "add_light", handle_add_light, schema=ADD_LIGHT_SCHEMA
    )

    async def handle_remove_light(call: ServiceCall) -> None:
        """Handle signal_lights.remove_light."""
        entry_id = call.data.get("config_entry_id")
        coord = _get_coordinator(hass, entry_id)
        if coord is None:
            _LOGGER.warning("Signal Lights: no active coordinator — ignoring service call")
            return
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
        entry_id = call.data.get("config_entry_id")
        coord = _get_coordinator(hass, entry_id)
        if coord is None:
            _LOGGER.warning("Signal Lights: no active coordinator — ignoring service call")
            return
        trigger_mode = call.data.get("trigger_mode", "template")
        trigger_config = call.data.get("trigger_config", {})
        template = call.data.get("template", "")
        name = call.data["name"]

        # Enforce count limit
        current_signals = coord.store.get_signals()
        if len(current_signals) >= MAX_SIGNALS:
            _LOGGER.error(
                "Signal Lights: cannot add signal '%s' — limit of %d signals reached",
                name, MAX_SIGNALS,
            )
            return

        # Restrict template mode to admin users
        if trigger_mode == "template":
            # user_id is None for system/automation calls — these are trusted
            # (only admins can create automations in HA)
            if call.context.user_id:
                user = await hass.auth.async_get_user(call.context.user_id)
                if not user or not user.is_admin:
                    _LOGGER.error(
                        "Signal Lights: template trigger mode requires admin privileges"
                    )
                    return

        # Check for duplicate signal names
        if coord.store.get_signal_by_name(name) is not None:
            _LOGGER.error(
                "Signal Lights: signal named '%s' already exists, cannot add duplicate",
                name,
            )
            return

        # Validate trigger config: for template mode check the template string;
        # for other modes validate the trigger_config dict.
        if trigger_mode == "template":
            if not template:
                _LOGGER.error(
                    "Signal Lights: signal '%s' uses template mode but no template was provided",
                    name,
                )
                return
        else:
            errors = validate_trigger_config(trigger_mode, trigger_config)
            if errors:
                _LOGGER.error(
                    "Signal Lights: invalid trigger config for signal '%s': %s",
                    name,
                    "; ".join(errors),
                )
                return

        # Generate template from trigger mode if not raw template
        if trigger_mode != "template" and not template:
            try:
                template = generate_template_from_trigger(trigger_mode, trigger_config)
            except ValueError as err:
                _LOGGER.error(
                    "Signal Lights: failed to generate template for signal '%s': %s",
                    name, err,
                )
                return

        # Validate Jinja2 syntax
        if template:
            try:
                from homeassistant.helpers.template import Template as HaTemplate
                HaTemplate(template)
            except Exception as err:  # noqa: BLE001
                _LOGGER.error(
                    "Signal Lights: template for signal '%s' has invalid Jinja2 syntax: %s",
                    name, err,
                )
                return

        # Warn about non-existent entities (not an error — entity might appear later)
        entity_id = trigger_config.get("entity_id", "")
        if entity_id and trigger_mode in ("entity_equals", "entity_on", "numeric_threshold"):
            if hass.states.get(entity_id) is None:
                _LOGGER.warning(
                    "Signal Lights: entity '%s' used in signal '%s' does not currently exist "
                    "(it may appear later)",
                    entity_id, name,
                )

        signal_def = {
            "name": name,
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
        _LOGGER.info("Signal Lights: added signal '%s'", name)

    hass.services.async_register(
        DOMAIN, "add_signal", handle_add_signal, schema=ADD_SIGNAL_SCHEMA
    )

    async def handle_remove_signal(call: ServiceCall) -> None:
        """Handle signal_lights.remove_signal."""
        entry_id = call.data.get("config_entry_id")
        coord = _get_coordinator(hass, entry_id)
        if coord is None:
            _LOGGER.warning("Signal Lights: no active coordinator — ignoring service call")
            return
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
        entry_id = call.data.get("config_entry_id")
        coord = _get_coordinator(hass, entry_id)
        if coord is None:
            _LOGGER.warning("Signal Lights: no active coordinator — ignoring service call")
            return
        ordered_names = call.data["order"]

        # Validate that all provided names exist
        current_signals = coord.store.get_signals()
        known_names = {s["name"] for s in current_signals}
        unknown = [n for n in ordered_names if n not in known_names]
        if unknown:
            _LOGGER.error(
                "Signal Lights: reorder_signals — unknown signal name(s): %s",
                unknown,
            )
            return

        await coord.store.reorder_signals(ordered_names)
        await coord.async_reload_config()
        _LOGGER.info("Signal Lights: reordered signals: %s", ordered_names)

    hass.services.async_register(
        DOMAIN, "reorder_signals", handle_reorder_signals, schema=REORDER_SIGNALS_SCHEMA
    )

    async def handle_configure_notifications(call: ServiceCall) -> None:
        """Handle signal_lights.configure_notifications."""
        entry_id = call.data.get("config_entry_id")
        coord = _get_coordinator(hass, entry_id)
        if coord is None:
            _LOGGER.warning("Signal Lights: no active coordinator — ignoring service call")
            return
        enabled = call.data["enabled"]
        targets = call.data.get("targets", [])

        # Enforce count limit
        if len(targets) > MAX_TARGETS:
            _LOGGER.error(
                "Signal Lights: cannot configure notifications — limit of %d targets reached "
                "(%d provided)",
                MAX_TARGETS, len(targets),
            )
            return

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
