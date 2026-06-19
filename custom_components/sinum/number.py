from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SinumConfigEntry
from .api import SinumConnectionError
from .const import DOMAIN, STYPE_ANALOG_OUTPUT, STYPE_PWM
from .coordinator import SinumCoordinator, via_device_for

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SinumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SinumCoordinator = entry.runtime_data
    variables = getattr(coordinator, "variables", None)
    if not isinstance(variables, list):
        try:
            variables = await coordinator.client.get_variables()
            coordinator.variables = variables
        except SinumConnectionError:
            _LOGGER.debug("Variables endpoint not available on this hub firmware")
            variables = []

    entities: list[NumberEntity] = []
    for var in variables:
        if var.get("type") in ("integer", "float", "number"):
            entities.append(SinumVariableNumber(coordinator, var, entry.entry_id))

    for device_id, device in coordinator.sbus_devices.items():
        if device.get("type") == STYPE_ANALOG_OUTPUT:
            entities.append(SinumAnalogOutputNumber(coordinator, device_id, entry.entry_id))
        elif device.get("type") == STYPE_PWM:
            entities.append(SinumPwmNumber(coordinator, device_id, entry.entry_id))

    async_add_entities(entities)


class SinumVariableNumber(CoordinatorEntity[SinumCoordinator], NumberEntity):
    """Sinum global variable exposed as a HA number entity."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX

    def __init__(
        self, coordinator: SinumCoordinator, variable: dict[str, Any], entry_id: str
    ) -> None:
        super().__init__(coordinator)
        self._variable_id: int = variable["id"]
        if not isinstance(getattr(coordinator, "variables", None), list):
            coordinator.variables = []
        if not any(item.get("id") == self._variable_id for item in coordinator.variables):
            coordinator.variables.append(variable)
        self._attr_name = variable.get("name", f"Variable {self._variable_id}")
        self._attr_unique_id = f"{entry_id}_variable_{self._variable_id}"
        self._attr_native_min_value = float(variable.get("min", -999999))
        self._attr_native_max_value = float(variable.get("max", 999999))
        self._attr_native_step = 1.0 if variable.get("type") == "integer" else 0.01
        self._attr_native_value = float(variable.get("value", 0))
        self._attr_icon = "mdi:variable"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_variables")},
            name="Sinum Variables",
            manufacturer="TECH Sterowniki",
            model=_hub_model(coordinator.hub_info),
        )

    @property
    def _variable(self) -> dict[str, Any]:
        variables = getattr(self.coordinator, "variables", [])
        for variable in variables:
            if variable.get("id") == self._variable_id:
                return variable
        return {}

    @property
    def native_value(self) -> float | None:
        value = self._variable.get("value")
        return float(value) if value is not None else None

    async def async_set_native_value(self, value: float) -> None:
        updated = await self.coordinator.client.set_variable(self._variable_id, value)
        variable = self._variable
        if variable:
            variable.update(updated)
        else:
            self.coordinator.variables.append(updated)
        self.async_write_ha_state()


def _hub_model(hub_info: dict[str, Any]) -> str:
    if not isinstance(hub_info, dict):
        return "Sinum EH-01"
    model_map = {
        "sinum_plus": "Sinum Plus",
        "sinum_pro": "Sinum Pro",
        "sinum_lite": "Sinum Lite",
        "sinum": "Sinum EH-01",
    }
    return hub_info.get("model") or model_map.get(hub_info.get("device_type", "")) or "Sinum EH-01"


class SinumAnalogOutputNumber(CoordinatorEntity[SinumCoordinator], NumberEntity):
    """SBUS analog_output — writable output value (e.g. 0–10 V control signal)."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:knob"

    def __init__(self, coordinator: SinumCoordinator, device_id: int, entry_id: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry_id}_sbus_{device_id}"
        device = coordinator.sbus_devices.get(device_id, {})
        name = device.get("_device_name") or device.get("name", str(device_id))
        self._attr_native_min_value = float(device.get("value_minimum", 0))
        self._attr_native_max_value = float(device.get("value_maximum", 10000))
        self._attr_native_step = 1.0
        self._attr_native_unit_of_measurement = device.get("unit") or None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_sbus_{device_id}")},
            name=name,
            manufacturer="TECH Sterowniki",
            model=device.get("_parent_model") or "Sinum SBUS Analog Output",
            suggested_area=device.get("_area") or None,
            via_device=via_device_for(device, entry_id),
        )

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.sbus_devices.get(self._device_id, {})

    @property
    def native_value(self) -> float | None:
        raw = self._device.get("value")
        return float(raw) if raw is not None else None

    async def async_set_native_value(self, value: float) -> None:
        updated = await self.coordinator.client.patch_sbus_device(
            self._device_id, {"value": int(value)}
        )
        self.coordinator.sbus_devices[self._device_id].update(updated)
        self.async_write_ha_state()


class SinumPwmNumber(CoordinatorEntity[SinumCoordinator], NumberEntity):
    """SBUS pulse_width_modulation — duty_cycle control (0–100 %)."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:sine-wave"
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
            manufacturer="TECH Sterowniki",
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
        updated = await self.coordinator.client.patch_sbus_device(
            self._device_id, {"duty_cycle": int(value)}
        )
        self.coordinator.sbus_devices[self._device_id].update(updated)
        self.async_write_ha_state()
