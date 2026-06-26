"""Sensor entity classes for WTP, SBUS and LoRa bus devices.

Sensor descriptions (data) live in sensor_bus_descriptions.py.
This module contains only the HA entity classes.

Re-exports all public names from sensor_bus_descriptions for backward compatibility
so existing callers (sensor.py, sensor_virtual.py, tests) can keep importing
from `sensor_bus` unchanged.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SinumCoordinator, SinumDeviceAvailableMixin, via_device_for
from .sensor_bus_descriptions import (  # noqa: F401  (re-export for callers)
    _SENTINEL_INT16,
    LORA_SENSORS,
    SBUS_REGULATOR_SENSORS,
    SBUS_SENSORS,
    WTP_SENSORS,
    SinumSensorDescription,
)

__all__ = [
    "_SENTINEL_INT16",
    "LORA_SENSORS",
    "SBUS_REGULATOR_SENSORS",
    "SBUS_SENSORS",
    "WTP_SENSORS",
    "SinumSensor",
    "SinumSensorDescription",
    "SinumTemperatureRegulatorSensor",
    "SinumButtonSensor",
]


class SinumSensor(SinumDeviceAvailableMixin, CoordinatorEntity[SinumCoordinator], SensorEntity):
    _attr_has_entity_name = True
    entity_description: SinumSensorDescription

    def __init__(
        self,
        coordinator: SinumCoordinator,
        device_id: int,
        description: SinumSensorDescription,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._source = description.source
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{self._source}_{device_id}_{description.key}"
        device = self._get_device_dict(coordinator)
        self._apply_dynamic_unit(device, description)
        self._attr_device_info = _sensor_device_info(device, entry_id, self._source, device_id)

    def _apply_dynamic_unit(
        self, device: dict[str, Any], description: SinumSensorDescription
    ) -> None:
        if description.native_unit_of_measurement:
            return
        device_unit = device.get("unit") or None
        if device_unit:
            self._attr_native_unit_of_measurement = device_unit

    def _get_device_dict(self, coordinator: SinumCoordinator) -> dict[str, Any]:
        if self._source == "virtual":
            return coordinator.virtual_devices.get(self._device_id, {})
        if self._source in ("sbus", "sbus_regulator"):
            return coordinator.sbus_devices.get(self._device_id, {})
        if self._source == "lora":
            return coordinator.lora_devices.get(self._device_id, {})
        return coordinator.wtp_devices.get(self._device_id, {})

    @property
    def _device(self) -> dict[str, Any]:
        return self._get_device_dict(self.coordinator)

    def _normalized_numeric_raw(self) -> int | float | None:
        raw = self._device.get(self.entity_description.api_key)
        if not isinstance(raw, (int, float)) or raw == _SENTINEL_INT16:
            return None
        if self._is_zero_unavailable(raw):
            return None
        return raw

    def _is_zero_unavailable(self, raw: int | float) -> bool:
        if raw != 0:
            return False
        return self.entity_description.zero_is_unavailable or self._device.get("status") == "offline"

    @property
    def native_value(self) -> float | str | None:
        raw = self._device.get(self.entity_description.api_key)
        if raw is None:
            return None
        if self.entity_description.is_text:
            return str(raw)
        normalized = self._normalized_numeric_raw()
        if normalized is None:
            return None
        return normalized * self.entity_description.scale


def _sensor_device_info(
    device: dict[str, Any], entry_id: str, source: str, device_id: int
) -> DeviceInfo:
    label = device.get("_device_name") or device.get("name", str(device_id))
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_{source}_{device_id}")},
        name=label,
        manufacturer="TECH Sterowniki",
        model=device.get("_parent_model") or _model_for_source(source),
        suggested_area=device.get("_area") or None,
        via_device=via_device_for(device, entry_id),
    )


def _button_device_info(
    device: dict[str, Any], entry_id: str, bus: str, device_id: int
) -> DeviceInfo:
    label = device.get("_device_name") or device.get("name", str(device_id))
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_{bus}_{device_id}")},
        name=label,
        manufacturer="TECH Sterowniki",
        model=device.get("_parent_model") or f"Sinum {bus.upper()} Button",
        suggested_area=device.get("_area") or None,
    )


def _wtp_or_sbus(
    coordinator: SinumCoordinator, bus: str
) -> dict[int, dict[str, Any]]:
    return coordinator.wtp_devices if bus == "wtp" else coordinator.sbus_devices


def _model_for_source(source: str) -> str:
    models = {
        "virtual": "Sinum Virtual Device",
        "sbus": "Sinum SBUS Sensor",
        "wtp_regulator": "Sinum Temperature Regulator",
        "sbus_regulator": "Sinum Temperature Regulator",
        "lora": "Sinum LoRa Sensor",
    }
    return models.get(source, "Sinum WTP Sensor")


class SinumTemperatureRegulatorSensor(SinumSensor):
    """Temperature regulator sensor with attributes for mode and control state."""

    def __init__(
        self,
        coordinator: SinumCoordinator,
        device_id: int,
        description: SinumSensorDescription,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator, device_id, description, entry_id)
        # _source stays as "wtp_regulator" or "sbus_regulator" — _get_device_dict handles both

    @staticmethod
    def _target_temperature_mode(value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        return value.get("current") or value.get("mode")

    @staticmethod
    def _copy_if_present(device: dict[str, Any], attrs: dict[str, Any], key: str) -> None:
        if key in device:
            attrs[key] = device[key]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Show regulator mode and control state as attributes."""
        device = self._device
        attrs: dict[str, Any] = {}

        self._copy_if_present(device, attrs, "system_mode")
        if "target_temperature_mode" in device:
            attrs["target_temperature_mode"] = self._target_temperature_mode(
                device["target_temperature_mode"]
            )
        self._copy_if_present(device, attrs, "mode_mutable")
        self._copy_if_present(device, attrs, "parent_id")

        return attrs


class SinumButtonSensor(
    SinumDeviceAvailableMixin, CoordinatorEntity[SinumCoordinator], SensorEntity
):
    """Last-action sensor for WTP/SBUS button devices (diagnostic fallback)."""

    _attr_has_entity_name = True
    _attr_translation_key = "button_last_action"
    _attr_icon = "mdi:gesture-tap-button"
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: SinumCoordinator,
        device_id: int,
        entry_id: str,
        bus: str,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._bus = bus
        self._attr_unique_id = f"{entry_id}_{bus}_{device_id}_last_action"
        device = _wtp_or_sbus(coordinator, bus).get(device_id, {})
        self._attr_device_info = _button_device_info(device, entry_id, bus, device_id)

    @property
    def _device(self) -> dict[str, Any]:
        store = (
            self.coordinator.wtp_devices if self._bus == "wtp" else self.coordinator.sbus_devices
        )
        return store.get(self._device_id, {})

    @property
    def native_value(self) -> str | None:
        action = self._device.get("action")
        if action is None:
            return None
        return str(action) if action != "" else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self._device
        attrs: dict[str, Any] = {"buttons_count": d.get("buttons_count", 1)}
        if "buzzer" in d:
            attrs["buzzer"] = d["buzzer"]
        return attrs
