"""Device-info builders for MiGO entities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo

from .const import DEVICE_TYPE_GATEWAY, DEVICE_TYPE_THERMOSTAT, DOMAIN, MANUFACTURER

if TYPE_CHECKING:
    from .coordinator import MigoDataUpdateCoordinator


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
) -> DeviceInfo:
    """Build the DeviceInfo for a thermostat (NAThermVaillant) device.

    Single source of truth: every entity attached to the thermostat
    device must produce exactly this structure.

    Links to the parent gateway via `via_device` (an `(DOMAIN, identifier)`
    tuple, resolved to the registry's internal ID by Home Assistant itself
    inside `DeviceRegistry.async_get_or_create`). A prior version of this
    function instead pre-resolved that internal ID itself and passed it via
    a `via_device_id` DeviceInfo key, believing `via_device` to be
    deprecated and at risk of raising instead of warning under some caller
    attributions. Neither belief survived contact with a real Home
    Assistant install: `via_device_id` is not a real `DeviceInfo` key in
    any released version - confirmed live, CI failing with `TypeError:
    DeviceRegistry.async_get_or_create() got an unexpected keyword argument
    'via_device_id'. Did you mean 'via_device'?` on every entity using it,
    which is to say every thermostat-attached entity, on every setup - and
    `via_device` itself carries no deprecation notice at all in the same
    real, currently-supported Home Assistant versions. Reverted.
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
