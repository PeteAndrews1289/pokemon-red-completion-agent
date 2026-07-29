from __future__ import annotations

from dataclasses import dataclass, replace
from enum import IntEnum, IntFlag, StrEnum
from typing import Protocol

from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.referee import CHAMPION_DEFEATED_FACT
from pokemon_red_completion.route import HALL_OF_FAME_FACT


class ReadOnlyMemory(Protocol):
    """The deliberately non-mutating memory surface available to the adapter."""

    def read_u8(self, address: int) -> int: ...


class RamAddress(IntEnum):
    """Verified symbols for the supported US revision-zero ROM.

    Symbols originate from pret/pokered commit
    ``1e96034092686d006e863cace09e87273051a3d8`` and are valid only after the
    repository's exact ROM fingerprint gate passes.
    """

    TILE_MAP = 0xC3A0
    TOP_MENU_ITEM_Y = 0xCC24
    TOP_MENU_ITEM_X = 0xCC25
    CURRENT_MENU_ITEM = 0xCC26
    LIST_SCROLL_OFFSET = 0xCC36
    MENU_WATCHED_KEYS = 0xCC29
    MENU_CURSOR_LOCATION = 0xCC30
    NPC_MOVEMENT_SCRIPT_TABLE = 0xCC57
    PLAYER_ATTACK_STAGE = 0xCD1A
    PLAYER_ACCURACY_STAGE = 0xCD1E
    ENEMY_DEFENSE_STAGE = 0xCD2F
    ENGAGED_TRAINER_CLASS = 0xCD2D
    ENGAGED_TRAINER_SET = 0xCD2E
    SIMULATED_JOYPAD_INDEX = 0xCD38
    JOY_IGNORE = 0xCD6B
    BATTLE_RESULT = 0xCF0B
    SHOP_SELECTED_ITEM = 0xCF91
    SHOP_QUANTITY = 0xCF96
    TILE_IN_FRONT_OF_PLAYER = 0xCFC6
    ENEMY_SPECIES = 0xCFE5
    ENEMY_HP = 0xCFE6
    ENEMY_LEVEL = 0xCFF3
    ENEMY_MAX_HP = 0xCFF4
    TRAINER_CLASS = 0xD031
    IS_IN_BATTLE = 0xD057
    CURRENT_OPPONENT = 0xD059
    GYM_LEADER_NUMBER = 0xD05C
    TRAINER_NUMBER = 0xD05D
    REPEL_REMAINING_STEPS = 0xD0DB
    PLAYER_MONEY = 0xD347
    PARTY_COUNT = 0xD163
    PARTY_SPECIES = 0xD164
    PARTY_MON_1_HP = 0xD16C
    PARTY_MON_1_STATUS = 0xD16F
    PARTY_MON_1_MOVES = 0xD173
    PARTY_MON_1_PP = 0xD188
    PARTY_MON_1_LEVEL = 0xD18C
    PARTY_MON_1_MAX_HP = 0xD18D
    PARTY_MON_2_HP = 0xD198
    PARTY_MON_2_STATUS = 0xD19B
    PARTY_MON_2_MOVES = 0xD19F
    PARTY_MON_2_PP = 0xD1B4
    PARTY_MON_2_LEVEL = 0xD1B8
    PARTY_MON_2_MAX_HP = 0xD1B9
    PARTY_MON_2_NICKNAME = 0xD2C0
    PARTY_MON_3_HP = 0xD1C4
    PARTY_MON_3_STATUS = 0xD1C7
    PARTY_MON_3_MOVES = 0xD1CB
    PARTY_MON_3_PP = 0xD1E0
    PARTY_MON_3_LEVEL = 0xD1E4
    PARTY_MON_3_MAX_HP = 0xD1E5
    PARTY_MON_3_NICKNAME = 0xD2CB
    NUM_BAG_ITEMS = 0xD31D
    BAG_ITEMS = 0xD31E
    OBTAINED_BADGES = 0xD356
    CURRENT_MAP = 0xD35E
    PLAYER_Y = 0xD361
    PLAYER_X = 0xD362
    PLAYER_MOVING_DIRECTION = 0xD528
    OAKS_LAB_SCRIPT = 0xD5F0
    PALLET_TOWN_SCRIPT = 0xD5F1
    VIRIDIAN_CITY_SCRIPT = 0xD5F4
    PEWTER_CITY_SCRIPT = 0xD5F7
    ROUTE_3_SCRIPT = 0xD5F8
    ROUTE_4_SCRIPT = 0xD5F9
    PEWTER_GYM_SCRIPT = 0xD5FC
    CERULEAN_GYM_SCRIPT = 0xD5FD
    ROUTE_6_SCRIPT = 0xD600
    ROUTE_24_SCRIPT = 0xD602
    ROUTE_25_SCRIPT = 0xD603
    MT_MOON_1F_SCRIPT = 0xD606
    MT_MOON_B2F_SCRIPT = 0xD607
    REDS_HOUSE_2F_SCRIPT = 0xD60C
    VIRIDIAN_MART_SCRIPT = 0xD60D
    CERULEAN_CITY_SCRIPT = 0xD60F
    VIRIDIAN_FOREST_SCRIPT = 0xD618
    BILLS_HOUSE_SCRIPT = 0xD661
    VERMILION_CITY_SCRIPT = 0xD62A
    SS_ANNE_2F_SCRIPT = 0xD665
    BEAT_GYM_FLAGS = 0xD72A
    STATUS_FLAGS_5 = 0xD730
    STATUS_FLAGS_6 = 0xD732
    MOVEMENT_FLAGS = 0xD736
    NPC_TRADE_FLAGS = 0xD737
    VERMILION_GYM_FIRST_LOCK = 0xD743
    VERMILION_GYM_SECOND_LOCK = 0xD744
    EVENT_FLAGS = 0xD747
    CURRENT_MAP_SCRIPT = 0xDA39


class MapId(IntEnum):
    PALLET_TOWN = 0x00
    VIRIDIAN_CITY = 0x01
    PEWTER_CITY = 0x02
    CERULEAN_CITY = 0x03
    LAVENDER_TOWN = 0x04
    VERMILION_CITY = 0x05
    CELADON_CITY = 0x06
    FUCHSIA_CITY = 0x07
    CINNABAR_ISLAND = 0x08
    INDIGO_PLATEAU = 0x09
    SAFFRON_CITY = 0x0A
    ROUTE_1 = 0x0C
    ROUTE_2 = 0x0D
    ROUTE_3 = 0x0E
    ROUTE_4 = 0x0F
    ROUTE_5 = 0x10
    ROUTE_6 = 0x11
    ROUTE_7 = 0x12
    ROUTE_8 = 0x13
    ROUTE_9 = 0x14
    ROUTE_10 = 0x15
    ROUTE_11 = 0x16
    ROUTE_24 = 0x23
    ROUTE_25 = 0x24
    REDS_HOUSE_1F = 0x25
    REDS_HOUSE_2F = 0x26
    OAKS_LAB = 0x28
    VIRIDIAN_POKECENTER = 0x29
    VIRIDIAN_MART = 0x2A
    VIRIDIAN_FOREST_NORTH_GATE = 0x2F
    ROUTE_2_GATE = 0x31
    VIRIDIAN_FOREST_SOUTH_GATE = 0x32
    VIRIDIAN_FOREST = 0x33
    PEWTER_GYM = 0x36
    PEWTER_POKECENTER = 0x3A
    MT_MOON_1F = 0x3B
    MT_MOON_B1F = 0x3C
    MT_MOON_B2F = 0x3D
    CERULEAN_TRASHED_HOUSE = 0x3E
    CERULEAN_POKECENTER = 0x40
    CERULEAN_GYM = 0x41
    MT_MOON_POKECENTER = 0x44
    UNDERGROUND_PATH_ROUTE_5 = 0x47
    UNDERGROUND_PATH_ROUTE_6 = 0x4A
    UNDERGROUND_PATH_ROUTE_7 = 0x4D
    UNDERGROUND_PATH_ROUTE_8 = 0x50
    DIGLETTS_CAVE_ROUTE_11 = 0x55
    BILLS_HOUSE = 0x58
    VERMILION_POKECENTER = 0x59
    VERMILION_MART = 0x5B
    VERMILION_GYM = 0x5C
    VERMILION_DOCK = 0x5E
    SS_ANNE_1F = 0x5F
    SS_ANNE_2F = 0x60
    SS_ANNE_CAPTAINS_ROOM = 0x65
    UNDERGROUND_PATH_NORTH_SOUTH = 0x77
    UNDERGROUND_PATH_WEST_EAST = 0x79
    ROCK_TUNNEL_POKECENTER = 0x51
    ROCK_TUNNEL_1F = 0x52
    LAVENDER_POKECENTER = 0x8D
    POKEMON_TOWER_1F = 0x8E
    POKEMON_TOWER_2F = 0x8F
    POKEMON_TOWER_3F = 0x90
    POKEMON_TOWER_4F = 0x91
    POKEMON_TOWER_5F = 0x92
    POKEMON_TOWER_6F = 0x93
    POKEMON_TOWER_7F = 0x94
    MR_FUJIS_HOUSE = 0x95
    CELADON_POKECENTER = 0x85
    GAME_CORNER = 0x87
    ROCKET_HIDEOUT_B1F = 0xC7
    ROCKET_HIDEOUT_B2F = 0xC8
    ROCKET_HIDEOUT_B3F = 0xC9
    ROCKET_HIDEOUT_B4F = 0xCA
    ROCKET_HIDEOUT_ELEVATOR = 0xCB
    ROCK_TUNNEL_B1F = 0xE8
    HALL_OF_FAME = 0x76
    CHAMPIONS_ROOM = 0x78
    INDIGO_PLATEAU_LOBBY = 0xAE
    VERMILION_TRADE_HOUSE = 0xC4
    DIGLETTS_CAVE = 0xC5


class EventFlag(IntEnum):
    FOLLOWED_OAK_INTO_LAB = 0x000
    FOLLOWED_OAK_INTO_LAB_2 = 0x020
    OAK_ASKED_TO_CHOOSE_MON = 0x021
    GOT_STARTER = 0x022
    BATTLED_RIVAL_IN_OAKS_LAB = 0x023
    GOT_POKEDEX = 0x025
    OAK_APPEARED_IN_PALLET = 0x027
    OAK_GOT_PARCEL = 0x038
    GOT_OAKS_PARCEL = 0x039
    BEAT_VIRIDIAN_GYM_GIOVANNI = 0x051
    GOT_TM34 = 0x076
    BEAT_BROCK = 0x077
    BEAT_CERULEAN_RIVAL = 0x098
    BEAT_CERULEAN_ROCKET_THIEF = 0x0A7
    BEAT_CERULEAN_GYM_TRAINER_0 = 0x0BA
    BEAT_CERULEAN_GYM_TRAINER_1 = 0x0BB
    GOT_TM11 = 0x0BE
    BEAT_MISTY = 0x0BF
    BEAT_ROUTE_6_TRAINER_0 = 0x411
    BEAT_ROUTE_6_TRAINER_1 = 0x412
    BEAT_ROUTE_6_TRAINER_2 = 0x413
    BEAT_ROUTE_6_TRAINER_3 = 0x414
    BEAT_ROUTE_6_TRAINER_4 = 0x415
    BEAT_ROUTE_6_TRAINER_5 = 0x416
    BEAT_ROUTE_8_TRAINER_0 = 0x431
    BEAT_ROUTE_8_TRAINER_1 = 0x432
    BEAT_ROUTE_8_TRAINER_2 = 0x433
    BEAT_ROUTE_8_TRAINER_3 = 0x434
    BEAT_ROUTE_8_TRAINER_4 = 0x435
    BEAT_ROUTE_8_TRAINER_5 = 0x436
    BEAT_ROUTE_8_TRAINER_6 = 0x437
    BEAT_ROUTE_8_TRAINER_7 = 0x438
    BEAT_ROUTE_8_TRAINER_8 = 0x439
    FOUND_ROCKET_HIDEOUT = 0x1B9
    BEAT_ROCKET_HIDEOUT_1_TRAINER_0 = 0x671
    BEAT_ROCKET_HIDEOUT_1_TRAINER_1 = 0x672
    BEAT_ROCKET_HIDEOUT_1_TRAINER_2 = 0x673
    BEAT_ROCKET_HIDEOUT_1_TRAINER_3 = 0x674
    BEAT_ROCKET_HIDEOUT_1_TRAINER_4 = 0x675
    ENTERED_ROCKET_HIDEOUT = 0x677
    BEAT_ROCKET_HIDEOUT_2_TRAINER_0 = 0x681
    BEAT_ROCKET_HIDEOUT_3_TRAINER_0 = 0x691
    BEAT_ROCKET_HIDEOUT_3_TRAINER_1 = 0x692
    BEAT_ROCKET_HIDEOUT_4_TRAINER_0 = 0x6A2
    BEAT_ROCKET_HIDEOUT_4_TRAINER_1 = 0x6A3
    BEAT_ROCKET_HIDEOUT_4_TRAINER_2 = 0x6A4
    ROCKET_HIDEOUT_4_DOOR_UNLOCKED = 0x6A5
    ROCKET_DROPPED_LIFT_KEY = 0x6A6
    BEAT_ROUTE_9_TRAINER_0 = 0x441
    BEAT_ROUTE_9_TRAINER_8 = 0x449
    BEAT_ROUTE_10_TRAINER_2 = 0x453
    BEAT_ROCK_TUNNEL_1_TRAINER_3 = 0x45C
    BEAT_ROCK_TUNNEL_1_TRAINER_4 = 0x45D
    BEAT_ROCK_TUNNEL_1_TRAINER_5 = 0x45E
    RESCUED_MR_FUJI = 0x117
    GOT_POKE_FLUTE = 0x128
    BEAT_POKEMON_TOWER_RIVAL = 0x0EF
    BEAT_POKEMONTOWER_3_TRAINER_0 = 0x0F1
    BEAT_POKEMONTOWER_3_TRAINER_1 = 0x0F2
    BEAT_POKEMONTOWER_3_TRAINER_2 = 0x0F3
    BEAT_POKEMONTOWER_4_TRAINER_0 = 0x0F9
    BEAT_POKEMONTOWER_4_TRAINER_1 = 0x0FA
    BEAT_POKEMONTOWER_4_TRAINER_2 = 0x0FB
    BEAT_POKEMONTOWER_5_TRAINER_0 = 0x102
    BEAT_POKEMONTOWER_5_TRAINER_1 = 0x103
    BEAT_POKEMONTOWER_5_TRAINER_2 = 0x104
    BEAT_POKEMONTOWER_5_TRAINER_3 = 0x105
    IN_PURIFIED_ZONE = 0x107
    BEAT_POKEMONTOWER_6_TRAINER_0 = 0x109
    BEAT_POKEMONTOWER_6_TRAINER_1 = 0x10A
    BEAT_POKEMONTOWER_6_TRAINER_2 = 0x10B
    BEAT_GHOST_MAROWAK = 0x10F
    BEAT_POKEMONTOWER_7_TRAINER_0 = 0x111
    BEAT_POKEMONTOWER_7_TRAINER_1 = 0x112
    BEAT_POKEMONTOWER_7_TRAINER_2 = 0x113
    RESCUED_MR_FUJI_WORLD = 0x4CF
    GOT_TM24 = 0x166
    BEAT_LT_SURGE = 0x167
    BEAT_ERIKA = 0x1A9
    GOT_HM04 = 0x238
    BEAT_KOGA = 0x259
    BEAT_BLAINE = 0x299
    BEAT_SABRINA = 0x361
    BEAT_ROUTE_3_TRAINER_0 = 0x3E2
    BEAT_ROUTE_3_TRAINER_1 = 0x3E3
    BEAT_ROUTE_3_TRAINER_2 = 0x3E4
    BEAT_ROUTE_3_TRAINER_3 = 0x3E5
    BEAT_ROUTE_3_TRAINER_4 = 0x3E6
    BEAT_ROUTE_3_TRAINER_5 = 0x3E7
    BEAT_ROUTE_3_TRAINER_6 = 0x3E8
    BEAT_ROUTE_3_TRAINER_7 = 0x3E9
    BEAT_ROUTE_4_TRAINER_0 = 0x3F2
    GOT_NUGGET = 0x540
    BEAT_ROUTE_24_ROCKET = 0x541
    BEAT_ROUTE_24_TRAINER_0 = 0x542
    BEAT_ROUTE_24_TRAINER_1 = 0x543
    BEAT_ROUTE_24_TRAINER_2 = 0x544
    BEAT_ROUTE_24_TRAINER_3 = 0x545
    BEAT_ROUTE_24_TRAINER_4 = 0x546
    BEAT_ROUTE_24_TRAINER_5 = 0x547
    NUGGET_REWARD_AVAILABLE = 0x549
    MET_BILL = 0x550
    BEAT_ROUTE_25_TRAINER_0 = 0x551
    BEAT_ROUTE_25_TRAINER_1 = 0x552
    BEAT_ROUTE_25_TRAINER_2 = 0x553
    BEAT_ROUTE_25_TRAINER_3 = 0x554
    BEAT_ROUTE_25_TRAINER_4 = 0x555
    BEAT_ROUTE_25_TRAINER_5 = 0x556
    BEAT_ROUTE_25_TRAINER_6 = 0x557
    BEAT_ROUTE_25_TRAINER_7 = 0x558
    BEAT_ROUTE_25_TRAINER_8 = 0x559
    USED_CELL_SEPARATOR_ON_BILL = 0x55B
    GOT_SS_TICKET = 0x55C
    MET_BILL_2 = 0x55D
    BILL_SAID_USE_CELL_SEPARATOR = 0x55E
    LEFT_BILLS_HOUSE_AFTER_HELPING = 0x55F
    BEAT_MT_MOON_1_TRAINER_0 = 0x571
    BEAT_MT_MOON_1_TRAINER_1 = 0x572
    BEAT_MT_MOON_1_TRAINER_2 = 0x573
    BEAT_MT_MOON_1_TRAINER_3 = 0x574
    BEAT_MT_MOON_1_TRAINER_4 = 0x575
    BEAT_MT_MOON_1_TRAINER_5 = 0x576
    BEAT_MT_MOON_1_TRAINER_6 = 0x577
    BEAT_MT_MOON_EXIT_SUPER_NERD = 0x579
    BEAT_MT_MOON_3_TRAINER_0 = 0x57A
    BEAT_MT_MOON_3_TRAINER_1 = 0x57B
    BEAT_MT_MOON_3_TRAINER_2 = 0x57C
    BEAT_MT_MOON_3_TRAINER_3 = 0x57D
    GOT_DOME_FOSSIL = 0x57E
    GOT_HELIX_FOSSIL = 0x57F
    GOT_HM01 = 0x5E0
    RUBBED_CAPTAINS_BACK = 0x5E1
    BEAT_ROCKET_HIDEOUT_GIOVANNI = 0x6A7
    BEAT_SILPH_CO_GIOVANNI = 0x78F
    GOT_HM03 = 0x880
    BEAT_LORELEI = 0x8E1
    BEAT_BRUNO = 0x8E9
    BEAT_AGATHA = 0x8F1
    BEAT_LANCE = 0x8FE
    BEAT_CHAMPION_RIVAL = 0x901
    BEAT_ROCK_TUNNEL_2_TRAINER_0 = 0x9B1
    BEAT_ROCK_TUNNEL_2_TRAINER_1 = 0x9B2
    BEAT_ROCK_TUNNEL_2_TRAINER_3 = 0x9B4
    BEAT_ROCK_TUNNEL_2_TRAINER_4 = 0x9B5
    BEAT_ROCK_TUNNEL_2_TRAINER_5 = 0x9B6
    BEAT_ROCK_TUNNEL_2_TRAINER_7 = 0x9B8


class ItemId(IntEnum):
    POKE_BALL = 0x04
    SUPER_POTION = 0x13
    REPEL = 0x1E
    DOME_FOSSIL = 0x29
    HELIX_FOSSIL = 0x2A
    SECRET_KEY = 0x2B
    NUGGET = 0x31
    SS_TICKET = 0x3F
    OAKS_PARCEL = 0x46
    SILPH_SCOPE = 0x48
    POKE_FLUTE = 0x49
    RARE_CANDY = 0x28
    X_ACCURACY = 0x2E
    LIFT_KEY = 0x4A
    HM01_CUT = 0xC4
    HM03_SURF = 0xC6
    HM04_STRENGTH = 0xC7
    TM11_BUBBLEBEAM = 0xD3
    TM24_THUNDERBOLT = 0xE0
    TM28_DIG = 0xE4
    TM34_BIDE = 0xEA


class Badge(IntFlag):
    BOULDER = 1 << 0
    CASCADE = 1 << 1
    THUNDER = 1 << 2
    RAINBOW = 1 << 3
    SOUL = 1 << 4
    MARSH = 1 << 5
    VOLCANO = 1 << 6
    EARTH = 1 << 7


