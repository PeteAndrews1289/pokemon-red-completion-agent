from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from pokemon_red_completion.constants import POKEMON_RED_US_REV_0
from pokemon_red_completion.global_router import MacroGraph
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.route_plan import plan_route
from pokemon_red_completion.strategic_navigation import (
    DestinationUnavailableReason,
)
from pokemon_red_completion.strategic_navigation_binding import (
    DestinationRouteBinding,
)
from pokemon_red_completion.strategic_navigation_model import (
    STRATEGIC_NAVIGATION_FEATURE_NAMES,
    StrategicNavigationLinear,
)
from pokemon_red_completion.strategic_navigation_protocol import (
    STRATEGIC_NAVIGATION_ADAPTER_ID,
    STRATEGIC_NAVIGATION_GAME_ID,
)
from pokemon_red_completion.strategic_navigation_scenario_routes import (
    STRATEGIC_SCENARIO_DESTINATIONS,
)
from pokemon_red_completion.strategic_navigation_scenarios import (
    StrategicNavigationScenario,
    load_strategic_navigation_scenario_registry,
)
from pokemon_red_completion.strategic_navigation_sealed_adapter import (
    StrategicSealedAdapterError,
    StrategicSealedCartridgeCaseRunner,
    StrategicSealedCartridgeTeacherEvidence,
    prepare_strategic_navigation_predictions,
    strategic_sealed_scenario_assignment_id,
)
from pokemon_red_completion.strategic_navigation_sealed_catalog import (
    STRATEGIC_SEALED_CASE_CATALOG_ENTRY_SCHEMA,
    STRATEGIC_SEALED_CASE_CATALOG_SCHEMA,
    STRATEGIC_SEALED_EXECUTION_CONFIGURATION_SHA256,
    parse_strategic_sealed_case_catalog,
)
from pokemon_red_completion.strategic_navigation_sealed_evaluation import (
    StrategicSealedCandidateUnavailableError,
    build_strategic_sealed_authorization,
    load_strategic_sealed_evaluation_plan,
    parse_strategic_sealed_authorization,
    require_strategic_sealed_runtime_preflight,
)
from pokemon_red_completion.strategic_navigation_trajectory import (
    ordered_strategic_navigation_bindings,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTERNAL_AUDIT_RECEIPT_SHA256 = "3" * 64
NON_TEST_ADAPTER_QUALIFICATION_RECEIPT_SHA256 = "4" * 64


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _catalog_document() -> dict[str, object]:
    plan = load_strategic_sealed_evaluation_plan(PROJECT_ROOT)
    return {
        "adapter_id": STRATEGIC_NAVIGATION_ADAPTER_ID,
        "cases": [
            {
                "capture": {
                    "checkpoint_id": f"sealed-adapter-fixture-{case.ordinal:02d}",
                    "envelope_sha256": f"{case.ordinal + 100:064x}",
                    "state_bytes": 100_000 + case.ordinal,
                    "state_sha256": f"{case.ordinal:064x}",
                },
                "case_id": case.case_id,
                "case_sha256": case.case_sha256,
                "ordinal": case.ordinal,
                "schema": STRATEGIC_SEALED_CASE_CATALOG_ENTRY_SCHEMA,
                "source_scenario_id": case.source_scenario_id,
                "source_scenario_sha256": case.source_scenario_sha256,
            }
            for case in plan.cases
        ],
        "evaluation_id": plan.evaluation_id,
        "execution_configuration_sha256": (
            STRATEGIC_SEALED_EXECUTION_CONFIGURATION_SHA256
        ),
        "game_id": STRATEGIC_NAVIGATION_GAME_ID,
        "plan_sha256": plan.plan_sha256,
        "rom_identity": {
            "sha1": POKEMON_RED_US_REV_0.sha1,
            "sha256": POKEMON_RED_US_REV_0.sha256,
            "size_bytes": POKEMON_RED_US_REV_0.size_bytes,
            "title": POKEMON_RED_US_REV_0.title,
        },
        "runtime_sha256": "c" * 64,
        "schema": STRATEGIC_SEALED_CASE_CATALOG_SCHEMA,
        "source_scenario_registry_sha256": plan.source_scenario_registry_sha256,
        "teacher_execution_sha256": plan.teacher_execution_sha256,
    }


class _Model:
    def __init__(self, probabilities: tuple[float, ...]) -> None:
        self.values = np.asarray(probabilities, dtype=np.float64)
        self.inputs: list[object] = []

    def probabilities(self, example: object) -> np.ndarray:
        self.inputs.append(example)
        return self.values.copy()

    def predict(self, example: object) -> int:
        return int(np.argmax(self.probabilities(example)))

    def to_dict(self) -> dict[str, object]:
        return {"fixture": "sealed-adapter-model"}


class _Session:
    def __init__(
        self,
        assignment_id: str,
        bindings: tuple[DestinationRouteBinding, ...],
        teacher_ref: str,
        events: list[str],
        *,
        evidence: StrategicSealedCartridgeTeacherEvidence | None = None,
    ) -> None:
        self.assignment_id = assignment_id
        self.bindings = bindings
        self.teacher_ref = teacher_ref
        self.events = events
        self.evidence = evidence

    def execute_teacher(self) -> StrategicSealedCartridgeTeacherEvidence:
        self.events.append("teacher")
        return self.evidence or StrategicSealedCartridgeTeacherEvidence(
            execution_status="succeeded",
            selected_destination_ref=self.teacher_ref,
            episode_manifest_sha256="e" * 64,
        )

    def close(self) -> None:
        self.events.append("close")


class _Factory:
    def __init__(
        self,
        *,
        plan_sha256: str,
        authorization_sha256: str,
        case_catalog_sha256: str,
        assignment_id: str,
        bindings: tuple[DestinationRouteBinding, ...],
        teacher_ref: str,
        evidence: StrategicSealedCartridgeTeacherEvidence | None = None,
    ) -> None:
        self.plan_sha256 = plan_sha256
        self.authorization_sha256 = authorization_sha256
        self.case_catalog_sha256 = case_catalog_sha256
        self.assignment_id = assignment_id
        self.runtime_sha256 = "c" * 64
        self.bindings = bindings
        self.teacher_ref = teacher_ref
        self.evidence = evidence
        self.events: list[str] = []

    def open_case(self, case: object, entry: object, scenario: object) -> _Session:
        self.events.append("open")
        return _Session(
            self.assignment_id,
            self.bindings,
            self.teacher_ref,
            self.events,
            evidence=self.evidence,
        )


def _bindings(
    *,
    costs: tuple[int, ...] | None = None,
) -> tuple[DestinationRouteBinding, ...]:
    plan = load_strategic_sealed_evaluation_plan(PROJECT_ROOT)
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    case = plan.cases[0]
    scenario = next(
        item for item in registry.scenarios if item.scenario_id == case.source_scenario_id
    )
    return _bindings_for_scenario(scenario, costs=costs)


def _bindings_for_scenario(
    scenario: StrategicNavigationScenario,
    *,
    costs: tuple[int, ...] | None = None,
) -> tuple[DestinationRouteBinding, ...]:
    route_costs = costs or tuple(
        range(1, len(scenario.candidate_objective_ids) + 1)
    )
    maximum = max(route_costs)
    graph = LocalGraph(
        {
            (0, index): (
                (LocalEdge((0, index + 1), action="right"),)
                if index < maximum
                else ()
            )
            for index in range(maximum + 1)
        }
    )
    macro = MacroGraph({1: ()})
    result = []
    for objective_id, cost in zip(
        scenario.candidate_objective_ids,
        route_costs,
        strict=True,
    ):
        spec = STRATEGIC_SCENARIO_DESTINATIONS[objective_id]
        result.append(
            DestinationRouteBinding.available(
                spec.destination_ref,
                spec.semantic_tags,
                plan_route(
                    macro,
                    {1: graph},
                    1,
                    (0, 0),
                    1,
                    goal_at=(0, cost),
                ),
            )
        )
    return tuple(result)


def _linear_model() -> StrategicNavigationLinear:
    width = len(STRATEGIC_NAVIGATION_FEATURE_NAMES)
    enabled = tuple(
        f"candidate.{metric}.relative_rank"
        for metric in (
            "route_cost",
            "route_steps",
            "map_transitions",
            "field_actions",
            "mode_changes",
        )
    )
    return StrategicNavigationLinear(
        weights=np.zeros(width, dtype=np.float64),
        feature_mean=np.zeros(width, dtype=np.float64),
        feature_scale=np.ones(width, dtype=np.float64),
        enabled_feature_names=enabled,
        feature_set_id="relative_route",
        l2=0.1,
        training_epochs=600,
    )


def _runner(
    monkeypatch: pytest.MonkeyPatch,
    *,
    probabilities: tuple[float, ...] = (0.2, 0.8),
    bindings: tuple[DestinationRouteBinding, ...] | None = None,
    evidence: StrategicSealedCartridgeTeacherEvidence | None = None,
) -> tuple[
    StrategicSealedCartridgeCaseRunner,
    list[object],
    _Factory,
    object,
    object,
]:
    plan = load_strategic_sealed_evaluation_plan(PROJECT_ROOT)
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    catalog = parse_strategic_sealed_case_catalog(
        _canonical(_catalog_document()),
        plan=plan,
        scenario_registry=registry,
    )
    authorization = parse_strategic_sealed_authorization(
        build_strategic_sealed_authorization(
            plan,
            authorization_id="sealed-adapter-fixture",
            authorized_by="test-owner",
            authorized_on="2026-08-13",
            source_commit="a" * 40,
            case_catalog_sha256=catalog.catalog_sha256,
            external_audit_receipt_sha256=EXTERNAL_AUDIT_RECEIPT_SHA256,
            non_test_adapter_qualification_receipt_sha256=(
                NON_TEST_ADAPTER_QUALIFICATION_RECEIPT_SHA256
            ),
        ),
        plan=plan,
    )
    grant = require_strategic_sealed_runtime_preflight(
        plan,
        authorization,
        source_commit=authorization.source_commit,
        source_bundle_sha256=plan.execution_source_bundle_sha256,
        source_clean=True,
        source_published=True,
        model_canonical_sha256=plan.model_canonical_sha256,
        model_file_sha256=plan.model_file_sha256,
        teacher_execution_sha256=plan.teacher_execution_sha256,
        case_catalog_sha256=catalog.catalog_sha256,
        external_audit_receipt_sha256=EXTERNAL_AUDIT_RECEIPT_SHA256,
        non_test_adapter_qualification_receipt_sha256=(
            NON_TEST_ADAPTER_QUALIFICATION_RECEIPT_SHA256
        ),
    )
    case = plan.cases[0]
    scenario = next(
        item for item in registry.scenarios if item.scenario_id == case.source_scenario_id
    )
    model = _linear_model()
    model_inputs: list[object] = []

    def fixture_probabilities(
        self: StrategicNavigationLinear,
        example: object,
    ) -> np.ndarray:
        model_inputs.append(example)
        return np.asarray(probabilities, dtype=np.float64)

    monkeypatch.setattr(
        StrategicNavigationLinear,
        "probabilities",
        fixture_probabilities,
    )
    entry = catalog.cases[0]
    assignment_id = strategic_sealed_scenario_assignment_id(
        entry=entry,
        scenario=scenario,
        registry_sha256=registry.registry_sha256,
        source_bundle_sha256=plan.execution_source_bundle_sha256,
        teacher_execution_sha256=plan.teacher_execution_sha256,
        source_commit=authorization.source_commit,
    )
    factory = _Factory(
        plan_sha256=plan.plan_sha256,
        authorization_sha256=authorization.authorization_sha256,
        case_catalog_sha256=catalog.catalog_sha256,
        assignment_id=assignment_id,
        bindings=bindings or _bindings(),
        teacher_ref=(
            f"pokemon.red:objective:{scenario.teacher_objective_id}:approach"
        ),
        evidence=evidence,
    )
    monkeypatch.setattr(
        "pokemon_red_completion.strategic_navigation_sealed_adapter."
        "canonical_strategic_navigation_model_sha256",
        lambda value: plan.model_canonical_sha256,
    )
    runner = StrategicSealedCartridgeCaseRunner(
        plan=plan,
        authorization=authorization,
        runtime_grant=grant,
        catalog=catalog,
        scenario_registry=registry,
        model=model,
        session_factory=factory,
    )
    return runner, model_inputs, factory, plan, scenario


def test_adapter_prepares_unlabeled_predictions_before_teacher_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner, model_inputs, factory, plan, scenario = _runner(monkeypatch)
    case = plan.cases[0]

    prediction = runner.prepare(case)

    assert factory.events == ["open"]
    assert len(model_inputs) == 1
    assert not hasattr(model_inputs[0], "selected_candidate_index")
    assert not hasattr(model_inputs[0], "outcome_status")
    assert prediction.model_prediction_tied is False
    assert prediction.model_prediction_index == 1
    ordered = ordered_strategic_navigation_bindings(
        factory.assignment_id,
        0,
        factory.bindings,
    )
    assert prediction.baseline_prediction_index == next(
        index for index, binding in enumerate(ordered) if binding.plan.cost == 1
    )

    teacher = runner.execute_teacher(case)

    assert factory.events == ["open", "teacher", "close"]
    teacher_ref = f"pokemon.red:objective:{scenario.teacher_objective_id}:approach"
    assert teacher.teacher_target_index == tuple(
        binding.destination_ref for binding in ordered
    ).index(teacher_ref)
    assert teacher.episode_manifest_sha256 == "e" * 64


def test_adapter_surfaces_model_and_baseline_ties_as_incorrect_choices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner, _, _, plan, _ = _runner(
        monkeypatch,
        probabilities=(0.5, 0.5),
        bindings=_bindings(costs=(1, 1)),
    )

    prediction = runner.prepare(plan.cases[0])

    assert prediction.model_prediction_index is None
    assert prediction.model_prediction_tied is True
    assert prediction.baseline_prediction_index is None
    assert prediction.baseline_prediction_tied is True


def test_adapter_refuses_unavailable_candidates_and_closes_the_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bindings = list(_bindings())
    unavailable = bindings[1]
    bindings[1] = DestinationRouteBinding.unavailable(
        unavailable.destination_ref,
        unavailable.semantic_tags,
        DestinationUnavailableReason.PLANNER_NO_ROUTE,
    )
    runner, _, factory, plan, _ = _runner(
        monkeypatch,
        bindings=tuple(bindings),
    )

    with pytest.raises(StrategicSealedCandidateUnavailableError):
        runner.prepare(plan.cases[0])

    assert factory.events == ["open", "close"]
    with pytest.raises(StrategicSealedAdapterError, match="cannot be reopened"):
        runner.prepare(plan.cases[0])


def test_adapter_refuses_teacher_before_prediction_and_wrong_teacher_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrong = StrategicSealedCartridgeTeacherEvidence(
        execution_status="succeeded",
        selected_destination_ref="pokemon.red:objective:not-the-teacher:approach",
        episode_manifest_sha256="e" * 64,
    )
    runner, _, factory, plan, _ = _runner(monkeypatch, evidence=wrong)

    with pytest.raises(StrategicSealedAdapterError, match="lacks its active"):
        runner.execute_teacher(plan.cases[0])
    runner.prepare(plan.cases[0])
    with pytest.raises(StrategicSealedAdapterError, match="non-preregistered"):
        runner.execute_teacher(plan.cases[0])

    assert factory.events == ["open", "teacher", "close"]


def test_adapter_abort_closes_a_prepared_session_without_teacher_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner, _, factory, plan, _ = _runner(monkeypatch)
    case = plan.cases[0]
    runner.prepare(case)

    runner.abort(case)

    assert factory.events == ["open", "close"]
    with pytest.raises(StrategicSealedAdapterError, match="lacks its active"):
        runner.execute_teacher(case)


def test_adapter_refuses_candidate_order_nonce_drift_and_closes_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner, _, factory, plan, _ = _runner(monkeypatch)
    factory.assignment_id = "f" * 64

    with pytest.raises(StrategicSealedAdapterError, match="assignment identity differs"):
        runner.prepare(plan.cases[0])

    assert factory.events == ["open", "close"]


@pytest.mark.parametrize(
    "probabilities",
    (
        (0.2,),
        (float("nan"), 0.5),
        (-0.1, 1.1),
        (0.2, 0.2),
    ),
)
def test_adapter_rejects_invalid_model_probability_vectors(
    monkeypatch: pytest.MonkeyPatch,
    probabilities: tuple[float, ...],
) -> None:
    runner, _, factory, plan, _ = _runner(
        monkeypatch,
        probabilities=probabilities,
    )

    with pytest.raises(StrategicSealedAdapterError, match="probabilities"):
        runner.prepare(plan.cases[0])

    assert factory.events == ["open", "close"]


def test_adapter_rejects_a_factory_identity_before_opening_any_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = load_strategic_sealed_evaluation_plan(PROJECT_ROOT)
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    catalog = parse_strategic_sealed_case_catalog(
        _canonical(_catalog_document()),
        plan=plan,
        scenario_registry=registry,
    )
    authorization = parse_strategic_sealed_authorization(
        build_strategic_sealed_authorization(
            plan,
            authorization_id="sealed-adapter-identity-fixture",
            authorized_by="test-owner",
            authorized_on="2026-08-13",
            source_commit="a" * 40,
            case_catalog_sha256=catalog.catalog_sha256,
            external_audit_receipt_sha256=EXTERNAL_AUDIT_RECEIPT_SHA256,
            non_test_adapter_qualification_receipt_sha256=(
                NON_TEST_ADAPTER_QUALIFICATION_RECEIPT_SHA256
            ),
        ),
        plan=plan,
    )
    grant = require_strategic_sealed_runtime_preflight(
        plan,
        authorization,
        source_commit=authorization.source_commit,
        source_bundle_sha256=plan.execution_source_bundle_sha256,
        source_clean=True,
        source_published=True,
        model_canonical_sha256=plan.model_canonical_sha256,
        model_file_sha256=plan.model_file_sha256,
        teacher_execution_sha256=plan.teacher_execution_sha256,
        case_catalog_sha256=catalog.catalog_sha256,
        external_audit_receipt_sha256=EXTERNAL_AUDIT_RECEIPT_SHA256,
        non_test_adapter_qualification_receipt_sha256=(
            NON_TEST_ADAPTER_QUALIFICATION_RECEIPT_SHA256
        ),
    )
    scenario = next(
        item
        for item in registry.scenarios
        if item.scenario_id == plan.cases[0].source_scenario_id
    )
    factory = _Factory(
        plan_sha256="f" * 64,
        authorization_sha256=authorization.authorization_sha256,
        case_catalog_sha256=catalog.catalog_sha256,
        assignment_id="d" * 64,
        bindings=_bindings(),
        teacher_ref=(
            f"pokemon.red:objective:{scenario.teacher_objective_id}:approach"
        ),
    )
    monkeypatch.setattr(
        "pokemon_red_completion.strategic_navigation_sealed_adapter."
        "canonical_strategic_navigation_model_sha256",
        lambda value: plan.model_canonical_sha256,
    )

    with pytest.raises(TypeError, match="frozen strategic linear scorer"):
        StrategicSealedCartridgeCaseRunner(
            plan=plan,
            authorization=authorization,
            runtime_grant=grant,
            catalog=catalog,
            scenario_registry=registry,
            model=_Model((0.2, 0.8)),
            session_factory=factory,
        )
    assert factory.events == []

    with pytest.raises(StrategicSealedAdapterError, match="factory identity"):
        StrategicSealedCartridgeCaseRunner(
            plan=plan,
            authorization=authorization,
            runtime_grant=grant,
            catalog=catalog,
            scenario_registry=registry,
                model=_linear_model(),
            session_factory=factory,
        )

    assert factory.events == []


def test_prediction_boundary_qualifies_all_36_non_test_scenario_shapes() -> None:
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    observed_candidate_counts: set[int] = set()

    class ShapeModel:
        def __init__(self) -> None:
            self.inputs: list[object] = []

        def probabilities(self, example: object) -> np.ndarray:
            self.inputs.append(example)
            candidates = example.candidates
            weights = np.arange(1, len(candidates) + 1, dtype=np.float64)
            return weights / np.sum(weights)

        def predict(self, example: object) -> int:
            return int(np.argmax(self.probabilities(example)))

        def to_dict(self) -> dict[str, object]:
            return {"fixture": "all-non-test-scenario-shapes"}

    model = ShapeModel()
    for scenario in registry.learning_scenarios():
        bindings = _bindings_for_scenario(scenario)
        assignment_id = hashlib.sha256(
            f"qualification:{scenario.scenario_id}".encode("ascii")
        ).hexdigest()

        prepared = prepare_strategic_navigation_predictions(
            model,
            assignment_id=assignment_id,
            bindings=bindings,
        )

        observed_candidate_counts.add(len(bindings))
        assert set(prepared.ordered_destination_refs) == {
            binding.destination_ref for binding in bindings
        }
        assert prepared.model_prediction_tied is False
        assert prepared.baseline_prediction_tied is False
        assert len(prepared.policy_input_sha256) == 64

    assert len(model.inputs) == 36
    assert observed_candidate_counts == {2, 3, 4, 5}
    assert all(
        not hasattr(value, "selected_candidate_index")
        and not hasattr(value, "outcome_status")
        for value in model.inputs
    )
