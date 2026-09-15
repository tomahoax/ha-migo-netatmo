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
| `/api/sethomedata` | Anticipation, manual setpoint duration, Away mode with an optional return time (`therm_mode`/`therm_mode_endtime`) |
| `/api/changeheatingcurve` | Heating curve (slope) adjustment |
| `/api/setheatingsystem` | Heating type configuration |
| `/api/changeheatingalgo` | Hysteresis threshold |
| `/api/getmeasure` | Historical data and boiler consumption |
| `/syncapi/v1/setconfigs` | DHW temperature, temperature offset, DHW always-on |

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
| `therm_mode_endtime` | Unix timestamp when `therm_mode` (while `"away"`) automatically reverts. **Not documented by Netatmo**, confirmed via a live debug-log capture - matches the return time shown in the MiGo app when leaving with "indicate a return date/time". Set via `sethomedata` (see below); absent when no return time is set. |
| `anticipation` | Heating anticipation enabled |
| `therm_setpoint_default_duration` | Default duration for manual setpoints (minutes) |
| `therm_heating_priority` | Heating priority: `eco`, `comfort` |
| `outdoor_temperature_source` | Outdoor temperature source |
| `capabilities` | Available features (e.g., `peak_and_off_peak_electricity_times`) |
| `linked_schedules` | Links between `therm` and `event` schedules. **Shape not documented by Netatmo** and not directly observed - the integration parses it defensively (mapping, list of pairs, or list of `{key: id, ...}` dicts) and falls back to picking the `event` schedule independently marked `selected` if it can't be resolved. See `helpers.get_event_schedule()`. |

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

### Event (DHW) schedules

Every home has two parallel families of schedules with the same names, zone
ids and timetables, distinguished by `type`: `therm` (room temperatures,
`zones[].rooms`) and `event` (DHW on/off per zone, `zones[].modules[].dhw_enabled`).
Both a `therm` and an `event` schedule are typically marked `selected: true`
at the same time - they are meant to be read together, not as alternatives.

