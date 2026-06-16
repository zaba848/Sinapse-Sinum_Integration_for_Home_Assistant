from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SinumConfigEntry
from .const import DOMAIN, VTYPE_RELAY, VTYPE_WICKET
from .coordinator import SinumCoordinator


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

    async_add_entities(entities)


def _device_info(coordinator: SinumCoordinator, device_id: int, entry_id: str, model: str) -> DeviceInfo:
    device = coordinator.virtual_devices.get(device_id, {})
    room = device.get("_room", "")
    name = device.get("_device_name", str(device_id))
    label = f"{room} {name}".strip() if room else name
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_virtual_{device_id}")},
        name=label,
        manufacturer="TECH Sterowniki",
        model=model,
        suggested_area=device.get("_area") or None,
    )


class SinumRelaySwitch(CoordinatorEntity[SinumCoordinator], SwitchEntity):
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, coordinator: SinumCoordinator, device_id: int, entry_id: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry_id}_virtual_{device_id}"
        self._attr_device_info = _device_info(coordinator, device_id, entry_id, "Sinum Relay Integrator")

    @property
    def name(self) -> str:
        d = self.coordinator.virtual_devices.get(self._device_id, {})
        room = d.get("_room", "")
        name = d.get("_device_name", str(self._device_id))
        return f"{room} {name}".strip() if room else name

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.virtual_devices.get(self._device_id, {})

    @property
    def is_on(self) -> bool:
        return bool(self._device.get("state"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        updated = await self.coordinator.client.patch_virtual_device(self._device_id, {"state": True})
        self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        updated = await self.coordinator.client.patch_virtual_device(self._device_id, {"state": False})
        self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()


class SinumWicketSwitch(CoordinatorEntity[SinumCoordinator], SwitchEntity):
    """Wicket (electric strike) — on = unlock, off = lock."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, coordinator: SinumCoordinator, device_id: int, entry_id: str) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry_id}_virtual_{device_id}"
        self._attr_device_info = _device_info(coordinator, device_id, entry_id, "Sinum Wicket")

    @property
    def name(self) -> str:
        d = self.coordinator.virtual_devices.get(self._device_id, {})
        room = d.get("_room", "")
        name = d.get("_device_name", str(self._device_id))
        return f"{room} {name}".strip() if room else name

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.virtual_devices.get(self._device_id, {})

    @property
    def is_on(self) -> bool:
        return self._device.get("state") in ("unlocked", "open")

    async def async_turn_on(self, **kwargs: Any) -> None:
        updated = await self.coordinator.client.patch_virtual_device(self._device_id, {"command": "unlock"})
        self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        updated = await self.coordinator.client.patch_virtual_device(self._device_id, {"command": "lock"})
        self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()
