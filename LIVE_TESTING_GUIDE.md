# Live Testing on Real Hub — Complete Guide

**Your Credentials:**
- Hub: http://10.0.61.220
- Admin: admin / adminTablica
- API Token: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...` (provided)

---

## Step 1: Test Hub Connectivity & Device Discovery

Run this on your local network (where the hub is accessible):

```bash
# From the repo root directory
python3 test_live_hub.py
```

**Expected Output:**
```
🧪 SINUM HUB LIVE API TEST SUITE
================================================

✅ Hub Info
   Name: sinumTablicaDomin
   Firmware: 1.24.0-alpha.1
   API: 1.4

✅ Virtual Devices: 8 found
   1. Thermostat (thermostat)
   2. Ceiling Light (dimmer_rgb_controller_integrator)
   ...

✅ WTP Devices: 12 found
   1. Fan Coil (fan_coil)
   ...

✅ SBUS Devices: 5 found
   ...

📊 Device Count:
   Virtual: 8
   WTP: 12
   SBUS: 5
   Total: 25
```

---

## Step 2: Upload MQTT Bridge to Hub

### Manual Upload (Recommended)

1. Open hub web UI: http://10.0.61.220
2. Login as: admin / adminTablica
3. Navigate to: **Settings → Integrations → Add MQTT Client**
   - Host: `10.0.63.53` (your HA IP or MQTT broker)
   - Port: `1883`
   - Username: `mosquitto` (or your MQTT username)
   - Password: Your MQTT password
   - **Save and note the MQTT Client ID** (e.g., `1`, `2`)

4. Navigate to: **Settings → Lua Scripts → New Script**
   - Name: `mqtt_bridge`
   - Paste entire content from: `lua_scripts/mqtt_bridge.lua`
   - **CRITICAL:** Edit line 17 to match MQTT Client ID:
     ```lua
     local CLIENT_ID = 1    -- Change to your client ID from above
     ```
   - Click **Save**
   - Click **Enable**

5. Check logs: **Settings → System → Logs**
   - Look for: `[Sinapse] MQTT bridge v0.7 started. Client ID: 1`
   - Look for: `[Sinapse] Published X virtual, Y wtp, Z sbus devices`

---

## Step 3: Verify MQTT Message Flow

### Option A: Using `mosquitto_sub` (if installed)

```bash
# From your local network
mosquitto_sub -h 10.0.63.53 -t "sinum/#" -v
```

Should see messages like:
```
sinum/state/10 {"id":10,"type":"thermostat","name":"Living Room",...}
sinum/state/20 {"id":20,"type":"temperature_sensor",...}
sinum/event/heartbeat {"ts":1718545200,"client_id":1}
sinum/event/heartbeat {"ts":1718545260,"client_id":1}
```

### Option B: Check HA MQTT Integration

1. Home Assistant → Settings → Add-ons → Mosquitto → Logs
2. Look for MQTT client connections from hub IP (10.0.61.220)

### Option C: Check Sinum Hub Logs

1. Hub web UI → Settings → System → Logs
2. Look for:
   ```
   [Sinapse] MQTT bridge v0.7 started
   [Sinapse] Published 8 virtual, 12 wtp, 5 sbus devices
   [Sinapse] device_state_changed: device 10
   ```

---

## Step 4: Test Device State Changes

### Change 1: Modify Thermostat

1. Hub web UI → Find a thermostat device
2. Change temperature (e.g., from 20°C to 22°C)
3. Check MQTT messages:
   ```bash
   mosquitto_sub -h 10.0.63.53 -t "sinum/state/10" -v
   # Should see: sinum/state/10 {"...","temperature":220,...}
   ```
4. Check hub logs:
   ```
   [Sinapse] device_state_changed: device 10
   ```

### Change 2: Toggle a Relay

1. Hub web UI → Find a relay device
2. Turn it on/off
3. Monitor MQTT for state change:
   ```bash
   mosquitto_sub -h 10.0.63.53 -t "sinum/state/#" | grep relay
   ```

---

## Step 5: Test HA Integration Discovery

1. Home Assistant → Settings → Devices & Services → Add Integration
2. Search for "Sinum (Sinapse)"
3. Configure:
   - **Hub IP**: 10.0.61.220
   - **Auth**: API Token (paste the long token provided)
   - **Polling Interval**: 30 seconds
4. Click "Create Integration"

**Expected:** Integration discovers 25 devices within 30 seconds

---

## Step 6: Verify HA Entities

1. Home Assistant → Developer Tools → States
2. Filter by `sinum_` prefix
3. You should see:
   - `climate.fan_coil_*` (SBUS fan coils)
   - `climate.living_room_thermostat` (virtual thermostats)
   - `sensor.sinus_temp_*` (temperature sensors)
   - `sensor.sinus_humidity_*` (humidity sensors)
   - `binary_sensor.sinus_motion_*` (two-state inputs)
   - `switch.sinus_relay_*` (relays)
   - And more...

**Expected count**: ~25 entities matching your device count

---

## Step 7: Test Climate Control (SBUS Fan Coil)

1. HA → Developer Tools → Services
2. Service: `climate.set_temperature`
3. Entity: `climate.fan_coil_1` (or your SBUS fan coil)
4. Temperature: `22` (°C)
5. Click "Call Service"

**Expected:**
- HA shows temperature in climate card
- Hub receives command (check logs)
- Verify in MQTT: `sinum/state/<device_id>` shows new temperature

---

## Troubleshooting

### Hub Not Reachable
```bash
ping 10.0.61.220
# Should see responses; if not, check network/firewall
```

### MQTT Bridge Not Starting
1. Check CLIENT_ID matches hub's configured MQTT client ID
2. Verify MQTT client connection in hub UI
3. Check hub logs for errors

### No MQTT Messages
1. Verify MQTT broker is running
2. Check hub MQTT client connection status
3. Ensure firewall allows port 1883
4. Verify CLIENT_ID is correct

### Devices Not Discovered in HA
1. Check HA logs for Sinum integration errors
2. Verify API token is correct
3. Verify hub IP is reachable from HA network
4. Check REST API response: `curl -H "Authorization: Bearer <token>" http://10.0.61.220/api/v1/info`

---

## Files Needed

Copy these files from repo to your test environment:

```bash
lua_scripts/mqtt_bridge.lua        # Upload to hub Lua Scripts
lua_scripts/sinapse_api.lua        # Optional: Upload for diagnostics
test_live_hub.py                   # Run for connectivity test
custom_components/sinum/*          # Copy to HA /config/custom_components/
```

---

## Live Testing Checklist

- [ ] Hub responds to API requests
- [ ] Device count matches PLAN.md (Virtual: 8, WTP: 12+, SBUS: 5)
- [ ] MQTT bridge starts on hub (check logs)
- [ ] MQTT messages flowing to broker
- [ ] HA integration discovers 25+ devices
- [ ] Temperature change on hub updates MQTT
- [ ] HA climate entity temperature can be set
- [ ] Hub logs show device_state_changed events

---

## Next: Report Results

After testing, document:
1. Device counts from `test_live_hub.py`
2. MQTT message flow (screenshot or log)
3. HA integration entity count
4. Any errors or issues encountered

Then we can:
- [ ] Verify everything matches expected behavior
- [ ] Fix any integration issues
- [ ] Document for next phases (7A, 7B, 7C)
- [ ] Prepare for HACS submission