**Resolving the DHW state for "right now"** (used by
`binary_sensor.migo_{home}_dhw_schedule`, see [entities](../entities.md#binary-sensors)):

1. Pick the active `event` schedule: prefer the one paired to the selected
   `therm` schedule via `linked_schedules` (shape not documented by Netatmo,
   parsed defensively - see `helpers.get_event_schedule()`), falling back to
   the `event` schedule independently marked `selected`.
2. Compute minutes elapsed since Monday 00:00 in the local timezone
   (`helpers.current_week_minutes()`).
3. In the schedule's `timetable` (not guaranteed sorted - sort by `m_offset`
   first), find the last entry whose `m_offset` is not in the future. If none
   qualifies (e.g. early Monday morning, before the week's first slot), wrap
   around to the timetable's last entry (`helpers.resolve_timetable_zone()`).
4. Look up that `zone_id` in `zones`, then read `dhw_enabled` from the module
   entry matching the gateway's `id` (falling back to the zone's single
   module if there's exactly one, since the module entry's `id` field is not
   always present in practice).
5. Force the result to `off` while the home's `therm_mode` is `"away"`: the
   Away temperature slot replaces the current schedule slot with hot water
   production disabled, so a plain timetable lookup would otherwise be
   misleading during Away.

**A caveat found in community testing:** the legacy `getthermostatsdata`
endpoint (see [Known limitations](#known-limitations-legacy-getthermostatsdata-endpoint)
below) also carries a per-zone DHW flag, `hw`, directly in its own schedule
data - but it is not kept in sync with the app once `event` schedules exist;
only `homesdata`'s `dhw_enabled` matches what the app actually shows. Do not
use `hw` for this.

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
| `simple_heating_algo_deadband` | int | Hysteresis deadband (see `/api/changeheatingalgo`) - documented, but **not seen in a live capture**; treat as unconfirmed |
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
- Default: 14 (1.4) as captured on the test installation this endpoint was traced from - **not a universal factory default**. This is an installation-specific calibration value (heating type, radiator sizing, ...) with no discoverable "true default": the API never echoes it back (see `docs/entities.md`'s note on `number.migo_{home}_heating_curve`), and a second real installation was confirmed at `2.6` instead during later development. `const.DEFAULT_HEATING_CURVE` (the heating curve number entity's no-data fallback) is a plain constant, not derived from this endpoint in any way - edit it to match your own installation

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
- Documented (not independently confirmed) to be returned in homestatus as
  `simple_heating_algo_deadband` on the gateway module - **not present in a
  live homestatus capture taken during later development**, reported
  alongside the hysteresis number entity's read side not reflecting a
  change made from the MiGo app. If a future capture confirms where the
  live value actually lives (homestatus, getconfigs, or elsewhere), update
  `number.py`'s `MigoHysteresisNumber._native_value_fallback` accordingly -
  until then, treat this endpoint and entity as write-only in practice
- To convert back, if this field is ever found: hysteresis = (`simple_heating_algo_deadband` + 1) / 10

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

**Request - Set DHW Always On:**
```json
{
  "home_id": "<home_id>",
  "home": {
    "modules": [{
      "id": "<gateway_module_id>",
      "dhw_always_on": true
    }]
  }
}
```

**Request - Set Temperature Offset:**
```json
{
  "home_id": "<home_id>",
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

**Notes for DHW Always On:**
- `dhw_always_on` is **not documented by Netatmo**, confirmed via a live
  debug-log capture of `/syncapi/v1/getconfigs`'s response - it sits on the
  same module entry as `dhw_setpoint_temperature`. Matches the MiGo app's
  "Toujours activée" toggle: forces the boiler to never suspend DHW heating,
  overriding the active schedule's per-slot production setting.

**Notes for Temperature Offset:**
- Range: -5.0 to +5.0°C
- Step: 0.5°C
- **`home_id` at the request root**, matching the DHW calls above - added
  after a live report that an earlier build (`home.id` only, no root-level
  `home_id`) neither set nor read back the real value: the request looked
  structurally valid and got a 200, but the offset never actually took
  effect server-side. Not independently confirmed by a fresh mitmproxy
  capture the way the DHW calls were - if this still doesn't take effect,
  that capture is the next step

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
Retrieves synchronization configurations, including per-module DHW settings
not present in `homesdata`/`homestatus`.

**Response - Key Data (per module, NAVaillant/Gateway):**
| Field | Description |
|-------|-------------|
| `dhw_setpoint_temperature` | Hot water temperature setpoint (°C) |
| `dhw_temperature_min` | Minimum allowed DHW setpoint (°C) |
| `dhw_temperature_max` | Maximum allowed DHW setpoint (°C) |
| `dhw_always_on` | Whether DHW production always stays on, overriding the schedule. **Not documented by Netatmo**, confirmed via a live debug-log capture - matches the MiGo app's "Toujours activée" toggle. |

---

### POST `/api/getmeasure`
Retrieves historical measurements and boiler consumption data.

> **Important:** This endpoint uses **form data** (`application/x-www-form-urlencoded`) instead of JSON. This is a legacy Netatmo API behavior.

**Request:**
```
Content-Type: application/x-www-form-urlencoded

device_id=<gateway_mac>&module_id=<thermostat_mac>&scale=1day&type=sum_boiler_on,sum_boiler_off&date_begin=<timestamp>
```

**Parameters:**
| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `device_id` | Yes | string | The gateway device MAC address (e.g., `70:ee:50:6b:e3:6a`) |
| `module_id` | Yes | string | The thermostat module MAC address (e.g., `04:00:00:6b:e3:6a`) |
| `scale` | Yes | string | Time scale: `30min`, `1hour`, `3hours`, `1day`, `1week`, `1month` |
| `type` | Yes | string | Comma-separated measure types |
| `date_begin` | No | int | Start timestamp (Unix) |
| `date_end` | No | int | End timestamp (Unix) |

**Available Measure Types:**
| Type | Unit | Description |
|------|------|-------------|
| `sum_boiler_on` | seconds | Boiler on time |
| `sum_boiler_off` | seconds | Boiler off time |
| `sum_energy_gaz_heating` | Wh | Gas burned for space heating |
| `sum_energy_gaz_hot_water` | Wh | Gas burned for domestic hot water |
| `sum_energy_elec_heating` | Wh | Boiler electricity use for heating |
| `sum_energy_elec_hot_water` | Wh | Boiler electricity use for hot water |

> **All six can be requested in a single call.** The response carries one value per
> requested type, positionally, in the order requested. Verified against a live
> NAVaillant gateway, so the energy measures cost no extra requests.

> **Note the French spelling `gaz`.** `sum_energy_gas_heating` is silently accepted
> and returns an **empty series rather than an error**, which is indistinguishable
> from "this hardware does not support it".

> **Energy is reported in Wh, at whole-kWh resolution** (values are always multiples
> of 1000). Calibrated against the MiGO app's own weekly consumption figures: the
> app's electricity values matched the API exactly.

`scripts/probe_energy.py` exists to test candidate measure types against a real
account, which is the only reliable way to learn what this undocumented endpoint
supports.

**Response:**
```json
{
  "body": {
    "1704067200": [3600, 82800],
    "1704153600": [4200, 82200]
  },
  "status": "ok",
  "time_exec": 0.05,
  "time_server": 1704240000
}
```

**Response Format:**

The body comes back in one of two shapes, and both are seen in practice:

- A dictionary keyed by Unix timestamp, each value an array of one element per
  requested measure type, in the requested order.
- A list of series objects, each with `beg_time`, `step_time` and `value`, where
  `value` is a list of those same arrays. Timestamps are derived as
  `beg_time + index * step_time`.

The scale determines the granularity (e.g. `1day` returns daily totals). The
integration requests `1day`.

**Notes:**
- Used by this integration for the **Daily boiler runtime** sensor and the four
  energy sensors
- The energy measures are what the Energy dashboard accepts (`device_class: energy`
  in kWh). The runtime measure is not, and no arithmetic on it can be: the dashboard
  filters on device class and unit, not on state class
- The `device_id` and `module_id` are MAC addresses found in the `/api/homesdata`
  response

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

## Known Limitations: Legacy `getthermostatsdata` Endpoint

Community forum testing (see project CHANGELOG for the thread reference)
found that `POST https://api.netatmo.com/api/getthermostatsdata` - the
legacy endpoint used by the older `vaillant-vsmart` integration, on a
*different host* than everything else in this document (`api.netatmo.com`
instead of `app.netatmo.net`) - accepts the same bearer token obtained via
this integration's OAuth flow, and returns fields not present in
`homesdata`/`homestatus`:

| Field | Description |
|-------|-------------|
| `system_mode` | The boiler quick-action mode as a single value: `winter` / `summer` / `frostguard` |
| `setpoint_away.setpoint_activate` | Boolean Away flag, radio-synced with the thermostat (can lag `homesdata`'s `therm_mode` by a few minutes right after a change) |
| `setpoint_hwb` | DHW boost state |
| `dhw`, `dhw_min`, `dhw_max` | DHW temperature and its configured range |

**This integration does not call this endpoint.** `therm_mode` (home-level,
already returned by `homesdata` at no extra API cost) and
`therm_setpoint_mode` (room-level) are sufficient to derive the boiler mode
and Away state used by `sensor.migo_{home}_boiler_mode`,
`binary_sensor.migo_{home}_away_mode` and the climate preset - see
`helpers.derive_boiler_mode()`. Calling a second, undocumented Netatmo host
with a token minted for a different one was judged to need its own
verification (real traffic capture, response envelope shape - this endpoint
returns `body.devices[]` rather than `body.homes[]`) before depending on it.
A throwaway probe script for that verification exists in this project's
development history; revisit `dhw_min`/`dhw_max` (DHW temperature range) if
that verification is done, since it is the one piece of data with no
existing equivalent path.

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
