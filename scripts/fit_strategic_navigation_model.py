#!/usr/bin/env python3
"""Fit the first destination ranker from counted strategic scenarios."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

from pokemon_red_completion.captured_progress import load_captured_progress
from pokemon_red_completion.private_artifacts import open_private_root
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.strategic_navigation_audit import (
    audit_strategic_navigation_collection,
)
from pokemon_red_completion.strategic_navigation_dataset import (
    CollectedStrategicNavigationDataset,
    load_assigned_strategic_navigation_episode,
)
from pokemon_red_completion.strategic_navigation_model import (
    STRATEGIC_NAVIGATION_FEATURE_NAMES,
    canonical_strategic_navigation_model_sha256,
    evaluate_strategic_navigation_model,
    select_strategic_navigation_model,
)
from pokemon_red_completion.strategic_navigation_protocol import (
    StrategicNavigationExecution,
)
from pokemon_red_completion.strategic_navigation_scenarios import (
    load_strategic_navigation_scenario_registry,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
COLLECTION_AUDIT = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "strategic-counted-collection-audit-2026-08-13.json"
)


class StrategicModelFitError(RuntimeError):
    """Raised when counted data cannot enter the development fit."""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--checkpoint-root", type=Path)
    parser.add_argument("--out-model", type=Path, required=True)
    parser.add_argument("--out-summary", type=Path, required=True)
    args = parser.parse_args()

    checkpoint_root = args.checkpoint_root or args.private_root / "checkpoints"
    datasets, source = _load_counted_datasets(
        private_root_path=args.private_root,
        checkpoint_root=checkpoint_root,
    )
    collection_audit = audit_strategic_navigation_collection(datasets)
    if not collection_audit.public_dict()["model_development_admitted"]:
        raise StrategicModelFitError(
            f"counted collection is not admitted: {collection_audit.public_dict()}"
        )
    training = tuple(
        example
        for dataset in datasets
        if dataset.partition == "train"
        for example in dataset.examples
    )
    validation = tuple(
        example
        for dataset in datasets
        if dataset.partition == "validation"
        for example in dataset.examples
    )
    model, trials = select_strategic_navigation_model(training, validation)
    training_metrics = evaluate_strategic_navigation_model(model, training)
    validation_metrics = evaluate_strategic_navigation_model(model, validation)

    _atomic_json(args.out_model, model.to_dict())
    model_file_sha256 = hashlib.sha256(args.out_model.read_bytes()).hexdigest()
    model_sha256 = canonical_strategic_navigation_model_sha256(model)
    validation_gate = {
        "accuracy_exceeds_route_cost_baseline": (
            validation_metrics.accuracy
            > validation_metrics.route_cost_baseline_accuracy
        ),
        "minimum_paired_wins": validation_metrics.paired_wins_over_route_cost >= 3,
        "zero_paired_losses": validation_metrics.paired_losses_to_route_cost == 0,
    }
    summary = {
        "schema": "strategic-navigation-model-development-summary-v1",
        "collection": {
            "audit_receipt_sha256": hashlib.sha256(
                COLLECTION_AUDIT.read_bytes()
            ).hexdigest(),
            "collection_source_commit": source.source_commit,
            "examples": len(training) + len(validation),
            "train_examples": len(training),
            "validation_examples": len(validation),
            "sealed_test_examples_opened": 0,
            "admission_audit": collection_audit.public_dict(),
        },
        "feature_schema": {
            "feature_schema_id": model.feature_schema_id,
            "feature_count": len(STRATEGIC_NAVIGATION_FEATURE_NAMES),
            "feature_names": list(STRATEGIC_NAVIGATION_FEATURE_NAMES),
            "candidate_scoring": "shared_per_candidate",
            "candidate_order_used_as_feature": False,
            "title_specific_identity_used_as_feature": False,
        },
        "selection": {
            "role": "development_validation_model_selection",
            "trials": list(trials),
            "sealed_test_used_for_selection": False,
        },
        "model": {
            "model_id": model.model_id,
            "model_sha256": model_sha256,
            "private_model_file_sha256": model_file_sha256,
            "hidden_units": int(model.weights1.shape[1]),
            "training_seed": model.training_seed,
        },
        "training": training_metrics.public_dict(),
        "validation": validation_metrics.public_dict(),
        "sealed_test": {
            "opened": False,
            "evaluated": False,
        },
        "pre_test_gate": {
            **validation_gate,
            "ready_for_external_audit": all(validation_gate.values()),
            "ready_for_sealed_test_after_external_audit": all(
                validation_gate.values()
            ),
            "validation_result_is_final_claim": False,
        },
    }
    _atomic_json(args.out_summary, summary)
    print(
        json.dumps(
            {
                "model_sha256": model_sha256,
                "selected_hidden_units": int(model.weights1.shape[1]),
                "validation_accuracy": validation_metrics.accuracy,
                "validation_route_cost_baseline_accuracy": (
                    validation_metrics.route_cost_baseline_accuracy
                ),
                "validation_paired_wins": (
                    validation_metrics.paired_wins_over_route_cost
                ),
                "validation_paired_losses": (
                    validation_metrics.paired_losses_to_route_cost
                ),
                "ready_for_external_audit": all(validation_gate.values()),
                "sealed_test_opened": False,
            },
            sort_keys=True,
        )
    )
    return 0


def _load_counted_datasets(
    *,
    private_root_path: Path,
    checkpoint_root: Path,
) -> tuple[tuple[CollectedStrategicNavigationDataset, ...], StrategicNavigationExecution]:
    receipt = _object(json.loads(COLLECTION_AUDIT.read_text()), "collection audit")
    if receipt.get("schema") != "strategic-counted-collection-audit-v1":
        raise StrategicModelFitError("counted collection audit schema differs")
    source_row = _object(receipt.get("collection_source"), "collection source")
    source = StrategicNavigationExecution(
        source_bundle_sha256=_text(source_row, "source_bundle_sha256"),
        behavior_configuration_sha256=_text(
            source_row, "behavior_configuration_sha256"
        ),
        objective_graph_sha256=_text(source_row, "objective_graph_sha256"),
        decision_contract_sha256=_text(source_row, "decision_contract_sha256"),
        teacher_execution_sha256=_text(source_row, "teacher_execution_sha256"),
        source_commit=_text(source_row, "git_commit"),
    )
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    if registry.registry_sha256 != source_row.get("registry_sha256"):
        raise StrategicModelFitError("scenario registry differs from collection receipt")
    headers: dict[str, tuple[str, Mapping[str, object]]] = {}
    for directory in private_root_path.glob("red-scen-*"):
        if (
            not directory.is_dir()
            or directory.name.startswith("red-scen-reh-")
            or directory.name.endswith(".partial")
        ):
            continue
        episode_path = directory / "episode.jsonl"
        if not episode_path.is_file():
            continue
        with episode_path.open() as handle:
            header = _object(json.loads(handle.readline()), "episode header")
        metadata = _object(header.get("metadata"), "episode metadata")
        collection = _object(metadata.get("collection"), "episode collection")
        attempt = _object(collection.get("attempt"), "episode attempt")
        if attempt.get("counted") is not True:
            continue
        scenario_row = _object(collection.get("scenario"), "episode scenario")
        scenario_id = _text(scenario_row, "scenario_id")
        if scenario_id in headers:
            raise StrategicModelFitError("counted scenario is duplicated")
        headers[scenario_id] = (
            _text(header, "episode_id"),
            _object(collection.get("capture"), "episode capture"),
        )

    learning = registry.learning_scenarios()
    if set(headers) != {scenario.scenario_id for scenario in learning}:
        raise StrategicModelFitError("counted scenario coverage differs")
    capture_index = _capture_index(checkpoint_root)
    store = open_private_root(private_root_path, repository_root=PROJECT_ROOT)
    datasets = []
    for scenario in learning:
        episode_id, capture_row = headers[scenario.scenario_id]
        key = (
            _text(capture_row, "state_sha256"),
            _text(capture_row, "envelope_sha256"),
            _text(capture_row, "checkpoint_id"),
        )
        state_path, envelope_path = capture_index[key]
        capture = load_captured_progress(envelope_path, state_path=state_path)
        assignment = registry.learning_assignment(
            scenario.scenario_id,
            capture=capture,
            execution=source,
        )
        if assignment.episode_id != episode_id:
            raise StrategicModelFitError("counted assignment identity differs")
        datasets.append(
            load_assigned_strategic_navigation_episode(
                store.open_episode(episode_id),
                assignment=assignment,
            )
        )
    return tuple(datasets), source


def _capture_index(
    checkpoint_root: Path,
) -> dict[tuple[str, str, str], tuple[Path, Path]]:
    result: dict[tuple[str, str, str], tuple[Path, Path]] = {}
    for envelope_path in checkpoint_root.rglob("*.state.json"):
        state_path = Path(str(envelope_path)[:-5])
        if not state_path.is_file():
            continue
        raw = _object(json.loads(envelope_path.read_text()), "capture envelope")
        key = (
            _text(raw, "state_sha256"),
            canonical_sha256(raw),
            _text(raw, "checkpoint_id"),
        )
        result.setdefault(key, (state_path, envelope_path))
    return result


def _object(value: object, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise StrategicModelFitError(f"{subject} must be an object")
    return value


def _text(value: Mapping[str, object], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise StrategicModelFitError(f"{key} must be non-empty text")
    return result


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
