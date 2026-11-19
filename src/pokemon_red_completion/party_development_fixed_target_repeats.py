"""Predeclared repeated ready-task costs, using existing outcome/binding records.

The trusted materializer authenticates each complete native comparison first.
This adapter combines measurements only; saves, recipients and earned progress
are never combined. Original single-task labels and default learners stay intact.
"""

from dataclasses import asdict, dataclass

from .party_development_catalog import PartyDevelopmentProspectiveBinding
from .party_development_fixed_target_outcomes import (
    FIXED_LEVEL_READY_OBJECTIVE,
    FixedLevelReadyContract,
    _digest,
    _require_menu,
)
from .provenance import canonical_sha256
from .scenario_lab import ScenarioPartition
from .scenario_outcomes import (
    CandidateOutcome,
    OutcomeCandidate,
    OutcomeEvidenceStatus,
    OutcomeObjective,
    ScenarioOutcomeError,
    ScenarioOutcomeExample,
)


FIXED_LEVEL_READY_REPEATED_OBJECTIVE = OutcomeObjective(
    "party-development.fixed-level-ready-repeated-cost.v1",
    FIXED_LEVEL_READY_OBJECTIVE.family,
    FIXED_LEVEL_READY_OBJECTIVE.criteria,
)


@dataclass(frozen=True, slots=True)
class RepeatedReadyContract:
    """One fixed recipient/task and the exact timing conditions to measure."""

    fixed_task: FixedLevelReadyContract
    timing_frames: tuple[int, ...]
    collection_recipe_sha256: str

    def __post_init__(self):
        if not isinstance(self.fixed_task, FixedLevelReadyContract):
            raise TypeError("repeated ready task needs its fixed recipient contract")
        if (
            not isinstance(self.timing_frames, tuple)
            or len(self.timing_frames) < 2
            or any(type(t) is not int or t < 0 for t in self.timing_frames)
            or tuple(sorted(set(self.timing_frames))) != self.timing_frames
        ):
            raise ScenarioOutcomeError("repeated timing conditions must be exact, unique and ordered")
        _digest(self.collection_recipe_sha256)

    def semantic_snapshot_sha256(self, original_semantic_snapshot_sha256):
        return canonical_sha256(
            dict(
                fixed_task_snapshot=self.fixed_task.semantic_snapshot_sha256(
                    original_semantic_snapshot_sha256
                ),
                repeated_ready_contract=asdict(self),
                aggregation="all-declared-timings-complete-then-sum-full-physical-cost",
            )
        )


def freeze_repeated_ready_binding(
    candidate_set, contract, *, original_semantic_snapshot_sha256, **binding_fields
):
    """Freeze the existing binding codec before any declared trial receives input."""
    if not isinstance(contract, RepeatedReadyContract):
        raise TypeError("repeated ready task needs its prospective contract")
    _require_menu(candidate_set, contract.fixed_task)
    if {"candidate_set", "semantic_snapshot_sha256", "outcome_objective_sha256"} & binding_fields.keys():
        raise ScenarioOutcomeError("caller cannot substitute repeated task semantics")
    return PartyDevelopmentProspectiveBinding.build(
        candidate_set=candidate_set,
        semantic_snapshot_sha256=contract.semantic_snapshot_sha256(
            original_semantic_snapshot_sha256
        ),
        outcome_objective_sha256=FIXED_LEVEL_READY_REPEATED_OBJECTIVE.objective_sha256,
        **binding_fields,
    )


