"""Exception hierarchy for the MiGO API client."""

from __future__ import annotations


class MigoApiError(Exception):
    """Base exception for MiGO API errors."""


class MigoAuthError(MigoApiError):
    """Authentication error."""


class MigoConnectionError(MigoApiError):
    """Connection error."""
