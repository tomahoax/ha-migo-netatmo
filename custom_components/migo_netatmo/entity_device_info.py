"""Device-info builders and device-registry helpers for MiGO entities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo

from .const import DEVICE_TYPE_GATEWAY, DEVICE_TYPE_THERMOSTAT, DOMAIN, MANUFACTURER

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import MigoDataUpdateCoordinator


def _resolve_via_device_id(
    hass: HomeAssistant | None,
    config_entry_id: str | None,
    gateway_id: str,
) -> str | None:
    """Resolve a gateway's registry-internal device_id, for `via_device_id`.

    `via_device_id` (the replacement for the deprecated `via_device`
    identifiers-tuple form) needs the device registry's own internal ID, not
    the `(DOMAIN, identifier)` tuple used everywhere else in this
    integration - this looks it up by the same identifier the gateway's own
    `DeviceInfo` registers under (`identifiers={(DOMAIN, gateway_id)}`, see
    `build_gateway_device_info`), scoped to this entity's own config entry
    via `async_get_device_by_identifier` - `async_get_device` is itself
    deprecated (identifiers are no longer guaranteed unique across config
    entries) and, like `via_device` before it, only warns *unless* Home
    Assistant happens to attribute the call to a core integration instead of
    this custom one, in which case it raises - the exact mechanism that
    broke entity setup live once already (see the CHANGELOG entry this
    helper was introduced for). Returns None if `hass` or `config_entry_id`
    isn't set yet (an entity's `device_info` can in principle be read before
    it's fully added to a platform) or the gateway device hasn't been
    registered yet - in either case, the caller should fall back to the
    deprecated `via_device` tuple rather than raise, since a device with no
    parent is still a valid device.
    """
    if hass is None or config_entry_id is None:
        return None
    device = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, gateway_id), config_entry_id)
    return device.id if device else None


def _entity_config_entry_id(entity: object) -> str | None:
    """Return the config entry ID an entity was added under, if it has one yet.

    `Entity.platform` is set (alongside `Entity.hass`) by
    `add_to_platform_start`, before `device_info` is ever read - see
    `entity_platform.py`'s `_async_add_entity`. Guarded defensively anyway,
    since nothing stops `device_info` being read earlier in principle (as
    every device_info test in this file does, none of which set `hass` or
    `platform` at all).
    """
    platform = getattr(entity, "platform", None)
    config_entry = getattr(platform, "config_entry", None) if platform is not None else None
    return config_entry.entry_id if config_entry is not None else None


def _home_name(coordinator: MigoDataUpdateCoordinator, home_id: str) -> str:
    """Return the display name of a home."""
    return coordinator.homes.get(home_id, {}).get("name", "MiGO")


def _looks_like_mac(device_id: str) -> bool:
    """Return True if device_id has the shape of a MAC address.

    Device ids come straight from the API and are not validated by it. Home
    Assistant merges device registry entries that share a connection tuple, so
    registering an arbitrary string as a CONNECTION_NETWORK_MAC lets a wrong or
    hostile value attach these entities to an unrelated device in the user's home
    and overwrite its displayed name, manufacturer and model.

    Args:
        device_id: The identifier reported by the API.

    Returns:
        True for the aa:bb:cc:dd:ee:ff shape only.
    """
    parts = device_id.split(":")
    return len(parts) == 6 and all(len(p) == 2 and all(c in "0123456789abcdefABCDEF" for c in p) for p in parts)


def build_gateway_device_info(
    coordinator: MigoDataUpdateCoordinator,
    gateway_id: str,
    home_id: str,
) -> DeviceInfo:
    """Build the DeviceInfo for a gateway (NAVaillant) device.

    Single source of truth: every entity attached to the gateway device
    must produce exactly this structure.
    """
    device_data = coordinator.devices.get(gateway_id, {})
    info = DeviceInfo(
        identifiers={(DOMAIN, gateway_id)},
        name=f"{_home_name(coordinator, home_id)} Gateway",
        manufacturer=MANUFACTURER,
        model=DEVICE_TYPE_GATEWAY,
    )
    # Only when it really is a MAC. The thermostat builder below always checked;
    # this one did not, and registered whatever the API returned.
    if _looks_like_mac(gateway_id):
        info["connections"] = {(CONNECTION_NETWORK_MAC, gateway_id)}
    if firmware := device_data.get("firmware_revision"):
        info["sw_version"] = str(firmware)
    if hw_version := device_data.get("hardware_version"):
        info["hw_version"] = str(hw_version)
    if serial := device_data.get("oem_serial"):
        info["serial_number"] = serial
    return info


def build_thermostat_device_info(
    coordinator: MigoDataUpdateCoordinator,
    thermostat_id: str,
    home_id: str,
    *,
    hass: HomeAssistant | None = None,
    config_entry_id: str | None = None,
) -> DeviceInfo:
    """Build the DeviceInfo for a thermostat (NAThermVaillant) device.

    Single source of truth: every entity attached to the thermostat
    device must produce exactly this structure.

    `hass`/`config_entry_id`, when given, resolve the parent gateway link
    via the non-deprecated `via_device_id` (see `_resolve_via_device_id`)
    instead of the deprecated `via_device` identifiers-tuple form. Callers
    pass their own `self.hass`/`_entity_config_entry_id(self)`; omitting
    them (or the registry lookup coming up empty, e.g. before the gateway
    device is registered) falls back to `via_device` so the link still
    exists, just via the deprecated form until a later call resolves it.
    """
    device_data = coordinator.devices.get(thermostat_id, {})
    info = DeviceInfo(
        identifiers={(DOMAIN, thermostat_id)},
        name=f"{_home_name(coordinator, home_id)} Thermostat",
        manufacturer=MANUFACTURER,
        model=DEVICE_TYPE_THERMOSTAT,
    )

    # Add MAC address connection if the device_id looks like a MAC address
    if _looks_like_mac(thermostat_id):
        info["connections"] = {(CONNECTION_NETWORK_MAC, thermostat_id)}

    # Link to the parent gateway device.
    if gateway_id := device_data.get("bridge"):
        via_device_id = _resolve_via_device_id(hass, config_entry_id, gateway_id)
        if via_device_id is not None:
            info["via_device_id"] = via_device_id
        else:
            info["via_device"] = (DOMAIN, gateway_id)

    if firmware := device_data.get("firmware_revision"):
        info["sw_version"] = str(firmware)
    return info


def build_home_fallback_device_info(
    coordinator: MigoDataUpdateCoordinator,
    home_id: str,
) -> DeviceInfo:
    """Build the last-resort DeviceInfo when no physical device is known."""
    return DeviceInfo(
        identifiers={(DOMAIN, home_id)},
        name=_home_name(coordinator, home_id),
        manufacturer=MANUFACTURER,
    )
