from __future__ import annotations

import hashlib
import json
import runpy
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.goal_manager_outcome_learning import outcome_update_configuration

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts/fit_goal_manager_acquisition_successor.py"),
    run_name="fit_goal_manager_acquisition_successor_test",
)
FIT_PLAN = (
    PROJECT_ROOT / "docs/evidence/goal-manager-acquisition-successor-fit-plan-v1-2026-08-18.json"
)
FAILURE_RECEIPT = (
    PROJECT_ROOT / "docs/evidence/acquisition-replanning-campaign-freeze-failure-v1-2026-08-18.json"
)
FIT_FAILURE_RECEIPT = (
    PROJECT_ROOT / "docs/evidence/goal-manager-acquisition-successor-fit-failure-v1-2026-08-18.json"
)


def test_fit_plan_freezes_one_new_target_and_two_evaluation_only_anchors() -> None:
    plan = json.loads(FIT_PLAN.read_bytes())

    assert plan["status"] == "frozen_before_private_outcome_decode"
    assert plan["configuration"] == outcome_update_configuration()
    assert plan["data_boundary"] == {
        "anchor_targets": 2,
        "anchor_use": "evaluation_only_no_gradient",
        "excluded_duplicate_base_arm": 1,
        "excluded_failed_prefix_choices": 19,
        "fresh_targets": 1,
        "validation_examples": 0,
        "test_examples": 0,
    }
    assert plan["gates"]["anchor_selected_probabilities"] == "nondecrease"
    assert plan["gates"]["protected_winner_flips"] == 0
    assert "living_pokedex_completion" in plan["claim_boundary"]["unsupported"]


def test_failed_acquisition_campaign_is_closed_with_zero_effects() -> None:
    receipt = json.loads(FAILURE_RECEIPT.read_bytes())

    assert receipt["status"] == "campaign_freeze_failed_closed_no_retry"
    assert receipt["failure"]["failed_stage"] == "action_free_root_inventory"
    assert receipt["campaign_state"]["campaign_plan_created"] is False
    assert receipt["campaign_state"]["retry_allowed"] is False
    assert set(receipt["zero_effects"].values()) == {0}
    assert set(receipt["counter_treatment"].values()) == {0}
    assert receipt["tracked_private_paths"] == 0
    assert receipt["tracked_private_identities"] == 0


def test_successor_fit_failure_is_consumed_without_counter_or_authority_gain() -> None:
    receipt = json.loads(FIT_FAILURE_RECEIPT.read_bytes())

    assert receipt["status"] == "fit_attempt_consumed_failed_closed_no_retry"
    assert receipt["attempt"] == {
        "candidate_bundle_created": False,
        "candidate_model_sha256": None,
        "cause_retained": False,
        "failure_stage": "unexpected_failure",
        "fit_identity_sha256": "83556d3e1aa4af942109c134ebd090f2ed0b2fd47f42fbd407ae0d34b15ca70e",
        "identity_consumed": True,
        "model_fit_attempts": 1,
        "model_fits_added": 0,
        "phase": "fit_attempted",
        "retry_allowed": False,
    }
    assert receipt["claim"]["durable_before_outcome_decode"] is True
    assert receipt["claim"]["semantic_outcomes_decoded_before_claim"] == 0
    assert set(receipt["counter_treatment"].values()) == {0}
    assert receipt["tracked_private_paths"] == 0
    assert receipt["tracked_private_identities"] == 0


class _Reader:
    def __init__(self, manifest_sha256: str) -> None:
        self.manifest_sha256 = manifest_sha256


class _State:
    status = "complete"


class _Store:
    def __init__(self, manifests: dict[str, str]) -> None:
        self.manifests = manifests

    def inspect_episode_state(self, episode_id: str) -> _State:
        assert episode_id in self.manifests
        return _State()

    def open_episode(self, episode_id: str) -> _Reader:
        return _Reader(self.manifests[episode_id])


def test_preflight_authenticates_manifests_without_decoding_outcomes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    claim = tmp_path / "claim.json"
    called: list[str] = []
    monkeypatch.setitem(
        SCRIPT["_preflight"].__globals__,
        "_prepare_private_readers",
        lambda _ready: called.append("authenticate") or {},
    )
    ready = {
        "private_root": tmp_path,
        "anchor_episode_id": "anchor",
        "candidate_episode_id": "candidate",
        "inputs": {
            "anchor_manifest_sha256": "1" * 64,
            "candidate_acquisition_manifest_sha256": "2" * 64,
        },
        "claim_path": claim,
        "fit_identity": "3" * 64,
        "fit_plan_sha256": "4" * 64,
        "learner_sha256": "5" * 64,
        "numpy_runtime_sha256": "6" * 64,
    }

    result = SCRIPT["_preflight"](ready)

    assert result["status"] == "ready_for_one_offline_successor_update"
    assert result["outcomes_decoded"] == 0
    assert result["model_fits"] == 0
    assert not claim.exists()
    assert called == ["authenticate"]


