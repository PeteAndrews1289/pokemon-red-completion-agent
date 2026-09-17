from __future__ import annotations

from scripts.run_red_trainer_decisive_pairs import decisive_cases


def test_decisive_pairs_change_only_opponent_identity_within_each_pair():
    templates = tuple(
        {
            "actor_hp": 50,
            "actor_moves": [{"move_ref": "first", "pp": 10}, {"move_ref": "second", "pp": 20}],
            "opponent_species_ref": "original",
            "opponent_party_count": 3,
            "opponent_reserves": [{"party_slot": 2}],
        }
        for _ in range(4)
    )
    cases = decisive_cases(templates)
    assert len(cases) == 8
    for index in range(0, 8, 2):
        first = cases[index][2]
        second = cases[index + 1][2]
        assert first["opponent_species_ref"] != second["opponent_species_ref"]
        assert first["opponent_national_number"] != second["opponent_national_number"]
        for key in set(first) - {"opponent_species_ref", "opponent_national_number"}:
            assert first[key] == second[key]
        assert first["opponent_party_count"] == 1
        assert first["opponent_moves"] == [
            {"move_ref": "pokemon.red.gb.us.rev0:move:033", "pp": 35}
        ]
        assert "actor_stats" not in first
