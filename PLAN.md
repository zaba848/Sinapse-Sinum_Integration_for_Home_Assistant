# Sinapse — Implementation Plan & Critical Review

> Last updated: 2026-06-25 (v0.4.0 — modbus energy meter, notify 404 fix, live-write validation executed)
> Verified against two live hubs (firmware `1.24.0-alpha.2`/`alpha.3`, API `1.4`).
> Credentials and API tokens must never be committed to this repository.

## 2026-06-25 Hardening Sprint ✅ (Completed & Released as v0.3.9)

### A. Live Validation (hardware + API + server)

- [x] Run live read-only hardware smoke against both hubs (`10.0.61.132`, `10.0.62.167`).
- [x] Verify core endpoints `/api/v1/info`, `/devices/wtp`, `/devices/sbus`, `/devices/virtual` return HTTP 200.
- [x] Verify API/config/retry test suites pass locally.
- [x] Verify release gate on GitHub Actions (`CI`, `Lint`, `CodeQL`, `HACS`).

### B. Failsafe/Fallback in Add/Reconfigure/Reauth Flow

- [x] Reject malformed host input in GUI flow (path/query/fragment, empty host).
- [x] Add transient connection retry for add/reconfigure credential probes.
- [x] Add password-mode fallback when login succeeds but `/info` is temporarily unavailable.
- [x] Add user-facing translation for `invalid_host` and update docs/screenshots.

### C. Security and UX Hardening (GUI + runtime)

- [x] Validate and normalize MQTT topic prefix; block wildcard injection.
- [x] Keep token/password auth-mode split explicit in GUI steps.
- [ ] Add anti-bruteforce/backoff policy for repeated failed reauth attempts.
- [ ] Add secure defaults guidance in README (network segmentation, least privilege API token, TLS proxy option).
- [x] `notify.py` — graceful `SinumNotSupportedError` (404) on sinum_lite; `api.py` 404 → `SinumNotSupportedError` (distinct from connection errors).

### D. API Coverage and HA Mapping Plan

- [x] Keep current coverage map in `docs/api_coverage.md` synchronized with implemented endpoints.
- [ ] Add endpoint-by-endpoint matrix: implemented in HA entity/service vs helper-only vs intentionally excluded.
- [ ] Prioritize remaining live-write validations (LoRa relay patch, RGB/dimmer idempotency, heat_pump_manager mode matrix).

### E. Quality Gates and Engineering Practices

- [x] 100% line coverage for `custom_components/sinum` maintained in local run.
- [x] Require `ruff check`, `ruff format --check`, `mypy`, and targeted+full tests before release.
- [ ] Add nightly regression summary to docs with trend (pass rate, duration, flaky tests).
- [ ] Keep cyclomatic complexity guard (`C901`, max-complexity=4) enforced for modified files.

---

## Current Reality

```text
Home Assistant
  └─ custom_components/sinum
       ├─ REST discovery and polling (30 s default)
       ├─ optional MQTT push bridge from Lua script on hub
       └─ optional Lua HTTP extension for extra hub diagnostics

Sinum EH-01 hub
  ├─ /api/v1/info, /api/v1/rooms, /api/v1/floors
  ├─ /api/v1/devices/virtual, /wtp, /sbus, /lora
  ├─ /api/v1/parent-devices
  ├─ /api/v1/schedules, /api/v1/scenes
  └─ Lua API v1.24+: HTTP server, MQTT client, buses, statistics, Energy Center
```

---

## Live Hub Inventory

Two hubs verified continuously. Hub 2 is the active HA instance.

### Hub 1 — tablica-wtp (sinum_plus, 10.0.61.132)

Heavy WTP installation: 28 virtual, 254 WTP, 8 SBUS, 34 rooms.

| Bus | Type | Count | HA entity |
|---|---|---:|---|
| WTP | `relay` | 108 | switch |
| WTP | `temperature_sensor` | 26 | sensor |
| WTP | `humidity_sensor` | 21 | sensor |
| WTP | `blind_controller` | 18 | cover |
| WTP | `temperature_regulator` | 15 | climate |
| WTP | `button` | 28 | event + sensor |
| WTP | `two_state_input_sensor` | 8 | binary_sensor |
| WTP | `light_sensor` | 6 | sensor |
| WTP | `iaq_sensor` | 5 | sensor |
| WTP | `pressure_sensor` | 5 | sensor |
| WTP | `co2_sensor` | 3 | sensor |
| WTP | `flood_sensor` | 2 | binary_sensor |
| WTP | `motion_sensor` | 2 | binary_sensor |
| WTP | `aq_sensor` | 2 | sensor |
| WTP | `energy_meter` | 1 | sensor (power/voltage/current/energy) |
| WTP | `fan_coil` / `fan_coil_v2` | 2 | climate |
| WTP | `dimmer` | 1 | light |
| WTP | `rgb_controller` | 1 | light (ONOFF only) |

