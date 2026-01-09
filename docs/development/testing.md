# Testing Guide

This guide covers how to run and write tests for the MiGo integration.

## Running Tests

### Prerequisites

Install development dependencies:

```bash
pip install -r requirements_dev.txt
```

### Run All Tests

```bash
pytest tests/ -v
```

### Run Specific Tests

```bash
# Run a specific test file
pytest tests/test_coordinator.py -v

# Run a specific test
pytest tests/test_coordinator.py::test_coordinator_update -v

# Run tests matching a pattern
pytest tests/ -k "coordinator" -v
```

### Coverage Report

```bash
pytest tests/ --cov=custom_components/migo_netatmo --cov-report=html
```

Open `htmlcov/index.html` to view the report.

## Test Structure

```
tests/
├── conftest.py           # Shared fixtures
├── test_config_flow.py   # Configuration flow tests
├── test_coordinator.py   # Data coordinator tests
├── test_api.py           # API client tests
└── test_entities.py      # Entity tests
```

## Writing Tests

### Using Fixtures

Common fixtures are defined in `conftest.py`:

```python
@pytest.fixture
def mock_api():
    """Return a mock API client."""
    ...

@pytest.fixture
def coordinator(mock_api):
    """Return a test coordinator."""
    ...
```

### Mocking API Calls

```python
async def test_set_temperature(mock_api, coordinator):
    """Test setting temperature."""
    mock_api.set_temperature = AsyncMock()

    climate = MigoClimate(coordinator, "room_1", mock_api)
    await climate.async_set_temperature(temperature=21.0)

    mock_api.set_temperature.assert_called_once_with(
        home_id="home_1",
        room_id="room_1",
        temperature=21.0,
    )
```

### Testing Entities

```python
async def test_climate_current_temperature(coordinator):
    """Test current temperature property."""
    coordinator.rooms = {
        "room_1": {
            "therm_measured_temperature": 20.5,
            "home_id": "home_1",
        }
    }

    climate = MigoClimate(coordinator, "room_1", Mock())
    assert climate.current_temperature == 20.5
```

### Testing Coordinator

```python
async def test_coordinator_update(hass, mock_api):
    """Test coordinator data update."""
    coordinator = MigoDataUpdateCoordinator(hass, mock_api)

    await coordinator.async_config_entry_first_refresh()

    assert len(coordinator.rooms) > 0
    assert len(coordinator.devices) > 0
```

### Testing Config Flow

```python
async def test_config_flow_success(hass):
    """Test successful config flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )

    assert result["type"] == FlowResultType.FORM

    with patch("custom_components.migo_netatmo.api.MigoApi") as mock:
        mock.return_value.authenticate = AsyncMock()
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"username": "test@example.com", "password": "secret"},
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
```

## Test Data

### Sample API Responses

Create fixtures with realistic API responses:

```python
@pytest.fixture
def homes_data():
    return {
        "body": {
            "homes": [{
                "id": "home_1",
                "name": "My Home",
                "rooms": [{
                    "id": "room_1",
                    "name": "Living Room",
                }],
                "modules": [{
                    "id": "device_1",
                    "type": "NAVaillant",
                }],
            }],
        }
    }
```

## Continuous Integration

Tests run automatically on:
- Pull requests
- Pushes to main branch

CI checks include:
- Unit tests (pytest)
- Linting (ruff)
- Type checking (optional)

## Best Practices

1. **Mock external calls**: Never make real API calls in tests
2. **Test edge cases**: Empty data, None values, errors
3. **Keep tests focused**: One assertion per test when possible
4. **Use descriptive names**: `test_climate_set_temperature_updates_cache`
5. **Clean up**: Use fixtures for setup/teardown

## Debugging Tests

### Verbose Output

```bash
pytest tests/ -v --tb=long
```

### Print Debug Info

```python
def test_something(caplog):
    caplog.set_level(logging.DEBUG)
    # ... test code ...
    print(caplog.text)
```

### Interactive Debugging

```bash
pytest tests/test_coordinator.py --pdb
```
