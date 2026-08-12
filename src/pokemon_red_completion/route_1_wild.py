"""Bounded, evidence-bearing handling for incidental overworld wild battles."""

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

ROUTE_1_WALKER_APPROACH = (14, 14)
ROUTE_1_WALKER_YIELD = (15, 14)
ROUTE_1_WALKER_CROSSED = (14, 13)
ROUTE_1_WALKER_CLEAR_ATTEMPTS = 24


class ActionExecutor(Protocol):
    def execute(self, action: MacroAction) -> object: ...


@dataclass(frozen=True, slots=True)
class Route1WildFleeEvidence:
    """One incidental encounter dismissed without changing protected state.

    The historical name remains public for compatibility; ``expected_map_id``
    makes the receipt safe for other authored overworld corridors.
    """

    initial_battle_state: int
    final_battle_state: int
    battle_result: int
    expected_map_id: int
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
            and self.map_id == self.expected_map_id
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
            "expected_map": self.expected_map_id,
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


def move_with_wild_flees(
    executor: ActionExecutor,
    reader: PokemonRedStateReader,
    directions: Iterable[str],
    label: str,
    *,
    expected_map_id: MapId,
    route_name: str,
    maximum_flees: int,
    stabilization_frames: int,
    maximum_step_attempts: int,
    step_retry_wait_frames: int,
    error_type: type[Exception],
) -> tuple[RawGameState, tuple[Route1WildFleeEvidence, ...], int]:
    """Follow one map corridor around a finite number of ordinary wilds."""

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
                if moved.battle_state != 1 or moved.map_id != expected_map_id:
                    raise error_type(
                        f"Unexpected non-wild battle interrupted {label} at step {step}."
                    )
                consumed = _direction_was_consumed(before, moved, direction)
                if not consumed and not _same_encounter_boundary(
                    before,
                    moved,
                    expected_map_id,
                ):
                    raise error_type(
                        f"{route_name} wild battle drifted before {label} step {step}."
                    )
                if len(flees) >= maximum_flees:
                    raise error_type(
                        f"{label} exceeded its bounded {maximum_flees}-encounter flee allowance."
                    )
                flees.append(
                    flee_wild(
                        executor,
                        reader,
                        moved,
                        expected_map_id=expected_map_id,
                        route_name=route_name,
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
            if not _same_route_boundary(before, moved, expected_map_id):
                raise error_type(f"{label} step {step} moved outside its requested direction.")
            if _is_route_1_walker_gate(before, direction, expected_map_id):
                crossed, walker_flees, walker_retries = _yield_to_route_1_walker(
                    executor,
                    reader,
                    maximum_flees=maximum_flees - len(flees),
                    stabilization_frames=stabilization_frames,
                    maximum_step_attempts=maximum_step_attempts,
                    step_retry_wait_frames=step_retry_wait_frames,
                    error_type=error_type,
                )
                flees.extend(walker_flees)
                movement_retries += walker_retries + 1
                state = crossed
                break
            if attempt == maximum_step_attempts:
                raise error_type(
                    f"{label} step {step} exceeded its bounded "
                    f"{maximum_step_attempts}-attempt movement allowance."
                )
            movement_retries += 1
            _wait(executor, step_retry_wait_frames)
            state = reader.read()
        else:  # pragma: no cover - the bounded loop always breaks or raises
            raise AssertionError("unreachable bounded movement loop")
    return state, tuple(flees), movement_retries


def _is_route_1_walker_gate(
    state: RawGameState,
    direction: str,
    expected_map_id: MapId,
) -> bool:
    return (
        expected_map_id == MapId.ROUTE_1
        and state.map_id == MapId.ROUTE_1
        and state.battle_state == 0
        and (state.player_x, state.player_y) == ROUTE_1_WALKER_APPROACH
        and direction == "up"
    )


def _yield_to_route_1_walker(
    executor: ActionExecutor,
    reader: PokemonRedStateReader,
    *,
    maximum_flees: int,
    stabilization_frames: int,
    maximum_step_attempts: int,
    step_retry_wait_frames: int,
    error_type: type[Exception],
) -> tuple[RawGameState, tuple[Route1WildFleeEvidence, ...], int]:
    """Create space for Route 1's horizontal youngster at one exact crossing."""

    flees: tuple[Route1WildFleeEvidence, ...] = ()
    movement_retries = 0
    for clear_attempt in range(1, ROUTE_1_WALKER_CLEAR_ATTEMPTS + 1):
        state = reader.read()
        if (
            state.map_id != MapId.ROUTE_1
            or state.battle_state != 0
            or (state.player_x, state.player_y) != ROUTE_1_WALKER_APPROACH
        ):
            raise error_type("Route 1 walker recovery left its exact approach gate.")

        _, new_flees, retries, progressed = _move_walker_step(
            executor,
            reader,
            "right",
            ROUTE_1_WALKER_YIELD,
            maximum_flees=maximum_flees - len(flees),
            stabilization_frames=stabilization_frames,
            maximum_step_attempts=maximum_step_attempts,
            step_retry_wait_frames=step_retry_wait_frames,
            allow_blocked=False,
            error_type=error_type,
        )
        flees += new_flees
        movement_retries += retries
        if not progressed:
            raise error_type("Route 1 walker recovery could not yield east.")

        _wait(executor, step_retry_wait_frames * clear_attempt)
        _, new_flees, retries, progressed = _move_walker_step(
            executor,
            reader,
            "left",
            ROUTE_1_WALKER_APPROACH,
            maximum_flees=maximum_flees - len(flees),
            stabilization_frames=stabilization_frames,
            maximum_step_attempts=maximum_step_attempts,
            step_retry_wait_frames=step_retry_wait_frames,
            allow_blocked=False,
            error_type=error_type,
        )
        flees += new_flees
        movement_retries += retries
        if not progressed:
            raise error_type("Route 1 walker recovery could not restore its approach.")

        crossed, new_flees, retries, progressed = _move_walker_step(
            executor,
            reader,
            "up",
            ROUTE_1_WALKER_CROSSED,
            maximum_flees=maximum_flees - len(flees),
            stabilization_frames=stabilization_frames,
            maximum_step_attempts=1,
            step_retry_wait_frames=step_retry_wait_frames,
            allow_blocked=True,
            error_type=error_type,
        )
        flees += new_flees
        movement_retries += retries
        if progressed:
            return crossed, flees, movement_retries
        movement_retries += 1
    raise error_type("Route 1 youngster did not clear within its bounded retries.")


def _move_walker_step(
    executor: ActionExecutor,
    reader: PokemonRedStateReader,
    direction: str,
    expected_position: tuple[int, int],
    *,
    maximum_flees: int,
    stabilization_frames: int,
    maximum_step_attempts: int,
    step_retry_wait_frames: int,
    allow_blocked: bool,
    error_type: type[Exception],
) -> tuple[RawGameState, tuple[Route1WildFleeEvidence, ...], int, bool]:
    flees: tuple[Route1WildFleeEvidence, ...] = ()
    retries = 0
    for attempt in range(1, maximum_step_attempts + 1):
        before = reader.read()
        executor.execute(MacroAction(MacroActionKind.MOVE, direction))
        moved = reader.read()
        consumed = _direction_was_consumed(before, moved, direction)
        if moved.battle_state:
            if moved.battle_state != 1 or moved.map_id != MapId.ROUTE_1:
                raise error_type("Route 1 walker recovery entered a non-wild battle.")
            if not consumed and not _same_encounter_boundary(before, moved, MapId.ROUTE_1):
                raise error_type("Route 1 walker encounter drifted from its protected step.")
            if len(flees) >= maximum_flees:
                raise error_type("Route 1 walker recovery exhausted its flee allowance.")
            flees += (
                flee_wild(
                    executor,
                    reader,
                    moved,
                    expected_map_id=MapId.ROUTE_1,
                    route_name="Route 1",
                    stabilization_frames=stabilization_frames,
                    error_type=error_type,
                ),
            )
            moved = reader.read()
        if consumed:
            if (moved.player_x, moved.player_y) != expected_position:
                raise error_type("Route 1 walker recovery crossed to an unexpected tile.")
            return moved, flees, retries, True
        if not _same_route_boundary(before, moved, MapId.ROUTE_1):
            raise error_type("Route 1 walker recovery drifted from its protected corridor.")
        if allow_blocked:
            return moved, flees, retries, False
        if attempt == maximum_step_attempts:
            break
        retries = attempt
        _wait(executor, step_retry_wait_frames)
    raise error_type("Route 1 walker recovery exhausted its movement attempts.")


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
    """Compatibility wrapper for the original Route 1 contract."""

    return move_with_wild_flees(
        executor,
        reader,
        directions,
        label,
        expected_map_id=MapId.ROUTE_1,
        route_name="Route 1",
        maximum_flees=maximum_flees,
        stabilization_frames=stabilization_frames,
        maximum_step_attempts=maximum_step_attempts,
        step_retry_wait_frames=step_retry_wait_frames,
        error_type=error_type,
    )


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


def _same_route_boundary(
    before: RawGameState,
    after: RawGameState,
    expected_map_id: MapId,
) -> bool:
    return (
        before.map_id == after.map_id == expected_map_id
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


def _same_encounter_boundary(
    before: RawGameState,
    encounter: RawGameState,
    expected_map_id: MapId,
) -> bool:
    return (
        before.map_id == encounter.map_id == expected_map_id
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


def flee_wild(
    executor: ActionExecutor,
    reader: PokemonRedStateReader,
    encounter: RawGameState,
    *,
    expected_map_id: int,
    route_name: str,
    stabilization_frames: int,
    error_type: type[Exception],
) -> Route1WildFleeEvidence:
    """Select RUN, wait out the handoff, and verify a position-preserving exit."""

    if encounter.battle_state != 1 or encounter.map_id != expected_map_id:
        raise error_type(f"{route_name} flee requires an active wild battle on its route.")
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
                final_battle_state=(raw.battle_state if raw.battle_state is not None else -1),
                battle_result=raw.battle_result if raw.battle_result is not None else -1,
                expected_map_id=int(expected_map_id),
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
                raise error_type(f"{route_name} flee failed its stabilized semantic evidence gate.")
            note_observed_battle_exit()
            return evidence
        if (
            raw.battle_state != 1
            or raw.map_id != expected_map_id
            or expected_position != (raw.player_x, raw.player_y)
            or raw.party_species_ids != expected_party
            or (raw.first_party_hp or 0) <= 0
        ):
            raise error_type(f"{route_name} flee lost its protected encounter boundary.")
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
                raise error_type(f"{route_name} flee exceeded its bounded RUN attempts.")
            executor.execute(MacroAction(MacroActionKind.CONFIRM))
            _wait(executor, 240)
            run_attempts += 1
            continue
        direction = (
            {0: "right", 1: "right", 2: "down"}.get(command) if command is not None else None
        )
        if direction is None:
            raise error_type(f"{route_name} flee exposed an invalid battle-menu cursor.")
        executor.execute(MacroAction(MacroActionKind.MOVE, direction))
        _wait(executor, 120)
    raise error_type(
        f"{route_name} flee exceeded its bounded transition after {run_attempts} RUN attempts."
    )


def flee_route_1_wild(
    executor: ActionExecutor,
    reader: PokemonRedStateReader,
    encounter: RawGameState,
    *,
    stabilization_frames: int,
    error_type: type[Exception],
) -> Route1WildFleeEvidence:
    """Compatibility wrapper for an authenticated Route 1 wild exit."""

    return flee_wild(
        executor,
        reader,
        encounter,
        expected_map_id=MapId.ROUTE_1,
        route_name="Route 1",
        stabilization_frames=stabilization_frames,
        error_type=error_type,
    )


def _wait(executor: ActionExecutor, frames: int) -> None:
    executor.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))
