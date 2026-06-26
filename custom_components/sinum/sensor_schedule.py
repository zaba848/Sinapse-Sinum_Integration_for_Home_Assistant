from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SinumCoordinator


class SinumScheduleSensor(CoordinatorEntity[SinumCoordinator], SensorEntity):
    """Base class for coordinator-backed schedule sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SinumCoordinator,
        schedule: dict[str, Any],
        entry_id: str,
        unique_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self._initial_schedule = schedule
        self._schedule_id = schedule.get("id")
        self._attr_unique_id = f"{entry_id}_schedule_{self._schedule_id}_{unique_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"schedule_{self._schedule_id}_{entry_id}")},
            name=f"Sinum Schedule {schedule.get('name', self._schedule_id)}",
            manufacturer="TECH Sterowniki",
            model="Schedule",
        )

    @property
    def _schedule(self) -> dict[str, Any]:
        schedules = getattr(self.coordinator, "schedules", [])
        for schedule in schedules:
            if str(schedule.get("id")) == str(self._schedule_id):
                return schedule
        return self._initial_schedule


class SinumScheduleTargetTempSensor(SinumScheduleSensor):
    """Current target temperature from schedule."""

    _attr_name = "Current Target Temperature"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:thermometer"

    def __init__(
        self,
        coordinator: SinumCoordinator,
        schedule: dict[str, Any],
        entry_id: str,
    ) -> None:
        super().__init__(coordinator, schedule, entry_id, "target_temp")

    @property
    def native_value(self) -> float | None:
        raw = self._schedule.get("current_target_temperature")
        return raw / 10 if raw is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "schedule_id": self._schedule.get("id"),
            "schedule_name": self._schedule.get("name"),
            "modes": self._schedule.get("modes", []),
        }


class SinumScheduleFallbackTempSensor(SinumScheduleSensor):
    """Fallback temperature for schedule."""

    _attr_name = "Fallback Temperature"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:thermometer-low"

    def __init__(
        self,
        coordinator: SinumCoordinator,
        schedule: dict[str, Any],
        entry_id: str,
    ) -> None:
        super().__init__(coordinator, schedule, entry_id, "fallback_temp")

    @property
    def native_value(self) -> float | None:
        raw = self._schedule.get("fallback")
        return raw / 10 if raw is not None else None


class SinumScheduleActivePeriodSensor(SinumScheduleSensor):
    """Active schedule period (current time entry)."""

    _attr_name = "Active Period"
    _attr_icon = "mdi:calendar-clock"

    def __init__(
        self,
        coordinator: SinumCoordinator,
        schedule: dict[str, Any],
        entry_id: str,
    ) -> None:
        super().__init__(coordinator, schedule, entry_id, "active_period")

    @staticmethod
    def _raw_entries(day_data: Any) -> list[Any]:
        if isinstance(day_data, list):
            return day_data
        if isinstance(day_data, dict):
            return day_data.get("configuration", [])
        return []

    @staticmethod
    def _day_entries(day_data: Any) -> list[dict[str, Any]]:
        """Normalise day schedule data: handles both list (thermal) and dict (relay) formats."""
        return [e for e in SinumScheduleActivePeriodSensor._raw_entries(day_data) if isinstance(e, dict)]

    @property
    def native_value(self) -> str:
        """Return 'Active' if in scheduled period, else 'Fallback'."""
        from datetime import datetime

        now = datetime.now()
        current_minutes = now.hour * 60 + now.minute
        weekday_names = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]
        weekday = weekday_names[now.weekday()]
        entries = self._day_entries(self._schedule.get(weekday))
        for entry in entries:
            if entry.get("start", 0) <= current_minutes < entry.get("end", 0):
                return "Active"
        return "Fallback"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        from datetime import datetime

        now = datetime.now()
        weekday_names = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]
        weekday = weekday_names[now.weekday()]
        entries = self._day_entries(self._schedule.get(weekday))
        is_thermal = self._schedule.get("type") == "thermal"
        return {
            "entries_today": len(entries),
            "schedule_entries": [
                {
                    "start": e.get("start"),
                    "end": e.get("end"),
                    **(
                        {"target_temp": e.get("target_temperature", 0) / 10}
                        if is_thermal
                        else {"state": e.get("state")}
                    ),
                }
                for e in entries
            ],
        }


class SinumScheduleAssociationCountSensor(SinumScheduleSensor):
    """Count of devices associated with schedule."""

    _attr_name = "Associated Devices"
    _attr_icon = "mdi:link"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: SinumCoordinator,
        schedule: dict[str, Any],
        entry_id: str,
    ) -> None:
        super().__init__(coordinator, schedule, entry_id, "assoc_count")

    @property
    def native_value(self) -> int:
        """Return total count of all associated devices."""
        assoc = self._schedule.get("associations", {})
        return sum(len(v) for v in assoc.values() if isinstance(v, list))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        assoc = self._schedule.get("associations", {})
        return {k: v for k, v in assoc.items() if isinstance(v, list)}
