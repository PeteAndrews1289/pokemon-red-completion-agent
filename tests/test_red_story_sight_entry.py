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

    def await_battle(*args, **kwargs):
        raw.battle_state = 2

    monkeypatch.setattr(entry.silph, "_await_trainer_battle", await_battle)
    actions = NS(execute=lambda a: calls.append(a))
    if fault:
        with pytest.raises((ValueError, RuntimeError)):
            entry.enter_story_sight(reader, actions, edge=edge, contract=contract, rom=b"fixture")
        assert len(calls) == (1 if fault == "wrong_opponent" else 0)
    else:
        entry.enter_story_sight(reader, actions, edge=edge, contract=contract, rom=b"fixture")
        assert len(calls) == 1


@pytest.mark.parametrize("fault", [None, "delayed", "map", "position", "static",
    "unverified", "recovery_map", "recovery_position", "battle_after", "second_wild",
    "wrong_opponent"])
def test_sight_entry_settles_one_ordinary_wild_before_exact_trainer(monkeypatch, fault):
    from pokemon_red_completion import gen1_route_runtime as route
    from pokemon_red_completion import red_player_wild_recovery as recovery

    raw = NS(battle_state=0, map_id=23, player_y=3, player_x=3)
    contract = NS(map_id=23, trainer_identity=(220, 20, 2), objective_id="reach_lavender")
    edge = LocalEdge(target=(3, 4), action="right", kind="walk")
    reader = NS(read=lambda: raw, read_input_readiness=lambda: NS(ready=True),
        trainer_engagement_active=lambda: False,
        read_active_trainer_identity=lambda: (
            (221, 21, 2) if fault == "wrong_opponent" else contract.trainer_identity))
    escaped, confirmations, diagnostics = [], [], []

    def action(a):
        if a.kind is entry.MacroActionKind.WAIT:
            return
        if a.kind is entry.MacroActionKind.MOVE:
            raw.player_x = 5 if fault == "position" else 4
            raw.map_id = 24 if fault == "map" else 23
            raw.battle_state = 0 if fault == "delayed" else 1
        else:
            assert raw.battle_state != 1, "never confirm blindly through a wild fight"
            confirmations.append(a)
            raw.battle_state = (
                1 if fault == "second_wild" or fault == "delayed" and not escaped else 2
            )

    actions = NS(execute=action,
        record_diagnostic_event=lambda kind, payload: diagnostics.append((kind, payload)))
    monkeypatch.setattr(route, "Gen1TraversalObserver", lambda _: NS(observe=lambda: NS(
        interruption="wild_battle", map_id=raw.map_id, at=(raw.player_y, raw.player_x))))
    monkeypatch.setattr(recovery, "retained_native_static_target",
        lambda *a: object() if fault == "static" else None)

    def flee(*args, **kwargs):
        assert kwargs["expected_map_id"] == 23 and kwargs["stabilization_frames"] == 120
        escaped.append(True)
        raw.battle_state = 2 if fault == "battle_after" else 0
        raw.map_id = 24 if fault == "recovery_map" else 23
        raw.player_x = 5 if fault == "recovery_position" else 4
        verified = fault != "unverified"
        return NS(verified=verified, map_id=raw.map_id, player_y=raw.player_y,
            player_x=raw.player_x, public_dict=lambda: dict(verified=verified))

    monkeypatch.setattr(route, "flee_wild", flee)
    if fault in {None, "delayed"}:
        entry.enter_story_sight(reader, actions, edge=edge, contract=contract, rom=b"fixture")
        assert escaped == [True] and raw.battle_state == 2
        assert len(diagnostics) == 1 and diagnostics[0][1]["learned"] is False
    else:
        with pytest.raises(RuntimeError):
            entry.enter_story_sight(reader, actions, edge=edge, contract=contract, rom=b"fixture")
        assert len(escaped) <= 1
        if fault in {"map", "position", "static"}:
            assert not escaped and not confirmations
