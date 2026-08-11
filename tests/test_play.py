from __future__ import annotations

import hashlib
import json
import os
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.fuchsia import (
    SNORLAX,
    SNORLAX_CAPTURE_POLICY,
    SNORLAX_SUPER_POTION_RESERVE,
)
from pokemon_red_completion.observation import (
    SQUIRTLE_SPECIES_ID,
    Badge,
    BattleMenuPhase,
    BattleMenuState,
    InputReadiness,
    MapId,
    OaksErrandPhase,
    OaksErrandState,
    OpeningControlState,
    OpeningPhase,
    RawGameState,
    RedPokedexState,
)
from pokemon_red_completion.opening import OpeningChapterReport
from pokemon_red_completion.planner_trajectory import SemanticObjectiveDecisionObserver
from pokemon_red_completion.play import (
    DEFAULT_QUALIFIED_PLAY_TIMING,
    LAB_EXIT_DIRECTIONS,
    LAB_RIVAL_TRIGGER_DIRECTIONS,
    PALLET_TO_ROUTE_1_DIRECTIONS,
    QUALIFIED_OBJECTIVE_COMPLETION_CHECKPOINTS,
    QUALIFIED_OBJECTIVE_SEQUENCE,
    QUALIFIED_PLAY_CHECKPOINT_COUNT,
    ROUTE_1_TO_VIRIDIAN_DIRECTIONS,
    VIRIDIAN_TO_MART_DIRECTIONS,
    QualifiedPlayError,
    QualifiedPlayProgress,
    QualifiedPlayReport,
    QualifiedPlayTiming,
    Route1WildFleeEvidence,
    _move_route_1_with_wild_flees,
    _objective_model_progress_bridge,
    _qualified_play_chapter_error,
    _trajectory_progress_bridge,
    is_parcel_verified,
    is_pokedex_verified,
    is_rival_resolution_verified,
    is_rival_victory_verified,
    run_qualified_play,
)
from pokemon_red_completion.rom import RomFingerprint
from pokemon_red_completion.route import COMPLETION_QUEST
from pokemon_red_completion.route_1_wild import move_with_wild_flees
from pokemon_red_completion.saffron import FRESH_WATER_PRICE, THUNDER_STONE_PRICE
from pokemon_red_completion.strategic_navigation_protocol import (
    STRATEGIC_NAVIGATION_REGISTRY_RELATIVE_PATH,
    parse_strategic_navigation_registry,
)
from pokemon_red_completion.trajectory import (
    InMemoryTrajectorySink,
    RecordingExecutor,
    SemanticSnapshot,
)


def _raw(
    map_id: MapId,
    x: int,
    y: int,
    *,
    party_count: int = 1,
    party_species_ids: tuple[int, ...] = (SQUIRTLE_SPECIES_ID,),
) -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=int(map_id),
        player_x=x,
        player_y=y,
        party_count=party_count,
        battle_state=0,
        badge_bits=0,
        bag_item_ids=(),
        event_flags=b"",
        party_species_ids=party_species_ids,
        first_party_level=6 if party_count else None,
        first_party_hp=21 if party_count else None,
        first_party_max_hp=21 if party_count else None,
        battle_result=0,
    )


def _opening_control(
    phase: OpeningPhase,
    *,
    starter_obtained: bool = False,
    first_party_species: int | None = None,
) -> OpeningControlState:
    return OpeningControlState(
        phase=phase,
        confirm_allowed=True,
        cancel_allowed=True,
        movement_allowed=True,
        followed_oak_into_lab=True,
        asked_to_choose=True,
        starter_obtained=starter_obtained,
        first_party_species=first_party_species,
    )


def _rival_victory() -> OaksErrandState:
    return OaksErrandState(
        phase=OaksErrandPhase.RIVAL_DEFEATED,
        joy_ignore=0,
        lab_script=18,
        mart_script=0,
        battled_rival=True,
        got_oaks_parcel=False,
        oak_got_parcel=False,
        got_pokedex=False,
        parcel_in_bag=False,
        first_party_species=SQUIRTLE_SPECIES_ID,
        first_party_level=6,
        first_party_hp=21,
        first_party_max_hp=21,
        battle_result=0,
        map_id=MapId.OAKS_LAB,
        battle_state=0,
    )


def _rival_loss() -> OaksErrandState:
    return replace(
        _rival_victory(),
        first_party_level=5,
        first_party_hp=19,
        first_party_max_hp=19,
        battle_result=1,
    )


def _parcel_obtained() -> OaksErrandState:
    return OaksErrandState(
        phase=OaksErrandPhase.PARCEL_OBTAINED,
        joy_ignore=0,
        lab_script=0,
        mart_script=2,
        battled_rival=True,
        got_oaks_parcel=True,
        oak_got_parcel=False,
        got_pokedex=False,
        parcel_in_bag=True,
        first_party_species=SQUIRTLE_SPECIES_ID,
        first_party_level=6,
        first_party_hp=21,
        first_party_max_hp=21,
        battle_result=0,
        map_id=MapId.VIRIDIAN_MART,
        battle_state=0,
    )


def _pokedex_obtained() -> OaksErrandState:
    return OaksErrandState(
        phase=OaksErrandPhase.POKEDEX_OBTAINED,
        joy_ignore=0,
        lab_script=18,
        mart_script=2,
        battled_rival=True,
        got_oaks_parcel=True,
        oak_got_parcel=True,
        got_pokedex=True,
        parcel_in_bag=False,
        first_party_species=SQUIRTLE_SPECIES_ID,
        first_party_level=6,
        first_party_hp=21,
        first_party_max_hp=21,
        # A successful Route 1 escape legitimately overwrites the earlier
        # rival-battle result. The final gate must rely on the captured rival
        # checkpoint rather than reinterpret this byte.
        battle_result=2,
        map_id=MapId.OAKS_LAB,
        battle_state=0,
    )


class _PewterEvidence:
    passed = True

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        return (
            ("lab_exited", "Exited Oak's Lab after the Pokédex", _raw(MapId.PALLET_TOWN, 12, 12)),
            (
                "viridian_northbound",
                "Reached Viridian City northbound",
                _raw(MapId.VIRIDIAN_CITY, 21, 35),
            ),
            ("route_2_reached", "Reached Route 2", _raw(MapId.ROUTE_2, 8, 71)),
            (
                "forest_gate_reached",
                "Reached Viridian Forest gate",
                _raw(MapId.VIRIDIAN_FOREST_SOUTH_GATE, 4, 7),
            ),
            (
                "forest_entered",
                "Entered Viridian Forest",
                _raw(MapId.VIRIDIAN_FOREST, 17, 47),
            ),
            (
                "forest_cleared",
                "Cleared Viridian Forest",
                _raw(MapId.VIRIDIAN_FOREST_NORTH_GATE, 4, 7),
            ),
            ("pewter_reached", "Reached Pewter City", _raw(MapId.PEWTER_CITY, 18, 35)),
            (
                "pewter_gym_entered",
                "Entered Pewter Gym battle-ready",
                _raw(MapId.PEWTER_GYM, 4, 13),
            ),
            ("brock_battle", "Verified the live Brock battle", _raw(MapId.PEWTER_GYM, 4, 2)),
            (
                "brock_defeated",
                "Defeated Brock and received TM34",
                _raw(MapId.PEWTER_GYM, 4, 2),
            ),
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "route": {
                "ordered_boundaries_verified": 9,
                "ordered_boundaries_total": 9,
                "brock_battle_observed": True,
            },
            "brock": {
                "victory_verified": True,
                "boulder_badge_verified": True,
                "tm34_verified": True,
                "overworld_control_verified": True,
                "squirtle_level": 12,
                "squirtle_hp": 27,
                "squirtle_max_hp": 33,
                "squirtle_status": 0,
                "bubble_pp": 23,
            },
        }


class _CeruleanEvidence:
    passed = True
    cerulean_reached = _raw(MapId.CERULEAN_CITY, 0, 18)

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        return (
            ("route_3_reached", "Reached Route 3 from Pewter", _raw(MapId.ROUTE_3, 1, 6)),
            (
                "route_3_trainer_0",
                "Verified required Route 3 trainer 0",
                _raw(MapId.ROUTE_3, 10, 6),
            ),
            (
                "route_3_trainer_1",
                "Verified required Route 3 trainer 1",
                _raw(MapId.ROUTE_3, 13, 11),
            ),
            (
                "route_3_trainer_3",
                "Verified required Route 3 trainer 3",
                _raw(MapId.ROUTE_3, 22, 4),
            ),
            (
                "route_3_trainer_6",
                "Verified required Route 3 trainer 6",
                _raw(MapId.ROUTE_3, 47, 9),
            ),
            (
                "route_4_reached",
                "Cleared the required Route 3 trainers",
                _raw(MapId.ROUTE_4, 0, 6),
            ),
            ("mt_moon_entered", "Entered Mt. Moon", _raw(MapId.MT_MOON_1F, 5, 31)),
            (
                "mt_moon_b1f",
                "Reached the connected Mt. Moon B1F route",
                _raw(MapId.MT_MOON_B1F, 5, 5),
            ),
            (
                "mt_moon_b2f",
                "Reached the fossil-side Mt. Moon B2F route",
                _raw(MapId.MT_MOON_B2F, 21, 17),
            ),
            (
                "required_rocket",
                "Verified the unavoidable Team Rocket battle",
                _raw(MapId.MT_MOON_B2F, 11, 19),
            ),
            (
                "super_nerd",
                "Verified the fossil-guarding Super Nerd battle",
                _raw(MapId.MT_MOON_B2F, 13, 8),
            ),
            (
                "helix_fossil",
                "Obtained the Helix Fossil",
                _raw(MapId.MT_MOON_B2F, 13, 7),
            ),
            (
                "mt_moon_b1f_ascent",
                "Reached the legal Mt. Moon exit ladder",
                _raw(MapId.MT_MOON_B1F, 23, 3),
            ),
            (
                "mt_moon_exited",
                "Exited Mt. Moon onto Route 4",
                _raw(MapId.ROUTE_4, 24, 6),
            ),
            ("cerulean_reached", "Reached Cerulean City", self.cerulean_reached),
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok",
            "route": {
                "ordered_boundaries_verified": 8,
                "ordered_boundaries_total": 8,
                "required_route_3_trainers": [0, 1, 3, 6],
            },
            "mt_moon": {
                "required_rocket_battle_observed": True,
                "super_nerd_battle_observed": True,
                "helix_fossil_verified": True,
            },
            "cerulean": {
                "arrival_verified": True,
                "wartortle_level": 17,
                "wartortle_hp": 26,
                "wartortle_max_hp": 49,
                "wartortle_status": 0,
            },
        }


class _CascadeEvidence:
    passed = True
    final_raw = _raw(MapId.CERULEAN_GYM, 5, 2)

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        checkpoint_ids = (
            "cerulean_rival_battle",
            "cerulean_rival_defeated",
            "route_24_trainer_5",
            "route_24_trainer_4",
            "route_24_trainer_3",
            "route_24_trainer_2",
            "route_24_trainer_1",
            "nugget_rocket_battle",
            "nugget_rocket_defeated",
            "route_25_trainer_8",
            "route_25_trainer_3",
            "route_25_trainer_2",
            "route_25_trainer_5",
            "bill_requested_help",
            "bill_cell_separator_used",
            "bill_restored",
            "ss_ticket_obtained",
            "bills_house_left",
            "cerulean_gym_trainer_battle",
            "cerulean_gym_trainer_defeated",
            "misty_battle",
            "misty_defeated",
        )
        return tuple(
            (checkpoint_id, checkpoint_id.replace("_", " ").title(), self.final_raw)
            for checkpoint_id in checkpoint_ids
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok",
            "route": {
                "route_24_trainers": [5, 4, 3, 2, 1],
                "route_25_trainers": [8, 3, 2, 5],
            },
            "cascade": {
                "victory_verified": True,
                "badge_verified": True,
                "tm11_verified": True,
                "ss_ticket_verified": True,
            },
        }


