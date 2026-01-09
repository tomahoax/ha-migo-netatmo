"""Constants for the MiGo (Netatmo) integration."""

from typing import Final

# =============================================================================
# Integration
# =============================================================================

DOMAIN: Final = "migo_netatmo"
MANUFACTURER: Final = "Saunier Duval"
MODEL_NAME: Final = "MiGO Thermostat"

# =============================================================================
# Netatmo API Endpoints
# =============================================================================

API_BASE_URL: Final = "https://app.netatmo.net"
API_AUTH_URL: Final = f"{API_BASE_URL}/oauth2/token"
API_HOMESDATA_URL: Final = f"{API_BASE_URL}/api/homesdata"
API_HOMESTATUS_URL: Final = f"{API_BASE_URL}/api/homestatus"
API_SETSTATE_URL: Final = f"{API_BASE_URL}/api/setstate"
API_SETTHERMMODE_URL: Final = f"{API_BASE_URL}/api/setthermmode"
API_SETHOMEDATA_URL: Final = f"{API_BASE_URL}/api/sethomedata"
API_SYNCHOMESCHEDULE_URL: Final = f"{API_BASE_URL}/api/synchomeschedule"
API_SWITCHHOMESCHEDULE_URL: Final = f"{API_BASE_URL}/api/switchhomeschedule"
API_CHANGEHEATINGCURVE_URL: Final = f"{API_BASE_URL}/api/changeheatingcurve"
API_SETHEATINGSYSTEM_URL: Final = f"{API_BASE_URL}/api/setheatingsystem"
API_SETCONFIGS_URL: Final = f"{API_BASE_URL}/syncapi/v1/setconfigs"

# Sync API endpoints (used by mobile app for real-time updates)
API_SYNC_HOMESTATUS_URL: Final = f"{API_BASE_URL}/syncapi/v1/homestatus"
API_SYNC_SETSTATE_URL: Final = f"{API_BASE_URL}/syncapi/v1/setstate"

# =============================================================================
# OAuth2 Credentials
# =============================================================================

CLIENT_ID: Final = "na_client_ios_sdbg"
CLIENT_SECRET: Final = "2139e4db25b33c417c62b779ada3f4e4"
USER_PREFIX: Final = "sdbg"
SCOPE: Final = "all_scopes"
GRANT_TYPE_PASSWORD: Final = "password"
GRANT_TYPE_REFRESH: Final = "refresh_token"

# =============================================================================
# Device Types
# =============================================================================

DEVICE_TYPE_GATEWAY: Final = "NAVaillant"
DEVICE_TYPE_THERMOSTAT: Final = "NAThermVaillant"
DEVICE_SUBTYPE_EBUS: Final = "NAEbusSdbg"

# Legacy alias for backward compatibility
DEVICE_TYPE: Final = DEVICE_TYPE_GATEWAY

# =============================================================================
# App Identification
# =============================================================================

APP_IDENTIFIER: Final = "app_thermostat_sdbg"
APP_TYPE: Final = "app_thermostat_sdbg"

# =============================================================================
# Thermostat Modes
# =============================================================================

MODE_SCHEDULE: Final = "schedule"
MODE_AWAY: Final = "away"
MODE_FROST_GUARD: Final = "hg"
MODE_MANUAL: Final = "manual"
MODE_HOME: Final = "home"
MODE_OFF: Final = "off"
MODE_MAX: Final = "max"

# HVAC mode to API mode mapping
HVAC_MODE_TO_API: Final = {
    "auto": MODE_SCHEDULE,
    "heat": MODE_MANUAL,
    "off": MODE_FROST_GUARD,
}

API_MODE_TO_HVAC: Final = {
    MODE_SCHEDULE: "auto",
    MODE_MANUAL: "heat",
    MODE_FROST_GUARD: "off",
    MODE_AWAY: "off",
    MODE_HOME: "heat",
}

# =============================================================================
# Schedule Types
# =============================================================================

SCHEDULE_TYPE_THERM: Final = "therm"
SCHEDULE_TYPE_EVENT: Final = "event"  # DHW schedule

# =============================================================================
# API Response Keys
# =============================================================================

KEY_BODY: Final = "body"
KEY_HOME: Final = "home"
KEY_HOMES: Final = "homes"
KEY_ROOMS: Final = "rooms"
KEY_MODULES: Final = "modules"
KEY_SCHEDULES: Final = "schedules"
KEY_STATUS: Final = "status"

