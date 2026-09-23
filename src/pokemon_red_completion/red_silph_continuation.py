"""Explicit earned Silph phases; learned combat, disclosed existing route support."""

from dataclasses import asdict, replace

from . import silph as route
from .battle_plan import RedBattlePlanId as Plan
from .battle_runtime import BattleRuntimeTiming, advance_battle_to_policy_boundary
from .executor import CountingExecutor
from .gen1_trainer_parties import trainer_party_quote
from .gen1_traversal import map_object_events
from .lorelei import _battle_x_accuracy
from .observation import EventFlag as Event
from .observation import ItemId, MapId, event_flag_is_set
from .red_goal_skills import _raw_party_fully_restored
from .red_party_pp import decode_red_party_pp
from .red_story_battle import FrozenStoryBattleController, StoryTrainerContract
from .rom import verify_rom_bytes

# These are battle admission contracts, never policy inputs or move preferences.
_PHASES = {
    "third": (
        Plan.SILPH_3F_ROCKET,
        MapId.SILPH_CO_3F,
        Event.BEAT_SILPH_CO_3F_TRAINER_0,
        MapId.SILPH_CO_5F,
        Event.BEAT_SILPH_CO_5F_TRAINER_0,
    ),
    "rival": (
        Plan.SILPH_7F_RIVAL,
        MapId.SILPH_CO_7F,
        Event.BEAT_SILPH_CO_RIVAL,
        MapId.SILPH_CO_3F,
        Event.SILPH_CO_3_UNLOCKED_DOOR_2,
    ),
    "eleventh": (
        Plan.SILPH_11F_ROCKET,
        MapId.SILPH_CO_11F,
        Event.BEAT_SILPH_CO_11F_TRAINER_0,
        MapId.SILPH_CO_7F,
        Event.BEAT_SILPH_CO_RIVAL,
    ),
    "giovanni": (
        Plan.SILPH_11F_GIOVANNI,
        MapId.SILPH_CO_11F,
        Event.BEAT_SILPH_CO_GIOVANNI,
        MapId.SILPH_CO_11F,
        Event.BEAT_SILPH_CO_11F_TRAINER_0,
    ),
}


def silph_continuation_contract(rom, raw, phase, *, rival_starter=None):
    """Quote ordinary trainers or exact-revision scripted boss identities.

    pret/pokered a1a22aaf scripts/SilphCo7F.asm selects Rival2 sets7/8/9
    by persistent rival starter. Giovanni's identity comes from object3 on11F;
    its separate story event is set only after his departure script.
    """
    if phase not in _PHASES:
        raise ValueError("unknown Silph continuation phase")
    plan, room, event, _, _ = _PHASES[phase]
    if raw.event_flags is None or event_flag_is_set(raw.event_flags, event):
        raise ValueError("Silph encounter already completed or unreadable")
    if phase in {"third", "eleventh"}:
        return StoryTrainerContract.from_cartridge(
            rom,
            raw,
            objective_id="liberate_silph",
            battle_plan_id=str(plan),
            map_id=int(room),
            defeated_event=int(event),
        )
    verify_rom_bytes(rom)
    if phase == "rival":
        # Internal starter IDs belong to the title adapter, not the actor.
        if type(rival_starter) is not int or rival_starter not in {177, 153, 176}:
            raise ValueError("unsupported persistent rival starter")
        opponent, number = 242, {177: 7, 153: 8, 176: 9}[rival_starter]
    else:
        matches = [o for o in map_object_events(rom, {int(room)}) if o.object_index == 3]
        if len(matches) != 1 or (matches[0].trainer_class, matches[0].trainer_set) != (229, 2):
            raise ValueError("Silph Giovanni object identity disagrees with revision")
        opponent, number = matches[0].trainer_class, matches[0].trainer_set
    quote = trainer_party_quote(rom, opponent, number)
    return StoryTrainerContract(
        "liberate_silph",
        str(plan),
        int(room),
        (opponent, opponent - 200, number),
        int(event),
        quote.expected_victory_money,
    )


