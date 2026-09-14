"""Helper utilities for MiGo (Netatmo) integration."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime
from typing import TYPE_CHECKING, Any, TypeVar

from homeassistant.util import dt as dt_util

from .const import (
    BOILER_MODE_DHW_ONLY,
    BOILER_MODE_FROST_GUARD,
    BOILER_MODE_NORMAL,
    DEVICE_TYPE_GATEWAY,
    DEVICE_TYPE_THERMOSTAT,
    KEY_BODY,
    MODE_FROST_GUARD,
    SCHEDULE_TYPE_EVENT,
    SCHEDULE_TYPE_THERM,
)

if TYPE_CHECKING:
    from .coordinator import MigoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


def safe_get(data: dict[str, Any] | None, *keys: str, default: T | None = None) -> Any | T | None:
    """Safely get a nested value from a dictionary.

    Args:
        data: The dictionary to get the value from.
        *keys: The keys to traverse.
        default: The default value if any key is missing.

    Returns:
        The value at the nested key path, or the default.

    Example:
        >>> data = {"body": {"home": {"id": "123"}}}
        >>> safe_get(data, "body", "home", "id")
        '123'
        >>> safe_get(data, "body", "missing", "key", default="N/A")
        'N/A'
    """
    if data is None:
        return default

    result: Any = data
    for key in keys:
        if isinstance(result, dict):
            result = result.get(key)
            if result is None:
                return default
        else:
            return default
    return result


def parse_api_response(response: dict[str, Any], required_key: str | None = None) -> dict[str, Any]:
    """Parse and validate an API response.

    Args:
        response: The raw API response.
        required_key: An optional key that must exist in the body.

    Returns:
        The body of the response.

    Raises:
        ValueError: If the response is invalid or missing required data.
    """
    if not isinstance(response, dict):
        raise ValueError(f"Invalid response type: {type(response)}")

    body = response.get(KEY_BODY)
    if body is None:
        raise ValueError("Response missing 'body' key")

    if required_key is not None and required_key not in body:
        raise ValueError(f"Response body missing required key: {required_key}")

    return body


def safe_float(value: Any, default: float | None = None) -> float | None:
    """Safely convert a value to float.

    Args:
        value: The value to convert.
        default: The default value if conversion fails.

    Returns:
        The float value or the default.
    """
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        _LOGGER.debug("Failed to convert %r to float", value)
        return default


def safe_int(value: Any, default: int | None = None) -> int | None:
    """Safely convert a value to int.

    Args:
        value: The value to convert.
        default: The default value if conversion fails.

    Returns:
        The int value or the default.
    """
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        _LOGGER.debug("Failed to convert %r to int", value)
        return default


def format_mac_address(mac: str) -> str:
    """Format a MAC address for display.

    Args:
        mac: The MAC address string.

    Returns:
        The formatted MAC address (uppercase with colons).
    """
    # Remove any existing separators and convert to uppercase
    clean = mac.replace(":", "").replace("-", "").upper()
    # Add colons every 2 characters
    return ":".join(clean[i : i + 2] for i in range(0, len(clean), 2))


def get_device_name(device_data: dict[str, Any], device_type: str) -> str:
    """Generate a human-readable device name.

    Args:
        device_data: The device data dictionary.
        device_type: The type of device (for display).

    Returns:
        A formatted device name.
    """
    device_id = device_data.get("id", "Unknown")
    # Use last 4 characters of ID for uniqueness
    short_id = device_id[-4:] if len(device_id) >= 4 else device_id
    return f"{device_type} {short_id}"


def calculate_signal_quality(strength: int | None, thresholds: tuple[int, int, int]) -> str | None:
    """Calculate signal quality from strength value.

    Args:
        strength: The signal strength value.
        thresholds: Tuple of (excellent, good, fair) thresholds.

    Returns:
        Signal quality string: "excellent", "good", "fair", or "poor".
    """
    if strength is None:
        return None

    excellent, good, fair = thresholds

    if strength >= excellent:
        return "excellent"
    if strength >= good:
        return "good"
    if strength >= fair:
        return "fair"
    return "poor"


def generate_unique_id(entity_type: str, entity_id: str) -> str:
    """Generate a consistent unique ID for entities.

    Args:
        entity_type: The type of entity (e.g., "temp", "humidity", "battery").
        entity_id: The entity's identifier (room_id, device_id, etc.).

    Returns:
        A unique ID string in the format "migo_netatmo_{type}_{id}".
    """
    return f"migo_netatmo_{entity_type}_{entity_id}"


def get_devices_by_type(
    coordinator: MigoDataUpdateCoordinator,
    device_type: str,
) -> dict[str, Any]:
    """Filter coordinator devices by type.

    Args:
        coordinator: The data update coordinator.
        device_type: The device type to filter by (e.g., "NATherm1", "NAPlug").

    Returns:
        Dictionary of device_id -> device_data for matching devices.
    """
    return {device_id: data for device_id, data in coordinator.devices.items() if data.get("type") == device_type}


def get_home_id_or_log_error(
    data: dict[str, Any],
    entity_type: str,
    entity_id: str,
) -> str | None:
    """Get home_id from data dict, logging an error if not found.

    Args:
        data: The data dictionary (room_data or device_data).
        entity_type: The type of entity for the error message (e.g., "room", "device").
        entity_id: The entity ID for the error message.

    Returns:
        The home_id if found, None otherwise (with error logged).
    """
    home_id = data.get("home_id")
    if not home_id:
        _LOGGER.error("No home_id found for %s %s", entity_type, entity_id)
        return None
    return home_id


def get_gateway_mac_for_home(
    coordinator: MigoDataUpdateCoordinator,
    home_id: str,
) -> str | None:
    """Get the gateway MAC address for a home.

    Args:
        coordinator: The data update coordinator.
        home_id: The home ID to find the gateway for.

    Returns:
        The gateway MAC address, or None if not found.
    """
    for device_id, device_data in coordinator.devices.items():
        if device_data.get("type") == DEVICE_TYPE_GATEWAY and device_data.get("home_id") == home_id:
            return device_id
    return None


def get_thermostat_for_room(
    coordinator: MigoDataUpdateCoordinator,
    room_id: str,
) -> str | None:
    """Get the thermostat device ID for a room.

    Args:
        coordinator: The data update coordinator.
        room_id: The room ID to find the thermostat for.

    Returns:
        The thermostat device ID, or None if not found.
    """
    room_data = coordinator.rooms.get(room_id, {})
    module_ids = room_data.get("module_ids", [])

    for module_id in module_ids:
        device_data = coordinator.devices.get(module_id, {})
        if device_data.get("type") == DEVICE_TYPE_THERMOSTAT:
            return module_id
    return None


# =============================================================================
# Boiler mode derivation
# =============================================================================


def derive_boiler_mode(
    therm_mode: str | None,
    room_setpoint_modes: Iterable[str | None],
) -> str:
    """Derive the home-level boiler quick-action mode.

    MiGo's "Actions rapides" (Normal / DHW only / Frost guard) are not
    returned as a single field by homesdata/homestatus. They can be derived
    from the home's `therm_mode` and the rooms' `therm_setpoint_mode`:
    frost guard is `therm_mode == "hg"`; DHW-only shows up as a room in
    `therm_setpoint_mode == "hg"` while the home itself is not; anything
    else is normal heating. This is independent of the Away preset
    (`therm_mode == "away"`), which is an orthogonal setting.

    Args:
        therm_mode: The home's `therm_mode` field.
        room_setpoint_modes: The `therm_setpoint_mode` of each room in the home.

    Returns:
        One of BOILER_MODE_NORMAL, BOILER_MODE_DHW_ONLY, BOILER_MODE_FROST_GUARD.
    """
    if therm_mode == MODE_FROST_GUARD:
        return BOILER_MODE_FROST_GUARD
    if MODE_FROST_GUARD in room_setpoint_modes:
        return BOILER_MODE_DHW_ONLY
    return BOILER_MODE_NORMAL


# =============================================================================
# Timetable resolution (DHW / event schedules)
# =============================================================================


def current_week_minutes(now: datetime | None = None) -> int:
    """Return minutes elapsed since Monday 00:00 in the local timezone.

    Args:
        now: Optional reference time, mainly for tests. Defaults to the
            current local time in Home Assistant's configured timezone.

    Returns:
        Minutes since Monday 00:00:00, in the range [0, 10080).
    """
    if now is None:
        now = dt_util.now()
    return now.weekday() * 1440 + now.hour * 60 + now.minute


def resolve_timetable_zone(
    timetable: list[dict[str, Any]],
    week_minutes: int,
) -> int | None:
    """Resolve the active zone_id for a timetable at a given point in the week.

    The API does not guarantee `timetable` is sorted by `m_offset`, so this
    sorts it first. Picks the last entry whose offset is not in the future,
    wrapping around to the last entry of the week when `week_minutes`
    precedes the first offset (e.g. early Monday morning, before the first
    slot of the week starts).

    Args:
        timetable: List of {"zone_id": int, "m_offset": int} entries.
        week_minutes: Minutes since Monday 00:00 to resolve against.

    Returns:
        The zone_id of the active entry, or None if the timetable is empty.
    """
    if not timetable:
        return None

    sorted_entries = sorted(timetable, key=lambda entry: entry.get("m_offset", 0))

    active = None
    for entry in sorted_entries:
        if entry.get("m_offset", 0) <= week_minutes:
            active = entry
        else:
            break

    if active is None:
        # week_minutes precedes the first offset of the week: the active
        # slot is whichever one started last, i.e. the last entry.
        active = sorted_entries[-1]

    return active.get("zone_id")


def _linked_event_schedule_id(linked_schedules: Any, therm_schedule_id: str) -> str | None:
    """Best-effort lookup of the event schedule id linked to a therm schedule id.

    The exact shape of `linked_schedules` in the homesdata response is not
    documented by Netatmo. This defensively handles the shapes plausible for
    an id-pairing structure: a mapping of {id: id} (either direction), or a
    list of pairs (as a dict of arbitrary key names, or a 2-tuple/list).

    Args:
        linked_schedules: The raw `linked_schedules` value from a home.
        therm_schedule_id: The id of the selected therm schedule.

    Returns:
        The paired event schedule id, or None if it cannot be resolved.
    """
    if isinstance(linked_schedules, dict):
        if therm_schedule_id in linked_schedules:
            return linked_schedules[therm_schedule_id]
        for key, value in linked_schedules.items():
            if value == therm_schedule_id:
                return key
        return None

    if isinstance(linked_schedules, list):
        for entry in linked_schedules:
            ids: list[Any] = []
            if isinstance(entry, dict):
                ids = list(entry.values())
            elif isinstance(entry, (list, tuple)):
                ids = list(entry)
            if therm_schedule_id in ids:
                others = [i for i in ids if i != therm_schedule_id]
                if others:
                    return others[0]

    return None


def get_event_schedule(home: dict[str, Any]) -> dict[str, Any] | None:
    """Return the DHW (event) schedule paired with the active heating schedule.

    Prefers the explicit `linked_schedules` pairing when present and
    resolvable, falling back to the event schedule that is independently
    marked `selected` (the app selects a therm and an event schedule in
    parallel, under the same name).

    Args:
        home: A home configuration dict (as stored in coordinator.homes).

    Returns:
        The event schedule dict, or None if none can be resolved.
    """
    schedules = home.get("schedules", [])
    therm_schedules = [s for s in schedules if s.get("type") == SCHEDULE_TYPE_THERM]
    event_schedules = [s for s in schedules if s.get("type") == SCHEDULE_TYPE_EVENT]

    selected_therm = next((s for s in therm_schedules if s.get("selected")), None)
    linked_schedules = home.get("linked_schedules")

    if selected_therm is not None and linked_schedules:
        linked_id = _linked_event_schedule_id(linked_schedules, selected_therm.get("id"))
        if linked_id is not None:
            for schedule in event_schedules:
                if schedule.get("id") == linked_id:
                    return schedule

    # Fallback: the event schedule independently marked selected.
    return next((s for s in event_schedules if s.get("selected")), None)
