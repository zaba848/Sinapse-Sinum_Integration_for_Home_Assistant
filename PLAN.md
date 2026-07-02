# Sinapse — Implementation Plan & Status

> Last updated: 2026-07-02 (released: v0.7.5 ✅)
> Current manifest version: v0.7.5 (deployed to RPi pending)
> Credentials, API tokens, HA tokens and passwords must never be committed.

---

## Verified Local Status

```text
Tests:  1 743 passing, 5 skipped (~9 s)
Coverage: 100% line coverage — all 28 modules
Ruff:   0 errors
mypy:   0 errors
CC:     <= 4, _LEGACY_ALLOWANCE = {}
```

Commands verified locally on 2026-07-02:

```bash
python3 -m pytest -q
/opt/homebrew/bin/ruff check custom_components/
/opt/homebrew/bin/ruff format --check custom_components/
/opt/homebrew/bin/mypy custom_components/sinum/ --ignore-missing-imports --no-site-packages
python3 -m pytest -q tests/test_code_quality.py
```

---

## Live Hub Inventory

| Hub | Firmware | Status | Key API inventory |
|---|---|---|---|
| tablica-wtp | 1.24.0-alpha.2 | smoke PASS | 30 virtual, 254 WTP, 8 SBUS, 2 SLINK, 1 alarm |
| sinum-tablica-sbus-1 | 1.24.0-alpha.4 | smoke PASS | 171 virtual, 35 WTP, 436 SBUS, 1 Modbus, 3 alarms |
| tablica-video-nowa | 1.24.0-alpha.4 | smoke PASS | 6 virtual, 21 WTP, 77 SBUS, 1 Modbus, 6 video |
| tablicaKlimak | 1.24.0-alpha.4 | smoke PASS | 13 virtual, 41 WTP, 25 SBUS, 5 Modbus |
| sinum-tablica-sbus2 | 1.24.0-alpha.3 | smoke PASS | 29 virtual, 50 WTP, 191 SBUS, 2 SLINK, 3 Modbus, 16 alarms |
| sinum-lora | 1.24.0-alpha.4 | smoke PASS | 2 LoRa devices (ACW THO: temp + humidity) |

Hardware config must come from environment variables or GitHub secrets, never from source files.

---

## Device Types → HA Platforms

| Type | Bus | HA platform | Notes |
|---|---|---|---|
| `relay` | WTP/SBUS/SLINK | switch | |
| `temperature_sensor` / `humidity_sensor` | all | sensor | |
| `co2_sensor`, `pressure_sensor`, `light_sensor` | WTP/SBUS | sensor | |
| `iaq_sensor`, `aq_sensor`, `air_quality_sensor` | WTP | sensor | validated against live payloads |
| `temperature_regulator` | WTP/SBUS | climate + sensor | |
| `fan_coil` / `fan_coil_v2` | WTP/SBUS | climate | gear_1/2/3 exposed as binary_sensor attrs |
| `blind_controller` | WTP/SBUS | cover | position feedback via WS |
| `dimmer` | WTP/SBUS/virtual | light | brightness |
| `rgb_controller` | WTP/SBUS | light | WTP REST, SBUS Lua path |
| `button` | WTP/SBUS | event + diagnostic sensor | |
| `two_state_input_sensor` | all | binary_sensor | |
| `flood_sensor` / `motion_sensor` / `smoke_sensor` / `opening_sensor` | all | binary_sensor | |
| `energy_meter` | WTP/SBUS/SLINK | sensor | power/voltage/current/energy |
| `analog_input` | SBUS | sensor | dynamic unit |
| `impulse_meter` | SBUS | sensor | total/window count + value |
| `analog_output` / `pulse_width_modulation` | SBUS | number | |
| `common_valve` / `valve_pump` | SBUS | switch/binary_sensor | |
| `heat_pump` / `inverter` / `battery` / `car_charger` / `common_dhw_main` | Modbus | sensor/switch | |
| `ip_camera` / `onvif_camera` | Video | camera | snapshot + WebRTC + RTSP |
| `thermostat` / `heat_pump_manager` / `dimmer_rgb_integrator` | Virtual | climate/light | |
| Alarm zones | alarm-system | alarm_control_panel | ARM_HOME/AWAY/NIGHT, bypass |
| Schedules | schedules | sensor + service | target temp, fallback, active period |
| Parent devices | parent-devices | binary_sensor + update | online/problem/firmware |

