#!/usr/bin/env python3
"""Propose a capture destination, then let the native goal policy choose the task.

Only the actual native goal outcome is eligible for fitting. The sampled source
proposal is retained for inspection/history, never independently labelled here.
The older destination-only runner remains unchanged in scope.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from dataclasses import replace
from typing import Any, cast

import run_red_regional_source_choice as source

from pokemon_red_completion.red_player_training_dataset import load_red_player_training_episode
from pokemon_red_completion.red_player_training_plan import RedPlayerTrainingPlan
from pokemon_red_completion.red_regional_goal_proposal import (
    REGIONAL_PROPOSAL_KIND,
    REGIONAL_PROPOSAL_SCHEMA,
    regional_proposal_record_id,
    regional_proposal_seed,
    regional_proposal_source_effort,
)


def _run(args: argparse.Namespace) -> dict[str, object]:
    ready = source.base._prepare(args)
    if (
        ready.decision_limit != 1
        or not ready.save_terminal_checkpoints
        or ready.training_plan is None
        or ready.causal_record is None
    ):
        raise ValueError("regional goal step needs one saved training decision")
    episode_id = cast(str, ready.training_plan.document["episode_id"])
    proposal_id = regional_proposal_record_id(episode_id)
    if ready.private_root.find_sealed_record(proposal_id, expected_kind=REGIONAL_PROPOSAL_KIND):
        raise ValueError("regional goal proposal already consumed; never resample")
    observed, candidates, menu = source.inspect_sources(ready, allow_no_choice=True)
    selection = None
    if len(candidates) >= 2:
        selection = source.sample_regional_acquisition(
            ready.causal_record.model,
            menu,
            seed=regional_proposal_seed(cast(int, ready.training_plan.document["seed"])),
        )
        selected = candidates[cast(int, selection["selected_candidate_index"])]
    else:
        # A unique destination is a binding, not a learned source choice.
        # With none, retain the native profile and its non-capture goals.
        selected = candidates[0] if candidates else None
    profile = selected.profile if selected is not None else ready.profile
    ready = replace(
        ready,
        profile=profile,
        training_plan=RedPlayerTrainingPlan(
            {
                **ready.training_plan.document,
                "profile_sha256": profile.profile_sha256,
            }
        ),
    )
    preflight = source.base._action_free_preflight(ready)
    assert ready.training_plan is not None and ready.causal_record is not None
    if preflight.get("status") not in {"ready", "ready_for_forced_bridge"}:
        raise ValueError("regional parent is not ready for bounded goal selection")
    proposal = ready.private_root.publish_sealed_record(
        proposal_id,
        kind=REGIONAL_PROPOSAL_KIND,
        record={
            "schema": REGIONAL_PROPOSAL_SCHEMA,
            "episode_id": episode_id,
            "parent_plan": dict(ready.training_plan.document),
            "profile_sha256": profile.profile_sha256,
            "profile": json.loads(
                source.build_red_goal_context_profile_payload(
                    profile_id=profile.profile_id,
                    providers=tuple(
                        (
                            spec.kind,
                            spec.mechanic,
                            cast(Mapping[str, object], source._thaw(spec.parameters)),
                        )
                        for spec in profile.providers
                    ),
                )
            ),
            "selected_source": selected.source_id if selected is not None else None,
            "source_mode": "sampled"
            if selection is not None
            else ("unique_binding" if selected is not None else "no_source"),
            "before": observed.public_dict(),
            "menu": menu.policy_dict() if menu is not None else None,
            "selection": selection,
            "candidate_sources": [row.source_id for row in candidates],
            "source_proposal_fitted": False,
            "controller_input_before_commit": False,
            "parent_overridden": False,
            "independent_evaluation": False,
        },
    )
    ready = replace(ready, regional_proposal_record_sha256=proposal.summary.record_sha256)
    assert ready.training_plan is not None and ready.causal_record is not None
    print(
        json.dumps(
            {
                "status": "regional_proposal_committed_before_input",
                "selected_source": selected.source_id if selected is not None else None,
                "proposal_record_sha256": proposal.summary.record_sha256,
                "parent_will_choose_goal": True,
                "source_proposal_fitted": False,
            }
        ),
        flush=True,
    )
    # Do not copy the greedy preflight choice into the run. The existing native
    # training authority makes and logs its actual exploratory goal decision.
    result = source.base._run_prepared(ready)
    parent = cast(dict[str, Any], result["episode"])
    if len(parent["steps"]) != 1 or parent["steps"][0]["status"] not in {"succeeded", "failed"}:
        raise ValueError("regional parent did not retain one settled goal")
    checkpoint = cast(list[dict[str, str]], result["terminal_checkpoints"])[0]["record_sha256"]
    effort = regional_proposal_source_effort(ready.private_root, episode_id, checkpoint)
    dataset = load_red_player_training_episode(
        ready.private_root,
        episode_id=episode_id,
        expected_manifest_sha256=cast(str, result["trajectory_manifest_sha256"]),
        plan=ready.training_plan,
        behavior_model=ready.causal_record.model,
    )
    return {
        "schema": "pokemon.red.regional-goal-step-result.v1",
        **(
            {"objective": ready.training_plan.document["objective"]}
            if ready.training_plan.document.get("objective") is not None
            else {}
        ),
        "episode_id": episode_id,
        "model_sha256": ready.model_sha256,
        "manifest_sha256": result["trajectory_manifest_sha256"],
        "checkpoint_sha256": checkpoint,
        "proposal_record_sha256": proposal.summary.record_sha256,
        "proposed_source": selected.source_id if selected is not None else None,
        "candidate_count": len(candidates),
        "parent_episode": parent,
        "eligible_examples": len(dataset.examples),
        "curriculum_outcomes": len(dataset.curriculum_examples),
        "eligible_source_examples": 0,
        "source_proposal_fitted": False,
        "source_acquisition_attempted": effort is not None,
        "parent_overridden": False,
        "model_fitted": False,
        "independent_evaluation": False,
    }


def main(argv: list[str] | None = None) -> int:
    result = _run(source.base._parser().parse_args(argv))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
