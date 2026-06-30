# Sinapse — Implementation Plan & Status

> Last updated: 2026-06-30 (v0.5.20)
> Verified against 5 live hubs (firmware `1.24.0-alpha.2/alpha.4`, API `1.4`).
> Credentials and API tokens must never be committed to this repository.

---

## Project Status (2026-06-30)

```text
Tests:  1 648 passing, 5 skipped (~9 s)
Ruff:   0 errors
mypy:   0 errors
CC:     ≤ 4, _LEGACY_ALLOWANCE = {}
Coverage: api.py 100%, coordinator.py 100%, websocket.py 100%
Live:   5 hubs connected (3846 HA entities total), 0 errors in error_log
Tags:   v0.5.15–v0.5.20 released on GitHub
Deploy: v0.5.17–v0.5.20 awaiting deploy to RPi (v0.5.16 last deployed)
```

---

## Live Hub Inventory (5 hubs)

| Hub | IP | Type | Key devices |
|---|---|---|---|
| sinum-tablica-sbus-1 | 10.0.62.167 | sinum_lite | 436 SBUS, 35 WTP, 169 virtual |
| tablica-wtp | 10.0.61.132 | sinum_plus | 254 WTP, 8 SBUS, 28 virtual |
| tablica-video-nowa | 10.0.62.117 | sinum_short | IP/ONVIF cameras |
| ehome-wojtek | (unknown) | — | newly added, full device list TBD |
| sinum-tablica-sbus2 | (unknown) | — | newly added, 433 entities in HA |

### Device types → HA platforms

| Type | Bus | HA platform | Notes |
|---|---|---|---|
| `relay` | WTP/SBUS/SLINK | switch | |
| `temperature_sensor` / `humidity_sensor` | all | sensor | |
| `temperature_regulator` | WTP/SBUS | climate + sensor | |
| `fan_coil` / `fan_coil_v2` | WTP/SBUS | climate | |
| `blind_controller` | WTP/SBUS | cover | |
| `dimmer` | WTP/SBUS/virtual | light | brightness |
| `rgb_controller` | WTP/SBUS | light | on/off only (API limitation) |
| `button` | WTP/SBUS | event + sensor | |
| `two_state_input_sensor` | all | binary_sensor | |
| `flood_sensor` / `motion_sensor` / `smoke_sensor` / `opening_sensor` | all | binary_sensor | |
| `energy_meter` | WTP/SBUS/SLINK | sensor | power/voltage/current/energy |
| `analog_input` | SBUS | sensor | dynamic unit |
| `impulse_meter` | SBUS | sensor | total/window count + value |
| `analog_output` / `pulse_width_modulation` | SBUS | number | |
| `common_valve` / `valve_pump` | SBUS | switch | |
| `heat_pump` / `inverter` / `battery` / `car_charger` / `common_dhw_main` | Modbus | sensor | disabled by default |
| `ip_camera` / `onvif_camera` | Video | camera | snapshot + WebRTC |
| `thermostat` / `heat_pump_manager` / `dimmer_rgb_integrator` | Virtual | climate/light | |
| Alarm zones | — | alarm_control_panel | |
| Schedules | — | sensor (3/schedule) | target temp, fallback, active period |
| Parent devices | — | binary_sensor + update | online/problem/firmware |

---

## Completed Phases

| Version | Summary | Tests |
|---|---|---|
| v0.1–v0.4 | Core: REST, coordinator, config_flow, virtual, WTP/SBUS sensors, climate, light, cover, switch, number | — |
| v0.5.0 | WS transport, CC gate | — |
| v0.5.3 | WS 100%, ConfigEntryAuthFailed | — |
| v0.5.4 | Sensor 404 crash fix, WS background task | — |
| v0.5.5 | CC zero-legacy, stale device cleanup | — |
| v0.5.6 | ConfigEntryAuthFailed, device registry cleanup | — |
| v0.5.7 | Full PL docs, ruff clean, MQTT bridge translation | 1 498 |
| v0.5.8 | mypy fix (light.py), temperature-zero → unavailable | 1 499 |
| v0.5.9 | Camera: snapshot proxy + WebRTC (ip_camera/onvif) | 1 516 |
| v0.5.10 | `run_scene` service, diagnostics video, notify tests | 1 546 |
| v0.5.13 | WebRTC trickle ICE, HA 2026.6 native API | — |
| v0.5.15 | SLINK bus (relay + energy_meter), WebRTC coordinator tests | 1 605 |
| v0.5.16 | Modbus: heat_pump, inverter, battery, car_charger, DHW sensors | 1 616 |
| v0.5.17 | Multi-hub device name prefix (hub_name: Device) | 1 616 |
| v0.5.18 | Per-phase unique translation keys, entity registry migration script | 1 616 |
| v0.5.19 | hub_prefixed_name extended to camera, sensor_virtual, event, binary_sensor, update, sensor_schedule | 1 616 |
| v0.5.20 | 100% coverage: api.py, coordinator.py, websocket.py (+32 tests) | 1 648 |