class _VermilionEvidence:
    passed = True
    final_raw = _raw(MapId.VERMILION_CITY, 19, 0)

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        checkpoint_ids = (
            "misty_ready",
            "trashed_house_entered",
            "robbery_rear_exit",
            "rocket_thief_battle",
            "tm28_obtained",
            "route_5_reached",
            "underground_north_entrance",
            "underground_tunnel",
            "underground_south_entrance",
            "route_6_reached",
            "route_6_trainer_f_battle",
            "route_6_trainer_f_defeated",
            "route_6_trainer_m_battle",
            "route_6_trainer_m_defeated",
            "vermilion_reached",
        )
        return tuple(
            (checkpoint_id, checkpoint_id.replace("_", " ").title(), self.final_raw)
            for checkpoint_id in checkpoint_ids
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok",
            "route": {
                "rocket_battle_observed": True,
                "tm28_verified": True,
                "route_6_trainer_events": [False, False, False, True, True, False],
                "vermilion_map_id": MapId.VERMILION_CITY,
                "vermilion_x": 19,
                "vermilion_y": 0,
            },
        }


class _SSAnneEvidence:
    passed = True
    final_raw = _raw(MapId.SS_ANNE_CAPTAINS_ROOM, 4, 3)

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        checkpoint_ids = (
            "vermilion_ready",
            "healed",
            "dock_reached",
            "ship_1f_reached",
            "ship_2f_reached",
            "rival_battle",
            "rival_defeated",
            "captain_room_reached",
            "hm01_obtained",
        )
        return tuple(
            (checkpoint_id, checkpoint_id.replace("_", " ").title(), self.final_raw)
            for checkpoint_id in checkpoint_ids
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok",
            "objective": "obtain_cut",
            "rival_battle_observed": True,
            "captain": {
                "rubbed_back": True,
                "got_hm01_event": True,
                "hm01_in_bag": True,
                "cut_fact": True,
            },
        }


class _SurgeEvidence:
    passed = True
    final_raw = replace(
        _raw(MapId.VERMILION_GYM, 5, 2),
        badge_bits=int(Badge.BOULDER | Badge.CASCADE | Badge.THUNDER),
    )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        checkpoint_ids = (
            "hm01_ready",
            "healed",
            "balls_purchased",
            "spearow_encounter",
            "spearow_captured",
            "diglett_captured",
            "dux_traded",
            "cut_taught",
            "diglett_dig_ready",
            "gym_reached",
            "first_switch",
            "second_switch",
            "surge_battle",
            "surge_defeated",
            "surge_reward_stable",
        )
        return tuple(
            (checkpoint_id, checkpoint_id.replace("_", " ").title(), self.final_raw)
            for checkpoint_id in checkpoint_ids
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok",
            "objective": "defeat_surge",
            "battle": {"dig_attacks": 3, "wrong_move_count": 0},
            "reward": {
                "beat_lt_surge": True,
                "got_tm24": True,
                "tm24_in_bag": True,
                "thunder_badge": True,
                "thunder_badge_mirror": True,
            },
        }


class _LavenderEvidence:
    passed = True
    final_raw = replace(
        _raw(MapId.LAVENDER_POKECENTER, 3, 3, party_count=3, party_species_ids=(0xB3, 0x40, 0x3B)),
        badge_bits=int(Badge.BOULDER | Badge.CASCADE | Badge.THUNDER),
    )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        checkpoint_ids = (
            "surge_ready",
            "gym_exited",
            "second_cut",
            "healed",
            "bubblebeam",
            "supplies",
            "reverse_underground",
            "cerulean_cut",
            "route9_cut",
            "route9_trainers",
            "rock_center",
            "tunnel_entered",
            "rock_tunnel_cleared",
            "lavender_reached",
            "lavender_stable",
        )
        return tuple(
            (checkpoint_id, checkpoint_id.replace("_", " ").title(), self.final_raw)
            for checkpoint_id in checkpoint_ids
        )

    def public_dict(self) -> dict[str, object]:
        return {"status": "ok", "objective": "reach_lavender"}


class _CeladonEvidence:
    passed = True
    final_raw = replace(
        _raw(MapId.CELADON_POKECENTER, 3, 3, party_count=3, party_species_ids=(0xB3, 0x40, 0x3B)),
        badge_bits=int(Badge.BOULDER | Badge.CASCADE | Badge.THUNDER),
    )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        checkpoint_ids = (
            "lavender_ready",
            "lavender_exited",
            "route8_reached",
            "route8_trainer8_battle",
            "route8_trainer8_defeated",
            "route8_entrance",
            "route8_gate",
            "west_east_tunnel",
            "west_east_tunnel_crossed",
            "route7_reached",
            "celadon_reached",
            "celadon_stable",
        )
        return tuple(
            (checkpoint_id, checkpoint_id.replace("_", " ").title(), self.final_raw)
            for checkpoint_id in checkpoint_ids
        )

    def public_dict(self) -> dict[str, object]:
        return {"status": "ok", "objective": "reach_celadon"}


class _HideoutEvidence:
    passed = True
    final_raw = _CeladonEvidence.final_raw

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        checkpoint_ids = (
            "celadon_ready",
            "game_corner",
            "guard_defeated",
            "poster_switch",
            "b3_reached",
            "b4_key_wing",
            "lift_key",
            "recovered",
            "elevator",
            "b4_boss_wing",
            "guard_2",
            "boss_door",
            "giovanni",
            "silph_scope",
            "dig_return",
            "scope_stable",
            "hideout_cleared",
            "scope_ready",
            "resources_verified",
        )
        return tuple(
            (checkpoint_id, checkpoint_id.replace("_", " ").title(), self.final_raw)
            for checkpoint_id in checkpoint_ids
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok",
            "objectives": ["clear_rocket_hideout", "obtain_silph_scope"],
        }


class _TowerEvidence:
    passed = True
    final_raw = replace(
        _raw(
            MapId.LAVENDER_POKECENTER,
            3,
            3,
            party_count=3,
            party_species_ids=(0x1C, 0x40, 0x3B),
        ),
        badge_bits=int(Badge.BOULDER | Badge.CASCADE | Badge.THUNDER),
    )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        checkpoint_ids = (
            "scope_ready",
            "tower_2f",
            "rival",
            "tower_3f",
            "tower_4f",
            "purified_1",
            "purified_2",
            "purified_3",
            "channelers",
            "x_accuracy",
            "rare_candy",
            "marowak",
            "rocket_19",
            "rocket_20",
            "rocket_21",
            "fuji_rescued",
            "poke_flute",
            "tower_cleared",
            "fuji_verified",
            "flute_verified",
            "resources_verified",
            "objective_ready",
            "semantic_gate",
            "party_verified",
            "controller_verified",
            "lavender_stable",
            "chapter_complete",
        )
        return tuple(
            (checkpoint_id, checkpoint_id.replace("_", " ").title(), self.final_raw)
            for checkpoint_id in checkpoint_ids
        )

    def public_dict(self) -> dict[str, object]:
        return {"status": "ok", "objective": "rescue_fuji"}


class _FuchsiaEvidence:
    passed = True
    final_raw = replace(
        _raw(
            MapId.FUCHSIA_POKECENTER,
            3,
            3,
            party_count=3,
            party_species_ids=(0x1C, 0x40, 0x3B),
        ),
        badge_bits=int(Badge.BOULDER | Badge.CASCADE | Badge.THUNDER),
    )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        checkpoint_ids = (
            "fuji_ready",
            "route12",
            "fisher",
            "snorlax",
            "recovered",
            "rocker",
            "route13_pair",
            "route13_clear",
            "route14_clear",
            "route15_clear",
            "fuchsia",
            "healed",
            "optionals",
            "fuchsia_stable",
        )
        return tuple(
            (checkpoint_id, checkpoint_id.replace("_", " ").title(), self.final_raw)
            for checkpoint_id in checkpoint_ids
        )

    def public_dict(self) -> dict[str, object]:
        return {"status": "ok", "objective": "reach_fuchsia"}


class _SafariEvidence:
    passed = True
    final_raw = _FuchsiaEvidence.final_raw

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        checkpoint_ids = (
            "surf_ready",
            "gate",
            "admitted",
            "east",
            "north",
            "west",
            "teeth_stance",
            "teeth",
            "hm03",
            "surf",
            "cleanup",
            "stable",
        )
        return tuple(
            (checkpoint_id, checkpoint_id.replace("_", " ").title(), self.final_raw)
            for checkpoint_id in checkpoint_ids
        )

    def public_dict(self) -> dict[str, object]:
        return {"status": "ok", "objective": "obtain_surf"}


class _KogaEvidence:
    passed = True
    final_raw = replace(
        _SafariEvidence.final_raw,
        badge_bits=int(Badge.BOULDER | Badge.CASCADE | Badge.THUNDER | Badge.SOUL),
    )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        checkpoint_ids = (
            "koga_ready",
            "gym_entry",
            "juggler3",
            "tamer2",
            "recovery1",
            "juggler4",
            "recovery2",
            "koga_stance",
            "koga_defeated",
            "rewards",
            "koga_stable",
        )
        return tuple(
            (checkpoint_id, checkpoint_id.replace("_", " ").title(), self.final_raw)
            for checkpoint_id in checkpoint_ids
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "status": "ok",
            "objective": "defeat_koga",
            "geographic_dependency": {
                "reason": "post-Surf Fuchsia cannot legally return to Celadon before Soul Badge",
            },
        }


class _StrengthEvidence:
    passed = True
    final_raw = _KogaEvidence.final_raw

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        checkpoint_ids = (
            "strength_ready",
            "warden_house",
            "warden_stance",
            "teeth_given",
            "hm04",
            "strength",
            "center_return",
            "strength_stable",
        )
        return tuple(
            (checkpoint_id, checkpoint_id.replace("_", " ").title(), self.final_raw)
            for checkpoint_id in checkpoint_ids
        )

    def public_dict(self) -> dict[str, object]:
        return {"status": "ok", "objective": "obtain_strength"}


class _ErikaEvidence:
    passed = True
    final_raw = replace(
        _StrengthEvidence.final_raw,
        badge_bits=int(Badge.BOULDER | Badge.CASCADE | Badge.THUNDER | Badge.RAINBOW | Badge.SOUL),
    )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        checkpoint_ids = (
            "erika_ready",
            "celadon_arrived",
            "celadon_ready",
            "gym_entered",
            "lass_defeated",
            "cooltrainer_defeated",
            "gym_recovered",
            "erika_stance",
            "erika_battle",
            "erika_defeated",
            "rainbow_received",
            "erika_stable",
        )
        return tuple(
            (checkpoint_id, checkpoint_id.replace("_", " ").title(), self.final_raw)
            for checkpoint_id in checkpoint_ids
        )

    def public_dict(self) -> dict[str, object]:
        return {"status": "ok", "objective": "defeat_erika"}


class _SaffronEvidence:
    passed = True
    final_raw = replace(_ErikaEvidence.final_raw, map_id=MapId.SAFFRON_POKECENTER)

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        checkpoint_ids = (
            "saffron_ready",
            "roof_reached",
            "water_bought",
            "gate_reached",
            "drink_consumed",
            "guards_bribed",
            "saffron_entered",
            "saffron_stable",
        )
        return tuple(
            (checkpoint_id, checkpoint_id.replace("_", " ").title(), self.final_raw)
            for checkpoint_id in checkpoint_ids
        )

    def public_dict(self) -> dict[str, object]:
        return {"status": "ok", "objective": "reach_saffron"}


