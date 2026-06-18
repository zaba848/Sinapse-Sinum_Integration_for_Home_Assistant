"""Tests for switch async_setup_entry and entity turn_on/turn_off actions."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sinum.const import (
    STYPE_COMMON_VALVE,
    STYPE_RELAY,
    STYPE_VALVE_PUMP,
    VTYPE_HEAT_PUMP_MANAGER,
    VTYPE_RELAY,
    VTYPE_WICKET,
    WTYPE_RELAY,
)
from custom_components.sinum.switch import (
    SinumBusRelaySwitch,
    SinumCommonValveSwitch,
    SinumDhwSwitch,
    SinumRelaySwitch,
    SinumValvePumpSwitch,
    SinumWicketSwitch,
    async_setup_entry,
)


def _make_coordinator(*, virtual=None, wtp=None, sbus=None):
    c = MagicMock()
    c.virtual_devices = virtual or {}
    c.wtp_devices = wtp or {}
    c.sbus_devices = sbus or {}
    c.client = MagicMock()
    c.client.patch_virtual_device = AsyncMock(return_value={})
    c.client.patch_wtp_device = AsyncMock(return_value={})
    c.client.patch_sbus_device = AsyncMock(return_value={})
    c.client.decode_temperature = lambda raw: raw / 10
    return c


def _make_entry(coordinator):
    entry = MagicMock()
    entry.runtime_data = coordinator
    entry.entry_id = "test_entry"
    return entry


def _wire(entity):
    entity.hass = MagicMock()
    entity.async_write_ha_state = MagicMock()
    return entity


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_virtual_relay_creates_relay_switch(self):
        virtual = {1: {"id": 1, "type": VTYPE_RELAY, "name": "Relay", "state": True}}
        coordinator = _make_coordinator(virtual=virtual)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        assert any(isinstance(e, SinumRelaySwitch) for e in added)

    @pytest.mark.asyncio
    async def test_virtual_wicket_creates_wicket_switch(self):
        virtual = {2: {"id": 2, "type": VTYPE_WICKET, "name": "Gate", "state": "locked"}}
        coordinator = _make_coordinator(virtual=virtual)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        assert any(isinstance(e, SinumWicketSwitch) for e in added)

    @pytest.mark.asyncio
    async def test_virtual_heat_pump_manager_with_dhw_creates_dhw_switch(self):
        virtual = {3: {"id": 3, "type": VTYPE_HEAT_PUMP_MANAGER, "name": "HP", "dhw_control": {"enabled": True}}}
        coordinator = _make_coordinator(virtual=virtual)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        assert any(isinstance(e, SinumDhwSwitch) for e in added)

    @pytest.mark.asyncio
    async def test_virtual_heat_pump_manager_without_dhw_skipped(self):
        virtual = {3: {"id": 3, "type": VTYPE_HEAT_PUMP_MANAGER, "name": "HP"}}
        coordinator = _make_coordinator(virtual=virtual)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        assert not any(isinstance(e, SinumDhwSwitch) for e in added)

    @pytest.mark.asyncio
    async def test_virtual_heat_pump_manager_dhw_without_enabled_skipped(self):
        virtual = {3: {"id": 3, "type": VTYPE_HEAT_PUMP_MANAGER, "name": "HP", "dhw_control": "not_a_dict"}}
        coordinator = _make_coordinator(virtual=virtual)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        assert not any(isinstance(e, SinumDhwSwitch) for e in added)

    @pytest.mark.asyncio
    async def test_wtp_relay_creates_bus_relay(self):
        wtp = {10: {"id": 10, "type": WTYPE_RELAY, "name": "WTP Relay", "state": False}}
        coordinator = _make_coordinator(wtp=wtp)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        relays = [e for e in added if isinstance(e, SinumBusRelaySwitch)]
        assert len(relays) == 1
        assert relays[0]._bus == "wtp"

    @pytest.mark.asyncio
    async def test_sbus_relay_creates_bus_relay(self):
        sbus = {20: {"id": 20, "type": STYPE_RELAY, "name": "SBUS Relay", "state": True}}
        coordinator = _make_coordinator(sbus=sbus)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        relays = [e for e in added if isinstance(e, SinumBusRelaySwitch)]
        assert len(relays) == 1
        assert relays[0]._bus == "sbus"

    @pytest.mark.asyncio
    async def test_sbus_valve_pump_creates_valve_pump_switch(self):
        sbus = {21: {"id": 21, "type": STYPE_VALVE_PUMP, "name": "Pump", "state": False}}
        coordinator = _make_coordinator(sbus=sbus)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        assert any(isinstance(e, SinumValvePumpSwitch) for e in added)

    @pytest.mark.asyncio
    async def test_sbus_common_valve_creates_common_valve_switch(self):
        sbus = {22: {"id": 22, "type": STYPE_COMMON_VALVE, "name": "Valve", "enabled": True}}
        coordinator = _make_coordinator(sbus=sbus)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        assert any(isinstance(e, SinumCommonValveSwitch) for e in added)

    @pytest.mark.asyncio
    async def test_unknown_virtual_type_skipped(self):
        virtual = {99: {"id": 99, "type": "unknown", "name": "Unknown"}}
        coordinator = _make_coordinator(virtual=virtual)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        assert len(added) == 0


class TestSinumRelaySwitch:
    def _make(self, state: bool = True):
        device = {"id": 1, "type": VTYPE_RELAY, "name": "Relay", "state": state}
        coordinator = _make_coordinator(virtual={1: device})
        entity = _wire(SinumRelaySwitch(coordinator, 1, "test_entry"))
        return entity, coordinator

    def test_is_on(self):
        entity, _ = self._make(True)
        assert entity.is_on is True

    def test_is_off(self):
        entity, _ = self._make(False)
        assert entity.is_on is False

    def test_unique_id(self):
        entity, _ = self._make()
        assert entity.unique_id == "test_entry_virtual_1"

    @pytest.mark.asyncio
    async def test_async_turn_on(self):
        entity, coordinator = self._make(False)
        coordinator.client.patch_virtual_device = AsyncMock(return_value={"state": True})
        await entity.async_turn_on()
        coordinator.client.patch_virtual_device.assert_awaited_once_with(1, {"state": True})

    @pytest.mark.asyncio
    async def test_async_turn_off(self):
        entity, coordinator = self._make(True)
        coordinator.client.patch_virtual_device = AsyncMock(return_value={"state": False})
        await entity.async_turn_off()
        coordinator.client.patch_virtual_device.assert_awaited_once_with(1, {"state": False})


class TestSinumWicketSwitch:
    def _make(self, state: str = "locked"):
        device = {"id": 2, "type": VTYPE_WICKET, "name": "Gate", "state": state}
        coordinator = _make_coordinator(virtual={2: device})
        entity = _wire(SinumWicketSwitch(coordinator, 2, "test_entry"))
        return entity, coordinator

    def test_is_on_when_unlocked(self):
        entity, _ = self._make("unlocked")
        assert entity.is_on is True

    def test_is_on_when_open(self):
        entity, _ = self._make("open")
        assert entity.is_on is True

    def test_is_off_when_locked(self):
        entity, _ = self._make("locked")
        assert entity.is_on is False

    @pytest.mark.asyncio
    async def test_async_turn_on_sends_unlock(self):
        entity, coordinator = self._make("locked")
        coordinator.client.patch_virtual_device = AsyncMock(return_value={"state": "unlocked"})
        await entity.async_turn_on()
        coordinator.client.patch_virtual_device.assert_awaited_once_with(2, {"command": "unlock"})

    @pytest.mark.asyncio
    async def test_async_turn_off_sends_lock(self):
        entity, coordinator = self._make("unlocked")
        coordinator.client.patch_virtual_device = AsyncMock(return_value={"state": "locked"})
        await entity.async_turn_off()
        coordinator.client.patch_virtual_device.assert_awaited_once_with(2, {"command": "lock"})


class TestSinumBusRelaySwitch:
    @pytest.mark.asyncio
    async def test_wtp_relay_turn_on(self):
        device = {"id": 10, "type": WTYPE_RELAY, "name": "WTP Relay", "state": False}
        coordinator = _make_coordinator(wtp={10: device})
        entity = _wire(SinumBusRelaySwitch(coordinator, 10, "test_entry", "wtp"))
        coordinator.client.patch_wtp_device = AsyncMock(return_value={"state": True})
        await entity.async_turn_on()
        coordinator.client.patch_wtp_device.assert_awaited_once_with(10, {"state": True})

    @pytest.mark.asyncio
    async def test_sbus_relay_turn_off(self):
        device = {"id": 20, "type": STYPE_RELAY, "name": "SBUS Relay", "state": True}
        coordinator = _make_coordinator(sbus={20: device})
        entity = _wire(SinumBusRelaySwitch(coordinator, 20, "test_entry", "sbus"))
        coordinator.client.patch_sbus_device = AsyncMock(return_value={"state": False})
        await entity.async_turn_off()
        coordinator.client.patch_sbus_device.assert_awaited_once_with(20, {"state": False})


class TestSinumValvePumpSwitch:
    @pytest.mark.asyncio
    async def test_turn_on(self):
        device = {"id": 21, "type": STYPE_VALVE_PUMP, "name": "Pump", "state": False}
        coordinator = _make_coordinator(sbus={21: device})
        entity = _wire(SinumValvePumpSwitch(coordinator, 21, "test_entry"))
        coordinator.client.patch_sbus_device = AsyncMock(return_value={"state": True})
        await entity.async_turn_on()
        coordinator.client.patch_sbus_device.assert_awaited_once_with(21, {"state": True})

    @pytest.mark.asyncio
    async def test_turn_off(self):
        device = {"id": 21, "type": STYPE_VALVE_PUMP, "name": "Pump", "state": True}
        coordinator = _make_coordinator(sbus={21: device})
        entity = _wire(SinumValvePumpSwitch(coordinator, 21, "test_entry"))
        coordinator.client.patch_sbus_device = AsyncMock(return_value={"state": False})
        await entity.async_turn_off()
        coordinator.client.patch_sbus_device.assert_awaited_once_with(21, {"state": False})


class TestSinumCommonValveSwitch:
    @pytest.mark.asyncio
    async def test_turn_on(self):
        device = {"id": 22, "type": STYPE_COMMON_VALVE, "name": "Valve", "enabled": False}
        coordinator = _make_coordinator(sbus={22: device})
        entity = _wire(SinumCommonValveSwitch(coordinator, 22, "test_entry"))
        coordinator.client.patch_sbus_device = AsyncMock(return_value={"enabled": True})
        await entity.async_turn_on()
        coordinator.client.patch_sbus_device.assert_awaited_once_with(22, {"enabled": True})

    @pytest.mark.asyncio
    async def test_turn_off(self):
        device = {"id": 22, "type": STYPE_COMMON_VALVE, "name": "Valve", "enabled": True}
        coordinator = _make_coordinator(sbus={22: device})
        entity = _wire(SinumCommonValveSwitch(coordinator, 22, "test_entry"))
        coordinator.client.patch_sbus_device = AsyncMock(return_value={"enabled": False})
        await entity.async_turn_off()
        coordinator.client.patch_sbus_device.assert_awaited_once_with(22, {"enabled": False})


class TestSinumDhwSwitchFalsyUpdate:
    """DHW switch when patch_virtual_device returns falsy value."""

    @pytest.mark.asyncio
    async def test_turn_on_with_falsy_update_does_not_raise(self):
        device = {
            "id": 5,
            "type": VTYPE_HEAT_PUMP_MANAGER,
            "name": "Heat Pump",
            "dhw_control": {"enabled": False},
        }
        coordinator = _make_coordinator(virtual={5: device})
        from custom_components.sinum.switch import SinumDhwSwitch
        entity = _wire(SinumDhwSwitch(coordinator, 5, "test_entry"))
        coordinator.client.patch_virtual_device = AsyncMock(return_value={})
        await entity.async_turn_on()
        coordinator.client.patch_virtual_device.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_turn_off_with_falsy_update_does_not_raise(self):
        device = {
            "id": 5,
            "type": VTYPE_HEAT_PUMP_MANAGER,
            "name": "Heat Pump",
            "dhw_control": {"enabled": True},
        }
        coordinator = _make_coordinator(virtual={5: device})
        from custom_components.sinum.switch import SinumDhwSwitch
        entity = _wire(SinumDhwSwitch(coordinator, 5, "test_entry"))
        coordinator.client.patch_virtual_device = AsyncMock(return_value={})
        await entity.async_turn_off()
        coordinator.client.patch_virtual_device.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_turn_on_with_truthy_update_updates_state(self):
        device = {
            "id": 5,
            "type": VTYPE_HEAT_PUMP_MANAGER,
            "name": "Heat Pump",
            "dhw_control": {"enabled": False},
        }
        coordinator = _make_coordinator(virtual={5: device})
        from custom_components.sinum.switch import SinumDhwSwitch
        entity = _wire(SinumDhwSwitch(coordinator, 5, "test_entry"))
        coordinator.client.patch_virtual_device = AsyncMock(
            return_value={"dhw_control": {"enabled": True}}
        )
        await entity.async_turn_on()
        assert coordinator.virtual_devices[5]["dhw_control"]["enabled"] is True

    @pytest.mark.asyncio
    async def test_turn_off_with_truthy_update_updates_state(self):
        device = {
            "id": 5,
            "type": VTYPE_HEAT_PUMP_MANAGER,
            "name": "Heat Pump",
            "dhw_control": {"enabled": True},
        }
        coordinator = _make_coordinator(virtual={5: device})
        from custom_components.sinum.switch import SinumDhwSwitch
        entity = _wire(SinumDhwSwitch(coordinator, 5, "test_entry"))
        coordinator.client.patch_virtual_device = AsyncMock(
            return_value={"dhw_control": {"enabled": False}}
        )
        await entity.async_turn_off()
        assert coordinator.virtual_devices[5]["dhw_control"]["enabled"] is False
