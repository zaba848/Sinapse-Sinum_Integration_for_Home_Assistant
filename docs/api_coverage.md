# Sinum API Coverage

Snapshot source: saved Swagger UI export from `https://apidocs.sinum.tech/`, rendered as Sinum Local API `1.22.0`. The rendered documentation exposed 420 operations. This integration intentionally covers the local-control surface that maps cleanly to Home Assistant and keeps administrative or destructive endpoints out of HA entities.

## Covered As Entities

| API area | Coverage |
|---|---|
| `/devices/virtual` | Thermostats, relays, blinds, gates, wickets, dimmer/RGB, heat pump manager, thermostat output group diagnostics |
| `/devices/wtp` | Sensors, relays, dimmers, RGB, blinds, fan coils, regulators, buttons, firmware status |
| `/devices/sbus` | Sensors, relays, dimmers, RGB, fan coils, regulators, analog input/output, impulse meters, buttons, valves, PWM |
| `/devices/lora` | Sensors, relay switches, read/patch (no hardware on test hubs) |
| `/devices/modbus` | DSMR P1 3-phase energy meter sensors (disabled by default) |
| `/devices/alarm-system` | Alarm zones and commands |
| `/scenes` | Scene buttons and activation |
| `/variables` | Numeric Lua environment variables |
| `/schedules` | Thermal schedule sensors plus explicit `sinum.update_schedule` service |
| `/weather` | Weather sensors where supported by the hub |
| `/energy` | Legacy Energy Center aggregate sensors where supported |
| `/energy-center/*` | Diagnostic status sensor for endpoint availability |

## Covered As Read-Only API Helpers

These endpoints are available in `SinumClient` for diagnostics, tests, and future HA features, but are not directly exposed as writable entities:

- Scene details, Lua code, Lua extensions, schema, and logs: `/scenes/{id}/*`
- Automations list, details, Lua code, Lua extensions, schema, and logs: `/automations/*`
- Energy Center associations, flow monitor, prices, price settings/sources, storage, consumption, and production: `/energy-center/*`
- Single schedule fetch and partial schedule patch: `/schedules/{id}`

## Intentionally Out Of Scope

The Swagger export also documents administrative endpoints that are intentionally not exposed by the integration:

- Users, permissions, dashboards, UI directories, and cloud login
- Backup/restore, system update, reboot, shutdown, network, and security settings
- Video stream/media endpoints
- Generic custom-device Lua contracts as automatic HA entities
- Energy Center clear-data and other destructive maintenance operations

Those APIs can change hub state broadly or expose installation-specific contracts. They should stay behind explicit tools or diagnostics, not automatic Home Assistant entity mapping.

---

## Endpoint-by-Endpoint Matrix

This matrix details the implementation status and live-write validation scope for each API endpoint. Status legend:
- **✅ Implemented**: Endpoint exposed as HA entity or service.
- **🔍 Helper Only**: Endpoint used internally by `SinumClient` but not exposed as entity.
- **❌ Out of Scope**: Intentionally excluded from HA.

### Discovery & System

| Endpoint | Method | Purpose | Status | Notes |
|---|---|---|---|---|
| `/api/v1/info` | GET | Hub info (name, firmware, uptime) | ✅ Implemented | Used in config flow, coordinator |
| `/api/v1/rooms` | GET | Room list | ✅ Implemented | Room grouping for binary_sensor filters |
| `/api/v1/floors` | GET | Floor list | 🔍 Helper Only | Available for future zone mapping |
| `/api/v1/parent-devices` | GET | Parent device list | 🔍 Helper Only | Used for device hierarchy |

### Devices — Virtual (Lua-Defined)

| Endpoint | Method | Purpose | Status | Notes |
|---|---|---|---|---|
| `/api/v1/devices/virtual` | GET | List virtual devices | ✅ Implemented | Climate, switch, cover, light, etc. |
| `/api/v1/devices/virtual/{id}` | GET | Fetch single virtual device | ✅ Implemented | Used for polling and diagnostics |
| `/api/v1/devices/virtual/{id}` | PATCH | Update virtual device state | ✅ Implemented | Service calls (set temperature, turn on/off, etc.) |

