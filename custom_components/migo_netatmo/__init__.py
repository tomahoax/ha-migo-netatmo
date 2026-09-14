"""The MiGO (Saunier Duval) integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MigoApi, MigoApiError, MigoAuthError
from .const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_USER_PREFIX, DEVICE_TYPE_GATEWAY, DOMAIN
from .coordinator import MigoDataUpdateCoordinator
from .helpers import get_devices_by_type

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.DATETIME,
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

    # Register each gateway device up front, before platforms are forwarded.
    # Home Assistant forwards all platforms concurrently
    # (async_forward_entry_setups), so without this a thermostat/room-owning
    # entity's device_info (which links to its parent gateway via
    # _resolve_via_device_id, looking the gateway up in the device registry)
    # could run before any gateway-owning platform has registered the
    # gateway device, silently omitting via_device_id for that session. The
    # gateway platform's own entities still register the full DeviceInfo
    # (name, model, connections, ...) afterwards - the registry merges it
    # into this same device, matched by identifiers.
    device_registry = dr.async_get(hass)
    for gateway_id in get_devices_by_type(coordinator, DEVICE_TYPE_GATEWAY):
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, gateway_id)},
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register update listener for options changes
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload entry when options change."""
    _LOGGER.debug("Reloading MiGO integration due to options change")
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: MigoConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