---

## Completed Phases

| Version | Summary | Tests |
|---|---|---|
| v0.1–v0.4 | Core REST, coordinator, config flow, WTP/SBUS/virtual platforms | – |
| v0.5.0–v0.5.7 | WS transport, CC gate, stale cleanup, PL docs, MQTT bridge | 1 498 |
| v0.5.8–v0.5.10 | temperature-zero fix, camera snapshot/WebRTC, run_scene, notify | 1 546 |
| v0.5.13–v0.5.16 | WebRTC trickle ICE, SLINK, Modbus device families | 1 616 |
| v0.5.17–v0.5.19 | multi-hub device name prefixes and entity-id collision fixes | 1 616 |
| v0.5.20 | api.py/coordinator.py/websocket.py coverage sweep | 1 648 |
| v0.6.0 | WS hardening (exponential backoff), WS default enabled | 1 648 |
| v0.7.0 | Camera motion events, SBUS blind position WS, alarm ARM_HOME/NIGHT, bypass, scene triggers | 1 671 |
| v0.7.1 | Camera RTSP polling, RTSP URL cache, IP sanitisation | 1 675 |
| v0.7.2 | Hub firmware version sensor, Sinapse title in UI | 1 678 |
| v0.7.3 | LoRa EUI as serial_number + software_version in device registry | 1 682 |
| v0.7.4 | Hub name prefix only in multi-hub setups | 1 689 |
| v0.7.5 | Delete dead scene.py, 100% line coverage all 28 modules, LoRa smoke check verified | 1 743 |

---

## Critical Analysis — Weak Points

Assessed 2026-07-02 via radon MI, CC, dependency mapping.

### 🔴 High priority (technical debt / architectural risk)

| # | File | Issue | Metric |
|---|---|---|---|
| 1 | `api.py` | God Object — 107 methods, 28 never called by integration (only in tests). ISP/SRP violated. | MI=C (7.47) |
| 2 | `climate.py` | 834 lines, 3 device types (fan_coil, fan_coil_v2, temperature_regulator), each with different control path | MI=C (0.00) |
| 3 | `light.py` | 815 lines, 4 pathways (WTP-rgb REST, SBUS-rgb Lua, dimmer, PWM) mixed in one class hierarchy | MI=C (0.00) |
| 4 | Bus extensibility | Adding a new bus requires edits in 15 files (coordinator + all 7 platform files). OCP violated systemically. | – |

### 🟡 Medium priority (quality / missing features)

| # | Issue | Notes |
|---|---|---|
| 5 | `sensor_bus_descriptions.py` 512 lines | 43 descriptions across WTP/SBUS/LoRa with shared keys — copy-paste between buses |
| 6 | No integration tests | All 1743 tests are unit tests with mocked coordinator; no full `async_setup_entry → entity.native_value` cycle tested |
| 7 | Translation inconsistencies | `title` missing in `en.json`; 10 keys in `en.json` absent from `strings.json` |
| 8 | `fan_coil` gear control | Gears exposed only as binary_sensor attrs; no `FAN` platform or `SELECT` for preset modes |
| 9 | Energy center data | 8 API methods (`get_energy_center_*`) available but never exposed as HA sensors |
| 10 | options flow missing WS path in reconfigure | WS path changeable in options but not in reconfigure step |

### 🟢 Low priority (cosmetic / backlog)

| # | Issue |
|---|---|
| 11 | `__init__.py` 499 lines — service registration + orchestration mixed |
| 12 | `via_device_for`, `hub_prefixed_name` are global functions, not coordinator methods |
| 13 | Missing `MEDIA_PLAYER` / `SELECT` / `FAN` platforms for fan_coil |
| 14 | No third language beyond EN/PL |

---

## Active Work Plan (ordered by priority)

### Phase A — Immediate housekeeping (now)

| Item | Status |
|---|---|
| Deploy v0.7.5 to RPi | ✅ Done |
| Create GitHub release v0.7.5 | ✅ Done |
| Fix translation inconsistencies | ✅ Done |
| Update smoke check LoRa parser (flat list response) | ✅ Done (8a17b0c) |

### Phase B — Climate refactor (next)