def test_main_claims_before_semantic_outcome_decode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    globals_ = SCRIPT["main"].__globals__
    monkeypatch.setitem(
        globals_,
        "_parser",
        lambda: SimpleNamespace(parse_args=lambda _argv: SimpleNamespace(preflight_only=False)),
    )
    monkeypatch.setitem(globals_, "_readiness", lambda _args: {"ready": True})
    monkeypatch.setitem(globals_, "fixed_account_claim_registry_root", lambda: tmp_path)
    monkeypatch.setitem(
        globals_, "fixed_account_claim_registry_lease", lambda *_args, **_kwargs: nullcontext()
    )
    monkeypatch.setitem(
        globals_,
        "_prepare_private_readers",
        lambda _ready: events.append("authenticate") or {"reader": object()},
    )
    monkeypatch.setitem(
        globals_, "_write_claim", lambda _ready: events.append("claim") or {"claim": True}
    )
    monkeypatch.setitem(
        globals_,
        "_prepare_fit_inputs",
        lambda _ready, _readers: events.append("decode") or {"prepared": True},
    )
    monkeypatch.setitem(
        globals_,
        "_fit",
        lambda _ready, _claim, _prepared: events.append("fit") or {"status": "complete"},
    )

    assert SCRIPT["main"]([]) == 0
    assert events == ["authenticate", "claim", "decode", "fit"]


def test_prior_fit_provenance_requires_all_four_exact_joins() -> None:
    inputs = {
        "anchor_result_receipt_sha256": "1" * 64,
        "base_training_source_commit": "2" * 40,
        "context_catalog_sha256": "3" * 64,
    }
    prior = {
        "result_receipt_sha256": inputs["anchor_result_receipt_sha256"],
        "base_training_source_commit": inputs["base_training_source_commit"],
        "base_context_catalog_sha256": inputs["context_catalog_sha256"],
        "base_registry_sha256": "4" * 64,
    }
    registry = SimpleNamespace(registry_sha256="4" * 64)

    SCRIPT["_require_prior_fit_provenance"](prior, inputs, registry)
    for field in tuple(prior):
        mutated = dict(prior)
        mutated[field] = "f" * len(str(mutated[field]))
        with pytest.raises(SCRIPT["AcquisitionSuccessorFitError"], match="prior_fit_provenance"):
            SCRIPT["_require_prior_fit_provenance"](mutated, inputs, registry)


def test_fit_claim_is_durable_and_one_shot(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    claim_path = tmp_path / "claim.json"
    ready = {
        "claim_path": claim_path,
        "fit_identity": "1" * 64,
        "fit_plan_sha256": "2" * 64,
        "inputs": {"base_model_canonical_sha256": "3" * 64},
        "source_commit": "4" * 40,
        "runner_sha256": "5" * 64,
        "learner_sha256": "6" * 64,
        "numpy_runtime_sha256": "7" * 64,
    }

    payload = SCRIPT["_write_claim"](ready)

    assert json.loads(claim_path.read_bytes()) == payload
    assert hashlib.sha256(claim_path.read_bytes()).hexdigest()
    assert claim_path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(SCRIPT["AcquisitionSuccessorFitError"], match="consumed"):
        SCRIPT["_write_claim"](ready)


def test_output_bundle_is_atomic_and_self_authenticating(tmp_path: Path) -> None:
    destination = tmp_path / "goal-manager-acquisition-successor-test"

    manifest_sha256 = SCRIPT["_publish_bundle"](
        destination,
        model_payload=b'{"model":1}\n',
        summary_payload=b'{"summary":1}\n',
        fit_identity_sha256="1" * 64,
    )

    manifest = json.loads((destination / "manifest.json").read_bytes())
    assert hashlib.sha256((destination / "manifest.json").read_bytes()).hexdigest() == (
        manifest_sha256
    )
    assert manifest["status"] == "complete"
    assert (
        manifest["files"]["model.json"]
        == hashlib.sha256((destination / "model.json").read_bytes()).hexdigest()
    )
    assert (
        manifest["files"]["summary.json"]
        == hashlib.sha256((destination / "summary.json").read_bytes()).hexdigest()
    )
    with pytest.raises(SCRIPT["AcquisitionSuccessorFitError"], match="publication"):
        SCRIPT["_publish_bundle"](
            destination,
            model_payload=b"x",
            summary_payload=b"y",
            fit_identity_sha256="1" * 64,
        )


def test_output_bundle_creation_failure_preserves_preexisting_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "goal-manager-acquisition-successor-test"
    preexisting = tmp_path / ".unrelated-partial"
    preexisting.mkdir()
    marker = preexisting / "owned-by-someone-else"
    marker.write_text("keep", encoding="utf-8")
    monkeypatch.setattr(
        SCRIPT["_publish_bundle"].__globals__["tempfile"],
        "mkdtemp",
        lambda **_kwargs: (_ for _ in ()).throw(FileExistsError()),
    )

    with pytest.raises(SCRIPT["AcquisitionSuccessorFitError"], match="publication"):
        SCRIPT["_publish_bundle"](
            destination,
            model_payload=b"x",
            summary_payload=b"y",
            fit_identity_sha256="1" * 64,
        )
    assert marker.read_text(encoding="utf-8") == "keep"