GAME_TIMER_COUNTING_MASK = 0x01
REDS_HOUSE_2F_NOOP_SCRIPT = 1
OAKS_LAB_SELECTION_READY_SCRIPT = 6
OAKS_LAB_STARTER_OBTAINED_SCRIPT = 10
JOY_IGNORE_CONFIRM_MASK = 0x01
JOY_IGNORE_CANCEL_MASK = 0x02
JOY_IGNORE_MOVEMENT_MASK = 0xF0
SCRIPTED_MOVEMENT_STATUS_MASK = (1 << 0) | (1 << 5) | (1 << 7)
EXITING_DOOR_MOVEMENT_MASK = 1 << 1
ABRA_SPECIES_ID = 0x94
PIDGEOTTO_SPECIES_ID = 0x96
BULBASAUR_SPECIES_ID = 0x99
RATTATA_SPECIES_ID = 0xA5
SQUIRTLE_SPECIES_ID = 0xB1
WARTORTLE_SPECIES_ID = 0xB3
BLASTOISE_SPECIES_ID = 0x1C
SQUIRTLE_LINEAGE_SPECIES_IDS = frozenset(
    {SQUIRTLE_SPECIES_ID, WARTORTLE_SPECIES_ID, BLASTOISE_SPECIES_ID}
)
TACKLE_MOVE_ID = 0x21
TAIL_WHIP_MOVE_ID = 0x27
WATER_GUN_MOVE_ID = 0x37
BUBBLE_MOVE_ID = 0x91
BROCK_OPPONENT_ID = 0xEA
BROCK_TRAINER_CLASS_ID = 0x22
BROCK_GYM_LEADER_NUMBER = 1
MT_MOON_SUPER_NERD_OPPONENT_ID = 0xD0
SUPER_NERD_TRAINER_CLASS_ID = 0x08
MT_MOON_SUPER_NERD_TRAINER_NUMBER = 2
YOUNGSTER_OPPONENT_ID = 0xC9
YOUNGSTER_TRAINER_CLASS_ID = 0x01
BUG_CATCHER_OPPONENT_ID = 0xCA
BUG_CATCHER_TRAINER_CLASS_ID = 0x02
LASS_OPPONENT_ID = 0xCB
LASS_TRAINER_CLASS_ID = 0x03
JR_TRAINER_M_OPPONENT_ID = 0xCD
JR_TRAINER_M_TRAINER_CLASS_ID = 0x05
JR_TRAINER_F_OPPONENT_ID = 0xCE
JR_TRAINER_F_TRAINER_CLASS_ID = 0x06
HIKER_OPPONENT_ID = 0xD1
HIKER_TRAINER_CLASS_ID = 0x09
RIVAL1_OPPONENT_ID = 0xE1
RIVAL1_TRAINER_CLASS_ID = 0x19
RIVAL2_OPPONENT_ID = 0xF2
RIVAL2_TRAINER_CLASS_ID = 0x2A
SS_ANNE_RIVAL_TRAINER_NUMBER = 2
SS_ANNE_RIVAL_ENGAGED_CLASS = 0x17
SS_ANNE_RIVAL_ENGAGED_SET = 7
CERULEAN_RIVAL_TRAINER_NUMBER = 8
CERULEAN_RIVAL_TRIGGER_Y = 6
CERULEAN_RIVAL_TRIGGER_XS = frozenset({20, 21})
ROUTE_3_REQUIRED_TRAINER_SPECS = (
    (0, BUG_CATCHER_OPPONENT_ID, BUG_CATCHER_TRAINER_CLASS_ID, 4),
    (1, YOUNGSTER_OPPONENT_ID, YOUNGSTER_TRAINER_CLASS_ID, 1),
    (3, BUG_CATCHER_OPPONENT_ID, BUG_CATCHER_TRAINER_CLASS_ID, 5),
    (6, BUG_CATCHER_OPPONENT_ID, BUG_CATCHER_TRAINER_CLASS_ID, 6),
)
ROCKET_OPPONENT_ID = 0xE6
ROCKET_TRAINER_CLASS_ID = 0x1E
# The collision-legal fossil route reaches Rocket1 from the B2F (21, 17)
# entry. Header 0 / party 1 engages while Red is at (11, 19).
MT_MOON_REQUIRED_ROCKET_TRAINER_INDEX = 0
MT_MOON_REQUIRED_ROCKET_TRAINER_NUMBER = 1
MT_MOON_REQUIRED_ROCKET_EVENT = EventFlag.BEAT_MT_MOON_3_TRAINER_0
MT_MOON_REQUIRED_ROCKET_TRIGGER_X = 11
MT_MOON_REQUIRED_ROCKET_TRIGGER_Y = 19
# The selected northbound bridge route alternates lanes around the five
# trainers. Each tuple is:
# (object/header index, event, opponent, class, party number, player x, player y).
ROUTE_24_REQUIRED_TRAINER_SPECS = (
    (
        5,
        EventFlag.BEAT_ROUTE_24_TRAINER_5,
        BUG_CATCHER_OPPONENT_ID,
        BUG_CATCHER_TRAINER_CLASS_ID,
        9,
        10,
        31,
    ),
    (
        4,
        EventFlag.BEAT_ROUTE_24_TRAINER_4,
        LASS_OPPONENT_ID,
        LASS_TRAINER_CLASS_ID,
        8,
        11,
        28,
    ),
    (
        3,
        EventFlag.BEAT_ROUTE_24_TRAINER_3,
        YOUNGSTER_OPPONENT_ID,
        YOUNGSTER_TRAINER_CLASS_ID,
        4,
        10,
        25,
    ),
    (
        2,
        EventFlag.BEAT_ROUTE_24_TRAINER_2,
        LASS_OPPONENT_ID,
        LASS_TRAINER_CLASS_ID,
        7,
        11,
        22,
    ),
    (
        1,
        EventFlag.BEAT_ROUTE_24_TRAINER_1,
        JR_TRAINER_M_OPPONENT_ID,
        JR_TRAINER_M_TRAINER_CLASS_ID,
        3,
        10,
        19,
    ),
)
ROUTE_24_ROCKET_TRAINER_NUMBER = 6
ROUTE_24_ROCKET_TRIGGER_X = 10
ROUTE_24_ROCKET_TRIGGER_Y = 15
# The collision-qualified Route 25 line deliberately avoids five optional
# trainers. These are the four live battles on the selected path to Bill.
ROUTE_25_REQUIRED_TRAINER_SPECS = (
    (
        8,
        EventFlag.BEAT_ROUTE_25_TRAINER_8,
        HIKER_OPPONENT_ID,
        HIKER_TRAINER_CLASS_ID,
        4,
        15,
        7,
    ),
    (
        3,
        EventFlag.BEAT_ROUTE_25_TRAINER_3,
        LASS_OPPONENT_ID,
        LASS_TRAINER_CLASS_ID,
        9,
        20,
        8,
    ),
    (
        2,
        EventFlag.BEAT_ROUTE_25_TRAINER_2,
        JR_TRAINER_M_OPPONENT_ID,
        JR_TRAINER_M_TRAINER_CLASS_ID,
        2,
        24,
        6,
    ),
    (
        5,
        EventFlag.BEAT_ROUTE_25_TRAINER_5,
        LASS_OPPONENT_ID,
        LASS_TRAINER_CLASS_ID,
        10,
        37,
        5,
    ),
)
MISTY_OPPONENT_ID = 0xEB
MISTY_TRAINER_CLASS_ID = 0x23
MISTY_TRAINER_NUMBER = 1
MISTY_GYM_LEADER_NUMBER = 2
CERULEAN_GYM_REQUIRED_TRAINER_NUMBER = 1
CERULEAN_GYM_REQUIRED_TRAINER_TRIGGER_X = 5
CERULEAN_GYM_REQUIRED_TRAINER_TRIGGER_Y = 3
MISTY_TRIGGER_X = 5
MISTY_TRIGGER_Y = 2
CERULEAN_ROCKET_TRAINER_NUMBER = 5
CERULEAN_ROCKET_TRIGGER_X = 30
CERULEAN_ROCKET_TRIGGER_YS = frozenset({7, 9})
ROUTE_6_JR_TRAINER_F_OPPONENT_ID = 0xCE
ROUTE_6_JR_TRAINER_F_CLASS_ID = 0x06
ROUTE_6_JR_TRAINER_F_NUMBER = 3
ROUTE_6_JR_TRAINER_M_OPPONENT_ID = 0xCD
ROUTE_6_JR_TRAINER_M_CLASS_ID = 0x05
ROUTE_6_JR_TRAINER_M_NUMBER = 5
MAIN_BATTLE_MENU_LEFT_SIGNATURE = (0x0E, 0x09, 0x11)
MAIN_BATTLE_MENU_RIGHT_SIGNATURE = (0x0E, 0x0F, 0x21)
MOVE_BATTLE_MENU_SIGNATURE = (0x0C, 0x05, 0xC7)
FILLED_MENU_CURSOR_TILE = 0xED
TILE_MAP_SIZE = 20 * 18
MIN_BATTLE_COMMAND = 0
MAX_BATTLE_COMMAND = 3
MIN_MOVE_MENU_SLOT = 1
MAX_MOVE_MENU_SLOT = 4
PARTY_LIMIT = 6
MAX_BAG_ITEMS = 20
EVENT_FLAGS_END = 0xD886
EVENT_FLAG_BYTES = EVENT_FLAGS_END - int(RamAddress.EVENT_FLAGS)


@dataclass(frozen=True, slots=True)
class RawGameState:
    """Revision-specific state read from a single emulator observation."""

    game_started: bool
    map_id: int | None
    player_x: int | None
    player_y: int | None
    party_count: int | None
    battle_state: int | None
    badge_bits: int | None = None
    bag_item_ids: tuple[int, ...] | None = None
    event_flags: bytes | None = None
    party_species_ids: tuple[int, ...] | None = None
    first_party_level: int | None = None
    first_party_hp: int | None = None
    first_party_max_hp: int | None = None
    first_party_status: int | None = None
    battle_result: int | None = None
    first_party_moves: tuple[int, ...] | None = None
    first_party_pp: tuple[int, ...] | None = None
    enemy_species_id: int | None = None
    enemy_hp: int | None = None
    enemy_level: int | None = None
    enemy_max_hp: int | None = None
    player_attack_stage: int | None = None
    player_accuracy_stage: int | None = None
    enemy_defense_stage: int | None = None


@dataclass(frozen=True, slots=True)
class BedroomInputState:
    joy_ignore: int
    map_script: int

    @property
    def ready(self) -> bool:
        return self.joy_ignore == 0 and self.map_script == REDS_HOUSE_2F_NOOP_SCRIPT


class OpeningPhase(StrEnum):
    UNKNOWN = "unknown"
    BEDROOM_READY = "bedroom_ready"
    DOWNSTAIRS = "downstairs"
    PALLET_FREE = "pallet_free"
    OAK_ESCORT = "oak_escort"
    STARTER_SELECTION_READY = "starter_selection_ready"
    STARTER_OBTAINED = "starter_obtained"


@dataclass(frozen=True, slots=True)
class OpeningControlState:
    phase: OpeningPhase
    confirm_allowed: bool
    cancel_allowed: bool
    movement_allowed: bool
    followed_oak_into_lab: bool
    asked_to_choose: bool
    starter_obtained: bool
    first_party_species: int | None

    @property
    def all_controls_allowed(self) -> bool:
        return self.confirm_allowed and self.cancel_allowed and self.movement_allowed


class OaksErrandPhase(StrEnum):
    UNKNOWN = "unknown"
    STARTER_READY = "starter_ready"
    RIVAL_BATTLE = "rival_battle"
    RIVAL_DEFEATED = "rival_defeated"
    PARCEL_OBTAINED = "parcel_obtained"
    POKEDEX_OBTAINED = "pokedex_obtained"


@dataclass(frozen=True, slots=True)
class OaksErrandState:
    """Semantic controls and evidence for the bounded rival/parcel/Pokédex chapter."""

    phase: OaksErrandPhase
    joy_ignore: int
    lab_script: int
    mart_script: int
    battled_rival: bool
    got_oaks_parcel: bool
    oak_got_parcel: bool
    got_pokedex: bool
    parcel_in_bag: bool
    first_party_species: int | None
    first_party_level: int | None
    first_party_hp: int | None
    first_party_max_hp: int | None
    battle_result: int | None
    map_id: int | None = None
    battle_state: int | None = None

    @property
    def controls_ready(self) -> bool:
        return self.joy_ignore == 0

    @property
    def rival_victory_snapshot(self) -> bool:
        return (
            self.phase is OaksErrandPhase.RIVAL_DEFEATED
            and self.map_id == MapId.OAKS_LAB
            and self.battle_state == 0
            and self.lab_script == 18
            and self.controls_ready
            and self.battle_result == 0
            and self.battled_rival
            and self.first_party_species == SQUIRTLE_SPECIES_ID
            and self.first_party_level == 6
            and self.first_party_hp == 21
            and self.first_party_max_hp == 21
        )

    @property
    def parcel_snapshot(self) -> bool:
        return (
            self.phase is OaksErrandPhase.PARCEL_OBTAINED
            and self.map_id == MapId.VIRIDIAN_MART
            and self.battle_state == 0
            and self.mart_script == 2
            and self.controls_ready
            and self.got_oaks_parcel
            and self.parcel_in_bag
        )

    @property
    def pokedex_snapshot(self) -> bool:
        return (
            self.phase is OaksErrandPhase.POKEDEX_OBTAINED
            and self.map_id == MapId.OAKS_LAB
            and self.battle_state == 0
            and self.lab_script == 18
            and self.controls_ready
            and self.got_oaks_parcel
            and self.oak_got_parcel
            and self.got_pokedex
            and not self.parcel_in_bag
            and self.first_party_species == SQUIRTLE_SPECIES_ID
        )


class TravelBoundary(StrEnum):
    UNKNOWN = "unknown"
    PALLET_LAB_EXTERIOR = "pallet_lab_exterior"
    VIRIDIAN_SOUTH_EDGE = "viridian_south_edge"
    ROUTE_2_SOUTH_EDGE = "route_2_south_edge"
    FOREST_SOUTH_GATE = "forest_south_gate"
    FOREST_SOUTH_ENTRY = "forest_south_entry"
    FOREST_NORTH_GATE = "forest_north_gate"
    ROUTE_2_NORTH_RETURN = "route_2_north_return"
    PEWTER_SOUTH_EDGE = "pewter_south_edge"
    PEWTER_GYM_ENTRANCE = "pewter_gym_entrance"


class NorthboundPhase(StrEnum):
    UNKNOWN = "unknown"
    LAB_EXITED = "lab_exited"
    VIRIDIAN_REACHED = "viridian_reached"
    ROUTE_2_SOUTH_REACHED = "route_2_south_reached"
    FOREST_GATE_REACHED = "forest_gate_reached"
    FOREST_ENTERED = "forest_entered"
    FOREST_CLEARED = "forest_cleared"
    PEWTER_REACHED = "pewter_reached"
    PEWTER_GYM_ENTERED = "pewter_gym_entered"
    BROCK_BATTLE = "brock_battle"
    BROCK_DEFEATED = "brock_defeated"


@dataclass(frozen=True, slots=True)
class InputReadiness:
    joy_ignore: int
    simulated_joypad_index: int
    npc_movement_script_table: int
    player_moving_direction: int
    status_flags_5: int
    movement_flags: int = 0

    @property
    def ready(self) -> bool:
        return (
            self.joy_ignore == 0
            and self.simulated_joypad_index == 0
            and self.npc_movement_script_table == 0
            and self.player_moving_direction == 0
            and not bool(self.status_flags_5 & SCRIPTED_MOVEMENT_STATUS_MASK)
            and not bool(self.movement_flags & EXITING_DOOR_MOVEMENT_MASK)
        )


class BattleMenuPhase(StrEnum):
    UNKNOWN = "unknown"
    MAIN = "main"
    MOVE = "move"


@dataclass(frozen=True, slots=True)
class BattleMenuState:
    """Revision-pinned menu meaning without exposing menu RAM to route code."""

    phase: BattleMenuPhase
    selected_move_slot: int | None = None
    selected_main_command: int | None = None


@dataclass(frozen=True, slots=True)
class PewterChapterState:
    """Revision-bound semantic evidence for travel to Pewter and Brock."""

    phase: NorthboundPhase
    boundary: TravelBoundary
    controls: InputReadiness
    local_script: int
    current_map_script: int
    oak_lab_script: int
    got_oaks_parcel: bool
    oak_got_parcel: bool
    got_pokedex: bool
    parcel_in_bag: bool
    beat_brock: bool
    got_tm34: bool
    tm34_in_bag: bool
    boulder_badge: bool
    boulder_badge_mirror: bool
    current_opponent: int
    trainer_class: int
    engaged_trainer_class: int
    gym_leader_number: int
    map_id: int | None
    player_x: int | None
    player_y: int | None
    party_count: int | None
    first_party_species: int | None
    first_party_hp: int | None
    first_party_max_hp: int | None
    first_party_level: int | None
    battle_state: int | None
    battle_result: int | None
    first_party_status: int | None = None
    first_party_moves: tuple[int, ...] | None = None
    first_party_pp: tuple[int, ...] | None = None

    @property
    def post_pokedex_invariants(self) -> bool:
        return (
            self.got_oaks_parcel
            and self.oak_got_parcel
            and self.got_pokedex
            and not self.parcel_in_bag
            and self.oak_lab_script == 18
            and self.party_count == 1
            and self.first_party_species == SQUIRTLE_SPECIES_ID
            and (self.first_party_hp or 0) > 0
        )

    @property
    def stable_travel_snapshot(self) -> bool:
        return (
            self.unbeaten_brock_invariants
            and self.battle_state == 0
            and self.controls.ready
            and self.current_map_script == 0
        )

    @property
    def unbeaten_brock_invariants(self) -> bool:
        return (
            self.post_pokedex_invariants
            and self.first_party_status == 0
            and not self.beat_brock
            and not self.got_tm34
            and not self.tm34_in_bag
            and not self.boulder_badge
            and not self.boulder_badge_mirror
        )

    @property
    def pewter_snapshot(self) -> bool:
        return (
            self.phase is NorthboundPhase.PEWTER_REACHED
            and self.boundary is TravelBoundary.PEWTER_SOUTH_EDGE
            and self.stable_travel_snapshot
            and self.local_script == 0
            and not self.beat_brock
            and not self.boulder_badge
            and not self.boulder_badge_mirror
        )

    @property
    def travel_boundary_snapshot(self) -> bool:
        if self.boundary is TravelBoundary.UNKNOWN or not self.stable_travel_snapshot:
            return False
        expected_script = {
            TravelBoundary.PALLET_LAB_EXTERIOR: 5,
            TravelBoundary.VIRIDIAN_SOUTH_EDGE: 0,
            TravelBoundary.ROUTE_2_SOUTH_EDGE: 0,
            TravelBoundary.FOREST_SOUTH_GATE: 0,
            TravelBoundary.FOREST_SOUTH_ENTRY: 0,
            TravelBoundary.FOREST_NORTH_GATE: 0,
            TravelBoundary.ROUTE_2_NORTH_RETURN: 0,
            TravelBoundary.PEWTER_SOUTH_EDGE: 0,
            TravelBoundary.PEWTER_GYM_ENTRANCE: 0,
        }[self.boundary]
        return self.local_script == expected_script

    @property
    def brock_battle_snapshot(self) -> bool:
        return (
            self.phase is NorthboundPhase.BROCK_BATTLE
            and self.map_id == MapId.PEWTER_GYM
            and self.unbeaten_brock_invariants
            and self.battle_state == 2
            and self.local_script == 3
            and self.current_map_script == 3
            and self.current_opponent == BROCK_OPPONENT_ID
            and self.trainer_class == BROCK_TRAINER_CLASS_ID
            and self.engaged_trainer_class == BROCK_OPPONENT_ID
            and self.gym_leader_number == BROCK_GYM_LEADER_NUMBER
        )

    @property
    def brock_ready_snapshot(self) -> bool:
        """Require a healthy, battle-capable Squirtle before challenging Brock."""
        moves = self.first_party_moves or ()
        pp = self.first_party_pp or ()
        try:
            bubble_slot = moves.index(BUBBLE_MOVE_ID)
        except ValueError:
            return False
        bubble_pp = pp[bubble_slot] & 0x3F if bubble_slot < len(pp) else 0
        return (
            self.phase is NorthboundPhase.PEWTER_GYM_ENTERED
            and self.boundary is TravelBoundary.PEWTER_GYM_ENTRANCE
            and self.travel_boundary_snapshot
            and not self.beat_brock
            and not self.boulder_badge
            and not self.boulder_badge_mirror
            and self.first_party_status == 0
            and (self.first_party_level or 0) >= 9
            and (self.first_party_hp or 0) >= 19
            and (self.first_party_max_hp or 0) >= (self.first_party_hp or 0)
            and bubble_pp >= 4
        )

    @property
    def brock_victory_snapshot(self) -> bool:
        return (
            self.phase is NorthboundPhase.BROCK_DEFEATED
            and self.map_id == MapId.PEWTER_GYM
            and self.post_pokedex_invariants
            and self.battle_state == 0
            and self.battle_result == 0
            and self.beat_brock
            and self.got_tm34
            and self.tm34_in_bag
            and self.boulder_badge
            and self.boulder_badge_mirror
            and self.local_script == 0
            and self.current_map_script == 0
            and self.controls.ready
            and self.first_party_status == 0
        )


class PewterProgressError(ValueError):
    """Raised when northbound evidence skips or contradicts a required boundary."""


