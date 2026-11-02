from __future__ import annotations

import json
import random
from dataclasses import replace

import numpy as np
import pytest

from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalOpportunity,
    GoalSelectionMode,
    GoalSituation,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.goal_resource_quote import GoalResourceQuote
from pokemon_red_completion.living_dex_option_value import (
    LIVING_DEX_OPTION_OUTCOME_NAMES,
    LivingDexOptionAvailability,
    LivingDexOptionCandidate,
    LivingDexOptionFeatures,
    LivingDexOptionKind,
    LivingDexOptionUtility,
    LivingDexOptionValueModel,
    option_feature_names,
)
from pokemon_red_completion.red_live_option_menu import (
    RedLiveOptionMenuError,
    RedLiveOptionSelectionMode,
    build_red_live_forced_singleton,
    build_red_live_option_set,
    select_red_live_option,
    supplemental_live_option,
)
from pokemon_red_completion.resource_economy_observation import EconomySnapshot


def _situation(
    *, resources: float = 0.9, safety: float = 0.1, storage: float = 0.2
) -> GoalSituation:
    return GoalSituation(
        story_pressure=0.0,
        collection_pressure=0.8,
        team_pressure=0.1,
        evolution_pressure=0.3,
        safety_pressure=safety,
        resource_pressure=resources,
        storage_pressure=storage,
        recovery_pressure=0.0,
        exploration_pressure=0.5,
    )


def _binding(
    kind: GoalKind,
    *,
    binding_ref: str,
    calls: list[str],
    quote: GoalResourceQuote | None = None,
) -> ExecutableGoalBinding:
    def execute() -> GoalExecutionReport:
        calls.append(binding_ref)
        return GoalExecutionReport(1, 1, {})

    return ExecutableGoalBinding(
        binding_ref=binding_ref,
        kind=kind,
        estimated_effort=0.2,
        estimated_risk=0.1,
        execute=execute,
        verify=lambda _report: GoalVerification.succeeded(),
        resource_quote=quote,
    )


def _ordinary_bindings(calls: list[str]) -> GoalBindingSet:
    restore = _binding(
        GoalKind.RESTORE_TEAM,
        binding_ref="private:red:center-route",
        calls=calls,
    )
    resupply = _binding(
        GoalKind.RESUPPLY,
        binding_ref="private:red:trainer-income",
        calls=calls,
        quote=GoalResourceQuote(
            available_funds=58,
            purchase_cost=0,
            reserves=(),
            expected_income=455,
        ),
    )
    by_kind = {binding.kind: binding for binding in (restore, resupply)}
    opportunities = tuple(
        by_kind[kind].opportunity
        if kind in by_kind
        else GoalOpportunity(
            binding_ref=f"private:red:masked:{kind.value}",
            kind=kind,
            availability=GoalAvailability.UNAVAILABLE,
            unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET,
        )
        for kind in GoalKind
    )
    return GoalBindingSet(opportunities, (restore, resupply))


def _no_ordinary_bindings() -> GoalBindingSet:
    return GoalBindingSet(
        tuple(
            GoalOpportunity(
                binding_ref=f"private:red:masked:{kind.value}",
                kind=kind,
                availability=GoalAvailability.UNAVAILABLE,
                unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET,
            )
            for kind in GoalKind
        ),
        (),
    )


@pytest.mark.parametrize("partial_is_ordinary", [False, True])
def test_approach_prior_is_scope_based_and_equal_for_both_menu_seams(partial_is_ordinary):
    from pokemon_red_completion.living_dex_goal_policy import project_living_dex_goal_candidate

    calls = []
    partial = replace(_binding(GoalKind.ADVANCE_STORY, binding_ref="opaque-one", calls=calls),
                      story_objective_ref="hidden-first", story_approach_only=True)
    terminal = replace(_binding(GoalKind.ADVANCE_STORY, binding_ref="opaque-two", calls=calls),
                       story_objective_ref="hidden-second")
    primary, extra = (partial, terminal) if partial_is_ordinary else (terminal, partial)
    mask = GoalOpportunity("masked", GoalKind.EXPLORE, GoalAvailability.UNAVAILABLE,
                           unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET)
    ordinary = GoalBindingSet((primary.opportunity, mask), (primary,))
    question = GoalBindingSet((extra.opportunity, mask), (extra,)).question(
        _situation(resources=0.1),
    )
    candidate = project_living_dex_goal_candidate(
        question, 0, feature_version=5, binding_ref=extra.binding_ref,
    )
    options = build_red_live_option_set(
        situation=_situation(resources=0.1), binding_set=ordinary,
        supplements=(supplemental_live_option(extra, candidate),),
        model_feature_version=5, ordering_seed_sha256="a" * 64,
        economy_snapshot=EconomySnapshot(58, ()), target_cash=0,
    )
    by_ref = {c.binding_ref: c for c in options.menu.candidates}
    assert by_ref[partial.binding_ref].features.dependency_unlock_gain == 0.5
    assert by_ref[terminal.binding_ref].features.dependency_unlock_gain == 1.0
    assert partial.opportunity == replace(partial, story_approach_only=False).opportunity
    public = json.dumps(options.public_dict())
    assert all(private not in public for private in (
        "opaque-one", "opaque-two", "hidden-first", "hidden-second", "story_approach_only",
    ))
    assert calls == []


