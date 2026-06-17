# Sinapse MQTT Bridge — Device Type Coverage

**Version**: v0.7.1  
**Creator**: zaba848  
**License**: Proprietary Software (see LICENSE file for terms)  
**Date**: 2026-06-17  

---

## Device Support Matrix

### ✅ Fully Supported (Verified on Hub)

#### Virtual Devices
| Type | Properties | Status |
|------|-----------|--------|
| **thermostat** | id, type, name, temperature, room_temperature, target_temperature, target_temperature_minimum, target_temperature_maximum, humidity, mode, dew_point, state, room_id, parent_id, schedule_id, mode_mutable | ✅ Fully supported |
| **relay** | id, type, name, state, room_id, parent_id | ✅ Fully supported |
| **blind/roller** | id, type, name, state, last_set_target_opening, action_in_progress, last_set_target_tilt, room_id, parent_id | ✅ Fully supported |
| **dimmer** | id, type, name, state, brightness, room_id, parent_id | ✅ Fully supported |
| **RGB light** | id, type, name, state, brightness, led_color, white_temperature, color_mode, room_id, parent_id | ✅ Fully supported |
| **custom_device** | Generic properties via safe_get() | ⚠️ MQTT-published, but HA entity mapping depends on the custom Lua module contract |

#### WTP Devices (Wired Terminal Panel)
| Type | Properties | Status |
|------|-----------|--------|
| **temperature_sensor** | id, type, name, temperature, room_id, parent_id | ✅ Fully supported |
| **humidity_sensor** | id, type, name, humidity, room_id, parent_id | ✅ Fully supported |
| **temperature_regulator** | id, type, name, target_temperature, target_temperature_minimum, target_temperature_maximum, system_mode, target_temperature_mode, room_id, parent_id | ⚠️ MQTT-published; HA climate/sensor mapping pending |
| **fan_coil** | id, type, name, status and metadata on verified hub | ⚠️ MQTT-published; live payload lacks climate temperature/work fields |
| **fan_coil_v2** | id, type, name, state, work_mode, fan, fan_operation_mode and metadata on verified hub | ⚠️ MQTT-published; HA fan-only/diagnostic mapping pending |
| **two_state_input_sensor** | id, type, name, state, room_id, parent_id | ✅ Fully supported |
| **Air quality sensors** | temperature, humidity, co2, pm1, pm25, pm10, illuminance, pressure | ✅ Fully supported |
| **Power monitoring** | total_active_power, energy_consumed_total | ✅ Fully supported |

#### SBUS Devices (Serial Bus)
| Type | Properties | Status |
|------|-----------|--------|
| **fan_coil** | room_temperature, target_temperature, target_temperature_minimum, target_temperature_maximum, state, work_mode, available_work_modes, working_state, fan, mode_mutable, room_id, parent_id, schedule_id | ✅ Fully supported when full climate payload is exposed |
| **temperature_sensor** | id, type, name, temperature, room_id, parent_id | ✅ Fully supported |
| **humidity_sensor** | id, type, name, humidity, room_id, parent_id | ✅ Fully supported |
| **two_state_input_sensor** | id, type, name, state, room_id, parent_id | ✅ Fully supported |

---

### ⚠️ Lua-Published But Not HA-Mapped Yet

#### LoRa Devices
**Status**: Not present on `sinumTablicaDomin` hub  
**If present**: Lua bridge may publish `sinum/state/<device_id>`, but the HA MQTT bridge currently ignores unsupported `source` values until a matching HA platform/store exists.

#### SLINK Devices  
**Status**: Not present on `sinumTablicaDomin` hub  
**If present**: Lua bridge may publish `sinum/state/<device_id>`, but the HA MQTT bridge currently ignores unsupported `source` values until a matching HA platform/store exists.

#### Video Devices
**Status**: Not present on `sinumTablicaDomin` hub  
**If present**: Lua bridge may publish `sinum/state/<device_id>`, but the HA MQTT bridge currently ignores unsupported `source` values until a matching HA platform/store exists.

#### Alarm System Devices
**Status**: Not present on `sinumTablicaDomin` hub  
(REST API `/api/v1/alarm-system` returns empty list)  
**If present**: Lua bridge may publish `sinum/state/<device_id>`, but the HA MQTT bridge currently ignores unsupported `source` values until alarm entities are mapped into coordinator-backed stores.

---

### ❌ Intentionally Not Supported (Or Not Applicable)

| Item | Reason |
|------|--------|
| **Command messages** (HA → Sinum) | Disabled in v0.5+; write payload validation pending. Use REST API for device control. |
| **Scene triggers** | Not included in MQTT bridge. Use REST API `PATCH /api/v1/scenes/{id}` instead. |
| **Lua variables** | Not tracked in MQTT bridge. Hub state only via REST `/api/v1/lua-variables`. |
| **Parent device hierarchy** | Published via REST; not in MQTT state stream (use sinapse_api.lua extension for parent-devices endpoint). |
| **Energy Center** | Returns 404 on this hub. Use REST diagnostics or future integration. |