class PewterProgressTracker:
    """Latch one ordered post-Pokédex proof without trusting a destination alone."""

    _BOUNDARIES = (
        TravelBoundary.PALLET_LAB_EXTERIOR,
        TravelBoundary.VIRIDIAN_SOUTH_EDGE,
        TravelBoundary.ROUTE_2_SOUTH_EDGE,
        TravelBoundary.FOREST_SOUTH_GATE,
        TravelBoundary.FOREST_SOUTH_ENTRY,
        TravelBoundary.FOREST_NORTH_GATE,
        TravelBoundary.ROUTE_2_NORTH_RETURN,
        TravelBoundary.PEWTER_SOUTH_EDGE,
        TravelBoundary.PEWTER_GYM_ENTRANCE,
    )

    def __init__(self, pokedex_state: OaksErrandState) -> None:
        if not pokedex_state.pokedex_snapshot:
            raise PewterProgressError(
                "Northbound qualification must begin at the verified Pokédex boundary."
            )
        self._boundary_index = -1
        self._saw_brock_ready = False
        self._saw_brock_battle = False
        self._brock_defeated = False

    @property
    def reached_boundaries(self) -> tuple[TravelBoundary, ...]:
        return self._BOUNDARIES[: self._boundary_index + 1]

    @property
    def saw_brock_battle(self) -> bool:
        return self._saw_brock_battle

    @property
    def saw_brock_ready(self) -> bool:
        return self._saw_brock_ready

    @property
    def brock_defeated(self) -> bool:
        return self._brock_defeated

    def observe(self, state: PewterChapterState) -> NorthboundPhase:
        if state.brock_victory_snapshot:
            if not self._saw_brock_battle:
                raise PewterProgressError(
                    "Brock victory cannot qualify without the observed live battle."
                )
            self._brock_defeated = True
            return NorthboundPhase.BROCK_DEFEATED

        if state.brock_battle_snapshot:
            if self._boundary_index != len(self._BOUNDARIES) - 1 or not self._saw_brock_ready:
                raise PewterProgressError(
                    "Brock battle appeared before the battle-ready gym-entry proof."
                )
            self._saw_brock_battle = True
            return NorthboundPhase.BROCK_BATTLE

        if state.boundary is TravelBoundary.UNKNOWN:
            return state.phase
        if not state.travel_boundary_snapshot:
            raise PewterProgressError("Travel boundary failed its stable semantic snapshot.")

        expected_index = self._boundary_index + 1
        if self._boundary_index >= 0 and state.boundary is self._BOUNDARIES[self._boundary_index]:
            return state.phase
        if expected_index >= len(self._BOUNDARIES):
            raise PewterProgressError("Unexpected travel boundary after Pewter Gym entry.")
        if state.boundary is not self._BOUNDARIES[expected_index]:
            raise PewterProgressError("Northbound evidence skipped a required travel boundary.")
        if state.boundary is TravelBoundary.PEWTER_GYM_ENTRANCE and not state.brock_ready_snapshot:
            raise PewterProgressError("Pewter Gym entry failed the healthy Bubble-readiness gate.")
        self._boundary_index = expected_index
        if state.boundary is TravelBoundary.PEWTER_GYM_ENTRANCE:
            self._saw_brock_ready = True
        return state.phase


class CeruleanBoundary(StrEnum):
    UNKNOWN = "unknown"
    ROUTE_3_WEST_ENTRY = "route_3_west_entry"
    ROUTE_4_WEST_ENTRY = "route_4_west_entry"
    MT_MOON_1F_ENTRY = "mt_moon_1f_entry"
    MT_MOON_B1F_DESCENT = "mt_moon_b1f_descent"
    MT_MOON_B2F_ENTRY = "mt_moon_b2f_entry"
    MT_MOON_B1F_ASCENT = "mt_moon_b1f_ascent"
    ROUTE_4_MT_MOON_EXIT = "route_4_mt_moon_exit"
    CERULEAN_WEST_ENTRY = "cerulean_west_entry"


class CeruleanPhase(StrEnum):
    UNKNOWN = "unknown"
    ROUTE_3_REACHED = "route_3_reached"
    ROUTE_3_TRAINER_BATTLE = "route_3_trainer_battle"
    ROUTE_4_REACHED = "route_4_reached"
    MT_MOON_ENTERED = "mt_moon_entered"
    MT_MOON_B1F_REACHED = "mt_moon_b1f_reached"
    MT_MOON_B2F_REACHED = "mt_moon_b2f_reached"
    REQUIRED_ROCKET_BATTLE = "required_rocket_battle"
    REQUIRED_ROCKET_DEFEATED = "required_rocket_defeated"
    SUPER_NERD_BATTLE = "super_nerd_battle"
    SUPER_NERD_DEFEATED = "super_nerd_defeated"
    FOSSIL_OBTAINED = "fossil_obtained"
    MT_MOON_CLEARED = "mt_moon_cleared"
    CERULEAN_REACHED = "cerulean_reached"


@dataclass(frozen=True, slots=True)
class CeruleanChapterState:
    """Semantic evidence for the ordered Brock-to-Cerulean chapter."""

    phase: CeruleanPhase
    boundary: CeruleanBoundary
    controls: InputReadiness
    local_script: int
    current_map_script: int
    beat_brock: bool
    got_tm34: bool
    boulder_badge: bool
    boulder_badge_mirror: bool
    beat_route_3_trainer_0: bool
    beat_route_3_trainer_1: bool
    beat_route_3_trainer_3: bool
    beat_route_3_trainer_6: bool
    beat_required_rocket: bool
    beat_super_nerd: bool
    got_dome_fossil: bool
    got_helix_fossil: bool
    dome_fossil_in_bag: bool
    helix_fossil_in_bag: bool
    current_opponent: int
    trainer_class: int
    trainer_number: int
    engaged_trainer_class: int
    engaged_trainer_set: int
    map_id: int | None
    player_x: int | None
    player_y: int | None
    party_count: int | None
    party_species_ids: tuple[int, ...] | None
    first_party_hp: int | None
    first_party_max_hp: int | None
    first_party_status: int | None
    battle_state: int | None
    battle_result: int | None

    @property
    def post_brock_invariants(self) -> bool:
        species = self.party_species_ids or ()
        return (
            self.beat_brock
            and self.got_tm34
            and self.boulder_badge
            and self.boulder_badge_mirror
            and 1 <= (self.party_count or 0) <= PARTY_LIMIT
            and bool(species)
            and species[0] in SQUIRTLE_LINEAGE_SPECIES_IDS
            and 0 < (self.first_party_hp or 0) <= (self.first_party_max_hp or 0)
        )

    @property
    def fossil_invariants(self) -> bool:
        chose_exactly_one = self.got_dome_fossil ^ self.got_helix_fossil
        corresponding_item = (
            self.got_dome_fossil and self.dome_fossil_in_bag and not self.helix_fossil_in_bag
        ) or (self.got_helix_fossil and self.helix_fossil_in_bag and not self.dome_fossil_in_bag)
        return (
            self.post_brock_invariants
            and self.required_route_3_trainers_defeated
            and self.beat_required_rocket
            and self.beat_super_nerd
            and chose_exactly_one
            and corresponding_item
        )

    @property
    def stable_overworld_snapshot(self) -> bool:
        return (
            self.post_brock_invariants
            and self.battle_state == 0
            and self.local_script == 0
            and self.current_map_script == 0
            and self.controls.ready
        )

    @property
    def travel_boundary_snapshot(self) -> bool:
        if (
            self.boundary is CeruleanBoundary.UNKNOWN
            or not self.stable_overworld_snapshot
            or _cerulean_boundary_position(self.map_id, self.player_x, self.player_y)
            is not self.boundary
        ):
            return False
        pre_fossil = {
            CeruleanBoundary.ROUTE_3_WEST_ENTRY,
            CeruleanBoundary.ROUTE_4_WEST_ENTRY,
            CeruleanBoundary.MT_MOON_1F_ENTRY,
            CeruleanBoundary.MT_MOON_B1F_DESCENT,
            CeruleanBoundary.MT_MOON_B2F_ENTRY,
        }
        if self.boundary is CeruleanBoundary.ROUTE_3_WEST_ENTRY:
            return not self.got_dome_fossil and not self.got_helix_fossil
        if self.boundary in pre_fossil:
            return (
                self.required_route_3_trainers_defeated
                and not self.got_dome_fossil
                and not self.got_helix_fossil
            )
        return self.fossil_invariants

    @property
    def required_route_3_trainer_events(self) -> tuple[bool, bool, bool, bool]:
        return (
            self.beat_route_3_trainer_0,
            self.beat_route_3_trainer_1,
            self.beat_route_3_trainer_3,
            self.beat_route_3_trainer_6,
        )

    @property
    def required_route_3_trainers_defeated(self) -> bool:
        return all(self.required_route_3_trainer_events)

    @property
    def route_3_trainer_battle_index(self) -> int | None:
        if (
            self.phase is not CeruleanPhase.ROUTE_3_TRAINER_BATTLE
            or self.map_id != MapId.ROUTE_3
            or not self.post_brock_invariants
            or self.battle_state != 2
            or self.local_script != 2
            or self.current_map_script != 2
        ):
            return None
        for spec, defeated in zip(
            ROUTE_3_REQUIRED_TRAINER_SPECS,
            self.required_route_3_trainer_events,
            strict=True,
        ):
            event_index, opponent, trainer_class, trainer_number = spec
            if (
                not defeated
                and self.current_opponent == opponent
                and self.trainer_class == trainer_class
                and self.trainer_number == trainer_number
                and self.engaged_trainer_class == opponent
                and self.engaged_trainer_set == trainer_number
            ):
                return event_index
        return None

    @property
    def route_3_trainer_battle_snapshot(self) -> bool:
        return self.route_3_trainer_battle_index is not None

    @property
    def required_rocket_battle_snapshot(self) -> bool:
        return (
            self.phase is CeruleanPhase.REQUIRED_ROCKET_BATTLE
            and self.map_id == MapId.MT_MOON_B2F
            and self.post_brock_invariants
            and self.battle_state == 2
            and self.local_script == 2
            and self.current_map_script == 2
            and self.player_x == MT_MOON_REQUIRED_ROCKET_TRIGGER_X
            and self.player_y == MT_MOON_REQUIRED_ROCKET_TRIGGER_Y
            and not self.beat_required_rocket
            and self.current_opponent == ROCKET_OPPONENT_ID
            and self.trainer_class == ROCKET_TRAINER_CLASS_ID
            and self.trainer_number == MT_MOON_REQUIRED_ROCKET_TRAINER_NUMBER
            and self.engaged_trainer_class == ROCKET_OPPONENT_ID
            and self.engaged_trainer_set == MT_MOON_REQUIRED_ROCKET_TRAINER_NUMBER
        )

    @property
    def super_nerd_battle_snapshot(self) -> bool:
        return (
            self.phase is CeruleanPhase.SUPER_NERD_BATTLE
            and self.map_id == MapId.MT_MOON_B2F
            and self.post_brock_invariants
            and self.beat_required_rocket
            and not self.beat_super_nerd
            and self.battle_state == 2
            and self.local_script == 3
            and self.current_map_script == 3
            and self.current_opponent == MT_MOON_SUPER_NERD_OPPONENT_ID
            and self.trainer_class == SUPER_NERD_TRAINER_CLASS_ID
            and self.trainer_number == MT_MOON_SUPER_NERD_TRAINER_NUMBER
            and self.engaged_trainer_class == MT_MOON_SUPER_NERD_OPPONENT_ID
            and self.engaged_trainer_set == MT_MOON_SUPER_NERD_TRAINER_NUMBER
        )

    @property
    def fossil_snapshot(self) -> bool:
        return (
            self.phase is CeruleanPhase.FOSSIL_OBTAINED
            and self.map_id == MapId.MT_MOON_B2F
            and self.fossil_invariants
            and self.stable_overworld_snapshot
        )

    @property
    def cerulean_snapshot(self) -> bool:
        return (
            self.phase is CeruleanPhase.CERULEAN_REACHED
            and self.boundary is CeruleanBoundary.CERULEAN_WEST_ENTRY
            and self.travel_boundary_snapshot
        )


class CeruleanProgressError(ValueError):
    """Raised when Brock-to-Cerulean evidence skips or contradicts a gate."""


class CeruleanProgressTracker:
    """Latch the exact route, mandatory battles, fossil, and Cerulean in order."""

    _BOUNDARIES = (
        CeruleanBoundary.ROUTE_3_WEST_ENTRY,
        CeruleanBoundary.ROUTE_4_WEST_ENTRY,
        CeruleanBoundary.MT_MOON_1F_ENTRY,
        CeruleanBoundary.MT_MOON_B1F_DESCENT,
        CeruleanBoundary.MT_MOON_B2F_ENTRY,
        CeruleanBoundary.MT_MOON_B1F_ASCENT,
        CeruleanBoundary.ROUTE_4_MT_MOON_EXIT,
        CeruleanBoundary.CERULEAN_WEST_ENTRY,
    )
    _LAST_PRE_FOSSIL_INDEX = 4

    def __init__(self, brock_state: PewterChapterState) -> None:
        if not brock_state.brock_victory_snapshot:
            raise CeruleanProgressError(
                "Cerulean qualification must begin at the verified Brock boundary."
            )
        self._boundary_index = -1
        self._route_3_trainer_index = -1
        self._saw_required_rocket_battle = False
        self._saw_super_nerd_battle = False
        self._fossil_obtained = False

    @property
    def reached_boundaries(self) -> tuple[CeruleanBoundary, ...]:
        return self._BOUNDARIES[: self._boundary_index + 1]

    @property
    def saw_required_rocket_battle(self) -> bool:
        return self._saw_required_rocket_battle

    @property
    def observed_route_3_trainers(self) -> tuple[int, ...]:
        return tuple(
            spec[0] for spec in ROUTE_3_REQUIRED_TRAINER_SPECS[: self._route_3_trainer_index + 1]
        )

    @property
    def saw_super_nerd_battle(self) -> bool:
        return self._saw_super_nerd_battle

    @property
    def fossil_obtained(self) -> bool:
        return self._fossil_obtained

    def observe(self, state: CeruleanChapterState) -> CeruleanPhase:
        if state.fossil_snapshot:
            if not self._saw_super_nerd_battle:
                raise CeruleanProgressError(
                    "Fossil acquisition cannot qualify without the Super Nerd battle."
                )
            self._fossil_obtained = True
            return CeruleanPhase.FOSSIL_OBTAINED

        if state.super_nerd_battle_snapshot:
            if (
                self._boundary_index != self._LAST_PRE_FOSSIL_INDEX
                or not self._saw_required_rocket_battle
                or not state.beat_required_rocket
            ):
                raise CeruleanProgressError(
                    "Super Nerd appeared before the required Mt. Moon Rocket proof."
                )
            self._saw_super_nerd_battle = True
            return CeruleanPhase.SUPER_NERD_BATTLE

        if state.required_rocket_battle_snapshot:
            if self._boundary_index != self._LAST_PRE_FOSSIL_INDEX:
                raise CeruleanProgressError(
                    "Required Rocket appeared before the Mt. Moon B2F entry proof."
                )
            self._saw_required_rocket_battle = True
            return CeruleanPhase.REQUIRED_ROCKET_BATTLE

        if state.route_3_trainer_battle_snapshot:
            if self._boundary_index != 0:
                raise CeruleanProgressError(
                    "Route 3 trainer appeared outside the verified Route 3 segment."
                )
            observed_event = state.route_3_trainer_battle_index
            expected_position = self._route_3_trainer_index + 1
            if (
                self._route_3_trainer_index >= 0
                and observed_event == ROUTE_3_REQUIRED_TRAINER_SPECS[self._route_3_trainer_index][0]
            ):
                return CeruleanPhase.ROUTE_3_TRAINER_BATTLE
            if expected_position >= len(ROUTE_3_REQUIRED_TRAINER_SPECS):
                raise CeruleanProgressError(
                    "Unexpected Route 3 trainer after all required battles."
                )
            expected_event = ROUTE_3_REQUIRED_TRAINER_SPECS[expected_position][0]
            if observed_event != expected_event:
                raise CeruleanProgressError(
                    "Route 3 trainer evidence skipped or reordered a required battle."
                )
            if not all(state.required_route_3_trainer_events[:expected_position]):
                raise CeruleanProgressError(
                    "Route 3 trainer event did not flip after its observed battle."
                )
            self._route_3_trainer_index = expected_position
            return CeruleanPhase.ROUTE_3_TRAINER_BATTLE

        if state.boundary is CeruleanBoundary.UNKNOWN:
            return state.phase
        if not state.travel_boundary_snapshot:
            raise CeruleanProgressError(
                "Cerulean-route boundary failed its stable semantic snapshot."
            )

        expected_index = self._boundary_index + 1
        if self._boundary_index >= 0 and state.boundary is self._BOUNDARIES[self._boundary_index]:
            return state.phase
        if expected_index >= len(self._BOUNDARIES):
            raise CeruleanProgressError("Unexpected boundary after Cerulean City entry.")
        if state.boundary is not self._BOUNDARIES[expected_index]:
            raise CeruleanProgressError("Cerulean evidence skipped a required boundary.")
        if state.boundary is CeruleanBoundary.ROUTE_4_WEST_ENTRY and (
            self._route_3_trainer_index != len(ROUTE_3_REQUIRED_TRAINER_SPECS) - 1
            or not state.required_route_3_trainers_defeated
        ):
            raise CeruleanProgressError(
                "Route 4 cannot qualify before all four required Route 3 battles."
            )
        if expected_index > self._LAST_PRE_FOSSIL_INDEX and not self._fossil_obtained:
            raise CeruleanProgressError("Mt. Moon exit cannot qualify before the fossil proof.")
        self._boundary_index = expected_index
        return state.phase


class CascadePhase(StrEnum):
    """Source-pinned semantic phases from Cerulean arrival through Misty."""

    UNKNOWN = "unknown"
    CERULEAN_READY = "cerulean_ready"
    RIVAL_BATTLE = "rival_battle"
    RIVAL_DEFEATED = "rival_defeated"
    ROUTE_24_TRAINER_BATTLE = "route_24_trainer_battle"
    NUGGET_ROCKET_BATTLE = "nugget_rocket_battle"
    NUGGET_ROCKET_DEFEATED = "nugget_rocket_defeated"
    ROUTE_25_TRAINER_BATTLE = "route_25_trainer_battle"
    BILL_REQUESTED_HELP = "bill_requested_help"
    BILL_CELL_SEPARATOR_USED = "bill_cell_separator_used"
    BILL_RESTORED = "bill_restored"
    SS_TICKET_OBTAINED = "ss_ticket_obtained"
    BILLS_HOUSE_LEFT = "bills_house_left"
    CERULEAN_GYM_TRAINER_BATTLE = "cerulean_gym_trainer_battle"
    CERULEAN_GYM_TRAINER_DEFEATED = "cerulean_gym_trainer_defeated"
    MISTY_BATTLE = "misty_battle"
    MISTY_DEFEATED = "misty_defeated"


