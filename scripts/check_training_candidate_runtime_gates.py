#!/usr/bin/env python3
"""Authenticate and score the strategic-candidate shadow/control chain."""

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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "plan",
        "offline",
        "model",
        "shadow",
        "shadow-replay",
        "control",
        "control-replay",
    ):
        parser.add_argument(
            f"--{name}", nargs=2, metavar=("PATH", "SHA256"), required=True
        )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    plan = _authenticated_json(*args.plan, subject="runtime promotion plan")
    offline = _authenticated_json(*args.offline, subject="offline gate")
    shadow = _authenticated_json(*args.shadow, subject="shadow audit")
    shadow_replay = _authenticated_json(*args.shadow_replay, subject="shadow replay")
    control = _authenticated_json(*args.control, subject="control audit")
    control_replay = _authenticated_json(*args.control_replay, subject="control replay")
    model_sha256 = _regular_file_sha256(Path(args.model[0]), subject="candidate model")
    if model_sha256 != args.model[1]:
        parser.error("candidate model failed authentication")
    _require_schema(
        plan,
        "pokemon-training-candidate-runtime-promotion-plan-v1",
        "runtime promotion plan",
    )
    _require_schema(
        offline,
        "pokemon-training-candidate-offline-gate-evaluation-v1",
        "offline gate",
    )
    for audit in (shadow, control):
        _require_schema(
            audit,
            "pokemon-training-candidate-runtime-audit-v1",
            "runtime audit",
        )
    for replay in (shadow_replay, control_replay):
        _require_schema(
            replay,
            "pokemon-training-candidate-replay-v1",
            "candidate replay",
        )

    required_offline = _mapping(
        plan.get("required_offline_gate"), subject="required offline gate"
    )
    if (
        offline.get("promotion_plan_sha256")
        != plan.get("offline_promotion_plan_sha256")
        or any(offline.get(key) != value for key, value in required_offline.items())
        or offline.get("candidate_model_file_sha256") != model_sha256
    ):
        parser.error("offline gate does not authorize this candidate model")

    lineages = _mapping(plan.get("lineages"), subject="runtime lineages")
    shadow_lineage = _mapping(lineages.get("shadow"), subject="shadow lineage")
    control_lineage = _mapping(
        lineages.get("causal_control"), subject="causal lineage"
    )
    _require_runtime_chain(
        shadow,
        shadow_replay,
        shadow_lineage,
        replay_sha256=args.shadow_replay[1],
        model_sha256=model_sha256,
        subject="shadow",
    )
    _require_runtime_chain(
        control,
        control_replay,
        control_lineage,
        replay_sha256=args.control_replay[1],
        model_sha256=model_sha256,
        subject="causal control",
    )
    runtime_sources = {
        "shadow": _provenance(shadow, subject="shadow audit").get("source_commit"),
        "causal_control": _provenance(control, subject="control audit").get(
            "source_commit"
        ),
    }
    if any(
        not isinstance(source, str) or _GIT_COMMIT.fullmatch(source) is None
        for source in runtime_sources.values()
    ):
        parser.error("runtime lineages must name exact committed sources")

    shadow_gates = _mapping(plan.get("shadow_gates"), subject="shadow gates")
    causal_gates = _mapping(plan.get("causal_gates"), subject="causal gates")
    shadow_checks = _shadow_checks(shadow, shadow_gates)
    causal_checks = _causal_checks(control, causal_gates)
    shadow_eligible = all(bool(check["passed"]) for check in shadow_checks.values())
    causal_eligible = shadow_eligible and all(
        bool(check["passed"]) for check in causal_checks.values()
    )
    payload = {
        "schema": "pokemon-training-candidate-runtime-gate-evaluation-v1",
        "runtime_promotion_plan_sha256": args.plan[1],
        "offline_gate_sha256": args.offline[1],
        "candidate_model_file_sha256": model_sha256,
        "shadow_audit_sha256": args.shadow[1],
        "shadow_replay_sha256": args.shadow_replay[1],
        "control_audit_sha256": args.control[1],
        "control_replay_sha256": args.control_replay[1],
        "runtime_source_commits": runtime_sources,
        "shadow_checks": shadow_checks,
        "causal_checks": causal_checks,
        "shadow_eligible": shadow_eligible,
        "causal_control_eligible": causal_eligible,
        "portable_training_loop_may_start": causal_eligible,
        "cross_title_transfer_eligible": False,
        "promotion_eligible": False,
    }
    _atomic_json(args.out, payload)
    print(
        json.dumps(
            {
                "shadow_eligible": shadow_eligible,
                "causal_control_eligible": causal_eligible,
            }
        )
    )
    return 0 if causal_eligible else 2