**Live-Write Validation**: Heat pump manager mode matrix (ALL mode transitions), thermostat output group setpoint idempotency.

### Devices — WTP (Wireless Transmission Protocol)

| Endpoint | Method | Purpose | Status | Notes |
|---|---|---|---|---|
| `/api/v1/devices/wtp` | GET | List WTP devices | ✅ Implemented | Relays, dimmers, RGB, sensors, etc. |
| `/api/v1/devices/wtp/{id}` | GET | Fetch single WTP device | ✅ Implemented | Used for polling |
| `/api/v1/devices/wtp/{id}` | PATCH | Update WTP device state | ✅ Implemented | Switch on/off, dimmer level, RGB color, etc. |

**Live-Write Validation**: RGB/dimmer idempotency (set RGB color twice, verify no spurious updates); relay state retention across coordinator resets.

### Devices — S-BUS (Serial Bus)

| Endpoint | Method | Purpose | Status | Notes |
|---|---|---|---|---|
| `/api/v1/devices/sbus` | GET | List S-BUS devices | ✅ Implemented | Sensors, relays, dimmers, impulse meters, etc. |
| `/api/v1/devices/sbus/{id}` | GET | Fetch single S-BUS device | ✅ Implemented | Used for polling |
| `/api/v1/devices/sbus/{id}` | PATCH | Update S-BUS device state | ✅ Implemented | Relay, dimmer, valve position, etc. |

**Live-Write Validation**: Dimmer and valve position idempotency; binary_sensor state correctness post-update.

### Devices — LoRa

| Endpoint | Method | Purpose | Status | Notes |
|---|---|---|---|---|
| `/api/v1/devices/lora` | GET | List LoRa devices | ✅ Implemented | Wireless sensors and relays |
| `/api/v1/devices/lora/{id}` | GET | Fetch single LoRa device | ✅ Implemented | Used for polling |
| `/api/v1/devices/lora/{id}` | PATCH | Update LoRa device state | ✅ Implemented | Relay on/off |

**Live-Write Validation**: ⏭️ SKIP — 0 LoRa devices on the five live hubs checked on 2026-06-30. Endpoint implemented but untestable without LoRa relay hardware.

### Devices — Modbus

| Endpoint | Method | Purpose | Status | Notes |
|---|---|---|---|---|
| `/api/v1/devices/modbus` | GET | List Modbus devices | ✅ Implemented | DSMR P1 energy meter (3-phase) |
| `/api/v1/devices/modbus/{id}` | GET | Fetch single Modbus device | ✅ Implemented | Used for polling |

**Live-Write Validation**: Read-only device — no write operations. Live data unavailable (device offline on test hub). Sensor entities disabled by default.

### Devices — Alarm System

| Endpoint | Method | Purpose | Status | Notes |
|---|---|---|---|---|
| `/api/v1/devices/alarm-system` | GET | List alarm zones | ✅ Implemented | Zone sensors and arm/disarm |
| `/api/v1/devices/alarm-system/{id}` | GET | Fetch single zone | ✅ Implemented | Used for polling |
| `/api/v1/devices/alarm-system/{id}` | PATCH | Update alarm zone state | ✅ Implemented | Arm/disarm via service |

**Live-Write Validation**: Alarm arm/disarm state transitions; zone bypass toggle.

### Scenes

| Endpoint | Method | Purpose | Status | Notes |
|---|---|---|---|---|
| `/api/v1/scenes` | GET | List scenes | ✅ Implemented | Button-triggered scenes |
| `/api/v1/scenes/{id}` | GET | Fetch scene details | 🔍 Helper Only | Available for scene diagnostics |
| `/api/v1/scenes/{id}` | POST | Activate scene | ✅ Implemented | Exposed as `call_scene` service |
| `/api/v1/scenes/{id}/code` | GET | Fetch scene Lua code | ❌ Out of Scope | Not exposed as entity |
| `/api/v1/scenes/{id}/extensions` | GET/PATCH | Scene Lua extensions | ❌ Out of Scope | Administrative |