def _approach(phase, actions, reader, emulator, timing, rom=None):
    """Reuse qualified chapter route/healing support without invoking its combat."""
    raw = reader.read()
    full_pp = tuple(
        (packed & 0xC0) | slot.maximum_pp
        for packed, slot in zip(
            raw.party_pp[0],
            decode_red_party_pp(raw.party_moves[0], raw.party_pp[0]).moves,
            strict=True,
        )
    )
    if phase == "third":
        route._move(actions, reader, route.CARD_KEY_RETURN, timing)
        route._move(actions, reader, ("up", "up", "down", "up"), timing)
        route._move(actions, reader, route.FIFTH_FLOOR_TO_ELEVATOR, timing)
        route._enter_silph_elevator(actions, reader, timing, "learned Silph5F elevator")
        route._select_elevator_floor(actions, reader, emulator, 2, timing)
        route._move(actions, reader, route.ELEVATOR_EXIT, timing)
        route._move(actions, reader, route.THIRD_FLOOR_GUARD, timing)
    elif phase == "rival-center":
        route._return_center_to_seventh(actions, reader, emulator, timing)
        route._move(actions, reader, route._directions("ULL"), timing)
    elif phase == "rival":
        route._move(actions, reader, route.THIRD_FLOOR_TO_7F, timing)
        route._move(actions, reader, ("down",), timing)
        route._heal_detour_from_seventh(
            actions, reader, emulator, timing, expected_first_party_pp=full_pp
        )
        route._return_center_to_seventh(actions, reader, emulator, timing)
        route._move(actions, reader, route._directions("ULL"), timing)
    elif phase == "eleventh":
        route._heal_detour_after_rival(
            actions, reader, emulator, timing, expected_first_party_pp=full_pp
        )
        route._return_center_to_seventh(actions, reader, emulator, timing)
        route._move(actions, reader, route.SEVENT_TO_11F, timing)
        route._require(reader.read(), MapId.SILPH_CO_11F, (3, 2), "learned Silph11F")
        route._move(actions, reader, ("down",) * 10, timing)
    else:
        # Healing/re-entry changes sprite positions. Replan from observed terrain,
        # rather than assuming every step of the old post-battle route succeeded.
        from .red_training_ground_route import RedVermilionGroundTransition

        transition = replace(
            RedVermilionGroundTransition.from_rom(rom),
            destination_map=int(MapId.SILPH_CO_11F), destination_at=(14, 7),
            full_event_offsets=True, observe_terrain=True,
        )
        transition(actions, reader, emulator)
        route._require(reader.read(), MapId.SILPH_CO_11F, (7, 14), "boss door approach")
        route._move(actions, reader, ("up",), timing)
        route._interact(actions, timing.dialogue_frames)
        route._confirm_many(actions, 3, timing.dialogue_frames)
        route._require_event(emulator, Event.SILPH_CO_11_UNLOCKED_DOOR)
        route._move(actions, reader, ("up", "up"), timing)
    route._await_trainer_battle(actions, reader, timing)


