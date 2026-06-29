"""Sinum camera platform — snapshot proxy + RTSP live stream via hub API.

Each IP/ONVIF camera configured in the Sinum hub is exposed as a HA camera
entity. Snapshots are fetched through the hub's /api/v1/devices/video/{id}/snapshot
endpoint (returns JPEG decoded from base64).

Live streaming (CameraEntityFeature.STREAM) is enabled for rtsp/onvif cameras
when the hub individual-device endpoint returns an unmasked password. HA's
internal stream proxy handles the RTSP connection — the URL is never sent to
the frontend.

Supported camera types: ip_camera (rtsp), onvif_camera (onvif).
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SinumConfigEntry
from .coordinator import SinumCoordinator

PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)

_VIDEO_STATUS_ONLINE = "online"
_VIDEO_STATUS_OFFLINE = "offline"
_MASKED_PASSWORD = "*******"

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

_STREAMABLE_TYPES = frozenset({"ip_camera", "onvif_camera"})


def _camera_base_attrs(dev: dict[str, Any]) -> dict[str, Any]:
    return {attr: dev[key] for key, attr in _CAMERA_BASE_KEYS if dev.get(key) is not None}


def _rtsp_credentials_ok(password: str) -> bool:
    return bool(password) and _MASKED_PASSWORD not in password


def _rtsp_host(dev: dict[str, Any]) -> str:
    ip = dev.get("ip", "")
    port = dev.get("port", 554)
    url_path = dev.get("url", "")
    return f"{ip}:{port}{url_path}"


def _rtsp_authority(login: str, password: str, host: str) -> str:
    if login:
        return f"{login}:{password}@{host}"
    return host


def _build_rtsp_url(dev: dict[str, Any]) -> str | None:
    """Construct rtsp://user:pass@ip:port/url from device fields.

    Returns None when password is still masked — stream not possible.
    """
    password = dev.get("password", "")
    ip = dev.get("ip", "")
    if not _rtsp_credentials_ok(password):
        return None
    if not ip:
        return None
    host = _rtsp_host(dev)
    authority = _rtsp_authority(dev.get("login", ""), password, host)
    return f"rtsp://{authority}"


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


class SinumCamera(CoordinatorEntity[SinumCoordinator], Camera):
    """Represents a single IP/ONVIF camera configured in the Sinum hub.

    Snapshots are fetched through the hub's snapshot proxy endpoint.
    Live streaming is provided via RTSP when hub returns unmasked credentials.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SinumCoordinator,
        device_id: int,
        entry_id: str,
    ) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        Camera.__init__(self)
        self._device_id = device_id
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_video_{device_id}"

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.video_devices.get(self._device_id, {})

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
    def supported_features(self) -> CameraEntityFeature:
        if self._device.get("type") in _STREAMABLE_TYPES:
            return CameraEntityFeature.STREAM
        return CameraEntityFeature(0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        dev = self._device
        attrs = _camera_base_attrs(dev)
        if dev.get("url2"):
            attrs["url2_path"] = dev["url2"]
        if dev.get("url3"):
            attrs["url3_path"] = dev["url3"]
        return attrs

    async def stream_source(self) -> str | None:
        """Return RTSP URL for live streaming, fetching full credentials from hub.

        The individual /devices/video/{id} endpoint returns an unmasked password
        unlike the list endpoint. Returns None if credentials are still masked
        (hub firmware limitation) — HA falls back to snapshot mode.
        """
        if self._device.get("type") not in _STREAMABLE_TYPES:
            return None
        try:
            dev = await self.coordinator.client.get_video_device(self._device_id)
        except Exception as exc:
            _LOGGER.debug("Cannot fetch camera %d credentials for stream: %s", self._device_id, exc)
            return None
        url = _build_rtsp_url(dev)
        if url is None:
            _LOGGER.debug("Camera %d: password masked by hub, stream unavailable", self._device_id)
        return url

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return JPEG snapshot from hub proxy endpoint."""
        try:
            return await self.coordinator.client.get_video_snapshot(self._device_id)
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