### Hub 2 — sinum-tablica-sbus-1 (sinum_lite, 10.0.62.167) — **active in HA**

Heavy SBUS installation: 169 virtual, 35 WTP, 436 SBUS, 60 rooms.

| Bus | Type | Count | HA entity |
|---|---|---:|---|
| SBUS | `temperature_sensor` | 134 | sensor |
| SBUS | `relay` | 69 | switch |
| SBUS | `temperature_regulator` | 51 | climate + sensor |
| SBUS | `humidity_sensor` | 46 | sensor |
| SBUS | `dimmer` | 38 | light |
| SBUS | `two_state_input_sensor` | 35 | binary_sensor |
| SBUS | `button` | 30 | event + sensor |
| SBUS | `analog_input` | 10 | sensor |
| SBUS | `rgb_controller` | 6 | light (ONOFF only) |
| SBUS | `impulse_meter` | 4 | sensor |
| SBUS | `analog_output` | 3 | number |
| SBUS | `motion_sensor` | 2 | binary_sensor |
| SBUS | `light_sensor` | 2 | sensor |
| SBUS | `pulse_width_modulation` | 2 | sensor |
| SBUS | `common_valve` / `valve_pump` | 4 | switch |
| Virtual | `thermostat` | 83 | climate |
| Virtual | `heat_pump_manager` | 1 | climate + switch (DHW) |
| Virtual | `dimmer_rgb_integrator` | 1 | light |
| Virtual | `custom_device` | 65 | — (intentionally skipped) |
| Virtual | `thermostat_output_group` | 9 | — (group metadata) |

---

## Critical Review

### Confirmed API Limitations (live-tested on both hubs)

| Device class | Bus | Accepted PATCH fields | Rejected fields |
|---|---|---|---|
| `rgb_controller` | WTP (label `rgbw`) | `state: bool` | brightness, led_color, white_temperature → 422 |
| `rgb_controller` | SBUS (label `rgbww`) | `state: bool` | same → 422 |
| `dimmer_rgb_integrator` | Virtual | `state: bool`, `brightness: int` | `led_color` → 422 |
| `dimmer` | WTP / SBUS | `state: bool`, `target_level: int` | — |
| `temperature_regulator` | WTP / SBUS | `target_temperature: int×10` | — |
| `fan_coil` | SBUS | `work_mode: str`, `target_temperature: int×10`, `fan_speed: str` | — |

### Bugs Fixed in Phase 14 (this branch)

- ✅ `SinumDimmerLight`: was sending `{"state": "on"/"off"}` string — API requires boolean
- ✅ `SinumBusRgbLight`: was trying to send brightness/color — always 422; now ONOFF-only
- ✅ `available_work_modes: []` (empty list from fan coil) returned `[OFF]` only instead of inferring
- ✅ `button.py` hardcoded `model="Sinum EH-01"` — now uses `coordinator.hub_info`
- ✅ Child devices on WTP/SBUS/LoRa buses had no `via_device` in HA Device Registry
- ✅ `_build_parent_maps` now returns `(model_maps, class_maps)` tuple; coordinator injects `_parent_class` + `_parent_id` for `via_device_for` helper

### Remaining Code Quality Issues

1. **`sensor.py` split completed** — platform setup/re-export remains in `sensor.py`; entity logic moved to
   `sensor_virtual.py`, `sensor_bus.py`, `sensor_schedule.py`.
2. **`climate.py` mixin added** — WTP/SBUS fan coil and temperature regulator now share bus-store,
   setpoint, min/max, HVAC mode and PATCH helpers.
3. **`SinumVariableNumber`** now extends `CoordinatorEntity`, reads `coordinator.variables`, and uses
   `hub_info` for model selection.
4. **`state_class` coverage is now guarded by tests** for measurements and totals.
5. **Test badge in README** reflects current full test count (866 passing).

### HA Compliance Gaps

| Requirement | Status |
|---|---|
| `hacs.json` | ✅ Present |
| `manifest.json` `homeassistant` min version | ✅ Present |
| `state_class` on measurement sensors | ✅ Present + unit-tested |
| `hassfest` validation | ❌ Not run |
| Translation keys complete | ⚠️ Partial |
| `brands/` folder (official HA listing) | ❌ Missing |
| `entity_category` on all diagnostic entities | ⚠️ Partial |

---

## Completed Phases

