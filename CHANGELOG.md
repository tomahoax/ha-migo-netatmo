# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security
- **Personal data no longer written to debug logs.** With debug logging on, the integration wrote your MiGO account email, your home's exact GPS coordinates, its city, and your home invitation code into the Home Assistant log on every polling cycle. Credentials and tokens were never affected. Debug logs still show the full structure of API responses, with those values replaced, so they remain useful for diagnosis and are now safe to attach to an issue. **If you have run this integration with debug logging enabled, your existing log files still contain that data**: delete or truncate them, and do not attach an old log to a bug report. Raw unredacted payloads remain available behind a separate opt-in logger, documented in [Troubleshooting](docs/troubleshooting.md)
- **Diagnostics downloads were incompletely redacted.** Credentials and location were replaced, but the home invitation code, hardware serial numbers, the boiler ID and the names of your homes, rooms and schedules were not. A diagnostics file showing REDACTED markers was therefore not as safe to publish as it looked
- **The Reconfigure dialog no longer pre-fills your stored password** or client secret. Sending them back to the browser as suggested form values put them where any script running in the Home Assistant page could read them
- **Backend error messages shown in the UI are now truncated**, closing an arbitrary-text channel from the API into Home Assistant notifications
- **Release archives now ship a `.sha256` checksum** so the download can be verified independently

### Added
- **Automatic removal of stale devices** - A device the MiGO account stops reporting is now removed from Home Assistant on the next refresh, instead of waiting for you to delete it by hand
- **Icons** for the gateway and thermostat firmware sensors and the schedule selector, which previously showed a generic icon

### Changed
- **Strict typing** - The integration reaches the Platinum `strict-typing` rule: mypy now runs with Home Assistant core's full strict profile, with no suppressions
- **Daily boiler runtime** - The sensor now reports fractional seconds rather than truncating to whole seconds
- **Thermostat RF signal and firmware sensors are now disabled by default**, matching the gateway's equivalents. Existing installations keep them enabled: the setting only applies when an entity is first created

### Fixed
- **Request timeout was not applied.** Requests could hang for up to 5 minutes instead of the intended 30 seconds, leaving entities unavailable for far longer than necessary when the MiGO service was slow
- **Malformed measurement data no longer breaks the whole refresh.** Two cases in the boiler-runtime parser raised an unhandled error that failed the entire update cycle instead of skipping one reading
- **Gateway MAC addresses are validated** before being registered, so an unexpected device ID can no longer attach MiGO entities to an unrelated device in your Home Assistant
- **Shared HTTP session in the config flow** - Setting up, reauthenticating or reconfiguring the integration no longer opens a private HTTP session outside Home Assistant's pool
- **Quieter logs during an outage** - A sustained MiGO outage now logs one error when the integration goes unavailable and one message when it recovers, instead of several errors every polling cycle
- **Boiler runtime crash** - A measurement series without a start time no longer raises an unhandled error mid-refresh
- **Authentication errors** - An authentication response with no token now surfaces as an authentication failure instead of an internal error

### Removed
- Unused internal helpers and one unreachable entity class, which inflated the test coverage figure without protecting anything reachable

## [0.41.0] - 2026-07-22

### Added
- **Reconfigure flow** - Change credentials from the integration entry menu; reauth and reconfigure refuse account switching
- **Diagnostics** - Downloadable config entry diagnostics with credentials and home location redacted
- **Icon translations** - Icons served via `icons.json` instead of hardcoded attributes
- **Stale device removal** - Devices no longer reported by the API can be deleted from the UI
- **Reauth on polling failures** - An expired password now triggers the reauthentication repair instead of failing silently
- **Translated error messages** - Failed actions raise visible, translated errors (all 5 languages)

### Changed
- **Minimum Home Assistant version is now 2025.8**
- **Options dialog** only manages the polling interval; credentials move to Reconfigure/Reauthenticate
- **Action failures are now visible** - Service calls that previously failed silently (missing home, API error) raise errors
- Config flow uses proper email/password selectors and aborts duplicate accounts before any network call

### Internal
- Entity layer refactored: single-source DeviceInfo builders, native `EntityDescription` pattern, `PARALLEL_UPDATES` on all platforms. No unique_id or entity_id changed (pinned by a registry contract test)
- Test suite runs against a real Home Assistant test instance (78 tests); CI runs on dev PRs with a latest-HA and a minimum-HA (2025.8) job
- Deprecated patterns removed: options update listener, `FlowResult`, silent `AbortFlow` swallowing

## [0.40.2] - 2026-07-22

### Fixed
- **Climate Heat mode and Boost preset crashing** (#13) - `set_hvac_mode` (Heat), `turn_on` and the Boost preset raised `MigoApi.set_temperature() got an unexpected keyword argument 'duration'`
  - v0.40 passed a `duration` to the API client without implementing it there
  - `set_temperature()` now accepts an optional `duration` (minutes) and `set_room_state()` an optional `end_time`, sent as `therm_setpoint_end_time` to the setstate endpoint
  - Heat mode now honours the "Manual setpoint duration" setting; Boost expires after 1 hour as intended
  - API mocks in tests are now autospecced so signature mismatches fail in CI

### Added
- **DHW temperature fetching** - `getconfigs` API call to read the domestic hot water temperature

## [0.40.1] - 2026-01-14

### Added
- **Refresh button** on Gateway and Thermostat configuration

### Changed
- Enable beta versions in HACS

## [0.40.0] - 2026-01-12

### Added
- **Heating curve control** - New number entity to adjust heating curve slope (0.0-5.0)
- **Reset heating curve button** - Button to reset heating curve to default value (1.5)
- **Configuration options** - Ability to modify credentials and OAuth settings in options flow
  - Email, Password, Client ID, Client Secret, User Prefix can now be changed after setup
  - Credentials are validated before saving
- **Boost preset** - New climate preset that forces maximum temperature (30°C) for 1 hour

### Fixed
- **Boiler runtime sensor not reporting data** - Fixed issue where the Daily Boiler Runtime sensor showed "Unknown"
  - Changed from `/api/getroommeasure` (home_id/room_id) to `/api/getmeasure` (device_id/module_id)
  - The `getmeasure` endpoint uses form-data instead of JSON (legacy Netatmo API)
  - Consumption data is now indexed by gateway device_id (MAC address)
  - Aligned with Vaillant vSmart integration approach

### Changed
- **Climate simplification** - Streamlined climate entity controls
  - Removed "Thermostat mode" select entity (redundant with climate presets)
  - Removed "Hot water only" preset (not a user-facing preset)
  - HVAC "Heat" mode now uses the configurable "Manual setpoint duration" setting
- **Sensor graph display** - Added `suggested_display_precision` for graph display
  - Outdoor temperature and boiler runtime sensors now show graph by default when clicked
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
- Updated entities documentation with new HVAC modes and presets behavior

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
