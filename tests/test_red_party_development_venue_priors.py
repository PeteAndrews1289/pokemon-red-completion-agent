from __future__ import annotations

import ast
import copy
import hashlib
import json
import sys
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

import pytest

import pokemon_red_completion.red_party_development_venue_priors as venue_prior_module
from pokemon_red_completion.blaine import ROUTE_11_TRAINING_VENUE
from pokemon_red_completion.collection_protocol import (
    committed_source_bundle_sha256,
)
from pokemon_red_completion.party_development_venue_priors import (
    PartyDevelopmentVenuePriorRegistry,
    VenuePriorUnitRatio,
)
from pokemon_red_completion.provenance import detect_source_identity
from pokemon_red_completion.red_party_development_venue_priors import (
    RED_PARTY_DEVELOPMENT_OUTCOME_POLICY,
    RedPartyDevelopmentVenuePriorError,
    attest_red_route_11_source_compatibility,
    compose_red_route_11_venue_prior,
    red_route_11_operational_contract,
)
from pokemon_red_completion.training_venue import TrainingVenue

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLAN_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-party-development-outcome-plan-v2-2026-08-14.json"
)
RESULT_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-party-development-outcome-result-v2-2026-08-14.json"
)


def _documents() -> tuple[dict[str, object], dict[str, object]]:
    return (
        json.loads(PLAN_PATH.read_text(encoding="ascii")),
        json.loads(RESULT_PATH.read_text(encoding="ascii")),
    )


@lru_cache(maxsize=1)
def _source_compatibility():
    identity = detect_source_identity(PROJECT_ROOT)
    assert identity.git_commit is not None
    current_bundle = committed_source_bundle_sha256(
        PROJECT_ROOT,
        revision=identity.git_commit,
    )
    return attest_red_route_11_source_compatibility(
        PROJECT_ROOT,
        current_commit=identity.git_commit,
        current_source_bundle_sha256=current_bundle,
    )


def _composition(
    plan: dict[str, object] | None = None,
    result: dict[str, object] | None = None,
    *,
    result_sha256: str | None = None,
):
    default_plan, default_result = _documents()
    compatibility = _source_compatibility()
    return compose_red_route_11_venue_prior(
        plan=default_plan if plan is None else plan,
        result=default_result if result is None else result,
        public_plan_sha256=hashlib.sha256(PLAN_PATH.read_bytes()).hexdigest(),
        public_result_sha256=(
            hashlib.sha256(RESULT_PATH.read_bytes()).hexdigest()
            if result_sha256 is None
            else result_sha256
        ),
        registry_source_commit=compatibility.current_commit,
        registry_source_bundle_sha256=(
            compatibility.current_source_bundle_sha256
        ),
        source_compatibility=compatibility,
    )


def test_route_11_receipts_compose_the_exact_observed_unit_ratios() -> None:
    composition = _composition()
    evidence = composition.evidence

    assert evidence.source_commit == "00499bc68b099ffcd0125a6777bc3b836a84ff0b"
    assert evidence.source_bundle_sha256 == (
        "969f6ae2f60282848d26d4097fcefe6e9881f3739d78b560bdf0f186482f6294"
    )
    assert evidence.venue == ROUTE_11_TRAINING_VENUE.band
    assert evidence.support_count == 1
    assert evidence.reliability == VenuePriorUnitRatio(1, 1)
    assert evidence.expected_yield == VenuePriorUnitRatio(4, 4)
    assert evidence.matchup_safety == VenuePriorUnitRatio(108, 108)
    assert evidence.travel_cost == VenuePriorUnitRatio(0, 108)
    assert evidence.recovery_cost == VenuePriorUnitRatio(10, 118)
    assert composition.registry.source_commit == (
        composition.source_compatibility.current_commit
    )
    assert composition.registry.source_bundle_sha256 == (
        composition.source_compatibility.current_source_bundle_sha256
    )


