"""Scene platform for Sinum integration.

Exposes Sinum hub scenes as Home Assistant Scene entities, enabling
automation triggers and scene activation.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.scene import Scene
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SinumCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Sinum scene entities from a config entry."""
    coordinator: SinumCoordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]

    @callback
    def update_scenes() -> None:
        """Update scene entities."""
        entities = []

        # Query virtual devices for scene types (scenes are virtual/device family specific)
        if "devices" in coordinator.data:
            for device in coordinator.data["devices"]:
                # Scenes are typically under "schedules" or "scenes" device family
                if device.get("device_family") in ["scenes", "virtual"]:
                    device_type = device.get("type", "")
                    if "scene" in device_type.lower():
                        entities.append(SinumSceneEntity(coordinator, config_entry, device))

        if entities:
            async_add_entities(entities, update_before_add=False)

    # Initial update
    coordinator.async_add_listener(update_scenes)
    update_scenes()


class SinumSceneEntity(CoordinatorEntity, Scene):
    """Represents a Sinum scene entity."""

    def __init__(
        self,
        coordinator: SinumCoordinator,
        config_entry: ConfigEntry,
        device: dict[str, Any],
    ) -> None:
        """Initialize the scene entity."""
        super().__init__(coordinator)

        self._device = device
        self._config_entry = config_entry
        self._attr_name = device.get("name", "Scene")
        self._attr_unique_id = f"sinum_scene_{device.get('id', 'unknown')}"

        # Device info for Home Assistant
        hub_name = config_entry.data.get("host", "Sinum Hub")
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{hub_name}_scenes")},
            "name": f"{hub_name} Scenes",
            "manufacturer": "Sinapse",
            "model": "Scene Group",
        }

    async def async_activate(self, **kwargs: Any) -> None:
        """Activate the scene."""
        device_id = self._device.get("id")

        if not device_id:
            _LOGGER.error("Scene has no device ID: %s", self._device)
            return

        try:
            # Run the scene via API
            await self.coordinator.client.run_scene(device_id)
            _LOGGER.debug("Scene activated: %s (id: %s)", self._attr_name, device_id)
        except Exception as err:
            _LOGGER.error("Error activating scene %s: %s", self._attr_name, err)
            raise

    @property
    def available(self) -> bool:
        """Scene is available if coordinator is OK."""
        return self.coordinator.last_update_success
