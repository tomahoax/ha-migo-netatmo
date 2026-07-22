"""Tests for the MiGo (Netatmo) API client."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.migo_netatmo.api import MigoApi, MigoApiError, MigoAuthError
from custom_components.migo_netatmo.const import MODE_MANUAL


def _create_mock_response(status: int, json_data: dict | None = None, text: str = "") -> MagicMock:
    """Create a mock aiohttp response that works as async context manager."""
    mock_response = MagicMock()
    mock_response.status = status
    mock_response.json = AsyncMock(return_value=json_data)
    mock_response.text = AsyncMock(return_value=text)
    return mock_response


def _create_mock_session(response: MagicMock) -> MagicMock:
    """Create a mock aiohttp session with proper async context manager support."""
    mock_session = MagicMock()
    mock_session.closed = False

    # Create an async context manager for the post method
    async_cm = AsyncMock()
    async_cm.__aenter__ = AsyncMock(return_value=response)
    async_cm.__aexit__ = AsyncMock(return_value=None)
    mock_session.post.return_value = async_cm

    return mock_session


class TestMigoApiAuthentication:
    """Tests for API authentication."""

    @pytest.mark.asyncio
    async def test_authenticate_success(self, token_response) -> None:
        """Test successful authentication."""
        mock_response = _create_mock_response(status=200, json_data=token_response)
        mock_session = _create_mock_session(mock_response)

        api = MigoApi(
            username="test@example.com",
            password="test_password",
            session=mock_session,
        )
        await api.authenticate()

        assert api._access_token == "test_access_token"
        assert api._refresh_token == "test_refresh_token"

    @pytest.mark.asyncio
    async def test_authenticate_invalid_credentials(self) -> None:
        """Test authentication with invalid credentials."""
        mock_response = _create_mock_response(status=403, text="Invalid credentials")
        mock_session = _create_mock_session(mock_response)

        api = MigoApi(
            username="test@example.com",
            password="test_password",
            session=mock_session,
        )
        with pytest.raises(MigoAuthError):
            await api.authenticate()


class TestMigoApiErrors:
    """Tests for API error handling."""

    def test_migo_api_error(self) -> None:
        """Test MigoApiError exception."""
        error = MigoApiError("Test error")
        assert str(error) == "Test error"

    def test_migo_auth_error(self) -> None:
        """Test MigoAuthError exception."""
        error = MigoAuthError("Auth failed")
        assert str(error) == "Auth failed"
        assert isinstance(error, MigoApiError)


class TestMigoApiSetTemperature:
    """Tests for set_temperature payload building (regression for issue #13)."""

    def _make_api(self) -> MigoApi:
        """Create an API client with a mocked request layer."""
        api = MigoApi(
            username="test@example.com",
            password="test_password",
            session=MagicMock(),
        )
        api._api_request = AsyncMock(return_value={"status": "ok"})
        return api

    def _sent_room_payload(self, api: MigoApi) -> dict:
        """Return the room dict sent to the setstate endpoint."""
        data = api._api_request.call_args.args[1]
        return data["home"]["rooms"][0]

    @pytest.mark.asyncio
    async def test_set_temperature_with_duration(self) -> None:
        """A duration in minutes becomes a therm_setpoint_end_time timestamp."""
        api = self._make_api()

        before = int(datetime.now(UTC).timestamp())
        await api.set_temperature(
            home_id="home_123",
            room_id="room_456",
            temperature=21.0,
            duration=60,
        )
        after = int(datetime.now(UTC).timestamp())

        room = self._sent_room_payload(api)
        assert room["id"] == "room_456"
        assert room["therm_setpoint_mode"] == MODE_MANUAL
        assert room["therm_setpoint_temperature"] == 21.0
        assert before + 3600 <= room["therm_setpoint_end_time"] <= after + 3600

    @pytest.mark.asyncio
    async def test_set_temperature_without_duration(self) -> None:
        """Without duration, no end time is sent (backend applies its default)."""
        api = self._make_api()

        await api.set_temperature(
            home_id="home_123",
            room_id="room_456",
            temperature=19.5,
        )

        room = self._sent_room_payload(api)
        assert room["therm_setpoint_mode"] == MODE_MANUAL
        assert room["therm_setpoint_temperature"] == 19.5
        assert "therm_setpoint_end_time" not in room

    @pytest.mark.asyncio
    async def test_set_room_state_with_end_time(self) -> None:
        """set_room_state forwards an explicit end_time unchanged."""
        api = self._make_api()

        await api.set_room_state(
            home_id="home_123",
            room_id="room_456",
            mode=MODE_MANUAL,
            temp=22.0,
            end_time=1704067200,
        )

        room = self._sent_room_payload(api)
        assert room["therm_setpoint_end_time"] == 1704067200


class TestMigoApiSession:
    """Tests for API session management."""

    def test_own_session_flag(self) -> None:
        """Test own_session flag is set correctly."""
        # When no session is provided, _own_session should be True
        api = MigoApi(username="test@example.com", password="test_password")
        assert api._own_session is True

    def test_provided_session_flag(self) -> None:
        """Test own_session flag when session is provided."""
        mock_session = MagicMock()
        api = MigoApi(
            username="test@example.com",
            password="test_password",
            session=mock_session,
        )
        assert api._own_session is False
        assert api._session is mock_session
