from __future__ import annotations

import inspect
import json
from dataclasses import replace

import pytest

import pokemon_red_completion.living_dex_dependency_evaluation_v2 as evaluation_v2
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_dependency_curriculum import (
    DependencyCandidateFeatures,
    DependencyMultiplicity,
    DependencyMultiset,
    DependencyStructure,
    dependency_predecision_features,
)
from pokemon_red_completion.living_dex_dependency_evaluation_v2 import (
    RETIRED_ROOTLESS_DEPENDENCY_V1_IDENTITIES,
    DependencyComparisonClaimV2,
    EvaluationExecutionBindingV2,
    FreshDependencyStructureV2,
    FreshDevelopmentCommitmentRosterV2,
    FreshDevelopmentCommitmentV2,
    FreshDevelopmentOpeningV2,
    LivingDexDependencyEvaluationV2Error,
    RootlessDependencyEvaluationDesignV2,
    build_dependency_comparison_claim_v2,
    build_dependency_fit_claim_v2,
    require_fresh_development_opening_set_v2,
    retired_v1_identity_set_sha256,
    rootless_dependency_counter_contract_v2,
    rootless_dependency_evaluation_blueprint_v2,
    rootless_dependency_stage_contract_v2,
    rootless_dependency_train_revalidation_contract_v2,
)
from pokemon_red_completion.living_dex_dependency_integrity import (
    DependencyEvaluationBundlePins,
    DependencyEvaluationFitIdentity,
)
from pokemon_red_completion.living_dex_dependency_ranker import (
    DEPENDENCY_RANKER_FEATURE_NAMES,
    DependencyRankerModel,
)


def _digest(index: int) -> str:
    return f"{index:064x}"


def _roster(*, offset: int = 100) -> FreshDevelopmentCommitmentRosterV2:
    return FreshDevelopmentCommitmentRosterV2(
        tuple(
            FreshDevelopmentCommitmentV2(
                record_id=f"rootless-v2-development-{index:032x}",
                manifest_sha256=_digest(offset + index),
                declared_record_sha256=_digest(offset + 10 + index),
                declared_total_bytes=512 + index,
            )
            for index in range(4)
        )
    )


def _binding(operation: str, *, offset: int) -> EvaluationExecutionBindingV2:
    return EvaluationExecutionBindingV2(
        operation=operation,  # type: ignore[arg-type]
        source_commit=f"{offset:040x}",
        source_bundle_sha256=_digest(offset + 1),
        runner_sha256=_digest(offset + 2),
        runtime_sha256=_digest(offset + 3),
    )


def _fit_pins(design: RootlessDependencyEvaluationDesignV2) -> DependencyEvaluationBundlePins:
    identity = DependencyEvaluationFitIdentity(
        design_sha256=design.design_sha256,
        train_dataset_sha256=_digest(301),
        fit_record_sha256=_digest(302),
        fit_sha256=_digest(303),
        model_sha256=_digest(304),
        fit_execution_manifest_sha256=_digest(305),
        executable_bundle_sha256=_digest(306),
    )
    return DependencyEvaluationBundlePins(
        fit_identity=identity,
        fit_manifest_record_sha256=_digest(307),
        fit_terminal_record_sha256=_digest(308),
    )


def test_blueprint_is_public_only_and_freezes_a_fresh_four_row_contract() -> None:
    blueprint = rootless_dependency_evaluation_blueprint_v2()
    commitment = blueprint["commitment_contract"]

    assert blueprint["private_artifact_accesses"] == 0
    assert blueprint["model_fits"] == 0
    assert blueprint["development_payloads_decoded"] == 0
    assert blueprint["comparisons"] == 0
    assert commitment["rows"] == 4
    assert commitment["payload_fields_public"] == []
    assert commitment["minimum_required_count"] == 17
    assert commitment["v1_opening_reuse_allowed"] is False
    assert set(commitment["metadata_fields_public"]) == {
        "record_id",
        "manifest_sha256",
        "declared_record_sha256",
        "declared_total_bytes",
    }
    assert commitment["opening_contains_outcome_or_reward"] is False
    assert commitment["nonce_bytes"] == 32
    assert commitment["nonce_generation"] == "cryptographically_secure_random_at_provisioning"
    assert commitment["nonce_inside_committed_private_payload"] is True
    assert commitment["commitment_dictionary_attack_falsifies_provisioning"] is True
    assert set(commitment["private_opening_fields"]) == {
        "scenario_id",
        "family_id",
        "nonce",
        "partition",
        "multiplicity",
        "structure",
        "before",
        "assigned_action",
    }


