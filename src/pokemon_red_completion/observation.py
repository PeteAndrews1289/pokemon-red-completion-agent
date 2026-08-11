from __future__ import annotations

import json
from dataclasses import dataclass, replace
from enum import IntEnum, IntFlag, StrEnum
from typing import Protocol, runtime_checkable

from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.encounters import encounter_log_path, is_wild_encounter
from pokemon_red_completion.referee import CHAMPION_DEFEATED_FACT
from pokemon_red_completion.route import HALL_OF_FAME_FACT


class ReadOnlyMemory(Protocol):
    """The deliberately non-mutating memory surface available to the adapter."""

    def read_u8(self, address: int) -> int: ...


@runtime_checkable
class ReadOnlyCartridgeRam(Protocol):
    """Narrow read-only access to banked cartridge RAM."""

    def read_cartridge_ram_u8(self, bank: int, address: int) -> int: ...


class RamAddress(IntEnum):
    """Verified symbols for the supported US revision-zero ROM.

    Symbols originate from pret/pokered commit
    ``1e96034092686d006e863cace09e87273051a3d8`` and are valid only after the
    repository's exact ROM fingerprint gate passes.
    """

    SPRITE_STATE_DATA_1 = 0xC100
    SPRITE_STATE_DATA_2 = 0xC200
    TILE_MAP = 0xC3A0
    OVERWORLD_MAP = 0xC6E8
    PLAYER_FACING_DIRECTION = 0xC109
    TOP_MENU_ITEM_Y = 0xCC24
    TOP_MENU_ITEM_X = 0xCC25
    CURRENT_MENU_ITEM = 0xCC26
    MAX_MENU_ITEM = 0xCC28
    LIST_SCROLL_OFFSET = 0xCC36
    MENU_WATCHED_KEYS = 0xCC29
    PLAYER_MON_NUMBER = 0xCC2F
    MENU_CURSOR_LOCATION = 0xCC30
    NPC_MOVEMENT_SCRIPT_TABLE = 0xCC57
    PLAYER_ATTACK_STAGE = 0xCD1A
    PLAYER_SPECIAL_STAGE = 0xCD1D
    PLAYER_ACCURACY_STAGE = 0xCD1E
    ENEMY_DEFENSE_STAGE = 0xCD2F
    ENGAGED_TRAINER_CLASS = 0xCD2D
    ENGAGED_TRAINER_SET = 0xCD2E
    SIMULATED_JOYPAD_INDEX = 0xCD38
    MISC_FLAGS = 0xCD60
    JOY_IGNORE = 0xCD6B
    BATTLE_RESULT = 0xCF0B
    SHOP_SELECTED_ITEM = 0xCF91
    SHOP_QUANTITY = 0xCF96
    WALK_COUNTER = 0xCFC5
    TILE_IN_FRONT_OF_PLAYER = 0xCFC6
    ENEMY_SPECIES = 0xCFE5
    ENEMY_HP = 0xCFE6
    ENEMY_MON_PARTY_POS = 0xCFE8
    ENEMY_LEVEL = 0xCFF3
    ENEMY_MAX_HP = 0xCFF4
    TRAINER_CLASS = 0xD031
    IS_IN_BATTLE = 0xD057
    CURRENT_OPPONENT = 0xD059
    ENEMY_BATTLE_STATUS_1 = 0xD067
    PLAYER_DISABLED_MOVE = 0xD06D
    GYM_LEADER_NUMBER = 0xD05C
    TRAINER_NUMBER = 0xD05D
    REPEL_REMAINING_STEPS = 0xD0DB
    PLAYER_MONEY = 0xD347
    PARTY_COUNT = 0xD163
    PARTY_SPECIES = 0xD164
    PARTY_MON_1 = 0xD16B
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
    POKEDEX_OWNED = 0xD2F7
    POKEDEX_SEEN = 0xD30A
    NUM_BAG_ITEMS = 0xD31D
    BAG_ITEMS = 0xD31E
    OBTAINED_BADGES = 0xD356
    CURRENT_MAP = 0xD35E
    CURRENT_TILE_BLOCK_MAP_VIEW_POINTER = 0xD35F
    PLAYER_Y = 0xD361
    PLAYER_X = 0xD362
    Y_BLOCK_COORD = 0xD363
    X_BLOCK_COORD = 0xD364
    CURRENT_MAP_TILESET = 0xD367
    CURRENT_MAP_HEIGHT = 0xD368
    CURRENT_MAP_WIDTH = 0xD369
    NUM_SPRITES = 0xD4E1
    MAP_SPRITE_DATA = 0xD4E4
    CURRENT_BOX_NUMBER = 0xD5A0
    PLAYER_MOVING_DIRECTION = 0xD528
    TOGGLEABLE_OBJECT_FLAGS = 0xD5A6
    TOGGLEABLE_OBJECT_LIST = 0xD5CE
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
    STATUS_FLAGS_1 = 0xD728
    BEAT_GYM_FLAGS = 0xD72A
    STATUS_FLAGS_5 = 0xD730
    STATUS_FLAGS_6 = 0xD732
    MOVEMENT_FLAGS = 0xD736
    WALK_BIKE_SURF_STATE = 0xD700
    NPC_TRADE_FLAGS = 0xD737
    VERMILION_GYM_FIRST_LOCK = 0xD743
    VERMILION_GYM_SECOND_LOCK = 0xD744
    EVENT_FLAGS = 0xD747
    SAFARI_STEPS = 0xD70D
    CURRENT_MAP_SCRIPT = 0xDA39
    SAFARI_BALLS = 0xDA47
    CURRENT_BOX_COUNT = 0xDA80
    CURRENT_BOX_SPECIES = 0xDA81
    CURRENT_BOX_MONS = 0xDA96


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
    ROUTE_12 = 0x17
    ROUTE_13 = 0x18
    ROUTE_14 = 0x19
    ROUTE_15 = 0x1A
    ROUTE_16 = 0x1B
    ROUTE_21 = 0x20
    ROUTE_22 = 0x21
    ROUTE_23 = 0x22
    ROUTE_24 = 0x23
    ROUTE_25 = 0x24
    REDS_HOUSE_1F = 0x25
    REDS_HOUSE_2F = 0x26
    OAKS_LAB = 0x28
    VIRIDIAN_POKECENTER = 0x29
    VIRIDIAN_MART = 0x2A
    VIRIDIAN_GYM = 0x2D
    DIGLETTS_CAVE_ROUTE_2 = 0x2E
    VICTORY_ROAD_1F = 0x6C
    LANCES_ROOM = 0x71
    VIRIDIAN_FOREST_NORTH_GATE = 0x2F
    ROUTE_2_GATE = 0x31
    VIRIDIAN_FOREST_SOUTH_GATE = 0x32
    VIRIDIAN_FOREST = 0x33
    PEWTER_GYM = 0x36
    PEWTER_MART = 0x38
    PEWTER_POKECENTER = 0x3A
    MT_MOON_1F = 0x3B
    MT_MOON_B1F = 0x3C
    MT_MOON_B2F = 0x3D
    CERULEAN_TRASHED_HOUSE = 0x3E
    CERULEAN_POKECENTER = 0x40
    CERULEAN_GYM = 0x41
    CERULEAN_MART = 0x43
    MT_MOON_POKECENTER = 0x44
    UNDERGROUND_PATH_ROUTE_5 = 0x47
    UNDERGROUND_PATH_ROUTE_6 = 0x4A
    UNDERGROUND_PATH_ROUTE_7 = 0x4D
    UNDERGROUND_PATH_ROUTE_8 = 0x50
    DIGLETTS_CAVE_ROUTE_11 = 0x55
    ROUTE_12_GATE_1F = 0x57
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
    FUCHSIA_POKECENTER = 0x9A
    WARDENS_HOUSE = 0x9B
    FUCHSIA_GYM = 0x9D
    SAFARI_ZONE_GATE = 0x9C
    POKEMON_TOWER_1F = 0x8E
    POKEMON_TOWER_2F = 0x8F
    POKEMON_TOWER_3F = 0x90
    POKEMON_TOWER_4F = 0x91
    POKEMON_TOWER_5F = 0x92
    POKEMON_TOWER_6F = 0x93
    POKEMON_TOWER_7F = 0x94
    MR_FUJIS_HOUSE = 0x95
    LAVENDER_MART = 0x96
    CELADON_POKECENTER = 0x85
    CELADON_GYM = 0x86
    GAME_CORNER = 0x87
    CELADON_MART_1F = 0x7A
    CELADON_MART_2F = 0x7B
    CELADON_MART_3F = 0x7C
    CELADON_MART_4F = 0x7D
    CELADON_MART_ROOF = 0x7E
    CELADON_MANSION_1F = 0x80
    CELADON_MANSION_2F = 0x81
    CELADON_MANSION_3F = 0x82
    CELADON_MANSION_ROOF = 0x83
    CELADON_MANSION_ROOF_HOUSE = 0x84
    CELADON_MART_5F = 0x88
    ROUTE_7_GATE = 0x4C
    FIGHTING_DOJO = 0xB1
    SAFFRON_GYM = 0xB2
    SAFFRON_MART = 0xB4
    SILPH_CO_1F = 0xB5
    SAFFRON_POKECENTER = 0xB6
    ROUTE_15_GATE_1F = 0xB8
    ROUTE_16_GATE_1F = 0xBA
    ROUTE_16_FLY_HOUSE = 0xBC
    POKEMON_MANSION_1F = 0xA5
    CINNABAR_GYM = 0xA6
    CINNABAR_POKECENTER = 0xAB
    CINNABAR_MART = 0xAC
    ROCKET_HIDEOUT_B1F = 0xC7
    ROCKET_HIDEOUT_B2F = 0xC8
    ROCKET_HIDEOUT_B3F = 0xC9
    ROCKET_HIDEOUT_B4F = 0xCA
    ROCKET_HIDEOUT_ELEVATOR = 0xCB
    SILPH_CO_2F = 0xCF
    SILPH_CO_3F = 0xD0
    SILPH_CO_5F = 0xD2
    SILPH_CO_7F = 0xD4
    SILPH_CO_9F = 0xE9
    SILPH_CO_11F = 0xEB
    SILPH_CO_ELEVATOR = 0xEC
    POKEMON_MANSION_2F = 0xD6
    POKEMON_MANSION_3F = 0xD7
    POKEMON_MANSION_B1F = 0xD8
    SAFARI_ZONE_EAST = 0xD9
    SAFARI_ZONE_NORTH = 0xDA
    SAFARI_ZONE_WEST = 0xDB
    SAFARI_ZONE_CENTER = 0xDC
    SAFARI_ZONE_SECRET_HOUSE = 0xDE
    ROCK_TUNNEL_B1F = 0xE8
    HALL_OF_FAME = 0x76
    CHAMPIONS_ROOM = 0x78
    INDIGO_PLATEAU_LOBBY = 0xAE
    ROUTE_22_GATE = 0xC1
    VICTORY_ROAD_2F = 0xC2
    VICTORY_ROAD_3F = 0xC6
    LORELEIS_ROOM = 0xF5
    BRUNOS_ROOM = 0xF6
    AGATHAS_ROOM = 0xF7
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
    GOT_TM27 = 0x050
    BEAT_VIRIDIAN_GYM_GIOVANNI = 0x051
    BEAT_VIRIDIAN_GYM_TRAINER_0 = 0x052
    BEAT_VIRIDIAN_GYM_TRAINER_1 = 0x053
    BEAT_VIRIDIAN_GYM_TRAINER_2 = 0x054
    BEAT_VIRIDIAN_GYM_TRAINER_3 = 0x055
    BEAT_VIRIDIAN_GYM_TRAINER_4 = 0x056
    BEAT_VIRIDIAN_GYM_TRAINER_5 = 0x057
    BEAT_VIRIDIAN_GYM_TRAINER_6 = 0x058
    BEAT_VIRIDIAN_GYM_TRAINER_7 = 0x059
    GOT_TM34 = 0x076
    BEAT_BROCK = 0x077
    BEAT_CERULEAN_RIVAL = 0x098
    BEAT_CERULEAN_ROCKET_THIEF = 0x0A7
    BEAT_CERULEAN_GYM_TRAINER_0 = 0x0BA
    BEAT_CERULEAN_GYM_TRAINER_1 = 0x0BB
    GOT_TM11 = 0x0BE
    BEAT_MISTY = 0x0BF
    GOT_TM13 = 0x18C
    GOT_HM02 = 0x4CE
    BEAT_ROUTE_21_TRAINER_0 = 0x511
    BEAT_ROUTE_21_TRAINER_1 = 0x512
    BEAT_ROUTE_21_TRAINER_2 = 0x513
    BEAT_ROUTE_21_TRAINER_3 = 0x514
    BEAT_ROUTE_21_TRAINER_4 = 0x515
    BEAT_ROUTE_21_TRAINER_5 = 0x516
    BEAT_ROUTE_21_TRAINER_6 = 0x517
    BEAT_ROUTE_21_TRAINER_7 = 0x518
    BEAT_ROUTE_21_TRAINER_8 = 0x519
    SECOND_ROUTE_22_RIVAL_BATTLE = 0x521
    BEAT_ROUTE_22_RIVAL_2ND_BATTLE = 0x526
    ROUTE_22_RIVAL_WANTS_BATTLE = 0x527
    PASSED_CASCADE_BADGE_CHECK = 0x530
    PASSED_THUNDER_BADGE_CHECK = 0x531
    PASSED_RAINBOW_BADGE_CHECK = 0x532
    PASSED_SOUL_BADGE_CHECK = 0x533
    PASSED_MARSH_BADGE_CHECK = 0x534
    PASSED_VOLCANO_BADGE_CHECK = 0x535
    PASSED_EARTH_BADGE_CHECK = 0x536
    VICTORY_ROAD_2F_BOULDER_ON_SWITCH_1 = 0x538
    VICTORY_ROAD_2F_BOULDER_ON_SWITCH_2 = 0x53F
    VICTORY_ROAD_3F_BOULDER_ON_SWITCH_1 = 0x660
    VICTORY_ROAD_3F_BOULDER_IN_HOLE = 0x666
    VICTORY_ROAD_1F_BOULDER_ON_SWITCH = 0x917
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
    BEAT_ROUTE_11_TRAINER_0 = 0x471
    BEAT_ROUTE_11_TRAINER_1 = 0x472
    BEAT_ROUTE_11_TRAINER_5 = 0x476
    BEAT_ROUTE_11_TRAINER_6 = 0x477
    BEAT_ROCK_TUNNEL_1_TRAINER_3 = 0x45C
    BEAT_ROCK_TUNNEL_1_TRAINER_4 = 0x45D
    BEAT_ROCK_TUNNEL_1_TRAINER_5 = 0x45E
    RESCUED_MR_FUJI = 0x117
    GOT_POKE_FLUTE = 0x128
    GOT_TM39 = 0x480
    BEAT_ROUTE_12_TRAINER_0 = 0x482
    BEAT_ROUTE_12_TRAINER_1 = 0x483
    BEAT_ROUTE_12_TRAINER_2 = 0x484
    BEAT_ROUTE_12_TRAINER_3 = 0x485
    BEAT_ROUTE_12_TRAINER_4 = 0x486
    BEAT_ROUTE_12_TRAINER_5 = 0x487
    BEAT_ROUTE_12_TRAINER_6 = 0x488
    FIGHT_ROUTE12_SNORLAX = 0x48E
    BEAT_ROUTE12_SNORLAX = 0x48F
    BEAT_ROUTE_13_TRAINER_0 = 0x491
    BEAT_ROUTE_13_TRAINER_1 = 0x492
    BEAT_ROUTE_13_TRAINER_2 = 0x493
    BEAT_ROUTE_13_TRAINER_3 = 0x494
    BEAT_ROUTE_13_TRAINER_4 = 0x495
    BEAT_ROUTE_13_TRAINER_5 = 0x496
    BEAT_ROUTE_13_TRAINER_6 = 0x497
    BEAT_ROUTE_13_TRAINER_7 = 0x498
    BEAT_ROUTE_13_TRAINER_8 = 0x499
    BEAT_ROUTE_13_TRAINER_9 = 0x49A
    BEAT_ROUTE_14_TRAINER_0 = 0x4A1
    BEAT_ROUTE_14_TRAINER_1 = 0x4A2
    BEAT_ROUTE_14_TRAINER_2 = 0x4A3
    BEAT_ROUTE_14_TRAINER_3 = 0x4A4
    BEAT_ROUTE_14_TRAINER_4 = 0x4A5
    BEAT_ROUTE_14_TRAINER_5 = 0x4A6
    BEAT_ROUTE_14_TRAINER_6 = 0x4A7
    BEAT_ROUTE_14_TRAINER_7 = 0x4A8
    BEAT_ROUTE_14_TRAINER_8 = 0x4A9
    BEAT_ROUTE_14_TRAINER_9 = 0x4AA
    GOT_EXP_ALL = 0x4B0
    BEAT_ROUTE_15_TRAINER_0 = 0x4B1
    BEAT_ROUTE_15_TRAINER_1 = 0x4B2
    BEAT_ROUTE_15_TRAINER_2 = 0x4B3
    BEAT_ROUTE_15_TRAINER_3 = 0x4B4
    BEAT_ROUTE_15_TRAINER_4 = 0x4B5
    BEAT_ROUTE_15_TRAINER_5 = 0x4B6
    BEAT_ROUTE_15_TRAINER_6 = 0x4B7
    BEAT_ROUTE_15_TRAINER_7 = 0x4B8
    BEAT_ROUTE_15_TRAINER_8 = 0x4B9
    BEAT_ROUTE_15_TRAINER_9 = 0x4BA
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
    GOT_TM21 = 0x1A8
    BEAT_ERIKA = 0x1A9
    BEAT_CELADON_GYM_TRAINER_0 = 0x1AA
    BEAT_CELADON_GYM_TRAINER_1 = 0x1AB
    BEAT_CELADON_GYM_TRAINER_2 = 0x1AC
    BEAT_CELADON_GYM_TRAINER_3 = 0x1AD
    BEAT_CELADON_GYM_TRAINER_4 = 0x1AE
    BEAT_CELADON_GYM_TRAINER_5 = 0x1AF
    BEAT_CELADON_GYM_TRAINER_6 = 0x1B0
    GOT_HM04 = 0x238
    GAVE_GOLD_TEETH = 0x239
    GOT_TM06 = 0x258
    BEAT_KOGA = 0x259
    BEAT_FUCHSIA_GYM_TRAINER_0 = 0x25A
    BEAT_FUCHSIA_GYM_TRAINER_1 = 0x25B
    BEAT_FUCHSIA_GYM_TRAINER_2 = 0x25C
    BEAT_FUCHSIA_GYM_TRAINER_3 = 0x25D
    BEAT_FUCHSIA_GYM_TRAINER_4 = 0x25E
    BEAT_FUCHSIA_GYM_TRAINER_5 = 0x25F
    MANSION_SWITCH_ON = 0x278
    BEAT_MANSION_1_TRAINER_0 = 0x289
    GOT_TM38 = 0x298
    BEAT_BLAINE = 0x299
    BEAT_CINNABAR_GYM_TRAINER_0 = 0x29A
    BEAT_CINNABAR_GYM_TRAINER_1 = 0x29B
    BEAT_CINNABAR_GYM_TRAINER_2 = 0x29C
    BEAT_CINNABAR_GYM_TRAINER_3 = 0x29D
    BEAT_CINNABAR_GYM_TRAINER_4 = 0x29E
    BEAT_CINNABAR_GYM_TRAINER_5 = 0x29F
    BEAT_CINNABAR_GYM_TRAINER_6 = 0x2A0
    CINNABAR_GYM_GATE_0_UNLOCKED = 0x2A8
    CINNABAR_GYM_GATE_1_UNLOCKED = 0x2A9
    CINNABAR_GYM_GATE_2_UNLOCKED = 0x2AA
    CINNABAR_GYM_GATE_3_UNLOCKED = 0x2AB
    CINNABAR_GYM_GATE_4_UNLOCKED = 0x2AC
    CINNABAR_GYM_GATE_5_UNLOCKED = 0x2AD
    CINNABAR_GYM_GATE_6_UNLOCKED = 0x2AE
    GOT_TM46 = 0x360
    DEFEATED_FIGHTING_DOJO = 0x350
    BEAT_KARATE_MASTER = 0x351
    BEAT_FIGHTING_DOJO_TRAINER_0 = 0x352
    BEAT_FIGHTING_DOJO_TRAINER_1 = 0x353
    BEAT_FIGHTING_DOJO_TRAINER_2 = 0x354
    BEAT_FIGHTING_DOJO_TRAINER_3 = 0x355
    GOT_HITMONLEE = 0x356
    GOT_HITMONCHAN = 0x357
    BEAT_SABRINA = 0x361
    BEAT_SAFFRON_GYM_TRAINER_0 = 0x362
    BEAT_SAFFRON_GYM_TRAINER_1 = 0x363
    BEAT_SAFFRON_GYM_TRAINER_2 = 0x364
    BEAT_SAFFRON_GYM_TRAINER_3 = 0x365
    BEAT_SAFFRON_GYM_TRAINER_4 = 0x366
    BEAT_SAFFRON_GYM_TRAINER_5 = 0x367
    BEAT_SAFFRON_GYM_TRAINER_6 = 0x368
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
    SAFARI_GAME_OVER = 0x24E
    IN_SAFARI_ZONE = 0x24F
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
    BEAT_SILPH_CO_3F_TRAINER_0 = 0x702
    SILPH_CO_3_UNLOCKED_DOOR_2 = 0x709
    BEAT_SILPH_CO_5F_TRAINER_0 = 0x722
    BEAT_SILPH_CO_RIVAL = 0x740
    BEAT_SILPH_CO_11F_TRAINER_0 = 0x784
    SILPH_CO_11_UNLOCKED_DOOR = 0x788
    GOT_MASTER_BALL = 0x78D
    BEAT_MANSION_2_TRAINER_0 = 0x801
    BEAT_MANSION_3_TRAINER_0 = 0x811
    BEAT_MANSION_3_TRAINER_1 = 0x812
    BEAT_MANSION_4_TRAINER_0 = 0x821
    BEAT_MANSION_4_TRAINER_1 = 0x822


