# AGENTS.md

This file provides guidance for AI agents working on this codebase.

## Project Overview

This is a Home Assistant custom integration for MiGO thermostats (Saunier Duval/Vaillant boilers), using the MiGO app's Netatmo API backend.

**Domain**: `migo_netatmo`

## Architecture

### Core Components

- `__init__.py` - Integration setup and entry point (`ConfigEntry.runtime_data`, no `hass.data[DOMAIN]`)
- `api/` - Netatmo API client, split by concern: `client.py` (the assembled `MigoApi` class),
  `auth.py` (token lifecycle), `transport.py` (the authenticated-request path, JSON boundary,
  redacted/raw logging), `endpoints_read.py`/`endpoints_write.py` (the get_*/set_* calls),
  `exceptions.py`. `__init__.py` re-exports `MigoApi` and the exception classes - that's the
  only surface anything outside `api/` should import.
- `coordinator.py` - Data update coordinator (polling)
- `config_flow.py` - Configuration UI flow (user, reauth, reconfigure, options)
- `entity.py` - The 11 base entity classes (MigoEntity through MigoRoomControlEntity)
- `entity_device_info.py` - DeviceInfo builders (`build_gateway_device_info` etc.) and the
  `via_device_id` registry-resolution helpers
- `entity_setup.py` - `register_dynamic_entities`, the dynamic-devices platform-setup helper
- `entity_mixin.py` - `MigoApiControlMixin` (API-calling), `_MigoCachedValueMixin`
  (optimistic-cache read pattern), `_MigoDescriptionEntityMixin` (entity-description read pattern)
- `entity_descriptions.py` - `MigoEntityDescriptionMixin`, the data_key/unique_id_key/value_fn
  fields shared by sensor.py's and binary_sensor.py's entity descriptions
- `helpers.py` - Pure utility functions shared across platforms
- `models.py` - TypedDicts describing API responses and coordinator data

### Entity Platforms

- `climate.py` - Thermostat climate entity (Auto/Heat/Off modes, Away/Frost guard/Hot water only/Boost presets)
- `sensor.py` - Temperature, humidity, battery, signal strength, firmware, measured gas/electricity
  energy, boiler runtime, derived boiler mode sensors
- `binary_sensor.py` - Boiler status, errors, reachability, Away mode, scheduled DHW sensors
- `switch.py` - Domestic Hot Water (DHW) boost, heating anticipation, Away mode, DHW always-on
- `select.py` - Schedule selection
- `number.py` - DHW temperature, manual setpoint duration, temperature offset, hysteresis, heating curve
- `datetime.py` - Away return date/time

No `button.py`: there is no dedicated button entity anymore (the last one, Reset
heating curve, was removed as redundant with editing the Heating Curve number
directly). `homeassistant.update_entity` already does what a manual-refresh
button did, for every entity, since they share one coordinator.

### Configuration

- `const.py` - Constants (domain, API URLs, etc.)
- `manifest.json` - Integration metadata
- `strings.json` / `translations/` - Localization (en, es, fr, it, ru)

## API Details

- **Base URL**: `https://app.netatmo.net`
- **Authentication**: OAuth2-like flow with email/password
- **Endpoints**: See `docs/api/reference.md`

## Development Guidelines

### Code Style

- Python 3.13+ (see `pyproject.toml` `requires-python`)
- Follow Home Assistant coding standards
- Use async/await for all I/O operations
- Lint/format with `ruff` (`ruff check` / `ruff format --check`), type-check with `mypy`
  (project config in `pyproject.toml`; there is no pylint/`.pylintrc` in this project)

### Entity Naming

- Unique IDs: `migo_netatmo_{entity_type}_{device_id}`
- Device identifiers: `(DOMAIN, home_id)` or `(DOMAIN, device_id)`

### Testing Changes

1. Install in Home Assistant dev environment
2. Check logs for errors: `custom_components.migo_netatmo`
3. Verify entities appear correctly
4. Test all entity operations

### Key Patterns

```python
# Coordinator pattern for data updates, typed via models.CoordinatorData
class MigoDataUpdateCoordinator(DataUpdateCoordinator[CoordinatorData]):
    async def _async_update_data(self) -> CoordinatorData: ...  # fetches homes/rooms/devices, see coordinator.py


# Config entry data: ConfigEntry.runtime_data, NOT hass.data[DOMAIN]
type MigoConfigEntry = ConfigEntry[MigoData]


async def async_setup_entry(hass: HomeAssistant, entry: MigoConfigEntry) -> bool:
    entry.runtime_data = MigoData(api=api, coordinator=coordinator)
    ...


# Platform setup reads it back from entry.runtime_data, not hass.data
async def async_setup_entry(hass, entry: MigoConfigEntry, async_add_entities):
    coordinator = entry.runtime_data.coordinator
    entities = []
    # Create entities from coordinator data
    async_add_entities(entities)
```

## Common Tasks

### Adding a new sensor

1. Add sensor description in `sensor.py`
2. Map data from API response in coordinator
3. Add translation keys in `strings.json` and `translations/`

### Updating API calls

1. Modify the relevant `api/` module (`endpoints_read.py`/`endpoints_write.py` for a new
   call, `auth.py`/`transport.py` for the request path itself)
2. Update `docs/api/reference.md`
3. Test authentication flow

### Adding a new language

1. Create `translations/{lang}.json`
2. Copy structure from `translations/en.json`
3. Translate all strings

## CI/CD

All of the following run on push/PR to `main` and `dev`, in `.github/workflows/validate.yaml`:

- **HACS validation** (`hacs/action`) and **hassfest validation** (`home-assistant/actions/hassfest`)
- **Lint** (`ruff check` + `ruff format --check`) and **mypy** (separate jobs)
- **Tests** across a Python/HA matrix (latest, and the minimum HA pinned in `hacs.json`),
  with coverage gated by `fail_under` in `pyproject.toml`

**Release**: `.github/workflows/release.yaml` re-stamps the version in `manifest.json`
and `pyproject.toml` from the git tag, builds `migo_netatmo.zip`, and uploads it as a
release asset (`hacs.json` has `zip_release: true` so HACS installs from that zip).

## Important Notes

- This integration uses **Netatmo API**, NOT myVAILLANT API
- Only compatible with "MiGo. Your Heating Assistant" app users
- NOT compatible with MiGO Link or myVAILLANT apps
