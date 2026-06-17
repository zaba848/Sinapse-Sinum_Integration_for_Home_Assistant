-- Sinapse MQTT Bridge v0.5 (Sinum Lua API - Safe getValue wrappers)

local CLIENT_ID   = 1
local TOPIC_PREFIX = "sinum"
local QOS         = 0
local RETAIN      = false

local client = mqtt_client[CLIENT_ID]

print("[Sinapse] MQTT bridge v0.5 started. Client ID: " .. tostring(CLIENT_ID))

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

    local temp = safe_get(device, "temperature")
    if temp ~= nil then snap.temperature = temp end
    local target_temp = safe_get(device, "target_temperature")
    if target_temp ~= nil then snap.target_temperature = target_temp end
    local humidity = safe_get(device, "humidity")
    if humidity ~= nil then snap.humidity = humidity end
    local mode = safe_get(device, "mode")
    if mode ~= nil then snap.mode = mode end
    local work_mode = safe_get(device, "work_mode")
    if work_mode ~= nil then snap.work_mode = work_mode end
    local available_work_modes = safe_get(device, "available_work_modes")
    if available_work_modes ~= nil then snap.available_work_modes = available_work_modes end
    local working_state = safe_get(device, "working_state")
    if working_state ~= nil then snap.working_state = working_state end
    local fan = safe_get(device, "fan")
    if fan ~= nil then snap.fan = fan end
    local schedule_id = safe_get(device, "schedule_id")
    if schedule_id ~= nil then snap.schedule_id = schedule_id end

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

if event.type == "application_initialized" then
    print("[Sinapse] >> application_initialized: publishing initial device snapshots")
    if virtual then
        for id, device in pairs(virtual) do
            local snap = device_snapshot(device)
            snap.source = "virtual"
            publish("state/" .. tostring(id), snap)
        end
    end
    if wtp then
        for id, device in pairs(wtp) do
            local snap = device_snapshot(device)
            snap.source = "wtp"
            publish("state/" .. tostring(id), snap)
        end
    end
    if sbus then
        for id, device in pairs(sbus) do
            local snap = device_snapshot(device)
            snap.source = "sbus"
            publish("state/" .. tostring(id), snap)
        end
    end
    print("[Sinapse] Initial device snapshots published")
end

if event.type == "device_state_changed" and event.source and event.source.id ~= 0 then
    local source = event.source
    local device, source_type = find_device(source.id)

    if device and source_type then
        local snap = device_snapshot(device)
        snap.source = source_type
        publish("state/" .. tostring(source.id), snap)
    else
        print("[Sinapse] device_state_changed: device " .. tostring(source.id) .. " not found in any container")
    end
end

if event.type == "minute_changed" then
    publish("event/heartbeat", { ts = os.time(), client_id = CLIENT_ID })
end