@dataclass(frozen=True, slots=True)
class CascadeState:
    """Semantic evidence for the Cerulean rival, Bill, and Cascade Badge."""

    phase: CascadePhase
    controls: InputReadiness
    local_script: int
    current_map_script: int
    prior_chapter_complete: bool
    beat_cerulean_rival: bool
    route_24_trainer_events: tuple[bool, bool, bool, bool, bool]
    got_nugget: bool
    nugget_in_bag: bool
    beat_route_24_rocket: bool
    route_25_trainer_events: tuple[bool, bool, bool, bool]
    bill_said_use_cell_separator: bool
    used_cell_separator_on_bill: bool
    met_bill: bool
    met_bill_2: bool
    got_ss_ticket: bool
    ss_ticket_in_bag: bool
    left_bills_house_after_helping: bool
    beat_cerulean_gym_trainer_0: bool
    beat_misty: bool
    got_tm11: bool
    tm11_in_bag: bool
    cascade_badge: bool
    cascade_badge_mirror: bool
    current_opponent: int
    trainer_class: int
    trainer_number: int
    engaged_trainer_class: int
    engaged_trainer_set: int
    gym_leader_number: int
    map_id: int | None
    player_x: int | None
    player_y: int | None
    party_count: int | None
    party_species_ids: tuple[int, ...] | None
    first_party_hp: int | None
    first_party_max_hp: int | None
    first_party_status: int | None
    battle_state: int | None
    battle_result: int | None

    @property
    def foundation_invariants(self) -> bool:
        species = self.party_species_ids or ()
        return (
            self.prior_chapter_complete
            and 1 <= (self.party_count or 0) <= PARTY_LIMIT
            and bool(species)
            and species[0] in SQUIRTLE_LINEAGE_SPECIES_IDS
            and 0 < (self.first_party_hp or 0) <= (self.first_party_max_hp or 0)
        )

    @property
    def stable_snapshot(self) -> bool:
        return (
            self.foundation_invariants
            and self.battle_state == 0
            and self.local_script == 0
            and self.current_map_script == 0
            and self.controls.ready
        )

    @property
    def no_cascade_progress(self) -> bool:
        return (
            not self.beat_cerulean_rival
            and not any(self.route_24_trainer_events)
            and not self.got_nugget
            and not self.nugget_in_bag
            and not self.beat_route_24_rocket
            and not any(self.route_25_trainer_events)
            and not self.bill_said_use_cell_separator
            and not self.used_cell_separator_on_bill
            and not self.met_bill
            and not self.met_bill_2
            and not self.got_ss_ticket
            and not self.ss_ticket_in_bag
            and not self.left_bills_house_after_helping
            and not self.beat_cerulean_gym_trainer_0
            and not self.beat_misty
            and not self.got_tm11
            and not self.tm11_in_bag
            and not self.cascade_badge
            and not self.cascade_badge_mirror
        )

    @property
    def cerulean_start_snapshot(self) -> bool:
        return (
            self.phase is CascadePhase.CERULEAN_READY
            and self.map_id == MapId.CERULEAN_CITY
            and self.player_x == 0
            and self.player_y == 18
            and self.stable_snapshot
            and self.no_cascade_progress
        )

    @property
    def rival_battle_snapshot(self) -> bool:
        return (
            self.phase is CascadePhase.RIVAL_BATTLE
            and self.map_id == MapId.CERULEAN_CITY
            and self.foundation_invariants
            and self.battle_state == 2
            and self.local_script == 2
            # Cerulean City's custom script table never mirrors its local
            # index through wCurMapScript.
            and self.current_map_script == 0
            and self.player_x in CERULEAN_RIVAL_TRIGGER_XS
            and self.player_y == CERULEAN_RIVAL_TRIGGER_Y
            and not self.beat_cerulean_rival
            and self.current_opponent == RIVAL1_OPPONENT_ID
            and self.trainer_class == RIVAL1_TRAINER_CLASS_ID
            and self.trainer_number == CERULEAN_RIVAL_TRAINER_NUMBER
        )

    @property
    def rival_victory_snapshot(self) -> bool:
        return (
            self.phase is CascadePhase.RIVAL_DEFEATED
            and self.map_id == MapId.CERULEAN_CITY
            and self.stable_snapshot
            and self.battle_result == 0
            and self.beat_cerulean_rival
        )

    @property
    def route_24_trainers_defeated(self) -> bool:
        return all(self.route_24_trainer_events)

    @property
    def route_24_trainer_battle_index(self) -> int | None:
        if (
            self.phase is not CascadePhase.ROUTE_24_TRAINER_BATTLE
            or self.map_id != MapId.ROUTE_24
            or not self.foundation_invariants
            or not self.beat_cerulean_rival
            or self.battle_state != 2
            or self.local_script != 2
            or self.current_map_script != 2
        ):
            return None
        for spec, defeated in zip(
            ROUTE_24_REQUIRED_TRAINER_SPECS,
            self.route_24_trainer_events,
            strict=True,
        ):
            (
                event_index,
                _,
                opponent,
                expected_class,
                expected_number,
                expected_x,
                expected_y,
            ) = spec
            if (
                not defeated
                and self.current_opponent == opponent
                and self.trainer_class == expected_class
                and self.trainer_number == expected_number
                and self.engaged_trainer_class == opponent
                and self.engaged_trainer_set == expected_number
                and self.player_x == expected_x
                and self.player_y == expected_y
            ):
                return event_index
        return None

    @property
    def route_24_trainer_battle_snapshot(self) -> bool:
        return self.route_24_trainer_battle_index is not None

    @property
    def nugget_rocket_battle_snapshot(self) -> bool:
        return (
            self.phase is CascadePhase.NUGGET_ROCKET_BATTLE
            and self.map_id == MapId.ROUTE_24
            and self.foundation_invariants
            and self.beat_cerulean_rival
            and self.route_24_trainers_defeated
            and self.got_nugget
            and self.nugget_in_bag
            and not self.beat_route_24_rocket
            and self.battle_state == 2
            and self.local_script == 3
            and self.current_map_script == 3
            and self.player_x == ROUTE_24_ROCKET_TRIGGER_X
            and self.player_y == ROUTE_24_ROCKET_TRIGGER_Y
            and self.current_opponent == ROCKET_OPPONENT_ID
            and self.trainer_class == ROCKET_TRAINER_CLASS_ID
            and self.trainer_number == ROUTE_24_ROCKET_TRAINER_NUMBER
            and self.engaged_trainer_class == ROCKET_OPPONENT_ID
            and self.engaged_trainer_set == ROUTE_24_ROCKET_TRAINER_NUMBER
        )

    @property
    def nugget_rocket_victory_snapshot(self) -> bool:
        return (
            self.phase is CascadePhase.NUGGET_ROCKET_DEFEATED
            and self.map_id == MapId.ROUTE_24
            and self.stable_snapshot
            and self.battle_result == 0
            and self.beat_cerulean_rival
            and self.route_24_trainers_defeated
            and self.got_nugget
            and self.nugget_in_bag
            and self.beat_route_24_rocket
        )

    @property
    def route_25_trainers_defeated(self) -> bool:
        return all(self.route_25_trainer_events)

    @property
    def route_25_trainer_battle_index(self) -> int | None:
        if (
            self.phase is not CascadePhase.ROUTE_25_TRAINER_BATTLE
            or self.map_id != MapId.ROUTE_25
            or not self.foundation_invariants
            or not self.beat_cerulean_rival
            or not self.route_24_trainers_defeated
            or not self.got_nugget
            or not self.beat_route_24_rocket
            or self.battle_state != 2
            or self.local_script != 2
            or self.current_map_script != 2
        ):
            return None
        for spec, defeated in zip(
            ROUTE_25_REQUIRED_TRAINER_SPECS,
            self.route_25_trainer_events,
            strict=True,
        ):
            (
                event_index,
                _,
                opponent,
                expected_class,
                expected_number,
                expected_x,
                expected_y,
            ) = spec
            if (
                not defeated
                and self.current_opponent == opponent
                and self.trainer_class == expected_class
                and self.trainer_number == expected_number
                and self.engaged_trainer_class == opponent
                and self.engaged_trainer_set == expected_number
                and self.player_x == expected_x
                and self.player_y == expected_y
            ):
                return event_index
        return None

    @property
    def route_25_trainer_battle_snapshot(self) -> bool:
        return self.route_25_trainer_battle_index is not None

    @property
    def bill_route_invariants(self) -> bool:
        return (
            self.foundation_invariants
            and self.beat_cerulean_rival
            and self.route_24_trainers_defeated
            and self.got_nugget
            and self.beat_route_24_rocket
            and self.route_25_trainers_defeated
        )

    @property
    def bill_requested_help_snapshot(self) -> bool:
        return (
            self.phase is CascadePhase.BILL_REQUESTED_HELP
            and self.map_id == MapId.BILLS_HOUSE
            and self.bill_route_invariants
            and self.battle_state == 0
            and self.local_script == 3
            and self.current_map_script == 0
            and self.controls.ready
            and self.bill_said_use_cell_separator
            and not self.used_cell_separator_on_bill
            and not self.met_bill
            and not self.met_bill_2
            and not self.got_ss_ticket
            and not self.left_bills_house_after_helping
        )

    @property
    def bill_cell_separator_used_snapshot(self) -> bool:
        return (
            self.phase is CascadePhase.BILL_CELL_SEPARATOR_USED
            and self.map_id == MapId.BILLS_HOUSE
            and self.bill_route_invariants
            and self.battle_state == 0
            and self.local_script in {3, 4}
            and self.current_map_script == 0
            and self.bill_said_use_cell_separator
            and self.used_cell_separator_on_bill
            and not self.met_bill
            and not self.met_bill_2
            and not self.got_ss_ticket
            and not self.left_bills_house_after_helping
        )

    @property
    def bill_restored_snapshot(self) -> bool:
        return (
            self.phase is CascadePhase.BILL_RESTORED
            and self.map_id == MapId.BILLS_HOUSE
            and self.bill_route_invariants
            and self.stable_snapshot
            and self.bill_said_use_cell_separator
            and self.used_cell_separator_on_bill
            and self.met_bill
            and self.met_bill_2
            and not self.got_ss_ticket
            and not self.left_bills_house_after_helping
        )

    @property
    def ss_ticket_snapshot(self) -> bool:
        return (
            self.phase is CascadePhase.SS_TICKET_OBTAINED
            and self.map_id == MapId.BILLS_HOUSE
            and self.bill_route_invariants
            and self.stable_snapshot
            and self.bill_said_use_cell_separator
            and self.used_cell_separator_on_bill
            and self.met_bill
            and self.met_bill_2
            and self.got_ss_ticket
            and self.ss_ticket_in_bag
            and not self.left_bills_house_after_helping
        )

    @property
    def bills_house_left_snapshot(self) -> bool:
        return (
            self.phase is CascadePhase.BILLS_HOUSE_LEFT
            and self.map_id == MapId.ROUTE_25
            and self.player_x == 45
            and self.player_y == 4
            and self.bill_route_invariants
            and self.stable_snapshot
            and self.bill_said_use_cell_separator
            and self.used_cell_separator_on_bill
            and self.met_bill
            and self.met_bill_2
            and self.got_ss_ticket
            and self.ss_ticket_in_bag
            and self.left_bills_house_after_helping
        )

    @property
    def bill_completion_invariants(self) -> bool:
        return (
            self.bill_route_invariants
            and self.bill_said_use_cell_separator
            and self.used_cell_separator_on_bill
            and self.met_bill
            and self.met_bill_2
            and self.got_ss_ticket
            and self.ss_ticket_in_bag
            and self.left_bills_house_after_helping
        )

    @property
    def cerulean_gym_trainer_battle_snapshot(self) -> bool:
        return (
            self.phase is CascadePhase.CERULEAN_GYM_TRAINER_BATTLE
            and self.map_id == MapId.CERULEAN_GYM
            and self.bill_completion_invariants
            and self.foundation_invariants
            and self.battle_state == 2
            and self.local_script == 2
            and self.current_map_script == 2
            and self.player_x == CERULEAN_GYM_REQUIRED_TRAINER_TRIGGER_X
            and self.player_y == CERULEAN_GYM_REQUIRED_TRAINER_TRIGGER_Y
            and not self.beat_cerulean_gym_trainer_0
            and not self.beat_misty
            and not self.got_tm11
            and not self.tm11_in_bag
            and not self.cascade_badge
            and not self.cascade_badge_mirror
            and self.current_opponent == JR_TRAINER_F_OPPONENT_ID
            and self.trainer_class == JR_TRAINER_F_TRAINER_CLASS_ID
            and self.trainer_number == CERULEAN_GYM_REQUIRED_TRAINER_NUMBER
            and self.engaged_trainer_class == JR_TRAINER_F_OPPONENT_ID
            and self.engaged_trainer_set == CERULEAN_GYM_REQUIRED_TRAINER_NUMBER
        )

    @property
    def cerulean_gym_trainer_victory_snapshot(self) -> bool:
        return (
            self.phase is CascadePhase.CERULEAN_GYM_TRAINER_DEFEATED
            and self.map_id == MapId.CERULEAN_GYM
            and self.bill_completion_invariants
            and self.stable_snapshot
            and self.battle_result == 0
            and self.beat_cerulean_gym_trainer_0
            and not self.beat_misty
            and not self.got_tm11
            and not self.tm11_in_bag
            and not self.cascade_badge
            and not self.cascade_badge_mirror
            and self.first_party_status == 0
        )

    @property
    def gym_route_invariants(self) -> bool:
        return self.bill_completion_invariants and self.beat_cerulean_gym_trainer_0

    @property
    def misty_battle_snapshot(self) -> bool:
        return (
            self.phase is CascadePhase.MISTY_BATTLE
            and self.map_id == MapId.CERULEAN_GYM
            and self.gym_route_invariants
            and self.foundation_invariants
            and self.battle_state == 2
            and self.local_script == 3
            # Misty's custom gym script advances locally but does not update
            # the mirrored current-map script used by ordinary trainers.
            and self.current_map_script == 0
            and self.player_x == MISTY_TRIGGER_X
            and self.player_y == MISTY_TRIGGER_Y
            and not self.beat_misty
            and not self.got_tm11
            and not self.tm11_in_bag
            and not self.cascade_badge
            and not self.cascade_badge_mirror
            and self.current_opponent == MISTY_OPPONENT_ID
            and self.trainer_class == MISTY_TRAINER_CLASS_ID
            and self.trainer_number == MISTY_TRAINER_NUMBER
            and self.engaged_trainer_class == MISTY_OPPONENT_ID
            and self.engaged_trainer_set == MISTY_TRAINER_NUMBER
            and self.gym_leader_number == MISTY_GYM_LEADER_NUMBER
        )

    @property
    def misty_victory_snapshot(self) -> bool:
        return (
            self.phase is CascadePhase.MISTY_DEFEATED
            and self.map_id == MapId.CERULEAN_GYM
            and self.gym_route_invariants
            and self.stable_snapshot
            and self.battle_result == 0
            and self.beat_misty
            and self.got_tm11
            and self.tm11_in_bag
            and self.cascade_badge
            and self.cascade_badge_mirror
            and self.first_party_status == 0
        )


class CascadeProgressError(ValueError):
    """Raised when rival-to-Cascade evidence skips or contradicts a gate."""


class CascadeProgressTracker:
    """Latch the exact live battles and Bill event transitions in order."""

    def __init__(self, cerulean_state: CeruleanChapterState) -> None:
        if not cerulean_state.cerulean_snapshot:
            raise CascadeProgressError(
                "Cascade qualification must begin at verified Cerulean arrival."
            )
        self._saw_rival_battle = False
        self._rival_defeated = False
        self._route_24_trainer_position = -1
        self._saw_nugget_rocket_battle = False
        self._nugget_rocket_defeated = False
        self._route_25_trainer_position = -1
        self._bill_stage = 0
        self._saw_cerulean_gym_trainer_battle = False
        self._cerulean_gym_trainer_defeated = False
        self._saw_misty_battle = False
        self._misty_defeated = False

    @property
    def saw_rival_battle(self) -> bool:
        return self._saw_rival_battle

    @property
    def rival_defeated(self) -> bool:
        return self._rival_defeated

    @property
    def observed_route_24_trainers(self) -> tuple[int, ...]:
        return tuple(
            spec[0]
            for spec in ROUTE_24_REQUIRED_TRAINER_SPECS[: self._route_24_trainer_position + 1]
        )

    @property
    def saw_nugget_rocket_battle(self) -> bool:
        return self._saw_nugget_rocket_battle

    @property
    def nugget_rocket_defeated(self) -> bool:
        return self._nugget_rocket_defeated

    @property
    def observed_route_25_trainers(self) -> tuple[int, ...]:
        return tuple(
            spec[0]
            for spec in ROUTE_25_REQUIRED_TRAINER_SPECS[: self._route_25_trainer_position + 1]
        )

    @property
    def bills_house_left(self) -> bool:
        return self._bill_stage >= 5

    @property
    def saw_cerulean_gym_trainer_battle(self) -> bool:
        return self._saw_cerulean_gym_trainer_battle

    @property
    def cerulean_gym_trainer_defeated(self) -> bool:
        return self._cerulean_gym_trainer_defeated

    @property
    def saw_misty_battle(self) -> bool:
        return self._saw_misty_battle

    @property
    def misty_defeated(self) -> bool:
        return self._misty_defeated

    def observe(self, state: CascadeState) -> CascadePhase:
        if state.misty_victory_snapshot:
            if not self._saw_misty_battle:
                raise CascadeProgressError(
                    "Misty victory cannot qualify without the observed live battle."
                )
            self._misty_defeated = True
            return CascadePhase.MISTY_DEFEATED

        if state.misty_battle_snapshot:
            if not self._cerulean_gym_trainer_defeated:
                raise CascadeProgressError(
                    "Misty appeared before the required Cerulean Gym trainer victory."
                )
            self._saw_misty_battle = True
            return CascadePhase.MISTY_BATTLE

        if state.cerulean_gym_trainer_victory_snapshot:
            if not self._saw_cerulean_gym_trainer_battle:
                raise CascadeProgressError(
                    "Cerulean Gym trainer victory lacks the observed live battle."
                )
            self._cerulean_gym_trainer_defeated = True
            return CascadePhase.CERULEAN_GYM_TRAINER_DEFEATED

        if state.cerulean_gym_trainer_battle_snapshot:
            if self._bill_stage != 5:
                raise CascadeProgressError(
                    "Cerulean Gym trainer appeared before Bill's Route 25 exit proof."
                )
            self._saw_cerulean_gym_trainer_battle = True
            return CascadePhase.CERULEAN_GYM_TRAINER_BATTLE

        if state.bills_house_left_snapshot:
            if self._bill_stage == 5:
                return CascadePhase.BILLS_HOUSE_LEFT
            if self._bill_stage != 4:
                raise CascadeProgressError(
                    "Bill's Route 25 exit appeared before the S.S. Ticket proof."
                )
            self._bill_stage = 5
            return CascadePhase.BILLS_HOUSE_LEFT

        if state.ss_ticket_snapshot:
            if self._bill_stage == 4:
                return CascadePhase.SS_TICKET_OBTAINED
            if self._bill_stage != 3:
                raise CascadeProgressError("S.S. Ticket appeared before Bill was restored.")
            self._bill_stage = 4
            return CascadePhase.SS_TICKET_OBTAINED

        if state.bill_restored_snapshot:
            if self._bill_stage == 3:
                return CascadePhase.BILL_RESTORED
            if self._bill_stage != 2:
                raise CascadeProgressError(
                    "Bill's restored form appeared before the cell separator proof."
                )
            self._bill_stage = 3
            return CascadePhase.BILL_RESTORED

        if state.bill_cell_separator_used_snapshot:
            if self._bill_stage == 2:
                return CascadePhase.BILL_CELL_SEPARATOR_USED
            if self._bill_stage != 1:
                raise CascadeProgressError("Bill's cell separator event skipped the help request.")
            self._bill_stage = 2
            return CascadePhase.BILL_CELL_SEPARATOR_USED

        if state.bill_requested_help_snapshot:
            if self._bill_stage == 1:
                return CascadePhase.BILL_REQUESTED_HELP
            if self._bill_stage != 0:
                raise CascadeProgressError(
                    "Bill's help request regressed after a later Bill proof."
                )
            if (
                not self._nugget_rocket_defeated
                or self._route_25_trainer_position != len(ROUTE_25_REQUIRED_TRAINER_SPECS) - 1
                or not state.route_25_trainers_defeated
            ):
                raise CascadeProgressError(
                    "Bill appeared before all four selected Route 25 battles."
                )
            self._bill_stage = 1
            return CascadePhase.BILL_REQUESTED_HELP

        if state.route_25_trainer_battle_snapshot:
            if not self._nugget_rocket_defeated:
                raise CascadeProgressError(
                    "Route 25 trainer appeared before the Nugget Rocket victory."
                )
            observed_event = state.route_25_trainer_battle_index
            current_event = (
                ROUTE_25_REQUIRED_TRAINER_SPECS[self._route_25_trainer_position][0]
                if self._route_25_trainer_position >= 0
                else None
            )
            if observed_event == current_event:
                return CascadePhase.ROUTE_25_TRAINER_BATTLE
            expected_position = self._route_25_trainer_position + 1
            if expected_position >= len(ROUTE_25_REQUIRED_TRAINER_SPECS):
                raise CascadeProgressError(
                    "Unexpected Route 25 trainer after the selected battles."
                )
            if observed_event != ROUTE_25_REQUIRED_TRAINER_SPECS[expected_position][0]:
                raise CascadeProgressError(
                    "Route 25 trainer evidence skipped or reordered a selected battle."
                )
            if not all(state.route_25_trainer_events[:expected_position]):
                raise CascadeProgressError(
                    "A Route 25 trainer event did not flip after its live battle."
                )
            self._route_25_trainer_position = expected_position
            return CascadePhase.ROUTE_25_TRAINER_BATTLE

        if state.nugget_rocket_victory_snapshot:
            if not self._saw_nugget_rocket_battle:
                raise CascadeProgressError(
                    "Nugget Rocket victory lacks the observed live Rocket battle."
                )
            self._nugget_rocket_defeated = True
            return CascadePhase.NUGGET_ROCKET_DEFEATED

        if state.nugget_rocket_battle_snapshot:
            if (
                not self._rival_defeated
                or self._route_24_trainer_position != len(ROUTE_24_REQUIRED_TRAINER_SPECS) - 1
                or not state.route_24_trainers_defeated
            ):
                raise CascadeProgressError(
                    "Nugget Rocket appeared before all five bridge trainers."
                )
            self._saw_nugget_rocket_battle = True
            return CascadePhase.NUGGET_ROCKET_BATTLE

        if state.route_24_trainer_battle_snapshot:
            if not self._rival_defeated:
                raise CascadeProgressError(
                    "Route 24 trainer appeared before the Cerulean rival victory."
                )
            observed_event = state.route_24_trainer_battle_index
            current_event = (
                ROUTE_24_REQUIRED_TRAINER_SPECS[self._route_24_trainer_position][0]
                if self._route_24_trainer_position >= 0
                else None
            )
            if observed_event == current_event:
                return CascadePhase.ROUTE_24_TRAINER_BATTLE
            expected_position = self._route_24_trainer_position + 1
            if expected_position >= len(ROUTE_24_REQUIRED_TRAINER_SPECS):
                raise CascadeProgressError(
                    "Unexpected Route 24 trainer after all five bridge battles."
                )
            if observed_event != ROUTE_24_REQUIRED_TRAINER_SPECS[expected_position][0]:
                raise CascadeProgressError(
                    "Route 24 trainer evidence skipped or reordered a bridge battle."
                )
            if not all(state.route_24_trainer_events[:expected_position]):
                raise CascadeProgressError(
                    "A Route 24 trainer event did not flip after its live battle."
                )
            self._route_24_trainer_position = expected_position
            return CascadePhase.ROUTE_24_TRAINER_BATTLE

        if state.rival_victory_snapshot:
            if not self._saw_rival_battle:
                raise CascadeProgressError("Cerulean rival victory lacks the observed live battle.")
            self._rival_defeated = True
            return CascadePhase.RIVAL_DEFEATED

        if state.rival_battle_snapshot:
            if self._saw_rival_battle:
                return CascadePhase.RIVAL_BATTLE
            self._saw_rival_battle = True
            return CascadePhase.RIVAL_BATTLE

        if state.cerulean_start_snapshot:
            return CascadePhase.CERULEAN_READY

        if state.phase is not CascadePhase.UNKNOWN:
            raise CascadeProgressError(
                f"{state.phase.value} failed its source-pinned semantic snapshot."
            )
        return CascadePhase.UNKNOWN


