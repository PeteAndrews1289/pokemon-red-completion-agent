"""Complete an owned learned trainer battle without issuing a funding verdict.

Fainting is a battle transition, not an identity violation. The ordinary funding
controller still enforces its original no-faints contract independently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .actions import MacroAction, MacroActionKind
from .battle_runtime import BattleActionExecutor, BattleRuntimeTiming
from .observation import PokemonRedStateReader, RawGameState, event_flag_is_set
from .red_learned_trainer import FrozenTrainerBattler, qualified_party_limit, story_party_limit
from .red_trainer_practice_episode import RedTrainerPracticeEpisode


class TrainerBattleLifecycleError(RuntimeError):
    """The continuing battle lost its identity or verifiable handoff."""


@dataclass(frozen=True)
class TrainerBattleCompletion:
    outcome: Literal["won", "lost", "unresolved"]
    field_ready: bool
    recovery_required: bool
    fainted_party_slots: tuple[int, ...]
    money_delta: int
    final_state: RawGameState
    episode: RedTrainerPracticeEpisode

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.red.learned-trainer-completion.v1",
            "outcome": self.outcome,
            "field_ready": self.field_ready,
            "recovery_required": self.recovery_required,
            "fainted_party_slots": list(self.fainted_party_slots),
            "money_delta": self.money_delta,
            "no_faint_constraint_met": not self.fainted_party_slots,
            "funding_success": False,
            "funding_verdict": "not_assessed_by_battle_completion",
            "final_map": self.final_state.map_id,
            "final_party_hp": list(self.final_state.party_hp or ()),
            "episode": self.episode.public_dict(),
        }


def continue_learned_trainer_battle(
    battler: FrozenTrainerBattler,
    reader: PokemonRedStateReader,
    executor: BattleActionExecutor,
    *,
    trainer_identity: tuple[int, int, int],
    defeated_event: int,
    ordinary_victory_money: int,
    timing: BattleRuntimeTiming,
    maximum_settle_pulses: int = 128,
    remaining_decisions: int = 80,
    story_authority: bool = False,
    victory_items: tuple[tuple[int, int], ...] = (),
    victory_badge_bits: int = 0,
) -> TrainerBattleCompletion:
    """Own one continuation; never reload, select teacher moves or retry.

    A win must prove the trainer event and exact payout. A loss must prove
    cartridge blackout, half cash, the recorded recovery map and restored HP.
    Unsupported/budget stops remain unresolved with no settlement inputs.
    """
    if (
        len(trainer_identity) != 3
        or any(type(value) is not int or not 0 <= value <= 255 for value in trainer_identity)
        or type(defeated_event) is not int
        or defeated_event < 0
        or type(ordinary_victory_money) is not int
        or ordinary_victory_money < 0
        or type(maximum_settle_pulses) is not int
        or not 1 <= maximum_settle_pulses <= 128
        or type(remaining_decisions) is not int or not 1 <= remaining_decisions <= 80
        or type(story_authority) is not bool
        or type(victory_badge_bits) is not int or not 0 <= victory_badge_bits <= 255
        or type(victory_items) is not tuple
        or any(type(row) is not tuple or len(row) != 2
               or type(row[0]) is not int or not 1 <= row[0] <= 255
               or type(row[1]) is not int or not 1 <= row[1] <= 99 for row in victory_items)
        or len(dict(victory_items)) != len(victory_items)
        or ((victory_items or victory_badge_bits) and not story_authority)
    ):
        raise ValueError("invalid learned trainer completion contract")
    initial = reader.read()
    party_limit = story_party_limit if story_authority else qualified_party_limit
    if (
        initial.battle_state != 2
        or initial.map_id is None
        or initial.party_count is None
        or not 1 <= initial.party_count <= party_limit(
            getattr(battler, "model_sha256", None),
            getattr(battler, "qualification_sha256", None),
        )
        or initial.party_species_ids is None
        or len(initial.party_species_ids) != initial.party_count
        or initial.bag_items is None
        or initial.event_flags is None
        or defeated_event >= len(initial.event_flags) * 8
        or event_flag_is_set(initial.event_flags, defeated_event)
        or type(initial.player_money) is not int
        or not 0 <= initial.player_money <= 999999
    ):
        raise TrainerBattleLifecycleError("continuation lacks an authenticated active opponent")
    starting_money = initial.player_money
    registrations = frozenset(reader.read_pokedex_state().owned_species)
    blackout_map = reader.read_last_blackout_map()
    fainted: set[int] = set()

    def preserve(raw: RawGameState, *, victory: bool = False) -> None:
        rewards_allowed = (victory and raw.battle_state == 0 and raw.event_flags is not None
                           and event_flag_is_set(raw.event_flags, defeated_event))
        rewarded_bag = dict(initial.bag_items)
        for item, count in victory_items:
            rewarded_bag[item] = rewarded_bag.get(item, 0) + count
        inventory_ok = raw.bag_items == initial.bag_items or (
            rewards_allowed and dict(raw.bag_items or ()) == rewarded_bag)
        badge_ok = raw.badge_bits == initial.badge_bits or (
            rewards_allowed and raw.badge_bits == initial.badge_bits | victory_badge_bits)
        if (
            raw.party_count != initial.party_count
            or raw.party_species_ids != initial.party_species_ids
            or not inventory_ok
            or not badge_ok
            or raw.party_hp is None
            or len(raw.party_hp) != initial.party_count
            or raw.party_max_hp is None
            or len(raw.party_max_hp) != initial.party_count
            or raw.party_status is None
            or len(raw.party_status) != initial.party_count
            or any(
                type(hp) is not int or type(cap) is not int or not 0 <= hp <= cap or cap <= 0
                for hp, cap in zip(raw.party_hp, raw.party_max_hp, strict=True)
            )
        ):
            raise TrainerBattleLifecycleError("party, inventory or HP integrity changed")
        fainted.update(index + 1 for index, hp in enumerate(raw.party_hp) if hp == 0)

    def guard(raw: RawGameState) -> None:
        preserve(raw)
        if (
            raw.battle_state != 2
            or raw.map_id != initial.map_id
            or reader.read_active_trainer_identity() != trainer_identity
            or raw.player_money != starting_money
        ):
            raise TrainerBattleLifecycleError("active trainer identity, map or money changed")

    guard(initial)
    episode = battler.continue_battle(
        reader,
        executor,
        expected_map=initial.map_id,
        timing=timing,
        decision_guard=guard,
        maximum_decisions=remaining_decisions,
        **({"story_authority": True} if story_authority else {}),
    )
    raw = reader.read()
    won = episode.battle_won and episode.stop_reason == "battle_won"
    preserve(raw, victory=won)
    lost = not episode.battle_won and episode.stop_reason == "party_defeated"
    if lost and any(raw.party_hp or ()):
        raise TrainerBattleLifecycleError("loss lacks an observed defeated party")
    if not won and not lost:
        return TrainerBattleCompletion(
            "unresolved",
            False,
            True,
            tuple(sorted(fainted)),
            (raw.player_money or 0) - starting_money,
            raw,
            episode,
        )
    pay_day_money = reader.read_total_pay_day_money()
    if type(pay_day_money) is not int or not 0 <= pay_day_money <= 999999:
        raise TrainerBattleLifecycleError("unreadable terminal Pay Day accumulator")
    expected_money = (
        min(999999, starting_money + ordinary_victory_money + pay_day_money)
        if won
        else starting_money // 2
    )
    for pulse in range(maximum_settle_pulses + 1):
        raw = reader.read()
        preserve(raw, victory=won)
        if raw.battle_state not in {0, 2}:
            raise TrainerBattleLifecycleError("unsupported settlement battle state")
        if raw.battle_state == 2:
            guard(raw)
            if won or any(raw.party_hp or ()):
                raise TrainerBattleLifecycleError("settlement would take an unowned battle choice")
        ready = reader.read_input_readiness().ready
        dialogue = reader.read_bottom_dialogue_box_visible()
        if raw.battle_state == 0 and ready and not dialogue and any(raw.party_hp or ()):
            break
        if pulse == maximum_settle_pulses:
            raise TrainerBattleLifecycleError("battle settlement exhausted its pulse budget")
        if raw.battle_state == 2 or dialogue:
            executor.execute(MacroAction(MacroActionKind.CONFIRM))
        executor.execute(MacroAction(MacroActionKind.WAIT, repeat=timing.dialogue_wait_frames))
    if (
        raw.player_money != expected_money
        or not registrations <= frozenset(reader.read_pokedex_state().owned_species)
        or reader.read_last_blackout_map() != blackout_map
        or raw.map_id != (initial.map_id if won else blackout_map)
        or raw.event_flags is None
        or event_flag_is_set(raw.event_flags, defeated_event) != won
        or (
            won
            and (
                raw.battle_result != 0
                or (raw.player_y, raw.player_x) != (initial.player_y, initial.player_x)
            )
        )
        or (
            lost
            and (
                raw.event_flags != initial.event_flags
                or raw.party_hp != raw.party_max_hp
                or any(raw.party_status or ())
            )
        )
    ):
        raise TrainerBattleLifecycleError("battle field handoff failed outcome verification")
    recovery = raw.party_hp != raw.party_max_hp or any(raw.party_status or ())
    return TrainerBattleCompletion(
        "won" if won else "lost",
        True,
        recovery,
        tuple(sorted(fainted)),
        expected_money - starting_money,
        raw,
        episode,
    )
