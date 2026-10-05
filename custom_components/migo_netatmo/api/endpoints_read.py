"""Read (get_*) endpoint methods for the API client."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from ..const import (
    API_GETCONFIGS_URL,
    API_GETMEASURE_URL,
    API_HOMESDATA_URL,
    API_HOMESTATUS_URL,
    APP_IDENTIFIER,
    APP_TYPE,
    DEVICE_TYPE_GATEWAY,
)
from ..models import (
    GetConfigsResponse,
    GetMeasureResponse,
    HomesDataResponse,
    HomeStatusApiResponse,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

_LOGGER = logging.getLogger(__name__)


class ReadEndpointsMixin:
    """Mixin providing the data-retrieval (get_*) endpoint methods.

    Combined into `MigoApi` alongside `AuthMixin`/`TransportMixin`/
    `WriteEndpointsMixin` - see `api/client.py`.
    """

    if TYPE_CHECKING:
        _api_request: Callable[..., Awaitable[dict[str, Any]]]

    async def get_homes_data(self) -> HomesDataResponse:
        """Get homes data (static configuration) from API.

        This returns the structure of all homes, rooms, modules, and schedules.

        Returns:
            The homesdata response containing home configurations.
        """
        data = {
            "device_types": [DEVICE_TYPE_GATEWAY],
            "sync_measurements": True,
            "app_identifier": APP_IDENTIFIER,
            "home_id": None,
            "app_type": APP_TYPE,
        }

        _LOGGER.debug("Fetching homes data")
        return cast(HomesDataResponse, await self._api_request(API_HOMESDATA_URL, data))

    async def get_home_status(self, home_id: str) -> HomeStatusApiResponse:
        """Get home status (real-time data) from API.

        This returns current temperatures, states, and device status.

        Args:
            home_id: The ID of the home to get status for.

        Returns:
            The homestatus response containing real-time data.
        """
        data = {"home_id": home_id}

        _LOGGER.debug("Fetching home status for: %s", home_id)
        return cast(HomeStatusApiResponse, await self._api_request(API_HOMESTATUS_URL, data))

    async def get_configs(self, home_id: str) -> GetConfigsResponse:
        """Get module configurations from API.

        This returns configuration data that may not be in homesdata/homestatus,
        such as DHW setpoint temperature.

        Args:
            home_id: The ID of the home to get configs for.

        Returns:
            The getconfigs response containing module configurations.
        """
        data = {"home_id": home_id}

        _LOGGER.debug("Fetching configs for: %s", home_id)
        return cast(GetConfigsResponse, await self._api_request(API_GETCONFIGS_URL, data))

    async def get_measure(
        self,
        device_id: str,
        module_id: str,
        scale: str = "1day",
        measure_types: list[str] | None = None,
        date_begin: int | None = None,
        date_end: int | None = None,
    ) -> GetMeasureResponse:
        """Get measurements (historical data) from API using device/module IDs.

        This is the endpoint used by Vaillant vSmart integration for boiler runtime.
        Unlike getroommeasure which uses home/room IDs, this uses device/module IDs.

        Args:
            device_id: The ID of the gateway device (NAVaillant).
            module_id: The ID of the thermostat module (NAThermVaillant).
            scale: Time scale for measurements (30min, 1hour, 3hours, 1day, 1week, 1month).
            measure_types: List of measure types to retrieve. If None, defaults to
                          ["sum_boiler_on", "sum_boiler_off"].
            date_begin: Optional start timestamp (Unix timestamp).
            date_end: Optional end timestamp (Unix timestamp).

        Returns:
            The getmeasure response containing historical measurements.
        """
        if measure_types is None:
            measure_types = [
                "sum_boiler_on",
                "sum_boiler_off",
            ]

        data: dict[str, Any] = {
            "device_id": device_id,
            "module_id": module_id,
            "scale": scale,
            "type": ",".join(measure_types),
        }

        if date_begin is not None:
            data["date_begin"] = date_begin
        if date_end is not None:
            data["date_end"] = date_end

        _LOGGER.debug(
            "Fetching measure for device=%s, module=%s, scale=%s, types=%s",
            device_id,
            module_id,
            scale,
            measure_types,
        )
        # getmeasure uses form data, not JSON (legacy API)
        return cast(GetMeasureResponse, await self._api_request(API_GETMEASURE_URL, data, use_json=False))
