# MiGO API Reference

Complete documentation of the Netatmo API used by the MiGO (Saunier Duval) application.

> **Note:** This documentation was enhanced through mitmproxy traffic capture of the MiGO iOS app v2.4.2.

> **Security Note:** The OAuth2 credentials (CLIENT_ID, CLIENT_SECRET) used by this integration were extracted from the official MiGO iOS app. They are required for authentication and are included in the integration source code. Do not share these credentials outside of this project.

---

## Differences with Standard Netatmo API

This integration uses the same base API as the [official Netatmo Energy API](https://dev.netatmo.com/apidocumentation/energy), but with some differences specific to the MiGO/Vaillant ecosystem.

### Endpoints Comparison

| Official Netatmo API | MiGO Integration | Notes |
|---------------------|------------------|-------|
| `/api/homesdata` | ✅ Used | Same endpoint |
| `/api/homestatus` | ✅ Used | Same endpoint |
| `/api/setthermmode` | ✅ Used | Same endpoint |
| `/api/switchhomeschedule` | ✅ Used | Same endpoint |
| `/api/setroomthermpoint` | ❌ Not used | Replaced by `/api/setstate` |
| `/api/setstate` | ✅ Used | More flexible than `setroomthermpoint` |

### MiGO-Specific Endpoints (Not in Official Netatmo API)

These endpoints are used by the MiGO app but are **not documented** in the official Netatmo API:

| Endpoint | Purpose |
|----------|---------|
| `/api/sethomedata` | Anticipation, manual setpoint duration |
| `/api/synchomeschedule` | Schedule synchronization |
| `/api/changeheatingcurve` | Heating curve (slope) adjustment |
| `/api/setheatingsystem` | Heating type configuration |
| `/api/changeheatingalgo` | Hysteresis threshold |
| `/syncapi/v1/setconfigs` | DHW temperature, temperature offset |
| `/syncapi/v1/homestatus` | Real-time status (sync version) |
| `/syncapi/v1/setstate` | State changes (sync version) |

### Why `/api/setstate` Instead of `/api/setroomthermpoint`?

The integration uses `/api/setstate` instead of the official `/api/setroomthermpoint` because:

1. **More flexible**: Can modify multiple properties in a single request
2. **Consistent**: Same endpoint for room state and module control (DHW)
3. **Used by MiGO app**: Matches the behavior of the official MiGO mobile app

---

## Base URL
```
https://app.netatmo.net
```

## Authentication

### POST `/oauth2/token`
OAuth2 authentication with credentials.

**Request:**
```
Content-Type: application/x-www-form-urlencoded

client_id=<CLIENT_ID>
client_secret=<CLIENT_SECRET>
grant_type=password
username=<email>
password=<password>
user_prefix=sdbg
scope=all_scopes
```

> **Note:** The CLIENT_ID and CLIENT_SECRET values can be found in `custom_components/migo_netatmo/const.py`.

**Response:**
```json
{
  "access_token": "...",
  "expires_in": 10800,
  "refresh_token": "...",
  "scope": ["all_scopes"]
}
```

---

## Data Endpoints

### POST `/api/homesdata`
Retrieves the static configuration of homes (structure, schedules, modules).

**Request:**
```json
{
  "device_types": ["NAVaillant"],
  "sync_measurements": true,
  "app_identifier": "app_thermostat_sdbg",
  "home_id": null,
  "app_type": "app_thermostat_sdbg"
}
```

**Response - Key Data:**

#### Home
| Field | Description |
|-------|-------------|
| `id` | Unique home ID |
| `name` | Home name |
| `therm_mode` | Current mode: `schedule`, `away`, `hg` |
| `anticipation` | Heating anticipation enabled |
| `therm_setpoint_default_duration` | Default duration for manual setpoints (minutes) |
| `therm_heating_priority` | Heating priority: `eco`, `comfort` |
| `outdoor_temperature_source` | Outdoor temperature source |
| `capabilities` | Available features (e.g., `peak_and_off_peak_electricity_times`) |
| `linked_schedules` | Links between therm and event schedules |

#### Modules (NAVaillant - Gateway)
| Field | Description |
|-------|-------------|
| `id` | MAC address |
| `type` | `NAVaillant` |
| `subtype` | `NAEbusSdbg` |
| `oem_serial` | OEM serial number |
| `dhw_control` | DHW control type: `instantaneous` |
| `reachable` | Connected or not |
| `modules_bridged` | List of connected thermostats |

#### Modules (NAThermVaillant - Thermostat)
| Field | Description |
|-------|-------------|
| `id` | MAC address |
| `type` | `NAThermVaillant` |
| `room_id` | Associated room ID |
| `bridge` | Gateway ID |

#### Rooms
| Field | Description |
|-------|-------------|
| `id` | Unique room ID |
| `name` | Room name |
| `type` | Room type: `custom`, `living_room`, etc. |
| `module_ids` | Thermostats in the room |
| `measure_offset_NAVaillant_temperature` | Temperature offset |

#### Schedules
| Field | Description |
|-------|-------------|
| `id` | Schedule ID |
| `name` | Schedule name |
| `type` | `therm` (heating) or `event` (DHW) |
| `selected` | Active schedule |
| `default` | Default schedule |
| `hg_temp` | Frost guard temperature |
| `away_temp` | Away temperature |
| `zones` | Temperature zones |
| `timetable` | Hourly schedule |

#### Zones
| Field | Description |
|-------|-------------|
| `id` | 0=Comfort, 1=Night, 4=Eco |
| `type` | 0=Comfort, 1=Night, 5=Eco |
| `name` | Zone name (`Comfort`, `Night`, `Eco`) |
| `rooms_temp` | Temperatures per room |
| `modules` | Module configuration for this zone (DHW) |

#### Timetable
| Field | Description |
|-------|-------------|
| `zone_id` | Zone ID |
| `m_offset` | Minutes since Monday 00:00 |

---

### POST `/api/homestatus` or `/syncapi/v1/homestatus`
Retrieves real-time data (temperatures, states).

> **Note:** The app uses `/syncapi/v1/homestatus` for synchronous requests.

**Request:**
```json
{
  "app_identifier": "app_thermostat_sdbg",
  "home_id": "<home_id>",
  "device_types": ["NAVaillant"]
}
```

**Response - Module Data:**

#### NAVaillant (Gateway)
| Field | Type | Description |
|-------|------|-------------|
| `id` | string | MAC address (e.g., `70:ee:50:6b:e3:6a`) |
| `type` | string | `NAVaillant` |
| `subtype` | string | `NAEbusSdbg` |
| `wifi_strength` | int | WiFi signal strength (0-100) |
| `rf_strength` | int | RF signal strength (0-100) |
| `firmware_revision` | int | Firmware version (e.g., 1030) |
| `hardware_version` | int | Hardware version (e.g., 237) |
| `oem_serial` | string | Complete OEM serial number |
| `boiler_id` | string | Boiler ID |
| `boiler_error` | array | List of boiler errors |
| `ebus_error` | bool | eBus error |
| `emf_avail` | bool | EMF available |
| `dhw_enabled` | bool | DHW enabled |
| `dhw_setpoint_endtime` | int | DHW boost end time (timestamp) |
| `outdoor_temperature` | float | Outdoor temperature |
| `simple_heating_algo_deadband` | int | Hysteresis deadband (see `/api/changeheatingalgo`) |
| `sequence_id` | int | Sequence ID |

#### NAThermVaillant (Thermostat)
| Field | Type | Description |
|-------|------|-------------|
| `id` | string | MAC address (e.g., `07:00:00:6b:d5:9a`) |
| `type` | string | `NAThermVaillant` |
| `bridge` | string | Parent gateway ID |
| `battery_level` | int | Battery level (mV, e.g., 3772) |
| `battery_percent` | int | Battery percentage (0-100) |
| `battery_state` | string | State: `high`, `medium`, `low` |
| `rf_strength` | int | RF signal strength (0-100) |
| `firmware_revision` | int | Firmware version |
| `reachable` | bool | Reachable |
| `boiler_status` | bool | Boiler running |
| `last_seen` | int | Last contact (timestamp) |
| `last_message` | int | Last message (timestamp) |
| `radio_id` | int | Radio ID |

**Response - Room Data:**
| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Room ID |
| `therm_measured_temperature` | float | Measured temperature |
| `therm_setpoint_temperature` | float | Setpoint temperature |
| `therm_setpoint_mode` | string | Mode: `schedule`, `manual`, `home`, `hg`, `away` |
| `therm_setpoint_start_time` | int | Setpoint start (timestamp) |
| `therm_setpoint_end_time` | int | Setpoint end (timestamp) |
| `anticipating` | bool | Anticipation in progress |
| `reachable` | bool | Room reachable |

---

## Control Endpoints

### POST `/api/sethomedata`
Changes the global home mode (used by the app for mode changes).

**Request:**
```json
{
  "app_identifier": "app_thermostat_sdbg",
  "home": {
    "id": "<home_id>",
    "temperature_control_mode": "heating",
    "therm_mode": "schedule",
    "therm_mode_endtime": null
  }
}
```

**Available Modes:**
| Mode | Description |
|------|-------------|
| `schedule` | Schedule mode (Auto) |
| `away` | Away mode |
| `hg` | Frost guard mode |

---

### POST `/api/setthermmode`
Changes the global home mode (alternative API).

**Request:**
```json
{
  "home_id": "<home_id>",
  "mode": "schedule|away|hg"
}
```

---

### POST `/api/setroomthermpoint` (Official Netatmo API - Not Used)

> **Note:** This endpoint is documented in the [official Netatmo API](https://dev.netatmo.com/apidocumentation/energy) but is **not used** by this integration. We use `/api/setstate` instead, which provides more flexibility.

Sets the thermostat point for a specific room.

**Request:**
```json
{
  "home_id": "<home_id>",
  "room_id": "<room_id>",
  "mode": "manual|max|home",
  "temp": 20.0,
  "endtime": 1704067200
}
```

**Parameters:**

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `home_id` | Yes | string | The home ID |
| `room_id` | Yes | string | The room ID |
| `mode` | Yes | string | The mode to apply: `manual`, `max`, or `home` |
| `temp` | No | float | Temperature to set (required for `manual` mode) |
| `endtime` | No | int | Unix timestamp when the setting expires |

**Available Modes:**

| Mode | Description |
|------|-------------|
| `manual` | Set a specific temperature until `endtime` |
| `max` | Set maximum temperature (30°C) until `endtime` |
| `home` | Return to schedule mode |

**Notes on `endtime`:**
- Only meaningful for `manual` and `max` modes
- If not set, uses the default duration configured at account level (`therm_setpoint_default_duration`)
- Must be a Unix timestamp in the future
- When the time expires, the room returns to schedule mode

---

### POST `/api/setstate` or `/syncapi/v1/setstate`
Modifies the state of rooms or modules. **This is the endpoint used by this integration** instead of `setroomthermpoint`.

> **Note:** The app uses `/syncapi/v1/setstate` with an `x-correlationid` header.

**Request - Change room mode/temperature:**
```json
{
  "app_identifier": "app_thermostat_sdbg",
  "home": {
    "id": "<home_id>",
    "rooms": [{
      "id": "<room_id>",
      "therm_setpoint_mode": "manual|home|hg",
      "therm_setpoint_temperature": 20
    }]
  }
}
```

**Available Room Modes:**
| Mode | Description |
|------|-------------|
| `manual` | Manual mode with specific temperature |
| `max` | Maximum temperature (30°C) - useful for quick heating boost |
| `home` | Home/presence mode |
| `hg` | Frost guard mode (minimum temperature ~7°C) |

**Optional Parameters for Timed Setpoints:**

The `setstate` endpoint also supports timed setpoints (similar to `setroomthermpoint`):

```json
{
  "home": {
    "id": "<home_id>",
    "rooms": [{
      "id": "<room_id>",
      "therm_setpoint_mode": "manual",
      "therm_setpoint_temperature": 22,
      "therm_setpoint_end_time": 1704067200
    }]
  }
}
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `therm_setpoint_end_time` | int | Unix timestamp when the setpoint expires |

> **Note:** If `therm_setpoint_end_time` is not provided, the system uses `therm_setpoint_default_duration` from the home configuration.

**Request - Control DHW (Domestic Hot Water):**
```json
{
  "app_identifier": "app_thermostat_sdbg",
  "home": {
    "id": "<home_id>",
    "modules": [{
      "id": "<module_id>",
      "dhw_enabled": true|false
    }]
  }
}
```

---

### POST `/api/switchhomeschedule`
Changes the active schedule.

**Request:**
```json
{
  "home_id": "<home_id>",
  "schedule_id": "<schedule_id>"
}
```

---

### POST `/api/setheatingsystem`
Sets the heating system type.

**Request:**
```json
{
  "device_id": "<gateway_mac_address>",
  "heating_type": "radiator|convector|floor_heating|unknown"
}
```

**Available Heating Types:**
| Type | Description |
|------|-------------|
| `radiator` | Radiators |
| `convector` | Convector heaters |
| `floor_heating` | Floor heating |
| `unknown` | Unknown/Not set |

---

### POST `/api/changeheatingcurve`
Sets the heating curve (slope).

**Request:**
```json
{
  "device_id": "<gateway_mac_address>",
  "slope": 14
}
```

**Notes:**
- `slope` value is 10x the displayed value (e.g., 14 = 1.4)
- Range: 5-35 (0.5-3.5 in UI)
- Default: 14 (1.4)

---

### POST `/api/changeheatingalgo`
Sets the heating algorithm hysteresis threshold.

**Request:**
```json
{
  "device_id": "<gateway_mac_address>",
  "algo_type": "simple_algo",
  "algo_params": {
    "high_deadband": 15
  }
}
```

**Response:**
```json
{
  "status": "ok",
  "time_exec": 0.024837017059326172,
  "time_server": 1767980332
}
```

**Notes:**
- `high_deadband` = hysteresis × 10 - 1
- Range: 0-19 (0.1°C to 2.0°C in UI)
- Examples:
  - 0.1°C → `high_deadband = 0`
  - 0.4°C → `high_deadband = 3`
  - 1.6°C → `high_deadband = 15` (default)
  - 1.8°C → `high_deadband = 17`
  - 2.0°C → `high_deadband = 19`
- The current value is returned in homestatus as `simple_heating_algo_deadband` on the gateway module
- To convert back: hysteresis = (`simple_heating_algo_deadband` + 1) / 10

---

### POST `/api/sethomedata` - Advanced Settings

**Request - Set Anticipation:**
```json
{
  "home": {
    "id": "<home_id>",
    "anticipation": true|false
  }
}
```

**Request - Set DHW Storage Mode:**
```json
{
  "home": {
    "id": "<home_id>",
    "modules": [{
      "id": "<gateway_module_id>",
      "dhw_control": "water_tank|instantaneous"
    }]
  }
}
```

**Request - Set Manual Setpoint Default Duration:**
```json
{
  "home": {
    "id": "<home_id>",
    "therm_setpoint_default_duration": 180
  }
}
```

**Notes:**
- `therm_setpoint_default_duration` is in minutes
- Range: 5-720 (5 minutes to 12 hours)
- Default: 180 (3 hours)

---

### POST `/syncapi/v1/setconfigs`
Sets module or room configuration.

**Request - Set DHW Temperature:**
```json
{
  "home_id": "<home_id>",
  "home": {
    "modules": [{
      "id": "<gateway_module_id>",
      "dhw_setpoint_temperature": 55
    }]
  }
}
```

**Request - Set Temperature Offset:**
```json
{
  "home": {
    "id": "<home_id>",
    "rooms": [{
      "id": "<room_id>",
      "therm_setpoint_offset": -1.5
    }]
  }
}
```

**Notes for DHW Temperature:**
- Range: 45-65°C

**Notes for Temperature Offset:**
- Range: -5.0 to +5.0°C
- Step: 0.5°C

---

### POST `/api/synchomeschedule`
Modifies a schedule (zones, temperatures, times).

**Request - Heating Schedule (type: therm):**
```json
{
  "app_identifier": "app_thermostat_sdbg",
  "home_id": "<home_id>",
  "schedule_id": "<schedule_id>",
  "schedule_type": "therm",
  "name": "Default Schedule",
  "default": false,
  "selected": true,
  "hg_temp": 7,
  "away_temp": 16,
  "timetable_sunrise": [],
  "timetable_sunset": [],
  "zones": [
    {
      "id": 0,
      "type": 0,
      "name": "Comfort",
      "modules": [],
      "rooms": [
        {"id": "<room_id>", "therm_setpoint_temperature": 19}
      ]
    },
    {
      "id": 1,
      "type": 1,
      "name": "Night",
      "rooms": [
        {"id": "<room_id>", "therm_setpoint_temperature": 17}
      ]
    },
    {
      "id": 4,
      "type": 5,
      "name": "Eco",
      "rooms": [
        {"id": "<room_id>", "therm_setpoint_temperature": 16}
      ]
    }
  ],
  "timetable": [
    {"zone_id": 1, "m_offset": 0},
    {"zone_id": 0, "m_offset": 420},
    {"zone_id": 1, "m_offset": 1320}
  ]
}
```

**Request - DHW Schedule (type: event):**
```json
{
  "app_identifier": "app_thermostat_sdbg",
  "home_id": "<home_id>",
  "schedule_id": "<schedule_id>",
  "schedule_type": "event",
  "name": "Default",
  "default": false,
  "selected": true,
  "timetable_sunrise": [],
  "timetable_sunset": [],
  "zones": [
    {
      "id": 0,
      "name": "Comfort",
      "type": 0,
      "modules": [
        {"id": "<module_id>", "dhw_enabled": true}
      ]
    },
    {
      "id": 1,
      "modules": [
        {"id": "<module_id>", "dhw_enabled": false}
      ]
    },
    {
      "id": 4,
      "modules": [
        {"id": "<module_id>", "dhw_enabled": false}
      ]
    }
  ],
  "timetable": [
    {"zone_id": 1, "m_offset": 0},
    {"zone_id": 0, "m_offset": 420},
    {"zone_id": 1, "m_offset": 1320}
  ]
}
```

---

### POST `/api/addpushcontext`
Registers the context for push notifications.

**Request:**
```json
{
  "type": "Apple",
  "os_version": "26.2",
  "extra_param": {},
  "app_version": "2.4.2",
  "app_identifier": "app_thermostat_sdbg",
  "accept_alert": "true",
  "app_type": "app_thermostat_sdbg",
  "device_version": "iPhone15,2",
  "credentials": {
    "device_token": "<apns_token>",
    "device_voip_token": null
  }
}
```

---

### POST `/syncapi/v1/getconfigs`
Retrieves synchronization configurations.

---

## Thresholds and Constants

### WiFi Thresholds (NAVaillant)
| Level | RSSI Threshold |
|-------|----------------|
| Excellent | > 56 |
| Good | 56-71 |
| Fair | 71-86 |
| Poor | < 86 |

### RF Radio Thresholds
| Level | RSSI Threshold |
|-------|----------------|
| Excellent | < 60 |
| Good | 60-70 |
| Fair | 70-80 |
| Poor | > 90 |

### Thermostat Battery Thresholds
| State | Level (mV) | Percentage |
|-------|------------|------------|
| Full | > 4100 | 100% |
| High | 3600-4100 | 75% |
| Medium | 3200-3600 | 50% |
| Low | 3000-3200 | 25% |
| Critical | < 3000 | 0% |

---

## Error Codes

| Code | Name | Description |
|------|------|-------------|
| 1 | ACCESS_TOKEN_MISSING | Access token missing |
| 2 | INVALID_ACCESS_TOKEN | Invalid token |
| 3 | ACCESS_TOKEN_EXPIRED | Token expired |
| 9 | DEVICE_NOT_FOUND | Device not found |
| 10 | MISSING_ARGS | Missing arguments |
| 11 | INTERNAL_ERROR | Internal error |
| 13 | OPERATION_FORBIDDEN | Operation forbidden |
| 21 | INVALID_ARG | Invalid argument |
| 23 | USER_NOT_FOUND | User not found |
| 41 | DEVICE_UNREACHABLE | Device unreachable |

---

## Available Webhooks

| Event | Description |
|-------|-------------|
| `low_battery` | Low battery |
| `boiler_not_responding` | Boiler not responding |
| `boiler_responding` | Boiler responding |
| `ebus_error` | eBus error |
| `boiler_error` | Boiler error |
| `maintenance_status` | Maintenance status |
| `refill_water` | Refill water |
| `no_connect_24h` | No connection for 24h |
| `state_changed` | State changed |

---

## Identified Features for Home Assistant

### Climate Entities (per room)
- [x] Current temperature
- [x] Setpoint temperature
- [x] HVAC mode (Auto/Heat/Off)
- [x] Preset modes (Away, Hot water only, Frost Guard)

### Sensor Entities
- [x] Measured temperature
- [x] Thermostat battery (%)
- [x] Thermostat RF signal
- [x] Gateway WiFi signal
- [x] Outdoor temperature
- [x] Gateway firmware version
- [x] Thermostat firmware version
- [x] Room humidity

### Binary Sensor Entities
- [x] Boiler running
- [x] Thermostat reachable
- [x] Boiler error
- [x] eBus error
- [x] Anticipating (heating anticipation in progress)

### Switch Entities
- [x] Domestic Hot Water (DHW)
- [x] Heating anticipation

### Number Entities
- [x] Heating curve (slope)
- [x] DHW temperature
- [x] Temperature offset
- [x] Manual setpoint default duration
- [x] Hysteresis threshold

### Select Entities
- [x] Active schedule
- [x] Thermostat mode (schedule, away, hg)
- [x] Heating type (radiator, convector, floor_heating)

### Button Entities
- [x] Refresh data

### Services
- [ ] `migo.set_schedule` - Change schedule
- [ ] `migo.set_zone_temperature` - Modify zone temperature
- [ ] `migo.boost_dhw` - Force DHW

### Diagnostic Information
- [x] Gateway firmware version
- [x] Thermostat firmware version
- [x] OEM serial number
- [x] MAC address
- [x] Hardware version
