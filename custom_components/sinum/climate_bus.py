from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ._climate_helpers import (
    _HVAC_TO_MODE,
    _MODE_TO_HVAC,
    _available_hvac_modes,
    _copy_keys_if_present,
    _has_climate_control,
    _state_action_from_text,
    _target_temperature_mode_value,
)
from .const import DOMAIN, STYPE_FAN_COIL, TEMP_MAX, TEMP_MIN, WTYPE_FAN_COIL, WTYPE_FAN_COIL_V2
from .coordinator import SinumCoordinator, via_device_for

_LOGGER = logging.getLogger(__name__)

# SBUS fan_coil working_state → HA HVAC action
_WORKING_STATE_TO_ACTION: dict[str, HVACAction] = {
    "heating_active": HVACAction.HEATING,
    "cooling_active": HVACAction.COOLING,
    "idle": HVACAction.IDLE,
    "off": HVACAction.OFF,
}

# Fan gear relay → HA fan mode string
_GEAR_TO_FAN_MODE: dict[str, str] = {
    "first": "1",
    "second": "2",
    "third": "3",
}
_FAN_MODE_TO_GEAR: dict[str, str] = {v: k for k, v in _GEAR_TO_FAN_MODE.items()}
_FAN_MODES: list[str] = ["1", "2", "3"]
_WTP_FAN_COIL_TYPES = {WTYPE_FAN_COIL, WTYPE_FAN_COIL_V2}


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
        manufacturer="TECH Sterowniki",
        model=device.get("_parent_model") or f"Sinum {source.upper()} Fan Coil",
        suggested_area=area,
        via_device=via_device_for(device, entry_id),
    )


def _bus_store(coordinator: SinumCoordinator, bus: str) -> dict[int, dict[str, Any]]:
    return coordinator.sbus_devices if bus == "sbus" else coordinator.wtp_devices


def _regulator_features(device: dict[str, Any]) -> ClimateEntityFeature:
    features = ClimateEntityFeature.TARGET_TEMPERATURE
    if device.get("mode_mutable", True):
        features |= ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
    return features


def _regulator_device_info(
    device: dict[str, Any], entry_id: str, bus: str, device_id: int
) -> DeviceInfo:
    area = device.get("_area") or None
    label = device.get("_device_name") or device.get("name", str(device_id))
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_{bus}_regulator_{device_id}")},
        name=label,
        manufacturer="TECH Sterowniki",
        model=device.get("_parent_model") or "Sinum Temperature Regulator",
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


def _bus_climate_config(
    coordinator: SinumCoordinator, bus: str
) -> tuple[dict[int, dict[str, Any]], set[str]]:
    if bus == "sbus":
        return coordinator.sbus_devices, {STYPE_FAN_COIL}
    return coordinator.wtp_devices, _WTP_FAN_COIL_TYPES


def _maybe_add_climate_entity(
    coordinator: SinumCoordinator,
    entities: list[ClimateEntity],
    entry_id: str,
    bus: str,
    device_id: int,
    device: dict[str, Any],
    fan_coil_types: set[str],
) -> None:
    dev_type = device.get("type")
    if dev_type in fan_coil_types and _has_climate_control(device, source=bus):
        entities.append(SinumFanCoilClimate(coordinator, device_id, entry_id, bus))
    elif dev_type == "temperature_regulator":
        entities.append(SinumTemperatureRegulatorClimate(coordinator, device_id, entry_id, bus))


def _add_bus_climate(
    coordinator: SinumCoordinator, entities: list[ClimateEntity], entry_id: str, bus: str
) -> None:
    store, fan_coil_types = _bus_climate_config(coordinator, bus)
    for device_id, device in store.items():
        _maybe_add_climate_entity(
            coordinator, entities, entry_id, bus, device_id, device, fan_coil_types
        )