# Room data keys
KEY_THERM_MEASURED_TEMP: Final = "therm_measured_temperature"
KEY_THERM_SETPOINT_TEMP: Final = "therm_setpoint_temperature"
KEY_THERM_SETPOINT_MODE: Final = "therm_setpoint_mode"
KEY_ANTICIPATING: Final = "anticipating"
KEY_REACHABLE: Final = "reachable"

# Module data keys
KEY_FIRMWARE_REVISION: Final = "firmware_revision"
KEY_WIFI_STRENGTH: Final = "wifi_strength"
KEY_RF_STRENGTH: Final = "rf_strength"
KEY_BATTERY_PERCENT: Final = "battery_percent"
KEY_BATTERY_STATE: Final = "battery_state"
KEY_BATTERY_LEVEL: Final = "battery_level"
KEY_BOILER_STATUS: Final = "boiler_status"
KEY_BOILER_ERROR: Final = "boiler_error"
KEY_EBUS_ERROR: Final = "ebus_error"
KEY_DHW_ENABLED: Final = "dhw_enabled"

# =============================================================================
# Temperature Constants
# =============================================================================

TEMP_MIN: Final = 7.0
TEMP_MAX: Final = 30.0
TEMP_STEP: Final = 0.5

# DHW Temperature
DHW_TEMP_MIN: Final = 45
DHW_TEMP_MAX: Final = 65
DHW_TEMP_STEP: Final = 1

# =============================================================================
# Heating System Settings
# =============================================================================

# Heating types (API values - singular form)
HEATING_TYPE_RADIATOR: Final = "radiator"
HEATING_TYPE_CONVECTOR: Final = "convector"
HEATING_TYPE_FLOOR: Final = "floor_heating"
HEATING_TYPE_UNKNOWN: Final = "unknown"

HEATING_TYPES: Final = [
    HEATING_TYPE_RADIATOR,
    HEATING_TYPE_CONVECTOR,
    HEATING_TYPE_FLOOR,
    HEATING_TYPE_UNKNOWN,
]

# Heating curve (slope) settings
HEATING_CURVE_MIN: Final = 5  # 0.5 in UI (value / 10)
HEATING_CURVE_MAX: Final = 35  # 3.5 in UI
HEATING_CURVE_STEP: Final = 1
HEATING_CURVE_DEFAULT: Final = 14  # 1.4 in UI

# Hysteresis settings (high_deadband = hysteresis * 10 - 1)
HYSTERESIS_MIN: Final = 0.1
HYSTERESIS_MAX: Final = 2.0
HYSTERESIS_STEP: Final = 0.1
HYSTERESIS_DEFAULT: Final = 0.5

# Manual setpoint duration (in seconds)
MANUAL_SETPOINT_DURATION_MIN: Final = 300  # 5 minutes
MANUAL_SETPOINT_DURATION_MAX: Final = 43200  # 12 hours
MANUAL_SETPOINT_DURATION_STEP: Final = 300  # 5 minutes

# Temperature offset
TEMP_OFFSET_MIN: Final = -5.0
TEMP_OFFSET_MAX: Final = 5.0
TEMP_OFFSET_STEP: Final = 0.5

# DHW control modes
DHW_CONTROL_WATER_TANK: Final = "water_tank"
DHW_CONTROL_INSTANTANEOUS: Final = "instantaneous"

# =============================================================================
# Timing Constants
# =============================================================================

DEFAULT_UPDATE_INTERVAL: Final = 300  # 5 minutes in seconds
TOKEN_EXPIRY_BUFFER: Final = 300  # Refresh 5 minutes before expiry
API_TIMEOUT: Final = 30  # API request timeout in seconds

# =============================================================================
# Signal Thresholds
# =============================================================================

# WiFi signal thresholds (NAVaillant gateway)
WIFI_THRESHOLD_EXCELLENT: Final = 56
WIFI_THRESHOLD_GOOD: Final = 71
WIFI_THRESHOLD_FAIR: Final = 86

# RF signal thresholds (thermostat radio)
RF_THRESHOLD_EXCELLENT: Final = 60
RF_THRESHOLD_GOOD: Final = 70
RF_THRESHOLD_FAIR: Final = 80

# =============================================================================
# Battery Thresholds (mV)
# =============================================================================

BATTERY_FULL: Final = 4100
BATTERY_HIGH: Final = 3600
BATTERY_MEDIUM: Final = 3200
BATTERY_LOW: Final = 3000

# =============================================================================
# Config Keys
# =============================================================================

CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"

# =============================================================================
# Entity ID Prefixes
# =============================================================================

ENTITY_ID_PREFIX: Final = "migo_netatmo"
