#!/usr/bin/env python3
"""Fit a declared native Red player batch without opening an emulator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pokemon_red_completion.collection_protocol import working_source_bundle_sha256
from pokemon_red_completion.private_artifacts import open_private_root
from pokemon_red_completion.provenance import (
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_player_model import load_player_goal_model_record
from pokemon_red_completion.red_player_training_fit import (
    RedPlayerEpisodeInput,
    fit_red_player_update,
)
from pokemon_red_completion.red_player_training_plan import RedPlayerTrainingPlan

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-artifact-root", type=Path, required=True)
    parser.add_argument("--prior-model-record", type=Path, required=True)
    parser.add_argument("--expected-prior-model-sha256", required=True)
    parser.add_argument(
        "--episode",
        action="append",
        required=True,
        help="episode-id:expected-manifest-sha256; include every declared episode",
    )
    args = parser.parse_args()
    source = detect_source_identity(ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(ROOT, source)
    assert source.git_commit is not None
    store = open_private_root(
        args.private_artifact_root, repository_root=ROOT, allow_same_device=True
    )
    prior = load_player_goal_model_record(
        args.prior_model_record, expected_model_sha256=args.expected_prior_model_sha256
    )
    requests = []
    for declaration in args.episode:
        episode_id, expected_manifest = declaration.split(":", 1)
        reader = store.open_episode(episode_id)
        if reader.manifest_sha256 != expected_manifest:
            raise ValueError("declared training episode digest differs")
        plan = RedPlayerTrainingPlan(reader.read_header()["metadata"]["player_training_plan"])
        # This small CLI is for a single behavior checkpoint's batch. The typed
        # fitter supports a full mixed-checkpoint history, but never guesses it.
        if plan.document["model_sha256"] != prior.model.model_sha256:
            raise ValueError("batch behavior model differs from the supplied checkpoint")
        requests.append(RedPlayerEpisodeInput(plan, episode_id, expected_manifest, prior))
    result = fit_red_player_update(
        store,
        prior=prior,
        episodes=tuple(requests),
        source_commit=source.git_commit,
        source_bundle_sha256=working_source_bundle_sha256(ROOT),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
