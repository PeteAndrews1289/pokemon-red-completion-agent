from __future__ import annotations

import json
from dataclasses import replace

import numpy as np
import pytest

from pokemon_red_completion.party_development_catalog import (
    PartyDevelopmentCatalogError, PartyDevelopmentProspectiveBinding,
)
from pokemon_red_completion.party_development_outcome_learning import (
    PartyDevelopmentOutcomeLearningError, PartyDevelopmentOutcomeModel,
    adapt_party_development_model_from_outcomes,
    upgrade_party_development_model_for_workload,
)
from pokemon_red_completion.party_development_outcomes import (
    PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE, PARTY_DEVELOPMENT_TOTAL_TASK_OBJECTIVE,
    adapt_party_development_outcomes_v2,
)
from pokemon_red_completion.party_development_rank import (
    PARTY_DEVELOPMENT_FEATURE_NAMES, PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID,
    PARTY_DEVELOPMENT_WORKLOAD_FEATURE_NAMES,
    PARTY_DEVELOPMENT_WORKLOAD_FEATURE_SCHEMA_ID,
    CandidateCompletionSemantics, EvolutionRouteKind, EvolutionSemantics,
    PartyDevelopmentCandidateSet, PartyDevelopmentContext,
    PartyDevelopmentFeatureError, PartyDevelopmentGoal,
    VenueOperationalPrior, VenuePriorFeatureMode, VenueTrainingWorkload,
    augment_training_candidate_set,
)
from pokemon_red_completion.player_option_level_workload import OptionLevelWorkload
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.team_training import BalancedTeamPolicy, GrindingArea
from pokemon_red_completion.training_candidate_rank import project_venue_choice_set

from test_party_development_outcome_learning import _initialized_model
from test_party_development_outcomes import _before_party, _completion, _trial


def _project(*, remaining_xp=500, include_workload=True, venues=None, levels=None):
    party = _before_party()
    projected = project_venue_choice_set(
        party, party.members[0], BalancedTeamPolicy(minimum_level=50, required_size=2),
        (GrindingArea("unit-route", 12, 18, measured_samples=100),
         GrindingArea("unit-cave", 18, 24, measured_samples=100)),
    )
    assert projected is not None
    context = PartyDevelopmentContext(
        goal=PartyDevelopmentGoal.EVOLUTION, party_size=2,
        below_floor_count=1, evolution_needed_count=1,
        registration_needed_count=1, living_needed_count=1, role_gap_count=0,
        registration_completion_ratio=0.5, living_completion_ratio=0.5,
        role_coverage_ratio=1.0, healthy_trainable_count=2,
        exhausted_count=0, fainted_count=0,
    )
    semantics = CandidateCompletionSemantics(
        evolution=EvolutionSemantics(True, 1, EvolutionRouteKind.LEVEL, levels_to_next=1),
        registration_needed=True,
    )
    work = OptionLevelWorkload(25, 26, remaining_xp)
    return augment_training_candidate_set(
        projected[1], context, (semantics, semantics),
        include_workload=include_workload,
        level_workloads=(levels if levels is not None else (work, work)) if include_workload else None,
        venue_workloads=venues,
    )


def _binding(menu, objective, *, tag="a", partition=ScenarioPartition.TRAIN):
    return PartyDevelopmentProspectiveBinding.build(
        scenario_id=f"unit-workload-{tag}", root_lineage_id=f"unit-workload-root-{tag}",
        initial_state_sha256=tag * 64, partition=partition,
        source_commit="1" * 40, source_bundle_sha256="2" * 64,
        semantic_snapshot_sha256="3" * 64, candidate_set=menu,
        venue_priors=(VenueOperationalPrior(),) * 2,
        venue_prior_registry_sha256="4" * 64,
        venue_prior_feature_mode=VenuePriorFeatureMode.MASKED_UNCALIBRATED,
        outcome_objective_sha256=objective.objective_sha256,
    )


def _example(*, total_task=True, tag="a", partition=ScenarioPartition.TRAIN, censored=False):
    menu = _project(venues=(VenueTrainingWorkload(0.9, 50), VenueTrainingWorkload(0.2, 5)))
    objective = PARTY_DEVELOPMENT_TOTAL_TASK_OBJECTIVE if total_task else PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE
    binding = _binding(menu, objective, tag=tag, partition=partition)
    complete = _completion(registered=11, evolution_steps=0)
    trials = (
        _trial(menu, 0, gain=100, frames=1_000, completion_after=complete, evolution_completed=True),
        _trial(menu, 1, gain=400, frames=2_000, completion_after=complete,
               evolution_completed=True, censored=censored),
    )
    return adapt_party_development_outcomes_v2(
        menu, trials, scenario_id=binding.scenario_id,
        root_lineage_id=binding.root_lineage_id,
        initial_state_sha256=binding.initial_state_sha256, partition=partition,
        prospective_binding=binding, total_task_efficiency=total_task,
    )


