from __future__ import annotations

import json
from dataclasses import replace

import pytest

import pokemon_red_completion.party_development_catalog as party_development_catalog_module
from pokemon_red_completion.party_development_catalog import (
    PartyDevelopmentCatalogError,
    PartyDevelopmentProspectiveBinding,
    PartyDevelopmentProspectiveCatalog,
    PartyDevelopmentUnavailableReason,
)
from pokemon_red_completion.party_development_frozen_catalog import (
    PartyDevelopmentFrozenCatalog,
    PartyDevelopmentFrozenCatalogError,
    PartyDevelopmentFrozenQuestion,
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
    candidate_count: int = 3,
) -> ScenarioOutcomeExample:
    candidates = []
    outcomes = []
    for candidate_index in range(candidate_count):
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
        outcomes.append(_outcome(candidate_index == index % candidate_count))
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


def _ready_catalog(
    *,
    candidate_widths: tuple[int, ...] | None = None,
) -> tuple[ScenarioOutcomeExample, ...]:
    widths = candidate_widths or (3,) * 14
    if len(widths) != 14:
        raise ValueError("candidate widths must cover all fourteen examples")
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
                candidate_count=widths[index],
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
                candidate_count=widths[index],
            )
        )
    return tuple(examples)


def _prospective_catalog(
    examples: tuple[ScenarioOutcomeExample, ...],
    *,
    semantic_snapshot_sha256: str | None = None,
    venue_prior_registry_sha256: str = "c" * 64,
    source_commit: str = "a" * 40,
    source_bundle_sha256: str = "b" * 64,
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
                source_commit=source_commit,
                source_bundle_sha256=source_bundle_sha256,
                semantic_snapshot_sha256=(semantic_snapshot_sha256 or example.initial_state_sha256),
                candidate_set=candidate_set,
                venue_priors=priors,
                venue_prior_registry_sha256=venue_prior_registry_sha256,
                outcome_objective_sha256=(PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE.objective_sha256),
                shared_venue_prior=(shared_prior if kind is TrainingChoiceKind.TRAINEE else None),
                candidate_available=tuple(item.available for item in example.candidates),
                candidate_unavailable_reasons=tuple(
                    None
                    if item.available
                    else PartyDevelopmentUnavailableReason.INSUFFICIENT_VENUE_EVIDENCE
                    for item in example.candidates
                ),
            )
        )
    return PartyDevelopmentProspectiveCatalog.freeze(tuple(bindings))


def _bound_campaign(
    examples: tuple[ScenarioOutcomeExample, ...],
) -> tuple[tuple[ScenarioOutcomeExample, ...], PartyDevelopmentProspectiveCatalog]:
    prospective = _prospective_catalog(examples)
    by_scenario = {item.scenario_id: item for item in prospective.bindings}
    bound = tuple(
        replace(
            example,
            prospective_binding_sha256=by_scenario[example.scenario_id].binding_sha256,
        )
        for example in examples
    )
    return bound, prospective


