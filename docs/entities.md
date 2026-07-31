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

| Preset | API Mode | Description |
|--------|----------|-------------|
| **Away** | `away` | Away mode - reduced temperature |
| **Frost guard** | `hg` | Frost protection mode |
| **Boost** | `manual` | Forces maximum temperature (30°C) for 1 hour |

> **Note:** The preset is cleared (set to None) when switching back to Auto mode.

### Attributes

- `current_temperature`: Current room temperature
- `temperature`: Target temperature
- `hvac_mode`: Current mode (off, heat, auto)
- `hvac_action`: Current action (off, heating, idle)
- `preset_mode`: Active preset (away, frost_guard, boost, or None)

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

---

## Binary Sensors

### Gateway Binary Sensors

| Entity ID Pattern | Name | Device Class | Description |
|-------------------|------|--------------|-------------|
| `binary_sensor.migo_{home}_boiler_error` | Boiler Error | problem | Boiler error detected |
| `binary_sensor.migo_{home}_ebus_error` | eBus Error | problem | eBus communication error |

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

---

## Numbers

### Gateway Controls

| Entity ID Pattern | Name | Range | Description |
|-------------------|------|-------|-------------|
| `number.migo_{home}_dhw_temperature` | DHW Temperature | 45-60°C | Hot water temperature setpoint |
| `number.migo_{home}_hysteresis` | Hysteresis Threshold | 0.1-2.0°C | Heating algorithm threshold |
| `number.migo_{home}_heating_curve` | Heating Curve | 0.0-5.0 | Heating curve slope adjustment |

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

## Buttons

| Entity ID Pattern | Name | Description |
|-------------------|------|-------------|
| `button.migo_{home}_refresh` | Refresh | Force data refresh from API |
| `button.migo_{home}_reset_heating_curve` | Reset Heating Curve | Reset heating curve to default value (1.5) |

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
