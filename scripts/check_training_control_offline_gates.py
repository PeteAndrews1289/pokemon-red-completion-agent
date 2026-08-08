#!/usr/bin/env python3
"""Authenticate a preregistration and candidate, then score every offline gate."""

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
    parser.add_argument("--plan", nargs=2, metavar=("PATH", "SHA256"), required=True)
    parser.add_argument("--candidate", nargs=2, metavar=("PATH", "SHA256"), required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    plan_path, plan_digest = args.plan
    candidate_path, candidate_digest = args.candidate
    plan = _authenticated_json(Path(plan_path), plan_digest, subject="promotion plan")
    candidate = _authenticated_json(
        Path(candidate_path), candidate_digest, subject="candidate summary"
    )
    if plan.get("schema") != "pokemon-training-control-promotion-plan-v2":
        parser.error("promotion plan schema is unsupported")
    if candidate.get("schema") != "pokemon-training-control-candidate-summary-v1":
        parser.error("candidate summary schema is unsupported")
    if candidate.get("model_id") != "pokemon.core.training.control.mlp.v1":
        parser.error("candidate model identity is unsupported")
    if plan.get("feature_schema_id") != "pokemon.core.training.control.features.v2":
        parser.error("promotion plan feature schema is unsupported")

    _require_preregistered_lineages(plan, candidate, parser)
    gates = _mapping(plan.get("offline_validation_gates"), subject="offline gates")
    validation = _mapping(candidate.get("validation"), subject="validation metrics")
    counts = _numeric_mapping(validation.get("class_counts"), subject="class counts")
    precision = _numeric_mapping(validation.get("class_precision"), subject="class precision")
    confusion = _numeric_mapping(validation.get("confusion"), subject="confusion")
    errors = _numeric_mapping(validation.get("operational_errors"), subject="operational errors")

    battle_examples = counts.get("fight", 0.0) + counts.get("flee", 0.0)
    if battle_examples <= 0:
        parser.error("validation contains no battle examples")
    battle_accuracy = (
        confusion.get("fight -> fight", 0.0) + confusion.get("flee -> flee", 0.0)
    ) / battle_examples
    safe_seeks = counts.get("seek", 0.0)
    if safe_seeks <= 0:
        parser.error("validation contains no safe seeks")
    safe_seek_false_heal_rate = errors.get("unnecessary_heal", math.inf) / safe_seeks
    observed = {
        "missed_required_heal": errors.get("missed_required_heal", math.inf),
        "premature_stop": errors.get("premature_stop", math.inf),
        "missed_stop": errors.get("missed_stop", math.inf),
        "unnecessary_heal": errors.get("unnecessary_heal", math.inf),
        "safe_seek_false_heal_rate": safe_seek_false_heal_rate,
        "heal_precision": precision.get("heal", 0.0),
        "genuine_accuracy": _number(validation.get("genuine_accuracy"), "genuine accuracy"),
        "battle_accuracy": battle_accuracy,
    }
    checks = {
        "missed_required_heal": _maximum_check(
            observed["missed_required_heal"],
            _number(gates.get("missed_required_heal"), "missed-required-heal gate"),
        ),
        "premature_stop": _maximum_check(
            observed["premature_stop"],
            _number(gates.get("premature_stop"), "premature-stop gate"),
        ),
        "missed_stop": _maximum_check(
            observed["missed_stop"],
            _number(gates.get("missed_stop"), "missed-stop gate"),
        ),
        "unnecessary_heal": _maximum_check(
            observed["unnecessary_heal"],
            _number(gates.get("maximum_unnecessary_heals"), "unnecessary-heal gate"),
        ),
        "safe_seek_false_heal_rate": _maximum_check(
            observed["safe_seek_false_heal_rate"],
            _number(
                gates.get("maximum_safe_seek_false_heal_rate"),
                "false-heal-rate gate",
            ),
        ),
        "heal_precision": _minimum_check(
            observed["heal_precision"],
            _number(gates.get("minimum_heal_precision"), "heal-precision gate"),
        ),
        "genuine_accuracy": _minimum_check(
            observed["genuine_accuracy"],
            _number(gates.get("minimum_genuine_accuracy"), "genuine-accuracy gate"),
        ),
        "battle_accuracy": _minimum_check(
            observed["battle_accuracy"],
            _number(gates.get("minimum_battle_accuracy"), "battle-accuracy gate"),
        ),
    }
    eligible = all(bool(check["passed"]) for check in checks.values())
    payload = {
        "schema": "pokemon-training-control-offline-gate-evaluation-v1",
        "promotion_plan_sha256": plan_digest,
        "candidate_summary_sha256": candidate_digest,
        "model_id": candidate["model_id"],
        "model_sha256": candidate.get("model_sha256"),
        "checks": checks,
        "offline_validation_eligible": eligible,
        "shadow_may_start": eligible,
        "promotion_eligible": False,
    }
    _atomic_json(args.out, payload)
    print(json.dumps({"offline_validation_eligible": eligible}))
    return 0 if eligible else 2


def _require_preregistered_lineages(
    plan: Mapping[str, object],
    candidate: Mapping[str, object],
    parser: argparse.ArgumentParser,
) -> None:
    lineages = _mapping(plan.get("lineages"), subject="lineages")
    training = lineages.get("training")
    validation = _mapping(lineages.get("sealed_validation"), subject="sealed validation")
    if not isinstance(training, list) or not all(isinstance(row, Mapping) for row in training):
        parser.error("promotion plan training lineages are invalid")
    expected = {
        (str(row.get("lineage_id")), "train", str(row.get("root_sha256")))
        for row in training
    }
    expected.add(
        (
            str(validation.get("lineage_id")),
            "validation",
            str(validation.get("root_sha256")),
        )
    )
    roots = candidate.get("lineage_roots")
    if not isinstance(roots, list) or not all(isinstance(row, Mapping) for row in roots):
        parser.error("candidate summary lacks authenticated lineage roots")
    actual = {
        (str(row.get("lineage_id")), str(row.get("partition")), str(row.get("state_sha256")))
        for row in roots
    }
    if actual != expected:
        parser.error("candidate lineages do not match the preregistered roots")


def _authenticated_json(path: Path, digest: str, *, subject: str) -> Mapping[str, object]:
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
    try:
        parsed = json.loads(payload)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{subject} is invalid JSON") from error
    return _mapping(parsed, subject=subject)


def _mapping(value: object, *, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{subject} must be an object")
    return value


def _numeric_mapping(value: object, *, subject: str) -> dict[str, float]:
    source = _mapping(value, subject=subject)
    return {key: _number(item, f"{subject} value") for key, item in source.items()}


def _number(value: object, subject: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{subject} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{subject} must be finite")
    return result


def _maximum_check(observed: float, threshold: float) -> dict[str, object]:
    return {
        "comparison": "at_most",
        "observed": observed,
        "threshold": threshold,
        "passed": observed <= threshold,
    }


def _minimum_check(observed: float, threshold: float) -> dict[str, object]:
    return {
        "comparison": "at_least",
        "observed": observed,
        "threshold": threshold,
        "passed": observed >= threshold,
    }


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
