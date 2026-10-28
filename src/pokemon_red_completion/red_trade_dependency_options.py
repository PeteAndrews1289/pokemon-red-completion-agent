"""Opt-in complete native level-evolution → NPC-exchange acquisition goals.

The model chooses an acquisition, not a fabricated new intermediate registration.
The subordinate evolution has a scoped physical-demand policy; the ordinary
registration/reserve policy still governs the final exchange. All child input
shares the caller's action/frame/wall budgets. No child selects a different goal.
"""

from collections import Counter
from dataclasses import replace

from .gen1_cartridge import EvolutionMethod, evolution_graph
from .goal_manager import GoalDecisionOutcome, GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .red_collection import red_species_ref
from .red_full_pokedex_direct_profile import _evolution_capability_parameters
from .red_goal_context_profile import (
    RedGoalMechanic,
    _thaw,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)
from .red_native_boxed_evolution import bind_native_boxed_evolution
from .red_npc_trade import RedNPCTradeError, stationary_npc_trades
from .red_npc_trade_options import npc_trade_bindings
from .red_resource_goal_router import RedResourceGoalRouter
from .red_trade_evolution_dependency import bind_trade_evolution_dependency


def npc_trade_dependency_bindings(
    runtime, observation, actions, world, *, maximum_actions, maximum_frames, maximum_quanta=128
):
    if not getattr(runtime, "npc_trade_dependencies", False):
        return ()
    if not runtime.npc_trades or runtime.registration_policy is None:
        raise ValueError("physical trade dependencies require registered native trades")
    if observation != runtime.adapter.observe():
        raise ValueError("physical trade dependency observation is stale")
    if (
        not observation.input_ready
        or observation.raw.battle_state
        or runtime.reader.read_bottom_dialogue_box_visible()
        or runtime.emulator.pressed_buttons
    ):
        return ()
    before = actions.actions_executed, runtime.emulator.frame_count
    state = runtime.emulator.save_state_bytes()
    collection = observation.collection_observation
    policy = runtime.registration_policy
    flags = runtime.reader.read_completed_npc_trades()
    counts = Counter(s.species_ref for s in collection.specimens)
    results = []
    for trade in stationary_npc_trades(world.rom):
        if (
            trade.index in flags
            or red_species_ref(trade.receive) in policy.goal_registered(collection)
            or counts[red_species_ref(trade.give)]
        ):
            continue
        for source, edges in sorted(evolution_graph(world.rom).items()):
            if counts[red_species_ref(source)] <= policy.protected_counts.get(
                red_species_ref(source), 0
            ) or not any(
                e.method is EvolutionMethod.LEVEL and e.to_species == trade.give for e in edges
            ):
                continue
            scoped = bind_trade_evolution_dependency(
                policy,
                collection,
                world.rom,
                trade_index=trade.index,
                source_species=source,
                completed_trades=flags,
            )
            parameters = dict(
                _evolution_capability_parameters(runtime.profile),
                source_species_ref=red_species_ref(source),
                target_species_ref=red_species_ref(trade.give),
                evolution_level=scoped.evolution_level,
            )
            providers = {
                spec.kind: (spec.kind, spec.mechanic, _thaw(spec.parameters))
                for spec in runtime.profile.providers
                if spec.kind is not GoalKind.EVOLVE_SPECIES
            }
            # A mixed capture profile may not predeclare an evolution provider.
            # Bind this observed prerequisite edge without changing its parent.
            providers[GoalKind.EVOLVE_SPECIES] = (
                GoalKind.EVOLVE_SPECIES, RedGoalMechanic.TARGETED_LEVEL_EVOLUTION, parameters
            )
            profile = parse_red_goal_context_profile(
                build_red_goal_context_profile_payload(
                    profile_id=runtime.profile.profile_id,
                    providers=tuple(
                        providers[kind] for kind in GoalKind if kind in providers
                    ),
                )
            )
            native = bind_native_boxed_evolution(
                replace(runtime, profile=profile, registration_policy=scoped),
                world,
                maximum_quanta=maximum_quanta,
                allow_cross_box=True,
            )
            offered = native.provider_for(GoalKind.EVOLVE_SPECIES, actions).offer(observation)
            inner = offered.binding
            if inner is None:
                routed = RedResourceGoalRouter(
                    native,
                    actions,
                    world,
                    maximum_controller_actions=maximum_actions,
                    maximum_emulator_frames=maximum_frames,
                    quote_resource_costs=True,
                    include_recovery_offers=False,
                ).enumerate_routed_kinds(observation, frozenset({GoalKind.EVOLVE_SPECIES}))
                choices = tuple(b for b in routed.bindings if b.kind is GoalKind.EVOLVE_SPECIES)
                if len(choices) > 1:
                    raise ValueError("physical intermediate has multiple execution bindings")
                inner = choices[0] if choices else None
            if inner is not None:
                results.append(_compose(runtime, observation, actions, world, trade, source, inner))
    if (
        before != (actions.actions_executed, runtime.emulator.frame_count)
        or state != runtime.emulator.save_state_bytes()
    ):
        raise ValueError("physical trade dependency discovery changed the game")
    return tuple(results)


