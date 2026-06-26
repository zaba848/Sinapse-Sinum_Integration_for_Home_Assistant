"""Sinum camera platform — snapshot proxy via hub API.

Each IP/ONVIF camera configured in the Sinum hub is exposed as a HA camera
entity. Snapshots are fetched through the hub's /api/v1/devices/video/{id}/snapshot
endpoint (returns JPEG decoded from base64). RTSP passwords are masked by the
hub API so live streaming is not available; use HA's Generic Camera integration
with direct RTSP credentials if streaming is required.

Supported camera types: ip_camera (rtsp), onvif_camera (onvif).
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SinumConfigEntry
from .coordinator import SinumCoordinator

PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)

_VIDEO_STATUS_ONLINE = "online"
_VIDEO_STATUS_OFFLINE = "offline"

_CAMERA_BASE_KEYS = (
    ("video_type", "video_type"),
    ("ip", "ip"),
    ("port", "port"),
    ("url", "url_path"),
    ("mac", "mac"),
    ("status", "status"),
    ("purpose", "purpose"),
    ("room_id", "room_id"),
)


def _camera_base_attrs(dev: dict[str, Any]) -> dict[str, Any]:
    return {attr: dev[key] for key, attr in _CAMERA_BASE_KEYS if dev.get(key) is not None}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SinumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SinumCoordinator = entry.runtime_data
    entities = [
        SinumCamera(coordinator, device_id, entry.entry_id)
        for device_id in coordinator.video_devices
    ]
    if entities:
        _LOGGER.debug("Setting up %d Sinum camera entities", len(entities))
    async_add_entities(entities)


class SinumCamera(Camera):
    """Represents a single IP/ONVIF camera configured in the Sinum hub.

    Snapshots are fetched through the hub's snapshot proxy endpoint.
    """

    _attr_has_entity_name = True
    _attr_supported_features = CameraEntityFeature(0)

    def __init__(
        self,
        coordinator: SinumCoordinator,
        device_id: int,
        entry_id: str,
    ) -> None:
        super().__init__()
        self._coordinator = coordinator
        self._device_id = device_id
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_video_{device_id}"

    @property
    def _device(self) -> dict[str, Any]:
        return self._coordinator.video_devices.get(self._device_id, {})

    @property
    def name(self) -> str:
        return self._device.get("name", f"Camera {self._device_id}")

    @property
    def is_on(self) -> bool:
        return self._device.get("status") == _VIDEO_STATUS_ONLINE

    @property
    def is_recording(self) -> bool:
        return False

    @property
    def brand(self) -> str | None:
        variant = self._device.get("variant")
        if variant and variant != "generic":
            return variant
        return None

    @property
    def model(self) -> str | None:
        return self._device.get("type")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        dev = self._device
        attrs = _camera_base_attrs(dev)
        if dev.get("url2"):
            attrs["url2_path"] = dev["url2"]
        if dev.get("url3"):
            attrs["url3_path"] = dev["url3"]
        return attrs

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return JPEG snapshot from hub proxy endpoint."""
        try:
            return await self._coordinator.client.get_video_snapshot(self._device_id)
        except Exception as exc:
            _LOGGER.debug("Snapshot failed for camera %d: %s", self._device_id, exc)
            return None

    @property
    def device_info(self) -> dict[str, Any]:
        dev = self._device
        info: dict[str, Any] = {
            "identifiers": {("sinum", f"{self._entry_id}_video_{self._device_id}")},
            "name": dev.get("name", f"Sinum Camera {self._device_id}"),
            "manufacturer": "Sinum",
            "model": dev.get("type", "ip_camera"),
        }
        if dev.get("mac"):
            info["connections"] = {("mac", dev["mac"])}
        return info
