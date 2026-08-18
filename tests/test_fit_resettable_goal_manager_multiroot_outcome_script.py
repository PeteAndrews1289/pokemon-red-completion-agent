from __future__ import annotations

import hashlib
import os
import runpy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from pokemon_red_completion.goal_manager_model import (
    GOAL_MANAGER_FEATURE_NAMES,
    GoalManagerLinearModel,
    canonical_goal_manager_model_sha256,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts/fit_resettable_goal_manager_multiroot_outcome.py"),
    run_name="fit_resettable_goal_manager_multiroot_outcome_script_test",
)
SCRIPT_GLOBALS = SCRIPT["_fit"].__globals__


def _model(weight: float = 0.0) -> GoalManagerLinearModel:
    width = len(GOAL_MANAGER_FEATURE_NAMES)
    weights = np.zeros(width)
    weights[0] = weight
    return GoalManagerLinearModel(
        weights=weights,
        feature_mean=np.zeros(width),
        feature_scale=np.ones(width),
        l2=0.02,
        training_epochs=1,
    )


def _ready(model: GoalManagerLinearModel | None = None):  # type: ignore[no-untyped-def]
    candidate = model or _model()
    development = SimpleNamespace(source=SimpleNamespace(git_commit="a" * 40))
    paired = SimpleNamespace(
        development=development,
        candidate_model=candidate,
        candidate_model_canonical_sha256=canonical_goal_manager_model_sha256(candidate),
    )
    return SimpleNamespace(paired=paired)


def _prepared(
    *,
    partition: str = "train",
    trial_roster: str = "c" * 64,
    menu_roster: str = "d" * 64,
    winner_roster: str = "e" * 64,
):  # type: ignore[no-untyped-def]
    runner_sha256 = SCRIPT["_file_sha256"](Path(SCRIPT["__file__"]).resolve())
    learner_sha256 = SCRIPT["_file_sha256"](
        PROJECT_ROOT / "src/pokemon_red_completion/resettable_goal_manager_multiroot_learning.py"
    )
    return SCRIPT["_PreparedInputs"](
        partition=partition,
        trials=(),
        trial_manifest_roster_sha256=trial_roster,
        guard_examples=(),
        kl_examples=(),
        guard_winner_manifest_roster_sha256=winner_roster,
        guard_menu_manifest_roster_sha256=menu_roster,
        runner_sha256=runner_sha256,
        learner_sha256=learner_sha256,
    )


class _Sealed:
    def __init__(self, record: dict[str, object]) -> None:
        self._record = record
        self.summary = SimpleNamespace(
            manifest_sha256="1" * 64,
            record_sha256="2" * 64,
        )

    def read(self) -> dict[str, object]:
        return dict(self._record)


def test_fit_and_comparison_identities_bind_all_manifest_rosters() -> None:
    ready = _ready()
    qualified = SimpleNamespace(plan_sha256="b" * 64)
    original = _prepared()
    changed_trial = replace(original, trial_manifest_roster_sha256="f" * 64)
    changed_menu = replace(original, guard_menu_manifest_roster_sha256="0" * 64)
    changed_winner = replace(original, guard_winner_manifest_roster_sha256="1" * 64)

    identities = {
        SCRIPT["_fit_identity"](ready, qualified, prepared)
        for prepared in (original, changed_trial, changed_menu, changed_winner)
    }
    comparison_identities = {
        SCRIPT["_comparison_identity"](
            ready,
            qualified,
            prepared,
            fit_identity_sha256=SCRIPT["_fit_identity"](
                ready,
                qualified,
                original,
            ),
            candidate_model=_model(0.1),
            bundle_manifest_sha256="9" * 64,
        )
        for prepared in (original, changed_trial, changed_menu, changed_winner)
    }

    assert len(identities) == 4
    assert len(comparison_identities) == 4


