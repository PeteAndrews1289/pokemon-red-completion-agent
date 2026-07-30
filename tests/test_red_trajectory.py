from __future__ import annotations

from dataclasses import replace

import pytest

from pokemon_red_completion.observation import (
    BattleMenuPhase,
    BattleMenuState,
    InputReadiness,
    MapId,
    RawGameState,
)
from pokemon_red_completion.red_trajectory import (
    POKEMON_CORE_ONTOLOGY_ID,
    POKEMON_RED_ADAPTER_ID,
    POKEMON_RED_GAME_ID,
    PokemonRedObservationEncoder,
)
from pokemon_red_completion.trajectory import canonical_json


class _Reader:
    def __init__(
        self,
        raw: RawGameState,
        menu: BattleMenuState,
        readiness: InputReadiness | None = None,
    ) -> None:
        self.raw = raw
        self.menu = menu
        self.readiness = readiness or InputReadiness(0, 0, 0, 0, 0)

    def read(self) -> RawGameState:
        return self.raw

    def read_input_readiness(self) -> InputReadiness:
        return self.readiness

    def read_battle_menu_state(self, raw: RawGameState) -> BattleMenuState:
        assert raw is self.raw
        return self.menu


def _raw() -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=MapId.PALLET_TOWN,
        player_x=5,
        player_y=6,
        party_count=1,
        battle_state=0,
        badge_bits=0,
        bag_item_ids=(4,),
        event_flags=None,
        party_species_ids=(0xB1,),
        first_party_level=5,
        first_party_hp=20,
        first_party_max_hp=20,
        first_party_status=0,
        first_party_moves=(0x21, 0x27),
        first_party_pp=(35, 30),
    )


def test_red_encoder_exposes_normalized_and_namespaced_semantics() -> None:
    encoder = PokemonRedObservationEncoder(
        _Reader(_raw(), BattleMenuState(BattleMenuPhase.UNKNOWN))
    )

    snapshot = encoder.snapshot()
    payload = snapshot.to_dict()
    features = payload["features"]

    assert snapshot.game_id == POKEMON_RED_GAME_ID
    assert snapshot.mode == "interactive"
    assert snapshot.location == "pokemon.red.gb.us.rev0:area:pallet_town"
    assert features["adapter_id"] == POKEMON_RED_ADAPTER_ID
    assert features["ontology_id"] == POKEMON_CORE_ONTOLOGY_ID
    assert features["world"] == {
        "area_ref": "pokemon.red.gb.us.rev0:area:pallet_town",
        "area_kind": "settlement",
        "position": {"x": 5, "y": 6},
    }
    assert features["party"]["lead"]["species_ref"] == ("pokemon.red.gb.us.rev0:species:177")
    assert features["party"]["lead"]["hp_ratio"] == 1.0
    assert features["party"]["lead"]["moves"][0] == {
        "slot_index": 0,
        "move_ref": "pokemon.red.gb.us.rev0:move:033",
        "pp": 35,
    }
    assert features["control"] == {"input_ready": True}
    assert snapshot.facts == ("pokemon.core:party:available",)
    assert features["menu"] is None


def test_red_encoder_normalizes_battle_state_without_raw_memory() -> None:
    raw = replace(
        _raw(),
        battle_state=2,
        first_party_hp=9,
        first_party_status=0x40,
        enemy_species_id=0x99,
        enemy_level=7,
        enemy_hp=11,
        enemy_max_hp=22,
        player_attack_stage=8,
        player_accuracy_stage=6,
        enemy_defense_stage=7,
    )
    encoder = PokemonRedObservationEncoder(
        _Reader(
            raw,
            BattleMenuState(
                BattleMenuPhase.MOVE,
                selected_move_slot=2,
            ),
        )
    )

    snapshot = encoder.snapshot()
    features = snapshot.to_dict()["features"]

    assert snapshot.mode == "battle"
    assert features["party"]["lead"]["status"] == "paralysis"
    assert features["battle"] == {
        "active": True,
        "kind": "trainer",
        "opponent_species_ref": "pokemon.red.gb.us.rev0:species:153",
        "opponent_level": 7,
        "opponent_hp": 11,
        "opponent_max_hp": 22,
        "opponent_hp_ratio": 0.5,
        "player_attack_stage": 1,
        "player_accuracy_stage": -1,
        "opponent_defense_stage": 0,
    }
    assert features["menu"] == {
        "kind": "battle_move",
        "selected_move_index": 1,
    }

    serialized = canonical_json(snapshot)
    for forbidden in (
        "event_flags",
        "bag_item_ids",
        "memory_address",
        "rom_path",
        "save_state",
    ):
        assert forbidden not in serialized


def test_privileged_event_changes_do_not_change_policy_snapshot() -> None:
    baseline = _raw()
    changed = replace(
        baseline,
        event_flags=b"\xff" * 32,
    )

    baseline_snapshot = PokemonRedObservationEncoder(
        _Reader(baseline, BattleMenuState(BattleMenuPhase.UNKNOWN))
    ).snapshot()
    changed_snapshot = PokemonRedObservationEncoder(
        _Reader(changed, BattleMenuState(BattleMenuPhase.UNKNOWN))
    ).snapshot()

    assert canonical_json(baseline_snapshot) == canonical_json(changed_snapshot)


