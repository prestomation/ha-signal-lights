"""Binary sensor platform for Signal Lights integration.

Provides:
  - binary_sensor.signal_lights_active — on when any signal is active
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
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
    """Set up Signal Lights binary sensor entities."""
    coordinator: SignalLightsCoordinator = entry.runtime_data
    async_add_entities([
        SignalLightsActiveBinarySensor(coordinator, entry),
    ])


class SignalLightsActiveBinarySensor(
    CoordinatorEntity[SignalLightsCoordinator], BinarySensorEntity
):
    """Binary sensor: on when any signal is currently active."""

    _attr_has_entity_name = True
    _attr_name = "Active"
    _attr_icon = "mdi:alarm-light"

    def __init__(
        self,
        coordinator: SignalLightsCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialise."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_active"
        self._attr_device_info = coordinator.get_device_info()

    @property
    def is_on(self) -> bool:
        """Return True if any signal is active."""
        if self.coordinator.data is None:
            return False
        return self.coordinator.data.get("is_active", False)
