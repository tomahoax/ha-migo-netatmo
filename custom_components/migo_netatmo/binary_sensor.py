"""Binary sensor platform for MiGO integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEVICE_TYPE_GATEWAY, DEVICE_TYPE_THERMOSTAT
from .entity import MigoGatewayEntity, MigoThermostatEntity, register_dynamic_entities
from .helpers import generate_unique_id, get_devices_by_type

if TYPE_CHECKING:
    from . import MigoConfigEntry
    from .coordinator import MigoDataUpdateCoordinator

# Coordinator-driven read-only platform
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class MigoBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a MiGO binary sensor entity.

    The key field is cosmetic; unique_id_key feeds generate_unique_id and
    must never change (users would lose recorder history).
    """

    data_key: str
    unique_id_key: str
    value_fn: Callable[[Any], bool | None] | None = None
    # Connectivity diagnostics stay available while reporting unreachable
    ignores_reachability: bool = False


# This integration exposes no room-level binary sensors: every boolean the API
# reports (boiler status, eBus/boiler errors, reachability) belongs to a gateway
# or a thermostat module, not to a room. Add a ROOM_BINARY_SENSORS tuple, a room
# entity class and a register_dynamic_entities() call together if that changes.

# Gateway binary sensor configurations
GATEWAY_BINARY_SENSORS: tuple[MigoBinarySensorEntityDescription, ...] = (
    MigoBinarySensorEntityDescription(
        key="ebus_error",
        data_key="ebus_error",
        unique_id_key="ebus_error",
        translation_key="ebus_error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    MigoBinarySensorEntityDescription(
        key="boiler_error",
        data_key="boiler_error",
        unique_id_key="boiler_error",
        translation_key="boiler_error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda v: bool(v) if v is not None else None,
    ),
)

# Thermostat binary sensor configurations
THERMOSTAT_BINARY_SENSORS: tuple[MigoBinarySensorEntityDescription, ...] = (
    MigoBinarySensorEntityDescription(
        key="boiler_status",
        data_key="boiler_status",
        unique_id_key="boiler_status",
        translation_key="boiler_status",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    MigoBinarySensorEntityDescription(
        key="reachable",
        data_key="reachable",
        unique_id_key="reachable",
        translation_key="reachable",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        ignores_reachability=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MigoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up MiGO binary sensor entities."""
    coordinator = entry.runtime_data.coordinator

    register_dynamic_entities(
        entry,
        coordinator,
        async_add_entities,
        get_current_ids=lambda: get_devices_by_type(coordinator, DEVICE_TYPE_GATEWAY),
        create_entities=lambda device_id: [
            MigoGatewayBinarySensor(coordinator=coordinator, device_id=device_id, description=description)
            for description in GATEWAY_BINARY_SENSORS
        ],
    )

    register_dynamic_entities(
        entry,
        coordinator,
        async_add_entities,
        get_current_ids=lambda: get_devices_by_type(coordinator, DEVICE_TYPE_THERMOSTAT),
        create_entities=lambda device_id: [
            MigoThermostatBinarySensor(coordinator=coordinator, device_id=device_id, description=description)
            for description in THERMOSTAT_BINARY_SENSORS
        ],
    )


class _MigoDeviceBinarySensorMixin(BinarySensorEntity):
    """Mixin for device-based binary sensors with common functionality."""

    entity_description: MigoBinarySensorEntityDescription

    @property
    def _device_data(self) -> dict[str, Any]:
        """Get current device data.

        Read-only stub: the concrete entity's MRO always resolves this to
        MigoDeviceEntity._device_data (see MigoGatewayBinarySensor/
        MigoThermostatBinarySensor below). Declared here, matching that
        base's read-only property, so static type checkers accept the
        multiple inheritance.
        """
        raise NotImplementedError

    def _init_binary_sensor(self, device_id: str, description: MigoBinarySensorEntityDescription) -> None:
        """Initialize binary sensor attributes from the entity description."""
        self.entity_description = description
        self._ignore_reachable = description.ignores_reachability
        self._attr_unique_id = generate_unique_id(description.unique_id_key, device_id)

    @property
    def is_on(self) -> bool | None:
        """Return True if the sensor is on."""
        value = self._device_data.get(self.entity_description.data_key)
        if self.entity_description.value_fn:
            return self.entity_description.value_fn(value)
        return value


class MigoGatewayBinarySensor(MigoGatewayEntity, _MigoDeviceBinarySensorMixin):
    """MiGO gateway binary sensor entity."""

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        device_id: str,
        description: MigoBinarySensorEntityDescription,
    ) -> None:
        """Initialize the gateway binary sensor."""
        super().__init__(coordinator, device_id)
        self._init_binary_sensor(device_id, description)


class MigoThermostatBinarySensor(MigoThermostatEntity, _MigoDeviceBinarySensorMixin):
    """MiGO thermostat binary sensor entity."""

    def __init__(
        self,
        coordinator: MigoDataUpdateCoordinator,
        device_id: str,
        description: MigoBinarySensorEntityDescription,
    ) -> None:
        """Initialize the thermostat binary sensor."""
        super().__init__(coordinator, device_id)
        self._init_binary_sensor(device_id, description)
