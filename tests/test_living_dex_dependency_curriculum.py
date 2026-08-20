from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import replace

import pytest

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_dependency_curriculum import (
    COMPLETED_FIT_MANIFEST_SCHEMA,
    COMPLETED_FIT_TERMINAL_SCHEMA,
    DEVELOPMENT_OPENING_SCHEMA,
    DependencyCandidateFeatures,
    DependencyMultiplicity,
    DependencyMultiset,
    DependencyTransition,
    DevelopmentCommitmentRoster,
    DevelopmentCommitmentRow,
    LivingDexDependencyCurriculumError,
    RootlessDependencyOutcome,
    RootlessLivingDexDependencyDesign,
    authenticate_completed_dependency_fit_bundle,
    build_rootless_living_dex_dependency_design,
    dependency_distance,
    materialize_train_dependency_outcome,
    transition_dependency_multiset,
    verify_development_openings_after_fit,
    verify_development_openings_for_comparison,
)


def _canonical(document: object) -> bytes:
    return (
        json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
        + b"\n"
    )


def _runtime_openings() -> tuple[bytes, ...]:
    base = 20 + secrets.randbelow(100)
    structures = ((base, base + 1), (base + 2, base + 3))
    payloads = []
    for family_index, (required_precursor, required_evolved) in enumerate(structures):
        family_id = f"development-family-{secrets.token_hex(8)}"
        for multiplicity in DependencyMultiplicity:
            scarce = multiplicity is DependencyMultiplicity.SCARCE
            before_precursor = (
                required_precursor if scarce else required_precursor + required_evolved
            )
            action = (
                GoalKind.ACQUIRE_SPECIES
                if scarce == (family_index % 2 == 0)
                else GoalKind.EVOLVE_SPECIES
            )
            payloads.append(
                _canonical(
                    {
                        "schema": DEVELOPMENT_OPENING_SCHEMA,
                        "scenario_id": (f"rootless-development-{secrets.token_hex(8)}"),
                        "family_id": family_id,
                        "nonce": secrets.token_hex(32),
                        "partition": "development",
                        "multiplicity": multiplicity.value,
                        "structure": {
                            "required_precursor_count": required_precursor,
                            "required_evolved_count": required_evolved,
                        },
                        "before": {
                            "precursor_count": before_precursor,
                            "evolved_count": 0,
                        },
                        "assigned_action": action.value,
                    }
                )
            )
    return tuple(payloads)


def _design(payloads: tuple[bytes, ...]) -> RootlessLivingDexDependencyDesign:
    rows = []
    for payload in payloads:
        document = json.loads(payload)
        rows.append(
            DevelopmentCommitmentRow(document["scenario_id"], hashlib.sha256(payload).hexdigest())
        )
    return build_rootless_living_dex_dependency_design(DevelopmentCommitmentRoster(tuple(rows)))


def _fit_bundle(
    design: RootlessLivingDexDependencyDesign,
) -> tuple[bytes, str, bytes, str]:
    fit_sha = secrets.token_hex(32)
    manifest = _canonical(
        {
            "schema": COMPLETED_FIT_MANIFEST_SCHEMA,
            "design_sha256": design.design_sha256,
            "fit_sha256": fit_sha,
            "train_dataset_sha256": secrets.token_hex(32),
            "executable_bundle_sha256": secrets.token_hex(32),
        }
    )
    manifest_sha = hashlib.sha256(manifest).hexdigest()
    terminal = _canonical(
        {
            "schema": COMPLETED_FIT_TERMINAL_SCHEMA,
            "status": "completed",
            "design_sha256": design.design_sha256,
            "fit_sha256": fit_sha,
            "fit_manifest_sha256": manifest_sha,
        }
    )
    return manifest, manifest_sha, terminal, hashlib.sha256(terminal).hexdigest()


