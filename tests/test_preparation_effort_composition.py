"""ROM-free draft: real binding composition, geometric quote, fresh child."""
from dataclasses import dataclass, field
from types import SimpleNamespace as N

import pytest

from test_red_player_preparation_binding import setup as direct_setup
from pokemon_red_completion import red_player_field_goals as f
from pokemon_red_completion import red_player_preparation_binding as p
from pokemon_red_completion.global_router import MacroEdge, MacroGraph, MacroPath, MacroTransition
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport, GoalVerification
from pokemon_red_completion.local_router import LocalEdge, LocalPath
from pokemon_red_completion.red_living_dex_provider_plan import RedLivingDexProviderPlanError
from pokemon_red_completion.route_executor import TraversalResource, TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlan, RoutePlanningError, RouteSegment


def fixture(monkeypatch, *, at_home=False, blocked=False):
    rt, actions, kwargs, mon = direct_setup(monkeypatch)
    raw = rt.reader.read()
    raw.game_started = True
    raw.map_id = 41 if at_home else 1
    raw.player_y = raw.player_x = 3 if at_home else 4
    rt.emulator.save_state_bytes = lambda: bytes([raw.map_id, raw.player_y, raw.player_x])
    observed, queries, doses = [], [], []
    resource = TraversalResource('steps', None, 2)

    def snapshot():
        observed.append((raw.map_id, raw.player_y, raw.player_x))
        return TraversalSnapshot(
            raw.map_id, (raw.player_y, raw.player_x), True, mode='land',
            capabilities=frozenset({'cut'}), resources=(resource,), last_outside_map=1,
        )

    monkeypatch.setattr(f, 'Gen1TraversalObserver', lambda *a, **k: N(observe=snapshot))
    monkeypatch.setattr(p, 'Gen1TraversalObserver', lambda *a, **k: N(observe=snapshot))
    monkeypatch.setattr(f, '_raw_party_fully_restored', lambda _: True)
    monkeypatch.setattr(f, 'observe_preparation_members', p.observe_preparation_members)
    monkeypatch.setattr(f, 'preparation_trainee', p.preparation_trainee)
    approach_edge = MacroEdge(41, cost=181)
    world = N(rom=b'fixture', macro_graph=MacroGraph({1: (approach_edge,), 41: ()},
                                                 outside_nodes=frozenset({1})))

    def quote(start, destination, *, goal_at):
        queries.append((start, destination, goal_at))
        if destination == 41:
            if start.map_id == 41:
                return RoutePlan(MacroPath((41,), ()), start.at, start.mode, (), None,
                                 start.at, start.mode)
            local = LocalPath((start.at,), (), (start.mode,))
            segment = RouteSegment(1, 41, local, MacroTransition(start.at, (3, 3), 'up'),
                                   'connection', False)
            return RoutePlan(MacroPath((1, 41), (approach_edge,)), start.at, start.mode,
                             (segment,), None, (3, 3), start.mode)
        assert destination == 12 and goal_at == (2, 2)
        assert start.map_id == 41 and start.at == (3, 3)
        assert start.capabilities == frozenset({'cut'})
        assert start.resources == (resource,) and start.last_outside_map == 1
        if blocked:
            raise RoutePlanningError('declared venue unreachable')
        return N(cost=24)

    world.plan_feasible_to_map = quote

    @dataclass
    class Route:
        rom: bytes = b'fixture'
        route_world: object = field(default_factory=lambda: world)
        destination_map: int = 41
        destination_at: tuple = (3, 3)

        def __call__(self, a, reader, emulator):
            assert a is actions and reader is rt.reader and emulator is rt.emulator
            raw.map_id = self.destination_map
            raw.player_y, raw.player_x = self.destination_at
            actions.actions_executed += 2
            emulator.frame_count += 40

    kwargs['route'] = Route()

    def dose(**kw):
        assert raw.map_id == 41 and (raw.player_y, raw.player_x) == (3, 3)
        assert kw['plan'] is kwargs['plan'] and kw['battler'] is kwargs['battler']
        assert kw['actions'] is actions and kw['emulator'] is rt.emulator
        doses.append(kw['maximum_battles'])
        mon.level, mon.experience = 6, 180
        actions.actions_executed += 5
        rt.emulator.frame_count += 200
        return {'xp_gained': 45}

    monkeypatch.setattr(p, 'execute_wild_preparation', dose)
    return rt, actions, kwargs, observed, queries, doses


@pytest.mark.parametrize('cap', [1, 3, 32, 128])
def test_direct_binding_retains_exact_legacy_quote(monkeypatch, cap):
    rt, actions, kwargs, _, _, _ = fixture(monkeypatch, at_home=True)
    direct = p.preparation_binding(rt, actions, maximum_battles=cap, **kwargs)
    assert direct.estimated_effort == min(1.0, (24 + 120 * cap) / 3000)
    assert direct.kind is GoalKind.DEVELOP_TEAM and direct.estimated_risk == .20
    assert actions.actions_executed == rt.emulator.frame_count == 0


