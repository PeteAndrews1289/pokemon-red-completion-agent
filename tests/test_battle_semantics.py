from __future__ import annotations

from copy import deepcopy

import pytest

from pokemon_red_completion.battle_semantics import (
    FEATURE_NAMES,
    FEATURE_SCHEMA_ID,
    MAX_EFFECTIVE_POWER,
    BattleFeatureError,
    BattleFeatureProjector,
)
from pokemon_red_completion.red_battle_catalog import (
    RED_BATTLE_CATALOG,
    RedBattleCatalogError,
)


def _snapshot() -> dict[str, object]:
    return {
        "schema_version": 1,
        "game_id": "pokemon.mainline:red:gb:us:rev0",
        "mode": "battle",
        "location": "pokemon.red.gb.us.rev0:area:route_20",
        "facts": ["pokemon.core:battle:active"],
        "features": {
            "adapter_id": "pokemon.red.gb.us.rev0.v1",
            "ontology_id": "pokemon.core.v1",
            "world": {
                "area_ref": "pokemon.red.gb.us.rev0:area:route_20",
                "area_kind": "route",
                "position": {"x": 7, "y": 9},
            },
            "progress": {"badge_count": 6},
            "party": {
                "count": 1,
                "species_refs": ["pokemon.red.gb.us.rev0:species:177"],
                "lead": {
                    "species_ref": "pokemon.red.gb.us.rev0:species:177",
                    "level": 42,
                    "hp": 80,
                    "max_hp": 120,
                    "hp_ratio": 0.666667,
                    "status": "paralysis",
                    "moves": [
                        {
                            "slot_index": 0,
                            "move_ref": "pokemon.red.gb.us.rev0:move:085",
                            "pp": 12,
                        },
                        {
                            "slot_index": 1,
                            "move_ref": "pokemon.red.gb.us.rev0:move:057",
                            "pp": 0,
                        },
                        {
                            "slot_index": 2,
                            "move_ref": "pokemon.red.gb.us.rev0:move:039",
                            "pp": 30,
                        },
                    ],
                },
            },
            "battle": {
                "active": True,
                "kind": "trainer",
                "opponent_species_ref": "pokemon.red.gb.us.rev0:species:022",
                "opponent_level": 40,
                "opponent_hp": 100,
                "opponent_max_hp": 200,
                "opponent_hp_ratio": 0.5,
                "player_attack_stage": 1,
                "player_accuracy_stage": -1,
                "opponent_defense_stage": 2,
            },
            "menu": {
                "kind": "battle_main",
                "selected_command_index": 0,
            },
            "objective_id": "route-specific-secret-that-must-not-be-used",
        },
    }


def _value(batch: object, candidate: int, feature_name: str) -> float:
    feature_names = batch.feature_names  # type: ignore[attr-defined]
    vector = batch.candidate_vectors[candidate]  # type: ignore[attr-defined]
    return vector[feature_names.index(feature_name)]


def _lead(snapshot: dict[str, object]) -> dict[str, object]:
    features = snapshot["features"]
    assert isinstance(features, dict)
    party = features["party"]
    assert isinstance(party, dict)
    lead = party["lead"]
    assert isinstance(lead, dict)
    return lead


def _battle(snapshot: dict[str, object]) -> dict[str, object]:
    features = snapshot["features"]
    assert isinstance(features, dict)
    battle = features["battle"]
    assert isinstance(battle, dict)
    return battle


