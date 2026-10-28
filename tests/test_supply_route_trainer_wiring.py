"""Supplemental purchases retain the ordinary learned transport boundary."""
import ast
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.goal_manager import GoalKind
import pokemon_red_completion.red_player_collection_options as collection


def supply_function(monkeypatch, *, field_ready=True):
    root = Path(__file__).resolve().parents[1]
    source = root / 'runtime_helpers/red_whole_player_inventory_20261006.py'
    if not source.exists():
        source = root.parent / 'helpers/red_whole_player_inventory_20261006.py'
    tree = ast.parse(source.read_text())
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef)
                    and node.name == 'postgame_ball_supply_peers')
    monkeypatch.setattr(collection, 'ordinary_ball_resupply_peer_needed',
                        lambda raw, *, hall_of_fame: not hall_of_fame)
    constructed = []

    class Router:
        def __init__(self, runtime, actions, world, **kwargs):
            self.runtime = runtime
            self.wrapper = kwargs['interruption_handler_wrapper']
            constructed.append(self)

        def enumerate_routed_kinds(self, observation, kinds):
            assert kinds == frozenset({GoalKind.RESUPPLY})
            inner = object()
            self.handler = (self.wrapper(inner, SimpleNamespace(kind=GoalKind.RESUPPLY))
                            if self.wrapper is not None else inner)
            return SimpleNamespace(bindings=(SimpleNamespace(
                binding_ref=self.runtime.profile.name, kind=GoalKind.RESUPPLY),))

    def profile(original, *, early_supply=False):
        return SimpleNamespace(name='early' if early_supply else 'ordinary', providers=())

    namespace = dict(_field_ready=lambda runtime: field_ready,
                     FrozenTrainerBattler=type('UnusedActor', (), {}),
                     GoalKind=GoalKind, supply_profile=profile,
                     bind_resupply_fly_profile=lambda profile: profile,
                     replace=replace, RedResourceGoalRouter=Router,
                     player_supply_reserve=lambda profile: None)
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
    return namespace['postgame_ball_supply_peers'], constructed


@dataclass
class Runtime:
    profile: object
    reader: object
    adapter: object
    trainer_battle_runner: object = None


def runtime():
    raw = SimpleNamespace(map_id=59)
    observation = SimpleNamespace(raw=raw, game_state=None)
    return Runtime(object(), SimpleNamespace(read=lambda: raw),
                   SimpleNamespace(observe=lambda: observation,
                                   graph=SimpleNamespace(completed_ids=lambda state: ())))


def test_both_supply_profiles_forward_the_same_learned_handler(monkeypatch):
    supply, routers = supply_function(monkeypatch)
    calls = []
    learned = object()

    def wrapper(inner, spec):
        calls.append((inner, spec.kind))
        return learned

    bindings = supply(runtime(), object(), object(), interruption_handler_wrapper=wrapper)
    assert {binding.binding_ref for binding in bindings} == {'early', 'ordinary'}
    assert len(calls) == len(routers) == 2
    assert all(router.wrapper is wrapper and router.handler is learned for router in routers)
    assert all(kind is GoalKind.RESUPPLY for _, kind in calls)


def test_omitting_supply_transport_authority_is_an_explicit_error(monkeypatch):
    supply, routers = supply_function(monkeypatch)
    with pytest.raises(TypeError, match='interruption_handler_wrapper'):
        supply(runtime(), object(), object())
    assert routers == []


def test_explicitly_disabled_learned_scope_preserves_legacy_router(monkeypatch):
    supply, routers = supply_function(monkeypatch)
    assert len(supply(runtime(), object(), object(), interruption_handler_wrapper=None)) == 2
    assert all(router.wrapper is None for router in routers)


def test_absent_supply_demand_does_not_construct_a_route(monkeypatch):
    supply, routers = supply_function(monkeypatch)
    monkeypatch.setattr(collection, 'ordinary_ball_resupply_peer_needed',
                        lambda raw, *, hall_of_fame: False)
    assert supply(runtime(), object(), object(), interruption_handler_wrapper=None) == ()
    assert routers == []
