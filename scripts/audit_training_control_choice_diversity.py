#!/usr/bin/env python3
"""Measure whether training features beat a candidate-set-only baseline."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from pokemon_red_completion.training_control_dataset import (
    TrainingControlDataset,
    load_training_control_replay,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--train",
        action="append",
        nargs=2,
        metavar=("PATH", "SHA256"),
        required=True,
    )
    parser.add_argument(
        "--validation",
        action="append",
        nargs=2,
        metavar=("PATH", "SHA256"),
        required=True,
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    training = tuple(
        load_training_control_replay(path, expected_sha256=digest)
        for path, digest in args.train
    )
    validation = tuple(
        load_training_control_replay(path, expected_sha256=digest)
        for path, digest in args.validation
    )
    if any(dataset.partition != "train" or not dataset.lineage_qualified for dataset in training):
        parser.error("choice audit training inputs must be qualified training lineages")
    if any(
        dataset.partition != "validation" or not dataset.lineage_qualified
        for dataset in validation
    ):
        parser.error("choice audit validation inputs must be qualified validation lineages")

    training_counts = _candidate_action_counts(training)
    validation_counts = _candidate_action_counts(validation)
    majority = {
        candidates: max(counts, key=lambda action: (counts[action], action))
        for candidates, counts in training_counts.items()
    }
    validation_examples = sum(sum(counts.values()) for counts in validation_counts.values())
    genuine_examples = sum(
        sum(counts.values())
        for candidates, counts in validation_counts.items()
        if "/" in candidates
    )
    correct = 0
    covered = 0
    genuine_correct = 0
    genuine_covered = 0
    for candidates, counts in validation_counts.items():
        examples = sum(counts.values())
        if candidates not in majority:
            continue
        covered += examples
        correct += counts[majority[candidates]]
        if "/" in candidates:
            genuine_covered += examples
            genuine_correct += counts[majority[candidates]]

    candidate_only_accuracy = correct / covered if covered else 0.0
    genuine_candidate_only_accuracy = (
        genuine_correct / genuine_covered if genuine_covered else 0.0
    )
    payload = {
        "schema": "pokemon-training-control-choice-diversity-audit-v1",
        "lineages": [_identity(dataset) for dataset in (*training, *validation)],
        "training_candidate_action_counts": _public_counts(training_counts),
        "validation_candidate_action_counts": _public_counts(validation_counts),
        "training_candidate_majority_policy": dict(sorted(majority.items())),
        "validation_examples": validation_examples,
        "validation_candidate_coverage": covered / validation_examples,
        "validation_candidate_only_accuracy": candidate_only_accuracy,
        "validation_genuine_examples": genuine_examples,
        "validation_genuine_candidate_coverage": (
            genuine_covered / genuine_examples if genuine_examples else 0.0
        ),
        "validation_genuine_candidate_only_accuracy": genuine_candidate_only_accuracy,
        "training_state_dependent_candidate_sets": sorted(
            candidates for candidates, counts in training_counts.items() if len(counts) > 1
        ),
        "validation_state_dependent_candidate_sets": sorted(
            candidates for candidates, counts in validation_counts.items() if len(counts) > 1
        ),
        "candidate_only_baseline_saturates_validation": (
            covered == validation_examples
            and correct == validation_examples
            and genuine_covered == genuine_examples
            and genuine_correct == genuine_examples
        ),
        "state_dependent_choice_demonstrated": any(
            len(counts) > 1 for counts in (*training_counts.values(), *validation_counts.values())
        ),
        "promotion_eligible": False,
    }
    _atomic_json(args.out, payload)
    print(
        json.dumps(
            {
                "validation_candidate_only_accuracy": payload[
                    "validation_candidate_only_accuracy"
                ],
                "validation_genuine_candidate_only_accuracy": payload[
                    "validation_genuine_candidate_only_accuracy"
                ],
            }
        )
    )
    return 0


def _candidate_action_counts(
    datasets: tuple[TrainingControlDataset, ...],
) -> dict[str, Counter[str]]:
    counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for dataset in datasets:
        for example in dataset.examples:
            candidates = "/".join(
                action.value for action in example.observation.candidate_actions
            )
            counts[candidates][example.action.value] += 1
    return dict(counts)


def _public_counts(counts: dict[str, Counter[str]]) -> dict[str, dict[str, int]]:
    return {
        candidates: dict(sorted(actions.items()))
        for candidates, actions in sorted(counts.items())
    }


def _identity(dataset: TrainingControlDataset) -> dict[str, object]:
    return {
        "lineage_id": dataset.lineage_id,
        "partition": dataset.partition,
        "artifact_sha256": dataset.artifact_sha256,
        "state_sha256": dataset.state_sha256,
        "source_commit": dataset.source_commit,
        "source_dirty": dataset.source_dirty,
    }


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
