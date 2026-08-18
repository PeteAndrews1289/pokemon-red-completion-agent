from __future__ import annotations

import json
import runpy
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind
from pokemon_red_completion.goal_manager_composition_qualification import (
    root_consumption_sha256,
)
from pokemon_red_completion.provenance import canonical_sha256

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts/run_develop_team_causal_goal_outcome.py"
SCRIPT = runpy.run_path(
    str(SCRIPT_PATH),
    run_name="develop_team_causal_goal_outcome_script_test",
)


def _readiness() -> SimpleNamespace:
    base = SimpleNamespace(
        source=SimpleNamespace(git_commit="a" * 40),
        source_bundle_sha256="b" * 64,
        runtime=SimpleNamespace(sha256="c" * 64),
        numpy_runtime_sha256="d" * 64,
        skill_manifest_sha256="e" * 64,
        context_plan_sha256="f" * 64,
    )
    paired = SimpleNamespace(
        development=base,
        candidate_model_canonical_sha256="1" * 64,
        prior_campaign_sha256=("4" * 64, "5" * 64),
        prior_campaigns=(),
    )
    return SimpleNamespace(paired=paired, runner_sha256="2" * 64)


def _gate() -> SimpleNamespace:
    return SimpleNamespace(
        bindings={},
        manifest_sha256="8" * 64,
        freeze_manifest_sha256="8" * 64,
    )


def _plan() -> dict[str, object]:
    state = "6" * 64
    envelope = "7" * 64
    root = {
        "partition": "train",
        "root_consumption_sha256": root_consumption_sha256(
            state_sha256=state,
            envelope_sha256=envelope,
        ),
        "root": {
            "entry_index": 3,
            "focus_kind": GoalKind.DEVELOP_TEAM.value,
            "state_sha256": state,
            "envelope_sha256": envelope,
        },
    }
    trial = {
        "maximum_decisions": 1,
        "partition": "train",
        "root_index": 0,
        "seed": SCRIPT["TRIAL_SEED"],
        "trial_index": 0,
    }
    identity = {
        "base_model_canonical_sha256": "1" * 64,
        "context_plan_sha256": "f" * 64,
        "freeze_execution_manifest_sha256": "8" * 64,
        "lane_consumption_sha256": SCRIPT["LANE_CONSUMPTION_SHA256"],
        "numpy_runtime_sha256": "d" * 64,
        "outcome_objective": SCRIPT["development"].goal_manager_development_outcome_objective(),
        "private_root_identity_sha256": "3" * 64,
        "prior_campaign_sha256": ["4" * 64, "5" * 64],
        "roots": [root],
        "runner_sha256": "2" * 64,
        "runtime_sha256": "c" * 64,
        "schema": SCRIPT["CAMPAIGN_SCHEMA"],
        "skill_manifest_sha256": "e" * 64,
        "source_bundle_sha256": "b" * 64,
        "source_commit": "a" * 40,
        "trials": [trial],
    }
    campaign_id = canonical_sha256(identity)
    return {
        **identity,
        "campaign_id": campaign_id,
        "campaign_consumption_sha256": canonical_sha256(
            {
                "campaign_id": campaign_id,
                "schema": SCRIPT["CAMPAIGN_CONSUMPTION_SCHEMA"],
            }
        ),
        "trials": [
            {
                **trial,
                "episode_id": f"red-develop-team-causal-{campaign_id[:32]}-00",
                "trial_claim_sha256": canonical_sha256(
                    {
                        "campaign_id": campaign_id,
                        "schema": SCRIPT["TRIAL_CLAIM_SCHEMA"],
                        "trial_index": 0,
                    }
                ),
            }
        ],
    }


