#!/usr/bin/env python3
"""Authenticate and score the complete training-control causal promotion chain."""

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
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_FINISHED = re.compile(
    r"finished: evolution_battles=(?P<evolution_battles>\d+), "
    r"evolution_healing_trips=(?P<evolution_heals>\d+), "
    r"balance_battles=(?P<balance_battles>\d+), "
    r"balance_healing_trips=(?P<balance_heals>\d+), "
    r"report=BalancedTeamReport\("
    r"required_size=(?P<required_size>\d+), "
    r"minimum_level=(?P<required_minimum>\d+), "
    r"maximum_level_spread=(?P<maximum_spread>\d+), "
    r"observed_size=(?P<observed_size>\d+), "
    r"observed_minimum_level=(?P<observed_minimum>\d+), "
    r"observed_level_spread=(?P<observed_spread>\d+), "
    r"fainted_count=(?P<faints>\d+),"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "candidate", "offline", "shadow", "decisions", "control", "log"):
        parser.add_argument(
            f"--{name}",
            nargs=2,
            metavar=("PATH", "SHA256"),
            required=True,
        )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    plan = _authenticated_json(*args.plan, subject="promotion plan")
    candidate = _authenticated_json(*args.candidate, subject="candidate summary")
    offline = _authenticated_json(*args.offline, subject="offline gate evaluation")
    shadow = _authenticated_json(*args.shadow, subject="shadow audit")
    decisions = _authenticated_json(*args.decisions, subject="controlled decisions")
    control = _authenticated_json(*args.control, subject="control audit")
    log_text = _authenticated_text(*args.log, subject="control log")

    if plan.get("schema") != "pokemon-training-control-promotion-plan-v2":
        parser.error("promotion plan schema is unsupported")
    if candidate.get("schema") != "pokemon-training-control-candidate-summary-v1":
        parser.error("candidate summary schema is unsupported")
    if offline.get("schema") != "pokemon-training-control-offline-gate-evaluation-v1":
        parser.error("offline gate schema is unsupported")
    source_commit = plan.get("source_commit")
    if not isinstance(source_commit, str) or _GIT_COMMIT.fullmatch(source_commit) is None:
        parser.error("promotion plan source commit is invalid")
    candidate_digest = args.candidate[1]
    if (
        offline.get("candidate_summary_sha256") != candidate_digest
        or offline.get("offline_validation_eligible") is not True
        or offline.get("shadow_may_start") is not True
        or offline.get("model_sha256") != candidate.get("model_sha256")
    ):
        parser.error("offline approval does not authenticate this eligible candidate")

    lineages = _mapping(plan.get("lineages"), subject="lineages")
    _require_audit_lineage(
        shadow,
        _mapping(lineages.get("shadow"), subject="shadow lineage"),
        source_commit=source_commit,
        subject="shadow audit",
    )
    if (
        shadow.get("status") != "ok"
        or shadow.get("error") is not None
        or shadow.get("model_had_execution_authority") is not False
        or shadow.get("authority_phases") != []
    ):
        parser.error("shadow audit is not a successful no-authority run")

    causal_lineage = _mapping(lineages.get("causal_control"), subject="causal lineage")
    _require_replay_lineage(
        decisions,
        causal_lineage,
        source_commit=source_commit,
        subject="controlled decisions",
    )
    _require_audit_lineage(
        control,
        causal_lineage,
        source_commit=source_commit,
        subject="control audit",
    )
    if decisions.get("status") != "ok" or decisions.get("error") is not None:
        parser.error("controlled replay did not complete successfully")
    if control.get("status") != "ok" or control.get("error") is not None:
        parser.error("control audit did not complete successfully")

    model_sha256 = candidate.get("model_sha256")
    model_file_sha256 = candidate.get("private_model_file_sha256")
    if not all(
        audit.get("model_sha256") == model_sha256
        and audit.get("model_artifact_sha256") == model_file_sha256
        for audit in (shadow, control)
    ):
        parser.error("live audits do not authenticate the selected model")

    segments = _mapping(decisions.get("segments"), subject="decision segments")
    evolution_rows = segments.get("evolution")
    balance_rows = segments.get("balance")
    if (
        set(segments) != {"evolution", "balance"}
        or not isinstance(evolution_rows, list)
        or not isinstance(balance_rows, list)
    ):
        parser.error("controlled decision segments are invalid")
    decision_count = len(evolution_rows) + len(balance_rows)
    if decision_count < 1 or not balance_rows:
        parser.error("controlled replay contains no decisions")
    terminal = _mapping(balance_rows[-1], subject="terminal decision")
    observation = _mapping(terminal.get("observation"), subject="terminal observation")
    features = _numeric_mapping(observation.get("features"), subject="terminal features")
    if (
        terminal.get("action") != "stop"
        or observation.get("phase") != "overworld"
        or observation.get("candidate_actions") != ["stop"]
    ):
        parser.error("controlled replay lacks one forced terminal stop")

    causal_gates = _mapping(plan.get("causal_gates"), subject="causal gates")
    authority_phases = causal_gates.get("authority_phases")
    if not isinstance(authority_phases, list) or not all(
        isinstance(value, str) for value in authority_phases
    ):
        parser.error("causal authority phases are invalid")
    if (
        control.get("authority_phases") != authority_phases
        or control.get("model_had_execution_authority") is not True
        or control.get("teacher_fallback_on_model_disagreement")
        != causal_gates.get("teacher_fallback_on_model_disagreement")
        or control.get("controlled_decisions") != decision_count
        or control.get("decisions") != decision_count
    ):
        parser.error("control audit does not prove the preregistered authority contract")

    execution = _parse_execution(log_text, parser)
    required_levels = causal_gates.get("required_final_party_levels")
    if not isinstance(required_levels, list) or not all(
        type(value) is int and value > 0 for value in required_levels  # noqa: E721
    ):
        parser.error("required final party levels are invalid")
    if execution["observed_spread"] != 0:
        parser.error("terminal log cannot reconstruct a nonzero-spread level vector")
    final_levels = [execution["observed_minimum"]] * execution["observed_size"]
    _require_terminal_feature(
        features,
        "party.fill_ratio",
        execution["observed_size"] / len(required_levels),
        parser,
    )
    _require_terminal_feature(features, "party.fainted_ratio", 0.0, parser)
    _require_terminal_feature(
        features,
        "party.minimum_level",
        execution["observed_minimum"] / 100,
        parser,
    )
    _require_terminal_feature(
        features,
        "party.level_spread",
        execution["observed_spread"] / 99,
        parser,
    )

    battles = execution["evolution_battles"] + execution["balance_battles"]
    healing_trips = execution["evolution_heals"] + execution["balance_heals"]
    faints = execution["faints"]
    observed: dict[str, object] = {
        "decisions": decision_count,
        "battles": battles,
        "healing_trips": healing_trips,
        "faints": faints,
        "final_party_levels": final_levels,
    }
    checks = {
        "authority_phases": _equal_check(control.get("authority_phases"), authority_phases),
        "teacher_fallback": _equal_check(
            control.get("teacher_fallback_on_model_disagreement"),
            causal_gates.get("teacher_fallback_on_model_disagreement"),
        ),
        "decisions": _maximum_check(decision_count, causal_gates, "maximum_decisions"),
        "battles": _maximum_check(battles, causal_gates, "maximum_battles"),
        "healing_trips": _maximum_check(
            healing_trips, causal_gates, "maximum_healing_trips"
        ),
        "faints": _maximum_check(faints, causal_gates, "maximum_faints"),
        "final_party_levels": _equal_check(final_levels, required_levels),
    }
    eligible = all(bool(check["passed"]) for check in checks.values())
    payload = {
        "schema": "pokemon-training-control-causal-gate-evaluation-v1",
        "promotion_plan_sha256": args.plan[1],
        "candidate_summary_sha256": candidate_digest,
        "offline_gate_evaluation_sha256": args.offline[1],
        "shadow_audit_sha256": args.shadow[1],
        "controlled_decisions_sha256": args.decisions[1],
        "control_audit_sha256": args.control[1],
        "control_log_sha256": args.log[1],
        "model_sha256": model_sha256,
        "observed": observed,
        "checks": checks,
        "causal_control_eligible": eligible,
        "portable_loop_may_start": eligible,
        "promotion_eligible": False,
    }
    _atomic_json(args.out, payload)
    print(json.dumps({"causal_control_eligible": eligible}))
    return 0 if eligible else 2


