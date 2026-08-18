from __future__ import annotations

import argparse
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.private_artifacts import _validate_episode_id

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = runpy.run_path(str(PROJECT_ROOT / "scripts/run_paired_goal_manager_outcome_screen.py"))


def test_runner_freezes_the_exact_two_prior_campaign_set() -> None:
    assert SCRIPT["EXPECTED_PRIOR_CAMPAIGN_SHA256"] == (
        "e99075d98cd9f3cd390b290fa336c6fe0ecbeccc6b50a643208a89b12d254d14",
        "452cff2afa25278900334b8c0e69583a0c511e943ef727593fed938653f995b9",
    )
    assert SCRIPT["_selection_contract"]() == {
        "development_outcome_unused": True,
        "distinct_roots_formally_inspected": 1,
        "guard_only_exposure_allowed": True,
        "model_scores_used": False,
        "replacement_root_allowed": False,
        "rule": (
            "first_registry_order_train_acquire_species_excluding_prior_"
            "teacher_free_campaign_states_and_closed_roots"
        ),
        "supervised_train_exposure_allowed": True,
    }


def test_arm_episode_identity_fits_the_private_store_contract() -> None:
    episode_id = SCRIPT["_arm_episode_id"]("a" * 64)

    _validate_episode_id(episode_id)
    assert episode_id == "red-pair-" + "a" * 64


def test_wrong_prior_campaign_set_fails_before_base_readiness() -> None:
    readiness = SCRIPT["_readiness"]
    globals_ = readiness.__globals__
    development = globals_["development"]
    called = False

    def forbidden(_args: argparse.Namespace) -> object:
        nonlocal called
        called = True
        raise AssertionError("private readiness must not run")

    original = development._readiness
    development._readiness = forbidden
    try:
        with pytest.raises(SCRIPT["PairedScreenRunError"], match="prior_campaign_attestation"):
            readiness(
                argparse.Namespace(
                    prior_campaign=[Path("one")],
                    expected_prior_campaign_sha256=["0" * 64],
                )
            )
    finally:
        development._readiness = original

    assert called is False


def test_historical_context_plan_opt_in_is_exact_and_preserves_layout_guard() -> None:
    require = SCRIPT["_require_prior_campaign_contract"]
    globals_ = require.__globals__
    development = globals_["development"]
    campaign_sha256, historical_context = next(
        iter(globals_["_HISTORICAL_CONTEXT_PLAN_BY_CAMPAIGN_SHA256"].items())
    )
    campaign = {
        "schema": development.CAMPAIGN_SCHEMA,
        "context_plan_sha256": historical_context,
        "candidate": {"model_canonical_sha256": "1" * 64},
    }
    calls = 0
    original = development._validate_campaign_layout

    def valid(_campaign: object) -> None:
        nonlocal calls
        calls += 1

    development._validate_campaign_layout = valid
    try:
        require(
            campaign,
            campaign_sha256=campaign_sha256,
            current_context_plan_sha256="9" * 64,
            expected_model_canonical_sha256="1" * 64,
            allow_historical_context_plan=True,
        )
        assert calls == 1

        for changed in (
            {**campaign, "schema": "wrong"},
            {**campaign, "candidate": {"model_canonical_sha256": "2" * 64}},
        ):
            with pytest.raises(SCRIPT["PairedScreenRunError"], match="prior_campaign_contract"):
                require(
                    changed,
                    campaign_sha256=campaign_sha256,
                    current_context_plan_sha256="9" * 64,
                    expected_model_canonical_sha256="1" * 64,
                    allow_historical_context_plan=True,
                )

        with pytest.raises(SCRIPT["PairedScreenRunError"], match="prior_campaign_contract"):
            require(
                campaign,
                campaign_sha256="8" * 64,
                current_context_plan_sha256="9" * 64,
                expected_model_canonical_sha256="1" * 64,
                allow_historical_context_plan=True,
            )
        with pytest.raises(SCRIPT["PairedScreenRunError"], match="prior_campaign_contract"):
            require(
                campaign,
                campaign_sha256=campaign_sha256,
                current_context_plan_sha256="9" * 64,
                expected_model_canonical_sha256="1" * 64,
                allow_historical_context_plan=False,
            )

        development._validate_campaign_layout = lambda _campaign: (_ for _ in ()).throw(
            development.RepeatableGoalManagerRunError("campaign_layout")
        )
        with pytest.raises(SCRIPT["PairedScreenRunError"], match="prior_campaign_contract"):
            require(
                campaign,
                campaign_sha256=campaign_sha256,
                current_context_plan_sha256="9" * 64,
                expected_model_canonical_sha256="1" * 64,
                allow_historical_context_plan=True,
            )
    finally:
        development._validate_campaign_layout = original