def test_diverse_isolated_catalog_reaches_only_the_initial_fit_gate() -> None:
    examples, prospective = _bound_campaign(_ready_catalog())
    audit = audit_party_development_outcome_catalog(
        examples,
        prospective_catalog=prospective,
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


def test_identity_free_candidate_set_and_binding_round_trip_exactly() -> None:
    example = _ready_catalog()[0]
    prospective = _prospective_catalog((example,))
    candidate_set = PartyDevelopmentCandidateSet(
        kind=prospective.bindings[0].kind,
        goal=prospective.bindings[0].goal,
        candidates=tuple(
            PartyDevelopmentCandidate(item.candidate_index, item.features)
            for item in example.candidates
        ),
    )

    restored_candidates = PartyDevelopmentCandidateSet.from_public_dict(
        candidate_set.public_dict()
    )
    restored_binding = PartyDevelopmentProspectiveBinding.from_public_dict(
        prospective.bindings[0].public_dict()
    )

    assert restored_candidates == candidate_set
    assert restored_binding == prospective.bindings[0]
    restored_binding.require_candidate_set(restored_candidates)


def _frozen_input_catalog(
    *,
    candidate_widths: tuple[int, ...] | None = None,
) -> PartyDevelopmentFrozenCatalog:
    examples = _ready_catalog(candidate_widths=candidate_widths)
    prospective = _prospective_catalog(examples)
    bindings_by_scenario = {
        item.scenario_id: item for item in prospective.bindings
    }
    questions = []
    for index, example in enumerate(examples):
        binding = bindings_by_scenario[example.scenario_id]
        candidate_set = PartyDevelopmentCandidateSet(
            kind=binding.kind,
            goal=binding.goal,
            candidates=tuple(
                PartyDevelopmentCandidate(item.candidate_index, item.features)
                for item in example.candidates
            ),
        )
        prepared = index in {7, 13}
        profile_id = f"source-profile-{index:02d}"
        questions.append(
            PartyDevelopmentFrozenQuestion(
                capture_id=(
                    f"prepared-capture-{index:02d}" if prepared else profile_id
                ),
                capture_envelope_sha256=("123456789abcdef0"[index] * 64),
                profile_id=profile_id,
                profile_file_sha256=("23456789abcdef01"[index] * 64),
                binding=binding,
                candidate_set=candidate_set,
                materialization_artifact_id=(
                    f"prepared-artifact-{index:02d}" if prepared else None
                ),
                materialization_manifest_sha256=(
                    ("3456789abcdef012"[index] * 64) if prepared else None
                ),
            )
        )
    return PartyDevelopmentFrozenCatalog.freeze(
        tuple(questions),
        reservation_plan_file_sha256="1" * 64,
        reservation_plan_sha256="2" * 64,
        inventory_file_sha256="3" * 64,
        inventory_sha256="4" * 64,
        pp_plan_file_sha256="5" * 64,
        pp_plan_sha256="6" * 64,
        context_catalog_file_sha256="7" * 64,
        context_catalog_sha256="8" * 64,
        venue_prior_registry_file_sha256="9" * 64,
        venue_prior_registry_sha256="c" * 64,
        rom_sha256="d" * 64,
        source_commit="a" * 40,
        source_bundle_sha256="b" * 64,
    )


def test_private_frozen_catalog_retains_features_without_opening_an_answer() -> None:
    catalog = _frozen_input_catalog()
    restored = PartyDevelopmentFrozenCatalog.from_private_dict(
        catalog.private_dict()
    )

    assert restored == catalog
    assert len(restored.questions) == 14
    assert sum(
        item.materialization_artifact_id is not None for item in restored.questions
    ) == 2
    assert restored.public_summary()["partition_counts"] == {
        "development": 6,
        "train": 8,
    }
    assert restored.public_summary()["outcomes_opened"] == 0
    assert restored.public_summary()["candidate_feature_values_public"] is False


def test_private_frozen_catalog_rejects_retained_feature_drift() -> None:
    document = _frozen_input_catalog().private_dict()
    questions = document["questions"]
    assert isinstance(questions, list)
    first = questions[0]
    assert isinstance(first, dict)
    candidate_set = first["candidate_set"]
    assert isinstance(candidate_set, dict)
    candidates = candidate_set["candidates"]
    assert isinstance(candidates, list)
    candidate = candidates[0]
    assert isinstance(candidate, dict)
    features = candidate["features"]
    assert isinstance(features, dict)
    features["candidate.hp_ratio"] += 0.01

    with pytest.raises(
        PartyDevelopmentFrozenCatalogError,
        match="features differ",
    ):
        PartyDevelopmentFrozenCatalog.from_private_dict(document)


def test_small_semantically_thin_catalog_reports_every_missing_gate() -> None:
    examples, prospective = _bound_campaign((_ready_catalog()[0],))
    audit = audit_party_development_outcome_catalog(
        examples,
        prospective_catalog=prospective,
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
    frozen, prospective = _bound_campaign(tuple(examples))

    audit = audit_party_development_outcome_catalog(
        frozen,
        prospective_catalog=prospective,
    )

    assert not audit.initial_fit_ready
    assert "insufficient_development_health_diversity" in audit.reasons
    assert "insufficient_development_pp_diversity" in audit.reasons
    assert "insufficient_development_evolution_route_diversity" in audit.reasons
    assert "insufficient_development_semantic_menu_diversity" in audit.reasons


def test_outcomes_must_match_the_exact_prospectively_frozen_candidate_menu() -> None:
    examples, prospective = _bound_campaign(_ready_catalog())
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
            outcome_objective_sha256=(PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE.objective_sha256),
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
            outcome_objective_sha256=(PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE.objective_sha256),
        )


def test_prospective_catalog_rejects_duplicate_outcome_rows() -> None:
    examples = _ready_catalog()
    prospective = _prospective_catalog(examples)

    with pytest.raises(PartyDevelopmentCatalogError, match="exactly"):
        prospective.require_exact_examples((examples[0], *examples))


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("objective", "prospective objective"),
        ("feature_names", "prospective feature contract"),
        ("prospective_binding", "re-attest its prospective binding"),
    ),
)
def test_prospective_join_rejects_every_outcome_contract_drift(
    mutation: str,
    message: str,
) -> None:
    examples, prospective = _bound_campaign((_ready_catalog()[0],))
    example = examples[0]
    if mutation == "objective":
        changed = replace(
            example,
            objective=replace(
                PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE,
                objective_id="party-development.mutated-objective.v1",
            ),
        )
    elif mutation == "feature_names":
        names = list(example.feature_names)
        names[0], names[1] = names[1], names[0]
        changed = replace(example, feature_names=tuple(names))
    else:
        changed = replace(example, prospective_binding_sha256="f" * 64)

    with pytest.raises(PartyDevelopmentCatalogError, match=message):
        prospective.require_exact_examples((changed,))


