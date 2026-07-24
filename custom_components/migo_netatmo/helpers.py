"""Helper utilities for MiGo (Netatmo) integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, overload

from homeassistant.exceptions import HomeAssistantError

from .const import DEVICE_TYPE_GATEWAY, DEVICE_TYPE_THERMOSTAT, DOMAIN
from .models import ModuleData, RoomData

if TYPE_CHECKING:
    from .coordinator import MigoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


@overload
def safe_get(data: Mapping[str, Any] | None, *keys: str) -> Any | None: ...
@overload
def safe_get[T](data: Mapping[str, Any] | None, *keys: str, default: T) -> Any | T: ...
def safe_get(data: Mapping[str, Any] | None, *keys: str, default: Any = None) -> Any:
    """Safely get a nested value from a dictionary or mapping (e.g. a TypedDict).

    Args:
        data: The mapping to get the value from.
        *keys: The keys to traverse.
        default: The default value if any key is missing.

    Returns:
        The value at the nested key path, or the default. When a non-None
        default is passed, the return type is narrowed accordingly (see
        overloads above) so callers don't need to re-check for None.

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
) -> dict[str, ModuleData]:
    """Filter coordinator devices by type.

    Args:
        coordinator: The data update coordinator.
        device_type: The device type to filter by (e.g., "NATherm1", "NAPlug").

    Returns:
        Dictionary of device_id -> device_data for matching devices.
    """
    return {device_id: data for device_id, data in coordinator.devices.items() if data.get("type") == device_type}


def get_home_id_or_raise(
    data: RoomData | ModuleData,
    entity_type: str,
    entity_id: str,
) -> str:
    """Get home_id from data dict, raising a UI-visible error if not found.

    Args:
        data: The data dictionary (room_data or device_data).
        entity_type: The type of entity for the error message (e.g., "room", "device").
        entity_id: The entity ID for the error message.

    Returns:
        The home_id.

    Raises:
        HomeAssistantError: If no home_id is associated with the entity.
    """
    home_id = data.get("home_id")
    if not home_id:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="missing_home_id",
            translation_placeholders={"entity_type": entity_type, "entity_id": entity_id},
        )
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
