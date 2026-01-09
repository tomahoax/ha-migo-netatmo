"""Type definitions for MiGo (Netatmo) API responses."""

from __future__ import annotations

from typing import NotRequired, TypedDict

# =============================================================================
# OAuth / Authentication
# =============================================================================


class TokenResponse(TypedDict):
    """OAuth token response from /oauth2/token."""

    access_token: str
    expires_in: int
    refresh_token: str
    scope: list[str]


# =============================================================================
# Schedule / Timetable
# =============================================================================


class TimetableEntry(TypedDict):
    """Single entry in a schedule timetable."""

    zone_id: int
    m_offset: int  # Minutes since Monday 00:00


class RoomTemperature(TypedDict):
    """Room temperature setting in a zone."""

    id: str
    therm_setpoint_temperature: float


class ZoneModule(TypedDict):
    """Module configuration in a zone (for DHW schedules)."""

    id: str
    dhw_enabled: NotRequired[bool]


class ScheduleZone(TypedDict):
    """Zone definition in a schedule."""

    id: int
    type: int  # 0=Comfort, 1=Night, 5=Eco
    name: str
    rooms: NotRequired[list[RoomTemperature]]
    modules: NotRequired[list[ZoneModule]]


class Schedule(TypedDict):
    """Schedule configuration."""

    id: str
    name: str
    type: str  # "therm" or "event"
    selected: bool
    default: bool
    hg_temp: NotRequired[float]  # Frost guard temperature
    away_temp: NotRequired[float]  # Away temperature
    zones: list[ScheduleZone]
    timetable: list[TimetableEntry]


# =============================================================================
# Room Data
# =============================================================================


class RoomConfig(TypedDict):
    """Static room configuration from homesdata."""

    id: str
    name: str
    type: str  # "custom", "living_room", etc.
    module_ids: list[str]
    measure_offset_NAVaillant_temperature: NotRequired[float]


class RoomStatus(TypedDict):
    """Real-time room status from homestatus."""

    id: str
    therm_measured_temperature: NotRequired[float]
    therm_setpoint_temperature: NotRequired[float]
    therm_setpoint_mode: NotRequired[str]  # "schedule", "manual", "home", "hg", "away"
    therm_setpoint_start_time: NotRequired[int]
    therm_setpoint_end_time: NotRequired[int]
    anticipating: NotRequired[bool]
    reachable: NotRequired[bool]


class RoomData(TypedDict):
    """Combined room data (config + status + metadata)."""

    # From RoomConfig
    id: str
    name: str
    type: str
    module_ids: NotRequired[list[str]]
    # From RoomStatus
    therm_measured_temperature: NotRequired[float]
    therm_setpoint_temperature: NotRequired[float]
    therm_setpoint_mode: NotRequired[str]
    therm_setpoint_start_time: NotRequired[int]
    therm_setpoint_end_time: NotRequired[int]
    anticipating: NotRequired[bool]
    reachable: NotRequired[bool]
    # Metadata added by coordinator
    home_id: str
    home_name: str


# =============================================================================
# Module / Device Data
# =============================================================================


class GatewayConfig(TypedDict):
    """Static gateway (NAVaillant) configuration from homesdata."""

    id: str
    type: str  # "NAVaillant"
    subtype: NotRequired[str]  # "NAEbusSdbg"
    oem_serial: NotRequired[str]
    dhw_control: NotRequired[str]  # "instantaneous"
    reachable: NotRequired[bool]
    modules_bridged: NotRequired[list[str]]


class GatewayStatus(TypedDict):
    """Real-time gateway status from homestatus."""

    id: str
    type: str
    subtype: NotRequired[str]
    wifi_strength: NotRequired[int]
    rf_strength: NotRequired[int]
    firmware_revision: NotRequired[int]
    hardware_version: NotRequired[int]
    oem_serial: NotRequired[str]
    boiler_id: NotRequired[str]
    boiler_error: NotRequired[list[str]]
    ebus_error: NotRequired[bool]
    emf_avail: NotRequired[bool]
    dhw_enabled: NotRequired[bool]
    dhw_setpoint_endtime: NotRequired[int]
    outdoor_temperature: NotRequired[float]
    sequence_id: NotRequired[int]


