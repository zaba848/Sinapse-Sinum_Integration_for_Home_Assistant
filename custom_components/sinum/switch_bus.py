"""Bus relay and common-valve switch entities (WTP / SBUS / SLINK / LoRa)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ._bus_registry import bus_patch_method, bus_store
from .const import DOMAIN, MANUFACTURER
from .coordinator import SinumCoordinator, SinumDeviceAvailableMixin, via_device_for


def _relay_device(coordinator: SinumCoordinator, bus: str, device_id: int) -> dict[str, Any]:
    store = bus_store(coordinator, bus)
    if store is None:
        store = coordinator.lora_devices
    device = store.get(device_id, {})
    return device if isinstance(device, dict) else {}


class SinumBusRelaySwitch(
    SinumDeviceAvailableMixin, CoordinatorEntity[SinumCoordinator], SwitchEntity
):
    """Physical relay on WTP, SBUS, SLINK or LoRa bus."""

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
        store = bus_store(self.coordinator, self._bus)
        if store is None:
            store = self.coordinator.lora_devices
        patch_method = bus_patch_method(self.coordinator, self._bus)
        if patch_method is None:
            raise HomeAssistantError(f"Unsupported bus for relay patch: {self._bus}")
        updated = await patch_method(self._device_id, {"state": state})
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
        return {k: d[k] for k in ("blockade", "emergency_behaviour", "blockade_reasons") if k in d}

    async def _patch_sbus(self, payload: dict[str, Any], err_msg: str) -> None:
        try:
            updated = await self.coordinator.client.patch_sbus_device(self._device_id, payload)
        except Exception as err:
            raise HomeAssistantError(f"{err_msg}: {err}") from err
        self.coordinator.sbus_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._patch_sbus({"enabled": True}, "Cannot open valve")

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._patch_sbus({"enabled": False}, "Cannot close valve")
