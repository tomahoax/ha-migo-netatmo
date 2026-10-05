"""Token lifecycle (authenticate/refresh/store/ensure-valid) for the API client."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast

import aiohttp

from ..const import (
    API_AUTH_URL,
    GRANT_TYPE_PASSWORD,
    GRANT_TYPE_REFRESH,
    SCOPE,
    TOKEN_EXPIRY_BUFFER,
)
from ..models import TokenResponse
from ..redact import mask_email
from .exceptions import MigoAuthError, MigoConnectionError
from .transport import _as_json_object

_LOGGER = logging.getLogger(__name__)


class AuthMixin:
    """Mixin providing authentication and token lifecycle management.

    Combined into `MigoApi` alongside `TransportMixin` and the read/write
    endpoint mixins - see `api/client.py`. `_get_session`/`_timeout` are
    provided by `MigoApi.__init__` itself; declared here only so this mixin
    type-checks on its own.
    """

    if TYPE_CHECKING:
        _access_token: str | None
        _refresh_token: str | None
        _token_expiry: datetime | None
        _client_id: str
        _client_secret: str
        _user_prefix: str
        _username: str
        _password: str
        _timeout: aiohttp.ClientTimeout

        async def _get_session(self) -> aiohttp.ClientSession: ...

    def _build_auth_headers(self) -> dict[str, str]:
        """Build headers for form-urlencoded auth requests.

        Returns:
            Dictionary of HTTP headers.
        """
        return {
            "Content-Type": "application/x-www-form-urlencoded",
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
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "grant_type": GRANT_TYPE_PASSWORD,
            "username": self._username,
            "password": self._password,
            "user_prefix": self._user_prefix,
            "scope": SCOPE,
        }

        # Masked: the username is the account email, which is also the login.
        _LOGGER.debug("Authenticating with Netatmo API for user: %s", mask_email(self._username))

        try:
            async with session.post(
                API_AUTH_URL,
                data=data,
                headers=self._build_auth_headers(),
                timeout=self._timeout,
            ) as response:
                if response.status == 400:
                    error_data = await response.json()
                    error_msg = error_data.get("error", "Authentication failed")
                    _LOGGER.error("Authentication failed: %s", error_msg)
                    raise MigoAuthError(error_msg)

                if response.status != 200:
                    _LOGGER.error("Authentication failed with status: %d", response.status)
                    raise MigoAuthError(f"Authentication failed: HTTP {response.status}")

                # _as_json_object checks it really is an object; the cast then
                # asserts the field shape, same as the other JSON boundaries.
                result = cast(TokenResponse, _as_json_object(await response.json()))
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
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "grant_type": GRANT_TYPE_REFRESH,
            "refresh_token": self._refresh_token,
        }

        _LOGGER.debug("Refreshing access token")

        try:
            async with session.post(
                API_AUTH_URL,
                data=data,
                headers=self._build_auth_headers(),
                timeout=self._timeout,
            ) as response:
                if response.status != 200:
                    _LOGGER.warning(
                        "Token refresh failed (status %d), re-authenticating",
                        response.status,
                    )
                    return await self.authenticate()

                result = cast(TokenResponse, _as_json_object(await response.json()))
                self._store_tokens(result, preserve_refresh=True)

                _LOGGER.debug("Token refreshed successfully")
                return True

        except aiohttp.ClientError as err:
            _LOGGER.warning("Error refreshing token: %s, re-authenticating", err)
            return await self.authenticate()

    def _store_tokens(
        self,
        token_data: TokenResponse,
        preserve_refresh: bool = False,
    ) -> None:
        """Store tokens from API response.

        Args:
            token_data: The token response from the API.
            preserve_refresh: If True, preserve existing refresh token if not in response.

        Raises:
            MigoAuthError: If the response carries no access token.
        """
        access_token = token_data.get("access_token")
        if access_token is None:
            # Previously a bare KeyError, which escaped authenticate() as-is
            # instead of surfacing as an auth failure.
            raise MigoAuthError("Authentication response carried no access token")
        self._access_token = access_token

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
