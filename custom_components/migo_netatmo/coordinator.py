"""Data coordinator for MiGo (Netatmo) integration."""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from datetime import timedelta
from typing import TYPE_CHECKING, Any, override

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MigoApi, MigoApiError, MigoAuthError
from .const import (
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    KEY_BODY,
    KEY_HOME,
    KEY_HOMES,
    KEY_MODULES,
    KEY_ROOMS,
    MEASURE_TYPES,
)
from .models import (
    ConsumptionData,
    CoordinatorData,
    HomeConfig,
    ModuleConfig,
    ModuleConfigData,
    ModuleData,
    ModuleStatus,
    RoomConfig,
    RoomData,
    RoomStatus,
)
from .redact import redact

if TYPE_CHECKING:
    from . import MigoConfigEntry

_LOGGER = logging.getLogger(__name__)


def _consumption_record(values: Sequence[Any], timestamp: int) -> ConsumptionData:
    """Map one getmeasure value row onto a ConsumptionData record.

    getmeasure returns one value per requested measure type, positionally, so
    const.MEASURE_TYPES is the schema and the indices below must stay in step with
    it. tests/test_consumption_measures.py pins that.

    Written with literal keys rather than zip(MEASURE_TYPES, values) so the
    TypedDict stays statically checkable, and length-guarded in pairs rather than
    unpacked so a boiler that reports only the two boiler-time measures yields a
    shorter record instead of an IndexError.

    Args:
        values: One row from the response, in MEASURE_TYPES order.
        timestamp: Unix timestamp this row covers.

    Returns:
        The record, carrying only the fields the row actually provided.
    """
    record: ConsumptionData = {"timestamp": timestamp}
    if len(values) > 1:
        record["sum_boiler_on"] = values[0]
        record["sum_boiler_off"] = values[1]
    if len(values) > 3:
        record["sum_energy_gaz_heating"] = values[2]
        record["sum_energy_gaz_hot_water"] = values[3]
    if len(values) > 5:
        record["sum_energy_elec_heating"] = values[4]
        record["sum_energy_elec_hot_water"] = values[5]
    return record


