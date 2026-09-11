#!/usr/bin/env python3
"""Bounded collect/fit/continue using existing source choices and immutable saves.

No automatic retries: by default a failed step stops after its outcome is fitted.
An explicit opt-in permits a fresh choice after verified safe search exhaustion.
An exception preserves existing episode/choice artifacts and aborts the cycle.
The second step must restore the first step's actual checkpoint and fitted model.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, cast

import run_red_regional_goal_step as goal
import run_red_regional_source_choice as source

from pokemon_red_completion.red_bounded_player import RedNoAvailableGoalError
from pokemon_red_completion.red_player_incremental_fit import (
    BehaviorRecord,
    fit_incremental_goal_results,
    fit_incremental_regional_result,
    fit_incremental_registered_results,
    load_prior_player_inventory,
)
from pokemon_red_completion.red_player_model import (
    RedPlayerModelRecord,
    load_player_goal_model_record,
    load_player_goal_model_record_bytes,
)


def _parser() -> argparse.ArgumentParser:
    parser = source.base._parser()
    parser.add_argument("--learning-steps", type=int, choices=range(1, 17), default=2)
    parser.add_argument(
        "--continue-after-status-recovery", action="store_true",
        help="Permit a fresh bounded choice after a verified degraded-status terminal.",
    )
    parser.add_argument(
        "--maximum-cycle-seconds",
        type=int,
        help="Stop between bounded episodes; required for more than four steps.",
    )
    parser.add_argument("--continue-after-search-exhaustion", action="store_true")
    parser.add_argument(
        "--automatic-goals",
        action="store_true",
        help="Choose native tasks and capture destinations; fit real outcomes.",
    )
    parser.add_argument(
        "--owned-evolution-objectives", action="store_true",
        help="Offer stock-derived native level evolutions alongside automatic capture goals.",
    )
    parser.add_argument(
        "--owned-evolution-fly-transport", action="store_true",
        help="Prospectively qualify and retain Fly/indoor access for new owned evolution goals.",
    )
    parser.add_argument(
        "--behavior-model-record", nargs=2, action="append", default=[], metavar=("SHA256", "PATH")
    )
    return parser


def _safe_exhausted_search(parent: dict[str, Any]) -> bool:
    """Only the existing verified, unchanged-collection failure permits replanning."""
    return _safe_failed_terminal(parent, "search_exhausted")


def _safe_failed_terminal(parent: dict[str, Any], reason: str) -> bool:
    """Replan from typed, verified terminals; never retry or hide failed costs."""
    steps = parent.get("steps")
    if not isinstance(steps, list) or len(steps) != 1:
        return False
    step = steps[0]
    if not isinstance(step, dict):
        return False
    before, after = step.get("collection_before"), step.get("collection_after")
    registered_safe = False
    if (
        isinstance(before, dict)
        and before.get("schema") == "pokemon.core.registered-collection-checkpoint.v1"
    ):
        from pokemon_red_completion.registered_checkpoint import RegisteredCollectionCheckpoint

        RegisteredCollectionCheckpoint.from_public(before)
        registered_safe = True
    return (
        step.get("status") == "failed"
        and step.get("failure_reason") == reason
        # Travel and failed throws legitimately change location/resources. The
        # provider's typed SEARCH_EXHAUSTED verification already requires a
        # settled field and living party; the next source runner rechecks them.
        # Preserve the full collection, not a fictitious cost-free game state.
        and type(step.get("semantic_state_changed")) is bool
        and isinstance(before, dict)
        and before == after
        and (
            registered_safe
            or (
                type(before.get("undeclared_specimen_losses")) is int
                and before.get("undeclared_specimen_losses") == 0
            )
        )
    )


def _run(args: argparse.Namespace) -> dict[str, object]:
    if type(args.learning_steps) is not int or not 1 <= args.learning_steps <= 16:
        raise ValueError("learning cycle step bound differs")
    maximum_seconds = getattr(args, "maximum_cycle_seconds", None)
    if maximum_seconds is not None and (
        type(maximum_seconds) is not int or not 1 <= maximum_seconds <= 7200
    ):
        raise ValueError("learning cycle time bound differs")
    if args.learning_steps > 4 and maximum_seconds is None:
        raise ValueError("extended learning cycle needs a time bound")
    started = time.monotonic()

    def deadline_reached() -> bool:
        return maximum_seconds is not None and time.monotonic() - started >= maximum_seconds

    if not args.train_player or args.decision_limit != 1 or not args.completion_dose:
        raise ValueError("learning cycle requires bounded single-choice training")
    continue_search = getattr(args, "continue_after_search_exhaustion", False)
    continue_status = getattr(args, "continue_after_status_recovery", False)
    if type(continue_status) is not bool:
        raise ValueError("status continuation declaration must be boolean")
    if type(continue_search) is not bool:
        raise ValueError("search continuation declaration must be boolean")
    automatic_goals = getattr(args, "automatic_goals", False)
    if type(automatic_goals) is not bool:
        raise ValueError("automatic goal declaration must be boolean")
    if continue_status and not automatic_goals:
        raise ValueError("status continuation requires native recovery choices")
    # Prepare the first episode directly.  The older implementation prepared an
    # otherwise unused aggregate identity, prepared episode 1 again, and then its
    # child runner prepared episode 1 a third time.  No controller input separates
    # those snapshots, so one authenticated readiness is the stronger binding.
    original = args.out.resolve()
    first = argparse.Namespace(**vars(args))
    first.pair_id = f"{args.pair_id}-01"
    first.training_seed = args.training_seed
    first.out = original.with_name(f"{original.stem}-01-parent.json")
    initial = source.base._prepare(first)
    if initial.continuation is None or not isinstance(initial.causal_record, RedPlayerModelRecord):
        raise ValueError("learning cycle requires a retained native model and saved endpoint")
    original = source.base._new_external_output(original, rom_path=initial.rom_path)
    overrides: dict[str, BehaviorRecord] = {}
    for expected, path in args.behavior_model_record:
        if expected in overrides:
            raise ValueError("behavior model declaration is duplicated")
        overrides[expected] = load_player_goal_model_record(
            Path(path),
            expected_model_sha256=expected,
        )

    def resolve(expected: str) -> BehaviorRecord:
        if expected in overrides:
            return overrides[expected]
        registered = initial.private_root.find_sealed_record(
            f"rp-model-{expected}",
            expected_kind="red_player_model",
        )
        if registered is None:
            registered = initial.private_root.find_sealed_record(
                f"rpr-model-{expected}",
                expected_kind="red_player_model",
            )
        if registered is None:
            raise ValueError("recorded behavior model needs an explicit declaration")
        return load_player_goal_model_record_bytes(
            registered.read_bytes(),
            expected_model_sha256=expected,
        )

    # Fail before controller input if any retained behavior model is unavailable.
    registered_objective = getattr(initial, "registration_policy", None) is not None
    owned_evolutions = getattr(args, "owned_evolution_objectives", False)
    owned_fly = getattr(args, "owned_evolution_fly_transport", False)
    if type(owned_fly) is not bool or (owned_fly and not owned_evolutions):
        raise ValueError("owned evolution Fly requires owned evolution objectives")
    if type(owned_evolutions) is not bool or (
        owned_evolutions and (not automatic_goals or not registered_objective)
    ):
        raise ValueError("owned evolution objectives require automatic registered goals")
    if not registered_objective or initial.causal_record.objective:
        load_prior_player_inventory(initial.private_root, initial.causal_record, resolve)
    current = first
    results: list[dict[str, object]] = []
    pending_support: list[dict[str, object]] = []
    stop = "step_limit"
    for ordinal in range(1, args.learning_steps + 1):
        if deadline_reached():
            stop = "time_limit_before_next_step"
            break
        if ordinal == 1:
            ready = initial
        else:
            current.pair_id = f"{args.pair_id}-{ordinal:02d}"
            current.training_seed = args.training_seed + ordinal - 1
            current.out = original.with_name(f"{original.stem}-{ordinal:02d}-parent.json")
            ready = source.base._prepare(current)
        evolution_inventory = None
        if owned_evolutions:
            from inspect_red_owned_evolution import inspect_owned_evolution

            evolution_inventory = (
                inspect_owned_evolution(ready, fly_transport=True)
                if owned_fly else inspect_owned_evolution(ready)
            )
            transition = evolution_inventory["selected_transition"]
            if transition is not None:
                current.regional_transitions = [*current.regional_transitions, transition]
                if owned_fly:
                    # The exact prospective transitions used in admission must
                    # also bind execution and every subsequent saved ancestor.
                    current.regional_transitions += ["evolution-fly", "indoor-fly-departure"]
                ready = source.base._prepare(current)
        if (
            ready.source_commit != initial.source_commit
            or ready.source_bundle_sha256 != initial.source_bundle_sha256
        ):
            raise ValueError("learning cycle source changed")
        assert isinstance(ready.causal_record, RedPlayerModelRecord)
        observed, candidates, menu = source.inspect_sources(
            ready, allow_no_choice=True, include_menu=True,
        )
        regional = True
        if automatic_goals:
            try:
                preflight = source.base._action_free_preflight(ready)
            except RedNoAvailableGoalError:
                # The retained local source may be exhausted while a newly
                # inventoried regional source is executable. Its runner checks
                # the selected profile before input; do not invent a local goal.
                if not candidates:
                    stop = "no_executable_native_goal"
                    break
                preflight = {"status": "regional_candidates_available", "available_goal_kinds": []}
            kinds = preflight.get("available_goal_kinds", [])
            if not isinstance(kinds, list) or any(not isinstance(kind, str) for kind in kinds):
                raise ValueError("automatic collection goal inventory differs")
            if "advance_story" in kinds:
                stop = "story_outside_collection_scope"
                break
            if not candidates and preflight.get("status") not in {
                "ready",
                "ready_for_forced_bridge",
            }:
                stop = "no_executable_collection_or_support_goal"
                break
            regional = kinds in ([], ["acquire_species"]) and len(candidates) >= 2
        elif len(candidates) < 2:
            stop = "no_genuine_source_choice"
            break
        if deadline_reached():
            stop = "time_limit_before_next_step"
            break
        # Existing runner records the actual sampled source before any input.
        inspected = (observed, candidates, menu)
        outcome = (
            source._run_prepared(ready, inspected=inspected)
            if regional
            else goal._run_prepared(ready, inspected=inspected)
        )
        source.base._write_exclusive(
            original.with_name(f"{original.stem}-{ordinal:02d}-source.json"),
            outcome,
        )
        common: dict[str, Any] = dict(
            prior=ready.causal_record,
            resolve=resolve,
            source_commit=ready.source_commit,
            source_bundle_sha256=ready.source_bundle_sha256,
        )
        if registered_objective:
            pending_support.append(outcome)
            fitted = fit_incremental_registered_results(
                ready.private_root,
                results=tuple(pending_support),
                **common,
            )
        elif regional:
            fitted = fit_incremental_regional_result(
                ready.private_root,
                result=outcome,
                **common,
            )
        else:
            pending_support.append(outcome)
            fitted = fit_incremental_goal_results(
                ready.private_root,
                results=tuple(pending_support),
                **common,
            )
        source.base._write_exclusive(
            original.with_name(f"{original.stem}-{ordinal:02d}-fit.json"),
            fitted,
        )
        results.append(
            {
                "ordinal": ordinal,
                "outcome": outcome,
                "fit": fitted,
                "selection_scope": "regional_destination" if regional else "native_goal",
                "continuation_source_rule": "warp_safe_v1" if registered_objective else "legacy",
                **({"owned_evolution_inventory": evolution_inventory}
                   if evolution_inventory is not None else {}),
            }
        )
        # Preserve exact preparation with every completed step, even when a
        # later preflight aborts the aggregate cycle or this outcome failed.
        source.base._write_exclusive(
            original.with_name(f"{original.stem}-{ordinal:02d}-step.json"), results[-1]
        )
        parent = cast(dict[str, Any], outcome["parent_episode"])
        print(
            json.dumps(
                {
                    "status": "learning_step_settled",
                    "ordinal": ordinal,
                    "maximum_steps": args.learning_steps,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "selection_scope": results[-1]["selection_scope"],
                    "episode_id": outcome["episode_id"],
                    "new_model": fitted.get("model"),
                    "parent_episode": parent,
                }
            ),
            flush=True,
        )
        failed = len(parent["steps"]) != 1 or parent["steps"][0]["status"] != "succeeded"
        if failed and not (
            (continue_search and _safe_exhausted_search(parent))
            or (continue_status and _safe_failed_terminal(parent, "recovery_required"))
        ):
            stop = "failed_step_retained_and_fitted"
            break
        if "model" in fitted:
            model = cast(dict[str, str], fitted["model"])
            current.expected_living_dex_model_sha256 = model["model_sha256"]
            current.living_dex_model_record = (
                args.private_artifact_root
                / f"{'rpr-model' if registered_objective else 'rp-model'}-{model['model_sha256']}"
                / "record.json"
            )
            # Zero-row support remains in the immutable episode artifacts.
            # Never relabel it as a destination-choice example.
            pending_support.clear()
        current.continue_from_checkpoint = [
            *current.continue_from_checkpoint,
            [outcome["episode_id"], outcome["checkpoint_sha256"]],
        ]
        selected = cast(str | None, outcome.get("selected_source", outcome.get("proposed_source")))
        if selected is not None:
            current.regional_transitions = [
                *current.regional_transitions,
                f"warp-safe:{selected}" if registered_objective else selected,
                f"discovery:{selected}",
            ]
    summary: dict[str, object] = {
        "schema": "pokemon.red.regional-learning-cycle.v1",
        **(
            {"objective": "pokemon.registered-collection.v1"}
            if registered_objective
            else {}
        ),
        "steps": results,
        "declared_maximum_steps": args.learning_steps,
        "stop_reason": stop,
        "maximum_cycle_seconds": maximum_seconds,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "deadline_scope": "between_bounded_episodes_no_inflight_interruption",
        "source_commit": initial.source_commit,
        "starting_model_sha256": initial.model_sha256,
        "maximum_controller_actions": args.learning_steps * 30_000,
        "maximum_emulator_frames": args.learning_steps * 3_000_000,
        "independent_evaluation": False,
        "automatic_retry": False,
        "continue_after_search_exhaustion": continue_search,
        "continue_after_status_recovery": continue_status,
        "automatic_goals": automatic_goals,
        "owned_evolution_objectives": owned_evolutions,
        "pending_support_episode_ids": [row["episode_id"] for row in pending_support],
        "sealed_red_accesses": 0,
        "crystal_accesses": 0,
        "full_game_replays": 0,
    }
    source.base._write_exclusive(original, summary)
    return summary


if __name__ == "__main__":
    print(json.dumps(_run(_parser().parse_args()), indent=2, sort_keys=True))
