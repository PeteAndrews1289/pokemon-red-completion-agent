from __future__ import annotations

import json
from dataclasses import replace

import pytest

from pokemon_red_completion.party_development_catalog import (
    PartyDevelopmentCatalogError,
    PartyDevelopmentProspectiveBinding,
    PartyDevelopmentProspectiveCatalog,
)
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
    PartyDevelopmentCandidate,
    PartyDevelopmentCandidateSet,
    PartyDevelopmentFeatureError,
    PartyDevelopmentGoal,
    VenueOperationalPrior,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.scenario_outcomes import (
    CandidateOutcome,
    OutcomeCandidate,
    OutcomeEvidenceStatus,
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
        features[_feature_index("choice.trainee")] = float(kind is TrainingChoiceKind.TRAINEE)
        features[_feature_index(f"context.goal.{goal.value}")] = 1.0
        features[_feature_index("candidate.hp_ratio")] = health
        features[_feature_index("candidate.attack_pp")] = pp
        features[_feature_index("candidate.projected_survival_margin")] = (
            -0.5 if health < 0.5 else 0.5
        )
        features[_feature_index(f"candidate.evolution_method.{route.value}")] = 1.0
        features[_feature_index("venue.prior_available")] = 1.0
        features[_feature_index("venue.prior_reliability")] = 0.75
        features[_feature_index("venue.prior_expected_yield")] = 0.5
        features[_feature_index("venue.prior_matchup_safety")] = 0.625
        features[_feature_index("venue.prior_travel_cost")] = 0.25
        features[_feature_index("venue.prior_recovery_cost")] = 0.125
        features[_feature_index("venue.prior_support")] = 1 / 64
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
                kind=(TrainingChoiceKind.TRAINEE if index % 2 == 0 else TrainingChoiceKind.VENUE),
                health=0.1 if index < 4 else 0.9,
                pp=0.2 if index < 4 else 0.8,
                route=(EvolutionRouteKind.LEVEL if index < 4 else EvolutionRouteKind.NONE),
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
                kind=(TrainingChoiceKind.TRAINEE if index % 2 == 0 else TrainingChoiceKind.VENUE),
                health=0.1 if index < 11 else 0.9,
                pp=0.2 if index < 11 else 0.8,
                route=(EvolutionRouteKind.LEVEL if index < 11 else EvolutionRouteKind.NONE),
            )
        )
    return tuple(examples)


def _prospective_catalog(
    examples: tuple[ScenarioOutcomeExample, ...],
) -> PartyDevelopmentProspectiveCatalog:
    bindings = []
    for example in examples:
        kind = (
            TrainingChoiceKind.TRAINEE
            if example.candidates[0].features[_feature_index("choice.trainee")] == 1.0
            else TrainingChoiceKind.VENUE
        )
        goal = next(
            goal
            for goal in PartyDevelopmentGoal
            if example.candidates[0].features[_feature_index(f"context.goal.{goal.value}")] == 1.0
        )
        candidate_set = PartyDevelopmentCandidateSet(
            kind=kind,
            goal=goal,
            candidates=tuple(
                PartyDevelopmentCandidate(item.candidate_index, item.features)
                for item in example.candidates
            ),
        )
        shared_prior = VenueOperationalPrior(
            available=True,
            reliability=0.75,
            expected_yield=0.5,
            matchup_safety=0.625,
            travel_cost=0.25,
            recovery_cost=0.125,
            support_count=1,
            evidence_sha256="9" * 64,
            frozen_before_scenario=True,
        )
        priors = (
            tuple(shared_prior for _ in example.candidates)
            if kind is TrainingChoiceKind.TRAINEE
            else tuple(
                VenueOperationalPrior(
                    available=True,
                    reliability=0.75,
                    expected_yield=0.5,
                    matchup_safety=0.625,
                    travel_cost=0.25,
                    recovery_cost=0.125,
                    support_count=1,
                    evidence_sha256="abcdef"[item.candidate_index] * 64,
                    frozen_before_scenario=True,
                )
                if item.features[_feature_index("venue.prior_available")] == 1.0
                else VenueOperationalPrior()
                for item in example.candidates
            )
        )
        bindings.append(
            PartyDevelopmentProspectiveBinding.build(
                scenario_id=example.scenario_id,
                root_lineage_id=example.root_lineage_id,
                initial_state_sha256=example.initial_state_sha256,
                partition=example.partition,
                source_commit="a" * 40,
                source_bundle_sha256="b" * 64,
                semantic_snapshot_sha256=example.initial_state_sha256,
                candidate_set=candidate_set,
                venue_priors=priors,
                venue_prior_registry_sha256="c" * 64,
                shared_venue_prior=(shared_prior if kind is TrainingChoiceKind.TRAINEE else None),
                candidate_available=tuple(item.available for item in example.candidates),
            )
        )
    return PartyDevelopmentProspectiveCatalog.freeze(tuple(bindings))


