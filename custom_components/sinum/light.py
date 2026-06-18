from __future__ import annotations

import math
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SinumConfigEntry
from .const import (
    DOMAIN,
    STYPE_DIMMER,
    STYPE_RGB_CONTROLLER,
    VTYPE_DIMMER_RGB,
    VTYPE_DIMMER_RGB_INTEGRATOR,
    WTYPE_DIMMER,
    WTYPE_RGB_CONTROLLER,
)
from .coordinator import SinumCoordinator


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

    for device_id, device in coordinator.wtp_devices.items():
        dev_type = device.get("type")
        if dev_type == WTYPE_DIMMER:
            entities.append(SinumBusDimmerLight(coordinator, device_id, entry.entry_id, "wtp"))
        elif dev_type == WTYPE_RGB_CONTROLLER:
            entities.append(SinumBusRgbLight(coordinator, device_id, entry.entry_id, "wtp"))

    for device_id, device in coordinator.sbus_devices.items():
        dev_type = device.get("type")
        if dev_type == STYPE_DIMMER:
            entities.append(SinumBusDimmerLight(coordinator, device_id, entry.entry_id, "sbus"))
        elif dev_type == STYPE_RGB_CONTROLLER:
            entities.append(SinumBusRgbLight(coordinator, device_id, entry.entry_id, "sbus"))

    async_add_entities(entities)


def _label(device: dict[str, Any]) -> str:
    return (device.get("_device_name") or device.get("name", "")).strip()


def _hex_to_hs(hex_color: str) -> tuple[float, float]:
    """Convert #RRGGBB to (hue 0-360, saturation 0-100)."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) < 6:
        return (0.0, 0.0)
    try:
        r, g, b = (int(hex_color[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return (0.0, 0.0)
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
    return h, s


def _hs_to_hex(hue: float, saturation: float) -> str:
    """Convert (hue 0-360, saturation 0-100) to #RRGGBB."""
    h = hue / 60
    s = saturation / 100
    i = math.floor(h)
    f = h - i
    p = 1 - s
    q = 1 - f * s
    t = 1 - (1 - f) * s
    mapping = [(1, t, p), (q, 1, p), (p, 1, t), (p, q, 1), (t, p, 1), (1, p, q)]
    r, g, b = mapping[int(i) % 6]
    return f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"


def _is_rgbww_animation_device(device: dict[str, Any]) -> bool:
    """RGBWW devices (RGB-S5m/P4m) report color/brightness but only accept state via PATCH."""
    return "rgbww" in device.get("labels", [])


def _supported_color_modes(device: dict[str, Any]) -> set[ColorMode]:
    if _is_rgbww_animation_device(device):
        return {ColorMode.ONOFF}
    modes: set[ColorMode] = set()
    if "led_color" in device or device.get("color_mode") == "rgb":
        modes.add(ColorMode.HS)
    if "white_temperature" in device or device.get("color_mode") == "temperature":
        modes.add(ColorMode.COLOR_TEMP)
    if not modes:
        modes.add(ColorMode.BRIGHTNESS)
    return modes


class SinumDimmerLight(CoordinatorEntity[SinumCoordinator], LightEntity):
    """Dimmer/RGB controller integrator."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_min_color_temp_kelvin = 1000
    _attr_max_color_temp_kelvin = 6500
    _attr_icon = "mdi:lightbulb"

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
        if _is_rgbww_animation_device(self._device):
            return ColorMode.ONOFF
        mode = self._device.get("color_mode", "")
        if mode == "rgb":
            return ColorMode.HS
        if mode == "temperature":
            return ColorMode.COLOR_TEMP
        return ColorMode.BRIGHTNESS

    @property
    def is_on(self) -> bool:
        return self._device.get("state") not in (None, "off", False)

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
        payload: dict[str, Any] = {"state": "on"}

        if ATTR_BRIGHTNESS in kwargs:
            payload["brightness"] = round(kwargs[ATTR_BRIGHTNESS] / 255 * 100)

        if ATTR_HS_COLOR in kwargs:
            h, s = kwargs[ATTR_HS_COLOR]
            payload["led_color"] = _hs_to_hex(h, s)

        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            payload["white_temperature"] = kwargs[ATTR_COLOR_TEMP_KELVIN]

        updated = await self.coordinator.client.patch_virtual_device(self._device_id, payload)
        self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        updated = await self.coordinator.client.patch_virtual_device(
            self._device_id, {"state": "off"}
        )
        self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()


class SinumBusDimmerLight(CoordinatorEntity[SinumCoordinator], LightEntity):
    """SBUS or WTP dimmer — uses target_level (0-100) for brightness."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_color_modes: set[ColorMode] = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_icon = "mdi:lightbulb-on"

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
        if self._bus == "wtp":
            updated = await self.coordinator.client.patch_wtp_device(self._device_id, payload)
            self.coordinator.wtp_devices[self._device_id].update(updated)
        else:
            updated = await self.coordinator.client.patch_sbus_device(self._device_id, payload)
            self.coordinator.sbus_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
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
        self.async_write_ha_state()


class SinumBusRgbLight(CoordinatorEntity[SinumCoordinator], LightEntity):
    """SBUS or WTP rgb_controller — brightness, color (HS), and color temperature."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_min_color_temp_kelvin = 1000
    _attr_max_color_temp_kelvin = 6500
    _attr_icon = "mdi:lightbulb-variant"

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
            model=device.get("_parent_model") or f"Sinum {bus.upper()} RGB Controller",
            suggested_area=device.get("_area") or None,
        )

    @property
    def _device(self) -> dict[str, Any]:
        store = (
            self.coordinator.wtp_devices if self._bus == "wtp" else self.coordinator.sbus_devices
        )
        return store.get(self._device_id, {})

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        return _supported_color_modes(self._device)

    @property
    def color_mode(self) -> ColorMode:
        if _is_rgbww_animation_device(self._device):
            return ColorMode.ONOFF
        mode = self._device.get("color_mode", "")
        if mode == "rgb":
            return ColorMode.HS
        if mode == "temperature":
            return ColorMode.COLOR_TEMP
        return ColorMode.BRIGHTNESS

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
        hex_color = self._device.get("led_color") or self._device.get("color")
        if not hex_color:
            return None
        return _hex_to_hs(hex_color)

    @property
    def color_temp_kelvin(self) -> int | None:
        return self._device.get("white_temperature")

    async def async_turn_on(self, **kwargs: Any) -> None:
        payload: dict[str, Any] = {"state": True}
        if not _is_rgbww_animation_device(self._device):
            if ATTR_BRIGHTNESS in kwargs:
                payload["brightness"] = round(kwargs[ATTR_BRIGHTNESS] / 255 * 100)
            if ATTR_HS_COLOR in kwargs:
                h, s = kwargs[ATTR_HS_COLOR]
                payload["led_color"] = _hs_to_hex(h, s)
            if ATTR_COLOR_TEMP_KELVIN in kwargs:
                payload["white_temperature"] = kwargs[ATTR_COLOR_TEMP_KELVIN]
        if self._bus == "wtp":
            updated = await self.coordinator.client.patch_wtp_device(self._device_id, payload)
            self.coordinator.wtp_devices[self._device_id].update(updated)
        else:
            updated = await self.coordinator.client.patch_sbus_device(self._device_id, payload)
            self.coordinator.sbus_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
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
        self.async_write_ha_state()
