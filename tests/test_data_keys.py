"""Tests that every entity description's data_key exists in the data model.

The sensor and binary sensor platforms look up values dynamically, via
`self._room_data.get(description.data_key)`. Because data_key is a plain str,
the type checker cannot verify it names a real field: a typo would silently
yield None and the entity would sit at "unknown" forever.

Rather than duplicating the model's keys into a Literal union that would drift
from models.py, these tests check the descriptions against the real TypedDicts
at collection time.
"""

from __future__ import annotations

import pytest

from custom_components.migo_netatmo.binary_sensor import (
    GATEWAY_BINARY_SENSORS,
    THERMOSTAT_BINARY_SENSORS,
    MigoBinarySensorEntityDescription,
)
from custom_components.migo_netatmo.models import ModuleData, RoomData
from custom_components.migo_netatmo.sensor import (
    GATEWAY_SENSORS,
    ROOM_SENSORS,
    THERMOSTAT_SENSORS,
    MigoSensorEntityDescription,
)

ROOM_DESCRIPTIONS = [*ROOM_SENSORS]
DEVICE_DESCRIPTIONS = [
    *GATEWAY_SENSORS,
    *THERMOSTAT_SENSORS,
    *GATEWAY_BINARY_SENSORS,
    *THERMOSTAT_BINARY_SENSORS,
]


def _describe(description: MigoSensorEntityDescription | MigoBinarySensorEntityDescription) -> str:
    """Return a readable test id for a description."""
    return f"{description.key}:{description.data_key}"


@pytest.mark.parametrize("description", ROOM_DESCRIPTIONS, ids=_describe)
def test_room_data_key_exists_in_model(description: MigoSensorEntityDescription) -> None:
    """Every room description reads a field RoomData actually declares."""
    assert description.data_key in RoomData.__annotations__, (
        f"{description.key} reads room field '{description.data_key}', "
        f"which RoomData does not declare. Add it to models.py or fix the data_key."
    )


@pytest.mark.parametrize("description", DEVICE_DESCRIPTIONS, ids=_describe)
def test_device_data_key_exists_in_model(
    description: MigoSensorEntityDescription | MigoBinarySensorEntityDescription,
) -> None:
    """Every gateway/thermostat description reads a field ModuleData declares."""
    assert description.data_key in ModuleData.__annotations__, (
        f"{description.key} reads device field '{description.data_key}', "
        f"which ModuleData does not declare. Add it to models.py or fix the data_key."
    )


def test_unique_id_keys_are_unique() -> None:
    """No two descriptions on the same device kind share a unique_id_key.

    A collision would make two entities fight over one registry entry.
    """
    for name, descriptions in (
        ("room", ROOM_DESCRIPTIONS),
        ("gateway", [*GATEWAY_SENSORS, *GATEWAY_BINARY_SENSORS]),
        ("thermostat", [*THERMOSTAT_SENSORS, *THERMOSTAT_BINARY_SENSORS]),
    ):
        keys = [d.unique_id_key for d in descriptions]
        assert len(keys) == len(set(keys)), f"duplicate unique_id_key among {name} descriptions: {keys}"
