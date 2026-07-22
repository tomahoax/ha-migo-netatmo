"""Diagnostics support for MiGO (Netatmo)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from . import MigoConfigEntry

# Credentials and anything that can locate the user's home.
# MACs and device/home IDs are kept: they are needed for support.
TO_REDACT = {
    "username",
    "password",
    "client_id",
    "client_secret",
    "user_prefix",
    "coordinates",
    "place",
    "city",
    "country",
    "altitude",
    "timezone",
    "location",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: MigoConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data.coordinator

    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "homes": async_redact_data(coordinator.homes, TO_REDACT),
        "rooms": async_redact_data(coordinator.rooms, TO_REDACT),
        "devices": async_redact_data(coordinator.devices, TO_REDACT),
        "consumption": coordinator.consumption,
    }
