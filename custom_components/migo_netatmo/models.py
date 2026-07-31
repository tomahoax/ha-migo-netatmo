"""Type definitions for MiGo (Netatmo) API responses.

Every field here is NotRequired, deliberately and without exception. Two
reasons, one practical and one about honesty:

- Practical: the integration reads this data through `.get(key, {})` chains
  against a wire format it does not control. A required field would make
  `rooms.get(room_id, {})` unusable as a typed expression, forcing a cast or a
  sentinel at every read site.
- Honest: nothing here is guaranteed by the API. The MiGO backend is an
  undocumented, unversioned Netatmo endpoint. Declaring a field required would
  assert a contract nobody has promised.

The combined types (RoomData, ModuleData) must stay field-wise supersets of the
types they merge. mypy enforces that, because the coordinator builds them by
TypedDict star-expansion: adding a field to RoomStatus and forgetting RoomData
becomes a type error rather than a value silently dropped on the floor.
"""

from __future__ import annotations

from typing import NotRequired, TypedDict

# =============================================================================
# OAuth / Authentication
# =============================================================================


class TokenResponse(TypedDict):
    """OAuth token response from /oauth2/token."""

    access_token: NotRequired[str]
    expires_in: NotRequired[int]
    refresh_token: NotRequired[str]
    scope: NotRequired[list[str]]


# =============================================================================
# Schedule / Timetable
# =============================================================================


class TimetableEntry(TypedDict):
    """Single entry in a schedule timetable."""

    zone_id: NotRequired[int]
    m_offset: NotRequired[int]  # Minutes since Monday 00:00


class RoomTemperature(TypedDict):
    """Room temperature setting in a zone."""

    id: NotRequired[str]
    therm_setpoint_temperature: NotRequired[float]


class ZoneModule(TypedDict):
    """Module configuration in a zone (for DHW schedules)."""

    id: NotRequired[str]
    dhw_enabled: NotRequired[bool]


class ScheduleZone(TypedDict):
    """Zone definition in a schedule."""

    id: NotRequired[int]
    type: NotRequired[int]  # 0=Comfort, 1=Night, 5=Eco
    name: NotRequired[str]
    rooms: NotRequired[list[RoomTemperature]]
    modules: NotRequired[list[ZoneModule]]


class Schedule(TypedDict):
    """Schedule configuration."""

    id: NotRequired[str]
    name: NotRequired[str]
    type: NotRequired[str]  # "therm" or "event"
    selected: NotRequired[bool]
    default: NotRequired[bool]
    hg_temp: NotRequired[float]  # Frost guard temperature
    away_temp: NotRequired[float]  # Away temperature
    zones: NotRequired[list[ScheduleZone]]
    timetable: NotRequired[list[TimetableEntry]]


# =============================================================================
# Room Data
# =============================================================================


class RoomConfig(TypedDict):
    """Static room configuration from homesdata."""

    id: NotRequired[str]
    name: NotRequired[str]
    type: NotRequired[str]  # "custom", "living_room", etc.
    module_ids: NotRequired[list[str]]
    # Hardware sensor calibration, not the user-facing offset. The temperature
    # offset number entity reads therm_setpoint_offset instead.
    measure_offset_NAVaillant_temperature: NotRequired[float]


class RoomStatus(TypedDict):
    """Real-time room status from homestatus."""

    id: NotRequired[str]
    therm_measured_temperature: NotRequired[float]
    therm_setpoint_temperature: NotRequired[float]
    therm_setpoint_mode: NotRequired[str]  # "schedule", "manual", "home", "hg", "away"
    therm_setpoint_start_time: NotRequired[int]
    therm_setpoint_end_time: NotRequired[int]
    # User-configured setpoint offset, surfaced by the temperature offset entity.
    therm_setpoint_offset: NotRequired[float]
    # Only reported by some hardware; the humidity sensor is gated on its
    # presence rather than declared unconditionally.
    humidity: NotRequired[float]
    anticipating: NotRequired[bool]
    reachable: NotRequired[bool]


