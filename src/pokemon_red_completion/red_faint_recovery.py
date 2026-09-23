"""Opt-in one-item field recovery, including an owned Revive.

The goal model chooses recovery versus other goals. Item/target selection is a
declared deterministic skill, not learned item selection or free party healing.
Historical field-healing profiles and all-party-blackout handling are unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass

from .actions import MacroActionKind
from .executor import CountingExecutor
from .field_recovery import EmulatorState, recovery_item_hp
from .goal_manager import GoalFailureReason, GoalKind, GoalUnavailableReason
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .lavender import (
    DEFAULT_LAVENDER_TIMING,
    LavenderTiming,
    _close_menus,
    _select_bag_item,
    _select_cursor,
)
from .observation import ItemId, MenuCursorState, PokemonRedStateReader, RawGameState
from .red_elixir_plan import _same
from .red_goal_manager import PokemonRedGoalStateAdapter, RedGoalBindingOffer, RedGoalObservation
from .victory_road import _pulse


class RedFaintRecoveryError(ValueError):
    """A recovery boundary or exact item effect could not be verified."""


def field_bag_row(cursor: MenuCursorState) -> int:
    """Both native START layouts, with and without the Pokedex entry."""
    count = cursor.maximum_visible_index  # START stores its count, not last row.
    if (
        type(count) is not int
        or count not in (6, 7)
        or (cursor.top_x, cursor.top_y) != (11, 2)
        or type(cursor.selected_visible_index) is not int
        or not 0 <= cursor.selected_visible_index < count
    ):
        raise RedFaintRecoveryError("expected observed START menu before selecting ITEM")
    return count - 5


def _open_bag(
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: EmulatorState,
    timing: LavenderTiming,
) -> None:
    _pulse(actions, MacroActionKind.OPEN_MENU, frames=timing.wait_frames)
    for _ in range(8):
        cursor = reader.read_menu_cursor_state()
        row = field_bag_row(cursor)
        if cursor.selected_visible_index == row:
            _pulse(actions, MacroActionKind.CONFIRM, frames=timing.wait_frames)
            return
        _pulse(
            actions,
            MacroActionKind.MOVE,
            "down" if cursor.selected_visible_index < row else "up",
            frames=timing.wait_frames,
        )
    raise RedFaintRecoveryError("START menu ITEM selection exceeded its bound")


@dataclass(frozen=True, slots=True)
class FieldRecoveryChoice:
    party_index: int
    item: ItemId
    expected_hp: int
    expected_status: int


def plan_faint_aware_recovery(raw: RawGameState) -> FieldRecoveryChoice | None:
    """Choose one useful owned item, fainted first then lowest HP fraction.

    Narrow HP items are preferred over Full Restore. A partial HP gain is a
    real one-item outcome; it is never represented as a fully restored party.
    """
    hp, maximum, status = raw.party_hp, raw.party_max_hp, raw.party_status
    if (
        raw.battle_state != 0
        or type(raw.party_count) is not int
        or not 1 <= raw.party_count <= 6
        or hp is None
        or maximum is None
        or status is None
        or not len(hp) == len(maximum) == len(status) == raw.party_count
        or any(type(v) is not int for values in (hp, maximum, status) for v in values)
        or any(
            not 0 <= h <= m or m < 2 or not 0 <= s <= 255
            for h, m, s in zip(hp, maximum, status, strict=True)
        )
        or not any(hp)
        or raw.bag_items is None
    ):
        raise RedFaintRecoveryError("field recovery requires a coherent living field party")
    if len(dict(raw.bag_items)) != len(raw.bag_items) or any(
        type(i) is not int or type(q) is not int or i <= 0 or not 1 <= q <= 99
        for i, q in raw.bag_items
    ):
        raise RedFaintRecoveryError("field recovery inventory differs")
    bag = dict(raw.bag_items)
    order = sorted(range(len(hp)), key=lambda i: (hp[i] / maximum[i], i))
    for i in order:
        if hp[i] == 0:
            if bag.get(int(ItemId.REVIVE), 0):
                # Gen I shifts the unsigned max HP right once; status is unchanged.
                return FieldRecoveryChoice(i, ItemId.REVIVE, maximum[i] // 2, status[i])
            continue
        items = (
            (ItemId.FULL_RESTORE, ItemId.FULL_HEAL)
            if status[i] and hp[i] < maximum[i]
            else (ItemId.FULL_HEAL, ItemId.FULL_RESTORE)
            if status[i]
            else (ItemId.POTION, ItemId.SUPER_POTION, ItemId.HYPER_POTION, ItemId.FULL_RESTORE)
        )
        for item in items:
            if not bag.get(int(item), 0):
                continue
            after_hp = recovery_item_hp(item, hp[i], maximum[i])
            after_status = 0 if item in (ItemId.FULL_RESTORE, ItemId.FULL_HEAL) else status[i]
            if (after_hp, after_status) != (hp[i], status[i]):
                return FieldRecoveryChoice(i, item, after_hp, after_status)
    return None


def verify_field_recovery(
    choice: FieldRecoveryChoice, before: RawGameState, after: RawGameState
) -> None:
    """Exactly one item and one declared HP/status effect; no unrelated mutation."""
    if plan_faint_aware_recovery(before) != choice:
        raise RedFaintRecoveryError("field recovery choice differs from its origin")
    assert before.party_hp is not None and before.party_status is not None
    assert before.bag_items is not None
    hp, status = list(before.party_hp), list(before.party_status)
    hp[choice.party_index], status[choice.party_index] = choice.expected_hp, choice.expected_status
    bag = tuple(
        (item, left)
        for item, qty in before.bag_items
        if (left := qty - int(item == choice.item)) > 0
    )
    stable = (
        "game_started",
        "battle_state",
        "map_id",
        "player_x",
        "player_y",
        "player_money",
        "party_count",
        "badge_bits",
        "event_flags",
        "party_species_ids",
        "party_levels",
        "party_max_hp",
        "party_moves",
        "party_pp",
    )
    if (
        any(not _same(getattr(before, name), getattr(after, name)) for name in stable)
        or not _same(after.bag_items, bag)
        or not _same(after.bag_item_ids, tuple(i for i, _ in bag))
        or not _same(after.party_hp, tuple(hp))
        or not _same(after.party_status, tuple(status))
    ):
        raise RedFaintRecoveryError("field recovery item effect or preservation differs")


@dataclass(slots=True)
class RedFaintAwareFieldRestoreGoalProvider:
    actions: CountingExecutor
    reader: PokemonRedStateReader
    emulator: EmulatorState
    adapter: PokemonRedGoalStateAdapter
    kind: GoalKind = GoalKind.RESTORE_TEAM

    def offer(self, observation: RedGoalObservation) -> RedGoalBindingOffer:
        if (
            not observation.input_ready
            or self.emulator.pressed_buttons
            or self.reader.read_bottom_dialogue_box_visible()
        ):
            return RedGoalBindingOffer.unavailable(
                self.kind, GoalUnavailableReason.TEMPORARILY_BLOCKED
            )
        try:
            choice = plan_faint_aware_recovery(observation.raw)
        except RedFaintRecoveryError:
            return RedGoalBindingOffer.unavailable(
                self.kind, GoalUnavailableReason.MISSING_CAPABILITY
            )
        if choice is None:
            needy = any(
                h < m or s
                for h, m, s in zip(
                    observation.raw.party_hp or (),
                    observation.raw.party_max_hp or (),
                    observation.raw.party_status or (),
                    strict=True,
                )
            )
            return RedGoalBindingOffer.unavailable(
                self.kind,
                GoalUnavailableReason.MISSING_RESOURCE
                if needy
                else GoalUnavailableReason.NO_LEGAL_TARGET,
            )
        claimed = False
        before = observation.raw
        assert before.party_hp is not None
        receipt = {
            "schema": "pokemon.red.faint-aware-field-recovery.v1",
            "bounded": True,
            "owned_items_consumed": 1,
            "party_index": choice.party_index,
            "item_id": int(choice.item),
            "before_hp": before.party_hp[choice.party_index],
            "after_hp": choice.expected_hp,
            "after_status": choice.expected_status,
            "target_selection": "deterministic_fainted_then_lowest_hp_fraction",
            "learned_authority": "goal_choice_only",
            "whole_party_restored": False,
        }

        def execute() -> GoalExecutionReport:
            nonlocal claimed
            if claimed:
                raise RedFaintRecoveryError("field recovery offer already consumed")
            claimed = True
            if (
                self.adapter.observe() != observation
                or self.emulator.pressed_buttons
                or self.reader.read_bottom_dialogue_box_visible()
                or not self.reader.read_input_readiness().ready
            ):
                raise RedFaintRecoveryError("field recovery origin changed before input")
            start_actions, start_frames = self.actions.actions_executed, self.emulator.frame_count
            timing = DEFAULT_LAVENDER_TIMING
            _open_bag(self.actions, self.reader, self.emulator, timing)
            _select_bag_item(self.actions, self.emulator, choice.item, timing)
            _pulse(self.actions, MacroActionKind.CONFIRM)
            _pulse(self.actions, MacroActionKind.CONFIRM, frames=240)
            _select_cursor(self.actions, self.emulator, choice.party_index, timing)
            _pulse(self.actions, MacroActionKind.CONFIRM)
            for _ in range(24):
                current = self.reader.read()
                if current.bag_items != before.bag_items:
                    # Never confirm again after any consumption, even a wrong effect.
                    verify_field_recovery(choice, before, current)
                    _close_menus(self.actions, self.reader, timing)
                    after = self.adapter.observe()
                    verify_field_recovery(choice, before, after.raw)
                    if not after.input_ready or self.emulator.pressed_buttons:
                        raise RedFaintRecoveryError("field recovery controls did not settle")
                    return GoalExecutionReport(
                        actions_executed=self.actions.actions_executed - start_actions,
                        frames_executed=self.emulator.frame_count - start_frames,
                        evidence=dict(receipt),
                    )
                _pulse(self.actions, MacroActionKind.CONFIRM)
            raise RedFaintRecoveryError("field recovery item was not consumed within bound")

        def verify(report: GoalExecutionReport) -> GoalVerification:
            after = self.adapter.observe()
            try:
                verify_field_recovery(choice, before, after.raw)
            except RedFaintRecoveryError:
                return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
            if (
                not claimed
                or report.actions_executed <= 0
                or report.evidence != receipt
                or not after.input_ready
                or self.emulator.pressed_buttons
                or after.collection_observation != observation.collection_observation
                or self.adapter.graph.completed_ids(after.game_state)
                != self.adapter.graph.completed_ids(observation.game_state)
            ):
                return GoalVerification.failed(GoalFailureReason.WORLD_STATE_DIVERGED)
            return GoalVerification.succeeded()

        return RedGoalBindingOffer.available(
            ExecutableGoalBinding(
                binding_ref="pokemon.red:recovery:one-owned-faint-aware-item",
                kind=self.kind,
                estimated_effort=0.08,
                estimated_risk=0.03,
                execute=execute,
                verify=verify,
            )
        )
