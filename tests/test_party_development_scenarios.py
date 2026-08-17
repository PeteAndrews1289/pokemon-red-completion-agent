from __future__ import annotations

import json

import pytest

from pokemon_red_completion.party import MoveObservation, PartyMemberObservation
from pokemon_red_completion.party_development_adapter import BoundPartyDevelopmentMenu
from pokemon_red_completion.party_development_catalog import (
    PartyDevelopmentProspectiveBinding,
    PartyDevelopmentUnavailableReason,
)
from pokemon_red_completion.party_development_outcomes import (
    PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE,
)
from pokemon_red_completion.party_development_rank import (
    CandidateCompletionSemantics,
    EvolutionRouteKind,
    EvolutionSemantics,
    PartyDevelopmentContext,
    PartyDevelopmentGoal,
    VenueOperationalPrior,
    augment_training_candidate_set,
)
from pokemon_red_completion.party_development_scenarios import (
    BALANCED_KIND_GOAL_SELECTION_PROTOCOL,
    BALANCED_REPEATABLE_PARTY_SCENARIO_SCHEMA,
    PartyDevelopmentScenarioOption,
    RepeatablePartyScenarioError,
    permute_bound_party_development_menu,
    select_repeatable_party_scenarios,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.team_training import GrindingArea
from pokemon_red_completion.training_candidate_rank import (
    TRAINING_CANDIDATE_FEATURE_NAMES,
    TrainingCandidate,
    TrainingCandidateSet,
    TrainingChoiceKind,
)


def _prior(character: str = "a") -> VenueOperationalPrior:
    return VenueOperationalPrior(
        available=True,
        reliability=0.75,
        expected_yield=0.6,
        matchup_safety=0.75,
        travel_cost=0.2,
        recovery_cost=0.1,
        support_count=8,
        evidence_sha256=character * 64,
        frozen_before_scenario=True,
    )


def _candidate_set(
    *,
    kind: TrainingChoiceKind,
    goal: PartyDevelopmentGoal,
    width: int,
    variant: int,
):
    rows = []
    for index in range(width):
        features = [0.0] * len(TRAINING_CANDIDATE_FEATURE_NAMES)
        features[TRAINING_CANDIDATE_FEATURE_NAMES.index("choice.trainee")] = float(
            kind is TrainingChoiceKind.TRAINEE
        )
        features[TRAINING_CANDIDATE_FEATURE_NAMES.index("candidate.level")] = 0.15 + 0.1 * index
        features[TRAINING_CANDIDATE_FEATURE_NAMES.index("candidate.hp_ratio")] = (
            0.2 if (variant + index) % 3 == 0 else 0.85
        )
        features[TRAINING_CANDIDATE_FEATURE_NAMES.index("candidate.attack_pp")] = (
            0.25 if (variant + index) % 2 == 0 else 0.9
        )
        rows.append(TrainingCandidate(index, tuple(features)))
    base = TrainingCandidateSet(kind=kind, candidates=tuple(rows))
    context = PartyDevelopmentContext(
        goal=goal,
        party_size=6,
        below_floor_count=4,
        evolution_needed_count=3,
        registration_needed_count=3,
        living_needed_count=2,
        role_gap_count=2,
        registration_completion_ratio=0.4,
        living_completion_ratio=0.3,
        role_coverage_ratio=0.5,
        healthy_trainable_count=5,
        exhausted_count=0,
        fainted_count=0,
    )
    semantics = tuple(
        CandidateCompletionSemantics(
            evolution=EvolutionSemantics(
                required=index % 2 == 0,
                stages_remaining=1 if index % 2 == 0 else 0,
                route_kind=(
                    EvolutionRouteKind.LEVEL if index % 2 == 0 else EvolutionRouteKind.NONE
                ),
                levels_to_next=3 if index % 2 == 0 else None,
            ),
            registration_needed=index % 2 == 0,
            living_target_needed=index % 3 == 0,
            role_needed=index % 2 == 1,
            projected_survival_margin=(-0.6 + 0.5 * index),
        )
        for index in range(width)
    )
    shared = _prior("a")
    priors = (
        tuple(shared for _ in range(width))
        if kind is TrainingChoiceKind.TRAINEE
        else tuple(_prior("abcdef"[index]) for index in range(width))
    )
    return (
        augment_training_candidate_set(
            base,
            context,
            semantics,
            venue_priors=priors,
        ),
        priors,
        (shared if kind is TrainingChoiceKind.TRAINEE else None),
    )


def _option(
    index: int,
    *,
    partition: ScenarioPartition,
    kind: TrainingChoiceKind,
    goal: PartyDevelopmentGoal,
    width: int = 3,
) -> PartyDevelopmentScenarioOption:
    candidates, priors, shared = _candidate_set(
        kind=kind,
        goal=goal,
        width=width,
        variant=index,
    )
    digest = f"{index + 1:064x}"
    binding = PartyDevelopmentProspectiveBinding.build(
        scenario_id=f"pool-option-{partition.value}-{index:03d}",
        root_lineage_id=f"pool-root-{partition.value}-{index:03d}",
        initial_state_sha256=digest,
        partition=partition,
        source_commit="a" * 40,
        source_bundle_sha256="b" * 64,
        semantic_snapshot_sha256=f"{index + 200:064x}",
        candidate_set=candidates,
        venue_priors=priors,
        venue_prior_registry_sha256="c" * 64,
        outcome_objective_sha256=(PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE.objective_sha256),
        shared_venue_prior=shared,
    )
    return PartyDevelopmentScenarioOption(
        option_id=f"private-option-{partition.value}-{index:03d}",
        root_lineage_id=binding.root_lineage_id,
        initial_state_sha256=binding.initial_state_sha256,
        partition=partition,
        candidate_set=candidates,
        binding=binding,
    )


def _pool() -> tuple[PartyDevelopmentScenarioOption, ...]:
    options = []
    for partition, start, count in (
        (ScenarioPartition.TRAIN, 0, 16),
        (ScenarioPartition.DEVELOPMENT, 100, 10),
    ):
        for offset in range(count):
            index = start + offset
            options.append(
                _option(
                    index,
                    partition=partition,
                    kind=tuple(TrainingChoiceKind)[offset % 2],
                    goal=tuple(PartyDevelopmentGoal)[offset % 4],
                    width=2 + offset % 3,
                )
            )
    return tuple(options)


def test_selection_is_reproducible_independent_and_semantically_diverse() -> None:
    first = select_repeatable_party_scenarios(
        _pool(),
        train_count=8,
        development_count=4,
        seed=20260816,
    )
    second = select_repeatable_party_scenarios(
        _pool(),
        train_count=8,
        development_count=4,
        seed=20260816,
    )

    assert first == second
    assert first.plan_sha256 == second.plan_sha256
    assert len(first.assignments) == 12
    assert len({item.root_lineage_id for item in first.assignments}) == 12
    assert len({item.initial_state_sha256 for item in first.assignments}) == 12
    for partition in (ScenarioPartition.TRAIN, ScenarioPartition.DEVELOPMENT):
        selected = tuple(item for item in first.assignments if item.partition is partition)
        assert {item.kind for item in selected} == set(TrainingChoiceKind)
        assert len({item.goal for item in selected}) >= 2
    encoded = json.dumps(first.public_dict(), sort_keys=True)
    assert "private-option" not in encoded
    assert "features" not in encoded
    assert first.public_dict()["teacher_choice_targets"] == 0


def test_seed_changes_randomization_without_crossing_the_split() -> None:
    first = select_repeatable_party_scenarios(_pool(), train_count=8, development_count=4, seed=11)
    second = select_repeatable_party_scenarios(_pool(), train_count=8, development_count=4, seed=12)

    assert first.plan_sha256 != second.plan_sha256
    assert tuple(
        (item.option_sha256, item.candidate_order, item.timing_offset_frames)
        for item in first.assignments
    ) != tuple(
        (item.option_sha256, item.candidate_order, item.timing_offset_frames)
        for item in second.assignments
    )
    assert all(item.partition is ScenarioPartition.TRAIN for item in first.assignments[:8])
    assert all(item.partition is ScenarioPartition.DEVELOPMENT for item in first.assignments[8:])


def test_v2_selection_balances_action_kinds_and_completion_goals() -> None:
    plan = select_repeatable_party_scenarios(
        _pool(),
        train_count=8,
        development_count=4,
        seed=20260816,
        selection_protocol=BALANCED_KIND_GOAL_SELECTION_PROTOCOL,
    )

    assert plan.public_dict()["schema"] == BALANCED_REPEATABLE_PARTY_SCENARIO_SCHEMA
    assert (
        plan.public_dict()["selection_protocol"]
        == BALANCED_KIND_GOAL_SELECTION_PROTOCOL
    )
    for partition in (ScenarioPartition.TRAIN, ScenarioPartition.DEVELOPMENT):
        selected = tuple(
            item for item in plan.assignments if item.partition is partition
        )
        kind_counts = [
            sum(item.kind is kind for item in selected) for kind in TrainingChoiceKind
        ]
        goal_counts = [
            sum(item.goal is goal for item in selected) for goal in PartyDevelopmentGoal
        ]
        assert max(kind_counts) - min(kind_counts) <= 1
        assert max(goal_counts) - min(goal_counts) <= 1


def test_selection_rejects_too_few_independent_roots() -> None:
    pool = tuple(item for item in _pool() if item.partition is ScenarioPartition.DEVELOPMENT)[:3]
    with pytest.raises(
        RepeatablePartyScenarioError,
        match="insufficient independent roots",
    ):
        select_repeatable_party_scenarios(
            tuple(item for item in _pool() if item.partition is ScenarioPartition.TRAIN)[:8] + pool,
            train_count=8,
            development_count=4,
            seed=3,
        )


def test_selection_rejects_cross_partition_root_reuse() -> None:
    pool = list(_pool())
    development_index = next(
        index for index, item in enumerate(pool) if item.partition is ScenarioPartition.DEVELOPMENT
    )
    development = pool[development_index]
    train = pool[0]
    crossed_binding = PartyDevelopmentProspectiveBinding.build(
        scenario_id=development.binding.scenario_id,
        root_lineage_id=train.root_lineage_id,
        initial_state_sha256=development.initial_state_sha256,
        partition=development.partition,
        source_commit=development.binding.source_commit,
        source_bundle_sha256=development.binding.source_bundle_sha256,
        semantic_snapshot_sha256=development.binding.semantic_snapshot_sha256,
        candidate_set=development.candidate_set,
        venue_priors=tuple(
            _prior("abcdef"[index]) for index in range(len(development.candidate_set.candidates))
        )
        if development.candidate_set.kind is TrainingChoiceKind.VENUE
        else tuple(_prior("a") for _ in development.candidate_set.candidates),
        venue_prior_registry_sha256=(development.binding.venue_prior_registry_sha256),
        outcome_objective_sha256=development.binding.outcome_objective_sha256,
        shared_venue_prior=(
            _prior("a") if development.candidate_set.kind is TrainingChoiceKind.TRAINEE else None
        ),
    )
    pool[development_index] = PartyDevelopmentScenarioOption(
        option_id=development.option_id,
        root_lineage_id=train.root_lineage_id,
        initial_state_sha256=development.initial_state_sha256,
        partition=development.partition,
        candidate_set=development.candidate_set,
        binding=crossed_binding,
    )

    with pytest.raises(RepeatablePartyScenarioError, match="crosses"):
        select_repeatable_party_scenarios(tuple(pool), train_count=8, development_count=4, seed=4)


def test_private_candidate_permutation_reindexes_every_parallel_binding() -> None:
    candidates, priors, shared = _candidate_set(
        kind=TrainingChoiceKind.TRAINEE,
        goal=PartyDevelopmentGoal.COLLECTION,
        width=3,
        variant=0,
    )
    members = tuple(
        PartyMemberObservation(
            slot=index + 1,
            species_id=10 + index,
            level=20 + index,
            hp=50,
            max_hp=60,
            moves=(MoveObservation(30 + index, 10, 20),),
            experience=1_000 + index,
        )
        for index in range(3)
    )
    venue = GrindingArea("private-venue", 12, 18, measured_samples=50)
    menu = BoundPartyDevelopmentMenu(
        candidate_set=candidates,
        semantic_snapshot_sha256="d" * 64,
        bindings=members,
        candidate_available=(True, False, True),
        candidate_unavailable_reasons=(
            None,
            PartyDevelopmentUnavailableReason.TRANSITION_UNAVAILABLE,
            None,
        ),
        venue_priors=priors,
        shared_venue=venue,
        shared_venue_prior=shared,
    )

    reordered = permute_bound_party_development_menu(menu, (2, 0, 1))

    assert tuple(item.slot for item in reordered.bindings) == (3, 1, 2)
    assert tuple(item.candidate_index for item in reordered.candidate_set.candidates) == (
        0,
        1,
        2,
    )
    assert tuple(item.features for item in reordered.candidate_set.candidates) == (
        candidates.candidates[2].features,
        candidates.candidates[0].features,
        candidates.candidates[1].features,
    )
    assert reordered.candidate_available == (True, True, False)
    assert reordered.candidate_unavailable_reasons == (
        None,
        None,
        PartyDevelopmentUnavailableReason.TRANSITION_UNAVAILABLE,
    )
    assert reordered.shared_venue == venue
    with pytest.raises(RepeatablePartyScenarioError, match="does not match"):
        permute_bound_party_development_menu(menu, (0, 1, 1))
