from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SinumConfigEntry
from ._bus_registry import bus_patch_method
from ._bus_registry import bus_store as _shared_bus_store
from .climate_fan_coil import _fan_coil_device_info
from .const import (
    STYPE_FAN_COIL,
    WTYPE_FAN_COIL,
    WTYPE_FAN_COIL_V2,
)
from .coordinator import SinumCoordinator, SinumDeviceAvailableMixin

PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)

_GEAR_ORDER: tuple[str, ...] = ("first", "second", "third")
_GEAR_TO_PRESET: dict[str, str] = {
    "first": "1",
    "second": "2",
    "third": "3",
}
_PRESET_TO_GEAR: dict[str, str] = {v: k for k, v in _GEAR_TO_PRESET.items()}
_PRESETS: list[str] = ["1", "2", "3"]

_WTP_FAN_COIL_TYPES = {WTYPE_FAN_COIL, WTYPE_FAN_COIL_V2}


def _has_fan_control(device: dict[str, Any]) -> bool:
    return "fan" in device and "work_mode" in device


def _output_type(device: dict[str, Any]) -> str:
    return device.get("fan", {}).get("output_type", "relay")


def _current_gear(device: dict[str, Any]) -> str | None:
    """Return the effective gear — relay_fan.current_gear for relay-output
    devices, manual_fan_gear for analog-output ones (current_gear never
    changes there since the relay isn't the active output)."""
    fan = device.get("fan", {})
    gear = (
        fan.get("relay_fan", {}).get("current_gear")
        if _output_type(device) == "relay"
        else fan.get("manual_fan_gear")
    )
    return gear if isinstance(gear, str) else None


def _analog_gear_percents(device: dict[str, Any]) -> dict[str, int]:
    analog = device.get("fan", {}).get("analog_fan", {})
    return {
        gear: analog[f"manual_{gear}_gear_percent"]
        for gear in _GEAR_ORDER
        if isinstance(analog.get(f"manual_{gear}_gear_percent"), (int, float))
    }


def _nearest_gear_for_percentage(device: dict[str, Any], percentage: int) -> str | None:
    percents = _analog_gear_percents(device)
    if not percents:
        return None
    return min(percents, key=lambda gear: abs(percents[gear] - percentage))


def _fan_store(coordinator: SinumCoordinator, bus: str) -> dict[int, dict[str, Any]]:
    store = _shared_bus_store(coordinator, bus)
    return coordinator.wtp_devices if store is None else store


def _add_from_store(
    coordinator: SinumCoordinator,
    entities: list[FanEntity],
    entry_id: str,
    bus: str,
    store: dict[int, dict[str, Any]],
    fan_coil_types: set[str],
) -> None:
    for device_id, device in store.items():
        if device.get("type") in fan_coil_types and _has_fan_control(device):
            entities.append(SinumFanCoilFan(coordinator, device_id, entry_id, bus))


def _add_fan_entities(
    coordinator: SinumCoordinator,
    entities: list[FanEntity],
    entry_id: str,
    bus: str,
) -> None:
    if bus == "sbus":
        _add_from_store(
            coordinator, entities, entry_id, "sbus", coordinator.sbus_devices, {STYPE_FAN_COIL}
        )
    else:
        _add_from_store(
            coordinator, entities, entry_id, "wtp", coordinator.wtp_devices, _WTP_FAN_COIL_TYPES
        )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SinumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SinumCoordinator = entry.runtime_data
    entities: list[FanEntity] = []
    _add_fan_entities(coordinator, entities, entry.entry_id, "sbus")
    _add_fan_entities(coordinator, entities, entry.entry_id, "wtp")
    async_add_entities(entities)


class SinumFanCoilFan(SinumDeviceAvailableMixin, CoordinatorEntity[SinumCoordinator], FanEntity):
    """Fan gear control for Sinum fan_coil and fan_coil_v2 devices.

    Exposes gear_1/gear_2/gear_3 as HA fan preset modes. For analog-output
    devices, also exposes each gear's calibrated percentage via SET_SPEED.
    turn_off sets work_mode=off; turn_on resumes automatic if unit was off.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "fan_coil_fan"
    _attr_icon = "mdi:fan"
    _attr_preset_modes = _PRESETS

    @property
    def supported_features(self) -> FanEntityFeature:
        features = (
            FanEntityFeature.PRESET_MODE | FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
        )
        if _output_type(self._device) != "relay":
            features |= FanEntityFeature.SET_SPEED
        return features

    @property
    def speed_count(self) -> int:
        return len(_GEAR_ORDER)

    def __init__(
        self,
        coordinator: SinumCoordinator,
        device_id: int,
        entry_id: str,
        bus: str,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._bus = bus
        self._attr_unique_id = f"{entry_id}_{bus}_{device_id}_fan"
        store = _fan_store(coordinator, bus)
        device = store.get(device_id, {})
        self._attr_device_info = _fan_coil_device_info(device, entry_id, bus, device_id)

    @property
    def _device(self) -> dict[str, Any]:
        return _fan_store(self.coordinator, self._bus).get(self._device_id, {})

    @property
    def is_on(self) -> bool:
        return self._device.get("work_mode", "off") != "off"

    @property
    def preset_mode(self) -> str | None:
        gear = _current_gear(self._device)
        return _GEAR_TO_PRESET.get(gear) if gear else None

    @property
    def percentage(self) -> int | None:
        if _output_type(self._device) == "relay":
            return None
        gear = _current_gear(self._device)
        return _analog_gear_percents(self._device).get(gear) if gear else None

    async def async_set_percentage(self, percentage: int) -> None:
        gear = _nearest_gear_for_percentage(self._device, percentage)
        if gear is None:
            return
        await self.async_set_preset_mode(_GEAR_TO_PRESET[gear])

    async def _patch(self, payload: dict[str, Any]) -> dict[str, Any]:
        patch_method = bus_patch_method(self.coordinator, self._bus)
        if patch_method is None:
            raise HomeAssistantError(f"Unsupported bus for fan patch: {self._bus}")
        return await patch_method(self._device_id, payload)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        gear = _PRESET_TO_GEAR.get(preset_mode)
        if not gear:
            _LOGGER.warning("Unknown fan preset mode: %s", preset_mode)
            return
        try:
            updated = await self._patch({"fan.manual_fan_gear": gear})
        except Exception as err:
            raise HomeAssistantError(f"Cannot set fan gear: {err}") from err
        if updated:
            self._device.update(updated)
        self.async_write_ha_state()

    def _turn_on_payload(self, preset_mode: str | None) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if preset_mode:
            gear = _PRESET_TO_GEAR.get(preset_mode)
            if gear:
                payload["fan.manual_fan_gear"] = gear
        if not self.is_on:
            payload["work_mode"] = "automatic"
        return payload

    async def async_turn_on(self, preset_mode: str | None = None, **kwargs: Any) -> None:
        payload = self._turn_on_payload(preset_mode)
        if not payload:
            return
        try:
            updated = await self._patch(payload)
        except Exception as err:
            raise HomeAssistantError(f"Cannot turn on fan coil: {err}") from err
        if updated:
            self._device.update(updated)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            updated = await self._patch({"work_mode": "off"})
        except Exception as err:
            raise HomeAssistantError(f"Cannot turn off fan coil: {err}") from err
        if updated:
            self._device.update(updated)
        self.async_write_ha_state()
