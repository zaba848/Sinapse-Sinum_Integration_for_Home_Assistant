"""Alarm control panel for Sinum Virtual Alarm System.

Supports:
  - Virtual alarm (software zones configured in Sinum app)
  - Satel alarm parent (physical Satel hardware integrated into Sinum)

REST endpoint: GET/PATCH /devices/alarm/{id}
States: disarmed | armed_home | armed_away | armed_night | triggered | pending
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SinumConfigEntry
from .api import SinumConnectionError
from .const import DOMAIN
from .coordinator import SinumCoordinator

_LOGGER = logging.getLogger(__name__)

# Sinum alarm state → HA AlarmControlPanelState
_STATE_MAP: dict[str, AlarmControlPanelState] = {
    "disarmed":    AlarmControlPanelState.DISARMED,
    "armed_home":  AlarmControlPanelState.ARMED_HOME,
    "armed_away":  AlarmControlPanelState.ARMED_AWAY,
    "armed_night": AlarmControlPanelState.ARMED_NIGHT,
    "triggered":   AlarmControlPanelState.TRIGGERED,
    "pending":     AlarmControlPanelState.PENDING,
    "arming":      AlarmControlPanelState.ARMING,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SinumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SinumCoordinator = entry.runtime_data
    entities: list[AlarmControlPanelEntity] = []

    try:
        alarm_devices = await coordinator.client.get_alarm_devices()
    except SinumConnectionError:
        _LOGGER.debug("Alarm system endpoint not available on this hub")
        return

    for device in alarm_devices:
        entities.append(SinumAlarmPanel(coordinator, device, entry.entry_id))

    async_add_entities(entities)


class SinumAlarmPanel(AlarmControlPanelEntity):
    """Represents a Sinum alarm system zone/panel."""

    _attr_has_entity_name = True
    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_HOME
        | AlarmControlPanelEntityFeature.ARM_AWAY
        | AlarmControlPanelEntityFeature.ARM_NIGHT
        | AlarmControlPanelEntityFeature.TRIGGER
    )
    _attr_code_arm_required = False

    def __init__(
        self,
        coordinator: SinumCoordinator,
        device: dict[str, Any],
        entry_id: str,
    ) -> None:
        self._coordinator = coordinator
        self._device_id: int = device["id"]
        self._data = device
        name: str = device.get("name", f"Alarm {self._device_id}")
        self._attr_name = name
        self._attr_unique_id = f"{entry_id}_alarm_{self._device_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_alarm_{self._device_id}")},
            name=name,
            manufacturer="TECH Sterowniki",
            model=f"Sinum {device.get('type', 'Alarm System').replace('_', ' ').title()}",
        )

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        raw = self._data.get("state", "disarmed")
        return _STATE_MAP.get(str(raw), AlarmControlPanelState.DISARMED)

    async def _patch(self, payload: dict[str, Any]) -> None:
        updated = await self._coordinator.client.patch_alarm_device(self._device_id, payload)
        self._data.update(updated)
        self.async_write_ha_state()

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        await self._patch({"state": "disarmed", "code": code})

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        await self._patch({"state": "armed_home", "code": code})

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        await self._patch({"state": "armed_away", "code": code})

    async def async_alarm_arm_night(self, code: str | None = None) -> None:
        await self._patch({"state": "armed_night", "code": code})

    async def async_alarm_trigger(self, code: str | None = None) -> None:
        await self._patch({"state": "triggered"})

    async def async_update(self) -> None:
        try:
            updated = await self._coordinator.client.get_alarm_device(self._device_id)
            self._data.update(updated)
        except SinumConnectionError as err:
            _LOGGER.warning("Alarm update failed for %s: %s", self._device_id, err)
