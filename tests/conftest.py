"""Pytest configuration and fixtures for MiGo (Netatmo) tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, create_autospec, patch

import pytest
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.migo_netatmo.api import MigoApi
from custom_components.migo_netatmo.const import DOMAIN
from custom_components.migo_netatmo.coordinator import MigoDataUpdateCoordinator


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading custom integrations in all tests."""
    return


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Create a mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="MiGo (Netatmo)",
        unique_id="test@example.com",
        data={
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "test_password",
        },
        options={},
    )


@pytest.fixture
def homes_data_response() -> dict[str, Any]:
    """Return mock homes data response."""
    return {
        "body": {
            "user": {"email": "test@example.com", "country": "FR"},
            "homes": [
                {
                    "id": "home_123",
                    "name": "My Home",
                    "therm_mode": "schedule",
                    # Personal data the real API returns. Present so the
                    # redaction tests fail for the right reason: without these,
                    # a broken redactor would still pass.
                    "coordinates": [49.123456, 2.654321],
                    "city": "Somewhere",
                    "country": "FR",
                    "altitude": 120,
                    "timezone": "Europe/Paris",
                    "invitation_code": ["ZsdApbpjOstMdOn1"],
                    "rooms": [
                        {
                            "id": "room_456",
                            "name": "Living Room",
                            "type": "living_room",
                            "module_ids": ["module_789"],
                        }
                    ],
                    "modules": [
                        {
                            "id": "gateway_001",
                            "type": "NAVaillant",
                            "subtype": "NAEbusSdbg",
                            "oem_serial": "SN123456",
                        },
                        {
                            "id": "module_789",
                            "type": "NAThermVaillant",
                            "room_id": "room_456",
                            "bridge": "gateway_001",
                        },
                    ],
                    "schedules": [
                        {
                            "id": "schedule_001",
                            "name": "Default",
                            "type": "therm",
                            "selected": True,
                            "default": True,
                        }
                    ],
                }
            ],
        },
        "status": "ok",
    }


@pytest.fixture
def home_status_response() -> dict[str, Any]:
    """Return mock home status response."""
    return {
        "body": {
            "home": {
                "id": "home_123",
                "rooms": [
                    {
                        "id": "room_456",
                        "therm_measured_temperature": 21.5,
                        "therm_setpoint_temperature": 20.0,
                        "therm_setpoint_mode": "schedule",
                        "reachable": True,
                        "anticipating": False,
                    }
                ],
                "modules": [
                    {
                        "id": "gateway_001",
                        "type": "NAVaillant",
                        "wifi_strength": 70,
                        "firmware_revision": 1030,
                        "dhw_enabled": True,
                        "ebus_error": False,
                        "boiler_error": [],
                    },
                    {
                        "id": "module_789",
                        "type": "NAThermVaillant",
                        "battery_percent": 85,
                        "battery_state": "high",
                        "rf_strength": 65,
                        "firmware_revision": 72,
                        "reachable": True,
                        "boiler_status": True,
                    },
                ],
            }
        },
        "status": "ok",
    }


@pytest.fixture
def configs_response() -> dict[str, Any]:
    """Return mock getconfigs response."""
    return {
        "body": {
            "home": {
                "id": "home_123",
                "modules": [
                    {
                        "id": "gateway_001",
                        "dhw_setpoint_temperature": 55,
                    }
                ],
            }
        },
        "status": "ok",
    }


@pytest.fixture
def consumption_response() -> dict[str, Any]:
    """Return mock consumption data response from /api/getmeasure.

    The response format is a dict with timestamps as keys and
    [sum_boiler_on, sum_boiler_off] arrays as values.
    """
    return {
        "body": {
            "1704067200": [3600, 82800],  # 1 hour on, 23 hours off
            "1704153600": [7200, 79200],  # 2 hours on, 22 hours off
            "1704240000": [5400, 81000],  # 1.5 hours on, 22.5 hours off
        },
        "status": "ok",
        "time_exec": 0.05,
        "time_server": 1704326400,
    }


