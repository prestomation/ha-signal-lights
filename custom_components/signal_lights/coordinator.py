"""DataUpdateCoordinator for Signal Lights.

Manages the signal evaluation engine, template tracking, and light control.
Template listeners handle real-time updates; the coordinator polls every 30s
as a fallback to catch expired event signals and sync state.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_template_result, TrackTemplate
from homeassistant.helpers.template import Template
try:
    from homeassistant.helpers.device_registry import DeviceInfo
except ImportError:
    from homeassistant.helpers.entity import DeviceInfo  # type: ignore[no-redef]
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .engine import Signal, LightConfig, SignalEngine
from .store import SignalLightsStore

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=30)


class SignalLightsCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that manages signal evaluation and light control."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        store: SignalLightsStore,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Signal Lights",
            update_interval=SCAN_INTERVAL,
        )
        self.store = store
        self._entry = entry
        self.engine = SignalEngine()
        self._template_unsubs: list[Any] = []

    async def async_setup(self) -> None:
        """Set up the engine from stored configuration and start template tracking."""
        self._load_engine_config()
        self._setup_template_listeners()

    def _load_engine_config(self) -> None:
        """Load signals and lights from the store into the engine."""
        # Load lights
        lights = [
            LightConfig(
                entity_id=l["entity_id"],
                brightness=l.get("brightness", 255),
            )
            for l in self.store.get_lights()
        ]
        self.engine.set_lights(lights)

        # Load signals
        signals = [
            Signal(
                name=s["name"],
                priority=s.get("priority", 0),
                color=tuple(s.get("color", [255, 255, 255])),
                trigger_type=s.get("trigger_type", "condition"),
                template=s.get("template", ""),
                duration=s.get("duration", 0),
                light_filter=s.get("light_filter", []),
                sort_order=s.get("sort_order", 0),
            )
            for s in self.store.get_signals()
        ]
        self.engine.set_signals(signals)

    def _setup_template_listeners(self) -> None:
        """Set up template listeners for all signals."""
        # Clean up existing listeners
        for unsub in self._template_unsubs:
            unsub()
        self._template_unsubs.clear()

        for signal in self.engine.signals:
            if not signal.template:
                continue

            template = Template(signal.template, self.hass)

            @callback
            def _template_changed(
                event, updates, signal_name=signal.name, sig=signal
            ):
                """Handle template result change."""
                for update in updates:
                    result = update.result
                    # Treat errors as falsy
                    if isinstance(result, Exception):
                        _LOGGER.warning(
                            "Signal '%s' template error: %s", signal_name, result
                        )
                        if sig.trigger_type == "condition":
                            self.engine.deactivate_signal(signal_name)
                        continue

                    is_truthy = _result_is_truthy(result)

                    if sig.trigger_type == "condition":
                        if is_truthy:
                            self.engine.activate_signal(signal_name)
                        else:
                            self.engine.deactivate_signal(signal_name)
                    elif sig.trigger_type == "event":
                        # Event signals activate on truthy transition
                        if is_truthy:
                            self.engine.activate_signal(signal_name)

                # Push updates to lights
                self.hass.async_create_task(self._apply_light_states())
                self.async_set_updated_data(self._build_data())

            track_template = TrackTemplate(template, None, None)

            unsub = async_track_template_result(
                self.hass,
                [track_template],
                _template_changed,
            )
            self._template_unsubs.append(unsub)

    async def _apply_light_states(self) -> None:
        """Push the current signal evaluation to physical lights."""
        states = self.engine.evaluate()
        for entity_id, state in states.items():
            if state is None:
                await self.hass.services.async_call(
                    "light",
                    "turn_off",
                    {"entity_id": entity_id},
                    blocking=False,
                )
            else:
                await self.hass.services.async_call(
                    "light",
                    "turn_on",
                    {
                        "entity_id": entity_id,
                        "rgb_color": list(state["rgb_color"]),
                        "brightness": state["brightness"],
                    },
                    blocking=False,
                )

    def _build_data(self) -> dict[str, Any]:
        """Build the coordinator data dict consumed by sensors."""
        winner = self.engine.get_global_winner()
        active_signals = self.engine.get_active_signals()
        return {
            "active_signal": winner.name if winner else "none",
            "active_color": _rgb_to_hex(winner.color) if winner else "#000000",
            "queue_depth": len(active_signals),
            "is_active": len(active_signals) > 0,
            "active_signal_names": [a.signal.name for a in active_signals],
        }

    async def _async_update_data(self) -> dict[str, Any]:
        """Fallback polling: clean up expired signals and re-evaluate."""
        expired = self.engine.cleanup_expired()
        if expired:
            _LOGGER.debug("Expired signals: %s", expired)
            await self._apply_light_states()
        return self._build_data()

    async def async_reload_config(self) -> None:
        """Reload configuration from store and re-setup template listeners."""
        self._load_engine_config()
        self._setup_template_listeners()
        await self._apply_light_states()
        self.async_set_updated_data(self._build_data())

    async def async_trigger_signal(self, name: str) -> bool:
        """Manually trigger an event signal."""
        result = self.engine.activate_signal(name)
        if result:
            await self._apply_light_states()
            self.async_set_updated_data(self._build_data())
        return result

    async def async_dismiss_signal(self, name: str) -> bool:
        """Manually dismiss a signal."""
        result = self.engine.dismiss_signal(name)
        if result:
            await self._apply_light_states()
            self.async_set_updated_data(self._build_data())
        return result

    async def async_refresh_signals(self) -> None:
        """Force re-evaluate all signals."""
        self.engine.cleanup_expired()
        await self._apply_light_states()
        self.async_set_updated_data(self._build_data())

    def get_device_info(self) -> DeviceInfo:
        """Return DeviceInfo for the Signal Lights instance."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title or "Signal Lights",
            manufacturer="Signal Lights",
            model="Signal Controller",
        )

    async def async_shutdown(self) -> None:
        """Clean up template listeners on shutdown."""
        for unsub in self._template_unsubs:
            unsub()
        self._template_unsubs.clear()


def _result_is_truthy(result: Any) -> bool:
    """Determine if a template result is truthy.

    Handles HA template results which can be strings like 'True', 'true',
    'on', 'yes', or actual booleans.
    """
    if isinstance(result, bool):
        return result
    if isinstance(result, str):
        return result.lower() in ("true", "on", "yes", "1")
    if isinstance(result, (int, float)):
        return result != 0
    return bool(result)


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    """Convert an RGB tuple to a hex color string."""
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
