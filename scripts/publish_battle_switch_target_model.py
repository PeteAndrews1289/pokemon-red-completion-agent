#!/usr/bin/env python3
"""Rebuild and privately publish one prospectively qualified switch-target model."""

from __future__ import annotations

import argparse
import json
import uuid
from collections.abc import Mapping
from pathlib import Path

from pokemon_red_completion.battle_control_labels import load_battle_control_artifact
from pokemon_red_completion.battle_switch_target import SWITCH_TARGET_FEATURE_SCHEMA_ID
from pokemon_red_completion.battle_switch_target_model import (
    canonical_switch_target_model_sha256,
)
from pokemon_red_completion.battle_switch_target_training import (
    fit_preassigned_switch_target_candidate,
)
from pokemon_red_completion.private_artifacts import open_private_root
from pokemon_red_completion.provenance import (
    detect_source_identity,
    require_clean_source,
    require_published_source,
)

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--training-labels", type=Path, action="append", required=True)
    parser.add_argument("--validation-labels", type=Path, action="append", required=True)
    parser.add_argument("--prospective-receipt", type=Path, required=True)
    parser.add_argument("--expected-model-sha256", required=True)
    parser.add_argument("--hidden-units", type=int, default=2)
    parser.add_argument("--epochs", type=int, default=1000)
    parser.add_argument("--learning-rate", type=float, default=0.01)
    parser.add_argument("--l2", type=float, default=0.003)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)

    try:
        source = detect_source_identity(REPOSITORY_ROOT, include_untracked=True)
        require_clean_source(source)
        require_published_source(REPOSITORY_ROOT, source)
        training = tuple(load_battle_control_artifact(path) for path in args.training_labels)
        validation = tuple(load_battle_control_artifact(path) for path in args.validation_labels)
        candidate = fit_preassigned_switch_target_candidate(
            training,
            validation,
            hidden_units=args.hidden_units,
            epochs=args.epochs,
            learning_rate=args.learning_rate,
            l2=args.l2,
            seed=args.seed,
        )
        model_payload = candidate.model.to_dict()
        model_sha256 = canonical_switch_target_model_sha256(candidate.model)
        if model_sha256 != args.expected_model_sha256:
            raise ValueError("rebuilt candidate does not match the frozen model digest")
        prospective = _load_prospective_receipt(args.prospective_receipt, model_sha256)
        test_artifact_id = _text(prospective, "artifact_id")
        if test_artifact_id in {
            *(dataset.artifact_id for dataset in training),
            *(dataset.artifact_id for dataset in validation),
        }:
            raise ValueError("prospective test lineage overlaps development lineages")

        private_root = open_private_root(
            args.private_root,
            repository_root=REPOSITORY_ROOT,
        )
        artifact_id = f"red-battle-switch-target-model-{uuid.uuid4().hex}"
        writer = private_root.begin_artifact(
            artifact_id,
            kind="battle_switch_target_model",
        )
        with writer:
            writer.append(
                "model",
                {
                    "record_type": "battle_switch_target_model",
                    "model": model_payload,
                    "model_sha256": model_sha256,
                    "source": source.public_dict(),
                },
            )
            writer.append(
                "training",
                {
                    "record_type": "battle_switch_target_training",
                    "feature_schema_id": SWITCH_TARGET_FEATURE_SCHEMA_ID,
                    "split": "complete_rollout_lineages",
                    "training_artifacts": [
                        {
                            "artifact_id": dataset.artifact_id,
                            "manifest_sha256": dataset.manifest_sha256,
                        }
                        for dataset in training
                    ],
                    "validation_artifacts": [
                        {
                            "artifact_id": dataset.artifact_id,
                            "manifest_sha256": dataset.manifest_sha256,
                        }
                        for dataset in validation
                    ],
                    "configuration": {
                        "epochs": args.epochs,
                        "hidden_units": args.hidden_units,
                        "l2": args.l2,
                        "learning_rate": args.learning_rate,
                        "seed": args.seed,
                        "weighting": "equal_total_weight_per_battle_plan",
                    },
                },
            )
            writer.append(
                "qualification",
                {
                    "record_type": "battle_switch_target_qualification",
                    "model_sha256": model_sha256,
                    "development": candidate.public_summary(),
                    "prospective_test": prospective,
                    "shadow_authority": True,
                    "causal_trial_authority": True,
                    "deployment_authority": False,
                    "reason_deployment_false": ("fresh_shadow_and_isolated_causal_replay_required"),
                },
            )
        print(
            json.dumps(
                {
                    "artifact": writer.summary.public_dict(),
                    "claim": (
                        "The exact prospectively qualified target head is authenticated for "
                        "shadow and isolated causal trials; deployment authority remains false."
                    ),
                    "model_sha256": model_sha256,
                    "shadow_authority": True,
                    "causal_trial_authority": True,
                    "deployment_authority": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except OSError:
        parser.error("Switch-target publication failed while reading or writing private data.")
    except Exception as error:
        parser.error(f"Switch-target publication failed: {type(error).__name__}: {error}")
    raise AssertionError("argparse error unexpectedly returned")


def _load_prospective_receipt(path: Path, model_sha256: str) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("prospective receipt is not an object")
    frozen = _mapping(value.get("frozen_candidate"), "frozen_candidate")
    lineage = _mapping(value.get("test_lineage"), "test_lineage")
    evaluation = _mapping(value.get("target_evaluation"), "target_evaluation")
    integrity = _mapping(value.get("integrity"), "integrity")
    examples = evaluation.get("examples")
    correct = evaluation.get("learned_correct")
    if (
        value.get("schema") != "pokemon-switch-target-prospective-prefix-test-v1"
        or frozen.get("canonical_payload_sha256") != model_sha256
        or frozen.get("hyperparameters_changed_before_test") is not False
        or frozen.get("test_evaluations") != 1
        or type(examples) is not int  # noqa: E721
        or type(correct) is not int  # noqa: E721
        or examples < 1
        or correct != examples
        or evaluation.get("all_battle_plans_perfect") is not True
        or lineage.get("task_complete_prefix") is not True
        or integrity.get("candidate_refit_after_test") is not False
        or integrity.get("partial_labels_used_for_training") is not False
        or integrity.get("counted_campaign_root_consumed") is not False
        or integrity.get("deployment_authority") is not False
    ):
        raise ValueError("prospective receipt does not authorize shadow publication")
    return {
        "artifact_id": _text(lineage, "artifact_id"),
        "manifest_sha256": _sha256(lineage, "manifest_sha256"),
        "schedule_sha256": _sha256(lineage, "schedule_sha256"),
        "harness_seed": _integer(lineage, "harness_seed"),
        "examples": examples,
        "correct": correct,
        "accuracy": evaluation.get("learned_accuracy"),
        "cross_entropy": evaluation.get("learned_cross_entropy"),
        "baseline_correct": evaluation.get("deterministic_baseline_correct"),
        "baseline_accuracy": evaluation.get("deterministic_baseline_accuracy"),
        "test_evaluations": frozen.get("test_evaluations"),
    }


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"prospective receipt {label} is invalid")
    return value


def _text(value: Mapping[str, object], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise ValueError(f"prospective receipt {key} is invalid")
    return result


def _sha256(value: Mapping[str, object], key: str) -> str:
    result = _text(value, key)
    if len(result) != 64 or any(character not in "0123456789abcdef" for character in result):
        raise ValueError(f"prospective receipt {key} is not a sha256 digest")
    return result


def _integer(value: Mapping[str, object], key: str) -> int:
    result = value.get(key)
    if type(result) is not int or result < 0:  # noqa: E721
        raise ValueError(f"prospective receipt {key} is invalid")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
