"""Tests for Sinum button entities."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sinum.api import SinumConnectionError
from custom_components.sinum.button import SinumSceneButton, async_setup_entry


def _make_coordinator(scenes=None):
    c = MagicMock()
    c.hub_info = {"name": "TestHub", "device_type": "sinum_lite", "version": "1.24"}
    c.scenes = scenes if scenes is not None else []
    c.client.run_scene = AsyncMock(return_value=None)
    c.client.get_scenes = AsyncMock(return_value=[])
    return c


class TestSinumSceneButton:
    def _make(self, scene_id=2, name="Good Night"):
        coordinator = _make_coordinator()
        return SinumSceneButton(coordinator, {"id": scene_id, "name": name}, "test_entry"), coordinator

    @pytest.mark.asyncio
    async def test_press_runs_scene(self):
        entity, coordinator = self._make()
        await entity.async_press()
        coordinator.client.run_scene.assert_awaited_once_with(2)

    def test_unique_id_contains_scene_id(self):
        entity, _ = self._make(scene_id=42)
        assert "42" in entity.unique_id
        assert entity.unique_id == "test_entry_scene_42"

    def test_name_uses_scene_name(self):
        entity, _ = self._make(name="Morning")
        assert entity.name == "Morning"

    def test_name_fallback_when_missing(self):
        coordinator = _make_coordinator()
        entity = SinumSceneButton(coordinator, {"id": 99}, "e")
        assert "99" in entity.name

    def test_device_info_uses_hub_name(self):
        entity, _ = self._make()
        assert entity.device_info["name"] == "TestHub Scenes"

    def test_icon_is_set(self):
        entity, _ = self._make()
        assert entity.icon is not None

    @pytest.mark.asyncio
    async def test_press_passes_correct_scene_id(self):
        entity, coordinator = self._make(scene_id=77)
        await entity.async_press()
        coordinator.client.run_scene.assert_awaited_once_with(77)

    @pytest.mark.asyncio
    async def test_setup_uses_coordinator_cached_scenes(self):
        """If coordinator.scenes is pre-populated, no API call is made."""
        scenes = [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]
        coordinator = _make_coordinator(scenes=scenes)
        added = []
        await async_setup_entry(MagicMock(), _make_entry(coordinator), lambda e, **_: added.extend(e))
        assert len(added) == 2
        coordinator.client.get_scenes.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_setup_fetches_scenes_when_cache_empty(self):
        """Empty coordinator.scenes triggers a get_scenes() call."""
        scenes = [{"id": 5, "name": "Night"}]
        coordinator = _make_coordinator(scenes=[])
        coordinator.client.get_scenes = AsyncMock(return_value=scenes)
        added = []
        await async_setup_entry(MagicMock(), _make_entry(coordinator), lambda e, **_: added.extend(e))
        assert len(added) == 1
        coordinator.client.get_scenes.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_setup_graceful_when_scenes_endpoint_unavailable(self):
        """SinumConnectionError from get_scenes results in zero entities, not a crash."""
        coordinator = _make_coordinator(scenes=[])
        coordinator.client.get_scenes = AsyncMock(side_effect=SinumConnectionError("404"))
        added = []
        await async_setup_entry(MagicMock(), _make_entry(coordinator), lambda e, **_: added.extend(e))
        assert added == []


def _make_entry(coordinator):
    e = MagicMock()
    e.runtime_data = coordinator
    e.entry_id = "test_entry"
    return e