def _require_replay_lineage(
    replay: Mapping[str, object],
    expected: Mapping[str, object],
    *,
    source_commit: str,
    subject: str,
) -> None:
    if replay.get("schema") != "pokemon-training-control-replay-v2":
        raise ValueError(f"{subject} schema is unsupported")
    _require_provenance(replay, expected, source_commit=source_commit, subject=subject)


def _require_audit_lineage(
    audit: Mapping[str, object],
    expected: Mapping[str, object],
    *,
    source_commit: str,
    subject: str,
) -> None:
    if audit.get("schema") != "pokemon-training-control-shadow-summary-v1":
        raise ValueError(f"{subject} schema is unsupported")
    _require_provenance(audit, expected, source_commit=source_commit, subject=subject)


def _require_provenance(
    payload: Mapping[str, object],
    expected: Mapping[str, object],
    *,
    source_commit: str,
    subject: str,
) -> None:
    provenance = _mapping(payload.get("provenance"), subject=f"{subject} provenance")
    if (
        provenance.get("lineage_id") != expected.get("lineage_id")
        or provenance.get("partition") != "unassigned"
        or provenance.get("state_sha256") != expected.get("root_sha256")
        or provenance.get("source_commit") != source_commit
        or provenance.get("source_dirty") is not False
    ):
        raise ValueError(f"{subject} provenance does not match the preregistration")


