"""Tests for Sinum alarm control panel."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.alarm_control_panel import AlarmControlPanelState

from custom_components.sinum.alarm_control_panel import SinumAlarmZone, async_setup_entry
from custom_components.sinum.api import SinumConnectionError


def _make_zone(zone_id=1, zone_status="disarmed", violated=False, armed=False, **kwargs):
    return {
        "id": zone_id,
        "name": f"Zone {zone_id}",
        "type": "alarm_zone",
        "zone_status": zone_status,
        "armed": armed,
        "violated": violated,
        "enter_time_delay": 15,
        "exit_time_delay": 15,
        "associations": {"inputs": [{"class": "sbus", "id": 10}]},
        **kwargs,
    }


def _make_entity(zone_data, alarm_zones=None):
    coordinator = MagicMock()
    zones = alarm_zones if alarm_zones is not None else {zone_data["id"]: zone_data}
    coordinator.alarm_zones = zones
    entity = SinumAlarmZone(coordinator, zone_data, "test_entry")
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    return entity


class TestAlarmSetup:
    @pytest.mark.asyncio
    async def test_empty_endpoint_adds_no_entities(self):
        coordinator = MagicMock()
        coordinator.client.get_alarm_devices = AsyncMock(return_value=[])
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "test_entry"
        async_add_entities = MagicMock()

        await async_setup_entry(MagicMock(), entry, async_add_entities)

        async_add_entities.assert_called_once_with([])

    @pytest.mark.asyncio
    async def test_connection_error_adds_no_entities(self):
        coordinator = MagicMock()
        coordinator.client.get_alarm_devices = AsyncMock(side_effect=SinumConnectionError("err"))
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "test_entry"
        async_add_entities = MagicMock()

        await async_setup_entry(MagicMock(), entry, async_add_entities)

        # async_add_entities is called with empty list (no entities registered)
        added = async_add_entities.call_args[0][0] if async_add_entities.called else []
        assert added == []

    @pytest.mark.asyncio
    async def test_two_zones_create_two_entities(self):
        coordinator = MagicMock()
        coordinator.client.get_alarm_devices = AsyncMock(
            return_value=[_make_zone(1), _make_zone(2, zone_status="armed", armed=True)]
        )
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "test_entry"
        added = []
        async_add_entities = MagicMock(side_effect=lambda e: added.extend(e))

        await async_setup_entry(MagicMock(), entry, async_add_entities)

        assert len(added) == 2
        assert sorted(coordinator.alarm_zones) == [1, 2]

    @pytest.mark.asyncio
    async def test_cached_zones_are_used_without_second_endpoint_fetch(self):
        coordinator = MagicMock()
        coordinator.alarm_zones = {1: _make_zone(1)}
        coordinator.client.get_alarm_devices = AsyncMock(
            side_effect=SinumConnectionError("transient")
        )
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "test_entry"
        added = []
        async_add_entities = MagicMock(side_effect=lambda e: added.extend(e))

        await async_setup_entry(MagicMock(), entry, async_add_entities)

        assert len(added) == 1
        coordinator.client.get_alarm_devices.assert_not_awaited()


class TestAlarmZoneState:
    def test_disarmed_state(self):
        zone = _make_zone(zone_status="disarmed", violated=False)
        entity = _make_entity(zone)
        assert entity.alarm_state == AlarmControlPanelState.DISARMED

    def test_armed_state_maps_to_armed_away(self):
        zone = _make_zone(zone_status="armed", armed=True)
        entity = _make_entity(zone)
        assert entity.alarm_state == AlarmControlPanelState.ARMED_AWAY

    def test_violated_state_maps_to_triggered(self):
        zone = _make_zone(zone_status="armed", armed=True, violated=True)
        entity = _make_entity(zone)
        assert entity.alarm_state == AlarmControlPanelState.TRIGGERED

    def test_violated_overrides_armed_status(self):
        # Even if zone_status is "disarmed" but violated, show TRIGGERED
        zone = _make_zone(zone_status="disarmed", violated=True)
        entity = _make_entity(zone)
        assert entity.alarm_state == AlarmControlPanelState.TRIGGERED

    def test_missing_zone_returns_disarmed(self):
        zone = _make_zone(zone_id=99)
        entity = _make_entity(zone, alarm_zones={})  # zone not in coordinator
        assert entity.alarm_state == AlarmControlPanelState.DISARMED

    def test_unknown_zone_status_returns_disarmed(self):
        zone = _make_zone(zone_status="unknown_future_state")
        entity = _make_entity(zone)
        assert entity.alarm_state == AlarmControlPanelState.DISARMED


class TestAlarmZoneAttributes:
    def test_extra_attributes_contain_delays(self):
        zone = _make_zone(zone_status="disarmed")
        entity = _make_entity(zone)
        attrs = entity.extra_state_attributes
        assert attrs["entry_delay_s"] == 15
        assert attrs["exit_delay_s"] == 15

    def test_extra_attributes_contain_inputs(self):
        zone = _make_zone()
        entity = _make_entity(zone)
        attrs = entity.extra_state_attributes
        assert "inputs" in attrs
        assert attrs["inputs"] == ["sbus/10"]

    def test_no_inputs_omits_key(self):
        zone = _make_zone()
        zone["associations"] = {"inputs": []}
        entity = _make_entity(zone)
        assert "inputs" not in entity.extra_state_attributes

    def test_missing_delays_omit_keys(self):
        zone = _make_zone()
        zone.pop("enter_time_delay")
        zone.pop("exit_time_delay")
        entity = _make_entity(zone)
        attrs = entity.extra_state_attributes
        assert "entry_delay_s" not in attrs
        assert "exit_delay_s" not in attrs


class TestAlarmZoneIdentity:
    def test_unique_id(self):
        zone = _make_zone(zone_id=5)
        entity = _make_entity(zone)
        assert entity.unique_id == "test_entry_alarm_5"

    def test_no_supported_features(self):
        from homeassistant.components.alarm_control_panel import AlarmControlPanelEntityFeature

        zone = _make_zone()
        entity = _make_entity(zone)
        expected = (
            AlarmControlPanelEntityFeature.ARM_AWAY
            | AlarmControlPanelEntityFeature.ARM_HOME
            | AlarmControlPanelEntityFeature.ARM_NIGHT
        )
        assert entity.supported_features == expected

    def test_coordinator_update_writes_state(self):
        zone = _make_zone()
        entity = _make_entity(zone)
        entity._handle_coordinator_update()
        entity.async_write_ha_state.assert_called_once()

    def test_icon(self):
        zone = _make_zone()
        entity = _make_entity(zone)
        assert entity.icon == "mdi:shield-home"


class TestAlarmModes:
    """Test ARM_HOME, ARM_NIGHT, and ARM_AWAY modes."""

    def test_supported_features_include_all_modes(self):
        from homeassistant.components.alarm_control_panel import AlarmControlPanelEntityFeature

        zone = _make_zone()
        entity = _make_entity(zone)
        features = entity.supported_features
        assert features & AlarmControlPanelEntityFeature.ARM_AWAY
        assert features & AlarmControlPanelEntityFeature.ARM_HOME
        assert features & AlarmControlPanelEntityFeature.ARM_NIGHT

    @pytest.mark.asyncio
    async def test_alarm_arm_away_with_mode(self):
        zone = _make_zone(zone_id=1)
        coordinator = MagicMock()
        coordinator.alarm_zones = {1: zone}
        coordinator.client.command_alarm_device = AsyncMock()
        coordinator.async_request_refresh = AsyncMock()
        entity = SinumAlarmZone(coordinator, zone, "test_entry")

        await entity.async_alarm_arm_away("1234")

        coordinator.client.command_alarm_device.assert_called_once_with(
            1, "arm", {"arm": "1234", "mode": "away"}
        )
        coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_alarm_arm_home_mode(self):
        zone = _make_zone(zone_id=1)
        coordinator = MagicMock()
        coordinator.alarm_zones = {1: zone}
        coordinator.client.command_alarm_device = AsyncMock()
        coordinator.async_request_refresh = AsyncMock()
        entity = SinumAlarmZone(coordinator, zone, "test_entry")

        await entity.async_alarm_arm_home("1234")

        coordinator.client.command_alarm_device.assert_called_once_with(
            1, "arm", {"arm": "1234", "mode": "home"}
        )
        coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_alarm_arm_night_mode(self):
        zone = _make_zone(zone_id=1)
        coordinator = MagicMock()
        coordinator.alarm_zones = {1: zone}
        coordinator.client.command_alarm_device = AsyncMock()
        coordinator.async_request_refresh = AsyncMock()
        entity = SinumAlarmZone(coordinator, zone, "test_entry")

        await entity.async_alarm_arm_night("1234")

        coordinator.client.command_alarm_device.assert_called_once_with(
            1, "arm", {"arm": "1234", "mode": "night"}
        )
        coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_alarm_arm_home_without_code_raises_error(self):
        zone = _make_zone(zone_id=1)
        entity = _make_entity(zone)
        from homeassistant.exceptions import HomeAssistantError

        with pytest.raises(HomeAssistantError, match="PIN code is required"):
            await entity.async_alarm_arm_home(None)

    @pytest.mark.asyncio
    async def test_alarm_arm_night_without_code_raises_error(self):
        zone = _make_zone(zone_id=1)
        entity = _make_entity(zone)
        from homeassistant.exceptions import HomeAssistantError

        with pytest.raises(HomeAssistantError, match="PIN code is required"):
            await entity.async_alarm_arm_night(None)

    @pytest.mark.asyncio
    async def test_alarm_arm_home_connection_error(self):
        from homeassistant.exceptions import HomeAssistantError

        zone = _make_zone(zone_id=1)
        coordinator = MagicMock()
        coordinator.alarm_zones = {1: zone}
        coordinator.client.command_alarm_device = AsyncMock(
            side_effect=SinumConnectionError("Connection lost")
        )
        entity = SinumAlarmZone(coordinator, zone, "test_entry")

        with pytest.raises(HomeAssistantError, match="Cannot arm alarm in home mode"):
            await entity.async_alarm_arm_home("1234")

    @pytest.mark.asyncio
    async def test_alarm_arm_night_connection_error(self):
        from homeassistant.exceptions import HomeAssistantError

        zone = _make_zone(zone_id=1)
        coordinator = MagicMock()
        coordinator.alarm_zones = {1: zone}
        coordinator.client.command_alarm_device = AsyncMock(
            side_effect=SinumConnectionError("Connection lost")
        )
        entity = SinumAlarmZone(coordinator, zone, "test_entry")

        with pytest.raises(HomeAssistantError, match="Cannot arm alarm in night mode"):
            await entity.async_alarm_arm_night("1234")


class TestAlarmBypass:
    """Test zone bypass and unbypass functionality."""

    @pytest.mark.asyncio
    async def test_bypass_zone(self):
        zone = _make_zone(zone_id=1)
        coordinator = MagicMock()
        coordinator.alarm_zones = {1: zone}
        coordinator.client.patch_alarm_device = AsyncMock()
        coordinator.async_request_refresh = AsyncMock()
        entity = SinumAlarmZone(coordinator, zone, "test_entry")

        await entity.async_bypass_zone("1234")

        coordinator.client.patch_alarm_device.assert_called_once_with(
            1, {"bypassed": True, "pin": "1234"}
        )
        coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_unbypass_zone(self):
        zone = _make_zone(zone_id=1)
        coordinator = MagicMock()
        coordinator.alarm_zones = {1: zone}
        coordinator.client.patch_alarm_device = AsyncMock()
        coordinator.async_request_refresh = AsyncMock()
        entity = SinumAlarmZone(coordinator, zone, "test_entry")

        await entity.async_unbypass_zone("1234")

        coordinator.client.patch_alarm_device.assert_called_once_with(
            1, {"bypassed": False, "pin": "1234"}
        )
        coordinator.async_request_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_bypass_zone_without_code_raises_error(self):
        from homeassistant.exceptions import HomeAssistantError

        zone = _make_zone(zone_id=1)
        entity = _make_entity(zone)

        with pytest.raises(HomeAssistantError, match="PIN code is required to bypass zone"):
            await entity.async_bypass_zone(None)

    @pytest.mark.asyncio
    async def test_bypass_zone_connection_error(self):
        from homeassistant.exceptions import HomeAssistantError

        zone = _make_zone(zone_id=1)
        coordinator = MagicMock()
        coordinator.alarm_zones = {1: zone}
        coordinator.client.patch_alarm_device = AsyncMock(
            side_effect=SinumConnectionError("Connection lost")
        )
        entity = SinumAlarmZone(coordinator, zone, "test_entry")

        with pytest.raises(HomeAssistantError, match="Cannot bypass zone"):
            await entity.async_bypass_zone("1234")

    @pytest.mark.asyncio
    async def test_unbypass_zone_without_code_raises_error(self):
        from homeassistant.exceptions import HomeAssistantError

        zone = _make_zone(zone_id=1)
        entity = _make_entity(zone)

        with pytest.raises(HomeAssistantError, match="PIN code is required to unbypass zone"):
            await entity.async_unbypass_zone(None)

    @pytest.mark.asyncio
    async def test_unbypass_zone_connection_error(self):
        from homeassistant.exceptions import HomeAssistantError

        zone = _make_zone(zone_id=1)
        coordinator = MagicMock()
        coordinator.alarm_zones = {1: zone}
        coordinator.client.patch_alarm_device = AsyncMock(
            side_effect=SinumConnectionError("Connection lost")
        )
        entity = SinumAlarmZone(coordinator, zone, "test_entry")

        with pytest.raises(HomeAssistantError, match="Cannot unbypass zone"):
            await entity.async_unbypass_zone("1234")

    def test_attributes_with_armed_mode(self):
        zone = _make_zone(zone_id=1, armed_mode="home")
        entity = _make_entity(zone)
        attrs = entity.extra_state_attributes
        assert attrs.get("armed_mode") == "home"

    def test_attributes_with_bypassed_zones(self):
        zone = _make_zone(zone_id=1)
        zone["bypassed_inputs"] = [{"class": "sbus", "id": 5}, {"class": "sbus", "id": 10}]
        entity = _make_entity(zone)
        attrs = entity.extra_state_attributes
        assert "bypassed_zones" in attrs
        assert attrs["bypassed_zones"] == ["sbus/5", "sbus/10"]

    def test_no_bypassed_zones_omits_key(self):
        zone = _make_zone(zone_id=1)
        zone["bypassed_inputs"] = []
        entity = _make_entity(zone)
        attrs = entity.extra_state_attributes
        assert "bypassed_zones" not in attrs
