from __future__ import annotations

from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SinumConfigEntry
from ._cover_helpers import _restore_cover_from_last_state, _virtual_device_info
from .const import (
    STYPE_BLIND_CONTROLLER,
    VTYPE_BLIND,
    VTYPE_GATE,
    WTYPE_BLIND_CONTROLLER,
)
from .coordinator import SinumCoordinator, SinumDeviceAvailableMixin
from .cover_gate import SinumGateCover  # noqa: F401
from .cover_sbus import SinumSbusBlindCover
from .cover_wtp import SinumWtpBlindCover

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SinumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SinumCoordinator = entry.runtime_data
    entities: list[CoverEntity] = []

    _add_virtual_covers(coordinator, entry.entry_id, entities)
    _add_wtp_covers(coordinator, entry.entry_id, entities)
    _add_sbus_covers(coordinator, entry.entry_id, entities)

    async_add_entities(entities)


def _add_virtual_covers(
    coordinator: SinumCoordinator, entry_id: str, entities: list[CoverEntity]
) -> None:
    for device_id, device in coordinator.virtual_devices.items():
        dev_type = device.get("type")
        if dev_type == VTYPE_BLIND:
            entities.append(SinumBlindCover(coordinator, device_id, entry_id))
        elif dev_type == VTYPE_GATE:
            entities.append(SinumGateCover(coordinator, device_id, entry_id))


def _add_wtp_covers(
    coordinator: SinumCoordinator, entry_id: str, entities: list[CoverEntity]
) -> None:
    for device_id, device in coordinator.wtp_devices.items():
        if device.get("type") != WTYPE_BLIND_CONTROLLER:
            continue
        entities.append(SinumWtpBlindCover(coordinator, device_id, entry_id))


def _add_sbus_covers(
    coordinator: SinumCoordinator, entry_id: str, entities: list[CoverEntity]
) -> None:
    for device_id, device in coordinator.sbus_devices.items():
        if device.get("type") != STYPE_BLIND_CONTROLLER:
            continue
        entities.append(SinumSbusBlindCover(coordinator, device_id, entry_id))


class SinumBlindCover(
    SinumDeviceAvailableMixin, CoordinatorEntity[SinumCoordinator], CoverEntity, RestoreEntity
):
    """Blind controller integrator — position 0 (closed) – 100 (open), optional tilt."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_device_class = CoverDeviceClass.BLIND
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
        | CoverEntityFeature.SET_TILT_POSITION
    )

    def __init__(self, coordinator: SinumCoordinator, device_id: int, entry_id: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry_id}_virtual_{device_id}"
        self._attr_device_info = _virtual_device_info(
            coordinator, device_id, entry_id, "Sinum Blind Controller"
        )
        device = coordinator.virtual_devices.get(device_id, {})
        if (pos := device.get("last_set_target_opening")) is not None:
            self._attr_current_cover_position = int(pos)
        if (tilt := device.get("last_set_target_tilt")) is not None:
            self._attr_current_cover_tilt_position = int(tilt)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._device:
            return
        await _restore_cover_from_last_state(self, restore_tilt=True)

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.virtual_devices.get(self._device_id, {})

    @property
    def current_cover_position(self) -> int | None:
        if self._device:
            pos = self._device.get("last_set_target_opening")
            if pos is not None:
                self._attr_current_cover_position = int(pos)
                return int(pos)
        return self._attr_current_cover_position

    @property
    def current_cover_tilt_position(self) -> int | None:
        if self._device:
            tilt = self._device.get("last_set_target_tilt")
            if tilt is not None:
                self._attr_current_cover_tilt_position = int(tilt)
                return int(tilt)
        return self._attr_current_cover_tilt_position

    @property
    def is_closed(self) -> bool | None:
        pos = self.current_cover_position
        if pos is None:
            return None
        return pos == 0

    @property
    def is_opening(self) -> bool:
        return bool(self._device.get("action_in_progress")) and not self.is_closed

    @property
    def is_closing(self) -> bool:
        return bool(self._device.get("action_in_progress")) and bool(self.is_closed)

    async def _patch_and_apply(self, payload: dict[str, Any], err_msg: str) -> None:
        try:
            updated = await self.coordinator.client.patch_virtual_device(self._device_id, payload)
        except Exception as err:
            raise HomeAssistantError(f"{err_msg}: {err}") from err
        self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._patch_and_apply(
            {"command": "open", "opening_percentage": 100}, "Cannot open cover"
        )

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._patch_and_apply(
            {"command": "open", "opening_percentage": 0}, "Cannot close cover"
        )

    async def async_stop_cover(self, **kwargs: Any) -> None:
        await self._patch_and_apply({"command": "stop"}, "Cannot stop cover")

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        await self._patch_and_apply(
            {"command": "open", "opening_percentage": kwargs[ATTR_POSITION]},
            "Cannot set cover position",
        )

    async def async_set_cover_tilt_position(self, **kwargs: Any) -> None:
        await self._patch_and_apply(
            {"command": "tilt", "tilt_percentage": kwargs[ATTR_TILT_POSITION]},
            "Cannot set cover tilt",
        )


__all__ = [
    "SinumBlindCover",
    "SinumGateCover",
    "SinumSbusBlindCover",
    "SinumWtpBlindCover",
    "async_setup_entry",
]