class ItemId(IntEnum):
    MASTER_BALL = 0x01
    ULTRA_BALL = 0x02
    GREAT_BALL = 0x03
    POKE_BALL = 0x04
    ANTIDOTE = 0x0B
    AWAKENING = 0x0E
    PARLYZ_HEAL = 0x0F
    FULL_RESTORE = 0x10
    SUPER_POTION = 0x13
    HYPER_POTION = 0x12
    POTION = 0x14
    REPEL = 0x1E
    THUNDER_STONE = 0x21
    MAX_REPEL = 0x39
    DOME_FOSSIL = 0x29
    HELIX_FOSSIL = 0x2A
    SECRET_KEY = 0x2B
    NUGGET = 0x31
    SS_TICKET = 0x3F
    GOLD_TEETH = 0x40
    X_ATTACK = 0x41
    OAKS_PARCEL = 0x46
    SILPH_SCOPE = 0x48
    POKE_FLUTE = 0x49
    IRON = 0x25
    RARE_CANDY = 0x28
    X_ACCURACY = 0x2E
    X_SPECIAL = 0x44
    CARD_KEY = 0x30
    FULL_HEAL = 0x34
    REVIVE = 0x35
    LIFT_KEY = 0x4A
    EXP_ALL = 0x4B
    SUPER_ROD = 0x4E
    ELIXIR = 0x52
    HM01_CUT = 0xC4
    HM02_FLY = 0xC5
    HM03_SURF = 0xC6
    HM04_STRENGTH = 0xC7
    TM06_TOXIC = 0xCE
    TM01_MEGA_PUNCH = 0xC9
    TM05_MEGA_KICK = 0xCD
    TM09_TAKE_DOWN = 0xD1
    TM11_BUBBLEBEAM = 0xD3
    TM13_ICE_BEAM = 0xD5
    TM14_BLIZZARD = 0xD6
    TM16_PAY_DAY = 0xD8
    TM17_SUBMISSION = 0xD9
    TM20_RAGE = 0xDC
    TM21_MEGA_DRAIN = 0xDD
    TM27_FISSURE = 0xE3
    TM46_PSYWAVE = 0xF6
    TM24_THUNDERBOLT = 0xE0
    TM28_DIG = 0xE4
    TM34_BIDE = 0xEA
    TM38_FIRE_BLAST = 0xEE
    TM40_SKULL_BASH = 0xF0
    FRESH_WATER = 0x3C
    SODA_POP = 0x3D
    LEMONADE = 0x3E


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
ZUBAT_SPECIES_ID = 0x6B
SQUIRTLE_SPECIES_ID = 0xB1
WARTORTLE_SPECIES_ID = 0xB3
BLASTOISE_SPECIES_ID = 0x1C
SQUIRTLE_LINEAGE_SPECIES_IDS = frozenset(
    {SQUIRTLE_SPECIES_ID, WARTORTLE_SPECIES_ID, BLASTOISE_SPECIES_ID}
)
TACKLE_MOVE_ID = 0x21
TAIL_WHIP_MOVE_ID = 0x27
MEGA_PUNCH_MOVE_ID = 0x05
WATER_GUN_MOVE_ID = 0x37
BUBBLE_MOVE_ID = 0x91
BUBBLEBEAM_MOVE_ID = 0x3D
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
# ``EnemySendOut`` draws Red's two-option trainer-switch prompt at (1, 8).
# The live prompt responds only to A/B and has exactly two entries.  Requiring
# the already-loaded next enemy and an active cursor excludes stale menu RAM
# during final-KO dialogue and evolution.
TRAINER_SWITCH_PROMPT_SIGNATURE = (0x08, 0x01, 0x01, 0x03)
FILLED_MENU_CURSOR_TILE = 0xED
TILE_MAP_SIZE = 20 * 18
MIN_BATTLE_COMMAND = 0
MAX_BATTLE_COMMAND = 3
MIN_MOVE_MENU_SLOT = 1
MAX_MOVE_MENU_SLOT = 4
PARTY_LIMIT = 6
PARTY_STRUCT_STRIDE = 44
PARTY_SPECIES_OFFSET = 0
PARTY_HP_OFFSET = 1
PARTY_STATUS_OFFSET = 4
PARTY_MOVES_OFFSET = 8
PARTY_PP_OFFSET = 29
PARTY_LEVEL_OFFSET = 33
PARTY_MAX_HP_OFFSET = 34
MAX_BAG_ITEMS = 20
EVENT_FLAGS_END = 0xD886
EVENT_FLAG_BYTES = EVENT_FLAGS_END - int(RamAddress.EVENT_FLAGS)
POKEDEX_SPECIES_COUNT = 151
POKEDEX_FLAG_BYTES = 19
RED_BOX_LIMIT = 12
RED_BOX_CAPACITY = 20
RED_BOX_STRUCT_STRIDE = 33
RED_BOX_SPECIES_OFFSET = 0
RED_BOX_LEVEL_OFFSET = 3
RED_BOX_DATA_BYTES = 0x462
RED_BOXES_PER_SRAM_BANK = 6
RED_BOX_SRAM_BASE = 0xA000
RED_BOX_SRAM_BANKS = (2, 3)
RED_BOX_CHANGED_MASK = 0x80