def test_preflight_root_binding_rejects_a_different_registry_root() -> None:
    require = SCRIPT["_require_selected_root_record"]
    entry_type = SCRIPT["development"]._ContextEntry
    entries = (
        entry_type(
            slot_id="selected-slot",
            state=Path("state"),
            envelope=Path("envelope"),
            profile=Path("profile"),
        ),
        entry_type(
            slot_id="other-slot",
            state=Path("state-2"),
            envelope=Path("envelope-2"),
            profile=Path("profile-2"),
        ),
    )
    selected = "red-goal-root-" + "1" * 64
    correct = {
        "entry_index": 0,
        "root_lineage_id": selected,
        "focus_kind": "acquire_species",
    }
    require(
        selected_root_lineage_id=selected,
        selected_slot_id="selected-slot",
        root_record=correct,
        entries=entries,
    )

    with pytest.raises(SCRIPT["PairedScreenRunError"], match="screen_root_selection"):
        require(
            selected_root_lineage_id=selected,
            selected_slot_id="selected-slot",
            root_record={**correct, "entry_index": 1},
            entries=entries,
        )


def test_formal_selection_excludes_closed_roots_before_choosing() -> None:
    select = SCRIPT["_selected_assignment"]
    globals_ = select.__globals__
    development = globals_["development"]
    open_registry = globals_["open_fixed_account_claim_registry"]
    first = SimpleNamespace(
        partition="train",
        focus_kind=SCRIPT["GoalKind"].ACQUIRE_SPECIES,
        root_lineage_id="red-goal-root-" + "1" * 64,
        slot_id="first",
    )
    second = SimpleNamespace(
        partition="train",
        focus_kind=SCRIPT["GoalKind"].ACQUIRE_SPECIES,
        root_lineage_id="red-goal-root-" + "2" * 64,
        slot_id="second",
    )
    assignments = {"first": first, "second": second}
    contexts = {
        "first": SimpleNamespace(state_sha256="3" * 64, envelope_sha256="4" * 64),
        "second": SimpleNamespace(state_sha256="5" * 64, envelope_sha256="6" * 64),
    }
    base = SimpleNamespace(
        entries=(SimpleNamespace(slot_id="first"), SimpleNamespace(slot_id="second")),
        candidate=SimpleNamespace(
            registry=SimpleNamespace(assignment=assignments.__getitem__),
            catalog=SimpleNamespace(entry=contexts.__getitem__),
        ),
    )
    readiness = SimpleNamespace(development=base, prior_campaigns=())

    globals_["open_fixed_account_claim_registry"] = lambda: object()
    original_open = development._historical_root_is_open
    development._historical_root_is_open = (
        lambda _base, entry, _registry: entry.slot_id != "first"
    )
    try:
        assert select(readiness) is second
    finally:
        development._historical_root_is_open = original_open
        globals_["open_fixed_account_claim_registry"] = open_registry


