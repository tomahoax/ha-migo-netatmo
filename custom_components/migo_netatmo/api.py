"""API client for MiGo (Netatmo) integration."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import aiohttp

from .const import (
    API_AUTH_URL,
    API_CHANGEHEATINGCURVE_URL,
    API_HOMESDATA_URL,
    API_HOMESTATUS_URL,
    API_SETCONFIGS_URL,
    API_SETHEATINGSYSTEM_URL,
    API_SETHOMEDATA_URL,
    API_SETSTATE_URL,
    API_SETTHERMMODE_URL,
    API_SWITCHHOMESCHEDULE_URL,
    API_TIMEOUT,
    APP_IDENTIFIER,
    APP_TYPE,
    CLIENT_ID,
    CLIENT_SECRET,
    DEVICE_TYPE_GATEWAY,
    GRANT_TYPE_PASSWORD,
    GRANT_TYPE_REFRESH,
    MODE_AWAY,
    MODE_MANUAL,
    MODE_SCHEDULE,
    SCOPE,
    TOKEN_EXPIRY_BUFFER,
    USER_PREFIX,
)

_LOGGER = logging.getLogger(__name__)


class MigoApiError(Exception):
    """Base exception for MiGO API errors."""


class MigoAuthError(MigoApiError):
    """Authentication error."""


class MigoConnectionError(MigoApiError):
    """Connection error."""


class MigoApi:
    """API client for MiGo (Netatmo) thermostat.

    This client handles authentication and communication with the Netatmo API
    used by the MiGO app for Saunier Duval thermostats.
    """

    def __init__(
        self,
        username: str,
        password: str,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        """Initialize the API client.

        Args:
            username: The MiGO account email address.
            password: The MiGO account password.
            session: Optional aiohttp session to use. If not provided, one will be created.
        """
        self._username = username
        self._password = password
        self._session = session
        self._own_session = session is None
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._token_expiry: datetime | None = None
        self._timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session.

        Returns:
            An active aiohttp ClientSession.
        """
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
            self._own_session = True
        return self._session

    async def close(self) -> None:
        """Close the session if we own it."""
        if self._own_session and self._session and not self._session.closed:
            await self._session.close()

    def _build_auth_headers(self) -> dict[str, str]:
        """Build headers for form-urlencoded auth requests.

        Returns:
            Dictionary of HTTP headers.
        """
        return {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "*/*",
        }

    def _build_api_headers(self, use_json: bool = True) -> dict[str, str]:
        """Build headers for authenticated API requests.

        Args:
            use_json: Whether to use JSON content type.

        Returns:
            Dictionary of HTTP headers.
        """
        content_type = "application/json" if use_json else "application/x-www-form-urlencoded"
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": content_type,
            "Accept": "*/*",
        }

    async def authenticate(self) -> bool:
        """Authenticate with Netatmo API using username/password.

        Returns:
            True if authentication was successful.

        Raises:
            MigoAuthError: If authentication fails.
            MigoConnectionError: If there's a network error.
        """
        session = await self._get_session()

        data = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": GRANT_TYPE_PASSWORD,
            "username": self._username,
            "password": self._password,
            "user_prefix": USER_PREFIX,
            "scope": SCOPE,
        }

        _LOGGER.debug("Authenticating with Netatmo API for user: %s", self._username)

        try:
            async with session.post(
                API_AUTH_URL,
                data=data,
                headers=self._build_auth_headers(),
            ) as response:
                if response.status == 400:
                    error_data = await response.json()
                    error_msg = error_data.get("error", "Authentication failed")
                    _LOGGER.error("Authentication failed: %s", error_msg)
                    raise MigoAuthError(error_msg)

                if response.status != 200:
                    _LOGGER.error("Authentication failed with status: %d", response.status)
                    raise MigoAuthError(f"Authentication failed: HTTP {response.status}")

                result = await response.json()
                self._store_tokens(result)

                _LOGGER.debug(
                    "Authentication successful, token expires at %s",
                    self._token_expiry,
                )
                return True

        except aiohttp.ClientError as err:
            _LOGGER.error("Connection error during authentication: %s", err)
            raise MigoConnectionError(f"Connection error: {err}") from err

    async def refresh_access_token(self) -> bool:
        """Refresh the access token using the refresh token.

        If no refresh token is available, falls back to full authentication.

        Returns:
            True if token refresh was successful.

        Raises:
            MigoAuthError: If token refresh and re-authentication both fail.
        """
        if not self._refresh_token:
            _LOGGER.debug("No refresh token available, performing full authentication")
            return await self.authenticate()

        session = await self._get_session()

        data = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": GRANT_TYPE_REFRESH,
            "refresh_token": self._refresh_token,
        }

        _LOGGER.debug("Refreshing access token")

        try:
            async with session.post(
                API_AUTH_URL,
                data=data,
                headers=self._build_auth_headers(),
            ) as response:
                if response.status != 200:
                    _LOGGER.warning(
                        "Token refresh failed (status %d), re-authenticating",
                        response.status,
                    )
                    return await self.authenticate()

                result = await response.json()
                self._store_tokens(result, preserve_refresh=True)

                _LOGGER.debug("Token refreshed successfully")
                return True

        except aiohttp.ClientError as err:
            _LOGGER.warning("Error refreshing token: %s, re-authenticating", err)
            return await self.authenticate()

    def _store_tokens(
        self,
        token_data: dict[str, Any],
        preserve_refresh: bool = False,
    ) -> None:
        """Store tokens from API response.

        Args:
            token_data: The token response from the API.
            preserve_refresh: If True, preserve existing refresh token if not in response.
        """
        self._access_token = token_data["access_token"]

        if preserve_refresh:
            self._refresh_token = token_data.get("refresh_token", self._refresh_token)
        else:
            self._refresh_token = token_data.get("refresh_token")

        expires_in = token_data.get("expires_in", 10800)
        self._token_expiry = datetime.now(UTC) + timedelta(seconds=expires_in)

    async def _ensure_token_valid(self) -> None:
        """Ensure the access token is valid, refreshing if needed.

        Raises:
            MigoAuthError: If unable to obtain a valid token.
        """
        if self._access_token is None:
            await self.authenticate()
            return

        if self._token_expiry is None:
            await self.authenticate()
            return

        # Check if token will expire soon (within buffer time)
        now = datetime.now(UTC)
        expiry_threshold = self._token_expiry - timedelta(seconds=TOKEN_EXPIRY_BUFFER)

        if now > expiry_threshold:
            _LOGGER.debug("Token expiring soon, refreshing")
            await self.refresh_access_token()

    async def _api_request(
        self,
        url: str,
        data: dict[str, Any] | None = None,
        method: str = "POST",
        use_json: bool = True,
    ) -> dict[str, Any]:
        """Make an authenticated API request.

        Args:
            url: The API endpoint URL.
            data: Request body data.
            method: HTTP method to use.
            use_json: If True, send data as JSON. Otherwise, form-urlencoded.

        Returns:
            The JSON response from the API.

        Raises:
            MigoApiError: If the request fails.
        """
        await self._ensure_token_valid()

        session = await self._get_session()
        headers = self._build_api_headers(use_json)

        request_kwargs: dict[str, Any] = {"headers": headers}
        if data is not None:
            if use_json:
                request_kwargs["json"] = data
            else:
                request_kwargs["data"] = data

        # Log request details
        _LOGGER.debug("API request: %s %s", method, url)
        if data is not None:
            _LOGGER.debug("API request payload: %s", data)

        try:
            async with session.request(method, url, **request_kwargs) as response:
                # Log response status
                _LOGGER.debug("API response: %s status=%d", url, response.status)

                if response.status == 401:
                    # Token expired, refresh and retry once
                    _LOGGER.debug("Got 401, refreshing token and retrying")
                    await self.authenticate()
                    request_kwargs["headers"] = self._build_api_headers(use_json)

                    async with session.request(method, url, **request_kwargs) as retry_response:
                        _LOGGER.debug(
                            "API retry response: %s status=%d",
                            url,
                            retry_response.status,
                        )
                        if retry_response.status >= 400:
                            error_text = await retry_response.text()
                            _LOGGER.error(
                                "API error after retry: %s %s returned %d: %s",
                                method,
                                url,
                                retry_response.status,
                                error_text,
                            )
                            raise MigoApiError(f"API returned {retry_response.status}: {error_text}")
                        result = await retry_response.json()
                        _LOGGER.debug("API response data: %s", result)
                        return result

                if response.status >= 400:
                    error_text = await response.text()
                    _LOGGER.error(
                        "API error: %s %s returned %d: %s",
                        method,
                        url,
                        response.status,
                        error_text,
                    )
                    raise MigoApiError(f"API returned {response.status}: {error_text}")

                result = await response.json()
                _LOGGER.debug("API response data: %s", result)
                return result

        except aiohttp.ClientResponseError as err:
            _LOGGER.error(
                "API request failed: %s %s - status=%d message=%s",
                method,
                url,
                err.status,
                err.message,
            )
            raise MigoApiError(f"API request failed: {err}") from err
        except aiohttp.ClientError as err:
            _LOGGER.error("API connection error: %s %s - %s", method, url, err)
            raise MigoConnectionError(f"Connection error: {err}") from err

    # =========================================================================
    # Data Retrieval Methods
    # =========================================================================

    async def get_homes_data(self) -> dict[str, Any]:
        """Get homes data (static configuration) from API.

        This returns the structure of all homes, rooms, modules, and schedules.

        Returns:
            The homesdata response containing home configurations.
        """
        data = {
            "device_types": [DEVICE_TYPE_GATEWAY],
            "sync_measurements": True,
            "app_identifier": APP_IDENTIFIER,
            "home_id": None,
            "app_type": APP_TYPE,
        }

        _LOGGER.debug("Fetching homes data")
        return await self._api_request(API_HOMESDATA_URL, data)

    async def get_home_status(self, home_id: str) -> dict[str, Any]:
        """Get home status (real-time data) from API.

        This returns current temperatures, states, and device status.

        Args:
            home_id: The ID of the home to get status for.

        Returns:
            The homestatus response containing real-time data.
        """
        data = {"home_id": home_id}

        _LOGGER.debug("Fetching home status for: %s", home_id)
        return await self._api_request(API_HOMESTATUS_URL, data)

    # =========================================================================
    # Room Control Methods
    # =========================================================================

    async def set_room_state(
        self,
        home_id: str,
        room_id: str,
        mode: str | None = None,
        temp: float | None = None,
    ) -> dict[str, Any]:
        """Set room state using the setstate API.

        Args:
            home_id: The home ID.
            room_id: The room ID.
            mode: Optional mode to set (manual, home, hg).
            temp: Optional target temperature.

        Returns:
            The API response.
        """
        room_data: dict[str, Any] = {"id": room_id}

        if mode is not None:
            room_data["therm_setpoint_mode"] = mode

        if temp is not None:
            room_data["therm_setpoint_temperature"] = temp

        data = {
            "home": {
                "id": home_id,
                "rooms": [room_data],
            }
        }

        _LOGGER.debug("Setting room %s state: mode=%s, temp=%s", room_id, mode, temp)
        return await self._api_request(API_SETSTATE_URL, data)

    async def set_temperature(
        self,
        home_id: str,
        room_id: str,
        temperature: float,
    ) -> dict[str, Any]:
        """Set target temperature for a room.

        This sets the room to manual mode with the specified temperature.

        Args:
            home_id: The home ID.
            room_id: The room ID.
            temperature: The target temperature in Celsius.

        Returns:
            The API response.
        """
        return await self.set_room_state(
            home_id=home_id,
            room_id=room_id,
            mode=MODE_MANUAL,
            temp=temperature,
        )

    async def set_mode(
        self,
        home_id: str,
        room_id: str,
        mode: str,
    ) -> dict[str, Any]:
        """Set operating mode for a room or home.

        For room-level modes (manual, home, hg), uses setstate.
        For global modes (schedule, away), uses setthermmode.

        Args:
            home_id: The home ID.
            room_id: The room ID.
            mode: The mode to set.

        Returns:
            The API response.
        """
        # Global modes that affect the whole home
        if mode in (MODE_SCHEDULE, MODE_AWAY):
            return await self.set_therm_mode(home_id=home_id, mode=mode)

        # Room-level modes
        return await self.set_room_state(
            home_id=home_id,
            room_id=room_id,
            mode=mode,
        )

    # =========================================================================
    # Home Control Methods
    # =========================================================================

    async def set_therm_mode(
        self,
        home_id: str,
        mode: str,
    ) -> dict[str, Any]:
        """Set global thermostat mode for a home.

        Args:
            home_id: The home ID.
            mode: The mode (schedule, away, hg).

        Returns:
            The API response.
        """
        data = {
            "home_id": home_id,
            "mode": mode,
        }

        _LOGGER.debug("Setting home %s therm mode to: %s", home_id, mode)
        return await self._api_request(API_SETTHERMMODE_URL, data)

    async def set_dhw_enabled(
        self,
        home_id: str,
        module_id: str,
        enabled: bool,
    ) -> dict[str, Any]:
        """Enable or disable domestic hot water (DHW/ECS).

        Args:
            home_id: The home ID.
            module_id: The NAVaillant module ID (gateway).
            enabled: True to enable DHW, False to disable.

        Returns:
            The API response.
        """
        data = {
            "home": {
                "id": home_id,
                "modules": [
                    {
                        "id": module_id,
                        "dhw_enabled": enabled,
                    }
                ],
            }
        }

        _LOGGER.debug("Setting DHW enabled=%s for module %s", enabled, module_id)
        return await self._api_request(API_SETSTATE_URL, data)

    async def switch_home_schedule(
        self,
        home_id: str,
        schedule_id: str,
    ) -> dict[str, Any]:
        """Switch to a different schedule.

        Args:
            home_id: The home ID.
            schedule_id: The schedule ID to activate.

        Returns:
            The API response.
        """
        data = {
            "home_id": home_id,
            "schedule_id": schedule_id,
        }

        _LOGGER.debug("Switching home %s to schedule: %s", home_id, schedule_id)
        return await self._api_request(API_SWITCHHOMESCHEDULE_URL, data)

    # =========================================================================
    # Advanced Settings Methods
    # =========================================================================

    async def set_anticipation(
        self,
        home_id: str,
        enabled: bool,
    ) -> dict[str, Any]:
        """Enable or disable heating anticipation.

        Args:
            home_id: The home ID.
            enabled: True to enable anticipation, False to disable.

        Returns:
            The API response.
        """
        data = {
            "home": {
                "id": home_id,
                "anticipation": enabled,
            }
        }

        _LOGGER.debug("Setting anticipation=%s for home %s", enabled, home_id)
        return await self._api_request(API_SETHOMEDATA_URL, data)

    async def set_heating_curve(
        self,
        device_id: str,
        slope: int,
    ) -> dict[str, Any]:
        """Set heating curve (slope).

        Args:
            device_id: The gateway device ID.
            slope: The slope value (5-35, representing 0.5-3.5 in UI).

        Returns:
            The API response.
        """
        data = {
            "device_id": device_id,
            "slope": slope,
        }

        _LOGGER.debug("Setting heating curve slope=%s for device %s", slope, device_id)
        return await self._api_request(API_CHANGEHEATINGCURVE_URL, data)

    async def set_heating_type(
        self,
        device_id: str,
        heating_type: str,
    ) -> dict[str, Any]:
        """Set heating system type.

        Args:
            device_id: The gateway device ID.
            heating_type: The heating type (radiators, convector, floor_heating, unknown).

        Returns:
            The API response.
        """
        data = {
            "device_id": device_id,
            "heating_type": heating_type,
        }

        _LOGGER.debug("Setting heating type=%s for device %s", heating_type, device_id)
        return await self._api_request(API_SETHEATINGSYSTEM_URL, data)

    async def set_dhw_storage(
        self,
        home_id: str,
        module_id: str,
        use_water_tank: bool,
    ) -> dict[str, Any]:
        """Set DHW storage mode (water tank vs instantaneous).

        Args:
            home_id: The home ID.
            module_id: The gateway module ID.
            use_water_tank: True for water tank, False for instantaneous.

        Returns:
            The API response.
        """
        dhw_control = "water_tank" if use_water_tank else "instantaneous"
        data = {
            "home": {
                "id": home_id,
                "modules": [
                    {
                        "id": module_id,
                        "dhw_control": dhw_control,
                    }
                ],
            }
        }

        _LOGGER.debug("Setting DHW storage=%s for module %s", dhw_control, module_id)
        return await self._api_request(API_SETHOMEDATA_URL, data)

    async def set_dhw_temperature(
        self,
        home_id: str,
        module_id: str,
        temperature: int,
    ) -> dict[str, Any]:
        """Set domestic hot water temperature.

        Args:
            home_id: The home ID.
            module_id: The gateway module ID.
            temperature: The DHW temperature (45-65°C).

        Returns:
            The API response.
        """
        # Based on mitmproxy capture: the API expects home_id at root level
        # and home.modules[].dhw_setpoint_temperature for the value
        data = {
            "home_id": home_id,
            "home": {
                "modules": [
                    {
                        "id": module_id,
                        "dhw_setpoint_temperature": temperature,
                    }
                ],
            },
        }

        _LOGGER.debug("Setting DHW temperature=%s for module %s", temperature, module_id)
        return await self._api_request(API_SETCONFIGS_URL, data)

    async def set_temperature_offset(
        self,
        home_id: str,
        room_id: str,
        offset: float,
    ) -> dict[str, Any]:
        """Set room temperature offset.

        Args:
            home_id: The home ID.
            room_id: The room ID.
            offset: The temperature offset (-5.0 to +5.0°C).

        Returns:
            The API response.
        """
        data = {
            "home": {
                "id": home_id,
                "rooms": [
                    {
                        "id": room_id,
                        "therm_setpoint_offset": offset,
                    }
                ],
            }
        }

        _LOGGER.debug("Setting temperature offset=%s for room %s", offset, room_id)
        return await self._api_request(API_SETCONFIGS_URL, data)

    async def set_manual_setpoint_duration(
        self,
        home_id: str,
        duration: int,
    ) -> dict[str, Any]:
        """Set default duration for manual setpoints.

        Args:
            home_id: The home ID.
            duration: Duration in seconds (300-43200, i.e., 5min to 12h).

        Returns:
            The API response.
        """
        data = {
            "home": {
                "id": home_id,
                "therm_setpoint_default_duration": duration,
            }
        }

        _LOGGER.debug("Setting manual setpoint duration=%s for home %s", duration, home_id)
        return await self._api_request(API_SETHOMEDATA_URL, data)
