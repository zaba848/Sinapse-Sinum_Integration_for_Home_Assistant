from __future__ import annotations

import math
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SinumConfigEntry
from .const import DOMAIN, VTYPE_DIMMER_RGB
from .coordinator import SinumCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SinumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SinumCoordinator = entry.runtime_data
    entities: list[LightEntity] = []

    for device_id, device in coordinator.virtual_devices.items():
        if device.get("type") == VTYPE_DIMMER_RGB:
            entities.append(SinumDimmerLight(coordinator, device_id, entry.entry_id))

    async_add_entities(entities)


def _label(device: dict[str, Any]) -> str:
    room = device.get("_room", "")
    name = device.get("_device_name", "")
    return f"{room} {name}".strip() if room else name


def _hex_to_hs(hex_color: str) -> tuple[float, float]:
    """Convert #RRGGBB to (hue 0-360, saturation 0-100)."""
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
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
    return "#{:02X}{:02X}{:02X}".format(int(r * 255), int(g * 255), int(b * 255))


def _supported_color_modes(device: dict[str, Any]) -> set[ColorMode]:
    modes: set[ColorMode] = {ColorMode.BRIGHTNESS}
    if "led_color" in device or device.get("color_mode") == "rgb":
        modes.add(ColorMode.HS)
    if "white_temperature" in device or device.get("color_mode") == "temperature":
        modes.add(ColorMode.COLOR_TEMP)
    return modes


class SinumDimmerLight(CoordinatorEntity[SinumCoordinator], LightEntity):
    """Dimmer/RGB controller integrator."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_min_color_temp_kelvin = 1000
    _attr_max_color_temp_kelvin = 6500

    def __init__(self, coordinator: SinumCoordinator, device_id: int, entry_id: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry_id}_virtual_{device_id}"
        device = coordinator.virtual_devices.get(device_id, {})
        self._attr_supported_color_modes = _supported_color_modes(device)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_virtual_{device_id}")},
            name=_label(device),
            manufacturer="TECH Sterowniki",
            model="Sinum Dimmer/RGB Controller",
            suggested_area=device.get("_area") or None,
        )

    @property
    def name(self) -> str:
        return _label(self.coordinator.virtual_devices.get(self._device_id, {}))

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.virtual_devices.get(self._device_id, {})

    @property
    def color_mode(self) -> ColorMode:
        mode = self._device.get("color_mode", "")
        if mode == "rgb":
            return ColorMode.HS
        if mode == "temperature":
            return ColorMode.COLOR_TEMP
        return ColorMode.BRIGHTNESS

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        return self._attr_supported_color_modes

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
            payload["color_mode"] = "rgb"

        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            payload["white_temperature"] = kwargs[ATTR_COLOR_TEMP_KELVIN]
            payload["color_mode"] = "temperature"

        updated = await self.coordinator.client.patch_virtual_device(self._device_id, payload)
        self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        updated = await self.coordinator.client.patch_virtual_device(self._device_id, {"state": "off"})
        self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()
