"""Tests for the MiGo (Netatmo) API client."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.migo_netatmo.api import (
    ERROR_BODY_MAX_LENGTH,
    MigoApi,
    MigoApiError,
    MigoAuthError,
    MigoConnectionError,
    _summarise_error_body,
)
from custom_components.migo_netatmo.const import (
    API_CHANGEHEATINGALGO_URL,
    API_CHANGEHEATINGCURVE_URL,
    API_SETCONFIGS_URL,
    API_SETHEATINGSYSTEM_URL,
    API_SETHOMEDATA_URL,
    API_SETSTATE_URL,
    API_SETTHERMMODE_URL,
    API_SWITCHHOMESCHEDULE_URL,
    GRANT_TYPE_REFRESH,
    MODE_AWAY,
    MODE_HOME,
    MODE_MANUAL,
    MODE_SCHEDULE,
)


def _create_mock_response(status: int, json_data: dict | None = None, text: str = "") -> MagicMock:
    """Create a mock aiohttp response that works as async context manager."""
    mock_response = MagicMock()
    mock_response.status = status
    mock_response.json = AsyncMock(return_value=json_data)
    mock_response.text = AsyncMock(return_value=text)
    return mock_response


def _response_as_context_manager(response: MagicMock) -> AsyncMock:
    """Wrap a mock response as an async context manager."""
    async_cm = AsyncMock()
    async_cm.__aenter__ = AsyncMock(return_value=response)
    async_cm.__aexit__ = AsyncMock(return_value=None)
    return async_cm


def _create_mock_session(response: MagicMock) -> MagicMock:
    """Create a mock aiohttp session with proper async context manager support."""
    mock_session = MagicMock()
    mock_session.closed = False

    async_cm = _response_as_context_manager(response)
    mock_session.post.return_value = async_cm
    mock_session.request.return_value = async_cm

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


class TestMigoApiTokenRefresh:
    """Tests for refresh_access_token and _ensure_token_valid."""

    def _make_api(self, session: MagicMock | None = None) -> MigoApi:
        """Create an API client, optionally with a preset mock session."""
        return MigoApi(
            username="test@example.com",
            password="test_password",
            session=session or MagicMock(),
        )

    @pytest.mark.asyncio
    async def test_refresh_without_refresh_token_falls_back_to_authenticate(self, token_response) -> None:
        """With no refresh token stored, refresh_access_token does a full login."""
        mock_session = _create_mock_session(_create_mock_response(status=200, json_data=token_response))
        api = self._make_api(mock_session)
        assert api._refresh_token is None

        result = await api.refresh_access_token()

        assert result is True
        mock_session.post.assert_called_once()
        assert api._access_token == "test_access_token"

    @pytest.mark.asyncio
    async def test_refresh_success_preserves_refresh_token_when_absent(self, token_response) -> None:
        """A refresh response without a new refresh_token keeps the old one."""
        response_without_refresh = {k: v for k, v in token_response.items() if k != "refresh_token"}
        mock_session = _create_mock_session(_create_mock_response(status=200, json_data=response_without_refresh))
        api = self._make_api(mock_session)
        api._refresh_token = "existing_refresh_token"

        result = await api.refresh_access_token()

        assert result is True
        assert api._access_token == "test_access_token"
        assert api._refresh_token == "existing_refresh_token"

    @pytest.mark.asyncio
    async def test_refresh_non_200_falls_back_to_authenticate(self, token_response) -> None:
        """A non-200 refresh response triggers a full re-authentication."""
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post.side_effect = [
            _response_as_context_manager(_create_mock_response(status=400, text="expired")),
            _response_as_context_manager(_create_mock_response(status=200, json_data=token_response)),
        ]
        api = self._make_api(mock_session)
        api._refresh_token = "existing_refresh_token"

        result = await api.refresh_access_token()

        assert result is True
        assert mock_session.post.call_count == 2
        assert api._access_token == "test_access_token"

    @pytest.mark.asyncio
    async def test_refresh_connection_error_falls_back_to_authenticate(self, token_response) -> None:
        """A network error during refresh triggers a full re-authentication."""
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post.side_effect = [
            aiohttp.ClientConnectionError("network down"),
            _response_as_context_manager(_create_mock_response(status=200, json_data=token_response)),
        ]
        api = self._make_api(mock_session)
        api._refresh_token = "existing_refresh_token"

        result = await api.refresh_access_token()

        assert result is True
        assert mock_session.post.call_count == 2

    @pytest.mark.asyncio
    async def test_ensure_token_valid_authenticates_when_no_access_token(self, token_response) -> None:
        """No access token yet -> a full authenticate() call."""
        mock_session = _create_mock_session(_create_mock_response(status=200, json_data=token_response))
        api = self._make_api(mock_session)
        assert api._access_token is None

        await api._ensure_token_valid()

        mock_session.post.assert_called_once()
        assert api._access_token == "test_access_token"

    @pytest.mark.asyncio
    async def test_ensure_token_valid_authenticates_when_no_expiry(self, token_response) -> None:
        """An access token without a known expiry triggers a full authenticate()."""
        mock_session = _create_mock_session(_create_mock_response(status=200, json_data=token_response))
        api = self._make_api(mock_session)
        api._access_token = "stale_token"
        api._token_expiry = None

        await api._ensure_token_valid()

        mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_token_valid_refreshes_when_expiring_soon(self, token_response) -> None:
        """A token within the expiry buffer is refreshed via the refresh flow."""
        mock_session = _create_mock_session(_create_mock_response(status=200, json_data=token_response))
        api = self._make_api(mock_session)
        api._access_token = "current_token"
        api._refresh_token = "current_refresh_token"
        api._token_expiry = datetime.now(UTC) + timedelta(seconds=10)

        await api._ensure_token_valid()

        # Refreshed via the refresh_token grant, not a fresh username/password login.
        mock_session.post.assert_called_once()
        sent_data = mock_session.post.call_args.kwargs["data"]
        assert sent_data["grant_type"] == GRANT_TYPE_REFRESH

    @pytest.mark.asyncio
    async def test_ensure_token_valid_does_nothing_when_still_valid(self) -> None:
        """A token well within its lifetime triggers no network call."""
        mock_session = MagicMock()
        mock_session.closed = False
        api = self._make_api(mock_session)
        api._access_token = "current_token"
        api._token_expiry = datetime.now(UTC) + timedelta(hours=1)

        await api._ensure_token_valid()

        mock_session.post.assert_not_called()


class TestMigoApiRequest:
    """Tests for the low-level _api_request helper (401 retry, error mapping)."""

    def _make_authenticated_api(self, session: MagicMock) -> MigoApi:
        """Create an API client that already holds a valid access token."""
        api = MigoApi(username="test@example.com", password="test_password", session=session)
        api._access_token = "current_token"
        api._token_expiry = datetime.now(UTC) + timedelta(hours=1)
        return api

    @pytest.mark.asyncio
    async def test_api_request_401_reauthenticates_and_retries(self, token_response) -> None:
        """A 401 triggers one full re-authentication and a single retry."""
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.request.side_effect = [
            _response_as_context_manager(_create_mock_response(status=401)),
            _response_as_context_manager(_create_mock_response(status=200, json_data={"status": "ok"})),
        ]
        mock_session.post.return_value = _response_as_context_manager(
            _create_mock_response(status=200, json_data=token_response)
        )
        api = self._make_authenticated_api(mock_session)

        result = await api._api_request("https://app.netatmo.net/api/somewhere", {"a": 1})

        assert result == {"status": "ok"}
        assert mock_session.request.call_count == 2
        mock_session.post.assert_called_once()  # the re-authenticate call

    @pytest.mark.asyncio
    async def test_api_request_401_retry_also_fails_raises_api_error(self, token_response) -> None:
        """If the retry after re-auth still errors, MigoApiError propagates."""
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.request.side_effect = [
            _response_as_context_manager(_create_mock_response(status=401)),
            _response_as_context_manager(_create_mock_response(status=500, text="still broken")),
        ]
        mock_session.post.return_value = _response_as_context_manager(
            _create_mock_response(status=200, json_data=token_response)
        )
        api = self._make_authenticated_api(mock_session)

        with pytest.raises(MigoApiError):
            await api._api_request("https://app.netatmo.net/api/somewhere")

    @pytest.mark.asyncio
    async def test_api_request_http_error_raises_api_error(self) -> None:
        """A non-401 error status raises MigoApiError with the response body."""
        mock_session = _create_mock_session(_create_mock_response(status=500, text="server error"))
        api = self._make_authenticated_api(mock_session)

        with pytest.raises(MigoApiError, match="500"):
            await api._api_request("https://app.netatmo.net/api/somewhere")

    @pytest.mark.asyncio
    async def test_api_request_connection_error_raises_migo_connection_error(self) -> None:
        """A network-level error is translated to MigoConnectionError."""
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.request.side_effect = aiohttp.ClientConnectionError("network down")
        api = self._make_authenticated_api(mock_session)

        with pytest.raises(MigoConnectionError):
            await api._api_request("https://app.netatmo.net/api/somewhere")

    @pytest.mark.asyncio
    async def test_api_request_non_object_payload_raises_api_error(self) -> None:
        """A 200 carrying a JSON array, not an object, is rejected at the boundary.

        Without this guard the array propagated as if it were a mapping, and the
        failure surfaced much later as an AttributeError somewhere downstream.
        """
        mock_session = _create_mock_session(_create_mock_response(status=200, json_data=["not", "an", "object"]))
        api = self._make_authenticated_api(mock_session)

        with pytest.raises(MigoApiError, match="Expected a JSON object"):
            await api._api_request("https://app.netatmo.net/api/somewhere")

    @pytest.mark.asyncio
    async def test_authenticate_without_access_token_raises_auth_error(self) -> None:
        """A token response with no access_token surfaces as an auth failure.

        It used to escape as a bare KeyError, which no caller handled.
        """
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post.return_value = _response_as_context_manager(
            _create_mock_response(status=200, json_data={"expires_in": 10800})
        )
        api = MigoApi(username="test@example.com", password="test_password", session=mock_session)

        with pytest.raises(MigoAuthError, match="no access token"):
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


class TestMigoApiControlMethods:
    """Tests for the thin setXxx wrapper methods (payload + endpoint URL)."""

    def _make_api(self) -> MigoApi:
        """Create an API client with a mocked request layer."""
        api = MigoApi(
            username="test@example.com",
            password="test_password",
            session=MagicMock(),
        )
        api._api_request = AsyncMock(return_value={"status": "ok"})
        return api

    @pytest.mark.asyncio
    async def test_set_mode_global_mode_uses_therm_mode_endpoint(self) -> None:
        """schedule/away are home-wide modes routed through setthermmode."""
        api = self._make_api()

        await api.set_mode(home_id="home_123", room_id="room_456", mode=MODE_SCHEDULE)

        api._api_request.assert_awaited_once_with(API_SETTHERMMODE_URL, {"home_id": "home_123", "mode": MODE_SCHEDULE})

    @pytest.mark.asyncio
    async def test_set_mode_room_mode_uses_setstate_endpoint(self) -> None:
        """manual/home/hg are room-level modes routed through setstate."""
        api = self._make_api()

        await api.set_mode(home_id="home_123", room_id="room_456", mode=MODE_HOME)

        url, data = api._api_request.call_args.args
        assert url == API_SETSTATE_URL
        assert data["home"]["rooms"][0] == {"id": "room_456", "therm_setpoint_mode": MODE_HOME}

    @pytest.mark.asyncio
    async def test_set_therm_mode(self) -> None:
        """set_therm_mode posts home_id and mode to setthermmode."""
        api = self._make_api()

        await api.set_therm_mode(home_id="home_123", mode=MODE_AWAY)

        api._api_request.assert_awaited_once_with(API_SETTHERMMODE_URL, {"home_id": "home_123", "mode": MODE_AWAY})

    @pytest.mark.asyncio
    async def test_set_dhw_enabled(self) -> None:
        """set_dhw_enabled nests the module under home.modules."""
        api = self._make_api()

        await api.set_dhw_enabled(home_id="home_123", module_id="gateway_001", enabled=True)

        url, data = api._api_request.call_args.args
        assert url == API_SETSTATE_URL
        assert data["home"]["modules"][0] == {"id": "gateway_001", "dhw_enabled": True}

    @pytest.mark.asyncio
    async def test_switch_home_schedule(self) -> None:
        """switch_home_schedule posts home_id and schedule_id."""
        api = self._make_api()

        await api.switch_home_schedule(home_id="home_123", schedule_id="schedule_001")

        api._api_request.assert_awaited_once_with(
            API_SWITCHHOMESCHEDULE_URL, {"home_id": "home_123", "schedule_id": "schedule_001"}
        )

    @pytest.mark.asyncio
    async def test_set_anticipation(self) -> None:
        """set_anticipation nests the flag under home.anticipation."""
        api = self._make_api()

        await api.set_anticipation(home_id="home_123", enabled=False)

        url, data = api._api_request.call_args.args
        assert url == API_SETHOMEDATA_URL
        assert data["home"] == {"id": "home_123", "anticipation": False}

    @pytest.mark.asyncio
    async def test_set_heating_curve_converts_slope_to_api_units(self) -> None:
        """UI slope (0.0-5.0) is sent as an integer API value (slope * 10)."""
        api = self._make_api()

        await api.set_heating_curve(device_id="gateway_001", slope=1.7)

        api._api_request.assert_awaited_once_with(API_CHANGEHEATINGCURVE_URL, {"device_id": "gateway_001", "slope": 17})

    @pytest.mark.asyncio
    async def test_set_heating_type(self) -> None:
        """set_heating_type posts device_id and heating_type."""
        api = self._make_api()

        await api.set_heating_type(device_id="gateway_001", heating_type="floor_heating")

        api._api_request.assert_awaited_once_with(
            API_SETHEATINGSYSTEM_URL, {"device_id": "gateway_001", "heating_type": "floor_heating"}
        )

    @pytest.mark.asyncio
    async def test_set_dhw_storage_water_tank(self) -> None:
        """use_water_tank=True maps to dhw_control='water_tank'."""
        api = self._make_api()

        await api.set_dhw_storage(home_id="home_123", module_id="gateway_001", use_water_tank=True)

        url, data = api._api_request.call_args.args
        assert url == API_SETHOMEDATA_URL
        assert data["home"]["modules"][0] == {"id": "gateway_001", "dhw_control": "water_tank"}

    @pytest.mark.asyncio
    async def test_set_dhw_storage_instantaneous(self) -> None:
        """use_water_tank=False maps to dhw_control='instantaneous'."""
        api = self._make_api()

        await api.set_dhw_storage(home_id="home_123", module_id="gateway_001", use_water_tank=False)

        data = api._api_request.call_args.args[1]
        assert data["home"]["modules"][0]["dhw_control"] == "instantaneous"

    @pytest.mark.asyncio
    async def test_set_dhw_temperature(self) -> None:
        """set_dhw_temperature sends home_id at root and the value under home.modules."""
        api = self._make_api()

        await api.set_dhw_temperature(home_id="home_123", module_id="gateway_001", temperature=55)

        url, data = api._api_request.call_args.args
        assert url == API_SETCONFIGS_URL
        assert data["home_id"] == "home_123"
        assert data["home"]["modules"][0] == {"id": "gateway_001", "dhw_setpoint_temperature": 55}

    @pytest.mark.asyncio
    async def test_set_temperature_offset(self) -> None:
        """set_temperature_offset nests the offset under home.rooms."""
        api = self._make_api()

        await api.set_temperature_offset(home_id="home_123", room_id="room_456", offset=-1.5)

        url, data = api._api_request.call_args.args
        assert url == API_SETCONFIGS_URL
        assert data["home"]["rooms"][0] == {"id": "room_456", "therm_setpoint_offset": -1.5}

    @pytest.mark.asyncio
    async def test_set_manual_setpoint_duration(self) -> None:
        """set_manual_setpoint_duration nests the duration under home."""
        api = self._make_api()

        await api.set_manual_setpoint_duration(home_id="home_123", duration=90)

        url, data = api._api_request.call_args.args
        assert url == API_SETHOMEDATA_URL
        assert data["home"] == {"id": "home_123", "therm_setpoint_default_duration": 90}

    @pytest.mark.asyncio
    async def test_set_hysteresis_converts_to_high_deadband(self) -> None:
        """Hysteresis in °C is converted to the API's high_deadband unit."""
        api = self._make_api()

        await api.set_hysteresis(device_id="gateway_001", hysteresis=0.4)

        api._api_request.assert_awaited_once_with(
            API_CHANGEHEATINGALGO_URL,
            {
                "device_id": "gateway_001",
                "algo_type": "simple_algo",
                "algo_params": {"high_deadband": 3},
            },
        )


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