@pytest.mark.parametrize('cap', [1, 3, 32, 128])
def test_routed_quote_reuses_child_plus_only_approach_cost(monkeypatch, cap):
    rt, actions, kwargs, observed, queries, doses = fixture(monkeypatch)
    outer = f.routed_preparation_binding(rt, actions, home_map=41,
                                        maximum_battles=cap, **kwargs)
    assert outer.estimated_effort == min(1.0, (181 + 24 + 120 * cap) / 3000)
    assert observed == [(1, 4, 4)]  # No semantic observation of projected nurse.
    assert [q[1:] for q in queries] == [(41, (3, 3)), (12, (2, 2))]
    assert not doses and actions.actions_executed == rt.emulator.frame_count == 0


def test_noop_approach_returns_same_real_child(monkeypatch):
    rt, actions, kwargs, _, _, _ = fixture(monkeypatch, at_home=True)
    direct = p.preparation_binding(rt, actions, maximum_battles=3, **kwargs)
    routed = f.routed_preparation_binding(rt, actions, home_map=41,
                                         maximum_battles=3, **kwargs)
    assert routed.binding_ref == direct.binding_ref
    assert routed.opportunity == direct.opportunity
    assert routed.resource_quote == direct.resource_quote
    assert routed.cash_outcome == direct.cash_outcome
    assert actions.actions_executed == rt.emulator.frame_count == 0


def test_real_child_is_fresh_after_arrival_and_owns_verification(monkeypatch):
    rt, actions, kwargs, observed, queries, doses = fixture(monkeypatch)
    bound = []
    real = p.preparation_binding

    def fresh(*args, **kw):
        assert (rt.reader.read().map_id, rt.reader.read().player_y) == (41, 3)
        result = real(*args, **kw)
        bound.append(result)
        return result

    monkeypatch.setattr(f, 'preparation_binding', fresh)
    outer = f.routed_preparation_binding(rt, actions, home_map=41,
                                        maximum_battles=3, **kwargs)
    assert bound == [] and doses == []
    report = outer.execute()
    assert len(bound) == 1 and doses == [3]
    assert observed == [(1, 4, 4), (41, 3, 3)]
    assert [q[1] for q in queries] == [41, 12, 12]  # Real child re-quotes actual arrival.
    assert (report.actions_executed, report.frames_executed) == (7, 240)
    assert outer.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    with pytest.raises(ValueError, match='stale or consumed'):
        outer.execute()


def test_unreachable_child_is_unavailable_before_input(monkeypatch):
    rt, actions, kwargs, observed, _, doses = fixture(monkeypatch, blocked=True)
    assert f.routed_preparation_binding(rt, actions, home_map=41, **kwargs) is None
    assert observed == [(1, 4, 4)] and not doses
    assert actions.actions_executed == rt.emulator.frame_count == 0


def test_unknown_quote_fault_is_not_masked_as_unavailable(monkeypatch):
    rt, actions, kwargs, _, _, _ = fixture(monkeypatch)
    real = kwargs['route'].route_world.plan_feasible_to_map

    def broken(start, destination, **kw):
        if destination == 12:
            raise RuntimeError('unknown planner fault')
        return real(start, destination, **kw)

    kwargs['route'].route_world.plan_feasible_to_map = broken
    with pytest.raises(RuntimeError, match='unknown planner fault'):
        f.routed_preparation_binding(rt, actions, home_map=41, **kwargs)
    assert actions.actions_executed == rt.emulator.frame_count == 0


def test_stale_source_still_blocks_all_input(monkeypatch):
    rt, actions, kwargs, _, _, doses = fixture(monkeypatch)
    binding = f.routed_preparation_binding(rt, actions, home_map=41, **kwargs)
    rt.emulator.save_state_bytes = lambda: b'changed'
    with pytest.raises(ValueError, match='stale or consumed'):
        binding.execute()
    assert not doses and actions.actions_executed == rt.emulator.frame_count == 0


def test_malformed_typed_projection_is_not_unavailability(monkeypatch):
    rt, actions, kwargs, _, _, _ = fixture(monkeypatch)
    real = kwargs['route'].route_world.plan_feasible_to_map

    def mismatched(start, destination, **kw):
        if destination == 41:
            return RoutePlan(MacroPath((41,), ()), (3, 3), 'land', (), None,
                             (3, 3), 'land')
        return real(start, destination, **kw)

    kwargs['route'].route_world.plan_feasible_to_map = mismatched
    # Keep a nonempty prefix so the malformed plan cannot take the healthy noop seam.
    from dataclasses import replace
    malformed = real(TraversalSnapshot(1, (4, 4), True, mode='land'), 41, goal_at=(3, 3))
    # A different starting coordinate is internally continuous but not source-bound.
    local = LocalPath(((5, 5),), (), ('land',))
    segment = RouteSegment(1, 41, local, MacroTransition((5, 5), (3, 3), 'up'),
                           'connection', False)
    malformed = replace(malformed, start_at=(5, 5), segments=(segment,))
    kwargs['route'].route_world.plan_feasible_to_map = (
        lambda start, destination, **kw: malformed if destination == 41
        else real(start, destination, **kw)
    )
    with pytest.raises(RedLivingDexProviderPlanError, match='another observation'):
        f.routed_preparation_binding(rt, actions, home_map=41, **kwargs)
    assert actions.actions_executed == rt.emulator.frame_count == 0