@pytest.mark.parametrize(
    "catalog_kwargs",
    (
        {"semantic_snapshot_sha256": "d" * 64},
        {"venue_prior_registry_sha256": "e" * 64},
        {"source_commit": "f" * 40},
        {"source_bundle_sha256": "1" * 64},
    ),
)
def test_outcome_cannot_join_to_a_different_prospective_context(
    catalog_kwargs: dict[str, str],
) -> None:
    raw = (_ready_catalog()[0],)
    bound, _ = _bound_campaign(raw)
    drifted = _prospective_catalog(raw, **catalog_kwargs)

    with pytest.raises(
        PartyDevelopmentCatalogError,
        match="re-attest its prospective binding",
    ):
        drifted.require_exact_examples(bound)


@pytest.mark.parametrize(
    "mutation",
    ("objective", "feature_names", "candidate_features", "shared_evidence"),
)
def test_prospective_digests_commit_every_transitive_menu_dimension(
    mutation: str,
) -> None:
    binding = _prospective_catalog((_ready_catalog()[0],)).bindings[0]
    if mutation == "objective":
        changed = {"outcome_objective_sha256": "d" * 64}
        message = "binding digest differs"
    elif mutation == "feature_names":
        changed = {"feature_names_sha256": "e" * 64}
        message = "binding digest differs"
    elif mutation == "candidate_features":
        changed = {
            "candidate_feature_sha256": (
                "f" * 64,
                *binding.candidate_feature_sha256[1:],
            )
        }
        message = "candidate menu digest differs"
    else:
        changed = {"shared_venue_prior_evidence_sha256": "1" * 64}
        message = "candidate menu digest differs"

    with pytest.raises(PartyDevelopmentCatalogError, match=message):
        replace(binding, **changed)