class _SilphEvidence:
    passed = True
    final_raw = _SaffronEvidence.final_raw

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        checkpoint_ids = (
            "silph_ready",
            "silph_supplied",
            "card_key",
            "third_floor_door",
            "rival_ready",
            "silph_rival",
            "eleventh_ready",
            "eleventh_rocket",
            "eleventh_door",
            "silph_liberated",
            "master_ball",
            "silph_terminal",
        )
        return tuple(
            (checkpoint_id, checkpoint_id.replace("_", " ").title(), self.final_raw)
            for checkpoint_id in checkpoint_ids
        )

    def public_dict(self) -> dict[str, object]:
        return {"status": "ok", "objective": "liberate_silph"}


class _DojoEvidence:
    passed = True
    final_raw = replace(
        _SilphEvidence.final_raw,
        party_count=6,
        party_species_ids=(0x1C, 0x40, 0x76, 0x84, 0x68, 0x2B),
    )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        checkpoint_ids = (
            "dojo_ready",
            "dojo_entered",
            "dojo_trainer_1",
            "dojo_trainer_2",
            "dojo_trainer_3",
            "dojo_trainer_4",
            "karate_master",
            "hitmonlee_received",
            "dojo_terminal",
        )
        return tuple(
            (checkpoint_id, checkpoint_id.replace("_", " ").title(), self.final_raw)
            for checkpoint_id in checkpoint_ids
        )

    def public_dict(self) -> dict[str, object]:
        return {"status": "ok", "objective": "recruit_hitmonlee"}


class _SabrinaEvidence:
    passed = True
    final_raw = replace(_DojoEvidence.final_raw, badge_bits=0x3F)

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        checkpoint_ids = (
            "sabrina_ready",
            "leader_reached",
            "sabrina_defeated",
            "marsh_badge",
            "gym_exited",
            "sabrina_terminal",
        )
        return tuple(
            (checkpoint_id, checkpoint_id.replace("_", " ").title(), self.final_raw)
            for checkpoint_id in checkpoint_ids
        )

    def public_dict(self) -> dict[str, object]:
        return {"status": "ok", "objective": "defeat_sabrina"}


class _CinnabarEvidence:
    passed = True
    final_raw = replace(
        _SabrinaEvidence.final_raw,
        map_id=MapId.CINNABAR_POKECENTER,
        player_x=3,
        player_y=3,
    )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        checkpoint_ids = (
            "cinnabar_ready",
            "fly_house_reached",
            "fly_taught",
            "pallet_reached",
            "cinnabar_reached",
            "cinnabar_terminal",
        )
        return tuple(
            (checkpoint_id, checkpoint_id.replace("_", " ").title(), self.final_raw)
            for checkpoint_id in checkpoint_ids
        )

    def public_dict(self) -> dict[str, object]:
        return {"status": "ok", "objective": "reach_cinnabar"}


class _BlaineEvidence:
    passed = True
    final_raw = replace(_CinnabarEvidence.final_raw, badge_bits=0x7F)

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        checkpoint_ids = (
            "blaine_ready",
            "mansion_entered",
            "secret_key_obtained",
            "mansion_returned",
            "gym_quizzes_cleared",
            "blaine_defeated",
            "tm38_received",
            "blaine_terminal",
        )
        return tuple(
            (checkpoint_id, checkpoint_id.replace("_", " ").title(), self.final_raw)
            for checkpoint_id in checkpoint_ids
        )

    def public_dict(self) -> dict[str, object]:
        return {"status": "ok", "objectives": ["obtain_secret_key", "defeat_blaine"]}


class _GiovanniEvidence:
    passed = True
    final_raw = replace(
        _BlaineEvidence.final_raw,
        map_id=MapId.VIRIDIAN_POKECENTER,
        badge_bits=0xFF,
    )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        checkpoint_ids = (
            "giovanni_ready",
            "viridian_arrived",
            "tm_slot_freed",
            "viridian_gym_entered",
            "viridian_trainers_cleared",
            "giovanni_recovered",
            "giovanni_defeated",
            "giovanni_terminal",
        )
        return tuple(
            (checkpoint_id, checkpoint_id.replace("_", " ").title(), self.final_raw)
            for checkpoint_id in checkpoint_ids
        )

    def public_dict(self) -> dict[str, object]:
        return {"status": "ok", "objectives": ["defeat_giovanni"]}


class _VictoryRoadEvidence:
    passed = True
    final_raw = replace(
        _GiovanniEvidence.final_raw,
        map_id=MapId.INDIGO_PLATEAU_LOBBY,
        player_x=2,
        player_y=5,
    )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        checkpoint_ids = (
            "victory_road_ready",
            "route22_rival",
            "victory_supplied",
            "badge_corridor",
            "vr1_switch",
            "vr2_switch",
            "vr3_hole",
            "vr2_final",
            "indigo_ready",
        )
        return tuple(
            (checkpoint_id, checkpoint_id.replace("_", " ").title(), self.final_raw)
            for checkpoint_id in checkpoint_ids
        )

    def public_dict(self) -> dict[str, object]:
        return {"status": "ok", "objective": "cross_victory_road"}


class _LoreleiEvidence:
    passed = True
    final_raw = replace(
        _VictoryRoadEvidence.final_raw,
        map_id=MapId.BRUNOS_ROOM,
        player_x=4,
        player_y=5,
    )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        checkpoint_ids = ("lorelei_ready", "lorelei_entered", "lorelei_defeated")
        return tuple(
            (checkpoint_id, checkpoint_id.replace("_", " ").title(), self.final_raw)
            for checkpoint_id in checkpoint_ids
        )

    def public_dict(self) -> dict[str, object]:
        return {"status": "ok", "objective": "defeat_lorelei"}


class _BrunoEvidence:
    passed = True
    final_raw = replace(
        _LoreleiEvidence.final_raw,
        map_id=MapId.AGATHAS_ROOM,
        player_x=4,
        player_y=5,
    )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        checkpoint_ids = ("bruno_ready", "bruno_engaged", "bruno_defeated")
        return tuple(
            (checkpoint_id, checkpoint_id.replace("_", " ").title(), self.final_raw)
            for checkpoint_id in checkpoint_ids
        )

    def public_dict(self) -> dict[str, object]:
        return {"status": "ok", "objective": "defeat_bruno"}


class _AgathaEvidence:
    passed = True
    final_raw = replace(
        _BrunoEvidence.final_raw,
        map_id=MapId.LANCES_ROOM,
        player_x=4,
        player_y=5,
    )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        checkpoint_ids = ("agatha_ready", "agatha_engaged", "agatha_defeated")
        return tuple(
            (checkpoint_id, checkpoint_id.replace("_", " ").title(), self.final_raw)
            for checkpoint_id in checkpoint_ids
        )

    def public_dict(self) -> dict[str, object]:
        return {"status": "ok", "objective": "defeat_agatha"}


class _LanceEvidence:
    passed = True
    final_raw = replace(
        _AgathaEvidence.final_raw,
        map_id=MapId.CHAMPIONS_ROOM,
        player_x=4,
        player_y=5,
    )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        checkpoint_ids = ("lance_ready", "lance_engaged", "lance_defeated")
        return tuple(
            (checkpoint_id, checkpoint_id.replace("_", " ").title(), self.final_raw)
            for checkpoint_id in checkpoint_ids
        )

    def public_dict(self) -> dict[str, object]:
        return {"status": "ok", "objective": "defeat_lance"}


class _ChampionEvidence:
    passed = True
    final_raw = replace(
        _LanceEvidence.final_raw,
        map_id=MapId.HALL_OF_FAME,
        player_x=4,
        player_y=7,
    )

    def checkpoints(self) -> tuple[tuple[str, str, RawGameState], ...]:
        checkpoint_ids = ("champion_ready", "champion_engaged", "hall_of_fame")
        return tuple(
            (checkpoint_id, checkpoint_id.replace("_", " ").title(), self.final_raw)
            for checkpoint_id in checkpoint_ids
        )

    def public_dict(self) -> dict[str, object]:
        return {"status": "ok", "objective": "enter_hall_of_fame"}


def test_qualified_play_direction_sequences_are_source_stable() -> None:
    assert LAB_RIVAL_TRIGGER_DIRECTIONS == (
        "down",
        "left",
        "left",
        "left",
        "down",
    )
    assert LAB_EXIT_DIRECTIONS == ("down",) * 6
    assert (
        *(("left",) * 3),
        *(("up",) * 10),
        "right",
        *(("up",) * 3),
    ) == PALLET_TO_ROUTE_1_DIRECTIONS
    assert (
        *(("up",) * 7),
        *(("left",) * 2),
        *(("up",) * 4),
        *(("right",) * 4),
        *(("up",) * 4),
        *(("left",) * 3),
        *(("up",) * 6),
        *(("right",) * 5),
        *(("up",) * 12),
        *(("left",) * 3),
        *(("up",) * 3),
    ) == ROUTE_1_TO_VIRIDIAN_DIRECTIONS
    assert (
        *(("up",) * 5),
        "left",
        *(("up",) * 2),
        "left",
        *(("up",) * 8),
        *(("right",) * 10),
        "up",
    ) == VIRIDIAN_TO_MART_DIRECTIONS


def test_qualified_play_timing_defaults_are_positive_bounded_integers() -> None:
    assert QualifiedPlayTiming() == QualifiedPlayTiming(
        transition_wait_frames=120,
        rival_trigger_wait_frames=360,
        battle_wait_frames=180,
        dialogue_wait_frames=240,
        route_1_north_seed_wait_frames=192,
        mart_prompt_wait_frames=240,
        route_1_south_seed_wait_frames=48,
        max_route_1_wild_flees=8,
        route_1_wild_exit_stabilization_frames=120,
        max_route_1_step_attempts=8,
        route_1_step_retry_wait_frames=24,
        max_rival_pulses=96,
        max_parcel_pulses=5,
        max_pokedex_pulses=42,
    )
    assert QualifiedPlayTiming() == DEFAULT_QUALIFIED_PLAY_TIMING
    assert fields(QualifiedPlayTiming)
    assert all(
        isinstance(getattr(DEFAULT_QUALIFIED_PLAY_TIMING, field.name), int)
        and not isinstance(getattr(DEFAULT_QUALIFIED_PLAY_TIMING, field.name), bool)
        and getattr(DEFAULT_QUALIFIED_PLAY_TIMING, field.name) > 0
        for field in fields(QualifiedPlayTiming)
    )


@pytest.mark.parametrize("invalid", (0, -1, True, 1.5))
def test_qualified_play_timing_rejects_unbounded_values(invalid: object) -> None:
    for field in fields(QualifiedPlayTiming):
        with pytest.raises(ValueError, match=f"{field.name} must be a positive integer"):
            replace(
                DEFAULT_QUALIFIED_PLAY_TIMING,
                **{field.name: invalid},
            )


def test_qualified_play_progress_is_sanitized_and_immutable() -> None:
    assert QUALIFIED_PLAY_CHECKPOINT_COUNT == 312
    progress = QualifiedPlayProgress(
        checkpoint_id="cerulean_reached",
        label="Reached Cerulean City",
        completed=312,
        total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
        frames_executed=252_989,
    )

    assert progress.completed == progress.total == 312
    assert progress.frames_executed == 252_989
    with pytest.raises(FrozenInstanceError):
        progress.completed = 10  # type: ignore[misc]


