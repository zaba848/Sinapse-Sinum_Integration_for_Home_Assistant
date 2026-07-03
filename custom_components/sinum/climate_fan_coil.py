"""Fan coil climate entity for WTP/SBUS bus devices."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ._climate_bus_mixin import _BusClimateMixin
from ._climate_helpers import (
    _copy_keys_if_present,
    _state_action_from_text,
    _target_temperature_mode_value,
)
from .const import DOMAIN, MANUFACTURER
from .coordinator import SinumCoordinator, via_device_for

_LOGGER = logging.getLogger(__name__)

_WORKING_STATE_TO_ACTION: dict[str, HVACAction] = {
    "heating_active": HVACAction.HEATING,
    "cooling_active": HVACAction.COOLING,
    "idle": HVACAction.IDLE,
    "off": HVACAction.OFF,
}

_GEAR_TO_FAN_MODE: dict[str, str] = {
    "first": "1",
    "second": "2",
    "third": "3",
}
_FAN_MODE_TO_GEAR: dict[str, str] = {v: k for k, v in _GEAR_TO_FAN_MODE.items()}
_FAN_MODES: list[str] = ["1", "2", "3"]


def _fan_coil_features(device: dict[str, Any]) -> ClimateEntityFeature:
    features = ClimateEntityFeature(0)
    if "target_temperature" in device:
        features |= ClimateEntityFeature.TARGET_TEMPERATURE
    if "fan" in device or device.get("fan_operation_mode"):
        features |= ClimateEntityFeature.FAN_MODE
    return features


def _fan_coil_device_info(
    device: dict[str, Any], entry_id: str, source: str, device_id: int
) -> DeviceInfo:
    area = device.get("_area") or None
    label = device.get("_device_name") or device.get("name", str(device_id))
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_{source}_{device_id}")},
        name=label,
        manufacturer=MANUFACTURER,
        model=device.get("_parent_model") or f"Sinum {source.upper()} Fan Coil",
        suggested_area=area,
        via_device=via_device_for(device, entry_id),
    )


def _add_fan_gear_attr(device: dict[str, Any], attrs: dict[str, Any]) -> None:
    manual_gear = device.get("fan", {}).get("manual_fan_gear")
    if manual_gear:
        attrs["manual_fan_gear"] = manual_gear


def _add_working_state_attr(device: dict[str, Any], attrs: dict[str, Any]) -> None:
    working_state = device.get("working_state")
    if working_state:
        attrs["working_state"] = working_state


def _fan_coil_extra_attrs(device: dict[str, Any]) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    _copy_keys_if_present(device, attrs, ("fan_operation_mode", "schedule_id"))
    if device.get("mode_mutable") is not None:
        attrs["mode_mutable"] = device["mode_mutable"]
    if "target_temperature_mode" in device:
        attrs["target_temperature_mode"] = _target_temperature_mode_value(
            device["target_temperature_mode"]
        )
    _add_fan_gear_attr(device, attrs)
    _add_working_state_attr(device, attrs)
    return attrs


class SinumFanCoilClimate(_BusClimateMixin, CoordinatorEntity[SinumCoordinator], ClimateEntity):
    """Climate entity for fan coil with work_mode, temperature, and fan control."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_translation_key = "fan_coil"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE
    )
    _attr_target_temperature_step = 0.5
    _attr_fan_modes = _FAN_MODES
    _attr_icon = "mdi:hvac"
    _current_temperature_key = "room_temperature"
    _mode_key = "work_mode"
    _patch_mode_key = "work_mode"

    def __init__(
        self,
        coordinator: SinumCoordinator,
        device_id: int,
        entry_id: str,
        source: str = "sbus",
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._source = source
        self._attr_unique_id = f"{entry_id}_{source}_{device_id}"
        device = self._device_dict(coordinator)
        self._attr_supported_features = _fan_coil_features(device)
        self._attr_device_info = _fan_coil_device_info(device, entry_id, source, device_id)

    @property
    def hvac_action(self) -> HVACAction:
        working_state = self._device.get("working_state")
        mapped = (
            _WORKING_STATE_TO_ACTION.get(working_state) if isinstance(working_state, str) else None
        )
        if mapped is not None:
            return mapped
        return _state_action_from_text(str(self._device.get("state", "")), self.hvac_mode)

    @property
    def fan_mode(self) -> str | None:
        relay_fan = self._device.get("fan", {}).get("relay_fan", {})
        gear = relay_fan.get("current_gear")
        if not isinstance(gear, str):
            return None
        return _GEAR_TO_FAN_MODE.get(gear)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return _fan_coil_extra_attrs(self._device)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        gear = _FAN_MODE_TO_GEAR.get(fan_mode)
        if not gear:
            _LOGGER.warning("Unknown fan mode: %s", fan_mode)
            return
        try:
            updated = await self._patch({"fan.manual_fan_gear": gear})
        except Exception as err:
            raise HomeAssistantError(f"Cannot set fan mode: {err}") from err
        if updated:
            self._device.update(updated)
        self.async_write_ha_state()