def test_clean_boot_is_not_ready_and_does_not_claim_a_location() -> None:
    raw = replace(
        _raw(),
        game_started=False,
        map_id=MapId.PALLET_TOWN,
        player_x=0,
        player_y=0,
        party_count=0,
        party_species_ids=(),
    )
    snapshot = PokemonRedObservationEncoder(
        _Reader(raw, BattleMenuState(BattleMenuPhase.UNKNOWN))
    ).snapshot()
    features = snapshot.to_dict()["features"]

    assert snapshot.mode == "booting"
    assert snapshot.location is None
    assert snapshot.facts == ()
    assert features["control"] == {"input_ready": False}
    assert features["world"] == {
        "area_ref": None,
        "area_kind": None,
        "position": {"x": None, "y": None},
    }


def test_blocked_overworld_uses_conservative_mode() -> None:
    blocked = InputReadiness(
        joy_ignore=1,
        simulated_joypad_index=0,
        npc_movement_script_table=0,
        player_moving_direction=0,
        status_flags_5=0,
    )
    snapshot = PokemonRedObservationEncoder(
        _Reader(
            _raw(),
            BattleMenuState(BattleMenuPhase.UNKNOWN),
            readiness=blocked,
        )
    ).snapshot()

    assert snapshot.mode == "scripted_or_blocked"
    assert snapshot.to_dict()["features"]["control"] == {"input_ready": False}


@pytest.mark.parametrize(
    ("battle_state", "menu", "expected"),
    (
        (
            0,
            BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=2),
            None,
        ),
        (
            2,
            BattleMenuState(BattleMenuPhase.UNKNOWN),
            None,
        ),
        (
            2,
            BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=2),
            {"kind": "battle_main", "selected_command_index": 2},
        ),
        (
            2,
            BattleMenuState(BattleMenuPhase.MOVE, selected_move_slot=3),
            {"kind": "battle_move", "selected_move_index": 2},
        ),
    ),
)
def test_menu_is_only_reported_for_known_live_battle_menus(
    battle_state: int,
    menu: BattleMenuState,
    expected: dict[str, object] | None,
) -> None:
    snapshot = PokemonRedObservationEncoder(
        _Reader(replace(_raw(), battle_state=battle_state), menu)
    ).snapshot()

    assert snapshot.to_dict()["features"]["menu"] == expected


def test_moves_skip_empty_slots_keep_slot_indexes_and_mask_pp_bits() -> None:
    raw = replace(
        _raw(),
        first_party_moves=(0x21, 0, 0x27, 0),
        first_party_pp=(0xC1, 0xFF, 0xBE, 0),
    )
    snapshot = PokemonRedObservationEncoder(
        _Reader(raw, BattleMenuState(BattleMenuPhase.UNKNOWN))
    ).snapshot()

    assert snapshot.to_dict()["features"]["party"]["lead"]["moves"] == [
        {
            "slot_index": 0,
            "move_ref": "pokemon.red.gb.us.rev0:move:033",
            "pp": 1,
        },
        {
            "slot_index": 2,
            "move_ref": "pokemon.red.gb.us.rev0:move:039",
            "pp": 62,
        },
    ]


def test_all_teacher_known_map_ids_have_meaningful_adapter_labels() -> None:
    for map_id in MapId:
        snapshot = PokemonRedObservationEncoder(
            _Reader(
                replace(_raw(), map_id=map_id),
                BattleMenuState(BattleMenuPhase.UNKNOWN),
            )
        ).snapshot()

        assert snapshot.location is not None
        assert ":area:map_" not in snapshot.location


@pytest.mark.parametrize(
    ("map_id", "expected_kind"),
    (
        (MapId.ROUTE_1, "route"),
        (MapId.CERULEAN_GYM, "gym"),
        (MapId.CERULEAN_POKECENTER, "healing"),
        (MapId.CELADON_MART_1F, "shop"),
        (MapId.VICTORY_ROAD_1F, "dungeon"),
        (MapId.ROUTE_12_GATE_1F, "gate"),
        (MapId.LORELEIS_ROOM, "league"),
        (MapId.UNDERGROUND_PATH_NORTH_SOUTH, "passage"),
        (MapId.SAFARI_ZONE_CENTER, "wilderness"),
        (MapId.SS_ANNE_1F, "ship"),
    ),
)
def test_adapter_classifies_common_area_kinds(
    map_id: MapId,
    expected_kind: str,
) -> None:
    snapshot = PokemonRedObservationEncoder(
        _Reader(
            replace(_raw(), map_id=map_id),
            BattleMenuState(BattleMenuPhase.UNKNOWN),
        )
    ).snapshot()

    assert snapshot.to_dict()["features"]["world"]["area_kind"] == expected_kind
