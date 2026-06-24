from __future__ import annotations

import logging
import math
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SinumConfigEntry
from .const import (
    DOMAIN,
    STYPE_BUTTON,
    STYPE_DIMMER,
    STYPE_RGB_CONTROLLER,
    VTYPE_DIMMER_RGB,
    VTYPE_DIMMER_RGB_INTEGRATOR,
    WTYPE_BUTTON,
    WTYPE_DIMMER,
    WTYPE_RGB_CONTROLLER,
)
from .coordinator import SinumCoordinator, via_device_for

_LOGGER = logging.getLogger(__name__)


def _add_bus_lights(
    coordinator: SinumCoordinator, entities: list[LightEntity], entry_id: str, bus: str
) -> None:
    store = coordinator.wtp_devices if bus == "wtp" else coordinator.sbus_devices
    dimmer_type = WTYPE_DIMMER if bus == "wtp" else STYPE_DIMMER
    rgb_type = WTYPE_RGB_CONTROLLER if bus == "wtp" else STYPE_RGB_CONTROLLER
    button_type = WTYPE_BUTTON if bus == "wtp" else STYPE_BUTTON

    for device_id, device in store.items():
        dev_type = device.get("type")
        if dev_type == dimmer_type:
            entities.append(SinumBusDimmerLight(coordinator, device_id, entry_id, bus))
        elif dev_type == rgb_type:
            entities.append(SinumBusRgbLight(coordinator, device_id, entry_id, bus))
        elif dev_type == button_type and "color" in device:
            entities.append(SinumButtonLight(coordinator, device_id, entry_id, bus))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SinumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SinumCoordinator = entry.runtime_data
    entities: list[LightEntity] = []

    for device_id, device in coordinator.virtual_devices.items():
        if device.get("type") in (VTYPE_DIMMER_RGB, VTYPE_DIMMER_RGB_INTEGRATOR):
            entities.append(SinumDimmerLight(coordinator, device_id, entry.entry_id))

    _add_bus_lights(coordinator, entities, entry.entry_id, "wtp")
    _add_bus_lights(coordinator, entities, entry.entry_id, "sbus")

    async_add_entities(entities)


def _label(device: dict[str, Any]) -> str:
    return (device.get("_device_name") or device.get("name", "")).strip()


def _hex_to_hsv(hex_color: str) -> tuple[float, float, float]:
    """Convert #RRGGBB to (hue 0-360, saturation 0-100, value 0-1)."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) < 6:
        return (0.0, 0.0, 1.0)
    try:
        r, g, b = (int(hex_color[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return (0.0, 0.0, 1.0)
    max_c = max(r, g, b)
    min_c = min(r, g, b)
    delta = max_c - min_c
    if delta == 0:
        h = 0.0
    elif max_c == r:
        h = 60 * (((g - b) / delta) % 6)
    elif max_c == g:
        h = 60 * ((b - r) / delta + 2)
    else:
        h = 60 * ((r - g) / delta + 4)
    s = 0.0 if max_c == 0 else (delta / max_c) * 100
    return h, s, max_c


def _hex_to_hs(hex_color: str) -> tuple[float, float]:
    """Convert #RRGGBB to (hue 0-360, saturation 0-100)."""
    h, s, _ = _hex_to_hsv(hex_color)
    return h, s


def _kelvin_to_hex(kelvin: int) -> str:
    """Convert color temperature in Kelvin to approximate #RRGGBB for RGB-only strips."""
    t = max(1000, min(40000, kelvin)) / 100
    if t <= 66:
        r = 255
        g = max(0, min(255, round(99.4708025861 * math.log(t) - 161.1195681661)))
    else:
        r = max(0, min(255, round(329.698727446 * ((t - 60) ** -0.1332047592))))
        g = max(0, min(255, round(288.1221695283 * ((t - 60) ** -0.0755148492))))
    if t >= 66:
        b = 255
    elif t <= 19:
        b = 0
    else:
        b = max(0, min(255, round(138.5177312231 * math.log(t - 10) - 305.0447927307)))
    return f"#{r:02X}{g:02X}{b:02X}"


def _hs_to_hex(hue: float, saturation: float, value: float = 1.0) -> str:
    """Convert (hue 0-360, saturation 0-100, value 0-1) to #RRGGBB."""
    h = hue / 60
    s = saturation / 100
    v = max(0.0, min(1.0, value))
    i = math.floor(h)
    f = h - i
    p = v * (1 - s)
    q = v * (1 - f * s)
    t = v * (1 - (1 - f) * s)
    mapping = [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)]
    r, g, b = mapping[int(i) % 6]
    return f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"


def _labels(device: dict[str, Any]) -> set[str]:
    labels = device.get("labels", [])
    if not isinstance(labels, list):
        return set()
    return {str(label).lower() for label in labels}


