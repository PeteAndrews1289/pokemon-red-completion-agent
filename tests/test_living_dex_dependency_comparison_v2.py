from __future__ import annotations

import pytest

from pokemon_red_completion.living_dex_dependency_comparison_v2 import (
    preflight_v2_comparison,
)
from pokemon_red_completion.living_dex_dependency_evaluation_v2 import (
    LivingDexDependencyEvaluationV2Error,
)
from pokemon_red_completion.living_dex_dependency_integrity_v2 import (
    AuthenticatedDependencyEvaluationFitV2,
)


def test_comparison_preflight_imports() -> None:
    assert preflight_v2_comparison is not None


from pokemon_red_completion.living_dex_dependency_evaluation_v2 import (
    EvaluationExecutionBindingV2,
    RootlessDependencyEvaluationDesignV2,
    build_dependency_comparison_claim_v2,
    build_dependency_fit_claim_v2,
)
from pokemon_red_completion.living_dex_dependency_integrity import (
    DependencyEvaluationBundlePins,
    DependencyEvaluationFitIdentity,
)
from pokemon_red_completion.living_dex_dependency_integrity_v2 import (
    _AUTHENTICATED_FIT_TOKEN_V2,
)
from pokemon_red_completion.living_dex_dependency_provision_v2 import (
    provision_v2_development_commitments,
)
from pokemon_red_completion.living_dex_dependency_ranker import (
    DEPENDENCY_RANKER_FEATURE_NAMES,
    DependencyRankerFit,
    DependencyRankerModel,
)


def test_preflight_v2_comparison_rejects_mismatched_fit() -> None:
    openings, roster = provision_v2_development_commitments()
    design = RootlessDependencyEvaluationDesignV2(roster)

    execution_binding_fit = EvaluationExecutionBindingV2(
        operation="fit",
        source_commit="0" * 40,
        source_bundle_sha256="1" * 64,
        runner_sha256="2" * 64,
        runtime_sha256="3" * 64,
    )

    fit_claim = build_dependency_fit_claim_v2(design, execution_binding=execution_binding_fit)

    execution_binding_comparison = EvaluationExecutionBindingV2(
        operation="comparison",
        source_commit="4" * 40,
        source_bundle_sha256="5" * 64,
        runner_sha256="6" * 64,
        runtime_sha256="7" * 64,
    )

    fit_identity = DependencyEvaluationFitIdentity(
        design_sha256=design.design_sha256,
        train_dataset_sha256="8" * 64,
        fit_record_sha256="9" * 64,
        fit_sha256="a" * 64,
        model_sha256="b" * 64,
        fit_execution_manifest_sha256="c" * 64,
        executable_bundle_sha256="d" * 64,
    )

    pins = DependencyEvaluationBundlePins(
        fit_identity=fit_identity,
        fit_manifest_record_sha256="e" * 64,
        fit_terminal_record_sha256="f" * 64,
    )

    comparison_claim = build_dependency_comparison_claim_v2(
        design,
        fit_claim=fit_claim,
        fit_bundle_pins=pins,
        execution_binding=execution_binding_comparison,
    )

    # Mutate the design in the authenticated fit to trigger the failure
    mutated_identity = DependencyEvaluationFitIdentity(
        design_sha256="0" * 64,  # Mutated
        train_dataset_sha256="8" * 64,
        fit_record_sha256="9" * 64,
        fit_sha256="a" * 64,
        model_sha256="b" * 64,
        fit_execution_manifest_sha256="c" * 64,
        executable_bundle_sha256="d" * 64,
    )
    mutated_pins = DependencyEvaluationBundlePins(
        fit_identity=mutated_identity,
        fit_manifest_record_sha256="e" * 64,
        fit_terminal_record_sha256="f" * 64,
    )

    model = DependencyRankerModel(
        DEPENDENCY_RANKER_FEATURE_NAMES,
        tuple(0.0 for _ in DEPENDENCY_RANKER_FEATURE_NAMES),
        "8" * 64,
    )
    fit = DependencyRankerFit(
        design_sha256="0" * 64,
        train_dataset_sha256="8" * 64,
        model=model,
        baseline_cross_entropy=0.69,
        fitted_cross_entropy=0.5,
        train_accuracy=1.0,
    )

    authenticated_fit = AuthenticatedDependencyEvaluationFitV2(
        fit=fit,
        pins=mutated_pins,
        _validation_token=_AUTHENTICATED_FIT_TOKEN_V2,
    )

    with pytest.raises(
        LivingDexDependencyEvaluationV2Error, match="V2 comparison preflight design differs"
    ):
        preflight_v2_comparison(comparison_claim, authenticated_fit=authenticated_fit)
