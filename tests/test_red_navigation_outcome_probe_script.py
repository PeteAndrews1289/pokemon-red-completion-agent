from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.captured_progress import CapturedProgressEnvelope
from pokemon_red_completion.global_router import MacroGraph
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.red_navigation_outcome_probe import (
    build_same_destination_navigation_question,
)
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import plan_route
from pokemon_red_completion.scenario_outcome_adapters import NavigationOutcomeTrial
from pokemon_red_completion.strategic_navigation import (
    NavigationOutcomeStatus,
    StrategicNavigationOutcome,
)
from pokemon_red_completion.strategic_navigation_scenario_runtime import (
    SameDestinationRoutePair,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts" / "run_red_navigation_outcome_probe.py")
)
SCRIPT_GLOBALS = SCRIPT["_run"].__globals__
PLAN_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-local-navigation-outcome-plan-2026-08-14.json"
)


def _route_pair() -> SameDestinationRoutePair:
    macro = MacroGraph({1: ()})
    shortest_graph = LocalGraph(
        {
            (0, 0): (LocalEdge((0, 1), "right"),),
            (0, 1): (
                LocalEdge((0, 0), "left"),
                LocalEdge((0, 2), "right"),
            ),
            (0, 2): (LocalEdge((0, 1), "left"),),
        }
    )
    detour_graph = LocalGraph(
        {
            (0, 0): (LocalEdge((1, 0), "down"),),
            (1, 0): (LocalEdge((1, 1), "right"),),
            (1, 1): (LocalEdge((1, 2), "right"),),
            (1, 2): (LocalEdge((0, 2), "up"),),
            (0, 2): (),
        }
    )
    shortest = plan_route(
        macro,
        {1: shortest_graph},
        1,
        (0, 0),
        1,
        goal_at=(0, 2),
    )
    detour = plan_route(
        macro,
        {1: detour_graph},
        1,
        (0, 0),
        1,
        goal_at=(0, 2),
    )
    return SameDestinationRoutePair(
        shortest,
        detour,
        excluded_step_ordinal=1,
        excluded_map=1,
        excluded_at=(0, 1),
    )


def test_public_plan_freezes_one_same_terminal_non_authority_probe() -> None:
    payload = json.loads(PLAN_PATH.read_text(encoding="ascii"))
    encoded = PLAN_PATH.read_text(encoding="ascii")

    assert payload["status"] == "prospective_unexecuted"
    assert payload["candidate_construction"]["candidate_count"] == 2
    assert payload["candidate_construction"]["same_terminal_required"] is True
    assert (
        payload["candidate_construction"]["detour_route"]["route_cost"]
        > payload["candidate_construction"]["shortest_route"]["route_cost"]
    )
    assert payload["execution"]["execute_each_candidate_exactly_once"] is True
    assert payload["interpretation"]["model_fit"] is False
    assert payload["interpretation"]["authority_promotion"] is False
    assert set(payload["protected_access"].values()) == {0}
    assert payload["private_path_fields"] == 0
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


class _Writer:
    def __init__(self) -> None:
        self.opened = False
        self.records: list[tuple[str, dict[str, object]]] = []
        self.summary = SimpleNamespace(
            public_dict=lambda: {
                "artifact_id": "red-local-nav-outcome-test",
                "status": "complete",
            }
        )

    def __enter__(self) -> _Writer:
        self.opened = True
        return self

    def __exit__(self, *args: object) -> None:
        del args
        self.opened = False

    def append(self, stream: str, record: dict[str, object]) -> None:
        assert self.opened
        self.records.append((stream, record))


class _Store:
    def __init__(self) -> None:
        self.writer = _Writer()
        self.artifact_id: str | None = None

    def begin_artifact(self, artifact_id: str, *, kind: str) -> _Writer:
        assert kind == "navigation_outcome_probe"
        self.artifact_id = artifact_id
        return self.writer


class _Emulator:
    def __enter__(self) -> _Emulator:
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def load_state(self, path: Path) -> None:
        assert path.name == "capture.state"


