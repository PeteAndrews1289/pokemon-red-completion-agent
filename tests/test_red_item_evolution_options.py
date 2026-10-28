from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_goal_context import _ActionDelegate
from test_red_native_boxed_item_evolution import _runtime

from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.gen1_cartridge import Evolution, EvolutionMethod
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.observation import ItemId, RedCurrentBoxState
from pokemon_red_completion.red_collection import (
    red_internal_species_id,
    red_internal_species_number,
    red_species_ref,
)
from pokemon_red_completion.red_goal_context import RedGoalContextError
from pokemon_red_completion.red_item_evolution_options import enumerate_red_item_evolutions
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalMechanic, build_red_goal_context_profile_payload, parse_red_goal_context_profile,
)


def _two_families(tmp_path, monkeypatch):
    runtime, reader = _runtime(
        tmp_path,
        monkeypatch,
        source=58,
        target=59,
        item=ItemId.FIRE_STONE,
    )
    reader.boxes = replace(
        reader.boxes,
        boxes=(
            reader.boxes.boxes[0],
            RedCurrentBoxState(1, (red_internal_species_id(61),), (30,)),
            *reader.boxes.boxes[2:],
        ),
    )
    owned = reader.read_pokedex_state().owned_species | {61}
    reader.read_pokedex_state = lambda: SimpleNamespace(seen_species=owned, owned_species=owned)
    monkeypatch.setattr(
        "pokemon_red_completion.red_native_boxed_item_evolution.evolution_graph",
        lambda _: {
            58: (Evolution(58, 59, EvolutionMethod.STONE, int(ItemId.FIRE_STONE)),),
            61: (Evolution(61, 62, EvolutionMethod.STONE, int(ItemId.WATER_STONE)),),
        },
    )
    world = SimpleNamespace(
        rom=b"fixture",
        plan_feasible_to_map=lambda *args, **kwargs: SimpleNamespace(steps=(1,)),
    )
    return runtime, reader, world


def _enumerate(runtime, world, *, interruption_handler_wrapper=None):
    actions = CountingExecutor(_ActionDelegate())
    before = runtime.reader.read(), runtime.emulator.frame_count
    candidates = enumerate_red_item_evolutions(
        runtime,
        runtime.adapter.observe(),
        actions,
        world,
        maximum_actions=3000,
        maximum_frames=300000,
        **({"interruption_handler_wrapper": interruption_handler_wrapper}
           if interruption_handler_wrapper is not None else {}),
    )
    assert before == (runtime.reader.read(), runtime.emulator.frame_count)
    assert actions.actions_executed == 0
    return candidates


def _target(option):
    return next(
        s.parameters["target_species_ref"]
        for s in option.profile.providers
        if s.kind is GoalKind.EVOLVE_SPECIES
    )


@pytest.mark.parametrize(
    "cash,held,expected",
    [
        (2298, False, {59: 2100, 62: 2100}),
        (2099, False, {}),
        (0, True, {59: 0}),
        (2298, True, {59: 0, 62: 2100}),
    ],
)
@pytest.mark.parametrize("declared", (False, True))
def test_all_missing_stone_targets_use_actual_individual_resources(
    tmp_path,
    monkeypatch,
    cash,
    held,
    expected,
    declared,
):
    runtime, reader, world = _two_families(tmp_path, monkeypatch)
    if not declared:
        providers = {spec.kind: (spec.kind, spec.mechanic, dict(spec.parameters))
                     for spec in runtime.profile.providers if spec.kind is not GoalKind.EVOLVE_SPECIES}
        providers[GoalKind.ADVANCE_STORY] = (GoalKind.ADVANCE_STORY, RedGoalMechanic.OAKS_ERRAND, {})
        providers[GoalKind.RECOVER_CONTROL] = (GoalKind.RECOVER_CONTROL, RedGoalMechanic.CONTROL_RECOVERY, {})
        runtime = replace(runtime, profile=parse_red_goal_context_profile(
            build_red_goal_context_profile_payload(profile_id=runtime.profile.profile_id,
                providers=tuple(providers[kind] for kind in GoalKind if kind in providers))))
    original_profile = runtime.profile
    reader.raw = replace(
        reader.raw, player_money=cash, bag_items=((int(ItemId.FIRE_STONE), 1),) if held else ()
    )
    candidates = _enumerate(runtime, world)
    assert {_target(c): c.economy_offer.planned_spend for c in candidates} == {
        red_species_ref(target): cost for target, cost in expected.items()
    }
    assert len({c.binding.binding_ref for c in candidates}) == len(candidates)
    assert runtime.profile == original_profile
    assert any(s.kind is GoalKind.EVOLVE_SPECIES for s in runtime.profile.providers) is declared


