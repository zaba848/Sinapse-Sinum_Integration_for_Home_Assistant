"""Extended coordinator tests covering fallback paths and edge cases."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sinum.api import SinumConnectionError
from custom_components.sinum.coordinator import (
    SinumCoordinator,
    _build_parent_maps,
    _collect_device_ids,
    _inject_parent_models,
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
            await coordinator._async_update_data()
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

    @pytest.mark.asyncio
    async def test_automations_stored_in_data(self, mock_client):
        """Automations endpoint is cached and returned in coordinator data."""
        mock_client.get_automations = AsyncMock(return_value=[{"id": 1, "name": "Night"}])
        coordinator = self._make_coordinator(mock_client)
        with patch.object(coordinator, "async_set_updated_data"):
            data = await coordinator._async_update_data()
        assert data["automations"] == [{"id": 1, "name": "Night"}]
        assert coordinator.automations == [{"id": 1, "name": "Night"}]

    @pytest.mark.asyncio
    async def test_automations_failure_ignored(self, mock_client):
        """Automations endpoint failure keeps coordinator update healthy."""
        mock_client.get_automations = AsyncMock(side_effect=SinumConnectionError("down"))
        coordinator = self._make_coordinator(mock_client)
        with patch.object(coordinator, "async_set_updated_data"):
            data = await coordinator._async_update_data()
        assert data is not None
        assert coordinator.automations == []


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

    def test_normalizes_string_ids_and_class_prefixes(self):
        rooms = [{"devices": [{"class": "wtp_device", "id": "42"}]}]
        _, wtp_ids, _, _ = _collect_device_ids(rooms)
        assert wtp_ids == [42]


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
        rooms = [
            {
                "id": 1,
                "name": "Hall",
                "devices": [{"id": 10, "class": "virtual", "name": "Hall Thermostat"}],
            }
        ]
        floors = {}
        device = {"id": 10, "type": "thermostat", "class": "virtual"}
        _inject_room_keys(device, 10, rooms, floors)
        assert device.get("_device_name") == "Hall Thermostat"

    def test_injects_device_name_with_source_and_string_id(self):
        rooms = [
            {
                "id": 1,
                "name": "Hall",
                "devices": [{"id": "10", "source": "wtp", "name": "Hall Sensor"}],
            }
        ]
        device = {"id": 10, "type": "temperature_sensor", "class": "wtp"}
        _inject_room_keys(device, 10, rooms, {})
        assert device.get("_device_name") == "Hall Sensor"


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
    async def test_cached_scenes_create_button_entities_without_refetch(self, mock_client):
        from custom_components.sinum.button import SinumSceneButton, async_setup_entry

        mock_client.get_scenes = AsyncMock(side_effect=SinumConnectionError("transient"))
        coordinator = MagicMock()
        coordinator.client = mock_client
        coordinator.scenes = [{"id": 1, "name": "Evening"}]
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "test_entry"

        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))

        assert len(added) == 1
        assert isinstance(added[0], SinumSceneButton)
        mock_client.get_scenes.assert_not_awaited()

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


class TestCoordinatorMissingCoverage:
    def _make_coordinator(self, mock_client):
        hass = MagicMock()
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            return SinumCoordinator(hass, mock_client, scan_interval=30)

    @pytest.mark.asyncio
    async def test_alarm_zones_connection_error_ignored(self, mock_client):
        """alarm_zones fetch SinumConnectionError → caught, not propagated."""
        mock_client.get_alarm_devices = AsyncMock(side_effect=SinumConnectionError("alarm down"))
        coordinator = self._make_coordinator(mock_client)
        with patch.object(coordinator, "async_set_updated_data"):
            data = await coordinator._async_update_data()
        assert data is not None  # did not raise

    @pytest.mark.asyncio
    async def test_device_with_no_id_skipped(self, mock_client):
        """Devices without 'id' in bulk response are silently skipped."""
        # Return a device without id in the collection
        mock_client.get_virtual_devices = AsyncMock(
            return_value=[{"type": "thermostat", "name": "No ID device"}]
        )
        coordinator = self._make_coordinator(mock_client)
        with patch.object(coordinator, "async_set_updated_data"):
            await coordinator._async_update_data()
        # Devices without id should not appear
        assert not any(
            d.get("name") == "No ID device" for d in coordinator.virtual_devices.values()
        )

    @pytest.mark.asyncio
    async def test_per_device_fallback_on_error(self, mock_client):
        """Per-device fallback: SinumConnectionError on one device is warned, others succeed."""
        # Simulate empty bulk + fallback device fetch
        mock_client.get_virtual_devices = AsyncMock(return_value=[])
        mock_client.get_virtual_device = AsyncMock(side_effect=SinumConnectionError("device gone"))
        # Populate parent_devices to trigger fallback loop
        mock_client.get_parent_devices = AsyncMock(
            return_value=[
                {
                    "id": 1,
                    "class": "virtual_parent_device",
                    "devices": [{"id": 10, "class": "virtual"}],
                }
            ]
        )
        coordinator = self._make_coordinator(mock_client)
        with patch.object(coordinator, "async_set_updated_data"):
            await coordinator._async_update_data()
        # Should not raise, device 10 simply not added

    def test_collect_device_ids_lora_class(self):
        """_collect_device_ids classifies 'lora' class devices into lora_ids."""
        parent_devices = [
            {
                "id": 99,
                "class": "lora_parent_device",
                "devices": [{"id": 10, "class": "lora"}],
            }
        ]
        _virtual_ids, _wtp_ids, _sbus_ids, lora_ids = _collect_device_ids(parent_devices)
        assert 10 in lora_ids

    @pytest.mark.asyncio
    async def test_per_device_fallback_success(self, mock_client):
        """Per-device fallback success path: item fetched and added to devices (lines 187-188)."""
        mock_client.get_virtual_devices = AsyncMock(return_value=[])
        fetched_device = {"id": 10, "class": "virtual", "type": "thermostat", "room_id": None}
        mock_client.get_virtual_device = AsyncMock(return_value=fetched_device)
        mock_client.get_parent_devices = AsyncMock(
            return_value=[
                {
                    "id": 1,
                    "class": "virtual_parent_device",
                    "devices": [{"id": 10, "class": "virtual"}],
                }
            ]
        )
        coordinator = self._make_coordinator(mock_client)
        with patch.object(coordinator, "async_set_updated_data"):
            await coordinator._async_update_data()
        assert 10 in coordinator.virtual_devices

    @pytest.mark.asyncio
    async def test_per_device_fallback_uses_parent_devices_when_rooms_empty(self, mock_client):
        """Parent-device trees provide fallback IDs when /rooms has no devices."""
        mock_client.get_rooms = AsyncMock(return_value=[])
        mock_client.get_virtual_devices = AsyncMock(return_value=[])
        mock_client.get_virtual_device = AsyncMock(
            return_value={"id": "10", "type": "thermostat", "temperature": 210}
        )
        mock_client.get_parent_devices = AsyncMock(
            return_value=[
                {
                    "id": 1,
                    "class": "virtual_parent_device",
                    "devices": [{"id": "10", "class": "virtual"}],
                }
            ]
        )
        coordinator = self._make_coordinator(mock_client)
        with patch.object(coordinator, "async_set_updated_data"):
            await coordinator._async_update_data()
        assert 10 in coordinator.virtual_devices
        assert coordinator.virtual_devices[10]["class"] == "virtual"
        mock_client.get_virtual_device.assert_awaited_once_with(10)

    @pytest.mark.asyncio
    async def test_cold_start_bulk_failure_uses_per_device_fallback(self, mock_client):
        """If a bulk endpoint fails before cache exists, fallback IDs still create entities."""
        mock_client.get_rooms = AsyncMock(return_value=[])
        mock_client.get_sbus_devices = AsyncMock(side_effect=SinumConnectionError("bus timeout"))
        mock_client.get_sbus_device = AsyncMock(
            return_value={"id": 300, "class": "sbus", "type": "rgb_controller"}
        )
        mock_client.get_parent_devices = AsyncMock(
            return_value=[
                {
                    "id": 1,
                    "class": "sbus_parent_device",
                    "devices": [{"id": 300, "class": "sbus"}],
                }
            ]
        )
        coordinator = self._make_coordinator(mock_client)
        with patch.object(coordinator, "async_set_updated_data"):
            await coordinator._async_update_data()
        assert 300 in coordinator.sbus_devices
        mock_client.get_sbus_device.assert_awaited_once_with(300)


class TestParentModelHelpers:
    """Unit tests for _build_parent_maps and _inject_parent_models helpers."""

    def test_build_parent_maps_extracts_model(self):
        parent_devices = [
            {"id": 1, "class": "sbus_parent_device", "model": "PS-06m"},
            {"id": 2, "class": "wtp_parent_device", "model": "WTP-01"},
        ]
        model_maps, _class_maps = _build_parent_maps(parent_devices)
        assert model_maps["sbus"][1] == "PS-06m"
        assert model_maps["wtp"][2] == "WTP-01"

    def test_build_parent_maps_skips_without_model(self):
        parent_devices = [{"id": 1, "class": "sbus_parent_device", "model": None}]
        model_maps, _class_maps = _build_parent_maps(parent_devices)
        assert "sbus" not in model_maps

    def test_build_parent_maps_skips_non_parent_class(self):
        parent_devices = [{"id": 1, "class": "sbus", "model": "PS-06m"}]
        model_maps, class_maps = _build_parent_maps(parent_devices)
        assert not model_maps and not class_maps

    def test_inject_parent_models_adds_field(self):
        devices = {10: {"parent_id": 1}, 11: {"parent_id": 99}}
        maps = {"sbus": {1: "PS-06m"}}
        _inject_parent_models(devices, "sbus", maps)
        assert devices[10]["_parent_model"] == "PS-06m"
        assert "_parent_model" not in devices[11]

    def test_inject_parent_models_no_op_when_empty_map(self):
        devices = {10: {"parent_id": 1}}
        _inject_parent_models(devices, "sbus", {})
        assert "_parent_model" not in devices[10]