@dataclass(frozen=True, slots=True)
class RedPokedexState:
    """National Pokédex ownership and sighting flags from the supported Red revision."""

    owned_species: frozenset[int]
    seen_species: frozenset[int]

    def __post_init__(self) -> None:
        for name in ("owned_species", "seen_species"):
            species = getattr(self, name)
            if any(
                type(number) is not int or not 1 <= number <= POKEDEX_SPECIES_COUNT
                for number in species
            ):
                raise ValueError(f"{name} must contain National Pokédex numbers 1 through 151")
        if not self.owned_species <= self.seen_species:
            raise ValueError("every owned species must also be marked seen")


@dataclass(frozen=True, slots=True)
class RedCurrentBoxState:
    """The currently loaded Bill's PC box using internal Red species identifiers."""

    box_index: int
    species_ids: tuple[int, ...]
    levels: tuple[int, ...]

    def __post_init__(self) -> None:
        if type(self.box_index) is not int or not 0 <= self.box_index < RED_BOX_LIMIT:
            raise ValueError("box_index must identify one of Red's twelve boxes")
        if len(self.species_ids) != len(self.levels):
            raise ValueError("box species and levels must have equal lengths")
        if len(self.species_ids) > RED_BOX_CAPACITY:
            raise ValueError("a Red box cannot contain more than twenty Pokémon")
        if any(type(species) is not int or species <= 0 for species in self.species_ids):
            raise ValueError("box species IDs must be positive integers")
        if any(type(level) is not int or not 1 <= level <= 100 for level in self.levels):
            raise ValueError("box levels must be between 1 and 100")


