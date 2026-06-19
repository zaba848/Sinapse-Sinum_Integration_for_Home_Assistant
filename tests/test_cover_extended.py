"""Extended tests for cover entities (improves 60% → 80%+ coverage)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.cover import CoverDeviceClass

from custom_components.sinum.cover import (
    SinumBlindCover,
    SinumGateCover,
    SinumSbusBlindCover,
    SinumWtpBlindCover,
    async_setup_entry,
)
from custom_components.sinum.const import (
    GATE_STATE_CLOSED,
    GATE_STATE_CLOSING,
    GATE_STATE_OPENING,
    STYPE_BLIND_CONTROLLER,
    VTYPE_BLIND,
    VTYPE_GATE,
    WTYPE_BLIND_CONTROLLER,
)


def _make_coordinator(virtual_devices=None, wtp_devices=None, sbus_devices=None):
    coord = MagicMock()
    coord.virtual_devices = virtual_devices or {}
    coord.wtp_devices = wtp_devices or {}
    coord.sbus_devices = sbus_devices or {}
    return coord


def _blind_device(pos=75, tilt=None, in_progress=False):
    d = {
        "id": 13,
        "type": "blind_controller_integrator",
        "last_set_target_opening": pos,
        "action_in_progress": in_progress,
        "class": "virtual",
    }
    if tilt is not None:
        d["last_set_target_tilt"] = tilt
    return d


def _gate_device(state="open"):
    return {
        "id": 14,
        "type": "gate",
        "state": state,
        "class": "virtual",
    }


def _wtp_blind_device(current=50, target=50, in_progress=False):
    return {
        "id": 25,
        "type": "blind_controller",
        "current_opening": current,
        "target_opening": target,
        "action_in_progress": in_progress,
        "class": "wtp",
    }


def _make_blind(pos=75) -> SinumBlindCover:
    device = _blind_device(pos)
    coord = _make_coordinator(virtual_devices={13: device})
    coord.client = MagicMock()
    with patch("homeassistant.helpers.frame.report_usage", return_value=None):
        entity = SinumBlindCover(coord, 13, "test_entry")
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    return entity


def _make_gate(state="open") -> SinumGateCover:
    device = _gate_device(state)
    coord = _make_coordinator(virtual_devices={14: device})
    coord.client = MagicMock()
    with patch("homeassistant.helpers.frame.report_usage", return_value=None):
        entity = SinumGateCover(coord, 14, "test_entry")
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    return entity


def _make_wtp_blind(current=50, target=50, in_progress=False) -> SinumWtpBlindCover:
    device = _wtp_blind_device(current, target, in_progress)
    coord = _make_coordinator(wtp_devices={25: device})
    coord.client = MagicMock()
    with patch("homeassistant.helpers.frame.report_usage", return_value=None):
        entity = SinumWtpBlindCover(coord, 25, "test_entry")
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    return entity


class TestSinumBlindCover:
    def test_is_closed_at_zero(self):
        entity = _make_blind(pos=0)
        assert entity.is_closed is True

    def test_is_not_closed_when_open(self):
        entity = _make_blind(pos=75)
        assert entity.is_closed is False

    def test_is_closed_none_when_no_position(self):
        coord = _make_coordinator(virtual_devices={13: {"id": 13, "type": "blind_controller_integrator"}})
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumBlindCover(coord, 13, "test_entry")
        assert entity.is_closed is None

    def test_current_cover_position(self):
        entity = _make_blind(pos=75)
        assert entity.current_cover_position == 75

    def test_tilt_position_none_when_absent(self):
        entity = _make_blind()
        assert entity.current_cover_tilt_position is None

    def test_tilt_position_when_present(self):
        device = _blind_device(pos=50, tilt=30)
        coord = _make_coordinator(virtual_devices={13: device})
        coord.client = MagicMock()
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumBlindCover(coord, 13, "test_entry")
        assert entity.current_cover_tilt_position == 30

    def test_device_class(self):
        entity = _make_blind()
        assert entity._attr_device_class == CoverDeviceClass.BLIND

    @pytest.mark.asyncio
    async def test_open_sends_100_percent(self):
        entity = _make_blind()
        entity.coordinator.client.patch_virtual_device = AsyncMock(return_value={})
        await entity.async_open_cover()
        entity.coordinator.client.patch_virtual_device.assert_awaited_once_with(
            13, {"command": "open", "opening_percentage": 100}
        )

    @pytest.mark.asyncio
    async def test_close_sends_0_percent(self):
        entity = _make_blind()
        entity.coordinator.client.patch_virtual_device = AsyncMock(return_value={})
        await entity.async_close_cover()
        entity.coordinator.client.patch_virtual_device.assert_awaited_once_with(
            13, {"command": "open", "opening_percentage": 0}
        )

    @pytest.mark.asyncio
    async def test_stop_sends_stop_command(self):
        entity = _make_blind()
        entity.coordinator.client.patch_virtual_device = AsyncMock(return_value={})
        await entity.async_stop_cover()
        entity.coordinator.client.patch_virtual_device.assert_awaited_once_with(
            13, {"command": "stop"}
        )

    @pytest.mark.asyncio
    async def test_set_position(self):
        entity = _make_blind()
        entity.coordinator.client.patch_virtual_device = AsyncMock(return_value={})
        await entity.async_set_cover_position(position=40)
        entity.coordinator.client.patch_virtual_device.assert_awaited_once_with(
            13, {"command": "open", "opening_percentage": 40}
        )

    @pytest.mark.asyncio
    async def test_set_tilt_position(self):
        entity = _make_blind()
        entity.coordinator.client.patch_virtual_device = AsyncMock(return_value={})
        await entity.async_set_cover_tilt_position(tilt_position=25)
        entity.coordinator.client.patch_virtual_device.assert_awaited_once_with(
            13, {"command": "tilt", "tilt_percentage": 25}
        )


class TestSinumGateCover:
    def test_is_closed_when_closed_state(self):
        entity = _make_gate(state=GATE_STATE_CLOSED)
        assert entity.is_closed is True

    def test_is_not_closed_when_open_state(self):
        entity = _make_gate(state="open")
        assert entity.is_closed is False

    def test_is_none_when_no_state(self):
        coord = _make_coordinator(virtual_devices={14: {"id": 14, "type": "gate"}})
        coord.client = MagicMock()
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumGateCover(coord, 14, "test_entry")
        assert entity.is_closed is None

    def test_is_opening(self):
        entity = _make_gate(state=GATE_STATE_OPENING)
        assert entity.is_opening is True

    def test_is_closing(self):
        entity = _make_gate(state=GATE_STATE_CLOSING)
        assert entity.is_closing is True

    def test_device_class(self):
        entity = _make_gate()
        assert entity._attr_device_class == CoverDeviceClass.GATE

    @pytest.mark.asyncio
    async def test_open_sends_full_open(self):
        entity = _make_gate()
        entity.coordinator.client.patch_virtual_device = AsyncMock(return_value={})
        await entity.async_open_cover()
        entity.coordinator.client.patch_virtual_device.assert_awaited_once_with(
            14, {"command": "full_open"}
        )

    @pytest.mark.asyncio
    async def test_open_sets_state_opening_optimistically(self):
        entity = _make_gate(state="open")
        entity.coordinator.client.patch_virtual_device = AsyncMock(return_value={})
        await entity.async_open_cover()
        assert entity.coordinator.virtual_devices[14]["state"] == GATE_STATE_OPENING

    @pytest.mark.asyncio
    async def test_close_sends_close(self):
        entity = _make_gate()
        entity.coordinator.client.patch_virtual_device = AsyncMock(return_value={})
        await entity.async_close_cover()
        entity.coordinator.client.patch_virtual_device.assert_awaited_once_with(
            14, {"command": "close"}
        )

    @pytest.mark.asyncio
    async def test_close_sets_state_closing_optimistically(self):
        entity = _make_gate(state="open")
        entity.coordinator.client.patch_virtual_device = AsyncMock(return_value={})
        await entity.async_close_cover()
        assert entity.coordinator.virtual_devices[14]["state"] == GATE_STATE_CLOSING


class TestSinumWtpBlindCover:
    def test_is_closed_at_zero(self):
        entity = _make_wtp_blind(current=0)
        assert entity.is_closed is True

    def test_is_not_closed_when_open(self):
        entity = _make_wtp_blind(current=50)
        assert entity.is_closed is False

    def test_is_opening(self):
        entity = _make_wtp_blind(current=20, target=80, in_progress=True)
        assert entity.is_opening is True

    def test_is_closing(self):
        entity = _make_wtp_blind(current=80, target=20, in_progress=True)
        assert entity.is_closing is True

    def test_is_not_opening_when_no_action(self):
        entity = _make_wtp_blind(current=20, target=80, in_progress=False)
        assert entity.is_opening is False

    def test_current_cover_position(self):
        entity = _make_wtp_blind(current=65)
        assert entity.current_cover_position == 65

    def test_device_class(self):
        entity = _make_wtp_blind()
        assert entity._attr_device_class == CoverDeviceClass.BLIND

    def test_is_opening_with_invalid_values_returns_false(self):
        """Defensive: non-numeric target/current should not raise."""
        device = {
            "id": 25,
            "type": "blind_controller",
            "current_opening": "n/a",
            "target_opening": "n/a",
            "action_in_progress": True,
        }
        coord = _make_coordinator(wtp_devices={25: device})
        coord.client = MagicMock()
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumWtpBlindCover(coord, 25, "test_entry")
        assert entity.is_opening is False
        assert entity.is_closing is False

    @pytest.mark.asyncio
    async def test_open_sends_100_percent(self):
        entity = _make_wtp_blind()
        entity.coordinator.client.patch_wtp_device = AsyncMock(return_value={})
        await entity.async_open_cover()
        entity.coordinator.client.patch_wtp_device.assert_awaited_once_with(
            25, {"command": "open", "opening_percentage": 100}
        )

    @pytest.mark.asyncio
    async def test_set_position(self):
        entity = _make_wtp_blind()
        entity.coordinator.client.patch_wtp_device = AsyncMock(return_value={})
        await entity.async_set_cover_position(position=35)
        entity.coordinator.client.patch_wtp_device.assert_awaited_once_with(
            25, {"command": "open", "opening_percentage": 35}
        )

    @pytest.mark.asyncio
    async def test_close_sends_0_percent(self):
        entity = _make_wtp_blind()
        entity.coordinator.client.patch_wtp_device = AsyncMock(return_value={})
        await entity.async_close_cover()
        entity.coordinator.client.patch_wtp_device.assert_awaited_once_with(
            25, {"command": "open", "opening_percentage": 0}
        )

    @pytest.mark.asyncio
    async def test_stop_sends_stop_command(self):
        entity = _make_wtp_blind()
        entity.coordinator.client.patch_wtp_device = AsyncMock(return_value={})
        await entity.async_stop_cover()
        entity.coordinator.client.patch_wtp_device.assert_awaited_once_with(
            25, {"command": "stop"}
        )

    def test_is_closed_none_when_no_current_opening(self):
        coord = _make_coordinator(wtp_devices={25: {"id": 25, "type": "blind_controller"}})
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumWtpBlindCover(coord, 25, "test_entry")
        assert entity.is_closed is None

    def test_is_opening_false_when_target_is_none(self):
        device = {"id": 25, "current_opening": 30, "action_in_progress": True}
        coord = _make_coordinator(wtp_devices={25: device})
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumWtpBlindCover(coord, 25, "test_entry")
        assert entity.is_opening is False

    def test_is_closing_false_when_current_is_none(self):
        device = {"id": 25, "target_opening": 10, "action_in_progress": True}
        coord = _make_coordinator(wtp_devices={25: device})
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumWtpBlindCover(coord, 25, "test_entry")
        assert entity.is_closing is False


class TestSinumBlindCoverIsOpeningClosing:
    def test_is_opening_true(self):
        device = _blind_device(pos=50, in_progress=True)
        coord = _make_coordinator(virtual_devices={13: device})
        coord.client = MagicMock()
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumBlindCover(coord, 13, "test_entry")
        assert entity.is_opening is True

    def test_is_closing_true(self):
        device = _blind_device(pos=0, in_progress=True)
        coord = _make_coordinator(virtual_devices={13: device})
        coord.client = MagicMock()
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumBlindCover(coord, 13, "test_entry")
        assert entity.is_closing is True


class TestSinumGateCoverStop:
    @pytest.mark.asyncio
    async def test_stop_sends_stop(self):
        entity = _make_gate()
        entity.coordinator.client.patch_virtual_device = AsyncMock(return_value={})
        await entity.async_stop_cover()
        entity.coordinator.client.patch_virtual_device.assert_awaited_once_with(
            14, {"command": "stop"}
        )


def _make_sbus_blind(current=50, target=50, tilt=None) -> SinumSbusBlindCover:
    device: dict = {
        "id": 30,
        "type": STYPE_BLIND_CONTROLLER,
        "current_opening": current,
        "target_opening": target,
    }
    if tilt is not None:
        device["current_tilt"] = tilt
        device["target_tilt"] = tilt
    coord = _make_coordinator(sbus_devices={30: device})
    coord.client = MagicMock()
    with patch("homeassistant.helpers.frame.report_usage", return_value=None):
        entity = SinumSbusBlindCover(coord, 30, "test_entry")
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    return entity


class TestSinumSbusBlindCover:
    def test_is_closed_at_zero(self):
        entity = _make_sbus_blind(current=0)
        assert entity.is_closed is True

    def test_is_not_closed_when_open(self):
        entity = _make_sbus_blind(current=60)
        assert entity.is_closed is False

    def test_is_closed_none_when_no_position(self):
        coord = _make_coordinator(sbus_devices={30: {"id": 30}})
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumSbusBlindCover(coord, 30, "test_entry")
        assert entity.is_closed is None

    def test_is_opening_true(self):
        entity = _make_sbus_blind(current=20, target=80)
        assert entity.is_opening is True

    def test_is_closing_true(self):
        entity = _make_sbus_blind(current=80, target=20)
        assert entity.is_closing is True

    def test_is_opening_false_when_target_is_none(self):
        device = {"id": 30, "current_opening": 30}
        coord = _make_coordinator(sbus_devices={30: device})
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumSbusBlindCover(coord, 30, "test_entry")
        assert entity.is_opening is False

    def test_is_closing_false_when_current_is_none(self):
        device = {"id": 30, "target_opening": 10}
        coord = _make_coordinator(sbus_devices={30: device})
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumSbusBlindCover(coord, 30, "test_entry")
        assert entity.is_closing is False

    def test_is_opening_invalid_values_returns_false(self):
        device = {"id": 30, "current_opening": "n/a", "target_opening": "n/a"}
        coord = _make_coordinator(sbus_devices={30: device})
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            entity = SinumSbusBlindCover(coord, 30, "test_entry")
        assert entity.is_opening is False
        assert entity.is_closing is False

    def test_current_cover_position(self):
        entity = _make_sbus_blind(current=45)
        assert entity.current_cover_position == 45

    def test_current_tilt_position(self):
        entity = _make_sbus_blind(tilt=30)
        assert entity.current_cover_tilt_position == 30

    def test_tilt_position_none_when_absent(self):
        entity = _make_sbus_blind()
        assert entity.current_cover_tilt_position is None

    @pytest.mark.asyncio
    async def test_open_sends_100_percent(self):
        entity = _make_sbus_blind()
        entity.coordinator.client.patch_sbus_device = AsyncMock(return_value={})
        await entity.async_open_cover()
        entity.coordinator.client.patch_sbus_device.assert_awaited_once_with(
            30, {"command": "open", "opening_percentage": 100}
        )

    @pytest.mark.asyncio
    async def test_close_sends_0_percent(self):
        entity = _make_sbus_blind()
        entity.coordinator.client.patch_sbus_device = AsyncMock(return_value={})
        await entity.async_close_cover()
        entity.coordinator.client.patch_sbus_device.assert_awaited_once_with(
            30, {"command": "open", "opening_percentage": 0}
        )

    @pytest.mark.asyncio
    async def test_stop(self):
        entity = _make_sbus_blind()
        entity.coordinator.client.patch_sbus_device = AsyncMock(return_value={})
        await entity.async_stop_cover()
        entity.coordinator.client.patch_sbus_device.assert_awaited_once_with(
            30, {"command": "stop"}
        )

    @pytest.mark.asyncio
    async def test_set_position(self):
        entity = _make_sbus_blind()
        entity.coordinator.client.patch_sbus_device = AsyncMock(return_value={})
        await entity.async_set_cover_position(position=55)
        entity.coordinator.client.patch_sbus_device.assert_awaited_once_with(
            30, {"command": "open", "opening_percentage": 55}
        )

    @pytest.mark.asyncio
    async def test_set_tilt(self):
        entity = _make_sbus_blind()
        entity.coordinator.client.patch_sbus_device = AsyncMock(return_value={})
        await entity.async_set_cover_tilt_position(tilt_position=40)
        entity.coordinator.client.patch_sbus_device.assert_awaited_once_with(
            30, {"command": "tilt", "tilt_percentage": 40}
        )


class TestCoverAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_setup_creates_gate_and_wtp_and_sbus(self):
        coord = _make_coordinator(
            virtual_devices={
                1: {"id": 1, "type": VTYPE_BLIND},
                2: {"id": 2, "type": VTYPE_GATE},
            },
            wtp_devices={3: {"id": 3, "type": WTYPE_BLIND_CONTROLLER}},
            sbus_devices={4: {"id": 4, "type": STYPE_BLIND_CONTROLLER}},
        )
        entry = MagicMock()
        entry.runtime_data = coord
        entry.entry_id = "test_entry"

        added: list = []
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            await async_setup_entry(MagicMock(), entry, lambda entities: added.extend(entities))

        types = {type(e).__name__ for e in added}
        assert "SinumBlindCover" in types
        assert "SinumGateCover" in types
        assert "SinumWtpBlindCover" in types
        assert "SinumSbusBlindCover" in types
