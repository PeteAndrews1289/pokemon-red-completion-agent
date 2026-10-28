"""Exact cartridge identity for a scripted story trainer without a sight header."""

from .gen1_trainer_parties import trainer_party_quote
from .gen1_traversal import map_object_events
from .observation import (
    CERULEAN_ROCKET_TRIGGER_X,
    CERULEAN_ROCKET_TRIGGER_YS,
    EventFlag,
    ItemId,
    MapId,
    event_flag_is_set,
)
from .red_story_battle import StoryTrainerContract
from .rom import verify_rom_bytes


def dojo_master_contract(rom, raw):
    """The interaction-only Master is not one of the four sight headers.

    Authenticate his exact cartridge object/party and native victory event;
    ordinary trainer enumeration must not invent a missing sight header.
    """
    verify_rom_bytes(rom)
    objects = [o for o in map_object_events(rom,{int(MapId.FIGHTING_DOJO)})
               if o.object_index == 1]
    event = int(EventFlag.BEAT_KARATE_MASTER)
    if (raw.map_id != int(MapId.FIGHTING_DOJO) or raw.event_flags is None
            or len(raw.event_flags)*8 <= event
            or event_flag_is_set(raw.event_flags,event) or len(objects) != 1
            or (objects[0].trainer_class,objects[0].trainer_set,objects[0].sprite_id,
                objects[0].direction_or_range,objects[0].at) != (224,1,14,208,(3,5))):
        raise ValueError('Dojo Master cartridge object or undefeated event differs')
    quote = trainer_party_quote(rom,224,1)
    return StoryTrainerContract('postgame_collection','scripted-dojo-master',
        int(MapId.FIGHTING_DOJO),(224,24,1),event,quote.expected_victory_money)


def dojo_master_introduction_contract(rom, reader):
    """Only already-open text beside the exact Master after all four native wins."""
    raw = reader.read()
    if (raw.map_id != int(MapId.FIGHTING_DOJO) or raw.battle_state != 0
            or (raw.player_y,raw.player_x) != (3,4) or raw.badge_bits != 255
            or not reader.read_bottom_dialogue_box_visible()
            or reader.read_player_facing() != 'right' or raw.event_flags is None
            or event_flag_is_set(raw.event_flags,int(EventFlag.BEAT_KARATE_MASTER))
            or not all(event_flag_is_set(raw.event_flags,int(event)) for event in (
                EventFlag.BEAT_FIGHTING_DOJO_TRAINER_0,EventFlag.BEAT_FIGHTING_DOJO_TRAINER_1,
                EventFlag.BEAT_FIGHTING_DOJO_TRAINER_2,EventFlag.BEAT_FIGHTING_DOJO_TRAINER_3,
            ))):
        return None
    objects = [o for o in reader.read_current_map_objects() if o.sprite_index == 1]
    if len(objects) != 1 or not objects[0].visible or objects[0].at != (3,5):
        return None
    return dojo_master_contract(rom,raw)


def cerulean_thief_contract(rom, reader):
    """Quote the exact coordinate-script thief; stale engaged RAM is not identity."""
    verify_rom_bytes(rom)
    raw = reader.read()
    event = int(EventFlag.BEAT_CERULEAN_ROCKET_THIEF)
    objects = [o for o in map_object_events(rom, {int(MapId.CERULEAN_CITY)}) if o.object_index == 2]
    if (
        raw.map_id != int(MapId.CERULEAN_CITY)
        or raw.player_x != CERULEAN_ROCKET_TRIGGER_X
        or raw.player_y not in CERULEAN_ROCKET_TRIGGER_YS
        or raw.event_flags is None
        or len(raw.event_flags) * 8 <= event
        or event_flag_is_set(raw.event_flags, event)
        or len(objects) != 1
        or (objects[0].trainer_class, objects[0].trainer_set, objects[0].movement) != (230, 5, 255)
        or not (
            raw.battle_state == 2
            and reader.read_active_trainer_identity() == (230, 30, 5)
            or raw.battle_state == 0
            and reader.trainer_engagement_active()
        )
    ):
        raise ValueError("Cerulean thief script identity or event differs")
    quote = trainer_party_quote(rom, 230, 5)
    return StoryTrainerContract(
        "reach_vermilion",
        "scripted-cerulean-thief",
        int(MapId.CERULEAN_CITY),
        (230, 30, 5),
        event,
        quote.expected_victory_money,
        victory_items=((int(ItemId.TM28_DIG), 1),),
    )