def test_commitment_roster_contains_only_metadata_from_the_qualified_inspector() -> None:
    roster = _roster()

    assert roster.public_dict()["payloads_opened"] == 0
    assert roster.public_dict()["payloads_decoded"] == 0
    assert all(
        set(row.public_dict())
        == {
            "schema",
            "record_id",
            "record_kind",
            "manifest_sha256",
            "declared_record_sha256",
            "declared_total_bytes",
            "payload_opened",
            "payload_integrity_verified",
        }
        for row in roster.rows
    )


def _openings() -> tuple[FreshDevelopmentOpeningV2, ...]:
    structures = (FreshDependencyStructureV2(17, 18), FreshDependencyStructureV2(19, 20))
    rows: list[FreshDevelopmentOpeningV2] = []
    for family, structure in enumerate(structures):
        for multiplicity_index, multiplicity in enumerate(DependencyMultiplicity):
            duplicate_ready = multiplicity is DependencyMultiplicity.DUPLICATE_READY
            precursor_count = structure.required_precursor_count
            if duplicate_ready:
                precursor_count += structure.required_evolved_count
            action = (
                GoalKind.ACQUIRE_SPECIES
                if (family == 0) == (not duplicate_ready)
                else GoalKind.EVOLVE_SPECIES
            )
            index = family * 2 + multiplicity_index
            rows.append(
                FreshDevelopmentOpeningV2(
                    scenario_id=f"rootless-v2-development-{index:032x}",
                    family_id=f"rootless-v2-family-{family:032x}",
                    nonce=(f"{index + 1:056x}" + "abcdef12"),
                    multiplicity=multiplicity,
                    structure=structure,
                    before=DependencyMultiset(precursor_count, 0),
                    assigned_action=action,
                )
            )
    return tuple(rows)


def test_private_opening_schema_enforces_disjoint_structures_and_balanced_denominator() -> None:
    openings = _openings()

    require_fresh_development_opening_set_v2(openings)
    assert [row.derived_reward for row in openings].count(1) == 2
    assert [row.derived_reward for row in openings].count(-1) == 2
    for row in openings:
        document = json.loads(row.canonical_private_bytes())
        assert set(document) == {
            "schema",
            "scenario_id",
            "family_id",
            "nonce",
            "partition",
            "multiplicity",
            "structure",
            "before",
            "assigned_action",
        }
        assert "reward" not in document
        assert "outcome" not in document
        assert min(document["structure"].values()) >= 17


@pytest.mark.parametrize("counts", ((16, 20), (17, 10_001), (1, 1)))
def test_v2_structure_rejects_public_train_and_v1_generator_domains(
    counts: tuple[int, int],
) -> None:
    with pytest.raises(LivingDexDependencyEvaluationV2Error, match="excluded domain"):
        FreshDependencyStructureV2(*counts)


def test_opening_set_rejects_unbalanced_derived_rewards_without_a_reward_field() -> None:
    rows = list(_openings())
    rows[2] = replace(rows[2], assigned_action=GoalKind.ACQUIRE_SPECIES)
    rows[3] = replace(rows[3], assigned_action=GoalKind.EVOLVE_SPECIES)

    with pytest.raises(LivingDexDependencyEvaluationV2Error, match="derived rewards"):
        require_fresh_development_opening_set_v2(tuple(rows))


@pytest.mark.parametrize(
    "mutation",
    ("v1_record_id", "retired_hash", "duplicate_hash", "unsorted", "invalid_size"),
)
def test_commitment_roster_rejects_v1_reuse_and_noncanonical_metadata(mutation: str) -> None:
    rows = list(_roster().rows)
    with pytest.raises(LivingDexDependencyEvaluationV2Error):
        if mutation == "v1_record_id":
            rows[0] = replace(rows[0], record_id="rootless-development-0000000000000000")
        elif mutation == "retired_hash":
            rows[0] = replace(
                rows[0],
                declared_record_sha256=next(iter(RETIRED_ROOTLESS_DEPENDENCY_V1_IDENTITIES)),
            )
        elif mutation == "duplicate_hash":
            rows[1] = replace(rows[1], declared_record_sha256=rows[0].declared_record_sha256)
        elif mutation == "unsorted":
            rows[0], rows[1] = rows[1], rows[0]
        else:
            rows[0] = replace(rows[0], declared_total_bytes=0)
        FreshDevelopmentCommitmentRosterV2(tuple(rows))


def test_design_identity_binds_roster_domain_stage_counter_and_retirement_contracts() -> None:
    design = RootlessDependencyEvaluationDesignV2(_roster())
    altered = RootlessDependencyEvaluationDesignV2(_roster(offset=200))
    public = design.public_dict()

    assert design.design_sha256 != altered.design_sha256
    assert design.development_roster.roster_sha256 != altered.development_roster.roster_sha256
    assert public["development_structure_domain"] == {
        "minimum_required_count": 17,
        "maximum_required_count": 10_000,
        "v1_generator_domain_excluded": "3_through_15",
        "public_train_domain_excluded": "1_through_2",
        "families": 2,
        "multiplicities_per_family": 2,
        "ranker_numeric_support": (
            "continuous_numeric_features_without_embedding_or_bounded_integer_lookup"
        ),
    }
    assert public["retired_v1_identity_set_sha256"] == retired_v1_identity_set_sha256()
    assert design.design_sha256 not in RETIRED_ROOTLESS_DEPENDENCY_V1_IDENTITIES


