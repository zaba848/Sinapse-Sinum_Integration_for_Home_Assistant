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
    return {
        "entry": _redact_entry_data(dict(entry.data)),
        "hub_info": _sanitize_device(coordinator.hub_info),
        **_bus_snapshots(coordinator),
        **_bus_counts(coordinator),
        **_performance_metrics(coordinator),
        "mqtt_enabled": coordinator.mqtt_bridge is not None,
    }


def _redact_entry_data(data: dict[str, Any]) -> dict[str, Any]:
    for key in (CONF_API_TOKEN, CONF_PASSWORD):
        if key in data:
            data[key] = "**REDACTED**"
    return data


def _bus_snapshots(coordinator: Any) -> dict[str, Any]:
    return {
        "virtual_devices": _snapshot_store(coordinator.virtual_devices),
        "wtp_devices": _snapshot_store(coordinator.wtp_devices),
        "sbus_devices": _snapshot_store(coordinator.sbus_devices),
        "lora_devices": _snapshot_store(coordinator.lora_devices),
        "slink_devices": _snapshot_store(coordinator.slink_devices),
        "modbus_devices": _snapshot_store(coordinator.modbus_devices),
        "video_devices": _snapshot_video_store(coordinator.video_devices),
        "parent_devices": [_sanitize_device(d) for d in coordinator.parent_devices],
        "floors": _snapshot_store(coordinator.floors),
    }


def _bus_counts(coordinator: Any) -> dict[str, Any]:
    return {
        "rooms_count": len(coordinator.rooms),
        "virtual_count": len(coordinator.virtual_devices),
        "wtp_count": len(coordinator.wtp_devices),
        "sbus_count": len(coordinator.sbus_devices),
        "lora_count": len(coordinator.lora_devices),
        "slink_count": len(coordinator.slink_devices),
        "modbus_count": len(coordinator.modbus_devices),
        "video_count": len(coordinator.video_devices),
        "parent_count": len(coordinator.parent_devices),
    }


def _performance_metrics(coordinator: Any) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "last_update_duration_ms": coordinator.last_update_duration_ms,
        "last_update_success_time": (
            coordinator.last_update_success_time.isoformat()
            if coordinator.last_update_success_time
            else None
        ),
        "fetch_failure_count": coordinator.fetch_failure_count,
        **coordinator.client.request_stats,
    }
    if coordinator.ws_bridge is not None:
        metrics["ws_connect_count"] = coordinator.ws_bridge.connect_count
        metrics["ws_reconnect_count"] = coordinator.ws_bridge.reconnect_count
    return metrics


def _snapshot_store(store: dict[Any, dict[str, Any]]) -> dict[str, Any]:
    return {str(dev_id): _sanitize_device(dev) for dev_id, dev in store.items()}


def _snapshot_video_store(store: dict[Any, dict[str, Any]]) -> dict[str, Any]:
    """Sanitize video devices — strip credentials before including in diagnostics."""
    return {str(dev_id): _sanitize_video_device(dev) for dev_id, dev in store.items()}


def _sanitize_video_device(device: dict[str, Any]) -> dict[str, Any]:
    sanitized = _sanitize_device(device)
    for key in ("password", "login"):
        if key in sanitized:
            sanitized[key] = "**REDACTED**"
    return sanitized


def _sanitize_device(device: dict[str, Any]) -> dict[str, Any]:
    """Remove any internal helper keys added by the coordinator."""
    return {k: v for k, v in device.items() if not k.startswith("_")}
