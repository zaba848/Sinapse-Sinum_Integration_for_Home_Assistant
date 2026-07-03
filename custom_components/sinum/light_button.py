"""Button panel backlight entity."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_HS_COLOR, ColorMode, LightEntity
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ._light_helpers import _hex_to_hs, _hs_to_hex, _label, _restore_button_light_state
from .const import DOMAIN, MANUFACTURER
from .coordinator import SinumCoordinator, SinumDeviceAvailableMixin, via_device_for


class SinumButtonLight(
    SinumDeviceAvailableMixin, CoordinatorEntity[SinumCoordinator], LightEntity, RestoreEntity
):
    """Button panel backlight — controls the physical LED color via the 'color' field."""

    _attr_has_entity_name = True
    _attr_translation_key = "button_backlight"
    _attr_icon = "mdi:led-on"
    _attr_color_mode = ColorMode.HS
    _attr_supported_color_modes = {ColorMode.HS}
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, coordinator: SinumCoordinator, device_id: int, entry_id: str, bus: str
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._bus = bus
        self._attr_unique_id = f"{entry_id}_{bus}_{device_id}_backlight"
        store = coordinator.wtp_devices if bus == "wtp" else coordinator.sbus_devices
        device = store.get(device_id, {})
        label = _label(device)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{bus}_{device_id}")},
            name=label,
            manufacturer=MANUFACTURER,
            model=device.get("_parent_model") or "Sinum Button",
            suggested_area=device.get("_area") or None,
            via_device=via_device_for(device, entry_id),
        )
        self._restored_color: str | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._device:
            return
        await _restore_button_light_state(self)

    @property
    def _device(self) -> dict[str, Any]:
        store = (
            self.coordinator.wtp_devices if self._bus == "wtp" else self.coordinator.sbus_devices
        )
        return store.get(self._device_id, {})

    @property
    def is_on(self) -> bool:
        d = self._device
        if d:
            color = d.get("color", "#000000")
            return color.lstrip("#").lower() not in ("000000", "")
        return bool(self._attr_is_on)

    @property
    def hs_color(self) -> tuple[float, float] | None:
        color = self._device.get("color")
        if color:
            return _hex_to_hs(color)
        return self._attr_hs_color

    def _store(self) -> dict[int, dict[str, Any]]:
        return self.coordinator.wtp_devices if self._bus == "wtp" else self.coordinator.sbus_devices

    def _resolve_turn_on_color(self, kwargs: dict[str, Any]) -> str:
        if ATTR_HS_COLOR in kwargs:
            h, s = kwargs[ATTR_HS_COLOR]
            return _hs_to_hex(h, s)
        return self._device.get("color") or "#0072c3"

    async def _patch_bus_color(self, color: str) -> dict[str, Any]:
        try:
            if self._bus == "wtp":
                result = await self.coordinator.client.patch_wtp_device(
                    self._device_id, {"color": color}
                )
            else:
                result = await self.coordinator.client.patch_sbus_device(
                    self._device_id, {"color": color}
                )
            return result or {}
        except Exception as err:
            raise HomeAssistantError(f"Cannot set backlight color: {err}") from err

    async def async_turn_on(self, **kwargs: Any) -> None:
        color = self._resolve_turn_on_color(kwargs)
        updated = await self._patch_bus_color(color)
        self._store()[self._device_id].update({"color": color, **updated})
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            if self._bus == "wtp":
                updated = await self.coordinator.client.patch_wtp_device(
                    self._device_id, {"color": "#000000"}
                )
            else:
                updated = await self.coordinator.client.patch_sbus_device(
                    self._device_id, {"color": "#000000"}
                )
        except Exception as err:
            raise HomeAssistantError(f"Cannot turn off backlight: {err}") from err
        self._store()[self._device_id].update({**{"color": "#000000"}, **(updated or {})})
        self.async_write_ha_state()