@pytest.mark.parametrize("source,target", [(30, 31), (33, 34), (35, 36)])
@pytest.mark.parametrize("stock", [0, 1, 3, 99])
def test_finite_stone_targets_require_real_stock(tmp_path, monkeypatch, source, target, stock):
    runtime, reader = _runtime(
        tmp_path, monkeypatch, source=source, target=target, item=ItemId.MOON_STONE
    )
    reader.raw = replace(
        reader.raw, player_money=0, bag_items=((int(ItemId.MOON_STONE), stock),) if stock else ()
    )
    world = SimpleNamespace(
        rom=b"fixture", plan_feasible_to_map=lambda *a, **k: SimpleNamespace(steps=(1,))
    )
    options = _enumerate(runtime, world)
    assert [_target(c) for c in options] == ([red_species_ref(target)] if stock else [])
    assert all(c.economy_offer.planned_spend == 0 for c in options)


def test_stone_stock_change_invalidates_previously_offered_target(tmp_path, monkeypatch):
    runtime, reader = _runtime(tmp_path, monkeypatch, source=30, target=31, item=ItemId.MOON_STONE)
    reader.raw = replace(reader.raw, bag_items=((int(ItemId.MOON_STONE), 2),))
    world = SimpleNamespace(
        rom=b"fixture", plan_feasible_to_map=lambda *a, **k: SimpleNamespace(steps=(1,))
    )
    (option,) = _enumerate(runtime, world)
    reader.raw = replace(reader.raw, bag_items=())
    with pytest.raises((RedGoalContextError, RuntimeError, ValueError)):
        option.binding.execute()
    assert _enumerate(runtime, world) == ()


def test_held_buyable_stack_does_not_require_a_purchase(tmp_path, monkeypatch):
    runtime, reader, world = _two_families(tmp_path, monkeypatch)
    reader.raw = replace(reader.raw, player_money=0, bag_items=((int(ItemId.FIRE_STONE), 3),))
    options = _enumerate(runtime, world)
    assert [_target(c) for c in options] == [red_species_ref(59)]
    assert options[0].economy_offer.planned_spend == 0


def test_registered_targets_and_protected_precursors_are_not_choices(tmp_path, monkeypatch):
    runtime, reader, world = _two_families(tmp_path, monkeypatch)
    runtime = replace(
        runtime,
        registration_policy=replace(
            runtime.registration_policy,
            protected_counts={red_species_ref(58): 1},
        ),
    )
    assert [_target(c) for c in _enumerate(runtime, world)] == [red_species_ref(62)]
    owned = reader.read_pokedex_state().owned_species | {62}
    reader.read_pokedex_state = lambda: SimpleNamespace(seen_species=owned, owned_species=owned)
    assert _enumerate(runtime, world) == ()


def test_each_native_binding_keeps_its_own_target_request(tmp_path, monkeypatch):
    import pokemon_red_completion.red_item_evolution_options as module

    runtime, _, world = _two_families(tmp_path, monkeypatch)
    original = module.bind_native_boxed_item_evolution
    calls = []

    class ReachedExecutor(Exception):
        pass

    def bind(candidate_runtime, *args, **kwargs):
        native = original(candidate_runtime, *args, **kwargs)

        def execute(*args, **kwargs):
            calls.append((candidate_runtime.profile, args, kwargs))
            raise ReachedExecutor

        return replace(native, boxed_item_evolution_executor=execute)

    monkeypatch.setattr(module, "bind_native_boxed_item_evolution", bind)
    candidates = _enumerate(runtime, world)
    assert len(candidates) == 2
    assert calls == []
    for candidate in reversed(candidates):
        with pytest.raises(ReachedExecutor):
            candidate.binding.execute()
        assert calls[-1][0] == candidate.profile
        request = calls[-1][1][0]
        target = red_species_ref(red_internal_species_number(request.evolved_internal_species_id))
        assert target == _target(candidate)


