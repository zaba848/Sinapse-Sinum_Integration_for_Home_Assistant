"""Gate cover entity (virtual device)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.cover import CoverDeviceClass, CoverEntity, CoverEntityFeature
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ._cover_helpers import _virtual_device_info
from .const import GATE_STATE_CLOSED, GATE_STATE_CLOSING, GATE_STATE_OPENING
from .coordinator import SinumCoordinator, SinumDeviceAvailableMixin


class SinumGateCover(
    SinumDeviceAvailableMixin, CoordinatorEntity[SinumCoordinator], CoverEntity, RestoreEntity
):
    """Gate controller — open/close/stop."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_device_class = CoverDeviceClass.GATE
    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    )

    def __init__(self, coordinator: SinumCoordinator, device_id: int, entry_id: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._restored_closed: bool | None = None
        self._attr_unique_id = f"{entry_id}_virtual_{device_id}"
        self._attr_device_info = _virtual_device_info(
            coordinator, device_id, entry_id, "Sinum Gate"
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._device:
            return
        last = await self.async_get_last_state()
        if last is None or last.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return
        self._restored_closed = last.state == GATE_STATE_CLOSED

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.virtual_devices.get(self._device_id, {})

    @property
    def is_closed(self) -> bool | None:
        if self._device:
            state = self._device.get("state")
            return state == GATE_STATE_CLOSED if state is not None else None
        return self._restored_closed

    @property
    def is_opening(self) -> bool:
        return self._device.get("state") == GATE_STATE_OPENING

    @property
    def is_closing(self) -> bool:
        return self._device.get("state") == GATE_STATE_CLOSING

    async def _patch_command(self, payload: dict[str, Any], err_msg: str) -> None:
        try:
            await self.coordinator.client.patch_virtual_device(self._device_id, payload)
        except Exception as err:
            raise HomeAssistantError(f"{err_msg}: {err}") from err

    async def _command_and_set_state(self, command: str, next_state: str, err_msg: str) -> None:
        await self._patch_command({"command": command}, err_msg)
        # Hub returns 304 for gate commands (async relay pulse) — update optimistically
        self.coordinator.virtual_devices[self._device_id]["state"] = next_state
        self.async_write_ha_state()

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._command_and_set_state("full_open", GATE_STATE_OPENING, "Cannot open gate")

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._command_and_set_state("close", GATE_STATE_CLOSING, "Cannot close gate")

    async def async_stop_cover(self, **kwargs: Any) -> None:
        await self._patch_command({"command": "stop"}, "Cannot stop gate")
        # Re-fetch actual state: gate may have stopped at unknown position
        updated = await self.coordinator.client.get_virtual_device(self._device_id)
        if updated:
            self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()
