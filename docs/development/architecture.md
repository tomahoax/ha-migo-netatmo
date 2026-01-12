# Architecture

This document describes the code structure and design patterns used in the MiGo integration.

## Overview

```
                    ┌─────────────────┐
                    │  Home Assistant │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   __init__.py   │
                    │  (Entry Point)  │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────▼───────┐ ┌────▼────┐ ┌───────▼───────┐
     │  config_flow   │ │   api   │ │  coordinator  │
     │   (Setup UI)   │ │ (HTTP)  │ │ (Data Update) │
     └────────────────┘ └────┬────┘ └───────┬───────┘
                             │              │
                             └──────┬───────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              │         │         │         │            │
        ┌─────▼────┐ ┌──▼──┐ ┌───▼───┐ ┌───▼───┐ ┌──────▼──────┐
        │ climate  │ │sens.│ │switch │ │select │ │   number    │
        └──────────┘ └─────┘ └───────┘ └───────┘ └─────────────┘
```

## Core Components

### MigoApi (`api.py`)

The API client handles all HTTP communication with the Netatmo backend.

**Responsibilities:**
- Authentication (OAuth2 with password grant)
- Token refresh
- API requests (GET/POST)
- Response parsing

**Key Methods:**
- `authenticate()`: Initial login
- `refresh_token()`: Token refresh
- `get_homes_data()`: Fetch configuration
- `get_home_status()`: Fetch current state
- `set_*()`: Control methods

### MigoDataUpdateCoordinator (`coordinator.py`)

The coordinator manages data fetching and caching using Home Assistant's DataUpdateCoordinator pattern.

**Responsibilities:**
- Periodic data updates (every 5 minutes)
- Data normalization
- Optimistic value caching
- Error handling

**Data Structures:**
- `homes`: Dict of home configurations
- `rooms`: Dict of room states
- `devices`: Dict of device states
- `consumption`: Dict of boiler consumption data (indexed by gateway device_id)

### Entity Base Classes (`entity.py`)

Hierarchical entity classes for code reuse.

```
MigoEntity (CoordinatorEntity)
├── MigoRoomEntity          # Room-based entities
│   └── MigoRoomControlEntity   # With API control
├── MigoDeviceEntity        # Device-based entities
│   └── MigoControlEntity       # With API control
└── MigoHomeEntity          # Home-based entities
    └── MigoHomeControlEntity   # With API control
```

### MigoApiControlMixin

A mixin providing common API control patterns:

```python
class MigoApiControlMixin:
    async def _call_api_and_refresh(self, api_method, **kwargs):
        await api_method(**kwargs)
        await self.coordinator.async_request_refresh()
```

## Data Flow

### Initialization

1. User adds integration via UI
2. `config_flow.py` validates credentials
3. `__init__.py` creates API client and coordinator
4. Coordinator fetches initial data
5. Entity platforms register entities

### Data Update

1. Coordinator timer triggers (every 5 minutes)
2. API client fetches home status
3. API client fetches consumption data via `/api/getmeasure`
   - Uses gateway `device_id` and thermostat `module_id`
   - Gateway/thermostat pairing is discovered automatically
4. Coordinator normalizes data into dicts
5. Entities read from coordinator dicts
6. Home Assistant updates entity states

### Control Flow

1. User changes entity state in HA
2. Entity calls appropriate API method
3. Optimistic value cached (if applicable)
4. Coordinator refresh triggered
5. New state reflected in entity

## Design Patterns

### Optimistic Updates

For values not immediately returned by the API:

```python
# Set value in cache before refresh
self.coordinator.set_cached_value(self._cache_key, value)
# Trigger refresh (actual value may differ)
await self.coordinator.async_request_refresh()
```

### Translation System

Entities use Home Assistant's translation system:

```python
_attr_translation_key = "thermostat"

@property
def translation_placeholders(self):
    return {"room_name": self._room_data.get("name")}
```

### Constants Organization

All magic values are centralized in `const.py`:

- API endpoints
- OAuth credentials
- Device types
- Temperature limits
- Mode mappings

## File Responsibilities

| File | Purpose |
|------|---------|
| `__init__.py` | Integration setup, platform forwarding |
| `api.py` | HTTP client, authentication |
| `config_flow.py` | Setup UI, credential validation |
| `const.py` | Constants, mappings |
| `coordinator.py` | Data update, caching |
| `entity.py` | Base entity classes |
| `helpers.py` | Utility functions |
| `climate.py` | Thermostat control |
| `sensor.py` | Read-only sensors |
| `binary_sensor.py` | Boolean sensors |
| `switch.py` | Toggle controls |
| `select.py` | Dropdown selections |
| `number.py` | Numeric inputs |
| `button.py` | Action triggers |

## Error Handling

### API Errors

- Network errors: Logged, entities go unavailable
- Auth errors: Trigger reauth flow
- Rate limits: Handled with backoff

### Entity Errors

- Missing data: Return None, log warning
- Invalid values: Log error, skip update
- Control failures: Log error, don't update state
