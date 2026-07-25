"""The MiGo (Netatmo) integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MigoApi, MigoApiError, MigoAuthError
from .const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_USER_PREFIX, DOMAIN
from .coordinator import MigoDataUpdateCoordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


@dataclass
class MigoData:
    """Runtime data for the MiGO integration."""

    api: MigoApi
    coordinator: MigoDataUpdateCoordinator


MigoConfigEntry = ConfigEntry[MigoData]


async def async_setup_entry(hass: HomeAssistant, entry: MigoConfigEntry) -> bool:
    """Set up MiGO from a config entry."""
    session = async_get_clientsession(hass)

    api = MigoApi(
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        session=session,
        client_id=entry.data.get(CONF_CLIENT_ID),
        client_secret=entry.data.get(CONF_CLIENT_SECRET),
        user_prefix=entry.data.get(CONF_USER_PREFIX),
    )

    try:
        await api.authenticate()
    except MigoAuthError as err:
        raise ConfigEntryAuthFailed(f"Authentication failed: {err}") from err
    except MigoApiError as err:
        raise ConfigEntryNotReady(f"Error connecting to API: {err}") from err

    coordinator = MigoDataUpdateCoordinator(hass, api, entry)

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = MigoData(api=api, coordinator=coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _register_stale_device_removal(hass, entry, coordinator)

    # Options changes reload the entry automatically via OptionsFlowWithReload

    return True


def _register_stale_device_removal(
    hass: HomeAssistant,
    entry: MigoConfigEntry,
    coordinator: MigoDataUpdateCoordinator,
) -> None:
    """Drop devices the API has stopped reporting, on every successful refresh.

    Satisfies the "stale-devices" quality-scale rule the way it prefers: the
    homesdata response is a full snapshot of the account, so a device that
    disappears from it is genuinely gone and can be removed without asking the
    user. async_remove_config_entry_device is kept as well, for the case of a
    device the API still reports but the user no longer wants.

    This lives here rather than in the coordinator on purpose: a coordinator
    should not be mutating the device registry mid-fetch. A listener runs only
    after a refresh the coordinator already considered successful.
    """

    @callback
    def _remove_stale_devices() -> None:
        # Three guards against deleting everything on a bad refresh.
        # _async_update_data clears homes/rooms/devices before repopulating, and
        # an auth failure part-way through aborts into ConfigEntryAuthFailed
        # while leaving the entry loaded with empty stores.
        if not coordinator.last_update_success:
            return
        known_ids = set(coordinator.devices) | set(coordinator.homes)
        if not known_ids:
            return

        device_registry = dr.async_get(hass)
        for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
            if any(domain == DOMAIN and identifier in known_ids for domain, identifier in device.identifiers):
                continue
            _LOGGER.debug(
                "Removing device %s (%s): no longer reported by the API",
                device.name,
                device.identifiers,
            )
            device_registry.async_update_device(device.id, remove_config_entry_id=entry.entry_id)

    # Run once now: the first refresh happened before this listener existed, so
    # devices that vanished while the entry was unloaded would otherwise linger
    # until the next polling cycle.
    _remove_stale_devices()
    entry.async_on_unload(coordinator.async_add_listener(_remove_stale_devices))


async def async_unload_entry(hass: HomeAssistant, entry: MigoConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        # The API object stays reachable through entry.runtime_data after unload,
        # holding a live password and both tokens. Hygiene, not a vulnerability.
        entry.runtime_data.api.clear_credentials()
    return unloaded


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    entry: MigoConfigEntry,
    device_entry: dr.DeviceEntry,
) -> bool:
    """Allow removing a device that the API no longer reports."""
    coordinator = entry.runtime_data.coordinator

    # Refuse while the caches cannot be trusted. _async_update_data clears
    # homes/rooms/devices before repopulating them, and an auth failure part-way
    # through aborts into ConfigEntryAuthFailed while leaving the entry loaded
    # with empty stores. Without this guard, every device looks unreported during
    # a password-expiry window and a user could delete a live one.
    if not coordinator.last_update_success or not (coordinator.devices or coordinator.homes):
        return False

    known_ids = set(coordinator.devices) | set(coordinator.homes)
    return not any(domain == DOMAIN and identifier in known_ids for domain, identifier in device_entry.identifiers)
