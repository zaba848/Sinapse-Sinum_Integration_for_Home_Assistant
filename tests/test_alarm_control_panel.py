"""Tests for Sinum alarm control panel setup."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sinum.alarm_control_panel import async_setup_entry


class TestAlarmControlPanelSetup:
    @pytest.mark.asyncio
    async def test_empty_alarm_endpoint_adds_no_entities(self):
        coordinator = MagicMock()
        coordinator.client.get_alarm_devices = AsyncMock(return_value=[])
        entry = MagicMock()
        entry.runtime_data = coordinator
        entry.entry_id = "test_entry"
        async_add_entities = MagicMock()

        await async_setup_entry(MagicMock(), entry, async_add_entities)

        async_add_entities.assert_called_once_with([])