def test_same_level_different_remaining_xp_is_observable_without_changing_v2_prefix():
    legacy = _project(include_workload=False)
    far, near = _project(remaining_xp=500), _project(remaining_xp=10)
    assert legacy.feature_schema_id == PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID
    for old, a, b in zip(legacy.candidates, far.candidates, near.candidates, strict=True):
        assert a.features[:len(PARTY_DEVELOPMENT_FEATURE_NAMES)] == old.features
        assert b.features[:len(PARTY_DEVELOPMENT_FEATURE_NAMES)] == old.features
        differences = [i for i, (x, y) in enumerate(zip(a.features, b.features, strict=True)) if x != y]
        assert differences == [far.feature_names.index("level_workload.remaining_xp")]


def test_known_unusable_and_known_zero_cost_do_not_look_unknown():
    unknown = _project()
    known = _project(venues=(VenueTrainingWorkload(0, 0, travel_steps=0),) * 2)
    values = dict(zip(known.feature_names, known.candidates[0].features, strict=True))
    assert values["venue.useful_encounters_known"] == 1
    assert values["venue.useful_encounter_share"] == 0
    assert values["venue.travel_steps_known"] == 1
    assert values["venue.travel_steps"] == 0
    assert values["venue.recovery_steps_known"] == 0
    assert unknown.candidates[0].features != known.candidates[0].features


@pytest.mark.parametrize("kwargs", [
    {"useful_encounter_share": float("nan")},
    {"useful_encounter_share": -0.1}, {"useful_encounter_share": 1.1},
    {"useful_encounter_share": True},
    {"expected_recipient_xp_per_encounter": float("inf")},
    {"expected_recipient_xp_per_encounter": -1},
    {"useful_encounter_share": 0, "expected_recipient_xp_per_encounter": 1},
    {"travel_steps": True}, {"travel_steps": -1},
    {"recovery_steps": 1_000_001},
])
def test_invalid_or_contradictory_prospective_workload_is_rejected(kwargs):
    values = dict(useful_encounter_share=0.5, expected_recipient_xp_per_encounter=20)
    values.update(kwargs)
    with pytest.raises(PartyDevelopmentFeatureError):
        VenueTrainingWorkload(**values)


def test_venue_menu_cannot_change_the_fixed_trainee_workload_between_candidates():
    with pytest.raises(PartyDevelopmentFeatureError, match="one observed trainee"):
        _project(levels=(OptionLevelWorkload(25, 26, 100), OptionLevelWorkload(25, 26, 200)))


def test_workload_cannot_contradict_the_declared_evolution_distance():
    with pytest.raises(PartyDevelopmentFeatureError, match="contradicts"):
        _project(levels=(OptionLevelWorkload(25, 27, 100),) * 2)


def test_candidate_and_binding_roundtrip_pin_the_new_schema_and_suffix_values():
    menu = _project()
    restored = PartyDevelopmentCandidateSet.from_public_dict(json.loads(json.dumps(menu.public_dict())))
    assert restored == menu
    binding = _binding(menu, PARTY_DEVELOPMENT_TOTAL_TASK_OBJECTIVE)
    restored_binding = PartyDevelopmentProspectiveBinding.from_public_dict(binding.public_dict())
    assert restored_binding == binding
    restored_binding.require_candidate_set(restored)
    with pytest.raises(PartyDevelopmentCatalogError, match="features differ"):
        restored_binding.require_candidate_set(_project(remaining_xp=10))
    bad = menu.public_dict()
    bad["schema"] = "pokemon-party-development-candidate-set-v2"
    with pytest.raises(PartyDevelopmentFeatureError):
        PartyDevelopmentCandidateSet.from_public_dict(bad)


def test_mixed_feature_schema_menu_is_rejected():
    legacy, current = _project(include_workload=False), _project()
    with pytest.raises(PartyDevelopmentFeatureError, match="crosses feature schemas"):
        replace(current, candidates=(legacy.candidates[0], current.candidates[1]))


