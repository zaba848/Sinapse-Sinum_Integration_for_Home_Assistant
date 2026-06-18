from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SinumConfigEntry
from .const import (
    DOMAIN,
    LTYPE_RELAY,
    STYPE_COMMON_VALVE,
    STYPE_RELAY,
    STYPE_VALVE_PUMP,
    VTYPE_HEAT_PUMP_MANAGER,
    VTYPE_RELAY,
    VTYPE_WICKET,
    WTYPE_RELAY,
)
from .coordinator import SinumCoordinator, via_device_for


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SinumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SinumCoordinator = entry.runtime_data
    entities: list[SwitchEntity] = []

    for device_id, device in coordinator.virtual_devices.items():
        dev_type = device.get("type")
        if dev_type == VTYPE_RELAY:
            entities.append(SinumRelaySwitch(coordinator, device_id, entry.entry_id))
        elif dev_type == VTYPE_WICKET:
            entities.append(SinumWicketSwitch(coordinator, device_id, entry.entry_id))
        elif dev_type == VTYPE_HEAT_PUMP_MANAGER:
            dhw = device.get("dhw_control")
            if isinstance(dhw, dict) and "enabled" in dhw:
                entities.append(SinumDhwSwitch(coordinator, device_id, entry.entry_id))

    for device_id, device in coordinator.wtp_devices.items():
        if device.get("type") == WTYPE_RELAY:
            entities.append(SinumBusRelaySwitch(coordinator, device_id, entry.entry_id, "wtp"))

    for device_id, device in coordinator.sbus_devices.items():
        dev_type = device.get("type")
        if dev_type == STYPE_RELAY:
            entities.append(SinumBusRelaySwitch(coordinator, device_id, entry.entry_id, "sbus"))
        elif dev_type == STYPE_VALVE_PUMP:
            entities.append(SinumValvePumpSwitch(coordinator, device_id, entry.entry_id))
        elif dev_type == STYPE_COMMON_VALVE:
            entities.append(SinumCommonValveSwitch(coordinator, device_id, entry.entry_id))

    for device_id, device in coordinator.lora_devices.items():
        if device.get("type") == LTYPE_RELAY:
            entities.append(SinumBusRelaySwitch(coordinator, device_id, entry.entry_id, "lora"))

    async_add_entities(entities)


def _device_info(
    coordinator: SinumCoordinator, device_id: int, entry_id: str, model: str
) -> DeviceInfo:
    device = coordinator.virtual_devices.get(device_id, {})
    name = device.get("_device_name") or device.get("name", str(device_id))
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_virtual_{device_id}")},
        name=name,
        manufacturer="TECH Sterowniki",
        model=model,
        suggested_area=device.get("_area") or None,
    )


