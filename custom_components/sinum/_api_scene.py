"""Mixin for scene, automation, variable and schedule API methods."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._api_helpers import _list_result
from .const import (
    API_AUTOMATION,
    API_AUTOMATION_LOGS,
    API_AUTOMATION_LUA,
    API_AUTOMATION_LUA_EXTENSIONS,
    API_AUTOMATION_SCHEMA,
    API_AUTOMATIONS,
    API_SCENE,
    API_SCENE_ACTIVATE,
    API_SCENE_LOGS,
    API_SCENE_LUA,
    API_SCENE_LUA_EXTENSIONS,
    API_SCENE_SCHEMA,
    API_SCENES,
    API_SCHEDULE,
    API_SCHEDULES,
    API_VARIABLE,
    API_VARIABLES,
)


class SceneMixin:
    """Mixin providing scene, automation, variable and schedule API methods."""

    if TYPE_CHECKING:
        async def _request(self, method: str, path: str, **kwargs: Any) -> Any: ...

    # ---------------------------------------------------------------- scenes

    async def get_scenes(self) -> list[dict[str, Any]]:
        result = await self._request("GET", API_SCENES)
        return _list_result(result, "scenes")

    async def get_scene(self, scene_id: int) -> dict[str, Any]:
        result = await self._request("GET", API_SCENE.format(id=scene_id))
        return result if isinstance(result, dict) else {}

    async def get_scene_lua(self, scene_id: int) -> dict[str, Any]:
        result = await self._request("GET", API_SCENE_LUA.format(id=scene_id))
        return result if isinstance(result, dict) else {}

    async def get_scene_lua_extensions(self, scene_id: int) -> list[dict[str, Any]]:
        result = await self._request("GET", API_SCENE_LUA_EXTENSIONS.format(id=scene_id))
        return _list_result(result, "lua_extensions", "extensions")

    async def get_scene_schema(self, scene_id: int) -> dict[str, Any]:
        result = await self._request("GET", API_SCENE_SCHEMA.format(id=scene_id))
        return result if isinstance(result, dict) else {}

    async def get_scene_logs(self, scene_id: int) -> list[dict[str, Any]]:
        result = await self._request("GET", API_SCENE_LOGS.format(id=scene_id))
        return _list_result(result, "logs")

    async def run_scene(self, scene_id: int) -> None:
        await self._request("POST", API_SCENE_ACTIVATE.format(id=scene_id))

    async def create_scene(self, name: str, lua: str) -> int:
        """Create a code-type scene and return its ID."""
        from .api import SinumConnectionError

        result = await self._request(
            "POST", API_SCENES, json={"name": name, "type": "code", "lua": lua}
        )
        if isinstance(result, dict) and result.get("id"):
            return int(result["id"])
        raise SinumConnectionError(f"Scene creation failed: {result}")

    async def patch_scene_lua(self, scene_id: int, lua: str) -> None:
        """Replace the Lua code of an existing scene."""
        await self._request("PATCH", API_SCENE.format(id=scene_id), json={"lua": lua})

    async def delete_scene(self, scene_id: int) -> None:
        """Delete a scene by ID."""
        await self._request("DELETE", API_SCENE.format(id=scene_id))

    async def find_scene_by_name(self, name: str) -> int | None:
        """Return the ID of the first scene matching *name*, or None."""
        scenes = await self.get_scenes()
        for s in scenes:
            if s.get("name") == name:
                return int(s["id"])
        return None

    async def get_or_create_scene(self, name: str) -> int:
        """Return ID of a named scene, creating it if it doesn't exist."""
        existing = await self.find_scene_by_name(name)
        if existing is not None:
            return existing
        return await self.create_scene(name, "-- HA RGB placeholder")

    # ------------------------------------------------------------ automations

    async def get_automations(self) -> list[dict[str, Any]]:
        result = await self._request("GET", API_AUTOMATIONS)
        return _list_result(result, "automations")

    async def get_automation(self, automation_id: int) -> dict[str, Any]:
        result = await self._request("GET", API_AUTOMATION.format(id=automation_id))
        return result if isinstance(result, dict) else {}

    async def get_automation_lua(self, automation_id: int) -> dict[str, Any]:
        result = await self._request("GET", API_AUTOMATION_LUA.format(id=automation_id))
        return result if isinstance(result, dict) else {}

    async def get_automation_lua_extensions(self, automation_id: int) -> list[dict[str, Any]]:
        result = await self._request("GET", API_AUTOMATION_LUA_EXTENSIONS.format(id=automation_id))
        return _list_result(result, "lua_extensions", "extensions")

    async def get_automation_schema(self, automation_id: int) -> dict[str, Any]:
        result = await self._request("GET", API_AUTOMATION_SCHEMA.format(id=automation_id))
        return result if isinstance(result, dict) else {}

    async def get_automation_logs(self, automation_id: int) -> list[dict[str, Any]]:
        result = await self._request("GET", API_AUTOMATION_LOGS.format(id=automation_id))
        return _list_result(result, "logs")

    # ------------------------------------------------------------ variables

    async def get_variables(self) -> list[dict[str, Any]]:
        result = await self._request("GET", API_VARIABLES)
        return _list_result(result, "variables")

    async def set_variable(self, variable_id: int, value: Any) -> dict[str, Any]:
        return await self._request(
            "PATCH", API_VARIABLE.format(id=variable_id), json={"value": value}
        )

    # ------------------------------------------------------------- schedules

    async def get_schedules(self) -> list[dict[str, Any]]:
        result = await self._request("GET", API_SCHEDULES)
        return _list_result(result, "schedules")

    async def get_schedule(self, schedule_id: int) -> dict[str, Any]:
        result = await self._request("GET", API_SCHEDULE.format(id=schedule_id))
        return result if isinstance(result, dict) else {}

    async def patch_schedule(self, schedule_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        result = await self._request("PATCH", API_SCHEDULE.format(id=schedule_id), json=payload)
        return result if isinstance(result, dict) else {}