def _supports_rgb(device: dict[str, Any]) -> bool:
    labels = _labels(device)
    dev_type = device.get("type")
    mode = str(device.get("color_mode", "")).lower()
    return (
        "led_color" in device
        or mode in {"rgb", "hs", "color"}
        or any("rgb" in label for label in labels)
        or dev_type in (VTYPE_DIMMER_RGB, VTYPE_DIMMER_RGB_INTEGRATOR)
        or dev_type in (WTYPE_RGB_CONTROLLER, STYPE_RGB_CONTROLLER)
    )


def _supports_color_temperature(device: dict[str, Any]) -> bool:
    labels = _labels(device)
    mode = str(device.get("color_mode", "")).lower()
    return (
        "white_temperature" in device
        or mode in {"temperature", "color_temp", "white_temperature"}
        or "rgbww" in labels
        or "ww" in labels
    )


def _supported_color_modes(device: dict[str, Any]) -> set[ColorMode]:
    modes: set[ColorMode] = set()
    if _supports_rgb(device):
        modes.add(ColorMode.HS)
    if _supports_color_temperature(device):
        modes.add(ColorMode.COLOR_TEMP)
    if not modes:
        modes.add(ColorMode.BRIGHTNESS)
    return modes


def _color_mode(device: dict[str, Any]) -> ColorMode:
    mode = str(device.get("color_mode", "")).lower()
    if mode in {"temperature", "color_temp", "white_temperature"}:
        return ColorMode.COLOR_TEMP
    if mode in {"rgb", "hs", "color"} or _supports_rgb(device):
        return ColorMode.HS
    if _supports_color_temperature(device):
        return ColorMode.COLOR_TEMP
    return ColorMode.BRIGHTNESS


class SinumDimmerLight(CoordinatorEntity[SinumCoordinator], LightEntity):
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
        return bool(self._device.get("state"))

    @property
    def brightness(self) -> int | None:
        raw = self._device.get("brightness")
        if raw is None:
            return None
        return round(raw / 100 * 255)

    @property
    def hs_color(self) -> tuple[float, float] | None:
        hex_color = self._device.get("led_color")
        if not hex_color:
            return None
        return _hex_to_hs(hex_color)

    @property
    def color_temp_kelvin(self) -> int | None:
        return self._device.get("white_temperature")

    async def async_turn_on(self, **kwargs: Any) -> None:
        payload: dict[str, Any] = {"state": True}

        if ATTR_BRIGHTNESS in kwargs:
            payload["brightness"] = round(kwargs[ATTR_BRIGHTNESS] / 255 * 100)

        if ATTR_HS_COLOR in kwargs:
            h, s = kwargs[ATTR_HS_COLOR]
            payload["led_color"] = _hs_to_hex(h, s)

        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
            if self._device.get("led_strip_type", "").lower() == "rgb":
                payload["led_color"] = _kelvin_to_hex(kelvin)
            else:
                payload["white_temperature"] = kelvin

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


class SinumBusDimmerLight(CoordinatorEntity[SinumCoordinator], LightEntity):
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

    @property
    def _device(self) -> dict[str, Any]:
        store = (
            self.coordinator.wtp_devices if self._bus == "wtp" else self.coordinator.sbus_devices
        )
        return store.get(self._device_id, {})

    @property
    def is_on(self) -> bool:
        return bool(self._device.get("state"))

    @property
    def brightness(self) -> int | None:
        raw = self._device.get("target_level")
        if raw is None:
            return None
        return round(raw / 100 * 255)

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


