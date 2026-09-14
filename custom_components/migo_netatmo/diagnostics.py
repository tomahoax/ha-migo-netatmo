"""Diagnostics support for MiGO (Netatmo)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .redact import redact

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from . import MigoConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: MigoConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    Everything goes through redact(), which shares its key list with the logging
    path (see redact.py). The previous version used Home Assistant's
    async_redact_data with a local TO_REDACT set; the recursion was never the
    problem, that helper handles nested lists and mappings correctly. The problem
    was the key list itself, which had drifted: it was missing invitation_code,
    oem_serial, boiler_id and every home, room and schedule name, and carried two
    keys ("place", "location") that match nothing in the payload and so gave
    false reassurance. Sharing one list with the logs is what stops that
    recurring.

    Device, home, room and module ids are deliberately NOT redacted: a support
    request is unactionable without them, and they identify neither the person
    nor the place.
    """
    coordinator = entry.runtime_data.coordinator

    return {
        "entry": {
            "data": redact(dict(entry.data)),
            "options": dict(entry.options),
        },
        "homes": redact(coordinator.homes),
        "rooms": redact(coordinator.rooms),
        "devices": redact(coordinator.devices),
        "consumption": redact(coordinator.consumption),
    }
