from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion import red_story_sight_entry as entry
from pokemon_red_completion.local_router import LocalEdge
from pokemon_red_completion.red_story_sight_entry import sight_entry_edge


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "hidden",
        "defeated",
        "overlap",
        "occupied",
        "wall",
        "ledge",
        "identity",
        "not_ready",
        "hazard",
    ],
)
def test_explicit_sight_boundary(fault):
    contract = NS(map_id=23, defeated_event=12, trainer_identity=(220, 20, 2))
    target = NS(
        map_id=23,
        event_flag=12,
        trainer_class=221 if fault == "identity" else 220,
        trainer_set=2,
        defeated=fault == "defeated",
        visible=fault != "hidden",
        lane=((3, 4),),
    )
    zones = [target]
    if fault == "overlap":
        zones.append(
            NS(
                event_flag=13,
                trainer_class=221,
                trainer_set=2,
                map_id=23,
                defeated=False,
                visible=True,
                lane=((3, 4),),
            )
        )
    start = NS(
        ready=fault != "not_ready",
        interruption=None,
        map_id=23,
        at=(3, 3),
        mode="land",
        occupied={(3, 4)} if fault == "occupied" else set(),
        hazards=(NS(at=(3, 4), kind="other" if fault == "hazard" else "trainer_sight"),),
    )
    edge = LocalEdge(target=(3, 4), action="right", kind="walk")
    if fault == "ledge":
        edge = replace(edge, kind="ledge")
    edges = () if fault == "wall" else (edge,)
    if fault:
        with pytest.raises(ValueError):
            sight_entry_edge(start, edges, zones, contract)
    else:
        assert sight_entry_edge(start, edges, zones, contract) == edge


@pytest.mark.parametrize("fault", [None, "moved", "busy", "wrong_opponent"])
def test_entry_checks_source_and_result(monkeypatch, fault):
    raw = NS(battle_state=0, map_id=23, player_y=3, player_x=2 if fault == "moved" else 3)
    contract = NS(map_id=23, trainer_identity=(220, 20, 2))
    edge = LocalEdge(target=(3, 4), action="right", kind="walk")
    calls = []
    reader = NS(
        read=lambda: raw,
        read_input_readiness=lambda: NS(ready=fault != "busy"),
        read_active_trainer_identity=lambda: (
            (221, 21, 2) if fault == "wrong_opponent" else (220, 20, 2)
        ),
    )

    def await_battle(*args):
        raw.battle_state = 2

    monkeypatch.setattr(entry.silph, "_await_trainer_battle", await_battle)
    actions = NS(execute=lambda a: calls.append(a))
    if fault:
        with pytest.raises((ValueError, RuntimeError)):
            entry.enter_story_sight(reader, actions, edge=edge, contract=contract)
        assert len(calls) == (1 if fault == "wrong_opponent" else 0)
    else:
        entry.enter_story_sight(reader, actions, edge=edge, contract=contract)
        assert len(calls) == 1
