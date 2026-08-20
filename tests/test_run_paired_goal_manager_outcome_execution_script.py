from __future__ import annotations

import runpy
import subprocess
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts/run_paired_goal_manager_outcome_execution.py"),
    run_name="paired_goal_manager_outcome_execution_script_test",
)


def _arms() -> list[dict[str, object]]:
    return [
        {
            "arm": "base",
            "claim_sha256": "1" * 64,
            "episode_id": "red-pair-" + "1" * 64,
            "model_canonical_sha256": "2" * 64,
        },
        {
            "arm": "candidate",
            "claim_sha256": "3" * 64,
            "episode_id": "red-pair-" + "3" * 64,
            "model_canonical_sha256": "4" * 64,
        },
    ]


def _qualified() -> SimpleNamespace:
    return SimpleNamespace(
        plan={"arms": _arms(), "root_consumption_sha256": "5" * 64},
        plan_sha256="6" * 64,
        root=object(),
        pair_execution_identity_sha256="7" * 64,
        arm_execution_identity_sha256=("8" * 64, "9" * 64),
        store=SimpleNamespace(
            inspect_episode_state=lambda _episode_id: SimpleNamespace(status="absent")
        ),
        screen_plan_path=Path("screen.json"),
    )


def _readiness() -> SimpleNamespace:
    return SimpleNamespace(
        runner_sha256="a" * 64,
        paired=SimpleNamespace(
            development=SimpleNamespace(
                source=SimpleNamespace(git_commit="b" * 40),
                candidate=SimpleNamespace(model=object()),
            ),
            candidate_model=object(),
        ),
    )


def test_parser_separates_preflight_execution_and_admission() -> None:
    parser = SCRIPT["_parser"]()
    mode = next(action for action in parser._actions if action.dest == "mode")
    options = {option for action in parser._actions for option in action.option_strings}

    assert tuple(mode.choices) == ("preflight", "execute", "admit")
    assert "--expected-pair-execution-identity-sha256" in options
    assert "--arm" not in options


def test_command_line_entry_point_executes_the_runner() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(
                PROJECT_ROOT
                / "scripts/run_paired_goal_manager_outcome_execution.py"
            ),
            "--help",
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--expected-pair-execution-identity-sha256" in result.stdout


def test_pair_claim_precedes_both_arm_claims_under_one_exclusive_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claim_pair = SCRIPT["_claim_pair"]
    globals_ = claim_pair.__globals__
    events: list[str] = []
    monkeypatch.setitem(globals_, "open_fixed_account_claim_registry", lambda: object())
    monkeypatch.setitem(
        globals_,
        "fixed_account_claim_registry_lease",
        lambda _registry, *, exclusive: (
            events.append(f"lease:{exclusive}") or nullcontext()
        ),
    )
    monkeypatch.setitem(globals_, "root_claim_is_available", lambda *_args: True)
    monkeypatch.setitem(
        globals_,
        "write_root_claim",
        lambda *_args, **_kwargs: events.append("root"),
    )
    development = globals_["development"]
    monkeypatch.setattr(development, "_trial_claim_is_available", lambda *_args: True)
    monkeypatch.setattr(
        development,
        "_write_trial_claim",
        lambda *_args, **_kwargs: events.append("arm"),
    )

    claim_pair(_readiness(), _qualified())

    assert events == ["lease:True", "root", "arm", "arm"]


def test_pair_execution_has_no_arm_selector_and_runs_base_then_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execute = SCRIPT["_execute_pair"]
    globals_ = execute.__globals__
    events: list[str] = []
    monkeypatch.setitem(
        globals_,
        "_claim_pair",
        lambda *_args: events.append("claimed_pair_and_both_arms"),
    )

    def arm_runner(
        _readiness: object,
        _qualified: object,
        *,
        arm: dict[str, object],
        model: object,
        arm_execution_identity_sha256: str,
    ) -> dict[str, object]:
        del model, arm_execution_identity_sha256
        name = str(arm["arm"])
        events.append(name)
        return {"arm": name, "status": "durable_terminal"}

    monkeypatch.setitem(globals_, "_execute_arm", arm_runner)

    result = execute(_readiness(), _qualified())

    assert events == ["claimed_pair_and_both_arms", "base", "candidate"]
    assert [arm["arm"] for arm in result["arms"]] == ["base", "candidate"]