def test_composed_registry_round_trips_but_public_projection_hides_support() -> None:
    composition = _composition()
    restored = PartyDevelopmentVenuePriorRegistry.from_private_dict(
        composition.registry.private_dict()
    )
    public = composition.public_dict()
    encoded = json.dumps(public, sort_keys=True)

    assert restored == composition.registry
    assert public["accepted_venue_evidence_count"] == 1
    assert public["rejected_stale_sibling_venue_count"] == 1
    assert public["outcomes_executed"] == 0
    assert public["teacher_queries"] == 0
    assert public["sealed_test_cases_opened"] == 0
    assert public["crystal_contexts_opened"] == 0
    assert public["private_path_fields"] == 0
    assert "red-goal-v1-029" not in encoded
    assert "24b848eeb9d0d7b1" not in encoded
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("retreat_hp_ratio", 0.44),
        ("reserve_total_pp", 3),
        ("maximum_battles", 199),
        ("maximum_budgeted_center_calls", 49),
        ("mandatory_heal_only_when_health_status_or_pp_is_unsafe", False),
    ),
)
def test_composition_rejects_published_policy_drift(
    field: str, replacement: object
) -> None:
    plan, result = _documents()
    drifted = copy.deepcopy(plan)
    training_policy = drifted["training_policy"]
    assert isinstance(training_policy, dict)
    training_policy[field] = replacement

    with pytest.raises(
        RedPartyDevelopmentVenuePriorError,
        match="training policy differs",
    ):
        _composition(drifted, result)


def test_composition_rejects_a_result_bound_to_another_plan() -> None:
    plan, result = _documents()
    drifted = copy.deepcopy(result)
    bindings = drifted["prospective_bindings"]
    assert isinstance(bindings, dict)
    bindings["public_plan_sha256"] = "f" * 64

    with pytest.raises(RedPartyDevelopmentVenuePriorError, match="identity"):
        _composition(plan, drifted)


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("candidate_kind", "higher_encounter_band_15_21"),
        ("evolution_completed", False),
        ("final_target_level", 25),
        ("faints", 1),
    ),
)
def test_composition_rejects_nonqualifying_route_trial(
    field: str, replacement: object
) -> None:
    plan, result = _documents()
    drifted = copy.deepcopy(result)
    collection = drifted["outcome_collection"]
    assert isinstance(collection, dict)
    trials = collection["trials"]
    assert isinstance(trials, list) and isinstance(trials[0], dict)
    trials[0][field] = replacement

    with pytest.raises(RedPartyDevelopmentVenuePriorError, match="bounded evolution"):
        _composition(plan, drifted)


@pytest.mark.parametrize(
    "field",
    ("fully_measured", "learner_update_eligible"),
)
def test_composition_rejects_an_outcome_excluded_from_learning(field: str) -> None:
    plan, result = _documents()
    drifted = copy.deepcopy(result)
    collection = drifted["outcome_collection"]
    assert isinstance(collection, dict)
    collection[field] = False

    with pytest.raises(RedPartyDevelopmentVenuePriorError, match="bounded evolution"):
        _composition(plan, drifted)


def test_composition_rejects_incomplete_center_phase_accounting() -> None:
    plan, result = _documents()
    drifted = copy.deepcopy(result)
    collection = drifted["outcome_collection"]
    assert isinstance(collection, dict)
    trials = collection["trials"]
    assert isinstance(trials, list) and isinstance(trials[0], dict)
    trials[0]["required_recovery_trips"] = 9

    with pytest.raises(RedPartyDevelopmentVenuePriorError, match="accounting"):
        _composition(plan, drifted)


def test_composition_rejects_sealed_or_cross_title_support() -> None:
    plan, result = _documents()
    for field in ("sealed_test", "crystal"):
        drifted = copy.deepcopy(plan)
        root = drifted["authenticated_root"]
        assert isinstance(root, dict)
        root[field] = True
        with pytest.raises(RedPartyDevelopmentVenuePriorError, match="open independent Red"):
            _composition(drifted, result)


def test_composition_rejects_the_stale_sibling_as_candidate_zero() -> None:
    plan, result = _documents()
    drifted = copy.deepcopy(plan)
    construction = drifted["candidate_construction"]
    assert isinstance(construction, dict)
    construction["ordered_minimum_encounter_levels"] = [15, 9]
    construction["ordered_maximum_encounter_levels"] = [21, 15]

    with pytest.raises(RedPartyDevelopmentVenuePriorError, match="candidate zero"):
        _composition(drifted, result)


def test_operational_contract_changes_when_policy_changes() -> None:
    compatibility = _source_compatibility()
    baseline = red_route_11_operational_contract(
        source_compatibility=compatibility
    )
    changed = red_route_11_operational_contract(
        source_compatibility=compatibility,
        policy=replace(
            RED_PARTY_DEVELOPMENT_OUTCOME_POLICY,
            retreat_hp_ratio=0.44,
        )
    )

    assert changed.policy_sha256 != baseline.policy_sha256
    assert changed.encounter_execution_sha256 == baseline.encounter_execution_sha256
    assert changed.recovery_execution_sha256 == baseline.recovery_execution_sha256
    assert changed.battle_timing_sha256 == baseline.battle_timing_sha256
    assert changed.accounting_sha256 == baseline.accounting_sha256
    assert changed.operational_contract_sha256 != baseline.operational_contract_sha256