def test_qualified_play_chapter_error_carries_sanitized_policy_evidence() -> None:
    error = _qualified_play_chapter_error(RuntimeError("chapter failed"), None)

    assert isinstance(error, QualifiedPlayError)
    assert str(error) == "chapter failed"
    assert error.evidence == {
        "schema": "pokemon-red-qualified-play-failure-evidence-v1",
        "exception_type": "RuntimeError",
        "battle_policy": None,
    }


def test_repeated_training_progress_uses_the_execution_step_in_event_identity() -> None:
    class Recorder:
        next_step_index = 10

    recorder = Recorder()
    sink = InMemoryTrajectorySink()
    emit = _trajectory_progress_bridge(None, sink, "training-episode", recorder, [0])  # type: ignore[arg-type]
    progress = QualifiedPlayProgress(
        checkpoint_id="mansion_team_training_progress",
        label="Balanced team training: 250 battles",
        completed=250,
        total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
        frames_executed=10_000,
    )

    emit(progress)
    recorder.next_step_index = 20
    emit(progress)

    assert [event.event_id for event in sink.events] == [
        "training-episode:checkpoint:10:250:mansion_team_training_progress",
        "training-episode:checkpoint:20:250:mansion_team_training_progress",
    ]


def test_qualified_progress_emits_one_legal_label_for_every_completion_objective() -> None:
    class SnapshotProvider:
        def snapshot(self) -> SemanticSnapshot:
            return SemanticSnapshot(game_id="pokemon.test", mode="interactive")

    class Executor:
        def execute(self, action: object) -> object:
            return action

    sink = InMemoryTrajectorySink()
    provider = SnapshotProvider()
    recorder: RecordingExecutor[object, object] = RecordingExecutor(
        delegate=Executor(),
        snapshot_provider=provider,
        sink=sink,
        episode_id="planner-episode",
    )
    observer = SemanticObjectiveDecisionObserver(
        graph=COMPLETION_QUEST,
        snapshot_provider=provider,
        recorder=recorder,
        policy_id="teacher-v1",
    )
    observer.select(QUALIFIED_OBJECTIVE_SEQUENCE[0])
    emit = _trajectory_progress_bridge(
        None,
        sink,
        "planner-episode",
        recorder,  # type: ignore[arg-type]
        [0],
        observer,
    )

    for completed, _ in dict(QUALIFIED_OBJECTIVE_COMPLETION_CHECKPOINTS).items():
        emit(
            QualifiedPlayProgress(
                checkpoint_id=f"checkpoint_{completed}",
                label=f"Checkpoint {completed}",
                completed=completed,
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=completed,
            )
        )

    planner_decisions = [
        decision for decision in sink.decisions if decision.decision_type == "objective_selection"
    ]
    assert (
        tuple(
            decision.action["objective_id"]  # type: ignore[index]
            for decision in planner_decisions
        )
        == QUALIFIED_OBJECTIVE_SEQUENCE
    )
    assert observer.completed_ids == frozenset(QUALIFIED_OBJECTIVE_SEQUENCE)
    assert observer.active_objective_id is None
    assert recorder.recording_failures == 0


def test_objective_model_progress_scores_every_fixed_boundary_without_answer_labels() -> None:
    class Policy:
        def __init__(self) -> None:
            self.completed: list[str] = []
            self.dispatched: list[str] = []

        @property
        def completed_objective_count(self) -> int:
            return len(self.completed)

        def complete(self, objective_id: str) -> None:
            self.completed.append(objective_id)

        def dispatch_fixed(self, objective_id: str) -> str:
            self.dispatched.append(objective_id)
            return objective_id

    policy = Policy()
    policy.dispatch_fixed(QUALIFIED_OBJECTIVE_SEQUENCE[0])
    emit = _objective_model_progress_bridge(None, policy)  # type: ignore[arg-type]
    for completed, _ in dict(QUALIFIED_OBJECTIVE_COMPLETION_CHECKPOINTS).items():
        emit(
            QualifiedPlayProgress(
                checkpoint_id=f"checkpoint_{completed}",
                label=f"Checkpoint {completed}",
                completed=completed,
                total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
                frames_executed=completed,
            )
        )

    assert tuple(policy.dispatched) == QUALIFIED_OBJECTIVE_SEQUENCE
    assert tuple(policy.completed) == QUALIFIED_OBJECTIVE_SEQUENCE