@pytest.mark.parametrize(
    "mutation",
    ("extra_field", "stage_drift", "counter_drift", "commitment_flag", "row_reorder"),
)
def test_design_round_trip_is_exact_and_rejects_contract_drift(mutation: str) -> None:
    design = RootlessDependencyEvaluationDesignV2(_roster())
    document = json.loads(json.dumps(design.public_dict()))
    assert RootlessDependencyEvaluationDesignV2.from_dict(document) == design
    if mutation == "extra_field":
        document["extra"] = False
    elif mutation == "stage_drift":
        document["stage_contract"]["same_process_fit_and_comparison_allowed"] = True
    elif mutation == "counter_drift":
        document["counter_contract"]["completed_fit"]["authority_promotions_added"] = 1
    elif mutation == "commitment_flag":
        document["development_roster"]["rows"][0]["payload_opened"] = True
    else:
        rows = document["development_roster"]["rows"]
        rows[0], rows[1] = rows[1], rows[0]

    with pytest.raises(LivingDexDependencyEvaluationV2Error):
        RootlessDependencyEvaluationDesignV2.from_dict(document)


def test_train_revalidation_binds_all_eight_public_values_without_v1_artifact_reuse() -> None:
    contract = rootless_dependency_train_revalidation_contract_v2()
    rows = contract["canonical_values"]

    assert len(rows) == 8
    assert len({row["scenario_id"] for row in rows}) == 8
    assert [row["assigned_action"] for row in rows].count("acquire_species") == 4
    assert [row["assigned_action"] for row in rows].count("evolve_species") == 4
    assert [row["derived_reward"] for row in rows].count(1) == 4
    assert [row["derived_reward"] for row in rows].count(-1) == 4
    assert contract["v1_train_artifact_reads"] == 0
    assert contract["new_outcomes_added"] == 0
    assert contract["canonical_values_sha256"] not in RETIRED_ROOTLESS_DEPENDENCY_V1_IDENTITIES


def test_fit_claim_has_separate_semantic_and_source_bound_identities() -> None:
    design = RootlessDependencyEvaluationDesignV2(_roster())
    first = build_dependency_fit_claim_v2(
        design,
        execution_binding=_binding("fit", offset=400),
    )
    new_runner = build_dependency_fit_claim_v2(
        design,
        execution_binding=_binding("fit", offset=500),
    )

    assert first.semantic_claim_sha256 == new_runner.semantic_claim_sha256
    assert first.execution_identity_sha256 != new_runner.execution_identity_sha256
    assert first.public_dict()["claim_before_fit"] is True
    assert first.public_dict()["development_payloads_permitted"] == 0
    assert first.public_dict()["retry_allowed"] is False
    assert first.semantic_claim_sha256 not in RETIRED_ROOTLESS_DEPENDENCY_V1_IDENTITIES


def test_comparison_claim_joins_fresh_fit_and_requires_a_separate_execution() -> None:
    design = RootlessDependencyEvaluationDesignV2(_roster())
    fit_claim = build_dependency_fit_claim_v2(
        design,
        execution_binding=_binding("fit", offset=400),
    )
    comparison = build_dependency_comparison_claim_v2(
        design,
        fit_claim=fit_claim,
        fit_bundle_pins=_fit_pins(design),
        execution_binding=_binding("comparison", offset=600),
    )
    public = comparison.public_dict()

    assert comparison.semantic_claim_sha256 != fit_claim.semantic_claim_sha256
    assert comparison.execution_identity_sha256 != fit_claim.execution_identity_sha256
    assert public["fit_bundle_authenticated_before_payload_open"] is True
    assert public["claim_before_payload_open"] is True
    assert public["development_payloads_exactly"] == 4
    assert public["retry_allowed"] is False