class _BusClimateMixin:
    """Shared helpers for WTP/SBUS climate entities."""

    _device_id: int
    _current_temperature_key = "temperature"
    _mode_key = "system_mode"
    _patch_mode_key = "system_mode"

    if TYPE_CHECKING:
        coordinator: SinumCoordinator

        def async_write_ha_state(self) -> None: ...

    @property
    def _bus_name(self) -> str:
        return getattr(self, "_source", getattr(self, "_bus", "wtp"))

    def _device_dict(self, coordinator: SinumCoordinator) -> dict[str, Any]:
        if self._bus_name == "sbus":
            return coordinator.sbus_devices.get(self._device_id, {})
        return coordinator.wtp_devices.get(self._device_id, {})

    @property
    def _device(self) -> dict[str, Any]:
        return self._device_dict(self.coordinator)

    @property
    def current_temperature(self) -> float | None:
        raw = self._device.get(self._current_temperature_key)
        if not raw:
            return None
        return raw / 10

    @property
    def target_temperature(self) -> float | None:
        raw = self._device.get("target_temperature")
        if not raw:
            return None
        return raw / 10

    @property
    def hvac_modes(self) -> list[HVACMode]:
        return _available_hvac_modes(self._device)

    @property
    def min_temp(self) -> float:
        raw_min = self._device.get("target_temperature_minimum")
        if raw_min is not None:
            return raw_min / 10
        return TEMP_MIN

    @property
    def max_temp(self) -> float:
        raw_max = self._device.get("target_temperature_maximum")
        if raw_max is not None:
            return raw_max / 10
        return TEMP_MAX

    @property
    def hvac_mode(self) -> HVACMode:
        mode = self._device.get(self._mode_key, "off")
        return _MODE_TO_HVAC.get(mode, HVACMode.OFF)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        raw = round(max(self.min_temp, min(self.max_temp, temperature)) * 10)
        try:
            updated = await self._patch({"target_temperature": raw})
        except Exception as err:
            raise HomeAssistantError(f"Cannot set temperature: {err}") from err
        if updated:
            self._device.update(updated)
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        sinum_mode = _HVAC_TO_MODE.get(hvac_mode, "off")
        try:
            updated = await self._patch({self._patch_mode_key: sinum_mode})
        except Exception as err:
            raise HomeAssistantError(f"Cannot set HVAC mode: {err}") from err
        if updated:
            self._device.update(updated)
        self.async_write_ha_state()

    async def _patch(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._bus_name == "sbus":
            return await self.coordinator.client.patch_sbus_device(self._device_id, payload)
        return await self.coordinator.client.patch_wtp_device(self._device_id, payload)


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


class SinumTemperatureRegulatorClimate(
    _BusClimateMixin, CoordinatorEntity[SinumCoordinator], ClimateEntity
):
    """Climate entity for WTP/SBUS temperature regulators."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_translation_key = "temperature_regulator"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_icon = "mdi:home-thermometer-outline"

    def __init__(
        self, coordinator: SinumCoordinator, device_id: int, entry_id: str, bus: str = "wtp"
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._bus = bus
        self._attr_unique_id = f"{entry_id}_{bus}_regulator_{device_id}"
        device = _bus_store(coordinator, bus).get(device_id, {})
        self._attr_supported_features = _regulator_features(device)
        self._attr_device_info = _regulator_device_info(device, entry_id, bus, device_id)

    @property
    def hvac_action(self) -> HVACAction:
        return _state_action_from_text(str(self._device.get("state", "")), self.hvac_mode)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self._device
        attrs: dict[str, Any] = {}
        _copy_keys_if_present(d, attrs, ("mode_mutable", "parent_id"))
        if "target_temperature_mode" in d:
            attrs["target_temperature_mode"] = _target_temperature_mode_value(
                d["target_temperature_mode"]
            )
        return attrs

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if not self._device.get("mode_mutable", True):
            _LOGGER.warning(
                "Temperature regulator %d does not allow mode changes (mode_mutable=false)",
                self._device_id,
            )
            return
        system_mode = _HVAC_TO_MODE.get(hvac_mode, "off")
        try:
            updated = await self._patch({"system_mode": system_mode})
        except Exception as err:
            raise HomeAssistantError(f"Cannot set HVAC mode: {err}") from err
        if updated:
            self._device.update(updated)
        self.async_write_ha_state()

    async def async_turn_on(self) -> None:
        try:
            updated = await self._patch({"system_mode": "heating"})
        except Exception as err:
            raise HomeAssistantError(f"Cannot turn on: {err}") from err
        if updated:
            self._device.update(updated)
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        try:
            updated = await self._patch({"system_mode": "off"})
        except Exception as err:
            raise HomeAssistantError(f"Cannot turn off: {err}") from err
        if updated:
            self._device.update(updated)
        self.async_write_ha_state()
