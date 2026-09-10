"""Action-free stock-derived evolution proposal for registered native learning.

This is deterministic candidate preparation, not learned species selection.
The existing native policy still chooses whether to evolve, capture or recover.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import run_paired_red_bounded_player as base

from pokemon_red_completion.gen1_cartridge import evolution_graph
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.red_collection import red_species_number
from pokemon_red_completion.red_goal_context_profile import (
    build_native_boxed_evolution_profile_payload,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.red_native_boxed_evolution import bind_native_boxed_evolution
from pokemon_red_completion.red_owned_evolution_inventory import (
    inventory_red_owned_level_evolutions,
)
from pokemon_red_completion.red_owned_evolution_priority import prioritize_owned_level_evolutions
from pokemon_red_completion.red_resource_goal_router import RedResourceGoalRouter


def inspect_owned_evolution(ready: base._Readiness) -> dict[str, Any]:
    """Offer the first stock-prioritized objective with a real native binding.

    A route being enumerable is not evidence of successful execution. Cost and
    outcome remain those of the actual played decision, never this proposal.
    """
    if (
        ready.continuation is None
        or ready.registration_policy is None
        or ready.training_plan is None
        or not ready.completion_dose
    ):
        raise ValueError("owned evolution inventory needs a registered bounded continuation")
    world = base._route_world(ready)
    if world is None:
        raise ValueError("owned evolution inventory needs cartridge routing")
    with base.PyBoyAdapter(ready.rom_path, watch=False, speed=None) as emulator:
        emulator.load_state_bytes(ready.capture.state_bytes)
        base._verify_continuation_restore(ready, emulator)
        before, frame = emulator.save_state_bytes(), emulator.frame_count
        controller = base.ReadOnlyController(emulator)
        runtime = base.build_red_goal_context_runtime(
            profile=ready.profile,
            capture=ready.capture,
            emulator=controller,
            reader=base.PokemonRedStateReader(controller),
        )
        runtime = base._registered_runtime(ready, runtime)
        observed = base._training_observation(runtime)
        policy = ready.registration_policy
        rows = inventory_red_owned_level_evolutions(
            observed.collection_observation,
            evolution_graph(world.rom),
            target_species=policy.targets,
            registered_species=policy.registered(observed.collection_observation),
            protected_source_counts=policy.protected_counts,
        )
        priority = prioritize_owned_level_evolutions(rows)
        actions = base.CountingExecutor(
            base.FrameSafeExecutor(
                controller,
                base.DEFAULT_NEW_GAME_TIMING.controller_timing(),
            )
        )
        checked = []
        selected = None
        for item in priority:
            row = item.prerequisite
            source = red_species_number(row.source_species_ref)
            target = red_species_number(row.target_species_ref)
            transition = f"evolution:{source}:{target}:{row.evolution_level}"
            if any(s.level == 100 for s in row.party_or_box_precursors):
                # The old executor chooses by storage slot, not our cheapest
                # precursor. Do not advertise a mixed level-cap stock until
                # that specific selection boundary is qualified.
                checked.append({"transition": transition, "available": False,
                                "minimum_level_gains": item.minimum_level_gains,
                                "reason": "mixed_level_cap_stock_unqualified"})
                continue
            profile = parse_red_goal_context_profile(
                build_native_boxed_evolution_profile_payload(
                    ready.profile,
                    source_species=source,
                    target_species=target,
                    evolution_level=row.evolution_level,
                )
            )
            native = bind_native_boxed_evolution(
                replace(runtime, profile=profile),
                world,
                maximum_quanta=128,
                allow_cross_box=True,
            )
            bindings = RedResourceGoalRouter(
                native,
                actions,
                world,
                maximum_controller_actions=ready.training_plan.maximum_actions,
                maximum_emulator_frames=ready.training_plan.maximum_frames,
                routed_recovery=ready.routed_recovery,
                include_recovery_offers=False,
            ).enumerate(observed)
            available = [b for b in bindings.bindings if b.kind is GoalKind.EVOLVE_SPECIES]
            if len(available) > 1:
                raise ValueError("owned evolution proposal has ambiguous native binding")
            checked.append(
                {
                    "transition": transition,
                    "available": bool(available),
                    "minimum_level_gains": item.minimum_level_gains,
                }
            )
            if available:
                selected = transition
                break
        if (
            before != emulator.save_state_bytes()
            or frame != emulator.frame_count
            or emulator.pressed_buttons
            or actions.actions_executed
        ):
            raise ValueError("owned evolution inspection changed the saved game")
        return {
            "schema": "pokemon.red.owned-evolution-inventory.v1",
            "checkpoint_sha256": ready.continuation.record_sha256,
            "missing_owned_level_objectives": len(rows),
            "native_stock_eligible_objectives": len(priority),
            "checked": checked,
            "selected_transition": selected,
            "selection_authority": "deterministic_minimum_level_gain_shortlist",
            "learned_target_selection": False,
            "controller_actions": 0,
            "emulator_frames": 0,
        }
