"""Tests for the MiGo (Netatmo) API client."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.migo_netatmo.api import MigoApi, MigoApiError, MigoAuthError


@pytest.fixture
def api():
    """Create an API instance for testing."""
    return MigoApi(username="test@example.com", password="test_password")


class TestMigoApiAuthentication:
    """Tests for API authentication."""

    @pytest.mark.asyncio
    async def test_authenticate_success(self, api, token_response) -> None:
        """Test successful authentication."""
        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=token_response)
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)
            mock_post.return_value = mock_response

            await api.authenticate()

            assert api._access_token == "test_access_token"
            assert api._refresh_token == "test_refresh_token"
            await api.close()

    @pytest.mark.asyncio
    async def test_authenticate_invalid_credentials(self, api) -> None:
        """Test authentication with invalid credentials."""
        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 403
            mock_response.text = AsyncMock(return_value="Invalid credentials")
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)
            mock_post.return_value = mock_response

            with pytest.raises(MigoAuthError):
                await api.authenticate()
            await api.close()


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


class TestMigoApiSession:
    """Tests for API session management."""

    def test_own_session_flag(self, api) -> None:
        """Test own_session flag is set correctly."""
        # When no session is provided, _own_session should be True
        assert api._own_session is True

    def test_provided_session_flag(self) -> None:
        """Test own_session flag when session is provided."""
        from unittest.mock import MagicMock

        mock_session = MagicMock()
        api = MigoApi(
            username="test@example.com",
            password="test_password",
            session=mock_session,
        )
        assert api._own_session is False
        assert api._session is mock_session
