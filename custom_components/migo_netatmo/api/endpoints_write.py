"""Write (set_*) endpoint methods for the API client."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from ..const import (
    API_CHANGEHEATINGALGO_URL,
    API_CHANGEHEATINGCURVE_URL,
    API_SETCONFIGS_URL,
    API_SETHEATINGSYSTEM_URL,
    API_SETHOMEDATA_URL,
    API_SETSTATE_URL,
    API_SWITCHHOMESCHEDULE_URL,
    MODE_MANUAL,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

_LOGGER = logging.getLogger(__name__)


class WriteEndpointsMixin:
    """Mixin providing the control (set_*) endpoint methods.

    Combined into `MigoApi` alongside `AuthMixin`/`TransportMixin`/
    `ReadEndpointsMixin` - see `api/client.py`.
    """

    if TYPE_CHECKING:
        _api_request: Callable[..., Awaitable[dict[str, Any]]]

    async def set_room_state(
        self,
        home_id: str,
        room_id: str,
        mode: str | None = None,
        temp: float | None = None,
        end_time: int | None = None,
    ) -> dict[str, Any]:
        """Set room state using the setstate API.

        Args:
            home_id: The home ID.
            room_id: The room ID.
            mode: Optional mode to set (manual, home, hg).
            temp: Optional target temperature.
            end_time: Optional Unix timestamp when the setpoint expires.
                If omitted, the backend applies therm_setpoint_default_duration.

        Returns:
            The API response.
        """
        room_data: dict[str, Any] = {"id": room_id}

        if mode is not None:
            room_data["therm_setpoint_mode"] = mode

        if temp is not None:
            room_data["therm_setpoint_temperature"] = temp

        if end_time is not None:
            room_data["therm_setpoint_end_time"] = end_time

        data = {
            "home": {
                "id": home_id,
                "rooms": [room_data],
            }
        }

        _LOGGER.debug(
            "Setting room %s state: mode=%s, temp=%s, end_time=%s",
            room_id,
            mode,
            temp,
            end_time,
        )
        return await self._api_request(API_SETSTATE_URL, data)

    async def set_temperature(
        self,
        home_id: str,
        room_id: str,
        temperature: float,
        duration: int | None = None,
    ) -> dict[str, Any]:
        """Set target temperature for a room.

        This sets the room to manual mode with the specified temperature.

        Args:
            home_id: The home ID.
            room_id: The room ID.
            temperature: The target temperature in Celsius.
            duration: Optional override duration in minutes. If omitted, the
                backend applies therm_setpoint_default_duration.

        Returns:
            The API response.
        """
        end_time: int | None = None
        if duration is not None:
            end_time = int(datetime.now(UTC).timestamp()) + duration * 60

        return await self.set_room_state(
            home_id=home_id,
            room_id=room_id,
            mode=MODE_MANUAL,
            temp=temperature,
            end_time=end_time,
        )

    async def set_home_therm_mode(
        self,
        home_id: str,
        mode: str,
        endtime: int | None = None,
    ) -> dict[str, Any]:
        """Set the home-level therm_mode via sethomedata, optionally with an end time.

        Unlike `set_therm_mode` (the setthermmode endpoint), this supports an
        optional Unix timestamp after which the mode automatically reverts -
        used for a "return home at" time when activating Away, which the
        MiGo app itself offers but setthermmode has no documented parameter
        for. `endtime` is always sent explicitly (including as `None`), so a
        call with no end time also clears out any previously-set one.

        Always sends `temperature_control_mode: "heating"` too, matching
        every `sethomedata` call the MiGo app itself makes for every mode
        except DHW-only (see `set_temperature_control_mode` for that one -
        confirmed live, the two cannot be combined in a single call). The
        API rejects any `therm_mode` change with a 403 ("Cannot change
        therm_mode while being in temperature_control_mode cooling") if the
        account's `temperature_control_mode` is `"cooling"` - sending
        "heating" here resets a value left over from DHW-only rather than
        reproducing that 403, confirmed live to work reliably (unlike
        pairing therm_mode with "cooling" in the same call, which never
        works no matter what mode is requested alongside it - see
        `set_temperature_control_mode`'s docstring for the full story).

        Args:
            home_id: The home ID.
            mode: The mode (schedule, away, hg).
            endtime: Optional Unix timestamp when the mode should end.
                None means indefinite.

        Returns:
            The API response.
        """
        data = {
            "home": {
                "id": home_id,
                "temperature_control_mode": "heating",
                "therm_mode": mode,
                "therm_mode_endtime": endtime,
            }
        }

        _LOGGER.debug(
            "Setting home %s therm_mode=%s endtime=%s via sethomedata",
            home_id,
            mode,
            endtime,
        )
        return await self._api_request(API_SETHOMEDATA_URL, data)

    async def set_temperature_control_mode(
        self,
        home_id: str,
        mode: str,
    ) -> dict[str, Any]:
        """Set the home's temperature_control_mode alone via sethomedata, no therm_mode field at all.

        Used to enter MiGo's "Eau chaude seulement" (DHW only) quick action
        (`mode="cooling"` - despite the name, not a literal cooling mode;
        this boiler line has no air conditioning, it's just the flag this
        account's real DHW-only quick action runs under).

        Deliberately omits `therm_mode`/`therm_mode_endtime` entirely,
        rather than resending the home's current therm_mode alongside the
        new temperature_control_mode the way `set_home_therm_mode` does.
        Reported live and confirmed: a `sethomedata` call that includes
        both `therm_mode` and `temperature_control_mode: "cooling"` gets
        rejected with a 403 ("Cannot change therm_mode while being in
        temperature_control_mode cooling"), regardless of whether
        `therm_mode`'s value actually changes from what it already was -
        the same combination with `"heating"` instead (`set_home_therm_mode`,
        used by every other home-level write in this integration) works
        fine. The restriction is specific to requesting "cooling" alongside
        a therm_mode field, not to reading/being in "cooling" generally.

        Args:
            home_id: The home ID.
            mode: "cooling" to enter DHW-only, "heating" to leave it
                without also touching therm_mode (prefer
                `set_home_therm_mode` when a therm_mode change is wanted
                too - it resets this field to "heating" as part of the
                same call).

        Returns:
            The API response.
        """
        data = {
            "home": {
                "id": home_id,
                "temperature_control_mode": mode,
            }
        }

        _LOGGER.debug("Setting home %s temperature_control_mode=%s via sethomedata", home_id, mode)
        return await self._api_request(API_SETHOMEDATA_URL, data)

    async def set_dhw_enabled(
        self,
        home_id: str,
        module_id: str,
        enabled: bool,
    ) -> dict[str, Any]:
        """Enable or disable domestic hot water (DHW/ECS).

        Args:
            home_id: The home ID.
            module_id: The NAVaillant module ID (gateway).
            enabled: True to enable DHW, False to disable.

        Returns:
            The API response.
        """
        data = {
            "home": {
                "id": home_id,
                "modules": [
                    {
                        "id": module_id,
                        "dhw_enabled": enabled,
                    }
                ],
            }
        }

        _LOGGER.debug("Setting DHW enabled=%s for module %s", enabled, module_id)
        return await self._api_request(API_SETSTATE_URL, data)

    async def switch_home_schedule(
        self,
        home_id: str,
        schedule_id: str,
    ) -> dict[str, Any]:
        """Switch to a different schedule.

        Args:
            home_id: The home ID.
            schedule_id: The schedule ID to activate.

        Returns:
            The API response.
        """
        data = {
            "home_id": home_id,
            "schedule_id": schedule_id,
        }

        _LOGGER.debug("Switching home %s to schedule: %s", home_id, schedule_id)
        return await self._api_request(API_SWITCHHOMESCHEDULE_URL, data)

    async def set_anticipation(
        self,
        home_id: str,
        enabled: bool,
    ) -> dict[str, Any]:
        """Enable or disable heating anticipation.

        Args:
            home_id: The home ID.
            enabled: True to enable anticipation, False to disable.

        Returns:
            The API response.
        """
        data = {
            "home": {
                "id": home_id,
                "anticipation": enabled,
            }
        }

        _LOGGER.debug("Setting anticipation=%s for home %s", enabled, home_id)
        return await self._api_request(API_SETHOMEDATA_URL, data)

    async def set_heating_curve(
        self,
        device_id: str,
        slope: float,
    ) -> dict[str, Any]:
        """Set heating curve (slope).

        Args:
            device_id: The gateway device ID.
            slope: The slope value in UI (0.0-5.0). API uses slope * 10.

        Returns:
            The API response.
        """
        # Convert UI value (0.0-5.0) to API value (0-50)
        api_slope = int(slope * 10)
        data = {
            "device_id": device_id,
            "slope": api_slope,
        }

        _LOGGER.debug(
            "Setting heating curve slope=%s (api=%s) for device %s",
            slope,
            api_slope,
            device_id,
        )
        return await self._api_request(API_CHANGEHEATINGCURVE_URL, data)

    async def set_heating_type(
        self,
        device_id: str,
        heating_type: str,
    ) -> dict[str, Any]:
        """Set heating system type.

        No entity exposes this yet: it is kept as a wrapper over a real
        endpoint, ready for a "heating type" select. Do not delete it as
        unused without also dropping that plan.

        Args:
            device_id: The gateway device ID.
            heating_type: The heating type (radiators, convector, floor_heating, unknown).

        Returns:
            The API response.
        """
        data = {
            "device_id": device_id,
            "heating_type": heating_type,
        }

        _LOGGER.debug("Setting heating type=%s for device %s", heating_type, device_id)
        return await self._api_request(API_SETHEATINGSYSTEM_URL, data)

    async def set_dhw_storage(
        self,
        home_id: str,
        module_id: str,
        use_water_tank: bool,
    ) -> dict[str, Any]:
        """Set DHW storage mode (water tank vs instantaneous).

        No entity exposes this yet: it is kept as a wrapper over a real
        endpoint, ready for a DHW storage switch. Do not delete it as
        unused without also dropping that plan.

        Args:
            home_id: The home ID.
            module_id: The gateway module ID.
            use_water_tank: True for water tank, False for instantaneous.

        Returns:
            The API response.
        """
        dhw_control = "water_tank" if use_water_tank else "instantaneous"
        data = {
            "home": {
                "id": home_id,
                "modules": [
                    {
                        "id": module_id,
                        "dhw_control": dhw_control,
                    }
                ],
            }
        }

        _LOGGER.debug("Setting DHW storage=%s for module %s", dhw_control, module_id)
        return await self._api_request(API_SETHOMEDATA_URL, data)

    async def set_dhw_temperature(
        self,
        home_id: str,
        module_id: str,
        temperature: int,
    ) -> dict[str, Any]:
        """Set domestic hot water temperature.

        Args:
            home_id: The home ID.
            module_id: The gateway module ID.
            temperature: The DHW temperature (45-65°C).

        Returns:
            The API response.
        """
        # Based on mitmproxy capture: the API expects home_id at root level
        # and home.modules[].dhw_setpoint_temperature for the value
        data = {
            "home_id": home_id,
            "home": {
                "modules": [
                    {
                        "id": module_id,
                        "dhw_setpoint_temperature": temperature,
                    }
                ],
            },
        }

        _LOGGER.debug("Setting DHW temperature=%s for module %s", temperature, module_id)
        return await self._api_request(API_SETCONFIGS_URL, data)

    async def set_dhw_always_on(
        self,
        home_id: str,
        module_id: str,
        enabled: bool,
    ) -> dict[str, Any]:
        """Set whether DHW production always stays on, overriding the schedule.

        `dhw_always_on` is undocumented by Netatmo, confirmed via a live
        debug-log capture of `/syncapi/v1/getconfigs`'s response - it sits
        on the same module entry as `dhw_setpoint_temperature`, which is
        why this follows the exact same request shape as
        `set_dhw_temperature` rather than `set_dhw_enabled` (which is a
        `setstate` call, a different endpoint entirely, for the per-slot
        schedule flag `dhw_always_on` overrides).

        Args:
            home_id: The home ID.
            module_id: The gateway module ID.
            enabled: True to force DHW production always on.

        Returns:
            The API response.
        """
        data = {
            "home_id": home_id,
            "home": {
                "modules": [
                    {
                        "id": module_id,
                        "dhw_always_on": enabled,
                    }
                ],
            },
        }

        _LOGGER.debug("Setting DHW always-on=%s for module %s", enabled, module_id)
        return await self._api_request(API_SETCONFIGS_URL, data)

    async def set_temperature_offset(
        self,
        home_id: str,
        room_id: str,
        offset: float,
    ) -> dict[str, Any]:
        """Set room temperature offset.

        Args:
            home_id: The home ID.
            room_id: The room ID.
            offset: The temperature offset (-5.0 to +5.0°C).

        Returns:
            The API response.
        """
        # setconfigs's other calls (set_dhw_temperature, set_dhw_always_on) were
        # confirmed via mitmproxy capture to need home_id at the root level, not
        # just nested under home.id - this call was missing that root-level key,
        # which is the likely reason it silently failed to take effect server-side
        # (reported live: neither sets nor reads back the real value). home.id is
        # kept too, matching the shape captured for this specific rooms variant.
        data = {
            "home_id": home_id,
            "home": {
                "id": home_id,
                "rooms": [
                    {
                        "id": room_id,
                        "therm_setpoint_offset": offset,
                    }
                ],
            },
        }

        _LOGGER.debug("Setting temperature offset=%s for room %s", offset, room_id)
        return await self._api_request(API_SETCONFIGS_URL, data)

    async def set_manual_setpoint_duration(
        self,
        home_id: str,
        duration: int,
    ) -> dict[str, Any]:
        """Set default duration for manual setpoints.

        Args:
            home_id: The home ID.
            duration: Duration in minutes (5-720, i.e., 5min to 12h).

        Returns:
            The API response.
        """
        data = {
            "home": {
                "id": home_id,
                "therm_setpoint_default_duration": duration,
            }
        }

        _LOGGER.debug("Setting manual setpoint duration=%s for home %s", duration, home_id)
        return await self._api_request(API_SETHOMEDATA_URL, data)

    async def set_hysteresis(
        self,
        device_id: str,
        hysteresis: float,
    ) -> dict[str, Any]:
        """Set hysteresis threshold for heating algorithm.

        Args:
            device_id: The gateway device ID (e.g., "70:ee:50:6b:e3:6a").
            hysteresis: Hysteresis value in °C (0.1 to 2.0).

        Returns:
            The API response.
        """
        # API uses high_deadband = hysteresis * 10 - 1
        # e.g., 0.4°C -> high_deadband = 3, 1.8°C -> high_deadband = 17
        high_deadband = int(hysteresis * 10 - 1)

        data = {
            "device_id": device_id,
            "algo_type": "simple_algo",
            "algo_params": {
                "high_deadband": high_deadband,
            },
        }

        _LOGGER.debug(
            "Setting hysteresis=%s (high_deadband=%s) for device %s",
            hysteresis,
            high_deadband,
            device_id,
        )
        return await self._api_request(API_CHANGEHEATINGALGO_URL, data)
