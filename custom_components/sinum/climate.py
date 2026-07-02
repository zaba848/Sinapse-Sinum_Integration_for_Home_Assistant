from __future__ import annotations

from homeassistant.components.climate import ClimateEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SinumConfigEntry
from ._climate_helpers import _available_hvac_modes, _has_climate_control, _is_thermostat
from .climate_bus import SinumFanCoilClimate, SinumTemperatureRegulatorClimate, _add_bus_climate
from .climate_virtual import SinumHeatPumpManagerClimate, SinumThermostat, _add_virtual_climate
from .coordinator import SinumCoordinator

PARALLEL_UPDATES = 0

# Re-exported for backward compatibility with tests and external imports
__all__ = [
    "SinumFanCoilClimate",
    "SinumHeatPumpManagerClimate",
    "SinumTemperatureRegulatorClimate",
    "SinumThermostat",
    "_available_hvac_modes",
    "_has_climate_control",
    "_is_thermostat",
    "async_setup_entry",
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SinumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SinumCoordinator = entry.runtime_data
    entities: list[ClimateEntity] = []
    _add_virtual_climate(coordinator, entities, entry.entry_id)
    _add_bus_climate(coordinator, entities, entry.entry_id, "sbus")
    _add_bus_climate(coordinator, entities, entry.entry_id, "wtp")
    async_add_entities(entities)