def test_operational_contract_rejects_a_stateful_route_11_walker() -> None:
    drifted = replace(
        ROUTE_11_TRAINING_VENUE,
        walk_to_grass_factory=lambda: ROUTE_11_TRAINING_VENUE.walk_to_grass,
    )

    with pytest.raises(RedPartyDevelopmentVenuePriorError, match="operating seam"):
        red_route_11_operational_contract(
            source_compatibility=_source_compatibility(),
            venue=drifted,
        )


def test_stateless_walker_proof_recomputes_the_loaded_ast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        venue_prior_module,
        "_loaded_element_ast_sha256",
        lambda *_args, **_kwargs: "f" * 64,
    )

    with pytest.raises(
        RedPartyDevelopmentVenuePriorError,
        match="positive statelessness proof",
    ):
        venue_prior_module._require_positive_route_11_stateless_walker()  # noqa: SLF001


def test_source_compatibility_recomputes_exact_bundles_and_ten_waivers() -> None:
    attestation = _source_compatibility()

    assert attestation.observed_commit == (
        "00499bc68b099ffcd0125a6777bc3b836a84ff0b"
    )
    assert attestation.observed_source_bundle_sha256 == (
        "969f6ae2f60282848d26d4097fcefe6e9881f3739d78b560bdf0f186482f6294"
    )
    assert attestation.waived_elements == (
        "core.project-trainee-candidates",
        "core.project-trainee-choice-set",
        "core.project-venue-candidates",
        "core.project-venue-choice-set",
        "module-assignments.blaine",
        "module-assignments.training-venue",
        "red.run-team-balancing",
        "red.team-training-execution-summary",
        "red.training-dig-to-vermilion",
        "training-venue.contract",
    )
    assert attestation.unchanged_elements_sha256 == (
        "62c927593fcc27c9dbb874ea38c4d20d4fcc894fd1ea2106ef97b3cf94707ab6"
    )
    assert attestation.current_elements_sha256 == (
        "207c5794759db5e157ce976e8ebf8b72931fe6faa7da5284182bb847d03a08f2"
    )
    assert attestation.waiver_allowlist_sha256 == (
        "c298f591ad9c05816c7521b8ab843b5141c1e2f7c6c419e4b117f635e28e7c14"
    )


def test_source_compatibility_covers_whole_venue_and_grinding_area_classes() -> None:
    elements = {
        spec.element_id: spec.qualname
        for spec in venue_prior_module._ROUTE_11_SOURCE_ELEMENTS  # noqa: SLF001
    }

    assert elements["training-venue.contract"] == "TrainingVenue"
    assert elements["core.grinding-area"] == "GrindingArea"
    assert "training-venue.fresh-walk-to-grass" not in elements
    assert "training-venue.is-in-map" not in elements


def test_source_compatibility_covers_all_element_module_assignments() -> None:
    module_paths = {
        spec.relative_path
        for spec in venue_prior_module._ROUTE_11_SOURCE_ELEMENTS  # noqa: SLF001
        if spec.kind == "module_assignments"
    }

    assert module_paths == {
        "src/pokemon_red_completion/battle_runtime.py",
        "src/pokemon_red_completion/blaine.py",
        "src/pokemon_red_completion/celadon.py",
        "src/pokemon_red_completion/party.py",
        "src/pokemon_red_completion/red_team_training.py",
        "src/pokemon_red_completion/team_training.py",
        "src/pokemon_red_completion/training_candidate_rank.py",
        "src/pokemon_red_completion/training_venue.py",
    }


def test_source_compatibility_rejects_an_uncovered_candidate_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = venue_prior_module._ROUTE_11_SOURCE_ELEMENTS  # noqa: SLF001
    monkeypatch.setattr(
        venue_prior_module,
        "_ROUTE_11_SOURCE_ELEMENTS",
        tuple(
            spec
            for spec in existing
            if spec.element_id != "core.eligible-venues"
        ),
    )

    with pytest.raises(
        RedPartyDevelopmentVenuePriorError,
        match="untracked project code",
    ):
        venue_prior_module._require_route_11_source_closure()  # noqa: SLF001


