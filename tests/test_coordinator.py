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
        virtual_ids, wtp_ids, sbus_ids, lora_ids = _collect_device_ids(rooms)
        assert set(virtual_ids) == {10, 11, 12, 13}
        assert set(wtp_ids) == {20, 21}
        assert sbus_ids == []
        assert lora_ids == []

    def test_empty_rooms(self):
        virtual_ids, wtp_ids, sbus_ids, lora_ids = _collect_device_ids([])
        assert virtual_ids == []
        assert wtp_ids == []
        assert sbus_ids == []
        assert lora_ids == []


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
        hass.config_entries = MagicMock()
        # Suppress HA frame/ContextVar check in newer HA versions
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            coordinator = SinumCoordinator(hass, mock_client, scan_interval=30)
        return coordinator

    @pytest.mark.asyncio
    async def test_update_populates_virtual_and_wtp(self, mock_client):
        coordinator = self._make_coordinator(mock_client)
        with patch.object(coordinator, "async_set_updated_data"):
            data = await coordinator._async_update_data()

        assert 10 in data["virtual"]
        assert 20 in data["wtp"]
        assert data["sbus"] == {}
        assert data["schedules"] == FIXTURES["schedules"]
        assert coordinator.schedules == FIXTURES["schedules"]
        assert data["virtual"][10]["type"] == "thermostat"
        assert data["wtp"][20]["type"] == "temperature_sensor"

    @pytest.mark.asyncio
    async def test_full_collections_include_devices_not_assigned_to_rooms(self, mock_client):
        unassigned = {
            "id": 99,
            "name": "Unassigned Relay",
            "type": "relay_integrator",
            "state": True,
            "class": "virtual",
        }
        mock_client.get_virtual_devices = AsyncMock(
            return_value=[dict(FIXTURES["virtual_thermostat"]), unassigned]
        )
        coordinator = self._make_coordinator(mock_client)
        with patch.object(coordinator, "async_set_updated_data"):
            data = await coordinator._async_update_data()

        assert 99 in data["virtual"]
        assert data["virtual"][99]["_room"] == ""
        assert data["virtual"][99]["_device_name"] == "Unassigned Relay"
        mock_client.get_virtual_device.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_sbus_collection_is_discovered_even_without_room_reference(self, mock_client):
        mock_client.get_sbus_devices = AsyncMock(
            return_value=[dict(FIXTURES["sbus_temperature_sensor"])]
        )
        coordinator = self._make_coordinator(mock_client)
        with patch.object(coordinator, "async_set_updated_data"):
            data = await coordinator._async_update_data()

        assert 30 in data["sbus"]
        assert data["sbus"][30]["type"] == "temperature_sensor"

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
    async def test_update_raises_on_hub_info_failure_with_no_cache(self, mock_client):
        """Hub unreachable (hub info fails, no cache) raises UpdateFailed."""
        from homeassistant.helpers.update_coordinator import UpdateFailed
        mock_client.get_hub_info = AsyncMock(
            side_effect=SinumConnectionError("hub unreachable")
        )
        coordinator = self._make_coordinator(mock_client)
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_update_uses_cached_rooms_on_408(self, mock_client):
        """When rooms returns 408 but cache exists, coordinator continues with cached rooms."""
        from homeassistant.helpers.update_coordinator import UpdateFailed
        coordinator = self._make_coordinator(mock_client)
        # Populate cache on first successful call
        with patch.object(coordinator, "async_set_updated_data"):
            await coordinator._async_update_data()
        assert coordinator.rooms  # cache populated

        # Now rooms endpoint times out (408 → SinumConnectionError)
        mock_client.get_rooms = AsyncMock(
            side_effect=SinumConnectionError("Hub internal timeout (bus may be busy)")
        )
        with patch.object(coordinator, "async_set_updated_data"):
            data = await coordinator._async_update_data()

        # Should not raise — uses cached rooms
        assert 10 in data["virtual"]

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

    @pytest.mark.asyncio
    async def test_bulk_fetch_failure_returns_cached_data(self, mock_client):
        """When bulk collection endpoint fails, cached devices are preserved."""
        coordinator = self._make_coordinator(mock_client)
        # Prime the cache with a successful fetch
        with patch.object(coordinator, "async_set_updated_data"):
            await coordinator._async_update_data()
        assert coordinator.virtual_devices  # cache populated

        # Now the bulk endpoint goes down
        mock_client.get_virtual_devices = AsyncMock(
            side_effect=SinumConnectionError("connection refused")
        )
        mock_client.get_wtp_devices = AsyncMock(
            side_effect=SinumConnectionError("connection refused")
        )
        mock_client.get_sbus_devices = AsyncMock(
            side_effect=SinumConnectionError("connection refused")
        )
        with patch.object(coordinator, "async_set_updated_data"):
            data = await coordinator._async_update_data()

        # Cached data is preserved — entities remain available
        assert 10 in data["virtual"]
        assert coordinator.virtual_devices is data["virtual"]
