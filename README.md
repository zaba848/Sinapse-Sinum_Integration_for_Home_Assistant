# Sinapse — Sinum Integration for Home Assistant

**Sinapse** connects a [TECH Sterowniki](https://www.techsterowniki.pl) **Sinum** building automation hub to Home Assistant over the local network. All physical and virtual devices are exposed as native HA entities with full read/write control and real-time state updates.

**Language:** English | [Polski](README.pl.md)

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg)](https://www.home-assistant.io)
[![Tests](https://img.shields.io/badge/tests-1678%20passing-brightgreen.svg)](tests/)
[![CC Gate](https://img.shields.io/badge/CC-≤4%20everywhere-brightgreen.svg)](tests/test_code_quality.py)
[![Version](https://img.shields.io/badge/version-0.7.2-blue.svg)](custom_components/sinum/manifest.json)
[![License](https://img.shields.io/badge/license-Source%20Available-lightgrey.svg)](LICENSE)

---

## What You Get

- **5 live production hubs** configured in Home Assistant; over 3 800 Sinum registry entities
- **12 entity platforms**: climate, sensor, binary\_sensor, switch, cover, light, event, button, number, update, alarm\_control\_panel, camera
- **7 local surfaces**: Virtual, WTP, SBUS, LoRa, SLINK, Modbus, Video — polled in parallel every 30 s
- **Real-time push** via WebSocket (\< 1 s latency), MQTT bridge as fallback
- **1 678 passing tests** across 46 test files, CC ≤ 4 on every function, ruff and mypy clean

---

## Quick Start

```
1. HACS → Integrations → ⋮ → Custom repositories
   URL: https://github.com/zaba848/sinapse-sinum-integration-for-home-assistant
   Category: Integration

2. Install "Sinum (Sinapse)" → Restart Home Assistant

3. Settings → Devices & Services → Add Integration → search "Sinum"
   Enter hub IP and API token

4. WebSocket real-time transport is enabled by default.
```

→ **[Full Installation Guide with screenshots](docs/installation.md)**

---

## Documentation

| Document | Contents |
|---|---|
| [Installation Guide](docs/installation.md) | HACS, manual install, token setup, step-by-step screenshots |
| [Entity Reference](docs/entities.md) | All platforms, attributes, automation examples |
| [Real-Time Transports](docs/real-time.md) | WebSocket setup + MQTT bridge (legacy) |
| [Development Guide](docs/development.md) | Setup, tests, CC rules, adding new device types |
| [CHANGELOG](CHANGELOG.md) | Full version history |
| [Security Policy](SECURITY.md) | Vulnerability reporting |
| [Contributing](CONTRIBUTING.md) | How to contribute, code style, PR checklist |

---

## Architecture

```
Sinum Hub
    │  REST API (HTTP/JSON)  PATCH /api/v1/devices/{bus}/{id}
    ▼
SinumClient (api.py)
    │  aiohttp · JWT auto-refresh · 408 retry · SinumNotSupportedError on 404
    ▼
SinumCoordinator (coordinator.py)
    │  DataUpdateCoordinator · parallel bus fetch · cached fallback
    │  removed_ids tracking → stale entity registry cleanup
    │
    ├──► Entity platforms (climate · sensor · switch · cover · light · …)
    │    Read: coordinator.{bus}_devices[id]
    │    Write: coordinator.client.patch_{bus}_device(id, payload)
    │
    ├──► WebSocket bridge (websocket.py)     ← recommended real-time
    │    Hub pushes device_state_changed events
    │    Coordinator cache patched immediately → entities refresh < 1 s
    │
    └──► MQTT bridge (mqtt.py + lua_scripts/mqtt_bridge.lua)  ← legacy fallback
         Hub Lua script publishes state changes to MQTT broker
         Integration subscribes and patches coordinator cache
```

**Auth**: prefers static API token (no expiry). Falls back to username + password with JWT auto-refresh on 401.

**Error handling**: `SinumConnectionError` on network/JSON failures. Coordinator returns cached state during hub outages. Write operations surface errors as `HomeAssistantError` in the HA UI. HTTP 408 (bus busy) retried once after 1 s.

---

## Supported Devices

### Entity Platforms

| Platform | Description |
|---|---|
| `climate` | Virtual thermostats · WTP/SBUS fan coils · temperature regulators · heat pump manager |
| `sensor` | Temperature · humidity · CO₂ · pressure · illuminance · PM · IAQ · power · energy · voltage · current · weather · hub diagnostics · Energy Center · automation status · schedule summaries |
| `binary_sensor` | Flood · motion · opening · smoke · two-state input · WTP fan coil valve state · parent device connectivity |
| `switch` | Virtual relay integrators · WTP/SBUS relays · wicket (electric strike) · valve\_pump · common\_valve |
| `cover` | Virtual blind integrators · gate · WTP/SBUS blind controllers |
| `light` | Virtual dimmer/RGB integrators · WTP/SBUS dimmers · WTP/SBUS RGB controllers |
| `event` | Physical button press events — fires per press, ideal for HA automations |
| `button` | Sinum Lua scenes (activated via `POST /activate`) |
| `number` | Numeric Lua environment variables · SBUS analog output (0–10 V) |
| `update` | Parent device firmware tracker |
| `alarm_control_panel` | Alarm system (when present on hub) |
| `camera` | IP/ONVIF cameras — RTSP stills (when credentials available) + hub snapshot fallback + WebRTC live view |

### Device Types per Bus

**Virtual** — `thermostat` · `relay_integrator` · `blind_controller_integrator` · `gate` · `wicket` · `dimmer_rgb_controller_integrator` · `dimmer_rgb_integrator` · `heat_pump_manager`

**WTP bus** — `temperature_sensor` · `humidity_sensor` · `pressure_sensor` · `light_sensor` · `co2_sensor` · `iaq_sensor` · `aq_sensor` · `motion_sensor` · `flood_sensor` · `opening_sensor` · `smoke_sensor` · `two_state_input_sensor` · `relay` · `dimmer` · `rgb_controller` · `blind_controller` · `energy_meter` · `fan_coil` · `fan_coil_v2` · `temperature_regulator` · `button`

**SBUS bus** — `temperature_sensor` · `humidity_sensor` · `light_sensor` · `motion_sensor` · `two_state_input_sensor` · `analog_input` · `analog_output` · `impulse_meter` · `relay` · `dimmer` · `rgb_controller` · `fan_coil` · `temperature_regulator` · `button` · `valve_pump` · `common_valve` · `pulse_width_modulation` · `blind_controller` · `energy_meter`

**LoRa bus** — `temperature_sensor` · `humidity_sensor` · `opening_sensor` · `flood_sensor` · `relay` · `two_state_input_sensor` · `smoke_sensor`

---

## Configuration Reference

### Integration options (Settings → … → Sinum → Configure)

| Option | Default | Description |
|---|---|---|
| Scan interval | 30 s | REST poll interval (10–300 s). Always active as safety reconciliation path. |
| Enable WebSocket real-time transport | **on** | Persistent WS to hub for instant state push (<1s latency). Enabled by default in v0.6.0+. |
| WebSocket endpoint path | `/api/v1/ws` | Change only if your hub firmware uses a non-standard path. |
| Enable MQTT real-time transport | off | Legacy MQTT push via Lua bridge. Use only if WS is not supported. |
| MQTT topic prefix | `sinum` | Must match `TOPIC_PREFIX` in `mqtt_bridge.lua`. |

### Re-authentication

If the hub token or password changes, HA shows a persistent notification. Click **Re-authenticate** and enter the new credentials — no restart needed.

### Multiple hubs

Multiple Sinum hubs can be added as separate config entries. Services (`sinum.send_notification`, `sinum.update_schedule`, `sinum.upload_mqtt_bridge`) accept an optional `entry_id` field to target a specific hub.

---

## HA Services

### `sinum.send_notification`

Sends a push notification via the hub to the Sinum mobile app.

```yaml
service: sinum.send_notification
data:
  title: "Home Assistant"
  message: "Front door open for 10 minutes."
```

### `sinum.update_schedule`

Updates a Sinum thermal schedule. Useful for dynamic heating programs from HA automations.

```yaml
service: sinum.update_schedule
data:
  schedule_id: 3
  payload:
    name: "Summer Mode"
    periods:
      - start: "08:00"
        temperature: 210   # °C × 10
```

### `sinum.upload_mqtt_bridge`

Renders and uploads the Lua MQTT bridge script to a hub scene. Replaces manual copy/paste.

```yaml
service: sinum.upload_mqtt_bridge
data:
  mqtt_scene_id: 1    # scene ID on the hub to overwrite
  mqtt_client_id: 1   # MQTT client ID from Sinum web UI
  dry_run: false      # set true to preview Lua without uploading
```

---

## Tested Hubs

| Hub | Firmware | Virtual | WTP | SBUS | SLINK | Modbus | Video | Alarm |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| tablica-wtp | 1.24.0-alpha.2 | 30 | 254 | 8 | 2 | 0 | 0 | 1 |
| sinum-tablica-sbus-1 | 1.24.0-alpha.4 | 171 | 35 | 436 | 0 | 1 | 0 | 3 |
| tablica-video-nowa | 1.24.0-alpha.4 | 6 | 21 | 77 | 0 | 1 | 6 | 0 |
| tablicaKlimak | 1.24.0-alpha.4 | 13 | 41 | 25 | 0 | 5 | 0 | 0 |
| sinum-tablica-sbus2 | 1.24.0-alpha.3 | 29 | 50 | 191 | 2 | 3 | 0 | 16 |

Read-only smoke, API coverage, HIL smoke and WebSocket checks passed on live hardware (2026-06-30).

`tablica-wtp` (WTP-heavy): 108 WTP relays, 18 blind controllers, 15 temperature regulators, 28 buttons, full sensor suite (temperature/humidity/CO₂/IAQ/pressure/light/motion/flood), 1 fan coil, 1 energy meter.

`sinum-tablica-sbus-1` (SBUS-heavy): 83 virtual thermostats, 51 SBUS temperature regulators, 69 SBUS relays, 38 SBUS dimmers, 6 SBUS RGB controllers, 30 SBUS buttons, 134 SBUS temperature sensors, 46 SBUS humidity sensors, 1 heat pump manager.

---

## Quality Assurance & Testing

### Local Quality Gates (Required before every merge)

```bash
# All tests pass (no regressions)
python3 -m pytest -q

# Cyclomatic Complexity ≤ 4 everywhere
python3 -m pytest -q tests/test_code_quality.py

# Ruff style checks
/opt/homebrew/bin/ruff check custom_components/

# No uncommitted formatting issues
/opt/homebrew/bin/ruff format --check custom_components/

# Type safety (Python 3.9+ compatible)
/opt/homebrew/bin/mypy custom_components/sinum/ \
  --ignore-missing-imports --no-site-packages

# No credentials in staged commits
git diff --cached | grep -iE "password|token|api.?key|secret" || echo "✓ Safe to commit"
```

### Post-Release Hardware Testing (5 live hubs)

```bash
# Read-only smoke (no writes, no credentials needed)
export SINUM_SMOKE_HUBS="HUB1=http://<IP1>,HUB2=http://<IP2>,..."
python3 scripts/hardware_smoke_check.py

# Safe write validation (dimmer + schedule only)
export SINUM_SBUS_TOKEN="<api-token>"
python3 scripts/validate_api_writes.py

# WebSocket event capture (30s passive listen)
python3 scripts/hardware_in_loop/websocket_listener.py \
  --hub=http://<SBUS_HUB> --token=<api-token> --duration=30
```

### Test Coverage

| Metric | Value | Target |
|---|---|---|
| Test files | 46 | ≥40 |
| Test cases | 1678 | ≥1600 |
| Ruff violations | 0 | 0 |
| MyPy errors | 0 | 0 |
| CC > 4 functions | 0 | 0 |
| Fixture data coverage | All 7 buses | All 7 buses |
| Hardware inventory | 5/5 hubs tested | 5/5 hubs PASS |

---

## Known Limitations

| Limitation | Details |
|---|---|
| **SBUS button action type without push transport** | SBUS hub resets `action` to `""` immediately after a press. Press IS detected via `buttons_count`, but `action` will be `None` without WebSocket/MQTT. |
| **`custom_device` virtual type** | Lua contracts vary per installation — not mapped to HA entities. Use scenes/automations instead. |
| **`thermostat_output_group`** | Diagnostic sensor (output count) only, no direct control entities. |
| **WTP RGB in temperature mode** | Hub firmware ignores color values when color-temperature mode is active; only `color_temp_kelvin` takes effect. |
| **Virtual blind integrators** | Report `position = None` when no physical controllers are linked (hub configuration issue, not integration bug). |
| **Energy Center** | Sensors appear only when hub firmware exposes `/api/v1/energy-center/*`. |
| **Schedules** | Read-only sensors + `sinum.update_schedule` service. Full schedule editing UI is not implemented. |
| **LoRa / SLINK / Video** | Require specific hardware modules. SLINK relay and energy meter entities are mapped; video cameras use RTSP (when credentials are available) for thumbnail stills and WebRTC for live view, with hub snapshot as fallback. LoRa write support is implemented but still needs relay hardware validation. |
| **Alpha firmware 408s** | Intermittent on bus polling. Integration retries once then serves cached state. |

---

## Security Best Practices

The hub communicates over plain HTTP on the local network.

- **Network**: place the hub on a dedicated IoT VLAN. Allow only HA to reach it on port 80. Block direct internet access.
- **Token over password**: generate a dedicated API token for HA integration. It is scoped, doesn't grant shell access, and can be revoked independently.
- **Never expose**: do not paste the token into GitHub issues, logs, screenshots, or chat messages. The integration redacts it from HA diagnostics.
- **TLS (optional)**: place an nginx or Caddy reverse proxy on the VLAN that terminates TLS and forwards to the hub.
- **Reauth protection**: integration blocks re-authentication after 5 consecutive failures for 5 minutes.

See also: [SECURITY.md](SECURITY.md)

---

## Official Sinum Resources

| Resource | URL |
|---|---|
| Sinum REST API docs | <https://apidocs.sinum.tech/> |
| Lua scripting manual | <https://www.techsterowniki.pl/!uploads/SINUM/LUA_user_manual.pdf> |
| Sinum FAQ (PL) | <https://www.techsterowniki.pl/blog/system-sinum-najczesciej-zadawane-pytania> |
| Knowledge base (PL) | <https://www.techsterowniki.pl/blog/kategoria/sinum> |
| Google Home integration | <https://www.techsterowniki.pl/blog/polaczenie-centrali-sinum-z-usluga-google-home> |
| Sinum Cloud app | <https://sinum.tech/sign-in> |

---

## Legal Notice

This is an unofficial community project. Not affiliated with, authorized by, or maintained by TECH Sterowniki. "TECH", "Sinum" and related names may be trademarks of their respective owners. This integration uses the hub's documented local API to control devices in the user's own installation. Users are responsible for compliance with local law and vendor terms.

---

## License

**Source Available — Commercial Use Restricted**

© 2026 Tomasz Panek · All Rights Reserved

Personal and non-commercial home automation use: **free**.  
Business, organizational, or product deployment: **license required** — contact zaba9214@gmail.com.

See [LICENSE](LICENSE) for full terms.
