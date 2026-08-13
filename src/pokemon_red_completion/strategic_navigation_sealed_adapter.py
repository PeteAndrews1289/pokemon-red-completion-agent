"""Prediction-first adapter between sealed cases and cartridge sessions.

The evaluator durably claims a case before calling :meth:`prepare`.  This
adapter then opens exactly that catalog row, derives the identity-free policy
question, and returns model plus baseline predictions.  The deterministic
teacher remains unreachable until the evaluator has durably committed those
predictions and calls :meth:`execute_teacher`.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from pokemon_red_completion.collection_protocol import collection_document_sha256
from pokemon_red_completion.strategic_navigation import StrategicNavigationTag
from pokemon_red_completion.strategic_navigation_binding import (
    DestinationRouteBinding,
)
from pokemon_red_completion.strategic_navigation_dataset import (
    StrategicNavigationInferenceInput,
)
from pokemon_red_completion.strategic_navigation_model import (
    StrategicNavigationLinear,
    StrategicNavigationScorer,
    canonical_strategic_navigation_model_sha256,
)
from pokemon_red_completion.strategic_navigation_protocol import (
    STRATEGIC_NAVIGATION_SCENARIO_COLLECTION_ID,
    STRATEGIC_NAVIGATION_SCENARIO_REHEARSAL_ASSIGNMENT_SCHEMA,
)
from pokemon_red_completion.strategic_navigation_scenario_routes import (
    STRATEGIC_SCENARIO_DESTINATIONS,
    validate_scenario_route_catalog,
)
from pokemon_red_completion.strategic_navigation_scenarios import (
    StrategicNavigationScenario,
    StrategicNavigationScenarioRegistry,
)
from pokemon_red_completion.strategic_navigation_sealed_catalog import (
    StrategicSealedCaseCatalog,
    StrategicSealedCaseCatalogEntry,
)
from pokemon_red_completion.strategic_navigation_sealed_evaluation import (
    StrategicSealedAuthorization,
    StrategicSealedCandidateUnavailableError,
    StrategicSealedEvaluationCase,
    StrategicSealedEvaluationError,
    StrategicSealedEvaluationPlan,
    StrategicSealedPrediction,
    StrategicSealedRuntimeGrant,
    StrategicSealedTeacherResult,
)
from pokemon_red_completion.strategic_navigation_trajectory import (
    ordered_strategic_navigation_bindings,
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


class StrategicSealedAdapterError(StrategicSealedEvaluationError):
    """Raised when a cartridge session weakens the sealed adapter contract."""


@dataclass(frozen=True, slots=True)
class StrategicSealedCartridgeTeacherEvidence:
    """Minimal evidence returned by a post-commit teacher execution."""

    execution_status: str
    selected_destination_ref: str | None = None
    episode_manifest_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.execution_status not in {"succeeded", "failed"}:
            raise StrategicSealedAdapterError(
                "sealed cartridge teacher status is invalid"
            )
        if self.execution_status == "succeeded":
            if (
                not isinstance(self.selected_destination_ref, str)
                or not self.selected_destination_ref
                or not isinstance(self.episode_manifest_sha256, str)
                or _SHA256.fullmatch(self.episode_manifest_sha256) is None
            ):
                raise StrategicSealedAdapterError(
                    "successful sealed teacher evidence is incomplete"
                )
        elif (
            self.selected_destination_ref is not None
            or self.episode_manifest_sha256 is not None
        ):
            raise StrategicSealedAdapterError(
                "failed sealed teacher evidence exposes partial results"
            )


@dataclass(frozen=True, slots=True)
class StrategicNavigationPreparedPredictions:
    """Identity-free choices derived before any teacher action is available."""

    ordered_destination_refs: tuple[str, ...]
    model_prediction_index: int | None
    model_prediction_tied: bool
    baseline_prediction_index: int | None
    baseline_prediction_tied: bool
    policy_input_sha256: str


class StrategicSealedCartridgeSession(Protocol):
    """One already-opened capture whose teacher remains behind a second call."""

    @property
    def assignment_id(self) -> str: ...

    @property
    def bindings(self) -> tuple[DestinationRouteBinding, ...]: ...

    def execute_teacher(self) -> StrategicSealedCartridgeTeacherEvidence: ...

    def close(self) -> None: ...


class StrategicSealedCartridgeSessionFactory(Protocol):
    """Identity-bound private input and emulator factory."""

    @property
    def plan_sha256(self) -> str: ...

    @property
    def authorization_sha256(self) -> str: ...

    @property
    def case_catalog_sha256(self) -> str: ...

    @property
    def runtime_sha256(self) -> str: ...

    def open_case(
        self,
        case: StrategicSealedEvaluationCase,
        entry: StrategicSealedCaseCatalogEntry,
        scenario: StrategicNavigationScenario,
    ) -> StrategicSealedCartridgeSession: ...


def strategic_sealed_scenario_assignment_id(
    *,
    entry: StrategicSealedCaseCatalogEntry,
    scenario: StrategicNavigationScenario,
    registry_sha256: str,
    source_bundle_sha256: str,
    teacher_execution_sha256: str,
    source_commit: str,
) -> str:
    """Derive the sole candidate-order nonce permitted for a sealed case."""

    if not isinstance(entry, StrategicSealedCaseCatalogEntry):
        raise TypeError("entry must be a sealed catalog entry")
    if not isinstance(scenario, StrategicNavigationScenario):
        raise TypeError("scenario must be a strategic navigation scenario")
    for value, subject in (
        (registry_sha256, "scenario registry"),
        (source_bundle_sha256, "source bundle"),
        (teacher_execution_sha256, "teacher execution"),
    ):
        if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
            raise StrategicSealedAdapterError(
                f"sealed assignment {subject} identity is invalid"
            )
    if not isinstance(source_commit, str) or _GIT_OID.fullmatch(source_commit) is None:
        raise StrategicSealedAdapterError(
            "sealed assignment source commit is invalid"
        )
    return collection_document_sha256(
        {
            "capture_envelope_sha256": entry.capture_envelope_sha256,
            "capture_state_sha256": entry.capture_state_sha256,
            "checkpoint_id": entry.checkpoint_id,
            "collection_id": STRATEGIC_NAVIGATION_SCENARIO_COLLECTION_ID,
            "registry_sha256": registry_sha256,
            "scenario_id": scenario.scenario_id,
            "scenario_partition": scenario.partition,
            "scenario_sha256": scenario.scenario_sha256,
            "schema": STRATEGIC_NAVIGATION_SCENARIO_REHEARSAL_ASSIGNMENT_SCHEMA,
            "source_bundle_sha256": source_bundle_sha256,
            "source_commit": source_commit,
            "teacher_execution_sha256": teacher_execution_sha256,
        }
    )


@dataclass(slots=True)
class _ActiveCase:
    case: StrategicSealedEvaluationCase
    scenario: StrategicNavigationScenario
    ordered_destination_refs: tuple[str, ...]
    session: StrategicSealedCartridgeSession


class StrategicSealedCartridgeCaseRunner:
    """Production policy boundary implementing the sealed evaluator protocol."""

    def __init__(
        self,
        *,
        plan: StrategicSealedEvaluationPlan,
        authorization: StrategicSealedAuthorization,
        runtime_grant: StrategicSealedRuntimeGrant,
        catalog: StrategicSealedCaseCatalog,
        scenario_registry: StrategicNavigationScenarioRegistry,
        model: StrategicNavigationScorer,
        session_factory: StrategicSealedCartridgeSessionFactory,
    ) -> None:
        if not isinstance(plan, StrategicSealedEvaluationPlan):
            raise TypeError("plan must be a sealed evaluation plan")
        if not isinstance(authorization, StrategicSealedAuthorization):
            raise TypeError("authorization must be a sealed authorization")
        if not isinstance(runtime_grant, StrategicSealedRuntimeGrant):
            raise TypeError("runtime_grant must be a sealed runtime grant")
        if not isinstance(catalog, StrategicSealedCaseCatalog):
            raise TypeError("catalog must be a sealed case catalog")
        if not isinstance(scenario_registry, StrategicNavigationScenarioRegistry):
            raise TypeError("scenario_registry must be a scenario registry")
        if type(model) is not StrategicNavigationLinear:  # noqa: E721
            raise TypeError("model must be the frozen strategic linear scorer")
        if not callable(getattr(session_factory, "open_case", None)):
            raise TypeError("session_factory must open sealed cartridge sessions")
        if (
            authorization.plan_sha256 != plan.plan_sha256
            or runtime_grant.plan_sha256 != plan.plan_sha256
            or runtime_grant.authorization_sha256
            != authorization.authorization_sha256
            or catalog.plan_sha256 != plan.plan_sha256
            or catalog.catalog_sha256 != authorization.case_catalog_sha256
            or runtime_grant.case_catalog_sha256 != catalog.catalog_sha256
            or catalog.teacher_execution_sha256 != plan.teacher_execution_sha256
            or scenario_registry.registry_sha256
            != plan.source_scenario_registry_sha256
        ):
            raise StrategicSealedAdapterError(
                "sealed adapter plan, authorization, catalog, or registry differs"
            )
        if canonical_strategic_navigation_model_sha256(model) != (
            plan.model_canonical_sha256
        ):
            raise StrategicSealedAdapterError("sealed adapter model differs")
        if (
            session_factory.plan_sha256 != plan.plan_sha256
            or session_factory.authorization_sha256
            != authorization.authorization_sha256
            or session_factory.case_catalog_sha256 != catalog.catalog_sha256
            or session_factory.runtime_sha256 != catalog.runtime_sha256
        ):
            raise StrategicSealedAdapterError(
                "sealed cartridge session factory identity differs"
            )
        validate_scenario_route_catalog(scenario_registry)
        self._plan = plan
        self._authorization = authorization
        self._runtime_grant = runtime_grant
        self._catalog = catalog
        self._scenario_registry = scenario_registry
        self._model = model
        self._session_factory = session_factory
        self._active: _ActiveCase | None = None
        self._opened_case_ids: set[str] = set()

    def prepare(
        self,
        case: StrategicSealedEvaluationCase,
    ) -> StrategicSealedPrediction:
        """Open one already-claimed input and compute predictions without a label."""

        self._require_known_case(case)
        if self._active is not None:
            raise StrategicSealedAdapterError(
                "a sealed cartridge case is already active"
            )
        if case.case_id in self._opened_case_ids:
            raise StrategicSealedAdapterError(
                "a sealed cartridge case cannot be reopened"
            )
        self._opened_case_ids.add(case.case_id)
        entry = self._catalog.case(case.case_id)
        scenario = self._scenario(case)
        session: StrategicSealedCartridgeSession | None = None
        try:
            session = self._session_factory.open_case(case, entry, scenario)
            canonical_bindings = self._require_canonical_bindings(
                case,
                scenario,
                session.bindings,
            )
            expected_assignment_id = strategic_sealed_scenario_assignment_id(
                entry=entry,
                scenario=scenario,
                registry_sha256=self._scenario_registry.registry_sha256,
                source_bundle_sha256=self._plan.execution_source_bundle_sha256,
                teacher_execution_sha256=self._plan.teacher_execution_sha256,
                source_commit=self._authorization.source_commit,
            )
            if session.assignment_id != expected_assignment_id:
                raise StrategicSealedAdapterError(
                    "sealed cartridge assignment identity differs"
                )
            prepared = prepare_strategic_navigation_predictions(
                self._model,
                assignment_id=session.assignment_id,
                bindings=canonical_bindings,
            )
            self._active = _ActiveCase(
                case=case,
                scenario=scenario,
                ordered_destination_refs=prepared.ordered_destination_refs,
                session=session,
            )
            return StrategicSealedPrediction(
                case_id=case.case_id,
                case_sha256=case.case_sha256,
                ordinal=case.ordinal,
                candidate_count=case.candidate_count,
                model_prediction_index=prepared.model_prediction_index,
                model_prediction_tied=prepared.model_prediction_tied,
                baseline_prediction_index=prepared.baseline_prediction_index,
                baseline_prediction_tied=prepared.baseline_prediction_tied,
                policy_input_sha256=prepared.policy_input_sha256,
            )
        except BaseException:
            if session is not None:
                session.close()
            raise

    def execute_teacher(
        self,
        case: StrategicSealedEvaluationCase,
    ) -> StrategicSealedTeacherResult:
        """Execute the deterministic teacher only after prediction commitment."""

        active = self._active
        if active is None or active.case != case:
            raise StrategicSealedAdapterError(
                "sealed teacher execution lacks its active prediction"
            )
        self._active = None
        try:
            evidence = active.session.execute_teacher()
            if evidence.execution_status == "failed":
                return StrategicSealedTeacherResult(
                    case_id=case.case_id,
                    case_sha256=case.case_sha256,
                    ordinal=case.ordinal,
                    candidate_count=case.candidate_count,
                    execution_status="failed",
                )
            expected_ref = (
                f"pokemon.red:objective:"
                f"{active.scenario.teacher_objective_id}:approach"
            )
            if evidence.selected_destination_ref != expected_ref:
                raise StrategicSealedAdapterError(
                    "sealed teacher selected a non-preregistered destination"
                )
            assert evidence.episode_manifest_sha256 is not None
            return StrategicSealedTeacherResult(
                case_id=case.case_id,
                case_sha256=case.case_sha256,
                ordinal=case.ordinal,
                candidate_count=case.candidate_count,
                execution_status="succeeded",
                teacher_target_index=active.ordered_destination_refs.index(
                    expected_ref
                ),
                episode_manifest_sha256=evidence.episode_manifest_sha256,
            )
        finally:
            active.session.close()

    def abort(self, case: StrategicSealedEvaluationCase) -> None:
        """Close a prepared session if the outer commitment step fails."""

        active = self._active
        if active is None:
            return
        if active.case != case:
            raise StrategicSealedAdapterError(
                "sealed adapter abort case differs from its active input"
            )
        self._active = None
        active.session.close()

    def _require_known_case(self, case: StrategicSealedEvaluationCase) -> None:
        if not isinstance(case, StrategicSealedEvaluationCase):
            raise TypeError("case must be a sealed evaluation case")
        if case not in self._plan.cases:
            raise StrategicSealedAdapterError(
                "sealed adapter case differs from the frozen plan"
            )

    def _scenario(
        self,
        case: StrategicSealedEvaluationCase,
    ) -> StrategicNavigationScenario:
        matches = tuple(
            scenario
            for scenario in self._scenario_registry.scenarios
            if scenario.scenario_id == case.source_scenario_id
        )
        if len(matches) != 1:
            raise StrategicSealedAdapterError(
                "sealed adapter source scenario is unavailable"
            )
        scenario = matches[0]
        if (
            scenario.partition != "test"
            or scenario.scenario_sha256 != case.source_scenario_sha256
        ):
            raise StrategicSealedAdapterError(
                "sealed adapter source scenario differs"
            )
        return scenario

    @staticmethod
    def _require_canonical_bindings(
        case: StrategicSealedEvaluationCase,
        scenario: StrategicNavigationScenario,
        bindings: tuple[DestinationRouteBinding, ...],
    ) -> tuple[DestinationRouteBinding, ...]:
        if not isinstance(bindings, tuple) or len(bindings) != case.candidate_count:
            raise StrategicSealedAdapterError(
                "sealed candidate binding count differs"
            )
        expected = tuple(
            STRATEGIC_SCENARIO_DESTINATIONS[objective_id]
            for objective_id in scenario.candidate_objective_ids
        )
        if any(
            not isinstance(binding, DestinationRouteBinding)
            or binding.destination_ref != spec.destination_ref
            or binding.semantic_tags != spec.semantic_tags
            for binding, spec in zip(bindings, expected, strict=True)
        ):
            raise StrategicSealedAdapterError(
                "sealed candidate binding identity or order differs"
            )
        if any(binding.plan is None for binding in bindings):
            raise StrategicSealedCandidateUnavailableError(
                "a declared sealed candidate is unavailable"
            )
        return bindings


def prepare_strategic_navigation_predictions(
    model: StrategicNavigationScorer,
    *,
    assignment_id: str,
    bindings: tuple[DestinationRouteBinding, ...],
) -> StrategicNavigationPreparedPredictions:
    """Project ordered routes into frozen model/baseline choices with no label."""

    if not callable(getattr(model, "probabilities", None)):
        raise TypeError("model must expose strategic probabilities")
    if not isinstance(bindings, tuple) or not 2 <= len(bindings) <= 5:
        raise StrategicSealedAdapterError(
            "strategic prediction candidate count is invalid"
        )
    if any(
        not isinstance(binding, DestinationRouteBinding) for binding in bindings
    ):
        raise StrategicSealedAdapterError(
            "strategic prediction binding is invalid"
        )
    if any(binding.plan is None for binding in bindings):
        raise StrategicSealedCandidateUnavailableError(
            "a strategic prediction candidate is unavailable"
        )
    ordered = ordered_strategic_navigation_bindings(
        assignment_id,
        0,
        bindings,
    )
    inference = StrategicNavigationInferenceInput.from_candidates(
        semantic_need_tags=(
            StrategicNavigationTag.ADVANCE_STORY,
            StrategicNavigationTag.REACH_NEXT_CHALLENGE,
        ),
        origin_semantic_tags=(
            StrategicNavigationTag.OVERWORLD,
            StrategicNavigationTag.SAFE_HUB,
        ),
        candidates=tuple(binding.candidate for binding in ordered),
    )
    probabilities = np.asarray(
        model.probabilities(inference),
        dtype=np.float64,
    )
    if (
        probabilities.shape != (len(bindings),)
        or not np.all(np.isfinite(probabilities))
        or np.any(probabilities < 0.0)
        or not math.isclose(
            float(np.sum(probabilities)),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
    ):
        raise StrategicSealedAdapterError(
            "sealed model probabilities are invalid"
        )
    model_winners = np.flatnonzero(probabilities == np.max(probabilities))
    model_tied = len(model_winners) != 1
    model_index = None if model_tied else int(model_winners[0])
    costs: list[int] = []
    for candidate in inference.candidates:
        cost = candidate.get("route_cost")
        if type(cost) is not int or cost < 0:  # noqa: E721
            raise StrategicSealedAdapterError(
                "sealed baseline route cost is invalid"
            )
        costs.append(cost)
    minimum = min(costs)
    baseline_winners = tuple(
        index for index, cost in enumerate(costs) if cost == minimum
    )
    baseline_tied = len(baseline_winners) != 1
    baseline_index = None if baseline_tied else baseline_winners[0]
    return StrategicNavigationPreparedPredictions(
        ordered_destination_refs=tuple(
            binding.destination_ref for binding in ordered
        ),
        model_prediction_index=model_index,
        model_prediction_tied=model_tied,
        baseline_prediction_index=baseline_index,
        baseline_prediction_tied=baseline_tied,
        policy_input_sha256=inference.ordered_policy_input_sha256,
    )
