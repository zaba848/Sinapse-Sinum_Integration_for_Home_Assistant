"""WTP blind cover entity."""

from __future__ import annotations

from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ._cover_helpers import (
    _compare_target_current,
    _label,
    _restore_cover_from_last_state,
)
from .const import DOMAIN, MANUFACTURER
from .coordinator import SinumCoordinator, SinumDeviceAvailableMixin, via_device_for


class SinumWtpBlindCover(
    SinumDeviceAvailableMixin, CoordinatorEntity[SinumCoordinator], CoverEntity, RestoreEntity
):
    """WTP blind_controller — position 0 (closed) – 100 (open), no tilt."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_device_class = CoverDeviceClass.BLIND
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(self, coordinator: SinumCoordinator, device_id: int, entry_id: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry_id}_wtp_{device_id}"
        device = coordinator.wtp_devices.get(device_id, {})
        label = _label(device)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_wtp_{device_id}")},
            name=label,
            manufacturer=MANUFACTURER,
            model=device.get("_parent_model") or "Sinum WTP Blind Controller",
            suggested_area=device.get("_area") or None,
            via_device=via_device_for(device, entry_id),
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._device:
            return
        await _restore_cover_from_last_state(self, restore_tilt=False)

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.wtp_devices.get(self._device_id, {})

    @property
    def current_cover_position(self) -> int | None:
        if self._device:
            pos = self._device.get("current_opening")
            return int(pos) if pos is not None else None
        return self._attr_current_cover_position

    @property
    def is_closed(self) -> bool | None:
        pos = self.current_cover_position
        if pos is None:
            return None
        return pos == 0

    @property
    def is_opening(self) -> bool:
        delta = _compare_target_current(self._device)
        return delta is not None and bool(self._device.get("action_in_progress")) and delta > 0

    @property
    def is_closing(self) -> bool:
        delta = _compare_target_current(self._device)
        return delta is not None and bool(self._device.get("action_in_progress")) and delta < 0

    async def async_open_cover(self, **kwargs: Any) -> None:
        try:
            updated = await self.coordinator.client.patch_wtp_device(
                self._device_id, {"command": "open", "opening_percentage": 100}
            )
        except Exception as err:
            raise HomeAssistantError(f"Cannot open cover: {err}") from err
        self.coordinator.wtp_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        try:
            updated = await self.coordinator.client.patch_wtp_device(
                self._device_id, {"command": "open", "opening_percentage": 0}
            )
        except Exception as err:
            raise HomeAssistantError(f"Cannot close cover: {err}") from err
        self.coordinator.wtp_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        try:
            updated = await self.coordinator.client.patch_wtp_device(
                self._device_id, {"command": "stop"}
            )
        except Exception as err:
            raise HomeAssistantError(f"Cannot stop cover: {err}") from err
        self.coordinator.wtp_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        position = kwargs[ATTR_POSITION]
        try:
            updated = await self.coordinator.client.patch_wtp_device(
                self._device_id, {"command": "open", "opening_percentage": position}
            )
        except Exception as err:
            raise HomeAssistantError(f"Cannot set cover position: {err}") from err
        self.coordinator.wtp_devices[self._device_id].update(updated)
        self.async_write_ha_state()