class RoomData(TypedDict):
    """Combined room data: RoomConfig + RoomStatus + coordinator metadata."""

    # From RoomConfig
    id: NotRequired[str]
    name: NotRequired[str]
    type: NotRequired[str]
    module_ids: NotRequired[list[str]]
    measure_offset_NAVaillant_temperature: NotRequired[float]
    # From RoomStatus
    therm_measured_temperature: NotRequired[float]
    therm_setpoint_temperature: NotRequired[float]
    therm_setpoint_mode: NotRequired[str]
    therm_setpoint_start_time: NotRequired[int]
    therm_setpoint_end_time: NotRequired[int]
    therm_setpoint_offset: NotRequired[float]
    humidity: NotRequired[float]
    anticipating: NotRequired[bool]
    reachable: NotRequired[bool]
    # Added by the coordinator
    home_id: NotRequired[str]
    home_name: NotRequired[str]


# =============================================================================
# Module / Device Data
# =============================================================================


class ModuleConfig(TypedDict):
    """Static module configuration from homesdata.

    Covers both device kinds. They are merged rather than split into gateway and
    thermostat variants because the code discriminates at runtime on the "type"
    field, never on a static type, and because a union of TypedDicts cannot
    infer a default for `module_configs.get(module_id, {})`.
    """

    id: NotRequired[str]
    type: NotRequired[str]  # "NAVaillant" (gateway) or "NAThermVaillant"

    # Gateway specific, type NAVaillant
    subtype: NotRequired[str]  # "NAEbusSdbg"
    oem_serial: NotRequired[str]
    dhw_control: NotRequired[str]  # "instantaneous"
    modules_bridged: NotRequired[list[str]]

    # Thermostat specific, type NAThermVaillant
    room_id: NotRequired[str]
    bridge: NotRequired[str]  # Parent gateway ID

    # Both
    reachable: NotRequired[bool]


class ModuleStatus(TypedDict):
    """Real-time module status from homestatus.

    Merged across device kinds, for the reasons given on ModuleConfig.
    """

    id: NotRequired[str]
    type: NotRequired[str]

    # Gateway specific, type NAVaillant
    subtype: NotRequired[str]
    wifi_strength: NotRequired[int]
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

    # Thermostat specific, type NAThermVaillant
    bridge: NotRequired[str]
    battery_level: NotRequired[int]  # mV
    battery_percent: NotRequired[int]  # 0-100
    battery_state: NotRequired[str]  # "high", "medium", "low"
    boiler_status: NotRequired[bool]
    last_seen: NotRequired[int]
    last_message: NotRequired[int]
    radio_id: NotRequired[int]

    # Both
    firmware_revision: NotRequired[int]
    rf_strength: NotRequired[int]
    reachable: NotRequired[bool]


class ModuleConfigData(TypedDict):
    """Module payload from the getconfigs endpoint.

    These are the fields this integration consumes, not an exhaustive model of
    the endpoint. getconfigs returns more; the coordinator merges the payload
    with `**`, so undeclared keys still reach coordinator.devices and are simply
    invisible to the type checker.
    """

    id: NotRequired[str]
    dhw_setpoint_temperature: NotRequired[float]
    simple_heating_algo_deadband: NotRequired[float]
    heating_curve: NotRequired[float]


class ModuleData(TypedDict):
    """Combined module data: ModuleConfig + ModuleStatus + ModuleConfigData.

    Covers a gateway (NAVaillant) or a thermostat (NAThermVaillant); use the
    "type" field to tell them apart at runtime.
    """

    # Common
    id: NotRequired[str]
    type: NotRequired[str]
    home_id: NotRequired[str]

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

    # From getconfigs
    dhw_setpoint_temperature: NotRequired[float]
    simple_heating_algo_deadband: NotRequired[float]
    heating_curve: NotRequired[float]

    # Common to both
    firmware_revision: NotRequired[int]
    rf_strength: NotRequired[int]
    reachable: NotRequired[bool]


# =============================================================================
# Home Data
# =============================================================================