def test_prospective_menu_digest_commits_candidate_availability_directly() -> None:
    binding = _prospective_catalog((_ready_catalog()[0],)).bindings[0]

    with pytest.raises(PartyDevelopmentCatalogError, match="candidate menu digest differs"):
        replace(
            binding,
            candidate_available=(True, True, False),
            candidate_unavailable_reasons=(
                None,
                None,
                PartyDevelopmentUnavailableReason.INSUFFICIENT_VENUE_EVIDENCE,
            ),
        )


def test_prospective_menu_digest_commits_candidate_specific_venue_evidence() -> None:
    binding = _prospective_catalog((_ready_catalog()[1],)).bindings[0]
    evidence = list(binding.venue_prior_evidence_sha256)
    evidence[0] = "2" * 64

    with pytest.raises(PartyDevelopmentCatalogError, match="candidate menu digest differs"):
        replace(binding, venue_prior_evidence_sha256=tuple(evidence))


def test_prospective_join_distinguishes_a_masked_candidate() -> None:
    raw = _ready_catalog()[0]
    masked_candidate = replace(raw.candidates[2], available=False)
    masked = replace(
        raw,
        candidates=(*raw.candidates[:2], masked_candidate),
        outcomes=(*raw.outcomes[:2], None),
    )
    examples, prospective = _bound_campaign((masked,))

    prospective.require_exact_examples(examples)
    unmasked = replace(
        examples[0],
        candidates=(
            *examples[0].candidates[:2],
            replace(examples[0].candidates[2], available=True),
        ),
    )
    with pytest.raises(PartyDevelopmentCatalogError, match="prospective availability"):
        prospective.require_exact_examples((unmasked,))


def test_prospective_menu_binds_the_causal_reason_for_a_masked_candidate() -> None:
    raw = _ready_catalog()[0]
    masked = replace(
        raw,
        candidates=(
            *raw.candidates[:2],
            replace(raw.candidates[2], available=False),
        ),
        outcomes=(*raw.outcomes[:2], None),
    )
    binding = _prospective_catalog((masked,)).bindings[0]

    assert binding.candidate_unavailable_reasons == (
        None,
        None,
        PartyDevelopmentUnavailableReason.INSUFFICIENT_VENUE_EVIDENCE,
    )
    with pytest.raises(PartyDevelopmentCatalogError, match="candidate menu digest differs"):
        replace(
            binding,
            candidate_unavailable_reasons=(
                None,
                None,
                PartyDevelopmentUnavailableReason.MISSING_RESOURCE,
            ),
        )


def test_prospective_build_rejects_an_unexplained_mask_before_hashing() -> None:
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

    with pytest.raises(PartyDevelopmentCatalogError, match="causal reason"):
        PartyDevelopmentProspectiveBinding.build(
            scenario_id="unexplained-mask",
            root_lineage_id="unexplained-root",
            initial_state_sha256="f" * 64,
            partition=ScenarioPartition.TRAIN,
            source_commit="a" * 40,
            source_bundle_sha256="b" * 64,
            semantic_snapshot_sha256="e" * 64,
            candidate_set=candidate_set,
            venue_priors=tuple(shared_prior for _ in candidate_set.candidates),
            venue_prior_registry_sha256="c" * 64,
            outcome_objective_sha256=(
                PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE.objective_sha256
            ),
            shared_venue_prior=shared_prior,
            candidate_available=(True, True, False),
        )


def test_prospective_join_uses_the_frozen_feature_vocabulary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    examples, prospective = _bound_campaign((_ready_catalog()[0],))
    changed_names = list(examples[0].feature_names)
    changed_names[0], changed_names[1] = changed_names[1], changed_names[0]
    changed_feature_names = tuple(changed_names)
    monkeypatch.setattr(
        party_development_catalog_module,
        "PARTY_DEVELOPMENT_FEATURE_NAMES",
        changed_feature_names,
    )
    changed = replace(examples[0], feature_names=changed_feature_names)

    with pytest.raises(PartyDevelopmentCatalogError, match="prospective feature contract"):
        prospective.require_exact_examples((changed,))