class VermilionPhase(StrEnum):
    """Source-pinned semantic phases from Misty toward Vermilion City."""

    UNKNOWN = "unknown"
    MISTY_READY = "misty_ready"
    TRASHED_HOUSE_ENTERED = "trashed_house_entered"
    ROBBERY_REAR_EXIT = "robbery_rear_exit"
    ROCKET_THIEF_BATTLE = "rocket_thief_battle"
    TM28_OBTAINED = "tm28_obtained"
    ROUTE_5_REACHED = "route_5_reached"
    UNDERGROUND_NORTH_ENTRANCE = "underground_north_entrance"
    UNDERGROUND_TUNNEL = "underground_tunnel"
    UNDERGROUND_SOUTH_ENTRANCE = "underground_south_entrance"
    ROUTE_6_REACHED = "route_6_reached"
    ROUTE_6_TRAINER_F_BATTLE = "route_6_trainer_f_battle"
    ROUTE_6_TRAINER_F_DEFEATED = "route_6_trainer_f_defeated"
    ROUTE_6_TRAINER_M_BATTLE = "route_6_trainer_m_battle"
    ROUTE_6_TRAINER_M_DEFEATED = "route_6_trainer_m_defeated"
    VERMILION_REACHED = "vermilion_reached"


@dataclass(frozen=True, slots=True)
class VermilionState:
    """Semantic evidence for the robbery and Underground Path route."""

    phase: VermilionPhase
    controls: InputReadiness
    local_script: int
    current_map_script: int
    prior_chapter_complete: bool
    beat_rocket_thief: bool
    tm28_in_bag: bool
    route_6_trainer_events: tuple[bool, bool, bool, bool, bool, bool]
    current_opponent: int
    trainer_class: int
    trainer_number: int
    engaged_trainer_class: int
    engaged_trainer_set: int
    map_id: int | None
    player_x: int | None
    player_y: int | None
    party_count: int | None
    party_species_ids: tuple[int, ...] | None
    first_party_hp: int | None
    first_party_max_hp: int | None
    first_party_status: int | None
    battle_state: int | None
    battle_result: int | None

    @property
    def foundation_invariants(self) -> bool:
        species = self.party_species_ids or ()
        return (
            self.prior_chapter_complete
            and 1 <= (self.party_count or 0) <= PARTY_LIMIT
            and bool(species)
            and species[0] in SQUIRTLE_LINEAGE_SPECIES_IDS
            and 0 < (self.first_party_hp or 0) <= (self.first_party_max_hp or 0)
            and self.first_party_status == 0
        )

    @property
    def stable_snapshot(self) -> bool:
        return (
            self.foundation_invariants
            and self.battle_state == 0
            and self.local_script == 0
            and self.current_map_script == 0
            and self.controls.ready
        )

    @property
    def misty_ready_snapshot(self) -> bool:
        return (
            self.phase is VermilionPhase.MISTY_READY
            and self.map_id == MapId.CERULEAN_GYM
            and self.player_x == MISTY_TRIGGER_X
            and self.player_y == MISTY_TRIGGER_Y
            and self.stable_snapshot
            and not self.beat_rocket_thief
            and not self.tm28_in_bag
            and not any(self.route_6_trainer_events)
        )

    @property
    def trashed_house_snapshot(self) -> bool:
        return (
            self.phase is VermilionPhase.TRASHED_HOUSE_ENTERED
            and self.map_id == MapId.CERULEAN_TRASHED_HOUSE
            and self.player_x == 2
            and self.player_y == 7
            and self.stable_snapshot
            and not self.beat_rocket_thief
            and not self.tm28_in_bag
        )

    @property
    def robbery_rear_exit_snapshot(self) -> bool:
        return (
            self.phase is VermilionPhase.ROBBERY_REAR_EXIT
            and self.map_id == MapId.CERULEAN_CITY
            and self.player_x == 27
            and self.player_y == 9
            and self.stable_snapshot
            and not self.beat_rocket_thief
            and not self.tm28_in_bag
        )

    @property
    def rocket_thief_battle_snapshot(self) -> bool:
        return (
            self.phase is VermilionPhase.ROCKET_THIEF_BATTLE
            and self.map_id == MapId.CERULEAN_CITY
            and self.foundation_invariants
            and self.battle_state == 2
            and self.local_script == 4
            and self.current_map_script == 0
            and self.player_x == CERULEAN_ROCKET_TRIGGER_X
            and self.player_y in CERULEAN_ROCKET_TRIGGER_YS
            and not self.beat_rocket_thief
            and not self.tm28_in_bag
            and self.current_opponent == ROCKET_OPPONENT_ID
            and self.trainer_class == ROCKET_TRAINER_CLASS_ID
            and self.trainer_number == CERULEAN_ROCKET_TRAINER_NUMBER
            and self.engaged_trainer_class == ROCKET_OPPONENT_ID
            and self.engaged_trainer_set == CERULEAN_ROCKET_TRAINER_NUMBER
        )

    @property
    def tm28_snapshot(self) -> bool:
        return (
            self.phase is VermilionPhase.TM28_OBTAINED
            and self.map_id == MapId.CERULEAN_CITY
            and self.player_x == CERULEAN_ROCKET_TRIGGER_X
            and self.player_y in CERULEAN_ROCKET_TRIGGER_YS
            and self.stable_snapshot
            and self.beat_rocket_thief
            and self.tm28_in_bag
            and self.battle_result == 0
        )

    @property
    def route_5_snapshot(self) -> bool:
        return (
            self.phase is VermilionPhase.ROUTE_5_REACHED
            and self.map_id == MapId.ROUTE_5
            and self.player_x == 3
            and self.player_y == 0
            and self.stable_snapshot
            and self.beat_rocket_thief
            and self.tm28_in_bag
            and not any(self.route_6_trainer_events)
        )

    @property
    def underground_north_entrance_snapshot(self) -> bool:
        return (
            self.phase is VermilionPhase.UNDERGROUND_NORTH_ENTRANCE
            and self.map_id == MapId.UNDERGROUND_PATH_ROUTE_5
            and self.player_x == 3
            and self.player_y == 7
            and self.stable_snapshot
            and self.beat_rocket_thief
            and self.tm28_in_bag
            and not any(self.route_6_trainer_events)
        )

    @property
    def underground_tunnel_snapshot(self) -> bool:
        return (
            self.phase is VermilionPhase.UNDERGROUND_TUNNEL
            and self.map_id == MapId.UNDERGROUND_PATH_NORTH_SOUTH
            and self.player_x == 5
            and self.player_y == 4
            and self.stable_snapshot
            and self.beat_rocket_thief
            and self.tm28_in_bag
            and not any(self.route_6_trainer_events)
        )

    @property
    def underground_south_entrance_snapshot(self) -> bool:
        return (
            self.phase is VermilionPhase.UNDERGROUND_SOUTH_ENTRANCE
            and self.map_id == MapId.UNDERGROUND_PATH_ROUTE_6
            and self.player_x == 4
            and self.player_y == 4
            and self.stable_snapshot
            and self.beat_rocket_thief
            and self.tm28_in_bag
            and not any(self.route_6_trainer_events)
        )

    @property
    def route_6_snapshot(self) -> bool:
        return (
            self.phase is VermilionPhase.ROUTE_6_REACHED
            and self.map_id == MapId.ROUTE_6
            and self.player_x == 17
            and self.player_y == 14
            and self.stable_snapshot
            and self.beat_rocket_thief
            and self.tm28_in_bag
            and not any(self.route_6_trainer_events)
        )

    @property
    def vermilion_snapshot(self) -> bool:
        return (
            self.phase is VermilionPhase.VERMILION_REACHED
            and self.map_id == MapId.VERMILION_CITY
            and self.player_x == 19
            and self.player_y == 0
            and self.stable_snapshot
            and self.beat_rocket_thief
            and self.tm28_in_bag
            and self.route_6_trainer_events == (False, False, False, True, True, False)
        )

    @property
    def route_6_trainer_f_battle_snapshot(self) -> bool:
        return (
            self.phase is VermilionPhase.ROUTE_6_TRAINER_F_BATTLE
            and self.map_id == MapId.ROUTE_6
            and self.foundation_invariants
            and self.battle_state == 2
            and self.local_script == 2
            and self.current_map_script == 2
            and self.player_x == 9
            and self.player_y == 30
            and self.route_6_trainer_events == (False, False, False, False, False, False)
            and self.current_opponent == ROUTE_6_JR_TRAINER_F_OPPONENT_ID
            and self.trainer_class == ROUTE_6_JR_TRAINER_F_CLASS_ID
            and self.trainer_number == ROUTE_6_JR_TRAINER_F_NUMBER
            and self.engaged_trainer_class == ROUTE_6_JR_TRAINER_F_OPPONENT_ID
            and self.engaged_trainer_set == ROUTE_6_JR_TRAINER_F_NUMBER
        )

    @property
    def route_6_trainer_f_defeated_snapshot(self) -> bool:
        return (
            self.phase is VermilionPhase.ROUTE_6_TRAINER_F_DEFEATED
            and self.map_id == MapId.ROUTE_6
            and self.player_x == 9
            and self.player_y == 30
            and self.stable_snapshot
            and self.route_6_trainer_events == (False, False, False, False, True, False)
            and self.battle_result == 0
        )

    @property
    def route_6_trainer_m_battle_snapshot(self) -> bool:
        return (
            self.phase is VermilionPhase.ROUTE_6_TRAINER_M_BATTLE
            and self.map_id == MapId.ROUTE_6
            and self.foundation_invariants
            and self.battle_state == 2
            and self.local_script == 2
            and self.current_map_script == 2
            and self.player_x == 9
            and self.player_y == 31
            and self.route_6_trainer_events == (False, False, False, False, True, False)
            and self.current_opponent == ROUTE_6_JR_TRAINER_M_OPPONENT_ID
            and self.trainer_class == ROUTE_6_JR_TRAINER_M_CLASS_ID
            and self.trainer_number == ROUTE_6_JR_TRAINER_M_NUMBER
            and self.engaged_trainer_class == ROUTE_6_JR_TRAINER_M_OPPONENT_ID
            and self.engaged_trainer_set == ROUTE_6_JR_TRAINER_M_NUMBER
        )

    @property
    def route_6_trainer_m_defeated_snapshot(self) -> bool:
        return (
            self.phase is VermilionPhase.ROUTE_6_TRAINER_M_DEFEATED
            and self.map_id == MapId.ROUTE_6
            and self.player_x == 9
            and self.player_y == 31
            and self.stable_snapshot
            and self.route_6_trainer_events == (False, False, False, True, True, False)
            and self.battle_result == 0
        )


class VermilionProgressError(ValueError):
    """Raised when Misty-to-Route-6 evidence skips or contradicts a gate."""


class VermilionProgressTracker:
    """Latch the robbery battle and source-ordered travel boundaries."""

    _ORDERED_PHASES = (
        VermilionPhase.MISTY_READY,
        VermilionPhase.TRASHED_HOUSE_ENTERED,
        VermilionPhase.ROBBERY_REAR_EXIT,
        VermilionPhase.ROCKET_THIEF_BATTLE,
        VermilionPhase.TM28_OBTAINED,
        VermilionPhase.ROUTE_5_REACHED,
        VermilionPhase.UNDERGROUND_NORTH_ENTRANCE,
        VermilionPhase.UNDERGROUND_TUNNEL,
        VermilionPhase.UNDERGROUND_SOUTH_ENTRANCE,
        VermilionPhase.ROUTE_6_REACHED,
        VermilionPhase.ROUTE_6_TRAINER_F_BATTLE,
        VermilionPhase.ROUTE_6_TRAINER_F_DEFEATED,
        VermilionPhase.ROUTE_6_TRAINER_M_BATTLE,
        VermilionPhase.ROUTE_6_TRAINER_M_DEFEATED,
        VermilionPhase.VERMILION_REACHED,
    )

    def __init__(self, misty_state: CascadeState) -> None:
        if not misty_state.misty_victory_snapshot:
            raise VermilionProgressError(
                "Vermilion qualification must begin at verified Misty victory."
            )
        self._phase_index = -1
        self._saw_rocket_battle = False

    @property
    def saw_rocket_battle(self) -> bool:
        return self._saw_rocket_battle

    def observe(self, state: VermilionState) -> VermilionPhase:
        snapshot_name = {
            VermilionPhase.MISTY_READY: "misty_ready_snapshot",
            VermilionPhase.TRASHED_HOUSE_ENTERED: "trashed_house_snapshot",
            VermilionPhase.ROBBERY_REAR_EXIT: "robbery_rear_exit_snapshot",
            VermilionPhase.ROCKET_THIEF_BATTLE: "rocket_thief_battle_snapshot",
            VermilionPhase.TM28_OBTAINED: "tm28_snapshot",
            VermilionPhase.ROUTE_5_REACHED: "route_5_snapshot",
            VermilionPhase.UNDERGROUND_NORTH_ENTRANCE: ("underground_north_entrance_snapshot"),
            VermilionPhase.UNDERGROUND_TUNNEL: "underground_tunnel_snapshot",
            VermilionPhase.UNDERGROUND_SOUTH_ENTRANCE: ("underground_south_entrance_snapshot"),
            VermilionPhase.ROUTE_6_REACHED: "route_6_snapshot",
            VermilionPhase.ROUTE_6_TRAINER_F_BATTLE: ("route_6_trainer_f_battle_snapshot"),
            VermilionPhase.ROUTE_6_TRAINER_F_DEFEATED: ("route_6_trainer_f_defeated_snapshot"),
            VermilionPhase.ROUTE_6_TRAINER_M_BATTLE: ("route_6_trainer_m_battle_snapshot"),
            VermilionPhase.ROUTE_6_TRAINER_M_DEFEATED: ("route_6_trainer_m_defeated_snapshot"),
            VermilionPhase.VERMILION_REACHED: "vermilion_snapshot",
        }.get(state.phase)
        if snapshot_name is None:
            return VermilionPhase.UNKNOWN
        if not getattr(state, snapshot_name):
            raise VermilionProgressError(
                f"{state.phase.value} failed its source-pinned semantic snapshot."
            )

        expected_index = self._phase_index + 1
        if self._phase_index >= 0 and state.phase is self._ORDERED_PHASES[self._phase_index]:
            return state.phase
        if expected_index >= len(self._ORDERED_PHASES):
            raise VermilionProgressError("Unexpected boundary after Route 6.")
        if state.phase is not self._ORDERED_PHASES[expected_index]:
            raise VermilionProgressError(
                "Vermilion-route evidence skipped a required semantic boundary."
            )
        if state.phase is VermilionPhase.TM28_OBTAINED and not self._saw_rocket_battle:
            raise VermilionProgressError("Rocket thief victory lacks the observed live battle.")
        if state.phase is VermilionPhase.ROCKET_THIEF_BATTLE:
            self._saw_rocket_battle = True
        self._phase_index = expected_index
        return state.phase


class SSAnnePhase(StrEnum):
    """Source-pinned semantic phases from Vermilion City through HM01."""

    UNKNOWN = "unknown"
    VERMILION_READY = "vermilion_ready"
    HEALED = "healed"
    DOCK_REACHED = "dock_reached"
    SHIP_1F_REACHED = "ship_1f_reached"
    SHIP_2F_REACHED = "ship_2f_reached"
    RIVAL_BATTLE = "rival_battle"
    RIVAL_DEFEATED = "rival_defeated"
    CAPTAIN_ROOM_REACHED = "captain_room_reached"
    HM01_OBTAINED = "hm01_obtained"


@dataclass(frozen=True, slots=True)
class SSAnneState:
    """ROM-free evidence for the S.S. Anne rival and Captain reward."""

    phase: SSAnnePhase
    controls: InputReadiness
    local_script: int
    current_map_script: int
    prior_chapter_complete: bool
    rubbed_captains_back: bool
    got_hm01: bool
    hm01_in_bag: bool
    cut_fact: bool
    current_opponent: int
    trainer_class: int
    trainer_number: int
    engaged_trainer_class: int
    engaged_trainer_set: int
    map_id: int | None
    player_x: int | None
    player_y: int | None
    party_count: int | None
    party_species_ids: tuple[int, ...] | None
    first_party_hp: int | None
    first_party_max_hp: int | None
    first_party_status: int | None
    first_party_pp: tuple[int, ...] | None
    battle_state: int | None
    battle_result: int | None

    @property
    def foundation_invariants(self) -> bool:
        species = self.party_species_ids or ()
        return (
            self.prior_chapter_complete
            and 1 <= (self.party_count or 0) <= PARTY_LIMIT
            and bool(species)
            and species[0] in SQUIRTLE_LINEAGE_SPECIES_IDS
            and 0 < (self.first_party_hp or 0) <= (self.first_party_max_hp or 0)
            and self.first_party_status == 0
        )

    @property
    def stable_snapshot(self) -> bool:
        return (
            self.foundation_invariants
            and self.battle_state == 0
            and self.current_map_script == 0
            and self.controls.ready
        )

    @property
    def no_cut_evidence(self) -> bool:
        return (
            not self.rubbed_captains_back
            and not self.got_hm01
            and not self.hm01_in_bag
            and not self.cut_fact
        )

    @property
    def vermilion_ready_snapshot(self) -> bool:
        return (
            self.phase is SSAnnePhase.VERMILION_READY
            and self.map_id == MapId.VERMILION_CITY
            and (self.player_x, self.player_y) == (19, 0)
            and self.local_script == 0
            and self.stable_snapshot
            and self.no_cut_evidence
        )

    @property
    def healed_snapshot(self) -> bool:
        return (
            self.phase is SSAnnePhase.HEALED
            and self.map_id == MapId.VERMILION_POKECENTER
            and (self.player_x, self.player_y) == (3, 3)
            and self.local_script == 0
            and self.stable_snapshot
            and self.first_party_hp == self.first_party_max_hp
            and all((pp & 0x3F) > 0 for pp in (self.first_party_pp or ()))
            and self.no_cut_evidence
        )

    @property
    def dock_snapshot(self) -> bool:
        return (
            self.phase is SSAnnePhase.DOCK_REACHED
            and self.map_id == MapId.VERMILION_DOCK
            and (self.player_x, self.player_y) == (14, 0)
            and self.local_script == 0
            and self.stable_snapshot
            and self.no_cut_evidence
        )

    @property
    def ship_1f_snapshot(self) -> bool:
        return (
            self.phase is SSAnnePhase.SHIP_1F_REACHED
            and self.map_id == MapId.SS_ANNE_1F
            and (self.player_x, self.player_y) == (27, 0)
            and self.local_script == 0
            and self.stable_snapshot
            and self.no_cut_evidence
        )

    @property
    def ship_2f_snapshot(self) -> bool:
        return (
            self.phase is SSAnnePhase.SHIP_2F_REACHED
            and self.map_id == MapId.SS_ANNE_2F
            and (self.player_x, self.player_y) == (2, 4)
            and self.local_script == 0
            and self.stable_snapshot
            and self.no_cut_evidence
        )

    @property
    def rival_battle_snapshot(self) -> bool:
        return (
            self.phase is SSAnnePhase.RIVAL_BATTLE
            and self.map_id == MapId.SS_ANNE_2F
            and (self.player_x, self.player_y) == (36, 8)
            and self.foundation_invariants
            and self.battle_state == 2
            and self.local_script == 2
            and self.current_map_script == 0
            and self.current_opponent == RIVAL2_OPPONENT_ID
            and self.trainer_class == RIVAL2_TRAINER_CLASS_ID
            and self.trainer_number == SS_ANNE_RIVAL_TRAINER_NUMBER
            and self.engaged_trainer_class == SS_ANNE_RIVAL_ENGAGED_CLASS
            and self.engaged_trainer_set == SS_ANNE_RIVAL_ENGAGED_SET
            and self.no_cut_evidence
        )

    @property
    def rival_defeated_snapshot(self) -> bool:
        return (
            self.phase is SSAnnePhase.RIVAL_DEFEATED
            and self.map_id == MapId.SS_ANNE_2F
            and (self.player_x, self.player_y) == (36, 8)
            and self.local_script == 4
            and self.stable_snapshot
            and self.battle_result == 0
            and self.no_cut_evidence
        )

    @property
    def captain_room_snapshot(self) -> bool:
        return (
            self.phase is SSAnnePhase.CAPTAIN_ROOM_REACHED
            and self.map_id == MapId.SS_ANNE_CAPTAINS_ROOM
            and (self.player_x, self.player_y) == (0, 7)
            and self.local_script == 0
            and self.stable_snapshot
            and self.no_cut_evidence
        )

    @property
    def hm01_snapshot(self) -> bool:
        return (
            self.phase is SSAnnePhase.HM01_OBTAINED
            and self.map_id == MapId.SS_ANNE_CAPTAINS_ROOM
            and (self.player_x, self.player_y) == (4, 3)
            and self.local_script == 0
            and self.stable_snapshot
            and self.rubbed_captains_back
            and self.got_hm01
            and self.hm01_in_bag
            and self.cut_fact
        )


class SSAnneProgressError(ValueError):
    """Raised when S.S. Anne evidence skips or contradicts a required gate."""