def run_learned_silph_continuation(
    emulator,
    reader,
    executor,
    *,
    rom,
    phase,
    controller,
    record,
    rival_from_center=False,
    opening_item_support=False,
    timing=route.DEFAULT_SILPH_TIMING,
):
    """Run one declared fresh encounter; caller durably saves every exception.

    Never handles a retained in-battle error by re-approaching or re-drawing a
    choice. A separate authenticated continuation must own such a terminal.
    """
    if not isinstance(controller, FrozenStoryBattleController):
        raise ValueError("explicit frozen story controller required")
    controller.require_identity()
    before = reader.read()
    if type(rival_from_center) is not bool or (rival_from_center and phase != "rival"):
        raise ValueError("Center rematch applies only to rival")
    if type(opening_item_support) is not bool or (opening_item_support and not rival_from_center):
        raise ValueError("opening item support requires explicit recovered rival entry")
    if opening_item_support and any(
        dict(before.bag_items or ()).get(int(i), 0) < 1
        for i in (ItemId.X_ACCURACY, ItemId.X_SPECIAL)
    ):
        raise ValueError("opening item support lacks actual stock")
    contract = silph_continuation_contract(
        rom, before, phase, rival_starter=reader.read_rival_starter() if phase == "rival" else None
    )
    _, _, _, source_map, prerequisite = _PHASES[phase]
    if rival_from_center:
        source_map = MapId.SAFFRON_POKECENTER
        route._require(before, source_map, (3, 3), "earned rival rematch")
        if not _raw_party_fully_restored(before) or before.player_money < 2800:
            raise ValueError("rival rematch requires full recovery and loss reserve")
    if (
        controller.contracts != (contract,)
        or before.battle_state
        or before.map_id != source_map
        or not event_flag_is_set(before.event_flags, prerequisite)
        or dict(before.bag_items or ()).get(int(ItemId.CARD_KEY)) != 1
        or not reader.read_input_readiness().ready
        or reader.read_bottom_dialogue_box_visible()
        or emulator.pressed_buttons
        or not any(before.party_hp or ())
    ):
        raise ValueError("stale Silph phase entry or prerequisite")
    if phase == "third":
        route._require(before, source_map, (20, 16), "Card Key continuation")
    owned = frozenset(reader.read_pokedex_state().owned_species)
    actions = CountingExecutor(executor)
    record("story-contract", asdict(contract))
    _approach(
        "rival-center" if rival_from_center else phase, actions, reader, emulator, timing, rom
    )
    entry = reader.read()
    for key in ("player_money", "bag_items", "party_species_ids", "party_moves", "badge_bits"):
        if getattr(entry, key) != getattr(before, key):
            raise RuntimeError("Silph support changed protected resources")
    if phase in {"third", "giovanni"} and (entry.party_hp, entry.party_pp) != (
        before.party_hp,
        before.party_pp,
    ):
        raise RuntimeError("unhealed Silph approach changed HP/PP")
    if opening_item_support:
        advance_battle_to_policy_boundary(
            reader,
            actions,
            expected_map=contract.map_id,
            expected_battle_state=2,
            timing=BattleRuntimeTiming(),
            label="rival item support",
        )
        if reader.read_active_trainer_identity() != contract.trainer_identity:
            raise ValueError("item support encountered wrong trainer")
        item_before = reader.read()
        route._battle_x_special(reader, actions, emulator, timing)
        _battle_x_accuracy(reader, actions, emulator)
        item_after = reader.read()
        expected_bag = dict(item_before.bag_items)
        for item in (ItemId.X_SPECIAL, ItemId.X_ACCURACY):
            expected_bag[int(item)] -= 1
            if not expected_bag[int(item)]:
                del expected_bag[int(item)]
        if (
            dict(item_after.bag_items) != expected_bag
            or item_after.player_money != item_before.player_money
            or item_after.party_species_ids != item_before.party_species_ids
            or item_after.party_pp != item_before.party_pp
            or item_after.event_flags != item_before.event_flags
        ):
            raise RuntimeError("opening item support failed exact resource verification")
        record(
            "opening-item-support",
            {
                "authority": "disclosed support, not model choice",
                "x_special": 1,
                "x_accuracy": 1,
                "hp_before": list(item_before.party_hp),
                "hp_after": list(item_after.party_hp),
                "cash": item_after.player_money,
            },
        )
    result = controller.run(
        reader,
        actions,
        objective_id=contract.objective_id,
        battle_plan_id=contract.battle_plan_id,
        expected_map=contract.map_id,
    )
    record("story-battle-completion", result.public_dict())
    if result.outcome != "won" or not result.field_ready:
        return {"status": result.outcome, "phase": phase, "battle": result.public_dict()}
    if phase == "third":
        route._move(actions, reader, ("down", "left"), timing)
        route._interact(actions, timing.dialogue_frames)
        route._confirm_many(actions, 4, timing.dialogue_frames)
        route._require_event(emulator, Event.SILPH_CO_3_UNLOCKED_DOOR_2)
    after = reader.read()
    for key in ("bag_items", "party_species_ids", "party_hp", "party_pp", "player_money"):
        if getattr(after, key) != getattr(result.final_state, key):
            raise RuntimeError("Silph postbattle support changed protected resources")
    if (
        after.battle_state
        or not reader.read_input_readiness().ready
        or reader.read_bottom_dialogue_box_visible()
        or emulator.pressed_buttons
        or not owned <= frozenset(reader.read_pokedex_state().owned_species)
    ):
        raise RuntimeError("Silph phase did not reach a preserved field endpoint")
    return {
        "status": "complete",
        "phase": phase,
        "battle": result.public_dict(),
        "cash_before": before.player_money,
        "cash_after": after.player_money,
        "giovanni_defeated": event_flag_is_set(after.event_flags, Event.BEAT_SILPH_CO_GIOVANNI),
        "actions": actions.actions_executed,
        "model_goal_queries": 0,
        "support": ["navigation", "door interaction", "free Center healing"],
    }
