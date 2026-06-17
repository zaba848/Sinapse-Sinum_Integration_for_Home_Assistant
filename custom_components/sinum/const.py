DOMAIN = "sinum"

# Config entry keys
CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_API_TOKEN = "api_token"
CONF_AUTH_MODE = "auth_mode"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_MQTT_ENABLED = "mqtt_enabled"

# Auth modes
AUTH_MODE_TOKEN = "token"
AUTH_MODE_PASSWORD = "password"

DEFAULT_SCAN_INTERVAL = 30

# REST API — all paths include /api/v1 prefix
API_LOGIN = "/api/v1/login"
API_REFRESH = "/api/v1/refresh"
API_INFO = "/api/v1/info"
API_ROOMS = "/api/v1/rooms"
API_FLOORS = "/api/v1/floors"
API_PARENT_DEVICES = "/api/v1/parent-devices"
API_VIRTUAL_DEVICES = "/api/v1/devices/virtual"
API_WTP_DEVICES = "/api/v1/devices/wtp"
API_SBUS_DEVICES = "/api/v1/devices/sbus"
API_VIRTUAL_DEVICE = "/api/v1/devices/virtual/{id}"
API_WTP_DEVICE = "/api/v1/devices/wtp/{id}"
API_SBUS_DEVICE = "/api/v1/devices/sbus/{id}"
API_SCENES = "/api/v1/scenes"
API_SCENE = "/api/v1/scenes/{id}"
API_VARIABLES = "/api/v1/variables"
API_VARIABLE = "/api/v1/variables/{id}"
API_NOTIFICATIONS = "/api/v1/notifications"
API_WEATHER = "/api/v1/weather"
API_ENERGY = "/api/v1/energy"
API_SCHEDULES = "/api/v1/schedules"
API_ALARM_DEVICES = "/api/v1/devices/alarm-system"
API_ALARM_DEVICE = "/api/v1/devices/alarm-system/{id}"

# Lua HTTP server (sinapse_api.lua — optional, provides wifi/signal data)
API_LUA_INFO = "/api/v1/lua/http-server/sinapse/info"

# Temperature stored as integer × 10 (220 = 22.0 °C)
TEMP_SCALE = 10
TEMP_MIN = 5.0
TEMP_MAX = 35.0

ATTR_SESSION = "session"
ATTR_REFRESH_TOKEN = "refresh_token"

# ── Virtual device types ───────────────────────────────────────────────────────
VTYPE_THERMOSTAT = "thermostat"
VTYPE_RELAY = "relay_integrator"
VTYPE_BLIND = "blind_controller_integrator"
VTYPE_GATE = "gate"
VTYPE_WICKET = "wicket"
VTYPE_DIMMER_RGB = "dimmer_rgb_controller_integrator"

# ── WTP device types ───────────────────────────────────────────────────────────
WTYPE_TEMP_SENSOR = "temperature_sensor"
WTYPE_HUMIDITY_SENSOR = "humidity_sensor"
WTYPE_CO2 = "co2_sensor"
WTYPE_AIR_QUALITY = "air_quality_sensor"
WTYPE_ENERGY_METER = "energy_meter"
WTYPE_LIGHT_SENSOR = "light_sensor"
WTYPE_PRESSURE_SENSOR = "pressure_sensor"
WTYPE_FLOOD_SENSOR = "flood_sensor"
WTYPE_MOTION_SENSOR = "motion_sensor"
WTYPE_OPENING_SENSOR = "opening_sensor"
WTYPE_SMOKE_SENSOR = "smoke_sensor"
WTYPE_TWO_STATE_INPUT_SENSOR = "two_state_input_sensor"
WTYPE_TEMPERATURE_REGULATOR = "temperature_regulator"
WTYPE_FAN_COIL = "fan_coil"
WTYPE_FAN_COIL_V2 = "fan_coil_v2"

# ── SBUS device types ──────────────────────────────────────────────────────────
STYPE_FAN_COIL = "fan_coil"
STYPE_HUMIDITY_SENSOR = "humidity_sensor"
STYPE_TEMPERATURE_SENSOR = "temperature_sensor"
STYPE_TWO_STATE_INPUT_SENSOR = "two_state_input_sensor"

# ── Gate states ────────────────────────────────────────────────────────────────
GATE_STATE_OPEN = "open"
GATE_STATE_OPENING = "opening"
GATE_STATE_CLOSED = "closed"
GATE_STATE_CLOSING = "closing"
GATE_STATE_MOVING = "moving"
GATE_STATE_NO_MOVE = "no_move"

# ── Wicket states ──────────────────────────────────────────────────────────────
WICKET_STATE_LOCKED = "locked"
WICKET_STATE_UNLOCKED = "unlocked"
WICKET_STATE_OPEN = "open"
WICKET_STATE_CLOSED = "closed"

# ── Notification service ───────────────────────────────────────────────────────
SERVICE_SEND_NOTIFICATION = "send_notification"
ATTR_NOTIFICATION_TITLE = "title"
ATTR_NOTIFICATION_MESSAGE = "message"
