-- Sinapse MQTT Bridge v0.7 (Optimized, Multi-Bus Support)
-- Creator: zaba848 (Home Assistant Sinum Integration)
-- License: MIT
-- Last updated: 2026-06-17
--
-- Supported device types:
-- ✅ Virtual: thermostat, relay, blind, dimmer, RGB light, custom_device (generic fields)
-- ✅ WTP: temperature_sensor, humidity_sensor, temperature_regulator, fan_coil, fan_coil_v2,
--    two_state_input_sensor, air_quality_sensor, power_meter, energy_meter
-- ✅ SBUS: fan_coil, temperature_sensor, humidity_sensor, two_state_input_sensor
-- ⚠️  Not on verified hub but will auto-support if present: LoRa, SLINK, Video, Alarm system
--
-- MQTT topics published:
--   sinum/state/<device_id>      Device state JSON (all properties via safe_get)
--   sinum/event/heartbeat        Heartbeat pulse (every minute)

local CLIENT_ID   = 1
local TOPIC_PREFIX = "sinum"
local QOS         = 0
local RETAIN      = false

local EVENTS = { INIT = "application_initialized", CHANGE = "device_state_changed", TICK = "minute_changed" }
local TOPICS = { STATE = "state", HB = "event/heartbeat" }

-- All supported device containers (dynamically includes only available ones)
local function get_containers()
    local result = {}
    local possible = {
        { "virtual", virtual },
        { "wtp", wtp },
        { "sbus", sbus },
        { "lora", lora },
        { "slink", slink },
        { "video", video },
        { "alarm_system", alarm_system },
    }
    for _, entry in ipairs(possible) do
        if entry[2] then table.insert(result, entry) end
    end
    return result
end

local CONTAINERS = get_containers()

-- Optional fields extracted from any device (schema-agnostic)
local OPTIONAL_FIELDS = {
    "temperature", "target_temperature", "humidity", "mode",
    "work_mode", "available_work_modes", "working_state", "fan", "schedule_id",
    "brightness", "led_color", "white_temperature", "color_mode",
    "last_set_target_opening", "action_in_progress", "last_set_target_tilt",
    "co2", "pm1", "pm25", "pm10", "illuminance", "pressure",
    "total_active_power", "energy_consumed_total",
    "fan_operation_mode", "has_messages", "status"
}

local client = mqtt_client[CLIENT_ID]

print("[Sinapse] MQTT bridge v0.7 started. Creator: zaba848. Client ID: " .. tostring(CLIENT_ID))

local function safe_get(obj, key)
    local ok, val = pcall(function() return obj:getValue(key) end)
    if ok then return val end
    return nil
end

local function publish(subtopic, data)
    local ok, payload = pcall(function() return JSON:encode(data) end)
    if not ok then
        print("[Sinapse] JSON encode error: " .. tostring(payload))
        return
    end
    client:publish(TOPIC_PREFIX .. "/" .. subtopic, payload, QOS, RETAIN)
    print("[Sinapse] Published: " .. subtopic)
end

local function device_snapshot(device)
    local snap = {
        id          = safe_get(device, "id"),
        type        = safe_get(device, "type"),
        name        = safe_get(device, "name"),
        room_id     = safe_get(device, "room_id"),
        parent_id   = safe_get(device, "parent_id"),
        state       = safe_get(device, "state"),
        updated_at  = os.time(),
    }
    for _, field in ipairs(OPTIONAL_FIELDS) do
        local val = safe_get(device, field)
        if val ~= nil then snap[field] = val end
    end
    return snap
end

local function find_device(device_id)
    for _, container_entry in ipairs(CONTAINERS) do
        local source_type, container = container_entry[1], container_entry[2]
        local ok, device = pcall(function() return container[device_id] end)
        if ok and device then return device, source_type end
    end
    return nil, nil
end

if event.type == EVENTS.INIT then
    local counts = {}
    for _, container_entry in ipairs(CONTAINERS) do
        local source_type = container_entry[1]
        counts[source_type] = 0
    end
    for _, container_entry in ipairs(CONTAINERS) do
        local source_type, container = container_entry[1], container_entry[2]
        if container then
            for id, device in pairs(container) do
                local snap = device_snapshot(device)
                snap.source = source_type
                publish(TOPICS.STATE .. "/" .. tostring(id), snap)
                counts[source_type] = counts[source_type] + 1
            end
        end
    end
    local msg = "[Sinapse] Published:"
    for source_type, count in pairs(counts) do
        if count > 0 then msg = msg .. " " .. count .. " " .. source_type .. "," end
    end
    print(msg:gsub(",$", " devices"))
end

if event.type == EVENTS.CHANGE and event.source and event.source.id ~= 0 then
    local device, source_type = find_device(event.source.id)
    if device and source_type then
        local snap = device_snapshot(device)
        snap.source = source_type
        publish(TOPICS.STATE .. "/" .. tostring(event.source.id), snap)
    else
        print("[Sinapse] device_state_changed: device " .. tostring(event.source.id) .. " not found")
    end
end

if event.type == EVENTS.TICK then
    publish(TOPICS.HB, { ts = os.time(), client_id = CLIENT_ID })
end