def _verify(design: RootlessLivingDexDependencyDesign, payloads: tuple[bytes, ...]):
    manifest, manifest_sha, terminal, terminal_sha = _fit_bundle(design)
    return verify_development_openings_for_comparison(
        design,
        completed_fit_manifest_bytes=manifest,
        expected_fit_manifest_sha256=manifest_sha,
        completed_fit_terminal_bytes=terminal,
        expected_fit_terminal_sha256=terminal_sha,
        opening_payloads=payloads,
    )


def test_public_design_contains_eight_train_rows_and_only_opaque_dev_roster() -> None:
    payloads = _runtime_openings()
    design = _design(payloads)
    public = design.public_dict()

    assert len(design.train_scenarios) == 8
    assert len(public["train_scenarios"]) == 8
    roster = public["development_commitment_roster"]
    assert roster["row_count"] == 4
    assert all(set(row) == {"scenario_id", "opening_sha256"} for row in roster["rows"])
    serialized = _canonical(public)
    assert b"nonce" not in serialized
    assert b"development-family" not in serialized
    assert b'"partition":"development"' not in serialized


def test_train_structures_and_assignments_remain_balanced() -> None:
    train = _design(_runtime_openings()).train_scenarios
    rewards = [materialize_train_dependency_outcome(row).reward for row in train]

    assert len({row.structure for row in train}) == 4
    assert [row.assigned_action for row in train].count(GoalKind.ACQUIRE_SPECIES) == 4
    assert [row.assigned_action for row in train].count(GoalKind.EVOLVE_SPECIES) == 4
    assert rewards.count(1) == 4
    assert rewards.count(-1) == 4


def test_scarce_and_duplicate_ready_policy_rows_differ_for_both_actions() -> None:
    train = _design(_runtime_openings()).train_scenarios
    for family_ordinal in range(4):
        scarce, duplicate = (row for row in train if row.family_ordinal == family_ordinal)
        assert scarce.multiplicity is DependencyMultiplicity.SCARCE
        assert duplicate.multiplicity is DependencyMultiplicity.DUPLICATE_READY
        for action in (GoalKind.ACQUIRE_SPECIES, GoalKind.EVOLVE_SPECIES):
            assert scarce.candidate_features(action).policy_dict() != (
                duplicate.candidate_features(action).policy_dict()
            )


def test_fit_authentication_is_a_separate_preopening_capability() -> None:
    payloads = _runtime_openings()
    design = _design(payloads)
    manifest, manifest_sha, terminal, terminal_sha = _fit_bundle(design)
    authenticated = authenticate_completed_dependency_fit_bundle(
        design,
        manifest,
        manifest_sha,
        terminal,
        terminal_sha,
    )

    comparison = verify_development_openings_after_fit(
        design,
        authenticated_fit=authenticated,
        opening_payloads=payloads,
    )

    assert comparison.canonical_fit_sha256 == authenticated.canonical_fit_sha256
    assert len(comparison.openings) == 4


def test_comparison_authenticates_fit_then_opens_distinct_held_out_families() -> None:
    payloads = _runtime_openings()
    design = _design(payloads)
    comparison = _verify(design, payloads)

    assert len(comparison.openings) == 4
    assert len({row.family_id for row in comparison.openings}) == 2
    assert len({row.nonce for row in comparison.openings}) == 4
    assert {row.structure for row in comparison.openings}.isdisjoint(
        row.structure for row in design.train_scenarios
    )
    assert [row.assigned_action for row in comparison.openings].count(GoalKind.ACQUIRE_SPECIES) == 2


def test_openings_are_not_read_before_fit_manifest_authentication() -> None:
    design = _design(_runtime_openings())
    manifest, _, terminal, terminal_sha = _fit_bundle(design)
    with pytest.raises(LivingDexDependencyCurriculumError, match="manifest pin"):
        verify_development_openings_for_comparison(
            design,
            completed_fit_manifest_bytes=manifest,
            expected_fit_manifest_sha256="0" * 64,
            completed_fit_terminal_bytes=terminal,
            expected_fit_terminal_sha256=terminal_sha,
            opening_payloads=(b"private-path-like-garbage",) * 4,
        )


