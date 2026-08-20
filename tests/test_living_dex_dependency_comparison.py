from __future__ import annotations

import hashlib
import json

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_dependency_comparison import compare_dependency_ranker
from pokemon_red_completion.living_dex_dependency_curriculum import (
    COMPLETED_FIT_MANIFEST_SCHEMA,
    COMPLETED_FIT_TERMINAL_SCHEMA,
    DEVELOPMENT_OPENING_SCHEMA,
    DependencyMultiplicity,
    DevelopmentCommitmentRoster,
    DevelopmentCommitmentRow,
    build_rootless_living_dex_dependency_design,
    materialize_train_dependency_outcome,
    verify_development_openings_for_comparison,
)
from pokemon_red_completion.living_dex_dependency_ranker import (
    DependencyRankerModel,
    fit_dependency_ranker,
)


def _line(document: object) -> bytes:
    return (
        json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
        + b"\n"
    )


def _openings() -> tuple[bytes, ...]:
    payloads: list[bytes] = []
    for family_index, (precursor, evolved) in enumerate(((3, 1), (1, 3))):
        for row_index, multiplicity in enumerate(DependencyMultiplicity):
            scarce = multiplicity is DependencyMultiplicity.SCARCE
            payloads.append(
                _line(
                    {
                        "schema": DEVELOPMENT_OPENING_SCHEMA,
                        "scenario_id": f"rootless-development-{family_index:08x}{row_index:08x}",
                        "family_id": f"development-family-{family_index:016x}",
                        "nonce": hashlib.sha256(
                            f"held-out-{family_index}-{row_index}".encode()
                        ).hexdigest(),
                        "partition": "development",
                        "multiplicity": multiplicity.value,
                        "structure": {
                            "required_precursor_count": precursor,
                            "required_evolved_count": evolved,
                        },
                        "before": {
                            "precursor_count": (precursor if scarce else precursor + evolved),
                            "evolved_count": 0,
                        },
                        "assigned_action": (
                            GoalKind.ACQUIRE_SPECIES.value
                            if scarce == (family_index % 2 == 0)
                            else GoalKind.EVOLVE_SPECIES.value
                        ),
                    }
                )
            )
    return tuple(payloads)


def _design_and_fit():
    openings = _openings()
    roster = DevelopmentCommitmentRoster(
        tuple(
            DevelopmentCommitmentRow(
                json.loads(payload)["scenario_id"],
                hashlib.sha256(payload).hexdigest(),
            )
            for payload in openings
        )
    )
    design = build_rootless_living_dex_dependency_design(roster)
    fit = fit_dependency_ranker(
        design,
        tuple(
            materialize_train_dependency_outcome(scenario) for scenario in design.train_scenarios
        ),
    )
    manifest = _line(
        {
            "schema": COMPLETED_FIT_MANIFEST_SCHEMA,
            "design_sha256": design.design_sha256,
            "fit_sha256": fit.fit_sha256,
            "train_dataset_sha256": fit.train_dataset_sha256,
            "executable_bundle_sha256": hashlib.sha256(b"bundle").hexdigest(),
        }
    )
    manifest_sha = hashlib.sha256(manifest).hexdigest()
    terminal = _line(
        {
            "schema": COMPLETED_FIT_TERMINAL_SCHEMA,
            "status": "completed",
            "design_sha256": design.design_sha256,
            "fit_sha256": fit.fit_sha256,
            "fit_manifest_sha256": manifest_sha,
        }
    )
    verified = verify_development_openings_for_comparison(
        design,
        completed_fit_manifest_bytes=manifest,
        expected_fit_manifest_sha256=manifest_sha,
        completed_fit_terminal_bytes=terminal,
        expected_fit_terminal_sha256=hashlib.sha256(terminal).hexdigest(),
        opening_payloads=openings,
    )
    return design, fit, verified


def test_aggregate_comparison_passes_without_disclosing_opening_rows() -> None:
    design, fit, verified = _design_and_fit()

    result = compare_dependency_ranker(
        design_sha256=design.design_sha256,
        model=fit.model,
        verified=verified,
    )

    assert result.candidate_correct == 4
    assert result.descriptive_gate_passed is True
    assert result.candidate_cross_entropy < result.baseline_cross_entropy
    assert result.candidate_mean_winner_probability > 0.5
    assert "openings" not in result.public_dict()
    assert "scenario" not in json.dumps(result.public_dict())


def test_zero_model_fails_the_descriptive_comparison_gate() -> None:
    design, fit, verified = _design_and_fit()
    zero = DependencyRankerModel(
        fit.model.feature_names,
        tuple(0.0 for _ in fit.model.weights),
        fit.model.train_dataset_sha256,
    )

    result = compare_dependency_ranker(
        design_sha256=design.design_sha256,
        model=zero,
        verified=verified,
    )

    assert result.descriptive_gate_passed is False
    assert result.candidate_cross_entropy == result.baseline_cross_entropy
