-- Sinapse MQTT Bridge v0.2
-- Upload this script to the Sinum hub:
--   Settings → Lua Scripts → New Script → paste this code → Save → Enable
--
-- Prerequisites:
--   1. Sinum hub: Integrations → Add MQTT client → point to your HA Mosquitto broker
--   2. Set CLIENT_ID below to the ID assigned by Sinum (shown after saving the client)
--   3. Optionally change TOPIC_PREFIX (default: "sinum")
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

-- ── Helper: safe device state snapshot ───────────────────────────────────────

local function device_snapshot(device, source)
    local snap = {
        id          = device.id,
        type        = device.type,
        name        = device.name,
        room_id     = device.room_id,
        state       = device.state,
        source      = source or "virtual",
        updated_at  = os.time(),
    }
    -- Virtual thermostat / heat pump
    if device.temperature        ~= nil then snap.temperature        = device.temperature        end
    if device.target_temperature ~= nil then snap.target_temperature = device.target_temperature end
    if device.humidity           ~= nil then snap.humidity           = device.humidity           end
    if device.mode               ~= nil then snap.mode               = device.mode               end
    -- Relay
    -- (state already covered above)
    -- Blind controller
    if device.last_set_target_opening ~= nil then snap.last_set_target_opening = device.last_set_target_opening end
    if device.action_in_progress      ~= nil then snap.action_in_progress      = device.action_in_progress      end
    if device.last_set_target_tilt    ~= nil then snap.last_set_target_tilt    = device.last_set_target_tilt    end
    -- Dimmer/RGB
    if device.brightness        ~= nil then snap.brightness        = device.brightness        end
    if device.led_color         ~= nil then snap.led_color         = device.led_color         end
    if device.white_temperature ~= nil then snap.white_temperature = device.white_temperature end
    if device.color_mode        ~= nil then snap.color_mode        = device.color_mode        end
    -- WTP sensors
    if device.co2               ~= nil then snap.co2               = device.co2               end
    if device.pm1               ~= nil then snap.pm1               = device.pm1               end
    if device.pm25              ~= nil then snap.pm25              = device.pm25              end
    if device.pm10              ~= nil then snap.pm10              = device.pm10              end
    if device.illuminance       ~= nil then snap.illuminance       = device.illuminance       end
    if device.pressure          ~= nil then snap.pressure          = device.pressure          end
    if device.total_active_power    ~= nil then snap.total_active_power    = device.total_active_power    end
    if device.energy_consumed_total ~= nil then snap.energy_consumed_total = device.energy_consumed_total end
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
    -- Virtual devices
    for id, device in pairs(wtp) do
        local snap = device_snapshot(device, "wtp")
        publish("state/" .. tostring(id), snap)
    end
    print("[Sinapse] Initial WTP state published")
end)

print("[Sinapse] MQTT bridge v0.2 started. Client ID: " .. tostring(CLIENT_ID))
