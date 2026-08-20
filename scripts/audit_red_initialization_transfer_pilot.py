#!/usr/bin/env python3
"""Compare Red and zero initialization on already-open Red development data.

This is a same-title power-calibration pilot, not a transfer result.  It opens
no ROM, save state, Crystal context, or sealed Red destination case.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import replace
from pathlib import Path

from pokemon_red_completion.evaluation_design import paired_one_sided_exact_p
from pokemon_red_completion.goal_manager import GoalKind, GoalManagerExample
from pokemon_red_completion.goal_manager_context_catalog import (
    parse_goal_manager_context_catalog,
)
from pokemon_red_completion.goal_manager_dataset import (
    admit_goal_manager_collection,
    load_assigned_goal_manager_episode,
)
from pokemon_red_completion.goal_manager_model import (
    GoalManagerLinearModel,
    canonical_goal_manager_model_sha256,
    goal_manager_adaptation_configuration,
    goal_manager_prior_adaptation_configuration,
)
from pokemon_red_completion.goal_manager_protocol import (
    load_committed_goal_manager_registry_at_revision,
)
from pokemon_red_completion.private_artifacts import open_private_root

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PILOT_BUDGETS = (9, 18, 27)
LOW_SHOT_BUDGETS = (0, 2, 3, 6, 9)


class RedInitializationPilotError(RuntimeError):
    """Raised when the retained development evidence does not authenticate."""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--source-model", type=Path, required=True)
    parser.add_argument("--source-summary", type=Path, required=True)
    args = parser.parse_args(argv)

    source_payload = args.source_model.read_bytes()
    source_document = _mapping(json.loads(source_payload), "source model")
    source_model = GoalManagerLinearModel.from_dict(source_document)
    source_summary_payload = args.source_summary.read_bytes()
    source_summary = _mapping(json.loads(source_summary_payload), "source summary")
    summary_model = _mapping(source_summary.get("model"), "source summary model")
    canonical_model_sha256 = canonical_goal_manager_model_sha256(source_model)
    if (
        summary_model.get("canonical_sha256") != canonical_model_sha256
        or summary_model.get("file_sha256") != hashlib.sha256(source_payload).hexdigest()
    ):
        raise RedInitializationPilotError("source model differs from its fit summary")

    source_collection = _mapping(
        source_summary.get("collection"), "source summary collection"
    )
    source_commit = source_collection.get("collection_source_commit")
    if not isinstance(source_commit, str) or not source_commit:
        raise RedInitializationPilotError("source summary commit is absent")
    registry = load_committed_goal_manager_registry_at_revision(
        PROJECT_ROOT, source_commit
    )
    catalog_payload = args.context_catalog.read_bytes()
    catalog = parse_goal_manager_context_catalog(catalog_payload, registry)
    store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
    datasets = {
        slot.slot_id: load_assigned_goal_manager_episode(
            store.open_episode(registry.assignment(slot.slot_id).episode_id),
            registry.assignment(slot.slot_id),
            context_catalog=catalog,
        )
        for slot in registry.slots
    }
    corpus = admit_goal_manager_collection(registry, catalog, datasets)
    adaptation_order = _balanced_adaptation_order(corpus.train_examples)
    validation = tuple(corpus.validation_examples)
    if len(adaptation_order) < PILOT_BUDGETS[-1] or len(validation) != 27:
        raise RedInitializationPilotError("Red development corpus shape differs")

    scratch_initialization = source_model.zero_weight_comparator()
    results: list[dict[str, object]] = []
    prior_results: list[dict[str, object]] = []
    for budget in PILOT_BUDGETS:
        prefix = tuple(
            replace(row, partition="adaptation")
            for row in adaptation_order[:budget]
        )
        red_initialized = source_model.fine_tune(prefix)
        scratch = scratch_initialization.fine_tune(prefix)
        results.append(
            {
                "budget": budget,
                "red_initialized_model_sha256": canonical_goal_manager_model_sha256(
                    red_initialized
                ),
                "scratch_model_sha256": canonical_goal_manager_model_sha256(scratch),
                **_paired_metrics(red_initialized, scratch, validation),
            }
        )
        red_prior = source_model.adapt_from_prior(prefix)
        scratch_prior = scratch_initialization.adapt_from_prior(prefix)
        prior_results.append(
            {
                "budget": budget,
                "red_initialized_model_sha256": canonical_goal_manager_model_sha256(
                    red_prior
                ),
                "scratch_model_sha256": canonical_goal_manager_model_sha256(
                    scratch_prior
                ),
                **_paired_metrics(red_prior, scratch_prior, validation),
            }
        )

    low_shot_results: list[dict[str, object]] = []
    prior_low_shot_results: list[dict[str, object]] = []
    first_round = tuple(adaptation_order[: len(GoalKind)])
    for rotation in range(len(GoalKind)):
        rotated = first_round[rotation:] + first_round[:rotation]
        for budget in LOW_SHOT_BUDGETS:
            if budget == 0:
                red_initialized = source_model
                scratch = scratch_initialization
            else:
                prefix = tuple(
                    replace(row, partition="adaptation")
                    for row in rotated[:budget]
                )
                red_initialized = source_model.fine_tune(prefix)
                scratch = scratch_initialization.fine_tune(prefix)
            metrics = _paired_metrics(red_initialized, scratch, validation)
            low_shot_results.append(
                {
                    "rotation": rotation,
                    "budget": budget,
                    "adaptation_goal_kinds": [
                        row.selected_kind.value for row in rotated[:budget]
                    ],
                    "red_correct": metrics["red_correct"],
                    "scratch_correct": metrics["scratch_correct"],
                    "paired": metrics["paired"],
                }
            )
            if budget == 0:
                red_prior = source_model
                scratch_prior = scratch_initialization
            else:
                red_prior = source_model.adapt_from_prior(prefix)
                scratch_prior = scratch_initialization.adapt_from_prior(prefix)
            prior_metrics = _paired_metrics(red_prior, scratch_prior, validation)
            prior_low_shot_results.append(
                {
                    "rotation": rotation,
                    "budget": budget,
                    "adaptation_goal_kinds": [
                        row.selected_kind.value for row in rotated[:budget]
                    ],
                    "red_correct": prior_metrics["red_correct"],
                    "scratch_correct": prior_metrics["scratch_correct"],
                    "paired": prior_metrics["paired"],
                }
            )

    receipt = {
        "schema": "pokemon-red-initialization-power-pilot.v1",
        "status": "development_only",
        "purpose": (
            "estimate paired win, loss, and tie behavior for prospective transfer "
            "power design without opening a target title"
        ),
        "source": {
            "collection_source_commit": registry.execution.source_commit,
            "registry_sha256": registry.registry_sha256,
            "context_catalog_sha256": hashlib.sha256(catalog_payload).hexdigest(),
            "source_model_canonical_sha256": canonical_model_sha256,
            "source_model_file_sha256": hashlib.sha256(source_payload).hexdigest(),
            "source_summary_file_sha256": hashlib.sha256(
                source_summary_payload
            ).hexdigest(),
        },
        "design": {
            "adaptation_budgets": list(PILOT_BUDGETS),
            "adaptation_order": "one_example_per_goal_kind_per_round",
            "same_examples_order_optimizer_and_normalizer": True,
            "differing_field": "initial_weights",
            "optimizer": goal_manager_adaptation_configuration(),
            "evaluation_contexts": len(validation),
            "independent_evaluation_lineages": len(
                {row.root_lineage_id for row in validation}
            ),
            "evaluation_goal_kind_counts": {
                kind.value: sum(row.selected_kind is kind for row in validation)
                for kind in GoalKind
            },
        },
        "results": results,
        "prior_preserving_results": {
            "configuration": goal_manager_prior_adaptation_configuration(),
            "results": prior_results,
        },
        "low_shot_rotation_pilot": {
            "budgets": list(LOW_SHOT_BUDGETS),
            "rotations": len(GoalKind),
            "same_validation_contexts_reused_across_rotations": True,
            "results": low_shot_results,
        },
        "prior_preserving_low_shot_rotation_pilot": {
            "budgets": list(LOW_SHOT_BUDGETS),
            "rotations": len(GoalKind),
            "same_validation_contexts_reused_across_rotations": True,
            "results": prior_low_shot_results,
        },
        "limitations": [
            "This is a same-title Red development pilot, not Crystal transfer evidence.",
            "The Red source model was trained on the source-title training distribution.",
            "The 27 validation contexts have already been used for development claims.",
            "Pilot rates inform design but do not replace a declared smallest useful effect.",
        ],
        "sealed_red_destination_contexts_opened": 0,
        "crystal_contexts_opened": 0,
        "promotion_eligible": False,
        "private_path_fields": 0,
    }
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


def _balanced_adaptation_order(
    examples: Iterable[GoalManagerExample],
) -> tuple[GoalManagerExample, ...]:
    by_kind: defaultdict[GoalKind, list[GoalManagerExample]] = defaultdict(list)
    for row in examples:
        if row.partition != "train" or row.teacher_choice_target is None:
            raise RedInitializationPilotError(
                "pilot adaptation source must be successful training evidence"
            )
        by_kind[row.selected_kind].append(row)
    if set(by_kind) != set(GoalKind):
        raise RedInitializationPilotError("pilot adaptation lacks a goal kind")
    minimum = min(len(by_kind[kind]) for kind in GoalKind)
    return tuple(
        by_kind[kind][ordinal]
        for ordinal in range(minimum)
        for kind in GoalKind
    )


def _paired_metrics(
    red_initialized: GoalManagerLinearModel,
    scratch: GoalManagerLinearModel,
    examples: tuple[GoalManagerExample, ...],
) -> dict[str, object]:
    wins = losses = both_correct = both_wrong = 0
    red_correct = scratch_correct = 0
    per_kind: dict[str, dict[str, int]] = {
        kind.value: {
            "contexts": 0,
            "red_correct": 0,
            "scratch_correct": 0,
            "wins": 0,
            "losses": 0,
        }
        for kind in GoalKind
    }
    for row in examples:
        target = row.teacher_choice_target
        if row.partition != "validation" or target is None:
            raise RedInitializationPilotError(
                "pilot evaluation requires successful validation evidence"
            )
        red_ok = red_initialized.predict(row.question) == target
        scratch_ok = scratch.predict(row.question) == target
        red_correct += int(red_ok)
        scratch_correct += int(scratch_ok)
        wins += int(red_ok and not scratch_ok)
        losses += int(not red_ok and scratch_ok)
        both_correct += int(red_ok and scratch_ok)
        both_wrong += int(not red_ok and not scratch_ok)
        kind = per_kind[row.selected_kind.value]
        kind["contexts"] += 1
        kind["red_correct"] += int(red_ok)
        kind["scratch_correct"] += int(scratch_ok)
        kind["wins"] += int(red_ok and not scratch_ok)
        kind["losses"] += int(not red_ok and scratch_ok)
    contexts = len(examples)
    return {
        "contexts": contexts,
        "red_correct": red_correct,
        "scratch_correct": scratch_correct,
        "red_accuracy": red_correct / contexts,
        "scratch_accuracy": scratch_correct / contexts,
        "paired": {
            "wins": wins,
            "losses": losses,
            "both_correct": both_correct,
            "both_wrong": both_wrong,
            "one_sided_exact_p": paired_one_sided_exact_p(wins, losses),
            "empirical_win_probability": wins / contexts,
            "empirical_loss_probability": losses / contexts,
            "empirical_tie_probability": (both_correct + both_wrong) / contexts,
        },
        "per_goal_kind": per_kind,
    }


def _mapping(value: object, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise RedInitializationPilotError(f"{subject} must be an object")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
