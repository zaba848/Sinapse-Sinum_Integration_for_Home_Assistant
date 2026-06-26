"""Tests for v0.5.0 platform quality improvements:
- PARALLEL_UPDATES = 0 on all write-capable platform modules
- SinumGateCover: state inference from hub 'state' field
- SinumBlindCover: position tracking after PATCH
- SinumSbusBlindCover: tilt support detection
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "sinum_devices.json").read_text())


# ──────────────────────────────────────────────────────────────────────────────
# PARALLEL_UPDATES
# ──────────────────────────────────────────────────────────────────────────────


class TestParallelUpdates:
    """All write-capable platform modules must declare PARALLEL_UPDATES = 0."""

    def _check(self, module_name: str) -> None:
        import importlib

        mod = importlib.import_module(f"custom_components.sinum.{module_name}")
        val = getattr(mod, "PARALLEL_UPDATES", None)
        assert val == 0, f"{module_name}.PARALLEL_UPDATES should be 0, got {val!r}"

    def test_switch(self):
        self._check("switch")

    def test_climate(self):
        self._check("climate")

    def test_cover(self):
        self._check("cover")

    def test_light(self):
        self._check("light")

    def test_number(self):
        self._check("number")

    def test_alarm_control_panel(self):
        self._check("alarm_control_panel")

    def test_button(self):
        self._check("button")

    def test_sensor(self):
        self._check("sensor")

    def test_binary_sensor(self):
        self._check("binary_sensor")

    def test_event(self):
        self._check("event")


# ──────────────────────────────────────────────────────────────────────────────
# Gate cover — state from hub field
# ──────────────────────────────────────────────────────────────────────────────


def _make_gate_cover(device_data: dict[str, Any]):
    from custom_components.sinum.cover import SinumGateCover

    coordinator = MagicMock()
    coordinator.virtual_devices = {device_data["id"]: device_data}
    coordinator.client.patch_virtual_device = AsyncMock(return_value={})
    coordinator.client.get_virtual_device = AsyncMock(return_value=device_data)
    entity = SinumGateCover(coordinator, device_data["id"], "entry")
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    return entity


class TestGateCover:
    def test_closed_when_state_closed(self):
        entity = _make_gate_cover(dict(FIXTURES["virtual_gate_closed"]))
        assert entity.is_closed is True

    def test_not_closed_when_state_opening(self):
        entity = _make_gate_cover(dict(FIXTURES["virtual_gate_opening"]))
        assert entity.is_closed is False

    def test_is_opening_when_state_opening(self):
        entity = _make_gate_cover(dict(FIXTURES["virtual_gate_opening"]))
        assert entity.is_opening is True
        assert entity.is_closing is False

    def test_not_opening_when_closed(self):
        entity = _make_gate_cover(dict(FIXTURES["virtual_gate_closed"]))
        assert entity.is_opening is False

    def test_is_closing_when_state_closing(self):
        from custom_components.sinum.const import GATE_STATE_CLOSING

        d = {**FIXTURES["virtual_gate_closed"], "state": GATE_STATE_CLOSING}
        entity = _make_gate_cover(d)
        assert entity.is_closing is True
        assert entity.is_opening is False

    def test_none_when_state_absent(self):
        entity = _make_gate_cover(dict(FIXTURES["virtual_gate_no_state"]))
        assert entity.is_closed is None

    def test_device_class_is_gate(self):
        from homeassistant.components.cover import CoverDeviceClass

        entity = _make_gate_cover(dict(FIXTURES["virtual_gate_closed"]))
        assert entity.device_class == CoverDeviceClass.GATE

    @pytest.mark.asyncio
    async def test_open_sets_state_optimistically(self):
        entity = _make_gate_cover(dict(FIXTURES["virtual_gate_closed"]))
        await entity.async_open_cover()
        from custom_components.sinum.const import GATE_STATE_OPENING

        assert entity.coordinator.virtual_devices[14]["state"] == GATE_STATE_OPENING

    @pytest.mark.asyncio
    async def test_close_sets_state_optimistically(self):
        entity = _make_gate_cover(dict(FIXTURES["virtual_gate_closed"]))
        await entity.async_close_cover()
        from custom_components.sinum.const import GATE_STATE_CLOSING

        assert entity.coordinator.virtual_devices[14]["state"] == GATE_STATE_CLOSING

    @pytest.mark.asyncio
    async def test_stop_refetches_state(self):
        from custom_components.sinum.const import GATE_STATE_CLOSED

        refetched = {**FIXTURES["virtual_gate_closed"], "state": GATE_STATE_CLOSED}
        entity = _make_gate_cover(dict(FIXTURES["virtual_gate_opening"]))
        entity.coordinator.client.get_virtual_device = AsyncMock(return_value=refetched)
        await entity.async_stop_cover()
        assert entity.coordinator.virtual_devices[15]["state"] == GATE_STATE_CLOSED

    def test_unique_id(self):
        entity = _make_gate_cover(dict(FIXTURES["virtual_gate_closed"]))
        assert entity.unique_id == "entry_virtual_14"


# ──────────────────────────────────────────────────────────────────────────────
# Virtual blind — position tracking
# ──────────────────────────────────────────────────────────────────────────────


def _make_blind_cover(device_data: dict[str, Any]):
    from custom_components.sinum.cover import SinumBlindCover

    coordinator = MagicMock()
    coordinator.virtual_devices = {device_data["id"]: device_data}
    coordinator.client.patch_virtual_device = AsyncMock(return_value=device_data)
    entity = SinumBlindCover(coordinator, device_data["id"], "entry")
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    return entity


class TestVirtualBlindCover:
    def test_position_from_last_set_target_opening(self):
        entity = _make_blind_cover(dict(FIXTURES["virtual_blind"]))
        assert entity.current_cover_position == 75

    def test_tilt_from_last_set_target_tilt(self):
        entity = _make_blind_cover(dict(FIXTURES["virtual_blind"]))
        assert entity.current_cover_tilt_position == 30

    def test_is_closed_at_zero(self):
        d = {**FIXTURES["virtual_blind"], "last_set_target_opening": 0}
        entity = _make_blind_cover(d)
        assert entity.is_closed is True

    def test_is_open_at_hundred(self):
        d = {**FIXTURES["virtual_blind"], "last_set_target_opening": 100}
        entity = _make_blind_cover(d)
        assert entity.is_closed is False

    def test_position_none_when_field_absent(self):
        d = {k: v for k, v in FIXTURES["virtual_blind"].items() if k != "last_set_target_opening"}
        entity = _make_blind_cover(d)
        assert entity.current_cover_position is None

    def test_action_in_progress_is_opening(self):
        d = {**FIXTURES["virtual_blind"], "action_in_progress": True, "last_set_target_opening": 100}
        entity = _make_blind_cover(d)
        assert entity.is_opening is True
        assert entity.is_closing is False

    def test_action_in_progress_is_closing(self):
        d = {**FIXTURES["virtual_blind"], "action_in_progress": True, "last_set_target_opening": 0}
        entity = _make_blind_cover(d)
        assert entity.is_closing is True

    def test_device_class_blind(self):
        from homeassistant.components.cover import CoverDeviceClass

        entity = _make_blind_cover(dict(FIXTURES["virtual_blind"]))
        assert entity.device_class == CoverDeviceClass.BLIND

    @pytest.mark.asyncio
    async def test_set_position_patches_hub(self):
        entity = _make_blind_cover(dict(FIXTURES["virtual_blind"]))
        await entity.async_set_cover_position(position=50)
        entity.coordinator.client.patch_virtual_device.assert_called_once_with(
            13, {"command": "open", "opening_percentage": 50}
        )

    @pytest.mark.asyncio
    async def test_open_cover_sends_100(self):
        entity = _make_blind_cover(dict(FIXTURES["virtual_blind"]))
        await entity.async_open_cover()
        entity.coordinator.client.patch_virtual_device.assert_called_once_with(
            13, {"command": "open", "opening_percentage": 100}
        )

    @pytest.mark.asyncio
    async def test_close_cover_sends_0(self):
        entity = _make_blind_cover(dict(FIXTURES["virtual_blind"]))
        await entity.async_close_cover()
        entity.coordinator.client.patch_virtual_device.assert_called_once_with(
            13, {"command": "open", "opening_percentage": 0}
        )


# ──────────────────────────────────────────────────────────────────────────────
# SBUS blind — tilt detection
# ──────────────────────────────────────────────────────────────────────────────


def _make_sbus_blind(device_data: dict[str, Any]):
    from custom_components.sinum.cover import SinumSbusBlindCover

    coordinator = MagicMock()
    coordinator.sbus_devices = {device_data["id"]: device_data}
    coordinator.client.patch_sbus_device = AsyncMock(return_value=device_data)
    entity = SinumSbusBlindCover(coordinator, device_data["id"], "entry")
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    return entity


class TestSbusBlindCover:
    def test_current_position_from_hub(self):
        entity = _make_sbus_blind(dict(FIXTURES["sbus_blind_controller"]))
        assert entity.current_cover_position == 50

    def test_tilt_from_hub(self):
        entity = _make_sbus_blind(dict(FIXTURES["sbus_blind_controller"]))
        assert entity.current_cover_tilt_position == 30

    def test_supports_tilt_when_field_present(self):
        from homeassistant.components.cover import CoverEntityFeature

        entity = _make_sbus_blind(dict(FIXTURES["sbus_blind_controller"]))
        assert CoverEntityFeature.SET_TILT_POSITION in entity.supported_features

    def test_no_tilt_support_when_field_absent(self):
        from homeassistant.components.cover import CoverEntityFeature

        d = {k: v for k, v in FIXTURES["sbus_blind_controller"].items()
             if k not in ("current_tilt", "target_tilt")}
        entity = _make_sbus_blind(d)
        assert CoverEntityFeature.SET_TILT_POSITION not in entity.supported_features

    def test_is_closed_at_zero(self):
        d = {**FIXTURES["sbus_blind_controller"], "current_opening": 0}
        entity = _make_sbus_blind(d)
        assert entity.is_closed is True

    def test_position_none_when_field_absent(self):
        d = {k: v for k, v in FIXTURES["sbus_blind_controller"].items()
             if k != "current_opening"}
        entity = _make_sbus_blind(d)
        assert entity.current_cover_position is None