class HomeConfig(TypedDict):
    """Home configuration from homesdata."""

    id: NotRequired[str]
    name: NotRequired[str]
    therm_mode: NotRequired[str]  # "schedule", "away", "hg"
    anticipation: NotRequired[bool]
    therm_setpoint_default_duration: NotRequired[int]
    therm_heating_priority: NotRequired[str]  # "eco", "comfort"
    outdoor_temperature_source: NotRequired[str]
    rooms: NotRequired[list[RoomConfig]]
    modules: NotRequired[list[ModuleConfig]]
    schedules: NotRequired[list[Schedule]]


class HomeStatus(TypedDict):
    """Home status from the homestatus API."""

    id: NotRequired[str]
    rooms: NotRequired[list[RoomStatus]]
    modules: NotRequired[list[ModuleStatus]]


class ConfigsHome(TypedDict):
    """Home payload from the getconfigs endpoint."""

    id: NotRequired[str]
    modules: NotRequired[list[ModuleConfigData]]


# =============================================================================
# API Responses
# =============================================================================


class HomesDataBody(TypedDict):
    """Body of the homesdata response."""

    homes: NotRequired[list[HomeConfig]]


class HomesDataResponse(TypedDict):
    """Full response from /api/homesdata."""

    body: NotRequired[HomesDataBody]
    status: NotRequired[str]
    time_exec: NotRequired[float]
    time_server: NotRequired[int]


class HomeStatusBody(TypedDict):
    """Body of the homestatus response."""

    home: NotRequired[HomeStatus]


class HomeStatusApiResponse(TypedDict):
    """Full response from /api/homestatus."""

    body: NotRequired[HomeStatusBody]
    status: NotRequired[str]
    time_exec: NotRequired[float]
    time_server: NotRequired[int]


class GetConfigsBody(TypedDict):
    """Body of the getconfigs response."""

    home: NotRequired[ConfigsHome]


class GetConfigsResponse(TypedDict):
    """Full response from /api/getconfigs."""

    body: NotRequired[GetConfigsBody]
    status: NotRequired[str]


class MeasureSeries(TypedDict):
    """One series in the list form of a getmeasure response.

    The element type of "value" admits None: the endpoint does return nulls in
    place of a missing sample pair, so declaring list[list[float | None]] would
    over-promise and make the runtime guard in the coordinator look redundant.
    """

    beg_time: NotRequired[int | None]
    step_time: NotRequired[int | None]
    value: NotRequired[list[list[float | None] | None] | None]


class GetMeasureResponse(TypedDict):
    """Full response from /api/getmeasure.

    The body comes back in one of two shapes, hence the union: a mapping of Unix
    timestamp to a [boiler_on, boiler_off] pair, or a list of series objects.
    The mapping form has unbounded keys, so it stays a plain dict rather than a
    TypedDict with invented timestamp fields.
    """

    body: NotRequired[dict[str, list[float | None]] | list[MeasureSeries]]
    status: NotRequired[str]


# =============================================================================
# Coordinator Data
# =============================================================================


class ConsumptionData(TypedDict):
    """Runtime and energy record, assembled by the coordinator from getmeasure.

    Field names deliberately match the API's own measure type names, including
    the French "gaz" spelling, so a value in a log or a diagnostics file can be
    traced straight back to the wire without a translation table.

    Every value is a float rather than an int: they are unpacked straight out of
    a JSON array whose element type the API does not pin down.

    The energy fields are NotRequired for a real reason, not just for style: a
    boiler that reports only the two boiler-time measures yields a shorter value
    row, and the record is built from whatever length arrives.

    Energy is in Wh. See const.WH_PER_KWH.
    """

    timestamp: NotRequired[int]
    sum_boiler_on: NotRequired[float]
    sum_boiler_off: NotRequired[float | None]
    sum_energy_gaz_heating: NotRequired[float | None]
    sum_energy_gaz_hot_water: NotRequired[float | None]
    sum_energy_elec_heating: NotRequired[float | None]
    sum_energy_elec_hot_water: NotRequired[float | None]


class CoordinatorData(TypedDict):
    """Data structure returned by the coordinator."""

    homes: NotRequired[dict[str, HomeConfig]]
    rooms: NotRequired[dict[str, RoomData]]
    devices: NotRequired[dict[str, ModuleData]]
