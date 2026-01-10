# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Heating curve control** - New number entity to adjust heating curve slope (0.0-5.0)
- **Reset heating curve button** - Button to reset heating curve to default value (1.5)
- **Configuration options** - Ability to modify credentials and OAuth settings in options flow
  - Email, Password, Client ID, Client Secret, User Prefix can now be changed after setup
  - Credentials are validated before saving

### Fixed
- **Boiler runtime sensor not reporting data** - Fixed issue where the Daily Boiler Runtime sensor showed "Unknown"
  - Changed from `/api/getroommeasure` (home_id/room_id) to `/api/getmeasure` (device_id/module_id)
  - The `getmeasure` endpoint uses form-data instead of JSON (legacy Netatmo API)
  - Consumption data is now indexed by gateway device_id (MAC address)
  - Aligned with Vaillant vSmart integration approach

### Changed
- **Code cleanup** - Removed unused code and constants
  - Removed `get_room_measure()` API method (replaced by `get_measure()`)
  - Removed unused API endpoint constants
  - Removed duplicate preset constants from `const.py`
  - Renamed `get_consumption(room_id)` to `get_consumption(device_id)` for clarity
- **Diagnostic entities** - Moved Battery and Reachable sensors to Diagnostic category (hidden by default)

### Documentation
- Updated API reference to document `/api/getmeasure` endpoint with form-data format
- Updated entities documentation to explain boiler runtime data source
- Updated architecture documentation with consumption data flow
- Added configuration options documentation

---

## [0.30.1] - 2026-01-10

### Fixed
- **Tests** - Prevent aiohttp thread leak in API tests
- **Imports** - Move import to top-level for better code organization

### Changed
- **Climate entity naming** - Simplified climate entity naming convention
- **Device info** - Added gateway MAC address to device info for better identification

### Documentation
- Enhanced API documentation

---

## [0.30.0] - 2026-01-09

### Changed
- **Major code refactoring** - Improved maintainability and code organization
  - Added `MigoRoomControlEntity` base class for room entities with API control
  - Use `DEFAULT_*` constants for number entities (DHW temp, hysteresis, etc.)
  - Added climate preset mode constants to `const.py`
  - Refactored `climate.py` to use `MigoRoomControlEntity`

### Added
- **Development environment** - VS Code dev containers support (`.devcontainer/`)
- **Issue templates** - GitHub issue templates for bugs and feature requests
- **Translations** - Added Spanish (es), Italian (it), and Russian (ru) translations
- **Testing** - Comprehensive test suite
  - 8 tests for configuration flow
  - 7 tests for API client
  - 18 tests for climate entity
  - Total: 46 tests passing

### Documentation
- Restructured `docs/` with proper hierarchy (index, installation, config, entities, troubleshooting)
- Moved API reference to `docs/api/reference.md`
- Added development guides (contributing, architecture, testing)

### DevOps
- Enhanced `dependabot.yml` with GitHub Actions ecosystem support

---

## [0.23.0] - 2026-01-09

### Documentation
- Updated README with current features and installation instructions

---

## [0.20.3] - 2026-01-09

### Added
- **DHW Temperature control** - Set hot water temperature (45-60°C)

---

## [0.20.2] - 2026-01-09

### Fixed
- **Heating type entity** - Converted heating type from select to read-only sensor
  - The API does not support changing heating type dynamically

---

## [0.20.1] - 2026-01-09

### Added
- **Manual setpoint duration** - Configure default duration for manual temperature changes (5-720 min)

### Fixed
- **DHW Boost naming** - Fixed DHW boost switch entity naming

---

## [0.20.0] - 2026-01-09

### Added
- Initial release of MiGo (Netatmo) integration for Home Assistant
- Support for Saunier Duval thermostats via MiGO app (Netatmo API)

#### Climate
- Climate entity with Auto/Heat/Off modes
- Temperature control with min/max limits
- Preset modes: Away, Hot water only, Frost guard

#### Sensors
- Room temperature and humidity
- Outdoor temperature (from gateway)
- Battery level (thermostat)
- WiFi signal strength (gateway)
- RF signal strength (thermostat)
- Gateway and thermostat firmware versions
- Daily boiler runtime (for Energy Dashboard)

#### Binary Sensors
- Boiler status (running/idle)
- Boiler error detection
- eBus error detection
- Device reachable status

#### Controls
- DHW (Domestic Hot Water) switch
- DHW Boost switch
- Heating anticipation switch
- Thermostat mode select (Auto/Away/Frost guard)
- Active schedule selection
- Heating curve adjustment (0.5-3.5)
- Hysteresis threshold adjustment (0.1-2.0°C)
- Temperature offset calibration (-5.0 to +5.0°C)

#### Other
- Manual data refresh button
- Multi-language support (English, French)
- GitHub Actions CI/CD workflows
- Pre-commit hooks with ruff

### Notes
- This integration uses the Netatmo API (app.netatmo.net)
- NOT compatible with MiGO Link or myVAILLANT apps
