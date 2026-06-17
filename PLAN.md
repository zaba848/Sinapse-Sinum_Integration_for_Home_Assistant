# Sinapse — Implementation Plan

> Roadmap for the Sinum EH-01 Home Assistant integration.  
> Last updated: 2026-06-17, verified against two live hubs (firmware `1.24.0-alpha.2`, API `1.4`).  
> Credentials and API tokens must never be committed to this repository.

---

## Current Reality

```text
Home Assistant
  └─ custom_components/sinum
       ├─ REST discovery and polling
       ├─ optional MQTT push bridge from Lua
       └─ optional Lua HTTP extension for extra hub diagnostics

Sinum EH-01 hub
  ├─ /api/v1/info
  ├─ /api/v1/rooms, /api/v1/floors
  ├─ /api/v1/devices/virtual
  ├─ /api/v1/devices/wtp
  ├─ /api/v1/devices/sbus
  ├─ /api/v1/parent-devices
  ├─ /api/v1/schedules
  ├─ /api/v1/scenes
  └─ Lua API v1.24.0: HTTP server, MQTT client, statistics, Energy Center, buses
```

---

## Live Hub Inventory

Two hubs verified continuously. Hub 2 is the active HA instance.

### Hub 1 — `tablica-wtp` (10.0.61.132) — sinum_plus

Heavy WTP installation: 28 virtual, 254 WTP, 8 SBUS, 34 rooms.

| Bus | Type | Count | HA status |
|---|---|---:|---|
| WTP | `relay` | 108 | ✅ switch |
| WTP | `temperature_sensor` | 26 | ✅ sensor (temp + humidity) |
| WTP | `humidity_sensor` | 21 | ✅ sensor |
| WTP | `blind_controller` | 18 | ✅ cover |
| WTP | `temperature_regulator` | 15 | ✅ climate |
| WTP | `button` | 28 | ❌ not yet |
| WTP | `two_state_input_sensor` | 8 | ✅ binary_sensor |
| WTP | `light_sensor` | 6 | ✅ sensor (illuminance) |
| WTP | `iaq_sensor` | 5 | ✅ sensor (iaq + air_quality) |
| WTP | `pressure_sensor` | 5 | ✅ sensor |
| WTP | `co2_sensor` | 3 | ✅ sensor |
| WTP | `flood_sensor` | 2 | ✅ binary_sensor |
| WTP | `motion_sensor` | 2 | ✅ binary_sensor |
| WTP | `aq_sensor` | 2 | ✅ sensor (PM1/2.5/4/10 + air_quality) |
| WTP | `energy_meter` | 1 | ✅ sensor (power, voltage, current, energy) |
| WTP | `fan_coil` | 1 | ✅ climate |
| WTP | `fan_coil_v2` | 1 | ✅ climate |
| WTP | `dimmer` | 1 | ✅ light |
| WTP | `rgb_controller` | 1 | ✅ light |
| SBUS | `relay` | 2 | ✅ switch |
| SBUS | `temperature_sensor` | 2 | ✅ sensor |
| SBUS | `humidity_sensor` | 1 | ✅ sensor |
| SBUS | `temperature_regulator` | 1 | ✅ climate + sensor |
| SBUS | `button` | 2 | ❌ not yet |
| Virtual | `thermostat` (various) | ~20 | ✅ climate |
| Virtual | `relay_integrator` | present | ✅ switch |

### Hub 2 — `sinum-tablica-sbus-1` (10.0.62.167) — sinum_lite — **active in HA**

Heavy SBUS installation: 169 virtual, 35 WTP, 436 SBUS, 60 rooms.

