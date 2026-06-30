# Sinapse - Implementation Plan & Status

> Last updated: 2026-07-01 (released: v0.6.0 ✅)
> Current manifest version: v0.6.0 (production)
> Credentials, API tokens, HA tokens and passwords must never be committed.

---

## Verified Local Status

```text
Tests:  1 648 passing, 5 skipped (~10 s)
Ruff:   0 errors
mypy:   0 errors
CC:     <= 4, _LEGACY_ALLOWANCE = {}
Working tree before implementation: clean
```

Commands verified locally on 2026-06-30:

```bash
python3 -m pytest -q
/opt/homebrew/bin/ruff check custom_components/
/opt/homebrew/bin/ruff format --check custom_components/
/opt/homebrew/bin/mypy custom_components/sinum/ --ignore-missing-imports --no-site-packages
.venv/bin/python -m pytest -q tests/test_code_quality.py
```

---

## Live Hub Inventory

| Hub | Firmware | Status | Key API inventory |
|---|---|---|---|
| tablica-wtp | 1.24.0-alpha.2 | smoke/API/HIL PASS | 30 virtual, 254 WTP, 8 SBUS, 2 SLINK, 1 alarm |
| sinum-tablica-sbus-1 | 1.24.0-alpha.4 | smoke/API/HIL/WS PASS | 171 virtual, 35 WTP, 436 SBUS, 1 Modbus, 3 alarms |
| tablica-video-nowa | 1.24.0-alpha.4 | smoke/API/HIL PASS, snapshot PASS | 6 virtual, 21 WTP, 77 SBUS, 1 Modbus, 6 video |
| tablicaKlimak | 1.24.0-alpha.4 | smoke/API/HIL/WS PASS | 13 virtual, 41 WTP, 25 SBUS, 5 Modbus |
| sinum-tablica-sbus2 | 1.24.0-alpha.3 | smoke/API/HIL/WS PASS | 29 virtual, 50 WTP, 191 SBUS, 2 SLINK, 3 Modbus, 16 alarms |

Hardware config must come from environment variables or GitHub secrets, never from source files.

Recommended local smoke configuration:

```bash
export SINUM_SMOKE_HUBS="WTP=http://10.0.61.132,SBUS=http://10.0.62.167,VIDEO=http://10.0.62.117"
export SINUM_USERNAME="admin"
export SINUM_PASSWORD="<hub-password>"
python3 scripts/hardware_smoke_check.py
```

If a hub uses a static token:

```bash
export SINUM_SBUS_TOKEN="<api-token>"
```

---

## Device Types -> HA Platforms

| Type | Bus | HA platform | Notes |
|---|---|---|---|
| `relay` | WTP/SBUS/SLINK | switch | |
| `temperature_sensor` / `humidity_sensor` | all | sensor | |
| `co2_sensor`, `pressure_sensor`, `light_sensor` | WTP/SBUS | sensor | implemented |
| `iaq_sensor`, `aq_sensor`, `air_quality_sensor` | WTP | sensor | descriptors and unit tests exist; needs live payload validation |
| `temperature_regulator` | WTP/SBUS | climate + sensor | |
| `fan_coil` / `fan_coil_v2` | WTP/SBUS | climate | |
| `blind_controller` | WTP/SBUS | cover | |
| `dimmer` | WTP/SBUS/virtual | light | brightness |
| `rgb_controller` | WTP/SBUS | light | WTP REST limitations, SBUS Lua path |
| `button` | WTP/SBUS | event + diagnostic sensor | |
| `two_state_input_sensor` | all | binary_sensor | |
| `flood_sensor` / `motion_sensor` / `smoke_sensor` / `opening_sensor` | all | binary_sensor | |
| `energy_meter` | WTP/SBUS/SLINK | sensor | power/voltage/current/energy |
| `analog_input` | SBUS | sensor | dynamic unit |
| `impulse_meter` | SBUS | sensor | total/window count + value |
| `analog_output` / `pulse_width_modulation` | SBUS | number | |
| `common_valve` / `valve_pump` | SBUS | switch/binary_sensor | |
| `heat_pump` / `inverter` / `battery` / `car_charger` / `common_dhw_main` | Modbus | sensor/switch | disabled by default where appropriate |
| `ip_camera` / `onvif_camera` | Video | camera | snapshot + WebRTC |
| `thermostat` / `heat_pump_manager` / `dimmer_rgb_integrator` | Virtual | climate/light | |
| Alarm zones | alarm-system | alarm_control_panel | write tests require explicit PIN |
| Schedules | schedules | sensor + service | target temp, fallback, active period |
| Parent devices | parent-devices | binary_sensor + update | online/problem/firmware |

