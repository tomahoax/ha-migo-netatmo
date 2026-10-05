"""Low-level HTTP transport, JSON boundary and logging helpers for the API client."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Final

import aiohttp

from ..redact import redact
from .exceptions import MigoApiError, MigoConnectionError

_LOGGER = logging.getLogger(__name__)

# Server error bodies reach a user-facing notification, so they are truncated
# there. The untruncated text still goes to the debug log.
ERROR_BODY_MAX_LENGTH: Final = 200

# Opt-in channel for unredacted payloads. A child logger inherits its parent's
# level, so checking the EFFECTIVE level here would defeat the whole point: it
# would go live the moment anyone debugs the integration normally. Only an
# explicit `custom_components.migo_netatmo.api.raw: debug` in Home Assistant's
# logger configuration sets a level on this logger itself.
#
# Hardcoded rather than derived from __name__: this exact name is documented
# in docs/troubleshooting.md, and must not change just because this code
# lives in api/transport.py rather than a flat api.py.
_RAW_LOGGER = logging.getLogger("custom_components.migo_netatmo.api.raw")


def _raw_logging_enabled() -> bool:
    """Return True only when the raw logger's own level was set explicitly."""
    return _RAW_LOGGER.level == logging.DEBUG


def _log_payload(label: str, payload: Any) -> None:
    """Log an API payload, with sensitive values redacted by default.

    The redacted form keeps the full structure, so it is still useful for
    diagnosing an undocumented backend, but the account email, the home's GPS
    coordinates, the invitation code and hardware serials come out replaced.

    Args:
        label: Human-readable description of what is being logged.
        payload: The request or response payload.
    """
    if _raw_logging_enabled():
        _RAW_LOGGER.debug("%s (raw, unredacted): %s", label, payload)
    elif _LOGGER.isEnabledFor(logging.DEBUG):
        # Guarded: redact() copies the whole payload, and this runs on every
        # poll. No point paying for it when DEBUG is off.
        _LOGGER.debug("%s: %s", label, redact(payload))


def _as_json_object(payload: object) -> dict[str, Any]:
    """Return payload as a JSON object, or raise if it is not one.

    aiohttp's response.json() is typed Any, so without this every caller would
    silently treat a JSON array or scalar as if it were a mapping. This is the
    one place the untrusted wire format becomes a typed value.

    Args:
        payload: The decoded JSON payload.

    Returns:
        The payload, as a JSON object.

    Raises:
        MigoApiError: If the payload is not a JSON object.
    """
    if not isinstance(payload, dict):
        raise MigoApiError(f"Expected a JSON object from the API, got {type(payload).__name__}")
    return payload


def _summarise_error_body(body: str) -> str:
    """Return a short, safe form of a server error body for a user-facing error.

    The full body ends up in a Home Assistant error notification through the
    api_error translation placeholder, which gives an untrusted backend an
    arbitrary-text channel into the frontend, usable for phishing. The complete
    text is still written to the debug log, where it is genuinely useful.

    Args:
        body: The raw response body.

    Returns:
        The body collapsed to one line and truncated.
    """
    collapsed = " ".join(body.split())
    if len(collapsed) <= ERROR_BODY_MAX_LENGTH:
        return collapsed
    return collapsed[:ERROR_BODY_MAX_LENGTH] + "..."


class TransportMixin:
    """Mixin providing the shared authenticated-request path.

    Combined into `MigoApi` alongside `AuthMixin` (token lifecycle) and the
    read/write endpoint mixins - see `api/client.py`. The attributes and
    methods declared under TYPE_CHECKING below are provided by the other
    mixins/`MigoApi.__init__` once assembled; declared here only so this
    mixin type-checks on its own.
    """

    if TYPE_CHECKING:
        _access_token: str | None
        _timeout: aiohttp.ClientTimeout

        async def _get_session(self) -> aiohttp.ClientSession: ...
        async def _ensure_token_valid(self) -> None: ...
        async def authenticate(self) -> bool: ...

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
            _log_payload("API request payload", data)

        try:
            async with session.request(method, url, timeout=self._timeout, **request_kwargs) as response:
                # Log response status
                _LOGGER.debug("API response: %s status=%d", url, response.status)

                if response.status == 401:
                    # Token expired, refresh and retry once
                    _LOGGER.debug("Got 401, refreshing token and retrying")
                    await self.authenticate()
                    request_kwargs["headers"] = self._build_api_headers(use_json)

                    async with session.request(method, url, timeout=self._timeout, **request_kwargs) as retry_response:
                        _LOGGER.debug(
                            "API retry response: %s status=%d",
                            url,
                            retry_response.status,
                        )
                        if retry_response.status >= 400:
                            error_text = await retry_response.text()
                            _LOGGER.debug(
                                "API error after retry: %s %s returned %d: %s",
                                method,
                                url,
                                retry_response.status,
                                error_text,
                            )
                            raise MigoApiError(
                                f"API returned {retry_response.status}: {_summarise_error_body(error_text)}"
                            )
                        result = _as_json_object(await retry_response.json())
                        _log_payload("API response data", result)
                        return result

                if response.status >= 400:
                    error_text = await response.text()
                    _LOGGER.debug(
                        "API error: %s %s returned %d: %s",
                        method,
                        url,
                        response.status,
                        error_text,
                    )
                    raise MigoApiError(f"API returned {response.status}: {_summarise_error_body(error_text)}")

                result = _as_json_object(await response.json())
                _log_payload("API response data", result)
                return result

        except aiohttp.ClientResponseError as err:
            _LOGGER.debug(
                "API request failed: %s %s - status=%d message=%s",
                method,
                url,
                err.status,
                err.message,
            )
            raise MigoApiError(f"API request failed: {err}") from err
        except aiohttp.ClientError as err:
            _LOGGER.debug("API connection error: %s %s - %s", method, url, err)
            raise MigoConnectionError(f"Connection error: {err}") from err
