"""Sensor platform for Signal Lights integration.

Provides:
  - sensor.signal_lights_active_signal — name of the current winning signal
  - sensor.signal_lights_active_color — hex color of the current signal
  - sensor.signal_lights_queue_depth — count of active signals
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SignalLightsCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Signal Lights sensor entities."""
    coordinator: SignalLightsCoordinator = entry.runtime_data
    async_add_entities([
        SignalLightsActiveSignalSensor(coordinator, entry),
        SignalLightsActiveColorSensor(coordinator, entry),
        SignalLightsQueueDepthSensor(coordinator, entry),
    ])


class _SignalLightsSensorBase(CoordinatorEntity[SignalLightsCoordinator], SensorEntity):
    """Base class for Signal Lights sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SignalLightsCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialise."""
        super().__init__(coordinator)
        self._attr_device_info = coordinator.get_device_info()


class SignalLightsActiveSignalSensor(_SignalLightsSensorBase):
    """Sensor showing the name of the currently active signal."""

    _attr_name = "Active Signal"
    _attr_icon = "mdi:traffic-light"

    def __init__(self, coordinator: SignalLightsCoordinator, entry: ConfigEntry) -> None:
        """Initialise."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_active_signal"

    @property
    def native_value(self) -> str:
        """Return the name of the active signal."""
        if self.coordinator.data is None:
            return "none"
        return self.coordinator.data.get("active_signal", "none")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes including the full active signal list."""
        if self.coordinator.data is None:
            return {}
        return {
            "active_signals": self.coordinator.data.get("active_signal_names", []),
        }


class SignalLightsActiveColorSensor(_SignalLightsSensorBase):
    """Sensor showing the hex color of the currently active signal."""

    _attr_name = "Active Color"
    _attr_icon = "mdi:palette"

    def __init__(self, coordinator: SignalLightsCoordinator, entry: ConfigEntry) -> None:
        """Initialise."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_active_color"

    @property
    def native_value(self) -> str:
        """Return the hex color."""
        if self.coordinator.data is None:
            return "#000000"
        return self.coordinator.data.get("active_color", "#000000")


class SignalLightsQueueDepthSensor(_SignalLightsSensorBase):
    """Sensor showing the number of currently active signals."""

    _attr_name = "Queue Depth"
    _attr_icon = "mdi:format-list-numbered"

    def __init__(self, coordinator: SignalLightsCoordinator, entry: ConfigEntry) -> None:
        """Initialise."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_queue_depth"

    @property
    def native_value(self) -> int:
        """Return the queue depth."""
        if self.coordinator.data is None:
            return 0
        return self.coordinator.data.get("queue_depth", 0)
