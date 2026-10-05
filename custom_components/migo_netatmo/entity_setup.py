"""Dynamic entity registration helper shared by MiGO platforms."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import callback

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

    from homeassistant.helpers.entity import Entity
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import MigoConfigEntry
    from .coordinator import MigoDataUpdateCoordinator


def register_dynamic_entities(
    entry: MigoConfigEntry,
    coordinator: MigoDataUpdateCoordinator,
    async_add_entities: AddEntitiesCallback,
    get_current_ids: Callable[[], Iterable[str]],
    create_entities: Callable[[str], Sequence[Entity]],
) -> None:
    """Create entities now, and again whenever new ids appear in coordinator data.

    Satisfies the "dynamic-devices" quality-scale rule: a room or device that
    appears in a later coordinator refresh gets its entities created live,
    without requiring a config entry reload.

    Args:
        entry: The config entry, used to unregister the listener on unload.
        coordinator: The data update coordinator to watch for new ids.
        async_add_entities: The platform's entity-registration callback.
        get_current_ids: Returns the current set of known ids (e.g.
            `coordinator.rooms` or `get_devices_by_type(coordinator, ...)`).
        create_entities: Builds the entities for one newly-seen id. Called
            exactly once per id the first time it is seen, not on every
            refresh for ids already known. May return an empty sequence
            (e.g. a sub-entity gated on data not yet present for that id).
    """
    known_ids: set[str] = set()

    @callback
    def _check_new() -> None:
        new_ids = set(get_current_ids()) - known_ids
        if not new_ids:
            return
        known_ids.update(new_ids)
        new_entities = [entity for id_ in new_ids for entity in create_entities(id_)]
        if new_entities:
            async_add_entities(new_entities)

    _check_new()
    entry.async_on_unload(coordinator.async_add_listener(_check_new))
