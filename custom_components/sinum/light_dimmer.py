from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ._light_helpers import (
    _color_mode,
    _hs_to_hex,
    _kelvin_to_hex,
    _label,
    _restore_light_state,
    _supported_color_modes,
)
from .const import DOMAIN
from .coordinator import SinumCoordinator, SinumDeviceAvailableMixin, via_device_for


class SinumDimmerLight(
    SinumDeviceAvailableMixin, CoordinatorEntity[SinumCoordinator], LightEntity, RestoreEntity
):
    """Dimmer/RGB controller integrator."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_min_color_temp_kelvin = 1000
    _attr_max_color_temp_kelvin = 6500
    _attr_icon = "mdi:led-strip-variant"

    def __init__(self, coordinator: SinumCoordinator, device_id: int, entry_id: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry_id}_virtual_{device_id}"
        device = coordinator.virtual_devices.get(device_id, {})
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_virtual_{device_id}")},
            name=_label(device),
            manufacturer="TECH Sterowniki",
            model=device.get("_parent_model") or "Sinum Dimmer/RGB Controller",
            suggested_area=device.get("_area") or None,
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._device:
            return
        await _restore_light_state(self)

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.virtual_devices.get(self._device_id, {})

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        return _supported_color_modes(self._device)

    @property
    def color_mode(self) -> ColorMode:
        return _color_mode(self._device)

    @property
    def is_on(self) -> bool:
        if self._device:
            return bool(self._device.get("state"))
        return bool(self._attr_is_on)

    @property
    def brightness(self) -> int | None:
        raw = self._device.get("brightness")
        if raw is not None:
            return round(raw / 100 * 255)
        return self._attr_brightness

    @property
    def hs_color(self) -> tuple[float, float] | None:
        from ._light_helpers import _hex_to_hs

        hex_color = self._device.get("led_color")
        if not hex_color:
            return None
        return _hex_to_hs(hex_color)

    @property
    def color_temp_kelvin(self) -> int | None:
        return self._device.get("white_temperature")

    def _turn_on_payload(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {"state": True}
        if ATTR_BRIGHTNESS in kwargs:
            payload["brightness"] = round(kwargs[ATTR_BRIGHTNESS] / 255 * 100)
        if ATTR_HS_COLOR in kwargs:
            h, s = kwargs[ATTR_HS_COLOR]
            payload["led_color"] = _hs_to_hex(h, s)
        self._apply_color_temp_payload(payload, kwargs)
        return payload

    def _apply_color_temp_payload(self, payload: dict[str, Any], kwargs: dict[str, Any]) -> None:
        if ATTR_COLOR_TEMP_KELVIN not in kwargs:
            return
        kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
        if self._device.get("led_strip_type", "").lower() == "rgb":
            payload["led_color"] = _kelvin_to_hex(kelvin)
            return
        payload["white_temperature"] = kelvin

    async def async_turn_on(self, **kwargs: Any) -> None:
        payload = self._turn_on_payload(kwargs)
        try:
            updated = await self.coordinator.client.patch_virtual_device(self._device_id, payload)
        except Exception as err:
            raise HomeAssistantError(f"Cannot turn on: {err}") from err
        self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            updated = await self.coordinator.client.patch_virtual_device(
                self._device_id, {"state": False}
            )
        except Exception as err:
            raise HomeAssistantError(f"Cannot turn off: {err}") from err
        self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()


class SinumBusDimmerLight(
    SinumDeviceAvailableMixin, CoordinatorEntity[SinumCoordinator], LightEntity, RestoreEntity
):
    """SBUS or WTP dimmer — uses target_level (0-100) for brightness."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_color_modes: set[ColorMode] = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_icon = "mdi:lightbulb-on-outline"

    def __init__(
        self, coordinator: SinumCoordinator, device_id: int, entry_id: str, bus: str
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._bus = bus
        self._attr_unique_id = f"{entry_id}_{bus}_{device_id}"
        device = (coordinator.wtp_devices if bus == "wtp" else coordinator.sbus_devices).get(
            device_id, {}
        )
        label = _label(device)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{bus}_{device_id}")},
            name=label,
            manufacturer="TECH Sterowniki",
            model=device.get("_parent_model") or f"Sinum {bus.upper()} Dimmer",
            suggested_area=device.get("_area") or None,
            via_device=via_device_for(device, entry_id),
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._device:
            return
        await _restore_light_state(self)

    @property
    def _device(self) -> dict[str, Any]:
        store = (
            self.coordinator.wtp_devices if self._bus == "wtp" else self.coordinator.sbus_devices
        )
        return store.get(self._device_id, {})

    @property
    def is_on(self) -> bool:
        if self._device:
            return bool(self._device.get("state"))
        return bool(self._attr_is_on)

    @property
    def brightness(self) -> int | None:
        raw = self._device.get("target_level")
        if raw is not None:
            return round(raw / 100 * 255)
        return self._attr_brightness

    async def async_turn_on(self, **kwargs: Any) -> None:
        payload: dict[str, Any] = {"state": True}
        if ATTR_BRIGHTNESS in kwargs:
            payload["target_level"] = round(kwargs[ATTR_BRIGHTNESS] / 255 * 100)
        try:
            if self._bus == "wtp":
                updated = await self.coordinator.client.patch_wtp_device(self._device_id, payload)
                self.coordinator.wtp_devices[self._device_id].update(updated)
            else:
                updated = await self.coordinator.client.patch_sbus_device(self._device_id, payload)
                self.coordinator.sbus_devices[self._device_id].update(updated)
        except Exception as err:
            raise HomeAssistantError(f"Cannot turn on: {err}") from err
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            if self._bus == "wtp":
                updated = await self.coordinator.client.patch_wtp_device(
                    self._device_id, {"state": False}
                )
                self.coordinator.wtp_devices[self._device_id].update(updated)
            else:
                updated = await self.coordinator.client.patch_sbus_device(
                    self._device_id, {"state": False}
                )
                self.coordinator.sbus_devices[self._device_id].update(updated)
        except Exception as err:
            raise HomeAssistantError(f"Cannot turn off: {err}") from err
        self.async_write_ha_state()
