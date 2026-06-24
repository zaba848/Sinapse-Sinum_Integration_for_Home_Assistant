"""Tests for Sinum thermal schedule sensors."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from custom_components.sinum.sensor import (
    SinumScheduleAssociationCountSensor,
    SinumScheduleFallbackTempSensor,
    SinumScheduleTargetTempSensor,
)

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "sinum_devices.json").read_text())


def _make_coordinator(schedule: dict):
    coordinator = MagicMock()
    coordinator.schedules = [schedule]
    return coordinator


class TestSinumScheduleSensors:
    def test_target_temperature_uses_current_schedule(self):
        schedule = dict(FIXTURES["schedules"][0])
        coordinator = _make_coordinator(schedule)
        entity = SinumScheduleTargetTempSensor(coordinator, schedule, "test_entry")

        assert entity.native_value == 21.5

        coordinator.schedules = [{**schedule, "current_target_temperature": 220}]
        assert entity.native_value == 22.0

    def test_fallback_temperature(self):
        schedule = dict(FIXTURES["schedules"][0])
        coordinator = _make_coordinator(schedule)
        entity = SinumScheduleFallbackTempSensor(coordinator, schedule, "test_entry")

        assert entity.native_value == 18.0

    def test_association_count(self):
        schedule = dict(FIXTURES["schedules"][0])
        coordinator = _make_coordinator(schedule)
        entity = SinumScheduleAssociationCountSensor(coordinator, schedule, "test_entry")

        assert entity.native_value == 2

    def test_target_temperature_attrs_follow_current_schedule(self):
        schedule = dict(FIXTURES["schedules"][0])
        coordinator = _make_coordinator(schedule)
        entity = SinumScheduleTargetTempSensor(coordinator, schedule, "test_entry")

        coordinator.schedules = [{**schedule, "name": "Updated Schedule", "modes": ["cooling"]}]
        attrs = entity.extra_state_attributes

        assert attrs["schedule_id"] == 7
        assert attrs["schedule_name"] == "Updated Schedule"
        assert attrs["modes"] == ["cooling"]

    def test_active_period_day_entries_accept_dict_configuration_format(self):
        """Line 120: relay-style dict schedule format is normalized via configuration key."""
        from custom_components.sinum.sensor import SinumScheduleActivePeriodSensor

        schedule = {
            "id": 8,
            "name": "Relay Schedule",
            "weekly_program": {
                "monday": {
                    "configuration": [
                        {"time_from": "06:00", "time_to": "08:00"},
                        "bad-entry",
                    ]
                }
            },
        }
        entries = SinumScheduleActivePeriodSensor._day_entries(schedule["weekly_program"]["monday"])

        assert entries == [{"time_from": "06:00", "time_to": "08:00"}]