def test_diverse_isolated_catalog_reaches_only_the_initial_fit_gate() -> None:
    examples = _ready_catalog()
    audit = audit_party_development_outcome_catalog(
        examples,
        prospective_catalog=_prospective_catalog(examples),
    )

    assert audit.initial_fit_ready
    assert audit.reasons == ()
    assert audit.learner_update_eligible_examples == 14
    assert dict(audit.partition_eligible_counts) == {"development": 6, "train": 8}
    assert set(audit.evolution_route_kinds) == {"level", "none"}
    assert audit.venue_prior_available_candidates > 0
    assert dict(audit.partition_semantic_menu_counts)["development"] >= 3
    assert audit.prospective_binding_count == 14
    public = audit.public_dict()
    assert public["paired_development_evaluation_required"] is True
    assert public["inferential_claim"] is False
    assert public["authority_promoted"] is False
    assert "candidate.hp_ratio" not in json.dumps(public, sort_keys=True)


def test_small_semantically_thin_catalog_reports_every_missing_gate() -> None:
    examples = (_ready_catalog()[0],)
    audit = audit_party_development_outcome_catalog(
        examples,
        prospective_catalog=_prospective_catalog(examples),
    )

    assert not audit.initial_fit_ready
    assert "insufficient_train_preferences" in audit.reasons
    assert "insufficient_development_preferences" in audit.reasons
    assert "missing_train_choice_kind" in audit.reasons
    assert "missing_development_choice_kind" in audit.reasons
    assert "insufficient_train_health_diversity" in audit.reasons
    assert "insufficient_train_pp_diversity" in audit.reasons
    assert "insufficient_train_evolution_route_diversity" in audit.reasons
    assert "insufficient_development_semantic_menu_diversity" in audit.reasons


def test_catalog_rejects_cross_partition_root_reuse() -> None:
    train = _ready_catalog()[0]
    development = replace(
        _ready_catalog()[8],
        root_lineage_id=train.root_lineage_id,
    )

    examples = (train, development)
    with pytest.raises(PartyDevelopmentCatalogError, match="repeats a root lineage"):
        _prospective_catalog(examples)


def test_catalog_rejects_non_one_hot_goal_features() -> None:
    example = _ready_catalog()[0]
    first = example.candidates[0]
    features = list(first.features)
    features[_feature_index("context.goal.collection")] = 1.0
    malformed = replace(
        example,
        candidates=(replace(first, features=tuple(features)), *example.candidates[1:]),
    )

    with pytest.raises(PartyDevelopmentFeatureError, match="goal"):
        _prospective_catalog((malformed,))


def test_prospective_freeze_requires_priors_for_every_available_venue_candidate() -> None:
    catalog = list(_ready_catalog())
    venue_index = next(
        index
        for index, example in enumerate(catalog)
        if example.candidates[0].features[_feature_index("choice.trainee")] == 0.0
    )
    example = catalog[venue_index]
    first = example.candidates[0]
    features = list(first.features)
    for name in (
        "venue.prior_available",
        "venue.prior_reliability",
        "venue.prior_expected_yield",
        "venue.prior_matchup_safety",
        "venue.prior_travel_cost",
        "venue.prior_recovery_cost",
        "venue.prior_support",
    ):
        features[_feature_index(name)] = 0.0
    catalog[venue_index] = replace(
        example,
        candidates=(replace(first, features=tuple(features)), *example.candidates[1:]),
    )

    with pytest.raises(PartyDevelopmentCatalogError, match="prospective evidence"):
        _prospective_catalog(tuple(catalog))


