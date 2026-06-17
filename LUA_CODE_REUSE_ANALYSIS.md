# Lua Script Code Reuse Analysis

**Reviewed:** mqtt_bridge.lua v0.5 and sinapse_api.lua v1.0  
**Date:** 2026-06-17

---

## Executive Summary

The two Lua scripts contain **3 major code reuse opportunities** and **2 consolidation candidates**:

1. **Duplicate utility function** - `safe_get()` defined identically in both files
2. **Repetitive optional field extraction** - 8 times in device_snapshot() (lines 39-56)
3. **Container iteration pattern** - 3 identical blocks for virtual/wtp/sbus (lines 76-96)
4. **Nested property extraction** - Pattern repeated in sinapse_api.lua (lines 116-137)
5. **Safe iteration wrapper** - Could be extracted to reusable function

**Impact:** Can reduce mqtt_bridge.lua from ~120 lines to ~80-90 lines while improving maintainability.

---

## FINDING 1: Duplicate `safe_get()` Function

**Location:**
- `mqtt_bridge.lua` lines 12-16
- `sinapse_api.lua` lines 32-36

**Code:**
```lua
local function safe_get(obj, key)
    local ok, val = pcall(function() return obj:getValue(key) end)
    if ok then return val end
    return nil
end
```

**Issue:** Identical implementation defined in both files. Violates DRY principle.

**Recommendation:** 
Create a shared utility module `sinapse_utils.lua` with common functions:

```lua
-- sinapse_utils.lua v1.0 - Shared utilities for Sinapse Lua scripts

local utils = {}

function utils.safe_get(obj, key)
    local ok, val = pcall(function() return obj:getValue(key) end)
    if ok then return val end
    return nil
end

return utils
```

Then import in both scripts:
```lua
local utils = require("sinapse_utils")
-- Use: utils.safe_get(device, "temperature")
```

**Impact:** +1 file, -2 function definitions, eliminates maintenance duplication.

---

## FINDING 2: Repetitive Optional Field Extraction Pattern

**Location:** `mqtt_bridge.lua` lines 39-56 (device_snapshot function)

**Current Code:**
```lua
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
```

**Problem:** 18 lines of repetitive code that follows the same pattern 8 times.

**Recommendation - Option A: Add helper function to utils**

```lua
-- In sinapse_utils.lua
function utils.add_optional_fields(source_obj, target_table, field_names)
    for _, field in ipairs(field_names) do
        local val = utils.safe_get(source_obj, field)
        if val ~= nil then
            target_table[field] = val
        end
    end
end
```

**Refactored device_snapshot():**
```lua
local function device_snapshot(device)
    local snap = {
        id          = utils.safe_get(device, "id"),
        type        = utils.safe_get(device, "type"),
        name        = utils.safe_get(device, "name"),
        room_id     = utils.safe_get(device, "room_id"),
        parent_id   = utils.safe_get(device, "parent_id"),
        state       = utils.safe_get(device, "state"),
        updated_at  = os.time(),
    }
    
    utils.add_optional_fields(device, snap, {
        "temperature",
        "target_temperature",
        "humidity",
        "mode",
        "work_mode",
        "available_work_modes",
        "working_state",
        "fan",
        "schedule_id",
    })
    
    return snap
end
```

**Impact:** Reduces device_snapshot() from 31 lines to 16 lines. More maintainable when adding new fields.

---

## FINDING 3: Container Iteration Pattern (3 Duplicates)

**Location:** `mqtt_bridge.lua` lines 76-96 (application_initialized event)

**Current Code:**
```lua
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
```

**Problem:** Same logic repeated 3 times with only container name and source string changing.

**Recommendation - Add helper to utils:**

```lua
-- In sinapse_utils.lua
function utils.publish_container_snapshots(containers, snapshot_fn, publish_fn)
    for source_name, container in pairs(containers) do
        if container then
            for id, device in pairs(container) do
                local snap = snapshot_fn(device)
                snap.source = source_name
                publish_fn("state/" .. tostring(id), snap)
            end
        end
    end
end
```

**Refactored event handler:**
```lua
if event.type == "application_initialized" then
    print("[Sinapse] >> application_initialized: publishing initial device snapshots")
    utils.publish_container_snapshots(
        { virtual = virtual, wtp = wtp, sbus = sbus },
        device_snapshot,
        publish
    )
    print("[Sinapse] Initial device snapshots published")
end
```

**Impact:** Reduces event handler from 21 lines to 8 lines. Single-source of truth for iteration logic.

---

## FINDING 4: Safe Iteration Pattern in sinapse_api.lua

**Location:** `sinapse_api.lua` lines 83-96 (GET /sinapse/floors)

**Current Pattern:**
```lua
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
```

**Similar Pattern:** Lines 115-137 in GET /sinapse/parent-devices uses almost identical structure.

**Recommendation - Add to utils:**

```lua
-- In sinapse_utils.lua
function utils.safe_iterate_with_builder(container, builder_fn)
    local result = {}
    if container then
        for _, item in pairs(container) do
            local ok, entry = pcall(builder_fn, item)
            if ok and entry and entry.id then
                result[#result + 1] = entry
            end
        end
    end
    return result
end
```

**Refactored /sinapse/floors:**
```lua
http_server:on("GET", "/sinapse/floors", function(req, res)
    local floors = utils.safe_iterate_with_builder(floor, function(f)
        return {
            id    = utils.safe_get(f, "id"),
            name  = utils.safe_get(f, "name"),
            level = utils.safe_get(f, "level"),
        }
    end)
    
    table.sort(floors, function(a, b)
        return (a.level or 0) < (b.level or 0)
    end)
    
    res:body(JSON:encode(floors))
end)
```

