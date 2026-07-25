"""Tests that debug logging does not write personal data to disk.

This is the regression guard for the finding that started the security audit: a
real 102 MB Home Assistant log contained the account email, the home's GPS
coordinates and a home invitation code 3175 times each, because the API client
logged every decoded response verbatim at DEBUG.

The Home Assistant log is downloadable from the UI by any admin, included in full
backups, readable by any add-on with config access, and is the artefact users
most often attach to a GitHub issue. So this is not a theoretical exposure.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.migo_netatmo.api import MigoApi, _log_payload, _raw_logging_enabled
from custom_components.migo_netatmo.redact import REDACTED
from tests.test_api import (
    _create_mock_response,
    _create_mock_session,
    _response_as_context_manager,
)

# Values planted in the conftest fixtures. If a refresh writes any of these to a
# log, a user sharing that log discloses their home address and account login.
LEAKY_VALUES = (
    "test@example.com",
    "49.123456",
    "Somewhere",
    "ZsdApbpjOstMdOn1",
    "SN123456",
)

RAW_LOGGER_NAME = "custom_components.migo_netatmo.api.raw"

# The shape the real backend returns, reduced to the fields that leaked.
HOMESDATA = {
    "body": {
        "user": {"email": "test@example.com", "country": "FR"},
        "homes": [
            {
                "id": "home_123",
                "name": "My Home",
                "coordinates": [49.123456, 2.654321],
                "city": "Somewhere",
                "invitation_code": ["ZsdApbpjOstMdOn1"],
                "modules": [{"id": "gateway_001", "oem_serial": "SN123456"}],
            }
        ],
    },
    "status": "ok",
}


class TestApiRequestDoesNotLeak:
    """The real _api_request path, driven with a mocked HTTP session.

    This has to exercise the actual client: the fixtures used elsewhere replace
    MigoApi wholesale, so a coordinator-level test would pass even with redaction
    removed entirely. That is precisely the trap this file has to avoid.
    """

    async def test_response_is_logged_redacted(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A realistic homesdata response is logged with personal data removed."""
        mock_session = _create_mock_session(_create_mock_response(status=200, json_data=HOMESDATA))
        api = MigoApi(username="test@example.com", password="pw", session=mock_session)
        api._access_token = "token"
        api._token_expiry = datetime.now(UTC) + timedelta(hours=1)

        with caplog.at_level(logging.DEBUG, logger="custom_components.migo_netatmo"):
            await api._api_request("https://app.netatmo.net/api/homesdata")

        # It was logged, and redacted, not merely skipped.
        assert "API response data" in caplog.text
        assert REDACTED in caplog.text
        for value in LEAKY_VALUES:
            assert value not in caplog.text, f"{value!r} was written to the log"

    async def test_identifiers_survive_in_the_log(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Redaction must not make the logs useless for diagnosis."""
        mock_session = _create_mock_session(_create_mock_response(status=200, json_data=HOMESDATA))
        api = MigoApi(username="test@example.com", password="pw", session=mock_session)
        api._access_token = "token"
        api._token_expiry = datetime.now(UTC) + timedelta(hours=1)

        with caplog.at_level(logging.DEBUG, logger="custom_components.migo_netatmo"):
            await api._api_request("https://app.netatmo.net/api/homesdata")

        assert "home_123" in caplog.text
        assert "gateway_001" in caplog.text

    async def test_the_account_email_is_masked_on_authentication(
        self,
        caplog: pytest.LogCaptureFixture,
        token_response: dict,
    ) -> None:
        """The auth log line said which account, in full. Now it masks it."""
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post.return_value = _response_as_context_manager(
            _create_mock_response(status=200, json_data=token_response)
        )
        api = MigoApi(username="test@example.com", password="pw", session=mock_session)

        with caplog.at_level(logging.DEBUG, logger="custom_components.migo_netatmo"):
            await api.authenticate()

        assert "test@example.com" not in caplog.text
        # Still distinguishable, for an install with more than one account.
        assert "t***@example.com" in caplog.text


class TestCoordinatorLogsDoNotLeak:
    """The coordinator's own dumps, which do fire under the standard fixtures."""

    async def test_no_personal_data_in_a_full_refresh(
        self,
        hass: HomeAssistant,
        init_integration: MockConfigEntry,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A full setup plus refresh at DEBUG writes none of the leaky values."""
        coordinator = init_integration.runtime_data.coordinator

        with caplog.at_level(logging.DEBUG, logger="custom_components.migo_netatmo"):
            await coordinator.async_refresh()
            await hass.async_block_till_done()

        for value in LEAKY_VALUES:
            assert value not in caplog.text, f"{value!r} was written to the log"

    async def test_home_name_is_not_logged(
        self,
        hass: HomeAssistant,
        init_integration: MockConfigEntry,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """The per-cycle "Processing home" line used to carry the home name."""
        coordinator = init_integration.runtime_data.coordinator

        with caplog.at_level(logging.DEBUG, logger="custom_components.migo_netatmo"):
            await coordinator.async_refresh()
            await hass.async_block_till_done()

        assert "Processing home home_123" in caplog.text
        assert "My Home" not in caplog.text


class TestRawLogger:
    """The opt-in unredacted channel."""

    def test_silent_when_only_the_package_is_at_debug(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """The whole point: debugging the integration must not enable raw dumps.

        A child logger inherits its parent's level, so an implementation that
        checked the effective level would leak for every user who follows the
        troubleshooting guide.
        """
        with caplog.at_level(logging.DEBUG, logger="custom_components.migo_netatmo"):
            assert _raw_logging_enabled() is False
            _log_payload("probe", {"email": "test@example.com"})

        assert "test@example.com" not in caplog.text
        assert REDACTED in caplog.text

    def test_verbose_only_when_the_raw_logger_is_set_explicitly(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Setting the raw logger's own level opts in to unredacted payloads."""
        raw_logger = logging.getLogger(RAW_LOGGER_NAME)
        previous = raw_logger.level
        raw_logger.setLevel(logging.DEBUG)
        try:
            with caplog.at_level(logging.DEBUG, logger=RAW_LOGGER_NAME):
                assert _raw_logging_enabled() is True
                _log_payload("probe", {"email": "test@example.com"})

            assert "test@example.com" in caplog.text
        finally:
            raw_logger.setLevel(previous)

    def test_nothing_is_logged_when_debug_is_off(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Redaction is skipped entirely when nobody is listening.

        redact() copies the whole payload, and this runs on every poll, so the
        cost must not be paid by users who are not debugging.
        """
        with caplog.at_level(logging.INFO, logger="custom_components.migo_netatmo"):
            _log_payload("probe", {"email": "test@example.com"})

        assert "probe" not in caplog.text
