#!/usr/bin/env python3
"""Authenticate and score the preregistered strategic-candidate offline gate."""

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
    for name in ("plan", "selection", "summary", "model"):
        parser.add_argument(f"--{name}", nargs=2, metavar=("PATH", "SHA256"), required=True)
    parser.add_argument(
        "--audit", action="append", nargs=2, metavar=("PATH", "SHA256"), required=True
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    plan = _authenticated_json(*args.plan, subject="promotion plan")
    selection = _authenticated_json(*args.selection, subject="training-only selection")
    summary = _authenticated_json(*args.summary, subject="candidate summary")
    model_sha256 = _regular_file_sha256(Path(args.model[0]), subject="candidate model")
    if model_sha256 != args.model[1]:
        parser.error("candidate model failed authentication")
    audits = tuple(
        _authenticated_json(path, digest, subject="choice audit")
        for path, digest in args.audit
    )
    _require_schema(plan, "pokemon-training-candidate-promotion-plan-v1", "promotion plan")
    _require_schema(
        selection, "pokemon-training-candidate-selection-v1", "training-only selection"
    )
    _require_schema(
        summary, "pokemon-training-candidate-model-summary-v1", "candidate summary"
    )
    for audit in audits:
        _require_schema(audit, "pokemon-training-candidate-choice-audit-v1", "choice audit")

    planned = _planned_lineages(plan, parser)
    roots = _summary_roots(summary, parser)
    audited = _audited_lineages(audits, parser)
    collection_gate = _mapping(plan.get("collection_gates"), subject="collection gates")
    offline_gate = _mapping(
        plan.get("offline_validation_gates"), subject="offline validation gates"
    )
    source_commit = plan.get("source_commit")
    expected_ids = set(planned)
    identity_checks = {
        "exact_lineage_roster": _all_check(
            set(roots) == expected_ids and set(audited) == expected_ids
        ),
        "plan_summary_audit_identity_chain": _all_check(
            all(
                lineage_id in roots
                and lineage_id in audited
                and roots[lineage_id]["state_sha256"] == planned[lineage_id]["root_sha256"]
                and audited[lineage_id]["state_sha256"]
                == planned[lineage_id]["root_sha256"]
                and roots[lineage_id]["artifact_sha256"]
                == audited[lineage_id]["replay_sha256"]
                and roots[lineage_id]["source_commit"] == source_commit
                and audited[lineage_id]["source_commit"] == source_commit
                and roots[lineage_id]["source_dirty"] is False
                and audited[lineage_id]["source_dirty"] is False
                for lineage_id in expected_ids
            )
        ),
        "model_file_identity": _all_check(
            summary.get("private_model_file_sha256") == model_sha256
        ),
        "whole_lineage_partition_audit": _all_check(
            _mapping(summary.get("partition_audit"), subject="partition audit").get(
                "promotion_eligible"
            )
            is True
        ),
    }

    required_levels = collection_gate.get("required_final_party_levels")
    required_kinds = set(_string_list(collection_gate.get("required_choice_kinds")))
    minimum_multi = _integer(
        collection_gate.get("minimum_multi_candidate_decisions"),
        "minimum multi-candidate decisions",
    )
    maximum_faints = _integer(collection_gate.get("maximum_faints"), "maximum faints")
    sampling_method = collection_gate.get("sampling_method")
    collection_checks: dict[str, dict[str, object]] = {}
    for lineage_id, audit in sorted(audited.items()):
        collection_checks[lineage_id] = _all_check(
            audit.get("status") == collection_gate.get("required_status")
            and audit.get("lineage_qualified") is True
            and audit.get("final_party_levels") == required_levels
            and _integer(audit.get("final_fainted_count"), "final faint count")
            <= maximum_faints
            and set(_mapping(audit.get("kind_counts"), subject="kind counts"))
            == required_kinds
            and _integer(
                audit.get("multi_candidate_decisions"), "multi-candidate decisions"
            )
            >= minimum_multi
            and audit.get("identity_fields_present")
            is collection_gate.get("identity_fields_present")
            and _integer(audit.get("observed_decisions"), "observed decisions")
            >= _integer(audit.get("retained_decisions"), "retained decisions")
            and sampling_method == "retain_first_and_per_kind_state_transitions"
        )

    selection_checks = _selection_checks(selection, summary, planned, roots)
    validation_id = next(
        lineage_id
        for lineage_id, identity in planned.items()
        if identity["partition"] == "validation"
    )
    validation_audit = audited[validation_id]
    validation = _mapping(summary.get("validation"), subject="validation metrics")
    genuine_accuracy = _number(validation.get("genuine_accuracy"), "genuine accuracy")
    genuine_baseline = _number(
        validation.get("genuine_shape_baseline_accuracy"),
        "genuine shape baseline accuracy",
    )
    audit_baseline = _number(
        validation_audit.get("genuine_shape_only_majority_accuracy"),
        "validation audit shape accuracy",
    )
    per_kind = _mapping(
        validation.get("genuine_kind_accuracy"), subject="genuine kind accuracy"
    )
    minimum_kind = _number(
        offline_gate.get("minimum_genuine_per_kind_accuracy"),
        "minimum per-kind accuracy",
    )
    offline_checks = {
        "state_dependent_choices": _equal_check(
            validation_audit.get("state_dependent_choice_demonstrated"),
            offline_gate.get("state_dependent_choice_demonstrated"),
        ),
        "validation_shape_baseline_below_ceiling": _maximum_check(
            audit_baseline,
            _number(
                offline_gate.get("maximum_genuine_shape_only_majority_accuracy"),
                "maximum shape baseline accuracy",
            ),
        ),
        "model_margin_over_training_shape_baseline": _minimum_check(
            genuine_accuracy - genuine_baseline,
            _number(
                offline_gate.get(
                    "minimum_genuine_heldout_model_margin_over_shape_baseline"
                ),
                "minimum model margin",
            ),
        ),
        "genuine_validation_accuracy": _minimum_check(
            genuine_accuracy,
            _number(
                offline_gate.get("minimum_genuine_heldout_accuracy"),
                "minimum genuine accuracy",
            ),
        ),
        "genuine_per_kind_accuracy": _all_check(
            set(per_kind) == required_kinds
            and all(
                _number(value, f"{kind} genuine accuracy") >= minimum_kind
                for kind, value in per_kind.items()
            )
        ),
        "validation_closed_during_selection": _all_check(
            selection.get("validation_opened")
            is offline_gate.get("validation_opened_during_selection")
            and summary.get("validation_opened") is True
        ),
    }
    eligible = all(
        bool(check["passed"])
        for group in (identity_checks, collection_checks, selection_checks, offline_checks)
        for check in group.values()
    )
    payload = {
        "schema": "pokemon-training-candidate-offline-gate-evaluation-v1",
        "promotion_plan_sha256": args.plan[1],
        "selection_sha256": args.selection[1],
        "candidate_summary_sha256": args.summary[1],
        "candidate_model_file_sha256": model_sha256,
        "choice_audit_sha256s": sorted(digest for _path, digest in args.audit),
        "source_commit": source_commit,
        "observed": {
            "validation_lineage": validation_id,
            "genuine_validation_accuracy": genuine_accuracy,
            "genuine_training_shape_baseline_accuracy": genuine_baseline,
            "genuine_validation_shape_majority_accuracy": audit_baseline,
            "genuine_model_margin": genuine_accuracy - genuine_baseline,
            "genuine_per_kind_accuracy": dict(per_kind),
        },
        "identity_checks": identity_checks,
        "collection_checks": collection_checks,
        "selection_checks": selection_checks,
        "offline_validation_checks": offline_checks,
        "offline_candidate_eligible": eligible,
        "shadow_may_start": eligible,
        "causal_control_may_start": False,
        "cross_title_transfer_eligible": False,
        "promotion_eligible": False,
    }
    _atomic_json(args.out, payload)
    print(json.dumps({"offline_candidate_eligible": eligible, "shadow_may_start": eligible}))
    return 0 if eligible else 2


def _planned_lineages(
    plan: Mapping[str, object], parser: argparse.ArgumentParser
) -> dict[str, dict[str, object]]:
    lineages = _mapping(plan.get("lineages"), subject="planned lineages")
    training = lineages.get("training")
    validation = lineages.get("sealed_validation")
    if not isinstance(training, list) or len(training) < 2 or not isinstance(validation, Mapping):
        parser.error("promotion plan lineage split is invalid")
    result: dict[str, dict[str, object]] = {}
    for partition, values in (("train", training), ("validation", [validation])):
        for raw in values:
            identity = _mapping(raw, subject="planned lineage")
            lineage_id = identity.get("lineage_id")
            root = identity.get("root_sha256")
            if not isinstance(lineage_id, str) or not isinstance(root, str):
                parser.error("planned lineage identity is invalid")
            _digest(root, "planned root digest")
            if lineage_id in result:
                parser.error("planned lineage identity is duplicated")
            result[lineage_id] = {
                "partition": partition,
                "root_sha256": root,
            }
    return result


def _summary_roots(
    summary: Mapping[str, object], parser: argparse.ArgumentParser
) -> dict[str, Mapping[str, object]]:
    raw = summary.get("lineage_roots")
    if not isinstance(raw, list):
        parser.error("candidate summary lacks lineage roots")
    result = {}
    for item in raw:
        identity = _mapping(item, subject="candidate lineage root")
        lineage_id = identity.get("lineage_id")
        if not isinstance(lineage_id, str) or lineage_id in result:
            parser.error("candidate summary lineage identity is invalid")
        result[lineage_id] = identity
    return result


def _audited_lineages(
    audits: tuple[Mapping[str, object], ...], parser: argparse.ArgumentParser
) -> dict[str, Mapping[str, object]]:
    result = {}
    for audit in audits:
        provenance = _mapping(audit.get("provenance"), subject="audit provenance")
        lineage_id = provenance.get("lineage_id")
        if not isinstance(lineage_id, str) or lineage_id in result:
            parser.error("choice audit lineage identity is invalid or duplicated")
        result[lineage_id] = {**audit, **provenance}
    return result


def _selection_checks(
    selection: Mapping[str, object],
    summary: Mapping[str, object],
    planned: Mapping[str, Mapping[str, object]],
    roots: Mapping[str, Mapping[str, object]],
) -> dict[str, dict[str, object]]:
    training = selection.get("training_lineages")
    if not isinstance(training, list):
        raise ValueError("selection lacks training lineages")
    selected = {
        str(row.get("lineage_id")): row
        for row in training
        if isinstance(row, Mapping) and isinstance(row.get("lineage_id"), str)
    }
    selected_ids = set(selected)
    planned_train_ids = {
        lineage_id
        for lineage_id, identity in planned.items()
        if identity["partition"] == "train"
    }
    selected_power = selection.get("selected_kind_balance_power")
    selection_hyperparameters = _mapping(
        selection.get("hyperparameters"), subject="selection hyperparameters"
    )
    summary_hyperparameters = _mapping(
        summary.get("hyperparameters"), subject="summary hyperparameters"
    )
    return {
        "training_only_lineage_roster": _all_check(selected_ids == planned_train_ids),
        "training_selection_identity_chain": _all_check(
            len(selected) == len(training)
            and all(
                lineage_id in roots
                and selected[lineage_id].get("artifact_sha256")
                == roots[lineage_id].get("artifact_sha256")
                and selected[lineage_id].get("state_sha256")
                == roots[lineage_id].get("state_sha256")
                and selected[lineage_id].get("source_commit")
                == roots[lineage_id].get("source_commit")
                and selected[lineage_id].get("source_dirty") is False
                for lineage_id in selected
            )
        ),
        "selection_declares_validation_closed": _equal_check(
            selection.get("validation_opened"), False
        ),
        "selected_hyperparameters_frozen": _all_check(
            all(
                summary_hyperparameters.get(name) == value
                for name, value in selection_hyperparameters.items()
            )
            and summary_hyperparameters.get("kind_balance_power") == selected_power
        ),
    }


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


def _digest(value: str, subject: str) -> None:
    if _SHA256.fullmatch(value) is None:
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


def _minimum_check(observed: float, minimum: float) -> dict[str, object]:
    return {
        "comparison": "greater_than_or_equal",
        "observed": observed,
        "minimum": minimum,
        "passed": observed >= minimum,
    }


def _maximum_check(observed: float, maximum: float) -> dict[str, object]:
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
