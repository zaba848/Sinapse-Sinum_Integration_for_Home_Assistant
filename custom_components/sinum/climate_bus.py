"""Bus climate entities — temperature regulator for WTP/SBUS."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ._climate_bus_mixin import _BusClimateMixin
from ._climate_helpers import (
    _HVAC_TO_MODE,
    _copy_keys_if_present,
    _has_climate_control,
    _state_action_from_text,
    _target_temperature_mode_value,
)
from .climate_fan_coil import SinumFanCoilClimate  # noqa: F401
from .const import (
    DOMAIN,
    MANUFACTURER,
    STYPE_FAN_COIL,
    WTYPE_FAN_COIL,
    WTYPE_FAN_COIL_V2,
)
from .coordinator import SinumCoordinator, via_device_for

_LOGGER = logging.getLogger(__name__)

_WTP_FAN_COIL_TYPES = {WTYPE_FAN_COIL, WTYPE_FAN_COIL_V2}


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
        manufacturer=MANUFACTURER,
        model=device.get("_parent_model") or "Sinum Temperature Regulator",
        suggested_area=area,
        via_device=via_device_for(device, entry_id),
    )


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