@dataclass(frozen=True, slots=True)
class RedBoxCollectionState:
    """A complete, checksum-verified view of all twelve PC boxes."""

    boxes: tuple[RedCurrentBoxState, ...]
    current_box_index: int
    storage_initialized: bool

    def __post_init__(self) -> None:
        if not isinstance(self.storage_initialized, bool):
            raise TypeError("storage_initialized must be a boolean")
        if (
            type(self.current_box_index) is not int
            or not 0 <= self.current_box_index < RED_BOX_LIMIT
        ):
            raise ValueError("current_box_index must identify one of Red's twelve boxes")
        if len(self.boxes) != RED_BOX_LIMIT:
            raise ValueError("box collection must contain all twelve boxes")
        if tuple(box.box_index for box in self.boxes) != tuple(range(RED_BOX_LIMIT)):
            raise ValueError("box collection must be ordered from box zero through eleven")

    @property
    def counts(self) -> tuple[int, ...]:
        return tuple(len(box.species_ids) for box in self.boxes)


@dataclass(frozen=True, slots=True)
class MenuCursorState:
    """Revision-decoded position and geometry of one live linear menu."""

    selected_visible_index: int
    scroll_offset: int
    maximum_visible_index: int
    top_x: int
    top_y: int

    def __post_init__(self) -> None:
        for name in (
            "selected_visible_index",
            "scroll_offset",
            "maximum_visible_index",
            "top_x",
            "top_y",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.selected_visible_index > self.maximum_visible_index:
            raise ValueError("selected menu index cannot exceed its visible maximum")

    @property
    def selected_absolute_index(self) -> int:
        return self.selected_visible_index + self.scroll_offset


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
    bag_items: tuple[tuple[int, int], ...] | None = None
    event_flags: bytes | None = None
    party_species_ids: tuple[int, ...] | None = None
    party_levels: tuple[int, ...] | None = None
    party_hp: tuple[int, ...] | None = None
    party_max_hp: tuple[int, ...] | None = None
    party_status: tuple[int, ...] | None = None
    party_moves: tuple[tuple[int, ...], ...] | None = None
    party_pp: tuple[tuple[int, ...], ...] | None = None
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
    player_special_stage: int | None = None
    player_accuracy_stage: int | None = None
    enemy_defense_stage: int | None = None
    player_disabled_move_slot: int | None = None
    player_disable_turns: int | None = None
    enemy_using_trapping_move: bool | None = None
    active_party_index: int | None = None
    active_party_species_id: int | None = None
    active_party_level: int | None = None
    active_party_hp: int | None = None
    active_party_max_hp: int | None = None
    active_party_status: int | None = None
    active_party_moves: tuple[int, ...] | None = None
    active_party_pp: tuple[int, ...] | None = None
    player_money: int | None = None

    @property
    def battler_level(self) -> int | None:
        """The active battler's level, falling back to the field lead."""

        return self.active_party_level or self.first_party_level

    @property
    def battler_hp(self) -> int | None:
        """The active battler's HP, falling back to the field lead."""

        return self.active_party_hp if self.active_party_hp is not None else self.first_party_hp

    @property
    def battler_max_hp(self) -> int | None:
        """The active battler's maximum HP, falling back to the field lead."""

        return (
            self.active_party_max_hp
            if self.active_party_max_hp is not None
            else self.first_party_max_hp
        )

    @property
    def battler_status(self) -> int | None:
        """The active battler's persistent status, falling back to the field lead."""

        return (
            self.active_party_status
            if self.active_party_status is not None
            else self.first_party_status
        )

    @property
    def battler_moves(self) -> tuple[int, ...] | None:
        """The active battler's moves, falling back to the field lead."""

        return self.active_party_moves or self.first_party_moves

    @property
    def battler_pp(self) -> tuple[int, ...] | None:
        """The active battler's PP, falling back to the field lead."""

        return self.active_party_pp or self.first_party_pp


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
        hp = self.first_party_hp
        max_hp = self.first_party_max_hp
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
            # Gen I DVs legitimately place a level-six, zero-stat-exp
            # Squirtle between 21 and 23 max HP.  The clean-start timing root
            # influences those DVs, so one exact stat vector is not semantic
            # victory evidence.  Keep the cartridge win/event proof and
            # require a living, internally consistent supported starter.
            and hp is not None
            and max_hp is not None
            and 0 < hp <= max_hp
            and 21 <= max_hp <= 23
        )

    @property
    def rival_resolution_snapshot(self) -> bool:
        """Authenticate either legal terminal outcome of the optional lab battle.

        Red advances Oak's script after both a win and a loss.  A loss restores the
        level-five starter to full health, while a win leaves the surviving
        level-six starter at its battle HP.  Keep those outcomes distinct so a
        completion teacher can recover the missed experience without claiming a
        victory that did not happen.
        """

        hp = self.first_party_hp
        max_hp = self.first_party_max_hp
        common = (
            self.phase is OaksErrandPhase.RIVAL_DEFEATED
            and self.map_id == MapId.OAKS_LAB
            and self.battle_state == 0
            and self.lab_script == 18
            and self.controls_ready
            and self.battled_rival
            and self.first_party_species == SQUIRTLE_SPECIES_ID
            and hp is not None
            and max_hp is not None
            and 0 < hp <= max_hp
        )
        if not common:
            return False
        if self.battle_result == 0:
            return self.first_party_level == 6 and 21 <= max_hp <= 23
        if self.battle_result == 1:
            return self.first_party_level == 5 and hp == max_hp and 19 <= max_hp <= 21
        return False

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
    walk_counter: int = 0

    @property
    def ready(self) -> bool:
        return (
            self.joy_ignore == 0
            and self.simulated_joypad_index == 0
            and self.npc_movement_script_table == 0
            and self.player_moving_direction == 0
            and not bool(self.status_flags_5 & SCRIPTED_MOVEMENT_STATUS_MASK)
            and not bool(self.movement_flags & EXITING_DOOR_MOVEMENT_MASK)
            and self.walk_counter == 0
        )


