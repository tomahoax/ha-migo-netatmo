"""Constants for the MiGo (Netatmo) integration."""

from typing import Final

# =============================================================================
# Integration
# =============================================================================

DOMAIN: Final = "migo_netatmo"
MANUFACTURER: Final = "Saunier Duval"

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
API_SWITCHHOMESCHEDULE_URL: Final = f"{API_BASE_URL}/api/switchhomeschedule"
API_CHANGEHEATINGCURVE_URL: Final = f"{API_BASE_URL}/api/changeheatingcurve"
API_SETHEATINGSYSTEM_URL: Final = f"{API_BASE_URL}/api/setheatingsystem"
API_SETCONFIGS_URL: Final = f"{API_BASE_URL}/syncapi/v1/setconfigs"
API_CHANGEHEATINGALGO_URL: Final = f"{API_BASE_URL}/api/changeheatingalgo"
API_GETMEASURE_URL: Final = f"{API_BASE_URL}/api/getmeasure"
API_GETCONFIGS_URL: Final = f"{API_BASE_URL}/syncapi/v1/getconfigs"

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

# Note: the HVAC-mode <-> MiGO-mode mappings live in climate.py
# (HVAC_TO_MIGO_MODE / MIGO_TO_HVAC_MODE), not here. An earlier pair of
# unused dicts in this module (HVAC_MODE_TO_API / API_MODE_TO_HVAC) still
# carried a stale, since-fixed mapping (MODE_HOME -> "heat" instead of
# "auto") and was removed rather than left as a latent-bug trap for a future
# caller to pick up by mistake.

# =============================================================================
# Boiler Mode (derived)
# =============================================================================
# MiGo's "Actions rapides" (Normal / DHW only / Frost guard) are not returned
# as a single API field. They are derived from the home's `therm_mode` and the
# rooms' `therm_setpoint_mode` - see helpers.derive_boiler_mode(). Distinct
# from MODE_AWAY, which is an independent, orthogonal home-level flag.

BOILER_MODE_NORMAL: Final = "normal"
BOILER_MODE_DHW_ONLY: Final = "dhw_only"
BOILER_MODE_FROST_GUARD: Final = "frost_guard"

# =============================================================================
# Schedule Types
# =============================================================================

SCHEDULE_TYPE_THERM: Final = "therm"
SCHEDULE_TYPE_EVENT: Final = "event"  # DHW schedule

# =============================================================================
# API Response Keys
# =============================================================================

# Measure types requested from /api/getmeasure, in this exact order: the endpoint
# returns one value per requested type, positionally, so the order IS the schema.
#
# All six come back in a single request, so the energy measures cost nothing
# extra. Verified against a live NAVaillant gateway.
#
# Note "gaz", the French spelling. "gas" is silently accepted and returns an
# empty series, which is indistinguishable from "your boiler does not support
# this", so this is an easy hour to lose.
#
# Energy values are in Wh at whole-kWh resolution (always multiples of 1000).
# Calibrated against the MiGO app's own weekly figures.
MEASURE_BOILER_ON: Final = "sum_boiler_on"
MEASURE_BOILER_OFF: Final = "sum_boiler_off"
MEASURE_GAS_HEATING: Final = "sum_energy_gaz_heating"
MEASURE_GAS_HOT_WATER: Final = "sum_energy_gaz_hot_water"
MEASURE_ELEC_HEATING: Final = "sum_energy_elec_heating"
MEASURE_ELEC_HOT_WATER: Final = "sum_energy_elec_hot_water"

MEASURE_TYPES: Final = (
    MEASURE_BOILER_ON,
    MEASURE_BOILER_OFF,
    MEASURE_GAS_HEATING,
    MEASURE_GAS_HOT_WATER,
    MEASURE_ELEC_HEATING,
    MEASURE_ELEC_HOT_WATER,
)

# Wh -> kWh. The API reports whole kWh already, so nothing is lost.
WH_PER_KWH: Final = 1000

KEY_BODY: Final = "body"
KEY_HOME: Final = "home"
KEY_HOMES: Final = "homes"
KEY_ROOMS: Final = "rooms"
KEY_MODULES: Final = "modules"

# =============================================================================
# Temperature Constants
# =============================================================================

TEMP_MIN: Final = 7.0
TEMP_MAX: Final = 30.0
TEMP_STEP: Final = 0.5

# =============================================================================
# Heating System Settings
# =============================================================================

# Manual setpoint duration (in minutes - API stores in minutes)
MANUAL_SETPOINT_DURATION_MIN: Final = 5  # 5 minutes
MANUAL_SETPOINT_DURATION_MAX: Final = 720  # 12 hours (720 minutes)
MANUAL_SETPOINT_DURATION_STEP: Final = 5  # 5 minutes

# Temperature offset
TEMP_OFFSET_MIN: Final = -5.0
TEMP_OFFSET_MAX: Final = 5.0
TEMP_OFFSET_STEP: Final = 0.5

# DHW temperature
DHW_TEMP_MIN: Final = 45
DHW_TEMP_MAX: Final = 60
DHW_TEMP_STEP: Final = 1

# Hysteresis threshold (0.1 to 2.0°C)
# API uses high_deadband = hysteresis * 10 - 1
HYSTERESIS_MIN: Final = 0.1
HYSTERESIS_MAX: Final = 2.0
HYSTERESIS_STEP: Final = 0.1

# Heating curve (slope) - 0 to 5 in UI
# API uses slope * 10 (0-50)
HEATING_CURVE_MIN: Final = 0.0
HEATING_CURVE_MAX: Final = 5.0
HEATING_CURVE_STEP: Final = 0.1
# No universal factory default exists for this value - it's installation-
# specific (heating type, radiator sizing, ...) and never echoed back by any
# API endpoint this integration calls (homesdata/homestatus/getconfigs all
# confirmed, via a live debug-log capture, not to carry it). This is simply
# the value MigoResetHeatingCurveButton and MigoHeatingCurveNumber's no-data
# fallback use - set per the user's own calibrated value, not a Netatmo/
# Saunier Duval constant.
DEFAULT_HEATING_CURVE: Final = 2.6

# =============================================================================
# Timing Constants
# =============================================================================

DEFAULT_UPDATE_INTERVAL: Final = 300  # 5 minutes in seconds
MIN_UPDATE_INTERVAL: Final = 60  # 1 minute minimum
MAX_UPDATE_INTERVAL: Final = 3600  # 1 hour maximum
TOKEN_EXPIRY_BUFFER: Final = 300  # Refresh 5 minutes before expiry
API_TIMEOUT: Final = 30  # API request timeout in seconds

# =============================================================================
# Config Keys
# =============================================================================

CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_CLIENT_ID: Final = "client_id"
CONF_CLIENT_SECRET: Final = "client_secret"
CONF_USER_PREFIX: Final = "user_prefix"
CONF_UPDATE_INTERVAL: Final = "update_interval"

# =============================================================================
# Default Values
# =============================================================================

DEFAULT_MANUAL_SETPOINT_DURATION: Final = 180  # 3 hours in minutes
DEFAULT_BOOST_DURATION: Final = 60  # 1 hour in minutes
DEFAULT_DHW_TEMPERATURE: Final = 60  # °C
DEFAULT_HYSTERESIS: Final = 1.6  # °C (deadband=15)
DEFAULT_TEMP_OFFSET: Final = 0.0  # °C