def _parse_execution(text: str, parser: argparse.ArgumentParser) -> dict[str, int]:
    matches = tuple(_FINISHED.finditer(text))
    if len(matches) != 1 or "\nFAILED:" in text:
        parser.error("control log lacks one unambiguous successful terminal report")
    return {name: int(value) for name, value in matches[0].groupdict().items()}


def _require_terminal_feature(
    features: Mapping[str, float],
    name: str,
    expected: float,
    parser: argparse.ArgumentParser,
) -> None:
    if name not in features or not math.isclose(features[name], expected, abs_tol=1e-12):
        parser.error(f"terminal decision contradicts the control log for {name}")


def _maximum_check(
    observed: int,
    gates: Mapping[str, object],
    name: str,
) -> dict[str, object]:
    threshold = gates.get(name)
    if type(threshold) is not int or threshold < 0:  # noqa: E721
        raise ValueError(f"causal gate {name} is invalid")
    return {
        "comparison": "at_most",
        "observed": observed,
        "threshold": threshold,
        "passed": observed <= threshold,
    }


def _equal_check(observed: object, expected: object) -> dict[str, object]:
    return {
        "comparison": "equal",
        "observed": observed,
        "expected": expected,
        "passed": observed == expected,
    }


def _authenticated_json(path: str, digest: str, *, subject: str) -> Mapping[str, object]:
    payload = _authenticated_bytes(Path(path), digest, subject=subject)
    try:
        parsed = json.loads(payload)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{subject} is invalid JSON") from error
    return _mapping(parsed, subject=subject)


def _authenticated_text(path: str, digest: str, *, subject: str) -> str:
    payload = _authenticated_bytes(Path(path), digest, subject=subject)
    try:
        return payload.decode()
    except UnicodeError as error:
        raise ValueError(f"{subject} is not UTF-8") from error


def _authenticated_bytes(path: Path, digest: str, *, subject: str) -> bytes:
    if _SHA256.fullmatch(digest) is None:
        raise ValueError(f"{subject} digest is invalid")
    try:
        metadata = path.lstat()
        payload = path.read_bytes()
    except OSError as error:
        raise ValueError(f"{subject} cannot be read") from error
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{subject} must be a regular file")
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError(f"{subject} failed authentication")
    return payload


def _mapping(value: object, *, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{subject} must be an object")
    return value


def _numeric_mapping(value: object, *, subject: str) -> dict[str, float]:
    source = _mapping(value, subject=subject)
    result: dict[str, float] = {}
    for key, item in source.items():
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError(f"{subject} value must be numeric")
        number = float(item)
        if not math.isfinite(number):
            raise ValueError(f"{subject} value must be finite")
        result[key] = number
    return result


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
