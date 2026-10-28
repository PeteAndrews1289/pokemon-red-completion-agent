"""Opt-in bounded one-off ball execution, preserving rather than fleeing.

This is deterministic mechanical support, not a learned capture policy. A
caller selects the exact ball and budget. Exhaustion/unsafe state raises with
the live encounter retained. No Run, attack, reset, or fallback is available.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from .actions import MacroActionKind
from .capture_survey import (
    capture_diagnostic_observation,
    capture_execution_counters,
    record_capture_diagnostic,
)
from .executor import CountingExecutor
from .observation import BattleMenuPhase, ItemId, PokemonRedStateReader, RawGameState
from .red_collection import red_internal_species_number


class OneOffCapturePaused(RuntimeError):
    """No automatic flee: caller must retain state and the reason for stopping."""


@dataclass(frozen=True, slots=True)
class OneOffCaptureRequest:
    internal_species: int
    level: int
    ball: ItemId

    def __post_init__(self) -> None:
        if type(self.internal_species) is not int:
            raise ValueError("one-off species must be an internal species integer")
        red_internal_species_number(self.internal_species)
        if type(self.level) is not int or not 1 <= self.level <= 100:
            raise ValueError("one-off level is invalid")
        if not isinstance(self.ball, ItemId) or self.ball not in {
            ItemId.MASTER_BALL,
            ItemId.ULTRA_BALL,
            ItemId.GREAT_BALL,
            ItemId.POKE_BALL,
        }:
            raise ValueError("one-off capture requires an explicitly selected ball")


@dataclass(slots=True)
class OneOffCaptureBudget:
    """Encounter-wide allocation, retained by the caller even on exceptions.

    A commitment precedes input: interrupted selection cannot silently grant a
    second attempt. Resume requires the observed ball count to match exactly.
    This is accounting, not save authentication: a persisted caller must bind
    this record to its retained state/encounter and original allocation receipt.
    """

    request: OneOffCaptureRequest
    max_throws: int
    initial_ball_count: int
    throws_committed: int = 0

    def validate(self) -> None:
        if (
            not isinstance(self.request, OneOffCaptureRequest)
            or type(self.max_throws) is not int
            or not 1 <= self.max_throws <= 99
            or type(self.initial_ball_count) is not int
            or not 0 <= self.initial_ball_count <= 99
            or type(self.throws_committed) is not int
            or not 0 <= self.throws_committed <= min(self.max_throws, self.initial_ball_count)
        ):
            raise ValueError("invalid encounter-wide capture budget")

    def __post_init__(self) -> None:
        self.validate()


def settle_caught_one_off_transfer(
    emulator,
    executor,
    reader,
    request: OneOffCaptureRequest,
    *,
    before_throw: RawGameState,
    initial_owned: frozenset[int],
    initial_specimens: Counter[int],
    expected_bag: dict[int, int],
    maximum_pulses: int = 96,
) -> bool:
    """Settle an already-registered catch; never select or throw another ball.

    Gen I updates the owned bit and box species list before copying all box
    structures. Reading the complete box during that transfer falsely rejects
    a valid capture. Wait through that transient using only cancellation, then
    require exact specimen/inventory proof at the settled field boundary.
    A retained-state caller must authenticate the original throw and evidence;
    this helper grants no retry or additional allocation.
    """
    from .surge import _bag, _pulse

    if type(maximum_pulses) is not int or not 1 <= maximum_pulses <= 96:
        raise ValueError("capture transfer settlement limit differs")
    number = red_internal_species_number(request.internal_species)
    expected_owned = initial_owned | {number}
    count = before_throw.party_count
    if number in initial_owned or type(count) is not int or not 1 <= count <= 6:
        raise OneOffCapturePaused("capture transfer lacks its original party/registration")
    for _ in range(maximum_pulses):
        raw = reader.read()
        if (
            raw.battle_state not in (0, 1)
            or raw.map_id != before_throw.map_id
            or (raw.player_y, raw.player_x) != (before_throw.player_y, before_throw.player_x)
            or raw.player_money != before_throw.player_money
            or reader.read_pokedex_state().owned_species != expected_owned
            or raw.party_count not in {count, min(6, count + 1)}
        ):
            raise OneOffCapturePaused("capture transfer changed protected boundary")
        for name in ("party_species_ids", "party_pp", "party_hp", "party_status",
                     "party_moves", "party_levels", "party_max_hp"):
            old, new = getattr(before_throw, name), getattr(raw, name)
            if old is not None and (new is None or new[:count] != old):
                raise OneOffCapturePaused("capture transfer changed original party or PP")
        if raw.party_species_ids is None or len(raw.party_species_ids) != raw.party_count:
            raise OneOffCapturePaused("capture transfer party inventory unavailable")
        if raw.party_count > count and raw.party_species_ids[count:] != (request.internal_species,):
            raise OneOffCapturePaused("capture transfer appended a different species")
        if (
            raw.battle_state == 0
            and reader.read_input_readiness().ready
            and not reader.read_bottom_dialogue_box_visible()
        ):
            boxes = reader.read_all_box_states()
            specimens = Counter(raw.party_species_ids) + Counter(
                species for box in boxes.boxes for species in box.species_ids
            )
            if (
                specimens != initial_specimens + Counter({request.internal_species: 1})
                or {k: v for k, v in _bag(emulator).items() if v} != expected_bag
            ):
                raise OneOffCapturePaused("capture registration/specimen or ball-spend mismatch")
            return True
        _pulse(executor, MacroActionKind.CANCEL, frames=120)
    raise OneOffCapturePaused("capture transfer settlement bound exhausted")


def run_one_off_capture(
    emulator,
    executor: CountingExecutor,
    reader: PokemonRedStateReader,
    request: OneOffCaptureRequest,
    *,
    max_throws: int,
    before_throw: Callable[[], bool] | None = None,
    record_decision: Callable[[dict[str, object]], None] | None = None,
    budget: OneOffCaptureBudget | None = None,
    select_replacement: Callable[[RawGameState], int] | None = None,
    commit_throw: Callable[[OneOffCaptureBudget], None] | None = None,
) -> bool:
    """Start at a settled wild MAIN menu; verify exact registration + specimen.

    A preparation callback may apply nondamaging status but must preserve target
    HP, collection and bag. Master Ball skips preparation. Reaching a limit is a
    paused development episode, not a successful autonomous recovery decision.
    """
    from .battle_recovery import switch_active_battler
    from .surge import _bag, _navigate_main, _pulse, _select_bag_item

    if type(max_throws) is not int or not 1 <= max_throws <= 99:
        raise ValueError("one-off throw budget must be between 1 and 99")
    species_number = red_internal_species_number(request.internal_species)
    start = reader.read()
    initial_owned = reader.read_pokedex_state().owned_species

    def specimens() -> Counter[int]:
        raw = reader.read()
        if raw.party_species_ids is None or raw.party_count != len(raw.party_species_ids):
            raise OneOffCapturePaused("party inventory unavailable")
        boxes = reader.read_all_box_states()
        return Counter(raw.party_species_ids) + Counter(
            species for box in boxes.boxes for species in box.species_ids
        )

    initial_specimens = specimens()
    initial_bag = dict(_bag(emulator))
    if budget is None:
        budget = OneOffCaptureBudget(request, max_throws, initial_bag.get(request.ball, 0))
    budget.validate()
    if budget.request != request or budget.max_throws != max_throws:
        raise OneOffCapturePaused("resumed capture request/allocation differs")
    previous_throws = budget.throws_committed
    if initial_bag.get(request.ball, 0) != budget.initial_ball_count - previous_throws:
        raise OneOffCapturePaused("resumed ball count differs from retained allocation")
    if previous_throws >= min(budget.max_throws, budget.initial_ball_count) and previous_throws:
        raise OneOffCapturePaused("throw budget exhausted; live encounter retained without Run")
    initial_pp = start.party_pp
    if initial_pp is None:
        raise OneOffCapturePaused("party PP evidence unavailable")

    def protected_inventory(throws: int) -> None:
        expected = dict(initial_bag)
        expected[request.ball] = expected.get(request.ball, 0) - (throws - previous_throws)
        if expected[request.ball] < 0:
            raise OneOffCapturePaused("ball budget accounting underflow")
        expected = {k: v for k, v in expected.items() if v}
        if {k: v for k, v in _bag(emulator).items() if v} != expected:
            raise OneOffCapturePaused("bag changed beyond selected ball spend")
        raw = reader.read()
        if raw.map_id != start.map_id or raw.player_money != start.player_money:
            raise OneOffCapturePaused("map or money changed")

    def live_boundary(*, allow_fainted: bool = False) -> None:
        raw = reader.read()
        identity = reader.read_wild_capture_identity()
        if (
            raw.battle_state != 1
            or identity is None
            or identity.original_species_id != request.internal_species
            or raw.enemy_level != request.level
            or not raw.enemy_hp
            or (not allow_fainted and (
                (raw.battler_hp or 0) <= 0
                or reader.read_battle_menu_state(raw).phase is not BattleMenuPhase.MAIN
            ))
        ):
            raise OneOffCapturePaused("one-off target/lead/MAIN boundary unavailable")
        if (
            specimens() != initial_specimens
            or reader.read_pokedex_state().owned_species != initial_owned
        ):
            raise OneOffCapturePaused("collection changed during live encounter")

    def replace_fainted(throws: int) -> None:
        raw = reader.read()
        if (raw.battler_hp or 0) > 0:
            return
        live_boundary(allow_fainted=True)
        protected_inventory(throws)
        if select_replacement is None:
            raise OneOffCapturePaused("catcher fainted; no automatic replacement or Run")
        if raw.party_hp is None or raw.party_pp is None:
            raise OneOffCapturePaused("replacement party evidence unavailable")
        slot = select_replacement(raw)
        if (
            type(slot) is not int
            or not 0 <= slot < len(raw.party_hp)
            or raw.party_hp[slot] <= 0
            or slot == raw.active_party_index
        ):
            raise OneOffCapturePaused("replacement choice is not a living reserve")
        if record_decision is not None:
            record_decision({"directive": "replace_fainted_catcher", "party_slot": slot + 1,
                             "throws_committed": throws, "learned": False})
        switch_active_battler(executor, reader, emulator, slot, expected_battle_state=1,
                              label="one-off capture replacement", wait_frames=120)
        after = reader.read()
        live_boundary()
        protected_inventory(throws)
        if (
            after.active_party_index != slot
            or after.enemy_hp != raw.enemy_hp
            or after.party_pp != raw.party_pp
            or after.party_species_ids != raw.party_species_ids
        ):
            raise OneOffCapturePaused("replacement changed protected target/party state")

    live_boundary(allow_fainted=(start.battler_hp or 0) <= 0)
    if species_number in initial_owned:
        raise OneOffCapturePaused("one-off target is already registered")
    boxes = reader.read_all_box_states()
    current_box = boxes.boxes[boxes.current_box_index]
    if start.party_count is None or (start.party_count >= 6 and len(current_box.species_ids) >= 20):
        raise OneOffCapturePaused("no room in party or current box")
    if not initial_bag.get(request.ball, 0):
        raise OneOffCapturePaused("selected ball unavailable; encounter retained")

    replace_fainted(previous_throws)
    live_boundary()
    for throw in range(previous_throws + 1, min(max_throws, budget.initial_ball_count) + 1):
        protected_inventory(throw - 1)
        live_boundary()
        if before_throw is not None and request.ball is not ItemId.MASTER_BALL:
            before_preparation = reader.read()
            moves_reader = getattr(reader, "read_enemy_capture_moves", lambda: None)
            status_reader = getattr(reader, "read_enemy_capture_status", lambda: None)
            before_moves = moves_reader()
            if not before_throw():
                raise OneOffCapturePaused("preparation ended encounter; inspect retained state")
            live_boundary()
            protected_inventory(throw - 1)
            after_preparation = reader.read()
            if after_preparation.enemy_hp != before_preparation.enemy_hp:
                from .red_capture_status_runtime import observed_rest_recovery
                if not observed_rest_recovery(
                    before_preparation, after_preparation, before_moves,
                    moves_reader(), status_reader(),
                ):
                    raise OneOffCapturePaused("preparation changed target HP")
        raw = reader.read()
        throw_start = raw
        pp_before_throw = raw.party_pp
        throw_counters = capture_execution_counters(emulator, executor)
        ball_quantity = dict(_bag(emulator)).get(request.ball, 0)
        record_capture_diagnostic(
            executor, "capture_throw_started", raw, source="one_off",
            throw=throw, ball=request.ball, ball_quantity=ball_quantity,
        )

        def finish_throw(outcome, state):
            record_capture_diagnostic(
                executor, "capture_throw_completed", state, source="one_off",
                throw=throw, ball=request.ball,
                ball_quantity=dict(_bag(emulator)).get(request.ball, 0),
                outcome=outcome, before_counters=throw_counters,
                counters=capture_execution_counters(emulator, executor),
            )

        if record_decision is not None:
            record_decision(
                {
                    "directive": "throw_ball",
                    "ball": int(request.ball),
                    "throw": throw,
                    "target_hp": raw.enemy_hp,
                    "catcher_hp": raw.battler_hp,
                    "capture_context": capture_diagnostic_observation(
                        raw, ball=request.ball, ball_quantity=ball_quantity
                    ),
                    "learned": False,
                }
            )
        budget.throws_committed = throw
        if commit_throw is not None:
            # Write-ahead intent must succeed before any ball-menu input. A
            # failed callback retains the committed count; it is not a retry.
            commit_throw(budget)
        _navigate_main(executor, reader, 1)
        _pulse(executor, MacroActionKind.CONFIRM)
        _select_bag_item(emulator, executor, request.ball)
        _pulse(executor, MacroActionKind.CONFIRM, frames=360)
        for _ in range(96):
            raw = reader.read()
            if reader.read_pokedex_state().owned_species == initial_owned | {species_number}:
                expected_bag = dict(initial_bag)
                expected_bag[request.ball] -= throw - previous_throws
                caught = settle_caught_one_off_transfer(
                    emulator, executor, reader, request,
                    before_throw=throw_start,
                    initial_owned=initial_owned,
                    initial_specimens=initial_specimens,
                    expected_bag={k: v for k, v in expected_bag.items() if v},
                )
                finish_throw("specimen_and_registration_verified", reader.read())
                return caught
            # Gen I can append the caught member (and its PP) while battle=1
            # and before ball removal/nickname settlement. Protect the original
            # party prefix; do not treat this transient as a second live turn.
            caught_pending = specimens() == initial_specimens + Counter(
                {request.internal_species: 1}
            ) and reader.read_pokedex_state().owned_species == initial_owned | {species_number}
            original_count = len(pp_before_throw or ())
            if (
                raw.party_pp is None
                or pp_before_throw is None
                or raw.party_pp[:original_count] != pp_before_throw
                or raw.party_species_ids is None
                or start.party_species_ids is None
                or raw.party_species_ids[:original_count] != start.party_species_ids
                or len(raw.party_pp)
                != original_count + int(caught_pending and len(start.party_species_ids) < 6)
            ):
                raise OneOffCapturePaused("ball turn unexpectedly changed original party or PP")
            if raw.map_id != start.map_id or raw.battle_state not in (0, 1):
                raise OneOffCapturePaused("one-off encounter exited its supported state")
            if raw.battle_state == 0:
                # B declines nicknames and cannot select an attack. Settle to
                # an actual field boundary, not an early battle-state byte.
                if (
                    reader.read_input_readiness().ready
                    and not reader.read_bottom_dialogue_box_visible()
                ):
                    protected_inventory(throw)
                    after = specimens()
                    owned = reader.read_pokedex_state().owned_species
                    if after == initial_specimens + Counter(
                        {request.internal_species: 1}
                    ) and owned == initial_owned | {species_number}:
                        finish_throw("specimen_and_registration_verified", raw)
                        return True
                    if after == initial_specimens and owned == initial_owned:
                        finish_throw("encounter_ended_without_retention", raw)
                        return False
                    raise OneOffCapturePaused("capture registration/specimen mismatch")
            else:
                if (raw.battler_hp or 0) <= 0:
                    finish_throw("catcher_fainted_live_encounter", raw)
                    # Do not spend a recovery turn when no further ball is
                    # authorized. A later caller must not refill this budget.
                    if throw >= min(max_throws, budget.initial_ball_count):
                        raise OneOffCapturePaused("throw budget exhausted at catcher faint")
                    replace_fainted(throw)
                    break
                phase = reader.read_battle_menu_state(raw).phase
                if phase is BattleMenuPhase.MAIN and not caught_pending:
                    protected_inventory(throw)
                    live_boundary()
                    finish_throw("not_caught_live_encounter", raw)
                    break
                if phase is BattleMenuPhase.MOVE and not caught_pending:
                    raise OneOffCapturePaused("unowned move menu during ball settlement")
            _pulse(executor, MacroActionKind.CANCEL, frames=120)
        else:
            finish_throw("unsettled_after_limit", raw)
            raise OneOffCapturePaused("ball settlement bound exhausted")
    raise OneOffCapturePaused("throw budget exhausted; live encounter retained without Run")
