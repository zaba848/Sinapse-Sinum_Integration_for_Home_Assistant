from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SinumConfigEntry
from .const import DOMAIN, TEMP_MAX, TEMP_MIN
from .coordinator import SinumCoordinator

_LOGGER = logging.getLogger(__name__)

# Sinum thermostat modes → HA HVAC modes
_MODE_TO_HVAC: dict[str, HVACMode] = {
    "heating": HVACMode.HEAT,
    "cooling": HVACMode.COOL,
    "automatic": HVACMode.AUTO,
    "off": HVACMode.OFF,
}
_HVAC_TO_MODE: dict[HVACMode, str] = {v: k for k, v in _MODE_TO_HVAC.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SinumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SinumCoordinator = entry.runtime_data
    entities = [
        SinumThermostat(coordinator, device_id, entry.entry_id)
        for device_id in coordinator.virtual_devices
        if _is_thermostat(coordinator.virtual_devices[device_id])
    ]
    async_add_entities(entities)


def _is_thermostat(device: dict[str, Any]) -> bool:
    return device.get("type") == "thermostat" or (
        "target_temperature" in device and "temperature" in device
    )


def _available_hvac_modes(device: dict[str, Any]) -> list[HVACMode]:
    modes = [HVACMode.OFF]
    for sinum_mode in device.get("available_work_modes", ["heating"]):
        ha_mode = _MODE_TO_HVAC.get(sinum_mode)
        if ha_mode and ha_mode not in modes:
            modes.append(ha_mode)
    if len(modes) == 1:
        modes.append(HVACMode.HEAT)
    return modes


class SinumThermostat(CoordinatorEntity[SinumCoordinator], ClimateEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_target_temperature_step = 0.5
    _attr_min_temp = TEMP_MIN
    _attr_max_temp = TEMP_MAX

    def __init__(self, coordinator: SinumCoordinator, device_id: int, entry_id: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry_id}_virtual_{device_id}"
        device = coordinator.virtual_devices.get(device_id, {})
        self._attr_hvac_modes = _available_hvac_modes(device)
        area = device.get("_area") or device.get("_room", "")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_virtual_{device_id}")},
            name=self._build_name(device),
            manufacturer="TECH Sterowniki",
            model="Sinum Virtual Thermostat",
            suggested_area=area or None,
        )

    @staticmethod
    def _build_name(device: dict[str, Any]) -> str:
        room = device.get("_room", "")
        name = device.get("name", "Thermostat")
        return f"{room} {name}".strip() if room else name

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.virtual_devices.get(self._device_id, {})

    @property
    def name(self) -> str:
        return self._build_name(self._device)

    @property
    def current_temperature(self) -> float | None:
        raw = self._device.get("temperature")
        if raw is None:
            return None
        return self.coordinator.client.decode_temperature(raw)

    @property
    def target_temperature(self) -> float | None:
        raw = self._device.get("target_temperature")
        if raw is None:
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
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self._device
        attrs: dict[str, Any] = {}
        if "humidity" in d:
            attrs["humidity"] = self.coordinator.client.decode_temperature(d["humidity"])
        if "dew_point" in d:
            attrs["dew_point"] = self.coordinator.client.decode_temperature(d["dew_point"])
        if "schedule_id" in d:
            attrs["schedule_id"] = d["schedule_id"]
        return attrs

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        raw = self.coordinator.client.encode_temperature(temperature)
        updated = await self.coordinator.client.patch_virtual_device(
            self._device_id, {"target_temperature": raw}
        )
        if updated:
            self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        sinum_mode = _HVAC_TO_MODE.get(hvac_mode, "off")
        updated = await self.coordinator.client.patch_virtual_device(
            self._device_id, {"mode": sinum_mode}
        )
        if updated:
            self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()