def test_qualified_play_report_is_complete_honest_and_privacy_safe() -> None:
    rom = RomFingerprint(
        filename="/private/home/Pokemon Red.gb",
        title="POKEMON RED",
        size_bytes=1_048_576,
        sha1="1" * 40,
        sha256="2" * 64,
    )
    opening = OpeningChapterReport(
        rom=rom,
        pyboy_version="2.7.0",
        emulator_window="SDL2",
        emulator_speed=4,
        clean_power_on=True,
        bedroom_recovery_pulses=0,
        bedroom=_raw(
            MapId.REDS_HOUSE_2F,
            3,
            6,
            party_count=0,
            party_species_ids=(),
        ),
        downstairs=_raw(
            MapId.REDS_HOUSE_1F,
            7,
            1,
            party_count=0,
            party_species_ids=(),
        ),
        outside=_raw(
            MapId.PALLET_TOWN,
            5,
            6,
            party_count=0,
            party_species_ids=(),
        ),
        oak_triggered=_raw(
            MapId.PALLET_TOWN,
            10,
            1,
            party_count=0,
            party_species_ids=(),
        ),
        selection_ready=_raw(
            MapId.OAKS_LAB,
            5,
            3,
            party_count=0,
            party_species_ids=(),
        ),
        starter=_raw(MapId.OAKS_LAB, 7, 4),
        selection_control=_opening_control(OpeningPhase.STARTER_SELECTION_READY),
        starter_control=_opening_control(
            OpeningPhase.STARTER_OBTAINED,
            starter_obtained=True,
            first_party_species=SQUIRTLE_SPECIES_ID,
        ),
        facts=frozenset(
            {
                "system:clean_power_on",
                "story:adventure_begun",
                "party:starter_obtained",
            }
        ),
        verified_objectives=("power_on", "begin_adventure", "choose_starter"),
        next_objective="receive_pokedex",
        frames_executed=21_216,
        actions_executed=178,
        controller_released=True,
    )
    report = QualifiedPlayReport(
        rom=rom,
        pyboy_version="2.7.0",
        emulator_window="SDL2",
        emulator_speed=4,
        opening=opening,
        rival_defeated=_raw(MapId.OAKS_LAB, 5, 6),
        viridian_reached=_raw(MapId.VIRIDIAN_CITY, 21, 35),
        parcel_received=_raw(MapId.VIRIDIAN_MART, 2, 5),
        pallet_returned=_raw(MapId.PALLET_TOWN, 10, 0),
        pokedex_received=_raw(MapId.OAKS_LAB, 5, 3),
        pewter=_PewterEvidence(),  # type: ignore[arg-type]
        cerulean=_CeruleanEvidence(),  # type: ignore[arg-type]
        cascade=_CascadeEvidence(),  # type: ignore[arg-type]
        vermilion=_VermilionEvidence(),  # type: ignore[arg-type]
        ss_anne=_SSAnneEvidence(),  # type: ignore[arg-type]
        surge=_SurgeEvidence(),  # type: ignore[arg-type]
        lavender=_LavenderEvidence(),  # type: ignore[arg-type]
        celadon=_CeladonEvidence(),  # type: ignore[arg-type]
        hideout=_HideoutEvidence(),  # type: ignore[arg-type]
        tower=_TowerEvidence(),  # type: ignore[arg-type]
        fuchsia=_FuchsiaEvidence(),  # type: ignore[arg-type]
        safari=_SafariEvidence(),  # type: ignore[arg-type]
        koga=_KogaEvidence(),  # type: ignore[arg-type]
        strength=_StrengthEvidence(),  # type: ignore[arg-type]
        erika=_ErikaEvidence(),  # type: ignore[arg-type]
        saffron=_SaffronEvidence(),  # type: ignore[arg-type]
        silph=_SilphEvidence(),  # type: ignore[arg-type]
        dojo=_DojoEvidence(),  # type: ignore[arg-type]
        sabrina=_SabrinaEvidence(),  # type: ignore[arg-type]
        cinnabar=_CinnabarEvidence(),  # type: ignore[arg-type]
        blaine=_BlaineEvidence(),  # type: ignore[arg-type]
        giovanni=_GiovanniEvidence(),  # type: ignore[arg-type]
        victory_road=_VictoryRoadEvidence(),  # type: ignore[arg-type]
        lorelei=_LoreleiEvidence(),  # type: ignore[arg-type]
        bruno=_BrunoEvidence(),  # type: ignore[arg-type]
        agatha=_AgathaEvidence(),  # type: ignore[arg-type]
        lance=_LanceEvidence(),  # type: ignore[arg-type]
        champion=_ChampionEvidence(),  # type: ignore[arg-type]
        rival_evidence=_rival_victory(),
        parcel_evidence=_parcel_obtained(),
        pokedex_evidence=_pokedex_obtained(),
        saw_trainer_battle=True,
        facts=frozenset(
            {
                "system:clean_power_on",
                "story:adventure_begun",
                "party:starter_obtained",
                "story:pokedex_received",
                "location:pewter_city",
                "badge:boulder",
                "location:cerulean_city",
                "item:ss_ticket",
                "badge:cascade",
                "location:vermilion_city",
                "move:cut_available",
                "badge:thunder",
                "location:lavender_town",
                "location:celadon_city",
                "story:rocket_hideout_cleared",
                "item:silph_scope",
                "item:poke_flute",
                "location:fuchsia_city",
                "move:surf_available",
                "move:strength_available",
                "badge:soul",
                "badge:rainbow",
                "location:saffron_city",
                "story:silph_co_liberated",
                "badge:marsh",
                "location:cinnabar_island",
                "item:secret_key",
                "badge:volcano",
                "badge:earth",
                "story:victory_road_cleared",
                "league:lorelei_defeated",
                "league:bruno_defeated",
                "league:agatha_defeated",
                "league:lance_defeated",
                "league:champion_defeated",
                "game:hall_of_fame",
            }
        ),
        verified_objectives=(
            "power_on",
            "begin_adventure",
            "choose_starter",
            "receive_pokedex",
            "reach_pewter",
            "defeat_brock",
            "reach_cerulean",
            "help_bill",
            "defeat_misty",
            "reach_vermilion",
            "obtain_cut",
            "defeat_surge",
            "reach_lavender",
            "reach_celadon",
            "clear_rocket_hideout",
            "obtain_silph_scope",
            "rescue_fuji",
            "reach_fuchsia",
            "obtain_surf",
            "obtain_strength",
            "defeat_koga",
            "defeat_erika",
            "reach_saffron",
            "liberate_silph",
            "defeat_sabrina",
            "reach_cinnabar",
            "obtain_secret_key",
            "defeat_blaine",
            "defeat_giovanni",
            "cross_victory_road",
            "defeat_lorelei",
            "defeat_bruno",
            "defeat_agatha",
            "defeat_lance",
            "defeat_champion",
            "enter_hall_of_fame",
        ),
        next_objective=None,
        frames_executed=394_000,
        actions_executed=5_704,
        controller_released=True,
        pokedex_state=RedPokedexState(
            owned_species=frozenset((7, 8, 9, 106)),
            seen_species=frozenset((7, 8, 9, 25, 106)),
        ),
    )

    public = report.public_dict()
    serialized = json.dumps(public, sort_keys=True)

    assert report.passed
    assert not replace(
        report,
        battle_policy_teacher_free_required=True,
        battle_policy_report={
            "teacher_queries_allowed": False,
            "teacher_queries": 1,
            "teacher_fallbacks": 0,
            "fallback_reasons": {},
        },
    ).passed
    assert replace(
        report,
        battle_policy_teacher_free_required=True,
        battle_policy_report={
            "teacher_queries_allowed": False,
            "teacher_queries": 0,
            "teacher_fallbacks": 0,
            "fallback_reasons": {},
        },
    ).passed
    assert not replace(report, training_candidate_authority_required=True).passed
    assert replace(
        report,
        training_candidate_authority_required=True,
        training_candidate_policy_report={
            "model_had_execution_authority": True,
            "controlled_decisions": 1,
            "teacher_fallback_on_model_disagreement": False,
        },
    ).passed
    assert replace(
        report,
        objective_policy_report={
            "authorized_decisions": 0,
            "completed_objectives": len(COMPLETION_QUEST),
            "expected_answer_labels_supplied": 0,
            "fixed_dispatch_decisions": len(COMPLETION_QUEST),
            "learned_choice_decisions": 0,
            "teacher_fallbacks": 0,
        },
    ).passed
    assert not replace(
        report,
        objective_policy_report={
            "authorized_decisions": 0,
            "completed_objectives": len(COMPLETION_QUEST),
            "expected_answer_labels_supplied": 0,
            "fixed_dispatch_decisions": len(COMPLETION_QUEST) - 1,
            "learned_choice_decisions": 0,
            "teacher_fallbacks": 0,
        },
    ).passed
    assert public["schema"] == "qualified-play-v27"
    assert public["status"] == "ok"
    assert public["qualified_through"] == "enter_hall_of_fame"
    assert public["game_complete"] is True
    assert public["safe_stop_reason"] == "completion_verified"
    assert public["training_candidate_policy"] is None
    assert public["training_candidate_authority_required"] is False
    assert [checkpoint["id"] for checkpoint in public["checkpoints"]] == [
        "bedroom_ready",
        "downstairs",
        "outside",
        "oak_triggered",
        "selection_ready",
        "starter_obtained",
        "rival_defeated",
        "viridian_reached",
        "parcel_received",
        "pallet_returned",
        "pokedex_received",
        "lab_exited",
        "viridian_northbound",
        "route_2_reached",
        "forest_gate_reached",
        "forest_entered",
        "forest_cleared",
        "pewter_reached",
        "pewter_gym_entered",
        "brock_battle",
        "brock_defeated",
        "route_3_reached",
        "route_3_trainer_0",
        "route_3_trainer_1",
        "route_3_trainer_3",
        "route_3_trainer_6",
        "route_4_reached",
        "mt_moon_entered",
        "mt_moon_b1f",
        "mt_moon_b2f",
        "required_rocket",
        "super_nerd",
        "helix_fossil",
        "mt_moon_b1f_ascent",
        "mt_moon_exited",
        "cerulean_reached",
        "cerulean_rival_battle",
        "cerulean_rival_defeated",
        "route_24_trainer_5",
        "route_24_trainer_4",
        "route_24_trainer_3",
        "route_24_trainer_2",
        "route_24_trainer_1",
        "nugget_rocket_battle",
        "nugget_rocket_defeated",
        "route_25_trainer_8",
        "route_25_trainer_3",
        "route_25_trainer_2",
        "route_25_trainer_5",
        "bill_requested_help",
        "bill_cell_separator_used",
        "bill_restored",
        "ss_ticket_obtained",
        "bills_house_left",
        "cerulean_gym_trainer_battle",
        "cerulean_gym_trainer_defeated",
        "misty_battle",
        "misty_defeated",
        "misty_ready",
        "trashed_house_entered",
        "robbery_rear_exit",
        "rocket_thief_battle",
        "tm28_obtained",
        "route_5_reached",
        "underground_north_entrance",
        "underground_tunnel",
        "underground_south_entrance",
        "route_6_reached",
        "route_6_trainer_f_battle",
        "route_6_trainer_f_defeated",
        "route_6_trainer_m_battle",
        "route_6_trainer_m_defeated",
        "vermilion_reached",
        "vermilion_ready",
        "healed",
        "dock_reached",
        "ship_1f_reached",
        "ship_2f_reached",
        "rival_battle",
        "rival_defeated",
        "captain_room_reached",
        "hm01_obtained",
        "hm01_ready",
        "healed",
        "balls_purchased",
        "spearow_encounter",
        "spearow_captured",
        "diglett_captured",
        "dux_traded",
        "cut_taught",
        "diglett_dig_ready",
        "gym_reached",
        "first_switch",
        "second_switch",
        "surge_battle",
        "surge_defeated",
        "surge_reward_stable",
        "surge_ready",
        "gym_exited",
        "second_cut",
        "healed",
        "bubblebeam",
        "supplies",
        "reverse_underground",
        "cerulean_cut",
        "route9_cut",
        "route9_trainers",
        "rock_center",
        "tunnel_entered",
        "rock_tunnel_cleared",
        "lavender_reached",
        "lavender_stable",
        "lavender_ready",
        "lavender_exited",
        "route8_reached",
        "route8_trainer8_battle",
        "route8_trainer8_defeated",
        "route8_entrance",
        "route8_gate",
        "west_east_tunnel",
        "west_east_tunnel_crossed",
        "route7_reached",
        "celadon_reached",
        "celadon_stable",
        "celadon_ready",
        "game_corner",
        "guard_defeated",
        "poster_switch",
        "b3_reached",
        "b4_key_wing",
        "lift_key",
        "recovered",
        "elevator",
        "b4_boss_wing",
        "guard_2",
        "boss_door",
        "giovanni",
        "silph_scope",
        "dig_return",
        "scope_stable",
        "hideout_cleared",
        "scope_ready",
        "resources_verified",
        "scope_ready",
        "tower_2f",
        "rival",
        "tower_3f",
        "tower_4f",
        "purified_1",
        "purified_2",
        "purified_3",
        "channelers",
        "x_accuracy",
        "rare_candy",
        "marowak",
        "rocket_19",
        "rocket_20",
        "rocket_21",
        "fuji_rescued",
        "poke_flute",
        "tower_cleared",
        "fuji_verified",
        "flute_verified",
        "resources_verified",
        "objective_ready",
        "semantic_gate",
        "party_verified",
        "controller_verified",
        "lavender_stable",
        "chapter_complete",
        "fuji_ready",
        "route12",
        "fisher",
        "snorlax",
        "recovered",
        "rocker",
        "route13_pair",
        "route13_clear",
        "route14_clear",
        "route15_clear",
        "fuchsia",
        "healed",
        "optionals",
        "fuchsia_stable",
        "surf_ready",
        "gate",
        "admitted",
        "east",
        "north",
        "west",
        "teeth_stance",
        "teeth",
        "hm03",
        "surf",
        "cleanup",
        "stable",
        "koga_ready",
        "gym_entry",
        "juggler3",
        "tamer2",
        "recovery1",
        "juggler4",
        "recovery2",
        "koga_stance",
        "koga_defeated",
        "rewards",
        "koga_stable",
        "strength_ready",
        "warden_house",
        "warden_stance",
        "teeth_given",
        "hm04",
        "strength",
        "center_return",
        "strength_stable",
        "erika_ready",
        "celadon_arrived",
        "celadon_ready",
        "gym_entered",
        "lass_defeated",
        "cooltrainer_defeated",
        "gym_recovered",
        "erika_stance",
        "erika_battle",
        "erika_defeated",
        "rainbow_received",
        "erika_stable",
        "saffron_ready",
        "roof_reached",
        "water_bought",
        "gate_reached",
        "drink_consumed",
        "guards_bribed",
        "saffron_entered",
        "saffron_stable",
        "silph_ready",
        "silph_supplied",
        "card_key",
        "third_floor_door",
        "rival_ready",
        "silph_rival",
        "eleventh_ready",
        "eleventh_rocket",
        "eleventh_door",
        "silph_liberated",
        "master_ball",
        "silph_terminal",
        "dojo_ready",
        "dojo_entered",
        "dojo_trainer_1",
        "dojo_trainer_2",
        "dojo_trainer_3",
        "dojo_trainer_4",
        "karate_master",
        "hitmonlee_received",
        "dojo_terminal",
        "sabrina_ready",
        "leader_reached",
        "sabrina_defeated",
        "marsh_badge",
        "gym_exited",
        "sabrina_terminal",
        "cinnabar_ready",
        "fly_house_reached",
        "fly_taught",
        "pallet_reached",
        "cinnabar_reached",
        "cinnabar_terminal",
        "blaine_ready",
        "mansion_entered",
        "secret_key_obtained",
        "mansion_returned",
        "gym_quizzes_cleared",
        "blaine_defeated",
        "tm38_received",
        "blaine_terminal",
        "giovanni_ready",
        "viridian_arrived",
        "tm_slot_freed",
        "viridian_gym_entered",
        "viridian_trainers_cleared",
        "giovanni_recovered",
        "giovanni_defeated",
        "giovanni_terminal",
        "victory_road_ready",
        "route22_rival",
        "victory_supplied",
        "badge_corridor",
        "vr1_switch",
        "vr2_switch",
        "vr3_hole",
        "vr2_final",
        "indigo_ready",
        "lorelei_ready",
        "lorelei_entered",
        "lorelei_defeated",
        "bruno_ready",
        "bruno_engaged",
        "bruno_defeated",
        "agatha_ready",
        "agatha_engaged",
        "agatha_defeated",
        "lance_ready",
        "lance_engaged",
        "lance_defeated",
        "champion_ready",
        "champion_engaged",
        "hall_of_fame",
    ]
    assert public["objective_progress"] == {
        "verified": 36,
        "total": 36,
        "verified_ids": [
            "power_on",
            "begin_adventure",
            "choose_starter",
            "receive_pokedex",
            "reach_pewter",
            "defeat_brock",
            "reach_cerulean",
            "help_bill",
            "defeat_misty",
            "reach_vermilion",
            "obtain_cut",
            "defeat_surge",
            "reach_lavender",
            "reach_celadon",
            "clear_rocket_hideout",
            "obtain_silph_scope",
            "rescue_fuji",
            "reach_fuchsia",
            "obtain_surf",
            "obtain_strength",
            "defeat_koga",
            "defeat_erika",
            "reach_saffron",
            "liberate_silph",
            "defeat_sabrina",
            "reach_cinnabar",
            "obtain_secret_key",
            "defeat_blaine",
            "defeat_giovanni",
            "cross_victory_road",
            "defeat_lorelei",
            "defeat_bruno",
            "defeat_agatha",
            "defeat_lance",
            "defeat_champion",
            "enter_hall_of_fame",
        ],
        "next": None,
    }
    assert public["rival"]["trainer_battle_observed"] is True
    assert public["rival"]["victory_verified"] is True
    assert public["parcel"] == {
        "received_verified": True,
        "delivered_verified": True,
        "present_after_delivery": False,
    }
    assert public["pokedex"] == {
        "received_verified": True,
        "controls_ready": True,
        "collection_progress": {
            "contract": "red-solo-perfect-save-level-100-v2",
            "target": 124,
            "owned": 4,
            "seen": 5,
            "missing": [
                number
                for number in range(1, 151)
                if number
                not in {
                    1,
                    2,
                    3,
                    4,
                    5,
                    6,
                    7,
                    8,
                    9,
                    27,
                    28,
                    37,
                    38,
                    52,
                    53,
                    65,
                    68,
                    69,
                    70,
                    71,
                    76,
                    94,
                    106,
                    107,
                    126,
                    127,
                    134,
                    136,
                    140,
                    141,
                }
            ],
            "excluded_owned": [],
            "pokedex_target_complete": False,
            "living_collection_verified": False,
            "level_100_collection_verified": False,
        },
    }
    for private_key in (
        "/private",
        "Pokemon Red.gb",
        "filename",
        "event_flags",
        "bag_item_ids",
        "party_species_ids",
        "battle_result",
        "joy_ignore",
        "lab_script",
        "mart_script",
    ):
        assert private_key not in serialized


