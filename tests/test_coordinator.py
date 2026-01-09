"""Tests for the MiGo (Netatmo) data coordinator."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.migo_netatmo.api import MigoApiError
from custom_components.migo_netatmo.coordinator import MigoDataUpdateCoordinator


@pytest.fixture
def coordinator(
    mock_api: MagicMock,
    mock_config_entry: MagicMock,
) -> MigoDataUpdateCoordinator:
    """Create a coordinator for testing."""
    hass = MagicMock()
    hass.loop = AsyncMock()

    coordinator = MigoDataUpdateCoordinator(
        hass=hass,
        api=mock_api,
        config_entry=mock_config_entry,
    )
    return coordinator


class TestMigoDataUpdateCoordinator:
    """Tests for the data update coordinator."""

    @pytest.mark.asyncio
    async def test_update_data_success(
        self,
        coordinator: MigoDataUpdateCoordinator,
    ) -> None:
        """Test successful data update."""
        result = await coordinator._async_update_data()

        assert "homes" in result
        assert "rooms" in result
        assert "devices" in result

        # Check that data was stored
        assert len(coordinator.homes) == 1
        assert len(coordinator.rooms) == 1
        assert len(coordinator.devices) == 2

    @pytest.mark.asyncio
    async def test_update_data_invalid_response(
        self,
        coordinator: MigoDataUpdateCoordinator,
        mock_api: MagicMock,
    ) -> None:
        """Test update with invalid API response."""
        mock_api.get_homes_data = AsyncMock(return_value={})

        with pytest.raises(UpdateFailed) as exc_info:
            await coordinator._async_update_data()

        assert "missing 'body'" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_update_data_api_error(
        self,
        coordinator: MigoDataUpdateCoordinator,
        mock_api: MagicMock,
    ) -> None:
        """Test update with API error."""
        mock_api.get_homes_data = AsyncMock(side_effect=MigoApiError("API error"))

        with pytest.raises(UpdateFailed) as exc_info:
            await coordinator._async_update_data()

        assert "Error communicating with API" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_update_data_skips_home_without_modules(
        self,
        coordinator: MigoDataUpdateCoordinator,
        mock_api: MagicMock,
    ) -> None:
        """Test that homes without modules are skipped."""
        mock_api.get_homes_data = AsyncMock(
            return_value={
                "body": {
                    "homes": [
                        {
                            "id": "home_no_modules",
                            "name": "Empty Home",
                            "rooms": [],
                            "modules": [],
                        }
                    ]
                }
            }
        )

        result = await coordinator._async_update_data()

        assert len(coordinator.homes) == 0

    @pytest.mark.asyncio
    async def test_update_data_home_status_error_continues(
        self,
        coordinator: MigoDataUpdateCoordinator,
        mock_api: MagicMock,
    ) -> None:
        """Test that home status errors don't stop processing."""
        mock_api.get_home_status = AsyncMock(side_effect=MigoApiError("Status error"))

        # Should not raise, just log warning
        result = await coordinator._async_update_data()

        # Home should still be processed (without status data)
        assert len(coordinator.homes) == 1


class TestCoordinatorDataAccess:
    """Tests for data access methods."""

    @pytest.mark.asyncio
    async def test_get_room(
        self,
        coordinator: MigoDataUpdateCoordinator,
    ) -> None:
        """Test getting room by ID."""
        await coordinator._async_update_data()

        room = coordinator.get_room("room_456")
        assert room is not None
        assert room["name"] == "Living Room"
        assert room["home_id"] == "home_123"

    @pytest.mark.asyncio
    async def test_get_room_not_found(
        self,
        coordinator: MigoDataUpdateCoordinator,
    ) -> None:
        """Test getting non-existent room."""
        await coordinator._async_update_data()

        room = coordinator.get_room("nonexistent")
        assert room is None

    @pytest.mark.asyncio
    async def test_get_home(
        self,
        coordinator: MigoDataUpdateCoordinator,
    ) -> None:
        """Test getting home by ID."""
        await coordinator._async_update_data()

        home = coordinator.get_home("home_123")
        assert home is not None
        assert home["name"] == "My Home"

    @pytest.mark.asyncio
    async def test_get_device(
        self,
        coordinator: MigoDataUpdateCoordinator,
    ) -> None:
        """Test getting device by ID."""
        await coordinator._async_update_data()

        device = coordinator.get_device("gateway_001")
        assert device is not None
        assert device["type"] == "NAVaillant"

    @pytest.mark.asyncio
    async def test_get_schedules(
        self,
        coordinator: MigoDataUpdateCoordinator,
    ) -> None:
        """Test getting schedules for a home."""
        await coordinator._async_update_data()

        schedules = coordinator.get_schedules("home_123")
        assert len(schedules) == 1
        assert schedules[0]["name"] == "Default"

    @pytest.mark.asyncio
    async def test_get_active_schedule(
        self,
        coordinator: MigoDataUpdateCoordinator,
    ) -> None:
        """Test getting active schedule for a home."""
        await coordinator._async_update_data()

        schedule = coordinator.get_active_schedule("home_123")
        assert schedule is not None
        assert schedule["selected"] is True

    @pytest.mark.asyncio
    async def test_get_active_schedule_none_selected(
        self,
        coordinator: MigoDataUpdateCoordinator,
        mock_api: MagicMock,
    ) -> None:
        """Test getting active schedule when none is selected."""
        # Modify fixture to have no selected schedule
        homes_data = mock_api.get_homes_data.return_value
        homes_data["body"]["homes"][0]["schedules"][0]["selected"] = False

        await coordinator._async_update_data()

        schedule = coordinator.get_active_schedule("home_123")
        assert schedule is None


class TestCoordinatorDataMerging:
    """Tests for data merging from config and status."""

    @pytest.mark.asyncio
    async def test_room_data_merged(
        self,
        coordinator: MigoDataUpdateCoordinator,
    ) -> None:
        """Test that room config and status data are merged."""
        await coordinator._async_update_data()

        room = coordinator.get_room("room_456")

        # From config
        assert room["name"] == "Living Room"
        assert room["type"] == "living_room"

        # From status
        assert room["therm_measured_temperature"] == 21.5
        assert room["therm_setpoint_temperature"] == 20.0
        assert room["reachable"] is True

        # Added by coordinator
        assert room["home_id"] == "home_123"
        assert room["home_name"] == "My Home"

    @pytest.mark.asyncio
    async def test_device_data_merged(
        self,
        coordinator: MigoDataUpdateCoordinator,
    ) -> None:
        """Test that device config and status data are merged."""
        await coordinator._async_update_data()

        device = coordinator.get_device("module_789")

        # From config
        assert device["type"] == "NAThermVaillant"
        assert device["room_id"] == "room_456"

        # From status
        assert device["battery_percent"] == 85
        assert device["rf_strength"] == 65
        assert device["boiler_status"] is True

        # Added by coordinator
        assert device["home_id"] == "home_123"