class VisibleMapObjectError(ValueError):
    """Raised when revision-pinned live sprite state is internally impossible."""


@dataclass(frozen=True, slots=True)
class VisibleMapObject:
    """One currently rendered, collision-bearing non-player map sprite."""

    sprite_index: int
    picture_id: int
    at: tuple[int, int]
    movement_status: int
    image_index: int

    def __post_init__(self) -> None:
        if not 1 <= self.sprite_index <= 15:
            raise ValueError("a map sprite index must be between 1 and 15")
        if not 1 <= self.picture_id <= 0xFF:
            raise ValueError("a visible map sprite needs a picture id")
        if self.image_index == 0xFF:
            raise ValueError("an off-screen sprite is not visibly occupying a coordinate")

    @property
    def moving(self) -> bool:
        return self.movement_status == 3


class CurrentStrengthBoulderError(ValueError):
    """Raised when revision-pinned live boulder state is internally impossible."""


@dataclass(frozen=True, slots=True)
class CurrentStrengthBoulder:
    """One currently pushable boulder, including objects outside the viewport."""

    sprite_index: int
    at: tuple[int, int]
    movement_status: int
    image_index: int
    movement_byte_2: int

    def __post_init__(self) -> None:
        if not 1 <= self.sprite_index <= 15:
            raise ValueError("a boulder sprite index must be between 1 and 15")
        if self.movement_byte_2 != 0x10:
            raise ValueError("a Strength boulder needs the engine's pushable movement byte")

    @property
    def visible(self) -> bool:
        return self.image_index != 0xFF


class CurrentMapObjectError(ValueError):
    """Raised when the active map-wide sprite table is internally impossible."""


@dataclass(frozen=True, slots=True)
class CurrentMapObject:
    """One toggle-present map object, whether inside the viewport or not."""

    sprite_index: int
    picture_id: int
    at: tuple[int, int]
    movement_status: int
    image_index: int
    facing_direction: int = 0

    def __post_init__(self) -> None:
        if not 1 <= self.sprite_index <= 15:
            raise ValueError("a map sprite index must be between 1 and 15")
        if not 1 <= self.picture_id <= 0xFF:
            raise ValueError("a current map sprite needs a picture id")

    @property
    def visible(self) -> bool:
        return self.image_index != 0xFF

    @property
    def moving(self) -> bool:
        return self.movement_status == 3


class CurrentMapBlocksError(ValueError):
    """Raised when Red's live bordered block buffer is internally impossible."""


@dataclass(frozen=True, slots=True)
class CurrentMapBlocks:
    """The current map's mutable block ids, excluding its three-block border."""

    map_id: int
    rows: tuple[tuple[int, ...], ...]

    def __post_init__(self) -> None:
        widths = tuple(len(row) for row in self.rows)
        if not widths or not widths[0] or len(set(widths)) != 1:
            raise ValueError("current map blocks must form a non-empty rectangular grid")

    @property
    def height(self) -> int:
        return len(self.rows)

    @property
    def width(self) -> int:
        return len(self.rows[0])

    def at(self, y: int, x: int) -> int:
        return self.rows[y][x]


class OverworldMovementModeError(ValueError):
    """Raised when the revision exposes an unknown locomotion byte."""


