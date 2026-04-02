"""DataUpdateCoordinator for Signal Lights.

Manages the signal evaluation engine, template tracking, light control,
and persistent notifications.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later, async_track_template_result, TrackTemplate
from homeassistant.helpers.template import Template
try:
    from homeassistant.helpers.device_registry import DeviceInfo
except ImportError:
    from homeassistant.helpers.entity import DeviceInfo  # type: ignore[no-redef]
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, NOTIFY_TARGET_RE, CONF_CYCLE_INTERVAL, DEFAULT_CYCLE_INTERVAL
from .engine import Signal, LightConfig, SignalEngine
from .store import SignalLightsStore

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=30)
NOTIFICATION_TITLE = "\U0001f6a8 Signal Lights"


class SignalLightsCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that manages signal evaluation, light control, and notifications."""

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
        self._last_notified_signal: str | None = None
        self._last_notified_signal_names: list[str] = []
        self._signal_errors: dict[str, str] = {}
        self._flush_lock = asyncio.Lock()
        # Per-entry notification tag prevents cross-entry notification collisions
        self._notification_tag = f"signal_lights_{entry.entry_id}"
        # Signal cycling state
        self._cycle_index: int = 0
        self._cycle_cancel: Callable | None = None

    async def async_setup(self) -> None:
        """Set up the engine from stored configuration and start template tracking."""
        self._load_engine_config()
        self._setup_template_listeners()

    def _load_engine_config(self) -> None:
        """Load signals and lights from the store into the engine."""
        lights = [
            LightConfig(
                entity_id=light["entity_id"],
                brightness=light.get("brightness", 255),
            )
            for light in self.store.get_lights()
        ]
        self.engine.set_lights(lights)

        signals = [
            Signal(
                name=s["name"],
                color=tuple(s.get("color", [255, 255, 255])),
                trigger_type=s.get("trigger_type", "condition"),
                template=s.get("template", ""),
                duration=s.get("duration", 0),
                light_filter=s.get("light_filter", []),
                sort_order=s.get("sort_order", 0),
                trigger_mode=s.get("trigger_mode", "template"),
                trigger_config=s.get("trigger_config", {}),
            )
            for s in self.store.get_signals()
        ]
        self.engine.set_signals(signals)

    def _setup_template_listeners(self) -> None:
        """Set up template listeners for all signals."""
        for unsub in self._template_unsubs:
            unsub.async_remove()
        self._template_unsubs.clear()
        self._signal_errors = {}

        for signal in self.engine.signals:
            if not signal.template:
                continue

            try:
                template = Template(signal.template, self.hass)
            except Exception as err:  # noqa: BLE001
                _LOGGER.error(
                    "Signal Lights: signal '%s' has an invalid template and will be skipped: %s",
                    signal.name, err,
                )
                self._signal_errors[signal.name] = str(err)
                continue

            # Default args are used here to capture the current loop variables
            # (signal_name, sig) by value. Without default args, all closures
            # would reference the same loop variable (the last iteration's value)
            # due to Python's late-binding closure semantics.
            @callback
            def _template_changed(
                event, updates, signal_name=signal.name, sig=signal
            ):
                """Handle template result change."""
                for update in updates:
                    result = update.result
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
                        if is_truthy:
                            self.engine.activate_signal(signal_name)

                # Consolidate into a single task to avoid triple-scheduling
                self.hass.async_create_task(self._flush())

            track_template = TrackTemplate(template, None, None)

            unsub = async_track_template_result(
                self.hass,
                [track_template],
                _template_changed,
            )
            self._template_unsubs.append(unsub)

    async def _flush(self) -> None:
        """Apply light states, notifications, and update coordinator data.

        Uses a lock to prevent concurrent flushes from interleaving
        (e.g., rapid template state changes firing multiple callbacks).
        """
        async with self._flush_lock:
            await self._apply_light_states()
            await self._apply_notifications()
            self.async_set_updated_data(self._build_data())

    def _get_cycle_interval(self) -> int:
        """Return the configured cycle interval in seconds (0 = disabled)."""
        return int(
            self._entry.options.get(CONF_CYCLE_INTERVAL, DEFAULT_CYCLE_INTERVAL)
        )

    def _cancel_cycle_timer(self) -> None:
        """Cancel any running cycle timer."""
        if self._cycle_cancel is not None:
            self._cycle_cancel()
            self._cycle_cancel = None

    @callback
    def _cycle_tick(self, _now: Any) -> None:
        """Advance the cycle index and re-apply lights."""
        self._cycle_cancel = None  # timer has fired; clear reference
        active_signals = self.engine.get_active_signals()
        if len(active_signals) >= 2 and self._get_cycle_interval() > 0:
            self._cycle_index = (self._cycle_index + 1) % len(active_signals)
            # Schedule the next tick before the flush so the timer is always set
            self._cycle_cancel = async_call_later(
                self.hass, self._get_cycle_interval(), self._cycle_tick
            )
        else:
            self._cycle_index = 0
        self.hass.async_create_task(self._flush())

    async def _apply_light_states(self) -> None:
        """Push the current signal evaluation to physical lights.

        When cycling is active (cycle_interval > 0 and 2+ signals active),
        overrides the per-light winner with the currently displayed cycle signal.
        """
        active_signals = self.engine.get_active_signals()
        cycle_interval = self._get_cycle_interval()

        if cycle_interval > 0 and len(active_signals) >= 2:
            # Cycling mode: ensure timer is running
            if self._cycle_cancel is None:
                self._cycle_cancel = async_call_later(
                    self.hass, cycle_interval, self._cycle_tick
                )
            # Clamp index in case signals were removed
            self._cycle_index = self._cycle_index % len(active_signals)
            cycle_signal = active_signals[self._cycle_index].signal

            # Build light states using the cycling signal, respecting light_filter
            for light in self.engine.lights:
                try:
                    if cycle_signal.applies_to_light(light.entity_id):
                        await self.hass.services.async_call(
                            "light",
                            "turn_on",
                            {
                                "entity_id": light.entity_id,
                                "rgb_color": list(cycle_signal.color),
                                "brightness": light.brightness,
                            },
                            blocking=False,
                        )
                    else:
                        # Light not in this signal's filter — use normal evaluation
                        winner = self.engine.get_winning_signal_for_light(light.entity_id)
                        if winner is None:
                            await self.hass.services.async_call(
                                "light", "turn_off",
                                {"entity_id": light.entity_id},
                                blocking=False,
                            )
                        else:
                            await self.hass.services.async_call(
                                "light", "turn_on",
                                {
                                    "entity_id": light.entity_id,
                                    "rgb_color": list(winner.color),
                                    "brightness": light.brightness,
                                },
                                blocking=False,
                            )
                except Exception:  # noqa: BLE001
                    _LOGGER.warning(
                        "Signal Lights: failed to control light %s", light.entity_id
                    )
        else:
            # Normal mode (no cycling): cancel any running timer and reset index
            self._cancel_cycle_timer()
            self._cycle_index = 0
            states = self.engine.evaluate()
            for entity_id, state in states.items():
                try:
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
                except Exception:  # noqa: BLE001
                    _LOGGER.warning(
                        "Signal Lights: failed to control light %s", entity_id
                    )

    async def _apply_notifications(self) -> None:
        """Send/update/clear notifications based on all active signals."""
        notif_config = self.store.get_notification_config()
        if not notif_config.get("enabled", False):
            return

        active_signals = self.engine.get_active_signals()
        active_names = [a.signal.name for a in active_signals]
        winner = self.engine.get_global_winner()
        current_name = winner.name if winner else None

        # No change — skip
        if active_names == self._last_notified_signal_names:
            return

        notify_targets = notif_config.get("targets", [])

        if current_name is None:
            # All signals cleared — dismiss notifications
            await self._dismiss_notifications(notify_targets)
        else:
            # New or changed signals — send/update with full list
            await self._send_notifications(current_name, active_names, notify_targets)

        self._last_notified_signal = current_name
        self._last_notified_signal_names = active_names

    async def _call_notify_target(self, target: str, data: dict) -> None:
        """Call a notify service target with the given data.

        target must be in 'domain.service' format (e.g. notify.mobile_app_fold7).
        """
        parts = target.split(".", 1)
        if len(parts) == 2:
            try:
                await self.hass.services.async_call(
                    parts[0],
                    parts[1],
                    data,
                    blocking=False,
                )
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Failed to call notify target %s", target)

    async def _send_notifications(
        self, signal_name: str, all_signal_names: list[str], targets: list[str]
    ) -> None:
        """Send or update persistent notification and mobile targets."""
        if len(all_signal_names) > 1:
            others = [n for n in all_signal_names if n != signal_name]
            message = f"{signal_name}\nAlso active: {', '.join(others)}"
        else:
            message = signal_name

        # HA sidebar persistent notification
        try:
            await self.hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": NOTIFICATION_TITLE,
                    "message": message,
                    "notification_id": self._notification_tag,
                },
                blocking=False,
            )
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to create persistent notification")

        # Mobile app targets — validate domain before calling
        for target in targets:
            if not NOTIFY_TARGET_RE.match(target):
                _LOGGER.warning(
                    "Signal Lights: skipping invalid notification target '%s' "
                    "(must match notify.<service_name>)",
                    target,
                )
                continue
            await self._call_notify_target(
                target,
                {
                    "title": NOTIFICATION_TITLE,
                    "message": message,
                    "data": {"tag": self._notification_tag},
                },
            )

    async def _dismiss_notifications(self, targets: list[str]) -> None:
        """Dismiss persistent notification and clear mobile notifications."""
        try:
            await self.hass.services.async_call(
                "persistent_notification",
                "dismiss",
                {"notification_id": self._notification_tag},
                blocking=False,
            )
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Failed to dismiss persistent notification")

        for target in targets:
            if not NOTIFY_TARGET_RE.match(target):
                _LOGGER.warning(
                    "Signal Lights: skipping invalid notification target '%s' "
                    "(must match notify.<service_name>)",
                    target,
                )
                continue
            await self._call_notify_target(
                target,
                {
                    "message": "clear_notification",
                    "data": {"tag": self._notification_tag},
                },
            )

    def _build_data(self) -> dict[str, Any]:
        """Build the coordinator data dict consumed by sensors.

        Uses engine.signals instead of re-reading the store to avoid redundant
        disk reads and re-sorting.
        """
        winner = self.engine.get_global_winner()
        active_signals = self.engine.get_active_signals()
        signals_info = [
            {
                "name": s.name,
                "sort_order": s.sort_order,
                "color": list(s.color),
                "trigger_type": s.trigger_type,
                "trigger_mode": s.trigger_mode,
                "trigger_config": s.trigger_config,
                "template": s.template,
                "duration": s.duration,
                "light_filter": s.light_filter,
            }
            for s in self.engine.signals
        ]
        cycle_interval = self._get_cycle_interval()
        cycling_active = cycle_interval > 0 and len(active_signals) >= 2
        cycle_signal = (
            active_signals[self._cycle_index % len(active_signals)].signal
            if cycling_active
            else None
        )
        # When cycling, report the currently-displayed signal instead of the winner
        display_signal = cycle_signal if cycling_active else winner
        return {
            "active_signal": display_signal.name if display_signal else "none",
            "active_color": _rgb_to_hex(display_signal.color) if display_signal else "#000000",
            "queue_depth": len(active_signals),
            "is_active": len(active_signals) > 0,
            "active_signal_names": [a.signal.name for a in active_signals],
            "signals": signals_info,
            "lights": self.store.get_lights(),
            "notifications": self.store.get_notification_config(),
            "signal_errors": dict(self._signal_errors),
            "cycle_interval": cycle_interval,
            "cycle_index": self._cycle_index if cycling_active else 0,
        }

    async def _async_update_data(self) -> dict[str, Any]:
        """Fallback polling: clean up expired signals and re-evaluate."""
        expired = self.engine.cleanup_expired()
        if expired:
            _LOGGER.debug("Expired signals: %s", expired)
            async with self._flush_lock:
                await self._apply_light_states()
                await self._apply_notifications()
        return self._build_data()

    async def async_reload_config(self) -> None:
        """Reload configuration from store and re-setup template listeners."""
        # Cancel cycle timer on reload — it will be restarted by _apply_light_states if needed
        self._cancel_cycle_timer()
        self._cycle_index = 0
        self._load_engine_config()
        self._setup_template_listeners()
        await self._flush()

    async def async_trigger_signal(self, name: str) -> bool:
        """Manually trigger an event signal."""
        result = self.engine.activate_signal(name)
        if result:
            await self._flush()
        return result

    async def async_dismiss_signal(self, name: str) -> bool:
        """Manually dismiss a signal."""
        result = self.engine.dismiss_signal(name)
        if result:
            await self._flush()
        return result

    async def async_refresh_signals(self) -> None:
        """Force re-evaluate all signals."""
        self.engine.cleanup_expired()
        await self._flush()

    @property
    def entry_title(self) -> str:
        """Human-readable name for this config entry."""
        return self._entry.title

    def get_device_info(self) -> DeviceInfo:
        """Return DeviceInfo for the Signal Lights instance."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title or "Signal Lights",
            manufacturer="Signal Lights",
            model="Signal Controller",
        )

    async def async_shutdown(self) -> None:
        """Clean up template listeners and cycle timer on shutdown."""
        self._cancel_cycle_timer()
        for unsub in self._template_unsubs:
            unsub.async_remove()
        self._template_unsubs.clear()


def _result_is_truthy(result: Any) -> bool:
    """Determine if a template result is truthy."""
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
