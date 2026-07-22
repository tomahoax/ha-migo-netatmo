"""Tests for the MiGo (Netatmo) config flow."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.migo_netatmo.api import MigoAuthError
from custom_components.migo_netatmo.const import DOMAIN

USER_INPUT = {"username": "test@example.com", "password": "test_password"}


@pytest.fixture
def mock_setup_entry():
    """Prevent the created entry from actually setting up."""
    with patch("custom_components.migo_netatmo.async_setup_entry", return_value=True) as mock:
        yield mock


class TestUserFlow:
    """Tests for the user step, driven through the flow manager."""

    async def test_form_shown(self, hass: HomeAssistant) -> None:
        """Test we get the initial form."""
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"
        assert result["errors"] == {}

    async def test_success_creates_entry(
        self,
        hass: HomeAssistant,
        patch_migo_api: MagicMock,
        mock_setup_entry: MagicMock,
    ) -> None:
        """Test a successful setup creates the entry with the right data."""
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
        await hass.async_block_till_done()

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["title"] == "test@example.com"
        assert result["data"] == USER_INPUT
        assert result["result"].unique_id == "test@example.com"
        patch_migo_api.authenticate.assert_called_once()
        patch_migo_api.close.assert_called_once()
        assert len(mock_setup_entry.mock_calls) == 1

    async def test_invalid_auth_then_recovery(
        self,
        hass: HomeAssistant,
        patch_migo_api: MagicMock,
        mock_setup_entry: MagicMock,
    ) -> None:
        """Test an auth error shows the form again, then the flow recovers."""
        patch_migo_api.authenticate.side_effect = MigoAuthError("Invalid credentials")

        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "invalid_auth"}

        patch_migo_api.authenticate.side_effect = None
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
        await hass.async_block_till_done()

        assert result["type"] is FlowResultType.CREATE_ENTRY

    async def test_no_homes(
        self,
        hass: HomeAssistant,
        patch_migo_api: MagicMock,
    ) -> None:
        """Test an account without homes is rejected."""
        patch_migo_api.get_homes_data.return_value = {"body": {"homes": []}}

        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "no_homes"}

    async def test_unknown_error(
        self,
        hass: HomeAssistant,
        patch_migo_api: MagicMock,
    ) -> None:
        """Test unexpected exceptions map to the unknown error."""
        patch_migo_api.authenticate.side_effect = Exception("boom")

        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "unknown"}

    async def test_duplicate_account_aborts(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        patch_migo_api: MagicMock,
    ) -> None:
        """Test configuring the same account twice aborts."""
        mock_config_entry.add_to_hass(hass)

        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "already_configured"


class TestReauthFlow:
    """Tests for the reauth flow, driven through the flow manager."""

    async def test_reauth_success(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        patch_migo_api: MagicMock,
        mock_setup_entry: MagicMock,
    ) -> None:
        """Test a successful reauth updates the entry data."""
        mock_config_entry.add_to_hass(hass)

        result = await mock_config_entry.start_reauth_flow(hass)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "reauth_confirm"

        new_input = {"username": "test@example.com", "password": "new_password"}
        result = await hass.config_entries.flow.async_configure(result["flow_id"], new_input)
        await hass.async_block_till_done()

        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "reauth_successful"
        assert mock_config_entry.data["password"] == "new_password"

    async def test_reauth_invalid_auth(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        patch_migo_api: MagicMock,
    ) -> None:
        """Test reauth with still-invalid credentials shows the error."""
        mock_config_entry.add_to_hass(hass)
        patch_migo_api.authenticate.side_effect = MigoAuthError("Invalid credentials")

        result = await mock_config_entry.start_reauth_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"username": "test@example.com", "password": "wrong_password"},
        )

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "invalid_auth"}

    async def test_reauth_account_mismatch_aborts(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        patch_migo_api: MagicMock,
    ) -> None:
        """Test reauth with a different account aborts."""
        mock_config_entry.add_to_hass(hass)

        result = await mock_config_entry.start_reauth_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"username": "other@example.com", "password": "whatever"},
        )

        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "unique_id_mismatch"


class TestReconfigureFlow:
    """Tests for the reconfigure flow."""

    async def test_reconfigure_success(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        patch_migo_api: MagicMock,
        mock_setup_entry: MagicMock,
    ) -> None:
        """Test a successful reconfigure updates the entry data."""
        mock_config_entry.add_to_hass(hass)

        result = await mock_config_entry.start_reconfigure_flow(hass)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "reconfigure"

        new_input = {"username": "test@example.com", "password": "brand_new_password"}
        result = await hass.config_entries.flow.async_configure(result["flow_id"], new_input)
        await hass.async_block_till_done()

        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "reconfigure_successful"
        assert mock_config_entry.data["password"] == "brand_new_password"

    async def test_reconfigure_account_mismatch_aborts(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        patch_migo_api: MagicMock,
    ) -> None:
        """Test reconfiguring to a different account aborts."""
        mock_config_entry.add_to_hass(hass)

        result = await mock_config_entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"username": "other@example.com", "password": "whatever"},
        )

        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "unique_id_mismatch"


class TestOptionsFlow:
    """Tests for the options flow."""

    async def test_options_update_interval_reloads(
        self,
        hass: HomeAssistant,
        init_integration: MockConfigEntry,
        patch_migo_api: MagicMock,
    ) -> None:
        """Test setting the polling interval reloads the entry automatically."""
        setup_calls_before = patch_migo_api.get_homes_data.call_count

        result = await hass.config_entries.options.async_init(init_integration.entry_id)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "init"

        result = await hass.config_entries.options.async_configure(result["flow_id"], {"update_interval": 120})
        await hass.async_block_till_done()

        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert init_integration.options == {"update_interval": 120}
        # OptionsFlowWithReload reloads the entry: setup ran again
        assert patch_migo_api.get_homes_data.call_count > setup_calls_before
        coordinator = init_integration.runtime_data.coordinator
        assert coordinator.update_interval.total_seconds() == 120