def adapt_repeated_ready_outcomes(
    candidate_set,
    timing_examples,
    *,
    contract,
    prospective_binding,
    single_task_binding,
    original_semantic_snapshot_sha256,
):
    """Aggregate complete, authenticated single-task TRAIN comparisons.

    Every timing and every legal candidate is required. An incomplete, censored
    or errored trial is retained by the caller and blocks this initial adapter;
    it cannot become a zero cost or be replaced by a successful sibling.
    """
    if not isinstance(contract, RepeatedReadyContract):
        raise TypeError("repeated ready task needs its prospective contract")
    _require_menu(candidate_set, contract.fixed_task)
    if not isinstance(prospective_binding, PartyDevelopmentProspectiveBinding):
        raise TypeError("repeated ready task needs its existing prospective binding")
    prospective_binding.require_candidate_set(candidate_set)
    if not isinstance(single_task_binding, PartyDevelopmentProspectiveBinding):
        raise TypeError("repeated task needs its authenticated single-task binding")
    single_task_binding.require_candidate_set(candidate_set)
    if (
        single_task_binding.outcome_objective_sha256 != FIXED_LEVEL_READY_OBJECTIVE.objective_sha256
        or single_task_binding.semantic_snapshot_sha256
        != contract.fixed_task.semantic_snapshot_sha256(original_semantic_snapshot_sha256)
        or any(
            getattr(single_task_binding, field) != getattr(prospective_binding, field)
            for field in (
                "root_lineage_id", "initial_state_sha256", "partition", "source_commit",
                "source_bundle_sha256", "venue_prior_registry_sha256", "venue_prior_feature_mode",
            )
        )
    ):
        raise ScenarioOutcomeError("single-task binding differs from the exact repeated recipient contract")
    if (
        prospective_binding.partition is not ScenarioPartition.TRAIN
        or prospective_binding.outcome_objective_sha256
        != FIXED_LEVEL_READY_REPEATED_OBJECTIVE.objective_sha256
        or prospective_binding.semantic_snapshot_sha256
        != contract.semantic_snapshot_sha256(original_semantic_snapshot_sha256)
        or not all(prospective_binding.candidate_available)
    ):
        raise ScenarioOutcomeError("repeated task source, objective, contract or full menu differs")
    if (
        not isinstance(timing_examples, tuple)
        or len(timing_examples) != len(contract.timing_frames)
        or any(not isinstance(pair, tuple) or len(pair) != 2 for pair in timing_examples)
        or tuple(pair[0] for pair in timing_examples) != contract.timing_frames
    ):
        raise ScenarioOutcomeError("every prospectively declared timing is required exactly once")
    candidates = tuple(
        OutcomeCandidate(c.candidate_index, c.features, True)
        for c in candidate_set.candidates
    )
    examples = tuple(pair[1] for pair in timing_examples)
    seen_evidence = set()
    for example in examples:
        if isinstance(example, ScenarioOutcomeExample):
            single_task_binding.require_matches(example)
        if (
            not isinstance(example, ScenarioOutcomeExample)
            or example.partition is not ScenarioPartition.TRAIN
            or example.objective != FIXED_LEVEL_READY_OBJECTIVE
            or example.root_lineage_id != prospective_binding.root_lineage_id
            or example.initial_state_sha256 != prospective_binding.initial_state_sha256
            or example.feature_schema_id != candidate_set.feature_schema_id
            or example.feature_names != candidate_set.feature_names
            or example.candidates != candidates
            or not example.fully_measured
        ):
            raise ScenarioOutcomeError("repeated trial changed source, partition, target or complete menu")
        for outcome in example.outcomes:
            if (
                outcome is None
                or outcome.status is not OutcomeEvidenceStatus.MEASURED
                or outcome.criterion_values[:3] != (1.0, 1.0, 1.0)
                or type(outcome.frames_executed) is not int
                or outcome.frames_executed < 1
                or outcome.criterion_values[3] != outcome.frames_executed
                or type(outcome.actions_executed) is not int
                or outcome.actions_executed < 1
                or outcome.criterion_values[5] != contract.fixed_task.workload.remaining_xp
                or outcome.evidence_sha256 is None
                or outcome.evidence_sha256 in seen_evidence
            ):
                raise ScenarioOutcomeError("all distinct completed target-task measurements are required")
            seen_evidence.add(outcome.evidence_sha256)
    if len({e.prospective_binding_sha256 for e in examples}) != 1:
        raise ScenarioOutcomeError("single-task prospective recipient/venue binding changed across timings")
    outcomes = []
    for index in range(len(candidates)):
        measured = tuple(example.outcomes[index] for example in examples)
        frames = sum(outcome.frames_executed for outcome in measured)
        actions = sum(outcome.actions_executed for outcome in measured)
        faints = sum(outcome.criterion_values[4] for outcome in measured)
        useful_xp = sum(outcome.criterion_values[5] for outcome in measured)
        outcomes.append(
            CandidateOutcome(
                status=OutcomeEvidenceStatus.MEASURED,
                criterion_values=(1.0, 1.0, 1.0, float(frames), float(faints), float(useful_xp)),
                actions_executed=actions,
                frames_executed=frames,
                evidence_sha256=canonical_sha256(
                    dict(
                        repeated_contract=asdict(contract),
                        timing_frames=contract.timing_frames,
                        single_example_sha256s=tuple(e.example_sha256 for e in examples),
                        candidate_index=index,
                        native_measurement_sha256s=tuple(o.evidence_sha256 for o in measured),
                    )
                ),
            )
        )
    result = ScenarioOutcomeExample(
        scenario_id=prospective_binding.scenario_id,
        root_lineage_id=prospective_binding.root_lineage_id,
        initial_state_sha256=prospective_binding.initial_state_sha256,
        partition=ScenarioPartition.TRAIN,
        objective=FIXED_LEVEL_READY_REPEATED_OBJECTIVE,
        feature_schema_id=candidate_set.feature_schema_id,
        feature_names=candidate_set.feature_names,
        candidates=candidates,
        outcomes=tuple(outcomes),
        prospective_binding_sha256=prospective_binding.binding_sha256,
    )
    prospective_binding.require_matches(result)
    return result
