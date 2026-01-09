"""Tests for the MiGo (Netatmo) API client."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.migo_netatmo.api import (
    MigoApi,
    MigoApiError,
    MigoAuthError,
    MigoConnectionError,
)


@pytest.fixture
def api() -> MigoApi:
    """Create an API client for testing."""
    return MigoApi(username="test@example.com", password="test_password")


class TestMigoApiAuthentication:
    """Tests for authentication methods."""

    @pytest.mark.asyncio
    async def test_authenticate_success(
        self,
        api: MigoApi,
        token_response: dict[str, Any],
    ) -> None:
        """Test successful authentication."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=token_response)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_response)))

        with patch.object(api, "_get_session", return_value=mock_session):
            result = await api.authenticate()

        assert result is True
        assert api._access_token == "test_access_token"
        assert api._refresh_token == "test_refresh_token"
        assert api._token_expiry is not None

    @pytest.mark.asyncio
    async def test_authenticate_invalid_credentials(self, api: MigoApi) -> None:
        """Test authentication with invalid credentials."""
        mock_response = AsyncMock()
        mock_response.status = 400
        mock_response.json = AsyncMock(return_value={"error": "invalid_grant"})

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_response)))

        with patch.object(api, "_get_session", return_value=mock_session):
            with pytest.raises(MigoAuthError) as exc_info:
                await api.authenticate()

        assert "invalid_grant" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_authenticate_connection_error(self, api: MigoApi) -> None:
        """Test authentication with connection error."""
        mock_session = MagicMock()
        mock_session.post = MagicMock(side_effect=aiohttp.ClientError("Connection failed"))

        with patch.object(api, "_get_session", return_value=mock_session):
            with pytest.raises(MigoConnectionError):
                await api.authenticate()


class TestMigoApiDataRetrieval:
    """Tests for data retrieval methods."""

    @pytest.mark.asyncio
    async def test_get_homes_data(
        self,
        api: MigoApi,
        homes_data_response: dict[str, Any],
    ) -> None:
        """Test getting homes data."""
        with patch.object(api, "_api_request", return_value=homes_data_response) as mock_request:
            result = await api.get_homes_data()

        assert result == homes_data_response
        mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_home_status(
        self,
        api: MigoApi,
        home_status_response: dict[str, Any],
    ) -> None:
        """Test getting home status."""
        with patch.object(api, "_api_request", return_value=home_status_response) as mock_request:
            result = await api.get_home_status("home_123")

        assert result == home_status_response
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        # Data is passed as second positional argument
        assert call_args[0][1]["home_id"] == "home_123"


class TestMigoApiRoomControl:
    """Tests for room control methods."""

    @pytest.mark.asyncio
    async def test_set_temperature(self, api: MigoApi) -> None:
        """Test setting temperature."""
        expected_response = {"status": "ok"}

        with patch.object(api, "_api_request", return_value=expected_response) as mock_request:
            result = await api.set_temperature("home_123", "room_456", 21.0)

        assert result == expected_response
        mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_mode_schedule(self, api: MigoApi) -> None:
        """Test setting schedule mode (global mode)."""
        expected_response = {"status": "ok"}

        with patch.object(api, "set_therm_mode", return_value=expected_response) as mock_therm_mode:
            result = await api.set_mode("home_123", "room_456", "schedule")

        mock_therm_mode.assert_called_once_with(home_id="home_123", mode="schedule")
        assert result == expected_response

    @pytest.mark.asyncio
    async def test_set_mode_manual(self, api: MigoApi) -> None:
        """Test setting manual mode (room-level mode)."""
        expected_response = {"status": "ok"}

        with patch.object(api, "set_room_state", return_value=expected_response) as mock_room_state:
            result = await api.set_mode("home_123", "room_456", "manual")

        mock_room_state.assert_called_once_with(
            home_id="home_123",
            room_id="room_456",
            mode="manual",
        )
        assert result == expected_response


class TestMigoApiHomeControl:
    """Tests for home control methods."""

    @pytest.mark.asyncio
    async def test_set_dhw_enabled(self, api: MigoApi) -> None:
        """Test enabling DHW."""
        expected_response = {"status": "ok"}

        with patch.object(api, "_api_request", return_value=expected_response) as mock_request:
            result = await api.set_dhw_enabled("home_123", "gateway_001", True)

        assert result == expected_response
        mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_switch_home_schedule(self, api: MigoApi) -> None:
        """Test switching schedule."""
        expected_response = {"status": "ok"}

        with patch.object(api, "_api_request", return_value=expected_response) as mock_request:
            result = await api.switch_home_schedule("home_123", "schedule_002")

        assert result == expected_response
        mock_request.assert_called_once()


class TestMigoApiTokenManagement:
    """Tests for token management."""

    def test_store_tokens(self, api: MigoApi, token_response: dict[str, Any]) -> None:
        """Test storing tokens from response."""
        api._store_tokens(token_response)

        assert api._access_token == "test_access_token"
        assert api._refresh_token == "test_refresh_token"
        assert api._token_expiry is not None

    def test_store_tokens_preserve_refresh(self, api: MigoApi) -> None:
        """Test storing tokens while preserving refresh token."""
        api._refresh_token = "original_refresh_token"

        api._store_tokens({"access_token": "new_access_token"}, preserve_refresh=True)

        assert api._access_token == "new_access_token"
        assert api._refresh_token == "original_refresh_token"