---

## Completed Phases

| Version | Summary | Tests |
|---|---|---|
| v0.1-v0.4 | Core REST, coordinator, config flow, WTP/SBUS/virtual platforms | - |
| v0.5.0-v0.5.7 | WS transport, CC gate, stale cleanup, PL docs, MQTT bridge | 1 498 |
| v0.5.8-v0.5.10 | temperature-zero fix, camera snapshot/WebRTC, run_scene, notify | 1 546 |
| v0.5.13-v0.5.16 | WebRTC trickle ICE, SLINK, Modbus device families | 1 616 |
| v0.5.17-v0.5.19 | multi-hub device name prefixes and entity-id collision fixes | 1 616 |
| v0.5.20 | api.py/coordinator.py/websocket.py coverage sweep | 1 648 |
| v0.6.0 | WS hardening (exponential backoff), WS default enabled, README IP removal | 1 648 |

---

## Implementation Plan

### P0 - Security and release hygiene

| Item | Status | Notes |
|---|---|---|
| Remove committed hub passwords/tokens from docs and scripts | Done | replaced with env vars and placeholders |
| Make `scripts/hardware_smoke_check.py` env/CLI driven | Done | no hardcoded password |
| Fix `scripts/validate_api_writes.py` alarm command payload | Done | alarm writes gated by `SINUM_ALARM_TEST_PIN` |
| Align stale HIL write test with current `SinumClient` method names | Done | destructive tests remain gated by env |

### P1 - Hardware validation path

| Item | Status | Notes |
|---|---|---|
| Replace mocked hardware-nightly workflow with real smoke runner | Done | runs on LAN/self-hosted runner with secrets |
| Run read-only smoke on known hubs | Done | 5/5 PASS on 2026-06-30 |
| Run API coverage HIL on known hubs | Done | 5/5 PASS, no critical failures |
| Run HIL smoke and camera snapshot | Done | 5/5 PASS; video snapshot device 27 returned 200 |
| Run WebSocket event-format HIL where traffic exists | Done | 4/4 non-video hubs PASS |
| Run live-write validation only where safe | In Progress | writes dimmers/schedules/heat-pump manager; alarm requires `SINUM_ALARM_TEST_PIN` |
| Document latest hardware result | Done | final post-deploy smoke 5/5 PASS; `docs/hardware_smoke_latest.md`, `docs/hardware_inventory_latest.md` |

### P2 - Multi-hub deploy and registry cleanup

| Item | Status | Notes |
|---|---|---|
| Check HA/RPi installed version and registry | Done | before deploy: 5 Sinum config entries, installed version 0.5.18, 4 123 live Sinum registry entries, 582 suffix entries |
| Deploy latest integration to RPi | Done | v0.5.21 installed to `/config/custom_components/sinum`; previous directory and registry backed up under `/config/backups/sinum` |
| Run entity registry migration | Done | HA WebSocket registry migration removed 322 stale collision entries; remaining migration candidates: 0 |
| Verify live entity names after restart | Done | HA API up on 2026.6.4; 5 Sinum config entries; live/file registry: 3 801 Sinum entries, 260 suffix entries, 0 removable collisions |
| Inventory `ehome-wojtek` and `sinum-tablica-sbus2` | Done | credentials label `ehome-wojtek` resolves via API as `tablicaKlimak` at 10.0.61.114 |

### P3 - Documentation and metadata

