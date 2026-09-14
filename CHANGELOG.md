# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

This release incorporates analysis and real-device testing shared by the
community on the [HACF forum thread](https://forum.hacf.fr/t/developpement-dune-integration-custom-migo-netatmo-pour-thermostats-saunier-duval-appel-aux-testeurs/73717/14).

### Fixed
- **Climate entity showing the wrong state during Frost guard / DHW-only quick actions** - MiGo stacks three independent notions (boiler quick-action mode, home-level Away, and the room's own setpoint) that no single room-level field can represent on its own
  - Real standby ("Veille" / Frost guard) used to display as "Heating": the room-level `therm_setpoint_mode` is `home` in that state, which incorrectly mapped to `HVACMode.HEAT`
  - Away mode was invisible in Home Assistant: only the room's `therm_setpoint_mode` was ever read, never the home-level `therm_mode` field that actually carries it
  - The "Away" preset was write-only: setting it worked, but `preset_mode` could never read it back afterwards
  - `hvac_mode` and `preset_mode` now derive from the home's `therm_mode` together with the room's `therm_setpoint_mode`
  - `hvac_action` now uses the thermostat's real `boiler_status` when available, falling back to the previous temperature-delta heuristic when it isn't
  - Added a "Hot water only" preset for MiGo's DHW-only quick action, previously indistinguishable from real Frost guard
- **Selecting the "Frost guard" (Veille) climate preset silently produced "Hot water only" instead** - `MigoApi.set_mode()` only ever routes `"hg"` to the room-level `setstate` endpoint, never to the home-level `setthermmode` one, even though `setthermmode` documents `"hg"` as a valid value there too. So both `HVACMode.OFF` and the Frost guard preset always wrote room-level `therm_setpoint_mode=hg` - which is exactly what this release's `Hot water only` preset means - and never the home-level `therm_mode=hg` that real standby needs. `async_set_preset_mode` now calls `set_therm_mode` directly for Frost guard (home-level) and `set_room_state` directly for Hot water only (room-level), bypassing the dispatcher for both instead of relying on it to guess
- **DHW boost and Heating anticipation switches lagging one poll cycle behind the API** - the DHW switch had no optimistic cache at all, and the anticipation switch filled its cache *after* the coordinator refresh that writes entity state, so neither reflected a toggle immediately
  - Both switches now use a shared `_call_api_optimistically` helper (`MigoApiControlMixin`) that writes the optimistic value and entity state *before* the API call, and restores the previous value if the call fails
  - Fixes a related latent bug: the optimistic cache (`coordinator._config_cache`) was never invalidated between refreshes, unlike `homes`/`rooms`/`devices` - a written key could shadow API data indefinitely. The new helper clears its key after a successful refresh, via a new `coordinator.clear_cached_value()`
- **Number entities (DHW temperature, heating curve, hysteresis, manual setpoint duration, temperature offset) and the Reset heating curve button permanently masking out-of-band changes** - same root cause as above: each set its own optimistic cache entry on write and never cleared it. Once you adjusted any of these from Home Assistant even once, all later changes made elsewhere (the MiGo mobile app, the boiler itself) would stay invisible in HA until the next full restart. Found while investigating a report that a DHW temperature change made in the mobile app didn't appear after pressing Refresh - that specific report turned out to be a Netatmo-side propagation delay (confirmed by checking the recorder history: the correct value did arrive a few minutes later on its own), but the cache bug it led to is real and is fixed here. All 6 entities now go through `_call_api_optimistically` too; `MigoTemperatureOffsetNumber` gained `MigoApiControlMixin` (via `MigoRoomControlEntity`) to get it, having had none before

### Added
- **Away mode entities** - `binary_sensor.migo_{home}_away_mode` (read-only) and `switch.migo_{home}_away_mode` (read/write), reading and writing the home-level `therm_mode` field directly. The switch writes via `setthermmode`, the same call the climate preset uses, so it has no side effect on the boiler quick-action mode
- **Boiler mode sensor** - `sensor.migo_{home}_boiler_mode`, exposing the derived boiler quick-action mode (Normal / DHW only / Frost guard) as its own entity, independent of Away
- **Scheduled DHW binary sensor** - `binary_sensor.migo_{home}_dhw_schedule`, resolving the currently active time slot of the selected DHW (`event`-type) schedule and reporting its `dhw_enabled` flag - data already returned by `homesdata` but previously read by no entity. Forced `off` while Away is active; reports `unavailable` rather than a guessed value when the schedule can't be resolved
- **Away return time** - `datetime.migo_{home}_away_until`, matching the MiGo app's own option to set a return date/time when activating Away. New `MigoApi.set_home_therm_mode()` method against `/api/sethomedata`, which documents an optional `therm_mode_endtime` timestamp that `/api/setthermmode` (used by `switch.migo_{home}_away_mode`, left untouched) does not support. There is no way to read the end time back from the API at all, so the entity reflects only what was last set from Home Assistant and is lost across a restart
  - **`button.migo_{home}_reset_away_until`** - Home Assistant's `datetime` platform has no way to clear a value back to empty from its own more-info dialog, so this button (no API call, purely local) is the deliberate way to reset it. Toggling `switch.migo_{home}_away_mode` in either direction also clears it as a side effect, since a plain toggle never specifies a return time and would otherwise leave a stale one displayed
- **Brand icon** - `custom_components/migo_netatmo/brand/icon.png` (256×256) and `icon@2x.png` (512×512), the official MiGo app icon. Self-hosted the same way as [ha-daitem](https://github.com/tomahoax/ha-daitem): Home Assistant serves it directly from the integration's own `brand/` folder since 2026.3, no submission to the external `home-assistant/brands` repository and no manifest change needed (`Integration.has_branding` just checks the folder exists). No dark variant: the icon is an opaque filled square, so Home Assistant's own fallback chain already serves `icon.png` for the dark-theme slot
  - Removed the old, non-functional icon staging locations (root `icon.png`/`icon@2x.png`, `brands_assets/`, `custom_components/migo_netatmo/icon.png`, and a `brands/` - plural, never read by anything - folder) in favor of this single working one
  - **Correction:** `ignore: brands` stays on the HACS validation workflow - HACS validates brand assets against the external `home-assistant/brands` repository, not the integration's own `brand/` folder. This integration's submission there was already made and rejected on substance (wrong logo); the ignore can't come out until a corrected one merges. The local `brand/` folder remains correct for the running app itself, which resolves it directly since Home Assistant 2026.3, independently of HACS's own listing

### Changed
- **Reorganized the device page's Controls/Configuration/Diagnostic cards for coherence** - `DHW boost` and `Heating anticipation` were previously `Configuration` while the new `Away mode` switch was primary, so functionally identical switches ended up in different cards. All three operational toggles (plus the climate entity, the active-schedule select and the Refresh buttons - quick actions, not settings) now land in `Controls`; `Configuration` is left holding only genuine setpoints/tuning values (DHW temperature, heating curve, hysteresis, manual setpoint duration, temperature offset) and the button that resets one of them. The Away mode binary_sensor (a read-only companion to its switch, previously duplicating it in the Sensors card) moves to `Diagnostic`. See `docs/entities.md`'s new "Device Page Organization" section for the convention this follows going forward
  - **Upgrade note:** Home Assistant does not retroactively move already-registered entities between cards on update - `entity_category` is registry metadata it treats as sticky once an entity exists, precisely so a user's own manual override isn't silently clobbered. On an existing install, the 3 reclassified entities (`DHW boost`, `Heating anticipation`, the `Away mode` binary_sensor) keep their old card until you either adjust each one's Entity category by hand (entity's settings dialog → Advanced → Entity category) or remove and re-add the integration. New installs get the new layout immediately
- **Removed the Gateway/Thermostat firmware sensors** - they duplicated Home Assistant's own "Device info" card, which already shows firmware version as `sw_version` for both devices. Removing an entity from the code does not delete it from an existing install's registry either; it shows as `unavailable` until manually removed (entity's settings dialog → Delete)

### Documentation
- Documented `event`-type (DHW) schedules, `linked_schedules`, and the timetable-resolution algorithm in `docs/api/reference.md`
- Documented the legacy `getthermostatsdata` endpoint (a second Netatmo host accepting the same MiGo token) under "Known Limitations" - not wired into this release since `therm_mode`/`therm_setpoint_mode` already cover the boiler mode and Away state at no extra API cost, and the endpoint's own response envelope and behavior on `api.netatmo.com` haven't been verified against live traffic in this codebase

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