def test_projector_builds_fixed_transferable_candidate_vectors() -> None:
    batch = BattleFeatureProjector(RED_BATTLE_CATALOG).project(_snapshot())

    assert batch.schema_id == FEATURE_SCHEMA_ID
    assert batch.feature_names == FEATURE_NAMES
    assert len(batch.feature_names) == 100
    assert batch.feature_names[-11:] == (
        "interaction.physical_x_player_attack_stage",
        "interaction.physical_x_opponent_defense_stage",
        "interaction.physical_x_player_burn",
        "interaction.move_accuracy_x_player_accuracy_stage",
        "interaction.recoil_x_player_missing_hp",
        "interaction.heal_x_player_missing_hp",
        "interaction.drain_x_player_missing_hp",
        "interaction.effective_power_x_opponent_hp",
        "interaction.effective_power_x_level_difference",
        "interaction.fixed_damage_x_player_level",
        "interaction.pp_x_effective_power",
    )
    assert batch.slot_indices == (0, 1, 2)
    assert batch.current_pp == (12.0, 0.0, 30.0)
    assert batch.legal_mask == (True, False, True)
    assert len(batch.candidate_vectors) == 3
    assert all(len(vector) == len(FEATURE_NAMES) for vector in batch.candidate_vectors)
    assert all(-1.0 <= value <= 1.0 for vector in batch.candidate_vectors for value in vector)

    assert _value(batch, 0, "state.player_hp_ratio") == pytest.approx(0.666667)
    assert _value(batch, 0, "state.player_level_fraction") == 0.42
    assert _value(batch, 0, "state.level_difference_fraction") == 0.02
    assert _value(batch, 0, "state.player_attack_stage_fraction") == pytest.approx(1 / 6)
    assert _value(batch, 0, "state.player_status.paralysis") == 1.0
    assert _value(batch, 0, "state.player_type.water") == 1.0
    assert _value(batch, 0, "state.opponent_type.water") == 1.0
    assert _value(batch, 0, "state.opponent_type.flying") == 1.0

    assert _value(batch, 0, "move.pp_fraction") == pytest.approx(12 / 15)
    assert _value(batch, 0, "move.power_fraction") == pytest.approx(95 / 255)
    assert _value(batch, 0, "move.accuracy") == 1.0
    assert _value(batch, 0, "move.category.special") == 1.0
    assert _value(batch, 0, "move.type.electric") == 1.0
    assert _value(batch, 0, "move.stab") == 0.0
    assert _value(batch, 0, "move.type_effectiveness_fraction") == 1.0
    assert _value(batch, 0, "move.effective_power_fraction") == pytest.approx(
        380 / MAX_EFFECTIVE_POWER
    )
    assert _value(batch, 0, "move.effect.status") == 1.0
    assert _value(
        batch,
        0,
        "interaction.move_accuracy_x_player_accuracy_stage",
    ) == pytest.approx(-1 / 6)
    assert _value(
        batch,
        0,
        "interaction.effective_power_x_opponent_hp",
    ) == pytest.approx((380 / MAX_EFFECTIVE_POWER) * 0.5)
    assert _value(
        batch,
        0,
        "interaction.effective_power_x_level_difference",
    ) == pytest.approx((380 / MAX_EFFECTIVE_POWER) * 0.02)
    assert _value(batch, 0, "interaction.pp_x_effective_power") == pytest.approx(
        (12 / 15) * (380 / MAX_EFFECTIVE_POWER)
    )

    assert _value(batch, 1, "move.stab") == 1.0
    assert _value(batch, 1, "move.type_effectiveness_fraction") == 0.125
    assert _value(batch, 1, "move.effective_power_fraction") == pytest.approx(
        71.25 / MAX_EFFECTIVE_POWER
    )
    assert _value(batch, 2, "move.category.status") == 1.0
    assert _value(batch, 2, "move.effect.debuff") == 1.0


def test_physical_stage_burn_and_accuracy_interactions_are_candidate_specific() -> None:
    snapshot = _snapshot()
    lead = _lead(snapshot)
    lead["status"] = "burn"
    lead["moves"] = [
        {
            "slot_index": 0,
            "move_ref": "pokemon.red.gb.us.rev0:move:033",
            "pp": 35,
        },
        {
            "slot_index": 1,
            "move_ref": "pokemon.red.gb.us.rev0:move:052",
            "pp": 25,
        },
        {
            "slot_index": 2,
            "move_ref": "pokemon.red.gb.us.rev0:move:039",
            "pp": 30,
        },
    ]
    battle = _battle(snapshot)
    battle["player_attack_stage"] = 3
    battle["player_accuracy_stage"] = -3
    battle["opponent_defense_stage"] = 2

    batch = BattleFeatureProjector(RED_BATTLE_CATALOG).project(snapshot)

    assert [
        _value(batch, index, "interaction.physical_x_player_attack_stage") for index in range(3)
    ] == [0.5, 0.0, 0.0]
    assert [
        _value(batch, index, "interaction.physical_x_opponent_defense_stage") for index in range(3)
    ] == [pytest.approx(1 / 3), 0.0, 0.0]
    assert [_value(batch, index, "interaction.physical_x_player_burn") for index in range(3)] == [
        1.0,
        0.0,
        0.0,
    ]
    assert [
        _value(batch, index, "interaction.move_accuracy_x_player_accuracy_stage")
        for index in range(3)
    ] == [pytest.approx(-0.475), -0.5, -0.5]


