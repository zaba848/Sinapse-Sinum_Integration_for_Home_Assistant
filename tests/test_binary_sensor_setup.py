"""Tests for binary_sensor async_setup_entry and parent device sensors."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.sinum.binary_sensor import (
    SinumBinarySensor,
    SinumParentErrorSensor,
    SinumParentOnlineSensor,
    async_setup_entry,
)
from custom_components.sinum.const import (
    STYPE_MOTION_SENSOR,
    WTYPE_FLOOD_SENSOR,
    WTYPE_MOTION_SENSOR,
    WTYPE_OPENING_SENSOR,
    WTYPE_SMOKE_SENSOR,
    WTYPE_TEMPERATURE_REGULATOR,
    WTYPE_TWO_STATE_INPUT_SENSOR,
)


def _make_coordinator(*, wtp=None, sbus=None, parent_devices=None):
    c = MagicMock()
    c.virtual_devices = {}
    c.wtp_devices = wtp or {}
    c.sbus_devices = sbus or {}
    c.parent_devices = parent_devices or []
    return c


def _make_entry(coordinator):
    entry = MagicMock()
    entry.runtime_data = coordinator
    entry.entry_id = "test_entry"
    return entry


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_flood_sensor_creates_entity(self):
        wtp = {1: {"id": 1, "type": WTYPE_FLOOD_SENSOR, "name": "Flood", "flood_detected": "wet"}}
        coordinator = _make_coordinator(wtp=wtp)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        assert len(added) == 1
        assert isinstance(added[0], SinumBinarySensor)

    @pytest.mark.asyncio
    async def test_motion_sensor_creates_entity(self):
        wtp = {2: {"id": 2, "type": WTYPE_MOTION_SENSOR, "name": "Motion", "state": "motion"}}
        coordinator = _make_coordinator(wtp=wtp)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        assert len(added) == 1
        assert isinstance(added[0], SinumBinarySensor)

    @pytest.mark.asyncio
    async def test_opening_sensor_creates_entity(self):
        wtp = {3: {"id": 3, "type": WTYPE_OPENING_SENSOR, "name": "Door", "state": "closed"}}
        coordinator = _make_coordinator(wtp=wtp)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        assert len(added) == 1

    @pytest.mark.asyncio
    async def test_smoke_sensor_creates_entity(self):
        wtp = {4: {"id": 4, "type": WTYPE_SMOKE_SENSOR, "name": "Smoke", "state": "ok"}}
        coordinator = _make_coordinator(wtp=wtp)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        assert len(added) == 1

    @pytest.mark.asyncio
    async def test_two_state_wtp_creates_entity(self):
        wtp = {5: {"id": 5, "type": WTYPE_TWO_STATE_INPUT_SENSOR, "name": "Input", "state": "off"}}
        coordinator = _make_coordinator(wtp=wtp)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        assert len(added) == 1

    @pytest.mark.asyncio
    async def test_temperature_regulator_with_target_reached_creates_extra_entity(self):
        wtp = {
            6: {
                "id": 6,
                "type": WTYPE_TEMPERATURE_REGULATOR,
                "name": "Thermostat",
                "target_temperature_reached": True,
            }
        }
        coordinator = _make_coordinator(wtp=wtp)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        # Only target_reached sensor (temperature_regulator not in _WTP_TYPE_TO_DESCRIPTION directly)
        target_reached = [
            e
            for e in added
            if hasattr(e, "entity_description") and e.entity_description.key == "target_reached"
        ]
        assert len(target_reached) == 1

    @pytest.mark.asyncio
    async def test_temperature_regulator_without_target_reached_key_skipped(self):
        wtp = {6: {"id": 6, "type": WTYPE_TEMPERATURE_REGULATOR, "name": "Thermostat"}}
        coordinator = _make_coordinator(wtp=wtp)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        assert len(added) == 0

    @pytest.mark.asyncio
    async def test_sbus_motion_sensor_creates_entity(self):
        sbus = {
            7: {"id": 7, "type": STYPE_MOTION_SENSOR, "name": "SBUS Motion", "state": "detected"}
        }
        coordinator = _make_coordinator(sbus=sbus)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        assert len(added) == 1

    @pytest.mark.asyncio
    async def test_sbus_temperature_regulator_with_target_reached(self):
        sbus = {
            8: {
                "id": 8,
                "type": WTYPE_TEMPERATURE_REGULATOR,
                "name": "SBUS Thermo",
                "target_temperature_reached": False,
            }
        }
        coordinator = _make_coordinator(sbus=sbus)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        target_reached = [
            e
            for e in added
            if hasattr(e, "entity_description") and e.entity_description.key == "target_reached"
        ]
        assert len(target_reached) == 1

    @pytest.mark.asyncio
    async def test_parent_online_sensor_created(self):
        parents = [{"id": 1, "class": "wtp", "name": "Hub WTP", "status": "online"}]
        coordinator = _make_coordinator(parent_devices=parents)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        online = [e for e in added if isinstance(e, SinumParentOnlineSensor)]
        assert len(online) == 1

    @pytest.mark.asyncio
    async def test_parent_error_sensor_created_when_has_messages_present(self):
        parents = [
            {"id": 1, "class": "wtp", "name": "Hub WTP", "status": "online", "has_messages": False}
        ]
        coordinator = _make_coordinator(parent_devices=parents)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        error = [e for e in added if isinstance(e, SinumParentErrorSensor)]
        assert len(error) == 1

    @pytest.mark.asyncio
    async def test_parent_error_sensor_not_created_when_no_has_messages(self):
        parents = [{"id": 2, "class": "sbus", "name": "Hub SBUS", "status": "online"}]
        coordinator = _make_coordinator(parent_devices=parents)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        error = [e for e in added if isinstance(e, SinumParentErrorSensor)]
        assert len(error) == 0

    @pytest.mark.asyncio
    async def test_unknown_wtp_type_skipped(self):
        wtp = {10: {"id": 10, "type": "unknown_device", "name": "Unknown"}}
        coordinator = _make_coordinator(wtp=wtp)
        entry = _make_entry(coordinator)
        added = []
        await async_setup_entry(MagicMock(), entry, lambda e, **kw: added.extend(e))
        assert len(added) == 0


class TestSinumParentOnlineSensor:
    def _make_sensor(self, parent: dict) -> SinumParentOnlineSensor:
        coordinator = MagicMock()
        coordinator.parent_devices = [parent]
        return SinumParentOnlineSensor(coordinator, parent, "test_entry")

    def test_is_on_when_online(self):
        parent = {"id": 1, "class": "wtp", "name": "Hub", "status": "online"}
        entity = self._make_sensor(parent)
        assert entity.is_on is True

    def test_is_off_when_offline(self):
        parent = {"id": 1, "class": "wtp", "name": "Hub", "status": "offline"}
        entity = self._make_sensor(parent)
        assert entity.is_on is False

    def test_is_none_when_no_status(self):
        parent = {"id": 1, "class": "wtp", "name": "Hub"}
        entity = self._make_sensor(parent)
        assert entity.is_on is None

    def test_unique_id(self):
        parent = {"id": 5, "class": "sbus", "name": "SBUS Hub"}
        entity = self._make_sensor(parent)
        assert entity.unique_id == "test_entry_parent_sbus_5"

    def test_extra_state_attributes(self):
        parent = {
            "id": 1,
            "class": "wtp",
            "name": "Hub",
            "status": "online",
            "software_status": "ok",
            "has_messages": False,
            "version": "1.24.0",
            "type": "wtp_hub",
        }
        entity = self._make_sensor(parent)
        attrs = entity.extra_state_attributes
        assert attrs["software_status"] == "ok"
        assert attrs["has_messages"] is False
        assert attrs["firmware_version"] == "1.24.0"
        assert attrs["type"] == "wtp_hub"
        assert attrs["class"] == "wtp"

    def test_returns_empty_when_parent_not_found(self):
        coordinator = MagicMock()
        coordinator.parent_devices = []
        parent = {"id": 99, "class": "wtp", "name": "Missing"}
        entity = SinumParentOnlineSensor(coordinator, parent, "test_entry")
        assert entity.is_on is None

    def test_device_info_uses_parent_model(self):
        parent = {"id": 1, "class": "wtp", "name": "Hub", "model": "EH-01", "version": "1.0.0"}
        entity = self._make_sensor(parent)
        assert entity.device_info["model"] == "EH-01"
        assert entity.device_info["sw_version"] == "1.0.0"


class TestSinumParentErrorSensor:
    def _make_sensor(self, parent: dict) -> SinumParentErrorSensor:
        coordinator = MagicMock()
        coordinator.parent_devices = [parent]
        return SinumParentErrorSensor(coordinator, parent, "test_entry")

    def test_is_on_when_has_messages_true(self):
        parent = {"id": 1, "class": "wtp", "name": "Hub", "has_messages": True}
        entity = self._make_sensor(parent)
        assert entity.is_on is True

    def test_is_off_when_has_messages_false(self):
        parent = {"id": 1, "class": "wtp", "name": "Hub", "has_messages": False}
        entity = self._make_sensor(parent)
        assert entity.is_on is False

    def test_is_none_when_has_messages_missing(self):
        parent = {"id": 1, "class": "wtp", "name": "Hub"}
        entity = self._make_sensor(parent)
        assert entity.is_on is None

    def test_unique_id_has_problem_suffix(self):
        parent = {"id": 3, "class": "sbus", "name": "Hub"}
        entity = self._make_sensor(parent)
        assert entity.unique_id == "test_entry_parent_sbus_3_problem"

    def test_returns_empty_when_parent_not_found(self):
        coordinator = MagicMock()
        coordinator.parent_devices = []
        parent = {"id": 99, "class": "wtp", "name": "Missing"}
        entity = SinumParentErrorSensor(coordinator, parent, "test_entry")
        assert entity.is_on is None


class TestBinarySensorStoreRouting:
    def test_wtp_source_reads_wtp_store_not_sbus(self):
        coordinator = _make_coordinator(
            wtp={1: {"id": 1, "type": WTYPE_MOTION_SENSOR, "motion_detected": "true"}},
            sbus={1: {"id": 1, "type": STYPE_MOTION_SENSOR, "motion_detected": "false"}},
        )
        from custom_components.sinum.binary_sensor import (
            BINARY_SENSOR_TYPES,
            SinumBinarySensor,
        )

        desc = next(d for d in BINARY_SENSOR_TYPES if d.key == "motion")
        entity = SinumBinarySensor(coordinator, 1, desc, "entry")
        assert entity.is_on is True

    def test_unknown_source_returns_empty_device(self):
        coordinator = _make_coordinator(wtp={1: {"id": 1, "state": True}})
        from custom_components.sinum.binary_sensor import SinumBinarySensorDescription

        desc = SinumBinarySensorDescription(
            key="custom",
            wtp_type="custom_type",
            source="unknown_bus",
            on_states=("true",),
        )
        entity = SinumBinarySensor(coordinator, 1, desc, "entry")
        assert entity.is_on is None
