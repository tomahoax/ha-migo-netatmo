# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0-beta3] - 2026-09-15

This release incorporates analysis and real-device testing shared by the
community on the [HACF forum thread](https://forum.hacf.fr/t/developpement-dune-integration-custom-migo-netatmo-pour-thermostats-saunier-duval-appel-aux-testeurs/73717/14).

### Security
- **Personal data no longer written to debug logs.** With debug logging on, the integration wrote your MiGO account email, your home's exact GPS coordinates, its city, and your home invitation code into the Home Assistant log on every polling cycle. Credentials and tokens were never affected. Debug logs still show the full structure of API responses, with those values replaced, so they remain useful for diagnosis and are now safe to attach to an issue. **If you have run this integration with debug logging enabled, your existing log files still contain that data**: delete or truncate them, and do not attach an old log to a bug report. Raw unredacted payloads remain available behind a separate opt-in logger, documented in [Troubleshooting](docs/troubleshooting.md)
- **Diagnostics downloads were incompletely redacted.** Credentials and location were replaced, but the home invitation code, hardware serial numbers, the boiler ID and the names of your homes, rooms and schedules were not. A diagnostics file showing REDACTED markers was therefore not as safe to publish as it looked
- **The Reconfigure dialog no longer pre-fills your stored password** or client secret. Sending them back to the browser as suggested form values put them where any script running in the Home Assistant page could read them
- **Backend error messages shown in the UI are now truncated**, closing an arbitrary-text channel from the API into Home Assistant notifications
- **Release archives now ship a `.sha256` checksum** so the download can be verified independently

### Added
- **Measured gas and electricity consumption** - Four new sensors report what the boiler actually consumed, in kWh, split between heating and hot water: *Gas for heating*, *Gas for hot water*, *Electricity for heating*, *Electricity for hot water*. They go straight into the Energy dashboard, with no template sensor and no estimating from runtime, at no extra API cost
- **Automatic removal of stale devices** - A device the MiGO account stops reporting is now removed from Home Assistant on the next refresh, instead of waiting for you to delete it by hand
- **Icons** for the gateway and thermostat firmware sensors and the schedule selector, which previously showed a generic icon
- **Away mode entities** - `binary_sensor.migo_{home}_away_mode` (read-only) and `switch.migo_{home}_away_mode` (read/write), reading and writing the home-level `therm_mode` field directly, with no side effect on the boiler quick-action mode
- **Boiler mode sensor** - `sensor.migo_{home}_boiler_mode`, exposing the derived boiler quick-action mode (Normal / DHW only / Frost guard) as its own entity, independent of Away
- **Scheduled DHW binary sensor** - `binary_sensor.migo_{home}_dhw_schedule`, resolving the currently active time slot of the selected DHW (`event`-type) schedule and reporting its `dhw_enabled` flag - data already returned by `homesdata` but previously read by no entity. Forced `off` while Away is active; reports `unavailable` when the schedule can't be resolved
- **Away return time** - `datetime.migo_{home}_away_until`, matching the MiGo app's own option to set a return date/time when activating Away. Reads back `therm_mode_endtime` from the API (undocumented by Netatmo, confirmed via a live debug-log capture), so it survives a Home Assistant restart and reflects a return time set directly in the MiGo app. Toggling `switch.migo_{home}_away_mode` in either direction clears it, since a plain toggle never specifies a return time and would otherwise leave a stale one displayed
- **DHW always-on switch** - `switch.migo_{home}_dhw_always_on`, matching the "Toujours activée" DHW setting in the MiGo app: forces the boiler to never suspend hot water heating, overriding the active schedule's per-slot production setting
- **Brand icon** - `custom_components/migo_netatmo/brand/icon.png` (256×256) and `icon@2x.png` (512×512), the official MiGo app icon. Self-hosted the same way as [ha-daitem](https://github.com/tomahoax/ha-daitem): Home Assistant serves it directly from the integration's own `brand/` folder since 2026.3, no submission to the external `home-assistant/brands` repository needed. The old, non-functional icon staging locations (root `icon.png`/`icon@2x.png`, `brands_assets/`, the plural `brands/` folder) were removed in favor of this single working one

### Changed
- **Strict typing** - The integration reaches the Platinum `strict-typing` rule: mypy now runs with Home Assistant core's full strict profile, with no suppressions
- **Daily boiler runtime** - The sensor now reports fractional seconds rather than truncating to whole seconds
- **Thermostat RF signal and firmware sensors are now disabled by default**, matching the gateway's equivalents. Existing installations keep them enabled: the setting only applies when an entity is first created
- **Reorganized the device page's Controls/Configuration/Diagnostic cards for coherence** - `DHW boost`, `Heating anticipation`, the `Away mode` switch and the climate entity, active-schedule select and quick-action buttons now all land in `Controls`; `Configuration` holds only genuine setpoints/tuning values (DHW temperature, heating curve, hysteresis, manual setpoint duration, temperature offset). The Away mode binary_sensor (a read-only companion to its switch) moves to `Diagnostic`. See `docs/entities.md`'s "Device Page Organization" section for the convention this follows going forward
  - **Upgrade note:** Home Assistant does not retroactively move already-registered entities between cards - `entity_category` is sticky registry metadata once an entity exists. On an existing install, the 3 reclassified entities (`DHW boost`, `Heating anticipation`, the `Away mode` binary_sensor) keep their old card until you either adjust each one's Entity category by hand or remove and re-add the integration. New installs get the new layout immediately
- **Removed `button.migo_{home}_refresh` (Gateway and Thermostat)** - every write in this integration already refreshes itself, and the poll interval is user-configurable (60s-3600s). Home Assistant's own built-in `homeassistant.update_entity` action (or the "Update" option in any migo_netatmo entity's more-info dialog) already forces an immediate refresh for every entity, for free, since they all share one coordinator - confirmed directly against Home Assistant's own source (`CoordinatorEntity.async_update()`). Existing installs keep the two button entities as `unavailable` until manually removed
- **Removed `button.migo_{home}_reset_away_until`**, at the user's explicit request. It had a real, distinct purpose from `switch.migo_{home}_away_mode` - clearing the return time while *staying* Away indefinitely, which turning the switch off cannot do (that exits Away entirely back to the schedule). Accepted tradeoff: toggling `switch.migo_{home}_away_mode` off and back on is now the only way to clear a stale return time. Same upgrade note as above for existing installs
- **Removed `button.migo_{home}_reset_heating_curve`**, at the user's explicit request. Editing `number.migo_{home}_heating_curve` directly already sets any value, including the installation-specific one this button wrote; there was nothing the button could do that the number entity couldn't. With this, the `button` platform is gone entirely - no button entities ship with this release. Same upgrade note as above for existing installs

### Fixed
- **Energy dashboard documentation was wrong.** It instructed you to add the boiler runtime sensor under *Gas consumption*, which the dashboard cannot accept: it requires a gas or energy device class, and runtime measures time. The template-sensor workaround it offered lower down also referenced an entity ID that does not match this integration's naming, so it would have silently evaluated to zero
- **Request timeout was not applied.** Requests could hang for up to 5 minutes instead of the intended 30 seconds, leaving entities unavailable for far longer than necessary when the MiGO service was slow
- **Malformed measurement data no longer breaks the whole refresh.** Two cases in the boiler-runtime parser raised an unhandled error that failed the entire update cycle instead of skipping one reading
- **Gateway MAC addresses are validated** before being registered, so an unexpected device ID can no longer attach MiGO entities to an unrelated device in your Home Assistant
- **Shared HTTP session in the config flow** - Setting up, reauthenticating or reconfiguring the integration no longer opens a private HTTP session outside Home Assistant's pool
- **Quieter logs during an outage** - A sustained MiGO outage now logs one error when the integration goes unavailable and one message when it recovers, instead of several errors every polling cycle
- **Boiler runtime crash** - A measurement series without a start time no longer raises an unhandled error mid-refresh
- **Authentication errors** - An authentication response with no token now surfaces as an authentication failure instead of an internal error
- **Away mode couldn't be turned on - toggling it immediately reverted to off**, with a `403` from the API (`temperature_control_mode: cooling`). `MigoApi.set_home_therm_mode()` now always sends `"temperature_control_mode": "heating"`, matching the MiGo app's own traffic - this boiler line (gas heating only) has no cooling capability, so that value was never legitimate to preserve. `datetime.migo_{home}_away_until` had the identical root cause and is fixed by the same change
- **`datetime.migo_{home}_away_until` now rejects a past return time with a clear validation error** instead of silently reverting to empty - the API rejects a past `therm_mode_endtime` outright, which used to look like "nothing happened". If Home Assistant's device-page compact date/time row submits a partial edit before you've picked a full future moment, use the entity's full more-info dialog instead
- **`number.migo_{home}_heating_curve`'s no-data fallback showed 1.5, not the value shown in the MiGo app** - `heating_curve` is never present in `homesdata`, `homestatus`, or `getconfigs` (confirmed via a live debug-log capture), so there is no API-discoverable "true default" to fall back to at all - it is an installation-specific calibration value. At the user's explicit request, the constant is now `2.6`, matching their own installation; documented everywhere as installation-specific, not universal
- **Turning off Away mode now clears `datetime.migo_{home}_away_until` immediately** instead of leaving the old value displayed until an unrelated future update happened to touch it
- **Reactivating Away mode right after a previous Away period no longer briefly flashes the old return time** on `datetime.migo_{home}_away_until` before it disappears
- **Climate entity now correctly reflects Frost guard, DHW-only and Away states.** MiGo stacks three independent notions (boiler quick-action mode, home-level Away, room setpoint) that no single room-level field can represent alone: real standby ("Veille"/Frost guard) used to display as "Heating"; Away was invisible in Home Assistant and, once made visible, was write-only (never read back); selecting the Frost guard preset silently produced "Hot water only" instead, because the write path routed both through the same room-level call. `hvac_mode`/`preset_mode`/`hvac_action` now derive from the home's `therm_mode` together with the room's `therm_setpoint_mode` and the thermostat's real `boiler_status`; a new "Hot water only" preset represents MiGo's DHW-only quick action; Frost guard, Hot water only and Away each now write through their own explicit, correct API call
- **DHW boost, Heating anticipation, and the number/button entities acting on DHW temperature, heating curve, hysteresis, manual setpoint duration and temperature offset no longer permanently mask out-of-band changes.** Each set an optimistic cache entry on write and never cleared it, so once you adjusted any of these from Home Assistant even once, later changes made elsewhere (the MiGo app, the boiler itself) stayed invisible until the next full restart. All of them now go through a shared `_call_api_optimistically` helper that clears its cache entry after a successful refresh
- **Entities no longer intermittently go `unavailable` while the MiGo app itself keeps working.** `device_info` properties linking a thermostat to its parent gateway used the deprecated `via_device` parameter, which Home Assistant can treat as a hard error rather than a warning depending on which integration it attributes the call to - reproduced when an entity got (re-)added outside its platform's normal setup (e.g. after an entity registry edit). All four now resolve `via_device_id` through the device registry directly, and the parent gateway device is registered up front before platforms are forwarded, so the lookup never races
- Away no longer gets hidden by a room's manual/boost override in `preset_mode`; the scheduled-DHW Away override now applies even when the schedule itself can't be resolved; the Away-mode binary sensor and the DHW-schedule sensor's Away override now read the same optimistic cache the switch does, instead of visibly lagging one refresh behind it; selecting the `Away` climate preset now clears a stale return time the same way the switch does
- **`number.migo_{home}_temperature_offset` didn't take effect - reported to neither set nor read back the real value.** Its `setconfigs` write was missing `home_id` at the request root, unlike this integration's other `setconfigs` calls (DHW temperature, DHW always-on), which need it there per a confirmed mitmproxy capture. The request looked valid and returned `200`, but the offset never actually applied server-side, so of course reading it back afterward - from Home Assistant or the MiGo app - kept showing the old value. Now sends `home_id` at the root, matching the other calls

### Removed
- Unused internal helpers and one unreachable entity class, which inflated the test coverage figure without protecting anything reachable

### Documentation
- Documented `event`-type (DHW) schedules, `linked_schedules`, and the timetable-resolution algorithm in `docs/api/reference.md`
- Documented the legacy `getthermostatsdata` endpoint (a second Netatmo host accepting the same MiGo token) under "Known Limitations" - not wired into this release since `therm_mode`/`therm_setpoint_mode` already cover the boiler mode and Away state at no extra API cost, and the endpoint's own response envelope and behavior on `api.netatmo.com` haven't been verified against live traffic in this codebase
- **Corrected a wrong claim about `number.migo_{home}_hysteresis`.** Reported live: this entity doesn't pick up a hysteresis change made from the MiGo app, even though writing to it from Home Assistant does reach the API. `docs/api/reference.md` claimed the written value is echoed back on `homestatus` as `simple_heating_algo_deadband` - a live capture taken during later development shows that field isn't actually present there for a real gateway module. Documented as unconfirmed rather than removed, in case a future capture finds it under some other condition; until then this entity is write-only in practice, the same situation `number.migo_{home}_heating_curve` was already documented to be in

## [0.41.0] - 2026-07-22 (never published)

> [!NOTE]
> No GitHub release was ever cut for this version, so nobody received it. The
> work listed below reached users as part of the next published release.


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
