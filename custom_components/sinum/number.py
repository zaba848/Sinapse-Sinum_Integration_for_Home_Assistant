from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SinumConfigEntry
from .api import SinumConnectionError, SinumNotSupportedError
from .const import DOMAIN, MANUFACTURER, STYPE_ANALOG_OUTPUT, STYPE_PWM
from .coordinator import SinumCoordinator, SinumDeviceAvailableMixin
from .number_bus import SinumAnalogOutputNumber, SinumPwmNumber  # noqa: F401

PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


def _cached_variables(coordinator: SinumCoordinator) -> list[dict[str, Any]]:
    stored = getattr(coordinator, "variables", None)
    if isinstance(stored, list):
        return stored
    return []


async def _load_variables(coordinator: SinumCoordinator) -> list[dict[str, Any]]:
    cached = _cached_variables(coordinator)
    if cached:
        return cached
    try:
        fetched = await coordinator.client.get_variables()
        coordinator.variables = fetched
        return fetched
    except (SinumConnectionError, SinumNotSupportedError):
        _LOGGER.debug("Variables endpoint not available on this hub firmware")
        return cached


def _variable_number_entities(
    coordinator: SinumCoordinator, variables: list[dict[str, Any]], entry_id: str
) -> list[NumberEntity]:
    return [
        SinumVariableNumber(coordinator, var, entry_id)
        for var in variables
        if var.get("type") in ("integer", "float", "number")
    ]


def _sbus_number_entities(coordinator: SinumCoordinator, entry_id: str) -> list[NumberEntity]:
    entities: list[NumberEntity] = []
    for device_id, device in coordinator.sbus_devices.items():
        if device.get("type") == STYPE_ANALOG_OUTPUT:
            entities.append(SinumAnalogOutputNumber(coordinator, device_id, entry_id))
        elif device.get("type") == STYPE_PWM:
            entities.append(SinumPwmNumber(coordinator, device_id, entry_id))
    return entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SinumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SinumCoordinator = entry.runtime_data
    variables = await _load_variables(coordinator)
    entities = _variable_number_entities(coordinator, variables, entry.entry_id)
    entities.extend(_sbus_number_entities(coordinator, entry.entry_id))

    async_add_entities(entities)


def _ensure_variable_cached(
    coordinator: SinumCoordinator, variable_id: int, variable: dict
) -> None:
    if not isinstance(getattr(coordinator, "variables", None), list):
        coordinator.variables = []
    if not any(item.get("id") == variable_id for item in coordinator.variables):
        coordinator.variables.append(variable)


class SinumVariableNumber(
    SinumDeviceAvailableMixin, CoordinatorEntity[SinumCoordinator], NumberEntity
):
    """Sinum global variable exposed as a HA number entity."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX

    def __init__(
        self, coordinator: SinumCoordinator, variable: dict[str, Any], entry_id: str
    ) -> None:
        super().__init__(coordinator)
        self._variable_id: int = variable["id"]
        _ensure_variable_cached(coordinator, self._variable_id, variable)
        self._attr_name = variable.get("name", f"Variable {self._variable_id}")
        self._attr_unique_id = f"{entry_id}_variable_{self._variable_id}"
        self._attr_native_min_value = float(variable.get("min", -999999))
        self._attr_native_max_value = float(variable.get("max", 999999))
        self._attr_native_step = 1.0 if variable.get("type") == "integer" else 0.01
        self._attr_native_value = float(variable.get("value", 0))
        self._attr_icon = "mdi:variable"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_variables")},
            name="Sinum Variables",
            manufacturer=MANUFACTURER,
            model=_hub_model(coordinator.hub_info),
        )

    @property
    def _variable(self) -> dict[str, Any]:
        variables = getattr(self.coordinator, "variables", [])
        for variable in variables:
            if variable.get("id") == self._variable_id:
                return variable
        return {}

    @property
    def _device(self) -> dict[str, Any]:
        return self._variable

    @property
    def native_value(self) -> float | None:
        value = self._variable.get("value")
        return float(value) if value is not None else None

    async def async_set_native_value(self, value: float) -> None:
        try:
            updated = await self.coordinator.client.set_variable(self._variable_id, value)
        except Exception as err:
            raise HomeAssistantError(f"Cannot set variable: {err}") from err
        variable = self._variable
        if variable:
            variable.update(updated)
        else:
            self.coordinator.variables.append(updated)
        self.async_write_ha_state()


def _hub_model(hub_info: dict[str, Any]) -> str:
    if not isinstance(hub_info, dict):
        return "Sinum EH-01"
    model_map = {
        "sinum_plus": "Sinum Plus",
        "sinum_pro": "Sinum Pro",
        "sinum_lite": "Sinum Lite",
        "sinum": "Sinum EH-01",
    }
    return hub_info.get("model") or model_map.get(hub_info.get("device_type", "")) or "Sinum EH-01"