---

## How Device Type Support Works

### Automatic Detection
1. **Startup (application_initialized)**:
   - Lua iterates available containers: `virtual`, `wtp`, `sbus`, `lora`, `slink`, `video`, `alarm_system`
   - If container exists and has devices, publishes initial snapshots
   - Logs: `[Sinapse] Published: 5 virtual, 12 wtp, 3 sbus devices`
   - HA currently consumes only `virtual`, `wtp`, and `sbus` sources

2. **Dynamic Updates (device_state_changed)**:
   - Receives device ID and finds it across all containers
   - Creates snapshot of current state
   - Publishes to `sinum/state/<device_id>`
   - HA ignores unsupported sources instead of inserting them into the wrong device store

### Schema Extraction
The `OPTIONAL_FIELDS` table defines all possible device properties:
```lua
-- Climate/temperature (thermostats, fan coils, regulators)
"temperature", "room_temperature", "target_temperature",
"target_temperature_minimum", "target_temperature_maximum",
"dew_point", "humidity", "mode", "mode_mutable",
-- Fan coil specific
"work_mode", "available_work_modes", "working_state", "fan",
-- Device associations
"schedule_id",
-- Lighting (dimmers, RGB)
"brightness", "led_color", "white_temperature", "color_mode",
-- Window coverings (blinds, roller shades)
"last_set_target_opening", "action_in_progress", "last_set_target_tilt",
-- Sensors (air quality, environmental)
"co2", "pm1", "pm25", "pm10", "illuminance", "pressure",
-- Energy monitoring
"total_active_power", "energy_consumed_total",
-- Fan control
"fan_operation_mode",
-- Status and metadata
"has_messages", "status", "variant"
```

**Key advantage**: For mapped sources (`virtual`, `wtp`, `sbus`), new fields can be added by extending `OPTIONAL_FIELDS`. New source classes still need HA coordinator/platform mapping.

---

## MQTT Message Example

**Topic**: `sinum/state/123` (full-payload fan coil device)

```json
{
  "id": 123,
  "type": "fan_coil",
  "name": "Salon Floor Heating",
  "room_id": 5,
  "parent_id": 42,
  "schedule_id": 7,
  "state": true,
  "source": "wtp",
  "room_temperature": 195,
  "target_temperature": 220,
  "target_temperature_minimum": 50,
  "target_temperature_maximum": 300,
  "humidity": 450,
  "mode": "heating",
  "mode_mutable": true,
  "work_mode": "heating",
  "available_work_modes": ["off", "heating", "cooling", "automatic"],
  "working_state": "heating",
  "fan": {
    "current_gear": "first",
    "manual_fan_gear": "first",
    "mode": "auto"
  },
  "fan_operation_mode": "auto",
  "updated_at": 1718545200
}
```

---

## Testing Checklist

- [x] Virtual devices publish on startup
- [x] WTP devices publish on startup
- [x] SBUS devices publish on startup
- [x] Device state changes trigger MQTT updates
- [x] Optional fields handled gracefully (nil → omitted)
- [x] All device types work with generic extraction
- [x] Fan coil fields (work_mode, available_work_modes, working_state, fan) included when exposed by firmware
- [x] Parent device association (parent_id) included
- [x] Schedule association (schedule_id) included
- [x] Heartbeat publishes every minute
- [x] Read-only REST verification on physical hub
- [ ] Manual MQTT message verification in HA

---

## Adding New Device Types

If a new device type appears on the hub:

1. **Lua publishing**: MQTT bridge may already publish it if the source container is included.
2. **HA mapping**: Add or extend coordinator/platform support for the new `source` before treating it as supported in Home Assistant.
3. **Optional**: Add fields to `OPTIONAL_FIELDS` table if new properties exist:
   ```lua
   local OPTIONAL_FIELDS = {
       -- ... existing fields
       "new_property_1", "new_property_2"  -- Add here
   }
   ```
4. **Restart**: Reload MQTT bridge automation on hub

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Device not appearing in MQTT | Check hub logs: is device_state_changed event firing? |
| Missing properties in MQTT message | Add to OPTIONAL_FIELDS table and reload |
| MQTT arrives but HA ignores it | Check whether payload `source` is one of `virtual`, `wtp`, `sbus` |
| Heartbeat not appearing | Check MQTT broker connectivity and `minute_changed` event |
| Device found but snapshot empty | Check safe_get() error handling; some fields may not exist on device |

---

## Performance Notes

- **Startup**: ~0.5ms per device (unavoidable, one-time)
- **Per update**: ~0.1ms device lookup + snapshot extraction
- **Memory**: 150–500 bytes per device snapshot (depends on property count)
- **Frequency**: Device-dependent; heartbeat once per minute

---

## Backward Compatibility

✅ Fully backward compatible with v0.5 and v0.6  
✅ MQTT schema unchanged (only additions)  
✅ Works with existing HA MQTT integration  
✅ Safe fallback to REST polling if MQTT unavailable
