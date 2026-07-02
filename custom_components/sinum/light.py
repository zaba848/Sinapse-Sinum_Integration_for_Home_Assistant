from __future__ import annotations

from typing import Any

from homeassistant.components.light import LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SinumConfigEntry
from ._light_helpers import (
    _color_mode,
    _hex_to_hs,
    _hex_to_hsv,
    _hs_to_hex,
    _kelvin_to_hex,
    _labels,
    _supported_color_modes,
    _supports_color_temperature,
)
from .const import (
    STYPE_BUTTON,
    STYPE_DIMMER,
    STYPE_RGB_CONTROLLER,
    VTYPE_DIMMER_RGB,
    VTYPE_DIMMER_RGB_INTEGRATOR,
    WTYPE_BUTTON,
    WTYPE_DIMMER,
    WTYPE_RGB_CONTROLLER,
)
from .coordinator import SinumCoordinator
from .light_dimmer import SinumBusDimmerLight, SinumDimmerLight
from .light_rgb import SinumBusRgbLight, SinumButtonLight

PARALLEL_UPDATES = 0

# Re-exported for backward compatibility with tests and external imports
__all__ = [
    "SinumBusDimmerLight",
    "SinumBusRgbLight",
    "SinumButtonLight",
    "SinumDimmerLight",
    "_color_mode",
    "_hex_to_hs",
    "_hex_to_hsv",
    "_hs_to_hex",
    "_kelvin_to_hex",
    "_labels",
    "_supported_color_modes",
    "_supports_color_temperature",
    "async_setup_entry",
]


def _bus_store(coordinator: SinumCoordinator, bus: str) -> dict[int, dict]:
    return coordinator.wtp_devices if bus == "wtp" else coordinator.sbus_devices


def _bus_types(bus: str) -> tuple[str, str, str]:
    if bus == "wtp":
        return WTYPE_DIMMER, WTYPE_RGB_CONTROLLER, WTYPE_BUTTON
    return STYPE_DIMMER, STYPE_RGB_CONTROLLER, STYPE_BUTTON


def _is_button_with_color(dev_type: str | None, button_type: str, device: dict[str, Any]) -> bool:
    return dev_type == button_type and "color" in device


def _bus_light_entity(
    coordinator: SinumCoordinator,
    device_id: int,
    entry_id: str,
    bus: str,
    device: dict[str, Any],
    dimmer_type: str,
    rgb_type: str,
    button_type: str,
) -> LightEntity | None:
    dev_type = device.get("type")
    if dev_type == dimmer_type:
        return SinumBusDimmerLight(coordinator, device_id, entry_id, bus)
    if dev_type == rgb_type:
        return SinumBusRgbLight(coordinator, device_id, entry_id, bus)
    if _is_button_with_color(dev_type, button_type, device):
        return SinumButtonLight(coordinator, device_id, entry_id, bus)
    return None


def _add_bus_lights(
    coordinator: SinumCoordinator, entities: list[LightEntity], entry_id: str, bus: str
) -> None:
    store = _bus_store(coordinator, bus)
    dimmer_type, rgb_type, button_type = _bus_types(bus)
    for device_id, device in store.items():
        entity = _bus_light_entity(
            coordinator, device_id, entry_id, bus, device, dimmer_type, rgb_type, button_type
        )
        if entity is not None:
            entities.append(entity)


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
