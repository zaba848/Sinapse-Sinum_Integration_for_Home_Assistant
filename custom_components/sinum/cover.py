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
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
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
from .coordinator import SinumCoordinator, via_device_for


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SinumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SinumCoordinator = entry.runtime_data
    entities: list[CoverEntity] = []

    for device_id, device in coordinator.virtual_devices.items():
        dev_type = device.get("type")
        if dev_type == VTYPE_BLIND:
            entities.append(SinumBlindCover(coordinator, device_id, entry.entry_id))
        elif dev_type == VTYPE_GATE:
            entities.append(SinumGateCover(coordinator, device_id, entry.entry_id))

    for device_id, device in coordinator.wtp_devices.items():
        if device.get("type") == WTYPE_BLIND_CONTROLLER:
            entities.append(SinumWtpBlindCover(coordinator, device_id, entry.entry_id))

    for device_id, device in coordinator.sbus_devices.items():
        if device.get("type") == STYPE_BLIND_CONTROLLER:
            entities.append(SinumSbusBlindCover(coordinator, device_id, entry.entry_id))

    async_add_entities(entities)


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


class SinumBlindCover(CoordinatorEntity[SinumCoordinator], CoverEntity):
    """Blind controller integrator — position 0 (closed) – 100 (open), optional tilt."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_device_class = CoverDeviceClass.BLIND
    _attr_icon = "mdi:blinds"
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

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.virtual_devices.get(self._device_id, {})

    @property
    def is_closed(self) -> bool | None:
        pos = self._device.get("last_set_target_opening")
        if pos is None:
            return None
        return int(pos) == 0

    @property
    def is_opening(self) -> bool:
        return bool(self._device.get("action_in_progress")) and not self.is_closed

    @property
    def is_closing(self) -> bool:
        return bool(self._device.get("action_in_progress")) and bool(self.is_closed)

    @property
    def current_cover_position(self) -> int | None:
        pos = self._device.get("last_set_target_opening")
        return int(pos) if pos is not None else None

    @property
    def current_cover_tilt_position(self) -> int | None:
        tilt = self._device.get("last_set_target_tilt")
        return int(tilt) if tilt is not None else None

    async def async_open_cover(self, **kwargs: Any) -> None:
        updated = await self.coordinator.client.patch_virtual_device(
            self._device_id, {"command": "open", "opening_percentage": 100}
        )
        self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        updated = await self.coordinator.client.patch_virtual_device(
            self._device_id, {"command": "open", "opening_percentage": 0}
        )
        self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        updated = await self.coordinator.client.patch_virtual_device(
            self._device_id, {"command": "stop"}
        )
        self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        position = kwargs[ATTR_POSITION]
        updated = await self.coordinator.client.patch_virtual_device(
            self._device_id, {"command": "open", "opening_percentage": position}
        )
        self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_set_cover_tilt_position(self, **kwargs: Any) -> None:
        tilt = kwargs[ATTR_TILT_POSITION]
        updated = await self.coordinator.client.patch_virtual_device(
            self._device_id, {"command": "tilt", "tilt_percentage": tilt}
        )
        self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()


class SinumGateCover(CoordinatorEntity[SinumCoordinator], CoverEntity):
    """Gate controller — open/close/stop."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_device_class = CoverDeviceClass.GATE
    _attr_icon = "mdi:gate"
    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    )

    def __init__(self, coordinator: SinumCoordinator, device_id: int, entry_id: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry_id}_virtual_{device_id}"
        self._attr_device_info = _device_info(coordinator, device_id, entry_id, "Sinum Gate")

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.virtual_devices.get(self._device_id, {})

    @property
    def is_closed(self) -> bool | None:
        state = self._device.get("state")
        if state is None:
            return None
        return state == GATE_STATE_CLOSED

    @property
    def is_opening(self) -> bool:
        return self._device.get("state") == GATE_STATE_OPENING

    @property
    def is_closing(self) -> bool:
        return self._device.get("state") == GATE_STATE_CLOSING

    async def async_open_cover(self, **kwargs: Any) -> None:
        updated = await self.coordinator.client.patch_virtual_device(
            self._device_id, {"command": "full_open"}
        )
        self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        updated = await self.coordinator.client.patch_virtual_device(
            self._device_id, {"command": "close"}
        )
        self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        updated = await self.coordinator.client.patch_virtual_device(
            self._device_id, {"command": "stop"}
        )
        self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()


