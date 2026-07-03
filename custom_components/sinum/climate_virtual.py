from __future__ import annotations

from typing import Any

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
    _active_mode_bounds,
    _available_hvac_modes,
    _copy_keys_if_present,
    _is_thermostat,
    _scaled_or_default,
    _target_temperature_mode_value,
)
from .const import DOMAIN, MANUFACTURER, TEMP_MAX, TEMP_MIN, VTYPE_HEAT_PUMP_MANAGER
from .coordinator import SinumCoordinator, SinumDeviceAvailableMixin


def _heat_pump_target_temp_attrs(device: dict[str, Any], decode: Any) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    tt = device.get("target_temperature")
    if not isinstance(tt, dict):
        return attrs
    for key in ("heating", "cooling", "automatic"):
        value = tt.get(key)
        if value is not None:
            attrs[f"target_temperature_{key}"] = decode(value)
    return attrs


def _heat_pump_dhw_attrs(device: dict[str, Any], decode: Any) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    dhw = device.get("dhw_control")
    if not isinstance(dhw, dict):
        return attrs
    target = dhw.get("target_temperature")
    if target is not None:
        attrs["dhw_target_temperature"] = decode(target)
    if "state" in dhw:
        attrs["dhw_state"] = dhw["state"]
    return attrs


def _add_virtual_climate(
    coordinator: SinumCoordinator, entities: list[ClimateEntity], entry_id: str
) -> None:
    for device_id, device in coordinator.virtual_devices.items():
        if _is_thermostat(device):
            entities.append(SinumThermostat(coordinator, device_id, entry_id))
        elif device.get("type") == VTYPE_HEAT_PUMP_MANAGER:
            entities.append(SinumHeatPumpManagerClimate(coordinator, device_id, entry_id))


class SinumThermostat(
    SinumDeviceAvailableMixin, CoordinatorEntity[SinumCoordinator], ClimateEntity
):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_target_temperature_step = 0.5
    _attr_icon = "mdi:home-thermometer"

    def __init__(self, coordinator: SinumCoordinator, device_id: int, entry_id: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry_id}_virtual_{device_id}"
        device = coordinator.virtual_devices.get(device_id, {})
        area = device.get("_area") or device.get("_room", "")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_virtual_{device_id}")},
            name=self._build_name(device),
            manufacturer=MANUFACTURER,
            model="Sinum Virtual Thermostat",
            suggested_area=area or None,
        )

    @staticmethod
    def _build_name(device: dict[str, Any]) -> str:
        return device.get("_device_name") or device.get("name", "Thermostat")

    @property
    def hvac_modes(self) -> list[HVACMode]:
        return _available_hvac_modes(self._device)

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.virtual_devices.get(self._device_id, {})

    @property
    def current_temperature(self) -> float | None:
        raw = self._device.get("temperature")
        if not raw:
            return None
        return self.coordinator.client.decode_temperature(raw)

    @property
    def target_temperature(self) -> float | None:
        raw = self._device.get("target_temperature")
        if not raw:
            return None
        return self.coordinator.client.decode_temperature(raw)

    @property
    def hvac_mode(self) -> HVACMode:
        mode = self._device.get("mode", "off")
        return _MODE_TO_HVAC.get(mode, HVACMode.OFF)

    @property
    def hvac_action(self) -> HVACAction:
        # `state: true` means the thermostat is actively heating/cooling
        if self._device.get("state") is True:
            mode = self._device.get("mode", "")
            if mode == "cooling":
                return HVACAction.COOLING
            return HVACAction.HEATING
        current_mode = self.hvac_mode
        if current_mode == HVACMode.OFF:
            return HVACAction.OFF
        return HVACAction.IDLE

    @property
    def min_temp(self) -> float:
        d = self._device
        mn, mx = _active_mode_bounds(d, self.hvac_mode)
        if mn is not None and mx is not None:
            return mn / 10
        return _scaled_or_default(d.get("target_temperature_minimum"), TEMP_MIN)

    @property
    def max_temp(self) -> float:
        d = self._device
        mn, mx = _active_mode_bounds(d, self.hvac_mode)
        if mn is not None and mx is not None:
            return mx / 10
        return _scaled_or_default(d.get("target_temperature_maximum"), TEMP_MAX)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self._device
        decode = self.coordinator.client.decode_temperature
        _temp_keys = (
            "humidity",
            "dew_point",
            "floor_temperature",
            "target_temperature_heating",
            "target_temperature_cooling",
        )
        attrs: dict[str, Any] = {k: decode(d[k]) for k in _temp_keys if d.get(k) is not None}
        if "target_temperature_mode" in d:
            attrs["target_temperature_mode"] = _target_temperature_mode_value(
                d["target_temperature_mode"]
            )
        _copy_keys_if_present(d, attrs, ("is_window_open", "schedule_id"))
        return attrs

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        raw = self.coordinator.client.encode_temperature(
            max(self.min_temp, min(self.max_temp, temperature))
        )
        try:
            updated = await self.coordinator.client.patch_virtual_device(
                self._device_id, {"target_temperature": raw}
            )
        except Exception as err:
            raise HomeAssistantError(f"Cannot set temperature: {err}") from err
        if updated:
            self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        sinum_mode = _HVAC_TO_MODE.get(hvac_mode, "off")
        try:
            updated = await self.coordinator.client.patch_virtual_device(
                self._device_id, {"mode": sinum_mode}
            )
        except Exception as err:
            raise HomeAssistantError(f"Cannot set HVAC mode: {err}") from err
        if updated:
            self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()