def _argv(private_marker: str = "/private/secret") -> list[str]:
    return [
        "--mode",
        "freeze",
        "--execution-manifest",
        ".public-execution-manifests/freeze.json",
        "--expected-execution-manifest-sha256",
        "8" * 64,
        "--context-plan",
        f"{private_marker}/context-plan.json",
        "--context-catalog",
        f"{private_marker}/catalog.json",
        "--base-model",
        f"{private_marker}/base-model.json",
        "--base-fit-summary",
        f"{private_marker}/base-fit.json",
        "--candidate-model",
        f"{private_marker}/candidate-model.json",
        "--candidate-fit-summary",
        f"{private_marker}/candidate-fit.json",
        "--fit-result-receipt",
        f"{private_marker}/fit-result.json",
        "--prior-campaign",
        f"{private_marker}/prior.json",
        "--expected-prior-campaign-sha256",
        "4" * 64,
        "--expected-fit-result-receipt-sha256",
        "5" * 64,
        "--expected-context-plan-sha256",
        "6" * 64,
        "--rom",
        f"{private_marker}/red.gb",
        "--private-root",
        f"{private_marker}/artifacts",
        "--campaign-plan",
        f"{private_marker}/campaign.json",
    ]


def test_public_manifest_failure_stops_before_readiness_and_hides_paths(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[str] = []
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "_public_gate",
        lambda args: (_ for _ in ()).throw(RuntimeError("/private/secret")),
    )
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "_readiness",
        lambda *args: calls.append("private readiness"),
    )

    assert SCRIPT["main"](_argv()) == 1
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result["failure_stage"] == "public_manifest_authentication"
    assert "/private/secret" not in output
    assert result["development_labels_opened"] == 0
    assert result["teacher_queries"] == 0
    assert result["model_fits"] == 0
    assert calls == []


def test_invalid_argument_never_prints_private_value_or_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    argv = _argv()
    argv[1] = "/private/secret-invalid-mode"

    assert SCRIPT["main"](argv) == 1
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["failure_stage"] == "argument_authentication"
    assert "/private/secret" not in captured.out
    assert captured.err == ""


def test_public_gate_uses_exact_reviewed_dependency_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, object] = {}
    bindings = {
        "source_commit": "a" * 40,
        "source_bundle_sha256": "b" * 64,
        "runner_sha256": "c" * 64,
    }

    def current_bindings(**kwargs):  # type: ignore[no-untyped-def]
        calls["bindings"] = kwargs
        return bindings

    def invocation(**kwargs):  # type: ignore[no-untyped-def]
        calls["invocation"] = kwargs
        return {"invocation": True}

    monkeypatch.setattr(
        SCRIPT["manifest_freezer"],
        "_current_public_bindings",
        current_bindings,
    )
    monkeypatch.setattr(
        SCRIPT["public_manifest"],
        "public_execution_invocation",
        invocation,
    )
    monkeypatch.setattr(
        SCRIPT["public_manifest"],
        "read_public_manifest",
        lambda *args, **kwargs: b"manifest\n",
    )
    monkeypatch.setattr(
        SCRIPT["public_manifest"],
        "authenticate_public_execution_manifest",
        lambda *args, **kwargs: calls.setdefault("authenticated", kwargs),
    )
    args = SCRIPT["_parser"]().parse_args(_argv())

    gate = SCRIPT["_public_gate"](args)

    assert calls["bindings"] == {
        "lane_id": SCRIPT["LANE_ID"],
        "runner": SCRIPT["RUNNER_RELATIVE"],
        "dependencies": list(SCRIPT["PUBLIC_DEPENDENCIES"]),
    }
    invocation = calls["invocation"]
    assert isinstance(invocation, dict)
    assert invocation["operation"] == "freeze"
    assert invocation["expected_campaign_sha256"] is None
    assert gate.manifest_sha256 == "8" * 64


