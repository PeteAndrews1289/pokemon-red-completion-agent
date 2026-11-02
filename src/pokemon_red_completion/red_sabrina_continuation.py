"""Opt-in learned Sabrina encounter with separate native reward handling."""
from dataclasses import asdict

from . import silph
from .gen1_trainer_parties import trainer_party_quote
from .gen1_traversal import map_object_events
from .observation import Badge, EventFlag, ItemId, MapId, event_flag_is_set
from .red_goal_skills import _raw_party_fully_restored
from .red_npc_approach import approach_npc
from .red_story_battle import FrozenStoryBattleController, StoryTrainerContract
from .rom import verify_rom_bytes


def sabrina_contract(rom, raw):
    verify_rom_bytes(rom)
    if (raw.event_flags is None or event_flag_is_set(raw.event_flags, EventFlag.BEAT_SABRINA)
            or raw.badge_bits & Badge.MARSH):
        raise ValueError("Sabrina encounter already consumed or unreadable")
    objects = [o for o in map_object_events(rom, {int(MapId.SAFFRON_GYM)})
               if o.object_index == 1]
    if len(objects) != 1 or (objects[0].trainer_class, objects[0].trainer_set) != (240, 1):
        raise ValueError("Sabrina object identity differs from qualified cartridge")
    quote = trainer_party_quote(rom, 240, 1)
    return StoryTrainerContract("defeat_sabrina", "sabrina", int(MapId.SAFFRON_GYM),
                                (240, 40, 1), int(EventFlag.BEAT_SABRINA),
                                quote.expected_victory_money,
                                ((int(ItemId.TM46_PSYWAVE), 1),), int(Badge.MARSH))


def run_learned_sabrina(emulator, reader, actions, *, rom, controller, record,
                       resume_approach=False):
    if not isinstance(controller, FrozenStoryBattleController):
        raise ValueError("explicit learned story controller required")
    controller.require_identity()
    before = reader.read()
    contract = sabrina_contract(rom, before)
    if type(resume_approach) is not bool:
        raise ValueError("approach continuation must be explicit")
    source_map = MapId.SAFFRON_GYM if resume_approach else MapId.SAFFRON_POKECENTER
    if (controller.contracts != (contract,) or before.battle_state
            or before.map_id != source_map
            or not _raw_party_fully_restored(before)
            or not event_flag_is_set(before.event_flags, EventFlag.BEAT_SILPH_CO_GIOVANNI)
            or not reader.read_input_readiness().ready or emulator.pressed_buttons
            or len(before.bag_items) >= 20):
        raise ValueError("Sabrina requires healed earned Center entry and reward capacity")
    record("story-contract", asdict(contract))
    approach = approach_npc(emulator, reader, actions, rom=rom,
                            map_id=contract.map_id, object_index=1)
    record("leader-approach", approach)
    entry = reader.read()
    for key in ("player_money", "bag_items", "party_species_ids", "party_hp", "party_pp",
                "party_moves", "badge_bits", "event_flags"):
        if getattr(entry, key) != getattr(before, key):
            raise RuntimeError("Sabrina approach changed protected resources or events")
    silph._interact(actions, silph.DEFAULT_SILPH_TIMING.dialogue_frames)
    silph._await_trainer_battle(actions, reader, silph.DEFAULT_SILPH_TIMING)
    result = controller.run(reader, actions, objective_id=contract.objective_id,
                            battle_plan_id=contract.battle_plan_id, expected_map=contract.map_id)
    record("story-battle-completion", result.public_dict())
    if result.outcome != "won" or not result.field_ready:
        return {"status": result.outcome, "battle": result.public_dict()}
    return settle_sabrina_rewards(reader, actions, before=before,
                                  victory_money=contract.victory_money,
                                  battle=result.public_dict())


def settle_sabrina_rewards(reader, actions, *, before, victory_money, battle):
    """Finish rewards after an independently established win; never battle again."""
    raw = reader.read()
    if (raw.battle_state or not event_flag_is_set(raw.event_flags, EventFlag.BEAT_SABRINA)
            or raw.player_money != before.player_money + victory_money):
        raise ValueError("Sabrina reward settlement requires native victory and payout")
    for _ in range(64):
        raw = reader.read()
        if (event_flag_is_set(raw.event_flags, EventFlag.GOT_TM46)
                and raw.badge_bits & Badge.MARSH
                and dict(raw.bag_items).get(ItemId.TM46_PSYWAVE) == 1
                and reader.read_input_readiness().ready
                and not reader.read_bottom_dialogue_box_visible()):
            break
        silph._interact(actions, silph.DEFAULT_SILPH_TIMING.dialogue_frames)
    else:
        raise RuntimeError("Sabrina reward did not settle within dialogue bound")
    expected = dict(before.bag_items)
    expected[int(ItemId.TM46_PSYWAVE)] = 1
    if (dict(raw.bag_items) != expected
            or raw.player_money != before.player_money + victory_money
            or raw.badge_bits != before.badge_bits | int(Badge.MARSH)):
        raise RuntimeError("Sabrina reward/resource reconciliation failed")
    return {"status": "complete", "marsh_badge": True, "tm46": True,
            "money_delta": victory_money, "battle": battle}
