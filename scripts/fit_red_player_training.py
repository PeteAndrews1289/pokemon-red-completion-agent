#!/usr/bin/env python3
"""Fit a declared native Red player batch without opening an emulator."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from pokemon_red_completion.collection_protocol import working_source_bundle_sha256
from pokemon_red_completion.private_artifacts import open_private_root
from pokemon_red_completion.provenance import (
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_player_incremental_fit import fit_incremental_registered_results
from pokemon_red_completion.red_player_model import (
    RedPlayerModelRecord,
    load_player_goal_model_record,
    load_player_goal_model_record_bytes,
)
from pokemon_red_completion.red_player_training_fit import (
    RedPlayerEpisodeInput,
    fit_red_player_update,
)
from pokemon_red_completion.red_player_training_plan import RedPlayerTrainingPlan
from pokemon_red_completion.registered_collection import REGISTERED_OBJECTIVE

ROOT = Path(__file__).resolve().parents[1]


def _behavior_resolver(store, prior):
    def resolve(expected):
        if expected == prior.model.model_sha256:
            return prior
        for prefix in ("rpr-model", "rp-model"):
            record = store.find_sealed_record(
                f"{prefix}-{expected}", expected_kind="red_player_model"
            )
            if record is not None:
                return load_player_goal_model_record_bytes(
                    record.read_bytes(), expected_model_sha256=expected
                )
        raise ValueError("prior registered behavior model is missing")
    return resolve


def _registered_results(declarations: list[str]) -> tuple[dict[str, object], ...]:
    """Authenticate the entire new batch before fitting; never admit measured-only rows."""
    results = []
    episode_ids = set()

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate registered result field")
            result[key] = value
        return result

    for declaration in declarations:
        path, expected = declaration.rsplit(":", 1)
        if re.fullmatch(r"[0-9a-f]{64}", expected) is None:
            raise ValueError("registered result digest is invalid")
        payload = Path(path).read_bytes()
        if hashlib.sha256(payload).hexdigest() != expected:
            raise ValueError("registered result digest differs")
        result = json.loads(payload, object_pairs_hook=unique)
        if (
            not isinstance(result, dict)
            or result.get("schema") not in {
                "pokemon.red.regional-acquisition-result.v1",
                "pokemon.red.regional-goal-step-result.v1",
            }
            or result.get("objective") != REGISTERED_OBJECTIVE
            or result.get("independent_evaluation") is not False
            or not isinstance(result.get("episode_id"), str)
            or not result["episode_id"]
        ):
            raise ValueError("registered result requires a native TRAIN episode")
        if result["episode_id"] in episode_ids:
            raise ValueError("registered result episode is duplicated")
        episode_ids.add(result["episode_id"])
        results.append(result)
    return tuple(results)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-artifact-root", type=Path, required=True)
    parser.add_argument("--prior-model-record", type=Path, required=True)
    parser.add_argument("--expected-prior-model-sha256", required=True)
    batch = parser.add_mutually_exclusive_group(required=True)
    batch.add_argument(
        "--episode",
        action="append",
        help="episode-id:expected-manifest-sha256; include every declared episode",
    )
    batch.add_argument(
        "--registered-result",
        action="append",
        help="result-path:sha256; every new native TRAIN result; clean local source permitted",
    )
    args = parser.parse_args()
    source = detect_source_identity(ROOT, include_untracked=True)
    require_clean_source(source)
    if not args.registered_result:
        require_published_source(ROOT, source)
    assert source.git_commit is not None
    store = open_private_root(
        args.private_artifact_root, repository_root=ROOT, allow_same_device=True
    )
    prior = load_player_goal_model_record(
        args.prior_model_record, expected_model_sha256=args.expected_prior_model_sha256
    )
    if args.registered_result:
        if not isinstance(prior, RedPlayerModelRecord) or prior.objective != REGISTERED_OBJECTIVE:
            raise ValueError("registered batch requires a registered prior model")
        results = _registered_results(args.registered_result)

        # Existing typed admission authenticates the prospective TRAIN plans,
        # sampled actions, outcomes and complete mixed-checkpoint prior corpus.
        # Historical measured rows are retained, not authorized as new inputs.
        result = fit_incremental_registered_results(
            store,
            prior=prior,
            results=results,
            resolve=_behavior_resolver(store, prior),
            source_commit=source.git_commit,
            source_bundle_sha256=working_source_bundle_sha256(ROOT),
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
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