def ss_anne_rival_contract(rom, reader):
    """Pinned RIVAL2 starter branch; native room script replaces an event bit."""
    verify_rom_bytes(rom)
    raw = reader.read()
    objects = [o for o in map_object_events(rom, {int(MapId.SS_ANNE_2F)}) if o.object_index == 2]
    if (
        raw.map_id != int(MapId.SS_ANNE_2F)
        or reader.read_ss_anne_rival_script() not in {0, 1, 2}
        or len(objects) != 1
        or (objects[0].sprite_id, objects[0].movement) != (2, 255)
    ):
        raise ValueError("S.S.Anne rival script or cartridge object differs")
    team = {177: 1, 153: 2, 176: 3}.get(reader.read_rival_starter())
    if team is None:
        raise ValueError("S.S.Anne rival starter differs")
    quote = trainer_party_quote(rom, 242, team)
    if raw.battle_state == 2 and reader.read_active_trainer_identity() != (242, 42, team):
        raise ValueError("S.S.Anne active rival differs from starter branch")
    return StoryTrainerContract(
        "obtain_cut",
        "ss-anne-rival-gate",
        int(MapId.SS_ANNE_2F),
        (242, 42, team),
        None,
        quote.expected_victory_money,
    )


def nugget_rocket_contract(rom, raw):
    """Authenticate the already-triggered reward script's trainer, not a new challenge."""
    verify_rom_bytes(rom)
    objects = [o for o in map_object_events(rom, {int(MapId.ROUTE_24)}) if o.object_index == 1]
    event = int(EventFlag.BEAT_ROUTE_24_ROCKET)
    if (
        len(objects) != 1
        or (objects[0].trainer_class, objects[0].trainer_set, objects[0].movement) != (230, 6, 255)
        or raw.map_id != int(MapId.ROUTE_24)
        or raw.battle_state != 2
        or raw.event_flags is None
        or len(raw.event_flags) * 8 <= event
        or event_flag_is_set(raw.event_flags, event)
        or not event_flag_is_set(raw.event_flags, int(EventFlag.GOT_NUGGET))
    ):
        raise ValueError("Nugget Rocket script identity or event differs")
    quote = trainer_party_quote(rom, 230, 6)
    return StoryTrainerContract(
        "help_bill",
        "scripted-nugget-rocket",
        int(MapId.ROUTE_24),
        (230, 30, 6),
        event,
        quote.expected_victory_money,
    )


def nugget_rocket_introduction_contract(rom, reader):
    """Own only the native reward dialogue at the cartridge Rocket's approach.

    The reward is not claimed here. Also accept the exact post-reward movement
    handoff: the dialogue can close before Red sets battle2. The already-awarded
    Nugget, engaged identity and blocked native movement must all agree. The
    existing live battle contract is authenticated again after battle begins.
    """
    verify_rom_bytes(rom)
    raw = reader.read()
    if raw.map_id != int(MapId.ROUTE_24) or raw.battle_state != 0:
        return None
    objects = [o for o in map_object_events(rom, {int(MapId.ROUTE_24)}) if o.object_index == 1]
    if len(objects) != 1 or (
        objects[0].trainer_class,
        objects[0].trainer_set,
        objects[0].movement,
    ) != (230, 6, 255):
        raise ValueError("Nugget Rocket introduction cartridge object differs")
    rocket = objects[0]
    visible = reader.read_bottom_dialogue_box_visible()
    pending = (
        not visible
        and raw.event_flags is not None
        and event_flag_is_set(raw.event_flags, int(EventFlag.GOT_NUGGET))
        and dict(raw.bag_items or ()).get(int(ItemId.NUGGET), 0) > 0
        and reader.read_trainer_battle_identity() == (230, 30, 230, 6)
        and not reader.read_input_readiness().ready
        and reader.read_input_readiness().player_moving_direction != 0
    )
    if (
        raw.event_flags is None
        or len(raw.event_flags) * 8 <= int(EventFlag.BEAT_ROUTE_24_TRAINER_5)
        or raw.player_y is None
        or raw.player_x is None
        or abs(raw.player_y - rocket.y) + abs(raw.player_x - rocket.x) != 1
        or not (visible or pending)
        or event_flag_is_set(raw.event_flags, int(EventFlag.BEAT_ROUTE_24_ROCKET))
        or not all(
            event_flag_is_set(raw.event_flags, int(event))
            for event in (
                EventFlag.BEAT_ROUTE_24_TRAINER_1,
                EventFlag.BEAT_ROUTE_24_TRAINER_2,
                EventFlag.BEAT_ROUTE_24_TRAINER_3,
                EventFlag.BEAT_ROUTE_24_TRAINER_4,
                EventFlag.BEAT_ROUTE_24_TRAINER_5,
            )
        )
    ):
        return None
    quote = trainer_party_quote(rom, rocket.trainer_class, rocket.trainer_set)
    return StoryTrainerContract(
        "help_bill",
        "scripted-nugget-rocket",
        int(MapId.ROUTE_24),
        (230, 30, 6),
        int(EventFlag.BEAT_ROUTE_24_ROCKET),
        quote.expected_victory_money,
    )


