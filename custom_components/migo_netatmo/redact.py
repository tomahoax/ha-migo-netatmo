"""Redaction of sensitive values, shared by logging and diagnostics.

This module is the single source of truth for what counts as sensitive. It
exists because the list used to live only in diagnostics.py, while api.py and
coordinator.py logged whole API responses with no filtering at all. The two
drifted, and the result was an account email, GPS coordinates to six decimal
places and a home invitation code written thousands of times into a debug log.

Anything that dumps server data, whether to a log or to a diagnostics download,
must go through `redact()`. Add new keys here and both paths are covered.
"""

from __future__ import annotations

from typing import Any, Final

REDACTED: Final = "**REDACTED**"

# Keys whose VALUE must never appear in a log or a diagnostics download.
#
# Deliberately absent: "id", "home_id", "device_id", "module_id", "room_id",
# "bridge", "type". They are needed to make a support request actionable and
# they identify nothing about the person or the place.
SENSITIVE_KEYS: Final = frozenset(
    {
        # Credentials
        "username",
        "password",
        "client_id",
        "client_secret",
        "user_prefix",
        "access_token",
        "refresh_token",
        # Account identity. The email is also the login.
        "email",
        "mail",
        # Anything that locates the home. "coordinates" is a lat/lon pair at
        # six decimal places, which resolves to a specific building.
        "coordinates",
        "city",
        "country",
        "altitude",
        "timezone",
        "place",
        "location",
        # A capability, not just an identifier: an invitation code lets another
        # account join the home. Treat it like a credential.
        "invitation_code",
        # Hardware identifiers, usable for warranty or support-desk pretexting.
        "oem_serial",
        "boiler_id",
        # Home, room, schedule and zone names are routinely a family name or a
        # street name. Redacting them costs readability in diagnostics, which is
        # why the technical ids above are kept in exchange.
        "name",
        "home_name",
    }
)


def mask_email(email: str) -> str:
    """Return an email with the local part masked, keeping it distinguishable.

    Used where a log line needs to say WHICH account it is talking about, for an
    install with more than one config entry, without writing the address that is
    also the account's login.

    Args:
        email: The address to mask. Anything without an "@" is masked whole.

    Returns:
        For example "a***@example.com".
    """
    if not email:
        return REDACTED
    local, _, domain = email.partition("@")
    if not domain:
        return REDACTED
    return f"{local[:1]}***@{domain}"


def redact(value: Any) -> Any:
    """Return a copy of value with every sensitive value replaced.

    Behaves like Home Assistant's `async_redact_data`, which is also fully
    recursive over mappings and lists. It is reimplemented here for one reason
    only: `async_redact_data` lives in `homeassistant.components.diagnostics`,
    and importing a component from `api.py` would make the API client depend on
    the diagnostics platform just to write a log line. This keeps the logging
    path dependency-free while both paths share SENSITIVE_KEYS above, which is
    the part that actually matters.

    One deliberate behavioural difference: this redacts a sensitive key even when
    its value is None or an empty string, where `async_redact_data` leaves those
    untouched. Uniformity is easier to reason about when auditing output.

    Args:
        value: Any decoded JSON value, or a coordinator data structure.

    Returns:
        A redacted copy. The input is never mutated.
    """
    if isinstance(value, dict):
        return {k: REDACTED if k in SENSITIVE_KEYS else redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    return value
