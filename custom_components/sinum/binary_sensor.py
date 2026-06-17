from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SinumConfigEntry
from .const import (
    DOMAIN,
    WTYPE_FAN_COIL,
    WTYPE_FLOOD_SENSOR,
    WTYPE_MOTION_SENSOR,
    WTYPE_OPENING_SENSOR,
    WTYPE_SMOKE_SENSOR,
    WTYPE_TWO_STATE_INPUT_SENSOR,
)
from .coordinator import SinumCoordinator


@dataclass(frozen=True, kw_only=True)
class SinumBinarySensorDescription(BinarySensorEntityDescription):
    wtp_type: str
    on_states: tuple[str, ...]
    source: str = "wtp"
    state_key: str = "state"


BINARY_SENSOR_TYPES: tuple[SinumBinarySensorDescription, ...] = (
    SinumBinarySensorDescription(
        key="flood",
        wtp_type=WTYPE_FLOOD_SENSOR,
        device_class=BinarySensorDeviceClass.MOISTURE,
        on_states=("wet", "flood", "alarm"),
    ),
    SinumBinarySensorDescription(
        key="motion",
        wtp_type=WTYPE_MOTION_SENSOR,
        device_class=BinarySensorDeviceClass.MOTION,
        on_states=("motion", "detected", "alarm"),
    ),
    SinumBinarySensorDescription(
        key="opening",
        wtp_type=WTYPE_OPENING_SENSOR,
        device_class=BinarySensorDeviceClass.OPENING,
        on_states=("open", "alarm"),
    ),
    SinumBinarySensorDescription(
        key="smoke",
        wtp_type=WTYPE_SMOKE_SENSOR,
        device_class=BinarySensorDeviceClass.SMOKE,
        on_states=("smoke", "alarm"),
    ),
    SinumBinarySensorDescription(
        key="two_state_input",
        wtp_type=WTYPE_TWO_STATE_INPUT_SENSOR,
        device_class=BinarySensorDeviceClass.OPENING,
        on_states=("true", "on", "open", "alarm"),
    ),
    SinumBinarySensorDescription(
        key="valve",
        wtp_type=WTYPE_FAN_COIL,
        device_class=BinarySensorDeviceClass.OPENING,
        state_key="valve_state",
        on_states=("true",),
    ),
)

_WTP_TYPE_TO_DESCRIPTION = {d.wtp_type: d for d in BINARY_SENSOR_TYPES}

SBUS_BINARY_SENSOR_TYPES: tuple[SinumBinarySensorDescription, ...] = (
    SinumBinarySensorDescription(
        key="two_state_input",
        wtp_type=WTYPE_TWO_STATE_INPUT_SENSOR,
        source="sbus",
        device_class=BinarySensorDeviceClass.OPENING,
        on_states=("true", "on", "open", "alarm"),
    ),
)

_SBUS_TYPE_TO_DESCRIPTION = {d.wtp_type: d for d in SBUS_BINARY_SENSOR_TYPES}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SinumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SinumCoordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = []

    for device_id, device in coordinator.wtp_devices.items():
        wtp_type = device.get("type", "")
        description = _WTP_TYPE_TO_DESCRIPTION.get(wtp_type)
        if description:
            entities.append(SinumBinarySensor(coordinator, device_id, description, entry.entry_id))

    for device_id, device in coordinator.sbus_devices.items():
        sbus_type = device.get("type", "")
        description = _SBUS_TYPE_TO_DESCRIPTION.get(sbus_type)
        if description:
            entities.append(SinumBinarySensor(coordinator, device_id, description, entry.entry_id))

    # Parent device connectivity sensors from REST /api/v1/parent-devices
    for parent in coordinator.parent_devices:
        entities.append(SinumParentOnlineSensor(coordinator, parent, entry.entry_id))
        if parent.get("has_messages") is not None:
            entities.append(SinumParentErrorSensor(coordinator, parent, entry.entry_id))

    async_add_entities(entities)


