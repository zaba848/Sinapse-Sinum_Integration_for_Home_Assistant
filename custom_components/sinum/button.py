from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SinumConfigEntry
from .api import SinumConnectionError
from .const import DOMAIN
from .coordinator import SinumCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SinumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SinumCoordinator = entry.runtime_data
    try:
        scenes = await coordinator.client.get_scenes()
    except SinumConnectionError:
        _LOGGER.debug("Scenes endpoint not available on this hub firmware")
        scenes = []

    entities = [SinumSceneButton(coordinator, scene, entry.entry_id) for scene in scenes]
    async_add_entities(entities)


class SinumSceneButton(ButtonEntity):
    """A HA button that triggers a Sinum scene/automation."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SinumCoordinator, scene: dict[str, Any], entry_id: str) -> None:
        self._coordinator = coordinator
        self._scene_id: int = scene["id"]
        scene_name: str = scene.get("name", f"Scene {self._scene_id}")
        self._attr_name = scene_name
        self._attr_unique_id = f"{entry_id}_scene_{self._scene_id}"
        self._attr_icon = "mdi:play-circle-outline"
        hub = coordinator.hub_info
        hub_name = hub.get("name") or "Sinum"
        model = hub.get("device_type") or "sinum"
        sw_version = hub.get("version")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_scenes")},
            name=f"{hub_name} Scenes",
            manufacturer="TECH Sterowniki",
            model=model,
            sw_version=sw_version,
        )

    async def async_press(self) -> None:
        await self._coordinator.client.run_scene(self._scene_id)
        _LOGGER.debug("Triggered Sinum scene %s", self._scene_id)
