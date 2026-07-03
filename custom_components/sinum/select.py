from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SinumConfigEntry
from .climate_fan_coil import _fan_coil_device_info
from .const import STYPE_FAN_COIL, WTYPE_FAN_COIL, WTYPE_FAN_COIL_V2
from .coordinator import SinumCoordinator, SinumDeviceAvailableMixin

PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)

_DEFAULT_WORK_MODES = ["heating", "cooling", "automatic", "off"]
_WTP_FAN_COIL_TYPES = {WTYPE_FAN_COIL, WTYPE_FAN_COIL_V2}


def _work_mode_options(device: dict[str, Any]) -> list[str]:
    declared = device.get("available_work_modes")
    if isinstance(declared, list) and declared:
        return [str(m) for m in declared]
    return _DEFAULT_WORK_MODES


def _needs_select(device: dict[str, Any]) -> bool:
    """True if device has work_mode but no temperature setpoint (no CLIMATE entity)."""
    return "work_mode" in device and "target_temperature" not in device


def _fan_store(coordinator: SinumCoordinator, bus: str) -> dict[int, dict[str, Any]]:
    return coordinator.sbus_devices if bus == "sbus" else coordinator.wtp_devices


def _add_from_store(
    coordinator: SinumCoordinator,
    entities: list[SelectEntity],
    entry_id: str,
    bus: str,
    store: dict[int, dict[str, Any]],
    fan_coil_types: set[str],
) -> None:
    for device_id, device in store.items():
        if device.get("type") in fan_coil_types and _needs_select(device):
            entities.append(SinumFanCoilModeSelect(coordinator, device_id, entry_id, bus))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SinumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SinumCoordinator = entry.runtime_data
    entities: list[SelectEntity] = []
    _add_from_store(
        coordinator, entities, entry.entry_id, "sbus", coordinator.sbus_devices, {STYPE_FAN_COIL}
    )
    _add_from_store(
        coordinator, entities, entry.entry_id, "wtp", coordinator.wtp_devices, _WTP_FAN_COIL_TYPES
    )
    async_add_entities(entities)


class SinumFanCoilModeSelect(
    SinumDeviceAvailableMixin, CoordinatorEntity[SinumCoordinator], SelectEntity
):
    """Work-mode selector for fan_coil devices that have no temperature setpoint.

    Only created when the device has work_mode but not target_temperature — i.e.
    no CLIMATE entity is created, so SELECT fills the mode-control gap.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "fan_coil_work_mode"
    _attr_icon = "mdi:hvac"

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
        self._attr_unique_id = f"{entry_id}_{bus}_{device_id}_work_mode"
        store = _fan_store(coordinator, bus)
        device = store.get(device_id, {})
        self._attr_options = _work_mode_options(device)
        self._attr_device_info = _fan_coil_device_info(device, entry_id, bus, device_id)

    @property
    def _device(self) -> dict[str, Any]:
        return _fan_store(self.coordinator, self._bus).get(self._device_id, {})

    @property
    def current_option(self) -> str | None:
        return self._device.get("work_mode")

    async def async_select_option(self, option: str) -> None:
        try:
            if self._bus == "sbus":
                updated = await self.coordinator.client.patch_sbus_device(
                    self._device_id, {"work_mode": option}
                )
            else:
                updated = await self.coordinator.client.patch_wtp_device(
                    self._device_id, {"work_mode": option}
                )
        except Exception as err:
            raise HomeAssistantError(f"Cannot set fan coil work mode: {err}") from err
        if updated:
            self._device.update(updated)
        self.async_write_ha_state()
