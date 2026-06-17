"""Tests for Sinum button entities."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sinum.button import SinumSceneButton


class TestSinumSceneButton:
    @pytest.mark.asyncio
    async def test_press_runs_scene(self):
        coordinator = MagicMock()
        coordinator.client.run_scene = AsyncMock(return_value=None)
        entity = SinumSceneButton(
            coordinator,
            {"id": 2, "name": "Good Night"},
            "test_entry",
        )

        await entity.async_press()

        coordinator.client.run_scene.assert_awaited_once_with(2)
