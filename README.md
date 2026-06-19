# Sinapse — Sinum Integration for Home Assistant

**Sinapse** connects a TECH Sterowniki Sinum hub to Home Assistant over the local network.

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg)](https://www.home-assistant.io)
[![Tests](https://img.shields.io/badge/tests-880%20passing-brightgreen.svg)](tests/)
[![Coverage](https://img.shields.io/badge/coverage-98%25-brightgreen.svg)](tests/)
[![Sinum API](https://img.shields.io/badge/Sinum%20API-1.4-informational)](https://apidocs.sinum.tech)

Local-first integration: REST polling is the baseline, with an optional Lua/MQTT bridge for lower-latency real-time updates.

---

## Supported Entities

| Platform | Description | Status |
|---|---|---|
| `climate` | Virtual thermostats, SBUS/WTP fan coils, SBUS/WTP temperature regulators, heat pump manager | ✅ |
| `sensor` | Temperature, humidity, illuminance, CO₂, pressure, PM, IAQ, power, energy, voltage, current, weather, hub diagnostics, Energy Center diagnostics, automation status, thermal schedule summaries, SBUS regulator target temp | ✅ |
| `binary_sensor` | Flood, motion, opening, smoke, two-state input, WTP fan coil valve state, parent device connectivity | ✅ |
| `switch` | Virtual relay integrators, wicket (electric strike), WTP/SBUS physical relays, valve_pump, common_valve | ✅ |
| `cover` | Virtual blind controller, gate, WTP blind controller | ✅ |
| `light` | Virtual dimmer/RGB, WTP/SBUS dimmer, WTP/SBUS RGB controller | ✅ |
| `event` | Button press event — fires per action, ideal for HA automations | ✅ |
| `button` | Sinum scenes (Lua `code` type) and Lua code scripts | ✅ |
| `number` | Numeric Lua environment variables, SBUS analog output (0–10 V) | ✅ |
| `update` | Parent device firmware tracker | ✅ |
| `alarm_control_panel` | Alarm system (if present on hub) | ✅ |

### Supported Device Types

**Virtual devices**: `thermostat`, `relay_integrator`, `blind_controller_integrator`, `gate`, `wicket`, `dimmer_rgb_controller_integrator`, `dimmer_rgb_integrator`, `heat_pump_manager`, `thermostat_output_group` diagnostics

**WTP bus**: `temperature_sensor`, `humidity_sensor`, `pressure_sensor`, `light_sensor`, `co2_sensor`, `iaq_sensor`, `aq_sensor`, `motion_sensor`, `flood_sensor`, `opening_sensor`, `smoke_sensor`, `two_state_input_sensor`, `relay`, `dimmer`, `rgb_controller`, `blind_controller`, `energy_meter`, `fan_coil`, `fan_coil_v2`, `temperature_regulator`, `button`

**SBUS bus**: `temperature_sensor`, `humidity_sensor`, `light_sensor`, `motion_sensor`, `two_state_input_sensor`, `analog_input`, `analog_output`, `impulse_meter`, `relay`, `dimmer`, `rgb_controller`, `fan_coil`, `temperature_regulator`, `button`, `valve_pump`, `common_valve`, `pulse_width_modulation`, `blind_controller`, `energy_meter`

**LoRa bus**: `temperature_sensor`, `humidity_sensor`, `opening_sensor`, `flood_sensor`, `relay`, `two_state_input_sensor`, `smoke_sensor`

---

## Installation

### HACS (recommended)

1. HACS → Integrations → three-dot menu → **Custom repositories**
2. Add `https://github.com/zaba848/Sinum_HomeAsistant_connector` as category **Integration**
3. Find and install **Sinapse**
4. Restart Home Assistant

### Manual

```bash
cp -r custom_components/sinum /config/custom_components/
```

Restart Home Assistant.

---

## Configuration

**Settings → Devices & Services → Add Integration → Sinum (Sinapse)**

| Auth method | Notes |
|---|---|
| API Token (recommended) | Static token from Sinum app → Settings → Integrations → API Tokens |
| Username + password | Standard login; integration manages JWT refresh automatically |

The polling interval defaults to 30 seconds and can be changed in integration options.

---

## Sinum Scenes and Automations

Sinum hubs can run Lua scripts in three modes: **scenes** (single-shot actions), **automations** (event-driven), and **custom devices**. Sinapse exposes scenes as `button` entities in Home Assistant — pressing the button activates the scene via `POST /api/v1/scenes/{id}/activate`.

This makes it easy to trigger hub-side logic from HA automations, dashboards, or voice assistants, without duplicating logic on the HA side.

**Example scene (all WTP blinds down at a specific time):**

```lua
-- Automation script: close all WTP blind controllers at 22:00
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

**Environment variables** (persistent across executions) are exposed as `number` entities, so HA can read and write them:

```lua
-- Scene: read setpoint from HA-writable variable and apply to regulators
local setpoint = variable[1]:getValue()
sbus[42]:setValue("target_temperature", setpoint * 10)  -- Sinum stores °C × 10
```

---

## Optional MQTT Real-Time Updates

MQTT is optional — REST polling (30 s default) works without it. With MQTT the hub pushes state changes immediately, so your entities update in under a second instead of at the next poll.

### How it works

The Lua script `mqtt_bridge.lua` runs on the hub as an automation. Whenever a device state changes it publishes a JSON payload to `{prefix}/state/{device_id}`. The HA integration subscribes, updates the coordinator data in-place, and refreshes entities — no REST poll needed for those updates.

### Prerequisites

- **MQTT broker** reachable from both HA and the Sinum hub (e.g. Mosquitto HA add-on)
- **Home Assistant MQTT integration** configured (Settings → Devices & Services → MQTT)

### Step-by-step setup

**Step 1 — Add an MQTT client on the hub**

1. Open the Sinum web UI (e.g. `http://10.0.61.132` or sinum.local)
2. Go to **Settings → System → Integrations → MQTT**
3. Click **Add** and fill in:
   - **Host**: IP address of your MQTT broker (e.g. `10.0.0.5` for example in Home Asistant)
   - **Port**: `1883` (or `8883` for TLS)
   - **Username / Password**: as configured in your broker
4. Save and note the assigned **Client ID** (e.g. `1`)

**Step 2 — Upload the Lua bridge script**

1. Open the Sinum web UI → **Automations → New** (+ button, top right)
2. Set a name, e.g. `mqtt_bridge`
3. Paste the full contents of [`lua_scripts/mqtt_bridge.lua`](lua_scripts/mqtt_bridge.lua)
4. At the top of the script, set:
   ```lua
   local CLIENT_ID    = 1          -- MQTT client ID from Step 1
   local TOPIC_PREFIX = "sinum"    -- must match HA integration option
   ```
5. Click **Save** and enable the automation

The script publishes the full device state on every change:

```lua
-- excerpt from mqtt_bridge.lua
mqtt[CLIENT_ID]:publish(
    TOPIC_PREFIX .. "/state/" .. tostring(device_id),
    json.encode(payload)
)
```

**Multiple hubs**: use a unique `TOPIC_PREFIX` per hub (e.g. `sinum/hub1` and `sinum/hub2`) so messages don't cross between integrations.

**Step 3 — Enable MQTT in the HA integration**

1. Settings → Devices & Services → find your **Sinum (Sinapse)** entry
2. Click **Configure** (three dots → Configure)
3. Enable **"MQTT real-time transport"**
4. Set **Topic prefix** to match the `TOPIC_PREFIX` in your Lua script
5. Click **Submit**

### Verifying it works

- Check hub logs (Sinum web UI → Logs) for lines like `[Sinapse] Published: sinum/state/42`
- In HA → Developer Tools → Events, listen for `sinum_heartbeat` — should fire every minute
- Toggle a relay and watch the HA entity update instantly (no 30 s delay)

### MQTT topics

| Topic | Direction | Content |
|---|---|---|
| `{prefix}/state/{device_id}` | Hub → HA | Full device state JSON with `source` field |
| `{prefix}/event/heartbeat` | Hub → HA | Heartbeat JSON every 60 s |
| `{prefix}/event/{type}` | Hub → HA | Any hub event (button_press, scene_activated, …) |

The `source` field in state payloads (`"virtual"`, `"wtp"`, `"sbus"`, `"lora"`) tells HA which device store to update. Payloads without `source` are treated as virtual devices.

### Troubleshooting

| Symptom | Likely cause |
|---|---|
| Entities still updating at 30 s intervals | MQTT not enabled in integration options, or `TOPIC_PREFIX` mismatch |
| No `[Sinapse] Published:` in hub logs | Lua automation disabled or MQTT client offline |
| HA MQTT integration not configured | Go to Settings → Devices & Services → Add integration → MQTT |
| `sinum_heartbeat` event never fires | Script running but MQTT client not connected to broker |

---

## Tested Hubs

Integration is tested against two live hubs running different hardware configurations:

| Hub | Model | API | Firmware | Virtual | WTP | SBUS |
|---|---|---|---|---|---|---|
| tablica-wtp | sinum_plus | 1.4 | 1.24.0-alpha.2 | 28 | 254 | 8 |
| sinum-tablica-sbus-1 | sinum_lite | 1.4 | 1.24.0-alpha.3 | 169 | 35 | 436 |

**tablica-wtp** is WTP-heavy: 108 WTP relays, 18 blind controllers, 15 temperature regulators, 28 buttons, assorted sensors (temperature, humidity, CO₂, IAQ, pressure, light, motion, flood), 1 fan coil, 1 energy meter.

**sinum-tablica-sbus-1** is SBUS-heavy: 83 virtual thermostats, 51 SBUS temperature regulators, 69 SBUS relays, 38 SBUS dimmers, 6 SBUS RGB controllers, 30 SBUS buttons, 134 SBUS temperature sensors, 46 SBUS humidity sensors, 1 heat pump manager.

**Note**: Both hubs run alpha firmware. The `/api/v1/rooms` and bus-list endpoints occasionally return HTTP 408 (bus timeout) — the integration handles this gracefully using cached data.

---

## Development

### Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
```

### Tests

```bash
pytest tests/           # 880 tests, ~3 s
pytest -v tests/        # verbose
pytest --cov=custom_components/sinum tests/  # with coverage (98%)
```

### Structure

```
custom_components/sinum/
  ├── __init__.py
  ├── api.py               # REST client (SinumClient) — aiohttp, JWT refresh
  ├── coordinator.py       # DataUpdateCoordinator — polls all bus endpoints
  ├── config_flow.py       # UI setup + reauth flow
  ├── climate.py           # Thermostats, fan coils, regulators, heat_pump_manager
  ├── sensor.py            # Sensor platform setup
  ├── sensor_bus.py        # WTP/SBUS/LoRa sensors
  ├── sensor_virtual.py    # Virtual, weather, energy, hub diagnostic sensors
  ├── sensor_schedule.py   # Thermal schedule sensors
  ├── binary_sensor.py     # Flood, motion, opening, valve state, connectivity
  ├── switch.py            # Relay integrators, wicket, WTP/SBUS relays, valve_pump, common_valve
  ├── cover.py             # Blind controller, gate (virtual + WTP)
  ├── light.py             # Dimmer/RGB (virtual + WTP/SBUS)
  ├── button.py            # Scenes (Lua code type)
  ├── event.py             # Button press events (SinumButtonEvent)
  ├── number.py            # Lua environment variables + SBUS analog_output
  ├── notify.py            # send_notification service → hub push notification
  ├── update.py            # Parent device firmware tracker
  ├── alarm_control_panel.py
  ├── diagnostics.py       # HA diagnostics redaction
  ├── mqtt.py              # MQTT bridge transport
  ├── services.yaml        # send_notification and update_schedule service schemas
  ├── strings.json         # UI strings (EN)
  └── translations/
      ├── en.json
      └── pl.json

lua_scripts/
  ├── mqtt_bridge.lua      # MQTT state bridge (v0.8.1) — upload to hub
  └── sinapse_api.lua      # Optional HTTP diagnostics endpoint on hub

tests/
  ├── fixtures/sinum_devices.json
  └── test_*.py            # 880 tests across all platforms and device types
```

---

## Known Limitations

- `button` devices — exposed as `last_action` sensor (disabled by default); for real-time triggers use the **Event entity** with MQTT bridge enabled
- `custom_device` virtual type — Lua contracts vary per installation, intentionally not mapped to HA entities; scene/automation Lua details are available through read-only API helpers
- `thermostat_output_group` virtual type — exposed as a disabled-by-default diagnostic output-count sensor, not as direct control entities
- Energy Center differs by firmware — legacy `/api/v1/energy` sensors and `/api/v1/energy-center/*` diagnostics appear only where the hub exposes those endpoints
- Schedules support read-only sensors and the explicit `sinum.update_schedule` service; full schedule editing UI is not implemented
- LoRa, SLINK, video cameras require specific hardware modules installed on the hub; video streams and SLINK devices are not mapped to HA entities yet
- Hub alpha firmware may cause intermittent HTTP 408 on bus polling — handled gracefully with cached state

---

## License

**Source Available — Commercial Use Restricted**

© 2026 Tomasz Panek — All Rights Reserved.

Personal/non-commercial home automation: **allowed**.  
Business, organizational, or product deployment: **license required** — contact zaba9214@gmail.com.

See [LICENSE](LICENSE) for full terms.