def test_attestation_invokes_source_closure_independently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attestation = _source_compatibility()

    def reject_closure() -> None:
        raise RedPartyDevelopmentVenuePriorError(
            "independent attestation closure sentinel"
        )

    monkeypatch.setattr(
        venue_prior_module,
        "_require_route_11_source_closure",
        reject_closure,
    )

    with pytest.raises(
        RedPartyDevelopmentVenuePriorError,
        match="independent attestation closure sentinel",
    ):
        attest_red_route_11_source_compatibility(
            PROJECT_ROOT,
            current_commit=attestation.current_commit,
            current_source_bundle_sha256=(
                attestation.current_source_bundle_sha256
            ),
        )


def test_operational_ast_digest_is_stable_across_supported_python_versions() -> None:
    node = ast.parse(
        "def sample(value: int = 1) -> int:\n"
        "    return value + 2\n"
    ).body[0]

    assert venue_prior_module._ast_node_sha256(  # noqa: SLF001
        node,
        qualname="sample",
    ) == "330afe6782e585ceb4d602d6654107636e260596646bf143e5ea99ee13ce931c"


def test_operational_ast_distinguishes_list_and_tuple_fields() -> None:
    assert venue_prior_module._canonical_ast_value([1, 2]) != (  # noqa: SLF001
        venue_prior_module._canonical_ast_value((1, 2))  # noqa: SLF001
    )


def test_operational_ast_rejects_an_unsupported_scalar() -> None:
    with pytest.raises(
        RedPartyDevelopmentVenuePriorError,
        match="unsupported semantic value",
    ):
        venue_prior_module._canonical_ast_value(object())  # noqa: SLF001


@pytest.mark.skipif(
    sys.version_info < (3, 12),
    reason="PEP 695 type-parameter syntax requires Python 3.12+",
)
def test_operational_ast_retains_nonempty_type_parameters() -> None:
    generic = ast.parse("def sample[T](value):\n    return value\n").body[0]
    plain = ast.parse("def sample(value):\n    return value\n").body[0]
    renamed = ast.parse("def sample[S](value):\n    return value\n").body[0]
    widened = ast.parse("def sample[T, U](value):\n    return value\n").body[0]

    generic_digest = venue_prior_module._ast_node_sha256(  # noqa: SLF001
        generic,
        qualname="sample",
    )
    assert generic_digest != venue_prior_module._ast_node_sha256(  # noqa: SLF001
        plain,
        qualname="sample",
    )
    assert generic_digest != venue_prior_module._ast_node_sha256(  # noqa: SLF001
        renamed,
        qualname="sample",
    )
    assert generic_digest != venue_prior_module._ast_node_sha256(  # noqa: SLF001
        widened,
        qualname="sample",
    )


@pytest.mark.parametrize(
    ("baseline", "changed"),
    (
        (b"VALUE = 1\n", b"VALUE = 2\n"),
        (b"VALUE: int = 1\n", b"VALUE: int = 2\n"),
    ),
)
def test_module_assignment_digest_retains_assign_and_annassign_values(
    baseline: bytes,
    changed: bytes,
) -> None:
    assert venue_prior_module._module_assignments_ast_sha256(  # noqa: SLF001
        baseline
    ) != venue_prior_module._module_assignments_ast_sha256(  # noqa: SLF001
        changed
    )


def test_operational_ast_ignores_comments_but_retains_docstrings() -> None:
    baseline = ast.parse("def sample():\n    return 1\n").body[0]
    commented = ast.parse("def sample():\n    # provenance note\n    return 1\n").body[0]
    documented = ast.parse('def sample():\n    "semantic note"\n    return 1\n').body[0]

    baseline_digest = venue_prior_module._ast_node_sha256(  # noqa: SLF001
        baseline,
        qualname="sample",
    )
    assert baseline_digest == venue_prior_module._ast_node_sha256(  # noqa: SLF001
        commented,
        qualname="sample",
    )
    assert baseline_digest != venue_prior_module._ast_node_sha256(  # noqa: SLF001
        documented,
        qualname="sample",
    )


def test_source_compatibility_rejects_a_false_current_bundle_claim() -> None:
    attestation = _source_compatibility()

    with pytest.raises(
        RedPartyDevelopmentVenuePriorError,
        match="current Route 11 source bundle differs",
    ):
        attest_red_route_11_source_compatibility(
            PROJECT_ROOT,
            current_commit=attestation.current_commit,
            current_source_bundle_sha256="f" * 64,
        )


