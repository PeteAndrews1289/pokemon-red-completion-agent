"""Compose separately selectable native Silph components and honest completion."""

from hashlib import sha256

from .gen1_trainer_parties import trainer_party_quote
from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .observation import EventFlag, ItemId, MapId, event_flag_is_set
from .player_option_challenge import OptionChallenge
from .red_goal_skills import _raw_party_fully_restored
from .red_player_field_goals import _field_ready
from .red_player_lesson import capture_player_lesson_snapshot
from .red_player_story_travel import story_travel_binding
from .red_silph_continuation import run_learned_silph_continuation, silph_continuation_contract
from .red_silph_learned_phase import (
    run_learned_silph_card_key_phase,
    silph_card_key_battle_contract,
)
from .red_silph_reward import collect_silph_reward
from .red_story_battle import FrozenStoryBattleController


def silph_card_key_story_option(
    runtime,
    actions,
    _,
    *,
    route,
    battler,
    battler_for_contract=None,
    continuous_travel=False,
    allow_surf=False,
    record=None,
):
    if battler_for_contract is not None and not callable(battler_for_contract):
        raise TypeError("Silph battler resolver must be callable")
    if type(continuous_travel) is not bool or type(allow_surf) is not bool:
        raise TypeError("Silph travel flags must be boolean")
    if allow_surf and getattr(route, "allow_surf", False) is not True:
        raise ValueError("Silph travel requires a Surf-enabled native executor")
    if record is not None and not callable(record):
        raise TypeError("Silph record must be callable")
    if not _field_ready(runtime):
        return None
    before, lesson = capture_player_lesson_snapshot(runtime)
    raw = before.raw
    if (
        "liberate_silph"
        not in {o.id for o in runtime.adapter.graph.available_objectives(before.game_state)}
        or raw.bag_items is None
        or len(raw.bag_items) >= 20
        or dict(raw.bag_items).get(int(ItemId.CARD_KEY), 0)
        or event_flag_is_set(raw.event_flags, int(EventFlag.BEAT_SILPH_CO_5F_TRAINER_0))
    ):
        return None
    # This executor already requires a restored entry. Advertising travel
    # before that prerequisite creates Center/other-story detours that cannot
    # reach this phase. Genuine nurse/preparation peers retain the decision.
    if not _raw_party_fully_restored(raw):
        return None
    center = raw.map_id == int(MapId.SAFFRON_POKECENTER)
    at_entry = center and (raw.player_y, raw.player_x) == (3, 3)
    if not at_entry:
        binding = story_travel_binding(
            runtime,
            actions,
            objective_id="liberate_silph",
            route=route,
            destination_at=(3, 3) if center else None,
            route_destination_at=(3, 3) if not center and continuous_travel else None,
            frontier=False if center else not continuous_travel,
            stop_at_map_boundary=False if center else not continuous_travel,
            allow_surf=allow_surf,
        )
        if binding is None and not center and continuous_travel:
            binding = story_travel_binding(
                runtime,
                actions,
                objective_id="liberate_silph",
                route=route,
                frontier=True,
                stop_at_map_boundary=True,
                allow_surf=allow_surf,
            )
        return None if binding is None else (binding, OptionChallenge(False, False, 0.0, 0.0, 0.0))
    if not _raw_party_fully_restored(raw):
        return None  # Existing genuine nurse/preparation choices retain authority.
    contract = silph_card_key_battle_contract(route.rom, raw)
    actor = battler if battler_for_contract is None else battler_for_contract(contract)
    actor.require_story_contract(contract)
    controller = FrozenStoryBattleController(actor, (contract,), evolution_rom=route.rom)
    source = runtime.emulator.save_state_bytes()
    used, terminal, result = False, None, None

    def execute():
        nonlocal used, terminal, result
        if used or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime):
            raise ValueError("Silph Card Key phase is stale or consumed")
        if battler_for_contract is not None and battler_for_contract(contract) is not actor:
            raise ValueError("Silph Card Key actor changed after quotation")
        actor.require_story_contract(contract)
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        result = run_learned_silph_card_key_phase(
            runtime.emulator,
            runtime.reader,
            actions,
            rom=route.rom,
            controller=controller,
            record=record or (lambda *args: None),
        )
        result = dict(
            result,
            battle_authority=(
                "development_scoped_frozen_model"
                if getattr(actor, "development_story_scope", None) is not None
                else "frozen_story_controller"
            ),
        )
        terminal = runtime.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            dict(
                support="existing_silph_card_key_phase",
                objective="liberate_silph",
                objective_completed=False,
                chapter_complete=False,
                phase=result,
            ),
        )

    def verify(report):
        if terminal is None or runtime.emulator.save_state_bytes() != terminal:
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        after, snapshot = capture_player_lesson_snapshot(runtime)
        if (
            result.get("status") == "complete"
            and result.get("card_key_acquired") is True
            and _field_ready(runtime)
            and dict(after.raw.bag_items or ()).get(int(ItemId.CARD_KEY)) == 1
            and event_flag_is_set(after.raw.event_flags, int(EventFlag.BEAT_SILPH_CO_5F_TRAINER_0))
            and set(snapshot["completed_objectives"]) == set(lesson["completed_objectives"])
        ):
            return GoalVerification.succeeded()
        reason = (
            GoalFailureReason.RESOURCE_LOST
            if result.get("status") == "lost"
            else GoalFailureReason.OUTCOME_NOT_VERIFIED
        )
        return GoalVerification.failed(reason)

    return (
        ExecutableGoalBinding(
            "pokemon.red:silph-card-key:" + sha256(source).hexdigest(),
            GoalKind.ADVANCE_STORY,
            0.2,
            0.15,
            execute,
            verify,
            story_objective_ref="liberate_silph",
        ),
        OptionChallenge(True, False, 0.0, 0.0, 0.0),
    )


