-- Sinapse MQTT Bridge v0.6 (Optimized & Refactored)

local CLIENT_ID   = 1
local TOPIC_PREFIX = "sinum"
local QOS         = 0
local RETAIN      = false

local EVENTS = { INIT = "application_initialized", CHANGE = "device_state_changed", TICK = "minute_changed" }
local TOPICS = { STATE = "state", HB = "event/heartbeat" }
local CONTAINERS = { { "virtual", virtual }, { "wtp", wtp }, { "sbus", sbus } }
local OPTIONAL_FIELDS = {
    "temperature", "target_temperature", "humidity", "mode",
    "work_mode", "available_work_modes", "working_state", "fan", "schedule_id"
}

local client = mqtt_client[CLIENT_ID]

print("[Sinapse] MQTT bridge v0.6 started. Client ID: " .. tostring(CLIENT_ID))

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
    local ok, device = pcall(function() return virtual[device_id] end)
    if ok and device then return device, "virtual" end

    ok, device = pcall(function() return wtp[device_id] end)
    if ok and device then return device, "wtp" end

    ok, device = pcall(function() return sbus[device_id] end)
    if ok and device then return device, "sbus" end

    return nil, nil
end

if event.type == EVENTS.INIT then
    local counts = { virtual = 0, wtp = 0, sbus = 0 }
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
    print("[Sinapse] Published " .. counts.virtual .. " virtual, " .. counts.wtp ..
          " wtp, " .. counts.sbus .. " sbus devices")
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
