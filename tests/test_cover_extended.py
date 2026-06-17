"""Extended tests for cover entities (improves 60% → 80%+ coverage)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sinum.cover import (
    SinumBlindCover,
    SinumGateCover,
    SinumWtpBlindCover,
)
from custom_components.sinum.const import GATE_STATE_CLOSING, GATE_STATE_OPENING, GATE_STATE_CLOSED


def _make_coordinator(virtual_devices=None, wtp_devices=None):
    coord = MagicMock()
    coord.virtual_devices = virtual_devices or {}
    coord.wtp_devices = wtp_devices or {}
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

    def test_icon(self):
        entity = _make_blind()
        assert entity._attr_icon == "mdi:blinds"

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

    def test_icon(self):
        entity = _make_gate()
        assert entity._attr_icon == "mdi:gate"

    @pytest.mark.asyncio
    async def test_open_sends_full_open(self):
        entity = _make_gate()
        entity.coordinator.client.patch_virtual_device = AsyncMock(return_value={})
        await entity.async_open_cover()
        entity.coordinator.client.patch_virtual_device.assert_awaited_once_with(
            14, {"command": "full_open"}
        )

    @pytest.mark.asyncio
    async def test_close_sends_close(self):
        entity = _make_gate()
        entity.coordinator.client.patch_virtual_device = AsyncMock(return_value={})
        await entity.async_close_cover()
        entity.coordinator.client.patch_virtual_device.assert_awaited_once_with(
            14, {"command": "close"}
        )


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

    def test_icon(self):
        entity = _make_wtp_blind()
        assert entity._attr_icon == "mdi:blinds-horizontal"

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