def _compose(runtime, observation, actions, world, trade, source, inner):
    used = False
    receipt = None
    terminal = None
    flags = runtime.reader.read_completed_npc_trades()
    start_actions, start_frames = actions.actions_executed, runtime.emulator.frame_count
    state = runtime.emulator.save_state_bytes()

    def execute():
        nonlocal used, receipt, terminal
        if (
            used
            or runtime.emulator.save_state_bytes() != state
            or (actions.actions_executed, runtime.emulator.frame_count)
            != (start_actions, start_frames)
        ):
            raise RedNPCTradeError("physical trade dependency was consumed or changed")
        used = True
        delegate = getattr(actions, "execute_evolution_subgoal", None)
        intermediate = delegate(inner) if callable(delegate) else inner.execute()
        intermediate_verification = inner.verify(intermediate)
        if intermediate_verification.status is not GoalDecisionOutcome.SUCCEEDED:
            # Preserve ordinary partial XP as incomplete work, never success.
            receipt = GoalExecutionReport(
                actions.actions_executed - start_actions,
                runtime.emulator.frame_count - start_frames,
                {
                    "mechanic": "trade_level_dependency",
                    "complete": False,
                    "intermediate_verification": {
                        "status": intermediate_verification.status.value,
                        "failure_reason": (
                            intermediate_verification.failure_reason.value
                            if intermediate_verification.failure_reason is not None else None
                        ),
                    },
                    "intermediate": dict(intermediate.evidence),
                },
            )
            return receipt
        fresh = runtime.adapter.observe()
        exchanges = tuple(
            b
            for b in npc_trade_bindings(
                runtime, fresh, actions, world.with_current_observation(runtime.reader)
            )
            if b.binding_ref == f"red-npc-trade:{trade.index}"
        )
        if len(exchanges) != 1:
            raise RedNPCTradeError(
                "physical intermediate completed but native trade is unavailable"
            )
        exchange = exchanges[0].execute()
        if exchanges[0].verify(exchange).status is not GoalDecisionOutcome.SUCCEEDED:
            raise RedNPCTradeError("physical dependency exchange did not verify")
        terminal = runtime.emulator.save_state_bytes()
        receipt = GoalExecutionReport(
            actions.actions_executed - start_actions,
            runtime.emulator.frame_count - start_frames,
            {
                "mechanic": "trade_level_dependency",
                "complete": True,
                "intermediate": dict(intermediate.evidence),
                "exchange": dict(exchange.evidence),
            },
        )
        return receipt

    def verify(report):
        if receipt is None or report != receipt or terminal is None:
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        after = runtime.adapter.observe()
        old, new = observation.collection_observation, after.collection_observation
        expected = Counter(s.species_ref for s in old.specimens)
        expected[red_species_ref(source)] -= 1
        expected[red_species_ref(trade.receive)] += 1
        actual = Counter(s.species_ref for s in new.specimens)
        policy = runtime.registration_policy
        if (
            runtime.emulator.save_state_bytes() == terminal
            and not runtime.emulator.pressed_buttons
            and after.input_ready
            and not after.raw.battle_state
            and not runtime.reader.read_bottom_dialogue_box_visible()
            and actual == +expected
            and new.owned_species
            == old.owned_species | {red_species_ref(trade.give), red_species_ref(trade.receive)}
            and runtime.reader.read_completed_npc_trades() == flags | {trade.index}
            and all(actual[s] >= n for s, n in policy.protected_counts.items())
            and after.raw.player_money == observation.raw.player_money
            and after.raw.bag_items == observation.raw.bag_items
        ):
            return GoalVerification.succeeded()
        return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)

    return ExecutableGoalBinding(
        binding_ref=f"red-npc-trade-dependency:{trade.index}:{source}",
        kind=GoalKind.ACQUIRE_SPECIES,
        estimated_effort=min(1.0, inner.estimated_effort + 0.2),
        estimated_risk=max(0.1, inner.estimated_risk),
        execute=execute,
        verify=verify,
        search_source_ref=f"pokemon.red:npc-trade:{trade.index}",
    )
