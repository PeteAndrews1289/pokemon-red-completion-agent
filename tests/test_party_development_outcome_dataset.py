from __future__ import annotations

import json
from dataclasses import replace

import pytest

from pokemon_red_completion.party_development_outcome_dataset import (
    audit_party_development_outcome_catalog,
)
from pokemon_red_completion.party_development_outcomes import (
    PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE,
)
from pokemon_red_completion.party_development_rank import (
    PARTY_DEVELOPMENT_FEATURE_NAMES,
    PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID,
    EvolutionRouteKind,
    PartyDevelopmentGoal,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.scenario_outcomes import (
    CandidateOutcome,
    OutcomeCandidate,
    OutcomeEvidenceStatus,
    ScenarioOutcomeError,
    ScenarioOutcomeExample,
)
from pokemon_red_completion.training_candidate_rank import TrainingChoiceKind


def _feature_index(name: str) -> int:
    return PARTY_DEVELOPMENT_FEATURE_NAMES.index(name)


def _outcome(winner: bool) -> CandidateOutcome:
    values = [0.0] * len(PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE.criteria)
    values[0] = 1.0
    values[1] = 1.0
    values[2] = float(winner)
    values[-1] = 1_000.0
    return CandidateOutcome(OutcomeEvidenceStatus.MEASURED, tuple(values))


def _example(
    index: int,
    *,
    partition: ScenarioPartition,
    goal: PartyDevelopmentGoal,
    kind: TrainingChoiceKind,
    health: float,
    pp: float,
    route: EvolutionRouteKind,
) -> ScenarioOutcomeExample:
    candidates = []
    outcomes = []
    for candidate_index in range(3):
        features = [0.0] * len(PARTY_DEVELOPMENT_FEATURE_NAMES)
        features[_feature_index("choice.trainee")] = float(
            kind is TrainingChoiceKind.TRAINEE
        )
        features[_feature_index(f"context.goal.{goal.value}")] = 1.0
        features[_feature_index("candidate.hp_ratio")] = health
        features[_feature_index("candidate.attack_pp")] = pp
        features[_feature_index("candidate.projected_survival_margin")] = (
            -0.5 if health < 0.5 else 0.5
        )
        features[
            _feature_index(f"candidate.evolution_method.{route.value}")
        ] = 1.0
        features[_feature_index("venue.prior_available")] = float(
            kind is TrainingChoiceKind.VENUE
        )
        candidates.append(OutcomeCandidate(candidate_index, tuple(features)))
        outcomes.append(_outcome(candidate_index == index % 3))
    prefix = "train" if partition is ScenarioPartition.TRAIN else "development"
    digest_character = "0123456789abcdef"[index]
    return ScenarioOutcomeExample(
        scenario_id=f"{prefix}-scenario-{index}",
        root_lineage_id=f"{prefix}-root-{index}",
        initial_state_sha256=digest_character * 64,
        partition=partition,
        objective=PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE,
        feature_schema_id=PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID,
        feature_names=PARTY_DEVELOPMENT_FEATURE_NAMES,
        candidates=tuple(candidates),
        outcomes=tuple(outcomes),
    )


def _ready_catalog() -> tuple[ScenarioOutcomeExample, ...]:
    examples = []
    for index in range(8):
        examples.append(
            _example(
                index,
                partition=ScenarioPartition.TRAIN,
                goal=(
                    PartyDevelopmentGoal.EVOLUTION
                    if index % 2 == 0
                    else PartyDevelopmentGoal.COLLECTION
                ),
                kind=(
                    TrainingChoiceKind.TRAINEE
                    if index % 2 == 0
                    else TrainingChoiceKind.VENUE
                ),
                health=0.1 if index < 4 else 0.9,
                pp=0.2 if index < 4 else 0.8,
                route=(
                    EvolutionRouteKind.LEVEL
                    if index < 4
                    else EvolutionRouteKind.NONE
                ),
            )
        )
    for index in range(8, 14):
        examples.append(
            _example(
                index,
                partition=ScenarioPartition.DEVELOPMENT,
                goal=(
                    PartyDevelopmentGoal.EVOLUTION
                    if index % 2 == 0
                    else PartyDevelopmentGoal.COLLECTION
                ),
                kind=(
                    TrainingChoiceKind.TRAINEE
                    if index % 2 == 0
                    else TrainingChoiceKind.VENUE
                ),
                health=0.1 if index < 11 else 0.9,
                pp=0.2 if index < 11 else 0.8,
                route=(
                    EvolutionRouteKind.LEVEL
                    if index < 11
                    else EvolutionRouteKind.NONE
                ),
            )
        )
    return tuple(examples)


def test_diverse_isolated_catalog_reaches_only_the_initial_fit_gate() -> None:
    audit = audit_party_development_outcome_catalog(_ready_catalog())

    assert audit.initial_fit_ready
    assert audit.reasons == ()
    assert audit.learner_update_eligible_examples == 14
    assert dict(audit.partition_eligible_counts) == {"development": 6, "train": 8}
    assert set(audit.evolution_route_kinds) == {"level", "none"}
    assert audit.venue_prior_available_candidates > 0
    public = audit.public_dict()
    assert public["paired_development_evaluation_required"] is True
    assert public["inferential_claim"] is False
    assert public["authority_promoted"] is False
    assert "candidate.hp_ratio" not in json.dumps(public, sort_keys=True)


def test_small_semantically_thin_catalog_reports_every_missing_gate() -> None:
    audit = audit_party_development_outcome_catalog((_ready_catalog()[0],))

    assert not audit.initial_fit_ready
    assert "insufficient_train_preferences" in audit.reasons
    assert "insufficient_development_preferences" in audit.reasons
    assert "missing_train_choice_kind" in audit.reasons
    assert "missing_development_choice_kind" in audit.reasons
    assert "insufficient_health_diversity" in audit.reasons
    assert "insufficient_pp_diversity" in audit.reasons
    assert "insufficient_evolution_route_diversity" in audit.reasons


def test_catalog_rejects_cross_partition_root_reuse() -> None:
    train = _ready_catalog()[0]
    development = replace(
        _ready_catalog()[8],
        root_lineage_id=train.root_lineage_id,
    )

    with pytest.raises(ScenarioOutcomeError, match="root lineage crosses"):
        audit_party_development_outcome_catalog((train, development))


def test_catalog_rejects_non_one_hot_goal_features() -> None:
    example = _ready_catalog()[0]
    first = example.candidates[0]
    features = list(first.features)
    features[_feature_index("context.goal.collection")] = 1.0
    malformed = replace(
        example,
        candidates=(replace(first, features=tuple(features)), *example.candidates[1:]),
    )

    with pytest.raises(ScenarioOutcomeError, match="goal features"):
        audit_party_development_outcome_catalog((malformed,))


def test_fit_gate_requires_priors_for_every_venue_candidate() -> None:
    catalog = list(_ready_catalog())
    venue_index = next(
        index
        for index, example in enumerate(catalog)
        if example.candidates[0].features[_feature_index("choice.trainee")] == 0.0
    )
    example = catalog[venue_index]
    first = example.candidates[0]
    features = list(first.features)
    features[_feature_index("venue.prior_available")] = 0.0
    catalog[venue_index] = replace(
        example,
        candidates=(replace(first, features=tuple(features)), *example.candidates[1:]),
    )

    audit = audit_party_development_outcome_catalog(tuple(catalog))

    assert not audit.initial_fit_ready
    assert "venue_outcomes_lack_complete_prospective_priors" in audit.reasons
