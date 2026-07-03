from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SinumConfigEntry
from .const import (
    DOMAIN,
    MANUFACTURER,
    LTYPE_RELAY,
    STYPE_COMMON_VALVE,
    STYPE_RELAY,
    VTYPE_HEAT_PUMP_MANAGER,
    VTYPE_RELAY,
    VTYPE_WICKET,
    WTYPE_RELAY,
)
from .coordinator import SinumCoordinator, SinumDeviceAvailableMixin, via_device_for

PARALLEL_UPDATES = 0


def _virtual_switch_entity(
    coordinator: SinumCoordinator, device_id: int, entry_id: str, device: dict[str, Any]
) -> SwitchEntity | None:
    dev_type = device.get("type")
    if not isinstance(dev_type, str):
        return None
    if dev_type == VTYPE_HEAT_PUMP_MANAGER:
        return _heat_pump_dhw_switch(coordinator, device_id, entry_id, device)
    factories = {
        VTYPE_RELAY: SinumRelaySwitch,
        VTYPE_WICKET: SinumWicketSwitch,
    }
    factory = factories.get(dev_type)
    if factory is None:
        return None
    return factory(coordinator, device_id, entry_id)


def _heat_pump_dhw_switch(
    coordinator: SinumCoordinator, device_id: int, entry_id: str, device: dict[str, Any]
) -> SwitchEntity | None:
    dhw = device.get("dhw_control")
    if not (isinstance(dhw, dict) and "enabled" in dhw):
        return None
    return SinumDhwSwitch(coordinator, device_id, entry_id)


def _wtp_switch_entity(
    coordinator: SinumCoordinator, device_id: int, entry_id: str, device: dict[str, Any]
) -> SwitchEntity | None:
    if device.get("type") != WTYPE_RELAY:
        return None
    return SinumBusRelaySwitch(coordinator, device_id, entry_id, "wtp")


def _sbus_switch_entity(
    coordinator: SinumCoordinator, device_id: int, entry_id: str, device: dict[str, Any]
) -> SwitchEntity | None:
    dev_type = device.get("type")
    if dev_type == STYPE_COMMON_VALVE:
        return SinumCommonValveSwitch(coordinator, device_id, entry_id)
    if dev_type != STYPE_RELAY:
        return None
    if "managed_by_thermostat" in device.get("labels", []):
        return None
    return SinumBusRelaySwitch(coordinator, device_id, entry_id, "sbus")


def _lora_switch_entity(
    coordinator: SinumCoordinator, device_id: int, entry_id: str, device: dict[str, Any]
) -> SwitchEntity | None:
    if device.get("type") != LTYPE_RELAY:
        return None
    return SinumBusRelaySwitch(coordinator, device_id, entry_id, "lora")


def _slink_switch_entity(
    coordinator: SinumCoordinator, device_id: int, entry_id: str, device: dict[str, Any]
) -> SwitchEntity | None:
    if device.get("type") != STYPE_RELAY:
        return None
    return SinumBusRelaySwitch(coordinator, device_id, entry_id, "slink")


def _bus_switch_entity(
    coordinator: SinumCoordinator,
    device_id: int,
    entry_id: str,
    bus: str,
    device: dict[str, Any],
) -> SwitchEntity | None:
    handlers = {
        "wtp": _wtp_switch_entity,
        "sbus": _sbus_switch_entity,
        "lora": _lora_switch_entity,
        "slink": _slink_switch_entity,
    }
    handler = handlers.get(bus)
    if handler is None:
        return None
    return handler(coordinator, device_id, entry_id, device)


def _add_bus_entities_for_store(
    coordinator: SinumCoordinator,
    entities: list[SwitchEntity],
    entry_id: str,
    bus: str,
    store: dict[int, dict[str, Any]],
) -> None:
    for device_id, device in store.items():
        entity = _bus_switch_entity(coordinator, device_id, entry_id, bus, device)
        if entity is not None:
            entities.append(entity)


def _add_virtual_switches(
    coordinator: SinumCoordinator, entities: list[SwitchEntity], entry_id: str
) -> None:
    for device_id, device in coordinator.virtual_devices.items():
        entity = _virtual_switch_entity(coordinator, device_id, entry_id, device)
        if entity is not None:
            entities.append(entity)


def _add_bus_switches(
    coordinator: SinumCoordinator, entities: list[SwitchEntity], entry_id: str
) -> None:
    _add_bus_entities_for_store(coordinator, entities, entry_id, "wtp", coordinator.wtp_devices)
    _add_bus_entities_for_store(coordinator, entities, entry_id, "sbus", coordinator.sbus_devices)
    _add_bus_entities_for_store(coordinator, entities, entry_id, "lora", coordinator.lora_devices)
    _add_bus_entities_for_store(coordinator, entities, entry_id, "slink", coordinator.slink_devices)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SinumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SinumCoordinator = entry.runtime_data
    entities: list[SwitchEntity] = []
    _add_virtual_switches(coordinator, entities, entry.entry_id)
    _add_bus_switches(coordinator, entities, entry.entry_id)
    async_add_entities(entities)


