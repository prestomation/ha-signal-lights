"""Config flow for Signal Lights integration.

Flow:
  1. async_step_user — Name the instance (default: "Signal Lights")
  2. Options flow — Manage lights and signals post-setup
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

from .const import DOMAIN

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

            # Prevent duplicate config entries
            await self.async_set_unique_id("signal_lights_instance")
            self._abort_if_unique_id_configured()

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
    """Options flow for Signal Lights.

    Lights and signals are managed via service calls and the options flow
    provides a summary of current configuration.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the options form with current configuration summary."""
        if user_input is not None:
            return self.async_create_entry(title="", data={})

        # Get current config from the coordinator
        lights_info = "No lights configured"
        signals_info = "No signals configured"
        try:
            coord = getattr(self.config_entry, "runtime_data", None)
            if coord is not None and hasattr(coord, "store"):
                lights = coord.store.get_lights()
                if lights:
                    light_names = [l["entity_id"] for l in lights]
                    lights_info = ", ".join(light_names)

                signals = coord.store.get_signals()
                if signals:
                    signal_names = [s["name"] for s in signals]
                    signals_info = ", ".join(signal_names)
        except Exception:  # noqa: BLE001
            lights_info = "Unable to load configuration"
            signals_info = "Unable to load configuration"

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({}),
            description_placeholders={
                "current_lights": lights_info,
                "current_signals": signals_info,
            },
        )
