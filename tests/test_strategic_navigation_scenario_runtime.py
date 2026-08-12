from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.captured_progress import CapturedProgressEnvelope
from pokemon_red_completion.global_router import MacroGraph
from pokemon_red_completion.local_router import (
    LocalEdge,
    LocalGraph,
    LocalRouterError,
    find_local_path,
)
from pokemon_red_completion.private_artifacts import (
    PrivateArtifactError,
    initialize_private_root,
)
from pokemon_red_completion.red_trajectory import POKEMON_RED_GAME_ID
from pokemon_red_completion.route_executor import (
    RouteExecutionError,
    RouteExecutionLimits,
    TraversalSnapshot,
)
from pokemon_red_completion.route_plan import (
    RoutePlan,
    RoutePlanningError,
    plan_route,
    without_warp_transit,
)
from pokemon_red_completion.strategic_navigation import DestinationUnavailableReason
from pokemon_red_completion.strategic_navigation_binding import DestinationRouteBinding
from pokemon_red_completion.strategic_navigation_protocol import (
    STRATEGIC_NAVIGATION_REGISTRY_RELATIVE_PATH,
    parse_strategic_navigation_registry,
)
from pokemon_red_completion.strategic_navigation_scenario_routes import (
    scenario_destination_specs,
)
from pokemon_red_completion.strategic_navigation_scenario_runtime import (
    StrategicScenarioRouteWorld,
    StrategicScenarioRuntimeError,
    record_strategic_scenario_rehearsal,
    require_executable_scenario_bindings,
)
from pokemon_red_completion.strategic_navigation_scenarios import (
    load_strategic_navigation_scenario_registry,
)
from pokemon_red_completion.trajectory import SemanticSnapshot

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class _World:
    at: tuple[int, int] = (0, 0)
    decision_seen_before_action: bool = False
    private_root: object | None = None
    episode_id: str | None = None
    acknowledge: bool = True

    def observe(self) -> TraversalSnapshot:
        return TraversalSnapshot(map_id=1, at=self.at, ready=True)

    def execute(self, action: MacroAction) -> object:
        if not self.decision_seen_before_action:
            assert self.private_root is not None
            assert self.episode_id is not None
            partial = Path(self.private_root) / f"{self.episode_id}.partial"
            decisions = partial / "decisions.jsonl"
            self.decision_seen_before_action = decisions.is_file()
        if action.kind is MacroActionKind.MOVE and self.acknowledge:
            self.at = (0, self.at[1] + 1)
        return action


class _SnapshotProvider:
    def snapshot(self) -> SemanticSnapshot:
        return SemanticSnapshot(
            game_id=POKEMON_RED_GAME_ID,
            mode="overworld",
            facts=("need:advance_story",),
            features={"candidate_count": 2},
        )


def _private_store(tmp_path: Path):
    repository = tmp_path / "repository"
    root = tmp_path / "private"
    repository.mkdir()
    root.mkdir()

    def device_id(path: Path) -> int:
        return 2 if path == root.resolve() else 1

    store = initialize_private_root(
        root,
        repository_root=repository,
        device_id=device_id,
        git_worktree_probe=lambda _path: False,
    )
    return root, store


def _fixture(tmp_path: Path):
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    scenario = registry.learning_scenarios()[0]
    execution = parse_strategic_navigation_registry(
        (PROJECT_ROOT / STRATEGIC_NAVIGATION_REGISTRY_RELATIVE_PATH).read_bytes()
    ).execution
    execution = replace(execution, source_commit="a" * 40)
    capture = CapturedProgressEnvelope(
        state_sha256="b" * 64,
        checkpoint_id="scenario-runtime-fixture",
        checkpoint_label="private scenario boundary",
        checkpoints_completed=7,
        checkpoints_total=40,
        verified_objective_ids=scenario.completed_objective_ids,
    )
    assignment = registry.rehearsal_assignment(
        scenario.scenario_id,
        capture=capture,
        execution=execution,
    )
    specs = scenario_destination_specs(registry, scenario.scenario_id)
    graph = LocalGraph(
        {
            (0, 0): (LocalEdge((0, 1), action="right"),),
            (0, 1): (LocalEdge((0, 2), action="right"),),
            (0, 2): (),
        }
    )
    macro = MacroGraph({1: ()})
    plans = (
        plan_route(macro, {1: graph}, 1, (0, 0), 1, goal_at=(0, 2)),
        plan_route(macro, {1: graph}, 1, (0, 0), 1, goal_at=(0, 1)),
    )
    bindings = tuple(
        DestinationRouteBinding.available(
            spec.destination_ref,
            spec.semantic_tags,
            plan,
        )
        for spec, plan in zip(specs, plans, strict=True)
    )
    root, store = _private_store(tmp_path)
    world = _World(private_root=root, episode_id=assignment.episode_id)
    return scenario, assignment, specs, bindings, store, world


