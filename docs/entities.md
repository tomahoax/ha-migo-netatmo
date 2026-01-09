# Entities Reference

This page lists all entities created by the MiGo integration.

## Climate

| Entity ID Pattern | Name | Description |
|-------------------|------|-------------|
| `climate.migo_netatmo_climate_{room_id}` | {Room Name} | Main thermostat control |

### Attributes

- `current_temperature`: Current room temperature
- `temperature`: Target temperature
- `hvac_mode`: Current mode (off, heat, auto)
- `hvac_action`: Current action (off, heating, idle)
- `preset_mode`: Active preset (away, hot_water_only, frost_guard, or None)

### Services

- `climate.set_temperature`: Set target temperature
- `climate.set_hvac_mode`: Change HVAC mode
- `climate.set_preset_mode`: Activate a preset

## Sensors

### Temperature and Humidity

| Entity ID Pattern | Name | Unit |
|-------------------|------|------|
| `sensor.migo_{room}_temperature` | {Room} Temperature | °C |
| `sensor.migo_{room}_humidity` | {Room} Humidity | % |
| `sensor.migo_outdoor_temperature` | Outdoor Temperature | °C |

### Device Status

| Entity ID Pattern | Name | Description |
|-------------------|------|-------------|
| `sensor.migo_battery` | Battery | Thermostat battery level (%) |
| `sensor.migo_wifi_strength` | WiFi Signal | Gateway WiFi signal strength |
| `sensor.migo_rf_strength` | RF Signal | Thermostat radio signal |
| `sensor.migo_gateway_firmware` | Gateway Firmware | Firmware version |
| `sensor.migo_thermostat_firmware` | Thermostat Firmware | Firmware version |
| `sensor.migo_heating_type` | Heating Type | System type (radiators, floor, etc.) |

## Binary Sensors

| Entity ID Pattern | Name | Device Class |
|-------------------|------|--------------|
| `binary_sensor.migo_boiler_status` | Boiler Status | running |
| `binary_sensor.migo_boiler_error` | Boiler Error | problem |
| `binary_sensor.migo_reachable` | Device Reachable | connectivity |
| `binary_sensor.migo_ebus_error` | eBus Error | problem |

## Switches

| Entity ID Pattern | Name | Description |
|-------------------|------|-------------|
| `switch.migo_dhw_boost` | DHW Boost | Hot water temperature boost |
| `switch.migo_anticipation` | Heating Anticipation | Predictive heating |

## Numbers

| Entity ID Pattern | Name | Range |
|-------------------|------|-------|
| `number.migo_dhw_temperature` | DHW Temperature | 45-60°C |
| `number.migo_manual_setpoint_duration` | Manual Setpoint Duration | 5-720 min |
| `number.migo_temperature_offset` | Temperature Offset | -5.0 to +5.0°C |
| `number.migo_hysteresis` | Hysteresis Threshold | 0.1-2.0°C |

## Selects

| Entity ID Pattern | Name | Options |
|-------------------|------|---------|
| `select.migo_therm_mode` | Thermostat Mode | Auto, Away, Frost guard |
| `select.migo_schedule` | Active Schedule | (Your configured schedules) |

## Buttons

| Entity ID Pattern | Name | Description |
|-------------------|------|-------------|
| `button.migo_refresh` | Refresh | Force data refresh from API |

## Device Info

All entities are grouped under a single device representing your MiGO home. The device includes:

- **Manufacturer**: Saunier Duval
- **Model**: MiGO Thermostat
- **Firmware**: Gateway firmware version
- **Serial Number**: Gateway OEM serial (if available)