@pytest.mark.parametrize(
    ("changes", "saw_trainer_battle"),
    (
        ({}, False),
        ({"phase": OaksErrandPhase.UNKNOWN}, True),
        ({"map_id": MapId.PALLET_TOWN}, True),
        ({"battle_state": 2}, True),
        ({"joy_ignore": 1}, True),
        ({"lab_script": 12}, True),
        ({"battled_rival": False}, True),
        ({"battle_result": 1}, True),
        ({"first_party_species": 0xB0}, True),
        ({"first_party_level": 5}, True),
        ({"first_party_hp": 0}, True),
        ({"first_party_hp": 22, "first_party_max_hp": 21}, True),
        ({"first_party_max_hp": 20}, True),
        ({"first_party_max_hp": 24}, True),
    ),
)
def test_rival_victory_gate_rejects_every_near_miss(
    changes: dict[str, object],
    saw_trainer_battle: bool,
) -> None:
    state = replace(_rival_victory(), **changes)

    assert not is_rival_victory_verified(
        state,
        saw_trainer_battle=saw_trainer_battle,
    )


def test_rival_victory_requires_observed_entry_and_exact_result() -> None:
    victory = _rival_victory()

    assert is_rival_victory_verified(victory, saw_trainer_battle=True)
    assert not is_rival_victory_verified(victory, saw_trainer_battle=False)
    assert not is_rival_victory_verified(
        replace(victory, battle_result=2),
        saw_trainer_battle=True,
    )


def test_rival_resolution_preserves_a_real_loss_without_calling_it_a_victory() -> None:
    loss = _rival_loss()

    assert is_rival_resolution_verified(loss, saw_trainer_battle=True)
    assert not is_rival_victory_verified(loss, saw_trainer_battle=True)
    assert not is_rival_resolution_verified(loss, saw_trainer_battle=False)
    assert not is_rival_resolution_verified(
        replace(loss, first_party_hp=18),
        saw_trainer_battle=True,
    )


@pytest.mark.parametrize(
    ("hp", "max_hp"),
    (
        (21, 21),
        (17, 22),
        (23, 23),
    ),
)
def test_rival_victory_accepts_supported_squirtle_dvs_and_surviving_hp(
    hp: int,
    max_hp: int,
) -> None:
    victory = replace(
        _rival_victory(),
        first_party_hp=hp,
        first_party_max_hp=max_hp,
    )

    assert is_rival_victory_verified(victory, saw_trainer_battle=True)


@pytest.mark.parametrize(
    "map_id",
    (MapId.ROUTE_1, MapId.ROUTE_2, MapId.VIRIDIAN_FOREST),
)
def test_overworld_traversal_flees_one_wild_and_preserves_the_consumed_step(
    map_id: MapId,
) -> None:
    before = replace(
        _raw(map_id, 10, 35),
        first_party_hp=23,
        first_party_max_hp=23,
        first_party_pp=(35, 30, 0, 0),
    )
    encounter = replace(
        before,
        player_y=34,
        battle_state=1,
        battle_result=0,
        enemy_species_id=165,
        enemy_level=3,
    )
    final = replace(
        encounter,
        battle_state=0,
        battle_result=2,
        first_party_hp=22,
    )

    class _Reader:
        state = before

        def read(self) -> RawGameState:
            return self.state

        def read_battle_menu_state(self, _raw: RawGameState) -> BattleMenuState:
            return BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=3)

        def read_input_readiness(self) -> InputReadiness:
            return InputReadiness(0, 0, 0, 0, 0)

    reader = _Reader()

    class _Executor:
        kinds: list[MacroActionKind] = []

        def execute(self, action: MacroAction) -> object:
            kind = action.kind
            self.kinds.append(kind)
            if kind is MacroActionKind.MOVE and reader.state is before:
                reader.state = encounter
            elif kind is MacroActionKind.CONFIRM and reader.state is encounter:
                reader.state = final
            return object()

    executor = _Executor()
    if map_id is MapId.ROUTE_1:
        terminal, flees, movement_retries = _move_route_1_with_wild_flees(  # type: ignore[arg-type]
            executor,
            reader,  # type: ignore[arg-type]
            ("up",),
            "Route 1 unit route",
            maximum_flees=1,
            stabilization_frames=120,
            maximum_step_attempts=8,
            step_retry_wait_frames=24,
        )
    else:
        terminal, flees, movement_retries = move_with_wild_flees(  # type: ignore[arg-type]
            executor,
            reader,  # type: ignore[arg-type]
            ("up",),
            f"{map_id.name} unit route",
            expected_map_id=map_id,
            route_name=map_id.name,
            maximum_flees=1,
            stabilization_frames=120,
            maximum_step_attempts=8,
            step_retry_wait_frames=24,
            error_type=QualifiedPlayError,
        )

    assert terminal is final
    assert len(flees) == 1
    assert movement_retries == 0
    assert isinstance(flees[0], Route1WildFleeEvidence)
    assert flees[0].verified
    assert flees[0].public_dict()["expected_map"] == int(map_id)
    assert flees[0].public_dict()["run_attempts"] == 1
    assert flees[0].public_dict()["stabilization_frames"] == 120
    assert executor.kinds.count(MacroActionKind.MOVE) == 1
    assert executor.kinds.count(MacroActionKind.CONFIRM) == 1


def test_route_1_traversal_rejects_wilds_beyond_its_declared_allowance() -> None:
    before = _raw(MapId.ROUTE_1, 10, 35)
    encounter = replace(
        before,
        player_y=34,
        battle_state=1,
        enemy_species_id=165,
        enemy_level=3,
    )

    class _Reader:
        state = before

        def read(self) -> RawGameState:
            return self.state

    reader = _Reader()

    class _Executor:
        def execute(self, _action: object) -> object:
            reader.state = encounter
            return object()

    with pytest.raises(QualifiedPlayError, match="bounded 0-encounter flee allowance"):
        _move_route_1_with_wild_flees(  # type: ignore[arg-type]
            _Executor(),
            reader,  # type: ignore[arg-type]
            ("up",),
            "Route 1 unit route",
            maximum_flees=0,
            stabilization_frames=120,
            maximum_step_attempts=8,
            step_retry_wait_frames=24,
        )


def test_route_1_traversal_yields_to_the_exact_northbound_walker_gate() -> None:
    approach = _raw(MapId.ROUTE_1, 14, 14)
    yielded = replace(approach, player_x=15)
    crossed = replace(approach, player_y=13)

    class _Reader:
        state = approach

        def read(self) -> RawGameState:
            return self.state

    reader = _Reader()

    class _Executor:
        directions: list[str] = []
        first_up = True

        def execute(self, action: MacroAction) -> object:
            if action.kind is not MacroActionKind.MOVE:
                return object()
            assert isinstance(action.value, str)
            self.directions.append(action.value)
            if action.value == "up" and self.first_up:
                self.first_up = False
            elif action.value == "right":
                reader.state = yielded
            elif action.value == "left":
                reader.state = approach
            elif action.value == "up":
                reader.state = crossed
            return object()

    executor = _Executor()
    terminal, flees, movement_retries = _move_route_1_with_wild_flees(  # type: ignore[arg-type]
        executor,
        reader,  # type: ignore[arg-type]
        ("up",),
        "Route 1 walker unit route",
        maximum_flees=0,
        stabilization_frames=120,
        maximum_step_attempts=8,
        step_retry_wait_frames=24,
    )

    assert terminal is crossed
    assert not flees
    assert movement_retries == 1
    assert executor.directions == ["up", "right", "left", "up"]


def test_route_1_traversal_flees_then_retries_an_unconsumed_encounter_step() -> None:
    before = replace(
        _raw(MapId.ROUTE_1, 10, 35),
        first_party_hp=23,
        first_party_max_hp=23,
        first_party_pp=(35, 30, 0, 0),
    )
    encounter = replace(
        before,
        battle_state=1,
        enemy_species_id=165,
        enemy_level=3,
    )
    exited = replace(encounter, battle_state=0, battle_result=2)
    terminal = replace(exited, player_y=34)

    class _Reader:
        state = before

        def read(self) -> RawGameState:
            return self.state

        def read_battle_menu_state(self, _raw: RawGameState) -> BattleMenuState:
            return BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=3)

        def read_input_readiness(self) -> InputReadiness:
            return InputReadiness(0, 0, 0, 0, 0)

    reader = _Reader()

    class _Executor:
        move_attempts = 0

        def execute(self, action: MacroAction) -> object:
            if action.kind is MacroActionKind.MOVE:
                self.move_attempts += 1
                reader.state = encounter if self.move_attempts == 1 else terminal
            elif action.kind is MacroActionKind.CONFIRM and reader.state is encounter:
                reader.state = exited
            return object()

    executor = _Executor()
    observed, flees, movement_retries = _move_route_1_with_wild_flees(  # type: ignore[arg-type]
        executor,
        reader,  # type: ignore[arg-type]
        ("up",),
        "Route 1 unit route",
        maximum_flees=1,
        stabilization_frames=120,
        maximum_step_attempts=8,
        step_retry_wait_frames=24,
    )

    assert observed is terminal
    assert len(flees) == 1
    assert flees[0].verified
    assert movement_retries == 1
    assert executor.move_attempts == 2


def test_route_1_traversal_retries_one_unconsumed_direction() -> None:
    before = replace(
        _raw(MapId.ROUTE_1, 10, 35),
        first_party_hp=23,
        first_party_max_hp=23,
        first_party_pp=(35, 30, 0, 0),
    )
    terminal = replace(before, player_y=34)

    class _Reader:
        state = before

        def read(self) -> RawGameState:
            return self.state

    reader = _Reader()

    class _Executor:
        move_attempts = 0

        def execute(self, action: MacroAction) -> object:
            if action.kind is MacroActionKind.MOVE:
                self.move_attempts += 1
                if self.move_attempts == 2:
                    reader.state = terminal
            return object()

    executor = _Executor()
    observed, flees, movement_retries = _move_route_1_with_wild_flees(  # type: ignore[arg-type]
        executor,
        reader,  # type: ignore[arg-type]
        ("up",),
        "Route 1 unit route",
        maximum_flees=1,
        stabilization_frames=120,
        maximum_step_attempts=8,
        step_retry_wait_frames=24,
    )

    assert observed is terminal
    assert flees == ()
    assert movement_retries == 1
    assert executor.move_attempts == 2


def test_route_1_traversal_rejects_an_exhausted_movement_allowance() -> None:
    before = replace(
        _raw(MapId.ROUTE_1, 10, 35),
        first_party_hp=23,
        first_party_max_hp=23,
        first_party_pp=(35, 30, 0, 0),
    )

    class _Reader:
        def read(self) -> RawGameState:
            return before

    class _Executor:
        move_attempts = 0

        def execute(self, action: MacroAction) -> object:
            if action.kind is MacroActionKind.MOVE:
                self.move_attempts += 1
            return object()

    executor = _Executor()
    with pytest.raises(QualifiedPlayError, match="bounded 2-attempt movement allowance"):
        _move_route_1_with_wild_flees(  # type: ignore[arg-type]
            executor,
            _Reader(),  # type: ignore[arg-type]
            ("up",),
            "Route 1 unit route",
            maximum_flees=1,
            stabilization_frames=120,
            maximum_step_attempts=2,
            step_retry_wait_frames=24,
        )

    assert executor.move_attempts == 2


