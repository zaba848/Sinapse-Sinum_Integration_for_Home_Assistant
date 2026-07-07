"""Sensor entities for Modbus and SLINK devices."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import SinumCoordinator, SinumDeviceAvailableMixin
from .sensor_modbus_descriptions import (
    _SENSOR_MAP,
    _SLINK_SENSOR_MAP,
    SinumModbusSensorDescription,
)

__all__ = [
    "SinumModbusSensor",
    "SinumModbusSensorDescription",
    "SinumSlinkSensor",
    "build_modbus_sensor_entities",
    "build_slink_sensor_entities",
]


def _get_field(device: dict[str, Any], path: str) -> Any:
    """Read a dot-separated path from device dict, e.g. 'phase_1.voltage'."""
    parts = path.split(".")
    val: Any = device
    for part in parts:
        if not isinstance(val, dict):
            return None
        val = val.get(part)
    return val


def _scaled_native_value(
    device: dict[str, Any], description: SinumModbusSensorDescription
) -> float | int | str | None:
    val = _get_field(device, description.field_path)
    if val is None:
        return None
    scale = description.scale
    if scale != 1.0 and isinstance(val, (int, float)):
        return round(val * scale, 6)
    return val


class SinumModbusSensor(SinumDeviceAvailableMixin, CoordinatorEntity[SinumCoordinator]):
    """A single sensor field on a Modbus device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SinumCoordinator,
        device_id: int,
        entry_id: str,
        description: SinumModbusSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._device_id = device_id
        self._attr_unique_id = f"{entry_id}_modbus_{device_id}_{description.key}"
        device = coordinator.modbus_devices.get(device_id, {})
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_modbus_{device_id}")},
            name=device.get("name", f"Modbus {device_id}"),
            manufacturer=MANUFACTURER,
            model="Sinum Modbus Energy Meter",
            sw_version=device.get("software_version"),
        )

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.modbus_devices.get(self._device_id, {})

    @property
    def native_value(self) -> float | int | str | None:
        return _scaled_native_value(self._device, self.entity_description)


def build_modbus_sensor_entities(
    coordinator: SinumCoordinator, entry_id: str
) -> list[SinumModbusSensor]:
    """Create sensor entities for all Modbus devices in the coordinator."""
    entities: list[SinumModbusSensor] = []
    for device_id, device in coordinator.modbus_devices.items():
        descriptions = _SENSOR_MAP.get(device.get("type", ""))
        if descriptions is None:
            continue
        for desc in descriptions:
            entities.append(SinumModbusSensor(coordinator, device_id, entry_id, desc))
    return entities


class SinumSlinkSensor(SinumDeviceAvailableMixin, CoordinatorEntity[SinumCoordinator]):
    """A single sensor field on a SLINK device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SinumCoordinator,
        device_id: int,
        entry_id: str,
        description: SinumModbusSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._device_id = device_id
        self._attr_unique_id = f"{entry_id}_slink_{device_id}_{description.key}"
        device = coordinator.slink_devices.get(device_id, {})
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_slink_{device_id}")},
            name=device.get("name", f"SLINK {device_id}"),
            manufacturer=MANUFACTURER,
            model="Sinum SLINK Energy Meter",
            sw_version=device.get("software_version"),
        )

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.slink_devices.get(self._device_id, {})

    @property
    def native_value(self) -> float | int | str | None:
        return _scaled_native_value(self._device, self.entity_description)


def build_slink_sensor_entities(
    coordinator: SinumCoordinator, entry_id: str
) -> list[SinumSlinkSensor]:
    """Create sensor entities for all SLINK devices in the coordinator."""
    entities: list[SinumSlinkSensor] = []
    for device_id, device in coordinator.slink_devices.items():
        descriptions = _SLINK_SENSOR_MAP.get(device.get("type", ""))
        if descriptions is None:
            continue
        for desc in descriptions:
            entities.append(SinumSlinkSensor(coordinator, device_id, entry_id, desc))
    return entities