class SinumRelaySwitch(CoordinatorEntity[SinumCoordinator], SwitchEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_icon = "mdi:electric-switch"

    def __init__(self, coordinator: SinumCoordinator, device_id: int, entry_id: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry_id}_virtual_{device_id}"
        self._attr_device_info = _device_info(
            coordinator, device_id, entry_id, "Sinum Relay Integrator"
        )

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.virtual_devices.get(self._device_id, {})

    @property
    def is_on(self) -> bool:
        return bool(self._device.get("state"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        updated = await self.coordinator.client.patch_virtual_device(
            self._device_id, {"state": True}
        )
        self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        updated = await self.coordinator.client.patch_virtual_device(
            self._device_id, {"state": False}
        )
        self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()


class SinumWicketSwitch(CoordinatorEntity[SinumCoordinator], SwitchEntity):
    """Wicket (electric strike) — on = unlock, off = lock."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_icon = "mdi:door-sliding"

    def __init__(self, coordinator: SinumCoordinator, device_id: int, entry_id: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry_id}_virtual_{device_id}"
        self._attr_device_info = _device_info(coordinator, device_id, entry_id, "Sinum Wicket")

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.virtual_devices.get(self._device_id, {})

    @property
    def is_on(self) -> bool:
        return self._device.get("state") in ("unlocked", "open")

    async def async_turn_on(self, **kwargs: Any) -> None:
        updated = await self.coordinator.client.patch_virtual_device(
            self._device_id, {"command": "unlock"}
        )
        self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        updated = await self.coordinator.client.patch_virtual_device(
            self._device_id, {"command": "lock"}
        )
        self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()


class SinumBusRelaySwitch(CoordinatorEntity[SinumCoordinator], SwitchEntity):
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
        if bus == "wtp":
            device = coordinator.wtp_devices.get(device_id, {})
        elif bus == "sbus":
            device = coordinator.sbus_devices.get(device_id, {})
        else:
            device = coordinator.lora_devices.get(device_id, {})
        name = device.get("_device_name") or device.get("name", str(device_id))
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{bus}_{device_id}")},
            name=name,
            manufacturer="TECH Sterowniki",
            model=device.get("_parent_model") or f"Sinum {bus.upper()} Relay",
            suggested_area=device.get("_area") or None,
            via_device=via_device_for(device, entry_id),
        )

    @property
    def _device(self) -> dict[str, Any]:
        if self._bus == "wtp":
            return self.coordinator.wtp_devices.get(self._device_id, {})
        if self._bus == "sbus":
            return self.coordinator.sbus_devices.get(self._device_id, {})
        return self.coordinator.lora_devices.get(self._device_id, {})

    @property
    def is_on(self) -> bool:
        return bool(self._device.get("state"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        if self._bus == "wtp":
            updated = await self.coordinator.client.patch_wtp_device(
                self._device_id, {"state": True}
            )
            self.coordinator.wtp_devices[self._device_id].update(updated)
        elif self._bus == "sbus":
            updated = await self.coordinator.client.patch_sbus_device(
                self._device_id, {"state": True}
            )
            self.coordinator.sbus_devices[self._device_id].update(updated)
        else:
            updated = await self.coordinator.client.patch_lora_device(
                self._device_id, {"state": True}
            )
            self.coordinator.lora_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self._bus == "wtp":
            updated = await self.coordinator.client.patch_wtp_device(
                self._device_id, {"state": False}
            )
            self.coordinator.wtp_devices[self._device_id].update(updated)
        elif self._bus == "sbus":
            updated = await self.coordinator.client.patch_sbus_device(
                self._device_id, {"state": False}
            )
            self.coordinator.sbus_devices[self._device_id].update(updated)
        else:
            updated = await self.coordinator.client.patch_lora_device(
                self._device_id, {"state": False}
            )
            self.coordinator.lora_devices[self._device_id].update(updated)
        self.async_write_ha_state()


class SinumValvePumpSwitch(CoordinatorEntity[SinumCoordinator], SwitchEntity):
    """SBUS valve_pump — state bool, with blockade and temperature thresholds as attributes."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_icon = "mdi:pump"

    def __init__(self, coordinator: SinumCoordinator, device_id: int, entry_id: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry_id}_sbus_{device_id}"
        device = coordinator.sbus_devices.get(device_id, {})
        name = device.get("_device_name") or device.get("name", str(device_id))
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_sbus_{device_id}")},
            name=name,
            manufacturer="TECH Sterowniki",
            model=device.get("_parent_model") or "Sinum SBUS Valve Pump",
            suggested_area=device.get("_area") or None,
            via_device=via_device_for(device, entry_id),
        )

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.sbus_devices.get(self._device_id, {})

    @property
    def is_on(self) -> bool:
        return bool(self._device.get("state"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self._device
        attrs: dict[str, Any] = {}
        if "blockade" in d:
            attrs["blockade"] = d["blockade"]
        if "emergency_behaviour" in d:
            attrs["emergency_behaviour"] = d["emergency_behaviour"]
        if "temperature_threshold_heating" in d:
            th = d["temperature_threshold_heating"]
            attrs["threshold_heating_c"] = th / 10 if isinstance(th, (int, float)) else None
        if "temperature_threshold_cooling" in d:
            tc = d["temperature_threshold_cooling"]
            attrs["threshold_cooling_c"] = tc / 10 if isinstance(tc, (int, float)) else None
        return attrs

    async def async_turn_on(self, **kwargs: Any) -> None:
        updated = await self.coordinator.client.patch_sbus_device(self._device_id, {"state": True})
        self.coordinator.sbus_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        updated = await self.coordinator.client.patch_sbus_device(self._device_id, {"state": False})
        self.coordinator.sbus_devices[self._device_id].update(updated)
        self.async_write_ha_state()


class SinumCommonValveSwitch(CoordinatorEntity[SinumCoordinator], SwitchEntity):
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
            manufacturer="TECH Sterowniki",
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
        updated = await self.coordinator.client.patch_sbus_device(
            self._device_id, {"enabled": True}
        )
        self.coordinator.sbus_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        updated = await self.coordinator.client.patch_sbus_device(
            self._device_id, {"enabled": False}
        )
        self.coordinator.sbus_devices[self._device_id].update(updated)
        self.async_write_ha_state()


class SinumDhwSwitch(CoordinatorEntity[SinumCoordinator], SwitchEntity):
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

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        dhw = self._device.get("dhw_control")
        if not isinstance(dhw, dict):
            return {}
        attrs: dict[str, Any] = {}
        decode = self.coordinator.client.decode_temperature
        if "state" in dhw:
            attrs["dhw_active"] = dhw["state"]
        if "temperature" in dhw:
            attrs["dhw_temperature_c"] = decode(dhw["temperature"])
        if "target_temperature" in dhw:
            attrs["dhw_target_c"] = decode(dhw["target_temperature"])
        if "hysteresis" in dhw:
            attrs["hysteresis"] = dhw["hysteresis"] / 10
        return attrs

    async def async_turn_on(self, **kwargs: Any) -> None:
        updated = await self.coordinator.client.patch_virtual_device(
            self._device_id, {"dhw_control": {"enabled": True}}
        )
        if updated:
            self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        updated = await self.coordinator.client.patch_virtual_device(
            self._device_id, {"dhw_control": {"enabled": False}}
        )
        if updated:
            self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()