class MigoDataUpdateCoordinator(DataUpdateCoordinator[CoordinatorData]):
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
        self.homes: dict[str, HomeConfig] = {}
        self.rooms: dict[str, RoomData] = {}
        self.devices: dict[str, ModuleData] = {}
        self.consumption: dict[str, ConsumptionData] = {}
        # Optimistic cache for config values the API does not echo back after a
        # write. Keys are interpolated (f"heating_curve_{device_id}"), so they
        # cannot be a Literal union; the value union below is exhaustive.
        self._config_cache: dict[str, bool | int | float] = {}

    @override
    async def _async_update_data(self) -> CoordinatorData:
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

            body = data.get(KEY_BODY)
            if body is None:
                # No explicit log: DataUpdateCoordinator logs the UpdateFailed
                # message once, then stays quiet until recovery.
                raise UpdateFailed("Invalid response from API: missing 'body'")

            # `or []`, not `.get(..., [])`: the API sends an explicit null here,
            # which a default only covers when the key is absent entirely.
            homes = body.get(KEY_HOMES) or []
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

        except MigoAuthError as err:
            # Triggers the reauthentication flow
            raise ConfigEntryAuthFailed(f"Authentication failed: {err}") from err
        except MigoApiError as err:
            # No explicit log: DataUpdateCoordinator logs this once when the
            # integration goes unavailable, and logs recovery on the next
            # successful refresh. Logging here would duplicate it every cycle.
            raise UpdateFailed(f"Error communicating with API: {err}") from err

    async def _process_home(self, home: HomeConfig) -> None:
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
        modules = home.get(KEY_MODULES) or []
        if not modules:
            _LOGGER.debug("Skipping home %s: no modules found", home_id)
            return

        rooms = home.get(KEY_ROOMS) or []
        _LOGGER.debug(
            "Processing home %s: %d rooms, %d modules",
            home_id,
            len(rooms),
            len(modules),
        )

        self.homes[home_id] = home

        # Get real-time status for this home
        room_status, module_status = await self._fetch_home_status(home_id)

        # Get module configurations (DHW temperature, etc.)
        module_configs = await self._fetch_home_configs(home_id)

        # Process rooms
        for room in rooms:
            self._process_room(room, home_id, home_name, room_status)

        # Process modules/devices
        for module in modules:
            self._process_module(module, home_id, module_status, module_configs)

    async def _fetch_home_status(
        self,
        home_id: str,
    ) -> tuple[dict[str, RoomStatus], dict[str, ModuleStatus]]:
        """Fetch real-time status for a home.

        Args:
            home_id: The home ID to fetch status for.

        Returns:
            Tuple of (room_status_dict, module_status_dict).
        """
        room_status: dict[str, RoomStatus] = {}
        module_status: dict[str, ModuleStatus] = {}

        try:
            status = await self.api.get_home_status(home_id)
            status_body = status.get(KEY_BODY) or {}
            home_data = status_body.get(KEY_HOME) or {}

            for room in home_data.get(KEY_ROOMS) or []:
                room_id = room.get("id")
                if room_id:
                    room_status[room_id] = room

            for module in home_data.get(KEY_MODULES) or []:
                module_id = module.get("id")
                if module_id:
                    module_status[module_id] = module

        except MigoAuthError:
            # Must reach _async_update_data to trigger reauth
            raise
        except MigoApiError as err:
            _LOGGER.warning("Failed to get status for home %s: %s", home_id, err)

        _LOGGER.debug(
            "Fetched status for home %s: %d rooms, %d modules",
            home_id,
            len(room_status),
            len(module_status),
        )
        return room_status, module_status

    async def _fetch_home_configs(self, home_id: str) -> dict[str, ModuleConfigData]:
        """Fetch module configurations for a home.

        This retrieves configuration data not available in homesdata/homestatus,
        such as DHW setpoint temperature.

        Args:
            home_id: The home ID to fetch configs for.

        Returns:
            Dictionary of module_id -> config data.
        """
        module_configs: dict[str, ModuleConfigData] = {}

        try:
            configs = await self.api.get_configs(home_id)
            configs_body = configs.get(KEY_BODY) or {}
            home_data = configs_body.get(KEY_HOME) or {}

            for module in home_data.get(KEY_MODULES) or []:
                module_id = module.get("id")
                if module_id:
                    module_configs[module_id] = module
                    _LOGGER.debug(
                        "Got config for module %s: %s",
                        module_id,
                        redact(module),
                    )

        except MigoAuthError:
            # Must reach _async_update_data to trigger reauth
            raise
        except MigoApiError as err:
            _LOGGER.debug("Failed to get configs for home %s: %s", home_id, err)

        return module_configs

    def _process_room(
        self,
        room: RoomConfig,
        home_id: str,
        home_name: str,
        room_status: dict[str, RoomStatus],
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
        module: ModuleConfig,
        home_id: str,
        module_status: dict[str, ModuleStatus],
        module_configs: dict[str, ModuleConfigData] | None = None,
    ) -> None:
        """Process a module and merge with status and config data.

        Args:
            module: The static module configuration.
            home_id: The home ID this module belongs to.
            module_status: Dictionary of module status by module ID.
            module_configs: Dictionary of module configs by module ID (optional).
        """
        module_id = module.get("id")
        if not module_id:
            return

        # Merge order matters: static configuration first, real-time status last.
        # getconfigs returns more keys than ModuleConfigData declares, and those
        # undeclared keys still land here via **. If any of them overlaps with
        # homestatus (reachable, dhw_enabled), a stale config value would
        # silently win over the live one and entities would report the wrong
        # state with nothing in the logs.
        status_data = module_status.get(module_id, {})
        config_data = (module_configs or {}).get(module_id, {})
        self.devices[module_id] = {
            **module,
            **config_data,
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
                    measure_types=list(MEASURE_TYPES),
                    date_begin=date_begin,
                )

                body = response.get(KEY_BODY, {})
                _LOGGER.debug("Consumption API response body: %s", redact(body))

                # Handle dict format: {"timestamp": [boiler_on, boiler_off], ...}
                if isinstance(body, dict):
                    # Get the most recent (highest timestamp)
                    if body:
                        timestamps = sorted(body.keys(), reverse=True)
                        for ts in timestamps:
                            # The keys are server-chosen, so a non-numeric one
                            # like "latest" is possible. int() would raise
                            # ValueError, which is not a MigoApiError and would
                            # escape into _async_update_data and fail the whole
                            # refresh rather than skip one reading.
                            if not ts.isdigit():
                                _LOGGER.debug(
                                    "Skipping non-numeric consumption timestamp %r for device %s",
                                    ts,
                                    device_id,
                                )
                                continue
                            values = body[ts]
                            if isinstance(values, list) and len(values) >= 2 and values[0] is not None:
                                record = _consumption_record(values, int(ts))
                                self.consumption[device_id] = record
                                _LOGGER.debug("Consumption for device %s: %s", device_id, record)
                                break

                # Handle list format (fallback)
                elif isinstance(body, list) and body:
                    first_entry = body[0]
                    if isinstance(first_entry, dict):
                        series = first_entry.get("value") or []
                        beg_time = first_entry.get("beg_time")
                        step_time = first_entry.get("step_time") or 86400

                        if beg_time is None:
                            # Timestamps below are derived from beg_time. This
                            # used to raise TypeError on `beg_time + ...`, inside
                            # a try that only catches MigoApiError/MigoAuthError,
                            # so it escaped unhandled into _async_update_data.
                            _LOGGER.debug(
                                "Consumption series for device %s carries no beg_time, skipping",
                                device_id,
                            )
                            continue

                        # Find the last non-null value (most recent with data)
                        for i, entry in enumerate(reversed(series)):
                            # The isinstance check is not redundant: the wire
                            # payload is unvalidated and does carry nulls inside
                            # "value". Without it, len(None) raises TypeError,
                            # which escapes the handlers below and fails the
                            # whole refresh instead of one reading.
                            if isinstance(entry, list) and len(entry) >= 2 and entry[0] is not None:
                                timestamp = beg_time + (len(series) - 1 - i) * step_time
                                record = _consumption_record(entry, timestamp)
                                self.consumption[device_id] = record
                                _LOGGER.debug("Consumption for device %s: %s", device_id, record)
                                break

            except MigoAuthError:
                # Must reach _async_update_data to trigger reauth
                raise
            except MigoApiError as err:
                _LOGGER.debug("Failed to get consumption for device %s: %s", device_id, err)

    def get_home(self, home_id: str) -> HomeConfig | None:
        """Get home data by ID.

        Args:
            home_id: The home ID to look up.

        Returns:
            The home data dictionary, or None if not found.
        """
        return self.homes.get(home_id)

    def get_device(self, device_id: str) -> ModuleData | None:
        """Get device/module data by ID.

        Args:
            device_id: The device ID to look up.

        Returns:
            The device data dictionary, or None if not found.
        """
        return self.devices.get(device_id)

    def get_consumption(self, device_id: str) -> ConsumptionData | None:
        """Get consumption data for a device (gateway).

        Args:
            device_id: The gateway device ID (MAC address like '70:ee:50:6b:e3:6a').

        Returns:
            The consumption data dictionary containing sum_boiler_on, sum_boiler_off,
            and timestamp, or None if not found.
        """
        return self.consumption.get(device_id)

    def set_cached_value(self, key: str, value: bool | int | float) -> None:
        """Store a value in the optimistic cache.

        Used for config values that the API doesn't return after modification.

        Args:
            key: Cache key (e.g., "heating_curve_70:ee:50:6b:e3:6a").
            value: The value to cache.
        """
        self._config_cache[key] = value

    def get_cached_value(self, key: str, default: bool | int | float | None = None) -> bool | int | float | None:
        """Get a value from the optimistic cache.

        Args:
            key: Cache key to look up.
            default: Default value if key not found.

        Returns:
            The cached value, or default if not found.
        """
        return self._config_cache.get(key, default)