def test_global_variety_cannot_hide_a_semantically_thin_development_partition() -> None:
    examples = list(_ready_catalog()[:8])
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
                kind=(TrainingChoiceKind.TRAINEE if index % 2 == 0 else TrainingChoiceKind.VENUE),
                health=0.9,
                pp=0.8,
                route=EvolutionRouteKind.NONE,
            )
        )
    frozen = tuple(examples)

    audit = audit_party_development_outcome_catalog(
        frozen,
        prospective_catalog=_prospective_catalog(frozen),
    )

    assert not audit.initial_fit_ready
    assert "insufficient_development_health_diversity" in audit.reasons
    assert "insufficient_development_pp_diversity" in audit.reasons
    assert "insufficient_development_evolution_route_diversity" in audit.reasons
    assert "insufficient_development_semantic_menu_diversity" in audit.reasons


def test_outcomes_must_match_the_exact_prospectively_frozen_candidate_menu() -> None:
    examples = _ready_catalog()
    prospective = _prospective_catalog(examples)
    first = examples[0]
    candidate = first.candidates[0]
    features = list(candidate.features)
    features[_feature_index("candidate.hp_ratio")] += 0.01
    changed = replace(
        first,
        candidates=(replace(candidate, features=tuple(features)), *first.candidates[1:]),
    )

    with pytest.raises(PartyDevelopmentCatalogError, match="candidate menu"):
        audit_party_development_outcome_catalog(
            (changed, *examples[1:]),
            prospective_catalog=prospective,
        )


def test_prospective_catalog_rejects_invalid_availability_before_hashing() -> None:
    example = _ready_catalog()[0]
    prospective = _prospective_catalog((example,))
    binding = prospective.bindings[0]
    candidate_set = PartyDevelopmentCandidateSet(
        kind=binding.kind,
        goal=binding.goal,
        candidates=tuple(
            PartyDevelopmentCandidate(item.candidate_index, item.features)
            for item in example.candidates
        ),
    )
    shared_prior = VenueOperationalPrior(
        available=True,
        reliability=0.75,
        expected_yield=0.5,
        matchup_safety=0.625,
        travel_cost=0.25,
        recovery_cost=0.125,
        support_count=1,
        evidence_sha256="9" * 64,
        frozen_before_scenario=True,
    )
    priors = tuple(shared_prior for _ in example.candidates)

    with pytest.raises(PartyDevelopmentCatalogError, match="availability"):
        PartyDevelopmentProspectiveBinding.build(
            scenario_id="availability-test",
            root_lineage_id="availability-root",
            initial_state_sha256="f" * 64,
            partition=ScenarioPartition.TRAIN,
            source_commit="a" * 40,
            source_bundle_sha256="b" * 64,
            semantic_snapshot_sha256="e" * 64,
            candidate_set=candidate_set,
            venue_priors=priors,
            venue_prior_registry_sha256="c" * 64,
            shared_venue_prior=shared_prior,
            candidate_available=(False,) * len(example.candidates),
        )


def test_trainee_catalog_binds_the_shared_training_venue_before_outcomes() -> None:
    example = _ready_catalog()[0]
    candidate_set = PartyDevelopmentCandidateSet(
        kind=TrainingChoiceKind.TRAINEE,
        goal=PartyDevelopmentGoal.EVOLUTION,
        candidates=tuple(
            PartyDevelopmentCandidate(item.candidate_index, item.features)
            for item in example.candidates
        ),
    )

    with pytest.raises(PartyDevelopmentCatalogError, match="shared venue"):
        PartyDevelopmentProspectiveBinding.build(
            scenario_id=example.scenario_id,
            root_lineage_id=example.root_lineage_id,
            initial_state_sha256=example.initial_state_sha256,
            partition=example.partition,
            source_commit="a" * 40,
            source_bundle_sha256="b" * 64,
            semantic_snapshot_sha256="e" * 64,
            candidate_set=candidate_set,
            venue_priors=tuple(
                VenueOperationalPrior(
                    available=True,
                    reliability=0.75,
                    expected_yield=0.5,
                    matchup_safety=0.625,
                    travel_cost=0.25,
                    recovery_cost=0.125,
                    support_count=1,
                    evidence_sha256="9" * 64,
                    frozen_before_scenario=True,
                )
                for _ in candidate_set.candidates
            ),
            venue_prior_registry_sha256="c" * 64,
        )


def test_prospective_catalog_rejects_duplicate_outcome_rows() -> None:
    examples = _ready_catalog()
    prospective = _prospective_catalog(examples)

    with pytest.raises(PartyDevelopmentCatalogError, match="exactly"):
        prospective.require_exact_examples((examples[0], *examples))
