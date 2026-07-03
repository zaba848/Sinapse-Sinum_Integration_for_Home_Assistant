"""SBUS number entities (analog output and PWM)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import SinumCoordinator, SinumDeviceAvailableMixin, via_device_for


def _analog_output_device_info(device: dict, entry_id: str, device_id: int) -> DeviceInfo:
    name = device.get("_device_name") or device.get("name", str(device_id))
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_sbus_{device_id}")},
        name=name,
        manufacturer=MANUFACTURER,
        model=device.get("_parent_model") or "Sinum SBUS Analog Output",
        suggested_area=device.get("_area") or None,
        via_device=via_device_for(device, entry_id),
    )


class SinumAnalogOutputNumber(
    SinumDeviceAvailableMixin, CoordinatorEntity[SinumCoordinator], NumberEntity
):
    """SBUS analog_output — writable output value (e.g. 0–10 V control signal)."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:tune-vertical"

    def __init__(self, coordinator: SinumCoordinator, device_id: int, entry_id: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry_id}_sbus_{device_id}"
        device = coordinator.sbus_devices.get(device_id, {})
        self._attr_native_min_value = float(device.get("value_minimum", 0))
        self._attr_native_max_value = float(device.get("value_maximum", 10000))
        self._attr_native_step = 1.0
        self._attr_native_unit_of_measurement = device.get("unit") or None
        self._attr_device_info = _analog_output_device_info(device, entry_id, device_id)

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.sbus_devices.get(self._device_id, {})

    @property
    def native_value(self) -> float | None:
        raw = self._device.get("value")
        return float(raw) if raw is not None else None

    async def async_set_native_value(self, value: float) -> None:
        try:
            updated = await self.coordinator.client.patch_sbus_device(
                self._device_id, {"value": int(value)}
            )
        except Exception as err:
            raise HomeAssistantError(f"Cannot set analog output: {err}") from err
        self.coordinator.sbus_devices[self._device_id].update(updated)
        self.async_write_ha_state()


class SinumPwmNumber(SinumDeviceAvailableMixin, CoordinatorEntity[SinumCoordinator], NumberEntity):
    """SBUS pulse_width_modulation — duty_cycle control (0–100 %)."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:pulse"
    _attr_native_min_value = 0.0
    _attr_native_max_value = 100.0
    _attr_native_step = 1.0
    _attr_native_unit_of_measurement = "%"

    def __init__(self, coordinator: SinumCoordinator, device_id: int, entry_id: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry_id}_sbus_{device_id}_pwm"
        device = coordinator.sbus_devices.get(device_id, {})
        name = device.get("_device_name") or device.get("name", str(device_id))
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_sbus_{device_id}")},
            name=name,
            manufacturer=MANUFACTURER,
            model=device.get("_parent_model") or "Sinum SBUS PWM",
            suggested_area=device.get("_area") or None,
            via_device=via_device_for(device, entry_id),
        )

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.sbus_devices.get(self._device_id, {})

    @property
    def native_value(self) -> float | None:
        raw = self._device.get("duty_cycle")
        return float(raw) if raw is not None else None

    async def async_set_native_value(self, value: float) -> None:
        try:
            updated = await self.coordinator.client.patch_sbus_device(
                self._device_id, {"duty_cycle": int(value)}
            )
        except Exception as err:
            raise HomeAssistantError(f"Cannot set PWM duty cycle: {err}") from err
        self.coordinator.sbus_devices[self._device_id].update(updated)
        self.async_write_ha_state()
