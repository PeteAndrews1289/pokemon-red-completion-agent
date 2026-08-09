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
    maximum_step_attempts: int,
    step_retry_wait_frames: int,
    error_type: type[Exception],
) -> tuple[RawGameState, tuple[Route1WildFleeEvidence, ...], int]:
    """Follow Route 1 and fail closed around a finite number of ordinary wilds."""

    if type(maximum_flees) is not int or maximum_flees < 0:  # noqa: E721
        raise ValueError("maximum_flees must be a non-negative integer")
    if type(stabilization_frames) is not int or stabilization_frames <= 0:  # noqa: E721
        raise ValueError("stabilization_frames must be a positive integer")
    if type(maximum_step_attempts) is not int or maximum_step_attempts <= 0:  # noqa: E721
        raise ValueError("maximum_step_attempts must be a positive integer")
    if type(step_retry_wait_frames) is not int or step_retry_wait_frames <= 0:  # noqa: E721
        raise ValueError("step_retry_wait_frames must be a positive integer")
    state = reader.read()
    flees: list[Route1WildFleeEvidence] = []
    movement_retries = 0
    for step, direction in enumerate(directions, start=1):
        for attempt in range(1, maximum_step_attempts + 1):
            before = state
            if before.battle_state:
                raise error_type(f"Unexpected battle interrupted {label} before step {step}.")
            executor.execute(MacroAction(MacroActionKind.MOVE, direction))
            moved = reader.read()
            if moved.battle_state:
                if moved.battle_state != 1 or moved.map_id != MapId.ROUTE_1:
                    raise error_type(
                        f"Unexpected non-wild battle interrupted {label} at step {step}."
                    )
                consumed = _direction_was_consumed(before, moved, direction)
                if not consumed and not _same_encounter_boundary(before, moved):
                    raise error_type(
                        f"Route 1 wild battle drifted before {label} step {step}."
                    )
                if len(flees) >= maximum_flees:
                    raise error_type(
                        f"{label} exceeded its bounded {maximum_flees}-encounter flee allowance."
                    )
                flees.append(
                    flee_route_1_wild(
                        executor,
                        reader,
                        moved,
                        stabilization_frames=stabilization_frames,
                        error_type=error_type,
                    )
                )
                state = reader.read()
                if consumed:
                    break
                if attempt == maximum_step_attempts:
                    raise error_type(
                        f"{label} step {step} exceeded its bounded "
                        f"{maximum_step_attempts}-attempt movement allowance after a wild exit."
                    )
                movement_retries += 1
                _wait(executor, step_retry_wait_frames)
                state = reader.read()
                continue
            if moved.first_party_hp == 0:
                raise error_type(f"The active party member fainted during {label}.")
            if _direction_was_consumed(before, moved, direction):
                state = moved
                break
            if not _same_route_boundary(before, moved):
                raise error_type(f"{label} step {step} moved outside its requested direction.")
            if attempt == maximum_step_attempts:
                raise error_type(
                    f"{label} step {step} exceeded its bounded "
                    f"{maximum_step_attempts}-attempt movement allowance."
                )
            movement_retries += 1
            _wait(executor, step_retry_wait_frames)
            state = reader.read()
        else:  # pragma: no cover - the bounded loop always breaks or raises
            raise AssertionError("unreachable Route 1 movement loop")
    return state, tuple(flees), movement_retries


def _direction_was_consumed(
    before: RawGameState,
    after: RawGameState,
    direction: str,
) -> bool:
    if before.map_id != after.map_id:
        return True
    if None in (before.player_x, before.player_y, after.player_x, after.player_y):
        return False
    assert before.player_x is not None
    assert before.player_y is not None
    assert after.player_x is not None
    assert after.player_y is not None
    if direction == "up":
        return after.player_x == before.player_x and after.player_y < before.player_y
    if direction == "down":
        return after.player_x == before.player_x and after.player_y > before.player_y
    if direction == "left":
        return after.player_y == before.player_y and after.player_x < before.player_x
    if direction == "right":
        return after.player_y == before.player_y and after.player_x > before.player_x
    return False


def _same_route_boundary(before: RawGameState, after: RawGameState) -> bool:
    return (
        before.map_id == after.map_id == MapId.ROUTE_1
        and before.player_x == after.player_x
        and before.player_y == after.player_y
        and after.battle_state == 0
        and before.party_species_ids == after.party_species_ids
        and before.first_party_level == after.first_party_level
        and before.first_party_max_hp == after.first_party_max_hp
        and before.first_party_pp == after.first_party_pp
        and before.first_party_status == after.first_party_status
        and before.first_party_hp == after.first_party_hp
    )


def _same_encounter_boundary(before: RawGameState, encounter: RawGameState) -> bool:
    return (
        before.map_id == encounter.map_id == MapId.ROUTE_1
        and before.player_x == encounter.player_x
        and before.player_y == encounter.player_y
        and before.battle_state == 0
        and encounter.battle_state == 1
        and before.party_species_ids == encounter.party_species_ids
        and before.first_party_level == encounter.first_party_level
        and before.first_party_hp == encounter.first_party_hp
        and before.first_party_max_hp == encounter.first_party_max_hp
        and before.first_party_pp == encounter.first_party_pp
        and before.first_party_status == encounter.first_party_status
    )


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