def test_readiness_derives_every_public_attestation_from_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bindings = {
        "source_commit": "a" * 40,
        "source_bundle_sha256": "b" * 64,
        "runner_sha256": "c" * 64,
        "multiroot_runner_sha256": "d" * 64,
        "paired_runner_sha256": "e" * 64,
        "development_runner_sha256": "f" * 64,
        "runtime_sha256": "1" * 64,
        "numpy_runtime_sha256": "2" * 64,
        "skill_manifest_sha256": "3" * 64,
    }
    captured: list[object] = []
    inherited = SimpleNamespace(paired=SimpleNamespace())
    monkeypatch.setattr(
        SCRIPT["multiroot"],
        "_readiness",
        lambda args: captured.append(args) or inherited,
    )
    args = SCRIPT["_parser"]().parse_args(_argv())

    readiness = SCRIPT["_readiness"](
        args,
        SimpleNamespace(
            bindings=bindings,
            manifest_sha256="8" * 64,
            freeze_manifest_sha256=None,
        ),
    )

    used = captured[0]
    assert used.expected_source_commit == bindings["source_commit"]
    assert used.expected_runner_sha256 == bindings["multiroot_runner_sha256"]
    assert used.expected_paired_runner_sha256 == bindings["paired_runner_sha256"]
    assert used.expected_development_runner_sha256 == bindings["development_runner_sha256"]
    assert used.expected_runtime_sha256 == bindings["runtime_sha256"]
    assert readiness.runner_sha256 == bindings["runner_sha256"]


def test_selects_only_first_static_unused_train_develop_team_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entries = tuple(SimpleNamespace(slot_id=f"slot-{index}") for index in range(5))
    assignments = (
        _assignment("validation", GoalKind.DEVELOP_TEAM, 0),
        _assignment("train", GoalKind.MANAGE_STORAGE, 1),
        _assignment("train", GoalKind.DEVELOP_TEAM, 2),
        _assignment("train", GoalKind.DEVELOP_TEAM, 3),
        _assignment("train", GoalKind.DEVELOP_TEAM, 4),
    )
    base = SimpleNamespace(
        entries=entries,
        candidate=SimpleNamespace(
            registry=SimpleNamespace(
                assignment=lambda slot: assignments[int(slot.rsplit("-", 1)[1])]
            )
        ),
    )
    readiness = SimpleNamespace(paired=SimpleNamespace(development=base, prior_campaigns=()))
    selected = _root(assignments[2])
    inspected: list[int] = []
    monkeypatch.setattr(SCRIPT["development"], "_historical_root_is_open", lambda *a: True)

    def inspect(*args, entry_index: int, **kwargs):  # type: ignore[no-untyped-def]
        inspected.append(entry_index)
        return selected

    monkeypatch.setattr(SCRIPT["development"], "_inspect_root", inspect)

    assert SCRIPT["_select_first_develop_team_root"](readiness, Path("claims")) is selected
    assert inspected == [2]


def test_never_substitutes_after_first_static_candidate_fails_inspection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entries = (SimpleNamespace(slot_id="slot-0"), SimpleNamespace(slot_id="slot-1"))
    assignments = (
        _assignment("train", GoalKind.DEVELOP_TEAM, 0),
        _assignment("train", GoalKind.DEVELOP_TEAM, 1),
    )
    base = SimpleNamespace(
        entries=entries,
        candidate=SimpleNamespace(
            registry=SimpleNamespace(
                assignment=lambda slot: assignments[int(slot.rsplit("-", 1)[1])]
            )
        ),
    )
    readiness = SimpleNamespace(paired=SimpleNamespace(development=base, prior_campaigns=()))
    inspected: list[int] = []
    monkeypatch.setattr(SCRIPT["development"], "_historical_root_is_open", lambda *a: True)
    monkeypatch.setattr(
        SCRIPT["development"],
        "_inspect_root",
        lambda *args, entry_index, **kwargs: inspected.append(entry_index),
    )

    with pytest.raises(
        SCRIPT["DevelopTeamCausalRunError"],
        match="action_free_develop_team_root_inventory",
    ):
        SCRIPT["_select_first_develop_team_root"](readiness, Path("claims"))
    assert inspected == [0]


@pytest.mark.parametrize(
    "available",
    (
        (GoalKind.RESTORE_TEAM.value,),
        (GoalKind.DEVELOP_TEAM.value, GoalKind.EVOLVE_SPECIES.value),
    ),
)
def test_root_requires_full_multi_choice_develop_menu_without_evolution(
    available: tuple[str, ...],
) -> None:
    assert not SCRIPT["_root_is_eligible"](
        _root(_assignment("train", GoalKind.DEVELOP_TEAM, 0), available=available),
        set(),
    )


