#!/usr/bin/env python3
"""Authenticate the portable training-control proof and classify its claims."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import stat
from collections.abc import Mapping
from pathlib import Path

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("candidate", "causal", "choice", "portable", "envelope"):
        parser.add_argument(
            f"--{name}",
            nargs=2,
            metavar=("PATH", "SHA256"),
            required=True,
        )
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    candidate = _authenticated_json(*args.candidate, subject="candidate summary")
    causal = _authenticated_json(*args.causal, subject="causal gate evaluation")
    choice = _authenticated_json(*args.choice, subject="choice-diversity audit")
    portable = _authenticated_json(*args.portable, subject="portable report")
    envelope = _authenticated_json(*args.envelope, subject="terminal state envelope")

    _require_schema(
        candidate,
        "pokemon-training-control-candidate-summary-v1",
        subject="candidate summary",
    )
    _require_schema(
        causal,
        "pokemon-training-control-causal-gate-evaluation-v1",
        subject="causal gate evaluation",
    )
    _require_schema(
        choice,
        "pokemon-training-control-choice-diversity-audit-v1",
        subject="choice-diversity audit",
    )
    _require_schema(
        portable,
        "pokemon-model-selected-objective-execution-v3",
        subject="portable report",
    )
    _require_schema(
        envelope,
        "pokemon-private-captured-progress-v1",
        subject="terminal state envelope",
    )

    _require_candidate_chain(candidate, causal, choice, args, parser)
    state_sha256 = _regular_file_sha256(args.state, subject="terminal emulator state")
    if envelope.get("state_sha256") != state_sha256:
        parser.error("terminal state envelope does not authenticate the emulator state")

    training = _mapping(portable.get("training_control"), subject="portable training control")
    assistance = _mapping(portable.get("assistance"), subject="portable assistance")
    source = _mapping(portable.get("source"), subject="portable source")
    before = _mapping(portable.get("before"), subject="portable before state")
    after = _mapping(portable.get("after"), subject="portable after state")
    steps = portable.get("decisions_and_executions")
    if not isinstance(steps, list) or len(steps) != 1 or not isinstance(steps[0], Mapping):
        parser.error("portable proof must contain exactly one objective execution")
    step = steps[0]
    evidence = _mapping(step.get("skill_evidence"), subject="portable skill evidence")
    development = _mapping(evidence.get("team_development"), subject="team development")
    levels = development.get("levels")
    if not isinstance(levels, list) or not all(
        type(level) is int and 1 <= level <= 100 for level in levels  # noqa: E721
    ):
        parser.error("portable terminal levels are invalid")
    controlled_decisions = training.get("controlled_decisions")

    authority_checks = {
        "causal_chain": _equal_check(causal.get("portable_loop_may_start"), True),
        "portable_status": _equal_check(portable.get("status"), "ok"),
        "published_clean_source": _all_check(
            source.get("worktree_dirty") is False
            and isinstance(source.get("git_commit"), str)
            and len(str(source.get("git_commit"))) == 40
        ),
        "model_identity": _all_check(
            training.get("model_sha256") == candidate.get("model_sha256")
            and training.get("model_file_sha256")
            == candidate.get("private_model_file_sha256")
        ),
        "full_training_authority": _all_check(
            training.get("authority_phases") == ["battle", "overworld"]
            and training.get("model_had_execution_authority") is True
            and training.get("teacher_fallback_on_model_disagreement") is False
            and type(controlled_decisions) is int  # noqa: E721
            and controlled_decisions > 0
            and controlled_decisions == training.get("decisions")
        ),
        "objective_boundary": _all_check(
            before.get("available_objectives") == ["defeat_blaine"]
            and step.get("objective_id") == "defeat_blaine"
            and step.get("kind") == "skill_completed"
            and evidence.get("objective") == "defeat_blaine"
            and evidence.get("status") == "ok"
        ),
        "fresh_completion_observation": _all_check(
            "defeat_blaine" in _string_list(after.get("completed_objectives"))
            and "badge:volcano" in _string_list(after.get("facts_added"))
            and "defeat_giovanni" in _string_list(after.get("available_objectives"))
        ),
        "developed_party": _all_check(
            development.get("final_forms_complete") is True
            and len(levels) == 6
            and min(levels, default=0) >= 55
        ),
        "assistance_boundary": _all_check(
            assistance.get("teacher_fallbacks") == 0
            and assistance.get("expected_route_label_provided") is False
            and assistance.get("mechanic_execution") == "teacher_authored_bounded_skill"
        ),
        "terminal_state": _all_check(
            envelope.get("checkpoint_id") == "portable_loop_defeat_blaine_terminal"
            and "defeat_blaine" in _string_list(envelope.get("verified_objective_ids"))
        ),
    }
    authority_eligible = all(bool(check["passed"]) for check in authority_checks.values())

    validation = _mapping(candidate.get("validation"), subject="candidate validation")
    model_genuine_accuracy = _number(
        validation.get("genuine_accuracy"), "candidate validation genuine accuracy"
    )
    baseline_genuine_accuracy = _number(
        choice.get("validation_genuine_candidate_only_accuracy"),
        "candidate-only genuine accuracy",
    )
    feature_value_checks = {
        "state_dependent_labels": _equal_check(
            choice.get("state_dependent_choice_demonstrated"), True
        ),
        "candidate_baseline_not_saturated": _equal_check(
            choice.get("candidate_only_baseline_saturates_validation"), False
        ),
        "model_beats_candidate_baseline": _strict_minimum_check(
            model_genuine_accuracy, baseline_genuine_accuracy
        ),
    }
    feature_value_eligible = all(
        bool(check["passed"]) for check in feature_value_checks.values()
    )
    payload = {
        "schema": "pokemon-training-control-portable-gate-evaluation-v1",
        "candidate_summary_sha256": args.candidate[1],
        "causal_gate_evaluation_sha256": args.causal[1],
        "choice_diversity_audit_sha256": args.choice[1],
        "portable_report_sha256": args.portable[1],
        "terminal_envelope_sha256": args.envelope[1],
        "terminal_state_sha256": state_sha256,
        "model_sha256": candidate.get("model_sha256"),
        "observed": {
            "controlled_decisions": controlled_decisions,
            "model_genuine_accuracy": model_genuine_accuracy,
            "candidate_only_genuine_accuracy": baseline_genuine_accuracy,
            "final_party_levels": levels,
        },
        "authority_integration_checks": authority_checks,
        "feature_value_checks": feature_value_checks,
        "portable_authority_integration_eligible": authority_eligible,
        "state_dependent_policy_evidence_eligible": feature_value_eligible,
        "verified_claims": (
            ["portable_captured_state_training_authority"] if authority_eligible else []
        ),
        "unsupported_claims": (
            [] if feature_value_eligible else ["state_dependent_training_policy"]
        ),
        "clean_start_evaluation_eligible": False,
        "cross_title_transfer_eligible": False,
        "end_to_end_learned_gameplay_eligible": False,
        "promotion_eligible": False,
    }
    _atomic_json(args.out, payload)
    print(
        json.dumps(
            {
                "portable_authority_integration_eligible": authority_eligible,
                "state_dependent_policy_evidence_eligible": feature_value_eligible,
            }
        )
    )
    return 0 if authority_eligible else 2


def _require_candidate_chain(
    candidate: Mapping[str, object],
    causal: Mapping[str, object],
    choice: Mapping[str, object],
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> None:
    if (
        causal.get("candidate_summary_sha256") != args.candidate[1]
        or causal.get("causal_control_eligible") is not True
        or causal.get("portable_loop_may_start") is not True
        or causal.get("model_sha256") != candidate.get("model_sha256")
    ):
        parser.error("causal approval does not authenticate this eligible candidate")
    roots = candidate.get("lineage_roots")
    lineages = choice.get("lineages")
    if not isinstance(roots, list) or not isinstance(lineages, list):
        parser.error("candidate or choice audit lacks lineage identities")
    candidate_identities = {
        (
            row.get("lineage_id"),
            row.get("partition"),
            row.get("artifact_sha256"),
            row.get("state_sha256"),
            row.get("source_commit"),
            row.get("source_dirty"),
        )
        for row in roots
        if isinstance(row, Mapping)
    }
    choice_identities = {
        (
            row.get("lineage_id"),
            row.get("partition"),
            row.get("artifact_sha256"),
            row.get("state_sha256"),
            row.get("source_commit"),
            row.get("source_dirty"),
        )
        for row in lineages
        if isinstance(row, Mapping)
    }
    if len(candidate_identities) != len(roots) or candidate_identities != choice_identities:
        parser.error("choice audit does not cover the candidate's exact lineages")


def _require_schema(payload: Mapping[str, object], schema: str, *, subject: str) -> None:
    if payload.get("schema") != schema:
        raise ValueError(f"{subject} schema is unsupported")


def _authenticated_json(path: str, digest: str, *, subject: str) -> Mapping[str, object]:
    if _SHA256.fullmatch(digest) is None:
        raise ValueError(f"{subject} digest is invalid")
    source = Path(path)
    try:
        metadata = source.lstat()
        payload = source.read_bytes()
    except OSError as error:
        raise ValueError(f"{subject} cannot be read") from error
    if source.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{subject} must be a regular file")
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError(f"{subject} failed authentication")
    try:
        parsed = json.loads(payload)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{subject} is invalid JSON") from error
    return _mapping(parsed, subject=subject)


def _regular_file_sha256(path: Path, *, subject: str) -> str:
    try:
        metadata = path.lstat()
        payload = path.read_bytes()
    except OSError as error:
        raise ValueError(f"{subject} cannot be read") from error
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{subject} must be a regular file")
    return hashlib.sha256(payload).hexdigest()


def _mapping(value: object, *, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{subject} must be an object")
    return value


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("expected a string list")
    return value


def _number(value: object, subject: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{subject} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{subject} must be finite")
    return result


def _equal_check(observed: object, expected: object) -> dict[str, object]:
    return {
        "comparison": "equal",
        "observed": observed,
        "expected": expected,
        "passed": observed == expected,
    }


def _all_check(passed: bool) -> dict[str, object]:
    return {"comparison": "all_required", "passed": passed}


def _strict_minimum_check(observed: float, baseline: float) -> dict[str, object]:
    return {
        "comparison": "greater_than",
        "observed": observed,
        "baseline": baseline,
        "passed": observed > baseline,
    }


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