def _require_runtime_chain(
    audit: Mapping[str, object],
    replay: Mapping[str, object],
    expected: Mapping[str, object],
    *,
    replay_sha256: str,
    model_sha256: str,
    subject: str,
) -> None:
    audit_provenance = _provenance(audit, subject=f"{subject} audit")
    replay_provenance = _provenance(replay, subject=f"{subject} replay")
    lineage_id = expected.get("lineage_id")
    root_sha256 = expected.get("root_sha256")
    if not isinstance(lineage_id, str) or not isinstance(root_sha256, str):
        raise ValueError(f"{subject} preregistered identity is invalid")
    _digest(root_sha256, f"{subject} root")
    if (
        audit.get("status") != "ok"
        or audit.get("error") is not None
        or replay.get("status") != "ok"
        or replay.get("error") is not None
        or audit.get("model_artifact_sha256") != model_sha256
        or audit.get("candidate_replay_sha256") != replay_sha256
        or audit_provenance != replay_provenance
        or audit_provenance.get("lineage_id") != lineage_id
        or audit_provenance.get("state_sha256") != root_sha256
        or audit_provenance.get("source_dirty") is not False
    ):
        raise ValueError(f"{subject} runtime identity chain is invalid")


def _shadow_checks(
    audit: Mapping[str, object], gates: Mapping[str, object]
) -> dict[str, dict[str, object]]:
    outcome = _mapping(audit.get("outcome"), subject="shadow outcome")
    required_kinds = gates.get("required_choice_kinds")
    per_kind = _mapping(
        audit.get("genuine_kind_accuracy"), subject="shadow per-kind accuracy"
    )
    minimum_per_kind = _number(
        gates.get("minimum_genuine_per_kind_accuracy"), "minimum shadow per-kind accuracy"
    )
    return {
        "status": _equal_check(audit.get("status"), gates.get("required_status")),
        "no_execution_authority": _equal_check(
            audit.get("model_had_execution_authority"),
            gates.get("model_had_execution_authority"),
        ),
        "choice_kinds": _equal_check(sorted(per_kind), sorted(_string_list(required_kinds))),
        "genuine_decisions": _minimum_check(
            _integer(audit.get("genuine_decisions"), "shadow genuine decisions"),
            _integer(
                gates.get("minimum_genuine_multi_candidate_decisions"),
                "minimum shadow genuine decisions",
            ),
        ),
        "genuine_accuracy": _minimum_check(
            _number(audit.get("genuine_accuracy"), "shadow genuine accuracy"),
            _number(gates.get("minimum_genuine_accuracy"), "minimum shadow accuracy"),
        ),
        "genuine_per_kind_accuracy": _all_check(
            set(per_kind) == set(_string_list(required_kinds))
            and all(
                _number(value, f"{kind} shadow accuracy") >= minimum_per_kind
                for kind, value in per_kind.items()
            )
        ),
        "faints": _maximum_check(
            _integer(outcome.get("final_fainted_count"), "shadow faints"),
            _integer(gates.get("maximum_faints"), "maximum shadow faints"),
        ),
        "final_party_levels": _equal_check(
            outcome.get("final_party_levels"), gates.get("required_final_party_levels")
        ),
    }