class ThermostatConfig(TypedDict):
    """Static thermostat (NAThermVaillant) configuration from homesdata."""

    id: str
    type: str  # "NAThermVaillant"
    room_id: NotRequired[str]
    bridge: NotRequired[str]  # Parent gateway ID


class ThermostatStatus(TypedDict):
    """Real-time thermostat status from homestatus."""

    id: str
    type: str
    bridge: NotRequired[str]
    battery_level: NotRequired[int]  # mV
    battery_percent: NotRequired[int]  # 0-100
    battery_state: NotRequired[str]  # "high", "medium", "low"
    rf_strength: NotRequired[int]
    firmware_revision: NotRequired[int]
    reachable: NotRequired[bool]
    boiler_status: NotRequired[bool]
    last_seen: NotRequired[int]
    last_message: NotRequired[int]
    radio_id: NotRequired[int]


class ModuleData(TypedDict):
    """Combined module data (config + status + metadata).

    This can be either a gateway (NAVaillant) or thermostat (NAThermVaillant).
    """

    # Common fields
    id: str
    type: str  # "NAVaillant" or "NAThermVaillant"
    home_id: str

    # Gateway specific
    subtype: NotRequired[str]
    oem_serial: NotRequired[str]
    dhw_control: NotRequired[str]
    modules_bridged: NotRequired[list[str]]
    wifi_strength: NotRequired[int]
    hardware_version: NotRequired[int]
    boiler_id: NotRequired[str]
    boiler_error: NotRequired[list[str]]
    ebus_error: NotRequired[bool]
    emf_avail: NotRequired[bool]
    dhw_enabled: NotRequired[bool]
    dhw_setpoint_endtime: NotRequired[int]
    outdoor_temperature: NotRequired[float]
    sequence_id: NotRequired[int]

    # Thermostat specific
    room_id: NotRequired[str]
    bridge: NotRequired[str]
    battery_level: NotRequired[int]
    battery_percent: NotRequired[int]
    battery_state: NotRequired[str]
    boiler_status: NotRequired[bool]
    last_seen: NotRequired[int]
    last_message: NotRequired[int]
    radio_id: NotRequired[int]

    # Common to both
    firmware_revision: NotRequired[int]
    rf_strength: NotRequired[int]
    reachable: NotRequired[bool]


# =============================================================================
# Home Data
# =============================================================================


class HomeConfig(TypedDict):
    """Home configuration from homesdata."""

    id: str
    name: str
    therm_mode: NotRequired[str]  # "schedule", "away", "hg"
    anticipation: NotRequired[bool]
    therm_setpoint_default_duration: NotRequired[int]
    therm_heating_priority: NotRequired[str]  # "eco", "comfort"
    outdoor_temperature_source: NotRequired[str]
    rooms: list[RoomConfig]
    modules: list[GatewayConfig | ThermostatConfig]
    schedules: NotRequired[list[Schedule]]


class HomeStatusResponse(TypedDict):
    """Response from homestatus API."""

    home: HomeStatus


class HomeStatus(TypedDict):
    """Home status from homestatus API."""

    id: str
    rooms: NotRequired[list[RoomStatus]]
    modules: NotRequired[list[GatewayStatus | ThermostatStatus]]


# =============================================================================
# API Responses
# =============================================================================


class HomesDataBody(TypedDict):
    """Body of homesdata response."""

    homes: list[HomeConfig]


class HomesDataResponse(TypedDict):
    """Full response from /api/homesdata."""

    body: HomesDataBody
    status: str
    time_exec: NotRequired[float]
    time_server: NotRequired[int]


class HomeStatusBody(TypedDict):
    """Body of homestatus response."""

    home: HomeStatus


class HomeStatusApiResponse(TypedDict):
    """Full response from /api/homestatus."""

    body: HomeStatusBody
    status: str
    time_exec: NotRequired[float]
    time_server: NotRequired[int]


class SetStateResponse(TypedDict):
    """Response from setstate API."""

    status: str
    time_exec: NotRequired[float]


# =============================================================================
# Coordinator Data
# =============================================================================


class CoordinatorData(TypedDict):
    """Data structure returned by the coordinator."""

    homes: dict[str, HomeConfig]
    rooms: dict[str, RoomData]
    devices: dict[str, ModuleData]
