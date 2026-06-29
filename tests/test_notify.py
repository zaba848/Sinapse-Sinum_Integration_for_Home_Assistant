"""Tests for Sinum notify platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sinum.api import SinumNotSupportedError
from custom_components.sinum.notify import SinumNotifyEntity, async_setup_entry
from homeassistant.exceptions import HomeAssistantError


def _make_coordinator(hub_name="TestHub", hub_model="sinum_lite"):
    c = MagicMock()
    c.hub_info = {"name": hub_name, "model": hub_model}
    c.client.send_notification = AsyncMock(return_value=None)
    return c


def _make_entity(entry_id="entry_abc", hub_name="TestHub", hub_model="sinum_lite"):
    coordinator = _make_coordinator(hub_name=hub_name, hub_model=hub_model)
    return SinumNotifyEntity(coordinator, entry_id), coordinator


# ──────────────────────────────────────────────────────────────────────────────
# Properties
# ──────────────────────────────────────────────────────────────────────────────


class TestSinumNotifyProperties:
    def test_unique_id_contains_entry_id(self):
        entity, _ = _make_entity(entry_id="my_entry")
        assert entity.unique_id == "my_entry_notify"

    def test_name_is_notification(self):
        entity, _ = _make_entity()
        assert entity.name == "Notification"

    def test_icon_is_bell(self):
        entity, _ = _make_entity()
        assert entity.icon == "mdi:bell-ring"

    def test_device_info_uses_hub_name(self):
        entity, _ = _make_entity(hub_name="MyHub")
        assert entity.device_info["name"] == "MyHub"

    def test_device_info_uses_hub_model(self):
        entity, _ = _make_entity(hub_model="sinum_plus")
        assert entity.device_info["model"] == "sinum_plus"

    def test_device_info_identifiers_contain_entry_id(self):
        entity, _ = _make_entity(entry_id="abc123")
        assert ("sinum", "abc123") in entity.device_info["identifiers"]

    def test_device_info_manufacturer(self):
        entity, _ = _make_entity()
        assert entity.device_info["manufacturer"] == "TECH Sterowniki"


# ──────────────────────────────────────────────────────────────────────────────
# send_message
# ──────────────────────────────────────────────────────────────────────────────


class TestSinumNotifySendMessage:
    @pytest.mark.asyncio
    async def test_sends_message_and_title(self):
        entity, coordinator = _make_entity()
        await entity.async_send_message("Hello world", title="Test")
        coordinator.client.send_notification.assert_awaited_once_with(
            title="Test", message="Hello world"
        )

    @pytest.mark.asyncio
    async def test_default_title_when_none(self):
        entity, coordinator = _make_entity()
        await entity.async_send_message("Hello world", title=None)
        coordinator.client.send_notification.assert_awaited_once_with(
            title="Sinum", message="Hello world"
        )

    @pytest.mark.asyncio
    async def test_raises_ha_error_when_not_supported(self):
        entity, coordinator = _make_entity()
        coordinator.client.send_notification = AsyncMock(
            side_effect=SinumNotSupportedError("not supported")
        )
        with pytest.raises(HomeAssistantError):
            await entity.async_send_message("msg")

    @pytest.mark.asyncio
    async def test_error_message_reflects_hub_limitation(self):
        entity, coordinator = _make_entity()
        coordinator.client.send_notification = AsyncMock(
            side_effect=SinumNotSupportedError("not supported")
        )
        with pytest.raises(HomeAssistantError, match="not support"):
            await entity.async_send_message("msg")

    @pytest.mark.asyncio
    async def test_message_passed_correctly(self):
        entity, coordinator = _make_entity()
        await entity.async_send_message("Fire alarm!", title="Alert")
        call_kwargs = coordinator.client.send_notification.call_args.kwargs
        assert call_kwargs["message"] == "Fire alarm!"

    @pytest.mark.asyncio
    async def test_extra_kwargs_do_not_crash(self):
        entity, coordinator = _make_entity()
        await entity.async_send_message("msg", title="T", data={"extra": "value"})
        coordinator.client.send_notification.assert_awaited_once()


# ──────────────────────────────────────────────────────────────────────────────
# Platform setup
# ──────────────────────────────────────────────────────────────────────────────


class TestNotifySetup:
    @pytest.mark.asyncio
    async def test_setup_creates_exactly_one_entity(self):
        coordinator = _make_coordinator()
        entry = MagicMock()
        entry.entry_id = "entry_x"
        entry.runtime_data = coordinator

        added = []
        await async_setup_entry(MagicMock(), entry, lambda ents: added.extend(ents))
        assert len(added) == 1

    @pytest.mark.asyncio
    async def test_setup_entity_is_notify_entity(self):
        coordinator = _make_coordinator()
        entry = MagicMock()
        entry.entry_id = "entry_x"
        entry.runtime_data = coordinator

        added = []
        await async_setup_entry(MagicMock(), entry, lambda ents: added.extend(ents))
        assert isinstance(added[0], SinumNotifyEntity)

    @pytest.mark.asyncio
    async def test_setup_entity_unique_id_uses_entry_id(self):
        coordinator = _make_coordinator()
        entry = MagicMock()
        entry.entry_id = "my_entry"
        entry.runtime_data = coordinator

        added = []
        await async_setup_entry(MagicMock(), entry, lambda ents: added.extend(ents))
        assert added[0].unique_id == "my_entry_notify"


# ──────────────────────────────────────────────────────────────────────────────
# Hub info edge cases
# ──────────────────────────────────────────────────────────────────────────────


class TestNotifyHubInfoEdgeCases:
    def test_hub_info_none_does_not_crash(self):
        coordinator = MagicMock()
        coordinator.hub_info = None
        coordinator.client.send_notification = AsyncMock()
        entity = SinumNotifyEntity(coordinator, "entry")
        assert entity.unique_id == "entry_notify"

    def test_hub_model_fallback_when_missing(self):
        coordinator = MagicMock()
        coordinator.hub_info = {"name": "Hub"}
        coordinator.client.send_notification = AsyncMock()
        entity = SinumNotifyEntity(coordinator, "entry")
        assert entity.device_info["model"] == "Sinum Hub"
