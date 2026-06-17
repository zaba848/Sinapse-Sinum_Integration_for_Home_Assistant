"""Diagnostics support for Sinum integration."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import SinumConfigEntry
from .const import CONF_API_TOKEN, CONF_PASSWORD


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: SinumConfigEntry,
) -> dict[str, Any]:
    coordinator = entry.runtime_data

    entry_data = {**entry.data}
    for secret_key in (CONF_API_TOKEN, CONF_PASSWORD):
        if secret_key in entry_data:
            entry_data[secret_key] = "**REDACTED**"

    virtual_snapshot = {
        str(dev_id): _sanitize_device(dev) for dev_id, dev in coordinator.virtual_devices.items()
    }
    wtp_snapshot = {
        str(dev_id): _sanitize_device(dev) for dev_id, dev in coordinator.wtp_devices.items()
    }
    sbus_snapshot = {
        str(dev_id): _sanitize_device(dev) for dev_id, dev in coordinator.sbus_devices.items()
    }

    return {
        "entry": entry_data,
        "hub_info": _sanitize_device(coordinator.hub_info),
        "virtual_devices": virtual_snapshot,
        "wtp_devices": wtp_snapshot,
        "sbus_devices": sbus_snapshot,
        "parent_devices": [_sanitize_device(dev) for dev in coordinator.parent_devices],
        "floors": {str(fid): _sanitize_device(floor) for fid, floor in coordinator.floors.items()},
        "rooms_count": len(coordinator.rooms),
        "virtual_count": len(coordinator.virtual_devices),
        "wtp_count": len(coordinator.wtp_devices),
        "sbus_count": len(coordinator.sbus_devices),
        "parent_count": len(coordinator.parent_devices),
        "mqtt_enabled": coordinator.mqtt_bridge is not None,
    }


def _sanitize_device(device: dict[str, Any]) -> dict[str, Any]:
    """Remove any internal helper keys added by the coordinator."""
    return {k: v for k, v in device.items() if not k.startswith("_")}