def test_missing_hp_interactions_activate_only_matching_move_effects() -> None:
    snapshot = _snapshot()
    lead = _lead(snapshot)
    lead["hp_ratio"] = 0.25
    lead["moves"] = [
        {
            "slot_index": 0,
            "move_ref": "pokemon.red.gb.us.rev0:move:036",
            "pp": 20,
        },
        {
            "slot_index": 1,
            "move_ref": "pokemon.red.gb.us.rev0:move:105",
            "pp": 20,
        },
        {
            "slot_index": 2,
            "move_ref": "pokemon.red.gb.us.rev0:move:071",
            "pp": 20,
        },
    ]

    batch = BattleFeatureProjector(RED_BATTLE_CATALOG).project(snapshot)

    assert [
        _value(batch, index, "interaction.recoil_x_player_missing_hp") for index in range(3)
    ] == [0.75, 0.0, 0.0]
    assert [_value(batch, index, "interaction.heal_x_player_missing_hp") for index in range(3)] == [
        0.0,
        0.75,
        0.0,
    ]
    assert [
        _value(batch, index, "interaction.drain_x_player_missing_hp") for index in range(3)
    ] == [0.0, 0.0, 0.75]


def test_power_level_fixed_damage_and_pp_interactions_remain_bounded() -> None:
    snapshot = _snapshot()
    lead = _lead(snapshot)
    lead["level"] = 50
    lead["moves"] = [
        {
            "slot_index": 0,
            "move_ref": "pokemon.red.gb.us.rev0:move:033",
            "pp": 7,
        },
        {
            "slot_index": 1,
            "move_ref": "pokemon.red.gb.us.rev0:move:069",
            "pp": 10,
        },
        {
            "slot_index": 2,
            "move_ref": "pokemon.red.gb.us.rev0:move:039",
            "pp": 30,
        },
    ]
    battle = _battle(snapshot)
    battle["opponent_level"] = 40
    battle["opponent_hp_ratio"] = 0.25

    batch = BattleFeatureProjector(RED_BATTLE_CATALOG).project(snapshot)
    tackle_power = 35 / MAX_EFFECTIVE_POWER
    seismic_toss_power = 0.5 / MAX_EFFECTIVE_POWER

    assert [
        _value(batch, index, "interaction.effective_power_x_opponent_hp") for index in range(3)
    ] == [
        pytest.approx(tackle_power * 0.25),
        pytest.approx(seismic_toss_power * 0.25),
        0.0,
    ]
    assert [
        _value(batch, index, "interaction.effective_power_x_level_difference") for index in range(3)
    ] == [
        pytest.approx(tackle_power * 0.1),
        pytest.approx(seismic_toss_power * 0.1),
        0.0,
    ]
    assert [
        _value(batch, index, "interaction.fixed_damage_x_player_level") for index in range(3)
    ] == [0.0, 0.5, 0.0]
    assert [_value(batch, index, "interaction.pp_x_effective_power") for index in range(3)] == [
        pytest.approx((7 / 35) * tackle_power),
        pytest.approx((10 / 20) * seismic_toss_power),
        0.0,
    ]
    assert all(-1.0 <= value <= 1.0 for vector in batch.candidate_vectors for value in vector)


def test_usable_counter_fails_closed_without_prior_damage_semantics() -> None:
    snapshot = _snapshot()
    _lead(snapshot)["moves"] = [
        {
            "slot_index": 0,
            "move_ref": "pokemon.red.gb.us.rev0:move:068",
            "pp": 20,
        },
        {
            "slot_index": 1,
            "move_ref": "pokemon.red.gb.us.rev0:move:033",
            "pp": 35,
        },
    ]

    with pytest.raises(
        BattleFeatureError,
        match="Counter requires prior-turn received-damage semantics",
    ):
        BattleFeatureProjector(RED_BATTLE_CATALOG).project(snapshot)


def test_depleted_counter_remains_a_safely_masked_candidate() -> None:
    snapshot = _snapshot()
    _lead(snapshot)["moves"] = [
        {
            "slot_index": 0,
            "move_ref": "pokemon.red.gb.us.rev0:move:068",
            "pp": 0,
        },
        {
            "slot_index": 1,
            "move_ref": "pokemon.red.gb.us.rev0:move:033",
            "pp": 35,
        },
    ]

    batch = BattleFeatureProjector(RED_BATTLE_CATALOG).project(snapshot)

    assert batch.legal_mask == (False, True)
    assert _value(batch, 0, "move.effect.counter") == 1.0
    assert _value(batch, 1, "move.effect.counter") == 0.0


