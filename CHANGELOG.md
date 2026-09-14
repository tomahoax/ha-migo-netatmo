# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

This release incorporates analysis and real-device testing shared by the
community on the [HACF forum thread](https://forum.hacf.fr/t/developpement-dune-integration-custom-migo-netatmo-pour-thermostats-saunier-duval-appel-aux-testeurs/73717/14).

### Fixed
- **Away mode couldn't be turned on - toggling it immediately reverted to off**, with a raw API error visible in the UI: `403 {"error":{"code":13,"message":"Cannot change therm_mode while being in temperature_control_mode cooling"}}`. `MigoApi.set_home_therm_mode()` (`sethomedata`) never sent `temperature_control_mode` at all, so it stayed stuck at whatever the account happened to have - `"cooling"`, which the API refuses to change `therm_mode` under. The MiGo app's own traffic (captured in `docs/api/reference.md`) always sends `"temperature_control_mode": "heating"` alongside every `therm_mode` change; this boiler line (gas heating only) has no cooling capability, so that's never a legitimate value to preserve. Now sent unconditionally on every call. The toggle correctly reverting to its previous state on API failure was already working as designed (`_call_api_optimistically`'s documented rollback contract) - nothing needed fixing there
- **`datetime.migo_{home}_away_until` silently rejected any value set on it** - same root cause as above: setting a return time activates Away via the same `set_home_therm_mode` call, so it hit the identical 403 and rolled back to empty, which looked like "no way to confirm the value" rather than a failed write. Fixed by the same change; confirmed no separate datetime-widget bug exists (no availability/editability coupling in `datetime.py` at all)
- **"Reset heating curve" set the value to 1.5, not the value shown in the MiGo app** - investigated via a live debug-log capture: `heating_curve` is never present in `homesdata`, `homestatus`, or `getconfigs`, so there is no way for this integration to discover a real, per-installation "default" to reset to at all. `const.DEFAULT_HEATING_CURVE` (`1.5`, itself inconsistent with `docs/api/reference.md`'s own captured `1.4`) was never more than an arbitrary constant standing in for one. At the user's explicit request (having confirmed writes from Home Assistant do work correctly and show up in the app), the constant is now `2.6`, matching their own installation - documented everywhere this value is referenced as installation-specific, not universal, so a future reader doesn't mistake it for a real API default. `number.migo_{home}_heating_curve`'s own docstring/comment corrected to stop implying a real API readback exists that in practice never fires
- **Turning off Away mode didn't clear a return time set on `datetime.migo_{home}_away_until`** - `MigoAwayModeSwitch` did clear the coordinator's cache entry for it (and the server-side value, via `endtime=None`), but clearing a cache dict entry doesn't by itself push any state - nothing told the datetime entity to actually re-render, so it kept showing the old value until whatever unrelated future update happened to touch it. `_call_api_optimistically` gained an `on_optimistic` hook, run synchronously right after this switch's own optimistic cache write (not after the whole call completes, where `coordinator.homes` may still be stale for several seconds under the debouncer described above) - the switch uses it to clear-and-immediately-notify the datetime entity's listener at that exact moment. `MigoAwayReturnDateTime.native_value` also now checks the switch's own optimistic cache (via the same `helpers.is_home_away()` other entities already share) instead of only raw `coordinator.homes` data, so it reads the fresh state right away rather than racing a possibly-delayed refresh
- **All entities intermittently going `unavailable` while the MiGo app itself kept working** - four `device_info` properties (`entity.py`, `climate.py`) linked a thermostat to its parent gateway via the deprecated `via_device` parameter. Home Assistant normally just logs a warning for a deprecated parameter from a custom integration, but when the call happened to be attributed to a *core* integration instead - reproduced here when an entity got (re-)added outside its platform's normal initial setup, e.g. right after an entity registry edit - it raises instead, aborting that entity's setup entirely and leaving it (and, transiently, others) `unavailable`. All four now resolve `via_device_id` (the registry's own internal device ID, looked up via the device registry rather than passed as an identifiers tuple) through a new shared `entity._resolve_via_device_id()` helper
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
- **Findings from a code review of this branch's own diff**, verified individually against the actual code before fixing (not taken at face value):
  - **Climate `preset_mode` hid an active Away state whenever the room had a manual or boost override** - the manual/boost checks `return`ed before the code ever reached the Away check below them, contradicting the adjacent comment's own claim that Away "is checked first". Away is now checked first in practice too, ahead of manual/boost as well as the boiler quick-action mode, consistent with the app allowing Away to combine with any of them
  - **`binary_sensor.migo_{home}_dhw_schedule`'s Away-forces-off override only applied once the schedule and its active zone were both fully resolved** - during Away, an unresolvable schedule reported `unknown` instead of the documented unconditional `off`. Away is now checked first and applied regardless of whether the rest of the lookup succeeds
  - **`binary_sensor.migo_{home}_away_mode` and the Away override inside `binary_sensor.migo_{home}_dhw_schedule` didn't read the optimistic cache `switch.migo_{home}_away_mode` writes** - both visibly disagreed with the switch until the next coordinator refresh completed. Both now share a new `helpers.is_home_away()` lookup with the switch itself, which also removes three separate copies of the same "resolve home_id → compare therm_mode" logic
  - **`MigoApiControlMixin._call_api_optimistically()` cleared the optimistic cache after a refresh with no further state push** - `async_request_refresh()` already drives `async_update_listeners()` internally, and it does so *before* the cache is cleared on the very next line, so every entity re-rendered once while still reading the (possibly stale) optimistic value; nothing pushed the now-authoritative one afterwards until some unrelated future update happened to differ from it. Now writes state once more right after clearing the cache
    - **Correction, reported live right after this shipped:** writing state again there caused a visible toggle/slider flicker - jump to the new value, revert to the old one, then jump back a few seconds later - on `Away mode`, `DHW always on`, `DHW boost`, and the `DHW temperature` number. Root cause: `async_request_refresh()` goes through the coordinator's refresh debouncer (10s cooldown, `immediate=True` - the *first* call in a while runs synchronously, any call within 10s of a previous refresh is coalesced and returns immediately without having fetched anything). The extra write ran unconditionally, so on a coalesced call it rendered the just-cleared cache against still-stale coordinator data - the revert-then-correct the report describes, self-resolving once the coalesced refresh actually completed. Reverted: `_call_api_optimistically` no longer writes state after clearing the cache, back to its original behavior of just leaving the optimistic value on screen
  - **`MigoDHWScheduleBinarySensor._resolve()` fully recomputed (including a timetable sort) on every property read** - once from `is_on`, once from `extra_state_attributes`. Now cached for the current coordinator data and invalidated in `_handle_coordinator_update`
  - **`MigoBoilerModeSensor.native_value` scanned every room in every home before filtering by `home_id`** - moved the filtering into a new, reusable `helpers.get_rooms_for_home()`
  - **Clarified two docstrings that overstated what the code actually does**, rather than changing behavior that turned out to be correct on closer reading: `MigoAwayModeSwitch`'s claim of "no side effect on the boiler quick-action mode" didn't account for real Frost guard sharing the same home-level `therm_mode` field as Away (mutually exclusive by construction, same as in the MiGo app itself - not a bug); `MigoDHWScheduleBinarySensor`'s claim of reporting `unavailable` when unresolved, when the code actually (and correctly) returns `unknown`
  - **Defensive hardening**: `helpers.resolve_timetable_zone()` now wraps an out-of-range `week_minutes` into a valid week instead of silently landing on the wrong zone (currently unreachable - its only caller always returns an in-range value - but not guaranteed by the function's own contract); `datetime.migo_{home}_away_until`'s `async_set_value` now normalizes a naive datetime to Home Assistant's configured timezone before converting it, rather than trusting Python's own (possibly different) system-local interpretation
- **Findings from a second code review of this branch's diff**, again verified individually before fixing:
  - **`button.migo_{home}_reset_away_until` didn't read the switch's optimistic Away cache** - it compared raw `coordinator.homes` data directly instead of `helpers.is_home_away()`, so pressing it right after toggling `switch.migo_{home}_away_mode` off (before the switch's own refresh lands) could read the still-stale "away" state and re-activate Away server-side, undoing the toggle the user just made. The button now uses `is_home_away()` like its siblings, and also clears its own cache and pushes listeners *before* the follow-up API call/refresh rather than after (the refresh's own listener push could otherwise fire while the cache was still populated, briefly re-showing the just-cleared value)
  - **Climate `hvac_mode`/`preset_mode` didn't read the same Away cache either** - same root cause, one remaining caller: `MigoClimate` could show the pre-toggle preset for a few seconds after `switch.migo_{home}_away_mode` is flipped, while the switch/binary_sensor/datetime entities (already fixed above) update immediately. Climate now resolves this room's gateway device and checks `is_home_away()` too, falling back to the raw home-level `therm_mode` if the gateway can't be resolved
  - **Selecting the `Away` climate preset couldn't clear a stale return time** - unlike `switch.migo_{home}_away_mode` and `button.migo_{home}_reset_away_until`, which write Away via `set_home_therm_mode(..., endtime=None)`, `async_set_preset_mode` still routed `Away` through the generic `set_mode()` dispatcher (`setthermmode`, which has no `endtime` parameter), so re-activating Away from the climate card's preset selector could leave a `datetime.migo_{home}_away_until` value from a previous Away period displayed. `Away` now has its own explicit branch calling `set_home_therm_mode` directly, like `Frost guard` and `Hot water only` already do; the now-unreachable `PRESET_TO_MIGO_MODE` mapping (its only entry) was removed rather than left as dead code
  - **A thermostat/room entity's `device_info` could permanently omit `via_device_id`** - Home Assistant forwards all platforms concurrently (`async_forward_entry_setups`), so nothing guaranteed a gateway-owning platform registered the gateway device before a thermostat-owning one read it (`_resolve_via_device_id` silently omits the link rather than raising, but a link once omitted at initial entity-add stays missing until reload). `async_setup_entry` now registers each gateway device in the device registry up front, before platforms are forwarded, so the lookup never races
  - **`datetime.migo_{home}_away_until`'s `async_set_value` cached a differently-typed value than every other read path** - it normalized the incoming value to an aware UTC datetime only for the `endtime` sent to the API, but cached the raw (possibly naive) argument as the optimistic value, while the API-fallback path always returns an aware datetime. The same normalized value is now used for both
  - **Two unused `const.py` dicts (`HVAC_MODE_TO_API`, `API_MODE_TO_HVAC`) still carried the pre-fix, now-wrong `MODE_HOME -> "heat"` mapping** - referenced nowhere, but a latent-bug trap for a future caller assuming they were the canonical mapping (that's `climate.py`'s `HVAC_TO_MIGO_MODE`/`MIGO_TO_HVAC_MODE`). Removed
  - **`_resolve_via_device_id()` itself used another deprecated device registry call** - `async_get_device` (identifiers-set lookup) is deprecated too, for the exact same reason and with the exact same raise-instead-of-warn risk as `via_device` above (identifiers are no longer guaranteed unique across config entries) - caught live, as a new warning, right after the first fix shipped. Switched to `async_get_device_by_identifier`, which is config-entry-scoped and needs this entity's own `config_entry_id` (a new `_entity_config_entry_id()` helper reads it off `Entity.platform.config_entry`, set alongside `Entity.hass` before `device_info` is ever read)

### Added
- **Away mode entities** - `binary_sensor.migo_{home}_away_mode` (read-only) and `switch.migo_{home}_away_mode` (read/write), reading and writing the home-level `therm_mode` field directly. The switch writes via `set_home_therm_mode` (sethomedata, with an explicit `endtime=None`), the same call the climate `Away` preset now also uses (see the "Fixed" entry below), so it has no side effect on the boiler quick-action mode
- **Boiler mode sensor** - `sensor.migo_{home}_boiler_mode`, exposing the derived boiler quick-action mode (Normal / DHW only / Frost guard) as its own entity, independent of Away
- **Scheduled DHW binary sensor** - `binary_sensor.migo_{home}_dhw_schedule`, resolving the currently active time slot of the selected DHW (`event`-type) schedule and reporting its `dhw_enabled` flag - data already returned by `homesdata` but previously read by no entity. Forced `off` while Away is active; reports `unavailable` rather than a guessed value when the schedule can't be resolved
- **Away return time** - `datetime.migo_{home}_away_until`, matching the MiGo app's own option to set a return date/time when activating Away. New `MigoApi.set_home_therm_mode()` method against `/api/sethomedata`, which documents an optional `therm_mode_endtime` timestamp that `/api/setthermmode` (used by `switch.migo_{home}_away_mode`, left untouched) does not support.
  - **`button.migo_{home}_reset_away_until`** - Home Assistant's `datetime` platform has no way to clear a value back to empty from its own more-info dialog, so this button is the deliberate way to reset it. Toggling `switch.migo_{home}_away_mode` in either direction also clears it as a side effect, since a plain toggle never specifies a return time and would otherwise leave a stale one displayed
  - **Correction: it *does* read back from the API** - this entry originally claimed "there is no way to read the end time back from the API at all," so the entity would reflect only what was last set from Home Assistant and be lost across a restart. Disproven when a return time set directly in the MiGo app (its own home screen showed "Absent (18.0°) jusqu'à après-demain 16:23") never appeared in Home Assistant, even after Refresh. A live debug-log capture confirmed `therm_mode_endtime` genuinely is present on `homesdata`'s home object - undocumented by Netatmo, but the exact same timestamp as the app's own display. The entity now falls back to it via the standard cache-then-API pattern (`_call_api_optimistically`) every other read/write entity in this integration already uses, gated on `therm_mode == "away"` so a value lingering from a past Away period isn't shown once the mode has moved on. It now survives a Home Assistant restart and reflects changes made from the MiGo app itself
    - `switch.migo_{home}_away_mode` and `button.migo_{home}_reset_away_until` now write via `set_home_therm_mode` with an explicit `endtime=None` (instead of `set_therm_mode`, which has no such parameter), so a stale return time can no longer resurface after either is used; the button also clears it server-side, not just locally, while currently Away
- **DHW always-on switch** - `switch.migo_{home}_dhw_always_on`, matching the "Toujours activée" DHW setting shown in a forum screenshot of the MiGo app: forces the boiler to never suspend hot water heating, overriding the active schedule's per-slot production setting. New `MigoApi.set_dhw_always_on()` method against `/syncapi/v1/setconfigs`'s `dhw_always_on` field - undocumented by Netatmo, confirmed via a live debug-log capture that it sits on the same module entry as `dhw_setpoint_temperature`
- **Brand icon** - `custom_components/migo_netatmo/brand/icon.png` (256×256) and `icon@2x.png` (512×512), the official MiGo app icon. Self-hosted the same way as [ha-daitem](https://github.com/tomahoax/ha-daitem): Home Assistant serves it directly from the integration's own `brand/` folder since 2026.3, no submission to the external `home-assistant/brands` repository and no manifest change needed (`Integration.has_branding` just checks the folder exists). No dark variant: the icon is an opaque filled square, so Home Assistant's own fallback chain already serves `icon.png` for the dark-theme slot
  - Removed the old, non-functional icon staging locations (root `icon.png`/`icon@2x.png`, `brands_assets/`, `custom_components/migo_netatmo/icon.png`, and a `brands/` - plural, never read by anything - folder) in favor of this single working one
  - **Correction:** `ignore: brands` stays on the HACS validation workflow - HACS validates brand assets against the external `home-assistant/brands` repository, not the integration's own `brand/` folder. This integration's submission there was already made and rejected on substance (wrong logo); the ignore can't come out until a corrected one merges. The local `brand/` folder remains correct for the running app itself, which resolves it directly since Home Assistant 2026.3, independently of HACS's own listing

### Changed
- **Reorganized the device page's Controls/Configuration/Diagnostic cards for coherence** - `DHW boost` and `Heating anticipation` were previously `Configuration` while the new `Away mode` switch was primary, so functionally identical switches ended up in different cards. All three operational toggles (plus the climate entity, the active-schedule select and the Refresh buttons - quick actions, not settings) now land in `Controls`; `Configuration` is left holding only genuine setpoints/tuning values (DHW temperature, heating curve, hysteresis, manual setpoint duration, temperature offset) and the button that resets one of them. The Away mode binary_sensor (a read-only companion to its switch, previously duplicating it in the Sensors card) moves to `Diagnostic`. See `docs/entities.md`'s new "Device Page Organization" section for the convention this follows going forward
  - **Upgrade note:** Home Assistant does not retroactively move already-registered entities between cards on update - `entity_category` is registry metadata it treats as sticky once an entity exists, precisely so a user's own manual override isn't silently clobbered. On an existing install, the 3 reclassified entities (`DHW boost`, `Heating anticipation`, the `Away mode` binary_sensor) keep their old card until you either adjust each one's Entity category by hand (entity's settings dialog → Advanced → Entity category) or remove and re-add the integration. New installs get the new layout immediately
- **Removed the Gateway/Thermostat firmware sensors** - they duplicated Home Assistant's own "Device info" card, which already shows firmware version as `sw_version` for both devices. Removing an entity from the code does not delete it from an existing install's registry either; it shows as `unavailable` until manually removed (entity's settings dialog → Delete)
- **Removed `button.migo_{home}_refresh` (Gateway and Thermostat)** - every write in this integration already refreshes itself (`MigoApiControlMixin`'s two helpers), so nothing depended on these for anything a user does from Home Assistant; their only remaining purpose was pulling in changes made outside HA (the MiGo app, the boiler itself) sooner than the next scheduled poll. That's already covered two ways that don't need dedicated entities: the poll interval is user-configurable (60s-3600s, integration options), and confirmed directly against Home Assistant's own source, `CoordinatorEntity.async_update()` - "Only used by the generic entity update service" - calls the exact same `coordinator.async_request_refresh()` these buttons did. Since every entity this integration exposes shares one coordinator, the built-in `homeassistant.update_entity` action (or the "Update" option in any migo_netatmo entity's more-info dialog) already does precisely what these buttons did, for free, on every entity, not just two. Same upgrade note as above: existing installs keep the two button entities as `unavailable` until manually removed
- **Removed `button.migo_{home}_reset_away_until`**, at the user's explicit request. It had a real, distinct purpose from `switch.migo_{home}_away_mode` - clearing the return time while *staying* Away indefinitely, which turning the switch off cannot do (that exits Away entirely back to the schedule) - flagged before removing it. Accepted tradeoff: there is no longer a way to clear just the return time without also leaving Away; toggling `switch.migo_{home}_away_mode` off and back on is the only way now. Same upgrade note as above for existing installs

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
