# AGENTS.md

This file provides guidance for AI agents working on this codebase.

## Project Overview

This is a Home Assistant custom integration for Saunier Duval thermostats using the MiGO app's Netatmo API backend.

**Domain**: `migo_netatmo`

## Architecture

### Core Components

- `__init__.py` - Integration setup and entry point
- `api.py` - Netatmo API client (authentication, API calls)
- `coordinator.py` - Data update coordinator (polling)
- `config_flow.py` - Configuration UI flow

### Entity Platforms

- `climate.py` - Thermostat climate entity (Auto/Heat/Off modes)
- `sensor.py` - Temperature, humidity, battery, signal strength, firmware sensors
- `binary_sensor.py` - Boiler status, errors, reachability sensors
- `switch.py` - Domestic Hot Water (DHW) control
- `select.py` - Thermostat mode and schedule selection
- `button.py` - Manual refresh button

### Configuration

- `const.py` - Constants (domain, API URLs, etc.)
- `entity.py` - Base entity class
- `manifest.json` - Integration metadata
- `strings.json` / `translations/` - Localization (EN, FR)

## API Details

- **Base URL**: `https://app.netatmo.net`
- **Authentication**: OAuth2-like flow with email/password
- **Endpoints**: See `docs/API_REFERENCE.md`

## Development Guidelines

### Code Style

- Python 3.11+
- Follow Home Assistant coding standards
- Use async/await for all I/O operations
- Run `pylint` with `.pylintrc` configuration

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
# Coordinator pattern for data updates
class MigoDataUpdateCoordinator(DataUpdateCoordinator):
    async def _async_update_data(self):
        return await self.api.get_homes_data()

# Entity registration
async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
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
2. Update `docs/API_REFERENCE.md`
3. Test authentication flow

### Adding a new language

1. Create `translations/{lang}.json`
2. Copy structure from `translations/en.json`
3. Translate all strings

## CI/CD

- **HACS Validation**: `.github/workflows/validate.yaml`
- **Release**: `.github/workflows/release.yaml` (auto-generates zip on tag)

## Important Notes

- This integration uses **Netatmo API**, NOT myVAILLANT API
- Only compatible with "MiGo. Your Heating Assistant" app users
- NOT compatible with MiGO Link or myVAILLANT apps
