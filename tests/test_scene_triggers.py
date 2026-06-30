"""Tests for Sinum scene platform and device triggers."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.device_automation import async_get_device_automations
from homeassistant.components.scene import DOMAIN as SCENE_DOMAIN
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
from homeassistant.setup import async_setup_component

from custom_components.sinum.const import DOMAIN


@pytest.mark.asyncio
async def test_scene_setup_entry(hass: HomeAssistant, mock_config_entry, mock_coordinator):
    """Test scene platform setup."""
    mock_config_entry.add_to_hass(hass)
    hass.data[DOMAIN] = {mock_config_entry.entry_id: {"coordinator": mock_coordinator}}
    
    # Mock devices with scene type
    mock_coordinator.data = {
        "devices": [
            {
                "id": "scene_1",
                "name": "Scene 1",
                "type": "scene_controller",
                "device_family": "scenes",
            }
        ]
    }
    
    # Load the scene platform
    await hass.config_entries.async_forward_entry_setups(mock_config_entry, [SCENE_DOMAIN])
    await hass.async_block_till_done()
    
    # Check scene entity was created
    entity_registry = async_get_entity_registry(hass)
    scene_entities = [
        ent for ent in entity_registry.entities.values()
        if ent.domain == SCENE_DOMAIN and ent.platform == DOMAIN
    ]
    assert len(scene_entities) > 0


@pytest.mark.asyncio
async def test_scene_activation(hass: HomeAssistant, mock_config_entry, mock_coordinator):
    """Test scene entity activation."""
    from custom_components.sinum.scene import SinumSceneEntity
    
    # Create a mock scene device
    device = {
        "id": "scene_1",
        "name": "Test Scene",
        "type": "scene_controller",
    }
    
    # Create scene entity
    scene_entity = SinumSceneEntity(mock_coordinator, mock_config_entry, device)
    scene_entity.hass = hass
    
    # Mock the API call
    mock_coordinator.client.run_scene = AsyncMock()
    
    # Activate scene
    await scene_entity.async_activate()
    
    # Verify API was called with correct device ID
    mock_coordinator.client.run_scene.assert_called_once_with("scene_1")


@pytest.mark.asyncio
async def test_scene_device_trigger(hass: HomeAssistant, mock_config_entry, mock_coordinator):
    """Test scene device trigger availability."""
    from custom_components.sinum.device_trigger import (
        TRIGGER_TYPE_SCENE_ACTIVATED,
        async_get_triggers,
    )
    
    # Setup entity registry with a scene entity
    entity_registry = async_get_entity_registry(hass)
    
    mock_device = entity_registry.async_get_or_create(
        domain=SCENE_DOMAIN,
        platform=DOMAIN,
        unique_id="scene_1",
        config_entry=mock_config_entry,
    )
    device_id = mock_device.device_id
    
    # Get triggers for device
    triggers = await async_get_triggers(hass, device_id)
    
    # Check scene trigger is available
    scene_triggers = [t for t in triggers if t.get("type") == TRIGGER_TYPE_SCENE_ACTIVATED]
    assert len(scene_triggers) > 0


@pytest.mark.asyncio
async def test_button_and_scene_triggers(hass: HomeAssistant, mock_config_entry):
    """Test that both button and scene triggers are returned."""
    from custom_components.sinum.device_trigger import (
        TRIGGER_TYPE_PRESSED,
        TRIGGER_TYPE_SCENE_ACTIVATED,
        async_get_triggers,
    )
    from homeassistant.components.event import DOMAIN as EVENT_DOMAIN
    
    # Setup entity registry with both button and scene entities
    entity_registry = async_get_entity_registry(hass)
    
    # Create a device
    button_entity = entity_registry.async_get_or_create(
        domain=EVENT_DOMAIN,
        platform=DOMAIN,
        unique_id="button_1",
        config_entry=mock_config_entry,
    )
    
    scene_entity = entity_registry.async_get_or_create(
        domain=SCENE_DOMAIN,
        platform=DOMAIN,
        unique_id="scene_1",
        config_entry=mock_config_entry,
    )
    
    # Both should be on the same device (update scene entity's device_id to match button)
    device_id = button_entity.device_id
    
    # Get all triggers for this device
    triggers = await async_get_triggers(hass, device_id)
    
    # Verify we get both button and scene triggers
    trigger_types = {t.get("type") for t in triggers}
    assert TRIGGER_TYPE_PRESSED in trigger_types
    assert TRIGGER_TYPE_SCENE_ACTIVATED in trigger_types


@pytest.mark.asyncio
async def test_scene_trigger_attachment(hass: HomeAssistant, mock_config_entry):
    """Test attaching scene device trigger to automation."""
    from custom_components.sinum.device_trigger import (
        TRIGGER_TYPE_SCENE_ACTIVATED,
        async_attach_trigger,
    )
    from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_TYPE
    
    # Create entity registry entry
    entity_registry = async_get_entity_registry(hass)
    scene_entity = entity_registry.async_get_or_create(
        domain=SCENE_DOMAIN,
        platform=DOMAIN,
        unique_id="scene_1",
        config_entry=mock_config_entry,
    )
    device_id = scene_entity.device_id
    
    # Create trigger config
    trigger_config = {
        CONF_DOMAIN: DOMAIN,
        CONF_DEVICE_ID: device_id,
        CONF_TYPE: TRIGGER_TYPE_SCENE_ACTIVATED,
    }
    
    # Mock action callback
    action_called = False
    
    async def mock_action(event_data):
        nonlocal action_called
        action_called = True
    
    # Attach trigger
    mock_trigger_info = MagicMock()
    remove_trigger = await async_attach_trigger(
        hass, trigger_config, mock_action, mock_trigger_info
    )
    
    # Verify a callback was registered
    assert remove_trigger is not None
    assert callable(remove_trigger)
