from __future__ import annotations

from typing import Any

from homeassistant.components.climate import HVACAction, HVACMode

_MODE_TO_HVAC: dict[str, HVACMode] = {
    "heating": HVACMode.HEAT,
    "cooling": HVACMode.COOL,
    "automatic": HVACMode.AUTO,
    "off": HVACMode.OFF,
}
_HVAC_TO_MODE: dict[HVACMode, str] = {v: k for k, v in _MODE_TO_HVAC.items()}


def _modes_from_declared(declared: list[str]) -> list[HVACMode]:
    """Build HA mode list from Sinum available_work_modes field."""
    modes: list[HVACMode] = [HVACMode.OFF]
    for sinum_mode in declared:
        ha_mode = _MODE_TO_HVAC.get(sinum_mode)
        if ha_mode and ha_mode not in modes:
            modes.append(ha_mode)
    return modes


def _append_if_supported(modes: list[HVACMode], mode: HVACMode, condition: bool) -> None:
    if condition and mode not in modes:
        modes.append(mode)


def _infer_current_mode(device: dict[str, Any], modes: list[HVACMode]) -> None:
    current = device.get("mode") or device.get("work_mode")
    if not current or current in ("off", ""):
        return
    ha_mode = _MODE_TO_HVAC.get(current)
    _append_if_supported(modes, ha_mode, ha_mode is not None)


def _infer_modes(device: dict[str, Any]) -> list[HVACMode]:
    """Infer HVAC mode list from temperature field presence when hub lists no modes."""
    modes: list[HVACMode] = [HVACMode.OFF]
    _append_if_supported(
        modes, HVACMode.HEAT, device.get("target_temperature_heating_minimum") is not None
    )
    _append_if_supported(
        modes, HVACMode.COOL, device.get("target_temperature_cooling_minimum") is not None
    )
    _infer_current_mode(device, modes)
    if len(modes) == 1:
        modes.append(HVACMode.HEAT)
    return modes


def _available_hvac_modes(device: dict[str, Any]) -> list[HVACMode]:
    if declared := device.get("available_work_modes"):
        return _modes_from_declared(declared)
    return _infer_modes(device)


def _active_mode_bounds(device: dict[str, Any], mode: HVACMode) -> tuple[Any, Any]:
    if mode == HVACMode.HEAT:
        return (
            device.get("target_temperature_heating_minimum"),
            device.get("target_temperature_heating_maximum"),
        )
    if mode == HVACMode.COOL:
        return (
            device.get("target_temperature_cooling_minimum"),
            device.get("target_temperature_cooling_maximum"),
        )
    return None, None


def _scaled_or_default(raw: Any, default: float) -> float:
    if raw is None:
        return default
    return raw / 10


def _target_temperature_mode_value(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("current") or value.get("mode")
    return value


def _copy_keys_if_present(
    source: dict[str, Any], target: dict[str, Any], keys: tuple[str, ...]
) -> None:
    for key in keys:
        if key in source:
            target[key] = source[key]


def _state_action_from_text(state: str, current_mode: HVACMode) -> HVACAction:
    if "heating" in state:
        return HVACAction.HEATING
    if "cooling" in state:
        return HVACAction.COOLING
    if current_mode == HVACMode.OFF:
        return HVACAction.OFF
    return HVACAction.IDLE


def _is_thermostat(device: dict[str, Any]) -> bool:
    return device.get("type") == "thermostat" or (
        "target_temperature" in device and "temperature" in device and "work_mode" not in device
    )


def _has_climate_control(device: dict[str, Any], source: str = "sbus") -> bool:
    """Check if fan_coil can be exposed as climate entity.

    Fan coil climate entities need both mode and setpoint controls. Devices that
    only report room temperature or fan state should stay as sensors/diagnostics.
    """
    return "work_mode" in device and "target_temperature" in device