def test_route_1_flee_revalidates_position_after_the_stabilization_wait() -> None:
    before = replace(
        _raw(MapId.ROUTE_1, 10, 35),
        first_party_hp=23,
        first_party_max_hp=23,
        first_party_pp=(35, 30, 0, 0),
    )
    encounter = replace(
        before,
        player_y=34,
        battle_state=1,
        enemy_species_id=165,
        enemy_level=3,
    )
    early_exit = replace(encounter, battle_state=0, battle_result=2)
    drifted_exit = replace(early_exit, player_y=35)

    class _Reader:
        state = before

        def read(self) -> RawGameState:
            return self.state

        def read_battle_menu_state(self, _raw: RawGameState) -> BattleMenuState:
            return BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=3)

        def read_input_readiness(self) -> InputReadiness:
            return InputReadiness(0, 0, 0, 0, 0)

    reader = _Reader()

    class _Executor:
        def execute(self, action: MacroAction) -> object:
            if action.kind is MacroActionKind.MOVE and reader.state is before:
                reader.state = encounter
            elif action.kind is MacroActionKind.CONFIRM and reader.state is encounter:
                reader.state = early_exit
            elif (
                action.kind is MacroActionKind.WAIT
                and action.repeat == 120
                and reader.state is early_exit
            ):
                reader.state = drifted_exit
            return object()

    with pytest.raises(QualifiedPlayError, match="stabilized semantic evidence gate"):
        _move_route_1_with_wild_flees(  # type: ignore[arg-type]
            _Executor(),
            reader,  # type: ignore[arg-type]
            ("up",),
            "Route 1 unit route",
            maximum_flees=1,
            stabilization_frames=120,
            maximum_step_attempts=8,
            step_retry_wait_frames=24,
        )


def test_captured_rival_checkpoint_survives_later_wild_escape_result() -> None:
    captured = _rival_victory()
    later_observation = replace(captured, battle_result=2)

    assert is_rival_victory_verified(captured, saw_trainer_battle=True)
    assert not is_rival_victory_verified(
        later_observation,
        saw_trainer_battle=True,
    )
    assert captured.battle_result == 0
    with pytest.raises(FrozenInstanceError):
        captured.battle_result = 2  # type: ignore[misc]


@pytest.mark.parametrize(
    "changes",
    (
        {"phase": OaksErrandPhase.UNKNOWN},
        {"map_id": MapId.VIRIDIAN_CITY},
        {"battle_state": 1},
        {"joy_ignore": 1},
        {"mart_script": 1},
        {"got_oaks_parcel": False},
        {"parcel_in_bag": False},
    ),
)
def test_parcel_gate_requires_the_full_conjunction(changes: dict[str, object]) -> None:
    assert not is_parcel_verified(replace(_parcel_obtained(), **changes))


def test_parcel_gate_accepts_only_the_stable_mart_snapshot() -> None:
    assert is_parcel_verified(_parcel_obtained())


@pytest.mark.parametrize(
    "changes",
    (
        {"phase": OaksErrandPhase.UNKNOWN},
        {"map_id": MapId.PALLET_TOWN},
        {"battle_state": 1},
        {"joy_ignore": 1},
        {"lab_script": 16},
        {"got_oaks_parcel": False},
        {"oak_got_parcel": False},
        {"got_pokedex": False},
        {"parcel_in_bag": True},
        {"first_party_species": 0xB0},
    ),
)
def test_pokedex_gate_requires_the_full_conjunction(changes: dict[str, object]) -> None:
    assert not is_pokedex_verified(replace(_pokedex_obtained(), **changes))


def test_pokedex_gate_accepts_stable_delivery_after_escape_result_overwrite() -> None:
    assert is_pokedex_verified(_pokedex_obtained())


def test_battle_start_offsets_require_auditable_policy_evidence() -> None:
    with pytest.raises(
        ValueError,
        match="require trajectory, battle-control, or objective-policy evidence",
    ):
        run_qualified_play(
            Path("/private/Pokemon Red.gb"),
            battle_start_offsets=(),
        )


def test_strategic_navigation_assignment_requires_matching_trajectory_episode() -> None:
    registry = parse_strategic_navigation_registry(
        (
            Path(__file__).resolve().parents[1]
            / STRATEGIC_NAVIGATION_REGISTRY_RELATIVE_PATH
        ).read_bytes()
    )
    assignment = replace(registry.rehearsal_assignment(), source_commit="a" * 40)

    with pytest.raises(ValueError, match="requires a trajectory sink"):
        run_qualified_play(
            Path("/private/Pokemon Red.gb"),
            strategic_navigation_assignment=assignment,
        )

    with pytest.raises(ValueError, match="must match the trajectory episode"):
        run_qualified_play(
            Path("/private/Pokemon Red.gb"),
            trajectory_sink=InMemoryTrajectorySink(),
            trajectory_episode_id="wrong-episode",
            strategic_navigation_assignment=assignment,
        )


def test_strategic_navigation_assignment_rejects_unknown_type() -> None:
    with pytest.raises(TypeError, match="unsupported type"):
        run_qualified_play(
            Path("/private/Pokemon Red.gb"),
            strategic_navigation_assignment=object(),  # type: ignore[arg-type]
        )


def _adjacent_artifact_identity(path: Path) -> tuple[bool, str | None]:
    if not path.exists():
        return False, None
    return True, hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.integration
