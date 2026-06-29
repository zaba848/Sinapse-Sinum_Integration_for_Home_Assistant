"""Tests for Sinum camera platform.

Covers:
- SinumCamera.name / is_on / brand / model
- extra_state_attributes structure
- async_camera_image calls coordinator.client.get_video_snapshot
- async_camera_image returns None on exception (no crash)
- device_info structure
- PARALLEL_UPDATES = 0
- async_setup_entry creates entities from coordinator.video_devices
- supported_features: STREAM for ip_camera/onvif_camera, 0 for others
- stream_source: builds rtsp:// URL from individual device endpoint
- stream_source: returns None when password is masked
- stream_source: returns None on API error
- CoordinatorEntity: available reflects coordinator last_update_success
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

_CAMERA_RTSP = {
    "id": 27,
    "name": "rejestrator 1",
    "type": "ip_camera",
    "video_type": "rtsp",
    "ip": "192.168.1.131",
    "port": 554,
    "url": "/ch01",
    "url2": "",
    "url3": "",
    "mac": "00:8e:5a:7e:9a:f3",
    "login": "admin",
    "password": "*******",
    "status": "online",
    "purpose": "general",
    "variant": "generic",
    "room_id": None,
    "class": "video",
}

_CAMERA_ONVIF = {
    "id": 33,
    "name": "NIEE 1",
    "type": "onvif_camera",
    "video_type": "onvif",
    "ip": "192.168.1.180",
    "port": 8554,
    "url": "/ch01",
    "url2": "",
    "url3": "",
    "mac": "bc:f8:11:52:51:54",
    "login": "admin",
    "password": "*******",
    "status": "online",
    "purpose": "general",
    "variant": "hikvision",
    "room_id": 5,
    "class": "video",
}

_CAMERA_OFFLINE = {
    **_CAMERA_RTSP,
    "id": 40,
    "name": "hhhurbbur 1",
    "status": "offline",
}

_FAKE_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 100


_CAMERA_RTSP_FULL_CREDS = {
    **_CAMERA_RTSP,
    "password": "secret123",
}

_CAMERA_UNKNOWN_TYPE = {
    **_CAMERA_RTSP,
    "id": 99,
    "type": "nvr",
    "video_type": "nvr",
}


def _make_camera(device_data: dict):
    from custom_components.sinum.camera import SinumCamera

    coordinator = MagicMock()
    coordinator.video_devices = {device_data["id"]: device_data}
    coordinator.last_update_success = True
    coordinator.client.get_video_snapshot = AsyncMock(return_value=_FAKE_JPEG)
    coordinator.client.get_video_device = AsyncMock(return_value=device_data)
    entity = SinumCamera(coordinator, device_data["id"], "entry_abc")
    entity.hass = MagicMock()
    return entity


# ──────────────────────────────────────────────────────────────────────────────
# Properties
# ──────────────────────────────────────────────────────────────────────────────


class TestSinumCameraProperties:
    def test_name_is_none(self):
        cam = _make_camera(_CAMERA_RTSP)
        assert cam.name is None

    def test_name_onvif_is_none(self):
        cam = _make_camera(_CAMERA_ONVIF)
        assert cam.name is None

    def test_is_on_when_online(self):
        cam = _make_camera(_CAMERA_RTSP)
        assert cam.is_on is True

    def test_is_off_when_offline(self):
        cam = _make_camera(_CAMERA_OFFLINE)
        assert cam.is_on is False

    def test_brand_generic_is_none(self):
        cam = _make_camera(_CAMERA_RTSP)
        assert cam.brand is None

    def test_brand_non_generic(self):
        cam = _make_camera(_CAMERA_ONVIF)
        assert cam.brand == "hikvision"

    def test_model_ip_camera(self):
        cam = _make_camera(_CAMERA_RTSP)
        assert cam.model == "ip_camera"

    def test_model_onvif(self):
        cam = _make_camera(_CAMERA_ONVIF)
        assert cam.model == "onvif_camera"

    def test_unique_id(self):
        cam = _make_camera(_CAMERA_RTSP)
        assert cam.unique_id == "entry_abc_video_27"

    def test_is_recording_always_false(self):
        cam = _make_camera(_CAMERA_RTSP)
        assert cam.is_recording is False


# ──────────────────────────────────────────────────────────────────────────────
# Extra state attributes
# ──────────────────────────────────────────────────────────────────────────────


class TestSinumCameraAttributes:
    def test_has_video_type(self):
        attrs = _make_camera(_CAMERA_RTSP).extra_state_attributes
        assert attrs["video_type"] == "rtsp"

    def test_has_ip(self):
        attrs = _make_camera(_CAMERA_RTSP).extra_state_attributes
        assert attrs["ip"] == "192.168.1.131"

    def test_has_port(self):
        attrs = _make_camera(_CAMERA_RTSP).extra_state_attributes
        assert attrs["port"] == 554

    def test_has_url_path(self):
        attrs = _make_camera(_CAMERA_RTSP).extra_state_attributes
        assert attrs["url_path"] == "/ch01"

    def test_has_mac(self):
        attrs = _make_camera(_CAMERA_RTSP).extra_state_attributes
        assert attrs["mac"] == "00:8e:5a:7e:9a:f3"

    def test_status_online(self):
        attrs = _make_camera(_CAMERA_RTSP).extra_state_attributes
        assert attrs["status"] == "online"

    def test_no_password_exposed(self):
        attrs = _make_camera(_CAMERA_RTSP).extra_state_attributes
        assert "password" not in attrs
        assert "login" not in attrs

    def test_room_id_none_excluded(self):
        cam = _make_camera(_CAMERA_RTSP)
        assert "room_id" not in cam.extra_state_attributes

    def test_room_id_present_when_set(self):
        cam = _make_camera(_CAMERA_ONVIF)
        assert cam.extra_state_attributes["room_id"] == 5

    def test_empty_url2_excluded(self):
        attrs = _make_camera(_CAMERA_RTSP).extra_state_attributes
        assert "url2_path" not in attrs

    def test_url2_present_when_set(self):
        d = {**_CAMERA_RTSP, "url2": "/ch02"}
        attrs = _make_camera(d).extra_state_attributes
        assert attrs["url2_path"] == "/ch02"

    def test_onvif_port(self):
        attrs = _make_camera(_CAMERA_ONVIF).extra_state_attributes
        assert attrs["port"] == 8554


# ──────────────────────────────────────────────────────────────────────────────
# Snapshot
# ──────────────────────────────────────────────────────────────────────────────


class TestSinumCameraSnapshot:
    @pytest.mark.asyncio
    async def test_returns_jpeg_from_hub(self):
        cam = _make_camera(_CAMERA_RTSP)
        result = await cam.async_camera_image()
        assert result == _FAKE_JPEG
        cam.coordinator.client.get_video_snapshot.assert_called_once_with(27)

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        cam = _make_camera(_CAMERA_RTSP)
        cam.coordinator.client.get_video_snapshot = AsyncMock(side_effect=Exception("timeout"))
        result = await cam.async_camera_image()
        assert result is None

    @pytest.mark.asyncio
    async def test_snapshot_uses_correct_device_id(self):
        cam = _make_camera(_CAMERA_ONVIF)
        await cam.async_camera_image()
        cam.coordinator.client.get_video_snapshot.assert_called_once_with(33)


# ──────────────────────────────────────────────────────────────────────────────
# Device info
# ──────────────────────────────────────────────────────────────────────────────


class TestSinumCameraDeviceInfo:
    def test_identifiers(self):
        cam = _make_camera(_CAMERA_RTSP)
        info = cam.device_info
        assert ("sinum", "entry_abc_video_27") in info["identifiers"]

    def test_name(self):
        cam = _make_camera(_CAMERA_RTSP)
        assert cam.device_info["name"] == "rejestrator 1"

    def test_model(self):
        cam = _make_camera(_CAMERA_RTSP)
        assert cam.device_info["model"] == "ip_camera"

    def test_no_connections(self):
        cam = _make_camera(_CAMERA_RTSP)
        assert "connections" not in cam.device_info


# ──────────────────────────────────────────────────────────────────────────────
# Platform setup
# ──────────────────────────────────────────────────────────────────────────────


class TestCameraSetup:
    @pytest.mark.asyncio
    async def test_creates_entities_for_all_video_devices(self):
        from custom_components.sinum.camera import async_setup_entry

        coordinator = MagicMock()
        coordinator.video_devices = {
            27: _CAMERA_RTSP,
            33: _CAMERA_ONVIF,
            40: _CAMERA_OFFLINE,
        }
        coordinator.client.get_video_snapshot = AsyncMock(return_value=_FAKE_JPEG)

        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.runtime_data = coordinator

        added = []
        await async_setup_entry(MagicMock(), entry, lambda ents: added.extend(ents))
        assert len(added) == 3

    @pytest.mark.asyncio
    async def test_no_entities_when_no_video_devices(self):
        from custom_components.sinum.camera import async_setup_entry

        coordinator = MagicMock()
        coordinator.video_devices = {}

        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.runtime_data = coordinator

        added = []
        await async_setup_entry(MagicMock(), entry, lambda ents: added.extend(ents))
        assert len(added) == 0


# ──────────────────────────────────────────────────────────────────────────────
# PARALLEL_UPDATES
# ──────────────────────────────────────────────────────────────────────────────


class TestCameraParallelUpdates:
    def test_parallel_updates_is_zero(self):
        import custom_components.sinum.camera as cam_mod

        assert cam_mod.PARALLEL_UPDATES == 0


# ──────────────────────────────────────────────────────────────────────────────
# supported_features
# ──────────────────────────────────────────────────────────────────────────────


class TestCameraFeatures:
    def test_ip_camera_has_stream_feature(self):
        from homeassistant.components.camera import CameraEntityFeature

        cam = _make_camera(_CAMERA_RTSP)
        assert cam.supported_features & CameraEntityFeature.STREAM

    def test_onvif_camera_has_stream_feature(self):
        from homeassistant.components.camera import CameraEntityFeature

        cam = _make_camera(_CAMERA_ONVIF)
        assert cam.supported_features & CameraEntityFeature.STREAM

    def test_unknown_type_has_stream_feature(self):
        from homeassistant.components.camera import CameraEntityFeature

        cam = _make_camera(_CAMERA_UNKNOWN_TYPE)
        assert cam.supported_features & CameraEntityFeature.STREAM


# ──────────────────────────────────────────────────────────────────────────────
# stream_source
# ──────────────────────────────────────────────────────────────────────────────


class TestCameraStreamSource:
    @pytest.mark.asyncio
    async def test_returns_rtsp_url_with_credentials(self):
        cam = _make_camera(_CAMERA_RTSP)
        cam.coordinator.client.get_video_device = AsyncMock(return_value=_CAMERA_RTSP_FULL_CREDS)
        url = await cam.stream_source()
        assert url == "rtsp://admin:secret123@192.168.1.131:554/ch01"

    @pytest.mark.asyncio
    async def test_returns_none_when_password_masked(self):
        cam = _make_camera(_CAMERA_RTSP)
        cam.coordinator.client.get_video_device = AsyncMock(return_value=_CAMERA_RTSP)
        url = await cam.stream_source()
        assert url is None

    @pytest.mark.asyncio
    async def test_returns_none_on_api_error(self):
        cam = _make_camera(_CAMERA_RTSP)
        cam.coordinator.client.get_video_device = AsyncMock(
            side_effect=Exception("connection refused")
        )
        url = await cam.stream_source()
        assert url is None

    @pytest.mark.asyncio
    async def test_returns_none_for_non_streamable_type(self):
        cam = _make_camera(_CAMERA_UNKNOWN_TYPE)
        cam.coordinator.client.get_video_device = AsyncMock(
            return_value={**_CAMERA_UNKNOWN_TYPE, "password": "secret"}
        )
        url = await cam.stream_source()
        assert url is None

    @pytest.mark.asyncio
    async def test_onvif_returns_rtsp_url(self):
        cam = _make_camera(_CAMERA_ONVIF)
        cam.coordinator.client.get_video_device = AsyncMock(
            return_value={**_CAMERA_ONVIF, "password": "pass456"}
        )
        url = await cam.stream_source()
        assert url == "rtsp://admin:pass456@192.168.1.180:8554/ch01"

    @pytest.mark.asyncio
    async def test_calls_individual_device_endpoint(self):
        cam = _make_camera(_CAMERA_RTSP)
        cam.coordinator.client.get_video_device = AsyncMock(return_value=_CAMERA_RTSP)
        await cam.stream_source()
        cam.coordinator.client.get_video_device.assert_called_once_with(27)

    @pytest.mark.asyncio
    async def test_url_without_login(self):
        dev = {**_CAMERA_RTSP_FULL_CREDS, "login": ""}
        cam = _make_camera(dev)
        cam.coordinator.client.get_video_device = AsyncMock(return_value=dev)
        url = await cam.stream_source()
        assert url == "rtsp://192.168.1.131:554/ch01"


# ──────────────────────────────────────────────────────────────────────────────
# CoordinatorEntity — availability
# ──────────────────────────────────────────────────────────────────────────────


class TestCameraAvailability:
    def test_available_when_coordinator_success(self):
        cam = _make_camera(_CAMERA_RTSP)
        cam.coordinator.last_update_success = True
        assert cam.available is True

    def test_unavailable_when_coordinator_failed(self):
        cam = _make_camera(_CAMERA_RTSP)
        cam.coordinator.last_update_success = False
        assert cam.available is False


# ──────────────────────────────────────────────────────────────────────────────
# _build_rtsp_url helper
# ──────────────────────────────────────────────────────────────────────────────


class TestBuildRtspUrl:
    def test_full_credentials(self):
        from custom_components.sinum.camera import _build_rtsp_url

        dev = {"login": "admin", "password": "pass", "ip": "10.0.1.1", "port": 554, "url": "/ch01"}
        assert _build_rtsp_url(dev) == "rtsp://admin:pass@10.0.1.1:554/ch01"

    def test_masked_password_returns_none(self):
        from custom_components.sinum.camera import _build_rtsp_url

        dev = {"login": "admin", "password": "*******", "ip": "10.0.1.1", "port": 554, "url": ""}
        assert _build_rtsp_url(dev) is None

    def test_empty_password_returns_none(self):
        from custom_components.sinum.camera import _build_rtsp_url

        dev = {"login": "admin", "password": "", "ip": "10.0.1.1", "port": 554, "url": ""}
        assert _build_rtsp_url(dev) is None

    def test_missing_ip_returns_none(self):
        from custom_components.sinum.camera import _build_rtsp_url

        dev = {"login": "admin", "password": "pass", "ip": "", "port": 554, "url": ""}
        assert _build_rtsp_url(dev) is None

    def test_no_login(self):
        from custom_components.sinum.camera import _build_rtsp_url

        dev = {"login": "", "password": "pass", "ip": "10.0.1.1", "port": 8554, "url": "/stream"}
        assert _build_rtsp_url(dev) == "rtsp://10.0.1.1:8554/stream"


# ──────────────────────────────────────────────────────────────────────────────
# CoordinatorEntity live-update path — simulates WebSocket push
# ──────────────────────────────────────────────────────────────────────────────


class TestCameraLiveUpdate:
    def test_is_on_reflects_live_status_change(self):
        """Camera picks up status changes pushed by coordinator (WS path)."""
        cam = _make_camera(_CAMERA_RTSP)
        assert cam.is_on is True

        cam.coordinator.video_devices[27]["status"] = "offline"
        assert cam.is_on is False

    def test_device_info_name_reflects_live_rename(self):
        cam = _make_camera(_CAMERA_RTSP)
        assert cam.device_info["name"] == "rejestrator 1"

        cam.coordinator.video_devices[27]["name"] = "Renamed Cam"
        assert cam.device_info["name"] == "Renamed Cam"

    def test_attributes_reflect_live_ip_change(self):
        cam = _make_camera(_CAMERA_RTSP)
        assert cam.extra_state_attributes["ip"] == "192.168.1.131"

        cam.coordinator.video_devices[27]["ip"] = "10.0.50.99"
        assert cam.extra_state_attributes["ip"] == "10.0.50.99"

    def test_device_gone_from_coordinator_returns_empty(self):
        cam = _make_camera(_CAMERA_RTSP)
        del cam.coordinator.video_devices[27]
        assert cam.name is None
        assert cam.is_on is False


# ──────────────────────────────────────────────────────────────────────────────
# WebRTC
# ──────────────────────────────────────────────────────────────────────────────


class TestCameraWebRtc:
    def test_has_native_webrtc_impl(self):
        """HA detects native WebRTC by checking if method is overridden."""
        from custom_components.sinum.camera import SinumCamera
        from homeassistant.components.camera import Camera

        assert SinumCamera.async_handle_async_webrtc_offer is not Camera.async_handle_async_webrtc_offer

    def test_stream_feature_enabled(self):
        from homeassistant.components.camera import CameraEntityFeature

        cam = _make_camera(_CAMERA_RTSP)
        assert cam.supported_features & CameraEntityFeature.STREAM

    @pytest.mark.asyncio
    async def test_offer_registers_session_and_posts(self):
        cam = _make_camera(_CAMERA_RTSP)
        send_message = MagicMock()
        cam.coordinator.client.post_video_stream_offer = AsyncMock(return_value=None)

        await cam.async_handle_async_webrtc_offer("v=0\r\noffer", "sess-123", send_message)

        cam.coordinator.register_webrtc_session.assert_called_once_with("sess-123", 27, send_message)
        cam.coordinator.client.post_video_stream_offer.assert_called_once_with(27, "v=0\r\noffer", "sess-123")

    @pytest.mark.asyncio
    async def test_offer_post_failure_dispatches_error(self):
        cam = _make_camera(_CAMERA_RTSP)
        send_message = MagicMock()
        cam.coordinator.client.post_video_stream_offer = AsyncMock(side_effect=Exception("hub down"))

        await cam.async_handle_async_webrtc_offer("v=0\r\noffer", "sess-456", send_message)

        cam.coordinator.dispatch_webrtc_error.assert_called_once_with("sess-456", "post_failed", "hub down")

    @pytest.mark.asyncio
    async def test_on_candidate_forwards_to_api(self):
        cam = _make_camera(_CAMERA_RTSP)
        candidate = MagicMock()
        candidate.candidate = "candidate:1 1 udp 2113937151 192.168.1.1 54321 typ host"
        candidate.sdp_mid = "0"
        candidate.sdp_m_line_index = 0
        cam.coordinator.client.post_video_candidate = AsyncMock(return_value=None)

        await cam.async_on_webrtc_candidate("sess-123", candidate)

        cam.coordinator.client.post_video_candidate.assert_called_once_with(27, "sess-123", candidate)

    @pytest.mark.asyncio
    async def test_on_candidate_ignores_api_error(self):
        cam = _make_camera(_CAMERA_RTSP)
        candidate = MagicMock()
        cam.coordinator.client.post_video_candidate = AsyncMock(side_effect=Exception("hub down"))

        # Should not raise
        await cam.async_on_webrtc_candidate("sess-123", candidate)

    def test_close_session_delegates_to_coordinator(self):
        cam = _make_camera(_CAMERA_RTSP)
        cam.close_webrtc_session("sess-abc")
        cam.coordinator.close_webrtc_session.assert_called_once_with("sess-abc")
