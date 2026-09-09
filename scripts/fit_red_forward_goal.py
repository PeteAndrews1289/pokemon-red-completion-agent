#!/usr/bin/env python3
"""Fit a separate shadow goal model from explicitly opted-in native Red episodes.

This opens no emulator and neither replaces nor promotes the existing player.
Provide the complete intended batch, including failures and censored episodes.
The output is an immutable private artifact, not a new authority or a sealed test.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pokemon_red_completion.collection_protocol import working_source_bundle_sha256  # noqa: E402
from pokemon_red_completion.forward_goal_learning import fit_forward_goal  # noqa: E402
from pokemon_red_completion.forward_goal_records import (  # noqa: E402
    _mapping,
    restore_forward_goal_plan,
)
from pokemon_red_completion.private_artifacts import open_private_root  # noqa: E402
from pokemon_red_completion.provenance import (  # noqa: E402
    canonical_sha256,
    detect_source_identity,
    require_clean_source,
)
from pokemon_red_completion.red_forward_dataset import load_red_forward_episode  # noqa: E402
from pokemon_red_completion.red_player_model import load_player_goal_model_record  # noqa: E402
from pokemon_red_completion.red_player_training_plan import RedPlayerTrainingPlan  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-artifact-root", type=Path, required=True)
    parser.add_argument("--behavior-model-record", type=Path, required=True)
    parser.add_argument("--expected-behavior-model-sha256", required=True)
    parser.add_argument(
        "--episode",
        action="append",
        required=True,
        help="episode-id:expected-manifest-sha256; the complete declared batch",
    )
    parser.add_argument("--ridge", type=float, default=1.0)
    parser.add_argument("--importance-cap", type=float, default=10.0)
    args = parser.parse_args(argv)
    source = detect_source_identity(ROOT, include_untracked=True)
    require_clean_source(source)
    model = load_player_goal_model_record(
        args.behavior_model_record,
        expected_model_sha256=args.expected_behavior_model_sha256,
    )
    store = open_private_root(
        args.private_artifact_root, repository_root=ROOT, allow_same_device=True
    )
    requests, outcomes, seen = [], [], set()
    for request in args.episode:
        episode_id, digest = request.split(":", 1)
        if episode_id in seen:
            raise ValueError("forward-goal batch repeats an episode")
        seen.add(episode_id)
        reader = store.open_episode(episode_id)
        if reader.manifest_sha256 != digest:
            raise ValueError("forward-goal episode manifest differs")
        metadata = _mapping(reader.read_header()["metadata"])
        plan = RedPlayerTrainingPlan(_mapping(metadata["player_training_plan"]))
        forward = restore_forward_goal_plan(metadata["forward_goal_plan"])
        objective = cast(str, metadata["forward_story_objective"])
        outcome = load_red_forward_episode(
            store,
            episode_id=episode_id,
            expected_manifest_sha256=digest,
            training_plan=plan,
            behavior_model=model.model,
            forward_plan=forward,
            objective_id=objective,
        )
        outcomes.append(outcome)
        requests.append(
            {
                "episode_id": episode_id,
                "manifest_sha256": digest,
                "training_plan_sha256": plan.plan_sha256,
                "forward_plan_sha256": forward.sha256,
            }
        )
    fitted = fit_forward_goal(outcomes, ridge=args.ridge, importance_cap=args.importance_cap)
    document = {
        "schema": "pokemon.red.forward-goal-shadow-fit.v1",
        "source_commit": source.git_commit,
        "source_bundle_sha256": working_source_bundle_sha256(ROOT),
        "behavior_model_sha256": model.model.model_sha256,
        "episodes": sorted(requests, key=lambda row: row["episode_id"]),
        "outcomes": [
            row.public_dict()
            for row in sorted(
                outcomes,
                key=lambda row: row.choice.decision_sha256,
            )
        ],
        "model": fitted.model.public_dict(),
        "model_sha256": fitted.model.sha256,
        "recorded_roots": fitted.recorded_roots,
        "settled_roots": fitted.settled_roots,
        "distinct_selected_inputs": fitted.distinct_inputs,
        "training_mse_before": list(fitted.mse_before),
        "training_mse_after": list(fitted.mse_after),
        "authority": "unqualified-shadow",
        "player_model_changed": False,
        "independent_evaluation": False,
    }
    record = store.publish_sealed_record(
        f"red-forward-fit-{canonical_sha256(document)}",
        kind="red_forward_goal_shadow_fit",
        record=document,
    )
    print(
        json.dumps(
            {
                "record_sha256": record.summary.record_sha256,
                "model_sha256": fitted.model.sha256,
                "settled_examples": fitted.model.settled_examples,
                "censored_examples": fitted.model.censored_examples,
                "recorded_roots": fitted.recorded_roots,
                "settled_roots": fitted.settled_roots,
                "authority": "unqualified-shadow",
                "player_model_changed": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
