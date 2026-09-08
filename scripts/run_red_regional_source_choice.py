#!/usr/bin/env python3
"""Choose one useful Red capture destination, then reuse the bounded player.

The existing native goal remains deterministic in this first hierarchical
integration. The separately logged destination choice uses the current value
model with full-support exploration. No automatic retries or model fits.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from typing import Any, cast

import run_paired_red_bounded_player as base

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_search_memory import GoalSearchMemory
from pokemon_red_completion.living_dex_option_value import LivingDexObservedArmExample
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_goal_context_profile import (
    _thaw,
    build_red_goal_context_profile_payload,
)
from pokemon_red_completion.red_goal_manager import RedGoalObservation
from pokemon_red_completion.red_living_dex_causal_adapter import (
    red_living_dex_outcome_from_observations,
)
from pokemon_red_completion.red_player_checkpoint import open_red_player_checkpoint
from pokemon_red_completion.red_player_training_plan import RedPlayerTrainingPlan
from pokemon_red_completion.red_regional_acquisition import (
    enumerate_red_regional_acquisitions,
    regional_acquisition_menu,
    regional_source_memory_key,
    sample_regional_acquisition,
)
from pokemon_red_completion.red_regional_choice_learning import (
    REGIONAL_CHOICE_KIND,
    REGIONAL_CHOICE_SCHEMA,
    REGIONAL_OUTCOME_KIND,
    REGIONAL_OUTCOME_SCHEMA,
    RedRegionalChoiceInput,
    load_red_regional_choice_example,
    regional_choice_record_id,
    regional_outcome_record_id,
)
from pokemon_red_completion.red_regional_goal_proposal import regional_proposal_source_effort


def require_source_attempt_ready(observed: RedGoalObservation) -> None:
    """Refuse an unsafe starting context before source sampling or commitment.

    Keep historical enumeration/fingerprints and actual failed attempts intact.
    This is an admission check, not a replacement for execution-time safety.
    """
    if (
        observed.raw.battle_state or not observed.input_ready
        or not observed.party.members
        or any(member.hp <= 0 for member in observed.party.members)
    ):
        raise ValueError("regional source needs settled party recovery before choice")


def source_search_memory(ready: base._Readiness) -> GoalSearchMemory:
    """Rebuild regional effort from played ancestors, not position-dependent bindings.

    The normal player still preserves its original search ledger unchanged.
    This separate projection covers only explicitly logged regional choices.
    """
    from pokemon_red_completion.red_player_checkpoint import CHECKPOINT_KIND, checkpoint_record_id

    memory = GoalSearchMemory()
    for episode_id, checkpoint_sha in ready.continuation_chain:
        choice = ready.private_root.find_sealed_record(
            regional_choice_record_id(episode_id),
            expected_kind=REGIONAL_CHOICE_KIND,
        )
        if choice is None:
            effort = regional_proposal_source_effort(ready.private_root, episode_id, checkpoint_sha)
            if effort is not None:
                source, objective, exhausted, actions, frames = effort
                memory.record(
                    regional_source_memory_key(source), objective, exhausted=exhausted,
                    actions=actions, frames=frames,
                )
            continue
        outcome = ready.private_root.find_sealed_record(
            regional_outcome_record_id(episode_id),
            expected_kind=REGIONAL_OUTCOME_KIND,
        )
        terminal = ready.private_root.find_sealed_record(
            checkpoint_record_id(episode_id),
            expected_kind=CHECKPOINT_KIND,
        )
        if outcome is None or terminal is None:
            raise ValueError("regional ancestor lacks its settled outcome")
        joined = ready.private_root.open_episode(episode_id)
        metadata = cast(dict[str, object], joined.read_header()["metadata"])
        if (
            terminal.summary.record_sha256 != checkpoint_sha
            or outcome.read()["terminal_checkpoint_sha256"] != checkpoint_sha
            or outcome.read()["choice_record_sha256"] != choice.summary.record_sha256
            or outcome.read()["manifest_sha256"] != joined.manifest_sha256
            or metadata.get("regional_choice_record_sha256")
            != choice.summary.record_sha256
        ):
            raise ValueError("regional ancestor history binding differs")
        document = choice.read()
        candidates = cast(list[dict[str, Any]], document["candidates"])
        selection = cast(dict[str, int], document["selection"])
        selected = candidates[selection["selected_candidate_index"]]
        steps = cast(dict[str, Any], terminal.read()["terminal_result"])["steps"]
        if len(steps) != 1 or steps[0]["status"] not in {"succeeded", "failed"}:
            raise ValueError("regional ancestor did not settle one acquisition")
        step = steps[0]
        memory.record(
            regional_source_memory_key(selected["source_id"]),
            step["collection_before"]["required_specimens_sha256"],
            exhausted=step.get("failure_reason") == "search_exhausted",
            actions=step["actions_executed"],
            frames=step["frames_executed"],
        )
    return memory


def inspect_sources(ready: base._Readiness, *, allow_no_choice: bool = False) -> tuple[Any, ...]:
    """Restore the exact parent and enumerate without predictions or controller input."""
    if ready.continuation is None or ready.training_plan is None or ready.causal_record is None:
        raise ValueError("regional source choice requires an authenticated train continuation")
    world = base._route_world(ready)
    if world is None:
        raise ValueError("regional source choice needs cartridge routing")
    with base.PyBoyAdapter(ready.rom_path, watch=False, speed=None) as emulator:
        emulator.load_state_bytes(ready.capture.state_bytes)
        base._verify_continuation_restore(ready, emulator)
        before, frame = emulator.save_state_bytes(), emulator.frame_count
        controller = base.ReadOnlyController(emulator)
        reader = base.PokemonRedStateReader(controller)
        runtime = base.build_red_goal_context_runtime(
            profile=ready.profile,
            capture=ready.capture,
            emulator=controller,
            reader=reader,
        )
        runtime = replace(
            runtime, remaining_acquisition_demand=ready.remaining_acquisition_demand,
        )
        actions = base.CountingExecutor(
            base.FrameSafeExecutor(
                controller,
                base.DEFAULT_NEW_GAME_TIMING.controller_timing(),
            )
        )
        observed = runtime.adapter.observe()
        candidates = enumerate_red_regional_acquisitions(
            runtime,
            observed,
            actions,
            world,
            maximum_actions=ready.training_plan.maximum_actions,
            maximum_frames=ready.training_plan.maximum_frames,
            routed_recovery=ready.routed_recovery,
            prepare_capture_storage=ready.completion_dose,
        )
        memory = source_search_memory(ready)
        menu = (
            None if allow_no_choice and len(candidates) < 2
            else regional_acquisition_menu(observed, candidates, memory)
        )
        if (
            before != emulator.save_state_bytes()
            or frame != emulator.frame_count
            or (emulator.pressed_buttons or actions.actions_executed)
        ):
            raise ValueError("regional inspection changed the saved game")
        return observed, candidates, menu


def _require_capture_parent(preflight: dict[str, Any]) -> None:
    if preflight.get("status") == "ready_for_forced_bridge" and (
        preflight.get("available_goal_kinds") == ["acquire_species"]
        and preflight.get("model_queries") == 0
    ):
        return
    decision = preflight.get("living_dex_causal_shadow", {}).get("decision", {})
    if decision.get("selected_kind") != GoalKind.ACQUIRE_SPECIES.value or (
        decision.get("mode") not in {"deterministic_unsupported", "deterministic_safety"}
    ):
        raise ValueError("regional parent would override or duplicate the source choice")


def _run(args: argparse.Namespace) -> dict[str, object]:
    ready = base._prepare(args)
    if ready.decision_limit != 1 or not ready.save_terminal_checkpoints:
        raise ValueError("regional pilot requires one saved bounded acquisition")
    assert ready.training_plan is not None and ready.causal_record is not None
    episode_id = cast(str, ready.training_plan.document["episode_id"])
    choice_id = regional_choice_record_id(episode_id)
    if ready.private_root.find_sealed_record(choice_id, expected_kind=REGIONAL_CHOICE_KIND):
        raise ValueError("regional choice identity already consumed; never resample")
    observed, candidates, menu = inspect_sources(ready)
    require_source_attempt_ready(observed)
    selection = sample_regional_acquisition(
        ready.causal_record.model,
        menu,
        seed=cast(int, ready.training_plan.document["seed"]),
    )
    selected = candidates[cast(int, selection["selected_candidate_index"])]
    ready = replace(
        ready,
        profile=selected.profile,
        training_plan=RedPlayerTrainingPlan(
            {
                **ready.training_plan.document,
                "profile_sha256": selected.profile.profile_sha256,
            }
        ),
    )
    _require_capture_parent(base._action_free_preflight(ready))
    declarations = []
    for candidate in candidates:
        profile_bytes = build_red_goal_context_profile_payload(
            profile_id=candidate.profile.profile_id,
            providers=tuple(
                (spec.kind, spec.mechanic, cast(dict[str, object], _thaw(spec.parameters)))
                for spec in candidate.profile.providers
            ),
        )
        declarations.append(
            {
                "source_id": candidate.source_id,
                "profile_sha256": candidate.profile.profile_sha256,
                "profile": json.loads(profile_bytes),
                "estimated_effort": candidate.binding.estimated_effort,
                "estimated_risk": candidate.binding.estimated_risk,
            }
        )
    assert ready.training_plan is not None
    declaration = {
        "schema": REGIONAL_CHOICE_SCHEMA,
        "episode_id": episode_id,
        "parent_plan": dict(ready.training_plan.document),
        "before": observed.public_dict(),
        "menu": menu.policy_dict(),
        "selection": selection,
        "candidates": declarations,
        "controller_input_before_commit": False,
        "independent_evaluation": False,
    }
    record = ready.private_root.publish_sealed_record(
        choice_id,
        kind=REGIONAL_CHOICE_KIND,
        record=declaration,
    )
    choice_sha = record.summary.record_sha256
    ready = replace(ready, regional_choice_record_sha256=choice_sha)
    print(
        json.dumps(
            {
                "status": "source_choice_committed_before_input",
                "candidate_count": len(candidates),
                "selected_source": selected.source_id,
                "selection": selection,
                "choice_record_sha256": choice_sha,
            }
        ),
        flush=True,
    )
    result = base._run_prepared(ready)
    episode = cast(dict[str, Any], result["episode"])
    steps = episode["steps"]
    if (
        len(steps) != 1
        or steps[0]["selected_kind"] != "acquire_species"
        or (steps[0]["status"] not in {"succeeded", "failed"})
    ):
        raise ValueError("source choice did not execute one settled acquisition")
    checkpoint_sha = cast(list[dict[str, str]], result["terminal_checkpoints"])[0]["record_sha256"]
    checkpoint = open_red_player_checkpoint(
        ready.private_root,
        episode_id=episode_id,
        expected_record_sha256=checkpoint_sha,
        original_parent=ready.capture,
        expected_profile_sha256=ready.profile.profile_sha256,
        expected_rom_sha256=ready.rom_sha256,
        expected_context_origin="training",
    )
    terminal_ready = replace(
        ready, capture=checkpoint.capture, continuation=checkpoint, restore_profile=ready.profile,
        restore_routed_recovery=ready.routed_recovery,
        restore_completion_dose=ready.completion_dose,
        restore_remaining_acquisition_demand=ready.remaining_acquisition_demand,
    )
    with base.PyBoyAdapter(ready.rom_path, watch=False, speed=None) as emulator:
        emulator.load_state_bytes(checkpoint.capture.state_bytes)
        base._verify_continuation_restore(terminal_ready, emulator)
        before, frame = emulator.save_state_bytes(), emulator.frame_count
        controller = base.ReadOnlyController(emulator)
        runtime = base.build_red_goal_context_runtime(
            profile=ready.profile,
            capture=checkpoint.capture,
            emulator=controller,
            reader=base.PokemonRedStateReader(controller),
        )
        after = runtime.adapter.observe().public_dict()
        if (
            before != emulator.save_state_bytes()
            or frame != emulator.frame_count
            or (emulator.pressed_buttons)
        ):
            raise ValueError("regional terminal observation changed the game")
    assert ready.training_plan is not None
    outcome = red_living_dex_outcome_from_observations(
        observed.public_dict(),
        after,
        succeeded=steps[0]["status"] == "succeeded",
        actions=episode["total_actions"],
        frames=episode["total_frames"],
        maximum_actions=ready.training_plan.maximum_actions,
        maximum_frames=ready.training_plan.maximum_frames,
    )
    example = LivingDexObservedArmExample(
        canonical_sha256({"schema": REGIONAL_CHOICE_SCHEMA, "choice_record_sha256": choice_sha}),
        "train",
        menu,
        cast(int, selection["selected_candidate_index"]),
        tuple(cast(list[float], selection["probabilities"])),
        outcome,
    )
    outcome_record = ready.private_root.publish_sealed_record(
        regional_outcome_record_id(episode_id),
        kind=REGIONAL_OUTCOME_KIND,
        record={
            "schema": REGIONAL_OUTCOME_SCHEMA,
            "episode_id": episode_id,
            "choice_record_sha256": choice_sha,
            "manifest_sha256": result["trajectory_manifest_sha256"],
            "terminal_checkpoint_sha256": checkpoint_sha,
            "after": after,
            "example": example.public_dict(),
        },
    )
    assert ready.causal_record is not None
    admitted = load_red_regional_choice_example(
        ready.private_root,
        RedRegionalChoiceInput(
            episode_id,
            choice_sha,
            outcome_record.summary.record_sha256,
            ready.causal_record,
        ),
    )
    return {
        "schema": "pokemon.red.regional-acquisition-result.v1",
        "episode_id": episode_id,
        "selected_source": selected.source_id,
        "candidate_count": len(candidates),
        "choice_record_sha256": choice_sha,
        "outcome_record_sha256": outcome_record.summary.record_sha256,
        "manifest_sha256": result["trajectory_manifest_sha256"],
        "checkpoint_sha256": checkpoint_sha,
        "model_sha256": ready.model_sha256,
        "eligible_examples": 1,
        "example": admitted.public_dict(),
        "parent_episode": episode,
        "parent_learning_examples": 0,
        "model_fitted": False,
        "independent_evaluation": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = base._parser()
    result = _run(parser.parse_args(argv))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
