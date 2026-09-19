"""ROM-free checks for the prospective full-team TRAIN recipes."""

from __future__ import annotations

from copy import deepcopy

from scripts.run_red_trainer_full_team_pairs import full_team_cases


def _template(index: int) -> dict[str, object]:
    return {
        "actor_hp": 50 + index,
        "party_reserves": [{"party_slot": 2}, {"party_slot": 3}],
        "opponent_reserves": [{"party_slot": 2}, {"party_slot": 3}],
    }


def test_full_team_pairs_change_only_observed_lead_hp() -> None:
    cases = full_team_cases(tuple(_template(index) for index in range(4)))

    assert len(cases) == 8
    for index in range(4):
        healthy = cases[2 * index]
        critical = cases[2 * index + 1]
        assert healthy[:2] == (index, "healthy")
        assert critical[:2] == (index, "critical")
        assert healthy[2]["actor_hp"] == 50 + index
        assert critical[2]["actor_hp"] == 8
        healthy_without_hp = deepcopy(healthy[2])
        critical_without_hp = deepcopy(critical[2])
        healthy_without_hp.pop("actor_hp")
        critical_without_hp.pop("actor_hp")
        assert healthy_without_hp == critical_without_hp
        assert len(healthy[2]["party_reserves"]) == 4
        assert len(healthy[2]["opponent_reserves"]) == 4
        assert healthy[2]["opponent_party_count"] == 5
