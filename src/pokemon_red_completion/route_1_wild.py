"""Bounded, evidence-bearing handling for incidental Route 1 wild battles."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_runtime import note_observed_battle_exit
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    MapId,
    PokemonRedStateReader,
    RawGameState,
)


class ActionExecutor(Protocol):
    def execute(self, action: MacroAction) -> object: ...


@dataclass(frozen=True, slots=True)
class Route1WildFleeEvidence:
    """One incidental encounter dismissed without changing protected state."""

    initial_battle_state: int
    final_battle_state: int
    battle_result: int
    map_id: int
    player_x: int
    player_y: int
    enemy_species_id: int
    enemy_level: int
    initial_hp: int
    final_hp: int
    maximum_hp_preserved: bool
    party_preserved: bool
    level_preserved: bool
    pp_preserved: bool
    status_preserved: bool
    control_ready: bool
    run_attempts: int
    stabilization_frames: int

    @property
    def verified(self) -> bool:
        return (
            self.initial_battle_state == 1
            and self.final_battle_state == 0
            and self.battle_result == 2
            and self.map_id == MapId.ROUTE_1
            and self.player_x >= 0
            and self.player_y >= 0
            and self.enemy_species_id > 0
            and self.enemy_level > 0
            and 0 < self.final_hp <= self.initial_hp
            and self.maximum_hp_preserved
            and self.party_preserved
            and self.level_preserved
            and self.pp_preserved
            and self.status_preserved
            and self.control_ready
            and 1 <= self.run_attempts <= 16
            and self.stabilization_frames > 0
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "battle_result": self.battle_result,
            "control_ready": self.control_ready,
            "enemy_level": self.enemy_level,
            "enemy_species_id": self.enemy_species_id,
            "final_battle_state": self.final_battle_state,
            "final_hp": self.final_hp,
            "initial_battle_state": self.initial_battle_state,
            "initial_hp": self.initial_hp,
            "level_preserved": self.level_preserved,
            "map": self.map_id,
            "maximum_hp_preserved": self.maximum_hp_preserved,
            "party_preserved": self.party_preserved,
            "position": [self.player_x, self.player_y],
            "pp_preserved": self.pp_preserved,
            "run_attempts": self.run_attempts,
            "stabilization_frames": self.stabilization_frames,
            "status_preserved": self.status_preserved,
            "verified": self.verified,
        }


def move_route_1_with_wild_flees(
    executor: ActionExecutor,
    reader: PokemonRedStateReader,
    directions: Iterable[str],
    label: str,
    *,
    maximum_flees: int,
    stabilization_frames: int,
    error_type: type[Exception],
) -> tuple[RawGameState, tuple[Route1WildFleeEvidence, ...]]:
    """Follow Route 1 and fail closed around a finite number of ordinary wilds."""

    if type(maximum_flees) is not int or maximum_flees < 0:  # noqa: E721
        raise ValueError("maximum_flees must be a non-negative integer")
    if type(stabilization_frames) is not int or stabilization_frames <= 0:  # noqa: E721
        raise ValueError("stabilization_frames must be a positive integer")
    state = reader.read()
    flees: list[Route1WildFleeEvidence] = []
    for step, direction in enumerate(directions, start=1):
        if state.battle_state:
            raise error_type(f"Unexpected battle interrupted {label} before step {step}.")
        executor.execute(MacroAction(MacroActionKind.MOVE, direction))
        state = reader.read()
        if not state.battle_state:
            if state.first_party_hp == 0:
                raise error_type(f"The active party member fainted during {label}.")
            continue
        if state.battle_state != 1 or state.map_id != MapId.ROUTE_1:
            raise error_type(f"Unexpected non-wild battle interrupted {label} at step {step}.")
        if len(flees) >= maximum_flees:
            raise error_type(
                f"{label} exceeded its bounded {maximum_flees}-encounter flee allowance."
            )
        flees.append(
            flee_route_1_wild(
                executor,
                reader,
                state,
                stabilization_frames=stabilization_frames,
                error_type=error_type,
            )
        )
        state = reader.read()
    return state, tuple(flees)


def flee_route_1_wild(
    executor: ActionExecutor,
    reader: PokemonRedStateReader,
    encounter: RawGameState,
    *,
    stabilization_frames: int,
    error_type: type[Exception],
) -> Route1WildFleeEvidence:
    """Select RUN, wait out the handoff, and verify a position-preserving exit."""

    if encounter.battle_state != 1 or encounter.map_id != MapId.ROUTE_1:
        raise error_type("Route 1 flee requires an active Route 1 wild battle.")
    expected_position = (encounter.player_x, encounter.player_y)
    expected_party = encounter.party_species_ids
    expected_level = encounter.first_party_level
    expected_max_hp = encounter.first_party_max_hp
    expected_pp = encounter.first_party_pp
    expected_status = encounter.first_party_status
    initial_hp = encounter.first_party_hp or 0
    run_attempts = 0
    for _ in range(128):
        raw = reader.read()
        if raw.battle_state == 0:
            if not reader.read_input_readiness().ready:
                _wait(executor, 24)
                continue
            _wait(executor, stabilization_frames)
            raw = reader.read()
            control_ready = reader.read_input_readiness().ready
            evidence = Route1WildFleeEvidence(
                initial_battle_state=encounter.battle_state,
                final_battle_state=(
                    raw.battle_state if raw.battle_state is not None else -1
                ),
                battle_result=raw.battle_result if raw.battle_result is not None else -1,
                map_id=raw.map_id if raw.map_id is not None else -1,
                player_x=raw.player_x if raw.player_x is not None else -1,
                player_y=raw.player_y if raw.player_y is not None else -1,
                enemy_species_id=encounter.enemy_species_id or 0,
                enemy_level=encounter.enemy_level or 0,
                initial_hp=initial_hp,
                final_hp=raw.first_party_hp or 0,
                maximum_hp_preserved=raw.first_party_max_hp == expected_max_hp,
                party_preserved=raw.party_species_ids == expected_party,
                level_preserved=raw.first_party_level == expected_level,
                pp_preserved=raw.first_party_pp == expected_pp,
                status_preserved=raw.first_party_status == expected_status,
                control_ready=control_ready,
                run_attempts=run_attempts,
                stabilization_frames=stabilization_frames,
            )
            if expected_position != (raw.player_x, raw.player_y) or not evidence.verified:
                raise error_type("Route 1 flee failed its stabilized semantic evidence gate.")
            note_observed_battle_exit()
            return evidence
        if (
            raw.battle_state != 1
            or raw.map_id != MapId.ROUTE_1
            or expected_position != (raw.player_x, raw.player_y)
            or raw.party_species_ids != expected_party
            or (raw.first_party_hp or 0) <= 0
        ):
            raise error_type("Route 1 flee lost its protected encounter boundary.")
        menu = reader.read_battle_menu_state(raw)
        if menu.phase is BattleMenuPhase.UNKNOWN:
            executor.execute(MacroAction(MacroActionKind.CANCEL))
            _wait(executor, 240)
            continue
        if menu.phase is BattleMenuPhase.MOVE:
            executor.execute(MacroAction(MacroActionKind.CANCEL))
            _wait(executor, 120)
            continue
        command = menu.selected_main_command
        if command == 3:
            if run_attempts >= 16:
                raise error_type("Route 1 flee exceeded its bounded RUN attempts.")
            executor.execute(MacroAction(MacroActionKind.CONFIRM))
            _wait(executor, 240)
            run_attempts += 1
            continue
        direction = (
            {0: "right", 1: "right", 2: "down"}.get(command)
            if command is not None
            else None
        )
        if direction is None:
            raise error_type("Route 1 flee exposed an invalid battle-menu cursor.")
        executor.execute(MacroAction(MacroActionKind.MOVE, direction))
        _wait(executor, 120)
    raise error_type(
        f"Route 1 flee exceeded its bounded transition after {run_attempts} RUN attempts."
    )


def _wait(executor: ActionExecutor, frames: int) -> None:
    executor.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))