def test_rehearsal_records_before_action_and_strictly_reloads_one_choice(
    tmp_path: Path,
) -> None:
    scenario, assignment, specs, bindings, store, world = _fixture(tmp_path)
    selected = require_executable_scenario_bindings(scenario, specs, bindings)

    result = record_strategic_scenario_rehearsal(
        store,
        assignment=assignment,
        scenario=scenario,
        metadata=assignment.episode_metadata(),
        snapshot_provider=_SnapshotProvider(),
        action_delegate=world,
        traversal_observer=world,
        bindings=bindings,
        selected_destination_ref=selected,
    )

    assert world.decision_seen_before_action
    assert result.report.passed
    assert len(result.dataset.examples) == 1
    assert result.dataset.partition == "unassigned"
    assert result.dataset.examples[0].outcome_status.value == "succeeded"
    assert result.public_dict()["dataset"]["teacher_choice_examples"] == 1
    with pytest.raises(PrivateArtifactError, match="already present"):
        record_strategic_scenario_rehearsal(
            store,
            assignment=assignment,
            scenario=scenario,
            metadata=assignment.episode_metadata(),
            snapshot_provider=_SnapshotProvider(),
            action_delegate=world,
            traversal_observer=world,
            bindings=bindings,
            selected_destination_ref=selected,
        )


def test_rehearsal_fails_before_private_write_on_binding_or_teacher_drift(
    tmp_path: Path,
) -> None:
    scenario, assignment, specs, bindings, store, world = _fixture(tmp_path)
    unavailable = DestinationRouteBinding.unavailable(
        bindings[1].destination_ref,
        bindings[1].semantic_tags,
        DestinationUnavailableReason.PLANNER_NO_ROUTE,
    )
    with pytest.raises(StrategicScenarioRuntimeError, match="unavailable"):
        require_executable_scenario_bindings(
            scenario,
            specs,
            (bindings[0], unavailable),
        )

    with pytest.raises(StrategicScenarioRuntimeError, match="preregistered teacher"):
        record_strategic_scenario_rehearsal(
            store,
            assignment=assignment,
            scenario=scenario,
            metadata=assignment.episode_metadata(),
            snapshot_provider=_SnapshotProvider(),
            action_delegate=world,
            traversal_observer=world,
            bindings=bindings,
            selected_destination_ref=bindings[1].destination_ref,
        )
    # No one-shot identity was spent by either preflight rejection.
    selected = require_executable_scenario_bindings(scenario, specs, bindings)
    result = record_strategic_scenario_rehearsal(
        store,
        assignment=assignment,
        scenario=scenario,
        metadata=assignment.episode_metadata(),
        snapshot_provider=_SnapshotProvider(),
        action_delegate=world,
        traversal_observer=world,
        bindings=bindings,
        selected_destination_ref=selected,
    )
    assert result.report.passed


