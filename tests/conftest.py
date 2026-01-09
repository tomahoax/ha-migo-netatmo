"""Pytest configuration and fixtures for MiGo (Netatmo) tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from custom_components.migo_netatmo.api import MigoApi
from custom_components.migo_netatmo.const import DOMAIN

# Path to test fixtures
FIXTURES_PATH = Path(__file__).parent / "fixtures"


def load_fixture(filename: str) -> dict[str, Any]:
    """Load a fixture file.

    Args:
        filename: Name of the fixture file.

    Returns:
        The parsed JSON data.
    """
    with (FIXTURES_PATH / filename).open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def hass() -> HomeAssistant:
    """Create a Home Assistant instance for testing."""
    hass = MagicMock(spec=HomeAssistant)
    hass.config_entries = MagicMock()
    hass.config_entries.flow = MagicMock()
    hass.config_entries.flow.async_init = AsyncMock()
    hass.config_entries.flow.async_configure = AsyncMock()
    hass.config_entries.async_reload = AsyncMock()
    hass.config_entries.async_update_entry = MagicMock()
    return hass


@pytest.fixture
def mock_config_entry() -> MagicMock:
    """Create a mock config entry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.domain = DOMAIN
    entry.unique_id = None
    entry.data = {
        CONF_USERNAME: "test@example.com",
        CONF_PASSWORD: "test_password",
    }
    entry.title = "MiGo (Netatmo)"

    def add_to_hass(hass):
        """Add entry to hass."""
        entry.unique_id = "test@example.com"
        hass.config_entries._entries = {entry.entry_id: entry}

    entry.add_to_hass = add_to_hass
    return entry


@pytest.fixture
def homes_data_response() -> dict[str, Any]:
    """Return mock homes data response."""
    return {
        "body": {
            "homes": [
                {
                    "id": "home_123",
                    "name": "My Home",
                    "therm_mode": "schedule",
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
            ]
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
def mock_api(
    homes_data_response: dict[str, Any],
    home_status_response: dict[str, Any],
) -> MagicMock:
    """Create a mock MiGO API client."""
    api = MagicMock(spec=MigoApi)
    api.authenticate = AsyncMock(return_value=True)
    api.get_homes_data = AsyncMock(return_value=homes_data_response)
    api.get_home_status = AsyncMock(return_value=home_status_response)
    api.set_temperature = AsyncMock(return_value={"status": "ok"})
    api.set_mode = AsyncMock(return_value={"status": "ok"})
    api.set_therm_mode = AsyncMock(return_value={"status": "ok"})
    api.set_dhw_enabled = AsyncMock(return_value={"status": "ok"})
    api.switch_home_schedule = AsyncMock(return_value={"status": "ok"})
    api.close = AsyncMock()
    return api


@pytest.fixture
def token_response() -> dict[str, Any]:
    """Return mock token response."""
    return {
        "access_token": "test_access_token",
        "refresh_token": "test_refresh_token",
        "expires_in": 10800,
        "scope": ["all_scopes"],
    }
