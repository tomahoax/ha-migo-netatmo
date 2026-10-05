# Entities Reference

This page lists all entities created by the MiGo integration.

## Device Architecture

The integration creates **two separate devices** in Home Assistant:

### Gateway (NAVaillant)

The main communication hub connected to your boiler via eBus. Provides WiFi connectivity and controls DHW (Domestic Hot Water).

**Device Info:**
- **Manufacturer**: Saunier Duval
- **Model**: NAVaillant
- **Connection**: WiFi + eBus

### Thermostat (NAThermVaillant)

The wall-mounted thermostat connected to the Gateway via RF (radio). Battery powered.

**Device Info:**
- **Manufacturer**: Saunier Duval
- **Model**: NAThermVaillant
- **Connected via**: Gateway (via_device relationship)

### Device Page Organization

Each device's page in Home Assistant auto-sorts its entities into up to
four cards, driven purely by domain (writable vs. read-only) and
`entity_category`. When adding a new entity, pick its category by asking
what kind of thing it is, not by matching a neighbor at random:

| Card | `entity_category` | What belongs there |
|------|--------------------|---------------------|
| **Controls** | *(unset)*, writable domain | An operational toggle/action with an immediate, user-facing effect - something you'd actually flip day to day (DHW boost, Away mode, Away until, Heating anticipation, the active schedule, the climate entity itself). |
| **Configuration** | `config` | A setpoint or tuning value you set occasionally and mostly leave alone (DHW temperature, heating curve, hysteresis, manual setpoint duration, temperature offset). |
| **Sensors** | *(unset)*, read-only domain | A measured or derived value you monitor (temperatures, boiler mode, scheduled DHW state). |
| **Diagnostic** | `diagnostic` | Read-only technical/troubleshooting data (signal strength, battery, error flags) - plus a read-only companion to a Controls entity, when its only purpose is history graphs or automation triggers rather than being the entity a user interacts with (Away mode's binary_sensor companion to its switch). |

Firmware/hardware version, serial number and MAC address are **not**
duplicated as entities: Home Assistant's built-in "Device info" card already
shows them (`sw_version`/`hw_version`/`serial_number`/`connections` set in
each entity's `device_info`, see `entity.py`). Adding a `sensor` for one of
these would just repeat that card.

---

## Climate

| Entity ID Pattern | Name | Device | Description |
|-------------------|------|--------|-------------|
| `climate.migo_netatmo_climate_{room_id}` | {Home Name} Thermostat | Thermostat | Main thermostat control |

### HVAC Modes

| Mode | API Mode | Description |
|------|----------|-------------|
| **Auto** | `schedule` | Follows the active schedule from MiGO app |
| **Heat** | `manual` | Manual override using configured duration (see "Manual setpoint duration" setting) |
| **Off** | `hg` | Frost guard protection (keeps minimum temperature) |

### Presets

MiGo stacks three independent notions: the boiler's own quick-action mode
(Normal / DHW only / Frost guard, home-level `therm_mode` combined with the
room's `therm_setpoint_mode`), a home-level Away flag (also `therm_mode`),
and the room's own setpoint. A single room-level API field cannot represent
all three, so the climate entity derives `hvac_mode` and `preset_mode` from
both the home's `therm_mode` and the room's `therm_setpoint_mode` together -
see `climate.MigoClimate._home_therm_mode` for the exact precedence.

| Preset | Source | Description |
|--------|--------|-------------|
| **Normal** | nothing else applies | The baseline state: home `therm_mode == "schedule"`, `temperature_control_mode == "heating"`, room not overridden. Read/write, via `sethomedata` (clears the room to `"home"` and the home to `schedule`/`heating` unconditionally, including a stale `"cooling"` left over from Hot water only, and an active Away). |
| **Away** | home `therm_mode == "away"` | Away mode - reduced temperature. Read/write, via `sethomedata` (no return-time support - see `datetime.migo_{home}_away_until` below for that). |
| **Frost guard** | home `therm_mode == "hg"` | Real standby: the boiler is stopped. Read/write, via `sethomedata` directly at the home level - distinct from Hot water only below, which writes `"hg"` at the room level instead. |
| **Hot water only** | room `therm_setpoint_mode == "hg"` while home `therm_mode` is not `"hg"` | MiGo's "DHW only" quick-action. Read/write: `therm_setpoint_mode == "hg"` at the room level (`setstate`, the same call selecting HVAC mode Off makes) plus `temperature_control_mode == "cooling"` home-wide (`sethomedata`, its own separate request - the API rejects combining a `therm_mode` change with `"cooling"` in one call). Preserves an active Away rather than clearing it, unlike Normal. |
| **Boost** | room `therm_setpoint_mode == "manual"` at max temperature | Forces maximum temperature (30°C) for 1 hour |

> **Note:** When Away is combined with any room-level override (DHW only,
> Frost guard, a manual setpoint, or Boost - the app allows all of these),
> the climate preset shows Away - it takes priority since it is the more
> actionable state, and is checked before any of the others. The other
> state remains visible independently: the boiler quick-action mode via
> `sensor.migo_{home}_boiler_mode` below, Away itself via
> `binary_sensor.migo_{home}_away_mode` / `switch.migo_{home}_away_mode`.

### Attributes

- `current_temperature`: Current room temperature
- `temperature`: Target temperature
- `hvac_mode`: Current mode (off, heat, auto)
- `hvac_action`: Current action (off, heating, idle)
- `preset_mode`: Active preset (normal, away, frost_guard, dhw_only, boost)

### Services

- `climate.set_temperature`: Set target temperature
- `climate.set_hvac_mode`: Change HVAC mode
- `climate.set_preset_mode`: Activate a preset

---

## Sensors

Four sensors are marked *disabled by default*: the two signal strengths and the two
firmware versions. They are verbose diagnostics, so a fresh install creates them
switched off to save recorder storage. Enable any of them from the device page or
from **Settings** → **Devices & services** → **Entities**, filtering on
**Disabled**. Your choice persists across integration updates.

### Gateway Sensors

| Entity ID Pattern | Name | Unit | Description |
|-------------------|------|------|-------------|
| `sensor.migo_{home}_outdoor_temperature` | Outdoor Temperature | °C | Outdoor temperature from gateway |
| `sensor.migo_{home}_wifi_signal` | WiFi Signal | % | Gateway WiFi signal strength (disabled by default) |
| `sensor.migo_{home}_gateway_firmware` | Gateway Firmware | - | Gateway firmware version (disabled by default) |

### Thermostat Sensors

| Entity ID Pattern | Name | Unit | Description |
|-------------------|------|------|-------------|
| `sensor.migo_{room}_temperature` | {Room} Temperature | °C | Room temperature |
| `sensor.migo_{room}_humidity` | {Room} Humidity | % | Room humidity (if available) |
| `sensor.migo_{home}_battery` | Battery | % | Thermostat battery level |
| `sensor.migo_{home}_rf_signal` | RF Signal | % | Thermostat radio signal (disabled by default) |
| `sensor.migo_{home}_thermostat_firmware` | Thermostat Firmware | - | Thermostat firmware version (disabled by default) |

### Energy Consumption (Gateway)

| Entity ID Pattern | Name | Unit | Description |
|-------------------|------|------|-------------|
| `sensor.migo_{gateway}_gas_for_heating` | Gas for heating | kWh | Measured gas burned for space heating, per day |
| `sensor.migo_{gateway}_gas_for_hot_water` | Gas for hot water | kWh | Measured gas burned for domestic hot water, per day |
| `sensor.migo_{gateway}_electricity_for_heating` | Electricity for heating | kWh | The boiler's own electricity use for heating |
| `sensor.migo_{gateway}_electricity_for_hot_water` | Electricity for hot water | kWh | The boiler's own electricity use for hot water |
| `sensor.migo_{gateway}_daily_boiler_runtime` | Daily Boiler Runtime | s | Daily boiler operation time |

The four energy sensors are `device_class: energy`, `state_class: total_increasing`,
in kWh, so they can be added to the Energy dashboard directly. Values are read in Wh
and divided by 1000; the API reports whole kWh, so nothing is lost.

Note that the **gas** sensors also appear in the dashboard's *electricity* picker,
and must not be added there. Home Assistant accepts `device_class: energy` for both
source types, and a gas figure measured in kWh has no alternative device class:
`device_class: gas` requires a volume unit. See
[Energy Dashboard Integration](../README.md#energy-dashboard-integration).

The daily boiler runtime sensor:
- `device_class`: duration
- `state_class`: total_increasing, so it gets long-term statistics
- Resets daily

It **cannot** be added to the Energy dashboard directly, because that dashboard
requires `device_class: gas` (m³, ft³, L, CCF, MCF) or `device_class: energy`
(kWh, MJ, ...) and this one measures time. Use the four energy sensors above
instead; see
[Energy Dashboard Integration](../README.md#energy-dashboard-integration).

**Data Source:**
- Retrieved via `/api/getmeasure` endpoint using gateway `device_id` and thermostat `module_id`
- The gateway MAC address (e.g., `70:ee:50:6b:e3:6a`) is used as the device identifier
- Uses form-data format (legacy Netatmo API)

**Extra Attributes:**
- `boiler_off_time`: Time boiler was off (seconds)
- `measurement_timestamp`: Unix timestamp of the measurement

### Boiler Mode (Gateway)

| Entity ID Pattern | Name | Description |
|-------------------|------|--------------|
| `sensor.migo_{home}_boiler_mode` | Boiler Mode | The boiler's "Actions rapides" quick-action mode: `normal`, `dhw_only` (Hot water only), or `frost_guard`. Derived from the home's `therm_mode` and the rooms' `therm_setpoint_mode` - MiGo does not return this as a single field. Independent of Away, which the app lets you combine with any of these three. |

---

## Binary Sensors

### Gateway Binary Sensors

| Entity ID Pattern | Name | Device Class | Description |
|-------------------|------|--------------|-------------|
| `binary_sensor.migo_{home}_boiler_error` | Boiler Error | problem | Boiler error detected |
| `binary_sensor.migo_{home}_ebus_error` | eBus Error | problem | eBus communication error |
| `binary_sensor.migo_{home}_away_mode` | Away Mode | - | Home-level Away flag (`therm_mode == "away"`). Read-only companion to `switch.migo_{home}_away_mode`. |
| `binary_sensor.migo_{home}_dhw_schedule` | Scheduled DHW | - | Whether hot water production is enabled for the *currently active* time slot of the selected DHW (`event`-type) schedule. Forced `off` while Away is active, even if the schedule/slot itself can't be resolved. State is `unknown` (never a guessed value) if it can't be resolved and Away is not active. See [API Reference](api/reference.md#event-dhw-schedules) for how the slot is resolved. |

### Thermostat Binary Sensors

| Entity ID Pattern | Name | Device Class | Description |
|-------------------|------|--------------|-------------|
| `binary_sensor.migo_{home}_boiler_status` | Boiler Status | running | Boiler is heating |
| `binary_sensor.migo_{home}_reachable` | Device Reachable | connectivity | Thermostat is reachable |

---

## Switches

| Entity ID Pattern | Name | Device | Description |
|-------------------|------|--------|-------------|
| `switch.migo_{home}_dhw_boost` | DHW Boost | Gateway | Hot water temperature boost |
| `switch.migo_{home}_anticipation` | Heating Anticipation | Home | Predictive heating |
| `switch.migo_{home}_away_mode` | Away Mode | Gateway | Home-wide Away flag. Writes via `sethomedata` with an explicit `endtime=None` (rather than `setthermmode`, which has no such parameter), so toggling from here also clears any return time set via `datetime.migo_{home}_away_until` or the MiGo app itself. Never touches room state, so the room-level boiler quick-action (Normal/DHW only) is always untouched; real Frost guard (the home-level third quick-action state) shares the same underlying field as Away, so it is replaced if active, same as in the MiGo app itself. |
| `switch.migo_{home}_dhw_always_on` | DHW Always On | Gateway | Matches the MiGo app's "Toujours activée" DHW setting: forces the boiler to never suspend hot water heating, overriding the active schedule's per-slot production setting. Read/write via `getconfigs`/`setconfigs`'s `dhw_always_on`, the same module-level config field pair as `number.migo_{home}_dhw_temperature`. |

---

## Numbers

### Gateway Controls

| Entity ID Pattern | Name | Range | Description |
|-------------------|------|-------|-------------|
| `number.migo_{home}_dhw_temperature` | DHW Temperature | 45-60°C | Hot water temperature setpoint |
| `number.migo_{home}_hysteresis` | Hysteresis Threshold | 0.1-2.0°C | Heating algorithm threshold |
| `number.migo_{home}_heating_curve` | Heating Curve | 0.0-5.0 | Heating curve slope adjustment. Write-only: never echoed back by the API, so this always shows either what was last set from Home Assistant or `DEFAULT_HEATING_CURVE` (`const.py`) - never the boiler's real current value on its own |

### Home Controls

| Entity ID Pattern | Name | Range | Description |
|-------------------|------|-------|-------------|
| `number.migo_{home}_manual_setpoint_duration` | Manual Setpoint Duration | 5-720 min | Default duration for manual temperature changes |

### Room Controls

| Entity ID Pattern | Name | Range | Description |
|-------------------|------|-------|-------------|
| `number.migo_{room}_temperature_offset` | Temperature Offset | -5.0 to +5.0°C | Room temperature calibration |

---

## Selects

| Entity ID Pattern | Name | Options | Description |
|-------------------|------|---------|-------------|
| `select.migo_{home}_schedule` | Active Schedule | (Your configured schedules) | Switch between schedules |

---

## Date/Time

| Entity ID Pattern | Name | Description |
|-------------------|------|-------------|
| `datetime.migo_{home}_away_until` | Away Until | Sets a return date/time when activating Away, matching the MiGo app's own option. Writes via `sethomedata`'s `therm_mode`/`therm_mode_endtime`, activating Away and setting the return time in one action - separate from `switch.migo_{home}_away_mode`, which stays on the simpler indefinite on/off call. `therm_mode_endtime` is echoed back on `homesdata`, so the value survives a Home Assistant restart and reflects a return time set directly in the MiGo app, as long as `therm_mode` is still `"away"`. Home Assistant's `datetime` platform has no way to clear a value back to empty from its own more-info dialog - toggling `switch.migo_{home}_away_mode` (either direction) clears it, server-side included. There is no way to clear just the return time while staying Away indefinitely (a dedicated button for that, `reset_away_until`, was removed as redundant) - toggling Away off and back on is the only way. |

---

## Configuration Options

After installation, you can configure the integration via **Settings** → **Devices & services** → **MiGo (Netatmo)** → **Configure**:

| Option | Description | Range | Default |
|--------|-------------|-------|---------|
| **Email** | MiGO account email | - | - |
| **Password** | MiGO account password | - | - |
| **Client ID** | Custom OAuth client ID (optional) | - | Default MiGO app |
| **Client Secret** | Custom OAuth client secret (optional) | - | Default MiGO app |
| **User Prefix** | Custom user prefix (optional) | - | sdbg |
| **Update interval** | How often to poll the API for updates | 60-3600 seconds | 300 seconds (5 min) |