class SSAnneProgressTracker:
    """Latch the live rival battle before accepting Captain/HM01 evidence."""

    _ORDERED_PHASES = (
        SSAnnePhase.VERMILION_READY,
        SSAnnePhase.HEALED,
        SSAnnePhase.DOCK_REACHED,
        SSAnnePhase.SHIP_1F_REACHED,
        SSAnnePhase.SHIP_2F_REACHED,
        SSAnnePhase.RIVAL_BATTLE,
        SSAnnePhase.RIVAL_DEFEATED,
        SSAnnePhase.CAPTAIN_ROOM_REACHED,
        SSAnnePhase.HM01_OBTAINED,
    )

    def __init__(self, vermilion_state: VermilionState) -> None:
        if not vermilion_state.vermilion_snapshot:
            raise SSAnneProgressError("S.S. Anne qualification must begin at verified Vermilion.")
        self._phase_index = -1
        self._saw_rival_battle = False

    @property
    def saw_rival_battle(self) -> bool:
        return self._saw_rival_battle

    def observe(self, state: SSAnneState) -> SSAnnePhase:
        snapshot_name = {
            SSAnnePhase.VERMILION_READY: "vermilion_ready_snapshot",
            SSAnnePhase.HEALED: "healed_snapshot",
            SSAnnePhase.DOCK_REACHED: "dock_snapshot",
            SSAnnePhase.SHIP_1F_REACHED: "ship_1f_snapshot",
            SSAnnePhase.SHIP_2F_REACHED: "ship_2f_snapshot",
            SSAnnePhase.RIVAL_BATTLE: "rival_battle_snapshot",
            SSAnnePhase.RIVAL_DEFEATED: "rival_defeated_snapshot",
            SSAnnePhase.CAPTAIN_ROOM_REACHED: "captain_room_snapshot",
            SSAnnePhase.HM01_OBTAINED: "hm01_snapshot",
        }.get(state.phase)
        if snapshot_name is None:
            return SSAnnePhase.UNKNOWN
        if not getattr(state, snapshot_name):
            raise SSAnneProgressError(
                f"{state.phase.value} failed its source-pinned semantic snapshot."
            )
        if self._phase_index >= 0 and state.phase is self._ORDERED_PHASES[self._phase_index]:
            return state.phase
        expected_index = self._phase_index + 1
        if (
            expected_index >= len(self._ORDERED_PHASES)
            or state.phase is not self._ORDERED_PHASES[expected_index]
        ):
            raise SSAnneProgressError("S.S. Anne evidence skipped a required semantic boundary.")
        if state.phase is SSAnnePhase.RIVAL_DEFEATED and not self._saw_rival_battle:
            raise SSAnneProgressError("S.S. Anne rival victory lacks the observed live battle.")
        if state.phase is SSAnnePhase.RIVAL_BATTLE:
            self._saw_rival_battle = True
        self._phase_index = expected_index
        return state.phase


class SurgePhase(StrEnum):
    """Ordered semantic gates from HM01 through the Thunder Badge."""

    HM01_READY = "hm01_ready"
    HEALED = "healed"
    BALLS_PURCHASED = "balls_purchased"
    SPEAROW_ENCOUNTER = "spearow_encounter"
    SPEAROW_CAPTURED = "spearow_captured"
    DIGLETT_CAPTURED = "diglett_captured"
    DUX_TRADED = "dux_traded"
    CUT_TAUGHT = "cut_taught"
    DIG_TAUGHT = "dig_taught"
    GYM_REACHED = "gym_reached"
    FIRST_SWITCH = "first_switch"
    SECOND_SWITCH = "second_switch"
    SURGE_BATTLE = "surge_battle"
    SURGE_DEFEATED = "surge_defeated"
    REWARD_STABLE = "reward_stable"


@dataclass(frozen=True, slots=True)
class SurgeState:
    """ROM-free evidence consumed by the ordered Surge progress tracker."""

    phase: SurgePhase
    hm01_ready: bool = False
    healed: bool = False
    balls_purchased: bool = False
    spearow_encounter: bool = False
    spearow_captured: bool = False
    diglett_captured: bool = False
    dux_traded: bool = False
    cut_taught: bool = False
    dig_taught: bool = False
    gym_reached: bool = False
    first_switch: bool = False
    second_switch: bool = False
    surge_battle: bool = False
    surge_defeated: bool = False
    reward_stable: bool = False

    def phase_snapshot(self) -> bool:
        return bool(getattr(self, self.phase.value))


class SurgeProgressError(ValueError):
    """Raised when Surge evidence skips or contradicts a required gate."""


class SurgeProgressTracker:
    """Require all fourteen Surge chapter gates in source-pinned order."""

    _ORDERED_PHASES = tuple(SurgePhase)

    def __init__(self) -> None:
        self._phase_index = -1
        self._saw_live_battle = False

    @property
    def saw_live_battle(self) -> bool:
        return self._saw_live_battle

    def observe(self, state: SurgeState) -> SurgePhase:
        if not state.phase_snapshot():
            raise SurgeProgressError(f"{state.phase.value} failed its semantic snapshot.")
        expected_index = self._phase_index + 1
        if self._phase_index >= 0 and state.phase is self._ORDERED_PHASES[self._phase_index]:
            return state.phase
        if (
            expected_index >= len(self._ORDERED_PHASES)
            or state.phase is not self._ORDERED_PHASES[expected_index]
        ):
            raise SurgeProgressError("Surge evidence skipped a required semantic gate.")
        if state.phase is SurgePhase.SURGE_BATTLE:
            self._saw_live_battle = True
        if (
            state.phase in {SurgePhase.SURGE_DEFEATED, SurgePhase.REWARD_STABLE}
            and not self._saw_live_battle
        ):
            raise SurgeProgressError("Surge victory lacks an observed live leader battle.")
        self._phase_index = expected_index
        return state.phase