def test_formal_selection_excludes_prior_state_across_lineage_rollover() -> None:
    select = SCRIPT["_selected_assignment"]
    globals_ = select.__globals__
    development = globals_["development"]
    open_registry = globals_["open_fixed_account_claim_registry"]
    first = SimpleNamespace(
        partition="train",
        focus_kind=SCRIPT["GoalKind"].ACQUIRE_SPECIES,
        root_lineage_id="red-goal-root-" + "7" * 64,
        slot_id="first",
    )
    second = SimpleNamespace(
        partition="train",
        focus_kind=SCRIPT["GoalKind"].ACQUIRE_SPECIES,
        root_lineage_id="red-goal-root-" + "8" * 64,
        slot_id="second",
    )
    assignments = {"first": first, "second": second}
    contexts = {
        "first": SimpleNamespace(state_sha256="a" * 64, envelope_sha256="b" * 64),
        "second": SimpleNamespace(state_sha256="c" * 64, envelope_sha256="d" * 64),
    }
    base = SimpleNamespace(
        entries=(SimpleNamespace(slot_id="first"), SimpleNamespace(slot_id="second")),
        candidate=SimpleNamespace(
            registry=SimpleNamespace(assignment=assignments.__getitem__),
            catalog=SimpleNamespace(entry=contexts.__getitem__),
        ),
    )
    prior = {
        "roots": [
            {
                "root_lineage_id": "red-goal-root-" + "9" * 64,
                "state_sha256": "a" * 64,
                "envelope_sha256": "b" * 64,
            }
        ]
    }
    readiness = SimpleNamespace(development=base, prior_campaigns=(prior,))

    globals_["open_fixed_account_claim_registry"] = lambda: object()
    original_open = development._historical_root_is_open
    development._historical_root_is_open = lambda _base, _entry, _registry: True
    try:
        assert select(readiness) is second
    finally:
        development._historical_root_is_open = original_open
        globals_["open_fixed_account_claim_registry"] = open_registry


def test_failure_stage_never_echoes_private_exception_text() -> None:
    sanitize = SCRIPT["_sanitized_failure_stage"]

    assert sanitize(OSError("/private/secret/root")) == "paired_screen_internal"
    assert sanitize(ValueError("candidate at /private/model")) == "paired_screen_internal"
    assert sanitize(SCRIPT["PairedScreenRunError"]("screen_plan_attestation")) == (
        "screen_plan_attestation"
    )


def test_failure_receipt_does_not_claim_protected_access_absence(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main = SCRIPT["main"]
    globals_ = main.__globals__
    readiness = globals_["_readiness"]
    parser = globals_["_parser"]
    globals_["_parser"] = lambda: SimpleNamespace(
        parse_args=lambda _argv: SimpleNamespace(mode="freeze")
    )
    globals_["_readiness"] = lambda _args: (_ for _ in ()).throw(
        OSError("/private/protected/input")
    )
    try:
        assert main(["--mode", "freeze"]) == 1
    finally:
        globals_["_readiness"] = readiness
        globals_["_parser"] = parser

    receipt = __import__("json").loads(capsys.readouterr().out)
    assert receipt["protected_access_status"] == "not_attested_on_failure"
    assert "sealed_red_accesses" not in receipt
    assert "crystal_accesses" not in receipt


def test_public_freeze_contract_is_zero_effect_and_nonpromoting() -> None:
    public = SCRIPT["_public_freeze_result"]
    plan = {
        "screen_id": "1" * 64,
        "root": {
            "available_goal_kinds": ["acquire_species", "explore"],
            "state_sha256": "2" * 64,
        },
    }
    readiness = SimpleNamespace(
        development=SimpleNamespace(
            candidate=SimpleNamespace(
                plan=SimpleNamespace(model_canonical_sha256="3" * 64)
            )
        ),
        candidate_model_canonical_sha256="4" * 64,
    )

    result = public(readiness, plan=plan)

    assert result["model_predictions"] == 0
    assert result["controller_actions"] == 0
    assert result["game_executions"] == 0
    assert result["unseen_comparisons_added"] == 0
    assert result["promotion_authorized"] is False
    assert result["maximum_decisions_per_arm"] == 3
