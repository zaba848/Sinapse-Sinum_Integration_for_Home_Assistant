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
from .const import (
    DOMAIN,
    STYPE_FAN_COIL,
    TEMP_MAX,
    TEMP_MIN,
    WTYPE_FAN_COIL,
    WTYPE_FAN_COIL_V2,
)
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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SinumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SinumCoordinator = entry.runtime_data
    entities: list[ClimateEntity] = []

    # Virtual thermostats
    for device_id in coordinator.virtual_devices:
        if _is_thermostat(coordinator.virtual_devices[device_id]):
            entities.append(SinumThermostat(coordinator, device_id, entry.entry_id))

    # SBUS fan coils (full climate control: work_mode + temp + fan)
    for device_id, device in coordinator.sbus_devices.items():
        if device.get("type") == STYPE_FAN_COIL and _has_climate_control(device):
            entities.append(SinumFanCoilClimate(coordinator, device_id, entry.entry_id, "sbus"))

    # WTP fan coils are only exposed as climate entities when firmware returns
    # full climate fields. The verified hub exposes several WTP fan coils with
    # metadata/fan status only, so those remain diagnostics until payloads grow.
    for device_id, device in coordinator.wtp_devices.items():
        if device.get("type") in _WTP_FAN_COIL_TYPES and _has_climate_control(device):
            entities.append(SinumFanCoilClimate(coordinator, device_id, entry.entry_id, "wtp"))

    async_add_entities(entities)


def _is_thermostat(device: dict[str, Any]) -> bool:
    return device.get("type") == "thermostat" or (
        "target_temperature" in device and "temperature" in device
        and "work_mode" not in device
    )


def _has_climate_control(device: dict[str, Any]) -> bool:
    """True if fan_coil has work_mode and target_temperature (full SBUS variant)."""
    return "work_mode" in device and "target_temperature" in device


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


class SinumFanCoilClimate(CoordinatorEntity[SinumCoordinator], ClimateEntity):
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
        self._attr_hvac_modes = _available_hvac_modes(device)

        # Use per-device temperature limits from API if available
        raw_min = device.get("target_temperature_minimum")
        raw_max = device.get("target_temperature_maximum")
        self._attr_min_temp = raw_min / 10 if raw_min is not None else TEMP_MIN
        self._attr_max_temp = raw_max / 10 if raw_max is not None else TEMP_MAX

        area = device.get("_area") or None
        room = device.get("_room", "")
        name = device.get("_device_name") or device.get("name", str(device_id))
        label = f"{room} {name}".strip() if room else name

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{source}_{device_id}")},
            name=label,
            manufacturer="TECH Sterowniki",
            model=f"Sinum {source.upper()} Fan Coil",
            suggested_area=area,
        )

    def _device_dict(self, coordinator: SinumCoordinator) -> dict[str, Any]:
        if self._source == "sbus":
            return coordinator.sbus_devices.get(self._device_id, {})
        return coordinator.wtp_devices.get(self._device_id, {})

    @property
    def _device(self) -> dict[str, Any]:
        return self._device_dict(self.coordinator)

    @property
    def name(self) -> str:
        d = self._device
        room = d.get("_room", "")
        name = d.get("_device_name") or d.get("name", str(self._device_id))
        return f"{room} {name}".strip() if room else name

    @property
    def current_temperature(self) -> float | None:
        raw = self._device.get("room_temperature")
        if raw is None:
            return None
        return raw / 10

    @property
    def target_temperature(self) -> float | None:
        raw = self._device.get("target_temperature")
        if raw is None:
            return None
        return raw / 10

    @property
    def hvac_mode(self) -> HVACMode:
        mode = self._device.get("work_mode", "off")
        return _MODE_TO_HVAC.get(mode, HVACMode.OFF)

    @property
    def hvac_action(self) -> HVACAction:
        working_state = self._device.get("working_state")
        if working_state:
            return _WORKING_STATE_TO_ACTION.get(working_state, HVACAction.IDLE)
        # Fallback: infer from state field
        state = str(self._device.get("state", ""))
        if "heating" in state:
            return HVACAction.HEATING
        if "cooling" in state:
            return HVACAction.COOLING
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        return HVACAction.IDLE

    @property
    def fan_mode(self) -> str | None:
        relay_fan = self._device.get("fan", {}).get("relay_fan", {})
        gear = relay_fan.get("current_gear")
        return _GEAR_TO_FAN_MODE.get(gear)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self._device
        attrs: dict[str, Any] = {}
        if fan_op := d.get("fan_operation_mode"):
            attrs["fan_operation_mode"] = fan_op
        if sched := d.get("schedule_id"):
            attrs["schedule_id"] = sched
        if d.get("mode_mutable") is not None:
            attrs["mode_mutable"] = d["mode_mutable"]
        manual_gear = d.get("fan", {}).get("manual_fan_gear")
        if manual_gear:
            attrs["manual_fan_gear"] = manual_gear
        return attrs

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        raw = round(temperature * 10)
        updated = await self._patch({"target_temperature": raw})
        if updated:
            self._device.update(updated)
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        work_mode = _HVAC_TO_MODE.get(hvac_mode, "off")
        updated = await self._patch({"work_mode": work_mode})
        if updated:
            self._device.update(updated)
        self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        gear = _FAN_MODE_TO_GEAR.get(fan_mode)
        if not gear:
            _LOGGER.warning("Unknown fan mode: %s", fan_mode)
            return
        updated = await self._patch({"fan.manual_fan_gear": gear})
        if updated:
            self._device.update(updated)
        self.async_write_ha_state()

    async def _patch(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._source == "sbus":
            return await self.coordinator.client.patch_sbus_device(self._device_id, payload)
        return await self.coordinator.client.patch_wtp_device(self._device_id, payload)