class SinumWtpBlindCover(CoordinatorEntity[SinumCoordinator], CoverEntity):
    """WTP blind_controller — position 0 (closed) – 100 (open), no tilt."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_device_class = CoverDeviceClass.BLIND
    _attr_icon = "mdi:blinds-horizontal"
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

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.wtp_devices.get(self._device_id, {})

    @property
    def is_closed(self) -> bool | None:
        pos = self._device.get("current_opening")
        if pos is None:
            return None
        return int(pos) == 0

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

    @property
    def current_cover_position(self) -> int | None:
        pos = self._device.get("current_opening")
        return int(pos) if pos is not None else None

    async def async_open_cover(self, **kwargs: Any) -> None:
        updated = await self.coordinator.client.patch_wtp_device(
            self._device_id, {"command": "open", "opening_percentage": 100}
        )
        self.coordinator.wtp_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        updated = await self.coordinator.client.patch_wtp_device(
            self._device_id, {"command": "open", "opening_percentage": 0}
        )
        self.coordinator.wtp_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        updated = await self.coordinator.client.patch_wtp_device(
            self._device_id, {"command": "stop"}
        )
        self.coordinator.wtp_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        position = kwargs[ATTR_POSITION]
        updated = await self.coordinator.client.patch_wtp_device(
            self._device_id, {"command": "open", "opening_percentage": position}
        )
        self.coordinator.wtp_devices[self._device_id].update(updated)
        self.async_write_ha_state()


class SinumSbusBlindCover(CoordinatorEntity[SinumCoordinator], CoverEntity):
    """SBUS blind_controller — position + tilt (venetian blinds)."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_device_class = CoverDeviceClass.BLIND
    _attr_icon = "mdi:blinds"

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

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.sbus_devices.get(self._device_id, {})

    @property
    def is_closed(self) -> bool | None:
        pos = self._device.get("current_opening")
        if pos is None:
            return None
        return int(pos) == 0

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

    @property
    def current_cover_position(self) -> int | None:
        pos = self._device.get("current_opening")
        return int(pos) if pos is not None else None

    @property
    def current_cover_tilt_position(self) -> int | None:
        tilt = self._device.get("current_tilt")
        return int(tilt) if tilt is not None else None

    async def async_open_cover(self, **kwargs: Any) -> None:
        updated = await self.coordinator.client.patch_sbus_device(
            self._device_id, {"command": "open", "opening_percentage": 100}
        )
        self.coordinator.sbus_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        updated = await self.coordinator.client.patch_sbus_device(
            self._device_id, {"command": "open", "opening_percentage": 0}
        )
        self.coordinator.sbus_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        updated = await self.coordinator.client.patch_sbus_device(
            self._device_id, {"command": "stop"}
        )
        self.coordinator.sbus_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        position = kwargs[ATTR_POSITION]
        updated = await self.coordinator.client.patch_sbus_device(
            self._device_id, {"command": "open", "opening_percentage": position}
        )
        self.coordinator.sbus_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_set_cover_tilt_position(self, **kwargs: Any) -> None:
        tilt = kwargs[ATTR_TILT_POSITION]
        updated = await self.coordinator.client.patch_sbus_device(
            self._device_id, {"command": "tilt", "tilt_percentage": tilt}
        )
        self.coordinator.sbus_devices[self._device_id].update(updated)
        self.async_write_ha_state()