def fossil_guard_object(rom):
    verify_rom_bytes(rom)
    objects = [o for o in map_object_events(rom, {int(MapId.MT_MOON_B2F)}) if o.object_index == 1]
    if len(objects) != 1 or (
        objects[0].trainer_class,
        objects[0].trainer_set,
        objects[0].movement,
    ) != (208, 2, 255):
        raise ValueError("scripted fossil guard differs from cartridge")
    return objects[0]


def fossil_guard_contract(rom, raw):
    guard = fossil_guard_object(rom)
    event = int(EventFlag.BEAT_MT_MOON_EXIT_SUPER_NERD)
    if (
        raw.event_flags is None
        or len(raw.event_flags) * 8 <= event
        or event_flag_is_set(raw.event_flags, event)
    ):
        raise ValueError("fossil guard is defeated or unreadable")
    quote = trainer_party_quote(rom, guard.trainer_class, guard.trainer_set)
    return StoryTrainerContract(
        "reach_cerulean",
        "scripted-fossil-guard",
        guard.map_id,
        (208, 8, 2),
        event,
        quote.expected_victory_money,
    )


def hideout_scripted_object(rom, map_id):
    verify_rom_bytes(rom)
    expected = {135: (11, 24, 230, 7), 202: (1, 23, 229, 1)}.get(map_id)
    if expected is None:
        raise ValueError("unsupported scripted Hideout room")
    index, picture, cls, team = expected
    objects = [o for o in map_object_events(rom, {map_id}) if o.object_index == index]
    if len(objects) != 1 or (
        objects[0].sprite_id,
        objects[0].trainer_class,
        objects[0].trainer_set,
        objects[0].movement,
    ) != (picture, cls, team, 255):
        raise ValueError("scripted Hideout cartridge object differs")
    return objects[0]


def hideout_scripted_contract(rom, raw):
    target = hideout_scripted_object(rom, raw.map_id)
    event = None if raw.map_id == 135 else int(EventFlag.BEAT_ROCKET_HIDEOUT_GIOVANNI)
    if raw.event_flags is None or (event is not None and event_flag_is_set(raw.event_flags, event)):
        raise ValueError("scripted Hideout event is unavailable or defeated")
    quote = trainer_party_quote(rom, target.trainer_class, target.trainer_set)
    return StoryTrainerContract(
        "clear_rocket_hideout",
        "game-corner-poster-guard" if event is None else "hideout-giovanni",
        raw.map_id,
        (target.trainer_class, target.trainer_class - 200, target.trainer_set),
        event,
        quote.expected_victory_money,
    )


def tower_rival_object(rom):
    verify_rom_bytes(rom)
    objects = [o for o in map_object_events(rom, {143}) if o.object_index == 1]
    if len(objects) != 1 or (objects[0].sprite_id, objects[0].movement) != (2, 255):
        raise ValueError("Tower rival cartridge object differs")
    return objects[0]


def tower_rival_contract(rom, reader):
    tower_rival_object(rom)
    raw = reader.read()
    event = int(EventFlag.BEAT_POKEMON_TOWER_RIVAL)
    team = {177: 4, 153: 5, 176: 6}.get(reader.read_rival_starter())
    if (
        raw.map_id != 143
        or team is None
        or raw.event_flags is None
        or len(raw.event_flags) * 8 <= event
        or event_flag_is_set(raw.event_flags, event)
    ):
        raise ValueError("Tower rival starter/event differs")
    if raw.battle_state == 2 and reader.read_active_trainer_identity() != (242, 42, team):
        raise ValueError("Tower active rival differs from starter branch")
    quote = trainer_party_quote(rom, 242, team)
    return StoryTrainerContract(
        "rescue_fuji", "tower-rival", 143, (242, 42, team), event, quote.expected_victory_money
    )
