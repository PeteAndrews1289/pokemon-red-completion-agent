from __future__ import annotations

import hashlib
import runpy
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.multi_goal_calibration_execution import (
    CalibrationExecutionRoot,
    CalibrationExecutionTrial,
    MultiGoalCalibrationCampaign,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = runpy.run_path(str(PROJECT_ROOT / "scripts" / "run_multi_goal_calibration_trial.py"))


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _campaign() -> MultiGoalCalibrationCampaign:
    root = CalibrationExecutionRoot(
        physical_root_sha256=_sha("physical-root"),
        record={
            "available_goal_kinds": ["advance_story", "develop_team"],
            "available_menu_sha256": _sha("menu"),
            "binding_manifest_sha256": _sha("binding"),
            "envelope_sha256": _sha("envelope"),
            "entry_index": 0,
            "policy_context_sha256": _sha("policy-context"),
            "question_sha256": _sha("question"),
            "root_lineage_id": "red-goal-root-" + "3" * 64,
            "state_sha256": _sha("state"),
        },
    )
    trial = CalibrationExecutionTrial(
        trial_ordinal=0,
        root_ordinal=0,
        selected_candidate_index=0,
        selected_goal_kind=GoalKind.ADVANCE_STORY,
        episode_id="red-multigoal-cal-test-00",
        trial_claim_sha256=_sha("trial-claim"),
    )
    return MultiGoalCalibrationCampaign(
        plan_sha256=_sha("plan"),
        campaign_id=_sha("campaign"),
        campaign_consumption_sha256=_sha("campaign-consumption"),
        source_commit="1" * 40,
        source_bundle_sha256=_sha("source"),
        freezer_runner_sha256=_sha("freezer"),
        development_runner_sha256=_sha("development-runner"),
        runtime_sha256=_sha("runtime"),
        numpy_runtime_sha256=_sha("numpy"),
        skill_manifest_sha256=_sha("skills"),
        context_plan_sha256=_sha("context-plan"),
        inventory_result_sha256=_sha("inventory"),
        private_root_identity_sha256=_sha("private-root"),
        candidate={},
        roots=(root,),
        trials=(trial,),
    )


def _readiness() -> SimpleNamespace:
    return SimpleNamespace(
        runner_sha256=_sha("execution-runner"),
        development=SimpleNamespace(
            source=SimpleNamespace(git_commit="2" * 40),
            rom_path=Path("red.gb"),
            entries=(SimpleNamespace(slot_id="slot-0"),),
            candidate=SimpleNamespace(
                catalog=SimpleNamespace(
                    catalog_sha256=_sha("catalog"),
                    entry=lambda _slot: SimpleNamespace(context_id=_sha("context")),
                )
            ),
        ),
    )


def test_reservation_claims_every_open_root_once(monkeypatch: pytest.MonkeyPatch) -> None:
    campaign = _campaign()
    readiness = _readiness()
    writes: list[dict[str, object]] = []
    available = {campaign.roots[0].physical_root_sha256}
    monkeypatch.setitem(
        SCRIPT["_reserve_all_roots"].__globals__,
        "root_claim_is_available",
        lambda _registry, identity: identity in available,
    )
    monkeypatch.setitem(
        SCRIPT["_reserve_all_roots"].__globals__,
        "write_root_claim",
        lambda _registry, **kwargs: writes.append(kwargs),
    )

    SCRIPT["_reserve_all_roots"](campaign, readiness, Path("registry"))

    assert len(writes) == 1
    assert writes[0]["root_consumption_sha256"] == (campaign.roots[0].physical_root_sha256)
    assert writes[0]["runner_sha256"] == readiness.runner_sha256


def test_reservation_accepts_an_authenticated_same_campaign_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign = _campaign()
    readiness = _readiness()
    expected = SCRIPT["_root_claim_record"](campaign, readiness)
    monkeypatch.setitem(
        SCRIPT["_verify_roots_reservable"].__globals__,
        "root_claim_is_available",
        lambda *_args: False,
    )
    monkeypatch.setitem(
        SCRIPT["_verify_roots_reservable"].__globals__,
        "read_root_claim",
        lambda *_args: {
            **expected,
            "root_consumption_sha256": campaign.roots[0].physical_root_sha256,
        },
    )

    SCRIPT["_verify_roots_reservable"](campaign, readiness, Path("registry"))

    inherited_runner = _sha("predecessor-runner")
    inherited = {
        "execution_identity_sha256": (
            campaign.root_reservation_execution_identity(inherited_runner)
        ),
        "root_consumption_sha256": campaign.roots[0].physical_root_sha256,
        "runner_sha256": inherited_runner,
        "schema": "pokemon.red.fresh-composition-root-claim.v1",
        "source_commit": "3" * 40,
    }
    monkeypatch.setitem(
        SCRIPT["_verify_roots_reservable"].__globals__,
        "read_root_claim",
        lambda *_args: inherited,
    )

    SCRIPT["_verify_roots_reservable"](campaign, readiness, Path("registry"))

    monkeypatch.setitem(
        SCRIPT["_verify_roots_reservable"].__globals__,
        "read_root_claim",
        lambda *_args: {
            **inherited,
            "execution_identity_sha256": _sha("foreign-campaign"),
        },
    )
    with pytest.raises(
        SCRIPT["RunMultiGoalCalibrationError"],
        match="closed_root_collision",
    ):
        SCRIPT["_verify_roots_reservable"](
            campaign,
            readiness,
            Path("registry"),
        )


def test_execute_reserves_campaign_and_trial_before_episode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign = _campaign()
    readiness = _readiness()
    trial = campaign.trials[0]
    root = SimpleNamespace()
    events: list[str] = []

    class _Store:
        def inspect_episode_state(self, _episode_id: str) -> SimpleNamespace:
            return SimpleNamespace(status="absent")

        def begin_episode(self, _episode_id: str) -> None:
            events.append("episode")
            raise RuntimeError("stop after ordering proof")

    globals_ = SCRIPT["_execute"].__globals__
    monkeypatch.setitem(
        globals_,
        "_load_campaign",
        lambda *_args: (Path("plan.json"), campaign, _Store()),
    )
    monkeypatch.setitem(globals_, "_selected_root", lambda *_args: (trial, root))
    monkeypatch.setitem(
        globals_["development"].__dict__,
        "_trial_claim_is_available",
        lambda *_args: True,
    )
    monkeypatch.setitem(globals_, "_protected_paths", lambda *_args: ())
    monkeypatch.setitem(globals_, "rom_adjacent_artifacts", lambda *_args: ())
    monkeypatch.setitem(
        globals_,
        "_reserve_all_roots",
        lambda *_args: events.append("roots"),
    )
    monkeypatch.setitem(
        globals_["development"].__dict__,
        "_write_trial_claim",
        lambda *_args, **_kwargs: events.append("trial"),
    )

    with pytest.raises(RuntimeError, match="ordering proof"):
        SCRIPT["_execute"](
            SimpleNamespace(trial_ordinal=0),
            readiness,
            Path("registry"),
        )

    assert events == ["roots", "trial", "episode"]


def test_preflight_never_reserves_or_claims(monkeypatch: pytest.MonkeyPatch) -> None:
    campaign = _campaign()
    readiness = _readiness()
    trial = campaign.trials[0]

    class _Store:
        def inspect_episode_state(self, _episode_id: str) -> SimpleNamespace:
            return SimpleNamespace(status="absent")

    globals_ = SCRIPT["_preflight"].__globals__
    monkeypatch.setitem(
        globals_,
        "_load_campaign",
        lambda *_args: (Path("plan.json"), campaign, _Store()),
    )
    monkeypatch.setitem(
        globals_,
        "_selected_root",
        lambda *_args: (trial, SimpleNamespace()),
    )
    monkeypatch.setitem(globals_, "_verify_roots_reservable", lambda *_args: None)
    monkeypatch.setitem(
        globals_["development"].__dict__,
        "_trial_claim_is_available",
        lambda *_args: True,
    )
    monkeypatch.setitem(globals_, "_protected_paths", lambda *_args: ())

    result = SCRIPT["_preflight"](
        SimpleNamespace(trial_ordinal=0),
        readiness,
        Path("registry"),
    )

    assert result["status"] == "trial_ready"
    assert result["controller_actions"] == 0
    assert result["emulator_frames"] == 0
    assert result["teacher_queries"] == 0


def test_failure_receipt_contains_no_private_identity() -> None:
    receipt = SCRIPT["_failure_receipt"]("campaign_authentication")

    assert receipt == {
        "controller_effects": "not_attested_on_failure",
        "failure_stage": "campaign_authentication",
        "private_path_fields": 0,
        "schema": "pokemon.red.multi-goal-calibration-trial-failure.v1",
        "status": "failed_closed",
        "teacher_queries": 0,
    }


def test_admit_authenticates_claim_before_loading_episode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign = _campaign()
    readiness = _readiness()
    trial = campaign.trials[0]
    claim_source_commit = "1" * 40
    claim_runner_sha256 = _sha("historical-execution-runner")
    execution_identity = campaign.trial_execution_identity(
        0,
        claim_runner_sha256,
    )
    events: list[str] = []

    class _Store:
        def inspect_episode_state(self, _episode_id: str) -> SimpleNamespace:
            events.append("state")
            return SimpleNamespace(status="complete")

        def open_episode(self, _episode_id: str) -> object:
            events.append("episode")
            return object()

    admitted = SimpleNamespace(
        public_dict=lambda: {"schema": "pokemon.red.multi-goal-calibration-admission.v1"}
    )
    globals_ = SCRIPT["_admit"].__globals__
    monkeypatch.setitem(
        globals_,
        "_load_campaign",
        lambda *_args: (Path("plan.json"), campaign, _Store()),
    )
    monkeypatch.setitem(
        globals_["development"].__dict__,
        "_read_trial_claim",
        lambda *_args: {
            "execution_identity_sha256": execution_identity,
            "runner_sha256": claim_runner_sha256,
            "schema": "pokemon.red.repeatable-goal-manager-trial-claim.v1",
            "source_commit": claim_source_commit,
            "trial_claim_sha256": trial.trial_claim_sha256,
        },
    )
    monkeypatch.setitem(globals_, "_protected_paths", lambda *_args: ())
    monkeypatch.setitem(globals_, "_require_unchanged", lambda *_args: None)
    monkeypatch.setitem(
        globals_,
        "_claim_source_is_published_ancestor",
        lambda predecessor, current: (
            predecessor == claim_source_commit
            and current == readiness.development.source.git_commit
        ),
    )
    monkeypatch.setitem(
        globals_,
        "_claim_runner_matches_source",
        lambda source, runner: source == claim_source_commit
        and runner == claim_runner_sha256,
    )

    def admit(_reader: object, **kwargs: object) -> SimpleNamespace:
        events.append("admit")
        assert kwargs["expected_execution_identity_sha256"] == execution_identity
        assert kwargs["expected_trial_claim_sha256"] == trial.trial_claim_sha256
        assert kwargs["expected_source_commit"] == claim_source_commit
        return admitted

    monkeypatch.setitem(globals_, "admit_multi_goal_calibration_episode", admit)

    receipt = SCRIPT["_admit"](
        SimpleNamespace(trial_ordinal=0),
        readiness,
        Path("registry"),
    )

    assert events == ["state", "episode", "admit"]
    assert receipt["status"] == "admitted"
    assert receipt["private_path_fields"] == 0


def test_admit_rejects_a_foreign_trial_claim_before_opening_episode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign = _campaign()
    readiness = _readiness()

    class _Store:
        def inspect_episode_state(self, _episode_id: str) -> SimpleNamespace:
            raise AssertionError("episode must remain unopened")

    globals_ = SCRIPT["_admit"].__globals__
    monkeypatch.setitem(
        globals_,
        "_load_campaign",
        lambda *_args: (Path("plan.json"), campaign, _Store()),
    )
    monkeypatch.setitem(
        globals_["development"].__dict__,
        "_read_trial_claim",
        lambda *_args: {"schema": "foreign"},
    )

    with pytest.raises(
        SCRIPT["RunMultiGoalCalibrationError"],
        match="trial_claim_authentication",
    ):
        SCRIPT["_admit"](
            SimpleNamespace(trial_ordinal=0),
            readiness,
            Path("registry"),
        )


def test_admit_rejects_a_non_ancestor_claim_before_opening_episode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign = _campaign()
    readiness = _readiness()
    trial = campaign.trials[0]
    execution_identity = campaign.trial_execution_identity(
        0,
        readiness.runner_sha256,
    )

    class _Store:
        def inspect_episode_state(self, _episode_id: str) -> SimpleNamespace:
            raise AssertionError("episode must remain unopened")

    globals_ = SCRIPT["_admit"].__globals__
    monkeypatch.setitem(
        globals_,
        "_load_campaign",
        lambda *_args: (Path("plan.json"), campaign, _Store()),
    )
    monkeypatch.setitem(
        globals_["development"].__dict__,
        "_read_trial_claim",
        lambda *_args: {
            "execution_identity_sha256": execution_identity,
            "runner_sha256": readiness.runner_sha256,
            "schema": "pokemon.red.repeatable-goal-manager-trial-claim.v1",
            "source_commit": "3" * 40,
            "trial_claim_sha256": trial.trial_claim_sha256,
        },
    )
    monkeypatch.setitem(
        globals_,
        "_claim_source_is_published_ancestor",
        lambda *_args: False,
    )
    monkeypatch.setitem(
        globals_,
        "_claim_runner_matches_source",
        lambda *_args: True,
    )

    with pytest.raises(
        SCRIPT["RunMultiGoalCalibrationError"],
        match="trial_claim_authentication",
    ):
        SCRIPT["_admit"](
            SimpleNamespace(trial_ordinal=0),
            readiness,
            Path("registry"),
        )


def test_claim_source_ancestry_is_checked_by_git(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[object, ...]] = []

    def run(*args: object, **kwargs: object) -> SimpleNamespace:
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", run)

    assert SCRIPT["_claim_source_is_published_ancestor"]("1" * 40, "2" * 40)
    command = calls[0][0][0]
    assert command == (
        "git",
        "merge-base",
        "--is-ancestor",
        "1" * 40,
        "2" * 40,
    )
    assert calls[0][1]["cwd"] == PROJECT_ROOT


def test_claim_runner_is_authenticated_from_historical_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = b"historical runner\n"
    runner_sha256 = hashlib.sha256(runner).hexdigest()
    calls: list[tuple[object, ...]] = []

    def run(*args: object, **kwargs: object) -> SimpleNamespace:
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout=runner)

    monkeypatch.setattr(subprocess, "run", run)

    assert SCRIPT["_claim_runner_matches_source"]("1" * 40, runner_sha256)
    command = calls[0][0][0]
    assert command == (
        "git",
        "show",
        f"{'1' * 40}:scripts/run_multi_goal_calibration_trial.py",
    )
    assert calls[0][1]["cwd"] == PROJECT_ROOT

    assert not SCRIPT["_claim_runner_matches_source"]("1" * 40, _sha("wrong"))