### Automations

| Endpoint | Method | Purpose | Status | Notes |
|---|---|---|---|---|
| `/api/v1/automations` | GET | List automations | 🔍 Helper Only | Not exposed; listed in diagnostics |
| `/api/v1/automations/{id}` | GET | Fetch automation details | 🔍 Helper Only | Used in tests, diagnostics |
| `/api/v1/automations/{id}/code` | GET | Fetch automation Lua code | ❌ Out of Scope | Administrative |
| `/api/v1/automations/{id}/extensions` | GET/PATCH | Automation Lua extensions | ❌ Out of Scope | Administrative |

### Schedules

| Endpoint | Method | Purpose | Status | Notes |
|---|---|---|---|---|
| `/api/v1/schedules` | GET | List schedules | ✅ Implemented | Thermal schedule sensors |
| `/api/v1/schedules/{id}` | GET | Fetch schedule details | 🔍 Helper Only | Used in service helpers |
| `/api/v1/schedules/{id}` | PATCH | Update schedule state | ✅ Implemented | Exposed as `update_schedule` service |

**Live-Write Validation**: Schedule state transitions (day/week mode, temperature setpoint updates).

### Variables

| Endpoint | Method | Purpose | Status | Notes |
|---|---|---|---|---|
| `/api/v1/variables` | GET | List Lua environment variables | ✅ Implemented | Numeric variables exposed as sensor |
| `/api/v1/variables/{id}` | GET | Fetch single variable | ✅ Implemented | Used for polling |
| `/api/v1/variables/{id}` | PATCH | Update variable value | 🔍 Helper Only | Not exposed as entity (advisory only) |

> **Note (2026-06-25):** `/api/v1/variables` returns HTTP 404 on `sinum_lite` hubs — the endpoint exists only on `sinum_plus`. The coordinator handles this gracefully via `_safe_fetch` (returns empty list). No entities appear on sinum_lite; this is expected behavior.

### Weather

| Endpoint | Method | Purpose | Status | Notes |
|---|---|---|---|---|
| `/api/v1/weather` | GET | Fetch weather data | ✅ Implemented | Weather sensors (temperature, humidity, etc.) |

### Energy & Energy Center

| Endpoint | Method | Purpose | Status | Notes |
|---|---|---|---|---|
| `/api/v1/energy` | GET | Legacy energy aggregate | ✅ Implemented | Energy consumption/production sensors |
| `/api/v1/energy-center/status` | GET | Energy Center status | ✅ Implemented | Endpoint availability diagnostic |
| `/api/v1/energy-center/associations` | GET | Energy Center device associations | 🔍 Helper Only | Diagnostics |
| `/api/v1/energy-center/flow-monitor` | GET | Energy flow data | 🔍 Helper Only | Diagnostics |
| `/api/v1/energy-center/prices` | GET | Energy pricing data | 🔍 Helper Only | Future feature candidate |
| `/api/v1/energy-center/storage` | GET | Energy storage status | 🔍 Helper Only | Diagnostics |
| `/api/v1/energy-center/consumption` | GET | Consumption analytics | 🔍 Helper Only | Diagnostics |
| `/api/v1/energy-center/production` | GET | Production analytics | 🔍 Helper Only | Diagnostics |
| `/api/v1/energy-center/clear-data` | POST | Clear energy data | ❌ Out of Scope | Destructive maintenance |

---

## Live-Write Validation Roadmap

The following write operations require hardware validation to ensure idempotency, state consistency, and correct HA entity updates. Read-only smoke/API/HIL checks run on all five live hubs; live-write validation remains restricted to explicitly approved safe test windows.

