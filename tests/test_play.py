from __future__ import annotations

import hashlib
import json
import os
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

from pokemon_red_completion.observation import (
    SQUIRTLE_SPECIES_ID,
    Badge,
    MapId,
    OaksErrandPhase,
    OaksErrandState,
    OpeningControlState,
    OpeningPhase,
    RawGameState,
)
from pokemon_red_completion.opening import OpeningChapterReport
from pokemon_red_completion.play import (
    DEFAULT_QUALIFIED_PLAY_TIMING,
    LAB_EXIT_DIRECTIONS,
    LAB_RIVAL_TRIGGER_DIRECTIONS,
    PALLET_TO_ROUTE_1_DIRECTIONS,
    QUALIFIED_PLAY_CHECKPOINT_COUNT,
    ROUTE_1_TO_VIRIDIAN_DIRECTIONS,
    VIRIDIAN_TO_MART_DIRECTIONS,
    QualifiedPlayProgress,
    QualifiedPlayReport,
    QualifiedPlayTiming,
    is_parcel_verified,
    is_pokedex_verified,
    is_rival_victory_verified,
    run_qualified_play,
)
from pokemon_red_completion.rom import RomFingerprint


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


class _SabrinaEvidence:
    passed = True
    final_raw = replace(_SilphEvidence.final_raw, badge_bits=0x3F)

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
        max_rival_pulses=56,
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
    assert QUALIFIED_PLAY_CHECKPOINT_COUNT == 267
    progress = QualifiedPlayProgress(
        checkpoint_id="cerulean_reached",
        label="Reached Cerulean City",
        completed=267,
        total=QUALIFIED_PLAY_CHECKPOINT_COUNT,
        frames_executed=252_989,
    )

    assert progress.completed == progress.total == 267
    assert progress.frames_executed == 252_989
    with pytest.raises(FrozenInstanceError):
        progress.completed = 10  # type: ignore[misc]


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
        sabrina=_SabrinaEvidence(),  # type: ignore[arg-type]
        cinnabar=_CinnabarEvidence(),  # type: ignore[arg-type]
        blaine=_BlaineEvidence(),  # type: ignore[arg-type]
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
        ),
        next_objective="defeat_giovanni",
        frames_executed=394_000,
        actions_executed=5_704,
        controller_released=True,
    )

    public = report.public_dict()
    serialized = json.dumps(public, sort_keys=True)

    assert report.passed
    assert public["schema"] == "qualified-play-v21"
    assert public["status"] == "ok"
    assert public["qualified_through"] == "defeat_blaine"
    assert public["game_complete"] is False
    assert public["safe_stop_reason"] == "latest_qualified_boundary"
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
    ]
    assert public["objective_progress"] == {
        "verified": 28,
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
        ],
        "next": "defeat_giovanni",
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
        ({"first_party_max_hp": 22}, True),
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


def _adjacent_artifact_identity(path: Path) -> tuple[bool, str | None]:
    if not path.exists():
        return False, None
    return True, hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.integration