| Bus | Type | Count | HA status |
|---|---|---:|---|
| SBUS | `temperature_sensor` | 134 | ✅ sensor |
| SBUS | `relay` | 69 | ✅ switch |
| SBUS | `temperature_regulator` | 51 | ✅ climate + sensor |
| SBUS | `humidity_sensor` | 46 | ✅ sensor |
| SBUS | `dimmer` | 38 | ✅ light |
| SBUS | `two_state_input_sensor` | 35 | ✅ binary_sensor |
| SBUS | `button` | 30 | ❌ not yet |
| SBUS | `analog_input` | 10 | ✅ sensor |
| SBUS | `rgb_controller` | 6 | ✅ light |
| SBUS | `impulse_meter` | 4 | ✅ sensor |
| SBUS | `analog_output` | 3 | ❌ not yet |
| SBUS | `motion_sensor` | 2 | ✅ binary_sensor |
| SBUS | `light_sensor` | 2 | ✅ sensor |
| SBUS | `pulse_width_modulation` | 2 | ❌ not yet |
| SBUS | `common_valve` | 2 | ❌ not yet |
| SBUS | `valve_pump` | 2 | ❌ not yet |
| WTP | `relay` | 11 | ✅ switch |
| WTP | `temperature_sensor` | 9 | ✅ sensor |
| WTP | `button` | 5 | ❌ not yet |
| WTP | `motion_sensor` | 3 | ✅ binary_sensor |
| WTP | `light_sensor` | 3 | ✅ sensor |
| WTP | `temperature_regulator` | 2 | ✅ climate |
| WTP | `humidity_sensor` | 2 | ✅ sensor |
| Virtual | `thermostat` | 83 | ✅ climate |
| Virtual | `relay_integrator` | 5 | ✅ switch |
| Virtual | `blind_controller_integrator` | 3 | ✅ cover |
| Virtual | `gate` | 2 | ✅ cover |
| Virtual | `dimmer_rgb_integrator` | 1 | ✅ light |
| Virtual | `thermostat_output_group` | 9 | ➖ no entity (group metadata) |
| Virtual | `heat_pump_manager` | 1 | ❌ not yet |
| Virtual | `custom_device` | 65 | ➖ intentionally skipped |

**HA entity counts (Hub 2 live)**: 136 climate · 468 sensor · 287 binary_sensor · 85 switch · 45 light · 5 cover · 38 button · 128 update · 3 alarm_control_panel

---

## Completed Phases

| Phase | Summary | Status |
|---|---|---|
| 1–6 | Core REST client, coordinator, config flow, virtual devices | ✅ Done |
| 7A | WTP fan_coil + fan_coil_v2 climate entities with fan modes | ✅ Done |
| 7B | Temperature regulator sensors + climate (WTP + SBUS) | ✅ Done |
| 7C | Thermal schedule sensors (target temp, active period, fallback, associations) | ✅ Done |
| 7D | MQTT bridge hardening (lua v0.7+, schema validation, heartbeat) | ✅ Done |
| 7E | Quality gate: 75→131 tests, translations, alarm panel, parent connectivity | ✅ Done |
| 8 | WTP/SBUS physical relay → switch; WTP blind_controller → cover | ✅ Done |
| 9 | SBUS/WTP dimmer → light; SBUS/WTP RGB controller → light; virtual dimmer_rgb_integrator | ✅ Done |
| 10 | SBUS motion sensor; SBUS illuminance/analog_input/impulse_meter sensors | ✅ Done |
| 11 | Sensor bug fixes: flood state_key, aq PM keys, iaq sensor, energy_meter fields | ✅ Done |

---

## Remaining Work

### Next — Button last_action sensor

Both hubs have significant button counts (33 WTP + 32 SBUS across both hubs). The `action` field holds the last button event as a string.

Options:
- `sensor` with state = last action string (simplest)
- HA `event` entity (preferred for automations — fires on MQTT update)

Fields available on button devices: `action` (string), `buttons_count` (int).  
Recommend starting with `sensor` platform (state = `action`), upgradeable to `event` later.

### SBUS analog_output

3 devices on Hub 2. Fields: `value` (0–10000 mV), `raw_value` (0–65535), `unit`, `value_minimum`, `value_maximum`.

Options:
- `sensor` showing current value (read-only)
- `number` entity for writable control (PATCH `{"value": N}`)

Prefer `number` for controllable outputs. Needs API write verification.

### SBUS valve_pump / common_valve

2+2 devices on Hub 2. `valve_pump` has `state` (bool) and temperature thresholds. `common_valve` has `enabled` (bool) and calibration settings.

- `valve_pump` → `switch` (state on/off + temperature thresholds as attributes)
- `common_valve` → `switch` (enabled on/off + attributes) or `climate` if useful

### SBUS pulse_width_modulation

2 devices on Hub 2. Fields: `duty_cycle`, `frequency`. Read-only diagnostic sensors for now.

### Virtual heat_pump_manager

1 device on Hub 2. Complex type — requires field analysis before implementing.

---

## Working Rules

- Do not commit secrets, tokens, hub credentials, or raw diagnostic payloads.
- Treat writes to fan coils, scenes, alarms, gates, and doors as potentially destructive.
- Prefer read-only discovery first, then test write payloads on non-critical devices.
- Keep REST polling as the baseline; MQTT is an optimization, not a dependency.
- All new device types must have at least a fixture + 1 unit test before merging.