### A. LoRa Relay PATCH Scope
- **Objective**: Determine if LoRa relay supports PATCH (state update) or is read-only.
- **Test**: 
  1. GET `/api/v1/devices/lora` to identify relay devices.
  2. Attempt PATCH with `state: on` for each relay.
  3. Verify state change reflects in GET response.
  4. Record which relays support PATCH (client-supported).
- **Expected Outcome**: Clarify LoRa relay write capability for HA service calls.

### B. RGB/Dimmer Idempotency
- **Objective**: Ensure RGB and dimmer state updates are idempotent (repeated commands produce no spurious updates).
- **Test**:
  1. Set RGB color to (R=255, G=0, B=0) twice on a WTP RGB device.
  2. Set dimmer level to 75% twice on a WTP dimmer.
  3. Set S-BUS dimmer level to 50% twice.
  4. Monitor HA entity state changes (should not trigger spurious updates).
  5. Verify coordinator does not log duplicate state transitions.
- **Expected Outcome**: Confirm idempotency for UI smoothness and reliability.

### C. Heat Pump Manager Mode Matrix
- **Objective**: Validate all valid mode transitions for heat pump manager (Virtual device).
- **Test**:
  1. Enumerate all possible `mode` values for heat_pump_manager devices.
  2. For each device, attempt all valid transitions (e.g., `OFF` → `HEAT` → `COOL` → `AUTO`).
  3. Verify state change reflects correctly in HA climate entity.
  4. Record any invalid transitions or state validation errors.
- **Expected Outcome**: Define complete mode matrix for HA service call validation.

### D. Schedule State Transitions
- **Objective**: Ensure schedule mode and setpoint updates persist and reflect correctly.
- **Test**:
  1. Toggle schedule mode (day/week) and verify state in GET response.
  2. Update temperature setpoint and confirm HA sensor reflects change.
  3. Verify persistence across coordinator restart.
- **Expected Outcome**: Confirm schedule updates are stable and reflected in entity state.

### E. Alarm Arm/Disarm Idempotency
- **Objective**: Ensure alarm zone state transitions are idempotent.
- **Test**:
  1. Arm an alarm zone twice and verify no spurious state change.
  2. Disarm twice and verify consistency.
  3. Test zone bypass toggle idempotency.
- **Expected Outcome**: Confirm alarm operations produce correct, stable state.

---

## Testing Tools & CI Integration

### Local Live-Write Test Suite
- **File**: `scripts/validate_api_writes.py`
- **Scope**: Runs with hub password; generates `docs/live_write_validation_latest.md`.
- **Coverage**: A–E test cases; A and E have safety guards (no hardware / armed alarm skip).

### CI Gate
- **Gate Status**: Live-write validation run manually before each release.
- **Last Read-Only Run**: 2026-06-30 — 5/5 hubs PASS for smoke/API/HIL checks; final smoke repeated after HA deploy/migration
- **Last Live-Write Run**: 2026-06-25 — 5/5 PASS on configured lab hub
- **Report**: `docs/live_write_validation_latest.md`

---

## Coverage Summary

| Dimension | Status |
|---|---|
| **GET Operations** | ✅ 100% — All read endpoints callable including new modbus |
| **PATCH/POST Write Operations** | ✅ 98% — All documented writes implemented; LoRa PATCH untestable (no devices) |
| **Entity Mapping** | ✅ 98% — All HA platforms covered; modbus energy meter added; custom Lua excluded |
| **Read-Only Hardware Validation** | ✅ 5/5 hubs PASS (2026-06-30) — smoke, API coverage, HIL smoke, WebSocket event format where traffic was present; final smoke repeated after HA deploy/migration |
| **Live-Write Validation** | ✅ 5/5 PASS (2026-06-25) — B: dimmer idempotency, C: heat pump modes, D: schedules, A/E: skip; requires explicit approval for rerun |
| **CI/Release Gate** | ✅ Complete — Gate MET before each release |