def test_enumeration_detects_mutation_even_on_error(tmp_path, monkeypatch):
    import pokemon_red_completion.red_item_evolution_options as module

    runtime, reader, world = _two_families(tmp_path, monkeypatch)

    def mutate(*args, **kwargs):
        reader.raw = replace(reader.raw, player_money=0)
        raise RuntimeError("partial probe failed")

    monkeypatch.setattr(module, "bind_native_boxed_item_evolution", mutate)
    with pytest.raises(ValueError, match="changed the game"):
        _enumerate(runtime, world)


@pytest.mark.parametrize('enabled', [False, True])
def test_routed_targets_use_separate_native_profiles_and_only_evolution_routing(
    tmp_path, monkeypatch, enabled
):
    from test_red_live_option_menu import _binding

    import pokemon_red_completion.red_item_evolution_options as module
    from pokemon_red_completion.observation import MapId

    runtime, reader, world = _two_families(tmp_path, monkeypatch)
    reader.raw = replace(reader.raw, map_id=MapId.ROUTE_1, player_x=1, player_y=1)
    profiles = []

    class Router:
        def __init__(self, native, *args, **kwargs):
            self.native = native
            assert kwargs["include_recovery_offers"] is False
            assert kwargs["maximum_controller_actions"] == 3000
            assert kwargs.get("interruption_handler_wrapper") is (wrapper if enabled else None)

        def enumerate_routed_kinds(self, observation, kinds):
            assert kinds == frozenset({GoalKind.EVOLVE_SPECIES})
            profiles.append(self.native.profile)
            target = next(
                s.parameters["target_species_ref"]
                for s in self.native.profile.providers
                if s.kind is GoalKind.EVOLVE_SPECIES
            )
            return SimpleNamespace(
                bindings=(_binding(GoalKind.EVOLVE_SPECIES, binding_ref=target, calls=[]),)
            )

    monkeypatch.setattr(module, "RedResourceGoalRouter", Router)
    def wrapper(inner, spec):
        return inner

    candidates = _enumerate(
        runtime, world, interruption_handler_wrapper=wrapper if enabled else None,
    )
    assert len(profiles) == len(candidates) == 2
    assert profiles[0] != profiles[1]
    assert [c.profile for c in candidates] == profiles


def test_loaded_cartridge_must_support_every_offered_edge(tmp_path, monkeypatch):
    runtime, _, world = _two_families(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "pokemon_red_completion.red_native_boxed_item_evolution.evolution_graph",
        lambda _: {},
    )
    with pytest.raises(RedGoalContextError, match="loaded cartridge"):
        _enumerate(runtime, world)


@pytest.mark.parametrize('wrapper', [True, 3, object()])
def test_invalid_evolution_wrapper_refuses_before_live_access(wrapper):
    with pytest.raises(TypeError, match='evolution interruption wrapper must be callable'):
        enumerate_red_item_evolutions(
            None, None, None, None, maximum_actions=1, maximum_frames=1,
            interruption_handler_wrapper=wrapper,
        )


def test_full_bag_cannot_be_repaired_by_routing(tmp_path, monkeypatch):
    import pokemon_red_completion.red_item_evolution_options as module

    runtime, reader, world = _two_families(tmp_path, monkeypatch)
    reader.raw = replace(reader.raw, bag_items=tuple((i, 1) for i in range(1, 21)))

    def forbidden(*args, **kwargs):
        raise AssertionError("full bag triggered route search")

    monkeypatch.setattr(module, "RedResourceGoalRouter", forbidden)
    assert _enumerate(runtime, world) == ()
