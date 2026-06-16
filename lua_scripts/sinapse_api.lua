-- Sinapse API Extension v1.0
-- Custom Lua HTTP server endpoints for Home Assistant integration.
--
-- Upload to the Sinum hub:
--   Settings → Lua Scripts → New Script → paste this → Save → Enable
--
-- Provides three read-only endpoints (same auth as regular REST API):
--   GET /api/v1/lua/http-server/sinapse/info            → hub system info
--   GET /api/v1/lua/http-server/sinapse/floors          → floors list with levels
--   GET /api/v1/lua/http-server/sinapse/parent-devices  → all parent device statuses
--
-- All endpoints require authentication:
--   Header:     Authorization: Bearer <token>
--   OR param:   ?access_token=<token>

-- ── Parent device container names ────────────────────────────────────────────

local PARENT_CLASSES = {
    "wtp_parent_device",
    "slink_parent_device",
    "sbus_parent_device",
    "tech_parent_device",
    "modbus_parent_device",
    "system_module_parent_device",
    "alarm_system_parent",
    "lora_parent_device",
    "video_parent_device",
}

-- ── Helper: safe getValue wrapper ─────────────────────────────────────────────

local function safe_get(obj, key)
    local ok, val = pcall(function() return obj:getValue(key) end)
    if ok then return val end
    return nil
end

-- ── GET /sinapse/info ─────────────────────────────────────────────────────────

http_server:on("GET", "/sinapse/info", function(req, res)
    local ver = system:version()
    local net = system:network()

    local eth_info = {}
    local wifi_info = {}

    if net then
        if net.ethernet then
            eth_info = {
                connected = net.ethernet.connected or false,
                ip        = net.ethernet.ip,
                mac       = net.ethernet.mac,
            }
        end
        if net.wifi then
            wifi_info = {
                connected = net.wifi.connected or false,
                signal    = net.wifi.signal,
                ssid      = net.wifi.ssid,
                ip        = net.wifi.ip,
                mac       = net.wifi.mac,
            }
        end
    end

    local info = {
        version  = ver.semver,
        major    = ver.major,
        minor    = ver.minor,
        build    = ver.build,
        uptime   = system:uptime(),
        uid      = system:uid(),
        hostname = system:hostname(),
        ethernet = eth_info,
        wifi     = wifi_info,
    }

    res:body(JSON:encode(info))
end)

-- ── GET /sinapse/floors ───────────────────────────────────────────────────────

http_server:on("GET", "/sinapse/floors", function(req, res)
    local floors = {}

    for _, f in pairs(floor) do
        local ok, entry = pcall(function()
            return {
                id    = f:getValue("id"),
                name  = f:getValue("name"),
                level = f:getValue("level"),
            }
        end)
        if ok and entry and entry.id then
            floors[#floors + 1] = entry
        end
    end

    -- Sort by level so ground floor (0) comes first
    table.sort(floors, function(a, b)
        return (a.level or 0) < (b.level or 0)
    end)

    res:body(JSON:encode(floors))
end)

-- ── GET /sinapse/parent-devices ───────────────────────────────────────────────

http_server:on("GET", "/sinapse/parent-devices", function(req, res)
    local result = {}

    for _, class_name in ipairs(PARENT_CLASSES) do
        local container = _G[class_name]
        if container then
            for _, dev in pairs(container) do
                local ok, entry = pcall(function()
                    local e = {
                        id              = safe_get(dev, "id"),
                        name            = safe_get(dev, "name"),
                        class           = class_name,
                        type            = safe_get(dev, "type"),
                        model           = safe_get(dev, "model"),
                        firm            = safe_get(dev, "firm"),
                        status          = safe_get(dev, "status"),
                        software_status = safe_get(dev, "software_status"),
                        has_messages    = safe_get(dev, "has_messages"),
                        version         = safe_get(dev, "version"),
                    }
                    -- update_details is a nested property — may not exist on all devices
                    e.update_version  = safe_get(dev, "update_details.available_version")
                    e.update_progress = safe_get(dev, "update_details.progress")
                    return e
                end)
                if ok and entry and entry.id then
                    result[#result + 1] = entry
                end
            end
        end
    end

    res:body(JSON:encode(result))
end)

print("[Sinapse API] v1.0 — endpoints registered: /sinapse/info, /sinapse/floors, /sinapse/parent-devices")
