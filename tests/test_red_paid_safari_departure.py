"""Native exit composition, failure retention and ordinary-parent admission."""

import json
from dataclasses import dataclass
from types import SimpleNamespace as NS

import pytest

import pokemon_red_completion.red_paid_safari_departure as module
from pokemon_red_completion.goal_manager import GoalDecisionOutcome
from pokemon_red_completion.red_autonomous_player import AutonomousSnapshot


def test_search_reserves_longer_exit_from_either_patrol_endpoint(monkeypatch):
    @dataclass
    class Start:
        map_id: int = 218
        at: tuple = (31, 28)

    start = Start()
    patrol = NS(map_id=218, first_at=start.at, second_at=(31, 29))
    points = []
    monkeypatch.setattr(module, "Gen1TraversalObserver", lambda *a, **k: NS(observe=lambda: start))

    def plan(current, *_):
        points.append(current.at)
        return NS(steps=(1,) * (51 if current.at == patrol.first_at else 53))

    monkeypatch.setattr(module, "plan_paid_safari_departure", plan)
    assert module.paid_search_step_reserve(None, None, None, patrol) == 71
    assert points == [patrol.first_at, patrol.second_at]
    start.at = (10, 10)
    with pytest.raises(ValueError, match="bound patrol"):
        module.paid_search_step_reserve(None, None, None, patrol)


def route_fixture(monkeypatch):
    start = NS(ready=True, interruption=None, map_id=218, mode="land", last_outside_map=7)
    session = NS(in_safari_zone=True, safari_game_over=False, safari_balls=24, safari_steps=129)
    plan = NS(
        steps=(1,), terminal_map=7, terminal_mode="land", macro_path=NS(maps=(218, 220, 156, 7))
    )
    world = NS(plan_feasible_to_map=lambda source, target: plan)
    reader = NS(read_safari_session_state=lambda: session)
    monkeypatch.setattr(module, "normalize_active_safari_exit_plan", lambda p: p)
    monkeypatch.setattr(module, "_supported_plan", lambda p, **kw: True)
    monkeypatch.setattr(
        module, "safari_departure_within_steps", lambda p, r: session.safari_steps > 70
    )
    return start, session, plan, world, reader


def test_step_safe_native_route_available_without_actions(monkeypatch):
    start, _, plan, world, reader = route_fixture(monkeypatch)
    assert module.plan_paid_safari_departure(start, world, reader) is plan


@pytest.mark.parametrize(
    "target,key,value",
    [
        ("start", "ready", False),
        ("start", "interruption", "wild_battle"),
        ("start", "map_id", 7),
        ("start", "mode", "unsupported"),
        ("start", "last_outside_map", 1),
        ("session", "in_safari_zone", False),
        ("session", "safari_game_over", True),
        ("session", "safari_steps", 70),
        ("session", "safari_balls", 0),
        ("plan", "terminal_map", 8),
        ("plan", "terminal_mode", "water"),
        ("plan", "steps", ()),
        ("plan", "macro_path", NS(maps=(218, 99, 7))),
    ],
)
def test_reject_unsafe_or_unsupported_departure(monkeypatch, target, key, value):
    start, session, plan, world, reader = route_fixture(monkeypatch)
    setattr(dict(start=start, session=session, plan=plan)[target], key, value)
    with pytest.raises(ValueError, match="paid Safari departure"):
        module.plan_paid_safari_departure(start, world, reader)


def facts(active=True):
    return dict(
        cash=1500,
        owned_species=["a"],
        registered_species=1,
        specimen_counts={"a": 1},
        specimens=1,
        bag_items=[],
        party_hp=[50],
        party_pp=[[10]],
        party_training=[[1, 66, 1000]],
        map_id=218 if active else 7,
        position_yx=[1, 2],
        battle_state=0,
        input_ready=True,
        session=dict(
            in_safari_zone=active,
            safari_game_over=False,
            safari_balls=24,
            safari_steps=129 if active else 80,
        ),
        actions=0 if active else 100,
        frames=0 if active else 10000,
    )


def run(tmp_path, *, error=None, change=None):
    before = AutonomousSnapshot(b"before", facts(), True)
    terminal_facts = facts(False)
    if change:
        terminal_facts.update(change)
    terminal = AutonomousSnapshot(b"terminal", terminal_facts, True)
    current = [before]

    def execute():
        current[0] = terminal
        if error:
            raise error
        return NS(evidence={"passed": True})

    binding = NS(
        binding_ref="exit",
        execute=execute,
        verify=lambda report: NS(status=GoalDecisionOutcome.SUCCEEDED),
    )
    provenance = dict(
        parent_state_sha256=before.sha256, maximum_actions=2000, maximum_frames=240000
    )
    result = module.run_paid_safari_departure(
        output=tmp_path / "run",
        snapshot=lambda: current[0],
        binding=binding,
        route={},
        provenance=provenance,
    )
    return result, json.loads((tmp_path / "run/plan.json").read_bytes())


def test_exit_is_mechanical_nonlearning_and_reusable_as_parent(tmp_path):
    result, parent = run(tmp_path)
    assert result["status"] == "complete"
    assert result["model_queries"] == result["extra_payment"] == 0
    assert result["outcome"]["learning_eligible"] is False
    module.verify_departure_parent(parent, result["outcome"], {"prior_result": json.dumps(result)})
    assert (tmp_path / "run/terminal.state").read_bytes() == b"terminal"
    with pytest.raises(FileExistsError):
        run(tmp_path)


def test_execution_failure_retains_actual_terminal_and_cannot_be_admitted(tmp_path):
    result, parent = run(tmp_path, error=RuntimeError("route did not settle"))
    assert result["status"] == "failed"
    assert result["outcome"]["error_chain"][0]["error_type"] == "RuntimeError"
    assert (tmp_path / "run/terminal.state").read_bytes() == b"terminal"
    with pytest.raises(ValueError):
        module.verify_departure_parent(
            parent, result["outcome"], {"prior_result": json.dumps(result)}
        )


@pytest.mark.parametrize(
    "key,value",
    [
        ("cash", 1000),
        ("specimens", 0),
        ("party_hp", [49]),
        ("party_training", []),
        ("owned_species", []),
        ("map_id", 8),
        ("battle_state", 1),
        ("input_ready", False),
    ],
)
def test_resource_or_boundary_changes_fail_and_are_retained(tmp_path, key, value):
    result, _ = run(tmp_path, change={key: value})
    assert result["status"] == "failed"
    assert result["outcome"]["after"][key] == value


@pytest.mark.parametrize("key,value", [("actions", 2001), ("frames", 240001), ("actions", True)])
def test_parent_cannot_hide_exceeded_bound(tmp_path, key, value):
    result, parent = run(tmp_path)
    result["outcome"]["after"][key] = value
    with pytest.raises(ValueError, match="exceeds"):
        module.verify_departure_parent(
            parent, result["outcome"], {"prior_result": json.dumps(result)}
        )


def test_interrupt_retains_state_before_reraising(tmp_path):
    with pytest.raises(KeyboardInterrupt):
        run(tmp_path, error=KeyboardInterrupt())
    assert (tmp_path / "run/terminal.state").read_bytes() == b"terminal"
    assert json.loads((tmp_path / "run/result.json").read_bytes())["status"] == "failed"