class TestMigoApiCredentialHygiene:
    """Tests for clear_credentials()."""

    def test_clear_credentials_forgets_password_and_tokens(self) -> None:
        """After clearing, nothing usable is left on the object."""
        api = MigoApi(username="test@example.com", password="secret", session=MagicMock())
        api._access_token = "live_access"
        api._refresh_token = "live_refresh"
        api._token_expiry = datetime.now(UTC) + timedelta(hours=1)

        api.clear_credentials()

        assert api._password == ""
        assert api._access_token is None
        assert api._refresh_token is None
        assert api._token_expiry is None

    def test_clear_credentials_leaves_the_shared_session_open(self) -> None:
        """It must not close a session Home Assistant owns."""
        session = MagicMock()
        session.closed = False
        api = MigoApi(username="test@example.com", password="secret", session=session)

        api.clear_credentials()

        session.close.assert_not_called()


class TestErrorBodySummary:
    """Tests for _summarise_error_body()."""

    def test_short_bodies_pass_through(self) -> None:
        """A normal Netatmo error body is already short."""
        body = '{"error":{"code":11,"message":"failed to connect to the database"}}'
        assert _summarise_error_body(body) == body

    def test_long_bodies_are_truncated(self) -> None:
        """A hostile backend must not get an unbounded channel into the UI."""
        result = _summarise_error_body("A" * 5000)

        assert len(result) == ERROR_BODY_MAX_LENGTH + 3
        assert result.endswith("...")

    def test_newlines_are_collapsed(self) -> None:
        """Multi-line bodies must not break the single-line error notification."""
        assert _summarise_error_body("line one\n\nline  two") == "line one line two"
