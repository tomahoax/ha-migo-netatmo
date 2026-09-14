"""API client for MiGo (Netatmo) integration - assembles the mixin pieces."""

from __future__ import annotations

from datetime import datetime

import aiohttp

from ..const import API_TIMEOUT, CLIENT_ID, CLIENT_SECRET, USER_PREFIX
from .auth import AuthMixin
from .endpoints_read import ReadEndpointsMixin
from .endpoints_write import WriteEndpointsMixin
from .transport import TransportMixin


class MigoApi(AuthMixin, TransportMixin, ReadEndpointsMixin, WriteEndpointsMixin):
    """API client for MiGo (Netatmo) thermostat.

    This client handles authentication and communication with the Netatmo API
    used by the MiGO app for Saunier Duval thermostats.

    Assembled from four mixins, one per concern: `AuthMixin` (token
    lifecycle), `TransportMixin` (the shared authenticated-request path),
    `ReadEndpointsMixin` (get_* endpoints) and `WriteEndpointsMixin` (set_*
    endpoints) - see their own modules under `api/`. Session lifecycle
    (`__init__`/`_get_session`/`close`/`clear_credentials`) stays here since
    it belongs to the concrete client, not to any one concern.
    """

    def __init__(
        self,
        username: str,
        password: str,
        session: aiohttp.ClientSession | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        user_prefix: str | None = None,
    ) -> None:
        """Initialize the API client.

        Args:
            username: The MiGO account email address.
            password: The MiGO account password.
            session: Optional aiohttp session to use. If not provided, one will be created.
            client_id: Optional custom OAuth client ID. Uses default if not provided.
            client_secret: Optional custom OAuth client secret. Uses default if not provided.
            user_prefix: Optional custom user prefix. Uses default if not provided.
        """
        self._username = username
        self._password = password
        self._session = session
        self._own_session = session is None
        self._client_id = client_id or CLIENT_ID
        self._client_secret = client_secret or CLIENT_SECRET
        self._user_prefix = user_prefix or USER_PREFIX
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

    def clear_credentials(self) -> None:
        """Forget the password and both tokens.

        Called on unload. Not exploitable, purely hygiene: a memory capture taken
        after a user removes the integration should not still contain live
        credentials. Deliberately not close(): the session belongs to Home
        Assistant, so closing it would be wrong.
        """
        self._password = ""
        self._access_token = None
        self._refresh_token = None
        self._token_expiry = None
