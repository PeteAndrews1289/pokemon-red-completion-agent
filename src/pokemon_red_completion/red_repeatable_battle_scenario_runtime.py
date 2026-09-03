"""Natural Red cartridge execution for repeatable battle scenario assignments.

This adapter restores an authenticated source state, uses ordinary controller
input to reach a battle boundary, and returns private state bytes plus their
path-free capture manifest.  It never edits RAM, chooses a move, queries a
teacher, or changes the assignment's inherited train/development lineage.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol, cast

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_recovery import switch_active_battler
from pokemon_red_completion.battle_runtime import advance_battle_to_policy_boundary
from pokemon_red_completion.battle_scenario_capture import (
    build_battle_scenario_capture_payload,
)
from pokemon_red_completion.battle_scenario_source_venue import (
    BattleScenarioSourceVenue,
    battle_scenario_reachable_venues,
)
from pokemon_red_completion.battle_source_conditioning import (
    BATTLE_RESOURCE_CONDITIONING_V1,
)
from pokemon_red_completion.blaine import (
    DIGLETTS_CAVE_TRAINING_VENUE,
    MANSION_TRAINING_VENUE,
    ROUTE_11_TRAINING_VENUE,
    red_training_venues_with_ground_transition,
)
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.executor import (
    ControllerTiming,
    CountingExecutor,
    FrameSafeExecutor,
)
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    MapId,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
    ReadOnlyMemory,
)
from pokemon_red_completion.red_battle_scenario import (
    PreparedRedBattleScenario,
    prepare_red_battle_scenario,
)
from pokemon_red_completion.red_battle_source_conditioning import (
    red_battle_party_identity,
)
from pokemon_red_completion.red_repeatable_battle_scenario_source import (
    adapt_repeatable_red_battle_source,
    red_party_menu_semantic_sha256,
)
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder
from pokemon_red_completion.repeatable_battle_scenario_factory import (
    RepeatableBattleScenarioAssignment,
    RepeatableBattleScenarioKind,
    RepeatableBattleSourceKind,
    RepeatableBattleSourceObservation,
)
from pokemon_red_completion.training_venue import TrainingVenue

_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


class RepeatableRedBattleScenarioSession(Protocol):
    """No-save emulator capabilities needed by the natural materializer."""

    def load_state_bytes(self, payload: bytes) -> None: ...

    def save_state_bytes(self) -> bytes: ...

    def press(self, button: str) -> None: ...

    def release(self, button: str) -> None: ...

    def tick(self, frames: int) -> None: ...

    def read_u8(self, address: int) -> int: ...


RepeatableRedBattleScenarioSessionFactory = Callable[
    [], AbstractContextManager[RepeatableRedBattleScenarioSession]
]


class RepeatableRedBattleScenarioRuntimeError(RuntimeError):
    """Raised when an assignment cannot be executed from its exact source."""


@dataclass(frozen=True, slots=True)
class MaterializedRepeatableRedBattleScenario:
    """Private capture payload and path-free execution evidence."""

    assignment: RepeatableBattleScenarioAssignment
    state_bytes: bytes
    manifest_payload: bytes
    initial_observation_sha256: str
    expected_map: int
    expected_battle_state: int
    controller_actions: int
    encounter_steps: int
    boundary_actions: int
    boundary_frames: int
    switch_actions: int

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.red.battle.repeatable-materialization.v1",
            "scenario_id": self.assignment.scenario_id,
            "source_lineage_id": self.assignment.source_lineage_id,
            "partition": self.assignment.partition.value,
            "scenario_kind": self.assignment.scenario_kind.value,
            "semantic_setup_sha256": self.assignment.semantic_setup_sha256,
            "state_sha256": hashlib.sha256(self.state_bytes).hexdigest(),
            "manifest_sha256": hashlib.sha256(self.manifest_payload).hexdigest(),
            "initial_observation_sha256": self.initial_observation_sha256,
            "expected_map": self.expected_map,
            "expected_battle_state": self.expected_battle_state,
            "pre_encounter_wait_frames": self.assignment.pre_encounter_wait_frames,
            "controller_actions": self.controller_actions,
            "encounter_steps": self.encounter_steps,
            "boundary_actions": self.boundary_actions,
            "boundary_frames": self.boundary_frames,
            "switch_actions": self.switch_actions,
            "memory_edits": 0,
            "move_choices": 0,
            "teacher_queries": 0,
            "private_path_fields": 0,
        }


def materialize_repeatable_red_battle_scenario(
    source: RepeatableBattleSourceObservation,
    assignment: RepeatableBattleScenarioAssignment,
    state_bytes: bytes,
    *,
    rom_bytes: bytes,
    materializer_source_commit: str,
    session_factory: RepeatableRedBattleScenarioSessionFactory,
    controller_timing: ControllerTiming | None = None,
    maximum_encounter_steps: int = 512,
) -> MaterializedRepeatableRedBattleScenario:
    """Execute one frozen assignment using only natural cartridge transitions."""

    _require_materialization_inputs(
        source,
        assignment,
        state_bytes,
        rom_bytes=rom_bytes,
        materializer_source_commit=materializer_source_commit,
        session_factory=session_factory,
        maximum_encounter_steps=maximum_encounter_steps,
    )
    timing = controller_timing or DEFAULT_NEW_GAME_TIMING.controller_timing()
    with session_factory() as session:
        session.load_state_bytes(state_bytes)
        reader = PokemonRedStateReader(cast(ReadOnlyMemory, session))
        raw = reader.read()
        last_blackout_map = reader.read_last_blackout_map()
        current_map_tileset = session.read_u8(RamAddress.CURRENT_MAP_TILESET)
        observed = _adapt_loaded_source(
            raw,
            source=source,
            last_blackout_map=last_blackout_map,
            current_map_tileset=current_map_tileset,
            reader=reader,
        )
        if observed != source:
            raise RepeatableRedBattleScenarioRuntimeError(
                "loaded source differs from its authenticated observation"
            )

        controller = FrameSafeExecutor(session, timing)
        actions = CountingExecutor(controller)
        if assignment.scenario_kind is RepeatableBattleScenarioKind.WILD:
            assert assignment.venue_id is not None
            edge, venue = _selected_venue(
                raw,
                assignment.venue_id,
                last_blackout_map=last_blackout_map,
                current_map_tileset=current_map_tileset,
                rom_bytes=rom_bytes,
            )
            _prepare_source_venue(edge, venue, actions, reader, session)
            if assignment.pre_encounter_wait_frames:
                actions.execute(
                    MacroAction(
                        MacroActionKind.WAIT,
                        repeat=assignment.pre_encounter_wait_frames,
                    )
                )
            prepared, boundary_actions, boundary_frames, switch_actions, steps = (
                _materialize_wild_boundary(
                    assignment,
                    venue,
                    actions,
                    controller,
                    reader,
                    session,
                    maximum_encounter_steps=maximum_encounter_steps,
                )
            )
            expected_map = venue.map_id
            expected_battle_state = 1
        else:
            if assignment.pre_encounter_wait_frames:
                actions.execute(
                    MacroAction(
                        MacroActionKind.WAIT,
                        repeat=assignment.pre_encounter_wait_frames,
                    )
                )
            before_switch = actions.actions_executed
            switch_active_battler(
                actions,
                reader,
                session,
                assignment.party_index,
                expected_battle_state=2,
                label="repeatable trainer scenario materialization",
            )
            switch_actions = actions.actions_executed - before_switch
            prepared = _prepare_capture_boundary(
                assignment,
                reader,
                expected_map=source.expected_map,
                expected_battle_state=2,
            )
            expected_map = source.expected_map
            expected_battle_state = 2
            boundary_actions = 0
            boundary_frames = 0
            steps = 0

        captured_state = session.save_state_bytes()
    if not isinstance(captured_state, bytes) or not captured_state:
        raise RepeatableRedBattleScenarioRuntimeError(
            "emulator returned no materialized state bytes"
        )
    manifest = build_battle_scenario_capture_payload(
        capture_id=assignment.scenario_id,
        root_lineage_id=assignment.source_lineage_id,
        partition=assignment.partition,
        state_bytes=captured_state,
        initial_observation_sha256=prepared.initial_observation_sha256,
        source_commit=materializer_source_commit,
        expected_map=expected_map,
        expected_battle_state=expected_battle_state,
        source_state_sha256=assignment.source_state_sha256,
    )
    return MaterializedRepeatableRedBattleScenario(
        assignment=assignment,
        state_bytes=captured_state,
        manifest_payload=manifest,
        initial_observation_sha256=prepared.initial_observation_sha256,
        expected_map=expected_map,
        expected_battle_state=expected_battle_state,
        controller_actions=actions.actions_executed + boundary_actions,
        encounter_steps=steps,
        boundary_actions=boundary_actions,
        boundary_frames=boundary_frames,
        switch_actions=switch_actions,
    )


def _require_materialization_inputs(
    source: RepeatableBattleSourceObservation,
    assignment: RepeatableBattleScenarioAssignment,
    state_bytes: bytes,
    *,
    rom_bytes: bytes,
    materializer_source_commit: str,
    session_factory: RepeatableRedBattleScenarioSessionFactory,
    maximum_encounter_steps: int,
) -> None:
    if not isinstance(source, RepeatableBattleSourceObservation):
        raise TypeError("source must be a repeatable battle source observation")
    if not isinstance(assignment, RepeatableBattleScenarioAssignment):
        raise TypeError("assignment must be a repeatable battle scenario assignment")
    if not isinstance(state_bytes, bytes) or not state_bytes:
        raise RepeatableRedBattleScenarioRuntimeError("source state bytes are unavailable")
    if hashlib.sha256(state_bytes).hexdigest() != source.state_sha256:
        raise RepeatableRedBattleScenarioRuntimeError("source state digest differs")
    if not isinstance(rom_bytes, bytes) or not rom_bytes:
        raise RepeatableRedBattleScenarioRuntimeError("immutable ROM bytes are unavailable")
    if _GIT_COMMIT.fullmatch(materializer_source_commit) is None:
        raise RepeatableRedBattleScenarioRuntimeError(
            "materializer source commit is invalid"
        )
    if not callable(session_factory):
        raise TypeError("session_factory must be callable")
    if type(maximum_encounter_steps) is not int or maximum_encounter_steps < 1:  # noqa: E721
        raise RepeatableRedBattleScenarioRuntimeError(
            "maximum encounter steps must be positive"
        )
    expected_kind = (
        RepeatableBattleScenarioKind.WILD
        if source.source_kind is RepeatableBattleSourceKind.FIELD
        else RepeatableBattleScenarioKind.TRAINER
    )
    if (
        assignment.source_id != source.source_id
        or assignment.source_lineage_id != source.source_lineage_id
        or assignment.partition is not source.partition
        or assignment.source_state_sha256 != source.state_sha256
        or assignment.source_commit != source.source_commit
        or assignment.scenario_kind is not expected_kind
    ):
        raise RepeatableRedBattleScenarioRuntimeError(
            "assignment differs from its authenticated source"
        )
    option = next(
        (item for item in source.party_options if item.party_index == assignment.party_index),
        None,
    )
    if option is None or option.menu_semantic_sha256 != assignment.menu_semantic_sha256:
        raise RepeatableRedBattleScenarioRuntimeError(
            "assignment party menu differs from its authenticated source"
        )
    if expected_kind is RepeatableBattleScenarioKind.WILD:
        if assignment.venue_id not in source.reachable_venue_ids:
            raise RepeatableRedBattleScenarioRuntimeError(
                "assignment venue is not reachable from its source"
            )
    elif (
        assignment.venue_id is not None
        or (
            assignment.party_index == source.active_party_index
            and assignment.pre_encounter_wait_frames != 0
        )
    ):
        raise RepeatableRedBattleScenarioRuntimeError(
            "trainer assignment is inconsistent with its source boundary"
        )


def _adapt_loaded_source(
    raw: RawGameState,
    *,
    source: RepeatableBattleSourceObservation,
    last_blackout_map: int,
    current_map_tileset: int,
    reader: PokemonRedStateReader,
) -> RepeatableBattleSourceObservation:
    if source.source_kind is RepeatableBattleSourceKind.FIELD:
        venues = battle_scenario_reachable_venues(
            raw,
            last_blackout_map=last_blackout_map,
            current_map_tileset=current_map_tileset,
        )
        active_party_index = None
        venue_ids = tuple(item.venue_id for item in venues)
    else:
        if reader.read_battle_menu_state(raw).phase is not BattleMenuPhase.MAIN:
            raise RepeatableRedBattleScenarioRuntimeError(
                "trainer source is not at the MAIN policy boundary"
            )
        active_party_index = raw.active_party_index
        venue_ids = ()
    return adapt_repeatable_red_battle_source(
        raw,
        source_id=source.source_id,
        source_lineage_id=source.source_lineage_id,
        partition=source.partition,
        state_sha256=source.state_sha256,
        source_commit=source.source_commit,
        source_kind=source.source_kind,
        active_party_index=active_party_index,
        reachable_venue_ids=venue_ids,
    )


def _selected_venue(
    raw: RawGameState,
    venue_id: str,
    *,
    last_blackout_map: int,
    current_map_tileset: int,
    rom_bytes: bytes,
) -> tuple[BattleScenarioSourceVenue, TrainingVenue]:
    reachable = battle_scenario_reachable_venues(
        raw,
        last_blackout_map=last_blackout_map,
        current_map_tileset=current_map_tileset,
    )
    matches = tuple(item for item in reachable if item.venue_id == venue_id)
    if len(matches) != 1:
        raise RepeatableRedBattleScenarioRuntimeError(
            "selected venue cannot be reauthenticated"
        )
    edge = matches[0]
    venues = {
        "route_11": ROUTE_11_TRAINING_VENUE,
        "digletts_cave": DIGLETTS_CAVE_TRAINING_VENUE,
        "pokemon_mansion_1f": MANSION_TRAINING_VENUE,
    }
    venue = venues[venue_id]
    if edge.relocation_required and venue_id in {"route_11", "digletts_cave"}:
        venue = {
            item.area_id: item
            for item in red_training_venues_with_ground_transition(rom_bytes)
        }[venue_id]
    if venue.map_id != edge.encounter_map:
        raise RepeatableRedBattleScenarioRuntimeError(
            "selected venue mechanics differ from its reachable edge"
        )
    return edge, venue


def _prepare_source_venue(
    edge: BattleScenarioSourceVenue,
    venue: TrainingVenue,
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: RepeatableRedBattleScenarioSession,
) -> None:
    raw = reader.read()
    before_identity = None
    relocation_sources = {
        "cinnabar_center": MapId.CINNABAR_POKECENTER,
        "celadon_center_route_11": MapId.CELADON_POKECENTER,
        "lavender_center_route_11": MapId.LAVENDER_POKECENTER,
    }
    if edge.source_location in relocation_sources:
        if raw.map_id != relocation_sources[edge.source_location] or raw.battle_state != 0:
            raise RepeatableRedBattleScenarioRuntimeError(
                "relocation source is not at its expected safe boundary"
            )
        before_identity = red_battle_party_identity(raw)
        venue.heal_and_return(actions, reader, emulator)
    elif edge.source_location in {
        "vermilion_transition_route_11",
        "vermilion_transition_digletts_cave",
    }:
        if raw.battle_state != 0:
            raise RepeatableRedBattleScenarioRuntimeError(
                "portable relocation source is not at a safe boundary"
            )
        before_identity = red_battle_party_identity(raw)
        venue.heal_and_return(actions, reader, emulator)
    elif raw.map_id != venue.map_id or raw.battle_state != 0:
        raise RepeatableRedBattleScenarioRuntimeError(
            "direct source is not at its selected venue boundary"
        )
    prepared = reader.read()
    if prepared.map_id != venue.map_id or prepared.battle_state != 0:
        raise RepeatableRedBattleScenarioRuntimeError(
            "source did not reach its selected encounter venue"
        )
    if before_identity is not None:
        BATTLE_RESOURCE_CONDITIONING_V1.require_identity_preserved(
            before_identity,
            red_battle_party_identity(prepared),
        )


def _materialize_wild_boundary(
    assignment: RepeatableBattleScenarioAssignment,
    venue: TrainingVenue,
    actions: CountingExecutor,
    controller: FrameSafeExecutor,
    reader: PokemonRedStateReader,
    emulator: RepeatableRedBattleScenarioSession,
    *,
    maximum_encounter_steps: int,
) -> tuple[PreparedRedBattleScenario, int, int, int, int]:
    encounter_steps = 0
    walk_calls = 0
    walker = venue.fresh_walk_to_grass()
    while reader.read().battle_state == 0:
        walk_calls += 1
        if walk_calls > maximum_encounter_steps * 4:
            raise RepeatableRedBattleScenarioRuntimeError(
                "wild encounter walker made no bounded progress"
            )
        encounter_steps += walker(actions, reader, emulator)
        if encounter_steps > maximum_encounter_steps:
            raise RepeatableRedBattleScenarioRuntimeError(
                "wild encounter exceeded its step bound"
            )
    boundary = advance_battle_to_policy_boundary(
        reader,
        controller,
        expected_map=venue.map_id,
        expected_battle_state=1,
        timing=venue.battle_timing,
        label="repeatable wild scenario materialization",
    )
    before_switch = actions.actions_executed
    switch_active_battler(
        actions,
        reader,
        emulator,
        assignment.party_index,
        expected_battle_state=1,
        label="repeatable wild scenario materialization",
    )
    switch_actions = actions.actions_executed - before_switch
    prepared = _prepare_capture_boundary(
        assignment,
        reader,
        expected_map=venue.map_id,
        expected_battle_state=1,
    )
    return (
        prepared,
        boundary.actions_executed,
        boundary.frames_executed,
        switch_actions,
        encounter_steps,
    )


def _prepare_capture_boundary(
    assignment: RepeatableBattleScenarioAssignment,
    reader: PokemonRedStateReader,
    *,
    expected_map: int,
    expected_battle_state: int,
) -> PreparedRedBattleScenario:
    raw = reader.read()
    if (
        raw.map_id != expected_map
        or raw.battle_state != expected_battle_state
        or raw.active_party_index != assignment.party_index
        or (raw.battler_hp or 0) <= 0
        or reader.read_battle_menu_state(raw).phase is not BattleMenuPhase.MAIN
    ):
        raise RepeatableRedBattleScenarioRuntimeError(
            "materialized state is not its selected live MAIN boundary"
        )
    if raw.active_party_species_id is None or raw.battler_moves is None or raw.battler_pp is None:
        raise RepeatableRedBattleScenarioRuntimeError(
            "materialized state lacks active party move mechanics"
        )
    if (
        red_party_menu_semantic_sha256(
            species_id=raw.active_party_species_id,
            move_ids=raw.battler_moves,
            current_pp=raw.battler_pp,
        )
        != assignment.menu_semantic_sha256
    ):
        raise RepeatableRedBattleScenarioRuntimeError(
            "materialized party menu differs from its prospective assignment"
        )
    return prepare_red_battle_scenario(
        PokemonRedObservationEncoder.from_state_reader(reader),
        raw,
    )


__all__ = [
    "MaterializedRepeatableRedBattleScenario",
    "RepeatableRedBattleScenarioRuntimeError",
    "RepeatableRedBattleScenarioSession",
    "RepeatableRedBattleScenarioSessionFactory",
    "materialize_repeatable_red_battle_scenario",
]
