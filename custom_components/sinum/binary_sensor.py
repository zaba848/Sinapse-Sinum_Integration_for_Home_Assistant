from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

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
    LTYPE_FLOOD_SENSOR,
    LTYPE_OPENING_SENSOR,
    LTYPE_SMOKE_SENSOR,
    LTYPE_TWO_STATE_INPUT_SENSOR,
    MANUFACTURER,
    STYPE_MOTION_SENSOR,
    STYPE_VALVE_PUMP,
    WTYPE_FAN_COIL,
    WTYPE_FLOOD_SENSOR,
    WTYPE_MOTION_SENSOR,
    WTYPE_OPENING_SENSOR,
    WTYPE_SMOKE_SENSOR,
    WTYPE_TEMPERATURE_REGULATOR,
    WTYPE_TWO_STATE_INPUT_SENSOR,
)
from .coordinator import (
    SinumCoordinator,
    SinumDeviceAvailableMixin,
    hub_prefixed_name,
    via_device_for,
)

PARALLEL_UPDATES = 0


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
        state_key="flood_detected",
        on_states=("true", "wet", "flood", "alarm"),
    ),
    SinumBinarySensorDescription(
        key="motion",
        wtp_type=WTYPE_MOTION_SENSOR,
        device_class=BinarySensorDeviceClass.MOTION,
        state_key="motion_detected",
        on_states=("true", "motion", "detected", "alarm"),
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
    SinumBinarySensorDescription(
        key="motion",
        wtp_type=STYPE_MOTION_SENSOR,
        source="sbus",
        device_class=BinarySensorDeviceClass.MOTION,
        state_key="motion_detected",
        on_states=("true", "motion", "detected", "alarm"),
    ),
    # valve_pump state is hub-managed (read-only) — expose as running binary sensor
    SinumBinarySensorDescription(
        key="pump",
        wtp_type=STYPE_VALVE_PUMP,
        source="sbus",
        device_class=BinarySensorDeviceClass.RUNNING,
        state_key="state",
        on_states=("true",),
    ),
)

_SBUS_TYPE_TO_DESCRIPTION = {d.wtp_type: d for d in SBUS_BINARY_SENSOR_TYPES}

LORA_BINARY_SENSOR_TYPES: tuple[SinumBinarySensorDescription, ...] = (
    SinumBinarySensorDescription(
        key="opening",
        wtp_type=LTYPE_OPENING_SENSOR,
        source="lora",
        device_class=BinarySensorDeviceClass.OPENING,
        on_states=("open", "true", "alarm"),
    ),
    SinumBinarySensorDescription(
        key="flood",
        wtp_type=LTYPE_FLOOD_SENSOR,
        source="lora",
        device_class=BinarySensorDeviceClass.MOISTURE,
        state_key="flood_detected",
        on_states=("true", "wet", "flood", "alarm"),
    ),
    SinumBinarySensorDescription(
        key="smoke",
        wtp_type=LTYPE_SMOKE_SENSOR,
        source="lora",
        device_class=BinarySensorDeviceClass.SMOKE,
        on_states=("smoke", "alarm"),
    ),
    SinumBinarySensorDescription(
        key="two_state_input",
        wtp_type=LTYPE_TWO_STATE_INPUT_SENSOR,
        source="lora",
        device_class=BinarySensorDeviceClass.OPENING,
        on_states=("true", "on", "open", "alarm"),
    ),
)

_LORA_TYPE_TO_DESCRIPTION = {d.wtp_type: d for d in LORA_BINARY_SENSOR_TYPES}

_TARGET_REACHED_WTP = SinumBinarySensorDescription(
    key="target_reached",
    wtp_type=WTYPE_TEMPERATURE_REGULATOR,
    source="wtp",
    device_class=None,
    state_key="target_temperature_reached",
    on_states=("true",),
    translation_key="target_reached",
)
_TARGET_REACHED_SBUS = SinumBinarySensorDescription(
    key="target_reached",
    wtp_type=WTYPE_TEMPERATURE_REGULATOR,
    source="sbus",
    device_class=None,
    state_key="target_temperature_reached",
    on_states=("true",),
    translation_key="target_reached",
)


def _fan_coil_gear_active(d: dict[str, Any], gear: str) -> bool | None:
    if gear in d and isinstance(d[gear], dict):
        return bool(d[gear].get("state", False))
    return None


def _needs_target_reached(
    desc: SinumBinarySensorDescription | None, dev_type: str, device: dict
) -> bool:
    return bool(
        desc and dev_type == WTYPE_TEMPERATURE_REGULATOR and "target_temperature_reached" in device
    )


