# Phase 7E Deployment Guide — Manual Setup

**Status**: Integration ready (75 tests passing), MQTT bridge v0.7.1 ready, documentation complete.

---

## Part 1: Install Sinum Integration on Home Assistant

### Step 1: Connect via SFTP or Web Terminal

Since SSH has permission issues, use HA's **Advanced SSH & Web Terminal** add-on or file editor:

1. Open HA web UI → Settings → System → Addons → "Advanced SSH & Web Terminal" (if not installed, install it first)
2. Click "Open Web Terminal" OR use SSH on different port (typically 22222)

### Step 2: Copy Integration Files

**Via Web Terminal:**
```bash
mkdir -p /config/custom_components/sinum
cd /config/custom_components
```

**Then upload all files from:** `/Users/tomaszpanek/Documents/Sinum_HomeAsistant_connector/custom_components/sinum/`

**OR via File Editor in HA:**
- Settings → Developer Tools → File Editor
- Create `/config/custom_components/sinum/` directory
- Upload each `.py` file, `manifest.json`, `strings.json`, `translations/` folder

### Step 3: Restart Home Assistant

```bash
ha core restart
```

Wait 2-3 minutes for restart to complete.

### Step 4: Add Integration

1. Settings → Devices & Services → Add Integration
2. Search for "Sinum (Sinapse)"
3. Configure:
   - **Hub IP**: `10.0.61.220` (your Sinum hub IP)
   - **Auth**: Choose API Token or Password
   - **Polling Interval**: 30 seconds (default)
4. Click "Create Integration"

**Expected**: Integration should connect and discover devices within 30 seconds.

---

## Part 2: Deploy Lua Scripts to Sinum Hub

### Prerequisites
- Sinum hub web UI access: `http://10.0.61.220` (adjust IP as needed)
- Sinum hub credentials (username/password or API token)
- MQTT broker configured in HA (Mosquitto add-on recommended)

### Step 2A: Configure MQTT in Sinum Hub

1. Open Sinum hub web UI → Integrations → Add MQTT Client
2. Enter MQTT broker details:
   - **Host**: `10.0.63.53` (HA IP from your network)
   - **Port**: `1883`
   - **Username**: `mosquitto` (if set in HA)
   - **Password**: Your MQTT password
3. Save and note the **MQTT Client ID** assigned (e.g., `1`, `2`, etc.)
4. Verify connection status shows "Connected"

### Step 2B: Upload MQTT Bridge Script

1. Sinum hub web UI → Settings → Lua Scripts → New Script
2. **Name**: `mqtt_bridge`
3. Copy entire content from: [`lua_scripts/mqtt_bridge.lua`](../../lua_scripts/mqtt_bridge.lua)
4. **CRITICAL**: Edit line 17:
   ```lua
   local CLIENT_ID = 1    -- Change to the ID from Step 2A
   ```
5. Save and Enable
6. Check hub logs (Settings → System → Logs):
   - Should see: `[Sinapse] MQTT bridge v0.7 started. Client ID: 1`
   - Should see: `[Sinapse] Published X virtual, Y wtp, Z sbus devices`

### Step 2C: Upload Lua API Extension (Optional)

1. Sinum hub web UI → Settings → Lua Scripts → New Script
2. **Name**: `sinapse_api`
3. Copy entire content from: [`lua_scripts/sinapse_api.lua`](../../lua_scripts/sinapse_api.lua)
4. Save and Enable
5. Check logs for: `[Sinapse API] v1.0 — endpoints registered`

### Step 2D: Enable MQTT in HA Integration

1. HA → Settings → Devices & Services → Sinum
2. Click Options gear icon
3. Toggle: "Enable MQTT real-time transport" → **ON**
4. Save

**Expected**: MQTT messages should now flow from Sinum hub to HA.

---

## Part 3: Verify Installation

### Check HA Integration Status

1. Settings → Devices & Services → Sinum
2. Should show device count: "X devices discovered"
3. Click through Entities tab to see all discovered entities

### Verify MQTT Messages

1. HA → Settings → Add-ons → Mosquitto → Logs
2. Look for connection from `sinum/state/*` topics

**OR** use MQTT client to subscribe:
```bash
mosquitto_sub -h 10.0.63.53 -t "sinum/#" -v
```

Should see messages like:
```
sinum/state/10 {"id":10,"type":"thermostat","name":"Living Room",...}
sinum/event/heartbeat {"ts":1718545200,"client_id":1}
```

### Check Sinum Hub Logs

1. Sinum hub web UI → Settings → System → Logs
2. Look for:
   - `[Sinapse] MQTT bridge v0.7 started`
   - `[Sinapse] Published X devices`
   - `[Sinapse] device_state_changed: device X`

---

## Part 4: Testing on Live System

### Test Device Discovery

1. HA → Developer Tools → States
2. Filter by `sinum_` to see all Sinum entities
3. Verify entity count matches hub device count

### Test MQTT Real-time Updates

1. Change a device on hub (e.g., turn on thermostat)
2. Check HA entity state updates within 1 second
3. Check hub logs for `device_state_changed` events

### Test Climate Control (SBUS Fan Coil)

1. HA → Developer Tools → Services
2. Service: `climate.set_temperature`
3. Entity: `climate.fan_coil_1` (or your SBUS fan coil)
4. Set temperature to 22°C
5. Check Sinum hub if value changed

### Test Scene Trigger (Optional)

1. HA → Developer Tools → Services
2. Service: `button.press`
3. Entity: `button.sinum_good_morning` (or your scene)
4. Verify scene executes on hub

---

## Troubleshooting

| Symptom | Solution |
|---------|----------|
| Integration won't load | Check manifest.json syntax, restart HA |
| No devices discovered | Verify hub IP/credentials, check HA logs |
| MQTT messages not flowing | Verify MQTT broker connected, check hub logs for script errors |
| Climate control not working | Verify SBUS fan coil has all required fields, test with REST API first |

---

## Files to Deploy

| File | Destination | Purpose |
|------|-------------|---------|
| `custom_components/sinum/*` | HA `/config/custom_components/sinum/` | Integration code |
| `lua_scripts/mqtt_bridge.lua` | Sinum hub Lua Scripts | Real-time state updates |
| `lua_scripts/sinapse_api.lua` | Sinum hub Lua Scripts | Diagnostics extension (optional) |

---

## Verification Checklist

- [ ] Integration installed on HA
- [ ] Devices discovered (count matches hub)
- [ ] MQTT bridge running on hub (check logs)
- [ ] MQTT messages flowing to HA (verify with mosquitto_sub)
- [ ] Climate entities show correct temperature
- [ ] Scene buttons trigger correctly
- [ ] HA logs show no integration errors

---

## Next: Phase 7F (If Needed)

After verification on live system:
1. Document device counts and entity mapping
2. Identify any missing entity types
3. Test Phase 7A (WTP fan coil) if not yet implemented
4. Prepare for HACS submission

---

**Questions?** Check logs on both HA and Sinum hub for error details.
