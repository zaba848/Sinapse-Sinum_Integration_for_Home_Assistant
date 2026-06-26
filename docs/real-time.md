# Real-Time Transports — Sinapse / Sinum Integration

**[← Back to README](../README.md)** · **[Polski](real-time.pl.md)**

---

Without a real-time transport, entity states update every 30 seconds (REST polling). The integration supports two push transports that reduce this to under 1 second.

| Transport | Latency | Requirements | Recommended |
|---|---|---|---|
| **WebSocket** | < 1 s | Hub firmware with `/api/v1/ws` | ✅ Yes |
| **MQTT bridge** | < 1 s | MQTT broker + Lua script on hub | Fallback only |
| REST polling | 30 s (default) | Always active | Safety net |

REST polling always runs in parallel as a reconciliation path — it catches anything missed by push transports.

---

## Contents

- [WebSocket Real-Time Transport](#websocket-real-time-transport)
- [MQTT Real-Time Bridge (Legacy)](#mqtt-real-time-bridge-legacy)

---

## WebSocket Real-Time Transport

WebSocket is the recommended transport. No broker, no Lua script — the hub pushes events directly over a persistent connection.

### How it works

The integration opens a persistent WebSocket connection to `/api/v1/ws` on the hub. The hub sends arrays of `device_state_changed` events whenever any device state changes. Each frame is processed immediately: only the changed field (`details`) is patched in the coordinator cache, and affected entities are refreshed instantly.

Example hub push payload:

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

If the connection drops, the bridge reconnects after 5 seconds automatically.

### Setup

1. Go to **Settings → Devices & Services** → find **Sinum (Sinapse)** → click **Configure**.
2. Enable **"Enable WebSocket real-time transport"**.
3. Leave path as `/api/v1/ws` (default — change only if your hub firmware uses a different endpoint).
4. Click **Submit**.

No restart required. The bridge connects immediately.

### Verifying WebSocket

Open **Developer Tools → Events → Listen to events** and type `sinum_device_state_changed`. Trigger any state change on the hub (toggle a switch, open a door, press a button). The event should appear in under a second.

### Troubleshooting WebSocket

| Symptom | Likely cause | Fix |
|---|---|---|
| Entities still update at 30 s intervals | WS not enabled, or hub firmware lacks `/api/v1/ws` | Check options, check hub firmware version |
| `PermissionError: WebSocket unauthorized` in logs | API token invalid or expired | Re-authenticate the integration |
| Frequent reconnects in logs | Hub WS connection unstable | Check hub firmware version, consider MQTT fallback |
| Events fire but state doesn't update | `details` field mismatch | Open a bug report with the raw event payload |

### WebSocket reconnect behavior

The bridge implements automatic reconnection with a 5-second delay. On reconnect, the coordinator performs an immediate full REST refresh to reconcile any state changes missed during the outage.

---

## MQTT Real-Time Bridge (Legacy)

Use the MQTT bridge only when WebSocket is not available on your hub firmware. It requires:

- A running MQTT broker (e.g., the Mosquitto add-on in HA)
- The `mqtt_bridge.lua` script uploaded to the Sinum hub

**Priority:** the integration tries WebSocket first. MQTT is only started if WebSocket is disabled in options.

### Architecture

```
Sinum Hub
  └── mqtt_bridge.lua (Automation, uploaded via sinum.upload_mqtt_bridge service)
        On any device state change:
        PUBLISH  {prefix}/state/{bus}/{device_id}   ← full device JSON
        PUBLISH  {prefix}/event/heartbeat           ← every 60 s
        PUBLISH  {prefix}/event/button_press        ← on button press

MQTT Broker (e.g., Mosquitto HA add-on)
  │
  ▼
HA MQTT Integration
  └── Sinapse mqtt.py
        SUBSCRIBE  {prefix}/state/+
        On message: patch coordinator cache → refresh entities instantly
```

### Step 1 — Add an MQTT client on the hub

Open the Sinum web UI (use your own hub IP/hostname):

**Settings → System → Integrations → MQTT client → Add MQTT client**

![Add MQTT client](images/setup/sinum-05-add-mqtt-client.png)

Configure:
- **Broker IP**: IP address of your HA host (where Mosquitto runs)
- **Port**: `1883`
- **Credentials**: as configured in Mosquitto
- Note the assigned **Client ID** (e.g. `1`)

### Step 2 — Upload the Lua bridge script

Use the HA service `sinum.upload_mqtt_bridge` — no manual editing needed. The service renders the Lua script and PATCHes it directly to the hub scene.

First, create an empty scene in Sinum (type: Automation or Scene) and note its ID. Then:

```yaml
service: sinum.upload_mqtt_bridge
data:
  mqtt_scene_id: 1    # ID of the scene to overwrite with the bridge script
  mqtt_client_id: 1   # MQTT client ID from Step 1
```

Optional parameters:

```yaml
service: sinum.upload_mqtt_bridge
data:
  entry_id: "01KV874N4F3B2W3ZPEXYFC3RVA"   # required only with multiple Sinum hubs
  mqtt_scene_id: 1
  mqtt_client_id: 1
  dry_run: true    # log the Lua script without uploading (for preview)
```

### Step 3 — Enable MQTT in the integration

1. Go to **Settings → Devices & Services → Sinum (Sinapse) → Configure**.
2. Enable **"Enable MQTT real-time transport"**.
3. Set **MQTT topic prefix** to match the Lua script (default: `sinum`).
4. Click **Submit**.

### MQTT topic reference

| Topic | Direction | Content |
|---|---|---|
| `{prefix}/state/{bus}/{device_id}` | Hub → HA | Full device state JSON |
| `{prefix}/event/heartbeat` | Hub → HA | Heartbeat (fires every 60 s) |
| `{prefix}/event/button_press` | Hub → HA | Button press event |

The heartbeat topic can be used in HA to detect if the Lua script has stopped running.

### MQTT troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Entities still update at 30 s intervals | MQTT not enabled in options, or topic prefix mismatch | Check options; verify `TOPIC_PREFIX` in Lua matches integration setting |
| No heartbeat for 2+ minutes | Lua automation stopped or MQTT client offline | Check Sinum automations list; check MQTT client status in Sinum |
| `sinum_heartbeat` never fires in HA | Broker unreachable from hub | Verify broker IP and credentials in Sinum MQTT client config |
| State updates arrive but wrong device | Topic routing issue | Check `mqtt_bridge.lua` version — use `sinum.upload_mqtt_bridge` to re-upload |

### Lua script version

The bundled Lua script is `mqtt_bridge.lua` v0.8.1. Always upload a fresh copy after updating the integration — the script format may change between versions.

```bash
# From the repo root
cat lua_scripts/mqtt_bridge.lua
```

Or call `sinum.upload_mqtt_bridge` with `dry_run: true` to preview the rendered Lua code without uploading.