class SinumBusRgbLight(CoordinatorEntity[SinumCoordinator], LightEntity):
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
            manufacturer="TECH Sterowniki",
            model=device.get("_parent_model") or f"Sinum {bus.upper()} RGB Controller",
            suggested_area=device.get("_area") or None,
            via_device=via_device_for(device, entry_id),
        )

    @property
    def _device(self) -> dict[str, Any]:
        store = (
            self.coordinator.wtp_devices if self._bus == "wtp" else self.coordinator.sbus_devices
        )
        return store.get(self._device_id, {})

    @property
    def is_on(self) -> bool:
        return bool(self._device.get("state"))

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        return _supported_color_modes(self._device)

    @property
    def color_mode(self) -> ColorMode:
        return _color_mode(self._device)

    @property
    def brightness(self) -> int | None:
        raw = self._device.get("brightness")
        if raw is None:
            return None
        return round(raw / 100 * 255)

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
        lua_lines: list[str] = []
        optimistic: dict[str, Any] = {}
        prefix = f"sbus[{self._device_id}]"

        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
            current_pct = self._device.get("brightness") or 80
            lua_lines.append(f'{prefix}:call("set_temperature",{{{kelvin},{current_pct}}})')
            optimistic["color_mode"] = "temperature"
            optimistic["white_temperature"] = kelvin
        else:
            if ATTR_HS_COLOR in kwargs:
                h, s = kwargs[ATTR_HS_COLOR]
                lua_lines.append(f'{prefix}:call("set_color",{{"{_hs_to_hex(h, s, 1.0)}",200}})')
                optimistic["color_mode"] = "rgb"
            if ATTR_BRIGHTNESS in kwargs:
                pct = round(kwargs[ATTR_BRIGHTNESS] / 255 * 100)
                lua_lines.append(f'{prefix}:call("set_brightness",{{{pct}}})')
                optimistic["brightness"] = pct

        return lua_lines, optimistic

    def _wtp_color_payload(self, **kwargs: Any) -> dict[str, Any]:
        """Build REST color payload for WTP RGB control."""
        payload: dict[str, Any] = {}
        has_hs = ATTR_HS_COLOR in kwargs
        has_brightness = ATTR_BRIGHTNESS in kwargs

        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            payload["color"] = _kelvin_to_hex(kwargs[ATTR_COLOR_TEMP_KELVIN])
        elif has_hs and has_brightness:
            h, s = kwargs[ATTR_HS_COLOR]
            payload["color"] = _hs_to_hex(h, s, kwargs[ATTR_BRIGHTNESS] / 255.0)
        elif has_hs:
            h, s = kwargs[ATTR_HS_COLOR]
            payload["color"] = _hs_to_hex(h, s, 1.0)
        elif has_brightness:
            current = self._device.get("led_color") or self._device.get("color") or "#ffffff"
            h, s, _ = _hex_to_hsv(current)
            payload["color"] = _hs_to_hex(h, s, kwargs[ATTR_BRIGHTNESS] / 255.0)

        return payload

    async def async_turn_on(self, **kwargs: Any) -> None:
        store = (
            self.coordinator.wtp_devices if self._bus == "wtp" else self.coordinator.sbus_devices
        )
        optimistic: dict[str, Any] = {"state": True}
        has_color_kwargs = ATTR_HS_COLOR in kwargs or ATTR_BRIGHTNESS in kwargs or ATTR_COLOR_TEMP_KELVIN in kwargs
        mode = str(self._device.get("color_mode", "")).lower()
        # WTP REST PATCH cannot override the schedule in temperature/animation mode.
        wtp_managed = self._bus == "wtp" and mode in ("temperature", "animation")

        if self._bus == "sbus" and has_color_kwargs:
            lua_lines, sbus_optimistic = self._sbus_lua_commands(**kwargs)
            optimistic.update(sbus_optimistic)
            try:
                await self._run_lua("\n".join(lua_lines))
            except Exception as err:
                raise HomeAssistantError(f"Cannot control RGB: {err}") from err

        rest_payload: dict[str, Any] = {"state": True}
        if self._bus == "wtp" and not wtp_managed:
            rest_payload.update(self._wtp_color_payload(**kwargs))

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

        store[self._device_id].update(optimistic)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        store = (
            self.coordinator.wtp_devices if self._bus == "wtp" else self.coordinator.sbus_devices
        )
        try:
            if self._bus == "wtp":
                updated = await self.coordinator.client.patch_wtp_device(
                    self._device_id, {"state": False}
                )
            else:
                updated = await self.coordinator.client.patch_sbus_device(
                    self._device_id, {"state": False}
                )
        except Exception as err:
            raise HomeAssistantError(f"Cannot turn off: {err}") from err
        store[self._device_id].update({**{"state": False}, **(updated or {})})
        self.async_write_ha_state()


class SinumButtonLight(CoordinatorEntity[SinumCoordinator], LightEntity):
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
            manufacturer="TECH Sterowniki",
            model=device.get("_parent_model") or "Sinum Button",
            suggested_area=device.get("_area") or None,
            via_device=via_device_for(device, entry_id),
        )

    @property
    def _device(self) -> dict[str, Any]:
        store = (
            self.coordinator.wtp_devices if self._bus == "wtp" else self.coordinator.sbus_devices
        )
        return store.get(self._device_id, {})

    @property
    def is_on(self) -> bool:
        color = self._device.get("color", "#000000")
        return color.lstrip("#").lower() not in ("000000", "")

    @property
    def hs_color(self) -> tuple[float, float] | None:
        color = self._device.get("color")
        if not color:
            return None
        return _hex_to_hs(color)

    def _store(self) -> dict[int, dict[str, Any]]:
        return self.coordinator.wtp_devices if self._bus == "wtp" else self.coordinator.sbus_devices

    async def async_turn_on(self, **kwargs: Any) -> None:
        if ATTR_HS_COLOR in kwargs:
            h, s = kwargs[ATTR_HS_COLOR]
            color = _hs_to_hex(h, s)
        else:
            color = self._device.get("color") or "#0072c3"
        try:
            if self._bus == "wtp":
                updated = await self.coordinator.client.patch_wtp_device(
                    self._device_id, {"color": color}
                )
            else:
                updated = await self.coordinator.client.patch_sbus_device(
                    self._device_id, {"color": color}
                )
        except Exception as err:
            raise HomeAssistantError(f"Cannot set backlight color: {err}") from err
        self._store()[self._device_id].update({**{"color": color}, **(updated or {})})
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