def test_plan_is_exactly_one_train_develop_team_decision() -> None:
    SCRIPT["_validate_plan"](
        _readiness(),
        _plan(),
        private_root_identity="3" * 64,
        expected_freeze_execution_manifest_sha256="8" * 64,
    )
    for field, value in (
        ("focus_kind", GoalKind.ACQUIRE_SPECIES.value),
        ("maximum_decisions", 2),
    ):
        changed = deepcopy(_plan())
        roots = changed["roots"]
        trials = changed["trials"]
        assert isinstance(roots, list) and isinstance(roots[0], dict)
        assert isinstance(trials, list) and isinstance(trials[0], dict)
        if field == "focus_kind":
            root = roots[0]["root"]
            assert isinstance(root, dict)
            root[field] = value
        else:
            trials[0][field] = value
        with pytest.raises(SCRIPT["DevelopTeamCausalRunError"]):
            SCRIPT["_validate_plan"](
                _readiness(),
                changed,
                private_root_identity="3" * 64,
                expected_freeze_execution_manifest_sha256="8" * 64,
            )


def test_nonfreeze_manifest_must_bind_exact_freeze_manifest_provenance() -> None:
    with pytest.raises(SCRIPT["DevelopTeamCausalRunError"], match="campaign_authentication"):
        SCRIPT["_validate_plan"](
            _readiness(),
            _plan(),
            private_root_identity="3" * 64,
            expected_freeze_execution_manifest_sha256="0" * 64,
        )


def test_lane_claim_is_written_before_one_nonresumable_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    qualified = SimpleNamespace(plan={}, plan_sha256="9" * 64)
    monkeypatch.setitem(
        SCRIPT["_execute"].__globals__,
        "open_fixed_account_claim_registry",
        lambda: Path("claims"),
    )
    monkeypatch.setitem(
        SCRIPT["_execute"].__globals__,
        "fixed_account_claim_registry_lease",
        lambda *args, **kwargs: nullcontext(),
    )
    monkeypatch.setitem(
        SCRIPT["_execute"].__globals__,
        "root_claim_is_available",
        lambda *args: True,
    )
    monkeypatch.setitem(
        SCRIPT["_execute"].__globals__,
        "write_root_claim",
        lambda *args, **kwargs: calls.append("lane claim"),
    )
    monkeypatch.setattr(
        SCRIPT["multiroot"],
        "_campaign_execution_identity",
        lambda *args: "a" * 64,
    )

    def execute(*args, resume: bool):  # type: ignore[no-untyped-def]
        assert calls == ["lane claim"]
        assert resume is False
        calls.append("prediction execution")
        return {
            "trials": [{"status": "complete"}],
            "complete_trials": 1,
            "failed_trials": 0,
            "campaign_terminal_sha256": "b" * 64,
        }

    monkeypatch.setattr(SCRIPT["multiroot"], "_execute", execute)

    result = SCRIPT["_execute"](_readiness(), _gate(), qualified)

    assert calls == ["lane claim", "prediction execution"]
    assert result["causal_train_examples_added"] == 0
    assert result["development_labels_opened"] == 0


def test_lane_claim_failure_prevents_prediction_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    globals_ = SCRIPT["_execute"].__globals__
    monkeypatch.setitem(globals_, "open_fixed_account_claim_registry", lambda: Path("claims"))
    monkeypatch.setitem(
        globals_,
        "fixed_account_claim_registry_lease",
        lambda *args, **kwargs: nullcontext(),
    )
    monkeypatch.setitem(globals_, "root_claim_is_available", lambda *args: True)
    monkeypatch.setitem(
        globals_,
        "write_root_claim",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("private path")),
    )
    monkeypatch.setattr(
        SCRIPT["multiroot"],
        "_campaign_execution_identity",
        lambda *args: "a" * 64,
    )
    monkeypatch.setattr(
        SCRIPT["multiroot"],
        "_execute",
        lambda *args, **kwargs: pytest.fail("prediction ran without durable lane claim"),
    )

    with pytest.raises(
        SCRIPT["DevelopTeamCausalRunError"],
        match="lane_claim_before_prediction",
    ):
        SCRIPT["_execute"](
            _readiness(),
            _gate(),
            SimpleNamespace(plan={}, plan_sha256="9" * 64),
        )


