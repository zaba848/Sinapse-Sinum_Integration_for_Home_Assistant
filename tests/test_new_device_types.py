"""Tests for new SBUS/WTP device type entities (relay, blind, dimmer, rgb, motion)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sinum.binary_sensor import SBUS_BINARY_SENSOR_TYPES, SinumBinarySensor
from custom_components.sinum.cover import SinumWtpBlindCover
from custom_components.sinum.light import SinumBusDimmerLight, SinumBusRgbLight
from custom_components.sinum.sensor import SBUS_SENSORS, SinumSensor
from custom_components.sinum.switch import SinumBusRelaySwitch

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "sinum_devices.json").read_text()
)


def _make_coordinator(*, wtp=None, sbus=None, virtual=None):
    c = MagicMock()
    c.virtual_devices = virtual or {}
    c.wtp_devices = wtp or {}
    c.sbus_devices = sbus or {}
    c.client = MagicMock()
    c.client.patch_wtp_device = AsyncMock(return_value={})
    c.client.patch_sbus_device = AsyncMock(return_value={})
    return c


def _wire(entity):
    """Attach a mock hass and suppress async_write_ha_state for unit tests."""
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    return entity


# ── Switch (relay) ─────────────────────────────────────────────────────────────

class TestBusRelaySwitch:
    def test_sbus_relay_is_on(self):
        device = dict(FIXTURES["sbus_relay"])
        coordinator = _make_coordinator(sbus={41: device})
        entity = SinumBusRelaySwitch(coordinator, 41, "test_entry", "sbus")
        assert entity.is_on is True

    def test_sbus_relay_is_off_after_state_change(self):
        device = dict(FIXTURES["sbus_relay"])
        coordinator = _make_coordinator(sbus={41: device})
        entity = SinumBusRelaySwitch(coordinator, 41, "test_entry", "sbus")
        coordinator.sbus_devices[41]["state"] = False
        assert entity.is_on is False

    def test_wtp_relay_is_off(self):
        device = dict(FIXTURES["wtp_relay"])
        coordinator = _make_coordinator(wtp={40: device})
        entity = SinumBusRelaySwitch(coordinator, 40, "test_entry", "wtp")
        assert entity.is_on is False

    @pytest.mark.asyncio
    async def test_sbus_relay_turn_on_calls_patch(self):
        device = dict(FIXTURES["sbus_relay"])
        coordinator = _make_coordinator(sbus={41: device})
        entity = _wire(SinumBusRelaySwitch(coordinator, 41, "test_entry", "sbus"))
        await entity.async_turn_on()
        coordinator.client.patch_sbus_device.assert_called_once_with(41, {"state": True})

    @pytest.mark.asyncio
    async def test_wtp_relay_turn_off_calls_patch(self):
        device = dict(FIXTURES["wtp_relay"])
        coordinator = _make_coordinator(wtp={40: device})
        entity = _wire(SinumBusRelaySwitch(coordinator, 40, "test_entry", "wtp"))
        await entity.async_turn_off()
        coordinator.client.patch_wtp_device.assert_called_once_with(40, {"state": False})

    def test_sbus_relay_unique_id(self):
        device = dict(FIXTURES["sbus_relay"])
        coordinator = _make_coordinator(sbus={41: device})
        entity = SinumBusRelaySwitch(coordinator, 41, "entry_abc", "sbus")
        assert entity.unique_id == "entry_abc_sbus_41"


# ── Cover (WTP blind) ──────────────────────────────────────────────────────────

class TestWtpBlindCover:
    def test_position_is_75(self):
        device = dict(FIXTURES["wtp_blind"])
        coordinator = _make_coordinator(wtp={42: device})
        entity = SinumWtpBlindCover(coordinator, 42, "test_entry")
        assert entity.current_cover_position == 75

    def test_not_closed_when_open(self):
        device = dict(FIXTURES["wtp_blind"])
        coordinator = _make_coordinator(wtp={42: device})
        entity = SinumWtpBlindCover(coordinator, 42, "test_entry")
        assert entity.is_closed is False

    def test_is_closed_at_zero(self):
        device = dict(FIXTURES["wtp_blind"])
        device["current_opening"] = 0
        coordinator = _make_coordinator(wtp={42: device})
        entity = SinumWtpBlindCover(coordinator, 42, "test_entry")
        assert entity.is_closed is True

    def test_is_closed_returns_none_when_missing(self):
        coordinator = _make_coordinator(wtp={42: {"id": 42, "type": "blind_controller"}})
        entity = SinumWtpBlindCover(coordinator, 42, "test_entry")
        assert entity.is_closed is None

    def test_is_opening(self):
        device = {"id": 42, "type": "blind_controller", "current_opening": 30, "target_opening": 80, "action_in_progress": True}
        coordinator = _make_coordinator(wtp={42: device})
        entity = SinumWtpBlindCover(coordinator, 42, "test_entry")
        assert entity.is_opening is True
        assert entity.is_closing is False

    def test_is_closing(self):
        device = {"id": 42, "type": "blind_controller", "current_opening": 80, "target_opening": 10, "action_in_progress": True}
        coordinator = _make_coordinator(wtp={42: device})
        entity = SinumWtpBlindCover(coordinator, 42, "test_entry")
        assert entity.is_closing is True
        assert entity.is_opening is False

    @pytest.mark.asyncio
    async def test_open_cover_patches_100(self):
        device = dict(FIXTURES["wtp_blind"])
        coordinator = _make_coordinator(wtp={42: device})
        entity = _wire(SinumWtpBlindCover(coordinator, 42, "test_entry"))
        await entity.async_open_cover()
        coordinator.client.patch_wtp_device.assert_called_once_with(42, {"command": "open", "opening_percentage": 100})

    @pytest.mark.asyncio
    async def test_close_cover_patches_0(self):
        device = dict(FIXTURES["wtp_blind"])
        coordinator = _make_coordinator(wtp={42: device})
        entity = _wire(SinumWtpBlindCover(coordinator, 42, "test_entry"))
        await entity.async_close_cover()
        coordinator.client.patch_wtp_device.assert_called_once_with(42, {"command": "open", "opening_percentage": 0})

    @pytest.mark.asyncio
    async def test_set_position(self):
        device = dict(FIXTURES["wtp_blind"])
        coordinator = _make_coordinator(wtp={42: device})
        entity = _wire(SinumWtpBlindCover(coordinator, 42, "test_entry"))
        from homeassistant.components.cover import ATTR_POSITION
        await entity.async_set_cover_position(**{ATTR_POSITION: 45})
        coordinator.client.patch_wtp_device.assert_called_once_with(42, {"command": "open", "opening_percentage": 45})


# ── Light (SBUS/WTP dimmer) ────────────────────────────────────────────────────

class TestBusDimmerLight:
    def test_sbus_dimmer_is_on(self):
        device = dict(FIXTURES["sbus_dimmer"])
        coordinator = _make_coordinator(sbus={43: device})
        entity = SinumBusDimmerLight(coordinator, 43, "test_entry", "sbus")
        assert entity.is_on is True

    def test_sbus_dimmer_brightness_scaled(self):
        device = dict(FIXTURES["sbus_dimmer"])  # target_level=60
        coordinator = _make_coordinator(sbus={43: device})
        entity = SinumBusDimmerLight(coordinator, 43, "test_entry", "sbus")
        assert entity.brightness == round(60 / 100 * 255)

    def test_wtp_dimmer_is_off(self):
        device = dict(FIXTURES["wtp_dimmer"])
        coordinator = _make_coordinator(wtp={44: device})
        entity = SinumBusDimmerLight(coordinator, 44, "test_entry", "wtp")
        assert entity.is_on is False

    def test_brightness_none_when_missing(self):
        coordinator = _make_coordinator(sbus={43: {"id": 43, "type": "dimmer", "state": True}})
        entity = SinumBusDimmerLight(coordinator, 43, "test_entry", "sbus")
        assert entity.brightness is None

    @pytest.mark.asyncio
    async def test_sbus_turn_on_with_brightness(self):
        device = dict(FIXTURES["sbus_dimmer"])
        coordinator = _make_coordinator(sbus={43: device})
        entity = _wire(SinumBusDimmerLight(coordinator, 43, "test_entry", "sbus"))
        from homeassistant.components.light import ATTR_BRIGHTNESS
        await entity.async_turn_on(**{ATTR_BRIGHTNESS: 128})
        coordinator.client.patch_sbus_device.assert_called_once_with(43, {"state": True, "target_level": round(128 / 255 * 100)})

    @pytest.mark.asyncio
    async def test_wtp_turn_off(self):
        device = dict(FIXTURES["wtp_dimmer"])
        coordinator = _make_coordinator(wtp={44: device})
        entity = _wire(SinumBusDimmerLight(coordinator, 44, "test_entry", "wtp"))
        await entity.async_turn_off()
        coordinator.client.patch_wtp_device.assert_called_once_with(44, {"state": False})


# ── Light (SBUS RGB controller) ────────────────────────────────────────────────

class TestBusRgbLight:
    def test_sbus_rgb_is_on(self):
        device = dict(FIXTURES["sbus_rgb"])
        coordinator = _make_coordinator(sbus={45: device})
        entity = SinumBusRgbLight(coordinator, 45, "test_entry", "sbus")
        assert entity.is_on is True

    def test_sbus_rgb_exposes_color(self):
        from homeassistant.components.light import ColorMode
        device = dict(FIXTURES["sbus_rgb"])
        coordinator = _make_coordinator(sbus={45: device})
        entity = SinumBusRgbLight(coordinator, 45, "test_entry", "sbus")
        assert ColorMode.HS in entity.supported_color_modes
        assert entity.color_mode == ColorMode.HS
        assert entity.hs_color is not None

    @pytest.mark.asyncio
    async def test_sbus_rgb_turn_on_sends_color(self):
        device = dict(FIXTURES["sbus_rgb"])
        coordinator = _make_coordinator(sbus={45: device})
        coordinator.client.get_or_create_scene = AsyncMock(return_value=99)
        coordinator.client.patch_scene_lua = AsyncMock(return_value=None)
        coordinator.client.run_scene = AsyncMock(return_value=None)
        entity = _wire(SinumBusRgbLight(coordinator, 45, "test_entry", "sbus"))
        from homeassistant.components.light import ATTR_HS_COLOR
        await entity.async_turn_on(**{ATTR_HS_COLOR: (120.0, 100.0)})
        # SBUS uses Lua — verify set_color was sent with green #00FF00
        lua_code = coordinator.client.patch_scene_lua.await_args.args[1]
        assert 'set_color' in lua_code
        assert '#00FF00' in lua_code.upper()
        # REST PATCH carries only state=True (no color — hub ignores color field for rgb_controllers)
        call_args = coordinator.client.patch_sbus_device.call_args
        assert call_args[0][0] == 45
        assert call_args[0][1] == {"state": True}


# ── Binary sensor (SBUS motion) ────────────────────────────────────────────────

class TestSbusMotionSensor:
    def _motion_desc(self):
        for d in SBUS_BINARY_SENSOR_TYPES:
            if d.key == "motion":
                return d
        raise KeyError("motion")

    def test_motion_detected(self):
        device = dict(FIXTURES["sbus_motion"])  # motion_detected=True
        coordinator = MagicMock()
        coordinator.wtp_devices = {}
        coordinator.sbus_devices = {46: device}
        entity = SinumBinarySensor(coordinator, 46, self._motion_desc(), "test_entry")
        assert entity.is_on is True

    def test_no_motion(self):
        device = dict(FIXTURES["sbus_motion"])
        device["motion_detected"] = False
        coordinator = MagicMock()
        coordinator.wtp_devices = {}
        coordinator.sbus_devices = {46: device}
        entity = SinumBinarySensor(coordinator, 46, self._motion_desc(), "test_entry")
        assert entity.is_on is False


# ── Sensor (SBUS illuminance) ──────────────────────────────────────────────────

class TestSbusIlluminanceSensor:
    def _illuminance_desc(self):
        return next(d for d in SBUS_SENSORS if d.key == "illuminance")

    def test_illuminance_reads_sbus_store(self):
        device = dict(FIXTURES["sbus_light_sensor"])  # illuminance=350
        coordinator = MagicMock()
        coordinator.virtual_devices = {}
        coordinator.wtp_devices = {}
        coordinator.sbus_devices = {47: device}
        entity = SinumSensor(coordinator, 47, self._illuminance_desc(), "test_entry")
        assert entity.native_value == 350.0  # scale=1.0


# ── Virtual dimmer_rgb_integrator ──────────────────────────────────────────────

class TestVirtualDimmerRgbIntegrator:
    def test_integrator_type_creates_light_entity(self):
        """dimmer_rgb_integrator virtual type should be recognized as a light device."""
        from custom_components.sinum.light import SinumDimmerLight

        device = dict(FIXTURES["virtual_dimmer_rgb_integrator"])
        coordinator = MagicMock()
        coordinator.virtual_devices = {14: device}
        coordinator.wtp_devices = {}
        coordinator.sbus_devices = {}

        entity = SinumDimmerLight(coordinator, 14, "test_entry")
        assert entity.is_on is True
        assert entity.brightness == round(50 / 100 * 255)
