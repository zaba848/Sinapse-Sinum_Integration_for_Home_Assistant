# Entity Reference — Sinapse / Sinum Integration

**[← Back to README](../README.md)** · **[Polski](entities.pl.md)**

---

## Contents

- [Platform Overview](#platform-overview)
- [Climate](#climate)
- [Sensor](#sensor)
- [Binary Sensor](#binary-sensor)
- [Switch](#switch)
- [Cover](#cover)
- [Light](#light)
- [Event — Physical Buttons](#event--physical-buttons)
- [Button — Sinum Scenes](#button--sinum-scenes)
- [Number](#number)
- [Update](#update)
- [Alarm Control Panel](#alarm-control-panel)
- [Camera](#camera)
- [Device Availability](#device-availability)

---

## Platform Overview

| Platform | Description | Buses |
|---|---|---|
| `climate` | Thermostats, fan coils, regulators, heat pump manager | Virtual, WTP, SBUS |
| `sensor` | Temperature, humidity, CO₂, energy, diagnostics, and more | All |
| `binary_sensor` | Flood, motion, opening, smoke, valve state, connectivity | WTP, SBUS, LoRa |
| `switch` | Relays, electric strike, valve pump, common valve | Virtual, WTP, SBUS |
| `cover` | Blind controllers, gates | Virtual, WTP |
| `light` | Dimmers, RGB controllers | Virtual, WTP, SBUS |
| `event` | Physical button press events | WTP, SBUS |
| `button` | Sinum Lua scenes | Hub-level |
| `number` | Lua environment variables, SBUS analog output | Virtual, SBUS |
| `update` | Parent device firmware tracker | Hub-level |
| `alarm_control_panel` | Alarm system | Hub-level |
| `camera` | IP/ONVIF cameras via hub snapshot proxy | Hub-level |

---

## Climate

### Virtual Thermostat (`thermostat`)

Controls a virtual zone thermostat. 

- **HVAC modes**: `heat` / `off`
- **Temperature range**: read from hub (`target_temperature_minimum` / `target_temperature_maximum`); values outside range are clamped before sending
- **Current temperature**: shown when a physical sensor is associated; otherwise `unknown`
- **Unique ID format**: `{entry_id}_virtual_{device_id}`

### Fan Coil — WTP (`fan_coil`, `fan_coil_v2`)

Full HVAC control over a WTP fan coil unit.

- **HVAC modes**: `heat`, `cool`, `fan_only`, `off`
- **Fan modes**: `low`, `medium`, `high`
- **Target temperature**: write via REST PATCH

WTP fan coils also expose a valve-state `binary_sensor` entity (`is_on = valve open`).

### Fan Coil — SBUS (`fan_coil`)

Same as WTP fan coil above, but communicates over SBUS bus.

### Temperature Regulator (`temperature_regulator` — WTP and SBUS)

On/off heating regulator with temperature control.

- **HVAC modes**: `heat` / `off`
- **Target temperature**: read/write

### Heat Pump Manager (`heat_pump_manager`)

Manages a central heat pump installation group.

- **HVAC modes**: `heat`, `cool`, `off`
- **Target temperature**: applied to the managed group
- **Extra state attributes**: child thermostat states as diagnostic data

---

## Sensor

### Reading quality

Hub temperature/humidity sensors return `unknown` (not `0.0`) when:
- Raw hub value is `0` and the device has no physical sensor (`zero_is_unavailable = True`)
- Device reports `status = "offline"`
- Hub sentinel value `−3276.8` is present (SBUS internal "no reading" code)

This prevents phantom 0.0 °C readings on virtual thermostats without associated hardware.

### Sensor types

| Device class | Unit | Scale | Notes |
|---|---|---|---|
| Temperature | °C | ×0.1 | Raw value is °C × 10 |
| Humidity | %RH | ×0.1 | Raw value is %RH × 10 |
| CO₂ | ppm | ×1 | |
| Illuminance | lx | ×1 | |
| Pressure | hPa | ×0.1 | |
| PM2.5 | µg/m³ | ×1 | |
| PM10 | µg/m³ | ×1 | |
| IAQ index | — | ×1 | Air quality index |
| Power | W | ×1 | |
| Energy | kWh | ×0.001 | Raw value is Wh |
| Voltage | V | ×0.1 | |
| Current | A | ×0.01 | |
| Impulse count | — | ×1 | Cumulative counter |
| Analog input | V | mapped 0–10 V | SBUS 0–100 scale |
| Weather | — | — | Enum: clear, cloudy, rain, snow, … |

### Special sensors

**Hub diagnostics**: firmware version, API version, hub name, uptime — exposed as `sensor.sinum_*_hub_info_*` entities.

**Energy Center**: flow temperature, storage temperature, production stats — appear only when hub firmware exposes `/api/v1/energy-center/*`.

**Automation status**: `last_run` timestamp and `status` text for each Sinum automation script.

**Schedule summaries**: active period name and target temperature for thermal schedules.

**SBUS regulator target temp**: target temperature as a dedicated sensor (in addition to the climate entity).

---

## Binary Sensor

| Device type | `is_on` meaning | Bus |
|---|---|---|
| `flood_sensor` | Flood detected | WTP, SBUS, LoRa |
| `motion_sensor` | Motion detected | WTP, SBUS |
| `opening_sensor` | Contact open | WTP, LoRa |
| `smoke_sensor` | Smoke detected | WTP, LoRa |
| `two_state_input_sensor` | Input active | WTP, SBUS |
| `fan_coil` valve state | Valve open | WTP |
| Parent device | Connected | Hub-level |

### Fan coil extra attributes

WTP fan coil binary sensors expose gear states as extra attributes:

```
gear_1_active: true
gear_2_active: false
gear_3_active: false
```

---

## Switch

Physical relays on WTP and SBUS buses, plus virtual relay integrators.

### Filtering

Relays tagged with the `managed_by_thermostat` label in Sinum are **excluded** from switch entities — they are controlled by the `climate` platform instead. This prevents double-control conflicts.

### Special types

| Type | Description |
|---|---|
| `relay_integrator` | Virtual relay (no physical bus) |
| `wicket` | Electric strike / door release |
| `valve_pump` | SBUS valve pump controller |
| `common_valve` | SBUS common valve |

---

## Cover

### Blind Controller — WTP (`blind_controller`)

- **Features**: open, close, stop, set position (0–100%)
- **State**: `open`, `closed`, `opening`, `closing`, `stopped`
- **Position tracking**: from hub `current_opening` field
- **Moving detection**: `is_opening` / `is_closing` compare `target_opening` vs `current_opening`
- **Restore on restart**: position restored from HA last-known state

### Blind Controller — Virtual Integrator (`blind_controller_integrator`)

Same features as WTP blind. State is `unknown` and position is `None` when no physical controllers are linked (hub configuration issue, not an integration bug).

### Gate — Virtual (`gate`)

- **Features**: open, close, stop
- **State machine**: open/close/opening/closing/stopped derived from hub `state` field
- **Position**: not supported (gates don't report position)

### SBUS Blind Controller (`blind_controller`)

- **Features**: open, close, stop, set position, optionally tilt (when `current_tilt`/`target_tilt` present)
- **Tilt detection**: automatic — entity supports `SET_TILT_POSITION` when tilt fields are present on the device

---

## Light

### Dimmer — WTP / SBUS (`dimmer`)

- **Features**: on/off, brightness 0–100%
- **Control**: REST PATCH to hub
- **Color mode**: `BRIGHTNESS`

### RGB Controller — WTP (`rgb_controller`)

- **Features**: on/off, brightness, RGB color, color temperature
- **Control**: REST PATCH
- **Color mode**: `HS` for color, `COLOR_TEMP` for white temperature
- **Limitation**: in color-temperature mode the hub ignores color values (firmware behavior); only `color_temp_kelvin` takes effect

### RGB Controller — SBUS (`rgb_controller`)

- **Features**: on/off, brightness, RGB color, color temperature
- **Control**: hub Lua scene — each SBUS RGB entity uses a dedicated persistent scene named `_ha_rgb_sbus_{id}`
- **Command sequence**: GET/POST to find-or-create scene → PATCH scene Lua code → POST `/activate`
- **Important**: `set_color` is sent before `set_brightness` — firmware resets brightness when color changes

### Button Backlight (`button`)

A WTP physical button's RGB backlight color. Appears in the entity's device configuration page.

- **Entity category**: `config`
- **Features**: on/off, HS color
- **Control**: REST PATCH `color` field

### Virtual Dimmer / RGB Integrators

Virtual devices that aggregate physical dimmers or RGB controllers. Same control interface as their physical counterparts.

---

## Event — Physical Buttons

Physical WTP and SBUS buttons are exposed as **Event entities** (`event.sinum_*`). Each press fires a `pressed` event with the press type.

### How detection works

The coordinator compares two fields on each poll:

| Field | Meaning |
|---|---|
| `action` | Press type: `"single"`, `"double"`, `"hold"`, … |
| `buttons_count` | Cumulative press counter — increments on every press |

Both fields are compared to the previous poll. An event fires if either changes. `buttons_count` catches rapid same-type presses that would otherwise be missed.

### Press detection latency

| Transport | Typical latency |
|---|---|
| REST polling only | Up to 30 s (poll interval) |
| WebSocket enabled | < 1 s |
| MQTT bridge enabled | < 1 s |

### Event attributes

| Attribute | Example | Description |
|---|---|---|
| `action` | `"single"`, `"double"`, `"hold"` | Press type from hub |
| `buttons_count` | `42` | Cumulative hub-side counter |

### SBUS button limitation

SBUS buttons reset `action` to `""` immediately after a press. By the time the coordinator polls, the `action` field may already be empty. The press IS detected via `buttons_count`, but `action` will be `None` in the event. Enable WebSocket or MQTT for real-time action type on SBUS buttons.

### Automating button presses

**Option A — Device trigger (recommended for UI-based automations):**

```yaml
automation:
  - alias: "Button long press → Night scene"
    trigger:
      - platform: device
        domain: sinum
        device_id: !secret button_device_id
        type: pressed
        subtype: hold
    action:
      - service: scene.turn_on
        target:
          entity_id: scene.night
```

**Option B — State trigger:**

```yaml
automation:
  - alias: "Living room button → toggle lights"
    trigger:
      - platform: state
        entity_id: event.sinum_living_room_button
    action:
      - service: light.toggle
        target:
          area_id: living_room
```

**Option C — MQTT event (fastest, requires MQTT bridge):**

```yaml
automation:
  - alias: "Button via MQTT event"
    trigger:
      - platform: event
        event_type: sinum_button_event
    condition:
      - condition: template
        value_template: "{{ trigger.event.data.action == 'single' }}"
    action:
      - service: scene.turn_on
        target:
          entity_id: scene.evening
```

---

## Button — Sinum Scenes

Sinum scenes with type `code` appear as `button` entities. Pressing the button calls `POST /api/v1/scenes/{id}/activate`.

```yaml
service: button.press
target:
  entity_id: button.sinum_close_all_blinds
```

Only `code`-type scenes are exposed — status/trigger scenes are read-only (shown as automation sensors).

---

## Number

### Lua Environment Variables

Numeric variables shared across Lua scripts on the hub. Read and write from HA automations to pass setpoints or trigger conditions to hub-side logic.

```yaml
# Set a setpoint from HA
service: number.set_value
target:
  entity_id: number.sinum_setpoint_bedroom
data:
  value: 22.5
```

```lua
-- Read in a Sinum scene
local setpoint = variable[1]:getValue()
sbus[42]:setValue("target_temperature", setpoint * 10)
```

### SBUS Analog Output (0–10 V)

Direct voltage output control. HA range: `0`–`100` mapped to `0–10 V`.

---

## Update

Parent device firmware tracker. Each Sinum parent device (hardware module) appears as an `update` entity showing the installed firmware version. Updating firmware through this entity is not supported — use the Sinum web UI.

---

## Alarm Control Panel

Present only when the hub has an alarm system (`/api/v1/devices/alarm-system` returns data).

- **States**: `disarmed`, `armed_home`, `armed_away`, `triggered`
- **Extra attributes**: input list formatted as `{class}/{id}`
- **Code required**: depends on hub configuration

---

## Camera

IP and ONVIF cameras configured in Sinum are exposed as HA camera entities. Snapshots are fetched through the hub's proxy endpoint `/api/v1/devices/video/{id}/snapshot`.

- **Live streaming**: not available — RTSP passwords are masked by the hub API. For streaming, use HA's Generic Camera integration with direct RTSP credentials.
- **Status**: `is_on = True` when camera status is `"online"`
- **Extra attributes**: `video_type`, `ip`, `port`, `url_path`, `mac`, `status`, `purpose`, `room_id`

---

## Device Availability

All Sinum entities use `available = bool(self._device)`. When the hub is unreachable and the coordinator falls back to cache, all entities remain available with stale state. If the cache is empty (fresh HA restart with hub down), entities show `unavailable`.

When a device is permanently removed from the hub, HA entities for that device are automatically removed from the entity registry on the next successful coordinator refresh. This prevents stale entries from accumulating.