def test_prepared_inventory_requires_campaign_terminal_before_any_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    campaign = SCRIPT["campaign"]
    qualified = SimpleNamespace(plan={}, store=SimpleNamespace())
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "open_fixed_account_claim_registry",
        lambda: Path("registry"),
    )
    monkeypatch.setattr(
        campaign,
        "_require_campaign_terminal",
        lambda *_args: order.append("terminal"),
    )
    monkeypatch.setattr(
        campaign,
        "_require_consumption_claims",
        lambda *_args: order.append("campaign_claims"),
    )
    monkeypatch.setattr(
        campaign,
        "_require_trial_claims",
        lambda *_args: order.append("trial_claims"),
    )
    monkeypatch.setattr(campaign, "_trials", lambda _plan: ())
    monkeypatch.setitem(SCRIPT_GLOBALS, "MULTIROOT_TRAIN_EPISODES", 0)
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "_load_guard_sets",
        lambda *_args: (
            (SimpleNamespace(),) * 18,
            (SimpleNamespace(),) * 54,
            "d" * 64,
            "e" * 64,
        ),
    )

    prepared = SCRIPT["_prepare_inputs"](_ready(), qualified, partition="train")

    assert order == ["terminal", "campaign_claims", "trial_claims"]
    assert prepared.trials == ()


def test_missing_campaign_terminal_stops_before_inventory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign = SCRIPT["campaign"]
    inspected = False

    def inspect(_episode: str):  # type: ignore[no-untyped-def]
        nonlocal inspected
        inspected = True
        return SimpleNamespace(status="partial", manifest_sha256=None, reason_code=None)

    qualified = SimpleNamespace(plan={}, store=SimpleNamespace(inspect_episode_state=inspect))
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "open_fixed_account_claim_registry",
        lambda: Path("registry"),
    )
    monkeypatch.setattr(
        campaign,
        "_require_campaign_terminal",
        lambda *_args: (_ for _ in ()).throw(
            campaign.ResettableMultirootRunError("campaign_terminal_authentication")
        ),
    )

    with pytest.raises(campaign.ResettableMultirootRunError):
        SCRIPT["_prepare_inputs"](_ready(), qualified, partition="train")

    assert inspected is False


def test_partition_inventory_never_inspects_the_other_partition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign = SCRIPT["campaign"]
    trials = tuple(
        {
            "episode_id": f"episode-{index}",
            "partition": "train" if index < 8 else "development",
            "trial_claim_sha256": f"{index + 1:064x}",
            "trial_index": index,
        }
        for index in range(12)
    )
    inspected: list[str] = []

    def inspect(episode_id: str):  # type: ignore[no-untyped-def]
        inspected.append(episode_id)
        return SimpleNamespace(
            status="absent",
            manifest_sha256=None,
            reason_code=None,
        )

    qualified = SimpleNamespace(
        plan={},
        store=SimpleNamespace(inspect_episode_state=inspect),
    )
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "open_fixed_account_claim_registry",
        lambda: Path("registry"),
    )
    monkeypatch.setattr(campaign, "_require_campaign_terminal", lambda *_args: None)
    monkeypatch.setattr(campaign, "_require_consumption_claims", lambda *_args: None)
    monkeypatch.setattr(campaign, "_require_trial_claims", lambda *_args: None)
    monkeypatch.setattr(campaign, "_trials", lambda _plan: trials)
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "_load_guard_sets",
        lambda *_args: (
            (SimpleNamespace(),) * 18,
            (SimpleNamespace(),) * 54,
            "d" * 64,
            "e" * 64,
        ),
    )

    train = SCRIPT["_prepare_inputs"](_ready(), qualified, partition="train")

    assert inspected == [f"episode-{index}" for index in range(8)]
    assert len(train.trials) == 8
    inspected.clear()

    development = SCRIPT["_prepare_inputs"](
        _ready(),
        qualified,
        partition="development",
        guard_source=train,
    )

    assert inspected == [f"episode-{index}" for index in range(8, 12)]
    assert len(development.trials) == 4