Split `climate.py` (834 lines, MI=C) into:
- `climate_bus.py` — `SinumFanCoil` (WTP/SBUS fan_coil, fan_coil_v2)
- `climate_virtual.py` — `SinumThermostat` (virtual thermostat, heat_pump_manager)
- `climate.py` — thin dispatcher calling `async_setup_entry` for each sub-module

Benefits: each module ≤ 350 lines, isolated test surface, MI grade improves from C → A.
Risk: medium — requires careful refactor to not break existing tests.
Tests: all existing climate tests must still pass; add 3 integration-style tests for sub-module setup.

### Phase C — Light refactor (after B)

Split `light.py` (815 lines, MI=C) into:
- `light_rgb.py` — `SinumWtpRgbLight` + `SinumBusRgbLight` (Lua-based)
- `light_dimmer.py` — `SinumDimmer` + `SinumPwm`
- `light.py` — thin dispatcher

Benefits: each module ≤ 300 lines. WTP vs SBUS rgb control paths clearly separated.
Risk: medium — Lua scene management currently in `light.py`; move cleanly.

### Phase D — FAN platform for fan_coil gear control

Add `Platform.FAN` to PLATFORMS:
- `SinumFanCoilFan` entity: `fan_mode` = `gear_1`/`gear_2`/`gear_3`/`off`
- Maps to `SET_FAN_MODE` WTP command
- Gear states already visible as binary_sensor attrs — this promotes them to first-class HA entities

### Phase E — Energy center sensors

API already has `get_energy_center_summary`, `get_energy_center_consumption`, `get_energy_center_production`.
Add `SinumEnergyCenter*` sensor group to `sensor_virtual.py` or new `sensor_energy.py`:
- Production (kW, kWh today/total)
- Consumption (kW, kWh today/total)
- Grid flow direction

### Phase F — Integration tests

Add `tests/test_integration.py` with real HA config-entry fixtures (using homeassistant-test-components):
- Full `async_setup_entry` → coordinator `_fetch_all` → platform setup → entity attributes
- No real hub needed — mock at HTTP level via `aioresponses`

### Phase G — api.py ISP facade (long-term)

Introduce thin facades keeping backwards compat:
- `SinumDeviceClient` — get/patch per bus
- `SinumSceneClient` — scene/lua management
- `SinumEnergyClient` — energy center
- `SinumClient` remains as aggregate facade

---

## Working Rules

- Never commit credentials, tokens or HA access tokens.
- Treat writes to fan coils, scenes, alarms, gates, covers and relays as potentially destructive.
- New device types require fixture data and at least one focused test before merge.
- `ruff check`, `ruff format --check`, `mypy`, full pytest and CC gate must pass before release.
- CC <= 4, `_LEGACY_ALLOWANCE = {}`; no new exceptions.
- Every new branch of integration code must be covered by tests.
- Deploy via `scripts/deploy_rpi.sh` with `SINUM_SSH_PASS` env var — never hardcode password in commands.

---

## Release & Quality Gates

Before every merge to `main`:

- [ ] `python3 -m pytest -q` — all tests pass
- [ ] `ruff check custom_components/` — 0 violations
- [ ] `ruff format --check custom_components/` — no formatting needed
- [ ] `mypy custom_components/sinum/ --ignore-missing-imports` — 0 errors
- [ ] `python3 -m pytest -q tests/test_code_quality.py` — CC ≤ 4

Deploy checklist:
- [ ] `bash scripts/deploy_rpi.sh` with `SINUM_SSH_PASS` and `HA_TOKEN` set
- [ ] HA restart confirmed (HTTP 200 from restart service)
- [ ] Entity count verified via HA REST API
- [ ] LoRa sensors reading live values

---

## Known API Limitations

| Device | Bus | Problem |
|---|---|---|
| `rgb_controller` | WTP | color/brightness can be firmware-limited in temperature mode |
| `rgb_controller` | SBUS | uses Lua scene calls — requires persistent scene per device |
| Virtual cover integrators | Virtual | no position feedback when no physical controller linked |
| LoRa relay PATCH | LoRa | implemented but relay test requires physical hardware present |
| Alarm arm/disarm | alarm-system | destructive; requires explicit PIN and owner approval |
| Energy center | all | API implemented, not yet exposed in HA |
