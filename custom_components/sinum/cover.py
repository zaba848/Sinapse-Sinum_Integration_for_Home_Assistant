from __future__ import annotations

from typing import Any

from homeassistant.components.cover import (
    ATTR_CURRENT_POSITION,
    ATTR_CURRENT_TILT_POSITION,
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SinumConfigEntry
from .const import (
    DOMAIN,
    GATE_STATE_CLOSED,
    GATE_STATE_CLOSING,
    GATE_STATE_OPENING,
    STYPE_BLIND_CONTROLLER,
    VTYPE_BLIND,
    VTYPE_GATE,
    WTYPE_BLIND_CONTROLLER,
)
from .coordinator import SinumCoordinator, SinumDeviceAvailableMixin, via_device_for


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


def _label(device: dict[str, Any]) -> str:
    return (device.get("_device_name") or device.get("name", "")).strip()


def _device_info(
    coordinator: SinumCoordinator, device_id: int, entry_id: str, model: str
) -> DeviceInfo:
    device = coordinator.virtual_devices.get(device_id, {})
    label = _label(device)
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_virtual_{device_id}")},
        name=label,
        manufacturer="TECH Sterowniki",
        model=model,
        suggested_area=device.get("_area") or None,
    )


async def _restore_cover_from_last_state(entity: Any, restore_tilt: bool) -> None:
    last = await entity.async_get_last_state()
    if last is None or last.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return
    if (v := last.attributes.get(ATTR_CURRENT_POSITION)) is not None:
        entity._attr_current_cover_position = int(v)
    if restore_tilt and (v := last.attributes.get(ATTR_CURRENT_TILT_POSITION)) is not None:
        entity._attr_current_cover_tilt_position = int(v)


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
        self._attr_device_info = _device_info(
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

    async def async_open_cover(self, **kwargs: Any) -> None:
        try:
            updated = await self.coordinator.client.patch_virtual_device(
                self._device_id, {"command": "open", "opening_percentage": 100}
            )
        except Exception as err:
            raise HomeAssistantError(f"Cannot open cover: {err}") from err
        self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        try:
            updated = await self.coordinator.client.patch_virtual_device(
                self._device_id, {"command": "open", "opening_percentage": 0}
            )
        except Exception as err:
            raise HomeAssistantError(f"Cannot close cover: {err}") from err
        self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        try:
            updated = await self.coordinator.client.patch_virtual_device(
                self._device_id, {"command": "stop"}
            )
        except Exception as err:
            raise HomeAssistantError(f"Cannot stop cover: {err}") from err
        self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        position = kwargs[ATTR_POSITION]
        try:
            updated = await self.coordinator.client.patch_virtual_device(
                self._device_id, {"command": "open", "opening_percentage": position}
            )
        except Exception as err:
            raise HomeAssistantError(f"Cannot set cover position: {err}") from err
        self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_set_cover_tilt_position(self, **kwargs: Any) -> None:
        tilt = kwargs[ATTR_TILT_POSITION]
        try:
            updated = await self.coordinator.client.patch_virtual_device(
                self._device_id, {"command": "tilt", "tilt_percentage": tilt}
            )
        except Exception as err:
            raise HomeAssistantError(f"Cannot set cover tilt: {err}") from err
        self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()


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
        self._attr_device_info = _device_info(coordinator, device_id, entry_id, "Sinum Gate")

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

    async def async_open_cover(self, **kwargs: Any) -> None:
        try:
            await self.coordinator.client.patch_virtual_device(
                self._device_id, {"command": "full_open"}
            )
        except Exception as err:
            raise HomeAssistantError(f"Cannot open gate: {err}") from err
        # Hub returns 304 for gate commands (async relay pulse) — update optimistically
        self.coordinator.virtual_devices[self._device_id]["state"] = GATE_STATE_OPENING
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        try:
            await self.coordinator.client.patch_virtual_device(
                self._device_id, {"command": "close"}
            )
        except Exception as err:
            raise HomeAssistantError(f"Cannot close gate: {err}") from err
        self.coordinator.virtual_devices[self._device_id]["state"] = GATE_STATE_CLOSING
        self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        try:
            await self.coordinator.client.patch_virtual_device(self._device_id, {"command": "stop"})
        except Exception as err:
            raise HomeAssistantError(f"Cannot stop gate: {err}") from err
        # Re-fetch actual state: gate may have stopped at unknown position
        updated = await self.coordinator.client.get_virtual_device(self._device_id)
        if updated:
            self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()


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
            manufacturer="TECH Sterowniki",
            model=device.get("_parent_model") or "Sinum WTP Blind Controller",
            suggested_area=device.get("_area") or None,
            via_device=via_device_for(device, entry_id),
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._device:
            return
        last = await self.async_get_last_state()
        if last is None or last.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return
        if (v := last.attributes.get(ATTR_CURRENT_POSITION)) is not None:
            self._attr_current_cover_position = int(v)

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
        d = self._device
        target = d.get("target_opening")
        current = d.get("current_opening")
        if target is None or current is None:
            return False
        try:
            return bool(d.get("action_in_progress")) and int(target) > int(current)
        except (TypeError, ValueError):
            return False

    @property
    def is_closing(self) -> bool:
        d = self._device
        target = d.get("target_opening")
        current = d.get("current_opening")
        if target is None or current is None:
            return False
        try:
            return bool(d.get("action_in_progress")) and int(target) < int(current)
        except (TypeError, ValueError):
            return False

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


class SinumSbusBlindCover(
    SinumDeviceAvailableMixin, CoordinatorEntity[SinumCoordinator], CoverEntity, RestoreEntity
):
    """SBUS blind_controller — position + tilt (venetian blinds)."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_device_class = CoverDeviceClass.BLIND

    def __init__(self, coordinator: SinumCoordinator, device_id: int, entry_id: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry_id}_sbus_{device_id}"
        device = coordinator.sbus_devices.get(device_id, {})
        label = _label(device)
        has_tilt = "current_tilt" in device or "target_tilt" in device
        self._attr_supported_features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.STOP
            | CoverEntityFeature.SET_POSITION
            | (CoverEntityFeature.SET_TILT_POSITION if has_tilt else CoverEntityFeature(0))
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_sbus_{device_id}")},
            name=label,
            manufacturer="TECH Sterowniki",
            model=device.get("_parent_model") or "Sinum SBUS Blind Controller",
            suggested_area=device.get("_area") or None,
            via_device=via_device_for(device, entry_id),
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._device:
            return
        await _restore_cover_from_last_state(self, restore_tilt=True)

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.sbus_devices.get(self._device_id, {})

    @property
    def current_cover_position(self) -> int | None:
        if self._device:
            pos = self._device.get("current_opening")
            return int(pos) if pos is not None else None
        return self._attr_current_cover_position

    @property
    def current_cover_tilt_position(self) -> int | None:
        if self._device:
            tilt = self._device.get("current_tilt")
            return int(tilt) if tilt is not None else None
        return self._attr_current_cover_tilt_position

    @property
    def is_closed(self) -> bool | None:
        pos = self.current_cover_position
        if pos is None:
            return None
        return pos == 0

    @property
    def is_opening(self) -> bool:
        d = self._device
        target = d.get("target_opening")
        current = d.get("current_opening")
        if target is None or current is None:
            return False
        try:
            return int(target) > int(current)
        except (TypeError, ValueError):
            return False

    @property
    def is_closing(self) -> bool:
        d = self._device
        target = d.get("target_opening")
        current = d.get("current_opening")
        if target is None or current is None:
            return False
        try:
            return int(target) < int(current)
        except (TypeError, ValueError):
            return False

    async def async_open_cover(self, **kwargs: Any) -> None:
        try:
            updated = await self.coordinator.client.patch_sbus_device(
                self._device_id, {"command": "open", "opening_percentage": 100}
            )
        except Exception as err:
            raise HomeAssistantError(f"Cannot open cover: {err}") from err
        self.coordinator.sbus_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        try:
            updated = await self.coordinator.client.patch_sbus_device(
                self._device_id, {"command": "open", "opening_percentage": 0}
            )
        except Exception as err:
            raise HomeAssistantError(f"Cannot close cover: {err}") from err
        self.coordinator.sbus_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        try:
            updated = await self.coordinator.client.patch_sbus_device(
                self._device_id, {"command": "stop"}
            )
        except Exception as err:
            raise HomeAssistantError(f"Cannot stop cover: {err}") from err
        self.coordinator.sbus_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        position = kwargs[ATTR_POSITION]
        try:
            updated = await self.coordinator.client.patch_sbus_device(
                self._device_id, {"command": "open", "opening_percentage": position}
            )
        except Exception as err:
            raise HomeAssistantError(f"Cannot set cover position: {err}") from err
        self.coordinator.sbus_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_set_cover_tilt_position(self, **kwargs: Any) -> None:
        tilt = kwargs[ATTR_TILT_POSITION]
        try:
            updated = await self.coordinator.client.patch_sbus_device(
                self._device_id, {"command": "tilt", "tilt_percentage": tilt}
            )
        except Exception as err:
            raise HomeAssistantError(f"Cannot set cover tilt: {err}") from err
        self.coordinator.sbus_devices[self._device_id].update(updated)
        self.async_write_ha_state()