def _device_info(
    coordinator: SinumCoordinator, device_id: int, entry_id: str, model: str
) -> DeviceInfo:
    device = coordinator.virtual_devices.get(device_id, {})
    name = device.get("_device_name") or device.get("name", str(device_id))
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_virtual_{device_id}")},
        name=name,
        manufacturer=MANUFACTURER,
        model=model,
        suggested_area=device.get("_area") or None,
    )


class _SinumVirtualSwitch(
    SinumDeviceAvailableMixin, CoordinatorEntity[SinumCoordinator], SwitchEntity
):
    """Base for switch entities backed by a virtual device."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(
        self,
        coordinator: SinumCoordinator,
        device_id: int,
        entry_id: str,
        model_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry_id}_virtual_{device_id}"
        self._attr_device_info = _device_info(coordinator, device_id, entry_id, model_name)

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.virtual_devices.get(self._device_id, {})

    async def _patch(self, payload: dict[str, Any]) -> None:
        updated = await self.coordinator.client.patch_virtual_device(
            self._device_id, payload
        )
        self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()


class SinumRelaySwitch(_SinumVirtualSwitch):
    _attr_icon = "mdi:electric-switch"

    def __init__(self, coordinator: SinumCoordinator, device_id: int, entry_id: str) -> None:
        super().__init__(coordinator, device_id, entry_id, "Sinum Relay Integrator")

    @property
    def is_on(self) -> bool:
        return bool(self._device.get("state"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        try:
            await self._patch({"state": True})
        except Exception as err:
            raise HomeAssistantError(f"Cannot turn on: {err}") from err

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            await self._patch({"state": False})
        except Exception as err:
            raise HomeAssistantError(f"Cannot turn off: {err}") from err


class SinumWicketSwitch(_SinumVirtualSwitch):
    """Wicket (electric strike) — on = unlock, off = lock."""

    _attr_icon = "mdi:door-sliding"

    def __init__(self, coordinator: SinumCoordinator, device_id: int, entry_id: str) -> None:
        super().__init__(coordinator, device_id, entry_id, "Sinum Wicket")

    @property
    def is_on(self) -> bool:
        return self._device.get("state") in ("unlocked", "open")

    async def async_turn_on(self, **kwargs: Any) -> None:
        try:
            await self._patch({"command": "unlock"})
        except Exception as err:
            raise HomeAssistantError(f"Cannot unlock wicket: {err}") from err

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            await self._patch({"command": "lock"})
        except Exception as err:
            raise HomeAssistantError(f"Cannot lock wicket: {err}") from err


def _relay_device(coordinator: SinumCoordinator, bus: str, device_id: int) -> dict[str, Any]:
    store = {
        "wtp": coordinator.wtp_devices,
        "sbus": coordinator.sbus_devices,
        "slink": coordinator.slink_devices,
        "lora": coordinator.lora_devices,
    }.get(bus, coordinator.lora_devices)
    return store.get(device_id, {})


class SinumBusRelaySwitch(
    SinumDeviceAvailableMixin, CoordinatorEntity[SinumCoordinator], SwitchEntity
):
    """Physical relay on WTP or SBUS bus."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_icon = "mdi:toggle-switch"

    def __init__(
        self, coordinator: SinumCoordinator, device_id: int, entry_id: str, bus: str
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._bus = bus
        self._attr_unique_id = f"{entry_id}_{bus}_{device_id}"
        device = _relay_device(coordinator, bus, device_id)
        name = device.get("_device_name") or device.get("name", str(device_id))
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{bus}_{device_id}")},
            name=name,
            manufacturer=MANUFACTURER,
            model=device.get("_parent_model") or f"Sinum {bus.upper()} Relay",
            suggested_area=device.get("_area") or None,
            via_device=via_device_for(device, entry_id),
        )

    @property
    def _device(self) -> dict[str, Any]:
        return _relay_device(self.coordinator, self._bus, self._device_id)

    @property
    def is_on(self) -> bool:
        return bool(self._device.get("state"))

    async def _patch_state(self, state: bool) -> None:
        _BUS_STORES = {
            "wtp": (self.coordinator.wtp_devices, "patch_wtp_device"),
            "sbus": (self.coordinator.sbus_devices, "patch_sbus_device"),
            "slink": (self.coordinator.slink_devices, "patch_slink_device"),
            "lora": (self.coordinator.lora_devices, "patch_lora_device"),
        }
        store, method_name = _BUS_STORES.get(self._bus, _BUS_STORES["lora"])
        updated = await getattr(self.coordinator.client, method_name)(self._device_id, {"state": state})
        store[self._device_id].update(updated)

    async def async_turn_on(self, **kwargs: Any) -> None:
        try:
            await self._patch_state(True)
        except Exception as err:
            raise HomeAssistantError(f"Cannot turn on: {err}") from err
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            await self._patch_state(False)
        except Exception as err:
            raise HomeAssistantError(f"Cannot turn off: {err}") from err
        self.async_write_ha_state()