@pytest.fixture
def mock_api(
    homes_data_response: dict[str, Any],
    home_status_response: dict[str, Any],
    configs_response: dict[str, Any],
    consumption_response: dict[str, Any],
) -> MagicMock:
    """Create a mock MiGO API client.

    Autospecced so calls with kwargs unknown to the real MigoApi
    signatures raise TypeError instead of passing silently.
    """
    api = create_autospec(MigoApi, instance=True)
    api.authenticate.return_value = True
    api.get_homes_data.return_value = homes_data_response
    api.get_home_status.return_value = home_status_response
    api.get_configs.return_value = configs_response
    api.get_measure.return_value = consumption_response
    api.set_temperature.return_value = {"status": "ok"}
    api.set_mode.return_value = {"status": "ok"}
    api.set_therm_mode.return_value = {"status": "ok"}
    api.set_dhw_enabled.return_value = {"status": "ok"}
    api.switch_home_schedule.return_value = {"status": "ok"}
    return api


@pytest.fixture
def coordinator(
    hass: HomeAssistant,
    mock_api: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> MigoDataUpdateCoordinator:
    """Create a coordinator bound to a real Home Assistant test instance."""
    mock_config_entry.add_to_hass(hass)
    return MigoDataUpdateCoordinator(
        hass=hass,
        api=mock_api,
        config_entry=mock_config_entry,
    )


@pytest.fixture
def patch_migo_api(mock_api: MagicMock) -> Generator[MagicMock]:
    """Patch the MigoApi class everywhere it is instantiated."""
    with (
        patch("custom_components.migo_netatmo.MigoApi", return_value=mock_api),
        patch("custom_components.migo_netatmo.config_flow.MigoApi", return_value=mock_api),
    ):
        yield mock_api


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    patch_migo_api: MagicMock,
) -> AsyncGenerator[MockConfigEntry]:
    """Set up the integration against a real Home Assistant test instance."""
    mock_config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    yield mock_config_entry


@pytest.fixture
def token_response() -> dict[str, Any]:
    """Return mock token response."""
    return {
        "access_token": "test_access_token",
        "refresh_token": "test_refresh_token",
        "expires_in": 10800,
        "scope": ["all_scopes"],
    }


@pytest.fixture
def mock_coordinator() -> MagicMock:
    """Create a mock coordinator with data, shared across entity-level unit tests."""
    coordinator = MagicMock()
    coordinator.rooms = {
        "room_456": {
            "id": "room_456",
            "name": "Living Room",
            "home_id": "home_123",
            "home_name": "My Home",
            "therm_measured_temperature": 21.5,
            "therm_setpoint_temperature": 20.0,
            "therm_setpoint_mode": "schedule",
            "reachable": True,
            "anticipating": False,
        }
    }
    coordinator.devices = {
        "gateway_001": {
            "id": "gateway_001",
            "type": "NAVaillant",
            "home_id": "home_123",
            "wifi_strength": 70,
            "dhw_enabled": True,
        },
        "module_789": {
            "id": "module_789",
            "type": "NAThermVaillant",
            "home_id": "home_123",
            "battery_percent": 85,
            "boiler_status": True,
        },
    }
    coordinator.homes = {
        "home_123": {
            "id": "home_123",
            "name": "My Home",
            "therm_mode": "schedule",
            "schedules": [
                {"id": "schedule_001", "name": "Comfort", "type": "therm", "selected": True},
                {"id": "schedule_002", "name": "Eco", "type": "therm", "selected": False},
                {"id": "schedule_003", "name": "DHW only", "type": "event", "selected": False},
            ],
        }
    }
    coordinator.get_cached_value = MagicMock(return_value=None)
    coordinator.set_cached_value = MagicMock()
    coordinator.async_request_refresh = AsyncMock()
    return coordinator