**Impact:** Improves error handling consistency, reduces duplicate try-catch wrapping.

---

## FINDING 5: find_device() Could Use Loop Consolidation

**Location:** `mqtt_bridge.lua` lines 61-72

**Current Code:**
```lua
local function find_device(device_id)
    local ok, device = pcall(function() return virtual[device_id] end)
    if ok and device then return device, "virtual" end

    ok, device = pcall(function() return wtp[device_id] end)
    if ok and device then return device, "wtp" end

    ok, device = pcall(function() return sbus[device_id] end)
    if ok and device then return device, "sbus" end

    return nil, nil
end
```

**Issue:** Three sequential lookups. Good as-is, but could be table-driven.

**Alternative (if needed for 4+ container types):**
```lua
local function find_device(device_id)
    local containers = { 
        { "virtual", virtual },
        { "wtp", wtp },
        { "sbus", sbus },
    }
    for _, pair in ipairs(containers) do
        local source_name, container = pair[1], pair[2]
        local ok, device = pcall(function() return container[device_id] end)
        if ok and device then return device, source_name end
    end
    return nil, nil
end
```

**Note:** Current version is clearer and faster (3 lookups vs loop + table allocation). **Keep as-is unless adding 4+ container types.**

---

## Consolidation Summary

| Opportunity | Location | Lines | Impact | Priority |
|---|---|---|---|---|
| `safe_get()` duplication | Both files | 2 × 5 = 10 | Extract to utils.lua | HIGH |
| Optional field extraction | device_snapshot() | 18 → 5 | Add utils.add_optional_fields() | HIGH |
| Container iteration | app_init event | 21 → 8 | Add utils.publish_container_snapshots() | HIGH |
| Safe iterate pattern | sinapse_api.lua | 2 × 12 = 24 | Add utils.safe_iterate_with_builder() | MEDIUM |
| find_device() lookup | find_device() | 12 | Keep as-is (clear and fast) | - |

---

## Proposed Implementation Timeline

**Phase 1 (Immediate):** Extract `safe_get()` to utils
- Create `/lua_scripts/sinapse_utils.lua`
- Update both scripts to require() it
- Test with real hub

**Phase 2 (Next):** Add `add_optional_fields()` helper
- Update device_snapshot()
- Test device state publishing

**Phase 3 (Optional):** Consolidate container iteration
- Add `publish_container_snapshots()` 
- Refactor event handlers
- Reduces mqtt_bridge.lua to ~85 lines

**Phase 4 (Low priority):** Generalize sinapse_api.lua iteration
- Add `safe_iterate_with_builder()`
- Refactor both endpoints
- Improves maintainability, not line count

---

## Risk Assessment

**Low Risk:**
- Extracting `safe_get()` — function signature identical
- Adding optional field helper — backwards compatible
- Adding iterate helper — doesn't change existing logic

**Testing Required:**
- MQTT bridge startup: verify "Initial device snapshots published"
- Device state changes: verify `device_state_changed` still publishes
- sinapse_api.lua endpoints: `/sinapse/info`, `/sinapse/floors`, `/sinapse/parent-devices`

---

## Code Examples: Before & After

### Before (mqtt_bridge.lua v0.5 - ~120 lines)
```lua
local function safe_get(obj, key)
    local ok, val = pcall(function() return obj:getValue(key) end)
    if ok then return val end
    return nil
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
    -- ... 7 more repetitive blocks ...
    local schedule_id = safe_get(device, "schedule_id")
    if schedule_id ~= nil then snap.schedule_id = schedule_id end
    
    return snap
end

if event.type == "application_initialized" then
    if virtual then
        for id, device in pairs(virtual) do
            local snap = device_snapshot(device)
            snap.source = "virtual"
            publish("state/" .. tostring(id), snap)
        end
    end
    -- ... 2 more identical blocks for wtp, sbus ...
end
```

### After (mqtt_bridge.lua optimized - ~85 lines)
```lua
local utils = require("sinapse_utils")

local function device_snapshot(device)
    local snap = {
        id          = utils.safe_get(device, "id"),
        type        = utils.safe_get(device, "type"),
        name        = utils.safe_get(device, "name"),
        room_id     = utils.safe_get(device, "room_id"),
        parent_id   = utils.safe_get(device, "parent_id"),
        state       = utils.safe_get(device, "state"),
        updated_at  = os.time(),
    }
    
    utils.add_optional_fields(device, snap, {
        "temperature", "target_temperature", "humidity", "mode",
        "work_mode", "available_work_modes", "working_state",
        "fan", "schedule_id",
    })
    
    return snap
end

if event.type == "application_initialized" then
    utils.publish_container_snapshots(
        { virtual = virtual, wtp = wtp, sbus = sbus },
        device_snapshot,
        publish
    )
end
```

**Savings:** ~35 lines of code, improved maintainability, single source of truth for patterns.

---

## File Paths

- `/Users/tomaszpanek/Documents/Sinum_HomeAsistant_connector/lua_scripts/mqtt_bridge.lua` (v0.5)
- `/Users/tomaszpanek/Documents/Sinum_HomeAsistant_connector/lua_scripts/sinapse_api.lua` (v1.0)
- **New:** `/Users/tomaszpanek/Documents/Sinum_HomeAsistant_connector/lua_scripts/sinapse_utils.lua` (proposed)