def test_fabricated_self_hashed_fit_cannot_replace_external_pins() -> None:
    design = _design(_runtime_openings())
    pinned_manifest, pinned_manifest_sha, pinned_terminal, pinned_terminal_sha = _fit_bundle(design)
    fabricated_manifest, _, fabricated_terminal, _ = _fit_bundle(design)
    assert fabricated_manifest != pinned_manifest
    assert fabricated_terminal != pinned_terminal
    with pytest.raises(LivingDexDependencyCurriculumError, match="manifest pin"):
        verify_development_openings_for_comparison(
            design,
            completed_fit_manifest_bytes=fabricated_manifest,
            expected_fit_manifest_sha256=pinned_manifest_sha,
            completed_fit_terminal_bytes=fabricated_terminal,
            expected_fit_terminal_sha256=pinned_terminal_sha,
            opening_payloads=_runtime_openings(),
        )


def test_terminal_must_bind_the_pinned_manifest_and_complete_fit() -> None:
    design = _design(_runtime_openings())
    manifest, manifest_sha, terminal, _ = _fit_bundle(design)
    document = json.loads(terminal)
    document["fit_manifest_sha256"] = secrets.token_hex(32)
    altered_terminal = _canonical(document)
    with pytest.raises(LivingDexDependencyCurriculumError, match="relationship"):
        verify_development_openings_for_comparison(
            design,
            completed_fit_manifest_bytes=manifest,
            expected_fit_manifest_sha256=manifest_sha,
            completed_fit_terminal_bytes=altered_terminal,
            expected_fit_terminal_sha256=hashlib.sha256(altered_terminal).hexdigest(),
            opening_payloads=_runtime_openings(),
        )


@pytest.mark.parametrize("mutation", ("reward", "nonce", "commitment", "duplicate"))
def test_opening_mutations_fail_closed(mutation: str) -> None:
    payloads = list(_runtime_openings())
    if mutation == "reward":
        document = json.loads(payloads[0])
        document["reward"] = 1
        payloads[0] = _canonical(document)
        design = _design(tuple(payloads))
    elif mutation == "nonce":
        document = json.loads(payloads[0])
        document["nonce"] = "a" * 64
        payloads[0] = _canonical(document)
        design = _design(tuple(payloads))
    elif mutation == "duplicate":
        document = json.loads(payloads[1])
        document["nonce"] = json.loads(payloads[0])["nonce"]
        payloads[1] = _canonical(document)
        design = _design(tuple(payloads))
    else:
        design = _design(tuple(payloads))
        document = json.loads(payloads[0])
        document["nonce"] = secrets.token_hex(32)
        payloads[0] = _canonical(document)

    with pytest.raises(LivingDexDependencyCurriculumError):
        _verify(design, tuple(payloads))


@pytest.mark.parametrize(
    "mutation",
    ("one_family", "one_multiplicity", "train_overlap", "actions", "all_positive"),
)
def test_development_set_mutations_fail_closed(mutation: str) -> None:
    payloads = list(_runtime_openings())
    documents = [json.loads(payload) for payload in payloads]
    if mutation == "one_family":
        documents[2]["family_id"] = documents[0]["family_id"]
        documents[3]["family_id"] = documents[0]["family_id"]
    elif mutation == "one_multiplicity":
        documents[1]["multiplicity"] = documents[0]["multiplicity"]
        documents[1]["before"] = documents[0]["before"]
    elif mutation == "train_overlap":
        documents[0]["structure"] = {
            "required_precursor_count": 1,
            "required_evolved_count": 1,
        }
        documents[1]["structure"] = documents[0]["structure"]
        documents[0]["before"]["precursor_count"] = 1
        documents[1]["before"]["precursor_count"] = 2
    elif mutation == "actions":
        for document in documents:
            document["assigned_action"] = GoalKind.ACQUIRE_SPECIES.value
    else:
        for document in documents:
            document["assigned_action"] = (
                GoalKind.ACQUIRE_SPECIES.value
                if document["multiplicity"] == DependencyMultiplicity.SCARCE.value
                else GoalKind.EVOLVE_SPECIES.value
            )
    mutated = tuple(_canonical(document) for document in documents)
    with pytest.raises(LivingDexDependencyCurriculumError):
        _verify(_design(mutated), mutated)


