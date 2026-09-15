"""Shared entity-description base for MiGO's description-driven entities.

`sensor.py`'s `MigoSensorEntityDescription` and `binary_sensor.py`'s
`MigoBinarySensorEntityDescription` each add their own platform-specific
field on top of this (`extra_attrs_fn`, `ignores_reachability`), but share
these three. `key` (on the Home Assistant base class each also extends) is
cosmetic; `unique_id_key` feeds `generate_unique_id` and must never change
(users would lose recorder history).

`sensor.py`'s `MigoEnergyEntityDescription` deliberately does *not* extend
this: it reads from a `ConsumptionData` record via `value_fn` alone, with no
`data_key` to look up on `_device_data` at all, so a shared `data_key: str`
field would be a required-but-unused one - worse than the one duplicated
`unique_id_key` field it would save.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, kw_only=True)
class MigoEntityDescriptionMixin:
    """Fields shared by every MiGO device-entity-description dataclass."""

    data_key: str
    unique_id_key: str
    value_fn: Callable[[Any], Any] | None = None
