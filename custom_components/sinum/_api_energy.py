"""Mixin for energy center and weather API methods."""

from __future__ import annotations

import asyncio
from typing import Any

from ._api_helpers import _list_result, _partition_energy_results
from .const import (
    API_ENERGY,
    API_ENERGY_CENTER_ASSOCIATIONS,
    API_ENERGY_CENTER_CONSUMPTION,
    API_ENERGY_CENTER_FLOW_MONITOR,
    API_ENERGY_CENTER_PRICES,
    API_ENERGY_CENTER_PRICES_SETTINGS,
    API_ENERGY_CENTER_PRICES_SOURCES,
    API_ENERGY_CENTER_PRODUCTION,
    API_ENERGY_CENTER_STORAGE,
    API_LUA_INFO,
    API_WEATHER,
)


class EnergyMixin:
    """Mixin providing energy center and weather API methods.

    Requires self._request() from the base SinumClient transport.
    """

    # --------------------------------------------------------------- weather

    async def get_weather(self) -> dict[str, Any]:
        return await self._request("GET", API_WEATHER)  # type: ignore[attr-defined]

    # --------------------------------------------------------------- energy

    async def get_energy(self) -> dict[str, Any]:
        return await self._request("GET", API_ENERGY)  # type: ignore[attr-defined]

    async def get_energy_center_associations(self) -> dict[str, Any]:
        result = await self._request("GET", API_ENERGY_CENTER_ASSOCIATIONS)  # type: ignore[attr-defined]
        return result if isinstance(result, dict) else {}

    async def get_energy_center_flow_monitor(self) -> dict[str, Any]:
        result = await self._request("GET", API_ENERGY_CENTER_FLOW_MONITOR)  # type: ignore[attr-defined]
        return result if isinstance(result, dict) else {}

    async def get_energy_center_prices(self) -> dict[str, Any]:
        result = await self._request("GET", API_ENERGY_CENTER_PRICES)  # type: ignore[attr-defined]
        return result if isinstance(result, dict) else {}

    async def get_energy_center_prices_settings(self) -> dict[str, Any]:
        result = await self._request("GET", API_ENERGY_CENTER_PRICES_SETTINGS)  # type: ignore[attr-defined]
        return result if isinstance(result, dict) else {}

    async def get_energy_center_prices_sources(self) -> list[dict[str, Any]]:
        result = await self._request("GET", API_ENERGY_CENTER_PRICES_SOURCES)  # type: ignore[attr-defined]
        return _list_result(result, "sources")

    async def get_energy_center_storage(self) -> dict[str, Any]:
        result = await self._request("GET", API_ENERGY_CENTER_STORAGE)  # type: ignore[attr-defined]
        return result if isinstance(result, dict) else {}

    async def get_energy_center_consumption(self) -> dict[str, Any]:
        result = await self._request("GET", API_ENERGY_CENTER_CONSUMPTION)  # type: ignore[attr-defined]
        return result if isinstance(result, dict) else {}

    async def get_energy_center_production(self) -> dict[str, Any]:
        result = await self._request("GET", API_ENERGY_CENTER_PRODUCTION)  # type: ignore[attr-defined]
        return result if isinstance(result, dict) else {}

    @staticmethod
    def _energy_center_keys() -> tuple[str, ...]:
        return (
            "associations",
            "flow_monitor",
            "prices",
            "prices_settings",
            "prices_sources",
            "storage",
            "consumption",
            "production",
        )

    def _energy_center_getters(self) -> tuple[Any, ...]:
        return (
            self.get_energy_center_associations,  # type: ignore[attr-defined]
            self.get_energy_center_flow_monitor,  # type: ignore[attr-defined]
            self.get_energy_center_prices,  # type: ignore[attr-defined]
            self.get_energy_center_prices_settings,  # type: ignore[attr-defined]
            self.get_energy_center_prices_sources,  # type: ignore[attr-defined]
            self.get_energy_center_storage,  # type: ignore[attr-defined]
            self.get_energy_center_consumption,  # type: ignore[attr-defined]
            self.get_energy_center_production,  # type: ignore[attr-defined]
        )

    async def _safe_get_energy_center_value(self, getter: Any) -> Any:
        try:
            return await getter()
        except Exception:
            return None

    @staticmethod
    def _build_energy_center_summary(keys: tuple[str, ...], results: list[Any]) -> dict[str, Any]:
        from .api import SinumConnectionError

        available, missing = _partition_energy_results(keys, results)
        if not available:
            raise SinumConnectionError("Energy Center endpoints unavailable")
        return {
            **available,
            "available_endpoints": list(available.keys()),
            "missing_endpoints": missing,
        }

    async def get_energy_center_summary(self) -> dict[str, Any]:
        keys = self._energy_center_keys()
        getters = self._energy_center_getters()
        results = await asyncio.gather(
            *(self._safe_get_energy_center_value(getter) for getter in getters)
        )
        return self._build_energy_center_summary(keys, list(results))

    # ----------------------------------------- Lua HTTP server (optional)

    async def get_lua_hub_info(self) -> dict[str, Any]:
        return await self._request("GET", API_LUA_INFO)  # type: ignore[attr-defined]