def test_failed_route_consumes_one_outcome_and_cannot_be_retried(tmp_path: Path) -> None:
    scenario, assignment, specs, bindings, store, world = _fixture(tmp_path)
    world.acknowledge = False
    selected = require_executable_scenario_bindings(scenario, specs, bindings)

    with pytest.raises(RouteExecutionError):
        record_strategic_scenario_rehearsal(
            store,
            assignment=assignment,
            scenario=scenario,
            metadata=assignment.episode_metadata(),
            snapshot_provider=_SnapshotProvider(),
            action_delegate=world,
            traversal_observer=world,
            bindings=bindings,
            selected_destination_ref=selected,
            limits=RouteExecutionLimits(
                max_step_attempts=1,
                replan_after_unchanged=1,
            ),
        )

    assert store.inspect_episode_state(assignment.episode_id).status == "failed"
    root = Path(world.private_root)  # type: ignore[arg-type]
    events_path = root / f"{assignment.episode_id}.failed.partial" / "events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="ascii").splitlines()]
    outcomes = [
        row
        for row in events
        if row.get("kind") == "strategic_navigation_outcome"
    ]
    assert len(outcomes) == 1
    assert outcomes[0]["payload"]["status"] == "failed"

    with pytest.raises(PrivateArtifactError, match="already present"):
        record_strategic_scenario_rehearsal(
            store,
            assignment=assignment,
            scenario=scenario,
            metadata=assignment.episode_metadata(),
            snapshot_provider=_SnapshotProvider(),
            action_delegate=world,
            traversal_observer=world,
            bindings=bindings,
            selected_destination_ref=selected,
        )


def test_origin_relocation_selects_the_cheapest_reachable_declared_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = object.__new__(StrategicScenarioRouteWorld)
    plans = {
        7: cast(
            RoutePlan,
            SimpleNamespace(cost=19, terminal_map=7, terminal_at=(3, 4), actions=("up",)),
        ),
        9: cast(
            RoutePlan,
            SimpleNamespace(cost=11, terminal_map=9, terminal_at=(8, 2), actions=("left",)),
        ),
    }

    def plan(_self: object, _start: TraversalSnapshot, goal_map: int) -> RoutePlan:
        if goal_map == 8:
            raise RoutePlanningError("unreachable fixture")
        return plans[goal_map]

    monkeypatch.setattr(StrategicScenarioRouteWorld, "_plan_candidate", plan)

    selected = world.plan_to_any_map(
        TraversalSnapshot(map_id=1, at=(0, 0), ready=True),
        frozenset({7, 8, 9}),
    )

    assert selected is plans[9]


def test_origin_relocation_rejects_an_empty_goal_set() -> None:
    world = object.__new__(StrategicScenarioRouteWorld)

    with pytest.raises(TypeError, match="relocation goals"):
        world.plan_to_any_map(
            TraversalSnapshot(map_id=1, at=(0, 0), ready=True),
            frozenset(),
        )


def test_skill_relocation_preserves_the_exact_declared_coordinate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = object.__new__(StrategicScenarioRouteWorld)
    expected = cast(RoutePlan, SimpleNamespace())
    calls: list[tuple[int, tuple[int, int] | None]] = []

    def plan(
        _self: object,
        _start: TraversalSnapshot,
        goal_map: int,
        *,
        goal_at: tuple[int, int] | None = None,
    ) -> RoutePlan:
        calls.append((goal_map, goal_at))
        return expected

    monkeypatch.setattr(StrategicScenarioRouteWorld, "_plan_candidate", plan)

    actual = world.plan_to_map(
        TraversalSnapshot(map_id=1, at=(0, 0), ready=True),
        6,
        goal_at=(3, 3),
    )

    assert actual is expected
    assert calls == [(6, (3, 3))]


def test_unrelated_warp_is_an_endpoint_not_a_local_shortcut() -> None:
    graph = LocalGraph(
        {
            (0, 0): (LocalEdge((0, 1), "right"),),
            (0, 1): (
                LocalEdge((0, 0), "left"),
                LocalEdge((0, 2), "right"),
            ),
            (0, 2): (LocalEdge((0, 1), "left"),),
        }
    )
    projected = without_warp_transit(
        graph,
        ((0, 1),),
        start_at=(0, 0),
    )

    assert projected.edges[(0, 1)] == ()
    with pytest.raises(LocalRouterError, match="no permitted local route"):
        find_local_path(projected, (0, 0), (0, 2))

    arriving = without_warp_transit(
        graph,
        ((0, 1),),
        start_at=(0, 1),
    )
    assert find_local_path(arriving, (0, 1), (0, 2)).coordinates == (
        (0, 1),
        (0, 2),
    )
