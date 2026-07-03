"""Alarm control panel for Sinum alarm zones.

API: GET /api/v1/devices/alarm-system  — list of alarm_zone devices
     GET /api/v1/devices/alarm-system/{id}  — single zone
     POST /api/v1/devices/alarm-system/{id}/command/arm     — arm with PIN
     POST /api/v1/devices/alarm-system/{id}/command/disarm  — disarm with PIN

State fields:
  zone_status : "armed" | "disarmed"
  violated    : bool  — zone sensor currently tripped

HA state mapping:
  violated=True        → TRIGGERED
  zone_status="armed"  → ARMED_AWAY
  default              → DISARMED
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
    CodeFormat,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SinumConfigEntry
from .api import SinumConnectionError, SinumNotSupportedError
from .const import DOMAIN, MANUFACTURER
from .coordinator import SinumCoordinator, SinumDeviceAvailableMixin

PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


def _format_alarm_inputs(inputs: list) -> list[str]:
    return [f"{i['class']}/{i['id']}" for i in inputs]


def _alarm_zone_dict(devices: list[dict]) -> dict[int, dict]:
    return {int(d["id"]): d for d in devices if "id" in d}


async def _fetch_alarm_devices(coordinator: SinumCoordinator) -> list[dict]:
    try:
        devices = await coordinator.client.get_alarm_devices()
        coordinator.alarm_zones = _alarm_zone_dict(devices)
        return devices
    except (SinumConnectionError, SinumNotSupportedError):
        _LOGGER.debug("Alarm system endpoint not available on this hub")
        return []


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SinumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SinumCoordinator = entry.runtime_data
    cached = getattr(coordinator, "alarm_zones", {})
    if isinstance(cached, dict) and cached:
        alarm_devices = list(cached.values())
    else:
        alarm_devices = await _fetch_alarm_devices(coordinator)
    entities = [SinumAlarmZone(coordinator, d, entry.entry_id) for d in alarm_devices]
    async_add_entities(entities)


class SinumAlarmZone(
    SinumDeviceAvailableMixin, CoordinatorEntity[SinumCoordinator], AlarmControlPanelEntity
):
    """Alarm zone from the Sinum alarm system."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_AWAY
        | AlarmControlPanelEntityFeature.ARM_HOME
        | AlarmControlPanelEntityFeature.ARM_NIGHT
    )
    _attr_code_arm_required = True
    _attr_code_format = CodeFormat.NUMBER
    _attr_icon = "mdi:shield-home"

    def __init__(
        self,
        coordinator: SinumCoordinator,
        device: dict[str, Any],
        entry_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._zone_id: int = int(device["id"])
        name: str = device.get("name", f"Alarm zone {self._zone_id}")
        self._attr_unique_id = f"{entry_id}_alarm_{self._zone_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_alarm_{self._zone_id}")},
            name=name,
            manufacturer=MANUFACTURER,
            model="Sinum Alarm Zone",
            suggested_area=device.get("_area") or None,
        )

    @property
    def _device(self) -> dict[str, Any]:
        return self.coordinator.alarm_zones.get(self._zone_id, {})

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        d = self._device
        if d.get("violated"):
            return AlarmControlPanelState.TRIGGERED
        if d.get("zone_status") == "armed":
            return AlarmControlPanelState.ARMED_AWAY
        return AlarmControlPanelState.DISARMED

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self._device
        attrs: dict[str, Any] = {}
        self._add_delay_attributes(attrs, d)
        self._add_armed_mode_attribute(attrs, d)
        self._add_input_attributes(attrs, d)
        self._add_bypassed_attributes(attrs, d)
        return attrs

    def _add_delay_attributes(self, attrs: dict[str, Any], device: dict[str, Any]) -> None:
        if (v := device.get("enter_time_delay")) is not None:
            attrs["entry_delay_s"] = v
        if (v := device.get("exit_time_delay")) is not None:
            attrs["exit_delay_s"] = v

    def _add_armed_mode_attribute(self, attrs: dict[str, Any], device: dict[str, Any]) -> None:
        if (v := device.get("armed_mode")) is not None:
            attrs["armed_mode"] = v

    def _add_input_attributes(self, attrs: dict[str, Any], device: dict[str, Any]) -> None:
        inputs = device.get("associations", {}).get("inputs", [])
        if inputs:
            attrs["inputs"] = _format_alarm_inputs(inputs)

    def _add_bypassed_attributes(self, attrs: dict[str, Any], device: dict[str, Any]) -> None:
        bypass_zones = device.get("bypassed_inputs", [])
        if bypass_zones:
            attrs["bypassed_zones"] = _format_alarm_inputs(bypass_zones)

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        if not code:
            raise HomeAssistantError("PIN code is required to arm the alarm")
        try:
            await self.coordinator.client.command_alarm_device(
                self._zone_id, "arm", {"arm": str(code), "mode": "away"}
            )
        except SinumConnectionError as err:
            raise HomeAssistantError(f"Cannot arm alarm: {err}") from err
        await self.coordinator.async_request_refresh()

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        if not code:
            raise HomeAssistantError("PIN code is required to arm the alarm")
        try:
            await self.coordinator.client.command_alarm_device(
                self._zone_id, "arm", {"arm": str(code), "mode": "home"}
            )
        except SinumConnectionError as err:
            raise HomeAssistantError(f"Cannot arm alarm in home mode: {err}") from err
        await self.coordinator.async_request_refresh()

    async def async_alarm_arm_night(self, code: str | None = None) -> None:
        if not code:
            raise HomeAssistantError("PIN code is required to arm the alarm")
        try:
            await self.coordinator.client.command_alarm_device(
                self._zone_id, "arm", {"arm": str(code), "mode": "night"}
            )
        except SinumConnectionError as err:
            raise HomeAssistantError(f"Cannot arm alarm in night mode: {err}") from err
        await self.coordinator.async_request_refresh()

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        if not code:
            raise HomeAssistantError("PIN code is required to disarm the alarm")
        try:
            await self.coordinator.client.command_alarm_device(
                self._zone_id, "disarm", {"disarm": str(code)}
            )
        except SinumConnectionError as err:
            raise HomeAssistantError(f"Cannot disarm alarm: {err}") from err
        await self.coordinator.async_request_refresh()

    async def async_bypass_zone(self, code: str | None = None) -> None:
        """Bypass a single zone (disable its sensors from triggering alarm)."""
        if not code:
            raise HomeAssistantError("PIN code is required to bypass zone")
        try:
            await self.coordinator.client.patch_alarm_device(
                self._zone_id, {"bypassed": True, "pin": str(code)}
            )
        except SinumConnectionError as err:
            raise HomeAssistantError(f"Cannot bypass zone: {err}") from err
        await self.coordinator.async_request_refresh()

    async def async_unbypass_zone(self, code: str | None = None) -> None:
        """Unbypass a zone (re-enable its sensors)."""
        if not code:
            raise HomeAssistantError("PIN code is required to unbypass zone")
        try:
            await self.coordinator.client.patch_alarm_device(
                self._zone_id, {"bypassed": False, "pin": str(code)}
            )
        except SinumConnectionError as err:
            raise HomeAssistantError(f"Cannot unbypass zone: {err}") from err
        await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
