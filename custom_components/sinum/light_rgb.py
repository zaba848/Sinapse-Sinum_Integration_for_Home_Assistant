from __future__ import annotations

import logging
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
    _hex_to_hs,
    _hex_to_hsv,
    _hs_to_hex,
    _kelvin_to_hex,
    _label,
    _restore_light_state,
    _supported_color_modes,
    _supports_color_temperature,
)
from .const import DOMAIN, MANUFACTURER
from .coordinator import SinumCoordinator, SinumDeviceAvailableMixin, via_device_for
from .light_button import SinumButtonLight  # noqa: F401

_LOGGER = logging.getLogger(__name__)


def _sbus_temp_lua(
    prefix: str, device: dict[str, Any], kwargs: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
    current_pct = device.get("brightness") or 80
    line = f'{prefix}:call("set_temperature",{{{kelvin},{current_pct}}})'
    return line, {"color_mode": "temperature", "white_temperature": kelvin}


def _sbus_color_lua(prefix: str, kwargs: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    lines: list[str] = []
    optimistic: dict[str, Any] = {}
    if ATTR_HS_COLOR in kwargs:
        h, s = kwargs[ATTR_HS_COLOR]
        color_hex = _hs_to_hex(h, s, 1.0)
        lines.append(f'{prefix}:call("set_color",{{"{color_hex}",200}})')
        optimistic.update({"color_mode": "rgb", "led_color": color_hex})
    if ATTR_BRIGHTNESS in kwargs:
        pct = round(kwargs[ATTR_BRIGHTNESS] / 255 * 100)
        lines.append(f'{prefix}:call("set_brightness",{{{pct}}})')
        optimistic["brightness"] = pct
    return lines, optimistic


def _has_color_kwargs(kwargs: dict[str, Any]) -> bool:
    return ATTR_HS_COLOR in kwargs or ATTR_BRIGHTNESS in kwargs or ATTR_COLOR_TEMP_KELVIN in kwargs


def _bus_store_rgb(coordinator: SinumCoordinator, bus: str) -> dict[int, dict[str, Any]]:
    return coordinator.wtp_devices if bus == "wtp" else coordinator.sbus_devices


class SinumBusRgbLight(
    SinumDeviceAvailableMixin, CoordinatorEntity[SinumCoordinator], LightEntity, RestoreEntity
):
    """SBUS or WTP rgb_controller.

    SBUS devices are controlled via Lua scenes (set_color / set_brightness /
    set_temperature).  State on/off is sent as a separate REST PATCH because
    the Lua set_state call is unreliable.  WTP rgb_controllers fall back to
    REST-only control (no confirmed Lua support on that firmware).
    """

    _attr_has_entity_name = True
    _attr_name = None
    _attr_min_color_temp_kelvin = 1000
    _attr_max_color_temp_kelvin = 6500
    _attr_icon = "mdi:led-strip-variant"

    def __init__(
        self, coordinator: SinumCoordinator, device_id: int, entry_id: str, bus: str
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._bus = bus
        self._attr_unique_id = f"{entry_id}_{bus}_{device_id}"
        self._lua_scene_id: int | None = None
        device = (coordinator.wtp_devices if bus == "wtp" else coordinator.sbus_devices).get(
            device_id, {}
        )
        label = _label(device)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{bus}_{device_id}")},
            name=label,
            manufacturer=MANUFACTURER,
            model=device.get("_parent_model") or f"Sinum {bus.upper()} RGB Controller",
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
    def supported_color_modes(self) -> set[ColorMode]:
        if self._bus == "sbus":
            # SBUS rgb_controllers always support HS via Lua, regardless of
            # whether the hub currently reports led_color in the device dict.
            modes = {ColorMode.HS}
            if _supports_color_temperature(self._device):
                modes.add(ColorMode.COLOR_TEMP)
            return modes
        return _supported_color_modes(self._device)

    @property
    def color_mode(self) -> ColorMode:
        if self._bus == "sbus":
            mode = str(self._device.get("color_mode", "")).lower()
            if mode in {"temperature", "color_temp", "white_temperature"}:
                return ColorMode.COLOR_TEMP
            return ColorMode.HS
        return _color_mode(self._device)

    @property
    def brightness(self) -> int | None:
        raw = self._device.get("brightness")
        if raw is not None:
            return round(raw / 100 * 255)
        return self._attr_brightness

    @property
    def hs_color(self) -> tuple[float, float] | None:
        # led_color is the actual hardware output; HS extraction ignores V so dimming
        # doesn't affect the reported hue/saturation shown in the HA colour picker.
        hex_color = self._device.get("led_color") or self._device.get("color")
        if not hex_color:
            return None
        return _hex_to_hs(hex_color)

    @property
    def color_temp_kelvin(self) -> int | None:
        return self._device.get("white_temperature")

    # ------------------------------------------------------------------ Lua helpers

    async def _ensure_lua_scene(self) -> int:
        """Return the ID of the persistent Lua scene for this device, creating it if needed."""
        if self._lua_scene_id is None:
            name = f"_ha_rgb_{self._bus}_{self._device_id}"
            self._lua_scene_id = await self.coordinator.client.get_or_create_scene(name)
        return self._lua_scene_id

    async def _run_lua(self, lua_code: str) -> None:
        """Update the scene's Lua code and activate it."""
        scene_id = await self._ensure_lua_scene()
        await self.coordinator.client.patch_scene_lua(scene_id, lua_code)
        await self.coordinator.client.run_scene(scene_id)

    async def async_will_remove_from_hass(self) -> None:
        if self._lua_scene_id is not None:
            try:
                await self.coordinator.client.delete_scene(self._lua_scene_id)
            except Exception:
                _LOGGER.debug("Could not delete RGB scene %s on removal", self._lua_scene_id)
            self._lua_scene_id = None

    # ------------------------------------------------------------------ commands

    def _sbus_lua_commands(self, **kwargs: Any) -> tuple[list[str], dict[str, Any]]:
        """Build Lua command lines and optimistic state for SBUS RGB control."""
        prefix = f"sbus[{self._device_id}]"
        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            line, optimistic = _sbus_temp_lua(prefix, self._device, kwargs)
            return [line], optimistic
        return _sbus_color_lua(prefix, kwargs)

    def _wtp_color_payload(self, **kwargs: Any) -> dict[str, Any]:
        """Build REST color payload for WTP RGB control."""
        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            return {"color": _kelvin_to_hex(kwargs[ATTR_COLOR_TEMP_KELVIN])}

        hs_payload = self._wtp_hs_payload(kwargs)
        if hs_payload is not None:
            return hs_payload

        brightness = kwargs.get(ATTR_BRIGHTNESS)
        if brightness is None:
            return {}
        return {"color": self._brightness_color(brightness)}

    @staticmethod
    def _wtp_hs_payload(kwargs: dict[str, Any]) -> dict[str, Any] | None:
        if ATTR_HS_COLOR not in kwargs:
            return None
        h, s = kwargs[ATTR_HS_COLOR]
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        value = 1.0 if brightness is None else brightness / 255.0
        return {"color": _hs_to_hex(h, s, value)}

    def _brightness_color(self, brightness: int) -> str:
        current = self._device.get("led_color") or self._device.get("color") or "#ffffff"
        h, s, _ = _hex_to_hsv(current)
        return _hs_to_hex(h, s, brightness / 255.0)

    async def _apply_sbus_color(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Run Lua color commands and return optimistic state; no-op if no color kwargs."""
        if not _has_color_kwargs(kwargs):
            return {}
        lua_lines, optimistic = self._sbus_lua_commands(**kwargs)
        try:
            await self._run_lua("\n".join(lua_lines))
        except Exception as err:
            raise HomeAssistantError(f"Cannot control RGB: {err}") from err
        return optimistic

    def _rest_turn_on_payload(self, **kwargs: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {"state": True}
        mode = str(self._device.get("color_mode", "")).lower()
        if self._bus == "wtp" and mode not in ("temperature", "animation"):
            payload.update(self._wtp_color_payload(**kwargs))
        return payload

    async def _patch_on(
        self, store: dict[int, dict[str, Any]], rest_payload: dict[str, Any]
    ) -> None:
        try:
            if self._bus == "wtp":
                updated = await self.coordinator.client.patch_wtp_device(
                    self._device_id, rest_payload
                )
            else:
                updated = await self.coordinator.client.patch_sbus_device(
                    self._device_id, {"state": True}
                )
            store[self._device_id].update(updated or {})
        except Exception as err:
            raise HomeAssistantError(f"Cannot turn on: {err}") from err

    async def _patch_off(self) -> dict[str, Any]:
        try:
            if self._bus == "wtp":
                result = await self.coordinator.client.patch_wtp_device(
                    self._device_id, {"state": False}
                )
            else:
                result = await self.coordinator.client.patch_sbus_device(
                    self._device_id, {"state": False}
                )
            return result or {}
        except Exception as err:
            raise HomeAssistantError(f"Cannot turn off: {err}") from err

    async def async_turn_on(self, **kwargs: Any) -> None:
        store = _bus_store_rgb(self.coordinator, self._bus)
        optimistic: dict[str, Any] = {"state": True}
        if self._bus == "sbus":
            optimistic.update(await self._apply_sbus_color(kwargs))
        await self._patch_on(store, self._rest_turn_on_payload(**kwargs))
        store[self._device_id].update(optimistic)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        store = _bus_store_rgb(self.coordinator, self._bus)
        updated = await self._patch_off()
        store[self._device_id].update({"state": False, **updated})
        self.async_write_ha_state()