def _causal_checks(
    audit: Mapping[str, object], gates: Mapping[str, object]
) -> dict[str, dict[str, object]]:
    outcome = _mapping(audit.get("outcome"), subject="control outcome")
    execution = _mapping(audit.get("execution"), subject="control execution")
    return {
        "status": _equal_check(audit.get("status"), gates.get("required_status")),
        "execution_authority": _equal_check(audit.get("model_had_execution_authority"), True),
        "authority_choice_kinds": _equal_check(
            audit.get("authority_choice_kinds"), gates.get("authority_choice_kinds")
        ),
        "teacher_fallback": _equal_check(
            audit.get("teacher_fallback_on_model_disagreement"),
            gates.get("teacher_fallback_on_model_disagreement"),
        ),
        "controlled_genuine_decisions": _minimum_check(
            _integer(audit.get("genuine_decisions"), "controlled genuine decisions"),
            _integer(
                gates.get("minimum_controlled_genuine_decisions"),
                "minimum controlled genuine decisions",
            ),
        ),
        "model_teacher_disagreements": _minimum_check(
            _integer(audit.get("disagreements"), "model/teacher disagreements"),
            _integer(
                gates.get("minimum_model_teacher_disagreements"),
                "minimum model/teacher disagreements",
            ),
        ),
        "candidate_decisions": _maximum_check(
            _integer(audit.get("decisions"), "candidate decisions"),
            _integer(gates.get("maximum_candidate_decisions"), "maximum decisions"),
        ),
        "battles": _maximum_check(
            _integer(execution.get("total_battles"), "control battles"),
            _integer(gates.get("maximum_battles"), "maximum battles"),
        ),
        "healing_trips": _maximum_check(
            _integer(execution.get("total_healing_trips"), "control healing trips"),
            _integer(gates.get("maximum_healing_trips"), "maximum healing trips"),
        ),
        "faints": _maximum_check(
            _integer(outcome.get("final_fainted_count"), "control faints"),
            _integer(gates.get("maximum_faints"), "maximum control faints"),
        ),
        "final_party_levels": _equal_check(
            outcome.get("final_party_levels"), gates.get("required_final_party_levels")
        ),
    }


def _provenance(payload: Mapping[str, object], *, subject: str) -> Mapping[str, object]:
    value = _mapping(payload.get("provenance"), subject=f"{subject} provenance")
    if set(value) != {
        "lineage_id",
        "partition",
        "source_commit",
        "source_dirty",
        "state_sha256",
    }:
        raise ValueError(f"{subject} provenance fields are invalid")
    return value


def _authenticated_json(path: str, digest: str, *, subject: str) -> Mapping[str, object]:
    _digest(digest, f"{subject} digest")
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


def _integer(value: object, subject: str) -> int:
    if type(value) is not int:  # noqa: E721
        raise ValueError(f"{subject} must be an integer")
    return value


def _digest(value: object, subject: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{subject} is invalid")


def _require_schema(payload: Mapping[str, object], schema: str, subject: str) -> None:
    if payload.get("schema") != schema:
        raise ValueError(f"{subject} schema is unsupported")


def _all_check(passed: bool) -> dict[str, object]:
    return {"comparison": "all_required", "passed": passed}


def _equal_check(observed: object, expected: object) -> dict[str, object]:
    return {
        "comparison": "equal",
        "observed": observed,
        "expected": expected,
        "passed": observed == expected,
    }


def _minimum_check(observed: int | float, minimum: int | float) -> dict[str, object]:
    return {
        "comparison": "greater_than_or_equal",
        "observed": observed,
        "minimum": minimum,
        "passed": observed >= minimum,
    }


def _maximum_check(observed: int | float, maximum: int | float) -> dict[str, object]:
    return {
        "comparison": "less_than_or_equal",
        "observed": observed,
        "maximum": maximum,
        "passed": observed <= maximum,
    }


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
