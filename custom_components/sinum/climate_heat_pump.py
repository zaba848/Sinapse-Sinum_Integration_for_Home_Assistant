"""Heat pump manager climate entity."""

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

from ._climate_helpers import _HVAC_TO_MODE, _MODE_TO_HVAC
from .const import DOMAIN, MANUFACTURER, TEMP_MAX, TEMP_MIN
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

    async def _patch_and_apply(self, payload: dict[str, Any], err_msg: str) -> None:
        try:
            updated = await self.coordinator.client.patch_virtual_device(self._device_id, payload)
        except Exception as err:
            raise HomeAssistantError(f"{err_msg}: {err}") from err
        if updated:
            self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def _patch_virtual_temperature(self, payload: dict[str, Any]) -> None:
        await self._patch_and_apply(payload, "Cannot set temperature")

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            payload: dict[str, Any] = {"enabled": False}
        else:
            sinum_mode = _HVAC_TO_MODE.get(hvac_mode, "heating")
            payload = {"enabled": True, "work_mode": sinum_mode}
        await self._patch_and_apply(payload, "Cannot set HVAC mode")

    async def async_turn_on(self) -> None:
        await self._patch_and_apply({"enabled": True}, "Cannot turn on")

    async def async_turn_off(self) -> None:
        await self._patch_and_apply({"enabled": False}, "Cannot turn off")