class SinumCommonValveSwitch(
    SinumDeviceAvailableMixin, CoordinatorEntity[SinumCoordinator], SwitchEntity
):
    """SBUS common_valve — enabled bool, complex calibration settings as attributes."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_icon = "mdi:valve"

    def __init__(self, coordinator: SinumCoordinator, device_id: int, entry_id: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry_id}_sbus_{device_id}"
        device = coordinator.sbus_devices.get(device_id, {})
        name = device.get("_device_name") or device.get("name", str(device_id))
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_sbus_{device_id}")},
            name=name,
            manufacturer=MANUFACTURER,
            model=device.get("_parent_model") or "Sinum SBUS Common Valve",
            suggested_area=device.get("_area") or None,
            via_device=via_device_for(device, entry_id),
        )

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.sbus_devices.get(self._device_id, {})

    @property
    def is_on(self) -> bool:
        return bool(self._device.get("enabled"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self._device
        attrs: dict[str, Any] = {}
        if "blockade" in d:
            attrs["blockade"] = d["blockade"]
        if "emergency_behaviour" in d:
            attrs["emergency_behaviour"] = d["emergency_behaviour"]
        if "blockade_reasons" in d:
            attrs["blockade_reasons"] = d["blockade_reasons"]
        return attrs

    async def async_turn_on(self, **kwargs: Any) -> None:
        try:
            updated = await self.coordinator.client.patch_sbus_device(
                self._device_id, {"enabled": True}
            )
        except Exception as err:
            raise HomeAssistantError(f"Cannot open valve: {err}") from err
        self.coordinator.sbus_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            updated = await self.coordinator.client.patch_sbus_device(
                self._device_id, {"enabled": False}
            )
        except Exception as err:
            raise HomeAssistantError(f"Cannot close valve: {err}") from err
        self.coordinator.sbus_devices[self._device_id].update(updated)
        self.async_write_ha_state()


class SinumDhwSwitch(SinumDeviceAvailableMixin, CoordinatorEntity[SinumCoordinator], SwitchEntity):
    """DHW (domestic hot water) enable switch on heat_pump_manager virtual devices."""

    _attr_has_entity_name = True
    _attr_translation_key = "dhw_control"
    _attr_icon = "mdi:water-boiler"

    def __init__(self, coordinator: SinumCoordinator, device_id: int, entry_id: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry_id}_virtual_{device_id}_dhw"
        self._attr_device_info = _device_info(
            coordinator, device_id, entry_id, "Sinum Heat Pump Manager"
        )

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.virtual_devices.get(self._device_id, {})

    @property
    def is_on(self) -> bool:
        dhw = self._device.get("dhw_control")
        if not isinstance(dhw, dict):
            return False
        return bool(dhw.get("enabled"))

    @staticmethod
    def _copy_decoded_temperature(
        attrs: dict[str, Any],
        source: dict[str, Any],
        source_key: str,
        target_key: str,
        decode: Any,
    ) -> None:
        if source_key not in source:
            return
        attrs[target_key] = decode(source[source_key])

    @staticmethod
    def _copy_if_present(
        attrs: dict[str, Any], source: dict[str, Any], source_key: str, target_key: str
    ) -> None:
        if source_key not in source:
            return
        attrs[target_key] = source[source_key]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        dhw = self._device.get("dhw_control")
        if not isinstance(dhw, dict):
            return {}
        attrs: dict[str, Any] = {}
        decode = self.coordinator.client.decode_temperature
        self._copy_if_present(attrs, dhw, "state", "dhw_active")
        self._copy_decoded_temperature(attrs, dhw, "temperature", "dhw_temperature_c", decode)
        self._copy_decoded_temperature(
            attrs,
            dhw,
            "target_temperature",
            "dhw_target_c",
            decode,
        )
        if "hysteresis" in dhw:
            attrs["hysteresis"] = dhw["hysteresis"] / 10
        return attrs

    async def async_turn_on(self, **kwargs: Any) -> None:
        try:
            updated = await self.coordinator.client.patch_virtual_device(
                self._device_id, {"dhw_control": {"enabled": True}}
            )
        except Exception as err:
            raise HomeAssistantError(f"Cannot enable DHW: {err}") from err
        if updated:
            self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            updated = await self.coordinator.client.patch_virtual_device(
                self._device_id, {"dhw_control": {"enabled": False}}
            )
        except Exception as err:
            raise HomeAssistantError(f"Cannot disable DHW: {err}") from err
        if updated:
            self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()