class OverworldMovementMode(IntEnum):
    """Revision-decoded player locomotion state from ``wWalkBikeSurfState``."""

    WALKING = 0
    BIKING = 1
    SURFING = 2

    @property
    def traversal_mode(self) -> str:
        return "water" if self is OverworldMovementMode.SURFING else "land"


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
            self.unbeaten_brock_transit_invariants
            and self.battle_state == 0
            and self.controls.ready
            and self.current_map_script == 0
        )

    @property
    def unbeaten_brock_transit_invariants(self) -> bool:
        status_is_safe = self.first_party_status == 0 or (
            self.first_party_status == 0x08
            and self.boundary
            in {
                TravelBoundary.FOREST_NORTH_GATE,
                TravelBoundary.ROUTE_2_NORTH_RETURN,
                TravelBoundary.PEWTER_SOUTH_EDGE,
            }
        )
        return (
            self.post_pokedex_invariants
            and status_is_safe
            and not self.beat_brock
            and not self.got_tm34
            and not self.tm34_in_bag
            and not self.boulder_badge
            and not self.boulder_badge_mirror
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
        self._last_encounter: tuple[int | None, ...] | None = None
        self._encounter_log = encounter_log_path()

    def read(self) -> RawGameState:
        status = self._memory.read_u8(RamAddress.STATUS_FLAGS_6)
        game_started = bool(status & GAME_TIMER_COUNTING_MASK)
        if not game_started:
            return RawGameState(False, None, None, None, None, None)

        bag_count = min(self._memory.read_u8(RamAddress.NUM_BAG_ITEMS), MAX_BAG_ITEMS)
        bag_entries = tuple(
            (
                self._memory.read_u8(int(RamAddress.BAG_ITEMS) + index * 2),
                self._memory.read_u8(int(RamAddress.BAG_ITEMS) + index * 2 + 1),
            )
            for index in range(bag_count)
        )
        bag_items = tuple(item_id for item_id, _quantity in bag_entries)
        party_count = min(self._memory.read_u8(RamAddress.PARTY_COUNT), PARTY_LIMIT)
        party_species = tuple(
            self._memory.read_u8(int(RamAddress.PARTY_SPECIES) + index)
            for index in range(party_count)
        )
        party_bases = tuple(
            int(RamAddress.PARTY_MON_1) + index * PARTY_STRUCT_STRIDE
            for index in range(party_count)
        )
        party_levels = tuple(
            self._memory.read_u8(base + PARTY_LEVEL_OFFSET) for base in party_bases
        )
        party_hp = tuple(self._read_u16_be(base + PARTY_HP_OFFSET) for base in party_bases)
        party_max_hp = tuple(self._read_u16_be(base + PARTY_MAX_HP_OFFSET) for base in party_bases)
        party_status = tuple(
            self._memory.read_u8(base + PARTY_STATUS_OFFSET) for base in party_bases
        )
        party_moves = tuple(
            tuple(self._memory.read_u8(base + PARTY_MOVES_OFFSET + index) for index in range(4))
            for base in party_bases
        )
        party_pp = tuple(
            tuple(self._memory.read_u8(base + PARTY_PP_OFFSET + index) for index in range(4))
            for base in party_bases
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
        battle_state = self._memory.read_u8(RamAddress.IS_IN_BATTLE)
        active_party_index = (
            self._memory.read_u8(RamAddress.PLAYER_MON_NUMBER) if battle_state else None
        )
        if active_party_index is not None and 0 <= active_party_index < party_count:
            active_base = int(RamAddress.PARTY_MON_1) + active_party_index * PARTY_STRUCT_STRIDE
            active_party_species_id = self._memory.read_u8(active_base + PARTY_SPECIES_OFFSET)
            active_party_level = self._memory.read_u8(active_base + PARTY_LEVEL_OFFSET)
            active_party_hp = self._read_u16_be(active_base + PARTY_HP_OFFSET)
            active_party_max_hp = self._read_u16_be(active_base + PARTY_MAX_HP_OFFSET)
            active_party_status = self._memory.read_u8(active_base + PARTY_STATUS_OFFSET)
            active_party_moves = tuple(
                self._memory.read_u8(active_base + PARTY_MOVES_OFFSET + index) for index in range(4)
            )
            active_party_pp = tuple(
                self._memory.read_u8(active_base + PARTY_PP_OFFSET + index) for index in range(4)
            )
        else:
            active_party_index = None
            active_party_species_id = None
            active_party_level = None
            active_party_hp = None
            active_party_max_hp = None
            active_party_status = None
            active_party_moves = None
            active_party_pp = None
        events = bytes(
            self._memory.read_u8(int(RamAddress.EVENT_FLAGS) + index)
            for index in range(EVENT_FLAG_BYTES)
        )
        disabled_move = self._memory.read_u8(RamAddress.PLAYER_DISABLED_MOVE) if battle_state else 0
        disabled_slot = (disabled_move >> 4) & 0x0F
        raw = RawGameState(
            game_started=True,
            map_id=self._memory.read_u8(RamAddress.CURRENT_MAP),
            player_x=self._memory.read_u8(RamAddress.PLAYER_X),
            player_y=self._memory.read_u8(RamAddress.PLAYER_Y),
            party_count=party_count,
            battle_state=battle_state,
            badge_bits=self._memory.read_u8(RamAddress.OBTAINED_BADGES),
            bag_item_ids=bag_items,
            bag_items=bag_entries,
            event_flags=events,
            party_species_ids=party_species,
            party_levels=party_levels,
            party_hp=party_hp,
            party_max_hp=party_max_hp,
            party_status=party_status,
            party_moves=party_moves,
            party_pp=party_pp,
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
            player_special_stage=(
                self._memory.read_u8(RamAddress.PLAYER_SPECIAL_STAGE) if battle_state else None
            ),
            player_accuracy_stage=(
                self._memory.read_u8(RamAddress.PLAYER_ACCURACY_STAGE) if battle_state else None
            ),
            enemy_defense_stage=(
                self._memory.read_u8(RamAddress.ENEMY_DEFENSE_STAGE) if battle_state else None
            ),
            player_disabled_move_slot=(
                disabled_slot if battle_state and 1 <= disabled_slot <= 4 else None
            ),
            player_disable_turns=(disabled_move & 0x0F) if battle_state else None,
            enemy_using_trapping_move=(
                bool(self._memory.read_u8(RamAddress.ENEMY_BATTLE_STATUS_1) & (1 << 5))
                if battle_state
                else None
            ),
            active_party_index=active_party_index,
            active_party_species_id=active_party_species_id,
            active_party_level=active_party_level,
            active_party_hp=active_party_hp,
            active_party_max_hp=active_party_max_hp,
            active_party_status=active_party_status,
            active_party_moves=active_party_moves,
            active_party_pp=active_party_pp,
            player_money=self._read_bcd(RamAddress.PLAYER_MONEY, 3),
        )

        if self._encounter_log is not None:
            self._record_encounter(raw)
        return raw

    def _record_encounter(self, raw: RawGameState) -> None:
        """Append one newly seen encounter to the harvest log.

        Only distinct encounters are written, so the cost is per battle rather
        than per read.  Battle memory is not populated the instant the battle
        flag flips: reads taken during that transition report species zero at
        level zero, which is how five nonexistent "wild encounters in Pallet
        Town" reached an earlier log.  Those are dropped here rather than left
        for the harvester, because a band is only as honest as its samples.
        """

        if not is_wild_encounter(raw):
            return
        encounter = (raw.map_id, raw.enemy_species_id, raw.enemy_level)
        if encounter == self._last_encounter:
            return
        self._last_encounter = encounter
        entry = {
            "map_id": raw.map_id,
            "enemy_species": raw.enemy_species_id,
            "enemy_level": raw.enemy_level,
            "battle_state": raw.battle_state,
        }
        with self._encounter_log.open("a", encoding="utf-8") as log:
            log.write(json.dumps(entry) + "\n")

    def read_pokedex_state(self) -> RedPokedexState:
        """Decode Red's two 151-bit National Pokédex flag arrays."""

        owned = bytes(
            self._memory.read_u8(int(RamAddress.POKEDEX_OWNED) + index)
            for index in range(POKEDEX_FLAG_BYTES)
        )
        seen = bytes(
            self._memory.read_u8(int(RamAddress.POKEDEX_SEEN) + index)
            for index in range(POKEDEX_FLAG_BYTES)
        )
        return RedPokedexState(
            owned_species=_decode_pokedex_flags(owned),
            seen_species=_decode_pokedex_flags(seen),
        )

    def read_current_box_state(self) -> RedCurrentBoxState:
        """Read and cross-check the current 20-slot Bill's PC box."""

        count = self._memory.read_u8(RamAddress.CURRENT_BOX_COUNT)
        if count > RED_BOX_CAPACITY:
            raise SemanticStateError(
                f"current box reports {count} Pokémon, above Red's {RED_BOX_CAPACITY}-slot limit"
            )
        box_index = self._memory.read_u8(RamAddress.CURRENT_BOX_NUMBER) & 0x7F
        species_ids = tuple(
            self._memory.read_u8(int(RamAddress.CURRENT_BOX_SPECIES) + index)
            for index in range(count)
        )
        struct_species = tuple(
            self._memory.read_u8(
                int(RamAddress.CURRENT_BOX_MONS)
                + index * RED_BOX_STRUCT_STRIDE
                + RED_BOX_SPECIES_OFFSET
            )
            for index in range(count)
        )
        if species_ids != struct_species:
            raise SemanticStateError(
                "current box species list disagrees with its boxed Pokémon structures"
            )
        levels = tuple(
            self._memory.read_u8(
                int(RamAddress.CURRENT_BOX_MONS)
                + index * RED_BOX_STRUCT_STRIDE
                + RED_BOX_LEVEL_OFFSET
            )
            for index in range(count)
        )
        return RedCurrentBoxState(
            box_index=box_index,
            species_ids=species_ids,
            levels=levels,
        )

    def read_all_box_states(self) -> RedBoxCollectionState:
        """Read all twelve boxes without exposing banked bytes to a planner.

        Red keeps the active box in Work RAM. After the first in-game box
        change, the other eleven boxes live in two checksummed SRAM banks and
        the active box's SRAM slot is deliberately marked empty. Before that
        first change, the source defines every non-active box as logically
        empty even though their backing SRAM has not been initialized.
        """

        current_box = self.read_current_box_state()
        raw_box_number = self._memory.read_u8(RamAddress.CURRENT_BOX_NUMBER)
        storage_initialized = bool(raw_box_number & RED_BOX_CHANGED_MASK)
        if not storage_initialized:
            return RedBoxCollectionState(
                boxes=tuple(
                    current_box
                    if box_index == current_box.box_index
                    else RedCurrentBoxState(box_index, (), ())
                    for box_index in range(RED_BOX_LIMIT)
                ),
                current_box_index=current_box.box_index,
                storage_initialized=False,
            )

        if not isinstance(self._memory, ReadOnlyCartridgeRam):
            raise SemanticStateError(
                "all-box inspection requires the bounded read-only cartridge-RAM port"
            )

        saved_boxes: list[RedCurrentBoxState] = []
        for bank_offset, bank in enumerate(RED_BOX_SRAM_BANKS):
            bank_payload = bytes(
                self._memory.read_cartridge_ram_u8(
                    bank,
                    RED_BOX_SRAM_BASE + offset,
                )
                for offset in range(RED_BOXES_PER_SRAM_BANK * RED_BOX_DATA_BYTES)
            )
            checksum_base = RED_BOX_SRAM_BASE + len(bank_payload)
            expected_bank_checksum = self._memory.read_cartridge_ram_u8(bank, checksum_base)
            if _red_box_checksum(bank_payload) != expected_bank_checksum:
                raise SemanticStateError(f"saved box SRAM bank {bank} failed its checksum")

            for bank_box_index in range(RED_BOXES_PER_SRAM_BANK):
                box_index = bank_offset * RED_BOXES_PER_SRAM_BANK + bank_box_index
                start = bank_box_index * RED_BOX_DATA_BYTES
                payload = bank_payload[start : start + RED_BOX_DATA_BYTES]
                expected_box_checksum = self._memory.read_cartridge_ram_u8(
                    bank,
                    checksum_base + 1 + bank_box_index,
                )
                if _red_box_checksum(payload) != expected_box_checksum:
                    raise SemanticStateError(f"saved box {box_index + 1} failed its checksum")
                saved_boxes.append(_decode_saved_red_box(box_index, payload))

        saved_boxes[current_box.box_index] = current_box
        return RedBoxCollectionState(
            boxes=tuple(saved_boxes),
            current_box_index=current_box.box_index,
            storage_initialized=True,
        )

    def read_menu_cursor_state(self) -> MenuCursorState:
        """Translate Red's current linear-menu cursor fields."""

        return MenuCursorState(
            selected_visible_index=self._memory.read_u8(RamAddress.CURRENT_MENU_ITEM),
            scroll_offset=self._memory.read_u8(RamAddress.LIST_SCROLL_OFFSET),
            maximum_visible_index=self._memory.read_u8(RamAddress.MAX_MENU_ITEM),
            top_x=self._memory.read_u8(RamAddress.TOP_MENU_ITEM_X),
            top_y=self._memory.read_u8(RamAddress.TOP_MENU_ITEM_Y),
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

    def trainer_switch_prompt_visible(self, raw: RawGameState) -> bool:
        """Return whether Red's live trainer-switch yes/no prompt owns input.

        The pinned battle engine loads the next enemy before displaying this
        prompt.  Evolution follows only after the final enemy has zero HP, so
        the enemy-HP gate and active two-option cursor distinguish the two
        transitions without relying on frame or button counts.
        """

        if raw.battle_state != 2 or (raw.enemy_hp or 0) <= 0 or (raw.party_count or 0) <= 1:
            return False
        signature = (
            self._memory.read_u8(RamAddress.TOP_MENU_ITEM_Y),
            self._memory.read_u8(RamAddress.TOP_MENU_ITEM_X),
            self._memory.read_u8(RamAddress.MAX_MENU_ITEM),
            self._memory.read_u8(RamAddress.MENU_WATCHED_KEYS),
        )
        selected = self._memory.read_u8(RamAddress.CURRENT_MENU_ITEM)
        return (
            signature == TRAINER_SWITCH_PROMPT_SIGNATURE
            and selected in {0, 1}
            and self._active_menu_cursor()
        )

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
            walk_counter=self._memory.read_u8(RamAddress.WALK_COUNTER),
        )

    def read_visible_map_objects(self) -> tuple[VisibleMapObject, ...]:
        """Project collision-bearing sprites that Red currently renders.

        The pinned engine stores fifteen non-player sprite slots in two
        parallel 16-byte tables. ``image_index == 0xff`` is the engine's own
        unavailable marker for a hidden or off-screen object, so this method
        deliberately promises visible occupancy rather than every object on
        the map. Failed-step discovery remains necessary outside that window.
        """

        count = self._memory.read_u8(RamAddress.NUM_SPRITES)
        if count > 15:
            raise VisibleMapObjectError(f"current map exposes impossible sprite count {count}")
        found: list[VisibleMapObject] = []
        for sprite_index in range(1, count + 1):
            state_1 = int(RamAddress.SPRITE_STATE_DATA_1) + sprite_index * 0x10
            state_2 = int(RamAddress.SPRITE_STATE_DATA_2) + sprite_index * 0x10
            picture_id = self._memory.read_u8(state_1)
            image_index = self._memory.read_u8(state_1 + 2)
            if picture_id == 0 or image_index == 0xFF:
                continue
            padded_y = self._memory.read_u8(state_2 + 4)
            padded_x = self._memory.read_u8(state_2 + 5)
            if padded_y < 4 or padded_x < 4:
                raise VisibleMapObjectError(
                    f"visible sprite {sprite_index} has invalid padded coordinate "
                    f"{(padded_y, padded_x)}"
                )
            found.append(
                VisibleMapObject(
                    sprite_index=sprite_index,
                    picture_id=picture_id,
                    at=(padded_y - 4, padded_x - 4),
                    movement_status=self._memory.read_u8(state_1 + 1),
                    image_index=image_index,
                )
            )
        return tuple(found)

    def read_visible_object_coordinates(self) -> frozenset[tuple[int, int]]:
        return frozenset(item.at for item in self.read_visible_map_objects())

    def read_current_map_objects(self) -> tuple[CurrentMapObject, ...]:
        """Read every toggle-present object from the map-wide sprite table."""

        count = self._memory.read_u8(RamAddress.NUM_SPRITES)
        if count > 15:
            raise CurrentMapObjectError(
                f"current map exposes impossible sprite count {count}"
            )
        hidden = self._read_hidden_current_sprite_indices()
        found: list[CurrentMapObject] = []
        occupied: set[tuple[int, int]] = set()
        for sprite_index in range(1, count + 1):
            if sprite_index in hidden:
                continue
            state_1 = int(RamAddress.SPRITE_STATE_DATA_1) + sprite_index * 0x10
            picture_id = self._memory.read_u8(state_1)
            if picture_id == 0:
                continue
            state_2 = int(RamAddress.SPRITE_STATE_DATA_2) + sprite_index * 0x10
            padded_y = self._memory.read_u8(state_2 + 4)
            padded_x = self._memory.read_u8(state_2 + 5)
            if padded_y < 4 or padded_x < 4:
                raise CurrentMapObjectError(
                    f"current sprite {sprite_index} has invalid padded coordinate "
                    f"{(padded_y, padded_x)}"
                )
            at = padded_y - 4, padded_x - 4
            if at in occupied:
                raise CurrentMapObjectError(
                    f"multiple current map objects occupy coordinate {at}"
                )
            occupied.add(at)
            found.append(
                CurrentMapObject(
                    sprite_index=sprite_index,
                    picture_id=picture_id,
                    at=at,
                    movement_status=self._memory.read_u8(state_1 + 1),
                    image_index=self._memory.read_u8(state_1 + 2),
                    facing_direction=self._memory.read_u8(state_1 + 9),
                )
            )
        return tuple(found)

    def read_current_object_coordinates(self) -> frozenset[tuple[int, int]]:
        return frozenset(item.at for item in self.read_current_map_objects())

    def trainer_engagement_active(self) -> bool:
        """Recognize the field interval between sight and trainer battle.

        ``wMiscFlags`` bit zero is overloaded by field actions, so it is not
        sufficient by itself.  A sight engagement also owns movement input or
        runs the engine's scripted NPC walk; requiring both sides avoids
        treating a stale successful-item flag as an encounter.
        """

        if not self._memory.read_u8(RamAddress.MISC_FLAGS) & 0x01:
            return False
        readiness = self.read_input_readiness()
        return bool(
            readiness.joy_ignore & JOY_IGNORE_MOVEMENT_MASK
            or readiness.npc_movement_script_table
            or readiness.status_flags_5 & 0x01
        )

    def read_current_strength_boulders(self) -> tuple[CurrentStrengthBoulder, ...]:
        """Read every pushable boulder from the current map's live sprite slots.

        Unlike :meth:`read_visible_map_objects`, this observation deliberately
        retains ``image_index == 0xff`` entries. Red keeps off-screen boulders'
        map coordinates in state data 2, and a puzzle planner must not turn
        those temporarily unrendered objects into empty floor. It does exclude
        objects whose current-map toggle flag says they are removed: those
        slots also retain coordinates and an off-screen image marker, but the
        collision engine no longer treats them as present.
        """

        count = self._memory.read_u8(RamAddress.NUM_SPRITES)
        if count > 15:
            raise CurrentStrengthBoulderError(
                f"current map exposes impossible sprite count {count}"
            )
        hidden = self._read_hidden_current_sprite_indices()
        found: list[CurrentStrengthBoulder] = []
        occupied: set[tuple[int, int]] = set()
        for sprite_index in range(1, count + 1):
            if sprite_index in hidden:
                continue
            state_1 = int(RamAddress.SPRITE_STATE_DATA_1) + sprite_index * 0x10
            if self._memory.read_u8(state_1) != 0x3F:
                continue
            movement_byte_2 = self._memory.read_u8(
                int(RamAddress.MAP_SPRITE_DATA) + 2 * (sprite_index - 1)
            )
            if movement_byte_2 != 0x10:
                continue
            state_2 = int(RamAddress.SPRITE_STATE_DATA_2) + sprite_index * 0x10
            padded_y = self._memory.read_u8(state_2 + 4)
            padded_x = self._memory.read_u8(state_2 + 5)
            if padded_y < 4 or padded_x < 4:
                raise CurrentStrengthBoulderError(
                    f"Strength boulder {sprite_index} has invalid padded coordinate "
                    f"{(padded_y, padded_x)}"
                )
            at = padded_y - 4, padded_x - 4
            if at in occupied:
                raise CurrentStrengthBoulderError(
                    f"multiple Strength boulders occupy coordinate {at}"
                )
            occupied.add(at)
            found.append(
                CurrentStrengthBoulder(
                    sprite_index=sprite_index,
                    at=at,
                    movement_status=self._memory.read_u8(state_1 + 1),
                    image_index=self._memory.read_u8(state_1 + 2),
                    movement_byte_2=movement_byte_2,
                )
            )
        return tuple(found)

    def _read_hidden_current_sprite_indices(self) -> frozenset[int]:
        """Resolve the engine's current-map sprite/global-toggle pairs."""

        base = int(RamAddress.TOGGLEABLE_OBJECT_LIST)
        hidden: set[int] = set()
        seen: set[int] = set()
        for entry_index in range(16 + 1):
            sprite_index = self._memory.read_u8(base + entry_index * 2)
            if sprite_index == 0xFF:
                return frozenset(hidden)
            if not 1 <= sprite_index <= 15:
                raise CurrentStrengthBoulderError(
                    f"toggleable object list exposes invalid sprite {sprite_index}"
                )
            if sprite_index in seen:
                raise CurrentStrengthBoulderError(
                    f"toggleable object list repeats sprite {sprite_index}"
                )
            seen.add(sprite_index)
            toggle_index = self._memory.read_u8(base + entry_index * 2 + 1)
            address = int(RamAddress.TOGGLEABLE_OBJECT_FLAGS) + toggle_index // 8
            if self._memory.read_u8(address) & (1 << (toggle_index % 8)):
                hidden.add(sprite_index)
        raise CurrentStrengthBoulderError(
            "toggleable object list lacks its bounded sentinel"
        )

    def read_current_map_blocks(self) -> CurrentMapBlocks:
        """Read the active mutable block grid from Red's bordered map buffer.

        The engine copies a map into ``wOverworldMap`` with three connection
        blocks of padding on every side. Cut mutates that buffer rather than
        cartridge data, so current traversal must read the inner grid back
        before it claims a tree changed the map.
        """

        map_id = self._memory.read_u8(RamAddress.CURRENT_MAP)
        height = self._memory.read_u8(RamAddress.CURRENT_MAP_HEIGHT)
        width = self._memory.read_u8(RamAddress.CURRENT_MAP_WIDTH)
        stride = width + 6
        if height == 0 or width == 0 or (height + 6) * stride > 1300:
            raise CurrentMapBlocksError(
                f"current map exposes impossible block dimensions {(height, width)}"
            )
        origin = int(RamAddress.OVERWORLD_MAP) + 3 * stride + 3
        rows = tuple(
            tuple(self._memory.read_u8(origin + y * stride + x) for x in range(width))
            for y in range(height)
        )
        return CurrentMapBlocks(map_id, rows)

    def read_overworld_movement_mode(self) -> OverworldMovementMode:
        raw = self._memory.read_u8(RamAddress.WALK_BIKE_SURF_STATE)
        try:
            return OverworldMovementMode(raw)
        except ValueError as error:
            raise OverworldMovementModeError(
                f"unsupported overworld movement mode {raw}"
            ) from error

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

    def _read_bcd(self, address: int, length: int) -> int:
        value = 0
        for offset in range(length):
            packed = self._memory.read_u8(address + offset)
            high, low = packed >> 4, packed & 0x0F
            if high > 9 or low > 9:
                raise SemanticStateError("packed decimal observation contains an invalid digit")
            value = value * 100 + high * 10 + low
        return value


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
        and (ItemId.TM11_BUBBLEBEAM in items or BUBBLEBEAM_MOVE_ID in (raw.first_party_moves or ()))
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
        MapId.CINNABAR_POKECENTER: "cinnabar_pokecenter",
        MapId.INDIGO_PLATEAU: "indigo_plateau",
        MapId.SAFFRON_CITY: "saffron_city",
        MapId.SAFFRON_POKECENTER: "saffron_pokecenter",
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
        MapId.ROUTE_12: "route_12",
        MapId.ROUTE_13: "route_13",
        MapId.ROUTE_14: "route_14",
        MapId.ROUTE_15: "route_15",
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
        MapId.LAVENDER_MART: "lavender_mart",
        MapId.FUCHSIA_POKECENTER: "fuchsia_pokecenter",
        MapId.WARDENS_HOUSE: "wardens_house",
        MapId.FUCHSIA_GYM: "fuchsia_gym",
        MapId.CELADON_POKECENTER: "celadon_pokecenter",
        MapId.GAME_CORNER: "game_corner",
        MapId.ROCKET_HIDEOUT_B1F: "rocket_hideout_b1f",
        MapId.ROCKET_HIDEOUT_B2F: "rocket_hideout_b2f",
        MapId.ROCKET_HIDEOUT_B3F: "rocket_hideout_b3f",
        MapId.ROCKET_HIDEOUT_B4F: "rocket_hideout_b4f",
        MapId.ROCKET_HIDEOUT_ELEVATOR: "rocket_hideout_elevator",
        MapId.LANCES_ROOM: "lances_room",
        MapId.HALL_OF_FAME: "hall_of_fame",
        MapId.CHAMPIONS_ROOM: "champions_room",
        MapId.INDIGO_PLATEAU_LOBBY: "indigo_plateau_lobby",
        MapId.LORELEIS_ROOM: "loreleis_room",
        MapId.BRUNOS_ROOM: "brunos_room",
        MapId.AGATHAS_ROOM: "agathas_room",
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
        MapId.LAVENDER_MART: "location:lavender_town",
        MapId.VERMILION_CITY: "location:vermilion_city",
        MapId.CELADON_CITY: "location:celadon_city",
        MapId.CELADON_POKECENTER: "location:celadon_city",
        MapId.FUCHSIA_CITY: "location:fuchsia_city",
        MapId.FUCHSIA_POKECENTER: "location:fuchsia_city",
        MapId.WARDENS_HOUSE: "location:fuchsia_city",
        MapId.FUCHSIA_GYM: "location:fuchsia_city",
        MapId.CINNABAR_ISLAND: "location:cinnabar_island",
        MapId.CINNABAR_POKECENTER: "location:cinnabar_island",
        MapId.CINNABAR_MART: "location:cinnabar_island",
        MapId.CINNABAR_GYM: "location:cinnabar_island",
        MapId.POKEMON_MANSION_1F: "location:cinnabar_island",
        MapId.POKEMON_MANSION_2F: "location:cinnabar_island",
        MapId.POKEMON_MANSION_3F: "location:cinnabar_island",
        MapId.POKEMON_MANSION_B1F: "location:cinnabar_island",
        MapId.SAFFRON_CITY: "location:saffron_city",
        MapId.SAFFRON_POKECENTER: "location:saffron_city",
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
    if ItemId.GOLD_TEETH in items:
        facts.add("item:gold_teeth")
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


def _decode_pokedex_flags(payload: bytes) -> frozenset[int]:
    if len(payload) != POKEDEX_FLAG_BYTES:
        raise ValueError(f"Pokédex flags must contain exactly {POKEDEX_FLAG_BYTES} bytes")
    return frozenset(
        national_number
        for national_number in range(1, POKEDEX_SPECIES_COUNT + 1)
        if payload[(national_number - 1) // 8] & (1 << ((national_number - 1) % 8))
    )


def _red_box_checksum(payload: bytes) -> int:
    """Match Red's complemented one-byte ``CalcCheckSum`` routine."""

    return (~sum(payload)) & 0xFF


def _decode_saved_red_box(box_index: int, payload: bytes) -> RedCurrentBoxState:
    if len(payload) != RED_BOX_DATA_BYTES:
        raise ValueError(f"saved Red box must contain exactly {RED_BOX_DATA_BYTES} bytes")
    count = payload[0]
    if count > RED_BOX_CAPACITY:
        raise SemanticStateError(
            f"saved box {box_index + 1} reports {count} Pokémon, "
            f"above Red's {RED_BOX_CAPACITY}-slot limit"
        )
    species_ids = tuple(payload[1 : 1 + count])
    structures_base = 1 + RED_BOX_CAPACITY + 1
    struct_species = tuple(
        payload[structures_base + index * RED_BOX_STRUCT_STRIDE + RED_BOX_SPECIES_OFFSET]
        for index in range(count)
    )
    if species_ids != struct_species:
        raise SemanticStateError(
            f"saved box {box_index + 1} species list disagrees with its Pokémon structures"
        )
    levels = tuple(
        payload[structures_base + index * RED_BOX_STRUCT_STRIDE + RED_BOX_LEVEL_OFFSET]
        for index in range(count)
    )
    return RedCurrentBoxState(
        box_index=box_index,
        species_ids=species_ids,
        levels=levels,
    )


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
