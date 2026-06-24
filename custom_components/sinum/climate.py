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
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SinumConfigEntry
from .const import (
    DOMAIN,
    STYPE_FAN_COIL,
    TEMP_MAX,
    TEMP_MIN,
    VTYPE_HEAT_PUMP_MANAGER,
    WTYPE_FAN_COIL,
    WTYPE_FAN_COIL_V2,
)
from .coordinator import SinumCoordinator, SinumDeviceAvailableMixin, via_device_for

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


def _add_virtual_climate(
    coordinator: SinumCoordinator, entities: list[ClimateEntity], entry_id: str
) -> None:
    for device_id, device in coordinator.virtual_devices.items():
        if _is_thermostat(device):
            entities.append(SinumThermostat(coordinator, device_id, entry_id))
        elif device.get("type") == VTYPE_HEAT_PUMP_MANAGER:
            entities.append(SinumHeatPumpManagerClimate(coordinator, device_id, entry_id))


def _add_bus_climate(
    coordinator: SinumCoordinator, entities: list[ClimateEntity], entry_id: str, bus: str
) -> None:
    store = coordinator.sbus_devices if bus == "sbus" else coordinator.wtp_devices
    fan_coil_types = {STYPE_FAN_COIL} if bus == "sbus" else _WTP_FAN_COIL_TYPES
    for device_id, device in store.items():
        dev_type = device.get("type")
        if dev_type in fan_coil_types and _has_climate_control(device, source=bus):
            entities.append(SinumFanCoilClimate(coordinator, device_id, entry_id, bus))
        elif dev_type == "temperature_regulator":
            entities.append(SinumTemperatureRegulatorClimate(coordinator, device_id, entry_id, bus))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SinumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SinumCoordinator = entry.runtime_data
    entities: list[ClimateEntity] = []
    _add_virtual_climate(coordinator, entities, entry.entry_id)
    _add_bus_climate(coordinator, entities, entry.entry_id, "sbus")
    _add_bus_climate(coordinator, entities, entry.entry_id, "wtp")
    async_add_entities(entities)


def _is_thermostat(device: dict[str, Any]) -> bool:
    return device.get("type") == "thermostat" or (
        "target_temperature" in device and "temperature" in device and "work_mode" not in device
    )


def _has_climate_control(device: dict[str, Any], source: str = "sbus") -> bool:
    """Check if fan_coil can be exposed as climate entity.

    Fan coil climate entities need both mode and setpoint controls. Devices that
    only report room temperature or fan state should stay as sensors/diagnostics.
    """
    return "work_mode" in device and "target_temperature" in device


def _modes_from_declared(declared: list[str]) -> list[HVACMode]:
    """Build HA mode list from Sinum available_work_modes field."""
    modes: list[HVACMode] = [HVACMode.OFF]
    for sinum_mode in declared:
        ha_mode = _MODE_TO_HVAC.get(sinum_mode)
        if ha_mode and ha_mode not in modes:
            modes.append(ha_mode)
    return modes


def _append_if_supported(modes: list[HVACMode], mode: HVACMode, condition: bool) -> None:
    if condition and mode not in modes:
        modes.append(mode)


def _infer_current_mode(device: dict[str, Any], modes: list[HVACMode]) -> None:
    current = device.get("mode") or device.get("work_mode")
    if not current or current in ("off", ""):
        return
    ha_mode = _MODE_TO_HVAC.get(current)
    _append_if_supported(modes, ha_mode, ha_mode is not None)


def _infer_modes(device: dict[str, Any]) -> list[HVACMode]:
    """Infer HVAC mode list from temperature field presence when hub lists no modes."""
    modes: list[HVACMode] = [HVACMode.OFF]
    _append_if_supported(
        modes, HVACMode.HEAT, device.get("target_temperature_heating_minimum") is not None
    )
    _append_if_supported(
        modes, HVACMode.COOL, device.get("target_temperature_cooling_minimum") is not None
    )
    _infer_current_mode(device, modes)
    if len(modes) == 1:
        modes.append(HVACMode.HEAT)
    return modes


def _available_hvac_modes(device: dict[str, Any]) -> list[HVACMode]:
    if declared := device.get("available_work_modes"):
        return _modes_from_declared(declared)
    return _infer_modes(device)


def _active_mode_bounds(device: dict[str, Any], mode: HVACMode) -> tuple[Any, Any]:
    if mode == HVACMode.HEAT:
        return (
            device.get("target_temperature_heating_minimum"),
            device.get("target_temperature_heating_maximum"),
        )
    if mode == HVACMode.COOL:
        return (
            device.get("target_temperature_cooling_minimum"),
            device.get("target_temperature_cooling_maximum"),
        )
    return None, None


def _scaled_or_default(raw: Any, default: float) -> float:
    if raw is None:
        return default
    return raw / 10


def _target_temperature_mode_value(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("current") or value.get("mode")
    return value


def _copy_keys_if_present(
    source: dict[str, Any], target: dict[str, Any], keys: tuple[str, ...]
) -> None:
    for key in keys:
        if key in source:
            target[key] = source[key]


def _state_action_from_text(state: str, current_mode: HVACMode) -> HVACAction:
    if "heating" in state:
        return HVACAction.HEATING
    if "cooling" in state:
        return HVACAction.COOLING
    if current_mode == HVACMode.OFF:
        return HVACAction.OFF
    return HVACAction.IDLE


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


def _add_fan_gear_attr(device: dict[str, Any], attrs: dict[str, Any]) -> None:
    manual_gear = device.get("fan", {}).get("manual_fan_gear")
    if manual_gear:
        attrs["manual_fan_gear"] = manual_gear


def _add_working_state_attr(device: dict[str, Any], attrs: dict[str, Any]) -> None:
    working_state = device.get("working_state")
    if working_state:
        attrs["working_state"] = working_state


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
            manufacturer="TECH Sterowniki",
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
        if raw is None:
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

        # Dynamically determine supported features based on available fields.
        features = ClimateEntityFeature(0)
        if "target_temperature" in device:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE
        if "fan" in device or device.get("fan_operation_mode"):
            features |= ClimateEntityFeature.FAN_MODE
        self._attr_supported_features = features

        area = device.get("_area") or None
        label = device.get("_device_name") or device.get("name", str(device_id))

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{source}_{device_id}")},
            name=label,
            manufacturer="TECH Sterowniki",
            model=device.get("_parent_model") or f"Sinum {source.upper()} Fan Coil",
            suggested_area=area,
            via_device=via_device_for(device, entry_id),
        )

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

        store = coordinator.sbus_devices if bus == "sbus" else coordinator.wtp_devices
        device = store.get(device_id, {})

        # Dynamic features based on mode_mutable
        features = ClimateEntityFeature.TARGET_TEMPERATURE
        if device.get("mode_mutable", True):
            features |= ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        self._attr_supported_features = features

        area = device.get("_area") or None
        label = device.get("_device_name") or device.get("name", str(device_id))

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{bus}_regulator_{device_id}")},
            name=label,
            manufacturer="TECH Sterowniki",
            model=device.get("_parent_model") or "Sinum Temperature Regulator",
            suggested_area=area,
            via_device=via_device_for(device, entry_id),
        )

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
            manufacturer="TECH Sterowniki",
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
        raw = self.coordinator.client.encode_temperature(
            max(self.min_temp, min(self.max_temp, temperature))
        )
        tt = self._device.get("target_temperature")
        payload: dict[str, Any] = (
            {"target_temperature": {"current": raw}}
            if isinstance(tt, dict)
            else {"target_temperature": raw}
        )
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