def test_stable_root_allows_only_source_bound_assignment_rollover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validate = SCRIPT["_validate_stable_root"]
    globals_ = validate.__globals__
    frozen = {
        "assignment_id": "1" * 64,
        "root_lineage_id": "red-goal-root-" + "1" * 64,
        "focus_kind": "acquire_species",
        "available_goal_kinds": ["acquire_species", "explore"],
        "state_sha256": "2" * 64,
        "question_sha256": "3" * 64,
    }
    current = {
        **frozen,
        "assignment_id": "4" * 64,
        "root_lineage_id": "red-goal-root-" + "4" * 64,
    }
    inspected = SimpleNamespace(
        available_goal_kinds=("acquire_species", "explore")
    )
    monkeypatch.setattr(globals_["development"], "_private_root_record", lambda _root: current)

    validate(inspected, frozen)
    current["question_sha256"] = "5" * 64
    with pytest.raises(SCRIPT["PairedExecutionRunError"], match="screen_root_drift"):
        validate(inspected, frozen)


def test_public_preflight_is_zero_action_and_leaves_identity_unclaimed() -> None:
    readiness = SimpleNamespace(
        runner_sha256="a" * 64,
        paired=SimpleNamespace(
            development=SimpleNamespace(source=SimpleNamespace(git_commit="b" * 40))
        ),
    )
    qualified = _qualified()
    qualified.plan["screen_id"] = "c" * 64

    result = SCRIPT["_public_preflight"](readiness, qualified)

    assert result["status"] == "paired_execution_ready_without_prediction_or_action"
    assert result["pair_identity_available"] is True
    assert result["model_predictions"] == 0
    assert result["controller_actions"] == 0
    assert result["game_executions"] == 0
    assert result["maximum_decisions_per_arm"] == 3


def test_failure_receipt_never_claims_protected_access_absence(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    main = SCRIPT["main"]
    globals_ = main.__globals__
    monkeypatch.setitem(
        globals_,
        "_parser",
        lambda: SimpleNamespace(
            parse_args=lambda _argv: SimpleNamespace(mode="preflight")
        ),
    )
    monkeypatch.setitem(
        globals_,
        "_readiness",
        lambda _args: (_ for _ in ()).throw(OSError("/private/protected/input")),
    )

    assert main(["--mode", "preflight"]) == 1

    receipt = __import__("json").loads(capsys.readouterr().out)
    assert receipt["protected_access_status"] == "not_attested_on_failure"
    assert "sealed_red_accesses" not in receipt
    assert "crystal_accesses" not in receipt


def test_execution_failure_never_claims_zero_effects(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    main = SCRIPT["main"]
    globals_ = main.__globals__
    monkeypatch.setitem(
        globals_,
        "_parser",
        lambda: SimpleNamespace(
            parse_args=lambda _argv: SimpleNamespace(mode="execute")
        ),
    )
    monkeypatch.setitem(
        globals_,
        "_readiness",
        lambda _args: (_ for _ in ()).throw(OSError("late execution failure")),
    )

    assert main(["--mode", "execute"]) == 1

    receipt = __import__("json").loads(capsys.readouterr().out)
    assert receipt["status"] == "failed_closed_execution_state_retained"
    assert receipt["execution_effects_status"] == "not_attested_on_failure"
    assert "model_predictions" not in receipt
    assert "controller_actions" not in receipt


def test_failure_stage_never_echoes_private_exception_text() -> None:
    sanitize = SCRIPT["_sanitized_failure_stage"]

    assert sanitize(OSError("/private/secret/root")) == "paired_execution_internal"
    assert sanitize(SCRIPT["PairedExecutionRunError"]("screen_root_drift")) == (
        "screen_root_drift"
    )


def test_admission_summary_never_calls_noncomposition_episodes_composition() -> None:
    source = (
        PROJECT_ROOT / "scripts/run_paired_goal_manager_outcome_execution.py"
    ).read_text(encoding="utf-8")

    assert '"composition_episodes_added"' not in source
    assert '"development_episodes_admitted"' in source
    assert '"verified_composition_episodes_added"' in source
