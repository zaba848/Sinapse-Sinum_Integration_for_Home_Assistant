# Sinapse — Implementation Plan & Status

> Last updated: 2026-07-08 (released: v0.8.0, maintenance cycles 0–4 complete)
> Current manifest version: v0.8.0
> Credentials, API tokens, HA tokens and passwords must never be committed.

---

## Verified Local Status

```text
Tests:  1 912 passing, 5 skipped (~12 s)
Coverage: 100% line coverage — all 32 modules
Ruff:   0 errors
mypy:   0 errors (errors in HA library stubs only, not our code)
CC:     <= 4, _LEGACY_ALLOWANCE = {}
# type: ignore: 2 remaining (both HA-stub limitations, not our code)
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

## Remaining Technical Debt (aktualne)

Assessed 2026-07-08 — only open items; resolved issues (climate/light god objects, FAN platform, Energy Center, integration tests, api.py split) moved to Completed Phases.

### High priority

| # | Issue | Files |
|---|---|---|
| 1 | Bus extensibility — new bus still needs platform entity modules, but core routing is centralized | `_bus_registry.py`, platforms |
| 2 | `sensor_modbus.py` further splits | entity vs descriptions (partially done v0.8.1) |
| 3 | VIDEO + SBUS2 hubs offline in lab — HA entries `setup_retry` | hardware smoke |

### Medium priority

| # | Issue | Notes |
|---|---|---|
| 4 | LoRa relay PATCH write untested on physical hardware | code exists |
| 5 | Energy Center PV/grid/battery/daily sensors | needs hub with live PV |
| 6 | Translation inconsistencies | `en.json` vs `strings.json` key drift |
| 7 | `sensor_bus_descriptions.py` size | shared keys across buses |

### Low priority / backlog

| # | Issue |
|---|---|
| 8 | `sensor_virtual.py` (416 lines) — further split candidate |
| 9 | `camera.py` — RTSP/WebRTC/snapshot mixins |
| 10 | `binary_sensor.py` per-bus split |
| 11 | Missing `MEDIA_PLAYER` platform |
| 12 | No third language beyond EN/PL |

---

## Maintenance Cycles

| Cycle | Scope | Status | Date |
|---|---|---|---|
| 0 | PLAN.md rewrite — stale weak points removed, Maintenance Cycles table | ✅ Done | 2026-07-08 |
| 1a | `services.py` extraction from `__init__.py` | ✅ Done | 2026-07-08 |
| 1b | slink WS/MQTT routing + binary_sensor store fallback | ✅ Done | 2026-07-08 |
| 1c | Reconfigure WS path + JWT sanitization gate + coverage gates | ✅ Done | 2026-07-08 |
| 2 | `_bus_registry.py` — replace 6 inline store dicts | ✅ Done | 2026-07-08 |
| 3 | Lifecycle multi-hub tests (7 scenarios) | ✅ Done | 2026-07-08 |
| 4 | Coordinator fetch via `BUS_REGISTRY` loop | ✅ Done | 2026-07-08 |
| HW | Smoke 6 hubs + `validate_api_writes` when lab network available | ⏳ Skipped (no lab env in session) | 2026-07-08 |
| 5+ | Further module splits (`sensor_virtual`, `camera`, `binary_sensor`) | 📋 Backlog | — |

---

## Completed Phases (archive v0.1–v0.8)

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
| v0.7.6 | FAN platform for fan_coil gear control, Energy Center flow/consumption/production sensors, climate/light refactor integration tests, real API field paths for EC sensors | 1 849 |
| v0.7.7 | api.py mixin extraction (SceneMixin/EnergyMixin), sensor_bus DRY, switch base class, cover split, WebRTC extraction, __init__ lifecycle extraction | 1 890 |
| v0.7.8 | sensor_virtual split (EC/hub/virtual), TYPE_CHECKING stubs, MANUFACTURER const, camera DOMAIN, binary_sensor cast | 1 890 |
| v0.7.9 | MI quality pass for API transport/response helpers, RGB light helpers and config flow helpers | 1 890 |
| v0.8.0 | WS log redaction, full platform setup harness, public artifact sanitization gate, release metadata gates | 1 912 |

### Resolved in v0.7.6–v0.8.x (formerly listed as weak points)

| Item | Resolution |
|---|---|
| `climate.py` god object (834 lines) | Split into `climate_fan_coil.py`, `climate_bus.py`, `climate_virtual.py`, `climate_heat_pump.py` |
| `light.py` god object (815 lines) | Split into `light_rgb.py`, `light_dimmer.py`, `light_button.py`, `light_dimmer_bus.py` |
| `api.py` god object (889 lines) | Mixin extraction: `_api_scene.py`, `_api_energy.py`, `_api_helpers.py` |
| `fan_coil` gear / FAN platform | `fan.py` platform + gear binary_sensor attrs |
| Energy center sensors | `sensor_energy_center.py` with flow/consumption/production |
| Integration-test depth | `test_integration.py` + `test_full_platform_setup.py` |
| `__init__.py` 499 lines | Lifecycle → `lifecycle.py`, services → `services.py` (~150 lines orchestration) |
| Bus store dict duplication | `_bus_registry.py` centralizes routing |
| Reconfigure WS path missing | WS path field added to reconfigure flow |
| Coverage gates (9 modules) | Extended to websocket, lifecycle, sensor_modbus, services |

---

## Critical Analysis — Weak Points

> **Removed 2026-07-08.** Stale items (climate/light god objects, missing FAN/EC, no integration tests) described issues fixed in v0.7.6–v0.8.x. See **Remaining Technical Debt** and **Completed Phases** above.

---

## Active Work Plan (ordered by priority)

### Phase A — v0.8.0 release ✅ Done (2026-07-07)

| Item | Status |
|---|---|
| WS log redaction + sanitization gates | ✅ Done |
| Full platform setup harness | ✅ Done |
| Version bump 0.8.0 + docs sync | ✅ Done |
| Deploy v0.8.0 to RPi | ✅ Done (manifest 0.8.0, tar deploy via `HA_HOST=<HA_IP>`) |
| GitHub release v0.8.0 | ⏳ Pending (gh auth / manual UI) |
| Hardware smoke 6/6 hubs | ✅ 4/6 PASS (VIDEO, SBUS2 unreachable) |

### Phase B — Hardware validation (now)

| Item | Hub | Status |
|---|---|---|
| HA RPi online + Energy dashboard | HA | ✅ Online (`/energy/electricity`), 3937 entities |
| Deploy v0.8.0 integration | RPi | ✅ manifest 0.8.0 deployed |
| Sinum config entries in HA | all | ✅ 6 entries (incl. sinum-lora); 4 loaded, 2 setup_retry (VIDEO, SBUS2) |
| Read-only smoke (6 hubs) | all | ✅ 4/6 PASS (WTP, SBUS, KLIMAK, LORA); VIDEO+SBUS2 ERR |
| HIL API coverage + WebSocket | SBUS, VIDEO | ⏳ SBUS ready; VIDEO hub offline |
| Safe write validation | KLIMAK, SBUS | ⏳ |
| LoRa hub → HA config entry | LORA | ✅ Done (`sinum-lora` loaded) |
| VIDEO hub network diagnosis | VIDEO | ⏳ smoke ERR; HA entry `setup_retry` |

### Phase C — Climate refactor ✅ Done (v0.7.6)

### Phase D — Light refactor ✅ Done (v0.7.6)

### Phase E — Energy center sensors ✅ Done (v0.7.6)

Live API schema confirmed 2026-07-02 by querying hubs directly.
Sensors use correct field paths after `_request()` unwraps `data` key:
- `SinumEnergyCenterFlowSensor.native_value` → `summary.building.value` (W, building consumption)
  - `extra_state_attributes`: `pv_power`, `grid_power`, `battery_power`, `battery_soc`
- `SinumEnergyCenterDataSensor` consumption → `total.total_consumption` (Wh, all-time)
  - `extra_state_attributes`: full dict with `today` and `total` breakdown
- `SinumEnergyCenterDataSensor` production → `total.all` (Wh, all-time)
  - `extra_state_attributes`: full dict with `today` and `total` breakdown

Possible Phase E follow-up:
- Add `today.total_consumption` / `today.all` as separate `MEASUREMENT` sensors (daily reset)
- Add `summary.pv.value` (current PV power), `summary.grid.value` (grid import/export) sensors
- Test against a hub with actual PV/battery (current hubs have `available: false` for these)

### Phase F — Integration tests ✅ Done (v0.8.0)

- `tests/test_integration.py` — coordinator → entity value paths
- `tests/test_full_platform_setup.py` — real HA `async_setup_entry` → entity/device registry

### Phase G — api.py mixin extraction ✅ Done (v0.7.7)

Split 889-line `api.py` into focused modules using Python mixin pattern:
- `_api_helpers.py` — `_list_result`, `_dict_list`, `_partition_energy_results` and normalisation helpers (shared)
- `_api_scene.py` — `SceneMixin`: scenes, automations, variables, schedules (38 methods)
- `_api_energy.py` — `EnergyMixin`: weather, energy center, Lua hub info (17 methods)
- `api.py` now: `SinumClient(SceneMixin, EnergyMixin)` — transport + auth only (~430 lines)
- Deferred import pattern for `SinumConnectionError` inside `_api_scene.py::create_scene` and `_api_energy.py::_build_energy_center_summary` to avoid circular imports
- Tests updated: `_dict_list` / `_list_result` now imported from `_api_helpers` not `api`

### Phase H — sensor_bus_descriptions DRY refactor ✅ Done (v0.7.7)

- `_COMMON_SENSOR_KWARGS` tuple: 9 shared sensors (temp, humidity, illuminance, power, voltage, current, energy × 3)
- `_with_source(source)` helper generates typed `SinumSensorDescription` tuples
- `WTP_SENSORS = _with_source("wtp") + (co2, pm*, pressure, iaq, air_quality, room_temperature, dew_point, battery, signal, wtp_regulator sensors)`
- `SBUS_SENSORS = _with_source("sbus") + (analog_value, impulse_*, pwm_*, valve_*)`
- Saved ~90 duplicate lines

### Phase I — switch.py base class extraction ✅ Done (v0.7.7)

- `_SinumVirtualSwitch` base: `SinumDeviceAvailableMixin + CoordinatorEntity + SwitchEntity`
- `SinumRelaySwitch` and `SinumWicketSwitch` now single-method subclasses
- `_patch()` helper on base: calls `patch_virtual_device` and calls `async_write_ha_state`

### Phase J — cover.py split ✅ Done (v0.7.7)

Follows `_climate_helpers.py` pattern:
- `_cover_helpers.py` — `_label`, `_virtual_device_info`, `_apply_restored_position/tilt`, `_restore_cover_from_last_state`, `_compare_target_current`
- `cover_wtp.py` — `SinumWtpBlindCover` (position only, no tilt)
- `cover_sbus.py` — `SinumSbusBlindCover` (position + conditional tilt)
- `cover.py` — thin dispatcher, imports and re-exports all classes, backward-compatible

### Phase K — coordinator.py WebRTC extraction ✅ Done (v0.7.7)

- `_webrtc.py` — `WebRtcSessionManager` class: tracks sessions dict, dispatches ICE/SDP/error events to HA via lazy imports of `WebRTCAnswer/Candidate/Error`, forwards ICE candidates to hub
- `coordinator.py` — `self._webrtc = WebRtcSessionManager(client)`, 6 thin stub methods

### Phase L — __init__.py lifecycle extraction ✅ Done (v0.7.7)

### Phase M — sensor_virtual.py split + weak point sweep ✅ Done (v0.7.8)

- Split `sensor_virtual.py` (808 lines) into three focused modules:
  - `sensor_energy_center.py` (296 lines) — EC status/flow/data/storage sensors
  - `sensor_hub.py` (117 lines) — hub uptime/Wi-Fi/firmware sensors
  - `sensor_virtual.py` (416 lines) — weather/energy/thermostat/automation sensors
- Added `TYPE_CHECKING` stub for `_request` in `SceneMixin` and `EnergyMixin`
- Added `MANUFACTURER = "TECH Sterowniki"` to `const.py`
- All 1912 tests passing, CC ≤ 4

### Phase N — Next code targets (v0.8.x)

| Item | Priority | Notes |
|---|---|---|
| `sensor_modbus.py` split (640 lines) | HIGH | ✅ Done (v0.8.1) — `sensor_modbus_descriptions.py` + 143-line entity module |
| Energy Center PV/grid/battery/daily sensors | MEDIUM | Needs hub with PV hardware |
| LoRa relay PATCH hardware validation | MEDIUM | Code exists, write untested |
| Bus registry pattern (reduce 15-file edits) | MEDIUM | Architectural |
| Reconfigure flow WS path field | LOW | UX gap |
| VIDEO hub network + motion events on live hardware | HIGH | Last smoke gap |

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
- [x] Deploy via `scripts/deploy_rpi.sh` with `HA_HOST` set to the RPi address
- [x] HA restart confirmed (manifest 0.8.0 on RPi)
- [x] 6 Sinum config entries present (incl. sinum-lora)
- [ ] VIDEO + SBUS2 entries reach `loaded` state (requires lab network)
- [ ] LoRa relay PATCH validated on physical hardware
- [ ] LoRa sensors reading live values in HA UI

---

## Known API Limitations

| Device | Bus | Problem |
|---|---|---|
| `rgb_controller` | WTP | color/brightness can be firmware-limited in temperature mode |
| `rgb_controller` | SBUS | uses Lua scene calls — requires persistent scene per device |
| Virtual cover integrators | Virtual | no position feedback when no physical controller linked |
| LoRa relay PATCH | LoRa | implemented but relay test requires physical hardware present |
| Alarm arm/disarm | alarm-system | destructive; requires explicit PIN and owner approval |
| Energy center | all | PV/battery sensors deferred until hub with live PV hardware |
