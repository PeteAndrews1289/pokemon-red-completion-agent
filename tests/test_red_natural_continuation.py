from pathlib import Path
from types import SimpleNamespace

import pytest

import hashlib
import json

from continue_red_natural_party import (
    CAPTURE_ID, LINEAGE, MODEL_SHA, SOURCE_SHA, WalkingOnlyWorld,
    bound, capture_capacity, continuation_parent, recover_hp,
)
from pokemon_red_completion.battle_scenario_capture import build_battle_scenario_capture_payload
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.global_router import MacroGraph
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlanningError


def raw(**changes):
    return SimpleNamespace(**({"party_count": 2, "party_hp": (30, 20),
        "party_status": (0, 0), "bag_items": ((4, 4),)} | changes))


def test_capture_stops_when_remaining_balls_cannot_reach_six():
    assert capture_capacity(raw(), 0)
    assert not capture_capacity(raw(bag_items=((4, 3),)), 0)
    assert not capture_capacity(raw(bag_items=()), 0)
    assert not capture_capacity(raw(party_count=6), 0)
    assert not capture_capacity(raw(), 12)
    assert not capture_capacity(raw(party_hp=(0, 20)), 0)
    assert not capture_capacity(raw(party_status=(8, 0)), 0)
    with pytest.raises(ValueError):
        capture_capacity(raw(party_count=1), 0)


def test_parent_hash_authentication_precedes_any_gameplay(tmp_path: Path):
    file = tmp_path / "state"
    file.write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash differs"):
        bound(file, "a" * 64)


def test_potion_recovery_uses_only_actual_inventory():
    current = raw(battle_state=0, party_max_hp=(60, 20))
    reader = SimpleNamespace(read=lambda: current,
        read_input_readiness=lambda: SimpleNamespace(ready=True))
    recover_hp(None, None, reader, lambda _: pytest.fail("no potion may be invented"))


def test_potion_recovery_cannot_replace_live_battle_actions():
    reader = SimpleNamespace(read=lambda: raw(battle_state=2))
    with pytest.raises(ValueError, match="ready field"):
        recover_hp(None, None, reader, lambda _: None)


def parent_args(tmp_path, **changes):
    parent = {"source_sha256": SOURCE_SHA, "final_state_sha256": "b" * 64,
        "model_sha256": MODEL_SHA, "battle": None, "pressed_buttons": [], "fits": 0,
        "memory_writes": 0, "frames": 123, "macros_attempted": 7, "elapsed_seconds": 1.5}
    parent.update(changes)
    result = tmp_path / "result.json"
    data = json.dumps(parent).encode()
    result.write_bytes(data)
    return SimpleNamespace(parent_result=result,
        parent_result_sha256=hashlib.sha256(data).hexdigest(), state=tmp_path / "final.state")


def test_pre_model_continuation_retains_cumulative_costs(tmp_path):
    sha, used = continuation_parent(parent_args(tmp_path))
    assert sha == "b" * 64
    assert used == {"frames": 123, "macros": 7, "seconds": 1.5, "stage": 1}


@pytest.mark.parametrize("change", [
    {"source_sha256": "c" * 64}, {"model_sha256": "c" * 64}, {"battle": {}},
    {"pressed_buttons": ["a"]}, {"fits": 1}, {"memory_writes": 1},
    {"cumulative": {"frames": 500000, "macros": 1, "seconds": 1, "stage": 1}},
    {"cumulative": {"frames": 1, "macros": 20000, "seconds": 1, "stage": 1}},
    {"cumulative": {"frames": 1, "macros": 1, "seconds": 900, "stage": 1}},
    {"cumulative": {"frames": 1, "macros": 1, "seconds": 1, "stage": 4}},
])
def test_continuation_rejects_replay_or_budget_reset(tmp_path, change):
    with pytest.raises(ValueError):
        continuation_parent(parent_args(tmp_path, **change))


def test_failed_model_log_cannot_be_replayed_as_preparation(tmp_path):
    args = parent_args(tmp_path)
    (tmp_path / "events").mkdir()
    with pytest.raises(ValueError):
        continuation_parent(args)


def test_local_approach_reserves_objects_warps_and_rejects_special_edges():
    graph = LocalGraph({(1, 1): (LocalEdge((1, 2), "right", required_mode="land"),),
                        (1, 2): (LocalEdge((1, 3), "right", kind="ledge"),)})
    world = SimpleNamespace(local_graphs={61: graph}, object_blockers={61: frozenset()},
        macro_graph=SimpleNamespace(warp_locations={}))
    adapter = WalkingOnlyWorld(world)
    start = TraversalSnapshot(61, (1, 1), ready=True, mode="land")
    plan = adapter.plan_feasible_to_map(start, 61, goal_at=(1, 2))
    assert len(plan.steps) == 1 and plan.steps[0].expected_mode == "land"
    with pytest.raises(RoutePlanningError):
        adapter.plan_feasible_to_map(start, 61, goal_at=(1, 3))
    world.object_blockers = {61: frozenset({(1, 2)})}
    with pytest.raises(RoutePlanningError):
        adapter.plan_feasible_to_map(start, 61, goal_at=(1, 2))


def test_local_approach_can_leave_arrival_warp_but_not_cross_other_warps():
    graph = LocalGraph({(1, 1): (LocalEdge((1, 2), "right"),),
                        (1, 2): (LocalEdge((1, 3), "right"),)})
    world = SimpleNamespace(local_graphs={61: graph}, object_blockers={61: frozenset()},
        macro_graph=SimpleNamespace(warp_locations={61: ((1, 1), (1, 3))}))
    adapter = WalkingOnlyWorld(world)
    start = TraversalSnapshot(61, (1, 1), ready=True, mode="land")
    assert len(adapter.plan_feasible_to_map(start, 61, goal_at=(1, 2)).steps) == 1
    with pytest.raises(RoutePlanningError):
        adapter.plan_feasible_to_map(start, 61, goal_at=(1, 3))
    world.object_blockers = {61: frozenset()}
    world.macro_graph.warp_locations = {61: ((1, 2),)}
    with pytest.raises(RoutePlanningError):
        adapter.plan_feasible_to_map(start, 61, goal_at=(1, 2))


def test_actual_continuation_manifest_identifier_is_valid_before_gameplay():
    result = build_battle_scenario_capture_payload(capture_id=CAPTURE_ID,
        root_lineage_id=LINEAGE, partition=ScenarioPartition.DEVELOPMENT,
        state_bytes=b"test-state", source_state_sha256=SOURCE_SHA,
        initial_observation_sha256="b" * 64, source_commit="c" * 40,
        expected_map=61, expected_battle_state=2)
    assert CAPTURE_ID.encode() in result