def test_comparison_rejects_a_different_design_or_any_retired_fit_identity() -> None:
    design = RootlessDependencyEvaluationDesignV2(_roster())
    other = RootlessDependencyEvaluationDesignV2(_roster(offset=200))
    fit_claim = build_dependency_fit_claim_v2(
        design,
        execution_binding=_binding("fit", offset=400),
    )

    with pytest.raises(LivingDexDependencyEvaluationV2Error, match="fit design"):
        build_dependency_comparison_claim_v2(
            other,
            fit_claim=fit_claim,
            fit_bundle_pins=_fit_pins(other),
            execution_binding=_binding("comparison", offset=600),
        )

    pins = _fit_pins(design)
    retired = next(iter(RETIRED_ROOTLESS_DEPENDENCY_V1_IDENTITIES))
    replaced_identity = replace(pins.fit_identity, model_sha256=retired)
    replaced_pins = DependencyEvaluationBundlePins(
        fit_identity=replaced_identity,
        fit_manifest_record_sha256=pins.fit_manifest_record_sha256,
        fit_terminal_record_sha256=pins.fit_terminal_record_sha256,
    )
    with pytest.raises(LivingDexDependencyEvaluationV2Error, match="retired V1"):
        DependencyComparisonClaimV2(
            design_sha256=design.design_sha256,
            development_roster_sha256=design.development_roster.roster_sha256,
            fit_claim_sha256=fit_claim.semantic_claim_sha256,
            fit_execution_identity_sha256=fit_claim.execution_identity_sha256,
            fit_bundle_pins=replaced_pins,
            execution_binding=_binding("comparison", offset=600),
        )


def test_stage_contract_makes_adaptive_fit_and_comparison_impossible_by_contract() -> None:
    contract = rootless_dependency_stage_contract_v2()

    assert contract["ordered_stages"] == [
        "design",
        "provision",
        "fit_preflight",
        "fit",
        "comparison_preflight",
        "comparison",
    ]
    assert contract["same_process_fit_and_comparison_allowed"] is False
    assert contract["retired_v1_identity_reuse_allowed"] is False
    assert contract["replacement_openings_allowed"] is False
    assert contract["fit"]["development_payloads_opened"] == 0
    assert contract["fit"]["purpose"] == (
        "untainted_compliance_replacement_not_new_learning_output"
    )
    assert contract["comparison_preflight"]["development_payloads_opened"] == 0
    assert contract["comparison"]["claim_before_first_payload_open"] is True
    assert contract["comparison"]["development_payloads_opened"] == 4


def test_counter_contract_does_not_double_count_the_identical_clean_refit() -> None:
    contract = rootless_dependency_counter_contract_v2()
    zero = contract["design_provision_preflight_and_train_revalidation"]

    assert all(value == 0 for value in zero.values())
    assert contract["completed_fit"]["model_fits_added"] == 0
    assert contract["completed_fit"]["synthetic_rootless_model_fits_added"] == 0
    assert contract["completed_fit_adds_learning_counter"] is False
    assert contract["completed_fit_event"] == (
        "clean_replacement_artifact_for_already_counted_identical_eight_row_fit"
    )
    assert contract["completed_comparison"]["unseen_comparisons_added"] == 1
    assert contract["completed_comparison"]["synthetic_rootless_unseen_comparisons_added"] == 1
    assert contract["completed_comparison_uses_fresh_v2_development_rows"] is True
    for stage in ("completed_fit", "completed_comparison"):
        assert contract[stage]["authority_promotions_added"] == 0
        assert contract[stage]["transfer_results_added"] == 0
        assert contract[stage]["verified_outcome_examples_added"] == 0
        assert contract[stage]["atomic_goal_episodes_added"] == 0
    assert contract["synthetic_results_are_gameplay"] is False
    assert contract["completed_fit_is_authority"] is False
    assert contract["completed_comparison_is_transfer"] is False


def test_existing_ranker_scores_the_full_v2_numeric_domain_without_an_embedding_bound() -> None:
    contract = evaluation_v2.rootless_dependency_ranker_contract_v2()
    structure = DependencyStructure(10_000, 10_000)
    state = dependency_predecision_features(DependencyMultiset(20_000, 0), structure)
    model = DependencyRankerModel(
        feature_names=DEPENDENCY_RANKER_FEATURE_NAMES,
        weights=(0.0, 0.0, 0.0, 0.0),
        train_dataset_sha256=_digest(900),
    )

    for semantics in ((1, 0, 0), (0, 1, 1)):
        assert model.score(DependencyCandidateFeatures(state, *semantics)) == 0.0
    assert contract["numeric_support"] == (
        "continuous_numeric_features_without_embedding_or_bounded_integer_lookup"
    )
    assert contract["required_count_support_inclusive"] == [17, 10_000]
    assert contract["fit_record_design_sha256"] == "must_equal_outer_v2_design_sha256"
    assert contract["fit_train_dataset_sha256"] == (
        "must_equal_v2_train_revalidation_record_sha256"
    )
    assert contract["v1_fit_or_model_reuse_allowed"] is False


def test_design_module_has_no_private_store_or_execution_dependency() -> None:
    source = inspect.getsource(evaluation_v2)

    assert "private_artifacts" not in source
    assert "find_sealed_record" not in source
    assert "inspect_sealed_record_metadata" not in source
    assert "pyboy" not in source.lower()
    assert "controller" not in source.lower()