@pytest.mark.parametrize("value", [None, 0, 1, "yes"])
def test_approach_scope_requires_boolean(value):
    from pokemon_red_completion.goal_manager_runtime import GoalManagerRuntimeError

    with pytest.raises(GoalManagerRuntimeError, match="story approach"):
        replace(_binding(GoalKind.ADVANCE_STORY, binding_ref="opaque", calls=[]),
                story_approach_only=value)


def test_nonstory_cannot_claim_approach_scope():
    from pokemon_red_completion.goal_manager_runtime import GoalManagerRuntimeError

    with pytest.raises(GoalManagerRuntimeError, match="story approach"):
        replace(_binding(GoalKind.ACQUIRE_SPECIES, binding_ref="opaque", calls=[]),
                story_approach_only=True)


def test_private_target_variants_with_equal_features_sample_without_model_query(monkeypatch):
    calls = []
    bindings = tuple(_binding(GoalKind.ACQUIRE_SPECIES, binding_ref=f"target-{i}", calls=calls)
                     for i in range(2))
    options = build_red_live_option_set(
        situation=_situation(resources=0.1),
        binding_set=_no_ordinary_bindings(),
        supplements=tuple(supplemental_live_option(b, _fishing_candidate(b.binding_ref, travel=0.2))
                          for b in bindings),
        model_feature_version=4,
        ordering_seed_sha256="a" * 64,
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("equal targets queried the model scorer")

    monkeypatch.setattr(LivingDexOptionValueModel, "scores", forbidden)
    monkeypatch.setattr(random.Random, "choices", forbidden)
    first = select_red_live_option(_model(), options, seed=1)
    again = select_red_live_option(_model(), options, seed=1)
    assert first.mode is RedLiveOptionSelectionMode.EQUIVALENT_EXPLORATION
    assert first.selected_candidate_index == again.selected_candidate_index
    assert first.probabilities == (0.5, 0.5)
    assert first.scores == (None, None)
    assert first.selected_binding.binding_ref == (
        options.bindings[first.selected_candidate_index].binding_ref
    )
    assert "target-" not in str(first.public_dict())
    assert calls == []


def _fishing_candidate(binding_ref: str, *, travel: float) -> LivingDexOptionCandidate:
    return LivingDexOptionCandidate(
        binding_ref=binding_ref,
        features=LivingDexOptionFeatures(
            kind=LivingDexOptionKind.ACQUIRE,
            completion_gain=0.25,
            dependency_unlock_gain=0.0,
            travel_effort=travel,
            execution_effort=0.4,
            resource_cost=0.1,
            storage_cost=0.01,
            party_risk=0.0,
            irreversibility_risk=0.0,
            uncertainty=0.3,
        ),
        availability=LivingDexOptionAvailability.AVAILABLE,
    )


def _model() -> LivingDexOptionValueModel:
    feature_version = 4
    names = option_feature_names(feature_version)
    coefficients = np.zeros((len(names), len(LIVING_DEX_OPTION_OUTCOME_NAMES)), dtype=np.float64)
    coefficients[names.index("kind.acquire"), 0] = 10.0
    return LivingDexOptionValueModel(
        coefficients=coefficients,
        intercept=np.zeros(len(LIVING_DEX_OPTION_OUTCOME_NAMES), dtype=np.float64),
        feature_mean=np.zeros(len(names), dtype=np.float64),
        feature_scale=np.ones(len(names), dtype=np.float64),
        train_dataset_sha256="a" * 64,
        settled_examples=108,
        censored_examples=0,
        ridge=0.25,
        maximum_importance_weight=4.0,
        feature_version=feature_version,
    )


def _mixed(calls: list[str]):
    first = _binding(
        GoalKind.ACQUIRE_SPECIES,
        binding_ref="private:red:fishing-map-23",
        calls=calls,
    )
    second = _binding(
        GoalKind.ACQUIRE_SPECIES,
        binding_ref="private:red:fishing-map-24",
        calls=calls,
    )
    supplements = (
        supplemental_live_option(first, _fishing_candidate("provider-row-0", travel=0.1)),
        supplemental_live_option(second, _fishing_candidate("provider-row-1", travel=0.8)),
    )
    return build_red_live_option_set(
        situation=_situation(),
        binding_set=_ordinary_bindings(calls),
        supplements=supplements,
        model_feature_version=4,
        ordering_seed_sha256="b" * 64,
        economy_snapshot=EconomySnapshot(58, (("capture", 6),)),
        target_cash=400,
    )


def test_mixed_menu_exposes_real_families_without_private_identity_or_actions() -> None:
    calls: list[str] = []
    options = _mixed(calls)

    assert calls == []
    assert len(options.menu.candidates) == 4
    assert {item.features.kind for item in options.menu.candidates} == {
        LivingDexOptionKind.ACQUIRE,
        LivingDexOptionKind.RESUPPLY,
        LivingDexOptionKind.RESTORE,
    }
    public = options.public_dict()
    encoded = json.dumps(public, sort_keys=True)
    assert public["distinct_option_kinds"] == 3
    assert public["ordinary_candidate_count"] == 2
    assert public["supplemental_candidate_count"] == 2
    assert "private:red" not in encoded
    assert "fishing-map" not in encoded
    assert "binding_ref" not in encoded


def test_supplemental_singleton_is_forced_identity_free_and_action_free() -> None:
    calls: list[str] = []
    original = _no_ordinary_bindings()
    fishing = _binding(
        GoalKind.ACQUIRE_SPECIES,
        binding_ref="private:red:fishing-map-23",
        calls=calls,
    )
    forced = build_red_live_forced_singleton(
        situation=_situation(),
        binding_set=original,
        supplements=(
            supplemental_live_option(
                fishing,
                _fishing_candidate("provider-row", travel=0.2),
            ),
        ),
        economy_snapshot=EconomySnapshot(58, (("capture", 6),)),
        target_cash=400,
    )

    question = forced.binding_set.question(forced.situation)
    assert calls == []
    assert forced.binding is fishing
    assert len(question.available_indices) == 1
    assert question.opportunities[question.available_indices[0]] == fishing.opportunity
    assert tuple(
        opportunity
        for opportunity in forced.binding_set.opportunities
        if opportunity.kind is not GoalKind.ACQUIRE_SPECIES
    ) == tuple(
        opportunity
        for opportunity in original.opportunities
        if opportunity.kind is not GoalKind.ACQUIRE_SPECIES
    )
    public = forced.public_dict()
    encoded = json.dumps(public, sort_keys=True)
    assert public["selection_mode"] == GoalSelectionMode.FORCED_SINGLETON.value
    assert public["model_queries"] == public["teacher_labels"] == 0
    assert public["training_examples"] == 0
    assert public["policy_sha256"] == forced.policy_sha256
    assert "private:red" not in encoded
    assert "fishing-map" not in encoded
    assert "binding_ref" not in encoded


@pytest.mark.parametrize("supplement_count", (0, 2))
def test_forced_singleton_rejects_any_non_singleton_inventory(
    supplement_count: int,
) -> None:
    calls: list[str] = []
    supplements = tuple(
        supplemental_live_option(
            _binding(
                GoalKind.ACQUIRE_SPECIES,
                binding_ref=f"private:red:fishing-map-{index}",
                calls=calls,
            ),
            _fishing_candidate(f"provider-row-{index}", travel=0.2),
        )
        for index in range(supplement_count)
    )

    with pytest.raises(RedLiveOptionMenuError, match="exactly one candidate"):
        build_red_live_forced_singleton(
            situation=_situation(),
            binding_set=_no_ordinary_bindings(),
            supplements=supplements,
        )
    assert calls == []


def test_forced_singleton_rejects_ordinary_executor_or_non_acquisition() -> None:
    calls: list[str] = []
    acquisition = supplemental_live_option(
        _binding(
            GoalKind.ACQUIRE_SPECIES,
            binding_ref="private:red:fishing-map-23",
            calls=calls,
        ),
        _fishing_candidate("provider-row", travel=0.2),
    )
    with pytest.raises(RedLiveOptionMenuError, match="ordinary executors"):
        build_red_live_forced_singleton(
            situation=_situation(),
            binding_set=_ordinary_bindings(calls),
            supplements=(acquisition,),
        )

    resupply = _binding(
        GoalKind.RESUPPLY,
        binding_ref="private:red:trainer-income",
        calls=calls,
        quote=GoalResourceQuote(58, 0, (), expected_income=455),
    )
    wrong = supplemental_live_option(
        resupply,
        _fishing_candidate("provider-row", travel=0.2),
    )
    with pytest.raises(RedLiveOptionMenuError, match="portable acquisition"):
        build_red_live_forced_singleton(
            situation=_situation(),
            binding_set=_no_ordinary_bindings(),
            supplements=(wrong,),
        )
    assert calls == []


def test_forced_singleton_preserves_storage_and_economy_guards() -> None:
    calls: list[str] = []
    fishing = supplemental_live_option(
        _binding(
            GoalKind.ACQUIRE_SPECIES,
            binding_ref="private:red:fishing-map-23",
            calls=calls,
        ),
        _fishing_candidate("provider-row", travel=0.2),
    )
    with pytest.raises(RedLiveOptionMenuError, match="storage safety"):
        build_red_live_forced_singleton(
            situation=_situation(storage=1.0),
            binding_set=_no_ordinary_bindings(),
            supplements=(fishing,),
        )
    with pytest.raises(RedLiveOptionMenuError, match="economy context"):
        build_red_live_forced_singleton(
            situation=_situation(),
            binding_set=_no_ordinary_bindings(),
            supplements=(fishing,),
            economy_snapshot=EconomySnapshot(58, ()),
        )
    assert calls == []


def test_forced_singleton_allows_acquisition_at_exact_storage_gate() -> None:
    calls: list[str] = []
    fishing = supplemental_live_option(
        _binding(
            GoalKind.ACQUIRE_SPECIES,
            binding_ref="private:red:fishing-map-23",
            calls=calls,
        ),
        _fishing_candidate("provider-row", travel=0.2),
    )

    forced = build_red_live_forced_singleton(
        situation=_situation(storage=0.75),
        binding_set=_no_ordinary_bindings(),
        supplements=(fishing,),
    )

    assert forced.binding.kind is GoalKind.ACQUIRE_SPECIES
    assert calls == []


@pytest.mark.parametrize("supplement_count", (0, 1))
def test_mixed_menu_preserves_ordinary_families_with_zero_or_one_supplements(
    supplement_count,
) -> None:
    calls: list[str] = []
    fishing = _binding(
        GoalKind.ACQUIRE_SPECIES,
        binding_ref="private:red:fishing-map-23",
        calls=calls,
    )
    supplements = (
        supplemental_live_option(
            fishing,
            _fishing_candidate("provider-row-0", travel=0.1),
        ),
    )[:supplement_count]

    options = build_red_live_option_set(
        situation=_situation(),
        binding_set=_ordinary_bindings(calls),
        supplements=supplements,
        model_feature_version=4,
        ordering_seed_sha256="e" * 64,
        economy_snapshot=EconomySnapshot(58, (("capture", 6),)),
        target_cash=400,
    )

    assert calls == []
    assert options.public_dict()["ordinary_candidate_count"] == 2
    assert options.public_dict()["supplemental_candidate_count"] == supplement_count
    kinds = {item.features.kind for item in options.menu.candidates}
    assert kinds >= {LivingDexOptionKind.RESUPPLY, LivingDexOptionKind.RESTORE}
    assert (LivingDexOptionKind.ACQUIRE in kinds) is bool(supplement_count)


def test_model_selects_one_exact_private_binding_without_executing_it() -> None:
    calls: list[str] = []
    options = _mixed(calls)
    utility = LivingDexOptionUtility(
        success_weight=50.0,
        completion_gain_weight=0.1,
        dependency_unlock_weight=0.0,
        action_cost_weight=0.0,
        frame_cost_weight=0.0,
        resource_cost_weight=0.0,
        party_cost_weight=0.0,
        storage_cost_weight=0.0,
        irreversible_loss_weight=0.0,
    )

    choice = select_red_live_option(
        _model(),
        options,
        seed=7,
        exploration_mix=0.0,
        utility=utility,
        allow_earning_exploration=True,
    )

    assert choice.mode is RedLiveOptionSelectionMode.MODEL_EXPLORATION
    assert choice.selected_binding.kind is GoalKind.ACQUIRE_SPECIES
    assert calls == []
    encoded = json.dumps(choice.public_dict(), sort_keys=True)
    assert choice.public_dict()["actions_executed"] == 0
    assert choice.public_dict()["emulator_frames"] == 0
    assert "private:red" not in encoded
    assert "fishing-map" not in encoded


def test_model_can_select_from_supplemental_options_without_an_ordinary_goal() -> None:
    calls: list[str] = []
    first = _binding(
        GoalKind.ACQUIRE_SPECIES,
        binding_ref="private:red:fishing-map-23",
        calls=calls,
    )
    second = _binding(
        GoalKind.ACQUIRE_SPECIES,
        binding_ref="private:red:fishing-map-24",
        calls=calls,
    )
    options = build_red_live_option_set(
        situation=_situation(resources=0.2),
        binding_set=_no_ordinary_bindings(),
        supplements=(
            supplemental_live_option(first, _fishing_candidate("provider-row-0", travel=0.1)),
            supplemental_live_option(second, _fishing_candidate("provider-row-1", travel=0.8)),
        ),
        model_feature_version=4,
        ordering_seed_sha256="c" * 64,
        economy_snapshot=EconomySnapshot(58, (("capture", 6),)),
        target_cash=400,
    )

    choice = select_red_live_option(
        _model(),
        options,
        seed=4,
        allow_earning_exploration=True,
    )

    assert options.public_dict()["ordinary_candidate_count"] == 0
    assert options.public_dict()["supplemental_candidate_count"] == 2
    assert choice.selected_binding.kind is GoalKind.ACQUIRE_SPECIES
    assert choice.mode is RedLiveOptionSelectionMode.MODEL_EXPLORATION
    assert calls == []


def test_supplemental_only_acquisitions_still_obey_storage_safety() -> None:
    calls: list[str] = []
    supplements = tuple(
        supplemental_live_option(
            _binding(
                GoalKind.ACQUIRE_SPECIES,
                binding_ref=f"private:red:fishing-map-{index}",
                calls=calls,
            ),
            _fishing_candidate(f"provider-row-{index}", travel=travel),
        )
        for index, travel in ((23, 0.1), (24, 0.2))
    )

    with pytest.raises(RedLiveOptionMenuError, match="distinct executable candidates"):
        build_red_live_option_set(
            situation=_situation(storage=0.95),
            binding_set=_no_ordinary_bindings(),
            supplements=supplements,
            model_feature_version=4,
            ordering_seed_sha256="d" * 64,
            economy_snapshot=EconomySnapshot(58, (("capture", 6),)),
            target_cash=400,
        )


def test_critical_resupply_remains_a_hard_safety_choice() -> None:
    calls: list[str] = []
    options = _mixed(calls)

    choice = select_red_live_option(
        _model(),
        options,
        seed=7,
        allow_earning_exploration=False,
    )

    assert choice.mode is RedLiveOptionSelectionMode.DETERMINISTIC_SAFETY
    assert choice.selected_binding.kind is GoalKind.RESUPPLY
    assert all(score is None for score in choice.scores)
    assert calls == []


def test_explicit_model_resource_authority_preserves_options_and_uses_scores():
    calls=[]
    original=_mixed(calls)
    options=replace(original,force_resource_safety=False)
    choice=select_red_live_option(_model(),options,seed=7,greedy_selection=True)
    assert options.menu is original.menu and options.bindings is original.bindings
    assert choice.mode is RedLiveOptionSelectionMode.MODEL_GREEDY
    assert all(score is not None for score in choice.scores)
    assert choice.public_dict()['resource_authority']=='model'
    assert options.public_dict()['resource_authority']=='model'
    assert calls==[]


def test_model_resource_authority_does_not_remove_emergency_restoration():
    calls=[]
    options=replace(_mixed(calls),force_resource_safety=False,
                    situation=_situation(resources=1.,safety=1.))
    choice=select_red_live_option(_model(),options,seed=7)
    assert choice.mode is RedLiveOptionSelectionMode.DETERMINISTIC_SAFETY
    assert choice.selected_binding.kind is GoalKind.RESTORE_TEAM
    assert calls==[]


def _pp_only_mixed(*, storage=0.2):
    options = replace(_mixed([]), force_resource_safety=False,
                      situation=_situation(resources=1., safety=1., storage=storage))
    bindings = tuple(replace(b, health_safety_recovery=False)
                     if b.kind is GoalKind.RESTORE_TEAM else b for b in options.bindings)
    original = replace(options.original_bindings, bindings=tuple(
        next(b for b in bindings if b.binding_ref == old.binding_ref)
        for old in options.original_bindings.bindings))
    return replace(options, bindings=bindings, original_bindings=original)


def test_pp_only_recovery_does_not_consume_item_due_to_unrelated_health_pressure():
    options = _pp_only_mixed()
    vectors = tuple(options.menu.candidate_vector(i) for i in options.menu.available_indices)
    choice = select_red_live_option(_model(), options, seed=7, greedy_selection=True)
    assert choice.mode is RedLiveOptionSelectionMode.MODEL_GREEDY
    assert all(score is not None for score in choice.scores)
    assert vectors == tuple(options.menu.candidate_vector(i)
                            for i in options.menu.available_indices)
    assert any(b.kind is GoalKind.RESTORE_TEAM for b in options.bindings)
    assert 'health_safety_recovery' not in json.dumps(options.public_dict())


@pytest.mark.parametrize('value', [None, 0, 1, 'yes'])
def test_private_health_safety_purpose_requires_boolean(value):
    from pokemon_red_completion.goal_manager_runtime import GoalManagerRuntimeError
    binding = _binding(GoalKind.RESTORE_TEAM, binding_ref='restore', calls=[])
    with pytest.raises(GoalManagerRuntimeError, match='health-safety'):
        replace(binding, health_safety_recovery=value)


def test_non_recovery_binding_cannot_claim_pp_safety_exclusion():
    from pokemon_red_completion.goal_manager_runtime import GoalManagerRuntimeError
    binding = _binding(GoalKind.ADVANCE_STORY, binding_ref='story', calls=[])
    with pytest.raises(GoalManagerRuntimeError, match='health-safety'):
        replace(binding, health_safety_recovery=False)


@pytest.mark.parametrize('permission',[None,0,1,'yes'])
def test_resource_authority_cannot_be_coerced(permission):
    with pytest.raises(TypeError,match='explicit boolean'):
        replace(_mixed([]),force_resource_safety=permission)


def test_control_recovery_cannot_enter_learned_mixed_authority() -> None:
    calls: list[str] = []
    original = _ordinary_bindings(calls)
    recovery = _binding(
        GoalKind.RECOVER_CONTROL,
        binding_ref="private:red:recovery",
        calls=calls,
    )
    bindings = GoalBindingSet(
        tuple(
            recovery.opportunity if item.kind is GoalKind.RECOVER_CONTROL else item
            for item in original.opportunities
        ),
        (*original.bindings, recovery),
    )

    with pytest.raises(RedLiveOptionMenuError, match="control recovery"):
        build_red_live_option_set(
            situation=_situation(),
            binding_set=bindings,
            supplements=(),
            model_feature_version=4,
            ordering_seed_sha256="b" * 64,
            economy_snapshot=EconomySnapshot(58, ()),
            target_cash=400,
        )


def test_economy_candidate_requires_fresh_economy_context() -> None:
    calls: list[str] = []
    fishing = _binding(
        GoalKind.ACQUIRE_SPECIES,
        binding_ref="private:red:fishing-map-23",
        calls=calls,
    )
    supplement = supplemental_live_option(
        fishing,
        _fishing_candidate("provider-row", travel=0.2),
    )

    with pytest.raises(RedLiveOptionMenuError, match="measured economy context"):
        build_red_live_option_set(
            situation=_situation(),
            binding_set=_ordinary_bindings(calls),
            supplements=(supplement,),
            model_feature_version=4,
            ordering_seed_sha256="b" * 64,
        )


def test_supplement_kind_must_match_its_executor() -> None:
    calls: list[str] = []
    wrong = _binding(
        GoalKind.RESUPPLY,
        binding_ref="private:red:not-acquisition",
        calls=calls,
        quote=GoalResourceQuote(58, 0, (), expected_income=455),
    )
    supplement = supplemental_live_option(
        wrong,
        _fishing_candidate("provider-row", travel=0.2),
    )

    with pytest.raises(RedLiveOptionMenuError, match="portable option kind"):
        build_red_live_option_set(
            situation=_situation(),
            binding_set=_ordinary_bindings(calls),
            supplements=(supplement,),
            model_feature_version=4,
            ordering_seed_sha256="b" * 64,
            economy_snapshot=EconomySnapshot(58, ()),
            target_cash=400,
        )


def test_full_storage_without_relief_masks_all_acquisition_candidates() -> None:
    calls: list[str] = []
    fishing = _binding(
        GoalKind.ACQUIRE_SPECIES,
        binding_ref="private:red:fishing-map-23",
        calls=calls,
    )
    options = build_red_live_option_set(
        situation=_situation(storage=1.0),
        binding_set=_ordinary_bindings(calls),
        supplements=(
            supplemental_live_option(
                fishing,
                _fishing_candidate("provider-row", travel=0.2),
            ),
        ),
        model_feature_version=4,
        ordering_seed_sha256="b" * 64,
        economy_snapshot=EconomySnapshot(58, ()),
        target_cash=400,
    )

    assert calls == []
    assert {item.features.kind for item in options.menu.candidates} == {
        LivingDexOptionKind.RESUPPLY,
        LivingDexOptionKind.RESTORE,
    }


def test_exact_storage_gate_keeps_one_bounded_acquisition_available() -> None:
    calls: list[str] = []
    fishing = _binding(
        GoalKind.ACQUIRE_SPECIES,
        binding_ref="private:red:fishing-map-23",
        calls=calls,
    )
    options = build_red_live_option_set(
        situation=_situation(storage=0.75),
        binding_set=_ordinary_bindings(calls),
        supplements=(
            supplemental_live_option(
                fishing,
                _fishing_candidate("provider-row", travel=0.2),
            ),
        ),
        model_feature_version=4,
        ordering_seed_sha256="b" * 64,
        economy_snapshot=EconomySnapshot(58, ()),
        target_cash=400,
    )

    assert LivingDexOptionKind.ACQUIRE in {item.features.kind for item in options.menu.candidates}
    assert calls == []


def test_critical_storage_with_relief_forces_manage_storage() -> None:
    calls: list[str] = []
    ordinary = _ordinary_bindings(calls)
    manage = _binding(
        GoalKind.MANAGE_STORAGE,
        binding_ref="private:red:manage-storage",
        calls=calls,
    )
    bindings = GoalBindingSet(
        tuple(
            manage.opportunity if item.kind is GoalKind.MANAGE_STORAGE else item
            for item in ordinary.opportunities
        ),
        (*ordinary.bindings, manage),
    )
    options = build_red_live_option_set(
        situation=_situation(storage=1.0),
        binding_set=bindings,
        supplements=(),
        model_feature_version=4,
        ordering_seed_sha256="b" * 64,
        economy_snapshot=EconomySnapshot(58, ()),
        target_cash=400,
    )

    choice = select_red_live_option(_model(), options, seed=7)

    assert choice.mode is RedLiveOptionSelectionMode.DETERMINISTIC_SAFETY
    assert choice.selected_binding.kind is GoalKind.MANAGE_STORAGE
    assert calls == []


def test_critical_party_forces_restore_without_model_authority() -> None:
    calls: list[str] = []
    options = build_red_live_option_set(
        situation=_situation(resources=0.1, safety=1.0),
        binding_set=_ordinary_bindings(calls),
        supplements=(),
        model_feature_version=4,
        ordering_seed_sha256="b" * 64,
        economy_snapshot=EconomySnapshot(400, ()),
        target_cash=400,
    )

    choice = select_red_live_option(_model(), options, seed=7)

    assert choice.mode is RedLiveOptionSelectionMode.DETERMINISTIC_SAFETY
    assert choice.selected_binding.kind is GoalKind.RESTORE_TEAM
    assert all(value is None for value in choice.scores)
    assert calls == []


def test_model_exploration_restore_probability_replays_exactly() -> None:
    calls: list[str] = []
    options = _mixed(calls)
    model = _model()
    seed = next(
        candidate_seed
        for candidate_seed in range(1000)
        if options.bindings[
            random.Random(candidate_seed).choices(
                range(len(options.bindings)),
                weights=select_red_live_option(
                    model,
                    options,
                    seed=candidate_seed,
                    allow_earning_exploration=True,
                ).probabilities,
                k=1,
            )[0]
        ].kind
        is GoalKind.RESTORE_TEAM
    )

    first = select_red_live_option(
        model,
        options,
        seed=seed,
        allow_earning_exploration=True,
    )
    replay = select_red_live_option(
        model,
        options,
        seed=seed,
        allow_earning_exploration=True,
    )

    assert first.mode is RedLiveOptionSelectionMode.MODEL_EXPLORATION
    assert first.selected_binding.kind is GoalKind.RESTORE_TEAM
    assert replay.probabilities == first.probabilities
    assert replay.selected_candidate_index == first.selected_candidate_index
    assert first.probabilities[first.selected_candidate_index] > 0.0
    assert calls == []


@pytest.mark.parametrize("copies", [1, 2, 8, 32])
@pytest.mark.parametrize("mix", [0.0, 0.25, 1.0])
def test_baseline_family_sampling_does_not_reward_duplicate_variants(monkeypatch, copies, mix):
    import math

    original = replace(_mixed([]), force_resource_safety=False,
                       situation=_situation(resources=0.1))
    exemplar = original.menu.candidates[0]
    candidates, bindings = [], []
    for candidate, binding in zip(original.menu.candidates, original.bindings, strict=True):
        count = copies if candidate.features.kind == exemplar.features.kind else 1
        for ordinal in range(count):
            ref = f"opaque-{len(candidates)}-{ordinal}"
            candidates.append(replace(candidate, binding_ref=ref))
            bindings.append(replace(binding, binding_ref=ref))
    options = replace(original, menu=replace(original.menu, candidates=tuple(candidates)),
                      bindings=tuple(bindings), ordinary_binding_refs=frozenset())
    # Known non-identical scores; the model is queried exactly once, not bypassed.
    queries = []
    def scores(self, menu, utility):
        queries.append(menu)
        return tuple(1.0 if c.features.kind == exemplar.features.kind else 0.0
                     for c in menu.candidates)
    monkeypatch.setattr(LivingDexOptionValueModel, "scores", scores)
    choice = select_red_live_option(_model(), options, seed=31, exploration_mix=mix)
    kinds = {c.features.kind for c in candidates}
    expected = (1.0 - mix) * math.e / (math.e + len(kinds) - 1) + mix / len(kinds)
    actual = sum(p for c, p in zip(candidates, choice.probabilities, strict=True)
                 if c.features.kind == exemplar.features.kind)
    assert actual == pytest.approx(expected)
    assert len(queries) == 1
    assert choice.kind_balanced_exploration is True
    assert choice.public_dict()["policy_id"] == "red-live-kind-balanced-option-v1"
    assert all(p > 0 for p in choice.probabilities)
    assert "opaque-" not in json.dumps(choice.public_dict())


@pytest.mark.parametrize("value", [None, 0, 1, "yes"])
def test_kind_balancing_rejects_nonboolean_authority(value):
    with pytest.raises(TypeError, match="kind-balanced"):
        select_red_live_option(_model(), _mixed([]), seed=1, kind_balanced_exploration=value)


def test_legacy_sampler_remains_explicitly_reproducible():
    import math

    options = replace(_mixed([]), force_resource_safety=False)
    choice = select_red_live_option(_model(), options, seed=17, kind_balanced_exploration=False)
    concrete = [v for v in choice.scores if v is not None]
    peak = max(concrete)
    total = sum(math.exp(v - peak) for v in concrete)
    expected = tuple(0.0 if v is None else 0.75 * math.exp(v - peak) / total + 0.25 / len(concrete)
                     for v in choice.scores)
    assert choice.probabilities == pytest.approx(expected)
    assert choice.kind_balanced_exploration is False
    assert "sampling_rule" not in choice.public_dict()
    assert choice.public_dict()["policy_id"] == "red-live-mixed-option-v1"
