"""Config flow for Signal Lights integration.

Flow:
  1. async_step_user — Name the instance (default: "Signal Lights")
  2. Options flow — Menu-driven UI for managing lights, signals, and notifications
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import DOMAIN, CONF_CYCLE_INTERVAL, DEFAULT_CYCLE_INTERVAL
from .engine import generate_template_from_trigger, validate_trigger_config

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional("name", default="Signal Lights"): str,
    }
)


class SignalLightsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial config flow for Signal Lights."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        if user_input is not None:
            name = user_input.get("name", "Signal Lights").strip() or "Signal Lights"

            # No unique_id constraint — multiple Signal Lights instances are supported.
            # Each entry gets isolated storage (signal_lights_{entry_id}).
            return self.async_create_entry(
                title=name,
                data={"name": name},
            )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SignalLightsOptionsFlow:
        """Return the options flow handler."""
        return SignalLightsOptionsFlow()


class SignalLightsOptionsFlow(OptionsFlow):
    """Options flow for Signal Lights — menu-driven light/signal management."""

    def __init__(self) -> None:
        """Initialise options flow state."""
        self._signal_data: dict[str, Any] = {}

    def _get_store(self):
        """Get the store from the coordinator."""
        coord = getattr(self.config_entry, "runtime_data", None)
        if coord is not None and hasattr(coord, "store"):
            return coord.store
        return None

    async def _reload_coordinator(self) -> None:
        """Reload the coordinator after config changes."""
        coord = getattr(self.config_entry, "runtime_data", None)
        if coord is not None and hasattr(coord, "async_reload_config"):
            await coord.async_reload_config()

    # -----------------------------------------------------------------------
    # Main menu
    # -----------------------------------------------------------------------

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the main menu as a select dropdown."""
        if user_input is not None:
            action = user_input.get("action")
            if action == "add_light":
                return await self.async_step_add_light()
            if action == "remove_light":
                return await self.async_step_remove_light()
            if action == "add_signal":
                return await self.async_step_add_signal()
            if action == "remove_signal":
                return await self.async_step_remove_signal()
            if action == "reorder_signals":
                return await self.async_step_reorder_signals()
            if action == "configure_notifications":
                return await self.async_step_configure_notifications()
            if action == "configure_cycling":
                return await self.async_step_configure_cycling()
            return self.async_create_entry(title="", data={})

        store = self._get_store()
        lights = store.get_lights() if store else []
        signals = store.get_signals() if store else []

        light_summary = ", ".join(l["entity_id"].split(".")[-1] for l in lights) if lights else "None"
        signal_summary = ", ".join(
            f"{s['name']} (#{i+1})" for i, s in enumerate(
                sorted(signals, key=lambda x: x.get("sort_order", 0))
            )
        ) if signals else "None"

        menu_options = [
            selector.SelectOptionDict(value="add_light", label="➕ Add a light"),
            selector.SelectOptionDict(value="add_signal", label="➕ Add a signal"),
        ]
        if lights:
            menu_options.append(
                selector.SelectOptionDict(value="remove_light", label="➖ Remove a light")
            )
        if signals:
            menu_options.append(
                selector.SelectOptionDict(value="remove_signal", label="➖ Remove a signal")
            )
        if len(signals) > 1:
            menu_options.append(
                selector.SelectOptionDict(value="reorder_signals", label="⬆️ Reorder signals")
            )
        menu_options.append(
            selector.SelectOptionDict(value="configure_notifications", label="🔔 Configure notifications")
        )
        menu_options.append(
            selector.SelectOptionDict(value="configure_cycling", label="🔄 Configure signal cycling")
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("action"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=menu_options,
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
            description_placeholders={
                "light_count": str(len(lights)),
                "light_list": light_summary,
                "signal_count": str(len(signals)),
                "signal_list": signal_summary,
            },
        )

    # -----------------------------------------------------------------------
    # Add light
    # -----------------------------------------------------------------------

    async def async_step_add_light(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a light entity."""
        if user_input is not None:
            store = self._get_store()
            if store:
                entity_id = user_input["entity_id"]
                brightness = user_input.get("brightness", 255)
                await store.add_light(entity_id, brightness)
                await self._reload_coordinator()
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="add_light",
            data_schema=vol.Schema(
                {
                    vol.Required("entity_id"): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="light")
                    ),
                    vol.Optional("brightness", default=255): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1, max=255, step=1, mode=selector.NumberSelectorMode.SLIDER
                        )
                    ),
                }
            ),
        )

    # -----------------------------------------------------------------------
    # Remove light
    # -----------------------------------------------------------------------

    async def async_step_remove_light(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove a registered light."""
        store = self._get_store()
        lights = store.get_lights() if store else []

        if not lights:
            return self.async_abort(reason="no_lights")

        if user_input is not None:
            if store:
                await store.remove_light(user_input["entity_id"])
                await self._reload_coordinator()
            return self.async_create_entry(title="", data={})

        light_options = [
            selector.SelectOptionDict(
                value=l["entity_id"],
                label=f"{l['entity_id']} (brightness: {l.get('brightness', 255)})",
            )
            for l in lights
        ]

        return self.async_show_form(
            step_id="remove_light",
            data_schema=vol.Schema(
                {
                    vol.Required("entity_id"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=light_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
        )

    # -----------------------------------------------------------------------
    # Add signal — step 1: basics + trigger mode
    # -----------------------------------------------------------------------

    async def async_step_add_signal(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a signal — step 1: name, color, trigger type, trigger mode."""
        if user_input is not None:
            self._signal_data = {
                "name": user_input["name"],
                "color": _parse_color(user_input["color"]),
                "trigger_type": user_input["trigger_type"],
                "trigger_mode": user_input["trigger_mode"],
            }
            trigger_mode = user_input["trigger_mode"]
            if trigger_mode == "entity_equals":
                return await self.async_step_trigger_entity_equals()
            if trigger_mode == "entity_on":
                return await self.async_step_trigger_entity_on()
            if trigger_mode == "numeric_threshold":
                return await self.async_step_trigger_numeric()
            # template mode
            return await self.async_step_trigger_template()

        return self.async_show_form(
            step_id="add_signal",
            data_schema=vol.Schema(
                {
                    vol.Required("name"): selector.TextSelector(),
                    vol.Required("color", default=[255, 0, 0]): selector.ColorRGBSelector(),
                    vol.Required("trigger_type", default="condition"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value="condition", label="Condition (active while true)"),
                                selector.SelectOptionDict(value="event", label="Event (fires for a duration)"),
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required("trigger_mode", default="entity_equals"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(value="entity_equals", label="Entity equals state"),
                                selector.SelectOptionDict(value="entity_on", label="Entity is on"),
                                selector.SelectOptionDict(value="numeric_threshold", label="Numeric above/below"),
                                selector.SelectOptionDict(value="template", label="Template (advanced)"),
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
        )

    # -----------------------------------------------------------------------
    # Trigger mode: entity_equals
    # -----------------------------------------------------------------------

    async def async_step_trigger_entity_equals(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Entity equals state trigger configuration."""
        if user_input is not None:
            trigger_config = {
                "entity_id": user_input["entity_id"],
                "state": user_input["state_value"],
            }
            template = generate_template_from_trigger("entity_equals", trigger_config)
            self._signal_data["trigger_config"] = trigger_config
            self._signal_data["template"] = template
            return await self._finalize_signal(user_input)

        schema_dict = {
            vol.Required("entity_id"): selector.EntitySelector(),
            vol.Required("state_value"): selector.TextSelector(),
        }
        self._add_duration_and_filter_fields(schema_dict)

        return self.async_show_form(
            step_id="trigger_entity_equals",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={
                "signal_name": self._signal_data.get("name", ""),
            },
        )

    # -----------------------------------------------------------------------
    # Trigger mode: entity_on
    # -----------------------------------------------------------------------

    async def async_step_trigger_entity_on(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Entity is on trigger configuration."""
        if user_input is not None:
            trigger_config = {"entity_id": user_input["entity_id"]}
            template = generate_template_from_trigger("entity_on", trigger_config)
            self._signal_data["trigger_config"] = trigger_config
            self._signal_data["template"] = template
            return await self._finalize_signal(user_input)

        schema_dict = {
            vol.Required("entity_id"): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=["binary_sensor", "switch", "light", "input_boolean"]
                )
            ),
        }
        self._add_duration_and_filter_fields(schema_dict)

        return self.async_show_form(
            step_id="trigger_entity_on",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={
                "signal_name": self._signal_data.get("name", ""),
            },
        )

    # -----------------------------------------------------------------------
    # Trigger mode: numeric_threshold
    # -----------------------------------------------------------------------

    async def async_step_trigger_numeric(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Numeric above/below trigger configuration."""
        if user_input is not None:
            trigger_config = {
                "entity_id": user_input["entity_id"],
                "threshold": float(user_input["threshold"]),
                "direction": user_input["direction"],
            }
            template = generate_template_from_trigger("numeric_threshold", trigger_config)
            self._signal_data["trigger_config"] = trigger_config
            self._signal_data["template"] = template
            return await self._finalize_signal(user_input)

        schema_dict = {
            vol.Required("entity_id"): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Required("threshold"): selector.NumberSelector(
                selector.NumberSelectorConfig(mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required("direction", default="above"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value="above", label="Above"),
                        selector.SelectOptionDict(value="below", label="Below"),
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }
        self._add_duration_and_filter_fields(schema_dict)

        return self.async_show_form(
            step_id="trigger_numeric",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={
                "signal_name": self._signal_data.get("name", ""),
            },
        )

    # -----------------------------------------------------------------------
    # Trigger mode: template (advanced)
    # -----------------------------------------------------------------------

    async def async_step_trigger_template(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Raw template trigger configuration."""
        if user_input is not None:
            self._signal_data["trigger_config"] = {"template": user_input["template"]}
            self._signal_data["template"] = user_input["template"]
            return await self._finalize_signal(user_input)

        schema_dict: dict[Any, Any] = {
            vol.Required("template"): selector.TemplateSelector(),
        }
        self._add_duration_and_filter_fields(schema_dict)

        return self.async_show_form(
            step_id="trigger_template",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={
                "signal_name": self._signal_data.get("name", ""),
                "trigger_type": self._signal_data.get("trigger_type", ""),
            },
        )

    # -----------------------------------------------------------------------
    # Signal finalization helper
    # -----------------------------------------------------------------------

    def _add_duration_and_filter_fields(self, schema_dict: dict) -> None:
        """Add duration and light_filter fields to a schema dict."""
        if self._signal_data.get("trigger_type") == "event":
            schema_dict[vol.Required("duration", default=60)] = selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=86400,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="seconds",
                )
            )

        store = self._get_store()
        lights = store.get_lights() if store else []
        if lights:
            schema_dict[vol.Optional("light_filter", default=[])] = selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="light",
                    multiple=True,
                )
            )

    async def _finalize_signal(self, user_input: dict[str, Any]) -> ConfigFlowResult:
        """Save the signal to the store and reload."""
        trigger_mode = self._signal_data.get("trigger_mode", "template")
        trigger_config = self._signal_data.get("trigger_config", {})

        # Validate trigger config before saving
        errors = validate_trigger_config(trigger_mode, trigger_config)
        if errors:
            _LOGGER.error(
                "Signal Lights (options flow): invalid trigger config for signal '%s': %s",
                self._signal_data.get("name", "?"),
                "; ".join(errors),
            )
            # Show the appropriate form again, with the error surfaced to the user
            form_errors = {"base": "invalid_trigger_config"}
            step_map = {
                "entity_equals": ("trigger_entity_equals", self.async_step_trigger_entity_equals),
                "entity_on": ("trigger_entity_on", self.async_step_trigger_entity_on),
                "numeric_threshold": ("trigger_numeric", self.async_step_trigger_numeric),
                "template": ("trigger_template", self.async_step_trigger_template),
            }
            step_info = step_map.get(trigger_mode)
            if step_info is not None:
                # Re-invoke the step handler to get the base form, then inject errors
                result = await step_info[1]()
                # Patch errors into the show_form result
                if hasattr(result, "description_placeholders") or isinstance(result, dict):
                    # FlowResultType.FORM — inject errors
                    if isinstance(result, dict) and result.get("type") == "form":
                        result["errors"] = form_errors
                    elif hasattr(result, "__class__") and result.__class__.__name__ == "FlowResult":
                        result["errors"] = form_errors
                return result
            # Fallback: abort
            return self.async_abort(reason="invalid_trigger_config")

        store = self._get_store()
        if store:
            signal_def = {
                "name": self._signal_data["name"],
                "color": self._signal_data["color"],
                "trigger_type": self._signal_data["trigger_type"],
                "trigger_mode": trigger_mode,
                "trigger_config": trigger_config,
                "template": self._signal_data.get("template", ""),
                "duration": int(user_input.get("duration", 0)),
                "light_filter": user_input.get("light_filter", []),
            }
            await store.add_signal(signal_def)
            await self._reload_coordinator()
        self._signal_data = {}
        return self.async_create_entry(title="", data={})

    # -----------------------------------------------------------------------
    # Remove signal
    # -----------------------------------------------------------------------

    async def async_step_remove_signal(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove a signal definition."""
        store = self._get_store()
        signals = store.get_signals() if store else []

        if not signals:
            return self.async_abort(reason="no_signals")

        if user_input is not None:
            if store:
                await store.remove_signal(user_input["name"])
                await self._reload_coordinator()
            return self.async_create_entry(title="", data={})

        signal_options = [
            selector.SelectOptionDict(
                value=s["name"],
                label=f"#{i+1} {s['name']} ({s.get('trigger_type', 'condition')})",
            )
            for i, s in enumerate(sorted(signals, key=lambda x: x.get("sort_order", 0)))
        ]

        return self.async_show_form(
            step_id="remove_signal",
            data_schema=vol.Schema(
                {
                    vol.Required("name"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=signal_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
        )

    # -----------------------------------------------------------------------
    # Reorder signals
    # -----------------------------------------------------------------------

    async def async_step_reorder_signals(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reorder signals by selecting a signal and a new position."""
        store = self._get_store()
        signals = store.get_signals() if store else []

        if len(signals) < 2:
            return self.async_abort(reason="not_enough_signals")

        if user_input is not None:
            if store:
                signal_name = user_input["signal"]
                new_position = int(user_input["position"])
                # Build new order
                ordered = sorted(signals, key=lambda x: x.get("sort_order", 0))
                names = [s["name"] for s in ordered]
                if signal_name in names:
                    names.remove(signal_name)
                    # new_position is 1-indexed
                    insert_idx = max(0, min(new_position - 1, len(names)))
                    names.insert(insert_idx, signal_name)
                    await store.reorder_signals(names)
                    await self._reload_coordinator()
            return self.async_create_entry(title="", data={})

        ordered = sorted(signals, key=lambda x: x.get("sort_order", 0))
        signal_options = [
            selector.SelectOptionDict(
                value=s["name"],
                label=f"#{i+1} {s['name']}",
            )
            for i, s in enumerate(ordered)
        ]
        position_options = [
            selector.SelectOptionDict(value=str(i + 1), label=f"Position {i + 1}")
            for i in range(len(ordered))
        ]

        return self.async_show_form(
            step_id="reorder_signals",
            data_schema=vol.Schema(
                {
                    vol.Required("signal"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=signal_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required("position"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=position_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
        )

    # -----------------------------------------------------------------------
    # Configure notifications
    # -----------------------------------------------------------------------

    async def async_step_configure_notifications(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure notification settings."""
        store = self._get_store()

        if user_input is not None:
            if store:
                enabled = user_input.get("enabled", False)
                targets_raw = user_input.get("targets", "")
                targets = [
                    t.strip() for t in targets_raw.split(",") if t.strip()
                ] if targets_raw else []
                await store.set_notification_config(enabled, targets)
                await self._reload_coordinator()
            return self.async_create_entry(title="", data={})

        notif_config = store.get_notification_config() if store else {}
        current_enabled = notif_config.get("enabled", False)
        current_targets = ", ".join(notif_config.get("targets", []))

        return self.async_show_form(
            step_id="configure_notifications",
            data_schema=vol.Schema(
                {
                    vol.Required("enabled", default=current_enabled): selector.BooleanSelector(),
                    vol.Optional("targets", default=current_targets): selector.TextSelector(
                        selector.TextSelectorConfig(
                            multiline=False,
                        )
                    ),
                }
            ),
            description_placeholders={
                "current_status": "enabled" if current_enabled else "disabled",
            },
        )


    # -----------------------------------------------------------------------
    # Configure signal cycling
    # -----------------------------------------------------------------------

    async def async_step_configure_cycling(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure signal cycling settings."""
        if user_input is not None:
            cycle_interval = int(user_input.get(CONF_CYCLE_INTERVAL, DEFAULT_CYCLE_INTERVAL))
            # Persist in options so the coordinator can read it
            new_options = dict(self.config_entry.options)
            new_options[CONF_CYCLE_INTERVAL] = cycle_interval
            self.hass.config_entries.async_update_entry(
                self.config_entry, options=new_options
            )
            await self._reload_coordinator()
            return self.async_create_entry(title="", data={})

        current_value = int(
            self.config_entry.options.get(CONF_CYCLE_INTERVAL, DEFAULT_CYCLE_INTERVAL)
        )

        return self.async_show_form(
            step_id="configure_cycling",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_CYCLE_INTERVAL, default=current_value): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=300,
                            step=1,
                            mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement="seconds",
                        )
                    ),
                }
            ),
        )


def _parse_color(color_input: Any) -> list[int]:
    """Parse color from various input formats to [R, G, B]."""
    if isinstance(color_input, list) and len(color_input) == 3:
        return [int(c) for c in color_input]
    if isinstance(color_input, dict):
        return [int(color_input.get("r", 0)), int(color_input.get("g", 0)), int(color_input.get("b", 0))]
    return [255, 255, 255]