class SinumBinarySensor(CoordinatorEntity[SinumCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    entity_description: SinumBinarySensorDescription

    def __init__(
        self,
        coordinator: SinumCoordinator,
        device_id: int,
        description: SinumBinarySensorDescription,
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._source = description.source
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{self._source}_{device_id}_{description.key}"
        device = self._get_device_dict(coordinator)
        room = device.get("_room", "")
        name = device.get("_device_name", str(device_id))
        label = f"{room} {name}".strip() if room else name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{self._source}_{device_id}")},
            name=label,
            manufacturer="TECH Sterowniki",
            model=f"Sinum {self._source.upper()} {description.wtp_type.replace('_', ' ').title()}",
            suggested_area=device.get("_area") or None,
        )

    def _get_device_dict(self, coordinator: SinumCoordinator) -> dict[str, Any]:
        if self._source == "sbus":
            return coordinator.sbus_devices.get(self._device_id, {})
        return coordinator.wtp_devices.get(self._device_id, {})

    @property
    def _device(self) -> dict[str, Any]:
        return self._get_device_dict(self.coordinator)

    @property
    def is_on(self) -> bool | None:
        state_key = self.entity_description.state_key
        state = self._device.get(state_key)
        if state is None:
            state = self._device.get("status") if state_key == "state" else None
        if state is None:
            return None
        if isinstance(state, bool):
            return str(state).lower() in self.entity_description.on_states
        return str(state).lower() in self.entity_description.on_states

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self._device
        attrs: dict[str, Any] = {}
        # Fan coil gear states — show which relay gear is active
        for gear in ("gear_1", "gear_2", "gear_3"):
            if gear in d and isinstance(d[gear], dict):
                attrs[f"{gear}_active"] = bool(d[gear].get("state", False))
        if "hotel_mode" in d:
            attrs["hotel_mode"] = d["hotel_mode"]
        return attrs


class SinumParentOnlineSensor(CoordinatorEntity[SinumCoordinator], BinarySensorEntity):
    """Connectivity sensor for a Sinum parent device (WTP, SLINK, SBUS, etc.)."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "parent_online"

    def __init__(
        self,
        coordinator: SinumCoordinator,
        parent: dict[str, Any],
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._parent_id = parent.get("id")
        parent_class = parent.get("class", "device")
        unique_key = f"{entry_id}_parent_{parent_class}_{self._parent_id}"
        self._attr_unique_id = unique_key
        label = parent.get("name") or f"{parent_class} {self._parent_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, unique_key)},
            name=label,
            manufacturer="TECH Sterowniki",
            model=parent.get("model") or parent_class.replace("_", " ").title(),
            sw_version=parent.get("version"),
        )

    def _current(self) -> dict[str, Any]:
        for p in self.coordinator.parent_devices:
            if p.get("id") == self._parent_id:
                return p
        return {}

    @property
    def is_on(self) -> bool | None:
        p = self._current()
        status = p.get("status")
        if status is None:
            return None
        return str(status).lower() == "online"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        p = self._current()
        return {
            "software_status": p.get("software_status"),
            "has_messages": p.get("has_messages"),
            "firmware_version": p.get("version"),
            "type": p.get("type"),
            "class": p.get("class"),
        }


class SinumParentErrorSensor(CoordinatorEntity[SinumCoordinator], BinarySensorEntity):
    """Problem sensor for a Sinum parent device — on when it has pending messages."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "parent_problem"

    def __init__(
        self,
        coordinator: SinumCoordinator,
        parent: dict[str, Any],
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._parent_id = parent.get("id")
        parent_class = parent.get("class", "device")
        unique_key = f"{entry_id}_parent_{parent_class}_{self._parent_id}_problem"
        self._attr_unique_id = unique_key
        label = parent.get("name") or f"{parent_class} {self._parent_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_parent_{parent_class}_{self._parent_id}")},
            name=label,
            manufacturer="TECH Sterowniki",
            model=parent.get("model") or parent_class.replace("_", " ").title(),
            sw_version=parent.get("version"),
        )

    def _current(self) -> dict[str, Any]:
        for p in self.coordinator.parent_devices:
            if p.get("id") == self._parent_id:
                return p
        return {}

    @property
    def is_on(self) -> bool | None:
        p = self._current()
        val = p.get("has_messages")
        if val is None:
            return None
        return bool(val)