def test_upgrade_preserves_the_existing_scorer_and_does_not_create_learning():
    base = _initialized_model()
    old_menu = _project(include_workload=False)
    new_menu = _project(venues=(VenueTrainingWorkload(0.9, 50), VenueTrainingWorkload(0.2, 5)))
    original = base.to_dict()
    upgraded = upgrade_party_development_model_for_workload(base)
    assert base.to_dict() == original
    np.testing.assert_array_equal(base.scores(old_menu), upgraded.scores(new_menu))
    np.testing.assert_array_equal(base.weights1, upgraded.weights1[:len(PARTY_DEVELOPMENT_FEATURE_NAMES)])
    assert not np.any(upgraded.weights1[len(PARTY_DEVELOPMENT_FEATURE_NAMES):])
    assert upgraded.teacher_prior == base.teacher_prior
    assert upgraded.outcome_training_examples == base.outcome_training_examples == 0
    assert upgraded.outcome_training_root_lineage_ids == base.outcome_training_root_lineage_ids
    assert upgraded.feature_schema_id == PARTY_DEVELOPMENT_WORKLOAD_FEATURE_SCHEMA_ID
    assert PartyDevelopmentOutcomeModel.from_dict(upgraded.to_dict()).to_dict() == upgraded.to_dict()
    assert PartyDevelopmentOutcomeModel.from_dict(original).to_dict() == original
    with pytest.raises(PartyDevelopmentOutcomeLearningError, match="schemas differ"):
        base.scores(new_menu)
    with pytest.raises(PartyDevelopmentOutcomeLearningError, match="schemas differ"):
        upgraded.scores(old_menu)


def test_whole_task_objective_prefers_fast_completion_over_surplus_xp():
    # Both finish the same evolution. Only the prospectively selected new
    # objective makes the shorter whole task win over a higher surplus XP rate.
    assert _example(total_task=False).best_candidate_indices == (1,)
    result = _example(total_task=True)
    assert result.best_candidate_indices == (0,)
    assert result.objective == PARTY_DEVELOPMENT_TOTAL_TASK_OBJECTIVE
    assert result.feature_names == PARTY_DEVELOPMENT_WORKLOAD_FEATURE_NAMES


def test_objective_cannot_be_substituted_after_prospective_binding():
    menu = _project()
    binding = _binding(menu, PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE)
    with pytest.raises(PartyDevelopmentCatalogError, match="objective"):
        adapt_party_development_outcomes_v2(
            menu, (), scenario_id=binding.scenario_id, root_lineage_id=binding.root_lineage_id,
            initial_state_sha256=binding.initial_state_sha256, partition=binding.partition,
            prospective_binding=binding, total_task_efficiency=True,
        )


def test_synthetic_workload_fit_reuses_the_existing_optimizer_and_retains_schema():
    # ROM-free artificial unit rows only. No native corpus, worker, persisted
    # model, actual gain or evaluation result is produced by this test.
    base = upgrade_party_development_model_for_workload(_initialized_model())
    result = adapt_party_development_model_from_outcomes(base, (_example(),), epochs=40)
    assert result.report.loss_after < result.report.loss_before
    assert result.model.feature_schema_id == base.feature_schema_id
    assert result.model.model_id == base.model_id
    assert result.model.outcome_training_examples == 1
    assert np.any(result.model.weights1[len(PARTY_DEVELOPMENT_FEATURE_NAMES):])


@pytest.mark.parametrize("case", ["development", "censored", "mixed_objectives"])
def test_workload_schema_does_not_relax_fitting_guards(case):
    base = upgrade_party_development_model_for_workload(_initialized_model())
    if case == "development":
        rows = (_example(partition=ScenarioPartition.DEVELOPMENT),)
        message = "partition"
    elif case == "censored":
        rows = (_example(censored=True),)
        message = "censored"
    else:
        rows = (_example(tag="a"), _example(total_task=False, tag="b"))
        message = "objectives differ"
    with pytest.raises(PartyDevelopmentOutcomeLearningError, match=message):
        adapt_party_development_model_from_outcomes(base, rows, epochs=1)


def test_workload_catalog_audit_keeps_the_existing_readiness_thresholds():
    from pokemon_red_completion.party_development_catalog import PartyDevelopmentProspectiveCatalog
    from pokemon_red_completion.party_development_outcome_dataset import audit_party_development_outcome_catalog
    menu = _project(venues=(VenueTrainingWorkload(0.9, 50), VenueTrainingWorkload(0.2, 5)))
    binding = _binding(menu, PARTY_DEVELOPMENT_TOTAL_TASK_OBJECTIVE)
    catalog = PartyDevelopmentProspectiveCatalog.freeze((binding,))
    audit = audit_party_development_outcome_catalog((_example(),), prospective_catalog=catalog)
    assert audit.example_count == 1
    assert not audit.initial_fit_ready
    assert audit.policy.minimum_train_examples == 8