def test_source_compatibility_rejects_loaded_runtime_drift_independently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attestation = _source_compatibility()
    loaded = venue_prior_module._loaded_source_element_rows()  # noqa: SLF001
    drifted = list(loaded)
    drifted[0] = {**drifted[0], "ast_sha256": "f" * 64}
    monkeypatch.setattr(
        venue_prior_module,
        "_loaded_source_element_rows",
        lambda: tuple(drifted),
    )

    with pytest.raises(
        RedPartyDevelopmentVenuePriorError,
        match="loaded Route 11 runtime differs",
    ):
        attest_red_route_11_source_compatibility(
            PROJECT_ROOT,
            current_commit=attestation.current_commit,
            current_source_bundle_sha256=(
                attestation.current_source_bundle_sha256
            ),
        )


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("current_elements_sha256", "f" * 64),
        ("unchanged_elements_sha256", "e" * 64),
        ("waiver_allowlist_sha256", "d" * 64),
        (
            "waived_elements",
            (
                "core.project-trainee-candidates",
                "core.project-trainee-choice-set",
            ),
        ),
    ),
)
def test_operational_contract_rederives_every_attestation_projection(
    field: str,
    replacement: object,
) -> None:
    fabricated = replace(
        _source_compatibility(),
        **{field: replacement},
    )

    with pytest.raises(
        RedPartyDevelopmentVenuePriorError,
        match="operational runtime differs",
    ):
        red_route_11_operational_contract(source_compatibility=fabricated)


def test_source_compatibility_rejects_unlisted_historical_element_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attestation = _source_compatibility()
    original = venue_prior_module.committed_executable_source_blob

    def changed_blob(
        repository_root: str | Path,
        *,
        revision: str,
        relative_path: str,
    ) -> bytes:
        payload = original(
            repository_root,
            revision=revision,
            relative_path=relative_path,
        )
        if (
            revision == attestation.observed_commit
            and relative_path.endswith("/team_training.py")
        ):
            return payload.replace(
                b"class TeamTrainingProgress",
                b"class HistoricalTeamTrainingProgress",
                1,
            )
        return payload

    monkeypatch.setattr(
        venue_prior_module,
        "committed_executable_source_blob",
        changed_blob,
    )

    with pytest.raises(
        RedPartyDevelopmentVenuePriorError,
        match="unreviewed Route 11 source drift",
    ):
        attest_red_route_11_source_compatibility(
            PROJECT_ROOT,
            current_commit=attestation.current_commit,
            current_source_bundle_sha256=(
                attestation.current_source_bundle_sha256
            ),
        )


def test_source_compatibility_rejects_committed_module_constant_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attestation = _source_compatibility()
    original_blob = venue_prior_module.committed_executable_source_blob
    fake_current_bundle = "f" * 64

    def changed_blob(
        repository_root: str | Path,
        *,
        revision: str,
        relative_path: str,
    ) -> bytes:
        payload = original_blob(
            repository_root,
            revision=revision,
            relative_path=relative_path,
        )
        if (
            revision == attestation.current_commit
            and relative_path.endswith("/team_training.py")
        ):
            changed = payload.replace(
                b"MINIMUM_FIGHTABLE_SHARE = 0.25",
                b"MINIMUM_FIGHTABLE_SHARE = 0.05",
                1,
            )
            assert changed != payload
            return changed
        return payload

    def changed_bundle(
        _repository_root: str | Path,
        *,
        revision: str,
    ) -> str:
        if revision == attestation.observed_commit:
            return attestation.observed_source_bundle_sha256
        if revision == attestation.current_commit:
            return fake_current_bundle
        raise AssertionError(f"unexpected revision: {revision}")

    monkeypatch.setattr(
        venue_prior_module,
        "committed_executable_source_blob",
        changed_blob,
    )
    monkeypatch.setattr(
        venue_prior_module,
        "committed_source_bundle_sha256",
        changed_bundle,
    )
    monkeypatch.setattr(
        venue_prior_module,
        "_loaded_source_element_rows",
        lambda: venue_prior_module._committed_source_element_rows(  # noqa: SLF001
            PROJECT_ROOT,
            revision=attestation.current_commit,
        ),
    )

    with pytest.raises(
        RedPartyDevelopmentVenuePriorError,
        match="unreviewed Route 11 source drift: module-assignments.team-training",
    ):
        attest_red_route_11_source_compatibility(
            PROJECT_ROOT,
            current_commit=attestation.current_commit,
            current_source_bundle_sha256=fake_current_bundle,
        )


