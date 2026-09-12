from __future__ import annotations

import json

import numpy as np
import pytest

from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalOpportunity,
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
    build_red_live_option_set,
    select_red_live_option,
    supplemental_live_option,
)
from pokemon_red_completion.resource_economy_observation import EconomySnapshot


def _situation(*, resources: float = 0.9, safety: float = 0.1) -> GoalSituation:
    return GoalSituation(
        story_pressure=0.0,
        collection_pressure=0.8,
        team_pressure=0.1,
        evolution_pressure=0.3,
        safety_pressure=safety,
        resource_pressure=resources,
        storage_pressure=0.2,
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
    coefficients = np.zeros(
        (len(names), len(LIVING_DEX_OPTION_OUTCOME_NAMES)), dtype=np.float64
    )
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
    assert {
        item.features.kind for item in options.menu.candidates
    } == {
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