def test_private_rom_defeats_blaine_without_adjacent_artifacts() -> None:
    raw_path = os.environ.get("POKEMON_RED_ROM")
    if not raw_path:
        pytest.skip("Set POKEMON_RED_ROM to run the private integration test")

    rom_path = Path(raw_path).expanduser().resolve()
    adjacent = tuple(Path(f"{rom_path}{suffix}") for suffix in (".ram", ".rtc", ".state"))
    before = tuple(_adjacent_artifact_identity(path) for path in adjacent)

    report = run_qualified_play(rom_path)

    after = tuple(_adjacent_artifact_identity(path) for path in adjacent)
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
    )
    assert report.next_objective == "defeat_giovanni"
    assert report.frames_executed == 3_869_179
    assert report.actions_executed == 32_695
    assert report.cascade.final_evidence.misty_victory_snapshot
    assert report.cascade.final_evidence.cascade_badge
    assert report.cascade.final_evidence.tm11_in_bag
    assert report.cascade.final_evidence.ss_ticket_in_bag
    assert report.vermilion.passed
    assert report.vermilion.frames_executed == 67_412
    assert report.vermilion.actions_executed == 1_306
    assert report.vermilion.final_evidence.vermilion_snapshot
    assert report.vermilion.final_evidence.route_6_trainer_events == (
        False,
        False,
        False,
        True,
        True,
        False,
    )
    assert [
        (item.player_x, item.player_y, item.enemy_species_id)
        for item in report.vermilion.route_6_wild_flees
    ] == [(15, 19, 0x24), (15, 22, 0x24), (15, 26, 0x24)]
    assert all(item.verified for item in report.vermilion.route_6_wild_flees)
    assert (
        report.vermilion.final_raw.map_id,
        report.vermilion.final_raw.player_x,
        report.vermilion.final_raw.player_y,
        report.vermilion.final_raw.first_party_level,
        report.vermilion.final_raw.first_party_hp,
        report.vermilion.final_raw.first_party_max_hp,
        report.vermilion.final_raw.first_party_status,
        report.vermilion.final_raw.first_party_pp,
    ) == (5, 19, 0, 25, 42, 69, 0, (20, 30, 30, 25))
    assert report.ss_anne.passed
    assert report.ss_anne.frames_executed == 29_005
    assert report.ss_anne.actions_executed == 410
    assert report.ss_anne.saw_rival_battle
    assert report.ss_anne.final_evidence.hm01_snapshot
    assert (
        report.ss_anne.final_raw.map_id,
        report.ss_anne.final_raw.player_x,
        report.ss_anne.final_raw.player_y,
        report.ss_anne.final_raw.first_party_level,
        report.ss_anne.final_raw.first_party_hp,
        report.ss_anne.final_raw.first_party_max_hp,
        report.ss_anne.final_raw.first_party_status,
        report.ss_anne.final_raw.first_party_pp,
    ) == (MapId.SS_ANNE_CAPTAINS_ROOM, 4, 3, 26, 12, 71, 0, (14, 30, 30, 25))
    assert report.surge.passed
    assert report.surge.frames_executed == 104_710
    assert report.surge.actions_executed == 1_659
    assert report.surge.dig_attacks == 5
    assert report.surge.wrong_move_count == 0
    assert report.surge.super_potion_used is False
    assert report.surge.final_raw.party_species_ids == (0xB3, 0x40, 0x3B)
    assert report.surge.final_raw.first_party_hp == 71
    assert report.surge.final_raw.first_party_max_hp == 71
    assert report.surge.final_raw.first_party_status == 0
    assert report.lavender.passed
    assert report.lavender.frames_executed == 222_371
    assert report.lavender.actions_executed == 3_402
    assert len(report.lavender.trainers) == 11
    assert len(report.lavender.wild_flees) == 8
    assert report.lavender.party_hp == report.lavender.party_max_hp == (79, 52, 37)
    assert report.lavender.party_status == (0, 0, 0)
    assert report.lavender.repels_used == 4
    assert report.lavender.super_potions_used == 5
    assert report.lavender.super_potions_remaining == 4
    assert report.lavender.purchase_cost == 7_000
    assert report.lavender.money_remaining == 14_301
    assert report.lavender.route_10_trainer_2_bypassed
    assert report.celadon.passed
    assert report.celadon.frames_executed == 23_641
    assert report.celadon.actions_executed == 521
    assert len(report.celadon.trainers) == 1
    assert report.celadon.trainers[0].selected_pp_spent == 5
    assert report.celadon.route_8_events_before == (False,) * 9
    assert report.celadon.route_8_events_after == (False,) * 8 + (True,)
    assert report.celadon.party_hp == report.celadon.party_max_hp == (81, 52, 37)
    assert report.celadon.party_status == (0, 0, 0)
    assert report.celadon.super_potions_remaining == 4
    assert report.celadon.repels_remaining == 0
    assert report.celadon.money_remaining == 14_631
    assert report.hideout.passed
    assert report.hideout.frames_executed == 103_157
    assert report.hideout.actions_executed == 1_191
    assert tuple(item.trainer_set for item in report.hideout.trainers) == (7, 18, 17, 16, 1)
    assert report.hideout.optional_events == (False,) * 8
    assert report.hideout.required_events == (True,) * 7
    assert report.hideout.entered_hideout_bug_event is False
    assert report.hideout.lift_key_carried
    assert report.hideout.silph_scope_carried
    assert report.hideout.super_potions_used == 2
    assert report.hideout.super_potions_remaining == 2
    assert report.hideout.party_hp == report.hideout.party_max_hp == (86, 52, 37)
    assert report.hideout.party_status == (0, 0, 0)
    assert report.hideout.money_remaining == 20_112
    assert report.tower.passed
    assert report.tower.frames_executed == 157_197
    assert report.tower.actions_executed == 2_372
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
    assert tuple(item.selected_pp_spent for item in report.tower.battles) == (
        11,
        4,
        2,
        5,
        2,
        2,
        1,
        4,
        5,
        4,
    )
    assert report.tower.optional_events == (False,) * 8
    assert report.tower.required_events == (True,) * 13
    assert report.tower.purified_zone_event
    assert report.tower.purified_heals == 3
    assert report.tower.super_potion_inventory_path == (2, 1, 0)
    assert report.tower.evolution_before == (0xB3, 0x40, 0x3B)
    assert report.tower.evolution_after == (0x1C, 0x40, 0x3B)
    assert report.tower.evolution_moves_preserved
    assert report.tower.party_hp == report.tower.party_max_hp == (111, 52, 37)
    assert report.tower.party_status == (0, 0, 0)
    assert report.tower.money_remaining == 27_437
    assert report.fuchsia.passed
    assert report.fuchsia.frames_executed == 277_925
    assert report.fuchsia.actions_executed == 2_276
    assert tuple(item.trainer_number for item in report.fuchsia.battles) == (
        3,
        None,
        2,
        1,
        12,
    )
    assert tuple(item.selected_pp_spent for item in report.fuchsia.battles) == (
        5,
        4,
        2,
        4,
        5,
    )
    assert report.fuchsia.required_events == (True,) * 5
    assert report.fuchsia.optional_events == (False,) * 35
    assert report.fuchsia.optional_items_carried == (False,) * 5
    assert report.fuchsia.flute_retained
    assert report.fuchsia.snorlax_fight_before is False
    assert report.fuchsia.snorlax_fight_after is False
    assert report.fuchsia.snorlax_object_tile_crossed
    assert report.fuchsia.wild_flees == 4
    assert report.fuchsia.initial_bag == report.fuchsia.final_bag
    assert report.fuchsia.party_hp == report.fuchsia.party_max_hp == (114, 52, 37)
    assert report.fuchsia.party_status == (0, 0, 0)
    assert report.fuchsia.money_remaining == 30_137
    assert report.safari.passed
    assert report.safari.frames_executed == 210_768
    assert report.safari.actions_executed == 1_664
    assert report.safari.counter_milestones == (500, 472, 376, 238, 228, 201, 0)
    assert report.safari.balls_milestones == (30,) * 7
    assert report.safari.encounters_fled == 6
    assert report.safari.gold_teeth
    assert report.safari.got_hm03
    assert report.safari.hm03_retained
    assert report.safari.moves_after == (0x2C, 0x27, 0x3D, 0x39)
    assert report.safari.pp_after == (25, 30, 20, 15)
    assert report.safari.safari_steps == report.safari.safari_balls == 0
    assert report.safari.in_safari_zone is False
    assert report.koga.passed
    assert report.koga.frames_executed == 151_336
    assert report.koga.actions_executed == 1_316
    assert tuple(item.selected_pp_spent for item in report.koga.battles) == (6, 5, 5, 8)
    assert tuple(item.hp_after for item in report.koga.battles) == (84, 66, 102, 107)
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
    assert report.koga.party_hp == report.koga.party_max_hp == (124, 52, 37)
    assert report.koga.party_status == (0, 0, 0)
    assert report.koga.surf_pp == 15
    assert report.strength.passed
    assert report.strength.frames_executed == 93_936
    assert report.strength.actions_executed == 726
    assert report.strength.gave_gold_teeth
    assert report.strength.got_hm04
    assert report.strength.gold_teeth_removed
    assert report.strength.hm04_retained
    assert report.strength.moves_before == (0x2C, 0x27, 0x3D, 0x39)
    assert report.strength.moves_after == (0x2C, 0x46, 0x3D, 0x39)
    assert report.strength.pp_after == (25, 15, 20, 15)
    assert report.strength.party_hp == report.strength.party_max_hp == (124, 52, 37)
    assert report.strength.party_status == (0, 0, 0)
    assert report.erika.passed
    assert report.saffron.passed
    assert report.saffron.money_before == 41_545
    assert report.saffron.money_after_purchase == report.saffron.money_after == 41_345
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
    assert report.silph.frames_executed == 1_039_491
    assert report.silph.actions_executed == 3_461
    assert report.silph.tm13_event
    assert report.silph.tm13_transfer_before_event
    assert report.silph.other_roof_rewards_untouched
    assert report.silph.upgraded_moves == (0x82, 0x46, 0x3A, 0x39)
    assert report.silph.upgraded_pp == (15, 15, 10, 15)
    assert report.silph.rival_potions_used == 0
    assert report.silph.hyper_potions_remaining == 6
    assert report.silph.max_repel_remaining == 0
    assert report.silph.card_key_quantity == 1
    assert report.silph.master_ball_quantity == 1
    assert all(value for _, value in report.silph.required_events)
    assert report.silph.money_before == 41_345
    assert report.silph.money_after == 40_894
    assert report.sabrina.passed
    assert report.sabrina.frames_executed == 174_109
    assert report.sabrina.actions_executed == 575
    assert report.sabrina.identity == (0xF0, 0xF0, 1)
    assert report.sabrina.trainer_events_before == (False,) * 7
    assert report.sabrina.trainer_events_after == (True,) * 7
    assert report.sabrina.got_tm46
    assert report.sabrina.beat_sabrina
    assert report.sabrina.marsh_badge
    assert report.sabrina.marsh_badge_mirror
    assert report.sabrina.tm46_quantity == 1
    assert report.sabrina.hyper_potions_remaining == 6
    assert report.cinnabar.passed
    assert report.cinnabar.frames_executed == 151_044
    assert report.cinnabar.actions_executed == 862
    assert report.cinnabar.lead_stats_before == (45, 139, 139, 98, 109, 90, 104)
    assert report.cinnabar.lead_stats_after == (46, 142, 142, 100, 112, 92, 106)
    assert report.cinnabar.hm02_item_before_event
    assert report.cinnabar.got_hm02
    assert report.cinnabar.dux_moves_after == (0x40, 0x1C, 0x0F, 0x13)
    assert report.cinnabar.dux_pp_after == (35, 15, 30, 15)
    assert report.cinnabar.route21_events_before == (False,) * 9
    assert report.cinnabar.route21_events_after == (False,) * 9
    assert report.cinnabar.wild_battles == 3
    assert [
        (item.x, item.y, item.species, item.level) for item in report.cinnabar.wild_flees
    ] == [(4, 12, 0xA5, 21), (3, 52, 0x18, 10), (3, 77, 0x18, 10)]
    assert all(
        item.party_preserved
        and item.pp_preserved
        and item.hp_safe
        and item.inventory_preserved
        for item in report.cinnabar.wild_flees
    )
    assert report.cinnabar.trainer_battles == 0
    assert report.cinnabar.party_hp == report.cinnabar.party_max_hp == (142, 52, 37)
    assert report.cinnabar.party_status == (0, 0, 0)
    assert report.blaine.passed
    assert report.blaine.frames_executed == 220_309
    assert report.blaine.actions_executed == 1_785
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
    assert report.blaine.money_remaining == 50_579
    assert before == after