class SinumHeatPumpManagerClimate(
    SinumDeviceAvailableMixin, CoordinatorEntity[SinumCoordinator], ClimateEntity
):
    """Virtual heat_pump_manager — controls heat pump work mode and target temperature."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_translation_key = "heat_pump_manager"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_target_temperature_step = 0.5
    _attr_min_temp = TEMP_MIN
    _attr_max_temp = TEMP_MAX
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.AUTO]
    _attr_icon = "mdi:heat-pump"

    def __init__(self, coordinator: SinumCoordinator, device_id: int, entry_id: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry_id}_virtual_{device_id}"
        device = coordinator.virtual_devices.get(device_id, {})
        area = device.get("_area") or device.get("_room", "")
        label = device.get("_device_name") or device.get("name", "Heat Pump Manager")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_virtual_{device_id}")},
            name=label,
            manufacturer=MANUFACTURER,
            model="Sinum Heat Pump Manager",
            suggested_area=area or None,
        )

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.virtual_devices.get(self._device_id, {})

    @property
    def current_temperature(self) -> float | None:
        raw = self._device.get("temperature")
        if raw is None:
            return None
        return self.coordinator.client.decode_temperature(raw)

    @property
    def target_temperature(self) -> float | None:
        tt = self._device.get("target_temperature")
        if tt is None:
            return None
        raw = tt.get("current") if isinstance(tt, dict) else tt
        if raw is None:
            return None
        return self.coordinator.client.decode_temperature(raw)

    @property
    def hvac_mode(self) -> HVACMode:
        if not self._device.get("enabled", True):
            return HVACMode.OFF
        mode = self._device.get("work_mode", "off")
        return _MODE_TO_HVAC.get(mode, HVACMode.OFF)

    @property
    def hvac_action(self) -> HVACAction:
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        if self._device.get("state") is True:
            mode = self._device.get("work_mode", "")
            if mode == "cooling":
                return HVACAction.COOLING
            return HVACAction.HEATING
        return HVACAction.IDLE

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self._device
        decode = self.coordinator.client.decode_temperature
        attrs = _heat_pump_target_temp_attrs(d, decode)
        attrs.update(_heat_pump_dhw_attrs(d, decode))
        return attrs

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        payload = self._build_temperature_payload(temperature)
        await self._patch_virtual_temperature(payload)

    def _build_temperature_payload(self, temperature: float) -> dict[str, Any]:
        raw = self.coordinator.client.encode_temperature(
            max(self.min_temp, min(self.max_temp, temperature))
        )
        tt = self._device.get("target_temperature")
        if isinstance(tt, dict):
            return {"target_temperature": {"current": raw}}
        return {"target_temperature": raw}

    async def _patch_virtual_temperature(self, payload: dict[str, Any]) -> None:
        try:
            updated = await self.coordinator.client.patch_virtual_device(self._device_id, payload)
        except Exception as err:
            raise HomeAssistantError(f"Cannot set temperature: {err}") from err
        if updated:
            self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        try:
            if hvac_mode == HVACMode.OFF:
                updated = await self.coordinator.client.patch_virtual_device(
                    self._device_id, {"enabled": False}
                )
            else:
                sinum_mode = _HVAC_TO_MODE.get(hvac_mode, "heating")
                updated = await self.coordinator.client.patch_virtual_device(
                    self._device_id, {"enabled": True, "work_mode": sinum_mode}
                )
        except Exception as err:
            raise HomeAssistantError(f"Cannot set HVAC mode: {err}") from err
        if updated:
            self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_turn_on(self) -> None:
        try:
            updated = await self.coordinator.client.patch_virtual_device(
                self._device_id, {"enabled": True}
            )
        except Exception as err:
            raise HomeAssistantError(f"Cannot turn on: {err}") from err
        if updated:
            self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        try:
            updated = await self.coordinator.client.patch_virtual_device(
                self._device_id, {"enabled": False}
            )
        except Exception as err:
            raise HomeAssistantError(f"Cannot turn off: {err}") from err
        if updated:
            self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()
