"""Tests for Sinum camera platform.

Covers:
- SinumCamera.name / is_on / brand / model
- extra_state_attributes structure
- async_camera_image calls coordinator.client.get_video_snapshot
- async_camera_image returns None on exception (no crash)
- device_info structure
- PARALLEL_UPDATES = 0
- async_setup_entry creates entities from coordinator.video_devices
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


def _make_camera(device_data: dict) -> "SinumCamera":
    from custom_components.sinum.camera import SinumCamera

    coordinator = MagicMock()
    coordinator.video_devices = {device_data["id"]: device_data}
    coordinator.client.get_video_snapshot = AsyncMock(return_value=_FAKE_JPEG)
    entity = SinumCamera(coordinator, device_data["id"], "entry_abc")
    entity.hass = MagicMock()
    return entity


# ──────────────────────────────────────────────────────────────────────────────
# Properties
# ──────────────────────────────────────────────────────────────────────────────


class TestSinumCameraProperties:
    def test_name_from_device(self):
        cam = _make_camera(_CAMERA_RTSP)
        assert cam.name == "rejestrator 1"

    def test_name_onvif(self):
        cam = _make_camera(_CAMERA_ONVIF)
        assert cam.name == "NIEE 1"

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
        cam._coordinator.client.get_video_snapshot.assert_called_once_with(27)

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        cam = _make_camera(_CAMERA_RTSP)
        cam._coordinator.client.get_video_snapshot = AsyncMock(side_effect=Exception("timeout"))
        result = await cam.async_camera_image()
        assert result is None

    @pytest.mark.asyncio
    async def test_snapshot_uses_correct_device_id(self):
        cam = _make_camera(_CAMERA_ONVIF)
        await cam.async_camera_image()
        cam._coordinator.client.get_video_snapshot.assert_called_once_with(33)


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

    def test_mac_in_connections(self):
        cam = _make_camera(_CAMERA_RTSP)
        assert ("mac", "00:8e:5a:7e:9a:f3") in cam.device_info["connections"]


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