---

## Immediate Actions Required (user)

### 1. Deploy v0.5.17–v0.5.20 to RPi

```bash
# Lokalnie:
tar czf /tmp/sinum_v0520.tar.gz custom_components/sinum/

# SSH na RPi:
scp /tmp/sinum_v0520.tar.gz tomasz@homeassistant.local:/tmp/
ssh tomasz@homeassistant.local \
  "cd /config && tar xzf /tmp/sinum_v0520.tar.gz"
```

Następnie restart HA:
```bash
curl -X POST http://homeassistant.local:8123/api/services/homeassistant/restart \
  -H "Authorization: Bearer <HA_TOKEN>"
```

### 2. Wyczyść stare entity_ids (migration script)

Po restarcie HA zatrzymaj go i uruchom skrypt:
```bash
ssh tomasz@homeassistant.local
ha core stop
python3 /config/scripts/migrate_entity_registry.py
ha core start
```

Skrypt usuwa ~85 collision entity_ids z sufiksem `_2`/`_3` które powstały zanim dodano prefiks hubów.

---

## Remaining Work

### Priorytet 1 — Jakość kodu (możliwe natychmiast)

| Plik | Coverage | Brakujące linie | Szacunek |
|---|---|---|---|
| `__init__.py` | 91% | 237, 275-276, 297-325, 367, 479-480 | setup/teardown paths, WS bridge start/stop |
| `config_flow.py` | 96% | 99, 108, 115, 117, 119, 277, 317-318, 491, 493 | edge cases w config flow |
| `binary_sensor.py` | 99% | 182, 312 | fan_coil gear logic, `_source_from_label` |
| `camera.py` | 98% | 117-118, 224 | `async_is_supported` URL parse error, `stream_source` non-streamable |
| `sensor_modbus.py` | 99% | 624 | jedna gałąź |

### Priorytet 2 — Nowe typy urządzeń

| Typ | Bus | Urządzenia live | Status |
|---|---|---|---|
| `iaq_sensor` / `air_quality_sensor` | WTP | 5+2 na tablica-wtp | **NIE zaimplementowane** w sensor_bus_descriptions.py (tylko const.py) |
| `aq_sensor` | WTP | 2 na tablica-wtp | Nie podłączone do sensora WTP |

> **Uwaga**: `analog_input`, `impulse_meter` już działają przez `SBUS_SENSORS`.

### Priorytet 3 — Multi-hub polish

| Item | Status |
|---|---|
| Uruchomić `migrate_entity_registry.py` → czyści 85 collision `_2/_3` entity_ids | Czeka na deploy + user |
| Zweryfikować live entity names po deployu v0.5.17–v0.5.19 | Po deployu |
| Sprawdzić nowe huby `ehome-wojtek` i `sinum-tablica-sbus2` — inventory urządzeń | TBD |

### Priorytet 4 — HACS / dokumentacja

| Item | Notes |
|---|---|
| hassfest validation | `docker run ghcr.io/home-assistant/hassfest` |
| HACS submission (`hacs/default` PR) | Po hassfest |
| Docs: SLINK, WebRTC, multi-hub, Energy Dashboard | README + docs/ |
| GitHub Releases dla v0.5.15–v0.5.20 | `gh release create` |

### Priorytet 5 — Funkcjonalne rozszerzenia (backlog)

| Feature | Priorytet | Uwagi |
|---|---|---|
| Camera: PTZ control | Low | Nieznany endpoint w API |
| Camera: motion events z WS | Medium | Hub może pushować `motion` dla video devices |
| LoRa relay live test | Low | Brak hardware |
| Alarm panel: arming modes, bypass | Low | Obecna implementacja podstawowa |
| Scene triggers w automatyzacjach | Low | device_trigger już jest, sceny przez `run_scene` |
| SBUS `blind_controller` position feedback | Medium | API endpoint TBD |

---

## Known API Limitations

| Device | Bus | Problem |
|---|---|---|
| `rgb_controller` | WTP/SBUS | `brightness`, `led_color` → 422; tylko `state: bool` |
| Virtual cover integrators | Virtual | Brak position feedback; state = unknown po restarcie |
| LoRa relay PATCH | LoRa | Nieprzetestowane — brak hardware |

---

## Working Rules

- Nigdy nie commitować sekretów, tokenów, credentials.
- Zapis do fan coils, scen, alarmów, bram — traktować jako destrukcyjne.
- Nowe typy urządzeń: fixture + ≥1 test przed mergiem.
- `ruff check`, `ruff format --check`, `mypy` muszą przejść na każdym commicie.
- CC ≤ 4, `_LEGACY_ALLOWANCE = {}` — brak wyjątków.
- Testy: każda nowa gałąź kodu musi być pokryta.
