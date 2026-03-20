"""Service handlers for Signal Lights."""

from __future__ import annotations

import asyncio
import logging
import re

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, NOTIFY_TARGET_RE
from .coordinator import SignalLightsCoordinator
from .engine import generate_template_from_trigger, validate_trigger_config

_LOGGER = logging.getLogger(__name__)

# Count limits
MAX_SIGNALS = 50
MAX_LIGHTS = 20
MAX_TARGETS = 10

# Validate config_entry_id format (HA uses ULID: 26 uppercase alphanumeric chars)
_ENTRY_ID_RE = re.compile(r'^[0-9A-Z]{26}$')


def _validate_entry_id(value: str) -> str:
    """Voluptuous validator: ensure config_entry_id is a valid HA ULID."""
    if not _ENTRY_ID_RE.match(value):
        raise vol.Invalid("config_entry_id must be a valid HA config entry ID (26-char ULID)")
    return value


def _validate_notify_target(value: str) -> str:
    """Voluptuous validator: ensure a notify target matches notify.* domain."""
    if not NOTIFY_TARGET_RE.match(value):
        raise vol.Invalid(
            f"Notify target '{value}' is invalid — must match notify.<service_name> "
            "(lowercase alphanumeric/underscore only)"
        )
    return value


# Shared optional config_entry_id field used in all service schemas
_ENTRY_ID_FIELD = {vol.Optional("config_entry_id"): _validate_entry_id}

TRIGGER_SIGNAL_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        **_ENTRY_ID_FIELD,
    }
)

DISMISS_SIGNAL_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        **_ENTRY_ID_FIELD,
    }
)

REFRESH_SCHEMA = vol.Schema(
    {
        **_ENTRY_ID_FIELD,
    }
)

ADD_LIGHT_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Optional("brightness", default=255): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=255)
        ),
        **_ENTRY_ID_FIELD,
    }
)

REMOVE_LIGHT_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        **_ENTRY_ID_FIELD,
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
        **_ENTRY_ID_FIELD,
    }
)

REMOVE_SIGNAL_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        **_ENTRY_ID_FIELD,
    }
)

UPDATE_SIGNAL_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Optional("new_name"): cv.string,
        vol.Optional("color"): vol.All(
            [vol.Coerce(int)], vol.Length(min=3, max=3)
        ),
        vol.Optional("trigger_type"): vol.In(["event", "condition"]),
        vol.Optional("trigger_mode"): vol.In(
            ["entity_equals", "entity_on", "numeric_threshold", "template"]
        ),
        vol.Optional("trigger_config"): _TRIGGER_CONFIG_SCHEMA,
        vol.Optional("template"): cv.string,
        vol.Optional("duration"): vol.Coerce(int),
        vol.Optional("light_filter"): [cv.entity_id],
        **_ENTRY_ID_FIELD,
    }
)

REORDER_SIGNALS_SCHEMA = vol.Schema(
    {
        vol.Required("order"): [cv.string],
        **_ENTRY_ID_FIELD,
    }
)

CONFIGURE_NOTIFICATIONS_SCHEMA = vol.Schema(
    {
        vol.Required("enabled"): cv.boolean,
        vol.Optional("targets", default=[]): [_validate_notify_target],
        **_ENTRY_ID_FIELD,
    }
)


async def _validate_and_generate_template(
    hass: HomeAssistant,
    trigger_mode: str,
    trigger_config: dict,
    template: str,
    signal_name: str,
) -> str | None:
    """Validate trigger config and return resolved template, or None on error.

    For template mode: checks that a template string is provided.
    For other modes: validates trigger_config, auto-generates template if missing.
    In all cases: validates Jinja2 syntax of the resolved template.
    Returns the (possibly generated) template string, or None if validation fails.
    """
    if trigger_mode == "template":
        if not template:
            _LOGGER.error(
                "Signal Lights: '%s' — template mode requires a template", signal_name
            )
            return None
    else:
        errors = validate_trigger_config(trigger_mode, trigger_config)
        if errors:
            _LOGGER.error(
                "Signal Lights: '%s' invalid trigger config: %s",
                signal_name,
                "; ".join(errors),
            )
            return None
        if not template:
            try:
                template = generate_template_from_trigger(trigger_mode, trigger_config)
            except ValueError as err:
                _LOGGER.error(
                    "Signal Lights: '%s' failed to generate template: %s",
                    signal_name,
                    err,
                )
                return None

    if template:
        try:
            from homeassistant.helpers.template import Template as HaTemplate  # noqa: PLC0415
            HaTemplate(template)
        except Exception as err:  # noqa: BLE001
            _LOGGER.error(
                "Signal Lights: '%s' — invalid Jinja2: %s", signal_name, err
            )
            return None

    return template


