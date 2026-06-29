# Sinapse — Implementation Plan & Critical Review

> Last updated: 2026-06-29 (v0.5.9 — camera platform, RTSP streaming)
> Verified against two live hubs (firmware `1.24.0-alpha.2`/`alpha.3`, API `1.4`).
> Credentials and API tokens must never be committed to this repository.

---

## Project Status (2026-06-29)

```text
Tests:  1 516 passing, 5 skipped (~8.2 s)
Ruff:   0 errors (28 files, pinned 0.4.8)
mypy:   0 errors (28 files)
CC:     ≤ 4, _LEGACY_ALLOWANCE = {}
Live:   2 581 entities on 2 hubs (both HA entries, 0 errors)
Tags:   v0.5.7, v0.5.8, v0.5.9 released (v0.5.8/5.9 GitHub Releases TBD)
HACS:   submission ready pending hassfest validation
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

### Known Hardware Limitations

| Issue | Status |
|---|---|
| Virtual cover integrators (roletki): state=unknown, no position feedback | Accepted — hardware limitation; state restores from HA after first command |
| WTP rgb_controller: Lua not supported — REST only, limited control in temperature mode | Accepted — firmware limitation |
| LoRa relay PATCH endpoint | Untested — no LoRa hardware available on either hub |

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
| 13 | HA event entity; DHW switch; target_reached binary_sensor; 552 tests | ✅ |
| 14 | Boolean state fix, RGB ONOFF-only, via_device hierarchy, critical review | ✅ |
| 15A | HA compliance: state_class, homeassistant min version, hacs.json | ✅ |
| 15B | Code quality: sensor.py split, climate mixin, SinumVariableNumber | ✅ |
| 15C | Test coverage: MQTT routing, multi-hub, event types | ✅ |
| 15D | New features: api_coverage, energy center, schedules, modbus | ✅ |
| 15E | HACS prep: brands/, translation keys, CONTRIBUTING.md | ✅ (except hassfest) |
| v0.3.x | Failsafe add/reauth flow, retry, host normalization, anti-bruteforce | ✅ |
| v0.4.x | WS transport, CC gate, modbus energy meter, quality sprint | ✅ |
| v0.5.x | WS 100%, ConfigEntryAuthFailed, stale cleanup, PL docs, ruff clean | ✅ |
| v0.5.8 | mypy fix (light.py), temperature-zero → unavailable (WTP regulators) | ✅ |
| v0.5.9 | Camera platform: snapshot proxy + RTSP streaming for ip_camera/onvif_camera | ✅ |

---

## Remaining Work

### Next: HACS Submission

- [ ] **hassfest validation** — run via Docker or CI (blocked locally: requires Python 3.12+
  environment with `homeassistant` package). See [hassfest Docker](#hassfest-docker) below.
- [ ] Submit PR to [hacs/default](https://github.com/hacs/default) once hassfest is clean.

#### hassfest Docker

```bash
docker run \
  --rm \
  -v $(pwd)/custom_components/sinum:/github/workspace/custom_components/sinum \
  ghcr.io/home-assistant/hassfest \
  --integration-path /github/workspace/custom_components/sinum
```

Or via the GitHub Actions workflow `.github/workflows/validate.yml` if configured.

### Backlog

| Item | Priority | Notes |
|---|---|---|
| Smoke test v0.5.8/v0.5.9 on live hub | **High** | Camera entity verification, temperature-zero fix |
| GitHub Releases v0.5.8 + v0.5.9 | **High** | Manual — `gh` not authenticated |
| Camera: PTZ control (pan/tilt/zoom) | Medium | API endpoint unknown — needs hub investigation |
| Camera: motion events from hub WebSocket | Medium | Hub may push `motion` events for video devices |
| LoRa relay live test | Low | No hardware — skip until available |
| Nightly regression summary in docs | Low | CI artefact, defer until HACS submission |
| Endpoint matrix in `docs/api_coverage.md` | Low | Dev docs completeness |
| Anti-bruteforce backoff — verify UI message | Low | Already implemented, needs UX test |

---

## Working Rules

- Never commit secrets, tokens, hub credentials, or raw diagnostic payloads.
- Treat writes to fan coils, scenes, alarms, gates, and doors as potentially destructive.
- Prefer read-only discovery first, then test write payloads on non-critical devices.
- Keep REST polling as the baseline; MQTT is an optimization, not a dependency.
- All new device types require a fixture + ≥1 unit test before merging.
- `ruff check`, `ruff format --check`, and `mypy` must pass on every commit.
- CC ≤ 4, `_LEGACY_ALLOWANCE = {}` — no exemptions.
