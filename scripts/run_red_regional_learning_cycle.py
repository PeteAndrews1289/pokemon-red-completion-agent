#!/usr/bin/env python3
"""Bounded collect/fit/continue using existing source choices and immutable saves.

No automatic retries: by default a failed step stops after its outcome is fitted.
An explicit opt-in permits a fresh choice after verified safe search exhaustion.
An exception preserves existing episode/choice artifacts and aborts the cycle.
The second step must restore the first step's actual checkpoint and fitted model.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, cast

import run_red_regional_source_choice as source

from pokemon_red_completion.red_player_incremental_fit import (
    BehaviorRecord,
    fit_incremental_regional_result,
    load_prior_player_inventory,
)
from pokemon_red_completion.red_player_model import (
    RedPlayerModelRecord,
    load_player_goal_model_record,
    load_player_goal_model_record_bytes,
)


def _parser() -> argparse.ArgumentParser:
    parser = source.base._parser()
    parser.add_argument("--learning-steps", type=int, choices=(1, 2, 3, 4), default=2)
    parser.add_argument("--continue-after-search-exhaustion", action="store_true")
    parser.add_argument("--behavior-model-record", nargs=2, action="append", default=[],
                        metavar=("SHA256", "PATH"))
    return parser


def _safe_exhausted_search(parent: dict[str, Any]) -> bool:
    """Only the existing verified, unchanged-collection failure permits replanning."""
    steps = parent.get("steps")
    if not isinstance(steps, list) or len(steps) != 1:
        return False
    step = steps[0]
    if not isinstance(step, dict):
        return False
    before, after = step.get("collection_before"), step.get("collection_after")
    return (
        step.get("status") == "failed"
        and step.get("failure_reason") == "search_exhausted"
        # Travel and failed throws legitimately change location/resources. The
        # provider's typed SEARCH_EXHAUSTED verification already requires a
        # settled field and living party; the next source runner rechecks them.
        # Preserve the full collection, not a fictitious cost-free game state.
        and type(step.get("semantic_state_changed")) is bool
        and isinstance(before, dict) and before == after
        and type(before.get("undeclared_specimen_losses")) is int
        and before.get("undeclared_specimen_losses") == 0
    )


def _run(args: argparse.Namespace) -> dict[str, object]:
    if type(args.learning_steps) is not int or not 1 <= args.learning_steps <= 4:
        raise ValueError("learning cycle step bound differs")
    if not args.train_player or args.decision_limit != 1 or not args.completion_dose:
        raise ValueError("learning cycle requires bounded single-choice training")
    continue_search = getattr(args, "continue_after_search_exhaustion", False)
    if type(continue_search) is not bool:
        raise ValueError("search continuation declaration must be boolean")
    initial = source.base._prepare(args)
    if initial.continuation is None or not isinstance(initial.causal_record, RedPlayerModelRecord):
        raise ValueError("learning cycle requires a retained native model and saved endpoint")
    if initial.output_path.exists():
        raise ValueError("learning cycle output exists; do not replay")
    overrides: dict[str, BehaviorRecord] = {}
    for expected, path in args.behavior_model_record:
        if expected in overrides:
            raise ValueError("behavior model declaration is duplicated")
        overrides[expected] = load_player_goal_model_record(
            Path(path), expected_model_sha256=expected,
        )

    def resolve(expected: str) -> BehaviorRecord:
        if expected in overrides:
            return overrides[expected]
        registered = initial.private_root.find_sealed_record(
            f"rp-model-{expected}", expected_kind="red_player_model",
        )
        if registered is None:
            raise ValueError("recorded behavior model needs an explicit declaration")
        return load_player_goal_model_record_bytes(
            registered.read_bytes(), expected_model_sha256=expected,
        )

    # Fail before controller input if any retained behavior model is unavailable.
    load_prior_player_inventory(initial.private_root, initial.causal_record, resolve)
    current = argparse.Namespace(**vars(args))
    original = initial.output_path
    results: list[dict[str, object]] = []
    stop = "step_limit"
    for ordinal in range(1, args.learning_steps + 1):
        current.pair_id = f"{args.pair_id}-{ordinal:02d}"
        current.training_seed = args.training_seed + ordinal - 1
        current.out = original.with_name(f"{original.stem}-{ordinal:02d}-parent.json")
        ready = source.base._prepare(current)
        if ready.source_commit != initial.source_commit:
            raise ValueError("learning cycle source changed")
        assert isinstance(ready.causal_record, RedPlayerModelRecord)
        _observed, candidates, _menu = source.inspect_sources(ready, allow_no_choice=True)
        if len(candidates) < 2:
            stop = "no_genuine_source_choice"
            break
        # Existing runner records the actual sampled source before any input.
        outcome = source._run(current)
        source.base._write_exclusive(
            original.with_name(f"{original.stem}-{ordinal:02d}-source.json"), outcome,
        )
        fitted = fit_incremental_regional_result(
            ready.private_root, prior=ready.causal_record, result=outcome, resolve=resolve,
            source_commit=ready.source_commit, source_bundle_sha256=ready.source_bundle_sha256,
        )
        source.base._write_exclusive(
            original.with_name(f"{original.stem}-{ordinal:02d}-fit.json"), fitted,
        )
        results.append({"ordinal": ordinal, "outcome": outcome, "fit": fitted})
        parent = cast(dict[str, Any], outcome["parent_episode"])
        failed = len(parent["steps"]) != 1 or parent["steps"][0]["status"] != "succeeded"
        if failed and not (continue_search and _safe_exhausted_search(parent)):
            stop = "failed_step_retained_and_fitted"
            break
        model = cast(dict[str, str], fitted["model"])
        current.expected_living_dex_model_sha256 = model["model_sha256"]
        current.living_dex_model_record = (
            args.private_artifact_root / f"rp-model-{model['model_sha256']}" / "record.json"
        )
        current.continue_from_checkpoint = [*current.continue_from_checkpoint,
            [outcome["episode_id"], outcome["checkpoint_sha256"]]]
        selected = cast(str, outcome["selected_source"])
        current.regional_transitions = [*current.regional_transitions,
                                       selected, f"discovery:{selected}"]
    summary = {
        "schema": "pokemon.red.regional-learning-cycle.v1", "steps": results,
        "declared_maximum_steps": args.learning_steps, "stop_reason": stop,
        "source_commit": initial.source_commit,
        "starting_model_sha256": initial.model_sha256,
        "maximum_controller_actions": args.learning_steps * 30_000,
        "maximum_emulator_frames": args.learning_steps * 3_000_000,
        "independent_evaluation": False, "automatic_retry": False,
        "continue_after_search_exhaustion": continue_search,
        "sealed_red_accesses": 0, "crystal_accesses": 0, "full_game_replays": 0,
    }
    source.base._write_exclusive(original, summary)
    return summary


if __name__ == "__main__":
    import json
    print(json.dumps(_run(_parser().parse_args()), indent=2, sort_keys=True))
