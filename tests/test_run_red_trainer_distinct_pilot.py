from __future__ import annotations

from scripts.run_red_trainer_distinct_pilot import prospective_cases


def test_pilot_recipes_change_observable_matchups_resources_and_party_sizes():
    templates = tuple(
        {
            "actor_hp": 50,
            "actor_moves": [{"move_ref": "first", "pp": 10}, {"move_ref": "second", "pp": 20}],
            "opponent_species_ref": "old-opponent",
            "opponent_national_number": 74,
            "opponent_party_count": 3,
            "opponent_reserves": [{"party_slot": 2}, {"party_slot": 3}],
            "party_reserves": [{"party_slot": 2}, {"party_slot": 3}],
        }
        for _ in range(4)
    )
    cases = prospective_cases(templates)
    assert len(cases) == 8
    assert {root for root, _, _ in cases} == {0, 1, 2, 3}
    assert all(
        spec["opponent_species_ref"] != "old-opponent"
        for _, name, spec in cases
        if name == "type-reversal"
    )
    assert all(
        spec["actor_hp"] == 8 and spec["actor_moves"][0]["pp"] == 1
        for _, name, spec in cases
        if name == "scarce-resource"
    )
    assert all(
        len(spec["party_reserves"]) == 1
        for root, name, spec in cases
        if name == "scarce-resource" and root < 2
    )
    assert all(
        spec["opponent_party_count"] == 1
        for root, name, spec in cases
        if name == "scarce-resource" and root >= 2
    )
    assert templates[0]["actor_moves"][0]["pp"] == 10
