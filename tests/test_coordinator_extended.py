"""Extended coordinator tests covering fallback paths and edge cases."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sinum.api import SinumConnectionError
from custom_components.sinum.coordinator import (
    SinumCoordinator,
    _collect_device_ids,
    _inject_room_keys,
)


class TestCoordinatorMissingPaths:
    def _make_coordinator(self, mock_client):
        hass = MagicMock()
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            return SinumCoordinator(hass, mock_client, scan_interval=30)

    @pytest.mark.asyncio
    async def test_hub_info_failure_with_cache_uses_cached(self, mock_client):
        """Hub info failure when cache is populated uses cached data (no exception)."""
        coordinator = self._make_coordinator(mock_client)
        # Prime cache
        with patch.object(coordinator, "async_set_updated_data"):
            await coordinator._async_update_data()
        assert coordinator.hub_info  # cache populated

        # Now hub info fails
        mock_client.get_hub_info = AsyncMock(side_effect=SinumConnectionError("down"))
        with patch.object(coordinator, "async_set_updated_data"):
            data = await coordinator._async_update_data()
        # Should not raise, uses cached hub_info
        assert coordinator.hub_info is not None

    @pytest.mark.asyncio
    async def test_lua_hub_info_merged_into_hub_info(self, mock_client):
        """Lua hub info fields (wifi) get merged into hub_info."""
        mock_client.get_lua_hub_info = AsyncMock(
            return_value={"wifi": {"signal": -65, "ssid": "Home"}}
        )
        coordinator = self._make_coordinator(mock_client)
        with patch.object(coordinator, "async_set_updated_data"):
            await coordinator._async_update_data()
        assert coordinator.hub_info.get("wifi", {}).get("signal") == -65

    @pytest.mark.asyncio
    async def test_lua_hub_info_failure_ignored(self, mock_client):
        """Lua hub info unavailable doesn't fail the update."""
        mock_client.get_lua_hub_info = AsyncMock(
            side_effect=SinumConnectionError("lua not installed")
        )
        coordinator = self._make_coordinator(mock_client)
        with patch.object(coordinator, "async_set_updated_data"):
            data = await coordinator._async_update_data()
        assert data is not None

    @pytest.mark.asyncio
    async def test_floors_failure_ignored(self, mock_client):
        """Floors endpoint failure doesn't fail the update."""
        mock_client.get_floors = AsyncMock(side_effect=SinumConnectionError("floors down"))
        coordinator = self._make_coordinator(mock_client)
        with patch.object(coordinator, "async_set_updated_data"):
            data = await coordinator._async_update_data()
        assert data is not None

    @pytest.mark.asyncio
    async def test_parent_devices_failure_ignored(self, mock_client):
        """Parent devices endpoint failure doesn't fail the update."""
        mock_client.get_parent_devices = AsyncMock(
            side_effect=SinumConnectionError("parent endpoint down")
        )
        coordinator = self._make_coordinator(mock_client)
        with patch.object(coordinator, "async_set_updated_data"):
            data = await coordinator._async_update_data()
        assert data is not None

    @pytest.mark.asyncio
    async def test_schedules_failure_ignored(self, mock_client):
        """Schedules endpoint failure doesn't fail the update."""
        mock_client.get_schedules = AsyncMock(side_effect=SinumConnectionError("down"))
        coordinator = self._make_coordinator(mock_client)
        with patch.object(coordinator, "async_set_updated_data"):
            data = await coordinator._async_update_data()
        assert data is not None


class TestCollectDeviceIdsEdgeCases:
    def test_skips_device_with_no_id(self):
        rooms = [{"devices": [{"class": "virtual"}]}]  # no id
        virtual_ids, wtp_ids, sbus_ids, lora_ids = _collect_device_ids(rooms)
        assert virtual_ids == []

    def test_deduplicates_same_device_in_multiple_rooms(self):
        rooms = [
            {"devices": [{"class": "virtual", "id": 10}]},
            {"devices": [{"class": "virtual", "id": 10}]},  # duplicate
        ]
        virtual_ids, _, _, _ = _collect_device_ids(rooms)
        assert virtual_ids.count(10) == 1

    def test_sbus_class_collected(self):
        rooms = [{"devices": [{"class": "sbus", "id": 50}]}]
        _, _, sbus_ids, _ = _collect_device_ids(rooms)
        assert 50 in sbus_ids

    def test_source_field_as_fallback_for_class(self):
        rooms = [{"devices": [{"source": "virtual", "id": 20}]}]
        virtual_ids, _, _, _ = _collect_device_ids(rooms)
        assert 20 in virtual_ids


class TestInjectRoomKeys:
    def test_injects_room_name_when_room_id_matches(self):
        rooms = [{"id": 1, "name": "Living Room", "devices": []}]
        floors = {}
        device = {"id": 10, "type": "thermostat", "room_id": 1}
        _inject_room_keys(device, 10, rooms, floors)
        assert device["_room"] == "Living Room"
        assert device["_id"] == 10

    def test_injects_floor_name_when_floor_found(self):
        floors = {2: {"id": 2, "name": "Ground Floor"}}
        rooms = [{"id": 1, "name": "Living Room", "floor_id": 2, "devices": []}]
        device = {"id": 10, "type": "thermostat", "room_id": 1}
        _inject_room_keys(device, 10, rooms, floors)
        assert device.get("_floor_name") == "Ground Floor"

    def test_injects_device_name_from_room_devices_list(self):
        rooms = [{"id": 1, "name": "Hall", "devices": [
            {"id": 10, "class": "virtual", "name": "Hall Thermostat"}
        ]}]
        floors = {}
        device = {"id": 10, "type": "thermostat", "class": "virtual"}
        _inject_room_keys(device, 10, rooms, floors)
        assert device.get("_device_name") == "Hall Thermostat"


class TestButtonSetupEntry:
    @pytest.mark.asyncio
    async def test_scenes_create_button_entities(self, mock_client):
        from custom_components.sinum.button import SinumSceneButton, async_setup_entry

        mock_client.get_scenes = AsyncMock(
            return_value=[{"id": 1, "name": "Evening"}, {"id": 2, "name": "Movie"}]
        )
        coordinator = MagicMock()
        coordinator.client = mock_client
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "test_entry"

        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        assert len(added) == 2
        assert all(isinstance(e, SinumSceneButton) for e in added)

    @pytest.mark.asyncio
    async def test_scenes_endpoint_unavailable_creates_no_buttons(self):
        from custom_components.sinum.button import async_setup_entry

        client = MagicMock()
        client.get_scenes = AsyncMock(side_effect=SinumConnectionError("no scenes"))
        coordinator = MagicMock()
        coordinator.client = client
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "test_entry"

        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        assert len(added) == 0