def _add_sensors_for_bus(
    store: dict[int, dict],
    type_map: dict[str, SinumBinarySensorDescription],
    target_reached_desc: SinumBinarySensorDescription | None,
    coordinator: SinumCoordinator,
    entities: list[BinarySensorEntity],
    entry_id: str,
) -> None:
    for device_id, device in store.items():
        dev_type = device.get("type", "")
        if description := type_map.get(dev_type):
            entities.append(SinumBinarySensor(coordinator, device_id, description, entry_id))
        if _needs_target_reached(target_reached_desc, dev_type, device):
            entities.append(
                SinumBinarySensor(
                    coordinator,
                    device_id,
                    cast(SinumBinarySensorDescription, target_reached_desc),
                    entry_id,
                )
            )


def _add_bus_binary_sensors(
    coordinator: SinumCoordinator,
    entities: list[BinarySensorEntity],
    entry_id: str,
) -> None:
    _add_sensors_for_bus(
        coordinator.wtp_devices,
        _WTP_TYPE_TO_DESCRIPTION,
        _TARGET_REACHED_WTP,
        coordinator,
        entities,
        entry_id,
    )
    _add_sensors_for_bus(
        coordinator.sbus_devices,
        _SBUS_TYPE_TO_DESCRIPTION,
        _TARGET_REACHED_SBUS,
        coordinator,
        entities,
        entry_id,
    )
    _add_sensors_for_bus(
        coordinator.lora_devices,
        _LORA_TYPE_TO_DESCRIPTION,
        None,
        coordinator,
        entities,
        entry_id,
    )


def _add_parent_binary_sensors(
    coordinator: SinumCoordinator,
    entities: list[BinarySensorEntity],
    entry_id: str,
) -> None:
    for parent in coordinator.parent_devices:
        entities.append(SinumParentOnlineSensor(coordinator, parent, entry_id))
        if parent.get("has_messages") is not None:
            entities.append(SinumParentErrorSensor(coordinator, parent, entry_id))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SinumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SinumCoordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = []
    _add_bus_binary_sensors(coordinator, entities, entry.entry_id)
    _add_parent_binary_sensors(coordinator, entities, entry.entry_id)
    async_add_entities(entities)


class SinumBinarySensor(
    SinumDeviceAvailableMixin, CoordinatorEntity[SinumCoordinator], BinarySensorEntity
):
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
        label = device.get("_device_name") or device.get("name", str(device_id))
        via = via_device_for(device, entry_id)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{self._source}_{device_id}")},
            name=label,
            manufacturer=MANUFACTURER,
            model=device.get("_parent_model")
            or f"Sinum {self._source.upper()} {description.wtp_type.replace('_', ' ').title()}",
            sw_version=device.get("software_version"),
            serial_number=device.get("eui"),
            suggested_area=device.get("_area") or None,
            via_device=via,
        )

    def _get_device_dict(self, coordinator: SinumCoordinator) -> dict[str, Any]:
        store = {
            "sbus": coordinator.sbus_devices,
            "lora": coordinator.lora_devices,
        }.get(self._source, coordinator.wtp_devices)
        return store.get(self._device_id, {})

    @property
    def _device(self) -> dict[str, Any]:
        return self._get_device_dict(self.coordinator)

    @property
    def is_on(self) -> bool | None:
        state_key = self.entity_description.state_key
        state = self._device.get(state_key)
        if state is None and state_key == "state":
            state = self._device.get("status")
        if state is None:
            return None
        return str(state).lower() in self.entity_description.on_states

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self._device
        attrs: dict[str, Any] = {}
        for gear in ("gear_1", "gear_2", "gear_3"):
            value = _fan_coil_gear_active(d, gear)
            if value is not None:
                attrs[f"{gear}_active"] = value
        if "hotel_mode" in d:
            attrs["hotel_mode"] = d["hotel_mode"]
        return attrs


class SinumParentOnlineSensor(CoordinatorEntity[SinumCoordinator], BinarySensorEntity):
    """Connectivity sensor for a Sinum parent device (WTP, SLINK, SBUS, etc.)."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "parent_online"
    _attr_icon = "mdi:router-network"

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
            name=hub_prefixed_name(coordinator, label),
            manufacturer=MANUFACTURER,
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
    _attr_icon = "mdi:alert-circle"

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
            name=hub_prefixed_name(coordinator, label),
            manufacturer=MANUFACTURER,
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
