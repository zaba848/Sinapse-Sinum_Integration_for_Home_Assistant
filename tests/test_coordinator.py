"""Tests for SinumCoordinator."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.sinum.api import SinumConnectionError
from custom_components.sinum.coordinator import (
    SinumCoordinator,
    SinumDeviceAvailableMixin,
    _collect_device_ids,
    _device_class,
    _device_id_as_int,
    _device_name_in_room,
    _find_room_containing_device,
    _inject_parent_model_for_device,
    _parent_id,
    _room_devices,
    _room_name_for_device,
    _source_from_label,
    _unique_ids,
    via_device_for,
)

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "sinum_devices.json").read_text())


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

    def test_skips_non_dict_rooms_and_devices(self):
        rooms = [
            "bad-room",
            {"devices": ["bad-device", {"id": "abc", "class": "wtp"}, {"id": 5, "class": "wtp"}]},
        ]
        virtual_ids, wtp_ids, sbus_ids, lora_ids = _collect_device_ids(rooms)
        assert virtual_ids == []
        assert wtp_ids == [5]
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

    def test_find_room_containing_device_skips_non_dict_values(self):
        rooms = [
            "bad-room",
            {
                "name": "Kitchen",
                "devices": ["bad-device", {"id": 12, "class": "virtual", "name": "Relay"}],
            },
        ]
        room, dev_name = _find_room_containing_device(rooms, 12, "virtual")
        assert room["name"] == "Kitchen"
        assert dev_name == "Relay"

    def test_room_helpers_skip_non_dict_values(self):
        rooms = [
            "bad-room",
            {"name": "Hall", "devices": ["bad-device", {"id": 7, "name": "Door"}]},
        ]
        assert _room_name_for_device(rooms, 7) == "Hall"
        assert _device_name_in_room(rooms, 7) == "Door"


class TestCoordinatorHelpers:
    def test_device_id_as_int_handles_invalid_values(self):
        assert _device_id_as_int("12") == 12
        assert _device_id_as_int(None) is None
        assert _device_id_as_int("abc") is None

    def test_device_class_normalizes_prefixes(self):
        assert _device_class({"class": "virtual_device"}) == "virtual"
        assert _device_class({"class": "wtp_parent_device"}) == "wtp"
        assert _device_class({"source": "sbus_line"}) == "sbus"
        assert _device_class({"bus": "lora_net"}) == "lora"
        assert _device_class({"class": "custom_bus"}) == "custom_bus"

    def test_source_from_label_and_unique_ids(self):
        assert _source_from_label("LoRa") == "lora"
        assert _source_from_label("WTP") == "wtp"
        assert _unique_ids([1, 2, 1, 3, 2]) == [1, 2, 3]

    def test_room_devices_returns_empty_for_non_list_devices(self):
        assert tuple(_room_devices({"devices": "bad"})) == ()

    def test_parent_id_returns_none_for_invalid_value(self):
        assert _parent_id("abc") is None

    def test_inject_parent_model_for_device_skips_missing_parent_id(self):
        device = {"id": 1}
        _inject_parent_model_for_device(device, {7: "Hub X"}, {7: "wtp_parent_device"})
        assert "_parent_model" not in device
        assert "_parent_id" not in device

    def test_via_device_for_returns_parent_tuple(self):
        assert via_device_for({"_parent_class": "wtp_parent_device", "_parent_id": 5}, "entry") == (
            "sinum",
            "entry_parent_wtp_parent_device_5",
        )
        assert via_device_for({}, "entry") is None

    def test_available_mixin_uses_super_available_and_device_presence(self):
        class _Base:
            @property
            def available(self):
                return True

        class _Entity(SinumDeviceAvailableMixin, _Base):
            def __init__(self, device):
                self.__device = device

            @property
            def _device(self):
                return self.__device

        assert _Entity({"id": 1}).available is True
        assert _Entity({}).available is False

    def test_available_mixin_device_property_raises_by_default(self):
        class _Base:
            @property
            def available(self):
                return True

        class _Entity(SinumDeviceAvailableMixin, _Base):
            pass

        with pytest.raises(NotImplementedError):
            _ = _Entity()._device


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
        assert data["scenes"] == FIXTURES["scenes"]
        assert data["schedules"] == FIXTURES["schedules"]
        assert coordinator.scenes == FIXTURES["scenes"]
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

        mock_client.get_hub_info = AsyncMock(side_effect=SinumConnectionError("hub unreachable"))
        coordinator = self._make_coordinator(mock_client)
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_update_uses_cached_rooms_on_408(self, mock_client):
        """When rooms returns 408 but cache exists, coordinator continues with cached rooms."""
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
        mock_client.get_virtual_device = AsyncMock(side_effect=SinumConnectionError("bad device"))
        coordinator = self._make_coordinator(mock_client)
        with patch.object(coordinator, "async_set_updated_data"):
            data = await coordinator._async_update_data()
        # Virtual devices failed but coordinator returned empty dict, not exception
        assert data["virtual"] == {}

    def test_apply_metadata_lua_info_merged_into_hub_info(self, mock_client):
        """lua_info dict is merged into hub_info, adding fields from Lua extension."""
        coordinator = self._make_coordinator(mock_client)
        coordinator.hub_info = {"version": "1.0", "name": "Hub"}
        coordinator._apply_metadata_results(
            hub_info=None,  # no fresh hub_info (use cache)
            lua_info={"wifi": {"signal": -60, "ssid": "MyNet"}},
            rooms=None,
            floors_list=None,
            parent_devices=None,
            scenes=None,
            schedules=None,
            automations=None,
            variables=None,
        )
        assert coordinator.hub_info["wifi"]["ssid"] == "MyNet"
        assert coordinator.hub_info["version"] == "1.0"

    def test_apply_metadata_raises_when_no_hub_info_and_no_cache(self, mock_client):
        """First-call failure with empty cache → UpdateFailed (hub unreachable)."""
        coordinator = self._make_coordinator(mock_client)
        coordinator.hub_info = {}
        with pytest.raises(UpdateFailed):
            coordinator._apply_metadata_results(
                hub_info=None,
                lua_info=None,
                rooms=None,
                floors_list=None,
                parent_devices=None,
                scenes=None,
                schedules=None,
                automations=None,
                variables=None,
            )

    def test_apply_metadata_none_values_do_not_overwrite_cache(self, mock_client):
        """None fetch results must not overwrite existing cached values."""
        coordinator = self._make_coordinator(mock_client)
        coordinator.hub_info = {"name": "cached-hub"}
        coordinator.scenes = [{"id": 1}]
        coordinator.schedules = [{"id": 2}]
        coordinator._apply_metadata_results(
            hub_info=None,
            lua_info=None,
            rooms=None,
            floors_list=None,
            parent_devices=None,
            scenes=None,
            schedules=None,
            automations=None,
            variables=None,
        )
        assert coordinator.hub_info["name"] == "cached-hub"
        assert coordinator.scenes == [{"id": 1}]
        assert coordinator.schedules == [{"id": 2}]

    def test_apply_metadata_floors_indexed_by_id(self, mock_client):
        """floors_list → dict keyed by int floor_id for O(1) lookup."""
        coordinator = self._make_coordinator(mock_client)
        coordinator.hub_info = {"name": "Hub"}
        coordinator._apply_metadata_results(
            hub_info={"name": "Hub"},
            lua_info=None,
            rooms=[],
            floors_list=[{"id": "3", "name": "Ground", "level": 0}],
            parent_devices=None,
            scenes=None,
            schedules=None,
            automations=None,
            variables=None,
        )
        assert 3 in coordinator.floors
        assert coordinator.floors[3]["name"] == "Ground"

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

    def test_process_bulk_devices_skips_invalid_items(self, mock_client):
        coordinator = self._make_coordinator(mock_client)
        coordinator.floors = {}
        rooms = []

        devices = coordinator._process_bulk_devices(
            ["bad", {"id": "x"}, {"id": 2, "name": "Relay"}], "virtual", rooms
        )

        assert list(devices) == [2]
        assert devices[2]["class"] == "virtual"

    @pytest.mark.asyncio
    async def test_fetch_device_collection_skips_non_dict_item_fallback(self, mock_client):
        coordinator = self._make_coordinator(mock_client)

        list_getter = AsyncMock(return_value=[])
        item_getter = AsyncMock(side_effect=["bad", {"id": 8, "name": "Sensor"}])

        result = await coordinator._fetch_device_collection(
            "WTP", list_getter, item_getter, [7, 8], [], {}
        )

        assert list(result) == [8]
        assert result[8]["class"] == "wtp"

    # ── auth error surfaces as ConfigEntryAuthFailed ──────────────────────────

    @pytest.mark.asyncio
    async def test_safe_fetch_reraises_sinum_auth_error(self, mock_client):

        from custom_components.sinum.api import SinumAuthError
        from custom_components.sinum.coordinator import _safe_fetch

        async def _raises_auth():
            raise SinumAuthError("token rejected")

        with pytest.raises(SinumAuthError):
            await _safe_fetch(_raises_auth, "hub info")

    @pytest.mark.asyncio
    async def test_async_update_data_raises_config_entry_auth_failed(self, mock_client):
        from homeassistant.exceptions import ConfigEntryAuthFailed

        from custom_components.sinum.api import SinumAuthError

        coordinator = self._make_coordinator(mock_client)
        mock_client.get_hub_info = AsyncMock(side_effect=SinumAuthError("token rejected"))

        with pytest.raises(ConfigEntryAuthFailed):
            await coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_safe_fetch_swallows_connection_error(self, mock_client):
        from custom_components.sinum.api import SinumConnectionError
        from custom_components.sinum.coordinator import _safe_fetch

        async def _raises_conn():
            raise SinumConnectionError("timeout")

        result = await _safe_fetch(_raises_conn, "rooms", default=[])
        assert result == []

    def test_inject_parent_models_sets_class_and_parent_id(self, mock_client):
        from custom_components.sinum.coordinator import _inject_parent_models

        devices = {1: {"id": 1, "parent_id": 77}}
        _inject_parent_models(
            devices,
            "wtp",
            {"wtp": {77: "Hub X"}},
            {"wtp": {77: "wtp_parent_device"}},
        )

        assert devices[1]["_parent_model"] == "Hub X"
        assert devices[1]["_parent_class"] == "wtp_parent_device"
        assert devices[1]["_parent_id"] == 77
