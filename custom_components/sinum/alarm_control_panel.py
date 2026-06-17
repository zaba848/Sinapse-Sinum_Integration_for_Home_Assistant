"""Alarm control panel for Sinum alarm zones.

API: GET /api/v1/devices/alarm-system  — list of alarm_zone devices
     GET /api/v1/devices/alarm-system/{id}  — single zone

State fields (read-only in API):
  zone_status : "armed" | "disarmed"
  violated    : bool  — zone sensor currently tripped

HA state mapping:
  violated=True        → TRIGGERED
  zone_status="armed"  → ARMED_AWAY
  default              → DISARMED

NOTE: The REST API does not expose arm/disarm commands (zone_status and
armed are read-only). The panel is therefore display-only with no
supported features. State is refreshed via the shared coordinator.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelState,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SinumConfigEntry
from .api import SinumConnectionError
from .const import DOMAIN
from .coordinator import SinumCoordinator

_LOGGER = logging.getLogger(__name__)


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
        entities.append(SinumAlarmZone(coordinator, device, entry.entry_id))

    async_add_entities(entities)


class SinumAlarmZone(CoordinatorEntity[SinumCoordinator], AlarmControlPanelEntity):
    """Alarm zone from the Sinum alarm system (read-only state monitor)."""

    _attr_has_entity_name = True
    _attr_name = None
    # REST API does not support arm/disarm — display-only panel
    _attr_supported_features = 0
    _attr_code_arm_required = False
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
            manufacturer="TECH Sterowniki",
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
        if (v := d.get("enter_time_delay")) is not None:
            attrs["entry_delay_s"] = v
        if (v := d.get("exit_time_delay")) is not None:
            attrs["exit_delay_s"] = v
        inputs = d.get("associations", {}).get("inputs", [])
        if inputs:
            attrs["inputs"] = [f"{i['class']}/{i['id']}" for i in inputs]
        return attrs

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