def test_unknown_inherited_trial_failure_is_named_and_retained(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    globals_ = SCRIPT["_execute"].__globals__
    monkeypatch.setitem(globals_, "open_fixed_account_claim_registry", lambda: Path("claims"))
    monkeypatch.setitem(
        globals_,
        "fixed_account_claim_registry_lease",
        lambda *args, **kwargs: nullcontext(),
    )
    monkeypatch.setitem(globals_, "root_claim_is_available", lambda *args: True)
    monkeypatch.setitem(globals_, "write_root_claim", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        SCRIPT["multiroot"],
        "_campaign_execution_identity",
        lambda *args: "a" * 64,
    )
    monkeypatch.setattr(
        SCRIPT["multiroot"],
        "_execute",
        lambda *args, **kwargs: {
            "trials": [
                {
                    "status": "failed_terminal_retained",
                    "artifact_state": "failed",
                    "failure_stage": "unexpected_failure",
                }
            ],
            "complete_trials": 0,
            "failed_trials": 1,
            "campaign_terminal_sha256": "b" * 64,
        },
    )

    result = SCRIPT["_execute"](
        _readiness(),
        _gate(),
        SimpleNamespace(plan={}, plan_sha256="9" * 64),
    )

    assert result["trial"]["artifact_state"] == "failed"
    assert result["trial"]["failure_stage"] == "develop_team_execution"


@pytest.mark.parametrize(
    ("outcome", "reward", "positive", "negative", "causal"),
    (
        (GoalDecisionOutcome.SUCCEEDED, 1.0, 1, 0, 1),
        (GoalDecisionOutcome.FAILED, -1.0, 0, 1, 1),
        (GoalDecisionOutcome.INTERRUPTED, None, 0, 0, 0),
    ),
)
def test_admission_accepts_only_settled_positive_or_negative_train_target(
    monkeypatch: pytest.MonkeyPatch,
    outcome: GoalDecisionOutcome,
    reward: float | None,
    positive: int,
    negative: int,
    causal: int,
) -> None:
    example = SimpleNamespace(
        selected_candidate_index=2,
        selected_kind=GoalKind.RESTORE_TEAM,
        outcome_status=outcome,
    )
    targets = (
        () if reward is None else (SimpleNamespace(selected_candidate_index=2, reward=reward),)
    )
    admitted = SimpleNamespace(
        verified_outcomes=1,
        dataset=SimpleNamespace(examples=(example,)),
        targets=targets,
    )
    partitions: list[str] = []
    _admission_mocks(monkeypatch, admitted, partitions)

    result = SCRIPT["_admit"](
        _readiness(),
        _gate(),
        SimpleNamespace(plan={}, plan_sha256="9" * 64),
    )

    assert partitions == ["train"]
    assert result["settled_positive_examples_added"] == positive
    assert result["settled_negative_examples_added"] == negative
    assert result["selected_goal_kind"] == GoalKind.RESTORE_TEAM.value
    if causal:
        assert (
            result["status"]
            == "single_train_causal_outcome_admitted_from_develop_team_focused_root"
        )
    assert result["causal_train_examples_added"] == causal
    assert result["atomic_goal_episodes_added"] == causal
    assert result["development_episode_attempts_added"] == 0
    assert result["verified_outcome_examples_added"] == 0
    assert result["model_fits_added"] == 0
    assert result["transfer_results_added"] == 0


def test_admission_rejects_reward_or_selected_index_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admitted = SimpleNamespace(
        verified_outcomes=1,
        dataset=SimpleNamespace(
            examples=(
                SimpleNamespace(
                    selected_candidate_index=2,
                    selected_kind=GoalKind.RESTORE_TEAM,
                    outcome_status=GoalDecisionOutcome.SUCCEEDED,
                ),
            )
        ),
        targets=(SimpleNamespace(selected_candidate_index=1, reward=-1.0),),
    )
    _admission_mocks(monkeypatch, admitted, [])

    with pytest.raises(SCRIPT["DevelopTeamCausalRunError"], match="train_outcome_admission"):
        SCRIPT["_admit"](
            _readiness(),
            _gate(),
            SimpleNamespace(plan={}, plan_sha256="9" * 64),
        )


def test_failed_terminal_is_retained_but_never_counted_as_training(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    globals_ = SCRIPT["_admit"].__globals__
    monkeypatch.setitem(globals_, "open_fixed_account_claim_registry", lambda: Path("claims"))
    monkeypatch.setitem(globals_, "root_claim_is_available", lambda *args: False)
    monkeypatch.setitem(globals_, "read_root_claim", lambda *args: {})
    monkeypatch.setitem(globals_, "_expected_lane_claim", lambda *args: {})
    monkeypatch.setattr(SCRIPT["multiroot"], "_require_campaign_terminal", lambda *args: None)
    monkeypatch.setattr(
        SCRIPT["multiroot"],
        "_load_partition",
        lambda *args, partition: ((), {"failed": 1}),
    )

    result = SCRIPT["_admit"](
        _readiness(),
        _gate(),
        SimpleNamespace(plan={}, plan_sha256="9" * 64),
    )

    assert result["invalid_trial_states"] == {"failed": 1}
    assert result["causal_train_examples_added"] == 0
    assert result["atomic_goal_episodes_added"] == 0
    assert result["selected_goal_kind"] is None


def test_runner_never_reuses_retired_acquisition_lane() -> None:
    source = SCRIPT_PATH.read_text()
    assert "run_single_root_causal_goal_outcome" not in source
    assert SCRIPT["LANE_ID"] == "first-develop-team-causal-goal-outcome-v1"
    assert (
        GoalKind.ACQUIRE_SPECIES.value
        not in SCRIPT["_zero_result"](
            schema="schema",
            status="status",
            gate=_gate(),
            campaign_plan_sha256="9" * 64,
        ).values()
    )


def _assignment(partition: str, kind: GoalKind, index: int) -> SimpleNamespace:
    return SimpleNamespace(
        partition=partition,
        focus_kind=kind,
        root_lineage_id=f"red-goal-root-{index:064x}",
        assignment_id=f"{index:064x}",
    )


def _root(
    assignment: SimpleNamespace,
    *,
    available: tuple[str, ...] = (
        GoalKind.DEVELOP_TEAM.value,
        GoalKind.RESTORE_TEAM.value,
        GoalKind.MANAGE_STORAGE.value,
    ),
) -> SimpleNamespace:
    return SimpleNamespace(
        assignment=assignment,
        capture=SimpleNamespace(state_sha256="a" * 64, envelope_sha256="b" * 64),
        available_goal_kinds=available,
    )


def _admission_mocks(
    monkeypatch: pytest.MonkeyPatch,
    admitted: SimpleNamespace,
    partitions: list[str],
) -> None:
    globals_ = SCRIPT["_admit"].__globals__
    monkeypatch.setitem(globals_, "open_fixed_account_claim_registry", lambda: Path("claims"))
    monkeypatch.setitem(globals_, "root_claim_is_available", lambda *args: False)
    monkeypatch.setitem(globals_, "read_root_claim", lambda *args: {})
    monkeypatch.setitem(globals_, "_expected_lane_claim", lambda *args: {})
    monkeypatch.setattr(SCRIPT["multiroot"], "_require_campaign_terminal", lambda *args: None)

    def load(*args, partition: str):  # type: ignore[no-untyped-def]
        partitions.append(partition)
        return (admitted,), {}

    monkeypatch.setattr(SCRIPT["multiroot"], "_load_partition", load)