def test_fit_claim_precedes_decode_and_retains_sanitized_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    order: list[str] = []
    terminals: list[dict[str, object]] = []
    ready = _ready()
    qualified = SimpleNamespace(plan_sha256="b" * 64)
    prepared = _prepared()
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "_claim_operation",
        lambda *_args: order.append("claim"),
    )

    def reject(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        order.append("decode")
        raise SCRIPT["ResettableGoalManagerLearningError"]("threshold")

    monkeypatch.setitem(SCRIPT_GLOBALS, "_decode_prepared_partition", reject)

    def publish(*_args, record, **_kwargs):  # type: ignore[no-untyped-def]
        order.append("terminal")
        terminals.append(dict(record))
        return _Sealed(dict(record))

    monkeypatch.setitem(SCRIPT_GLOBALS, "_publish_operation_terminal", publish)

    with pytest.raises(SCRIPT["ResettableGoalManagerLearningError"]):
        SCRIPT["_fit"](
            ready,
            qualified,
            prepared,
            tmp_path / "candidate",
            "f" * 64,
        )

    assert order == ["claim", "decode", "terminal"]
    assert terminals[0]["status"] == "failed"
    assert terminals[0]["failure_stage"] == "preregistered_learning_gate_rejected"
    assert terminals[0]["model_fits"] == 0


def test_fit_retains_failure_terminal_for_keyboard_interrupt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    terminals: list[dict[str, object]] = []
    monkeypatch.setitem(SCRIPT_GLOBALS, "_claim_operation", lambda *_args: None)
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "_decode_prepared_partition",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "_publish_operation_terminal",
        lambda *_args, record, **_kwargs: terminals.append(dict(record)) or _Sealed(dict(record)),
    )

    with pytest.raises(KeyboardInterrupt):
        SCRIPT["_fit"](
            _ready(),
            SimpleNamespace(plan_sha256="b" * 64),
            _prepared(),
            tmp_path / "candidate",
            "f" * 64,
        )

    assert terminals[0]["status"] == "failed"
    assert terminals[0]["failure_stage"] == "unexpected_failure"


