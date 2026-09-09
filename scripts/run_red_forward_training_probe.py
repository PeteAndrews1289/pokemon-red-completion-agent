#!/usr/bin/env python3
"""One bounded first-choice learner probe on an authenticated TRAIN context.

This does not fit, enter sealed evaluation, or promote a full player. Its first
actor and frozen old continuation have distinct identities and records.
"""

from __future__ import annotations

import argparse
import json
from contextlib import ExitStack
from dataclasses import replace

import run_paired_red_bounded_player as base

from pokemon_red_completion.red_forward_probe import load_red_forward_probe


def _parser() -> argparse.ArgumentParser:
    parser = base._parser()
    parser.description = __doc__
    parser.add_argument("--probe-fit-record-id", required=True)
    parser.add_argument("--probe-fit-record-sha256", required=True)
    parser.add_argument("--probe-model-sha256", required=True)
    parser.add_argument("--probe-tail-seed", required=True, type=int)
    parser.add_argument("--probe-read-only", action="store_true")
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    ready = base._prepare(args)
    if not ready.save_terminal_checkpoints:
        raise ValueError("forward probe requires terminal and failure retention")
    probe = load_red_forward_probe(
        ready.private_root,
        record_id=args.probe_fit_record_id,
        expected_record_sha256=args.probe_fit_record_sha256,
        expected_model_sha256=args.probe_model_sha256,
        tail_seed=args.probe_tail_seed,
    )
    base._require_forward_probe_scope(ready, probe)
    episode_id = base._episode_id(ready.pair_id, base.FORWARD_PROBE_ARM_ID)
    claim_id = "forward-probe-claim-" + ready.pair_id
    if ready.private_root.find_sealed_record(claim_id, expected_kind="red_forward_probe_claim"):
        raise ValueError("forward probe already claimed; never retry")
    # The existing preflight authenticates current mechanics without any input.
    # It does not copy its old-policy diagnostic recommendation into the probe.
    scoped = replace(
        ready,
        forward_story_objective=probe.objective_id,
        forward_resource_budget=probe.fitted_plan.max_resources,
    )
    preflight = base._action_free_preflight(scoped)
    available = preflight.get("available_goal_count")
    if preflight["status"] != "ready" or type(available) is not int or available < 2:
        raise ValueError("forward probe needs a genuine current choice")
    declaration = {
        "schema": "pokemon.red.forward-first-choice-probe-declaration.v1",
        "episode_id": episode_id,
        "source_commit": ready.source_commit,
        "source_bundle_sha256": ready.source_bundle_sha256,
        "state_sha256": ready.capture.state_sha256,
        "profile_sha256": ready.profile.profile_sha256,
        "root_lineage_id": ready.continuation_root_lineage_id,
        "partition": "train",
        "probe": probe.header(),
        "no_retry_after_claim": True,
        "model_fitted": False,
        "independent_evaluation": False,
        "read_only": bool(args.probe_read_only),
        "preflight": preflight,
    }
    if args.probe_read_only:
        return {
            **declaration,
            "controller_actions": 0,
            "emulator_frames": 0,
            "episode_created": False,
            "first_actor_predictions": 0,
        }
    before = {str(i): base._sha256(p) for i, p in enumerate(ready.protected_paths)}
    adjacent = base.rom_adjacent_artifacts(ready.rom_path)
    claim = ready.private_root.publish_sealed_record(
        claim_id,
        kind="red_forward_probe_claim",
        record=declaration,
    )
    with ExitStack() as resources:
        viewer = None
        if ready.dashboard_port is not None:
            state = base.DashboardState()
            viewer = base.BoundedPlayerDashboard(state, decision_limit=ready.decision_limit)
            dashboard = resources.enter_context(
                base.ProgressDashboardServer(state, port=ready.dashboard_port),
            )
            print(
                json.dumps(
                    {
                        "dashboard_url": dashboard.url,
                        "status": "first-choice-training-probe-starting",
                    }
                ),
                flush=True,
            )
        arm = base._run_arm(
            ready,
            arm_id=base.FORWARD_PROBE_ARM_ID,
            authority=base._challenger_authority(ready),
            viewer=viewer,
            forward_probe=probe,
        )
    if before != {str(i): base._sha256(p) for i, p in enumerate(ready.protected_paths)}:
        raise ValueError("forward probe changed a protected input")
    if adjacent != base.rom_adjacent_artifacts(ready.rom_path):
        raise ValueError("forward probe wrote a ROM-adjacent artifact")
    checkpoint = ready.private_root.find_sealed_record(
        base.checkpoint_record_id(episode_id),
        expected_kind=base.CHECKPOINT_KIND,
    )
    if checkpoint is None:
        raise ValueError("forward probe terminal checkpoint absent")
    return {
        **declaration,
        "claim_record_sha256": claim.summary.record_sha256,
        "trajectory_manifest_sha256": arm.trajectory_manifest_sha256,
        "checkpoint_sha256": checkpoint.summary.record_sha256,
        "episode": arm.episode.public_dict(),
        "automatic_promotion": False,
        "native_training_admission": False,
        "sealed_red_accesses": 0,
        "crystal_accesses": 0,
        "full_game_replays": 0,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = _run(args)
    base._write_exclusive(args.out, result)
    print(json.dumps(result, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
