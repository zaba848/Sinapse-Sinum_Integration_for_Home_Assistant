from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

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
    try:
        variables = await coordinator.client.get_variables()
    except SinumConnectionError:
        _LOGGER.debug("Variables endpoint not available on this hub firmware")
        variables = []

    entities: list[NumberEntity] = []
    for var in variables:
        if var.get("type") in ("integer", "float", "number"):
            entities.append(SinumVariableNumber(coordinator, var, entry.entry_id))

    async_add_entities(entities)


class SinumVariableNumber(NumberEntity):
    """Sinum global variable exposed as a HA number entity."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: SinumCoordinator, variable: dict[str, Any], entry_id: str) -> None:
        self._coordinator = coordinator
        self._variable_id: int = variable["id"]
        self._variable = variable
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
            manufacturer="TECH Sterowniki",
            model="Sinum EH-01",
        )

    @property
    def native_value(self) -> float:
        return float(self._variable.get("value", 0))

    async def async_set_native_value(self, value: float) -> None:
        updated = await self._coordinator.client.set_variable(self._variable_id, value)
        self._variable.update(updated)
        self.async_write_ha_state()

    async def async_update(self) -> None:
        try:
            variables = await self._coordinator.client.get_variables()
        except SinumConnectionError as err:
            _LOGGER.warning("Variable update failed for %s: %s", self._variable_id, err)
            return
        for variable in variables:
            if variable.get("id") == self._variable_id:
                self._variable.update(variable)
                break
