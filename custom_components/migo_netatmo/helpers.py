"""Helper utilities for MiGo (Netatmo) integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, TypeVar

from .const import DEVICE_TYPE_GATEWAY, DEVICE_TYPE_THERMOSTAT, KEY_BODY

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