def test_route_progress_and_objective_changes_cannot_change_vectors() -> None:
    baseline = _snapshot()
    changed = deepcopy(baseline)
    changed["location"] = "pokemon.red.gb.us.rev0:area:champions_room"
    features = changed["features"]
    assert isinstance(features, dict)
    features["world"] = {
        "area_ref": "pokemon.red.gb.us.rev0:area:champions_room",
        "area_kind": "league",
        "position": {"x": 1, "y": 1},
    }
    features["progress"] = {"badge_count": 8}
    features["objective_id"] = "a-different-route-specific-secret"

    projector = BattleFeatureProjector(RED_BATTLE_CATALOG)
    assert projector.project(baseline) == projector.project(changed)

    forbidden_tokens = (
        "location",
        "area",
        "route",
        "objective",
        "species_ref",
        "move_ref",
        "species_id",
        "move_id",
        "slot",
    )
    assert all(
        forbidden not in feature_name
        for feature_name in FEATURE_NAMES
        for forbidden in forbidden_tokens
    )


def test_candidate_vectors_are_equivariant_to_move_slot_permutation() -> None:
    first = _snapshot()
    second = deepcopy(first)
    first_features = first["features"]
    second_features = second["features"]
    assert isinstance(first_features, dict)
    assert isinstance(second_features, dict)
    first_party = first_features["party"]
    second_party = second_features["party"]
    assert isinstance(first_party, dict)
    assert isinstance(second_party, dict)
    first_lead = first_party["lead"]
    second_lead = second_party["lead"]
    assert isinstance(first_lead, dict)
    assert isinstance(second_lead, dict)

    first_lead["moves"] = first_lead["moves"][:2]  # type: ignore[index]
    second_moves = second_lead["moves"][:2]  # type: ignore[index]
    second_moves[0]["slot_index"] = 1
    second_moves[1]["slot_index"] = 0
    second_lead["moves"] = list(reversed(second_moves))

    projector = BattleFeatureProjector(RED_BATTLE_CATALOG)
    first_batch = projector.project(first)
    second_batch = projector.project(second)

    assert first_batch.feature_names == second_batch.feature_names
    assert first_batch.slot_indices == second_batch.slot_indices == (0, 1)
    assert first_batch.candidate_vectors == tuple(reversed(second_batch.candidate_vectors))
    assert first_batch.current_pp == tuple(reversed(second_batch.current_pp))
    assert first_batch.legal_mask == tuple(reversed(second_batch.legal_mask))


def test_input_list_order_does_not_change_sorted_batch() -> None:
    baseline = _snapshot()
    reordered = deepcopy(baseline)
    features = reordered["features"]
    assert isinstance(features, dict)
    party = features["party"]
    assert isinstance(party, dict)
    lead = party["lead"]
    assert isinstance(lead, dict)
    lead["moves"] = list(reversed(lead["moves"]))  # type: ignore[arg-type]

    projector = BattleFeatureProjector(RED_BATTLE_CATALOG)
    assert projector.project(baseline) == projector.project(reordered)


@pytest.mark.parametrize(
    ("path", "value", "error"),
    [
        (("mode",), "interactive", BattleFeatureError),
        (("features", "menu", "kind"), "battle_move", BattleFeatureError),
        (("features", "party", "lead", "status"), "confused", BattleFeatureError),
        (
            ("features", "party", "lead", "species_ref"),
            "pokemon.red.gb.us.rev0:species:031",
            RedBattleCatalogError,
        ),
        (
            ("features", "party", "lead", "moves", 0, "move_ref"),
            "pokemon.red.gb.us.rev0:move:999",
            RedBattleCatalogError,
        ),
        (("features", "party", "lead", "moves", 0, "pp"), -1, BattleFeatureError),
    ],
)
def test_malformed_or_unknown_snapshot_mechanics_fail_closed(
    path: tuple[object, ...],
    value: object,
    error: type[Exception],
) -> None:
    snapshot = _snapshot()
    cursor: object = snapshot
    for component in path[:-1]:
        cursor = cursor[component]  # type: ignore[index]
    cursor[path[-1]] = value  # type: ignore[index]

    with pytest.raises(error):
        BattleFeatureProjector(RED_BATTLE_CATALOG).project(snapshot)
