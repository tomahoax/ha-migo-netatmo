"""Data coordinator for MiGo (Netatmo) integration."""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MigoApi, MigoApiError
from .const import (
    CONF_UPDATE_INTERVAL,
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
        # Get update interval from options, fallback to default
        update_interval_seconds = config_entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        _LOGGER.debug("Using update interval: %d seconds", update_interval_seconds)

        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval_seconds),
        )
        self.api = api
        self.homes: dict[str, Any] = {}
        self.rooms: dict[str, Any] = {}
        self.devices: dict[str, Any] = {}
        # Consumption data: device_id (gateway) -> {sum_boiler_on, sum_boiler_off, timestamp}
        self.consumption: dict[str, dict[str, Any]] = {}
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

            # Fetch consumption data for all rooms
            await self._fetch_all_consumption()

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

    async def _fetch_all_consumption(self) -> None:
        """Fetch consumption data using device/module IDs.

        This retrieves sum_boiler_on and sum_boiler_off using the getmeasure endpoint
        with device_id (gateway) and module_id (thermostat) like Vaillant vSmart does.
        Uses 1day scale to get daily totals.

        API response format for getmeasure:
        {
            "body": {
                "1767178800": [sum_boiler_on, sum_boiler_off],
                "1767265200": [sum_boiler_on, sum_boiler_off],
                ...
            }
        }

        Or with list format:
        {
            "body": [
                {
                    "beg_time": 1767178800,
                    "step_time": 86400,
                    "value": [[sum_boiler_on, sum_boiler_off], ...]
                }
            ]
        }
        """
        # Request data for the last 7 days - required by API to return data
        date_begin = int(time.time()) - (7 * 24 * 60 * 60)

        # Find gateway and thermostat pairs
        for device_id, device_data in self.devices.items():
            device_type = device_data.get("type")
            if device_type != "NAVaillant":
                continue

            # Find the thermostat module linked to this gateway
            module_id = None
            home_id = device_data.get("home_id")
            for mod_id, mod_data in self.devices.items():
                if mod_data.get("type") == "NAThermVaillant" and mod_data.get("home_id") == home_id:
                    # Check if this thermostat is linked to the gateway
                    bridge = mod_data.get("bridge")
                    if bridge == device_id:
                        module_id = mod_id
                        break

            if not module_id:
                _LOGGER.debug("No thermostat module found for gateway %s", device_id)
                continue

            try:
                response = await self.api.get_measure(
                    device_id=device_id,
                    module_id=module_id,
                    scale="1day",
                    measure_types=["sum_boiler_on", "sum_boiler_off"],
                    date_begin=date_begin,
                )

                body = safe_get(response, KEY_BODY, default={})
                _LOGGER.debug("Consumption API response body: %s", body)

                # Handle dict format: {"timestamp": [boiler_on, boiler_off], ...}
                if isinstance(body, dict):
                    # Get the most recent (highest timestamp)
                    if body:
                        timestamps = sorted(body.keys(), reverse=True)
                        for ts in timestamps:
                            values = body[ts]
                            if isinstance(values, list) and len(values) >= 2:
                                boiler_on, boiler_off = values
                                if boiler_on is not None:
                                    # Store by device_id for lookup
                                    self.consumption[device_id] = {
                                        "timestamp": int(ts),
                                        "sum_boiler_on": boiler_on,
                                        "sum_boiler_off": boiler_off,
                                    }
                                    _LOGGER.debug(
                                        "Consumption for device %s: boiler_on=%s, boiler_off=%s",
                                        device_id,
                                        boiler_on,
                                        boiler_off,
                                    )
                                    break

                # Handle list format (fallback)
                elif isinstance(body, list) and body:
                    first_entry = body[0]
                    if isinstance(first_entry, dict):
                        values = first_entry.get("value", [])
                        beg_time = first_entry.get("beg_time")
                        step_time = first_entry.get("step_time", 86400)

                        # Find the last non-null value (most recent with data)
                        for i, value in enumerate(reversed(values)):
                            if isinstance(value, list) and len(value) >= 2:
                                boiler_on, boiler_off = value
                                if boiler_on is not None:
                                    timestamp = beg_time + (len(values) - 1 - i) * step_time
                                    self.consumption[device_id] = {
                                        "timestamp": timestamp,
                                        "sum_boiler_on": boiler_on,
                                        "sum_boiler_off": boiler_off,
                                    }
                                    _LOGGER.debug(
                                        "Consumption for device %s: boiler_on=%s, boiler_off=%s",
                                        device_id,
                                        boiler_on,
                                        boiler_off,
                                    )
                                    break

            except MigoApiError as err:
                _LOGGER.debug("Failed to get consumption for device %s: %s", device_id, err)

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

    def get_consumption(self, device_id: str) -> dict[str, Any] | None:
        """Get consumption data for a device (gateway).

        Args:
            device_id: The gateway device ID (MAC address like '70:ee:50:6b:e3:6a').

        Returns:
            The consumption data dictionary containing sum_boiler_on, sum_boiler_off,
            and timestamp, or None if not found.
        """
        return self.consumption.get(device_id)

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
