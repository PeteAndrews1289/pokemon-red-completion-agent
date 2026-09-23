"""A bounded Silph phase with learned combat and disclosed route/item support."""

from dataclasses import asdict

from .actions import MacroAction, MacroActionKind
from .battle_plan import RedBattlePlanId
from .executor import CountingExecutor
from .observation import EventFlag, ItemId, MapId, event_flag_is_set
from .red_goal_skills import _raw_party_fully_restored
from .red_story_battle import FrozenStoryBattleController, StoryTrainerContract
from .silph import (
    DEFAULT_SILPH_TIMING,
    _approach_first_silph_battle,
    _collect_silph_card_key,
    _require,
)


def silph_card_key_battle_contract(rom, raw):
    return StoryTrainerContract.from_cartridge(
        rom,
        raw,
        objective_id="liberate_silph",
        battle_plan_id=str(RedBattlePlanId.SILPH_5F_ROCKET),
        map_id=int(MapId.SILPH_CO_5F),
        defeated_event=int(EventFlag.BEAT_SILPH_CO_5F_TRAINER_0),
    )


def run_learned_silph_card_key_phase(
    emulator, reader, executor, *, rom, controller, record, timing=DEFAULT_SILPH_TIMING
):
    """One encounter, no purchases/items, retained loss, no chapter-completion claim.

    Caller authenticates and claims the source and saves all exception terminals.
    This is a new optional phase, not a replacement for the legacy chapter runner.
    """
    if not isinstance(controller, FrozenStoryBattleController):
        raise ValueError("Silph learned phase needs its explicit story controller")
    controller.require_identity()
    before = reader.read()
    _require(before, MapId.SAFFRON_POKECENTER, (3, 3), "learned Silph phase entry")
    contract = silph_card_key_battle_contract(rom, before)
    if (
        controller.contracts != (contract,)
        or before.battle_state
        or not _raw_party_fully_restored(before)
        or not reader.read_input_readiness().ready
        or before.bag_items is None
        or len(before.bag_items) >= 20
        or dict(before.bag_items).get(int(ItemId.CARD_KEY), 0)
        or type(before.party_count) is not int
        or not 1 <= before.party_count <= 6
        or emulator.pressed_buttons
    ):
        raise ValueError("learned Silph phase has stale scope, inventory or recovery state")
    actions = CountingExecutor(executor)
    initial_frames = emulator.frame_count
    owned_before = frozenset(reader.read_pokedex_state().owned_species)
    record("story-contract", asdict(contract))
    _approach_first_silph_battle(actions, reader, emulator, timing)
    entry = reader.read()
    for key in ("player_money", "bag_items", "party_species_ids", "party_hp", "party_pp"):
        if getattr(entry, key) != getattr(before, key):
            raise RuntimeError("Silph approach changed protected resources before learned combat")
    result = controller.run(
        reader,
        actions,
        objective_id=contract.objective_id,
        battle_plan_id=contract.battle_plan_id,
        expected_map=contract.map_id,
    )
    record("story-battle-completion", result.public_dict())
    if result.outcome != "won" or not result.field_ready:
        return {
            "status": result.outcome,
            "card_key_acquired": False,
            "battle_outcome": result.outcome,
            "model_goal_queries": 0,
        }
    _collect_silph_card_key(actions, reader, emulator, timing)
    # Close only observed pickup dialogue; never blindly interact again.
    for _ in range(32):
        if reader.read().battle_state or reader.read().map_id != contract.map_id:
            raise RuntimeError("Card Key dialogue left the verified field boundary")
        visible = reader.read_bottom_dialogue_box_visible()
        if not visible and reader.read_input_readiness().ready:
            break
        if visible:
            actions.execute(MacroAction(MacroActionKind.CANCEL))
        actions.execute(MacroAction(MacroActionKind.WAIT, repeat=timing.menu_frames))
    else:
        raise RuntimeError("Card Key dialogue did not settle within its bound")
    after = reader.read()
    expected_bag = dict(before.bag_items)
    expected_bag[int(ItemId.CARD_KEY)] = 1
    if (
        dict(after.bag_items or ()) != expected_bag
        or after.party_species_ids != before.party_species_ids
        or after.party_hp != result.final_state.party_hp
        or after.party_pp != result.final_state.party_pp
        or after.player_money != result.final_state.player_money
        or frozenset(reader.read_pokedex_state().owned_species) != owned_before
        or not event_flag_is_set(after.event_flags, contract.defeated_event)
        or after.battle_state
        or not reader.read_input_readiness().ready
        or emulator.pressed_buttons
    ):
        raise RuntimeError("learned Silph Card Key handoff failed preservation")
    return {
        "status": "complete",
        "battle_outcome": result.outcome,
        "card_key_acquired": True,
        "chapter_complete": False,
        "battle_authority": "qualified_frozen_k_story",
        "model_goal_queries": 0,
        "battle_decisions": len(result.episode.decisions),
        "cash_before": before.player_money,
        "cash_after": after.player_money,
        "actions": actions.actions_executed,
        "frames": emulator.frame_count - initial_frames,
        "combat_items": 0,
        "purchases": 0,
        "sales": 0,
        "support": ["navigation", "Card Key pickup"],
    }