def test_source_compatibility_rejects_a_stale_waiver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attestation = _source_compatibility()
    existing = venue_prior_module._ROUTE_11_SOURCE_COMPATIBILITY_WAIVERS
    monkeypatch.setattr(
        venue_prior_module,
        "_ROUTE_11_SOURCE_COMPATIBILITY_WAIVERS",
        (
            *existing,
            replace(existing[0], element_id="unused.runtime-change"),
        ),
    )

    with pytest.raises(
        RedPartyDevelopmentVenuePriorError,
        match="stale exception",
    ):
        attest_red_route_11_source_compatibility(
            PROJECT_ROOT,
            current_commit=attestation.current_commit,
            current_source_bundle_sha256=(
                attestation.current_source_bundle_sha256
            ),
        )


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("git_commit", "d" * 40),
        ("source_bundle_sha256", "e" * 64),
    ),
)
def test_composition_rejects_a_false_historical_source_claim(
    field: str,
    replacement: str,
) -> None:
    plan, result = _documents()
    drifted = copy.deepcopy(result)
    source = drifted["source"]
    assert isinstance(source, dict)
    source[field] = replacement

    with pytest.raises(
        RedPartyDevelopmentVenuePriorError,
        match="successful published source|required compatibility proof",
    ):
        _composition(plan, drifted)


def test_composition_pins_the_result_receipt_digest() -> None:
    with pytest.raises(RedPartyDevelopmentVenuePriorError, match="identity"):
        _composition(result_sha256="f" * 64)


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("candidate_kind", "lower_encounter_band_9_15"),
        ("evolution_completed", False),
        ("faints", 99),
        ("battles_completed", 0),
    ),
)
def test_composition_computes_and_validates_the_rejected_stale_sibling(
    field: str,
    replacement: object,
) -> None:
    plan, result = _documents()
    drifted = copy.deepcopy(result)
    collection = drifted["outcome_collection"]
    assert isinstance(collection, dict)
    trials = collection["trials"]
    assert isinstance(trials, list) and isinstance(trials[1], dict)
    trials[1][field] = replacement

    with pytest.raises(RedPartyDevelopmentVenuePriorError, match="stale Cave"):
        _composition(plan, drifted)


def test_operational_contract_has_independent_golden_coverage() -> None:
    contract = red_route_11_operational_contract(
        source_compatibility=_source_compatibility()
    )

    assert contract.policy_sha256 == (
        "bb1ff8c7b449b359f01c7c1c9474c1a660ea604f629cbc0c9130e20030a7cd8c"
    )
    assert contract.encounter_execution_sha256 == (
        "cf2c6be5946cf560051c8bde8ddeff0a1fb2d726e65e1557b05731ca16481b70"
    )
    assert contract.recovery_execution_sha256 == (
        "947a6d8812f6c2f9000f9ce14f5fa05ebad428f13f5a6950c93601bd50b14e90"
    )
    assert contract.battle_timing_sha256 == (
        "c02aecda4093bf3f49a029dd9ce1823aa4163d5ef7f8b7addfa7ef186f7cba79"
    )
    assert contract.accounting_sha256 == (
        "b0d9aac12951e68958cf086c4602d277a7775e2676506e24d062dd28fe1bf874"
    )


@pytest.mark.parametrize(
    "venue",
    (
        replace(
            ROUTE_11_TRAINING_VENUE,
            band=replace(
                ROUTE_11_TRAINING_VENUE.band,
                measured_samples=80,
            ),
        ),
        replace(
            ROUTE_11_TRAINING_VENUE,
            walk_to_grass=lambda *_args: 1,
        ),
    ),
)
def test_operational_contract_rejects_measured_band_or_walker_identity_drift(
    venue: TrainingVenue,
) -> None:
    with pytest.raises(RedPartyDevelopmentVenuePriorError, match="operating seam"):
        red_route_11_operational_contract(
            source_compatibility=_source_compatibility(),
            venue=venue,
        )


def test_operational_contract_rejects_drift_in_the_global_measured_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    drifted = replace(
        ROUTE_11_TRAINING_VENUE,
        band=replace(
            ROUTE_11_TRAINING_VENUE.band,
            measured_samples=80,
        ),
    )
    monkeypatch.setattr(
        venue_prior_module,
        "ROUTE_11_TRAINING_VENUE",
        drifted,
    )

    with pytest.raises(RedPartyDevelopmentVenuePriorError, match="operating seam"):
        red_route_11_operational_contract(
            source_compatibility=_source_compatibility(),
            venue=drifted,
        )
