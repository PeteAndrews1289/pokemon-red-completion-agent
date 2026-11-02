from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from test_red_npc_trade import TRADE, observation

import pokemon_red_completion.red_trade_dependency_options as module
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport, GoalVerification
from pokemon_red_completion.red_collection import red_species_ref as ref


@pytest.mark.parametrize("failure", [None, "partial", "lost_stock", "no_trade", "bad_receipt"])
@pytest.mark.parametrize("delegated", (False, True))
def test_composed_goal_requires_complete_exchange_and_exact_stock(monkeypatch, failure, delegated):
    before = observation()
    current = [before]
    state = [b"original"]
    counters = NS(actions_executed=0)
    emulator = NS(frame_count=0, pressed_buttons=(), save_state_bytes=lambda: state[0])
    flags = [frozenset({4})]
    reader = NS(
        read_completed_npc_trades=lambda: flags[0], read_bottom_dialogue_box_visible=lambda: False
    )
    runtime = NS(
        emulator=emulator,
        reader=reader,
        adapter=NS(observe=lambda: current[0]),
        registration_policy=NS(protected_counts={ref(1): 2}),
    )
    trade = replace(TRADE, give=64)

    def evolve():
        counters.actions_executed += 10
        emulator.frame_count += 100
        state[0] = b"intermediate"
        return GoalExecutionReport(10, 100, {"evolution_partial": failure == "partial"})

    def exchange():
        after = observation(True)
        after.collection_observation.owned_species |= {ref(64)}
        if failure == "lost_stock":
            after.collection_observation.specimens = after.collection_observation.specimens[1:]
        current[0] = after
        flags[0] |= {trade.index}
        counters.actions_executed += 5
        emulator.frame_count += 50
        state[0] = b"terminal"
        return GoalExecutionReport(5, 50, {"exchange": True})

    inner = NS(
        execute=evolve,
        estimated_effort=0.5,
        estimated_risk=0.1,
        verify=lambda _: (
            GoalVerification.failed(module.GoalFailureReason.OUTCOME_NOT_VERIFIED)
            if failure == "partial"
            else GoalVerification.succeeded()
        ),
    )
    if delegated:
        def execute_selected_evolution(selected):
            assert selected is inner
            return selected.execute()
        counters.execute_evolution_subgoal = execute_selected_evolution
    binding = NS(
        binding_ref=f"red-npc-trade:{trade.index}",
        execute=exchange,
        verify=lambda _: GoalVerification.succeeded(),
    )
    monkeypatch.setattr(
        module, "npc_trade_bindings", lambda *args: () if failure == "no_trade" else (binding,)
    )
    world = NS(with_current_observation=lambda _: object())
    option = module._compose(runtime, before, counters, world, trade, 63, inner)
    assert option.kind is GoalKind.ACQUIRE_SPECIES
    if failure == "no_trade":
        with pytest.raises(module.RedNPCTradeError):
            option.execute()
        return
    report = option.execute()
    if failure == "bad_receipt":
        report = GoalExecutionReport(0, 0, {})
    assert (option.verify(report).status.value == "succeeded") is (failure is None)
    if failure is None:
        assert (report.actions_executed, report.frames_executed) == (15, 150)
        assert report.evidence["complete"]
    if failure == "partial":
        assert not report.evidence["complete"] and state[0] == b"intermediate"
        assert report.evidence["intermediate_verification"] == {
            "status": "failed", "failure_reason": "outcome_not_verified",
        }
    with pytest.raises(module.RedNPCTradeError):
        option.execute()


def test_dependency_inventory_is_explicitly_opted_in():
    assert (
        module.npc_trade_dependency_bindings(
            NS(), None, None, None, maximum_actions=1000, maximum_frames=10000
        )
        == ()
    )


@pytest.mark.parametrize("evolution_seed", [True, False])
def test_discovery_exposes_a_complete_goal_without_input(
    dependency, monkeypatch, evolution_seed  # noqa: F811
):
    from test_red_trade_evolution_dependency import bind

    from pokemon_red_completion.executor import CountingExecutor

    runtime, reader, _ = dependency
    runtime = replace(runtime, npc_trades=True, npc_trade_dependencies=True)
    if not evolution_seed:
        from test_red_player_collection_options import corridor

        providers = tuple(
            (spec.kind, spec.mechanic, module._thaw(spec.parameters))
            for spec in runtime.profile.providers
            if spec.kind is not GoalKind.EVOLVE_SPECIES
        ) + (
            (GoalKind.ACQUIRE_SPECIES, module.RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
             corridor().profile_parameters()),
        )
        profile = module.parse_red_goal_context_profile(
            module.build_red_goal_context_profile_payload(
                profile_id=runtime.profile.profile_id,
                providers=tuple(
                    sorted(providers, key=lambda row: tuple(GoalKind).index(row[0]))
                ),
            )
        )
        runtime = replace(runtime, profile=profile)
        assert all(spec.kind is not GoalKind.EVOLVE_SPECIES for spec in profile.providers)
    original_profile = runtime.profile
    scoped = bind(runtime)
    retargeted = []
    native_binding = module.bind_native_boxed_evolution

    def bind_native(current, *args, **kwargs):
        retargeted.append(current)
        return native_binding(current, *args, **kwargs)

    monkeypatch.setattr(module, "bind_native_boxed_evolution", bind_native)
    trade = NS(index=1, give=78, receive=124)
    monkeypatch.setattr(module, "stationary_npc_trades", lambda _: (trade,))
    monkeypatch.setattr(
        module,
        "evolution_graph",
        lambda _: {77: (NS(method=module.EvolutionMethod.LEVEL, to_species=78),)},
    )
    monkeypatch.setattr(module, "bind_trade_evolution_dependency", lambda *a, **kw: scoped)
    reader.read_completed_npc_trades = lambda: frozenset()
    reader.read_bottom_dialogue_box_visible = lambda: False
    runtime.emulator.save_state_bytes = lambda: b"original"
    actions = CountingExecutor(NS(execute=lambda _: pytest.fail("unexpected input")))
    result = module.npc_trade_dependency_bindings(
        runtime,
        runtime.adapter.observe(),
        actions,
        NS(rom=b"fixture"),
        maximum_actions=1000,
        maximum_frames=10000,
    )
    assert len(result) == 1 and result[0].kind is GoalKind.ACQUIRE_SPECIES
    assert actions.actions_executed == 0
    assert runtime.profile is original_profile
    assert runtime.emulator.frame_count == 0
    assert runtime.emulator.save_state_bytes() == b"original"
    assert len(retargeted) == 1 and retargeted[0].registration_policy is scoped
    providers = retargeted[0].profile.providers
    assert all(spec in providers for spec in original_profile.providers
               if spec.kind is not GoalKind.EVOLVE_SPECIES)
    assert tuple(spec.kind for spec in providers) == tuple(
        kind for kind in GoalKind if any(spec.kind is kind for spec in providers)
    )
    evolution = next(spec for spec in providers if spec.kind is GoalKind.EVOLVE_SPECIES)
    assert evolution.parameters["source_species_ref"] == ref(77)
    assert evolution.parameters["target_species_ref"] == ref(78)
    assert evolution.parameters["evolution_level"] == scoped.evolution_level


# Explicit fixture import: it patches cartridge readers, not production behavior.
from test_red_trade_evolution_dependency import dependency  # noqa: E402,F401
