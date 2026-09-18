from __future__ import annotations

from copy import deepcopy

from scripts.run_red_trainer_terminal_switch_successor import successor_cases


def test_successor_preserves_hp_pair_and_declares_two_supported_reserve_moves() -> None:
    templates = (
        {"actor_hp": 50, "actor_moves": [{"move_ref": "old", "pp": 5}],
         "party_reserves": [{"party_slot": 2, "moves": []}],
         "opponent_party_count": 3, "opponent_reserves": [{}]},
        {"actor_hp": 55, "actor_moves": [{"move_ref": "old", "pp": 5}],
         "party_reserves": [{"party_slot": 2, "moves": []}],
         "opponent_party_count": 3, "opponent_reserves": [{}]},
    )
    cases = successor_cases(templates)
    assert len(cases) == 4
    assert [row[:2] for row in cases] == [
        (0, "healthy"), (0, "critical"), (3, "healthy"), (3, "critical")
    ]
    for offset in (0, 2):
        healthy = deepcopy(cases[offset][2])
        critical = deepcopy(cases[offset + 1][2])
        healthy.pop("actor_hp")
        critical.pop("actor_hp")
        assert healthy == critical
        assert len(healthy["party_reserves"]) == 1
        assert [move["move_ref"].split(":")[-1] for move in
                healthy["party_reserves"][0]["moves"]] == ["057", "061"]
    assert cases[2][2]["actor_moves"][0]["move_ref"].endswith(":053")
