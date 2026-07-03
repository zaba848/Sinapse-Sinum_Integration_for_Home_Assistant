"""Shared _BusClimateMixin for WTP/SBUS climate entities."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.climate import HVACMode
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.exceptions import HomeAssistantError

from ._climate_helpers import _HVAC_TO_MODE, _MODE_TO_HVAC, _available_hvac_modes
from .const import TEMP_MAX, TEMP_MIN

if TYPE_CHECKING:
    from .coordinator import SinumCoordinator


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