| Item | Status | Notes |
|---|---|---|
| Update README/README.pl test counts, version, hub count | Done | refreshed for v0.5.21 / 1 648 passing tests |
| Update docs/development test counts and HIL instructions | Done | HIL scripts documented as standalone scripts |
| Align `pyproject.toml` with integration version | Done | pyproject is now 0.5.21 |
| Add v0.5.21 changelog entry | Done | release hygiene changes documented |

### P4 - IAQ/AQ validation

| Item | Status | Notes |
|---|---|---|
| Confirm live payload fields for WTP `iaq_sensor`, `aq_sensor`, `air_quality_sensor` | Pending hardware inventory | code already has descriptors for `iaq`, `air_quality`, PM fields |
| Add fixture/test only if live payload differs | Pending | do not duplicate existing generic sensor behavior |

### P5 - Backlog

| Feature | Priority | Notes |
|---|---|---|
| Camera PTZ control | Low | endpoint unknown |
| Camera motion events from WS | Medium | depends on live video WS payloads |
| LoRa relay live test | Low | no LoRa hardware on known hubs |
| Alarm modes and bypass | Low | current implementation basic |
| Scene triggers in automations | Low | `device_trigger` exists; scenes via `run_scene` |
| SBUS `blind_controller` position feedback | Medium | API endpoint TBD |

---

## Release Plan For This Work

1. Apply P0/P1/P3 code and docs fixes.
2. Run local gates:
   - `python3 -m pytest -q`
   - `/opt/homebrew/bin/ruff check custom_components/`
   - `/opt/homebrew/bin/ruff format --check custom_components/`
   - `/opt/homebrew/bin/mypy custom_components/sinum/ --ignore-missing-imports --no-site-packages`
   - `.venv/bin/python -m pytest -q tests/test_code_quality.py`
3. Run final hardware tests:
   - read-only smoke against known hubs;
   - live-write validation only with explicit safe env vars and no alarm operation unless `SINUM_ALARM_TEST_PIN` is set.
4. Deploy v0.5.21 to HA/RPi, run registry migration, restart HA and verify API.
5. Commit, tag and publish release.

---

## Known API Limitations

| Device | Bus | Problem |
|---|---|---|
| `rgb_controller` | WTP/SBUS | WTP color/brightness can be firmware-limited; SBUS color path uses Lua scene calls |
| Virtual cover integrators | Virtual | no position feedback when no physical controller is linked |
| LoRa relay PATCH | LoRa | implemented but untested without hardware |
| Alarm arm/disarm | alarm-system | destructive; requires explicit PIN and owner approval |

---

## v0.7.0+ Backlog

| Feature | Priority | Effort | Status | Notes |
|---|---|---|---|---|
| **P4 — IAQ/AQ Live Probe** | Medium | 15 min | ✅ Complete | All 3 WTP iaq_sensor devices validated; descriptors match live payloads |
| **P5.1 — Scene device_trigger** | Medium | 1-2 h | ✅ Complete | Scene platform + device_trigger automation support implemented and tested |
| **P5.2 — Camera motion events** | Medium | 2-3 h | ✅ Complete | Motion_detected WS event type, coordinator dispatch, event entity; all tests passing (1648 ✅) |
| **P5.3 — SBUS blind position feedback** | Medium | 2-3 h | In Progress | Position fields (`current_opening`, `current_tilt`) already in API; verify live feedback and add comprehensive tests |
| **Alarm modes & bypass** | Low | 2-3 h | Pending | Add arm/disarm modes, zone bypass (requires destructive write testing) |
| **LoRa relay live test** | Low | 1 h | Blocked | No LoRa hardware on known hubs; waiting for LoRa-equipped hub |
| **Performance metrics** | Low | 3-4 h | Future | Add WS uptime/reconnect rate dashboard; integration health metrics |

---

## Working Rules

- Never commit credentials, tokens or HA access tokens.
- Treat writes to fan coils, scenes, alarms, gates, covers and relays as potentially destructive.
- New device types require fixture data and at least one focused test before merge.
- `ruff check`, `ruff format --check`, `mypy`, full pytest and CC gate must pass before release.
- CC <= 4, `_LEGACY_ALLOWANCE = {}`; no new exceptions.
- Every new branch of integration code must be covered by tests.
