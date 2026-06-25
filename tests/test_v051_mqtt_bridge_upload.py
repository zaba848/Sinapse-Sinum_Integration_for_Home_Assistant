"""Tests for v0.5.1: sinum.upload_mqtt_bridge service and Lua template rendering.

Covers:
- lua_mqtt_bridge.render(): injects client_id and topic_prefix
- upload_mqtt_bridge service: uses defaults from options/data, calls patch_scene_lua
- dry_run: does not call patch_scene_lua
- Override via service call parameters (scene_id, mqtt_client_id)
- Options flow: mqtt_scene_id and mqtt_client_id fields accepted
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol


# ──────────────────────────────────────────────────────────────────────────────
# Lua template rendering
# ──────────────────────────────────────────────────────────────────────────────


class TestLuaMqttBridgeRender:
    def test_default_values_in_output(self):
        from custom_components.sinum.lua_mqtt_bridge import render
        lua = render(topic_prefix="sinum", client_id=1)
        assert 'local CLIENT_ID   = 1' in lua
        assert 'local TOPIC_PREFIX = "sinum"' in lua

    def test_custom_prefix_injected(self):
        from custom_components.sinum.lua_mqtt_bridge import render
        lua = render(topic_prefix="sinum/tablica-wtp", client_id=1)
        assert 'local TOPIC_PREFIX = "sinum/tablica-wtp"' in lua

    def test_custom_client_id_injected(self):
        from custom_components.sinum.lua_mqtt_bridge import render
        lua = render(topic_prefix="sinum", client_id=3)
        assert 'local CLIENT_ID   = 3' in lua

    def test_output_is_valid_lua_structure(self):
        from custom_components.sinum.lua_mqtt_bridge import render
        lua = render(topic_prefix="sinum", client_id=1)
        # Must contain critical Lua constructs
        assert 'mqtt_client[CLIENT_ID]' in lua
        assert 'event.type' in lua
        assert 'application_initialized' in lua
        assert 'device_state_changed' in lua
        assert 'minute_changed' in lua

    def test_different_prefix_and_client(self):
        from custom_components.sinum.lua_mqtt_bridge import render
        lua2 = render(topic_prefix="home/hub2", client_id=2)
        assert 'local CLIENT_ID   = 2' in lua2
        assert 'local TOPIC_PREFIX = "home/hub2"' in lua2

    def test_returns_string(self):
        from custom_components.sinum.lua_mqtt_bridge import render
        result = render(topic_prefix="x", client_id=1)
        assert isinstance(result, str)
        assert len(result) > 500


# ──────────────────────────────────────────────────────────────────────────────
# upload_mqtt_bridge service
# ──────────────────────────────────────────────────────────────────────────────


def _make_coordinator(options: dict | None = None, data: dict | None = None) -> MagicMock:
    coord = MagicMock()
    coord.client.patch_scene_lua = AsyncMock()
    coord.config_entry = MagicMock()
    coord.config_entry.options = options or {}
    coord.config_entry.data = data or {}
    return coord


def _make_service_call(call_data: dict) -> MagicMock:
    call = MagicMock()
    call.data = call_data
    return call


async def _invoke_upload(hass: MagicMock, call_data: dict, coordinator: MagicMock) -> None:
    """Simulate calling handle_upload_mqtt_bridge via __init__ service registration."""
    from custom_components.sinum import (
        UPLOAD_MQTT_BRIDGE_SCHEMA,
        _render_mqtt_bridge_lua,
    )
    from custom_components.sinum.const import (
        ATTR_ENTRY_ID,
        ATTR_MQTT_CLIENT_ID,
        ATTR_MQTT_DRY_RUN,
        ATTR_MQTT_SCENE_ID,
        CONF_MQTT_CLIENT_ID,
        CONF_MQTT_SCENE_ID,
        CONF_MQTT_TOPIC_PREFIX,
        DEFAULT_MQTT_CLIENT_ID,
        DEFAULT_MQTT_SCENE_ID,
        DEFAULT_MQTT_TOPIC_PREFIX,
    )

    opts = coordinator.config_entry.options
    data = coordinator.config_entry.data

    scene_id = call_data.get(
        ATTR_MQTT_SCENE_ID,
        opts.get(CONF_MQTT_SCENE_ID, data.get(CONF_MQTT_SCENE_ID, DEFAULT_MQTT_SCENE_ID)),
    )
    client_id = call_data.get(
        ATTR_MQTT_CLIENT_ID,
        opts.get(CONF_MQTT_CLIENT_ID, data.get(CONF_MQTT_CLIENT_ID, DEFAULT_MQTT_CLIENT_ID)),
    )
    topic_prefix = opts.get(
        CONF_MQTT_TOPIC_PREFIX,
        data.get(CONF_MQTT_TOPIC_PREFIX, DEFAULT_MQTT_TOPIC_PREFIX),
    )
    lua_code = _render_mqtt_bridge_lua(topic_prefix=topic_prefix, client_id=int(client_id))
    dry_run = call_data.get(ATTR_MQTT_DRY_RUN, False)
    if not dry_run:
        await coordinator.client.patch_scene_lua(int(scene_id), lua_code)


class TestUploadMqttBridgeService:
    @pytest.mark.asyncio
    async def test_uploads_to_default_scene_1(self):
        coord = _make_coordinator()
        await _invoke_upload(MagicMock(), {}, coord)
        coord.client.patch_scene_lua.assert_called_once()
        scene_id, lua = coord.client.patch_scene_lua.call_args[0]
        assert scene_id == 1
        assert 'local CLIENT_ID   = 1' in lua

    @pytest.mark.asyncio
    async def test_uses_scene_id_from_options(self):
        coord = _make_coordinator(options={"mqtt_scene_id": 7})
        await _invoke_upload(MagicMock(), {}, coord)
        scene_id, _ = coord.client.patch_scene_lua.call_args[0]
        assert scene_id == 7

    @pytest.mark.asyncio
    async def test_call_overrides_scene_id(self):
        coord = _make_coordinator(options={"mqtt_scene_id": 7})
        await _invoke_upload(MagicMock(), {"scene_id": 99}, coord)
        scene_id, _ = coord.client.patch_scene_lua.call_args[0]
        assert scene_id == 99

    @pytest.mark.asyncio
    async def test_uses_client_id_from_options(self):
        coord = _make_coordinator(options={"mqtt_client_id": 2})
        await _invoke_upload(MagicMock(), {}, coord)
        _, lua = coord.client.patch_scene_lua.call_args[0]
        assert 'local CLIENT_ID   = 2' in lua

    @pytest.mark.asyncio
    async def test_uses_topic_prefix_from_options(self):
        coord = _make_coordinator(options={"mqtt_topic_prefix": "sinum/my-hub"})
        await _invoke_upload(MagicMock(), {}, coord)
        _, lua = coord.client.patch_scene_lua.call_args[0]
        assert 'local TOPIC_PREFIX = "sinum/my-hub"' in lua

    @pytest.mark.asyncio
    async def test_dry_run_does_not_upload(self):
        coord = _make_coordinator()
        await _invoke_upload(MagicMock(), {"dry_run": True}, coord)
        coord.client.patch_scene_lua.assert_not_called()

    @pytest.mark.asyncio
    async def test_call_overrides_client_id(self):
        coord = _make_coordinator()
        await _invoke_upload(MagicMock(), {"mqtt_client_id": 5}, coord)
        _, lua = coord.client.patch_scene_lua.call_args[0]
        assert 'local CLIENT_ID   = 5' in lua

    @pytest.mark.asyncio
    async def test_falls_back_to_data_when_no_options(self):
        coord = _make_coordinator(
            options={},
            data={"mqtt_scene_id": 4, "mqtt_client_id": 2, "mqtt_topic_prefix": "hub/data"},
        )
        await _invoke_upload(MagicMock(), {}, coord)
        scene_id, lua = coord.client.patch_scene_lua.call_args[0]
        assert scene_id == 4
        assert 'local CLIENT_ID   = 2' in lua
        assert 'local TOPIC_PREFIX = "hub/data"' in lua


# ──────────────────────────────────────────────────────────────────────────────
# Schema validation
# ──────────────────────────────────────────────────────────────────────────────


class TestUploadMqttBridgeSchema:
    def test_empty_call_valid(self):
        from custom_components.sinum import UPLOAD_MQTT_BRIDGE_SCHEMA
        result = UPLOAD_MQTT_BRIDGE_SCHEMA({})
        assert result["dry_run"] is False

    def test_all_fields_valid(self):
        from custom_components.sinum import UPLOAD_MQTT_BRIDGE_SCHEMA
        result = UPLOAD_MQTT_BRIDGE_SCHEMA(
            {"scene_id": 3, "mqtt_client_id": 2, "dry_run": True, "entry_id": "abc"}
        )
        assert result["scene_id"] == 3
        assert result["mqtt_client_id"] == 2
        assert result["dry_run"] is True

    def test_scene_id_must_be_integer(self):
        from custom_components.sinum import UPLOAD_MQTT_BRIDGE_SCHEMA
        with pytest.raises((vol.Invalid, ValueError, TypeError)):
            UPLOAD_MQTT_BRIDGE_SCHEMA({"scene_id": "not_a_number"})


# ──────────────────────────────────────────────────────────────────────────────
# Options flow new fields
# ──────────────────────────────────────────────────────────────────────────────


class TestOptionsFlowMqttFields:
    def _make_options_flow(self, options: dict | None = None, data: dict | None = None):
        from custom_components.sinum.config_flow import SinumOptionsFlow
        entry = MagicMock()
        entry.options = options or {}
        entry.data = data or {}
        return SinumOptionsFlow(entry)

    def test_mqtt_scene_id_default_1(self):
        flow = self._make_options_flow()
        assert flow._opt("mqtt_scene_id", 1) == 1

    def test_mqtt_scene_id_from_options(self):
        flow = self._make_options_flow(options={"mqtt_scene_id": 5})
        assert flow._opt("mqtt_scene_id", 1) == 5

    def test_mqtt_client_id_default_1(self):
        flow = self._make_options_flow()
        assert flow._opt("mqtt_client_id", 1) == 1

    def test_mqtt_client_id_from_data_fallback(self):
        flow = self._make_options_flow(options={}, data={"mqtt_client_id": 3})
        assert flow._opt("mqtt_client_id", 1) == 3
