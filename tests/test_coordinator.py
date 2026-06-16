"""Tests for SinumCoordinator."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sinum.api import SinumConnectionError
from custom_components.sinum.coordinator import (
    SinumCoordinator,
    _collect_device_ids,
    _device_name_in_room,
    _room_name_for_device,
)

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "sinum_devices.json").read_text()
)


class TestCollectDeviceIds:
    def test_separates_virtual_and_wtp(self):
        rooms = FIXTURES["rooms"]
        virtual_ids, wtp_ids, sbus_ids = _collect_device_ids(rooms)
        assert set(virtual_ids) == {10, 11, 12, 13}
        assert set(wtp_ids) == {20, 21}
        assert sbus_ids == []

    def test_empty_rooms(self):
        virtual_ids, wtp_ids, sbus_ids = _collect_device_ids([])
        assert virtual_ids == []
        assert wtp_ids == []
        assert sbus_ids == []


class TestRoomHelpers:
    def test_room_name_for_device(self):
        rooms = FIXTURES["rooms"]
        assert _room_name_for_device(rooms, 10) == "Living Room"
        assert _room_name_for_device(rooms, 12) == "Kitchen"
        assert _room_name_for_device(rooms, 999) == ""

    def test_device_name_in_room(self):
        rooms = FIXTURES["rooms"]
        assert _device_name_in_room(rooms, 10) == "Thermostat"
        assert _device_name_in_room(rooms, 12) == "Relay"
        assert _device_name_in_room(rooms, 999) == "999"


class TestSinumCoordinator:
    def _make_coordinator(self, mock_client):
        hass = MagicMock()
        hass.loop = MagicMock()
        return SinumCoordinator(hass, mock_client, scan_interval=30)

    @pytest.mark.asyncio
    async def test_update_populates_virtual_and_wtp(self, mock_client):
        coordinator = self._make_coordinator(mock_client)
        with patch.object(coordinator, "async_set_updated_data"):
            data = await coordinator._async_update_data()

        assert 10 in data["virtual"]
        assert 20 in data["wtp"]
        assert data["sbus"] == {}
        assert data["virtual"][10]["type"] == "thermostat"
        assert data["wtp"][20]["type"] == "temperature_sensor"

    @pytest.mark.asyncio
    async def test_update_injects_room_and_name_keys(self, mock_client):
        coordinator = self._make_coordinator(mock_client)
        with patch.object(coordinator, "async_set_updated_data"):
            await coordinator._async_update_data()

        thermostat = coordinator.virtual_devices[10]
        assert thermostat["_room"] == "Living Room"
        assert thermostat["_device_name"] == "Thermostat"
        assert thermostat["_id"] == 10

    @pytest.mark.asyncio
    async def test_update_raises_on_room_failure(self, mock_client):
        from homeassistant.helpers.update_coordinator import UpdateFailed
        mock_client.get_rooms = AsyncMock(
            side_effect=SinumConnectionError("hub unreachable")
        )
        coordinator = self._make_coordinator(mock_client)
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_single_device_failure_does_not_abort(self, mock_client):
        mock_client.get_virtual_devices = AsyncMock(return_value=[])
        mock_client.get_virtual_device = AsyncMock(
            side_effect=SinumConnectionError("bad device")
        )
        coordinator = self._make_coordinator(mock_client)
        with patch.object(coordinator, "async_set_updated_data"):
            data = await coordinator._async_update_data()
        # Virtual devices failed but coordinator returned empty dict, not exception
        assert data["virtual"] == {}
