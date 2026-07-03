"""Virtual-device switch entities (relay, wicket, DHW)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import SinumCoordinator, SinumDeviceAvailableMixin


def _dhw_plain_attrs(dhw: dict[str, Any]) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    if "state" in dhw:
        attrs["dhw_active"] = dhw["state"]
    if "hysteresis" in dhw:
        attrs["hysteresis"] = dhw["hysteresis"] / 10
    return attrs


def _dhw_temp_attrs(dhw: dict[str, Any], decode: Any) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    if "temperature" in dhw:
        attrs["dhw_temperature_c"] = decode(dhw["temperature"])
    if "target_temperature" in dhw:
        attrs["dhw_target_c"] = decode(dhw["target_temperature"])
    return attrs


def _dhw_attrs(dhw: dict[str, Any], decode: Any) -> dict[str, Any]:
    return {**_dhw_plain_attrs(dhw), **_dhw_temp_attrs(dhw, decode)}


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

    async def _patch(self, payload: dict[str, Any], err_msg: str) -> None:
        try:
            updated = await self.coordinator.client.patch_virtual_device(self._device_id, payload)
            self.coordinator.virtual_devices[self._device_id].update(updated)
            self.async_write_ha_state()
        except Exception as err:
            raise HomeAssistantError(f"{err_msg}: {err}") from err


class SinumRelaySwitch(_SinumVirtualSwitch):
    _attr_icon = "mdi:electric-switch"

    def __init__(self, coordinator: SinumCoordinator, device_id: int, entry_id: str) -> None:
        super().__init__(coordinator, device_id, entry_id, "Sinum Relay Integrator")

    @property
    def is_on(self) -> bool:
        return bool(self._device.get("state"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._patch({"state": True}, "Cannot turn on")

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._patch({"state": False}, "Cannot turn off")


class SinumWicketSwitch(_SinumVirtualSwitch):
    """Wicket (electric strike) — on = unlock, off = lock."""

    _attr_icon = "mdi:door-sliding"

    def __init__(self, coordinator: SinumCoordinator, device_id: int, entry_id: str) -> None:
        super().__init__(coordinator, device_id, entry_id, "Sinum Wicket")

    @property
    def is_on(self) -> bool:
        return self._device.get("state") in ("unlocked", "open")

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._patch({"command": "unlock"}, "Cannot unlock wicket")

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._patch({"command": "lock"}, "Cannot lock wicket")


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

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        dhw = self._device.get("dhw_control")
        if not isinstance(dhw, dict):
            return {}
        return _dhw_attrs(dhw, self.coordinator.client.decode_temperature)

    async def _patch_virtual(self, payload: dict[str, Any], err_msg: str) -> None:
        try:
            updated = await self.coordinator.client.patch_virtual_device(self._device_id, payload)
        except Exception as err:
            raise HomeAssistantError(f"{err_msg}: {err}") from err
        if updated:
            self.coordinator.virtual_devices[self._device_id].update(updated)
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._patch_virtual({"dhw_control": {"enabled": True}}, "Cannot enable DHW")

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._patch_virtual({"dhw_control": {"enabled": False}}, "Cannot disable DHW")
