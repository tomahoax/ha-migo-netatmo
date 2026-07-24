# AGENTS.md

This file provides guidance for AI agents working on this codebase.

## Project Overview

This is a Home Assistant custom integration for MiGO thermostats (Saunier Duval/Vaillant boilers), using the MiGO app's Netatmo API backend.

**Domain**: `migo_netatmo`

## Architecture

### Core Components

- `__init__.py` - Integration setup and entry point (`ConfigEntry.runtime_data`, no `hass.data[DOMAIN]`)
- `api.py` - Netatmo API client (authentication, API calls)
- `coordinator.py` - Data update coordinator (polling)
- `config_flow.py` - Configuration UI flow (user, reauth, reconfigure, options)
- `entity.py` - Base entity classes and DeviceInfo builders
- `helpers.py` - Pure utility functions shared across platforms
- `models.py` - TypedDicts describing API responses and coordinator data

### Entity Platforms

- `climate.py` - Thermostat climate entity (Auto/Heat/Off modes)
- `sensor.py` - Temperature, humidity, battery, signal strength, firmware sensors
- `binary_sensor.py` - Boiler status, errors, reachability sensors
- `switch.py` - Domestic Hot Water (DHW) control, heating anticipation
- `select.py` - Schedule selection
- `number.py` - DHW temperature, manual setpoint duration, temperature offset, hysteresis, heating curve
- `button.py` - Manual refresh, reset heating curve

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
    async def _async_update_data(self) -> CoordinatorData:
        ...  # fetches homes/rooms/devices, see coordinator.py

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

1. Modify `api.py` methods
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
