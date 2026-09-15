"""Derive one mixed-family execution profile from an observed Red source.

The catalog source, collection observation and cartridge geometry choose the
declarations.  Callers cannot nominate a species or encounter route.  This is
action-free configuration work, not a policy decision or a learned outcome.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import cast

from .collection import CollectionLocation
from .emulator import PyBoyAdapter
from .executor import ReadOnlyController
from .generation_one import GENERATION_ONE_LEVEL_EVOLUTIONS
from .goal_manager import GoalKind
from .goal_manager_context_catalog import GoalManagerContextCapture
from .observation import PokemonRedStateReader
from .red_acquisition import RED_ACQUISITION_CATALOG, RedAcquisitionKind
from .red_collection import red_species_number, red_species_ref
from .red_goal_context import build_red_goal_context_runtime
from .red_goal_context_profile import (
    RedGoalContextProfile,
    RedGoalMechanic,
    _thaw,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)
from .red_goal_manager import RedGoalObservation
from .red_living_dex_multifamily_curriculum import (
    RedLivingDexMultifamilyError,
    map_id_for_wild_source,
)
from .red_living_dex_provider_curriculum import RedEncounterSourceTarget
from .red_living_dex_wild_corridor import (
    RedLivingDexWildCorridor,
    RedLivingDexWildCorridorError,
    derive_red_living_dex_wild_corridor,
)
from .strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld


class RedFullPokedexDirectProfileError(ValueError):
    """The selected source cannot declare both supported acquisition families."""


class RedFullPokedexDirectOriginError(ValueError):
    """The catalog origin was not a stable action-free field observation."""


def _level_evolution(
    observation: RedGoalObservation,
) -> tuple[int, int, int]:
    owned = observation.collection_observation.owned_species
    boxed = {
        specimen.species_ref
        for specimen in observation.collection_observation.specimens
        if specimen.location is CollectionLocation.BOX
    }
    candidates = []
    for source, target, level in GENERATION_ONE_LEVEL_EVOLUTIONS:
        source_ref, target_ref = red_species_ref(source), red_species_ref(target)
        try:
            method = RED_ACQUISITION_CATALOG.method_for(target_ref)
        except ValueError:
            continue
        if (
            target_ref not in owned
            and source_ref in boxed
            and method.kind is RedAcquisitionKind.EVOLUTION
            and method.consumes_species_ref == source_ref
            and method.source_id == f"evolution:level:{level}"
        ):
            candidates.append((source, target, level))
    if not candidates:
        raise RedFullPokedexDirectProfileError(
            "catalog origin has no missing native boxed level evolution"
        )
    return min(candidates, key=lambda row: (row[1], row[0], row[2]))


def _wild_sources(observation: RedGoalObservation) -> Iterable[str]:
    owned = observation.collection_observation.owned_species
    sources: dict[str, tuple[int, int]] = {}
    for method in RED_ACQUISITION_CATALOG.methods:
        if method.kind is RedAcquisitionKind.WILD and method.species_ref not in owned:
            try:
                map_id = int(map_id_for_wild_source(method.source_id))
            except RedLivingDexMultifamilyError:
                continue
            species_number = red_species_number(method.species_ref)
            sources[method.source_id] = (
                min(sources.get(method.source_id, (152, map_id))[0], species_number),
                map_id,
            )
    current_map = observation.raw.map_id
    return tuple(
        source
        for source, _ in sorted(
            sources.items(),
            key=lambda item: (
                item[1][1] != current_map,
                item[1][0],
                item[0],
            ),
        )
    )


def _capture_corridor(
    observation: RedGoalObservation,
    world: StrategicScenarioRouteWorld,
) -> RedLivingDexWildCorridor:
    for source in _wild_sources(observation):
        try:
            map_id = int(map_id_for_wild_source(source))
            return derive_red_living_dex_wild_corridor(
                RedEncounterSourceTarget(source),
                world.terrain[map_id],
                world.local_graphs[map_id],
                excluded=(
                    frozenset(world.object_blockers[map_id])
                    | frozenset(world.macro_graph.warp_locations.get(map_id, ()))
                ),
                cartridge=world.rom,
            )
        except (
            KeyError,
            RedLivingDexMultifamilyError,
            RedLivingDexWildCorridorError,
        ):
            continue
    raise RedFullPokedexDirectProfileError(
        "catalog origin has no missing cartridge-derived wild corridor"
    )


def derive_direct_full_pokedex_profile(
    profile: RedGoalContextProfile,
    observation: RedGoalObservation,
    world: StrategicScenarioRouteWorld,
) -> RedGoalContextProfile:
    """Replace target-bearing declarations with deterministic observed ones."""
    if not isinstance(profile, RedGoalContextProfile):
        raise TypeError("direct full-Pokédex profile needs a source profile")
    if not isinstance(observation, RedGoalObservation):
        raise TypeError("direct full-Pokédex profile needs a Red observation")
    if not isinstance(world, StrategicScenarioRouteWorld):
        raise TypeError("direct full-Pokédex profile needs cartridge route geometry")
    source, target, level = _level_evolution(observation)
    corridor = _capture_corridor(observation, world)
    providers: dict[
        GoalKind, tuple[GoalKind, RedGoalMechanic, Mapping[str, object]]
    ] = {
        spec.kind: (
            spec.kind,
            spec.mechanic,
            cast(Mapping[str, object], _thaw(spec.parameters)),
        )
        for spec in profile.providers
        if spec.kind not in {GoalKind.ACQUIRE_SPECIES, GoalKind.EVOLVE_SPECIES}
    }
    providers[GoalKind.ACQUIRE_SPECIES] = (
        GoalKind.ACQUIRE_SPECIES,
        RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
        corridor.profile_parameters(),
    )
    providers[GoalKind.EVOLVE_SPECIES] = (
        GoalKind.EVOLVE_SPECIES,
        RedGoalMechanic.TARGETED_LEVEL_EVOLUTION,
        {
            "source_species_ref": red_species_ref(source),
            "target_species_ref": red_species_ref(target),
            "evolution_level": level,
        },
    )
    return parse_red_goal_context_profile(
        build_red_goal_context_profile_payload(
            profile_id=profile.profile_id,
            providers=tuple(providers[kind] for kind in GoalKind if kind in providers),
        )
    )


def derive_direct_full_pokedex_profile_from_capture(
    rom_path: Path,
    capture: GoalManagerContextCapture,
    profile: RedGoalContextProfile,
    world: StrategicScenarioRouteWorld,
) -> RedGoalContextProfile:
    """Open one capture read-only and prove derivation leaves it byte-identical."""
    with PyBoyAdapter(rom_path, watch=False, speed=None) as emulator:
        emulator.load_state_bytes(capture.state_bytes)
        before = (
            emulator.save_state_bytes(),
            emulator.frame_count,
            emulator.pressed_buttons,
        )
        controller = ReadOnlyController(emulator)
        runtime = build_red_goal_context_runtime(
            profile=profile,
            capture=capture,
            emulator=controller,
            reader=PokemonRedStateReader(controller),
        )
        observed = runtime.adapter.observe()
        try:
            derived = derive_direct_full_pokedex_profile(profile, observed, world)
        except RedFullPokedexDirectProfileError as error:
            after = (
                emulator.save_state_bytes(),
                emulator.frame_count,
                emulator.pressed_buttons,
            )
            if before != after:
                raise RedFullPokedexDirectOriginError(
                    "direct profile derivation changed its catalog origin"
                ) from error
            raise
        after = (
            emulator.save_state_bytes(),
            emulator.frame_count,
            emulator.pressed_buttons,
        )
        if before != after or observed.raw.battle_state or not observed.input_ready:
            raise RedFullPokedexDirectOriginError(
                "direct profile derivation needs a stable field origin"
            )
    return derived