def _get_coordinator(
    hass: HomeAssistant, entry_id: str | None = None
) -> SignalLightsCoordinator | None:
    """Return the active coordinator for the requested entry.

    Uses hass.data[DOMAIN] for O(1) lookup instead of iterating config entries.

    - If entry_id is given, look up that specific entry.
    - If entry_id is None and exactly one entry exists, return it (backward compat).
    - If entry_id is None and multiple entries exist, log a warning and return None.
    - If no entries exist, return None (caller logs if needed).
    """
    domain_data = hass.data.get(DOMAIN, {})
    coords = {
        eid: c
        for eid, c in domain_data.items()
        if isinstance(c, SignalLightsCoordinator)
    }

    if not coords:
        return None

    if entry_id is not None:
        coord = coords.get(entry_id)
        if not coord:
            _LOGGER.warning(
                "Signal Lights: config_entry_id '%s' not found", entry_id
            )
            _LOGGER.debug("Available: %s", list(coords.keys()))
        return coord

    if len(coords) == 1:
        return next(iter(coords.values()))

    # Multiple entries and no entry_id specified
    _LOGGER.warning("Signal Lights: multiple setups exist — specify config_entry_id")
    _LOGGER.debug("Signal Lights: available entries: %s", list(coords.keys()))
    return None


def _resolve_coordinator(
    hass: HomeAssistant, call: ServiceCall
) -> SignalLightsCoordinator | None:
    """Return coordinator for the call, logging a warning when none is found.

    _get_coordinator already logs for: entry_id not found, multiple entries.
    We only add a warning here for the zero-entries case (setup not loaded yet).
    """
    entry_id = call.data.get("config_entry_id")
    coord = _get_coordinator(hass, entry_id)
    if coord is None:
        # Only log for the zero-coordinators case — other cases already logged
        # by _get_coordinator (not-found, multiple setups).
        domain_data = hass.data.get(DOMAIN, {})
        has_any = any(
            isinstance(c, SignalLightsCoordinator) for c in domain_data.values()
        )
        if not has_any:
            _LOGGER.warning(
                "Signal Lights: no active coordinator — ignoring service call"
            )
    return coord


def _find_light_conflict(
    hass: HomeAssistant, entity_id: str, skip_coord: SignalLightsCoordinator
) -> tuple[str, str] | None:
    """Return (entry_id, title) of another setup that already owns entity_id, or None."""
    domain_data = hass.data.get(DOMAIN, {})
    for eid, other in domain_data.items():
        if isinstance(other, SignalLightsCoordinator) and other is not skip_coord:
            if any(light["entity_id"] == entity_id for light in other.store.get_lights()):
                return eid, other.entry_title
    return None