def test_private_rom_enters_hall_of_fame_without_adjacent_artifacts() -> None:
    raw_path = os.environ.get("POKEMON_RED_ROM")
    if not raw_path:
        pytest.skip("Set POKEMON_RED_ROM to run the private integration test")

    rom_path = Path(raw_path).expanduser().resolve()
    adjacent = tuple(Path(f"{rom_path}{suffix}") for suffix in (".ram", ".rtc", ".state"))
    before = tuple(_adjacent_artifact_identity(path) for path in adjacent)

    report = run_qualified_play(rom_path)

    after = tuple(_adjacent_artifact_identity(path) for path in adjacent)
    print(
        "qualification_metrics="
        + json.dumps(
            {
                "frames_executed": report.frames_executed,
                "actions_executed": report.actions_executed,
                "collection_progress": (
                    {
                        "owned": report.collection_progress.collection.pokedex_owned_count,
                        "living": report.collection_progress.collection.living_count,
                        "level_100": report.collection_progress.collection.level_cap_count,
                        "box_counts": report.collection_progress.box_counts,
                    }
                    if report.collection_progress is not None
                    else None
                ),
            },
            sort_keys=True,
        )
    )
    assert report.passed
    assert report.verified_objectives == (
        "power_on",
        "begin_adventure",
        "choose_starter",
        "receive_pokedex",
        "reach_pewter",
        "defeat_brock",
        "reach_cerulean",
        "help_bill",
        "reach_vermilion",
        "obtain_cut",
        "defeat_misty",
        "defeat_surge",
        "reach_lavender",
        "reach_celadon",
        "clear_rocket_hideout",
        "obtain_silph_scope",
        "rescue_fuji",
        "reach_fuchsia",
        "obtain_surf",
        "defeat_erika",
        "obtain_strength",
        "reach_saffron",
        "liberate_silph",
        "defeat_sabrina",
        "defeat_koga",
        "reach_cinnabar",
        "obtain_secret_key",
        "defeat_blaine",
        "defeat_giovanni",
        "cross_victory_road",
        "defeat_lorelei",
        "defeat_bruno",
        "defeat_agatha",
        "defeat_lance",
        "defeat_champion",
        "enter_hall_of_fame",
    )
    assert report.next_objective is None
    # Completionist balanced-team lineage: live Route 1 acquisition, verified
    # all-box census, and the zero-faint six-member training block intentionally
    # make these totals much larger than the historical single-carry route.
    assert report.frames_executed == 83_619_428
    assert report.actions_executed == 765_088
    assert report.collection_progress is not None
    assert report.collection_progress.collection.target_count == 124
    assert report.collection_progress.collection.living_target_count == 120
    assert report.collection_progress.collection.pokedex_owned_count == 18
    assert report.collection_progress.collection.living_count == 13
    assert report.collection_progress.collection.level_cap_count == 0
    assert report.collection_progress.box_counts == (9,) + (0,) * 11
    assert report.cascade.final_evidence.misty_victory_snapshot
    assert report.cascade.final_evidence.cascade_badge
    assert report.cascade.final_evidence.tm11_in_bag
    assert report.cascade.final_evidence.ss_ticket_in_bag
    assert report.vermilion.passed
    assert report.vermilion.final_evidence.vermilion_snapshot
    assert report.vermilion.final_evidence.route_6_trainer_events == (
        False,
        False,
        False,
        True,
        True,
        False,
    )
    # Wild encounters are RNG-driven, so their count is a property of the seed
    # rather than of the route.  Gate the recovery behaviour (every encounter is
    # fled safely) and bound the count instead of pinning it, so a different
    # schedule does not fail a chapter that behaved correctly.
    assert 0 <= len(report.vermilion.route_6_wild_flees) <= 4
    assert all(item.enemy_species_id > 0 for item in report.vermilion.route_6_wild_flees)
    assert all(item.verified for item in report.vermilion.route_6_wild_flees)
    assert (
        report.vermilion.final_raw.map_id,
        report.vermilion.final_raw.player_x,
        report.vermilion.final_raw.player_y,
        report.vermilion.final_raw.first_party_level,
        report.vermilion.final_raw.first_party_max_hp,
        report.vermilion.final_raw.first_party_status,
    ) == (5, 19, 0, 25, 69, 0)
    # The number and timing of Route 6 encounters vary with the emulator's
    # power-on schedule, so the resulting HP and PP snapshot is not a route
    # identity.  Preserve the actual contract: the lead arrives alive, within
    # its verified maximum HP, and with every move still usable.
    assert (
        0
        < report.vermilion.final_raw.first_party_hp
        <= report.vermilion.final_raw.first_party_max_hp
    )
    assert all((value & 0x3F) > 0 for value in report.vermilion.final_raw.first_party_pp)
    assert report.ss_anne.passed
    assert report.ss_anne.saw_rival_battle
    assert report.ss_anne.final_evidence.hm01_snapshot
    assert (
        report.ss_anne.final_raw.map_id,
        report.ss_anne.final_raw.player_x,
        report.ss_anne.final_raw.player_y,
        report.ss_anne.final_raw.first_party_level,
        report.ss_anne.final_raw.first_party_max_hp,
        report.ss_anne.final_raw.first_party_status,
    ) == (MapId.SS_ANNE_CAPTAINS_ROOM, 4, 3, 26, 71, 0)
    assert 0 < report.ss_anne.final_raw.first_party_hp <= 71
    assert all((value & 0x3F) > 0 for value in report.ss_anne.final_raw.first_party_pp)
    assert report.surge.passed
    assert report.surge.dig_attacks > 0
    assert report.surge.wrong_move_count == 0
    assert report.surge.super_potion_used is False
    assert report.surge.final_raw.party_species_ids == (0xB3, 0x40, 0x3B)
    assert report.surge.final_raw.first_party_max_hp == 71
    # Earlier encounter timing changes the health carried through the Surge
    # chapter.  The route contract is survival without persistent status, not
    # one seed's exact damage roll.
    assert 0 < report.surge.final_raw.first_party_hp <= report.surge.final_raw.first_party_max_hp
    assert report.surge.final_raw.first_party_status == 0
    assert report.lavender.passed
    assert len(report.lavender.trainers) == 11
    assert 0 <= len(report.lavender.wild_flees) <= 20
    assert all(
        item.party_preserved and item.pp_preserved and item.hp_safe and item.inventory_preserved
        for item in report.lavender.wild_flees
    )
    assert report.lavender.party_hp == report.lavender.party_max_hp
    assert all(status == 0 for status in report.lavender.party_status)
    assert report.lavender.repels_used == 4
    assert (
        report.lavender.parlyz_heals_used + report.lavender.parlyz_heals_remaining
        == report.lavender.parlyz_heals_purchased
    )
    assert report.lavender.money_remaining > 0
    assert report.lavender.route_10_trainer_2_bypassed
    assert report.celadon.passed
    assert len(report.celadon.trainers) == 1
    assert report.celadon.trainers[0].selected_pp_spent > 0
    assert report.celadon.route_8_events_before == (False,) * 9
    assert report.celadon.route_8_events_after == (False,) * 8 + (True,)
    assert report.celadon.party_hp == report.celadon.party_max_hp
    assert all(status == 0 for status in report.celadon.party_status)
    assert report.celadon.repels_remaining == 0
    assert report.celadon.money_remaining > 0
    assert report.hideout.passed
    assert tuple(item.trainer_set for item in report.hideout.trainers) == (7, 18, 17, 16, 1)
    assert report.hideout.optional_events == (False,) * 8
    assert report.hideout.required_events == (True,) * 7
    assert report.hideout.entered_hideout_bug_event is False
    assert report.hideout.lift_key_carried
    assert report.hideout.silph_scope_carried
    assert report.hideout.party_hp == report.hideout.party_max_hp
    assert all(status == 0 for status in report.hideout.party_status)
    assert report.hideout.money_remaining > 0
    assert report.tower.passed
    assert tuple(item.trainer_number for item in report.tower.battles) == (
        5,
        10,
        14,
        19,
        21,
        20,
        None,
        19,
        20,
        21,
    )
    assert all(item.selected_pp_spent > 0 for item in report.tower.battles)
    assert report.tower.optional_events == (False,) * 8
    assert report.tower.required_events == (True,) * 13
    assert report.tower.purified_zone_event
    assert report.tower.purified_heals >= 0
    assert all(
        after <= before
        for before, after in zip(
            report.tower.super_potion_inventory_path,
            report.tower.super_potion_inventory_path[1:],
            strict=False,
        )
    )
    assert report.tower.evolution_before in {
        (0xB3, 0x40, 0x3B),
        (0x1C, 0x40, 0x3B),
    }
    assert report.tower.evolution_after == (0x1C, 0x40, 0x3B)
    assert report.tower.evolution_moves_preserved
    assert report.tower.party_hp == report.tower.party_max_hp
    assert all(status == 0 for status in report.tower.party_status)
    assert report.tower.money_remaining > 0
    assert report.fuchsia.passed
    assert tuple(item.trainer_number for item in report.fuchsia.battles) == (
        3,
        None,
        2,
        1,
        12,
    )
    assert all(item.selected_pp_spent > 0 for item in report.fuchsia.battles)
    assert report.fuchsia.required_events == (True,) * 5
    assert report.fuchsia.optional_events == (False,) * 35
    assert report.fuchsia.optional_items_carried == (False,) * 5
    assert report.fuchsia.flute_retained
    assert report.fuchsia.snorlax_fight_before is False
    assert report.fuchsia.snorlax_fight_after is False
    assert report.fuchsia.snorlax_object_tile_crossed
    assert 0 <= report.fuchsia.wild_flees <= 4
    snorlax = report.fuchsia.battles[1]
    assert snorlax.captured
    assert 1 <= snorlax.balls_used <= SNORLAX_CAPTURE_POLICY.max_throws
    assert snorlax.recovery_items_used <= SNORLAX_SUPER_POTION_RESERVE
    assert snorlax.party_after == snorlax.party_before + (SNORLAX,)
    assert report.fuchsia.party_hp == report.fuchsia.party_max_hp
    assert all(status == 0 for status in report.fuchsia.party_status)
    assert report.fuchsia.money_remaining > 0
    assert report.safari.passed
    assert report.safari.counter_milestones == (500, 472, 376, 238, 228, 201, 0)
    assert report.safari.balls_milestones == (30,) * 7
    assert 0 <= report.safari.encounters_fled <= 20
    assert report.safari.gold_teeth
    assert report.safari.got_hm03
    assert report.safari.hm03_retained
    assert report.safari.moves_after == (0x2C, 0x27, 0x3D, 0x39)
    assert report.safari.pp_after == (25, 30, 20, 15)
    assert report.safari.safari_steps == report.safari.safari_balls == 0
    assert report.safari.in_safari_zone is False
    assert report.koga.passed
    assert all(item.selected_pp_spent > 0 for item in report.koga.battles)
    assert all(
        item.hp_after > 0 or (item.terminal_mutual_ko and item.hp_after == 0)
        for item in report.koga.battles
    )
    assert report.koga.trainer_events_before_koga == (
        False,
        True,
        False,
        False,
        True,
        True,
    )
    assert report.koga.trainer_events_after_koga == (True,) * 6
    assert report.koga.got_tm06
    assert report.koga.beat_koga
    assert report.koga.soul_badge
    assert report.koga.soul_badge_mirror
    assert report.koga.party_hp == report.koga.party_max_hp
    assert all(status == 0 for status in report.koga.party_status)
    assert report.koga.surf_pp == 15
    assert report.strength.passed
    assert report.strength.gave_gold_teeth
    assert report.strength.got_hm04
    assert report.strength.gold_teeth_removed
    assert report.strength.hm04_retained
    assert report.strength.moves_before == (0x2C, 0x27, 0x3D, 0x39)
    assert report.strength.moves_after == (0x2C, 0x46, 0x3D, 0x39)
    assert report.strength.pp_after == (25, 15, 20, 15)
    assert report.strength.party_hp == report.strength.party_max_hp
    assert all(status == 0 for status in report.strength.party_status)
    assert report.erika.passed
    assert report.saffron.passed
    assert report.saffron.money_before - report.saffron.money_after_stone == THUNDER_STONE_PRICE
    assert (
        report.saffron.money_after_stone - report.saffron.money_after_purchase == FRESH_WATER_PRICE
    )
    assert report.saffron.money_after_purchase == report.saffron.money_after
    assert (
        report.saffron.fresh_water_before,
        report.saffron.fresh_water_after_purchase,
        report.saffron.fresh_water_after_guard,
    ) == (0, 1, 0)
    assert (
        report.saffron.guard_flag_before,
        report.saffron.guard_flag_after_consumption,
        report.saffron.guard_flag_after_dialogue,
    ) == (0, 0, 64)
    assert report.saffron.battle_free
    assert report.saffron.final_raw.map_id == MapId.SAFFRON_POKECENTER
    assert (
        report.saffron.final_raw.player_x,
        report.saffron.final_raw.player_y,
    ) == (3, 3)
    assert report.silph.passed
    assert report.silph.tm13_event
    assert report.silph.other_roof_rewards_untouched
    assert report.silph.upgraded_moves == (0x82, 0x46, 0x3A, 0x39)
    assert report.silph.upgraded_pp == (15, 15, 10, 15)
    assert report.silph.max_repel_remaining == 0
    assert report.silph.card_key_quantity == 1
    assert report.silph.master_ball_quantity == 1
    assert all(value for _, value in report.silph.required_events)
    assert report.silph.money_before > 0
    assert report.silph.money_after > 0
    assert report.sabrina.passed
    assert report.sabrina.identity == (0xF0, 0xF0, 1)
    assert report.sabrina.trainer_events_before == (False,) * 7
    assert report.sabrina.trainer_events_after == (True,) * 7
    assert report.sabrina.got_tm46
    assert report.sabrina.beat_sabrina
    assert report.sabrina.marsh_badge
    assert report.sabrina.marsh_badge_mirror
    assert report.sabrina.tm46_quantity == 1
    assert 0 <= report.sabrina.hyper_potions_remaining <= 6
    assert report.cinnabar.passed
    assert report.cinnabar.lead_stats_after[0] >= report.cinnabar.lead_stats_before[0]
    assert all(
        after >= before
        for before, after in zip(
            report.cinnabar.lead_stats_before[1:],
            report.cinnabar.lead_stats_after[1:],
            strict=True,
        )
    )
    assert report.cinnabar.hm02_item_before_event
    assert report.cinnabar.got_hm02
    assert report.cinnabar.dux_moves_after == (0x40, 0x1C, 0x0F, 0x13)
    assert report.cinnabar.dux_pp_after == (35, 15, 30, 15)
    assert report.cinnabar.route21_events_before == (False,) * 9
    assert report.cinnabar.route21_events_after == (False,) * 9
    assert report.cinnabar.wild_battles == len(report.cinnabar.wild_flees)
    assert 0 <= report.cinnabar.wild_battles <= 3
    assert all(
        item.party_preserved and item.pp_preserved and item.hp_safe and item.inventory_preserved
        for item in report.cinnabar.wild_flees
    )
    assert report.cinnabar.trainer_battles == 0
    assert report.cinnabar.party_hp == report.cinnabar.party_max_hp
    assert all(status == 0 for status in report.cinnabar.party_status)
    assert report.blaine.passed
    assert report.blaine.mansion_switch_trace == (False, True, False, True)
    assert report.blaine.mansion_trainer_events_after == (False,) * 6
    assert report.blaine.secret_key_quantity == 1
    assert report.blaine.gym_trainer_events_before == (False,) * 7
    assert report.blaine.gym_trainer_events_after == (True,) * 7
    assert report.blaine.identity == (0xEF, 0xEF, 1)
    assert report.blaine.got_tm38
    assert report.blaine.beat_blaine
    assert report.blaine.volcano_badge
    assert report.blaine.volcano_badge_mirror
    assert report.blaine.tm38_quantity == 1
    assert report.blaine.money_remaining > 0
    assert report.giovanni.passed
    assert report.giovanni.identity == (0xE5, 0xE5, 3)
    assert report.giovanni.trainer_events_before == (False,) * 8
    assert report.giovanni.trainer_events_before_giovanni == (
        True,
        True,
        True,
        False,
        True,
        True,
        False,
        True,
    )
    assert report.giovanni.trainer_events_after == (True,) * 8
    assert report.giovanni.got_tm27
    assert report.giovanni.beat_giovanni
    assert report.giovanni.earth_badge
    assert report.giovanni.earth_badge_mirror
    assert report.giovanni.tm27_quantity == 1
    assert report.giovanni.money_remaining > 0
    assert report.victory_road.passed
    assert report.victory_road.rival_party == (
        (0x97, 47),
        (0x12, 45),
        (0x16, 45),
        (0x21, 47),
        (0x95, 50),
        (0x9A, 53),
    )
    assert report.victory_road.badge_checks == (True,) * 7
    assert report.victory_road.party_hp == report.victory_road.party_max_hp
    assert all(status == 0 for status in report.victory_road.party_status)
    assert report.victory_road.final_raw.first_party_moves == (0x42, 0x46, 0x3A, 0x39)
    assert report.victory_road.final_raw.first_party_pp == (25, 15, 10, 15)
    assert report.lorelei.passed
    assert report.bruno.passed
    assert report.agatha.passed
    assert report.lance.passed
    assert report.champion.passed
    assert report.champion.x_specials_used == 6
    assert report.champion.final_raw.map_id == MapId.HALL_OF_FAME
    assert report.champion.final_raw.first_party_moves == (0x05, 0x46, 0x3B, 0x39)
    assert before == after
