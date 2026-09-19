"""The paired curriculum changes observed lead HP and nothing else in a pair."""

from __future__ import annotations

from copy import deepcopy

from scripts.run_red_trainer_terminal_hp_pairs import terminal_hp_cases


def test_terminal_pair_recipe_is_small_and_hp_matched() -> None:
    templates = tuple({
        "actor_hp": hp,
        "party_reserves": [{"party_slot": 2}, {"party_slot": 3}],
        "opponent_party_count": 3,
        "opponent_reserves": [{"party_slot": 2}, {"party_slot": 3}],
    } for hp in (50, 55))
    cases = terminal_hp_cases(templates)
    assert len(cases) == 4
    assert [row[:2] for row in cases] == [
        (0, "healthy"), (0, "critical"), (3, "healthy"), (3, "critical")
    ]
    for index in (0, 2):
        healthy, critical = deepcopy(cases[index][2]), deepcopy(cases[index + 1][2])
        assert healthy.pop("actor_hp") == templates[index // 2]["actor_hp"]
        assert critical.pop("actor_hp") == 8
        assert healthy == critical
        assert healthy["opponent_party_count"] == 1
        assert len(healthy["party_reserves"]) == 1