async def async_register_services(hass: HomeAssistant) -> None:
    """Register all Signal Lights services."""
    if hass.services.has_service(DOMAIN, "trigger_signal"):
        return  # already registered

    # Domain-level lock for add_light to prevent cross-entry race conditions
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault("add_light_lock", asyncio.Lock())

    async def handle_trigger_signal(call: ServiceCall) -> None:
        """Handle signal_lights.trigger_signal."""
        coord = _resolve_coordinator(hass, call)
        if coord is None:
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
        coord = _resolve_coordinator(hass, call)
        if coord is None:
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
        coord = _resolve_coordinator(hass, call)
        if coord is None:
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
        coord = _resolve_coordinator(hass, call)
        if coord is None:
            return

        async with hass.data[DOMAIN]["add_light_lock"]:
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
            conflict = _find_light_conflict(hass, entity_id, coord)
            if conflict is not None:
                conflict_entry_id, conflict_title = conflict
                _LOGGER.error(
                    "Signal Lights: light '%s' is already registered in setup '%s' (%s) — "
                    "remove it there first before adding to '%s'",
                    entity_id,
                    conflict_title,
                    conflict_entry_id,
                    coord.entry_title,
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
        coord = _resolve_coordinator(hass, call)
        if coord is None:
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
        coord = _resolve_coordinator(hass, call)
        if coord is None:
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

        # Validate trigger config and resolve template (shared helper).
        # Returns None on any error (already logged); returns the resolved
        # template string on success.
        resolved_template = await _validate_and_generate_template(
            hass, trigger_mode, trigger_config, template, name
        )
        if resolved_template is None:
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
            "template": resolved_template or "",
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
        coord = _resolve_coordinator(hass, call)
        if coord is None:
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

    async def handle_update_signal(call: ServiceCall) -> None:
        """Handle signal_lights.update_signal."""
        coord = _resolve_coordinator(hass, call)
        if coord is None:
            return
        name = call.data["name"]

        # Find the existing signal first
        existing = coord.store.get_signal_by_name(name)
        if existing is None:
            _LOGGER.warning(
                "signal_lights.update_signal: signal '%s' not found", name
            )
            return

        updates: dict = {}

        # Handle rename
        if "new_name" in call.data:
            new_name = call.data["new_name"]
            # Check for collision only if name actually changed
            if new_name != name and coord.store.get_signal_by_name(new_name) is not None:
                _LOGGER.error(
                    "Signal Lights: update_signal — a signal named '%s' already exists", new_name
                )
                return
            updates["name"] = new_name

        if "color" in call.data:
            updates["color"] = list(call.data["color"])
        if "trigger_type" in call.data:
            updates["trigger_type"] = call.data["trigger_type"]
        if "duration" in call.data:
            updates["duration"] = call.data["duration"]
        if "light_filter" in call.data:
            updates["light_filter"] = call.data["light_filter"]

        # Determine effective trigger_mode and trigger_config for validation/regen
        new_trigger_mode = call.data.get("trigger_mode", existing.get("trigger_mode", "template"))
        new_trigger_config = call.data.get("trigger_config", existing.get("trigger_config", {}))
        new_template = call.data.get("template", existing.get("template", ""))

        if "trigger_mode" in call.data:
            updates["trigger_mode"] = new_trigger_mode
        if "trigger_config" in call.data:
            updates["trigger_config"] = new_trigger_config
        if "template" in call.data:
            updates["template"] = new_template

        # Determine if template-related validation is needed.
        # We validate when: trigger_mode/config changed, or template explicitly updated.
        trigger_mode_changed = "trigger_mode" in call.data or "trigger_config" in call.data
        template_explicitly_updated = "template" in call.data

        needs_validation = trigger_mode_changed or template_explicitly_updated

        # Security: restrict template mode to admin users.
        # Check when: the effective mode is "template" (new or existing) AND we're
        # modifying something that involves the template.
        existing_mode = existing.get("trigger_mode", "template")
        is_template_mode_call = (
            new_trigger_mode == "template"
            or (existing_mode == "template" and template_explicitly_updated)
        )
        if is_template_mode_call and needs_validation:
            # user_id is None for system/automation calls — trusted
            if call.context.user_id:
                user = await hass.auth.async_get_user(call.context.user_id)
                if not user or not user.is_admin:
                    _LOGGER.error(
                        "Signal Lights: template trigger mode requires admin privileges"
                    )
                    return

        if needs_validation:
            # Validate and resolve the template using the shared helper
            resolved_template = await _validate_and_generate_template(
                hass, new_trigger_mode, new_trigger_config, new_template, name
            )
            if resolved_template is None:
                return
            updates["template"] = resolved_template
        elif template_explicitly_updated and new_template:
            # Template changed without mode/config change — validate Jinja2 only
            try:
                from homeassistant.helpers.template import Template as HaTemplate  # noqa: PLC0415
                HaTemplate(new_template)
            except Exception as err:  # noqa: BLE001
                _LOGGER.error(
                    "Signal Lights: update_signal '%s' — invalid Jinja2: %s", name, err
                )
                return

        if not updates:
            _LOGGER.debug("signal_lights.update_signal: no fields to update for '%s'", name)
            return

        saved = await coord.store.update_signal(name, updates)
        if saved:
            await coord.async_reload_config()
            _LOGGER.info("Signal Lights: updated signal '%s' with %s", name, list(updates.keys()))
        else:
            _LOGGER.warning("signal_lights.update_signal: signal '%s' disappeared before save", name)

    hass.services.async_register(
        DOMAIN, "update_signal", handle_update_signal, schema=UPDATE_SIGNAL_SCHEMA
    )

    async def handle_reorder_signals(call: ServiceCall) -> None:
        """Handle signal_lights.reorder_signals."""
        coord = _resolve_coordinator(hass, call)
        if coord is None:
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
        coord = _resolve_coordinator(hass, call)
        if coord is None:
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
        "add_light", "remove_light", "add_signal", "update_signal", "remove_signal",
        "reorder_signals", "configure_notifications",
    ):
        hass.services.async_remove(DOMAIN, service)
