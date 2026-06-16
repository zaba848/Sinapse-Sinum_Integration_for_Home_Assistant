-- Sinapse MQTT Bridge v0.3 (Hardened)
-- Upload this script to the Sinum hub:
--   Settings → Lua Scripts → New Script → paste this code → Save → Enable
--
-- Prerequisites:
--   1. Sinum hub: Integrations → Add MQTT client → point to your HA Mosquitto broker
--   2. Set CLIENT_ID below to the ID assigned by Sinum (shown after saving the client)
--   3. Optionally change TOPIC_PREFIX (default: "sinum")
--
-- Changes in v0.3:
--   - All device property access now uses safe getValue() wrappers
--   - Publishes initial snapshots for virtual, wtp, AND sbus device classes
--   - Includes fan coil fields: work_mode, available_work_modes, working_state, fan
--   - Includes parent_id and schedule_id for device associations
--   - Safer error handling on device state changes
--
-- Topic schema:
--   sinum/state/<device_id>    Device state JSON     (Sinum → HA)
--   sinum/event/<event_type>   Hub event JSON        (Sinum → HA)
--   sinum/cmd/<device_id>      Command JSON          (HA → Sinum)

local CLIENT_ID   = 1          -- ← change to your MQTT client ID
local TOPIC_PREFIX = "sinum"
local QOS         = 0
local RETAIN      = false

local client = mqtt_client[CLIENT_ID]

-- ── Helper: publish JSON table ────────────────────────────────────────────────

local function publish(subtopic, data)
    local ok, payload = pcall(json.encode, data)
    if not ok then
        print("[Sinapse] JSON encode error: " .. tostring(payload))
        return
    end
    client:publish(TOPIC_PREFIX .. "/" .. subtopic, payload, QOS, RETAIN)
end

-- ── Helper: safe getValue wrapper ───────────────────────────────────────────

local function safe_get(obj, key)
    local ok, val = pcall(function() return obj:getValue(key) end)
    if ok then return val end
    return nil
end

-- ── Helper: safe device state snapshot ───────────────────────────────────────

local function device_snapshot(device, source)
    local snap = {
        id          = safe_get(device, "id"),
        type        = safe_get(device, "type"),
        name        = safe_get(device, "name"),
        room_id     = safe_get(device, "room_id"),
        parent_id   = safe_get(device, "parent_id"),
        state       = safe_get(device, "state"),
        source      = source or "virtual",
        updated_at  = os.time(),
    }
    -- Virtual thermostat / heat pump / temperature regulator
    local temp = safe_get(device, "temperature")
    if temp ~= nil then snap.temperature = temp end
    local target_temp = safe_get(device, "target_temperature")
    if target_temp ~= nil then snap.target_temperature = target_temp end
    local humidity = safe_get(device, "humidity")
    if humidity ~= nil then snap.humidity = humidity end
    local mode = safe_get(device, "mode")
    if mode ~= nil then snap.mode = mode end
    -- Relay
    -- (state already covered above)
    -- Blind controller
    local opening = safe_get(device, "last_set_target_opening")
    if opening ~= nil then snap.last_set_target_opening = opening end
    local action = safe_get(device, "action_in_progress")
    if action ~= nil then snap.action_in_progress = action end
    local tilt = safe_get(device, "last_set_target_tilt")
    if tilt ~= nil then snap.last_set_target_tilt = tilt end
    -- Dimmer/RGB
    local brightness = safe_get(device, "brightness")
    if brightness ~= nil then snap.brightness = brightness end
    local led_color = safe_get(device, "led_color")
    if led_color ~= nil then snap.led_color = led_color end
    local white_temp = safe_get(device, "white_temperature")
    if white_temp ~= nil then snap.white_temperature = white_temp end
    local color_mode = safe_get(device, "color_mode")
    if color_mode ~= nil then snap.color_mode = color_mode end
    -- WTP sensors
    local co2 = safe_get(device, "co2")
    if co2 ~= nil then snap.co2 = co2 end
    local pm1 = safe_get(device, "pm1")
    if pm1 ~= nil then snap.pm1 = pm1 end
    local pm25 = safe_get(device, "pm25")
    if pm25 ~= nil then snap.pm25 = pm25 end
    local pm10 = safe_get(device, "pm10")
    if pm10 ~= nil then snap.pm10 = pm10 end
    local illuminance = safe_get(device, "illuminance")
    if illuminance ~= nil then snap.illuminance = illuminance end
    local pressure = safe_get(device, "pressure")
    if pressure ~= nil then snap.pressure = pressure end
    local power = safe_get(device, "total_active_power")
    if power ~= nil then snap.total_active_power = power end
    local energy = safe_get(device, "energy_consumed_total")
    if energy ~= nil then snap.energy_consumed_total = energy end
    -- Fan coil fields
    local work_mode = safe_get(device, "work_mode")
    if work_mode ~= nil then snap.work_mode = work_mode end
    local available_work_modes = safe_get(device, "available_work_modes")
    if available_work_modes ~= nil then snap.available_work_modes = available_work_modes end
    local working_state = safe_get(device, "working_state")
    if working_state ~= nil then snap.working_state = working_state end
    -- Fan coil fan sub-object: {"current_gear", "manual_fan_gear", "mode"}
    local fan = safe_get(device, "fan")
    if fan ~= nil then snap.fan = fan end
    local fan_mode = safe_get(device, "fan_operation_mode")
    if fan_mode ~= nil then snap.fan_operation_mode = fan_mode end
    -- Schedule association (thermal schedules)
    local schedule_id = safe_get(device, "schedule_id")
    if schedule_id ~= nil then snap.schedule_id = schedule_id end
    return snap
