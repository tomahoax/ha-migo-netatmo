# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.10.0] - 2026-01-04

### Changed
- **Code refactoring** - Improved maintainability and reduced code duplication
  - Added `MigoApiControlMixin` to centralize API call + refresh pattern
  - `MigoControlEntity` and `MigoHomeControlEntity` now use the shared mixin
  - `MigoClimate` now inherits from `MigoApiControlMixin` for consistency
  - Added `get_home_id_or_log_error()` helper to reduce boilerplate validation code
  - Optimistic cache for configuration values not returned by API (heating curve, DHW temp, temp offset, anticipation)

### Fixed
- **Configuration entities not updating** - Fixed issue where Configuration entities (Heating curve, DHW temperature, Temperature offset, Anticipation) were not updating after modification due to Netatmo API not returning these values

---

## [0.9.1] - 2026-01-04

### Added
- **Brand icons** - Added `brands/` folder for proper logo display in HACS and Home Assistant
- **My Home Assistant button** - One-click HACS installation button in README

### Changed
- **Improved documentation** - Simplified HACS installation instructions with collapsible manual steps

---

## [0.9.0] - 2026-01-04

### Changed
- **Home Assistant best practices compliance** - Improved code quality for Bronze tier
  - Refactored `button.py` to inherit from `MigoHomeEntity` (consistent device_info)
  - Improved type hints across all entity files (switch, select, number, climate)
  - Added missing translations for `dhw_temperature` and `temperature_offset`
  - Added config flow tests (`tests/test_config_flow.py`)

---

## [0.8.0] - 2026-01-04

### Changed
- **Enhanced debug logging** - Comprehensive logging for troubleshooting
  - All API requests now log URL and payload (DEBUG level)
  - All API responses now log status code and data (DEBUG level)
  - All API errors now log full error details (ERROR level)
  - All entity control operations now log start and completion (DEBUG level)
  - Coordinator refresh now logs processing statistics (DEBUG level)
  - Config flow now logs authentication progression (DEBUG level)

### How to enable debug logs
Add to your Home Assistant `configuration.yaml`:
```yaml
logger:
  logs:
    custom_components.migo_netatmo: debug
```

---

## [0.7.0] - 2026-01-04

### Added
- **DHW Temperature control** - Set hot water temperature (45-65°C)
- **Temperature Offset control** - Adjust room temperature calibration (-5.0 to +5.0°C)

---

## [0.6.0] - 2026-01-04

### Changed
- **Major code refactoring** - Improved maintainability and reduced code duplication
  - Added `generate_unique_id()` and `get_devices_by_type()` helper functions
  - Added `MigoControlEntity` and `MigoHomeControlEntity` base classes for entities with API control
  - Refactored `sensor.py`: 8 classes → 2 generic classes with configuration-driven approach
  - Refactored `binary_sensor.py`: 5 classes → 2 generic classes with configuration-driven approach
  - Updated `switch.py`, `select.py`, `number.py` to use new base classes
  - Reduced total lines of code by ~20% while maintaining functionality

---

## [0.5.3] - 2026-01-04

### Fixed
- **Heating curve display** - Fixed heating curve not showing actual API value
  - Read from `heating_curve_slope` field (not `slope`)

---

## [0.5.2] - 2026-01-04

### Fixed
- **Heating type value** - Fixed 400 Bad Request error when changing heating type
  - Changed `radiators` to `radiator` (singular form as expected by API)

---

## [0.5.1] - 2026-01-04

### Fixed
- **Heating type API** - Fixed heating type changes not being applied
  - Changed from `/api/sethomedata` to `/api/setheatingsystem` endpoint
  - Simplified request format to `{device_id, heating_type}` (matching official MiGO app)

---

## [0.5.0] - 2026-01-04

### Changed
- **Improved entity organization** - Better categorization for cleaner UI display
  - WiFi signal, RF signal sensors → DIAGNOSTIC (hidden by default)
  - eBus error, Boiler error sensors → DIAGNOSTIC (hidden by default)
  - Heating type select → CONFIG (configuration section)
  - Heating curve number → CONFIG (configuration section)
  - Anticipation switch → CONFIG (configuration section)

---

## [0.4.1] - 2026-01-03

### Fixed
- **Heating type select entity** - Fixed 400 Bad Request error when changing heating type
  - The API requires the sethomedata endpoint with home.modules structure instead of the setheatingsystem endpoint

---

## [0.4.0] - 2026-01-03

### Added
- **Advanced heating settings**:
  - Heating curve (slope) number entity - Adjust heating curve from 0.5 to 3.5
  - Heating type select entity - Choose between radiators, convector, floor heating
  - Heating anticipation switch - Enable/disable heating anticipation
- **API Documentation** - Complete documentation of new control endpoints:
  - `POST /api/sethomedata` - Set heating type, anticipation, DHW storage mode, setpoint duration
  - `POST /api/changeheatingcurve` - Set heating curve slope
  - `POST /syncapi/v1/setconfigs` - Set DHW temperature, temperature offset

---

## [0.3.0] - 2025-01-03

### Added
- **Outdoor temperature sensor** - Displays external temperature from the gateway
- **Climate preset modes** (Quick actions):
  - Away (Absent)
  - Hot water only (Eau chaude seulement)
  - Frost guard (Hors-gel)

---

## [0.1.0] - 2025-01-03

### Added
- Initial release of MiGo (Netatmo) integration for Home Assistant
- Support for Saunier Duval thermostats via MiGO app (Netatmo API)
- **Climate entity** with Auto/Heat/Off modes and temperature control
- **Sensors**:
  - Room temperature and humidity
  - Battery level (thermostat)
  - WiFi signal strength (gateway)
  - RF signal strength (thermostat)
  - Gateway and thermostat firmware versions
- **Binary sensors**:
  - Boiler status (running/idle)
  - Boiler error detection
  - Device reachable status
  - eBus error detection
  - Heating anticipation in progress
- **Switch**: Domestic Hot Water (DHW) control
- **Select entities**:
  - Thermostat mode (Auto/Away/Frost guard)
  - Active schedule selection
- **Button**: Manual data refresh
- Multi-language support (English, French)
- GitHub Actions CI/CD workflows

### Notes
- This integration uses the Netatmo API (app.netatmo.net)
- NOT compatible with MiGO Link or myVAILLANT apps
