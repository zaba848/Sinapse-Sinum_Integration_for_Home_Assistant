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
from .coordinator import SinumCoordinator, via_device_for

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

    # Virtual thermostats and heat pump manager
    for device_id, device in coordinator.virtual_devices.items():
        dev_type = device.get("type")
        if _is_thermostat(device):
            entities.append(SinumThermostat(coordinator, device_id, entry.entry_id))
        elif dev_type == VTYPE_HEAT_PUMP_MANAGER:
            entities.append(SinumHeatPumpManagerClimate(coordinator, device_id, entry.entry_id))

    # SBUS fan coils (full climate control: work_mode + temp + fan)
    for device_id, device in coordinator.sbus_devices.items():
        if device.get("type") == STYPE_FAN_COIL and _has_climate_control(device, source="sbus"):
            entities.append(SinumFanCoilClimate(coordinator, device_id, entry.entry_id, "sbus"))
        elif device.get("type") == "temperature_regulator":
            entities.append(
                SinumTemperatureRegulatorClimate(coordinator, device_id, entry.entry_id, "sbus")
            )

    # WTP fan coils and temperature regulators
    for device_id, device in coordinator.wtp_devices.items():
        if device.get("type") in _WTP_FAN_COIL_TYPES and _has_climate_control(device, source="wtp"):
            entities.append(SinumFanCoilClimate(coordinator, device_id, entry.entry_id, "wtp"))
        elif device.get("type") == "temperature_regulator":
            entities.append(
                SinumTemperatureRegulatorClimate(coordinator, device_id, entry.entry_id, "wtp")
            )

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


def _available_hvac_modes(device: dict[str, Any]) -> list[HVACMode]:
    modes = [HVACMode.OFF]

    # Explicit list (FanCoil may populate this); skip empty lists to fall through to inference
    declared = device.get("available_work_modes")
    if declared:
        for sinum_mode in declared:
            ha_mode = _MODE_TO_HVAC.get(sinum_mode)
            if ha_mode and ha_mode not in modes:
                modes.append(ha_mode)
        return modes

    # Infer from mode-specific temperature fields (thermostat with null available_work_modes)
    if device.get("target_temperature_heating_minimum") is not None:
        modes.append(HVACMode.HEAT)
    if device.get("target_temperature_cooling_minimum") is not None and HVACMode.COOL not in modes:
        modes.append(HVACMode.COOL)

    # Always include current active mode so it never disappears from the picker
    current = device.get("mode") or device.get("work_mode")
    if current and current not in ("off", ""):
        ha_mode = _MODE_TO_HVAC.get(current)
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
        mode = self.hvac_mode
        if mode == HVACMode.HEAT:
            mn = d.get("target_temperature_heating_minimum")
            mx = d.get("target_temperature_heating_maximum")
            if mn is not None and mx is not None:
                return mn / 10
        elif mode == HVACMode.COOL:
            mn = d.get("target_temperature_cooling_minimum")
            mx = d.get("target_temperature_cooling_maximum")
            if mn is not None and mx is not None:
                return mn / 10
        raw_min = d.get("target_temperature_minimum")
        if raw_min is not None:
            return raw_min / 10
        return TEMP_MIN

    @property
    def max_temp(self) -> float:
        d = self._device
        mode = self.hvac_mode
        if mode == HVACMode.HEAT:
            mn = d.get("target_temperature_heating_minimum")
            mx = d.get("target_temperature_heating_maximum")
            if mn is not None and mx is not None:
                return mx / 10
        elif mode == HVACMode.COOL:
            mn = d.get("target_temperature_cooling_minimum")
            mx = d.get("target_temperature_cooling_maximum")
            if mn is not None and mx is not None:
                return mx / 10
        raw_max = d.get("target_temperature_maximum")
        if raw_max is not None:
            return raw_max / 10
        return TEMP_MAX

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self._device
        decode = self.coordinator.client.decode_temperature
        attrs: dict[str, Any] = {}
        if d.get("humidity") is not None:
            attrs["humidity"] = decode(d["humidity"])
        if d.get("dew_point") is not None:
            attrs["dew_point"] = decode(d["dew_point"])
        if d.get("floor_temperature") is not None:
            attrs["floor_temperature"] = decode(d["floor_temperature"])
        if d.get("target_temperature_heating") is not None:
            attrs["target_temperature_heating"] = decode(d["target_temperature_heating"])
        if d.get("target_temperature_cooling") is not None:
            attrs["target_temperature_cooling"] = decode(d["target_temperature_cooling"])
        if "target_temperature_mode" in d:
            ttm = d["target_temperature_mode"]
            attrs["target_temperature_mode"] = (
                ttm.get("current") or ttm.get("mode") if isinstance(ttm, dict) else ttm
            )
        if "is_window_open" in d:
            attrs["is_window_open"] = d["is_window_open"]
        if "schedule_id" in d:
            attrs["schedule_id"] = d["schedule_id"]
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
        if working_state and working_state in _WORKING_STATE_TO_ACTION:
            return _WORKING_STATE_TO_ACTION[working_state]
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
        if "target_temperature_mode" in d:
            ttm = d["target_temperature_mode"]
            attrs["target_temperature_mode"] = (
                ttm.get("current") or ttm.get("mode") if isinstance(ttm, dict) else ttm
            )
        manual_gear = d.get("fan", {}).get("manual_fan_gear")
        if manual_gear:
            attrs["manual_fan_gear"] = manual_gear
        if working_state := d.get("working_state"):
            attrs["working_state"] = working_state
        return attrs

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
        state = str(self._device.get("state", ""))
        if "heating" in state:
            return HVACAction.HEATING
        if "cooling" in state:
            return HVACAction.COOLING
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        return HVACAction.IDLE

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self._device
        attrs: dict[str, Any] = {}
        if "mode_mutable" in d:
            attrs["mode_mutable"] = d["mode_mutable"]
        if "parent_id" in d:
            attrs["parent_id"] = d["parent_id"]
        if "target_temperature_mode" in d:
            ttm = d["target_temperature_mode"]
            attrs["target_temperature_mode"] = (
                ttm.get("current") or ttm.get("mode") if isinstance(ttm, dict) else ttm
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


class SinumHeatPumpManagerClimate(CoordinatorEntity[SinumCoordinator], ClimateEntity):
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
        attrs: dict[str, Any] = {}
        tt = d.get("target_temperature")
        if isinstance(tt, dict):
            decode = self.coordinator.client.decode_temperature
            for k in ("heating", "cooling", "automatic"):
                if tt.get(k) is not None:
                    attrs[f"target_temperature_{k}"] = decode(tt[k])
        dhw = d.get("dhw_control")
        if isinstance(dhw, dict):
            if dhw.get("target_temperature") is not None:
                attrs["dhw_target_temperature"] = self.coordinator.client.decode_temperature(
                    dhw["target_temperature"]
                )
            if "state" in dhw:
                attrs["dhw_state"] = dhw["state"]
        return attrs

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        raw = self.coordinator.client.encode_temperature(
            max(self.min_temp, min(self.max_temp, temperature))
        )
        tt = self._device.get("target_temperature")
        if isinstance(tt, dict):
            payload: dict[str, Any] = {"target_temperature": {"current": raw}}
        else:
            payload = {"target_temperature": raw}
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
