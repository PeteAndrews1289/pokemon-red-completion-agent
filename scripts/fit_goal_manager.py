#!/usr/bin/env python3
"""Fit the portable goal manager from the complete authenticated Red curriculum."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import uuid
from contextlib import suppress
from pathlib import Path

from pokemon_red_completion.goal_manager_context_catalog import (
    parse_goal_manager_context_catalog,
)
from pokemon_red_completion.goal_manager_dataset import (
    admit_goal_manager_collection,
    load_assigned_goal_manager_episode,
)
from pokemon_red_completion.goal_manager_model import (
    GOAL_MANAGER_FEATURE_NAMES,
    GoalManagerLinearModel,
    canonical_goal_manager_model_sha256,
    evaluate_goal_manager_model,
    goal_manager_fit_configuration,
)
from pokemon_red_completion.goal_manager_protocol import (
    load_committed_goal_manager_registry,
)
from pokemon_red_completion.private_artifacts import open_private_root

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class GoalManagerFitError(RuntimeError):
    """Raised before a partial, unauthenticated or weak corpus can be fit."""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--out-model", type=Path, required=True)
    parser.add_argument("--out-summary", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.out_model.resolve() == args.out_summary.resolve():
        parser.error("model and summary outputs must differ")

    registry = load_committed_goal_manager_registry(PROJECT_ROOT)
    context_catalog = parse_goal_manager_context_catalog(
        args.context_catalog.read_bytes(),
        registry,
    )
    store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
    model_destination = _private_output_path(
        args.out_model,
        private_root=args.private_root,
        subject="model",
    )
    summary_destination = _private_output_path(
        args.out_summary,
        private_root=args.private_root,
        subject="summary",
    )
    datasets = {
        slot.slot_id: load_assigned_goal_manager_episode(
            store.open_episode(registry.assignment(slot.slot_id).episode_id),
            registry.assignment(slot.slot_id),
            context_catalog=context_catalog,
        )
        for slot in registry.slots
    }
    corpus = admit_goal_manager_collection(registry, context_catalog, datasets)
    fit_configuration = goal_manager_fit_configuration()
    model = GoalManagerLinearModel.fit(corpus.train_examples)
    training = evaluate_goal_manager_model(model, corpus.train_examples)
    validation = evaluate_goal_manager_model(model, corpus.validation_examples)
    validation_gate = _validation_gate(validation.public_dict())

    model_payload = _canonical_line(model.to_dict())
    model_sha256 = canonical_goal_manager_model_sha256(model)
    summary = {
        "schema": "pokemon-core-goal-manager-development-fit-v1",
        "collection": {
            **corpus.public_dict(),
            "collection_source_commit": registry.execution.source_commit,
            "registry_sha256": registry.registry_sha256,
            "teacher_execution_sha256": registry.execution.teacher_execution_sha256,
        },
        "feature_schema": {
            "candidate_order_used_as_feature": False,
            "candidate_scoring": "shared_per_candidate",
            "feature_count": len(GOAL_MANAGER_FEATURE_NAMES),
            "feature_names": list(GOAL_MANAGER_FEATURE_NAMES),
            "private_binding_identity_used_as_feature": False,
            "title_identity_used_as_feature": False,
        },
        "fit": fit_configuration,
        "model": {
            "canonical_sha256": model_sha256,
            "file_sha256": hashlib.sha256(model_payload).hexdigest(),
            "model_id": model.model_id,
        },
        "training": training.public_dict(),
        "validation": validation.public_dict(),
        "validation_gate": validation_gate,
        "held_out_titles": {
            "opened": False,
            "evaluated": False,
            "next_environment": "pokemon.mainline:crystal",
        },
        "private_path_fields": 0,
    }
    _publish_private_bytes(model_destination, model_payload)
    _publish_private_bytes(summary_destination, _canonical_line(summary))
    print(
        json.dumps(
            {
                "model_sha256": model_sha256,
                "train_examples": len(corpus.train_examples),
                "validation_examples": len(corpus.validation_examples),
                "validation_accuracy": validation.accuracy,
                "ready_for_held_out_title_evaluation": validation_gate["passed"],
                "held_out_titles_opened": False,
            },
            sort_keys=True,
        )
    )
    return 0


def _validation_gate(metrics: dict[str, object]) -> dict[str, object]:
    baselines = metrics.get("baselines")
    selected_kind = metrics.get("selected_kind_accuracy")
    accuracy = metrics.get("accuracy")
    if not isinstance(baselines, dict) or not isinstance(selected_kind, dict):
        raise GoalManagerFitError("goal-manager validation metrics are incomplete")
    if not isinstance(accuracy, (int, float)) or isinstance(accuracy, bool):
        raise GoalManagerFitError("goal-manager validation accuracy is invalid")

    def comparison(name: str) -> dict[str, object]:
        value = baselines.get(name)
        if not isinstance(value, dict):
            raise GoalManagerFitError(f"goal-manager {name} baseline is absent")
        return value

    fixed = comparison("fixed_priority")
    pressure = comparison("highest_pressure")
    effort = comparison("lowest_effort")

    def baseline_accuracy(value: dict[str, object]) -> float:
        result = value.get("accuracy")
        if not isinstance(result, (int, float)) or isinstance(result, bool):
            raise GoalManagerFitError("goal-manager baseline accuracy is invalid")
        return float(result)

    def paired(value: dict[str, object], key: str) -> float:
        comparison_value = value.get("paired_comparison")
        if not isinstance(comparison_value, dict):
            raise GoalManagerFitError("goal-manager paired comparison is absent")
        result = comparison_value.get(key)
        if not isinstance(result, (int, float)) or isinstance(result, bool):
            raise GoalManagerFitError("goal-manager paired comparison is invalid")
        return float(result)

    checks = {
        "accuracy_at_least_0_70": float(accuracy) >= 0.70,
        "beats_fixed_priority_accuracy": float(accuracy) > baseline_accuracy(fixed),
        "beats_lowest_effort_accuracy": float(accuracy) > baseline_accuracy(effort),
        "fixed_priority_paired_p_below_0_05": paired(fixed, "two_sided_exact_p") < 0.05,
        "lowest_effort_paired_p_below_0_05": paired(effort, "two_sided_exact_p") < 0.05,
        "not_worse_than_highest_pressure_paired": (
            paired(pressure, "wins") >= paired(pressure, "losses")
        ),
        "every_goal_kind_accuracy_at_least_0_50": bool(selected_kind)
        and all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and float(value) >= 0.50
            for value in selected_kind.values()
        ),
    }
    return {**checks, "passed": all(checks.values())}


def _canonical_line(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _private_output_path(path: Path, *, private_root: Path, subject: str) -> Path:
    if not path.is_absolute():
        raise GoalManagerFitError(f"goal-manager {subject} output must be an absolute path")
    root = Path(os.path.abspath(private_root))
    destination = Path(os.path.abspath(path))
    if destination.parent != root:
        raise GoalManagerFitError(
            f"goal-manager {subject} output must be a direct child of the private root"
        )
    if destination.name.startswith(".") or not destination.name:
        raise GoalManagerFitError(f"goal-manager {subject} output name is invalid")
    return destination


def _publish_private_bytes(path: Path, payload: bytes) -> None:
    """Publish mode-0600 bytes without replacing different prior evidence."""

    try:
        metadata = path.lstat()
    except FileNotFoundError:
        metadata = None
    except OSError as error:
        raise GoalManagerFitError("goal-manager output cannot be inspected") from error
    if metadata is not None:
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise GoalManagerFitError("goal-manager output must be a regular file")
        try:
            existing = path.read_bytes()
        except OSError as error:
            raise GoalManagerFitError("goal-manager output cannot be read") from error
        if existing != payload:
            raise GoalManagerFitError(
                "goal-manager output already exists with different content"
            )
        return

    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.partial")
    descriptor = -1
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.link(temporary, path, follow_symlinks=False)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except FileExistsError:
        if not path.is_file() or path.is_symlink() or path.read_bytes() != payload:
            raise GoalManagerFitError(
                "goal-manager output already exists with different content"
            ) from None
    except OSError as error:
        raise GoalManagerFitError("goal-manager output cannot be published") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        with suppress(FileNotFoundError):
            temporary.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
