"""API client package for MiGo (Netatmo) integration.

Split by concern rather than one flat module: `exceptions.py` (the error
hierarchy), `transport.py` (the shared authenticated-request path, JSON
boundary and logging helpers), `auth.py` (token lifecycle), `endpoints_read.py`
/`endpoints_write.py` (the get_*/set_* API calls), and `client.py` (the
concrete `MigoApi` class assembling all of the above). Only `MigoApi` and the
exception classes are re-exported here - that is the integration's real public
surface; every other module in this package imports the internals it needs
directly from their own submodule.
"""

from __future__ import annotations

from .client import MigoApi
from .exceptions import MigoApiError, MigoAuthError, MigoConnectionError

__all__ = [
    "MigoApi",
    "MigoApiError",
    "MigoAuthError",
    "MigoConnectionError",
]
