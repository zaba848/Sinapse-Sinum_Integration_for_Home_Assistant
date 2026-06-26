# Sinapse — Sinum Integration for Home Assistant

**Sinapse** connects a TECH Sterowniki Sinum EH-01 building automation hub to Home Assistant over the local network. It exposes all physical and virtual devices as native Home Assistant entities with full read/write control.

**Language:** English | [Polski](README.pl.md)

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg)](https://www.home-assistant.io)
[![Tests](https://img.shields.io/badge/tests-1460%20passing-brightgreen.svg)](tests/)
[![Stability](https://img.shields.io/badge/stability-weekly%20validated-green.svg)](https://github.com/zaba848/sinapse-sinum-integration-for-home-assistant/actions/workflows/test-stability.yml)
[![Version](https://img.shields.io/badge/version-0.5.4-blue.svg)](custom_components/sinum/manifest.json)
[![License](https://img.shields.io/badge/license-Source%20Available-lightgrey.svg)](LICENSE)

---

## Legal Notice

- This is an unofficial community project and is not affiliated with, authorized by, endorsed by, or maintained by TECH Sterowniki.
- "TECH", "Sinum" and related names/logos may be trademarks of their respective owners.
- This integration uses documented/available hub APIs to read and control devices in the user's own installation.
- Users are responsible for ensuring their use complies with local law, vendor terms, and network/security policies.
- The software is provided as-is; see [LICENSE](LICENSE) for warranty and liability limitations.

---

## Table of Contents

- [How It Works](#how-it-works)
- [Supported Devices](#supported-devices)
- [Installation](#installation)
- [Configuration](#configuration)
- [Entity Reference](#entity-reference)
  - [Event — Physical Buttons](#event--physical-buttons)
- [HA Services](#ha-services)
- [Sinum Scenes, Automations and Variables](#sinum-scenes-automations-and-variables)
- [WebSocket Real-Time Transport](#websocket-real-time-transport)
- [MQTT Real-Time Bridge](#mqtt-real-time-bridge)
- [Release Stabilization Policy](#release-stabilization-policy)
- [Development Guide](#development-guide)
- [Adding New Device Types](#adding-new-device-types)
- [Known Limitations](#known-limitations)
- [Rollback Procedure](#rollback-procedure)
- [License](#license)

---

## How It Works

```
Sinum Hub 
    │
    │  REST API (HTTP/JSON)
    │  POST/PATCH /api/v1/devices/{bus}/{id}
    │
    ▼
SinumClient (api.py)
    │  asyncio + aiohttp, 25s timeout, 408 retry
    │  JWT auto-refresh or static API token
    │
    ▼
SinumCoordinator (coordinator.py)
    │  DataUpdateCoordinator, polls every 30s (configurable)
    │  Fetches all buses in parallel: virtual, WTP, SBUS, LoRa
    │  Falls back to cached state when hub is unreachable
    │
    ├──► Entity platforms (climate, sensor, switch, cover, light, …)
    │    Each entity reads from coordinator.{bus}_devices[id]
    │    Writes go directly to the hub via coordinator.client
    │
    ├──► WebSocket bridge (optional, websocket.py)
    │    Hub pushes event arrays
    │    → integration iterates events and applies device_state_changed updates
    │    → coordinator updated in-place → instant entity refresh
    │
    └──► MQTT bridge (optional fallback, mqtt.py)
         Hub Lua script publishes state changes → HA subscribes
         → coordinator updated in-place → instant entity refresh
```

**Auth**: Prefers static API token (no expiry). Falls back to username/password with JWT; on 401 the integration refreshes the JWT automatically and retries.

**Error handling**: Network errors and JSON decode failures raise `SinumConnectionError`. The coordinator returns cached state on fetch failure so entities stay available during brief hub outages. Entity write operations (`turn_on`, `set_temperature`, etc.) catch errors and surface them as `HomeAssistantError` visible in the HA UI.

**Bus timeout (408)**: The Sinum bus layer returns HTTP 408 when the physical bus is temporarily busy. The integration retries once after 1 second before raising an error.

---

## Supported Devices

### Entity Platforms

| Platform | Description |
|---|---|
| `climate` | Virtual thermostats, SBUS/WTP fan coils, SBUS/WTP temperature regulators, heat pump manager |
| `sensor` | Temperature, humidity, illuminance, CO₂, pressure, PM, IAQ, power, energy, voltage, current, weather, hub diagnostics, Energy Center, automation status, thermal schedule summaries, SBUS regulator target temp |
| `binary_sensor` | Flood, motion, opening, smoke, two-state input, WTP fan coil valve state, parent device connectivity |
| `switch` | Virtual relay integrators, wicket (electric strike), WTP/SBUS physical relays, valve_pump, common_valve |
| `cover` | Virtual blind controller integrator, gate, WTP blind controller |
| `light` | Virtual dimmer/RGB integrators, WTP/SBUS dimmer, WTP/SBUS RGB controller |
| `event` | Button press events — fires per action, ideal for HA automations |
| `button` | Sinum scenes (Lua `code` type) and Lua code scripts |
| `number` | Numeric Lua environment variables, SBUS analog output (0–10 V) |
| `update` | Parent device firmware tracker |
| `alarm_control_panel` | Alarm system (if present on hub) |

### Device Types per Bus

**Virtual devices**
`thermostat` · `relay_integrator` · `blind_controller_integrator` · `gate` · `wicket` · `dimmer_rgb_controller_integrator` · `dimmer_rgb_integrator` · `heat_pump_manager` · `thermostat_output_group`

**WTP bus**
`temperature_sensor` · `humidity_sensor` · `pressure_sensor` · `light_sensor` · `co2_sensor` · `iaq_sensor` · `aq_sensor` · `motion_sensor` · `flood_sensor` · `opening_sensor` · `smoke_sensor` · `two_state_input_sensor` · `relay` · `dimmer` · `rgb_controller` · `blind_controller` · `energy_meter` · `fan_coil` · `fan_coil_v2` · `temperature_regulator` · `button`

**SBUS bus**
`temperature_sensor` · `humidity_sensor` · `light_sensor` · `motion_sensor` · `two_state_input_sensor` · `analog_input` · `analog_output` · `impulse_meter` · `relay` · `dimmer` · `rgb_controller` · `fan_coil` · `temperature_regulator` · `button` · `valve_pump` · `common_valve` · `pulse_width_modulation` · `blind_controller` · `energy_meter`

**LoRa bus**
`temperature_sensor` · `humidity_sensor` · `opening_sensor` · `flood_sensor` · `relay` · `two_state_input_sensor` · `smoke_sensor`

---

## Installation

### HACS (recommended)

1. **HACS → Integrations → ⋮ → Custom repositories**
2. Add `https://github.com/zaba848/sinapse-sinum-integration-for-home-assistant` → category **Integration**
3. Find and install **Sinum (Sinapse)**
4. Restart Home Assistant

### Manual

Copy the integration directory to your HA config:

```bash
cp -r custom_components/sinum /config/custom_components/
```

Restart Home Assistant.

## Release Stabilization Policy

During release stabilization windows, the project follows a temporary feature freeze.

- New features are paused until hardware smoke checks pass on both WTP and SBUS hubs.
- Only regressions, reliability fixes, and release-blocking issues are allowed.
- A release is cut only after CI/CodeQL/HACS checks are green and the smoke checklist is completed.

Current stabilization artifacts are tracked in `HARDWARE_TEST_PLAN.md` and workflow summaries.

---

## Adding Sinum to Home Assistant — Quick Start

### Step 1 — Prepare the Sinum hub access token

Open the Sinum web UI in the same local network as Home Assistant, for example `http://sinum.local` or `http://10.0.62.167`.

![Sinum local sign-in](docs/images/setup/sinum-01-sign-in.png)

After signing in, go to **Settings → System → Integrations**.

![Sinum Settings System Integrations](docs/images/setup/sinum-02-settings-system-integrations.png)

In the **External integration tokens** section:

1. Click **Add token**.
2. Enter a clear name, for example `Home Assistant`.
3. Select the token type.
4. Click **Save**.
5. Copy the generated token immediately and store it securely.

![Sinum add external integration token](docs/images/setup/sinum-04-add-token.png)

You can later review or revoke tokens from **Settings → System → Integrations → External integration tokens → Token list**.

![Sinum token list](docs/images/setup/sinum-03-token-list.png)

Do not paste the token into GitHub issues, logs, screenshots or chat messages. If the token is lost, create a new one and revoke the old token in Sinum.

### Step 2 — Add the integration in Home Assistant

**Settings → Devices & Services → Add Integration → search for "Sinum"**

The setup wizard runs two screens:

**Screen 1 — Hub address and auth method**

| Field | Description |
|---|---|
| Host | IP address or hostname of your hub, e.g. `10.0.62.167`. Do not include `http://`. |
| Auth method | `api_token` (recommended) or `username_password` |

> If you don't know the hub IP, try `sinum.local` first. If that does not resolve, check the IP assigned to the hub in your router/DHCP lease list.

**Screen 2 — Credentials**

| Auth method | What to enter | Where to get it |
|---|---|---|
| API Token | Paste the token | Sinum web UI → Settings → System → Integrations → External integration tokens → Add token |
| Username / Password | Your Sinum login | Same credentials used for the Sinum web UI |

Click **Submit** — HA discovers all devices and creates entities automatically.

### Step 3 — Enable real-time updates (recommended)

Without this step, entities update every 30 s. With WebSocket, updates arrive in under 1 s.

1. **Settings → Devices & Services → Sinum (Sinapse) → Configure**
2. Enable **"Enable WebSocket real-time transport"**
3. Leave path as `/api/v1/ws` (default)
4. Click **Submit**

### Step 4 — (Optional) MQTT fallback

If your hub firmware doesn't support WebSocket (`/api/v1/ws` returns an error), use the MQTT bridge as fallback. See [MQTT Real-Time Bridge (Legacy)](#mqtt-real-time-bridge-legacy).

---

## Configuration Reference

### Options (accessible via Configure on the integration card)

| Option | Default | Description |
|---|---|---|
| Scan interval | 30 s | REST poll interval. 10–300 s. Always active as safety reconciliation path. |
| Enable WebSocket real-time transport | off | Opens a persistent WS to the hub for instant state push. Recommended. |
| WebSocket endpoint path | `/api/v1/ws` | Change only if your hub uses a non-standard path. |
| Enable MQTT real-time transport | off | Legacy MQTT push via Lua bridge. Use only if WS not supported. |
| MQTT topic prefix | `sinum` | Must match `TOPIC_PREFIX` in `mqtt_bridge.lua`. |

### Re-authentication

If the hub token or password changes, HA will show a persistent notification — click **Re-authenticate** and enter the new credentials. No restart needed.

### Reconfiguration

Click **Configure** (not Reconfigure) on the integration card to change options (WS, MQTT, scan interval). Click **⋮ → Reconfigure** to change the host or auth method.

---

## Entity Reference

### Climate

**Virtual Thermostat** (`thermostat`)
Controls a virtual zone thermostat. Modes: `heat` / `off`. Temperature range read from hub (`target_temperature_minimum` / `target_temperature_maximum`); values outside the range are clamped before sending so no 422 validation error occurs. The current temperature sensor is shown when a physical sensor is associated; otherwise the temperature state is `unknown`.

**Fan Coil** (`fan_coil`, `fan_coil_v2` — WTP and SBUS)
Full HVAC control: modes `heat`, `cool`, `fan_only`, `off`; fan speeds `low`, `medium`, `high`; target temperature. WTP fan coils also expose a valve-state binary sensor.

**Temperature Regulator** (`temperature_regulator` — WTP and SBUS)
On/off heating regulator with target temperature. Modes: `heat` / `off`.

**Heat Pump Manager** (`heat_pump_manager`)
Manages a central heat pump group: modes `heat`, `cool`, `off`; target temperature. Exposes child thermostat states as diagnostic sensors.

### Sensor

Hub temperature and humidity sensors return `unknown` (not `0.0`) when:
- The raw hub value is `0` and the device has no physical sensor (`zero_is_unavailable = True` flag)
- The device reports `status = "offline"`
- The hub sentinel value `−3276.8` is present (SBUS internal "no reading" code)

This prevents phantom readings on virtual thermostats without associated hardware.

**Sensor types include**: temperature (°C, ×0.1 scale), humidity (%RH), CO₂ (ppm), illuminance (lx), pressure (hPa), PM2.5/PM10 (µg/m³), IAQ index, power (W), energy (kWh), voltage (V), current (A), impulse count, analog input (0–10 V), weather conditions, hub info, Energy Center flow/storage/production, automation run status, schedule active period.

### Light

**Dimmer** (WTP / SBUS): brightness 0–100%, REST PATCH.

**RGB Controller — WTP**: REST PATCH for color, brightness, and color temperature. Note: in color-temperature mode the hub ignores color values (firmware limitation).

**RGB Controller — SBUS**: Uses a persistent Lua scene named `_ha_rgb_sbus_{id}` for each device. Each command sequence:
1. GET or POST to find/create the scene
2. PATCH the scene Lua code with the target state
3. POST `/activate` to execute it

Lua call order matters: `set_color` first, then `set_brightness` — the firmware resets brightness when color changes.

**Button Backlight** (WTP `button`): Appears in the device configuration page (not on the main dashboard). Category: `EntityCategory.CONFIG`.

### Cover

**Blind Controller** (WTP / virtual integrator): `open`, `close`, `stop`, set position 0–100.

**Gate** (virtual): `open`, `close`, `stop`. State machine tracks open/close/stopped states.

Virtual blind integrators with no associated physical controllers report `state = unknown` and `position = None` — this is correct hub behavior when no physical devices are linked.

### Switch

Physical relays filtered by the `managed_by_thermostat` label: relays tagged with this label are excluded from switch entities because they are controlled by the climate platform instead.

### Event — Physical Buttons

Physical Sinum buttons (WTP and SBUS bus) are exposed as **Event entities** (`event.sinum_*`).

#### How it works

When a button is pressed, the hub sets the `action` field on the device (`"single"`, `"double"`, `"hold"`, etc.) and increments `buttons_count`. On the next coordinator update the integration compares both values to the previous ones and fires a `pressed` event if either changed. This means:

| Scenario | Without MQTT | With MQTT |
|---|---|---|
| First press detected | Next poll, up to 30 s | < 1 s (hub push) |
| Two presses, different type | Both detected | Both detected |
| Two presses, same type (e.g. single + single) | Detected via `buttons_count` increment | Both detected |

The `buttons_count` field (increments on every press regardless of type) eliminates the "missed second press" problem even without MQTT.

#### Event attributes

| Attribute | Example | Description |
|---|---|---|
| `action` | `"single"`, `"double"`, `"hold"` | Press type reported by hub |
| `buttons_count` | `42` | Cumulative press counter (hub-side) |

#### Setting up button automations

**Option A — HA automation triggered by event entity (recommended):**

```yaml
automation:
  - alias: "Living room button single press → toggle lights"
    trigger:
      - platform: event
        event_type: state_changed
        # OR use the Event trigger:
      - platform: state
        entity_id: event.sinum_living_room_button
    condition:
      - condition: template
        value_template: "{{ trigger.to_state.attributes.event_type == 'pressed' }}"
    action:
      - service: light.toggle
        target:
          area_id: living_room
```

Better: use the **Event** trigger in the HA UI — navigate to **Settings → Automations → + New** and select "Sinum Button" as trigger entity. HA will offer you to select the press type.

```yaml
automation:
  - alias: "Button long press → scene Night"
    trigger:
      - platform: device
        domain: sinum
        device_id: !secret button_device_id
        type: pressed
        subtype: hold
```

**Option B — MQTT event (fastest, zero polling delay):**

The hub fires a `sinum_button_event` HA event (via `mqtt.py`'s `_handle_event`) for each button press, independently of coordinator polls. Use it in automations when latency matters:

```yaml
automation:
  - alias: "Button press via MQTT"
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

> This requires MQTT bridge enabled. See [MQTT Real-Time Bridge](#mqtt-real-time-bridge).

#### Eliminating the polling delay

The preferred method is **WebSocket** (no broker needed, hub firmware ≥ 0.5.x with `/api/v1/ws` support):

1. **Settings → Devices & Services → Sinum → Configure**
2. Enable **"Enable WebSocket real-time transport"**
3. Leave path as `/api/v1/ws` (default)
4. Click **Submit** — HA restarts the bridge automatically

Fallback: the legacy **MQTT bridge** still works for older hub firmware. See [MQTT Real-Time Bridge](#mqtt-real-time-bridge).

After enabling WebSocket: press a button and watch the HA event fire instantly in **Developer Tools → Events → Listen → `sinum_device_state_changed`**.

### Number

**Lua environment variables**: read/write numeric variables shared across Lua scripts. Use from HA automations to pass setpoints or trigger conditions to hub-side logic.

**SBUS Analog Output** (0–10 V): direct 0–100 range mapped to 0–10 V output.

---

## HA Services

### `sinum.send_notification`

Sends a push notification via the hub to the Sinum mobile app.

```yaml
service: sinum.send_notification
data:
  title: "Home Assistant"
  message: "The front door has been open for 10 minutes."
```

### `sinum.update_schedule`

Updates a Sinum thermal schedule via the hub API. Useful for dynamically changing heating programs from HA automations.

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

Optional `entry_id` field selects a specific hub when multiple Sinum integrations are loaded.

---

## Sinum Scenes, Automations and Variables

The Sinum hub executes Lua scripts in three contexts:

| Context | Trigger | HA exposure |
|---|---|---|
| **Scene** (`code` type) | Manual activation | `button` entity — press to activate |
| **Automation** | Hub event (time, device state) | Read-only sensor (`last_run`, `status`) |
| **Lua variable** | Persistent across executions | `number` entity — read and write from HA |

### Triggering a scene from HA

Any scene with type `code` appears as a `button` entity. Press it in the dashboard or call it from an automation:

```yaml
service: button.press
target:
  entity_id: button.sinum_close_all_blinds
```

The integration calls `POST /api/v1/scenes/{id}/activate`.

### Writing a variable from HA and reading it in Lua

**HA side** — set the variable via the `number` entity:
```yaml
service: number.set_value
target:
  entity_id: number.sinum_setpoint_bedroom
data:
  value: 22.5
```

**Lua side** — read the variable in a scene or automation:
```lua
local setpoint = variable[1]:getValue()
sbus[42]:setValue("target_temperature", setpoint * 10)  -- hub stores °C × 10
```

### Example: close all blinds at 22:00

Upload as a **Sinum Automation** (not a scene):

```lua
if event.type == "minute_changed" then
    if dateTime:getHours() == 22 and dateTime:getMinutes() == 0 then
        room[1]:foreach(function(device)
            if device:getValue("type") == "blind_controller" then
                device:setValue("position", 0)
            end
        end)
    end
end
```

### Example: read HA setpoint and apply to SBUS regulators

Upload as a **Sinum Scene** (activated from HA `button` entity):

```lua
local setpoint = variable[1]:getValue()
sbus[42]:setValue("target_temperature", setpoint * 10)
sbus[43]:setValue("target_temperature", setpoint * 10)
```

---

## WebSocket Real-Time Transport

WebSocket is the recommended real-time transport. No broker, no Lua script — the hub pushes events directly.

### How it works

The integration opens a persistent WebSocket connection to `/api/v1/ws` on the hub. The hub sends arrays of `device_state_changed` events whenever any device state changes. The integration iterates all events in each frame, patches only the changed field (`details`), and refreshes affected entities instantly — no waiting for the poll cycle.

```json
[
  {
    "data": {
      "type": "device_state_changed",
      "details": "humidity",
      "payload": { "class": "sbus", "id": 12, "humidity": 445 }
    }
  }
]
```

Supported buses: `virtual`, `wtp`, `sbus`, `lora`, `modbus`, `video`.

If the WS connection drops, the bridge reconnects after 5 s. REST polling (30 s default) continues in parallel as a reconciliation path.

### Setup

1. **Settings → Devices & Services → Sinum (Sinapse) → Configure**
2. Enable **"Enable WebSocket real-time transport"**
3. Path: `/api/v1/ws` (default — change only if your hub uses a different endpoint)
4. Click **Submit**

### Verifying WebSocket

Open **Developer Tools → Events → Listen to events** and type `sinum_device_state_changed`. Trigger any state change (toggle a switch, open a door, etc.) — the event should appear in under a second.

### Troubleshooting WebSocket

| Symptom | Likely cause |
|---|---|
| Entities still update at 30 s intervals | WS not enabled, or hub firmware doesn't support `/api/v1/ws` |
| `PermissionError: WebSocket unauthorized` in logs | API token invalid or expired — re-authenticate the integration |
| Frequent reconnects in logs | Hub WS connection is not stable — check hub firmware version |

---

## MQTT Real-Time Bridge (Legacy)

The MQTT bridge is the legacy real-time path. Use it only if your hub firmware doesn't support WebSocket. Requires a running MQTT broker (e.g. Mosquitto HA add-on).

**Priority:** the integration tries WebSocket first. Only if WebSocket is disabled does it fall back to MQTT.

### Architecture

```
Sinum Hub
  └── mqtt_bridge.lua (Automation, uploaded via sinum.upload_mqtt_bridge service)
        On any device state change:
        PUBLISH  {prefix}/state/{device_id}  ← full device JSON
        PUBLISH  {prefix}/event/heartbeat    ← every 60 s

MQTT Broker (e.g. Mosquitto add-on)
  │
  ▼
HA MQTT Integration
  └── Sinapse mqtt.py
        SUBSCRIBE {prefix}/state/+
        On message: update coordinator cache → refresh entities
```

### Step-by-step MQTT setup

#### Step 1 — Add an MQTT client on the hub

1. Open the Sinum web UI (e.g. `http://10.0.62.167`)
2. **Settings → System → Integrations → MQTT client → Add MQTT client**
3. Fill in broker IP, port `1883`, credentials
4. Save and note the assigned **Client ID** (e.g. `1`)

![Sinum add MQTT client](docs/images/setup/sinum-05-add-mqtt-client.png)

#### Step 2 — Upload the Lua bridge

Use the HA service **`sinum.upload_mqtt_bridge`** — no manual copy/paste needed:

```yaml
service: sinum.upload_mqtt_bridge
data:
  mqtt_scene_id: 1    # scene ID on the hub to overwrite (create one first)
  mqtt_client_id: 1   # MQTT client ID from Step 1
```

Or use the Developer Tools → Services UI. The service renders the Lua script and PATCHes it to the hub scene.

#### Step 3 — Enable MQTT in the HA integration

1. Settings → Devices & Services → find **Sinum (Sinapse)** → **Configure**
2. Enable **"MQTT real-time transport"**
3. Set **Topic prefix** to match the Lua script (default: `sinum`)
4. Click **Submit**

### MQTT topic reference

| Topic | Direction | Content |
|---|---|---|
| `{prefix}/state/{device_id}` | Hub → HA | Full device state JSON |
| `{prefix}/event/heartbeat` | Hub → HA | Heartbeat JSON, fires every 60 s |
| `{prefix}/event/{type}` | Hub → HA | Hub events (button_press, …) |

### MQTT troubleshooting

| Symptom | Likely cause |
|---|---|
| Entities still update at 30 s intervals | MQTT not enabled in options, or `TOPIC_PREFIX` mismatch |
| No log lines on hub | Lua automation disabled or MQTT client offline |
| `sinum_heartbeat` never fires | Lua running but broker unreachable |

---

## Development Guide

### Setup

```bash
git clone https://github.com/zaba848/sinapse-sinum-integration-for-home-assistant
cd sinapse-sinum-integration-for-home-assistant
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
```

### Running tests

```bash
pytest tests/                                       # 1460 tests, ~8 s
pytest -v tests/test_api.py                         # single file, verbose
pytest --cov=custom_components/sinum tests/         # coverage report
```

Run the cyclomatic complexity gate:

```bash
pytest tests/test_code_quality.py -v               # all functions must have CC ≤ 4
```

### Linting

```bash
ruff check custom_components/      # lint
ruff format custom_components/     # auto-format
```

Both are required to pass before merging (enforced by CI via `.github/workflows/lint.yml`).

### Project structure

```
custom_components/sinum/
  ├── __init__.py              Entry point: setup, reload, unload
  ├── api.py                   REST client (SinumClient, _read_json, error types)
  ├── coordinator.py           DataUpdateCoordinator — polls all buses
  ├── config_flow.py           UI setup + re-auth + options flow
  ├── const.py                 All constants (API paths, device types, defaults)
  │
  ├── climate.py               Thermostats, fan coils, regulators, heat pump manager
  ├── sensor.py                Sensor platform entry point
  ├── sensor_bus.py            WTP / SBUS / LoRa sensor entity classes (SinumSensor etc.)
  ├── sensor_bus_descriptions.py  Sensor description data (SinumSensorDescription + *_SENSORS tuples)
  ├── sensor_virtual.py        Virtual, weather, energy, hub diagnostic sensors
  ├── sensor_schedule.py       Thermal schedule sensors
  ├── binary_sensor.py         Flood, motion, opening, valve state, connectivity
  ├── switch.py                Relays, wicket, valve_pump, common_valve
  ├── cover.py                 Blind controller, gate
  ├── light.py                 Dimmer, RGB (virtual + WTP/SBUS)
  ├── button.py                Sinum scenes as HA buttons
  ├── event.py                 Button press events
  ├── number.py                Lua variables + SBUS analog output
  ├── notify.py                send_notification → hub push notification
  ├── update.py                Parent device firmware tracker
  ├── alarm_control_panel.py   Alarm system
  ├── websocket.py             WebSocket real-time transport (SinumWebSocketBridge)
  ├── mqtt.py                  MQTT legacy bridge transport
  ├── diagnostics.py           HA diagnostics (redacts credentials)
  │
  ├── services.yaml            Service schemas (send_notification, update_schedule)
  ├── strings.json             UI strings (EN)
  └── translations/
      ├── en.json
      └── pl.json

lua_scripts/
  ├── mqtt_bridge.lua          MQTT state bridge v0.8.1 — upload to hub
  └── sinapse_api.lua          Optional HTTP diagnostics endpoint on hub

tests/
  ├── fixtures/sinum_devices.json   Sample hub API payloads used by tests
  ├── conftest.py
  ├── test_code_quality.py     CC gate — all functions must have CC ≤ 4
  ├── hardware_in_loop/        HIL scripts for live hub testing
  └── test_*.py                1460 tests across all platforms and device types
```

### Key classes

**`SinumClient`** (`api.py`) — async HTTP client. One instance per coordinator. Handles:
- Auth: static `api_token` header, or JWT with `_refresh_jwt()` on 401
- Retry: one automatic retry on HTTP 408 (bus busy), after 1 s sleep
- Error surfacing: `SinumConnectionError` (network/timeout/JSON), `SinumAuthError` (credentials)
- `_read_json()`: reads raw bytes, handles empty body, raises `SinumConnectionError` on non-JSON

**`SinumCoordinator`** (`coordinator.py`) — extends `DataUpdateCoordinator`. On each poll:
1. Fetches rooms (for device ID lists and room metadata)
2. Fetches each bus collection in parallel with `_fetch_device_collection()`
3. On bulk endpoint failure: returns cached dict, entities stay alive
4. On per-device failure: logs warning, skips that device
5. Injects room name, floor name, parent hardware model into each device dict

**`SinumSensorDescription`** (`sensor_bus_descriptions.py`) — dataclass extending `SensorEntityDescription`. Extra fields:
- `source`: which bus (`"wtp"`, `"sbus"`, `"lora"`)
- `api_key`: key in the raw device dict
- `scale`: raw value multiplier (e.g. `0.1` for °C × 10)
- `zero_is_unavailable`: return `None` instead of `0.0` when raw value is zero

---

## Adding New Device Types

### 1. Sensor on an existing bus (WTP / SBUS / LoRa)

Add a `SinumSensorDescription` entry to the relevant tuple in `sensor_bus_descriptions.py`:

```python
# In WTP_SENSORS tuple (sensor_bus_descriptions.py)
SinumSensorDescription(
    key="pm2_5",                           # unique key within the device type
    api_key="pm2_5",                       # field name in the raw hub JSON
    source="wtp",
    wtp_type="air_quality_sensor",         # hub device type that has this field
    device_class=SensorDeviceClass.PM25,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement="µg/m³",
    scale=1.0,
    suggested_display_precision=0,
    # zero_is_unavailable=True,            # set if 0 means "no sensor"
),
```

No other changes needed — `sensor.py` imports `WTP_SENSORS` / `SBUS_SENSORS` / `LORA_SENSORS` from `sensor_bus_descriptions.py` (via re-export in `sensor_bus.py`) and creates entities automatically.

### 2. New entity platform for an existing device type

1. Create `custom_components/sinum/myplatform.py`
2. Define an entity class that extends the appropriate HA base (e.g. `SwitchEntity`)
3. Read data from `self.coordinator.wtp_devices[self._device_id]` (or `sbus_devices`, `virtual_devices`)
4. Write changes via `await self.coordinator.client.patch_wtp_device(id, payload)`
5. Register in `async_setup_entry`:

```python
# In __init__.py (or a dedicated setup function)
async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    entities = [
        MySinumEntity(coordinator, device_id, entry.entry_id)
        for device_id, device in coordinator.wtp_devices.items()
        if device.get("type") == "my_device_type"
    ]
    async_add_entities(entities)
```

6. Add the platform to `PLATFORMS` list in `__init__.py`

### 3. New virtual device type

Virtual devices live in `coordinator.virtual_devices`. Filter by `device.get("type")` in your `async_setup_entry`. Write via `coordinator.client.patch_virtual_device(id, payload)`.

### 4. MQTT real-time support for a new device

The MQTT bridge (`lua_scripts/mqtt_bridge.lua`) publishes full device state on any change. When the integration receives the message it calls `coordinator.async_set_updated_data()` with the merged device dict. No entity-side changes are needed — the `CoordinatorEntity` base class handles re-render automatically.

To add a new device type to the Lua bridge, add a handler in the `handle_*` section of `mqtt_bridge.lua`:

```lua
-- At the bottom of the dispatch table in mqtt_bridge.lua
["my_device_type"] = function(device)
    return {
        id      = device:getValue("id"),
        type    = device:getValue("type"),
        state   = device:getValue("state"),
        my_field = safe_get(device, "my_field"),
    }
end,
```

### 5. Writing tests

Tests live in `tests/test_*.py`. Use the shared `make_response()` helper from `test_api.py` / `test_api_extended.py` to mock hub responses:

```python
from unittest.mock import AsyncMock, MagicMock
import json as _json

def make_response(status: int, data: object = None) -> MagicMock:
    resp = MagicMock()
    resp.status = status
    _data = data if data is not None else {}
    resp.read = AsyncMock(return_value=_json.dumps(_data).encode())
    return resp
```

Mock the coordinator for entity tests:

```python
def _make_coordinator(virtual=None, wtp=None, sbus=None):
    c = MagicMock()
    c.virtual_devices = virtual or {}
    c.wtp_devices = wtp or {}
    c.sbus_devices = sbus or {}
    c.client = MagicMock()
    c.client.patch_virtual_device = AsyncMock(return_value={})
    return c
```

---

## Tested Hubs

Integration is tested against two live hubs in production:

| Hub | Model | API | Firmware | Virtual | WTP | SBUS |
|---|---|---|---|---|---|---|
| tablica-wtp | sinum_plus | 1.4 | 1.24.0-alpha.2 | 28 | 254 | 8 |
| sinum-tablica-sbus-1 | sinum_lite | 1.4 | 1.24.0-alpha.3 | 169 | 35 | 436 |

**tablica-wtp** — WTP-heavy installation: 108 WTP relays, 18 blind controllers, 15 temperature regulators, 28 buttons, temperature/humidity/CO₂/IAQ/pressure/light/motion/flood sensors, 1 fan coil, 1 energy meter.

**sinum-tablica-sbus-1** — SBUS-heavy installation: 83 virtual thermostats, 51 SBUS temperature regulators, 69 SBUS relays, 38 SBUS dimmers, 6 SBUS RGB controllers, 30 SBUS buttons, 134 SBUS temperature sensors, 46 SBUS humidity sensors, 1 heat pump manager. Total: 1497 HA entities (verified 2026-06-24).

> Both hubs run alpha firmware. The `/api/v1/rooms` and bus-list endpoints occasionally return HTTP 408 (bus timeout). The integration handles this gracefully by serving cached state until the next successful poll.

---

## Known Limitations

| Limitation | Notes |
|---|---|
| **SBUS button action type without MQTT** | SBUS hub resets `action` to `""` immediately after a press — by polling time it is gone. The press IS detected via `buttons_count`, but the event fires with `action=None`. WTP buttons keep `action` set until next press, so type is always available. For real-time action type on both buses, enable the MQTT bridge. |
| **`custom_device` virtual type** | Lua contracts vary per installation; not mapped to HA entities. Use scenes/automations to control them. |
| **`thermostat_output_group`** | Exposed as a disabled-by-default diagnostic sensor (output count), not as direct control entities. |
| **WTP RGB in temperature mode** | Hub firmware ignores color values when color-temperature mode is active; only `color_temp_kelvin` works. |
| **Virtual blind integrators** | Report `state = unknown` and `position = None` when no physical controllers are linked to them (hub configuration issue, not an integration bug). Position is tracked from `last_set_target_opening` (HA-issued commands) — manually-operated blinds may show stale position until the next HA command. |
| **Virtual gate position** | Gate open/close/opening/closing state is read from the hub `state` field. If the firmware does not return `state`, the entity shows "Unknown". Run `scripts/validate_v040_features.py` to survey gate fields on your hub. |
| **Thermostat without sensor** | Virtual thermostats with no assigned physical temperature sensor return `target_temperature = None` (displayed as "unavailable" in HA) rather than 0.0°C. This is correct behaviour — the hub returns 0 when no sensor is linked. |
| **Energy Center** | Diagnostics sensors appear only where the hub firmware exposes `/api/v1/energy-center/*` endpoints. |
| **Schedules** | Read-only sensors + `sinum.update_schedule` service. Full schedule editing UI is not implemented. |
| **LoRa / SLINK / Video** | Require specific hardware modules. Video streams and SLINK devices are not mapped to HA entities. |
| **Alpha firmware 408s** | Intermittent on bus polling; the integration retries once then uses cached state. |

## Security Best Practices

The Sinum hub communicates over plain HTTP on the local network. Follow these recommendations to reduce exposure:

### Network isolation
- Place the hub on a **dedicated IoT VLAN** separated from workstations and internet-facing services.
- Allow only Home Assistant to reach the hub's IP on port 80. Block direct internet access to the hub.
- If you expose Home Assistant to the internet (Nabu Casa, reverse proxy), ensure the Sinum hub is **not** reachable from the WAN.

### Authentication
- Prefer **API Token** authentication over username + password — the external integration token is scoped, doesn't grant shell access, and can be revoked in the Sinum web UI without changing your password.
- Use the **least-privilege token**: generate a dedicated token for the HA integration, not your admin credentials.
- Do not share the API token in bug reports, logs, or GitHub issues. The integration redacts it from diagnostics, but system logs may still capture it.

### TLS (optional)
- The hub does not natively support HTTPS. If you need encrypted communication, place an **nginx or Caddy reverse proxy** on the same VLAN that terminates TLS and forwards to the hub. Update the `host` field in the integration to the proxy address.

### Secrets management
- Never store credentials in YAML automations or templates. Use `secrets.yaml` or the HA Secrets manager.
- The integration stores the API token or password in the HA config entry (encrypted at rest by HA).

### Reauth protection
- The integration blocks reauth after **5 consecutive failures** for 5 minutes, preventing local brute-force attempts via the HA GUI.

---

## Rollback Procedure

If a release introduces a regression, rollback quickly:

1. Download the previous `sinum.zip` from GitHub Releases.
2. Replace `config/custom_components/sinum` with the older version.
3. Restart Home Assistant Core.
4. Verify integration setup, entity availability, and key automations.
5. Open an issue with logs and the exact version pair (from -> to).

For production environments, keep the previous two release zip files archived locally.

---

## License

**Source Available — Commercial Use Restricted**

© 2026 Tomasz Panek — All Rights Reserved.

Personal and non-commercial home automation use: **free**.
Business, organizational, or product deployment: **license required** — contact zaba9214@gmail.com.

See [LICENSE](LICENSE) for full terms.
