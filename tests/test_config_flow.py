"""Tests for the MiGo (Netatmo) config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.migo_netatmo.api import MigoAuthError
from custom_components.migo_netatmo.config_flow import MigoConfigFlow


class TestConfigFlow:
    """Tests for the config flow."""

    @pytest.mark.asyncio
    async def test_step_user_form(self) -> None:
        """Test we get the form."""
        flow = MigoConfigFlow()
        flow.hass = MagicMock()

        result = await flow.async_step_user()

        assert result["type"] == "form"
        assert result["step_id"] == "user"
        assert result["errors"] == {}

    @pytest.mark.asyncio
    async def test_step_user_success(self, homes_data_response) -> None:
        """Test successful user step."""
        flow = MigoConfigFlow()
        flow.hass = MagicMock()
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = MagicMock()
        flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})

        with patch("custom_components.migo_netatmo.config_flow.MigoApi") as mock_api_class:
            mock_api = MagicMock()
            mock_api.authenticate = AsyncMock()
            mock_api.get_homes_data = AsyncMock(return_value=homes_data_response)
            mock_api.close = AsyncMock()
            mock_api_class.return_value = mock_api

            result = await flow.async_step_user({"username": "test@example.com", "password": "test_password"})

            assert result["type"] == "create_entry"
            mock_api.authenticate.assert_called_once()
            mock_api.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_step_user_invalid_auth(self) -> None:
        """Test invalid auth error."""
        flow = MigoConfigFlow()
        flow.hass = MagicMock()

        with patch("custom_components.migo_netatmo.config_flow.MigoApi") as mock_api_class:
            mock_api = MagicMock()
            mock_api.authenticate = AsyncMock(side_effect=MigoAuthError("Invalid credentials"))
            mock_api_class.return_value = mock_api

            result = await flow.async_step_user({"username": "test@example.com", "password": "wrong_password"})

            assert result["type"] == "form"
            assert result["errors"] == {"base": "invalid_auth"}

    @pytest.mark.asyncio
    async def test_step_user_no_homes(self) -> None:
        """Test no homes error."""
        flow = MigoConfigFlow()
        flow.hass = MagicMock()

        with patch("custom_components.migo_netatmo.config_flow.MigoApi") as mock_api_class:
            mock_api = MagicMock()
            mock_api.authenticate = AsyncMock()
            mock_api.get_homes_data = AsyncMock(return_value={"body": {"homes": []}})
            mock_api.close = AsyncMock()
            mock_api_class.return_value = mock_api

            result = await flow.async_step_user({"username": "test@example.com", "password": "test_password"})

            assert result["type"] == "form"
            assert result["errors"] == {"base": "no_homes"}

    @pytest.mark.asyncio
    async def test_step_user_unknown_error(self) -> None:
        """Test unknown error handling."""
        flow = MigoConfigFlow()
        flow.hass = MagicMock()

        with patch("custom_components.migo_netatmo.config_flow.MigoApi") as mock_api_class:
            mock_api = MagicMock()
            mock_api.authenticate = AsyncMock(side_effect=Exception("Unknown error"))
            mock_api_class.return_value = mock_api

            result = await flow.async_step_user({"username": "test@example.com", "password": "test_password"})

            assert result["type"] == "form"
            assert result["errors"] == {"base": "unknown"}


class TestReauthFlow:
    """Tests for the reauth flow."""

    @pytest.mark.asyncio
    async def test_step_reauth(self) -> None:
        """Test reauth step redirects to reauth_confirm."""
        flow = MigoConfigFlow()
        flow.hass = MagicMock()
        flow.async_step_reauth_confirm = AsyncMock(return_value={"type": "form", "step_id": "reauth_confirm"})

        result = await flow.async_step_reauth({"username": "test@example.com"})

        assert result["type"] == "form"
        assert result["step_id"] == "reauth_confirm"

    @pytest.mark.asyncio
    async def test_step_reauth_confirm_success(self) -> None:
        """Test successful reauth confirm."""
        flow = MigoConfigFlow()
        flow.hass = MagicMock()
        flow.hass.config_entries = MagicMock()
        flow.hass.config_entries.async_update_entry = MagicMock()
        flow.hass.config_entries.async_reload = AsyncMock()

        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry_id"
        flow._get_reauth_entry = MagicMock(return_value=mock_entry)
        flow.async_abort = MagicMock(return_value={"type": "abort", "reason": "reauth_successful"})

        with patch("custom_components.migo_netatmo.config_flow.MigoApi") as mock_api_class:
            mock_api = MagicMock()
            mock_api.authenticate = AsyncMock()
            mock_api.close = AsyncMock()
            mock_api_class.return_value = mock_api

            result = await flow.async_step_reauth_confirm({"username": "test@example.com", "password": "new_password"})

            assert result["type"] == "abort"
            assert result["reason"] == "reauth_successful"

    @pytest.mark.asyncio
    async def test_step_reauth_confirm_invalid_auth(self) -> None:
        """Test reauth with invalid credentials."""
        flow = MigoConfigFlow()
        flow.hass = MagicMock()

        with patch("custom_components.migo_netatmo.config_flow.MigoApi") as mock_api_class:
            mock_api = MagicMock()
            mock_api.authenticate = AsyncMock(side_effect=MigoAuthError("Invalid credentials"))
            mock_api_class.return_value = mock_api

            result = await flow.async_step_reauth_confirm(
                {"username": "test@example.com", "password": "wrong_password"}
            )

            assert result["type"] == "form"
            assert result["errors"] == {"base": "invalid_auth"}