| Phase | Summary | Status |
|---|---|---|
| 1–6 | Core REST client, coordinator, config_flow, virtual devices | ✅ |
| 7A | WTP fan_coil + fan_coil_v2 climate entities | ✅ |
| 7B | Temperature regulator sensors + climate (WTP + SBUS) | ✅ |
| 7C | Thermal schedule sensors | ✅ |
| 7D | MQTT bridge hardening (lua v0.7+, heartbeat) | ✅ |
| 7E | Quality gate: translations, alarm panel, parent connectivity | ✅ |
| 8 | WTP/SBUS physical relay → switch; WTP blind_controller → cover | ✅ |
| 9 | SBUS/WTP dimmer → light; RGB controller → light; virtual dimmer | ✅ |
| 10 | SBUS motion sensor; illuminance/analog_input/impulse_meter sensors | ✅ |
| 11 | Sensor bug fixes: flood, aq PM, iaq, energy_meter fields | ✅ |
| 12 | valve_pump/common_valve switch; analog_output number; heat_pump_manager | ✅ |
| 13 | HA event entity; DHW switch; target_reached binary_sensor; 552 tests, 93% | ✅ |
| 14 | Boolean state fix, RGB ONOFF-only, via_device hierarchy, critical review | 🔄 |

---

## Remaining Work (Phase 15+)

### Phase 15A — HA compliance (next sprint)

- [x] Add `state_class = SensorStateClass.MEASUREMENT` to temp/humidity/illuminance/CO₂/pressure
- [x] Add `state_class = SensorStateClass.TOTAL_INCREASING` to energy/impulse meter sensors
- [x] Add `"homeassistant": "2024.1.0"` to `manifest.json`
- [x] Create `hacs.json`
- [x] Update README test badge/count to 880 passing

### Phase 15B — Code quality

- [x] Split `sensor.py` into `sensor_virtual.py`, `sensor_bus.py`, `sensor_schedule.py`
- [x] Extract shared base mixin for fan coil and temperature regulator climate entities
- [x] Fix `SinumVariableNumber` to extend `CoordinatorEntity` and use `hub_info` for model
- [x] Remove `_is_rgbww_animation_device` (dead code — all bus RGB is ONOFF-only now)

### Phase 15C — Missing test coverage

- [x] MQTT: WTP vs SBUS source routing test
- [x] MQTT: multi-field payload (temperature + state in one message)
- [x] MQTT: event type variety (button_press, heartbeat, unknown)
- [x] MQTT: missing `source` field → fallback to virtual store
- [x] Multi-hub: two entries with same device IDs don't collide
- [x] Multi-hub: service registration with N hubs

### Phase 15D — New features

- [x] API coverage audit against saved Sinum Swagger docs — see `docs/api_coverage.md`
- [x] `thermostat_output_group`: disabled-by-default diagnostic sensor
- [x] Automations: read-only API helpers and disabled-by-default status diagnostics
- [x] Schedules: explicit `sinum.update_schedule` PATCH service with multi-hub routing guard
- [x] Energy Center: `/energy-center/*` API helpers and disabled-by-default status diagnostic
- [ ] `LoRa` relay: verify `patch_lora_device` endpoint on live hub — **NO HARDWARE** (0 LoRa devices on both hubs 2026-06-25); code is in api.py but untested
- [x] `SBUS analog_input`: confirm read-only sensor coverage
- [x] RGB/dimmer idempotent live write check — **PASS** (2026-06-25, SBUS dimmers 121 + 122, idempotent=True)
- [x] `heat_pump_manager` heating/cooling mode — **CONFIRMED** valid modes: `heating`, `cooling`, `automatic` via `work_mode` PATCH; `off` → 422 (use `enabled: false` instead)
- [x] Modbus energy meter (`/api/v1/devices/modbus`) — 15 sensors per device, disabled_by_default, variant=p1 (DSMR P1)

### Phase 15E — HACS submission prep (do not start process yet)

- [x] Create `brands/sinum/` folder with `icon.png` and `icon@2x.png`
- [x] Complete translation keys in `strings.json`, `en.json`, and `pl.json`
- [ ] Run `hassfest` validation and fix all warnings (blocked locally: hassfest not installed and network install escalation rejected)
- [x] Add CONTRIBUTING.md

---

## Working Rules

- Never commit secrets, tokens, hub credentials, or raw diagnostic payloads.
- Treat writes to fan coils, scenes, alarms, gates, and doors as potentially destructive.
- Prefer read-only discovery first, then test write payloads on non-critical devices.
- Keep REST polling as the baseline; MQTT is an optimization, not a dependency.
- All new device types require a fixture + ≥1 unit test before merging.
- `ruff check` and `ruff format --check` must pass on every commit.