_CONTINUATION_EVENTS = (
    ("third", EventFlag.BEAT_SILPH_CO_3F_TRAINER_0, EventFlag.BEAT_SILPH_CO_5F_TRAINER_0),
    ("rival", EventFlag.BEAT_SILPH_CO_RIVAL, EventFlag.SILPH_CO_3_UNLOCKED_DOOR_2),
    ("eleventh", EventFlag.BEAT_SILPH_CO_11F_TRAINER_0, EventFlag.BEAT_SILPH_CO_RIVAL),
    ("giovanni", EventFlag.BEAT_SILPH_CO_GIOVANNI, EventFlag.BEAT_SILPH_CO_11F_TRAINER_0),
)


def silph_continuation_phase(raw):
    """Private native admission shared by the option and its preparation preview."""
    if (
        raw.event_flags is None
        or raw.bag_items is None
        or dict(raw.bag_items).get(int(ItemId.CARD_KEY)) != 1
    ):
        return None
    return next(
        (
            name
            for name, defeated, prerequisite in _CONTINUATION_EVENTS
            if not event_flag_is_set(raw.event_flags, int(defeated))
            and event_flag_is_set(raw.event_flags, int(prerequisite))
        ),
        None,
    )


def silph_continuation_story_option(
    runtime,
    actions,
    _,
    *,
    route,
    battler,
    combat_levels,
    battler_for_contract=None,
    continuous_travel=False,
    allow_surf=False,
    record=None,
):
    """Offer a native-prerequisite encounter, not a supplied chapter scheduler.

    Recovered entry deliberately uses an already-restored Center; normal nurse
    and preparation peers own recovery. The legacy embedded healing is never
    invoked here. Giovanni's native reward is a disclosed completion mechanic.
    """
    if battler_for_contract is not None and not callable(battler_for_contract):
        raise TypeError("Silph battler resolver must be callable")
    if type(continuous_travel) is not bool or type(allow_surf) is not bool:
        raise TypeError("Silph travel flags must be boolean")
    if allow_surf and getattr(route, "allow_surf", False) is not True:
        raise ValueError("Silph travel requires a Surf-enabled native executor")
    if record is not None and not callable(record):
        raise TypeError("Silph record must be callable")
    if not _field_ready(runtime):
        return None
    before, lesson = capture_player_lesson_snapshot(runtime)
    raw = before.raw
    if (
        "liberate_silph"
        not in {o.id for o in runtime.adapter.graph.available_objectives(before.game_state)}
        or raw.event_flags is None
        or raw.bag_items is None
        or dict(raw.bag_items).get(int(ItemId.CARD_KEY)) != 1
    ):
        return None
    phase = silph_continuation_phase(raw)
    if phase is None:
        return None
    defeated = next(row[1] for row in _CONTINUATION_EVENTS if row[0] == phase)
    # Keep space for the actual President reward; existing storage peers may
    # release bag capacity, never discard the required Card Key or a Pokemon.
    if phase == "giovanni" and len(raw.bag_items) >= 20:
        return None
    # Match the real recovered-entry prerequisite before offering travel,
    # not only after returning to the Center's exact admission tile.
    if not _raw_party_fully_restored(raw):
        return None
    center = raw.map_id == int(MapId.SAFFRON_POKECENTER)
    at_entry = center and (raw.player_y, raw.player_x) == (3, 3)
    if not at_entry:
        binding = story_travel_binding(
            runtime,
            actions,
            objective_id="liberate_silph",
            route=route,
            destination_at=(3, 3) if center else None,
            route_destination_at=(3, 3) if not center and continuous_travel else None,
            frontier=False if center else not continuous_travel,
            stop_at_map_boundary=False if center else not continuous_travel,
            allow_surf=allow_surf,
        )
        if binding is None and not center and continuous_travel:
            binding = story_travel_binding(
                runtime,
                actions,
                objective_id="liberate_silph",
                route=route,
                frontier=True,
                stop_at_map_boundary=True,
                allow_surf=allow_surf,
            )
        return None if binding is None else (binding, OptionChallenge(False, False, 0.0, 0.0, 0.0))
    if not _raw_party_fully_restored(raw):
        return None
    contract = silph_continuation_contract(
        route.rom,
        raw,
        phase,
        rival_starter=runtime.reader.read_rival_starter() if phase == "rival" else None,
    )
    party = trainer_party_quote(
        route.rom, contract.trainer_identity[0], contract.trainer_identity[2]
    )
    challenge = OptionChallenge.from_levels(
        combat_levels=combat_levels, opponent_levels=tuple(m.level for m in party.party)
    )
    actor = battler if battler_for_contract is None else battler_for_contract(contract)
    actor.require_story_contract(contract)
    controller = FrozenStoryBattleController(actor, (contract,), evolution_rom=route.rom)
    source = runtime.emulator.save_state_bytes()
    used, terminal, result = False, None, None

    def execute():
        nonlocal used, terminal, result
        if used or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime):
            raise ValueError("Silph continuation is stale or consumed")
        if battler_for_contract is not None and battler_for_contract(contract) is not actor:
            raise ValueError("Silph continuation actor changed after quotation")
        actor.require_story_contract(contract)
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        result = dict(
            run_learned_silph_continuation(
                runtime.emulator,
                runtime.reader,
                actions,
                rom=route.rom,
                phase=phase,
                controller=controller,
                record=record or (lambda *args: None),
                rival_from_center=phase == "rival",
                recovered_from_center=phase != "rival",
                ordinary_game_economy=True,
            )
        )
        result.update(
            support=["navigation", "door interaction"],
            embedded_restoration=False,
            battle_authority=(
                "development_scoped_frozen_model"
                if getattr(actor, "development_story_scope", None) is not None
                else "frozen_story_controller"
            ),
        )
        if phase == "giovanni" and result.get("status") == "complete":
            result["reward"] = collect_silph_reward(
                runtime.emulator, runtime.reader, actions, rom=route.rom
            )
        terminal = runtime.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            dict(
                support="existing_silph_continuation_and_native_reward",
                objective="liberate_silph",
                phase=result,
                objective_completed=phase == "giovanni" and result.get("status") == "complete",
                chapter_complete=phase == "giovanni" and result.get("status") == "complete",
            ),
        )

    def verify(report):
        if terminal is None or runtime.emulator.save_state_bytes() != terminal:
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        after, snapshot = capture_player_lesson_snapshot(runtime)
        completed = set(lesson["completed_objectives"])
        expected = completed | ({"liberate_silph"} if phase == "giovanni" else set())
        stock = dict(after.raw.bag_items or ())
        if (
            result.get("status") == "complete"
            and _field_ready(runtime)
            and event_flag_is_set(after.raw.event_flags, int(defeated))
            and stock.get(int(ItemId.CARD_KEY)) == 1
            and set(snapshot["completed_objectives"]) == expected
            and (
                phase != "third"
                or event_flag_is_set(
                    after.raw.event_flags, int(EventFlag.SILPH_CO_3_UNLOCKED_DOOR_2)
                )
            )
            and (
                phase != "giovanni"
                or (
                    stock.get(int(ItemId.MASTER_BALL)) == 1
                    and event_flag_is_set(after.raw.event_flags, int(EventFlag.GOT_MASTER_BALL))
                )
            )
        ):
            return GoalVerification.succeeded()
        return GoalVerification.failed(
            GoalFailureReason.RESOURCE_LOST
            if result.get("status") == "lost"
            else GoalFailureReason.OUTCOME_NOT_VERIFIED
        )

    return (
        ExecutableGoalBinding(
            "pokemon.red:silph-" + phase + ":" + sha256(source).hexdigest(),
            GoalKind.ADVANCE_STORY,
            0.2,
            0.15,
            execute,
            verify,
            story_objective_ref="liberate_silph",
        ),
        challenge,
    )