def test_runner_writes_catalog_before_two_one_shot_candidate_outcomes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = tmp_path / "capture.state"
    envelope_path = tmp_path / "capture.state.json"
    rom_path = tmp_path / "red.gb"
    state_path.write_bytes(b"state")
    envelope_path.write_bytes(b"envelope")
    rom_path.write_bytes(b"rom")
    state_sha256 = hashlib.sha256(b"state").hexdigest()
    envelope_sha256 = hashlib.sha256(b"envelope").hexdigest()
    rom_sha256 = hashlib.sha256(b"rom").hexdigest()
    pair = _route_pair()
    question = build_same_destination_navigation_question(
        pair,
        initial_state_sha256=state_sha256,
    )
    plan = {
        "authenticated_root": {
            "state_sha256": state_sha256,
            "capture_envelope_sha256": envelope_sha256,
            "rom_sha256": rom_sha256,
        },
        "candidate_construction": {
            "candidate_order_rule": "state-sha256-high-bit-detour-first-v1",
            "shortest_route": {
                "route_cost": pair.shortest.cost,
                "route_steps": len(pair.shortest.steps),
            },
            "detour_route": {
                "route_cost": pair.detour.cost,
                "route_steps": len(pair.detour.steps),
                "excluded_shortest_step_ordinal": pair.excluded_step_ordinal,
            },
            "expected_shortest_candidate_index": question.shortest_candidate_index,
        },
    }
    capture = CapturedProgressEnvelope(
        state_sha256=state_sha256,
        checkpoint_id="navigation-probe-fixture",
        checkpoint_label="navigation probe fixture",
        checkpoints_completed=2,
        checkpoints_total=40,
        verified_objective_ids=(),
    )
    source = SimpleNamespace(
        git_commit="a" * 40,
        public_dict=lambda: {"git_commit": "a" * 40},
    )
    execution = SimpleNamespace(source_bundle_sha256="b" * 64)
    execution_registry = SimpleNamespace(execution=execution)
    assignment = SimpleNamespace(assignment_id="source-assignment")
    scenario_registry = SimpleNamespace(
        scenario=lambda scenario_id: SimpleNamespace(scenario_id=scenario_id),
        rehearsal_assignment=lambda *args, **kwargs: assignment,
    )
    world = SimpleNamespace(
        rules=SimpleNamespace(cut_block_swaps=()),
        plan_same_destination_pair=lambda *args, **kwargs: pair,
    )
    store = _Store()
    start = TraversalSnapshot(map_id=1, at=(0, 0), ready=True)

    monkeypatch.setitem(SCRIPT_GLOBALS, "detect_source_identity", lambda *a, **k: source)
    monkeypatch.setitem(SCRIPT_GLOBALS, "require_clean_source", lambda value: None)
    monkeypatch.setitem(SCRIPT_GLOBALS, "require_published_source", lambda *a: None)
    monkeypatch.setitem(SCRIPT_GLOBALS, "_load_plan", lambda: (plan, "c" * 64))
    monkeypatch.setitem(SCRIPT_GLOBALS, "load_captured_progress", lambda *a, **k: capture)
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "load_committed_strategic_navigation_registry",
        lambda root: execution_registry,
    )
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "working_source_bundle_sha256",
        lambda root: "b" * 64,
    )
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "load_strategic_navigation_scenario_registry",
        lambda root: scenario_registry,
    )
    monkeypatch.setitem(SCRIPT_GLOBALS, "resolve_rom_path", lambda value: rom_path)
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "verify_rom",
        lambda path: SimpleNamespace(sha256=rom_sha256),
    )
    monkeypatch.setitem(SCRIPT_GLOBALS, "rom_adjacent_artifacts", lambda path: ())
    monkeypatch.setitem(SCRIPT_GLOBALS, "PyBoyAdapter", lambda path: _Emulator())
    monkeypatch.setitem(SCRIPT_GLOBALS, "_observer", lambda *a: (object(), object()))
    monkeypatch.setitem(SCRIPT_GLOBALS, "_stable_start", lambda *a: start)
    monkeypatch.setitem(SCRIPT_GLOBALS, "require_scenario_origin", lambda *a: None)
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "StrategicScenarioRouteWorld",
        SimpleNamespace(from_rom=lambda payload: world),
    )
    monkeypatch.setitem(SCRIPT_GLOBALS, "open_private_root", lambda *a, **k: store)

    def execute_candidate(*, candidate_index: int, question, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        assert store.writer.opened
        assert store.writer.records[0][0] == "catalog"
        assert sum(stream == "trials" for stream, _ in store.writer.records) == (
            candidate_index
        )
        decision = question.decision(
            candidate_index,
            episode_id="red-local-nav-outcome-test",
            root_lineage_id=f"red-local-nav-root-{state_sha256[:16]}",
        )
        route = question.plans[candidate_index]
        outcome = StrategicNavigationOutcome(
            decision_id=decision.decision_id,
            selected_destination_ref=decision.selected_destination_ref,
            status=NavigationOutcomeStatus.SUCCEEDED,
            terminal_reached=True,
            movement_requests=len(route.steps),
            acknowledged_steps=len(route.steps),
            wait_actions=0,
        )
        return (
            NavigationOutcomeTrial(decision, outcome, frames_executed=100),
            {"candidate_index": candidate_index},
        )

    monkeypatch.setitem(SCRIPT_GLOBALS, "_execute_candidate", execute_candidate)
    receipt = SCRIPT["_run"](
        SimpleNamespace(
            state=state_path,
            envelope=envelope_path,
            rom=rom_path,
            private_root=tmp_path,
            exact_ci_run=123,
            execute=True,
        )
    )

    assert receipt["status"] == "complete"
    assert receipt["fully_measured"] is True
    assert receipt["learner_update_eligible"] is True
    assert receipt["authority_promoted"] is False
    assert receipt["model_fit"] is False
    assert [stream for stream, _ in store.writer.records] == [
        "catalog",
        "trials",
        "trials",
        "outcomes",
    ]
    assert store.artifact_id == f"red-local-nav-outcome-{'a' * 12}-{state_sha256[:12]}"


def test_execution_requires_explicit_private_and_ci_bindings() -> None:
    with pytest.raises(
        SCRIPT["RedNavigationOutcomeRunError"],
        match="private root and exact green CI",
    ):
        SCRIPT["_run"](
            SimpleNamespace(
                state=Path("capture.state"),
                envelope=None,
                rom=None,
                private_root=None,
                exact_ci_run=None,
                execute=True,
            )
        )