def test_semantic_adapter_carries_observed_work_and_binds_the_selected_objective():
    from test_party_development_adapter import _snapshot
    legacy = _snapshot(venue_prior_feature_mode=VenuePriorFeatureMode.MASKED_UNCALIBRATED)
    observed = replace(
        legacy, include_workload=True,
        level_workloads_by_member=(None, OptionLevelWorkload(24, 28, 1_500), None),
        venue_workloads_by_member=(
            (None,) * 3,
            (VenueTrainingWorkload(0.9, 50), VenueTrainingWorkload(0.2, 5), None),
            (None,) * 3,
        ),
    )
    menu = observed.venue_menu(observed.party.members[1])
    assert menu is not None
    values = dict(zip(menu.candidate_set.feature_names, menu.candidate_set.candidates[0].features, strict=True))
    assert values["level_workload.remaining_xp"] == 1_500 / 2_000_000
    assert values["venue.useful_encounter_share"] == 0.9
    binding = observed.freeze_binding(menu, scenario_id="unit-observed", total_task_efficiency=True)
    assert binding.outcome_objective_sha256 == PARTY_DEVELOPMENT_TOTAL_TASK_OBJECTIVE.objective_sha256
    assert binding.feature_schema_id == PARTY_DEVELOPMENT_WORKLOAD_FEATURE_SCHEMA_ID
    assert observed.semantic_snapshot_sha256 != legacy.semantic_snapshot_sha256
    assert observed.level_workload_for(observed.party.members[0]) is None


def test_semantic_adapter_rejects_unannounced_or_misaligned_workload_observations():
    from pokemon_red_completion.party_development_adapter import PartyDevelopmentAdapterError
    from test_party_development_adapter import _snapshot
    original = _snapshot()
    with pytest.raises(PartyDevelopmentAdapterError, match="opt-in"):
        replace(original, level_workloads_by_member=(None, None, None))
    with pytest.raises(PartyDevelopmentAdapterError, match="align"):
        replace(original, include_workload=True, level_workloads_by_member=(None,))
    with pytest.raises(PartyDevelopmentAdapterError, match="align"):
        replace(original, include_workload=True, venue_workloads_by_member=((None,),) * 3)


def _unit_growth_cartridge():
    from types import SimpleNamespace
    from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
    class UnitGrowthCartridge(RedPracticeCartridge):
        def __init__(self):
            pass
        def species(self, internal_id):
            return SimpleNamespace(experience_at_level=lambda level: level ** 3)
    return UnitGrowthCartridge()


def test_red_workload_uses_exact_observed_xp_and_overdue_evolution_requires_a_level_up():
    from pokemon_red_completion.red_party_development_adapter import observe_red_evolution_workload
    member = replace(_before_party().members[0], experience=25 ** 3 + 100)
    evolution = EvolutionSemantics(True, 1, EvolutionRouteKind.LEVEL, levels_to_next=1)
    work = observe_red_evolution_workload(member, evolution, _unit_growth_cartridge())
    assert work == OptionLevelWorkload(25, 26, 26 ** 3 - member.experience)
    overdue = replace(evolution, levels_to_next=0)
    assert observe_red_evolution_workload(member, overdue, _unit_growth_cartridge()) == work
    assert observe_red_evolution_workload(replace(member, experience=None), evolution,
                                          _unit_growth_cartridge()) is None
    assert observe_red_evolution_workload(member, evolution, None) is None


def test_red_workload_rejects_xp_inconsistent_with_observed_level():
    from pokemon_red_completion.red_party_development_adapter import (
        RedPartyDevelopmentAdapterError, observe_red_evolution_workload,
    )
    member = _before_party().members[0]
    evolution = EvolutionSemantics(True, 1, EvolutionRouteKind.LEVEL, levels_to_next=1)
    with pytest.raises(RedPartyDevelopmentAdapterError, match="XP differs"):
        observe_red_evolution_workload(member, evolution, _unit_growth_cartridge())


def test_red_snapshot_populates_workload_from_its_coherent_party_observation():
    import test_red_party_development_adapter as fixture
    from pokemon_red_completion.party import PartyObservation
    from pokemon_red_completion.red_party_development_adapter import build_red_party_development_snapshot
    observation = fixture._observation()
    members = tuple(replace(member, experience=member.level ** 3 + 100)
                    for member in observation.party.members)
    observation = replace(observation, party=PartyObservation(members=members))
    areas = fixture._areas()
    snapshot = build_red_party_development_snapshot(
        fixture._reservation(), source_root_lineage_id=fixture._CANONICAL_ROOT,
        observation=observation, evolutions=fixture._evolutions(),
        policy=BalancedTeamPolicy(minimum_level=30, required_size=3), areas=areas,
        venue_prior_registry=fixture._registry(areas[0]),
        venue_operational_contract_sha256=("6" * 64,) * 2,
        source_commit="3" * 40, source_bundle_sha256="4" * 64,
        include_workload=True, cartridge=_unit_growth_cartridge(),
    )
    first = snapshot.level_workload_for(members[0])
    assert first == OptionLevelWorkload(22, 26, 26 ** 3 - (22 ** 3 + 100))
    assert snapshot.level_workload_for(members[1]) is None
    assert snapshot.level_workload_for(members[2]) is None
