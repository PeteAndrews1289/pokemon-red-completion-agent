#!/usr/bin/env python3
"""Authenticate the strategic-ranker portable proof and apply frozen gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
from collections.abc import Mapping
from pathlib import Path

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "runtime", "model", "portable", "envelope"):
        parser.add_argument(f"--{name}", nargs=2, metavar=("PATH", "SHA256"), required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    plan = _authenticated_json(*args.plan, subject="portable plan")
    runtime = _authenticated_json(*args.runtime, subject="runtime qualification")
    portable = _authenticated_json(*args.portable, subject="portable report")
    envelope = _authenticated_json(*args.envelope, subject="terminal envelope")
    model_file_sha256 = _regular_file_sha256(Path(args.model[0]), subject="candidate model")
    if model_file_sha256 != args.model[1]:
        parser.error("candidate model failed authentication")
    state_sha256 = _regular_file_sha256(args.state, subject="terminal state")

    _require_schema(plan, "pokemon-training-candidate-portable-plan-v1")
    _require_schema(runtime, "pokemon-training-candidate-runtime-receipt-v1")
    _require_schema(portable, "pokemon-model-selected-objective-execution-v3")
    _require_schema(envelope, "pokemon-private-captured-progress-v1")

    planned_root = _mapping(plan.get("root"), "planned root")
    planned_models = _mapping(plan.get("models"), "planned models")
    planned_candidate = _mapping(
        planned_models.get("training_candidate"), "planned candidate model"
    )
    capture = _mapping(portable.get("capture"), "portable capture")
    source = _mapping(portable.get("source"), "portable source")
    before = _mapping(portable.get("before"), "portable before state")
    after = _mapping(portable.get("after"), "portable after state")
    assistance = _mapping(portable.get("assistance"), "portable assistance")
    candidate = _mapping(
        portable.get("training_candidate_control"), "portable candidate control"
    )
    steps = portable.get("decisions_and_executions")
    if not isinstance(steps, list) or len(steps) != 1 or not isinstance(steps[0], Mapping):
        parser.error("portable proof must contain exactly one objective execution")
    step = steps[0]
    evidence = _mapping(step.get("skill_evidence"), "portable skill evidence")
    development = _mapping(evidence.get("team_development"), "team development")
    terminal = _mapping(evidence.get("terminal"), "terminal party")
    levels = _integer_list(development.get("levels"), "terminal party levels")
    party_hp = _integer_list(terminal.get("party_hp"), "terminal party HP")
    party_max_hp = _integer_list(terminal.get("party_max_hp"), "terminal maximum HP")
    party_status = _integer_list(terminal.get("party_status"), "terminal party status")

    controlled = candidate.get("controlled_decisions")
    disagreements = candidate.get("disagreements")
    checks = {
        "qualified_runtime_chain": _check(
            plan.get("runtime_qualification_receipt_sha256") == args.runtime[1]
            and runtime.get("status") == "runtime_qualified"
            and runtime.get("portable_training_loop_may_start") is True
        ),
        "published_clean_source": _check(
            source.get("worktree_dirty") is False
            and isinstance(source.get("git_commit"), str)
            and len(str(source.get("git_commit"))) == 40
        ),
        "root_identity": _check(
            capture.get("state_sha256") == planned_root.get("state_sha256")
            and capture.get("checkpoint_id") == planned_root.get("checkpoint_id")
        ),
        "model_identity": _check(
            model_file_sha256 == planned_candidate.get("model_file_sha256")
            and model_file_sha256 == runtime.get("candidate_model_file_sha256")
            and candidate.get("model_file_sha256") == model_file_sha256
            and candidate.get("model_sha256")
            == planned_candidate.get("canonical_model_sha256")
            == runtime.get("candidate_model_canonical_sha256")
        ),
        "live_candidate_authority": _check(
            candidate.get("authority_choice_kinds") == ["trainee", "venue"]
            and candidate.get("model_had_execution_authority") is True
            and candidate.get("teacher_fallback_on_model_disagreement") is False
            and type(controlled) is int  # noqa: E721
            and controlled >= 100
            and controlled == candidate.get("decisions")
            and type(disagreements) is int  # noqa: E721
            and disagreements >= 1
        ),
        "objective_boundary": _check(
            portable.get("status") == "ok"
            and before.get("available_objectives") == ["defeat_blaine"]
            and step.get("objective_id") == "defeat_blaine"
            and step.get("kind") == "skill_completed"
            and evidence.get("objective") == "defeat_blaine"
            and evidence.get("status") == "ok"
        ),
        "bounded_development": _check(
            development.get("final_forms_complete") is True
            and len(levels) == 6
            and min(levels, default=0) >= 55
            and _bounded_integer(development.get("battles"), maximum=1900)
            and _bounded_integer(development.get("healing_trips"), maximum=1150)
        ),
        "fresh_completion_observation": _check(
            "badge:volcano" in _string_list(after.get("facts_added"))
            and "defeat_blaine" in _string_list(after.get("completed_objectives"))
            and "defeat_giovanni" in _string_list(after.get("available_objectives"))
        ),
        "healthy_terminal_party": _check(
            len(party_hp) == len(party_max_hp) == len(party_status) == 6
            and party_hp == party_max_hp
            and party_hp != []
            and party_status == [0] * 6
        ),
        "assistance_boundary": _check(
            assistance.get("teacher_fallbacks") == 0
            and assistance.get("expected_route_label_provided") is False
            and assistance.get("mechanic_execution") == "teacher_authored_bounded_skill"
            and assistance.get("branching_model_decisions") == 0
            and assistance.get("singleton_dispatches") == 1
        ),
        "terminal_state_chain": _check(
            envelope.get("state_sha256") == state_sha256
            and envelope.get("checkpoint_id") == "portable_loop_defeat_blaine_terminal"
            and "defeat_blaine" in _string_list(envelope.get("verified_objective_ids"))
        ),
    }
    eligible = all(bool(value["passed"]) for value in checks.values())
    payload = {
        "schema": "pokemon-training-candidate-portable-gate-evaluation-v1",
        "plan_sha256": args.plan[1],
        "runtime_qualification_sha256": args.runtime[1],
        "candidate_model_file_sha256": model_file_sha256,
        "portable_report_sha256": args.portable[1],
        "terminal_state_sha256": state_sha256,
        "terminal_envelope_sha256": args.envelope[1],
        "observed": {
            "controlled_decisions": controlled,
            "model_teacher_disagreements": disagreements,
            "genuine_accuracy": candidate.get("genuine_accuracy"),
            "team_development_battles": development.get("battles"),
            "team_development_healing_trips": development.get("healing_trips"),
            "final_party_levels": levels,
        },
        "checks": checks,
        "portable_strategic_authority_eligible": eligible,
        "clean_start_evaluation_eligible": False,
        "branching_objective_evidence_eligible": False,
        "cross_title_transfer_eligible": False,
        "end_to_end_learned_gameplay_eligible": False,
        "promotion_eligible": False,
    }
    _atomic_json(args.out, payload)
    print(json.dumps({"portable_strategic_authority_eligible": eligible}))
    return 0 if eligible else 2


def _authenticated_json(path: str, digest: str, *, subject: str) -> Mapping[str, object]:
    if _SHA256.fullmatch(digest) is None:
        raise ValueError(f"{subject} digest is invalid")
    source = Path(path)
    try:
        metadata = source.lstat()
        raw = source.read_bytes()
    except OSError as error:
        raise ValueError(f"{subject} cannot be read") from error
    if source.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{subject} must be a regular file")
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError(f"{subject} failed authentication")
    try:
        return _mapping(json.loads(raw), subject)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{subject} is invalid JSON") from error


def _regular_file_sha256(path: Path, *, subject: str) -> str:
    try:
        metadata = path.lstat()
        raw = path.read_bytes()
    except OSError as error:
        raise ValueError(f"{subject} cannot be read") from error
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{subject} must be a regular file")
    return hashlib.sha256(raw).hexdigest()


def _mapping(value: object, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{subject} must be an object")
    return value


def _require_schema(value: Mapping[str, object], schema: str) -> None:
    if value.get("schema") != schema:
        raise ValueError(f"{schema} input is unsupported")


def _integer_list(value: object, subject: str) -> list[int]:
    if not isinstance(value, list) or not all(type(item) is int for item in value):  # noqa: E721
        raise ValueError(f"{subject} is invalid")
    return value


def _string_list(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _bounded_integer(value: object, *, maximum: int) -> bool:
    return type(value) is int and 0 <= value <= maximum  # type: ignore[operator]  # noqa: E721


def _check(passed: bool) -> dict[str, bool]:
    return {"passed": passed}


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="ascii")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
