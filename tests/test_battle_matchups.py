from __future__ import annotations

import pytest

from pokemon_red_completion.battle_matchups import (
    MIN_SAFE_SWITCH_HP_RATIO,
    best_reserve_matchup,
    project_party_matchups,
    project_reserve_control_features,
)
from pokemon_red_completion.red_battle_catalog import (
    RED_BATTLE_CATALOG,
    pokemon_red_move_ref,
    pokemon_red_species_ref,
)


def _member(
    species_id: int,
    *,
    level: int,
    hp: int,
    moves: tuple[tuple[int, int], ...],
) -> dict[str, object]:
    return {
        "species_ref": pokemon_red_species_ref(species_id),
        "level": level,
        "hp": hp,
        "max_hp": 100,
        "hp_ratio": hp / 100,
        "status": None,
        "moves": [
            {
                "slot_index": slot,
                "move_ref": pokemon_red_move_ref(move_id),
                "pp": pp,
            }
            for slot, (move_id, pp) in enumerate(moves)
        ],
    }


def _lorelei_observation(*, jolteon_hp: int = 100) -> dict[str, object]:
    return {
        "features": {
            "party": {
                "active_index": 0,
                "members": [
                    _member(0x1C, level=63, hp=100, moves=((0x39, 15), (0x3A, 10))),
                    _member(0x68, level=55, hp=jolteon_hp, moves=((0x57, 10), (0x62, 20))),
                    _member(0x84, level=55, hp=100, moves=((0x22, 15), (0x1D, 10))),
                ],
            },
            "battle": {
                "opponent_species_ref": pokemon_red_species_ref(0x78),
                "opponent_level": 54,
            },
        }
    }


def test_matchup_profiles_hide_identity_but_preserve_mechanics() -> None:
    profiles = project_party_matchups(_lorelei_observation(), RED_BATTLE_CATALOG)

    assert tuple(profile.party_slot for profile in profiles) == (1, 2, 3)
    assert profiles[1].offensive_type_margin > profiles[0].offensive_type_margin
    assert profiles[1].offensive_power > profiles[0].offensive_power
    assert profiles[1].usable_move_fraction == 0.5
    assert all(-1.0 <= profile.defensive_resistance <= 1.0 for profile in profiles)


def test_best_reserve_selects_jolteon_for_lorelei_water_matchup() -> None:
    selected = best_reserve_matchup(_lorelei_observation(), RED_BATTLE_CATALOG)

    assert selected is not None
    assert selected.party_slot == 2
    assert selected.safe


def test_matchup_selection_follows_candidate_permutation_not_party_identity() -> None:
    observation = _lorelei_observation()
    party = observation["features"]["party"]  # type: ignore[index]
    members = party["members"]  # type: ignore[index]
    party["members"] = [members[0], members[2], members[1]]

    selected = best_reserve_matchup(observation, RED_BATTLE_CATALOG)

    assert selected is not None
    assert selected.party_slot == 3


def test_matchup_selection_changes_when_the_opponent_types_change() -> None:
    observation = _lorelei_observation()
    battle = observation["features"]["battle"]  # type: ignore[index]
    battle["opponent_species_ref"] = pokemon_red_species_ref(0x76)

    selected = best_reserve_matchup(observation, RED_BATTLE_CATALOG)

    assert selected is not None
    assert selected.party_slot == 3


def test_switch_ranking_keeps_health_as_a_hard_first_boundary() -> None:
    selected = best_reserve_matchup(
        _lorelei_observation(jolteon_hp=int(MIN_SAFE_SWITCH_HP_RATIO * 100) - 1),
        RED_BATTLE_CATALOG,
    )

    assert selected is not None
    assert selected.party_slot == 3


def test_switch_ranking_values_level_when_candidates_have_the_same_type_matchup() -> None:
    observation = _lorelei_observation()
    party = observation["features"]["party"]  # type: ignore[index]
    party["members"] = [  # type: ignore[index]
        _member(0x1C, level=45, hp=100, moves=((0x39, 15),)),
        _member(0xB1, level=40, hp=100, moves=((0x21, 20),)),
        _member(0xB1, level=25, hp=100, moves=((0x0A, 35),)),
    ]
    battle = observation["features"]["battle"]  # type: ignore[index]
    battle["opponent_species_ref"] = pokemon_red_species_ref(0xB1)
    battle["opponent_level"] = 30

    selected = best_reserve_matchup(observation, RED_BATTLE_CATALOG)

    assert selected is not None
    assert selected.party_slot == 2


def test_switch_target_fails_closed_when_every_reserve_is_below_health_floor() -> None:
    observation = _lorelei_observation(jolteon_hp=49)
    members = observation["features"]["party"]["members"]  # type: ignore[index]
    members[2]["hp"] = 49
    members[2]["hp_ratio"] = 0.49

    assert best_reserve_matchup(observation, RED_BATTLE_CATALOG) is None


def test_control_summary_exposes_candidate_relative_advantage() -> None:
    values = project_reserve_control_features(
        _lorelei_observation(),
        RED_BATTLE_CATALOG,
    )

    assert len(values) == 15
    assert values[0] == 1.0
    assert values[1] == 1.0
    assert values[12] > 0.0
    assert values[14] > 0.0
    assert all(-1.0 <= value <= 1.0 for value in values)


def test_no_living_reserve_produces_a_zero_summary() -> None:
    observation = _lorelei_observation()
    members = observation["features"]["party"]["members"]  # type: ignore[index]
    for member in members[1:]:  # type: ignore[index]
        member["hp"] = 0
        member["hp_ratio"] = 0.0

    assert project_reserve_control_features(observation, RED_BATTLE_CATALOG) == pytest.approx(
        (0.0,) * 15
    )