end

-- ── Subscribe: HA → Sinum commands ───────────────────────────────────────────

client:subscribe(TOPIC_PREFIX .. "/cmd/#")

client:onMessage(function(topic, payload, qos, retain, dup)
    local device_id = tonumber(topic:match("/cmd/(%d+)$"))
    if not device_id then
        print("[Sinapse] Unknown cmd topic: " .. topic)
        return
    end

    local ok, data = pcall(json.decode, payload)
    if not ok or type(data) ~= "table" then
        print("[Sinapse] Invalid JSON on " .. topic)
        return
    end

    local device = devices:getById(device_id)
    if not device then
        print("[Sinapse] Device not found: " .. tostring(device_id))
        return
    end

    -- Handle command vs property assignment
    if data.command then
        device:call(data.command, data)
    else
        for key, value in pairs(data) do
            device:setValue(key, value)
        end
    end
end)

-- ── Publish: device state changes → HA ───────────────────────────────────────

automation:onEvent("device_state_changed", function(event)
    local device = event.source
    if not device or not device.id then return end

    local source = device.class or "virtual"
    local snap = device_snapshot(device, source)
    publish("state/" .. tostring(device.id), snap)
end)

-- ── Publish: Lua variable changes ─────────────────────────────────────────────

automation:onEvent("lua_variable_state_changed", function(event)
    local var = event.source
    if not var or not var.id then return end
    publish("event/variable_changed", {
        id    = var.id,
        name  = var.name,
        value = var.value,
        ts    = os.time(),
    })
end)

-- ── Publish: scene activated ──────────────────────────────────────────────────

automation:onEvent("scene_activated", function(event)
    local scene = event.source
    if not scene then return end
    publish("event/scene_activated", {
        id   = scene.id,
        name = scene.name,
        ts   = os.time(),
    })
end)

automation:onEvent("activate_scene_by_id", function(event)
    publish("event/scene_activated", {
        id   = event.id,
        name = "",
        ts   = os.time(),
    })
end)

-- ── Publish: solar events (for automations in HA) ────────────────────────────

for _, solar_event in ipairs({"sunrise", "dawn", "sunset", "dusk"}) do
    automation:onEvent(solar_event, function()
        publish("event/" .. solar_event, { ts = os.time() })
    end)
end

-- ── Publish: MQTT client status (self-monitoring) ────────────────────────────

automation:onEvent("mqtt_client_connected", function(event)
    publish("event/mqtt_connected", { client_id = CLIENT_ID, ts = os.time() })
end)

automation:onEvent("mqtt_client_disconnected", function(event)
    publish("event/mqtt_disconnected", { client_id = CLIENT_ID, ts = os.time() })
end)

-- ── Startup: publish all current device states ───────────────────────────────

automation:onEvent("application_initialized", function()
    -- Virtual devices (thermostats, relays, blinds, dimmers, etc.)
    if virtual and type(virtual) == "table" then
        for id, device in pairs(virtual) do
            local snap = device_snapshot(device, "virtual")
            publish("state/" .. tostring(id), snap)
        end
        print("[Sinapse] Initial virtual device state published")
    end
    -- WTP devices (sensors, fan coils, regulators, etc.)
    if wtp and type(wtp) == "table" then
        for id, device in pairs(wtp) do
            local snap = device_snapshot(device, "wtp")
            publish("state/" .. tostring(id), snap)
        end
        print("[Sinapse] Initial WTP device state published")
    end
    -- SBUS devices (fan coils, sensors, etc.)
    if sbus and type(sbus) == "table" then
        for id, device in pairs(sbus) do
            local snap = device_snapshot(device, "sbus")
            publish("state/" .. tostring(id), snap)
        end
        print("[Sinapse] Initial SBUS device state published")
    end
    print("[Sinapse] MQTT bridge startup complete")
end)

print("[Sinapse] MQTT bridge v0.3 started. Client ID: " .. tostring(CLIENT_ID))
