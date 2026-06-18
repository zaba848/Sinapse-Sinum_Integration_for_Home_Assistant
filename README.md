# Sinapse — Sinum Integration for Home Assistant

**Sinapse** connects a TECH Sterowniki Sinum hub to Home Assistant over the local network.

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg)](https://www.home-assistant.io)
[![Tests](https://img.shields.io/badge/tests-865%20passing-brightgreen.svg)](tests/)
[![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen.svg)](tests/)
[![Sinum API](https://img.shields.io/badge/Sinum%20API-1.4-informational)](https://apidocs.sinum.tech)

Local-first integration: REST polling is the baseline, with an optional Lua/MQTT bridge for lower-latency real-time updates.

---

## Supported Entities

| Platform | Description | Status |
|---|---|---|
| `climate` | Virtual thermostats, SBUS/WTP fan coils, SBUS/WTP temperature regulators, heat pump manager | ✅ |
| `sensor` | Temperature, humidity, illuminance, CO₂, pressure, PM, IAQ, power, energy, voltage, current, weather, hub diagnostics, thermal schedule summaries, SBUS regulator target temp | ✅ |
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

**Virtual devices**: `thermostat`, `relay_integrator`, `blind_controller_integrator`, `gate`, `wicket`, `dimmer_rgb_controller_integrator`, `dimmer_rgb_integrator`, `heat_pump_manager`

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

MQTT is optional — REST polling is fully supported without it. With MQTT the hub pushes state changes immediately instead of waiting for the next poll cycle.

### Prerequisites

- MQTT broker configured in Home Assistant (e.g. Mosquitto add-on)
- Sinum hub can reach the MQTT broker on the local network

### Setup

**1. Add MQTT client on hub**

Open Sinum hub web UI → Integrations → Add MQTT client. Note the assigned **Client ID**.

**2. Upload Lua bridge script**

Sinum hub web UI → Settings → Lua Scripts → New script.  
Paste contents of [`lua_scripts/mqtt_bridge.lua`](lua_scripts/mqtt_bridge.lua).  
Set `CLIENT_ID = <id from step 1>`, save and enable.

The script publishes the full device state JSON every time a device property changes:

```lua
-- excerpt from mqtt_bridge.lua
mqtt[CLIENT_ID]:publish(
    TOPIC_PREFIX .. "/state/" .. tostring(device_id),
    json.encode(payload)
)
```

For multiple Sinum hubs connected to the same MQTT broker, set a unique `TOPIC_PREFIX` in each Lua script — for example `sinum/tablica-wtp` and `sinum/tablica-sbus-1` — and use the same prefix in the integration options for that hub.

Verify by checking hub logs for `[Sinapse] Published:` entries.

**3. Enable in HA**

Sinum integration → Options → Enable MQTT real-time transport → Save.

### MQTT Topics

| Topic | Direction | Content |
|---|---|---|
| `{topic_prefix}/state/{device_id}` | Hub → HA | Full device state JSON |
| `{topic_prefix}/event/heartbeat` | Hub → HA | Heartbeat every minute |

Default `topic_prefix` is `sinum`.

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
pytest tests/           # 865 tests, ~3 s
pytest -v tests/        # verbose
pytest --cov=custom_components/sinum tests/  # with coverage (100%)
```

### Structure

```
custom_components/sinum/
  ├── __init__.py
  ├── api.py               # REST client (SinumClient) — aiohttp, JWT refresh
  ├── coordinator.py       # DataUpdateCoordinator — polls all bus endpoints
  ├── config_flow.py       # UI setup + reauth flow
  ├── climate.py           # Thermostats, fan coils, regulators, heat_pump_manager
  ├── sensor.py            # Temperature, humidity, IAQ, energy, weather, schedules, PWM
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
  ├── services.yaml        # send_notification service schema
  ├── strings.json         # UI strings (EN)
  └── translations/
      ├── en.json
      └── pl.json

lua_scripts/
  ├── mqtt_bridge.lua      # MQTT state bridge (v0.8.1) — upload to hub
  └── sinapse_api.lua      # Optional HTTP diagnostics endpoint on hub

tests/
  ├── fixtures/sinum_devices.json
  └── test_*.py            # 865 tests across all platforms and device types
```

---

## Known Limitations

- `button` devices — exposed as `last_action` sensor (disabled by default); for real-time triggers use the **Event entity** with MQTT bridge enabled
- `custom_device` virtual type — Lua contracts vary per installation, intentionally not mapped to HA entities
- `thermostat_output_group` virtual type — hub-managed output group, no direct HA mapping
- Energy Center (`/api/v1/energy`) not available on all hubs — entities will not appear where missing
- LoRa, SLINK, video cameras require specific hardware modules installed on the hub
- Hub alpha firmware may cause intermittent HTTP 408 on bus polling — handled gracefully with cached state

---

## License

**Source Available — Commercial Use Restricted**

© 2026 Tomasz Panek — All Rights Reserved.

Personal/non-commercial home automation: **allowed**.  
Business, organizational, or product deployment: **license required** — contact zaba9214@gmail.com.

See [LICENSE](LICENSE) for full terms.
