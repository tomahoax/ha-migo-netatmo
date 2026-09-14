"""Binary sensor platform for MiGO integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEVICE_TYPE_GATEWAY, DEVICE_TYPE_THERMOSTAT
from .entity import MigoGatewayEntity, MigoRoomEntity, MigoThermostatEntity
from .helpers import (
    current_week_minutes,
    generate_unique_id,
    get_devices_by_type,
    get_event_schedule,
    is_home_away,
    resolve_timetable_zone,
)

if TYPE_CHECKING:
    from . import MigoConfigEntry
    from .coordinator import MigoDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class BinarySensorConfig:
    """Configuration for a binary sensor entity."""

    data_key: str
    unique_id_key: str
    translation_key: str
    device_class: BinarySensorDeviceClass | None = None
    entity_category: EntityCategory | None = None
    value_fn: Callable[[Any], bool | None] | None = None


# Room-based binary sensor configurations
ROOM_BINARY_SENSORS: tuple[BinarySensorConfig, ...] = ()

# Gateway binary sensor configurations
GATEWAY_BINARY_SENSORS: tuple[BinarySensorConfig, ...] = (
    BinarySensorConfig(
        data_key="ebus_error",
        unique_id_key="ebus_error",
        translation_key="ebus_error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorConfig(
        data_key="boiler_error",
        unique_id_key="boiler_error",
        translation_key="boiler_error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda v: bool(v) if v is not None else None,
    ),
)

# Thermostat binary sensor configurations
THERMOSTAT_BINARY_SENSORS: tuple[BinarySensorConfig, ...] = (
    BinarySensorConfig(
        data_key="boiler_status",
        unique_id_key="boiler_status",
        translation_key="boiler_status",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    BinarySensorConfig(
        data_key="reachable",
        unique_id_key="reachable",
        translation_key="reachable",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MigoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MiGO binary sensor entities."""
    coordinator = entry.runtime_data.coordinator

    entities: list[BinarySensorEntity] = []

    # Room-based binary sensors
    for room_id in coordinator.rooms:
        for config in ROOM_BINARY_SENSORS:
            entities.append(
                MigoRoomBinarySensor(
                    coordinator=coordinator,
                    room_id=room_id,
                    config=config,
                )
            )

    # Gateway binary sensors
    for device_id in get_devices_by_type(coordinator, DEVICE_TYPE_GATEWAY):
        for config in GATEWAY_BINARY_SENSORS:
            entities.append(
                MigoGatewayBinarySensor(
                    coordinator=coordinator,
                    device_id=device_id,
                    config=config,
                )
            )

    # Thermostat binary sensors
    for device_id in get_devices_by_type(coordinator, DEVICE_TYPE_THERMOSTAT):
        for config in THERMOSTAT_BINARY_SENSORS:
            entities.append(
                MigoThermostatBinarySensor(
                    coordinator=coordinator,
                    device_id=device_id,
                    config=config,
                )
            )

    # Away mode and DHW schedule binary sensors, one per gateway
    for device_id in get_devices_by_type(coordinator, DEVICE_TYPE_GATEWAY):
        entities.append(MigoAwayModeBinarySensor(coordinator=coordinator, device_id=device_id))
        entities.append(MigoDHWScheduleBinarySensor(coordinator=coordinator, device_id=device_id))

    async_add_entities(entities)


class MigoRoomBinarySensor(MigoRoomEntity, BinarySensorEntity):
    """MiGO room-based binary sensor using configuration."""

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        room_id: str,
        config: BinarySensorConfig,
    ) -> None:
        """Initialize the room binary sensor."""
        super().__init__(coordinator, room_id)
        self._config = config
        self._attr_unique_id = generate_unique_id(config.unique_id_key, room_id)
        self._attr_translation_key = config.translation_key
        self._attr_device_class = config.device_class
        self._attr_entity_category = config.entity_category

    @property
    def is_on(self) -> bool | None:
        """Return True if the sensor is on."""
        value = self._room_data.get(self._config.data_key)
        if self._config.value_fn:
            return self._config.value_fn(value)
        return value


class _MigoDeviceBinarySensorMixin(BinarySensorEntity):
    """Mixin for device-based binary sensors with common functionality."""

    _config: BinarySensorConfig
    _device_data: dict[str, Any]

    def _init_binary_sensor(self, device_id: str, config: BinarySensorConfig) -> None:
        """Initialize binary sensor attributes from config."""
        self._config = config
        self._attr_unique_id = generate_unique_id(config.unique_id_key, device_id)
        self._attr_translation_key = config.translation_key
        self._attr_device_class = config.device_class
        self._attr_entity_category = config.entity_category

    @property
    def is_on(self) -> bool | None:
        """Return True if the sensor is on."""
        value = self._device_data.get(self._config.data_key)
        if self._config.value_fn:
            return self._config.value_fn(value)
        return value


class MigoGatewayBinarySensor(MigoGatewayEntity, _MigoDeviceBinarySensorMixin):
    """MiGO gateway binary sensor entity."""

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        device_id: str,
        config: BinarySensorConfig,
    ) -> None:
        """Initialize the gateway binary sensor."""
        super().__init__(coordinator, device_id)
        self._init_binary_sensor(device_id, config)


class MigoThermostatBinarySensor(MigoThermostatEntity, _MigoDeviceBinarySensorMixin):
    """MiGO thermostat binary sensor entity."""

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        device_id: str,
        config: BinarySensorConfig,
    ) -> None:
        """Initialize the thermostat binary sensor."""
        super().__init__(coordinator, device_id)
        self._init_binary_sensor(device_id, config)


