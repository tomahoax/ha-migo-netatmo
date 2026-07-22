"""Tests for MiGo (Netatmo) integration setup and unload."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.migo_netatmo.api import MigoApiError, MigoAuthError


async def test_setup_entry(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Test the integration sets up and populates runtime data."""
    assert init_integration.state is ConfigEntryState.LOADED

    data = init_integration.runtime_data
    assert data.api is not None
    assert data.coordinator.homes.keys() == {"home_123"}
    assert data.coordinator.rooms.keys() == {"room_456"}
    assert set(data.coordinator.devices) == {"gateway_001", "module_789"}


async def test_setup_entry_creates_entities(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Test that entities exist and have real states after setup."""
    climate = hass.states.get("climate.my_home_thermostat_thermostat")
    assert climate is not None
    assert climate.state == "auto"
    assert climate.attributes["current_temperature"] == 21.5
    assert climate.attributes["temperature"] == 20.0

    wifi = hass.states.get("sensor.my_home_gateway_wifi_signal")
    assert wifi is not None
    assert wifi.state == "70"

    battery = hass.states.get("sensor.my_home_thermostat_battery")
    assert battery is not None
    assert battery.state == "85"
    assert battery.attributes["battery_state"] == "high"

    boiler = hass.states.get("binary_sensor.my_home_thermostat_boiler_status")
    assert boiler is not None
    assert boiler.state == "on"


async def test_unload_entry(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Test the integration unloads cleanly."""
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()

    assert init_integration.state is ConfigEntryState.NOT_LOADED


async def test_setup_entry_auth_error_starts_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    patch_migo_api: MagicMock,
) -> None:
    """Test that an auth failure at setup puts the entry in reauth."""
    patch_migo_api.authenticate.side_effect = MigoAuthError("bad credentials")
    mock_config_entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert any(flow["handler"] == "migo_netatmo" and flow["context"]["source"] == "reauth" for flow in flows)


async def test_setup_entry_api_error_retries(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    patch_migo_api: MagicMock,
) -> None:
    """Test that a connection failure at setup schedules a retry."""
    patch_migo_api.authenticate.side_effect = MigoApiError("cannot reach API")
    mock_config_entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