def test_complete_but_unsettled_development_is_durably_uninterpretable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    order: list[str] = []
    terminals: list[dict[str, object]] = []
    ready = _ready()
    qualified = SimpleNamespace(plan_sha256="b" * 64)
    prepared = _prepared(partition="development")
    episodes = tuple(SimpleNamespace(targets=()) for _ in range(4))
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "_claim_operation",
        lambda *_args: order.append("claim"),
    )

    def decode(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        order.append("decode")
        return episodes, {}

    monkeypatch.setitem(SCRIPT_GLOBALS, "_decode_prepared_partition", decode)

    def publish(*_args, record, **_kwargs):  # type: ignore[no-untyped-def]
        order.append("terminal")
        terminals.append(dict(record))
        return _Sealed(dict(record))

    monkeypatch.setitem(SCRIPT_GLOBALS, "_publish_operation_terminal", publish)
    output = tmp_path / "comparison.json"

    result = SCRIPT["_compare"](
        ready,
        qualified,
        prepared,
        candidate_model=_model(0.1),
        bundle_manifest_sha256="9" * 64,
        destination=output,
        comparison_identity="8" * 64,
    )

    assert order == ["claim", "decode", "terminal"]
    assert result["status"] == "fixed_denominator_uninterpretable"
    assert result["settled_development_targets"] == 0
    assert terminals[0]["status"] == "fixed_denominator_uninterpretable"
    assert terminals[0]["comparisons"] == 0
    assert output.is_file()


def test_comparison_terminal_failure_retains_published_result_digest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    terminals: list[dict[str, object]] = []
    episodes = tuple(SimpleNamespace(targets=()) for _ in range(4))
    monkeypatch.setitem(SCRIPT_GLOBALS, "_claim_operation", lambda *_args: None)
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "_decode_prepared_partition",
        lambda *_args, **_kwargs: (episodes, {}),
    )

    def publish(*_args, record, **_kwargs):  # type: ignore[no-untyped-def]
        terminals.append(dict(record))
        if len(terminals) == 1:
            raise SCRIPT["MultirootFitRunError"]("comparison_terminal_publication")
        return _Sealed(dict(record))

    monkeypatch.setitem(SCRIPT_GLOBALS, "_publish_operation_terminal", publish)
    output = tmp_path / "comparison.json"

    with pytest.raises(
        SCRIPT["MultirootFitRunError"],
        match="comparison_terminal_publication",
    ):
        SCRIPT["_compare"](
            _ready(),
            SimpleNamespace(plan_sha256="b" * 64),
            _prepared(partition="development"),
            candidate_model=_model(0.1),
            bundle_manifest_sha256="9" * 64,
            destination=output,
            comparison_identity="8" * 64,
        )

    assert output.is_file()
    assert terminals[1]["status"] == "failed"
    assert terminals[1]["output_file_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert terminals[1]["result_sha256"] == terminals[1]["output_file_sha256"]


def test_descriptor_reader_rejects_symlink_wrong_mode_and_hard_link(
    tmp_path: Path,
) -> None:
    subject = "candidate model"
    regular = tmp_path / "regular.json"
    regular.write_bytes(b"{}\n")
    regular.chmod(0o600)
    assert SCRIPT["_read_regular_file"](regular, subject) == b"{}\n"

    symlink = tmp_path / "symlink.json"
    symlink.symlink_to(regular)
    with pytest.raises(SCRIPT["MultirootFitRunError"], match="authentication"):
        SCRIPT["_read_regular_file"](symlink, subject)

    permissive = tmp_path / "permissive.json"
    permissive.write_bytes(b"{}\n")
    permissive.chmod(0o644)
    with pytest.raises(SCRIPT["MultirootFitRunError"], match="authentication"):
        SCRIPT["_read_regular_file"](permissive, subject)

    linked = tmp_path / "linked.json"
    os.link(regular, linked)
    with pytest.raises(SCRIPT["MultirootFitRunError"], match="authentication"):
        SCRIPT["_read_regular_file"](regular, subject)

    source = tmp_path / "source.py"
    source.write_bytes(b"pass\n")
    source.chmod(0o644)
    assert SCRIPT["_file_sha256"](source) == hashlib.sha256(b"pass\n").hexdigest()
    source_symlink = tmp_path / "source-link.py"
    source_symlink.symlink_to(source)
    with pytest.raises(SCRIPT["MultirootFitRunError"], match="source_file"):
        SCRIPT["_file_sha256"](source_symlink)
    source_hardlink = tmp_path / "source-hardlink.py"
    os.link(source, source_hardlink)
    with pytest.raises(SCRIPT["MultirootFitRunError"], match="source_file"):
        SCRIPT["_file_sha256"](source)


def test_atomic_comparison_publication_never_replaces_collision(tmp_path: Path) -> None:
    destination = tmp_path / "comparison.json"
    first = b'{"status":"first"}\n'
    second = b'{"status":"second"}\n'

    digest = SCRIPT["_write_atomic_no_replace"](
        destination,
        first,
        subject="comparison",
    )

    assert digest == hashlib.sha256(first).hexdigest()
    assert destination.read_bytes() == first
    assert destination.stat().st_mode & 0o777 == 0o600
    with pytest.raises(SCRIPT["MultirootFitRunError"], match="comparison_publication"):
        SCRIPT["_write_atomic_no_replace"](
            destination,
            second,
            subject="comparison",
        )
    assert destination.read_bytes() == first


def test_candidate_bundle_requires_external_manifest_and_exact_fit_terminal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model = _model(0.1)
    ready = _ready()
    prepared = _prepared(partition="train")
    qualified = SimpleNamespace(plan_sha256="b" * 64, store=None)
    fit_identity = SCRIPT["_fit_identity"](ready, qualified, prepared)
    model_payload = SCRIPT["_canonical_line"](model.to_dict())
    model_file_sha256 = hashlib.sha256(model_payload).hexdigest()
    summary = {
        "schema": "pokemon.red.resettable-goal-manager-fit-summary.v1",
        "status": "train_only_shadow_fit_complete",
        "fit_identity_sha256": fit_identity,
        "campaign_plan_sha256": qualified.plan_sha256,
        "campaign_terminal_sha256": SCRIPT["campaign"]._campaign_terminal_identity(qualified),
        "base_model_canonical_sha256": ready.paired.candidate_model_canonical_sha256,
        "candidate_model_canonical_sha256": canonical_goal_manager_model_sha256(model),
        "candidate_model_file_sha256": model_file_sha256,
        "train_gate": {},
        "fit": {},
        "trial_manifest_roster_sha256": prepared.trial_manifest_roster_sha256,
        "guard_menu_manifest_roster_sha256": prepared.guard_menu_manifest_roster_sha256,
        "guard_winner_manifest_roster_sha256": (prepared.guard_winner_manifest_roster_sha256),
        "invalid_train_states": {},
        "development_outcomes_accessed": 0,
        "evaluation": None,
        "promotion_authorized": False,
        "authority_delta": 0,
        "private_path_fields": 0,
    }
    summary_payload = SCRIPT["_canonical_line"](summary)
    bundle = tmp_path / "candidate"
    manifest_sha256 = SCRIPT["_publish_bundle"](
        bundle,
        model_payload=model_payload,
        summary_payload=summary_payload,
        identity_sha256=fit_identity,
    )
    terminal_record = SCRIPT["_fit_terminal_record"](
        ready,
        qualified,
        prepared,
        fit_identity=fit_identity,
        status="complete",
        failure_stage=None,
        model_fits=1,
        bundle_manifest_sha256=manifest_sha256,
        candidate_model_canonical_sha256=canonical_goal_manager_model_sha256(model),
        candidate_model_file_sha256=model_file_sha256,
        summary_file_sha256=hashlib.sha256(summary_payload).hexdigest(),
    )
    qualified.store = SimpleNamespace(
        find_sealed_record=lambda *_args, **_kwargs: _Sealed(terminal_record)
    )
    runner_sha256 = SCRIPT["_file_sha256"](Path(SCRIPT["__file__"]).resolve())
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "open_fixed_account_claim_registry",
        lambda: Path("registry"),
    )
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "read_root_claim",
        lambda *_args: {
            "schema": "pokemon.red.fresh-composition-root-claim.v1",
            "root_consumption_sha256": fit_identity,
            "execution_identity_sha256": fit_identity,
            "source_commit": "a" * 40,
            "runner_sha256": runner_sha256,
        },
    )

    with pytest.raises(SCRIPT["MultirootFitRunError"], match="bundle_attestation"):
        SCRIPT["_load_candidate_bundle"](
            bundle,
            tmp_path,
            ready=ready,
            qualified=qualified,
            prepared=prepared,
            expected_fit_identity=fit_identity,
            expected_bundle_manifest_sha256="0" * 64,
            expected_source_commit="a" * 40,
        )

    loaded, observed_manifest = SCRIPT["_load_candidate_bundle"](
        bundle,
        tmp_path,
        ready=ready,
        qualified=qualified,
        prepared=prepared,
        expected_fit_identity=fit_identity,
        expected_bundle_manifest_sha256=manifest_sha256,
        expected_source_commit="a" * 40,
    )

    assert loaded.to_dict() == model.to_dict()
    assert observed_manifest == manifest_sha256

    altered_terminal = dict(terminal_record)
    altered_terminal["model_fits"] = 0
    qualified.store = SimpleNamespace(
        find_sealed_record=lambda *_args, **_kwargs: _Sealed(altered_terminal)
    )
    with pytest.raises(SCRIPT["MultirootFitRunError"], match="fit_terminal"):
        SCRIPT["_load_candidate_bundle"](
            bundle,
            tmp_path,
            ready=ready,
            qualified=qualified,
            prepared=prepared,
            expected_fit_identity=fit_identity,
            expected_bundle_manifest_sha256=manifest_sha256,
            expected_source_commit="a" * 40,
        )


def test_offline_runner_separates_fit_and_comparison_modes() -> None:
    parser = SCRIPT["_parser"]()
    choices = parser._option_string_actions["--mode"].choices

    assert tuple(choices) == (
        "preflight-fit",
        "fit",
        "preflight-compare",
        "compare",
    )
    assert "--expected-candidate-bundle-manifest-sha256" in parser._option_string_actions