class PokemonRedStateReader:
    def __init__(self, memory: ReadOnlyMemory) -> None:
        self._memory = memory

    def read(self) -> RawGameState:
        status = self._memory.read_u8(RamAddress.STATUS_FLAGS_6)
        game_started = bool(status & GAME_TIMER_COUNTING_MASK)
        if not game_started:
            return RawGameState(False, None, None, None, None, None)

        bag_count = min(self._memory.read_u8(RamAddress.NUM_BAG_ITEMS), MAX_BAG_ITEMS)
        bag_items = tuple(
            self._memory.read_u8(int(RamAddress.BAG_ITEMS) + index * 2)
            for index in range(bag_count)
        )
        party_count = min(self._memory.read_u8(RamAddress.PARTY_COUNT), PARTY_LIMIT)
        party_species = tuple(
            self._memory.read_u8(int(RamAddress.PARTY_SPECIES) + index)
            for index in range(party_count)
        )
        first_party_level = (
            self._memory.read_u8(RamAddress.PARTY_MON_1_LEVEL) if party_count else None
        )
        first_party_hp = self._read_u16_be(RamAddress.PARTY_MON_1_HP) if party_count else None
        first_party_max_hp = (
            self._read_u16_be(RamAddress.PARTY_MON_1_MAX_HP) if party_count else None
        )
        first_party_status = (
            self._memory.read_u8(RamAddress.PARTY_MON_1_STATUS) if party_count else None
        )
        first_party_moves = (
            tuple(
                self._memory.read_u8(int(RamAddress.PARTY_MON_1_MOVES) + index)
                for index in range(4)
            )
            if party_count
            else None
        )
        first_party_pp = (
            tuple(
                self._memory.read_u8(int(RamAddress.PARTY_MON_1_PP) + index) for index in range(4)
            )
            if party_count
            else None
        )
        events = bytes(
            self._memory.read_u8(int(RamAddress.EVENT_FLAGS) + index)
            for index in range(EVENT_FLAG_BYTES)
        )
        battle_state = self._memory.read_u8(RamAddress.IS_IN_BATTLE)
        return RawGameState(
            game_started=True,
            map_id=self._memory.read_u8(RamAddress.CURRENT_MAP),
            player_x=self._memory.read_u8(RamAddress.PLAYER_X),
            player_y=self._memory.read_u8(RamAddress.PLAYER_Y),
            party_count=party_count,
            battle_state=battle_state,
            badge_bits=self._memory.read_u8(RamAddress.OBTAINED_BADGES),
            bag_item_ids=bag_items,
            event_flags=events,
            party_species_ids=party_species,
            first_party_level=first_party_level,
            first_party_hp=first_party_hp,
            first_party_max_hp=first_party_max_hp,
            first_party_status=first_party_status,
            battle_result=self._memory.read_u8(RamAddress.BATTLE_RESULT),
            first_party_moves=first_party_moves,
            first_party_pp=first_party_pp,
            enemy_species_id=self._memory.read_u8(RamAddress.ENEMY_SPECIES),
            enemy_hp=self._read_u16_be(RamAddress.ENEMY_HP),
            enemy_level=self._memory.read_u8(RamAddress.ENEMY_LEVEL),
            enemy_max_hp=self._read_u16_be(RamAddress.ENEMY_MAX_HP),
            player_attack_stage=(
                self._memory.read_u8(RamAddress.PLAYER_ATTACK_STAGE) if battle_state else None
            ),
            player_accuracy_stage=(
                self._memory.read_u8(RamAddress.PLAYER_ACCURACY_STAGE) if battle_state else None
            ),
            enemy_defense_stage=(
                self._memory.read_u8(RamAddress.ENEMY_DEFENSE_STAGE) if battle_state else None
            ),
        )

    def read_bedroom_input_state(self) -> BedroomInputState:
        """Read the two revision-specific input-readiness symbols for Red's bedroom."""
        return BedroomInputState(
            joy_ignore=self._memory.read_u8(RamAddress.JOY_IGNORE),
            map_script=self._memory.read_u8(RamAddress.REDS_HOUSE_2F_SCRIPT),
        )

    def read_opening_control_state(self, raw: RawGameState) -> OpeningControlState:
        """Translate opening scripts and event bits into a bounded semantic phase."""
        joy_ignore = self._memory.read_u8(RamAddress.JOY_IGNORE)
        lab_script = self._memory.read_u8(RamAddress.OAKS_LAB_SCRIPT)
        pallet_script = self._memory.read_u8(RamAddress.PALLET_TOWN_SCRIPT)
        confirm_allowed = not bool(joy_ignore & JOY_IGNORE_CONFIRM_MASK)
        cancel_allowed = not bool(joy_ignore & JOY_IGNORE_CANCEL_MASK)
        movement_allowed = not bool(joy_ignore & JOY_IGNORE_MOVEMENT_MASK)
        followed = _event(raw.event_flags, EventFlag.FOLLOWED_OAK_INTO_LAB)
        followed_2 = _event(raw.event_flags, EventFlag.FOLLOWED_OAK_INTO_LAB_2)
        asked = _event(raw.event_flags, EventFlag.OAK_ASKED_TO_CHOOSE_MON)
        starter = _event(raw.event_flags, EventFlag.GOT_STARTER)
        first_species = raw.party_species_ids[0] if raw.party_species_ids else None

        phase = OpeningPhase.UNKNOWN
        if (
            raw.map_id == MapId.OAKS_LAB
            and raw.player_x == 7
            and raw.player_y == 4
            and raw.party_count == 1
            and starter
            and lab_script == OAKS_LAB_STARTER_OBTAINED_SCRIPT
            and joy_ignore == 0
        ):
            phase = OpeningPhase.STARTER_OBTAINED
        elif (
            raw.map_id == MapId.OAKS_LAB
            and raw.player_x == 5
            and raw.player_y == 3
            and raw.party_count == 0
            and followed
            and followed_2
            and asked
            and not starter
            and lab_script == OAKS_LAB_SELECTION_READY_SCRIPT
            and joy_ignore == 0
        ):
            phase = OpeningPhase.STARTER_SELECTION_READY
        elif _event(raw.event_flags, EventFlag.OAK_APPEARED_IN_PALLET):
            phase = OpeningPhase.OAK_ESCORT
        elif raw.map_id == MapId.PALLET_TOWN and pallet_script == 0 and movement_allowed:
            phase = OpeningPhase.PALLET_FREE
        elif raw.map_id == MapId.REDS_HOUSE_1F and movement_allowed:
            phase = OpeningPhase.DOWNSTAIRS
        elif (
            raw.map_id == MapId.REDS_HOUSE_2F
            and movement_allowed
            and self._memory.read_u8(RamAddress.REDS_HOUSE_2F_SCRIPT) == REDS_HOUSE_2F_NOOP_SCRIPT
        ):
            phase = OpeningPhase.BEDROOM_READY

        return OpeningControlState(
            phase=phase,
            confirm_allowed=confirm_allowed,
            cancel_allowed=cancel_allowed,
            movement_allowed=movement_allowed,
            followed_oak_into_lab=followed and followed_2,
            asked_to_choose=asked,
            starter_obtained=starter,
            first_party_species=first_species,
        )

    def read_oaks_errand_state(self, raw: RawGameState) -> OaksErrandState:
        """Translate pinned script, event, inventory, and party state into one phase."""
        joy_ignore = self._memory.read_u8(RamAddress.JOY_IGNORE)
        lab_script = self._memory.read_u8(RamAddress.OAKS_LAB_SCRIPT)
        mart_script = self._memory.read_u8(RamAddress.VIRIDIAN_MART_SCRIPT)
        battled_rival = _event(raw.event_flags, EventFlag.BATTLED_RIVAL_IN_OAKS_LAB)
        got_oaks_parcel = _event(raw.event_flags, EventFlag.GOT_OAKS_PARCEL)
        oak_got_parcel = _event(raw.event_flags, EventFlag.OAK_GOT_PARCEL)
        got_pokedex = _event(raw.event_flags, EventFlag.GOT_POKEDEX)
        parcel_in_bag = ItemId.OAKS_PARCEL in set(raw.bag_item_ids or ())
        first_species = raw.party_species_ids[0] if raw.party_species_ids else None

        phase = OaksErrandPhase.UNKNOWN
        if (
            raw.map_id == MapId.OAKS_LAB
            and raw.battle_state == 0
            and lab_script == 18
            and joy_ignore == 0
            and got_oaks_parcel
            and oak_got_parcel
            and got_pokedex
            and not parcel_in_bag
            and first_species == SQUIRTLE_SPECIES_ID
        ):
            phase = OaksErrandPhase.POKEDEX_OBTAINED
        elif (
            raw.map_id == MapId.VIRIDIAN_MART
            and raw.battle_state == 0
            and mart_script == 2
            and joy_ignore == 0
            and got_oaks_parcel
            and parcel_in_bag
        ):
            phase = OaksErrandPhase.PARCEL_OBTAINED
        elif (
            raw.map_id == MapId.OAKS_LAB
            and raw.battle_state == 0
            and lab_script == 18
            and joy_ignore == 0
            and battled_rival
            and first_species == SQUIRTLE_SPECIES_ID
        ):
            phase = OaksErrandPhase.RIVAL_DEFEATED
        elif raw.map_id == MapId.OAKS_LAB and raw.battle_state == 2 and lab_script == 12:
            phase = OaksErrandPhase.RIVAL_BATTLE
        elif (
            raw.map_id == MapId.OAKS_LAB
            and raw.party_count == 1
            and first_species == SQUIRTLE_SPECIES_ID
            and lab_script == OAKS_LAB_STARTER_OBTAINED_SCRIPT
        ):
            phase = OaksErrandPhase.STARTER_READY

        return OaksErrandState(
            phase=phase,
            joy_ignore=joy_ignore,
            lab_script=lab_script,
            mart_script=mart_script,
            battled_rival=battled_rival,
            got_oaks_parcel=got_oaks_parcel,
            oak_got_parcel=oak_got_parcel,
            got_pokedex=got_pokedex,
            parcel_in_bag=parcel_in_bag,
            first_party_species=first_species,
            first_party_level=raw.first_party_level,
            first_party_hp=raw.first_party_hp,
            first_party_max_hp=raw.first_party_max_hp,
            battle_result=raw.battle_result,
            map_id=raw.map_id,
            battle_state=raw.battle_state,
        )

    def read_battle_menu_state(self, raw: RawGameState) -> BattleMenuState:
        """Translate the pinned battle-menu symbols into a safe semantic state.

        In the pinned pret/pokered source, ``wTopMenuItemY``,
        ``wTopMenuItemX``, and ``wMenuWatchedKeys`` distinguish these menus.
        A live ``▶`` at ``wMenuCursorLocation`` proves that ``HandleMenuInput``
        still owns the menu; selection replaces it with ``▷`` before the
        signature bytes are cleared. ``wCurrentMenuItem`` is one-based only in
        the move menu.
        """
        if raw.battle_state not in {1, 2}:
            return BattleMenuState(BattleMenuPhase.UNKNOWN)

        signature = (
            self._memory.read_u8(RamAddress.TOP_MENU_ITEM_Y),
            self._memory.read_u8(RamAddress.TOP_MENU_ITEM_X),
            self._memory.read_u8(RamAddress.MENU_WATCHED_KEYS),
        )
        if signature in {
            MAIN_BATTLE_MENU_LEFT_SIGNATURE,
            MAIN_BATTLE_MENU_RIGHT_SIGNATURE,
        }:
            selected_row = self._memory.read_u8(RamAddress.CURRENT_MENU_ITEM)
            if not 0 <= selected_row <= 1 or not self._active_menu_cursor():
                return BattleMenuState(BattleMenuPhase.UNKNOWN)
            selected_main_command = selected_row
            if signature == MAIN_BATTLE_MENU_RIGHT_SIGNATURE:
                selected_main_command += 2
            if MIN_BATTLE_COMMAND <= selected_main_command <= MAX_BATTLE_COMMAND:
                return BattleMenuState(
                    BattleMenuPhase.MAIN,
                    selected_main_command=selected_main_command,
                )
        if signature == MOVE_BATTLE_MENU_SIGNATURE:
            selected_move_slot = self._memory.read_u8(RamAddress.CURRENT_MENU_ITEM)
            if (
                MIN_MOVE_MENU_SLOT <= selected_move_slot <= MAX_MOVE_MENU_SLOT
                and self._active_menu_cursor()
            ):
                return BattleMenuState(
                    BattleMenuPhase.MOVE,
                    selected_move_slot=selected_move_slot,
                )
        return BattleMenuState(BattleMenuPhase.UNKNOWN)

    def _active_menu_cursor(self) -> bool:
        cursor_address = self._memory.read_u8(RamAddress.MENU_CURSOR_LOCATION)
        cursor_address |= self._memory.read_u8(int(RamAddress.MENU_CURSOR_LOCATION) + 1) << 8
        if not (
            int(RamAddress.TILE_MAP) <= cursor_address < int(RamAddress.TILE_MAP) + TILE_MAP_SIZE
        ):
            return False
        return self._memory.read_u8(cursor_address) == FILLED_MENU_CURSOR_TILE

    def read_input_readiness(self) -> InputReadiness:
        return InputReadiness(
            joy_ignore=self._memory.read_u8(RamAddress.JOY_IGNORE),
            simulated_joypad_index=self._memory.read_u8(RamAddress.SIMULATED_JOYPAD_INDEX),
            npc_movement_script_table=self._memory.read_u8(RamAddress.NPC_MOVEMENT_SCRIPT_TABLE),
            player_moving_direction=self._memory.read_u8(RamAddress.PLAYER_MOVING_DIRECTION),
            status_flags_5=self._memory.read_u8(RamAddress.STATUS_FLAGS_5),
            movement_flags=self._memory.read_u8(RamAddress.MOVEMENT_FLAGS),
        )

    def read_pewter_chapter_state(self, raw: RawGameState) -> PewterChapterState:
        """Translate route, script, battle, and badge evidence into one phase."""
        controls = self.read_input_readiness()
        got_oaks_parcel = _event(raw.event_flags, EventFlag.GOT_OAKS_PARCEL)
        oak_got_parcel = _event(raw.event_flags, EventFlag.OAK_GOT_PARCEL)
        got_pokedex = _event(raw.event_flags, EventFlag.GOT_POKEDEX)
        beat_brock = _event(raw.event_flags, EventFlag.BEAT_BROCK)
        got_tm34 = _event(raw.event_flags, EventFlag.GOT_TM34)
        parcel_in_bag = ItemId.OAKS_PARCEL in set(raw.bag_item_ids or ())
        tm34_in_bag = ItemId.TM34_BIDE in set(raw.bag_item_ids or ())
        local_script = self._local_script(raw.map_id)
        current_map_script = self._memory.read_u8(RamAddress.CURRENT_MAP_SCRIPT)
        badge_bits = raw.badge_bits or 0
        badge_mirror = self._memory.read_u8(RamAddress.BEAT_GYM_FLAGS)
        boundary = _travel_boundary(raw)

        phase = NorthboundPhase.UNKNOWN
        if (
            raw.map_id == MapId.PEWTER_GYM
            and raw.battle_state == 0
            and raw.battle_result == 0
            and beat_brock
            and got_tm34
            and tm34_in_bag
            and bool(badge_bits & Badge.BOULDER)
            and bool(badge_mirror & Badge.BOULDER)
            and local_script == 0
            and current_map_script == 0
            and controls.ready
        ):
            phase = NorthboundPhase.BROCK_DEFEATED
        elif (
            raw.map_id == MapId.PEWTER_GYM
            and raw.battle_state == 2
            and local_script == 3
            and current_map_script == 3
            and self._memory.read_u8(RamAddress.CURRENT_OPPONENT) == BROCK_OPPONENT_ID
            and self._memory.read_u8(RamAddress.TRAINER_CLASS) == BROCK_TRAINER_CLASS_ID
            and self._memory.read_u8(RamAddress.ENGAGED_TRAINER_CLASS) == BROCK_OPPONENT_ID
            and self._memory.read_u8(RamAddress.GYM_LEADER_NUMBER) == BROCK_GYM_LEADER_NUMBER
        ):
            phase = NorthboundPhase.BROCK_BATTLE
        elif boundary is TravelBoundary.PEWTER_GYM_ENTRANCE:
            phase = NorthboundPhase.PEWTER_GYM_ENTERED
        elif boundary is TravelBoundary.PEWTER_SOUTH_EDGE:
            phase = NorthboundPhase.PEWTER_REACHED
        elif boundary in {
            TravelBoundary.ROUTE_2_NORTH_RETURN,
            TravelBoundary.FOREST_NORTH_GATE,
        }:
            phase = NorthboundPhase.FOREST_CLEARED
        elif boundary is TravelBoundary.FOREST_SOUTH_ENTRY:
            phase = NorthboundPhase.FOREST_ENTERED
        elif boundary is TravelBoundary.FOREST_SOUTH_GATE:
            phase = NorthboundPhase.FOREST_GATE_REACHED
        elif boundary is TravelBoundary.ROUTE_2_SOUTH_EDGE:
            phase = NorthboundPhase.ROUTE_2_SOUTH_REACHED
        elif boundary is TravelBoundary.VIRIDIAN_SOUTH_EDGE:
            phase = NorthboundPhase.VIRIDIAN_REACHED
        elif boundary is TravelBoundary.PALLET_LAB_EXTERIOR:
            phase = NorthboundPhase.LAB_EXITED

        return PewterChapterState(
            phase=phase,
            boundary=boundary,
            controls=controls,
            local_script=local_script,
            current_map_script=current_map_script,
            oak_lab_script=self._memory.read_u8(RamAddress.OAKS_LAB_SCRIPT),
            got_oaks_parcel=got_oaks_parcel,
            oak_got_parcel=oak_got_parcel,
            got_pokedex=got_pokedex,
            parcel_in_bag=parcel_in_bag,
            beat_brock=beat_brock,
            got_tm34=got_tm34,
            tm34_in_bag=tm34_in_bag,
            boulder_badge=bool(badge_bits & Badge.BOULDER),
            boulder_badge_mirror=bool(badge_mirror & Badge.BOULDER),
            current_opponent=self._memory.read_u8(RamAddress.CURRENT_OPPONENT),
            trainer_class=self._memory.read_u8(RamAddress.TRAINER_CLASS),
            engaged_trainer_class=self._memory.read_u8(RamAddress.ENGAGED_TRAINER_CLASS),
            gym_leader_number=self._memory.read_u8(RamAddress.GYM_LEADER_NUMBER),
            map_id=raw.map_id,
            player_x=raw.player_x,
            player_y=raw.player_y,
            party_count=raw.party_count,
            first_party_species=(raw.party_species_ids[0] if raw.party_species_ids else None),
            first_party_hp=raw.first_party_hp,
            first_party_max_hp=raw.first_party_max_hp,
            first_party_level=raw.first_party_level,
            first_party_status=raw.first_party_status,
            battle_state=raw.battle_state,
            battle_result=raw.battle_result,
            first_party_moves=raw.first_party_moves,
            first_party_pp=raw.first_party_pp,
        )

    def read_cerulean_chapter_state(self, raw: RawGameState) -> CeruleanChapterState:
        """Translate the pinned Route 3, Mt. Moon, and Cerulean evidence."""
        controls = self.read_input_readiness()
        local_script = self._local_script(raw.map_id)
        current_map_script = self._memory.read_u8(RamAddress.CURRENT_MAP_SCRIPT)
        boundary = _cerulean_boundary(raw)
        items = set(raw.bag_item_ids or ())
        badge_bits = raw.badge_bits or 0
        badge_mirror = self._memory.read_u8(RamAddress.BEAT_GYM_FLAGS)

        beat_brock = _event(raw.event_flags, EventFlag.BEAT_BROCK)
        got_tm34 = _event(raw.event_flags, EventFlag.GOT_TM34)
        required_route_3_events = (
            _event(raw.event_flags, EventFlag.BEAT_ROUTE_3_TRAINER_0),
            _event(raw.event_flags, EventFlag.BEAT_ROUTE_3_TRAINER_1),
            _event(raw.event_flags, EventFlag.BEAT_ROUTE_3_TRAINER_3),
            _event(raw.event_flags, EventFlag.BEAT_ROUTE_3_TRAINER_6),
        )
        beat_required_rocket = _event(raw.event_flags, MT_MOON_REQUIRED_ROCKET_EVENT)
        beat_super_nerd = _event(raw.event_flags, EventFlag.BEAT_MT_MOON_EXIT_SUPER_NERD)
        got_dome_fossil = _event(raw.event_flags, EventFlag.GOT_DOME_FOSSIL)
        got_helix_fossil = _event(raw.event_flags, EventFlag.GOT_HELIX_FOSSIL)

        current_opponent = self._memory.read_u8(RamAddress.CURRENT_OPPONENT)
        trainer_class = self._memory.read_u8(RamAddress.TRAINER_CLASS)
        trainer_number = self._memory.read_u8(RamAddress.TRAINER_NUMBER)
        engaged_trainer_class = self._memory.read_u8(RamAddress.ENGAGED_TRAINER_CLASS)
        engaged_trainer_set = self._memory.read_u8(RamAddress.ENGAGED_TRAINER_SET)
        route_3_trainer_position = _required_route_3_trainer_position(
            current_opponent,
            trainer_class,
            trainer_number,
            engaged_trainer_class,
            engaged_trainer_set,
        )

        phase = CeruleanPhase.UNKNOWN
        if boundary is CeruleanBoundary.CERULEAN_WEST_ENTRY:
            phase = CeruleanPhase.CERULEAN_REACHED
        elif boundary in {
            CeruleanBoundary.MT_MOON_B1F_ASCENT,
            CeruleanBoundary.ROUTE_4_MT_MOON_EXIT,
        }:
            phase = CeruleanPhase.MT_MOON_CLEARED
        elif (
            raw.map_id == MapId.MT_MOON_B2F
            and raw.battle_state == 0
            and beat_super_nerd
            and got_dome_fossil ^ got_helix_fossil
            and local_script == 0
            and current_map_script == 0
            and controls.ready
        ):
            phase = CeruleanPhase.FOSSIL_OBTAINED
        elif (
            raw.map_id == MapId.MT_MOON_B2F
            and raw.battle_state == 2
            and local_script == 3
            and current_map_script == 3
            and current_opponent == MT_MOON_SUPER_NERD_OPPONENT_ID
            and trainer_class == SUPER_NERD_TRAINER_CLASS_ID
            and trainer_number == MT_MOON_SUPER_NERD_TRAINER_NUMBER
        ):
            phase = CeruleanPhase.SUPER_NERD_BATTLE
        elif beat_super_nerd:
            phase = CeruleanPhase.SUPER_NERD_DEFEATED
        elif (
            raw.map_id == MapId.MT_MOON_B2F
            and raw.battle_state == 2
            and local_script == 2
            and current_map_script == 2
            and raw.player_x == MT_MOON_REQUIRED_ROCKET_TRIGGER_X
            and raw.player_y == MT_MOON_REQUIRED_ROCKET_TRIGGER_Y
            and not beat_required_rocket
            and current_opponent == ROCKET_OPPONENT_ID
            and trainer_class == ROCKET_TRAINER_CLASS_ID
            and trainer_number == MT_MOON_REQUIRED_ROCKET_TRAINER_NUMBER
            and engaged_trainer_class == ROCKET_OPPONENT_ID
            and engaged_trainer_set == MT_MOON_REQUIRED_ROCKET_TRAINER_NUMBER
        ):
            phase = CeruleanPhase.REQUIRED_ROCKET_BATTLE
        elif beat_required_rocket:
            phase = CeruleanPhase.REQUIRED_ROCKET_DEFEATED
        elif (
            raw.map_id == MapId.ROUTE_3
            and raw.battle_state == 2
            and local_script == 2
            and current_map_script == 2
            and route_3_trainer_position is not None
            and not required_route_3_events[route_3_trainer_position]
        ):
            phase = CeruleanPhase.ROUTE_3_TRAINER_BATTLE
        elif boundary is CeruleanBoundary.MT_MOON_B2F_ENTRY:
            phase = CeruleanPhase.MT_MOON_B2F_REACHED
        elif boundary is CeruleanBoundary.MT_MOON_B1F_DESCENT:
            phase = CeruleanPhase.MT_MOON_B1F_REACHED
        elif boundary is CeruleanBoundary.MT_MOON_1F_ENTRY:
            phase = CeruleanPhase.MT_MOON_ENTERED
        elif boundary is CeruleanBoundary.ROUTE_4_WEST_ENTRY:
            phase = CeruleanPhase.ROUTE_4_REACHED
        elif boundary is CeruleanBoundary.ROUTE_3_WEST_ENTRY:
            phase = CeruleanPhase.ROUTE_3_REACHED

        return CeruleanChapterState(
            phase=phase,
            boundary=boundary,
            controls=controls,
            local_script=local_script,
            current_map_script=current_map_script,
            beat_brock=beat_brock,
            got_tm34=got_tm34,
            boulder_badge=bool(badge_bits & Badge.BOULDER),
            boulder_badge_mirror=bool(badge_mirror & Badge.BOULDER),
            beat_route_3_trainer_0=required_route_3_events[0],
            beat_route_3_trainer_1=required_route_3_events[1],
            beat_route_3_trainer_3=required_route_3_events[2],
            beat_route_3_trainer_6=required_route_3_events[3],
            beat_required_rocket=beat_required_rocket,
            beat_super_nerd=beat_super_nerd,
            got_dome_fossil=got_dome_fossil,
            got_helix_fossil=got_helix_fossil,
            dome_fossil_in_bag=ItemId.DOME_FOSSIL in items,
            helix_fossil_in_bag=ItemId.HELIX_FOSSIL in items,
            current_opponent=current_opponent,
            trainer_class=trainer_class,
            trainer_number=trainer_number,
            engaged_trainer_class=engaged_trainer_class,
            engaged_trainer_set=engaged_trainer_set,
            map_id=raw.map_id,
            player_x=raw.player_x,
            player_y=raw.player_y,
            party_count=raw.party_count,
            party_species_ids=raw.party_species_ids,
            first_party_hp=raw.first_party_hp,
            first_party_max_hp=raw.first_party_max_hp,
            first_party_status=raw.first_party_status,
            battle_state=raw.battle_state,
            battle_result=raw.battle_result,
        )

    def read_cascade_state(self, raw: RawGameState) -> CascadeState:
        """Translate the pinned Cerulean rival, Bill, and Misty evidence."""
        controls = self.read_input_readiness()
        local_script = self._local_script(raw.map_id)
        current_map_script = self._memory.read_u8(RamAddress.CURRENT_MAP_SCRIPT)
        items = set(raw.bag_item_ids or ())
        badge_bits = raw.badge_bits or 0
        badge_mirror = self._memory.read_u8(RamAddress.BEAT_GYM_FLAGS)

        route_24_events = tuple(
            _event(raw.event_flags, spec[1]) for spec in ROUTE_24_REQUIRED_TRAINER_SPECS
        )
        route_25_events = tuple(
            _event(raw.event_flags, spec[1]) for spec in ROUTE_25_REQUIRED_TRAINER_SPECS
        )
        state = CascadeState(
            phase=CascadePhase.UNKNOWN,
            controls=controls,
            local_script=local_script,
            current_map_script=current_map_script,
            prior_chapter_complete=_cascade_prior_chapter_complete(raw, items, badge_mirror),
            beat_cerulean_rival=_event(raw.event_flags, EventFlag.BEAT_CERULEAN_RIVAL),
            route_24_trainer_events=(
                route_24_events[0],
                route_24_events[1],
                route_24_events[2],
                route_24_events[3],
                route_24_events[4],
            ),
            got_nugget=_event(raw.event_flags, EventFlag.GOT_NUGGET),
            nugget_in_bag=ItemId.NUGGET in items,
            beat_route_24_rocket=_event(raw.event_flags, EventFlag.BEAT_ROUTE_24_ROCKET),
            route_25_trainer_events=(
                route_25_events[0],
                route_25_events[1],
                route_25_events[2],
                route_25_events[3],
            ),
            bill_said_use_cell_separator=_event(
                raw.event_flags, EventFlag.BILL_SAID_USE_CELL_SEPARATOR
            ),
            used_cell_separator_on_bill=_event(
                raw.event_flags, EventFlag.USED_CELL_SEPARATOR_ON_BILL
            ),
            met_bill=_event(raw.event_flags, EventFlag.MET_BILL),
            met_bill_2=_event(raw.event_flags, EventFlag.MET_BILL_2),
            got_ss_ticket=_event(raw.event_flags, EventFlag.GOT_SS_TICKET),
            ss_ticket_in_bag=ItemId.SS_TICKET in items,
            left_bills_house_after_helping=_event(
                raw.event_flags, EventFlag.LEFT_BILLS_HOUSE_AFTER_HELPING
            ),
            beat_cerulean_gym_trainer_0=_event(
                raw.event_flags, EventFlag.BEAT_CERULEAN_GYM_TRAINER_0
            ),
            beat_misty=_event(raw.event_flags, EventFlag.BEAT_MISTY),
            got_tm11=_event(raw.event_flags, EventFlag.GOT_TM11),
            tm11_in_bag=ItemId.TM11_BUBBLEBEAM in items,
            cascade_badge=bool(badge_bits & Badge.CASCADE),
            cascade_badge_mirror=bool(badge_mirror & Badge.CASCADE),
            current_opponent=self._memory.read_u8(RamAddress.CURRENT_OPPONENT),
            trainer_class=self._memory.read_u8(RamAddress.TRAINER_CLASS),
            trainer_number=self._memory.read_u8(RamAddress.TRAINER_NUMBER),
            engaged_trainer_class=self._memory.read_u8(RamAddress.ENGAGED_TRAINER_CLASS),
            engaged_trainer_set=self._memory.read_u8(RamAddress.ENGAGED_TRAINER_SET),
            gym_leader_number=self._memory.read_u8(RamAddress.GYM_LEADER_NUMBER),
            map_id=raw.map_id,
            player_x=raw.player_x,
            player_y=raw.player_y,
            party_count=raw.party_count,
            party_species_ids=raw.party_species_ids,
            first_party_hp=raw.first_party_hp,
            first_party_max_hp=raw.first_party_max_hp,
            first_party_status=raw.first_party_status,
            battle_state=raw.battle_state,
            battle_result=raw.battle_result,
        )
        phase_snapshots = (
            (CascadePhase.MISTY_DEFEATED, "misty_victory_snapshot"),
            (CascadePhase.MISTY_BATTLE, "misty_battle_snapshot"),
            (
                CascadePhase.CERULEAN_GYM_TRAINER_DEFEATED,
                "cerulean_gym_trainer_victory_snapshot",
            ),
            (
                CascadePhase.CERULEAN_GYM_TRAINER_BATTLE,
                "cerulean_gym_trainer_battle_snapshot",
            ),
            (CascadePhase.BILLS_HOUSE_LEFT, "bills_house_left_snapshot"),
            (CascadePhase.SS_TICKET_OBTAINED, "ss_ticket_snapshot"),
            (CascadePhase.BILL_RESTORED, "bill_restored_snapshot"),
            (
                CascadePhase.BILL_CELL_SEPARATOR_USED,
                "bill_cell_separator_used_snapshot",
            ),
            (
                CascadePhase.BILL_REQUESTED_HELP,
                "bill_requested_help_snapshot",
            ),
            (
                CascadePhase.ROUTE_25_TRAINER_BATTLE,
                "route_25_trainer_battle_snapshot",
            ),
            (
                CascadePhase.NUGGET_ROCKET_DEFEATED,
                "nugget_rocket_victory_snapshot",
            ),
            (
                CascadePhase.NUGGET_ROCKET_BATTLE,
                "nugget_rocket_battle_snapshot",
            ),
            (
                CascadePhase.ROUTE_24_TRAINER_BATTLE,
                "route_24_trainer_battle_snapshot",
            ),
            (CascadePhase.RIVAL_DEFEATED, "rival_victory_snapshot"),
            (CascadePhase.RIVAL_BATTLE, "rival_battle_snapshot"),
            (CascadePhase.CERULEAN_READY, "cerulean_start_snapshot"),
        )
        for phase, snapshot_name in phase_snapshots:
            candidate = replace(state, phase=phase)
            if getattr(candidate, snapshot_name):
                return candidate
        return state

    def read_vermilion_state(self, raw: RawGameState) -> VermilionState:
        """Translate the pinned robbery and Underground Path evidence."""
        controls = self.read_input_readiness()
        local_script = self._local_script(raw.map_id)
        current_map_script = self._memory.read_u8(RamAddress.CURRENT_MAP_SCRIPT)
        items = set(raw.bag_item_ids or ())
        badge_mirror = self._memory.read_u8(RamAddress.BEAT_GYM_FLAGS)
        route_6_events = tuple(
            _event(raw.event_flags, event)
            for event in (
                EventFlag.BEAT_ROUTE_6_TRAINER_0,
                EventFlag.BEAT_ROUTE_6_TRAINER_1,
                EventFlag.BEAT_ROUTE_6_TRAINER_2,
                EventFlag.BEAT_ROUTE_6_TRAINER_3,
                EventFlag.BEAT_ROUTE_6_TRAINER_4,
                EventFlag.BEAT_ROUTE_6_TRAINER_5,
            )
        )
        state = VermilionState(
            phase=VermilionPhase.UNKNOWN,
            controls=controls,
            local_script=local_script,
            current_map_script=current_map_script,
            prior_chapter_complete=_vermilion_prior_chapter_complete(raw, items, badge_mirror),
            beat_rocket_thief=_event(raw.event_flags, EventFlag.BEAT_CERULEAN_ROCKET_THIEF),
            tm28_in_bag=ItemId.TM28_DIG in items,
            route_6_trainer_events=(
                route_6_events[0],
                route_6_events[1],
                route_6_events[2],
                route_6_events[3],
                route_6_events[4],
                route_6_events[5],
            ),
            current_opponent=self._memory.read_u8(RamAddress.CURRENT_OPPONENT),
            trainer_class=self._memory.read_u8(RamAddress.TRAINER_CLASS),
            trainer_number=self._memory.read_u8(RamAddress.TRAINER_NUMBER),
            engaged_trainer_class=self._memory.read_u8(RamAddress.ENGAGED_TRAINER_CLASS),
            engaged_trainer_set=self._memory.read_u8(RamAddress.ENGAGED_TRAINER_SET),
            map_id=raw.map_id,
            player_x=raw.player_x,
            player_y=raw.player_y,
            party_count=raw.party_count,
            party_species_ids=raw.party_species_ids,
            first_party_hp=raw.first_party_hp,
            first_party_max_hp=raw.first_party_max_hp,
            first_party_status=raw.first_party_status,
            battle_state=raw.battle_state,
            battle_result=raw.battle_result,
        )
        phase_snapshots = (
            (VermilionPhase.VERMILION_REACHED, "vermilion_snapshot"),
            (
                VermilionPhase.ROUTE_6_TRAINER_M_DEFEATED,
                "route_6_trainer_m_defeated_snapshot",
            ),
            (
                VermilionPhase.ROUTE_6_TRAINER_M_BATTLE,
                "route_6_trainer_m_battle_snapshot",
            ),
            (
                VermilionPhase.ROUTE_6_TRAINER_F_DEFEATED,
                "route_6_trainer_f_defeated_snapshot",
            ),
            (
                VermilionPhase.ROUTE_6_TRAINER_F_BATTLE,
                "route_6_trainer_f_battle_snapshot",
            ),
            (VermilionPhase.ROUTE_6_REACHED, "route_6_snapshot"),
            (
                VermilionPhase.UNDERGROUND_SOUTH_ENTRANCE,
                "underground_south_entrance_snapshot",
            ),
            (VermilionPhase.UNDERGROUND_TUNNEL, "underground_tunnel_snapshot"),
            (
                VermilionPhase.UNDERGROUND_NORTH_ENTRANCE,
                "underground_north_entrance_snapshot",
            ),
            (VermilionPhase.ROUTE_5_REACHED, "route_5_snapshot"),
            (VermilionPhase.TM28_OBTAINED, "tm28_snapshot"),
            (
                VermilionPhase.ROCKET_THIEF_BATTLE,
                "rocket_thief_battle_snapshot",
            ),
            (VermilionPhase.ROBBERY_REAR_EXIT, "robbery_rear_exit_snapshot"),
            (
                VermilionPhase.TRASHED_HOUSE_ENTERED,
                "trashed_house_snapshot",
            ),
            (VermilionPhase.MISTY_READY, "misty_ready_snapshot"),
        )
        for phase, snapshot_name in phase_snapshots:
            candidate = replace(state, phase=phase)
            if getattr(candidate, snapshot_name):
                return candidate
        return state

    def read_ss_anne_state(self, raw: RawGameState) -> SSAnneState:
        """Translate pinned harbor, rival, Captain, and HM01 evidence."""
        controls = self.read_input_readiness()
        items = set(raw.bag_item_ids or ())
        state = SSAnneState(
            phase=SSAnnePhase.UNKNOWN,
            controls=controls,
            local_script=self._local_script(raw.map_id),
            current_map_script=self._memory.read_u8(RamAddress.CURRENT_MAP_SCRIPT),
            prior_chapter_complete=_ss_anne_prior_chapter_complete(
                raw,
                items,
                self._memory.read_u8(RamAddress.BEAT_GYM_FLAGS),
            ),
            rubbed_captains_back=_event(raw.event_flags, EventFlag.RUBBED_CAPTAINS_BACK),
            got_hm01=_event(raw.event_flags, EventFlag.GOT_HM01),
            hm01_in_bag=ItemId.HM01_CUT in items,
            cut_fact="move:cut_available" in semantic_facts(raw),
            current_opponent=self._memory.read_u8(RamAddress.CURRENT_OPPONENT),
            trainer_class=self._memory.read_u8(RamAddress.TRAINER_CLASS),
            trainer_number=self._memory.read_u8(RamAddress.TRAINER_NUMBER),
            engaged_trainer_class=self._memory.read_u8(RamAddress.ENGAGED_TRAINER_CLASS),
            engaged_trainer_set=self._memory.read_u8(RamAddress.ENGAGED_TRAINER_SET),
            map_id=raw.map_id,
            player_x=raw.player_x,
            player_y=raw.player_y,
            party_count=raw.party_count,
            party_species_ids=raw.party_species_ids,
            first_party_hp=raw.first_party_hp,
            first_party_max_hp=raw.first_party_max_hp,
            first_party_status=raw.first_party_status,
            first_party_pp=raw.first_party_pp,
            battle_state=raw.battle_state,
            battle_result=raw.battle_result,
        )
        phase_snapshots = (
            (SSAnnePhase.HM01_OBTAINED, "hm01_snapshot"),
            (SSAnnePhase.CAPTAIN_ROOM_REACHED, "captain_room_snapshot"),
            (SSAnnePhase.RIVAL_DEFEATED, "rival_defeated_snapshot"),
            (SSAnnePhase.RIVAL_BATTLE, "rival_battle_snapshot"),
            (SSAnnePhase.SHIP_2F_REACHED, "ship_2f_snapshot"),
            (SSAnnePhase.SHIP_1F_REACHED, "ship_1f_snapshot"),
            (SSAnnePhase.DOCK_REACHED, "dock_snapshot"),
            (SSAnnePhase.HEALED, "healed_snapshot"),
            (SSAnnePhase.VERMILION_READY, "vermilion_ready_snapshot"),
        )
        for phase, snapshot_name in phase_snapshots:
            candidate = replace(state, phase=phase)
            if getattr(candidate, snapshot_name):
                return candidate
        return state

    def _local_script(self, map_id: int | None) -> int:
        address = {
            MapId.OAKS_LAB: RamAddress.OAKS_LAB_SCRIPT,
            MapId.PALLET_TOWN: RamAddress.PALLET_TOWN_SCRIPT,
            MapId.VIRIDIAN_CITY: RamAddress.VIRIDIAN_CITY_SCRIPT,
            MapId.VIRIDIAN_FOREST: RamAddress.VIRIDIAN_FOREST_SCRIPT,
            MapId.PEWTER_CITY: RamAddress.PEWTER_CITY_SCRIPT,
            MapId.PEWTER_GYM: RamAddress.PEWTER_GYM_SCRIPT,
            MapId.ROUTE_3: RamAddress.ROUTE_3_SCRIPT,
            MapId.ROUTE_4: RamAddress.ROUTE_4_SCRIPT,
            MapId.MT_MOON_1F: RamAddress.MT_MOON_1F_SCRIPT,
            MapId.MT_MOON_B2F: RamAddress.MT_MOON_B2F_SCRIPT,
            MapId.CERULEAN_CITY: RamAddress.CERULEAN_CITY_SCRIPT,
            MapId.CERULEAN_GYM: RamAddress.CERULEAN_GYM_SCRIPT,
            MapId.ROUTE_6: RamAddress.ROUTE_6_SCRIPT,
            MapId.ROUTE_24: RamAddress.ROUTE_24_SCRIPT,
            MapId.ROUTE_25: RamAddress.ROUTE_25_SCRIPT,
            MapId.BILLS_HOUSE: RamAddress.BILLS_HOUSE_SCRIPT,
            MapId.VERMILION_CITY: RamAddress.VERMILION_CITY_SCRIPT,
            MapId.SS_ANNE_2F: RamAddress.SS_ANNE_2F_SCRIPT,
        }.get(map_id)
        return self._memory.read_u8(address) if address is not None else 0

    def _read_u16_be(self, address: int) -> int:
        return (self._memory.read_u8(address) << 8) | self._memory.read_u8(address + 1)


