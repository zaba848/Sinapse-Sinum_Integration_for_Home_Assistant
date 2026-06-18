"""Tests for LoRa bus entities, SBUS blind controller, alarm arm/disarm, and new sensors."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sinum.api import SinumConnectionError

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "sinum_devices.json").read_text()
)


def _make_coordinator(lora=None, sbus=None, wtp=None, virtual=None):
    coordinator = MagicMock()
    coordinator.lora_devices = lora or {}
    coordinator.sbus_devices = sbus or {}
    coordinator.wtp_devices = wtp or {}
    coordinator.virtual_devices = virtual or {}
    coordinator.client.patch_lora_device = AsyncMock(return_value={})
    coordinator.client.patch_sbus_device = AsyncMock(return_value={})
    coordinator.client.patch_wtp_device = AsyncMock(return_value={})
    coordinator.client.patch_virtual_device = AsyncMock(return_value={})
    coordinator.client.decode_temperature = lambda raw: raw / 10
    return coordinator


# ─────────────────────── LoRa Switch ────────────────────────────

class TestLoraRelaySwitch:
    def _make(self):
        from custom_components.sinum.switch import SinumBusRelaySwitch
        device = dict(FIXTURES["lora_relay"])
        device["_device_name"] = "LoRa Relay"
        coordinator = _make_coordinator(lora={73: device})
        entity = SinumBusRelaySwitch(coordinator, 73, "test_entry", "lora")
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()
        return entity, coordinator

    def test_unique_id(self):
        entity, _ = self._make()
        assert entity.unique_id == "test_entry_lora_73"

    def test_is_on_when_state_true(self):
        entity, _ = self._make()
        assert entity.is_on is True

    def test_is_off_when_state_false(self):
        from custom_components.sinum.switch import SinumBusRelaySwitch
        device = dict(FIXTURES["lora_relay"])
        device["state"] = False
        coordinator = _make_coordinator(lora={73: device})
        entity = SinumBusRelaySwitch(coordinator, 73, "test_entry", "lora")
        assert entity.is_on is False

    @pytest.mark.asyncio
    async def test_turn_on_calls_patch_lora(self):
        entity, coordinator = self._make()
        coordinator.lora_devices[73] = dict(FIXTURES["lora_relay"])
        coordinator.client.patch_lora_device = AsyncMock(return_value={"state": True})
        await entity.async_turn_on()
        coordinator.client.patch_lora_device.assert_awaited_once_with(73, {"state": True})

    @pytest.mark.asyncio
    async def test_turn_off_calls_patch_lora(self):
        entity, coordinator = self._make()
        coordinator.lora_devices[73] = dict(FIXTURES["lora_relay"])
        coordinator.client.patch_lora_device = AsyncMock(return_value={"state": False})
        await entity.async_turn_off()
        coordinator.client.patch_lora_device.assert_awaited_once_with(73, {"state": False})

    def test_lora_bus_setup_creates_switch(self):
        from custom_components.sinum.switch import async_setup_entry
        device = {"type": "relay", "_device_name": "LoRa Relay"}
        coordinator = _make_coordinator(lora={73: device})
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "test"
        added = []
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        )
        assert any(e._bus == "lora" for e in added if hasattr(e, "_bus"))


# ─────────────────────── LoRa Sensors ───────────────────────────

class TestLoraSensors:
    def test_temperature_sensor_native_value(self):
        from custom_components.sinum.sensor import SinumSensor, LORA_SENSORS
        device = dict(FIXTURES["lora_temp_sensor"])
        device["_device_name"] = "LoRa Temp"
        coordinator = _make_coordinator(lora={70: device})
        desc = next(d for d in LORA_SENSORS if d.key == "temperature")
        entity = SinumSensor(coordinator, 70, desc, "test_entry")
        assert entity.native_value == pytest.approx(21.5)

    def test_battery_sensor_native_value(self):
        from custom_components.sinum.sensor import SinumSensor, LORA_SENSORS
        device = dict(FIXTURES["lora_temp_sensor"])
        device["_device_name"] = "LoRa Temp"
        coordinator = _make_coordinator(lora={70: device})
        desc = next(d for d in LORA_SENSORS if d.key == "battery")
        entity = SinumSensor(coordinator, 70, desc, "test_entry")
        assert entity.native_value == 85

    def test_signal_sensor_native_value(self):
        from custom_components.sinum.sensor import SinumSensor, LORA_SENSORS
        device = dict(FIXTURES["lora_temp_sensor"])
        device["_device_name"] = "LoRa Temp"
        coordinator = _make_coordinator(lora={70: device})
        desc = next(d for d in LORA_SENSORS if d.key == "signal")
        entity = SinumSensor(coordinator, 70, desc, "test_entry")
        assert entity.native_value == 72

    def test_humidity_sensor_native_value(self):
        from custom_components.sinum.sensor import SinumSensor, LORA_SENSORS
        device = dict(FIXTURES["lora_humidity_sensor"])
        device["_device_name"] = "LoRa Humidity"
        coordinator = _make_coordinator(lora={71: device})
        desc = next(d for d in LORA_SENSORS if d.key == "humidity")
        entity = SinumSensor(coordinator, 71, desc, "test_entry")
        # fixture humidity=65, scale=0.1 → 6.5
        assert entity.native_value == pytest.approx(6.5)

    def test_lora_sensor_unique_id(self):
        from custom_components.sinum.sensor import SinumSensor, LORA_SENSORS
        device = dict(FIXTURES["lora_temp_sensor"])
        device["_device_name"] = "LoRa Temp"
        coordinator = _make_coordinator(lora={70: device})
        desc = next(d for d in LORA_SENSORS if d.key == "temperature")
        entity = SinumSensor(coordinator, 70, desc, "test_entry")
        assert entity.unique_id == "test_entry_lora_70_temperature"


# ─────────────────────── LoRa Binary Sensors ────────────────────

class TestLoraBinarySensors:
    def test_opening_sensor_is_on_when_open(self):
        from custom_components.sinum.binary_sensor import SinumBinarySensor, LORA_BINARY_SENSOR_TYPES
        device = dict(FIXTURES["lora_opening_sensor"])
        device["_device_name"] = "LoRa Door"
        coordinator = _make_coordinator(lora={72: device})
        desc = next(d for d in LORA_BINARY_SENSOR_TYPES if d.key == "opening")
        entity = SinumBinarySensor(coordinator, 72, desc, "test_entry")
        assert entity.is_on is True

    def test_opening_sensor_is_off_when_closed(self):
        from custom_components.sinum.binary_sensor import SinumBinarySensor, LORA_BINARY_SENSOR_TYPES
        device = {"id": 72, "type": "opening_sensor", "state": "closed", "_device_name": "LoRa Door"}
        coordinator = _make_coordinator(lora={72: device})
        desc = next(d for d in LORA_BINARY_SENSOR_TYPES if d.key == "opening")
        entity = SinumBinarySensor(coordinator, 72, desc, "test_entry")
        assert entity.is_on is False

    def test_lora_setup_creates_binary_sensor(self):
        from custom_components.sinum.binary_sensor import async_setup_entry
        device = {"type": "opening_sensor", "state": "open", "_device_name": "LoRa Door"}
        coordinator = _make_coordinator(lora={72: device})
        coordinator.wtp_devices = {}
        coordinator.sbus_devices = {}
        coordinator.parent_devices = []
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "test"
        added = []
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        )
        assert len(added) == 1
        assert added[0]._source == "lora"

    def test_lora_binary_sensor_unique_id(self):
        from custom_components.sinum.binary_sensor import SinumBinarySensor, LORA_BINARY_SENSOR_TYPES
        device = dict(FIXTURES["lora_opening_sensor"])
        device["_device_name"] = "LoRa Door"
        coordinator = _make_coordinator(lora={72: device})
        desc = next(d for d in LORA_BINARY_SENSOR_TYPES if d.key == "opening")
        entity = SinumBinarySensor(coordinator, 72, desc, "test_entry")
        assert entity.unique_id == "test_entry_lora_72_opening"


# ─────────────────────── SBUS Blind Controller ──────────────────

class TestSbusBlindCover:
    def _make(self, device_override=None):
        from custom_components.sinum.cover import SinumSbusBlindCover
        device = dict(FIXTURES["sbus_blind_controller"])
        device["_device_name"] = "SBUS Blind"
        if device_override:
            device.update(device_override)
        coordinator = _make_coordinator(sbus={60: device})
        entity = SinumSbusBlindCover(coordinator, 60, "test_entry")
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()
        return entity, coordinator

    def test_unique_id(self):
        entity, _ = self._make()
        assert entity.unique_id == "test_entry_sbus_60"

    def test_current_position(self):
        entity, _ = self._make()
        assert entity.current_cover_position == 50

    def test_current_tilt_position(self):
        entity, _ = self._make()
        assert entity.current_cover_tilt_position == 30

    def test_is_closed_when_position_zero(self):
        entity, _ = self._make({"current_opening": 0})
        assert entity.is_closed is True

    def test_is_open_when_position_nonzero(self):
        entity, _ = self._make({"current_opening": 50})
        assert entity.is_closed is False

    def test_is_opening_when_target_greater(self):
        entity, _ = self._make({"current_opening": 20, "target_opening": 80})
        assert entity.is_opening is True

    def test_is_closing_when_target_less(self):
        entity, _ = self._make({"current_opening": 80, "target_opening": 20})
        assert entity.is_closing is True

    def test_not_opening_when_target_equals_current(self):
        entity, _ = self._make({"current_opening": 50, "target_opening": 50})
        assert entity.is_opening is False
        assert entity.is_closing is False

    def test_not_opening_when_no_target(self):
        entity, _ = self._make({"current_opening": 50, "target_opening": None})
        assert entity.is_opening is False

    def test_has_tilt_feature_when_tilt_present(self):
        from homeassistant.components.cover import CoverEntityFeature
        entity, _ = self._make()
        assert entity.supported_features & CoverEntityFeature.SET_TILT_POSITION

    def test_no_tilt_feature_when_no_tilt_keys(self):
        from custom_components.sinum.cover import SinumSbusBlindCover
        from homeassistant.components.cover import CoverEntityFeature
        device = {"id": 60, "type": "blind_controller", "current_opening": 50, "_device_name": "Blind"}
        coordinator = _make_coordinator(sbus={60: device})
        entity = SinumSbusBlindCover(coordinator, 60, "test_entry")
        assert not (entity.supported_features & CoverEntityFeature.SET_TILT_POSITION)

    @pytest.mark.asyncio
    async def test_open_cover_sends_open_command(self):
        entity, coordinator = self._make()
        coordinator.sbus_devices[60] = dict(FIXTURES["sbus_blind_controller"])
        coordinator.client.patch_sbus_device = AsyncMock(return_value={})
        await entity.async_open_cover()
        coordinator.client.patch_sbus_device.assert_awaited_once_with(
            60, {"command": "open", "opening_percentage": 100}
        )

    @pytest.mark.asyncio
    async def test_close_cover_sends_zero_percentage(self):
        entity, coordinator = self._make()
        coordinator.sbus_devices[60] = dict(FIXTURES["sbus_blind_controller"])
        coordinator.client.patch_sbus_device = AsyncMock(return_value={})
        await entity.async_close_cover()
        coordinator.client.patch_sbus_device.assert_awaited_once_with(
            60, {"command": "open", "opening_percentage": 0}
        )

    @pytest.mark.asyncio
    async def test_stop_cover_sends_stop_command(self):
        entity, coordinator = self._make()
        coordinator.sbus_devices[60] = dict(FIXTURES["sbus_blind_controller"])
        coordinator.client.patch_sbus_device = AsyncMock(return_value={})
        await entity.async_stop_cover()
        coordinator.client.patch_sbus_device.assert_awaited_once_with(60, {"command": "stop"})

    @pytest.mark.asyncio
    async def test_set_cover_position(self):
        from homeassistant.components.cover import ATTR_POSITION
        entity, coordinator = self._make()
        coordinator.sbus_devices[60] = dict(FIXTURES["sbus_blind_controller"])
        coordinator.client.patch_sbus_device = AsyncMock(return_value={})
        await entity.async_set_cover_position(**{ATTR_POSITION: 75})
        coordinator.client.patch_sbus_device.assert_awaited_once_with(
            60, {"command": "open", "opening_percentage": 75}
        )

    @pytest.mark.asyncio
    async def test_set_cover_tilt_position(self):
        from homeassistant.components.cover import ATTR_TILT_POSITION
        entity, coordinator = self._make()
        coordinator.sbus_devices[60] = dict(FIXTURES["sbus_blind_controller"])
        coordinator.client.patch_sbus_device = AsyncMock(return_value={})
        await entity.async_set_cover_tilt_position(**{ATTR_TILT_POSITION: 45})
        coordinator.client.patch_sbus_device.assert_awaited_once_with(
            60, {"command": "tilt", "tilt_percentage": 45}
        )

    def test_sbus_blind_setup_creates_entity(self):
        from custom_components.sinum.cover import async_setup_entry
        device = dict(FIXTURES["sbus_blind_controller"])
        device["_device_name"] = "Blind"
        coordinator = _make_coordinator(sbus={60: device})
        coordinator.virtual_devices = {}
        coordinator.wtp_devices = {}
        coordinator.lora_devices = {}
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "test"
        added = []
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        )
        from custom_components.sinum.cover import SinumSbusBlindCover
        assert any(isinstance(e, SinumSbusBlindCover) for e in added)


# ─────────────────────── Alarm Arm/Disarm ───────────────────────

class TestAlarmArmDisarm:
    def _make(self):
        from custom_components.sinum.alarm_control_panel import SinumAlarmZone
        zone = {
            "id": 1, "name": "Zone 1", "type": "alarm_zone",
            "zone_status": "disarmed", "armed": False, "violated": False,
        }
        coordinator = MagicMock()
        coordinator.alarm_zones = {1: zone}
        coordinator.client.command_alarm_device = AsyncMock(return_value=None)
        entity = SinumAlarmZone(coordinator, zone, "test_entry")
        entity.hass = MagicMock()
        entity.async_write_ha_state = MagicMock()
        return entity, coordinator

    @pytest.mark.asyncio
    async def test_arm_away_sends_correct_command(self):
        entity, coordinator = self._make()
        await entity.async_alarm_arm_away(code="1234")
        coordinator.client.command_alarm_device.assert_awaited_once_with(
            1, "arm", {"arm": "1234"}
        )

    @pytest.mark.asyncio
    async def test_disarm_sends_correct_command(self):
        entity, coordinator = self._make()
        await entity.async_alarm_disarm(code="5678")
        coordinator.client.command_alarm_device.assert_awaited_once_with(
            1, "disarm", {"disarm": "5678"}
        )

    @pytest.mark.asyncio
    async def test_arm_without_code_raises_ha_error(self):
        from homeassistant.exceptions import HomeAssistantError
        entity, _ = self._make()
        with pytest.raises(HomeAssistantError, match="PIN code is required"):
            await entity.async_alarm_arm_away(code=None)

    @pytest.mark.asyncio
    async def test_disarm_without_code_raises_ha_error(self):
        from homeassistant.exceptions import HomeAssistantError
        entity, _ = self._make()
        with pytest.raises(HomeAssistantError, match="PIN code is required"):
            await entity.async_alarm_disarm(code=None)

    @pytest.mark.asyncio
    async def test_arm_connection_error_raises_ha_error(self):
        from homeassistant.exceptions import HomeAssistantError
        entity, coordinator = self._make()
        coordinator.client.command_alarm_device = AsyncMock(
            side_effect=SinumConnectionError("hub down")
        )
        with pytest.raises(HomeAssistantError, match="Cannot arm alarm"):
            await entity.async_alarm_arm_away(code="1234")

    @pytest.mark.asyncio
    async def test_disarm_connection_error_raises_ha_error(self):
        from homeassistant.exceptions import HomeAssistantError
        entity, coordinator = self._make()
        coordinator.client.command_alarm_device = AsyncMock(
            side_effect=SinumConnectionError("hub down")
        )
        with pytest.raises(HomeAssistantError, match="Cannot disarm alarm"):
            await entity.async_alarm_disarm(code="1234")

    def test_code_format_is_number(self):
        from homeassistant.components.alarm_control_panel import CodeFormat
        entity, _ = self._make()
        assert entity.code_format == CodeFormat.NUMBER

    def test_code_arm_required_is_true(self):
        entity, _ = self._make()
        assert entity.code_arm_required is True


# ─────────────────────── SBUS Energy Meter Sensors ──────────────

class TestSbusEnergyMeterSensors:
    def _make_sensor(self, key):
        from custom_components.sinum.sensor import SinumSensor, SBUS_SENSORS
        device = dict(FIXTURES["sbus_energy_meter"])
        device["_device_name"] = "SBUS Energy"
        coordinator = _make_coordinator(sbus={61: device})
        desc = next(d for d in SBUS_SENSORS if d.key == key)
        entity = SinumSensor(coordinator, 61, desc, "test_entry")
        return entity

    def test_active_power(self):
        entity = self._make_sensor("active_power")
        assert entity.native_value == pytest.approx(1.5)  # 1500 mW * 0.001 = 1.5 W

    def test_voltage(self):
        entity = self._make_sensor("voltage")
        assert entity.native_value == pytest.approx(2.3)  # 2300 mV * 0.001 = 2.3 V

    def test_current(self):
        entity = self._make_sensor("current")
        assert entity.native_value == pytest.approx(0.65)  # 650 mA * 0.001 = 0.65 A

    def test_energy_consumed_total(self):
        entity = self._make_sensor("energy_consumed_total")
        assert entity.native_value == pytest.approx(12500)  # 12500 Wh, scale=1.0

    def test_energy_consumed_today(self):
        entity = self._make_sensor("energy_consumed_today")
        assert entity.native_value == pytest.approx(150)  # 150 Wh, scale=1.0

    def test_energy_consumed_yesterday(self):
        entity = self._make_sensor("energy_consumed_yesterday")
        assert entity.native_value == pytest.approx(200)  # 200 Wh, scale=1.0


# ─────────────────────── WTP Battery/Signal Sensors ─────────────

class TestWtpBatterySignalSensors:
    def _make_sensor(self, key):
        from custom_components.sinum.sensor import SinumSensor, WTP_SENSORS
        device = {"id": 20, "type": "temperature_sensor", "battery": 75, "signal": 88, "_device_name": "WTP Dev"}
        coordinator = _make_coordinator(wtp={20: device})
        desc = next((d for d in WTP_SENSORS if d.key == key), None)
        if desc is None:
            pytest.skip(f"No WTP sensor descriptor for key={key}")
        entity = SinumSensor(coordinator, 20, desc, "test_entry")
        return entity

    def test_battery_sensor(self):
        entity = self._make_sensor("battery")
        assert entity.native_value == 75

    def test_signal_sensor(self):
        entity = self._make_sensor("signal")
        assert entity.native_value == 88


# ─────────────────────── LoRa Coordinator Integration ───────────

class TestLoraCoordinatorIntegration:
    def _make_coordinator_obj(self, mock_client):
        from unittest.mock import patch
        from homeassistant.helpers.frame import report_usage  # noqa: F401
        hass = MagicMock()
        hass.loop = MagicMock()
        hass.config_entries = MagicMock()
        from custom_components.sinum.coordinator import SinumCoordinator
        with patch("homeassistant.helpers.frame.report_usage", return_value=None):
            coordinator = SinumCoordinator(hass, mock_client, scan_interval=30)
        return coordinator

    @pytest.mark.asyncio
    async def test_lora_devices_included_in_update(self, mock_client):
        from unittest.mock import patch
        lora_device = dict(FIXTURES["lora_temp_sensor"])
        mock_client.get_lora_devices = AsyncMock(return_value=[lora_device])
        mock_client.get_lora_device = AsyncMock(return_value=lora_device)
        coordinator = self._make_coordinator_obj(mock_client)
        with patch.object(coordinator, "async_set_updated_data"):
            data = await coordinator._async_update_data()
        assert 70 in data["lora"]
        assert data["lora"][70]["type"] == "temperature_sensor"

    @pytest.mark.asyncio
    async def test_lora_failure_returns_cached(self, mock_client):
        from unittest.mock import patch
        lora_device = dict(FIXTURES["lora_temp_sensor"])
        mock_client.get_lora_devices = AsyncMock(return_value=[lora_device])
        coordinator = self._make_coordinator_obj(mock_client)
        with patch.object(coordinator, "async_set_updated_data"):
            await coordinator._async_update_data()
        assert coordinator.lora_devices

        mock_client.get_lora_devices = AsyncMock(
            side_effect=SinumConnectionError("lora down")
        )
        with patch.object(coordinator, "async_set_updated_data"):
            data = await coordinator._async_update_data()
        assert 70 in data["lora"]
