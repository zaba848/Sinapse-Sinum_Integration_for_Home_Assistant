from __future__ import annotations

import math
from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_HS_COLOR, ColorMode
from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN

from .const import (
    STYPE_RGB_CONTROLLER,
    VTYPE_DIMMER_RGB,
    VTYPE_DIMMER_RGB_INTEGRATOR,
    WTYPE_RGB_CONTROLLER,
)

_RGB_DEVICE_TYPES = frozenset(
    {VTYPE_DIMMER_RGB, VTYPE_DIMMER_RGB_INTEGRATOR, WTYPE_RGB_CONTROLLER, STYPE_RGB_CONTROLLER}
)
_RGB_COLOR_MODES = frozenset({"rgb", "hs", "color"})
_COLOR_TEMP_MODES = frozenset({"temperature", "color_temp", "white_temperature"})


def _label(device: dict[str, Any]) -> str:
    return (device.get("_device_name") or device.get("name", "")).strip()


def _parse_hex_rgb(hex_color: str) -> tuple[float, float, float] | None:
    normalized = hex_color.lstrip("#")
    if len(normalized) < 6:
        return None
    try:
        r = int(normalized[0:2], 16) / 255.0
        g = int(normalized[2:4], 16) / 255.0
        b = int(normalized[4:6], 16) / 255.0
        return (r, g, b)
    except ValueError:
        return None


def _hue_from_rgb(r: float, g: float, b: float, delta: float, max_c: float) -> float:
    if delta == 0:
        return 0.0
    if max_c == r:
        return 60 * (((g - b) / delta) % 6)
    if max_c == g:
        return 60 * ((b - r) / delta + 2)
    return 60 * ((r - g) / delta + 4)


def _hex_to_hsv(hex_color: str) -> tuple[float, float, float]:
    """Convert #RRGGBB to (hue 0-360, saturation 0-100, value 0-1)."""
    rgb = _parse_hex_rgb(hex_color)
    if rgb is None:
        return (0.0, 0.0, 1.0)
    r, g, b = rgb
    max_c = max(r, g, b)
    min_c = min(r, g, b)
    delta = max_c - min_c
    h = _hue_from_rgb(r, g, b, delta, max_c)
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


def _has_rgb_label(labels: set[str]) -> bool:
    return any("rgb" in label for label in labels)


def _rgb_by_label_or_type(device: dict[str, Any]) -> bool:
    return _has_rgb_label(_labels(device)) or device.get("type") in _RGB_DEVICE_TYPES


def _supports_rgb(device: dict[str, Any]) -> bool:
    mode = str(device.get("color_mode", "")).lower()
    return "led_color" in device or mode in _RGB_COLOR_MODES or _rgb_by_label_or_type(device)


def _supports_color_temperature(device: dict[str, Any]) -> bool:
    labels = _labels(device)
    mode = str(device.get("color_mode", "")).lower()
    return (
        "white_temperature" in device
        or mode in _COLOR_TEMP_MODES
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


def _color_mode_is_rgb(mode: str, device: dict[str, Any]) -> bool:
    return mode in _RGB_COLOR_MODES or _supports_rgb(device)


def _color_mode(device: dict[str, Any]) -> ColorMode:
    mode = str(device.get("color_mode", "")).lower()
    if mode in _COLOR_TEMP_MODES:
        return ColorMode.COLOR_TEMP
    if _color_mode_is_rgb(mode, device):
        return ColorMode.HS
    if _supports_color_temperature(device):
        return ColorMode.COLOR_TEMP
    return ColorMode.BRIGHTNESS


async def _restore_light_state(entity: Any) -> None:
    last = await entity.async_get_last_state()
    if last is None or last.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return
    entity._attr_is_on = last.state == STATE_ON
    if (v := last.attributes.get(ATTR_BRIGHTNESS)) is not None:
        entity._attr_brightness = int(v)


async def _restore_button_light_state(entity: Any) -> None:
    last = await entity.async_get_last_state()
    if last is None or last.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return
    entity._attr_is_on = last.state == STATE_ON
    if last.attributes.get(ATTR_HS_COLOR):
        entity._attr_hs_color = tuple(last.attributes[ATTR_HS_COLOR])