def _travel_boundary(raw: RawGameState) -> TravelBoundary:
    position = (raw.map_id, raw.player_x, raw.player_y)
    if position == (MapId.PALLET_TOWN, 12, 12):
        return TravelBoundary.PALLET_LAB_EXTERIOR
    if position == (MapId.VIRIDIAN_CITY, 21, 35):
        return TravelBoundary.VIRIDIAN_SOUTH_EDGE
    if raw.map_id == MapId.ROUTE_2 and raw.player_x in {7, 8, 9} and raw.player_y == 71:
        return TravelBoundary.ROUTE_2_SOUTH_EDGE
    if position == (MapId.VIRIDIAN_FOREST_SOUTH_GATE, 4, 7):
        return TravelBoundary.FOREST_SOUTH_GATE
    if raw.map_id == MapId.VIRIDIAN_FOREST and raw.player_x in {16, 17} and raw.player_y == 47:
        return TravelBoundary.FOREST_SOUTH_ENTRY
    if raw.map_id == MapId.VIRIDIAN_FOREST_NORTH_GATE:
        return TravelBoundary.FOREST_NORTH_GATE
    if position == (MapId.ROUTE_2, 3, 11):
        return TravelBoundary.ROUTE_2_NORTH_RETURN
    if raw.map_id == MapId.PEWTER_CITY and raw.player_x in {18, 19} and raw.player_y == 35:
        return TravelBoundary.PEWTER_SOUTH_EDGE
    if position == (MapId.PEWTER_GYM, 4, 13):
        return TravelBoundary.PEWTER_GYM_ENTRANCE
    return TravelBoundary.UNKNOWN


def _cerulean_boundary(raw: RawGameState) -> CeruleanBoundary:
    return _cerulean_boundary_position(raw.map_id, raw.player_x, raw.player_y)


def _cerulean_boundary_position(
    map_id: int | None, player_x: int | None, player_y: int | None
) -> CeruleanBoundary:
    position = (map_id, player_x, player_y)
    return {
        (MapId.ROUTE_3, 0, 9): CeruleanBoundary.ROUTE_3_WEST_ENTRY,
        (MapId.ROUTE_3, 0, 10): CeruleanBoundary.ROUTE_3_WEST_ENTRY,
        (MapId.ROUTE_4, 9, 17): CeruleanBoundary.ROUTE_4_WEST_ENTRY,
        (MapId.MT_MOON_1F, 14, 35): CeruleanBoundary.MT_MOON_1F_ENTRY,
        (MapId.MT_MOON_B1F, 5, 5): CeruleanBoundary.MT_MOON_B1F_DESCENT,
        (MapId.MT_MOON_B2F, 21, 17): CeruleanBoundary.MT_MOON_B2F_ENTRY,
        (MapId.MT_MOON_B1F, 23, 3): CeruleanBoundary.MT_MOON_B1F_ASCENT,
        (MapId.ROUTE_4, 24, 6): CeruleanBoundary.ROUTE_4_MT_MOON_EXIT,
        (MapId.CERULEAN_CITY, 0, 18): CeruleanBoundary.CERULEAN_WEST_ENTRY,
    }.get(position, CeruleanBoundary.UNKNOWN)


def _required_route_3_trainer_position(
    current_opponent: int,
    trainer_class: int,
    trainer_number: int,
    engaged_trainer_class: int,
    engaged_trainer_set: int,
) -> int | None:
    for position, spec in enumerate(ROUTE_3_REQUIRED_TRAINER_SPECS):
        _, opponent, expected_class, expected_number = spec
        if (
            current_opponent == opponent
            and trainer_class == expected_class
            and trainer_number == expected_number
            and engaged_trainer_class == opponent
            and engaged_trainer_set == expected_number
        ):
            return position
    return None


def _cascade_prior_chapter_complete(raw: RawGameState, items: set[int], badge_mirror: int) -> bool:
    got_dome_fossil = _event(raw.event_flags, EventFlag.GOT_DOME_FOSSIL)
    got_helix_fossil = _event(raw.event_flags, EventFlag.GOT_HELIX_FOSSIL)
    corresponding_fossil = (
        got_dome_fossil
        and ItemId.DOME_FOSSIL in items
        and not got_helix_fossil
        and ItemId.HELIX_FOSSIL not in items
    ) or (
        got_helix_fossil
        and ItemId.HELIX_FOSSIL in items
        and not got_dome_fossil
        and ItemId.DOME_FOSSIL not in items
    )
    return (
        _event(raw.event_flags, EventFlag.BEAT_BROCK)
        and _event(raw.event_flags, EventFlag.GOT_TM34)
        and bool((raw.badge_bits or 0) & Badge.BOULDER)
        and bool(badge_mirror & Badge.BOULDER)
        and all(
            _event(raw.event_flags, event)
            for event in (
                EventFlag.BEAT_ROUTE_3_TRAINER_0,
                EventFlag.BEAT_ROUTE_3_TRAINER_1,
                EventFlag.BEAT_ROUTE_3_TRAINER_3,
                EventFlag.BEAT_ROUTE_3_TRAINER_6,
                MT_MOON_REQUIRED_ROCKET_EVENT,
                EventFlag.BEAT_MT_MOON_EXIT_SUPER_NERD,
            )
        )
        and corresponding_fossil
    )


def _vermilion_prior_chapter_complete(
    raw: RawGameState, items: set[int], badge_mirror: int
) -> bool:
    return (
        _cascade_prior_chapter_complete(raw, items, badge_mirror)
        and all(
            _event(raw.event_flags, event)
            for event in (
                EventFlag.BEAT_CERULEAN_RIVAL,
                EventFlag.GOT_NUGGET,
                EventFlag.BEAT_ROUTE_24_ROCKET,
                EventFlag.BILL_SAID_USE_CELL_SEPARATOR,
                EventFlag.USED_CELL_SEPARATOR_ON_BILL,
                EventFlag.MET_BILL,
                EventFlag.MET_BILL_2,
                EventFlag.GOT_SS_TICKET,
                EventFlag.LEFT_BILLS_HOUSE_AFTER_HELPING,
                EventFlag.BEAT_CERULEAN_GYM_TRAINER_0,
                EventFlag.GOT_TM11,
                EventFlag.BEAT_MISTY,
            )
        )
        and ItemId.SS_TICKET in items
        and ItemId.TM11_BUBBLEBEAM in items
        and bool((raw.badge_bits or 0) & Badge.CASCADE)
        and bool(badge_mirror & Badge.CASCADE)
    )


def _ss_anne_prior_chapter_complete(raw: RawGameState, items: set[int], badge_mirror: int) -> bool:
    return (
        _vermilion_prior_chapter_complete(raw, items, badge_mirror)
        and _event(raw.event_flags, EventFlag.BEAT_CERULEAN_ROCKET_THIEF)
        and ItemId.TM28_DIG in items
        and tuple(
            _event(raw.event_flags, event)
            for event in (
                EventFlag.BEAT_ROUTE_6_TRAINER_0,
                EventFlag.BEAT_ROUTE_6_TRAINER_1,
                EventFlag.BEAT_ROUTE_6_TRAINER_2,
                EventFlag.BEAT_ROUTE_6_TRAINER_3,
                EventFlag.BEAT_ROUTE_6_TRAINER_4,
                EventFlag.BEAT_ROUTE_6_TRAINER_5,
            )
        )
        == (False, False, False, True, True, False)
    )


def event_flag_is_set(event_flags: bytes | None, bit_index: int) -> bool:
    if bit_index < 0:
        raise ValueError("event bit index cannot be negative")
    if event_flags is None:
        return False
    byte_index, bit = divmod(bit_index, 8)
    return byte_index < len(event_flags) and bool(event_flags[byte_index] & (1 << bit))


class SemanticStateError(ValueError):
    """Raised when a run cannot establish a trustworthy semantic-state origin."""


class SemanticStateTracker:
    """Latch only verified semantic milestones observed within one clean run."""

    def __init__(self, initial_raw_state: RawGameState) -> None:
        if initial_raw_state.game_started:
            raise SemanticStateError(
                "A clean run must begin before the game timer starts; refusing adjacent state."
            )
        self._latched_facts: set[str] = {"system:clean_power_on"}

    @property
    def latched_facts(self) -> frozenset[str]:
        return frozenset(self._latched_facts)

    def observe(self, raw: RawGameState) -> GameState:
        observed = semantic_facts(raw)
        self._latched_facts.update(observed)
        return GameState(
            mode=game_mode(raw),
            facts=frozenset(self._latched_facts),
            location=location_label(raw.map_id),
        )


def game_mode(raw: RawGameState) -> GameMode:
    if not raw.game_started:
        return GameMode.BOOTING
    if raw.map_id == MapId.HALL_OF_FAME:
        return GameMode.HALL_OF_FAME
    if raw.battle_state in {1, 2}:
        return GameMode.BATTLE
    return GameMode.OVERWORLD


def location_label(map_id: int | None) -> str | None:
    if map_id is None:
        return None
    return {
        MapId.PALLET_TOWN: "pallet_town",
        MapId.VIRIDIAN_CITY: "viridian_city",
        MapId.PEWTER_CITY: "pewter_city",
        MapId.CERULEAN_CITY: "cerulean_city",
        MapId.LAVENDER_TOWN: "lavender_town",
        MapId.VERMILION_CITY: "vermilion_city",
        MapId.CELADON_CITY: "celadon_city",
        MapId.FUCHSIA_CITY: "fuchsia_city",
        MapId.CINNABAR_ISLAND: "cinnabar_island",
        MapId.INDIGO_PLATEAU: "indigo_plateau",
        MapId.SAFFRON_CITY: "saffron_city",
        MapId.ROUTE_1: "route_1",
        MapId.ROUTE_2: "route_2",
        MapId.ROUTE_3: "route_3",
        MapId.ROUTE_4: "route_4",
        MapId.ROUTE_5: "route_5",
        MapId.ROUTE_6: "route_6",
        MapId.ROUTE_7: "route_7",
        MapId.ROUTE_8: "route_8",
        MapId.ROUTE_9: "route_9",
        MapId.ROUTE_10: "route_10",
        MapId.ROUTE_24: "route_24",
        MapId.ROUTE_25: "route_25",
        MapId.REDS_HOUSE_1F: "reds_house_1f",
        MapId.REDS_HOUSE_2F: "reds_house_2f",
        MapId.OAKS_LAB: "oaks_lab",
        MapId.VIRIDIAN_POKECENTER: "viridian_pokecenter",
        MapId.VIRIDIAN_MART: "viridian_mart",
        MapId.VIRIDIAN_FOREST_NORTH_GATE: "viridian_forest_north_gate",
        MapId.ROUTE_2_GATE: "route_2_gate",
        MapId.VIRIDIAN_FOREST_SOUTH_GATE: "viridian_forest_south_gate",
        MapId.VIRIDIAN_FOREST: "viridian_forest",
        MapId.PEWTER_GYM: "pewter_gym",
        MapId.PEWTER_POKECENTER: "pewter_pokecenter",
        MapId.MT_MOON_1F: "mt_moon_1f",
        MapId.MT_MOON_B1F: "mt_moon_b1f",
        MapId.MT_MOON_B2F: "mt_moon_b2f",
        MapId.CERULEAN_TRASHED_HOUSE: "cerulean_trashed_house",
        MapId.CERULEAN_POKECENTER: "cerulean_pokecenter",
        MapId.CERULEAN_GYM: "cerulean_gym",
        MapId.MT_MOON_POKECENTER: "mt_moon_pokecenter",
        MapId.UNDERGROUND_PATH_ROUTE_5: "underground_path_route_5",
        MapId.UNDERGROUND_PATH_ROUTE_6: "underground_path_route_6",
        MapId.UNDERGROUND_PATH_ROUTE_7: "underground_path_route_7",
        MapId.UNDERGROUND_PATH_ROUTE_8: "underground_path_route_8",
        MapId.BILLS_HOUSE: "bills_house",
        MapId.UNDERGROUND_PATH_NORTH_SOUTH: "underground_path_north_south",
        MapId.UNDERGROUND_PATH_WEST_EAST: "underground_path_west_east",
        MapId.ROCK_TUNNEL_POKECENTER: "rock_tunnel_pokecenter",
        MapId.ROCK_TUNNEL_1F: "rock_tunnel_1f",
        MapId.ROCK_TUNNEL_B1F: "rock_tunnel_b1f",
        MapId.LAVENDER_POKECENTER: "lavender_pokecenter",
        MapId.CELADON_POKECENTER: "celadon_pokecenter",
        MapId.GAME_CORNER: "game_corner",
        MapId.ROCKET_HIDEOUT_B1F: "rocket_hideout_b1f",
        MapId.ROCKET_HIDEOUT_B2F: "rocket_hideout_b2f",
        MapId.ROCKET_HIDEOUT_B3F: "rocket_hideout_b3f",
        MapId.ROCKET_HIDEOUT_B4F: "rocket_hideout_b4f",
        MapId.ROCKET_HIDEOUT_ELEVATOR: "rocket_hideout_elevator",
        MapId.HALL_OF_FAME: "hall_of_fame",
        MapId.CHAMPIONS_ROOM: "champions_room",
        MapId.INDIGO_PLATEAU_LOBBY: "indigo_plateau_lobby",
    }.get(map_id, f"map_{map_id:02x}")


def semantic_facts(raw: RawGameState) -> frozenset[str]:
    if not raw.game_started:
        return frozenset()

    facts: set[str] = {"story:adventure_begun"}
    events = raw.event_flags
    items = set(raw.bag_item_ids or ())
    badges = Badge(raw.badge_bits or 0)

    if (raw.party_count or 0) > 0 or _event(events, EventFlag.GOT_STARTER):
        facts.add("party:starter_obtained")
    if _event(events, EventFlag.FOLLOWED_OAK_INTO_LAB):
        facts.add("story:oak_lab_reached")
    if _event(events, EventFlag.OAK_ASKED_TO_CHOOSE_MON):
        facts.add("story:starter_selection_ready")
    if _event(events, EventFlag.GOT_POKEDEX):
        facts.add("story:pokedex_received")

    map_facts = {
        MapId.PEWTER_CITY: "location:pewter_city",
        MapId.CERULEAN_CITY: "location:cerulean_city",
        MapId.LAVENDER_TOWN: "location:lavender_town",
        MapId.LAVENDER_POKECENTER: "location:lavender_town",
        MapId.VERMILION_CITY: "location:vermilion_city",
        MapId.CELADON_CITY: "location:celadon_city",
        MapId.CELADON_POKECENTER: "location:celadon_city",
        MapId.FUCHSIA_CITY: "location:fuchsia_city",
        MapId.CINNABAR_ISLAND: "location:cinnabar_island",
        MapId.SAFFRON_CITY: "location:saffron_city",
    }
    if raw.map_id in map_facts:
        facts.add(map_facts[MapId(raw.map_id)])
    if raw.map_id in {MapId.INDIGO_PLATEAU, MapId.INDIGO_PLATEAU_LOBBY}:
        facts.add("story:victory_road_cleared")

    for badge, fact in {
        Badge.BOULDER: "badge:boulder",
        Badge.CASCADE: "badge:cascade",
        Badge.THUNDER: "badge:thunder",
        Badge.RAINBOW: "badge:rainbow",
        Badge.SOUL: "badge:soul",
        Badge.MARSH: "badge:marsh",
        Badge.VOLCANO: "badge:volcano",
        Badge.EARTH: "badge:earth",
    }.items():
        if badges & badge:
            facts.add(fact)

    _add_if_event(facts, events, EventFlag.GOT_SS_TICKET, "item:ss_ticket")
    _add_if_event(
        facts,
        events,
        EventFlag.BEAT_ROCKET_HIDEOUT_GIOVANNI,
        "story:rocket_hideout_cleared",
    )
    _add_if_event(facts, events, EventFlag.BEAT_SILPH_CO_GIOVANNI, "story:silph_co_liberated")
    _add_if_event(facts, events, EventFlag.BEAT_LORELEI, "league:lorelei_defeated")
    _add_if_event(facts, events, EventFlag.BEAT_BRUNO, "league:bruno_defeated")
    _add_if_event(facts, events, EventFlag.BEAT_AGATHA, "league:agatha_defeated")
    _add_if_event(facts, events, EventFlag.BEAT_LANCE, "league:lance_defeated")
    _add_if_event(facts, events, EventFlag.BEAT_CHAMPION_RIVAL, CHAMPION_DEFEATED_FACT)

    if ItemId.SS_TICKET in items:
        facts.add("item:ss_ticket")
    if ItemId.SILPH_SCOPE in items:
        facts.add("item:silph_scope")
    if ItemId.POKE_FLUTE in items or _event(events, EventFlag.GOT_POKE_FLUTE):
        facts.add("item:poke_flute")
    if ItemId.SECRET_KEY in items:
        facts.add("item:secret_key")
    if ItemId.HM01_CUT in items or _event(events, EventFlag.GOT_HM01):
        facts.add("move:cut_available")
    if ItemId.HM03_SURF in items or _event(events, EventFlag.GOT_HM03):
        facts.add("move:surf_available")
    if ItemId.HM04_STRENGTH in items or _event(events, EventFlag.GOT_HM04):
        facts.add("move:strength_available")

    if raw.map_id == MapId.HALL_OF_FAME and _event(events, EventFlag.BEAT_CHAMPION_RIVAL):
        facts.add(HALL_OF_FAME_FACT)
    return frozenset(facts)


def _event(events: bytes | None, event: EventFlag) -> bool:
    return event_flag_is_set(events, int(event))


def _add_if_event(
    facts: set[str],
    events: bytes | None,
    event: EventFlag,
    fact: str,
) -> None:
    if _event(events, event):
        facts.add(fact)