def test_train_policy_features_have_no_identity_or_label_leakage() -> None:
    forbidden = {
        "species",
        "family",
        "title",
        "route",
        "assignment",
        "reward",
        "post",
        "scenario",
        "partition",
    }
    for scenario in _design(_runtime_openings()).train_scenarios:
        for action in (GoalKind.ACQUIRE_SPECIES, GoalKind.EVOLVE_SPECIES):
            features = scenario.candidate_features(action).policy_dict()
            flattened = " ".join(
                (*features.keys(), *(str(value) for value in features.values()))
            ).lower()
            assert "proposed-rootless" in flattened
            assert not any(token in flattened for token in forbidden)


def test_train_outcome_rejects_path_identity_and_cross_scenario_forgery() -> None:
    train = _design(_runtime_openings()).train_scenarios
    outcome = materialize_train_dependency_outcome(train[0])
    with pytest.raises(LivingDexDependencyCurriculumError, match="identity"):
        replace(outcome, scenario_id="../../private/label.json")
    with pytest.raises(LivingDexDependencyCurriculumError, match="bound"):
        replace(outcome, scenario_id=train[2].scenario_id)


def test_transition_and_outcome_cannot_be_forged_or_use_storage() -> None:
    scenario = _design(_runtime_openings()).train_scenarios[0]
    outcome = materialize_train_dependency_outcome(scenario)
    with pytest.raises(LivingDexDependencyCurriculumError, match="semantics"):
        DependencyCandidateFeatures(scenario.predecision_features, 0, 0, 0)
    with pytest.raises(LivingDexDependencyCurriculumError, match="not derived"):
        DependencyTransition(scenario.before, scenario.assigned_action, scenario.before, True)
    with pytest.raises(LivingDexDependencyCurriculumError, match="not derived"):
        RootlessDependencyOutcome(
            outcome.scenario_id,
            outcome.structure,
            "settled",
            outcome.action,
            outcome.before,
            DependencyMultiset(99, 99),
            outcome.dependency_distance_before,
            0,
            True,
            1,
        )
    with pytest.raises(LivingDexDependencyCurriculumError, match="candidate action"):
        scenario.candidate_features(GoalKind.MANAGE_STORAGE)
    with pytest.raises(LivingDexDependencyCurriculumError, match="transition action"):
        transition_dependency_multiset(scenario.before, GoalKind.MANAGE_STORAGE)


def test_scenario_and_roster_layout_mutations_fail_closed() -> None:
    design = _design(_runtime_openings())
    with pytest.raises(LivingDexDependencyCurriculumError, match="partition"):
        replace(design.train_scenarios[0], partition="development")
    with pytest.raises(LivingDexDependencyCurriculumError, match="canonical eight"):
        RootlessLivingDexDependencyDesign(design.train_scenarios[:-1], design.development_roster)
    with pytest.raises(LivingDexDependencyCurriculumError, match="four distinct"):
        DevelopmentCommitmentRoster(design.development_roster.rows[:3])


def test_train_distance_and_interruption_are_exact_and_censored() -> None:
    scenario = _design(_runtime_openings()).train_scenarios[0]
    transition = transition_dependency_multiset(scenario.before, scenario.assigned_action)
    assert dependency_distance(transition.after, scenario.structure) == (
        dependency_distance(scenario.before, scenario.structure) - 1
    )
    interrupted = materialize_train_dependency_outcome(scenario, interrupted=True)
    assert interrupted.after is None
    assert interrupted.dependency_distance_after is None
    assert interrupted.preserved_required_living_species is None
    assert interrupted.reward is None
