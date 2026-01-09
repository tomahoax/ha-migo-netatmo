"""Data coordinator for MiGo (Netatmo) integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MigoApi, MigoApiError
from .const import (
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    KEY_BODY,
    KEY_HOME,
    KEY_HOMES,
    KEY_MODULES,
    KEY_ROOMS,
)
from .helpers import safe_get

if TYPE_CHECKING:
    from . import MigoConfigEntry

_LOGGER = logging.getLogger(__name__)


class MigoDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching MiGO data.

    This coordinator handles fetching data from the MiGO API and provides
    structured access to homes, rooms, and devices data.
    """

    config_entry: MigoConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        api: MigoApi,
        config_entry: MigoConfigEntry,
    ) -> None:
        """Initialize the coordinator.

        Args:
            hass: The Home Assistant instance.
            api: The MiGO API client.
            config_entry: The config entry for this integration.
        """
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_UPDATE_INTERVAL),
        )
        self.api = api
        self.homes: dict[str, Any] = {}
        self.rooms: dict[str, Any] = {}
        self.devices: dict[str, Any] = {}
        # Optimistic cache for config values not returned by API
        self._config_cache: dict[str, Any] = {}

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API.

        This method is called by the coordinator to fetch fresh data.

        Returns:
            Dictionary containing homes, rooms, and devices data.

        Raises:
            UpdateFailed: If there's an error fetching data.
        """
        _LOGGER.debug("Starting MiGO data refresh")

        try:
            data = await self.api.get_homes_data()

            body = safe_get(data, KEY_BODY)
            if body is None:
                _LOGGER.error("Invalid API response: missing 'body' key")
                raise UpdateFailed("Invalid response from API: missing 'body'")

            homes = safe_get(body, KEY_HOMES, default=[])
            _LOGGER.debug("Found %d homes in API response", len(homes))

            # Reset data stores
            self.homes = {}
            self.rooms = {}
            self.devices = {}

            for home in homes:
                await self._process_home(home)

            _LOGGER.debug(
                "MiGO data refresh complete: %d homes, %d rooms, %d devices",
                len(self.homes),
                len(self.rooms),
                len(self.devices),
            )

            return {
                KEY_HOMES: self.homes,
                KEY_ROOMS: self.rooms,
                "devices": self.devices,
            }

        except MigoApiError as err:
            _LOGGER.error("Failed to refresh MiGO data: %s", err)
            raise UpdateFailed(f"Error communicating with API: {err}") from err

    async def _process_home(self, home: dict[str, Any]) -> None:
        """Process a single home and its rooms/modules.

        Args:
            home: The home data from the API.
        """
        home_id = home.get("id")
        if not home_id:
            _LOGGER.debug("Skipping home without ID")
            return

        home_name = home.get("name", "Home")

        # Skip homes without modules (not properly configured)
        modules = home.get(KEY_MODULES, [])
        if not modules:
            _LOGGER.debug("Skipping home %s (%s): no modules found", home_id, home_name)
            return

        rooms = home.get(KEY_ROOMS, [])
        _LOGGER.debug(
            "Processing home %s (%s): %d rooms, %d modules",
            home_id,
            home_name,
            len(rooms),
            len(modules),
        )

        self.homes[home_id] = home

        # Get real-time status for this home
        room_status, module_status = await self._fetch_home_status(home_id)

        # Process rooms
        for room in rooms:
            self._process_room(room, home_id, home_name, room_status)

        # Process modules/devices
        for module in modules:
            self._process_module(module, home_id, module_status)

    async def _fetch_home_status(
        self,
        home_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Fetch real-time status for a home.

        Args:
            home_id: The home ID to fetch status for.

        Returns:
            Tuple of (room_status_dict, module_status_dict).
        """
        room_status: dict[str, Any] = {}
        module_status: dict[str, Any] = {}

        try:
            status = await self.api.get_home_status(home_id)
            home_data = safe_get(status, KEY_BODY, KEY_HOME, default={})

            for room in home_data.get(KEY_ROOMS, []):
                room_id = room.get("id")
                if room_id:
                    room_status[room_id] = room

            for module in home_data.get(KEY_MODULES, []):
                module_id = module.get("id")
                if module_id:
                    module_status[module_id] = module

        except MigoApiError as err:
            _LOGGER.warning("Failed to get status for home %s: %s", home_id, err)

        _LOGGER.debug(
            "Fetched status for home %s: %d rooms, %d modules",
            home_id,
            len(room_status),
            len(module_status),
        )
        return room_status, module_status

    def _process_room(
        self,
        room: dict[str, Any],
        home_id: str,
        home_name: str,
        room_status: dict[str, Any],
    ) -> None:
        """Process a room and merge with status data.

        Args:
            room: The static room configuration.
            home_id: The home ID this room belongs to.
            home_name: The home name for display purposes.
            room_status: Dictionary of room status by room ID.
        """
        room_id = room.get("id")
        if not room_id:
            return

        # Merge static room data with real-time status
        status_data = room_status.get(room_id, {})
        self.rooms[room_id] = {
            **room,
            **status_data,
            "home_id": home_id,
            "home_name": home_name,
        }

    def _process_module(
        self,
        module: dict[str, Any],
        home_id: str,
        module_status: dict[str, Any],
    ) -> None:
        """Process a module and merge with status data.

        Args:
            module: The static module configuration.
            home_id: The home ID this module belongs to.
            module_status: Dictionary of module status by module ID.
        """
        module_id = module.get("id")
        if not module_id:
            return

        # Merge static module data with real-time status
        status_data = module_status.get(module_id, {})
        self.devices[module_id] = {
            **module,
            **status_data,
            "home_id": home_id,
        }

    def get_room(self, room_id: str) -> dict[str, Any] | None:
        """Get room data by ID.

        Args:
            room_id: The room ID to look up.

        Returns:
            The room data dictionary, or None if not found.
        """
        return self.rooms.get(room_id)

    def get_home(self, home_id: str) -> dict[str, Any] | None:
        """Get home data by ID.

        Args:
            home_id: The home ID to look up.

        Returns:
            The home data dictionary, or None if not found.
        """
        return self.homes.get(home_id)

    def get_device(self, device_id: str) -> dict[str, Any] | None:
        """Get device/module data by ID.

        Args:
            device_id: The device ID to look up.

        Returns:
            The device data dictionary, or None if not found.
        """
        return self.devices.get(device_id)

    def get_schedules(self, home_id: str) -> list[dict[str, Any]]:
        """Get schedules for a home.

        Args:
            home_id: The home ID to get schedules for.

        Returns:
            List of schedule dictionaries.
        """
        home = self.get_home(home_id)
        if home is None:
            return []
        return home.get("schedules", [])

    def get_active_schedule(self, home_id: str) -> dict[str, Any] | None:
        """Get the active schedule for a home.

        Args:
            home_id: The home ID to get the active schedule for.

        Returns:
            The active schedule dictionary, or None if not found.
        """
        schedules = self.get_schedules(home_id)
        for schedule in schedules:
            if schedule.get("selected"):
                return schedule
        return None

    def set_cached_value(self, key: str, value: Any) -> None:
        """Store a value in the optimistic cache.

        Used for config values that the API doesn't return after modification.

        Args:
            key: Cache key (e.g., "heating_curve_70:ee:50:6b:e3:6a").
            value: The value to cache.
        """
        self._config_cache[key] = value

    def get_cached_value(self, key: str, default: Any = None) -> Any:
        """Get a value from the optimistic cache.

        Args:
            key: Cache key to look up.
            default: Default value if key not found.

        Returns:
            The cached value, or default if not found.
        """
        return self._config_cache.get(key, default)
