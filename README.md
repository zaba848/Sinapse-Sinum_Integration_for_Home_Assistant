# Sinapse — Sinum Integration for Home Assistant

**Sinapse** connects a TECH Sterowniki Sinum EH-01 hub to Home Assistant over the local network.

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg)](https://www.home-assistant.io)
[![Sinum API](https://img.shields.io/badge/Sinum%20API-1.4-informational)](https://www.techsterowniki.pl/baza-wiedzy-sinum)
[![License](https://img.shields.io/badge/License-Commercial-red.svg)](LICENSE)

The integration is local-first: REST polling is the baseline transport, with an optional Lua/MQTT bridge for lower-latency updates.

---

## Current Status

Verified on a real Sinum hub:

| Field | Value |
|---|---|
| Firmware | `1.24.0-alpha.1` |
| API | `1.4` |
| Lua manual | `v1.24.0`, rev. `2026-06-16` |
| Hub model | EH-01 / `sinum` |

The code now discovers devices from full class endpoints:

- `/api/v1/devices/virtual`
- `/api/v1/devices/wtp`
- `/api/v1/devices/sbus`

This matters because devices do not have to be assigned to rooms. `/api/v1/rooms` is used for area mapping and fallback discovery only.

---

## Supported Today

| Platform | Sinum sources |
|---|---|
| `climate` | Virtual thermostats |
| `sensor` | WTP temperature/humidity, WTP air/energy-style sensors where present, SBUS temperature/humidity, weather, hub uptime/Wi-Fi when available |
| `binary_sensor` | WTP flood/motion/opening/smoke/two-state inputs, SBUS two-state inputs, parent online/problem status |
| `switch` | Virtual relay integrator, wicket |
| `cover` | Virtual blind controller, gate |
| `light` | Virtual dimmer/RGB controller |
| `button` | Sinum scenes/scripts via `PATCH /api/v1/scenes/{id}` |
| `number` | Numeric Lua variables |
| `update` | Parent device firmware status |

Not yet production-ready:

- WTP/SBUS fan coil climate entities
- WTP temperature regulator climate entities
- Thermal schedule entities
- TECH RS, Modbus heat pump, Energy Center, LoRa, SLINK, cameras

See [PLAN.md](PLAN.md) for the detailed roadmap and verified device counts.

---

## Installation

### HACS

1. HACS -> Integrations -> three-dot menu -> **Custom repositories**
2. Add this repository as category **Integration**
3. Install **Sinapse**
4. Restart Home Assistant

### Manual

```bash
cd /config
cp -r /path/to/ha-sinapse/custom_components/sinum custom_components/
```

Restart Home Assistant.

---

## Configuration

Go to **Settings -> Devices & Services -> Add Integration -> Sinum (Sinapse)**.

Recommended authentication:

| Method | Notes |
|---|---|
| API token | Preferred. Static token created in Sinum app settings. |
| Username/password | Supported. Integration logs in and refreshes session JWT. |

The integration sends authorization as:

```text
Authorization: Bearer <token>
```

Do not commit API tokens, passwords, exported diagnostics with secrets, or local test credentials.

---

## Optional MQTT

MQTT is optional. REST polling works without it.

To enable real-time updates:

1. Configure an MQTT broker in Home Assistant, for example Mosquitto.
2. In Sinum, add an MQTT client pointing to the broker.
3. Upload [`lua_scripts/mqtt_bridge.lua`](lua_scripts/mqtt_bridge.lua) to the Sinum Lua scripts panel.
4. Set the Lua `CLIENT_ID` to the ID assigned by Sinum.
5. Enable MQTT in the integration options.

Current topic layout:

| Topic | Direction |
|---|---|
| `sinum/state/{device_id}` | Sinum -> HA state updates |
| `sinum/event/{type}` | Sinum -> HA events |
| `sinum/cmd/{device_id}` | HA -> Sinum commands |

The bridge still needs a hardening pass before relying on it for critical control paths. REST remains the supported baseline.

---

## Optional Lua HTTP Extension

[`lua_scripts/sinapse_api.lua`](lua_scripts/sinapse_api.lua) can expose extra hub diagnostics, especially Wi-Fi details not returned by regular REST `/api/v1/info` on every firmware build.

Expected endpoint:

```text
GET /api/v1/lua/http-server/sinapse/info
```

The integration treats this as best-effort. If the script is not installed, setup continues normally.

---

## Verified REST Endpoints

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/login` | Password login |
| `POST /api/v1/refresh` | Refresh JWT |
| `GET /api/v1/info` | Hub info |
| `GET /api/v1/rooms` | Rooms and room device references |
| `GET /api/v1/floors` | Floors for suggested areas |
| `GET /api/v1/parent-devices` | Bus/module health |
| `GET /api/v1/devices/virtual` | Virtual devices |
| `GET /api/v1/devices/wtp` | WTP devices |
| `GET /api/v1/devices/sbus` | SBUS devices |
| `GET/PATCH /api/v1/devices/virtual/{id}` | Virtual device read/write |
| `GET/PATCH /api/v1/devices/sbus/{id}` | SBUS device read/write |
| `GET /api/v1/scenes` | Scenes and Lua code scripts |
| `PATCH /api/v1/scenes/{id}` | Trigger scene/script with `{"trigger": true}` |
| `GET /api/v1/schedules` | Thermal schedules and temperature curves |
| `GET /api/v1/weather` | Weather payload |
| `GET /api/v1/devices/alarm-system` | Alarm panels, empty on verified hub |

`/api/v1/energy` returned `404` on the verified hub, so Energy Center support remains future work.

---

## Development

```bash
pip install -r requirements-dev.txt
pytest tests/
ruff check custom_components/sinum/
python3 -m compileall custom_components/sinum tests
```

---

## Roadmap

Immediate next work:

1. Implement fan coil `climate` entities for WTP `fan_coil`, WTP `fan_coil_v2`, and SBUS `fan_coil`.
2. Add schedule sensors for thermal schedules and temperature curves.
3. Decide whether WTP `temperature_regulator` should be exposed as climate entities or thermostat attributes.
4. Harden the Lua MQTT bridge with safe `getValue()` snapshots and initial publishes for virtual/WTP/SBUS devices.
5. Run the full test suite after installing dev dependencies.

Detailed plan: [PLAN.md](PLAN.md).

---

## License

**Source Available — Commercial Use Restricted**

© 2026 Tomasz Panek — All Rights Reserved.

| Use case | Allowed |
|---|---|
| Personal home automation, non-commercial | Yes |
| Business / organization deployment | License required |
| Integration into a paid product or service | License required |
| Resale or redistribution | License required |

Commercial license: **zaba9214@gmail.com**  
See [LICENSE](LICENSE) for full terms.
