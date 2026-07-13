"""Sinum camera platform — snapshot proxy + WebRTC live stream via hub.

Each IP/ONVIF camera configured in the Sinum hub is exposed as a HA camera
entity. Snapshots are fetched through the hub's /api/v1/devices/video/{id}/snapshot
endpoint (returns JPEG decoded from base64).

Live streaming uses WebRTC signaling: SDP offer is forwarded to the hub via
POST /api/v1/devices/video/{id}/stream; the hub's go2rtc server returns an
SDP answer and trickle ICE candidates via WebSocket. ICE candidates from the
browser are also forwarded back to the hub.

Supported camera types: ip_camera (rtsp), onvif_camera (onvif).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.components.camera.const import StreamType
from homeassistant.components.camera.webrtc import (
    CameraWebRTCProvider,
    async_register_webrtc_provider,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SinumConfigEntry
from .const import DOMAIN
from .coordinator import SinumCoordinator, hub_prefixed_name

if TYPE_CHECKING:
    from homeassistant.components.camera.webrtc import WebRTCSendMessage
    from webrtc_models import RTCIceCandidateInit

PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)

_VIDEO_STATUS_ONLINE = "online"
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


class SinumWebRTCProvider(CameraWebRTCProvider):
    """Routes WebRTC signaling through the Sinum hub's go2rtc server.

    Registered as a provider (instead of native camera override) so that
    cameras expose both HLS and WebRTC stream types in their capabilities,
    allowing playback on Chromecast and other HLS-only players.
    """

    def __init__(self, coordinator: SinumCoordinator) -> None:
        self._coordinator = coordinator

    @property
    def domain(self) -> str:
        return DOMAIN

    @callback
    def async_is_supported(self, stream_source: str) -> bool:
        from urllib.parse import urlparse

        try:
            host = urlparse(stream_source).hostname or ""
        except Exception:
            return False
        return host in self._coordinator.video_device_ips

    async def async_handle_async_webrtc_offer(
        self,
        camera: Camera,
        offer_sdp: str,
        session_id: str,
        send_message: WebRTCSendMessage,
    ) -> None:
        device_id: int | None = getattr(camera, "_device_id", None)
        if device_id is None:
            return
        self._coordinator.register_webrtc_session(session_id, device_id, send_message)
        try:
            await self._coordinator.client.post_video_stream_offer(device_id, offer_sdp, session_id)
        except Exception as exc:
            self._coordinator.dispatch_webrtc_error(session_id, "post_failed", str(exc))

    async def async_on_webrtc_candidate(
        self, session_id: str, candidate: RTCIceCandidateInit
    ) -> None:
        await self._coordinator.forward_webrtc_candidate(session_id, candidate)

    @callback
    def async_close_session(self, session_id: str) -> None:
        self._coordinator.close_webrtc_session(session_id)


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
        provider = SinumWebRTCProvider(coordinator)
        entry.async_on_unload(async_register_webrtc_provider(hass, provider))
    async_add_entities(entities)


class SinumCamera(CoordinatorEntity[SinumCoordinator], Camera):
    """Represents a single IP/ONVIF camera configured in the Sinum hub.

    Snapshots are fetched through the hub's snapshot proxy endpoint.
    Live streaming is provided via RTSP when hub returns unmasked credentials.
    """

    _attr_has_entity_name = True
    _attr_frontend_stream_type = StreamType.WEB_RTC
    _attr_use_stream_for_stills = True

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
        self._rtsp_url: str | None = None
        self._rtsp_fetched: bool = False

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.video_devices.get(self._device_id, {})

    @property
    def name(self) -> str | None:
        return None

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
        return CameraEntityFeature.STREAM

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        dev = self._device
        attrs = _camera_base_attrs(dev)
        if dev.get("url2"):
            attrs["url2_path"] = dev["url2"]
        if dev.get("url3"):
            attrs["url3_path"] = dev["url3"]
        return attrs

    async def _fetch_rtsp_url(self) -> None:
        """Fetch and cache RTSP URL from hub. No-op on API error (retry next call)."""
        try:
            dev = await self.coordinator.client.get_video_device(self._device_id)
            self._rtsp_url = _build_rtsp_url(dev)
            self._rtsp_fetched = True
        except Exception as exc:
            _LOGGER.debug("Cannot fetch camera %d credentials: %s", self._device_id, exc)

    async def stream_source(self) -> str | None:
        """Return RTSP URL for live streaming and still image generation.

        Result is cached after the first successful hub response. The cache is
        intentionally not reset on coordinator updates — RTSP credentials don't
        change at run time. Returns None on masked password or API failure.
        """
        if self._device.get("type") not in _STREAMABLE_TYPES:
            return None
        if not self._rtsp_fetched:
            await self._fetch_rtsp_url()
        if self._rtsp_url is None:
            _LOGGER.debug("Camera %d: RTSP unavailable (masked or fetch failed)", self._device_id)
        return self._rtsp_url

    async def async_camera_image(
        self,
        width: int | None = None,
        height: int | None = None,
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
        name = dev.get("name", f"Sinum Camera {self._device_id}")
        return {
            "identifiers": {(DOMAIN, f"{self._entry_id}_video_{self._device_id}")},
            "name": hub_prefixed_name(self.coordinator, name),
            "manufacturer": "Sinum",
            "model": dev.get("type", "ip_camera"),
        }