class MigoAwayModeBinarySensor(MigoGatewayEntity, BinarySensorEntity):
    """MiGO Away (absence) mode binary sensor, home-wide.

    Reads the home-level `therm_mode` field, which the climate entity's
    single room-level `therm_setpoint_mode` cannot represent on its own:
    `therm_mode` is "away" whenever the home-wide Away preset is active,
    independently of the boiler quick-action mode (Normal / DHW only /
    Frost guard). Read-only companion to the `MigoAwayModeSwitch`.

    Diagnostic: the switch is the primary, visible representation in
    Controls; this sensor is for history graphs and automation triggers, so
    it moves to Diagnostic instead of duplicating the switch in "Sensors".

    Reads the same optimistic cache `MigoAwayModeSwitch` writes (via
    `is_home_away`), so toggling the switch is reflected here immediately
    too, rather than lagging one coordinator refresh behind it.
    """

    _attr_translation_key = "away_mode"
    _attr_icon = "mdi:home-export-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: MigoDataUpdateCoordinator, device_id: str) -> None:
        """Initialize the away mode binary sensor."""
        super().__init__(coordinator, device_id)
        self._attr_unique_id = generate_unique_id("away_mode", device_id)

    @property
    def is_on(self) -> bool | None:
        """Return True if away mode is active."""
        return is_home_away(self.coordinator, self._device_id, self._device_data)


def _zone_dhw_module(zone: dict[str, Any], device_id: str) -> dict[str, Any] | None:
    """Find the module entry for `device_id` in a schedule zone.

    Falls back to the zone's single module if there is exactly one, since
    the MiGo app is typically used with a single gateway per home and the
    module entry's `id` field is not always present in the response.

    Args:
        zone: A schedule zone dict (from an "event" schedule).
        device_id: The gateway module id to look up.

    Returns:
        The matching module dict, or None if it cannot be resolved.
    """
    modules = zone.get("modules", [])
    for module in modules:
        if module.get("id") == device_id:
            return module
    if len(modules) == 1:
        return modules[0]
    return None


class MigoDHWScheduleBinarySensor(MigoGatewayEntity, BinarySensorEntity):
    """MiGO scheduled DHW (hot water) state for the currently active time slot.

    Reads the "event"-type schedule paired with the active "therm" schedule
    (via `linked_schedules`, see `get_event_schedule`), resolves which zone
    is active right now from its timetable, and reports that zone's
    `dhw_enabled` flag - the same "Domestic hot water production" toggle
    shown on each temperature slot in the MiGo app. This data was already
    returned by homesdata but read by no entity before.

    Forced to `off` while Away mode is active: the Away temperature slot
    replaces the current schedule slot with hot water production disabled,
    so a plain timetable lookup would be misleading during Away. This
    override applies regardless of whether the schedule/zone can otherwise
    be resolved - Away is checked first, not just on the fully-resolved
    path, since it is known independently of the timetable lookup.

    Reports its state as `unknown` (never a guessed value) when the
    schedule or the active zone cannot be resolved - the entity itself
    stays available, only this one derived value can't be determined.
    """

    _attr_translation_key = "dhw_schedule"
    _attr_icon = "mdi:water-boiler-alert"

    def __init__(self, coordinator: MigoDataUpdateCoordinator, device_id: str) -> None:
        """Initialize the DHW schedule binary sensor."""
        super().__init__(coordinator, device_id)
        self._attr_unique_id = generate_unique_id("dhw_schedule", device_id)
        self._resolved_cache: dict[str, Any] | None = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Invalidate the cached resolution before the base class re-renders state."""
        self._resolved_cache = None
        super()._handle_coordinator_update()

    def _resolve(self) -> dict[str, Any]:
        """Resolve the current DHW schedule state and its extra attributes.

        Cached for the lifetime of the current coordinator data (cleared in
        `_handle_coordinator_update`) - both `is_on` and
        `extra_state_attributes` call this, and it would otherwise fully
        re-run `get_event_schedule()`/`resolve_timetable_zone()` (a sort)
        twice per state write for no reason.

        Returns:
            A dict with "enabled" (bool | None) plus debug attributes
            "schedule_name", "zone_name", "zone_id", "overridden_by_away".
        """
        if self._resolved_cache is not None:
            return self._resolved_cache

        home_id = self._device_data.get("home_id")
        home_data = self.coordinator.homes.get(home_id, {}) if home_id else {}
        overridden_by_away = is_home_away(self.coordinator, self._device_id, self._device_data) or False

        schedule = get_event_schedule(home_data)
        if schedule is None:
            self._resolved_cache = {
                "enabled": False if overridden_by_away else None,
                "overridden_by_away": overridden_by_away,
            }
            return self._resolved_cache

        week_minutes = current_week_minutes()
        zone_id = resolve_timetable_zone(schedule.get("timetable", []), week_minutes)
        zone = next((z for z in schedule.get("zones", []) if z.get("id") == zone_id), None)
        if zone is None:
            self._resolved_cache = {
                "enabled": False if overridden_by_away else None,
                "schedule_name": schedule.get("name"),
                "overridden_by_away": overridden_by_away,
            }
            return self._resolved_cache

        module = _zone_dhw_module(zone, self._device_id)
        enabled = module.get("dhw_enabled") if module is not None else None
        if overridden_by_away:
            enabled = False

        self._resolved_cache = {
            "enabled": enabled,
            "schedule_name": schedule.get("name"),
            "zone_name": zone.get("name"),
            "zone_id": zone_id,
            "overridden_by_away": overridden_by_away,
        }
        return self._resolved_cache

    @property
    def is_on(self) -> bool | None:
        """Return True if scheduled DHW is enabled for the active time slot."""
        return self._resolve().get("enabled")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return debug attributes: which schedule/zone was resolved."""
        resolved = dict(self._resolve())
        resolved.pop("enabled", None)
        return resolved
