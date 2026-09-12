from dataclasses import dataclass
from types import SimpleNamespace

import pytest

import pokemon_red_completion.red_routed_storage_relief as storage
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.route_plan import RoutePlanningError


@dataclass
class Router:
    runtime: object
    actions: object
    world: object
    routed_recovery: bool = False

    def _replan(self, _request):
        pytest.fail("no replan in this fixture")

    def plan_feasible_to_map(self, *args, **kwargs):
        return self.world.plan_feasible_to_map(*args, **kwargs)


def fixture(monkeypatch):
    calls = []
    actions = SimpleNamespace(actions_executed=0)
    emulator = SimpleNamespace(frame_count=0)
    raw = SimpleNamespace(map_id=22, player_y=5, player_x=6, battle_state=0,
                          bag_items=((4, 2),), player_money=109)
    collection = SimpleNamespace(current_box_index=0,
        box_counts=(20, 3, 0) + (20,) * 9, box_capacity=20,
        specimens=("a", "a", "b"))
    observation = SimpleNamespace(raw=raw, input_ready=True,
        collection_observation=collection, immediate_capture_slots=0)
    traversal = SimpleNamespace(observe=lambda: (raw.map_id, raw.player_y, raw.player_x))
    adapter = SimpleNamespace(observe=lambda: observation)
    runtime = SimpleNamespace(reader=SimpleNamespace(), emulator=emulator, adapter=adapter)
    route = SimpleNamespace(steps=(1, 2), terminal_map=64)
    world = SimpleNamespace(plan_feasible_to_map=lambda *_a, **_k: route)
    router = Router(runtime, actions, world)
    other = ExecutableGoalBinding("evolution", GoalKind.EVOLVE_SPECIES, .3, .1,
        execute=lambda: pytest.fail("goal changed"),
        verify=lambda _: GoalVerification.succeeded())
    restore = ExecutableGoalBinding("restore", GoalKind.RESTORE_TEAM, .2, .1,
        execute=lambda: pytest.fail("goal changed"),
        verify=lambda _: GoalVerification.succeeded())
    bindings = GoalBindingSet((other.opportunity, restore.opportunity), (other, restore))

    monkeypatch.setattr(storage, "Gen1TraversalObserver", lambda _: traversal)
    monkeypatch.setattr(storage, "_POKEMON_CENTER_MAPS", (64,))
    monkeypatch.setattr(storage, "dependency_specimen_ledger", lambda c: tuple(c.specimens))
    monkeypatch.setattr(storage, "prepare_center_departure", lambda *_: None)
    monkeypatch.setattr(storage, "Gen1RouteInterruptionHandler", lambda *_a, **_k: None)
    monkeypatch.setattr("pokemon_red_completion.red_resource_goal_router._walking_plan",
                        lambda _: True)

    def tick(action_count, frame_count):
        actions.actions_executed += action_count
        emulator.frame_count += frame_count

    def travel(*_a, **_k):
        calls.append("travel")
        tick(7, 50)
        raw.map_id, raw.player_y, raw.player_x = 64, 4, 13
        return SimpleNamespace(passed=True)

    def switch(target_box_index):
        calls.append(("switch", target_box_index))
        tick(3, 30)
        collection.current_box_index = target_box_index
        observation.immediate_capture_slots = 20 - collection.box_counts[target_box_index]
        return GoalExecutionReport(3, 30, {"collection_preserved": True})

    def provider(*, target_box_index, **_kwargs):
        binding = ExecutableGoalBinding("local-box-switch", GoalKind.MANAGE_STORAGE,
            .08, .03, execute=lambda: switch(target_box_index),
            verify=lambda _: GoalVerification.succeeded())
        return SimpleNamespace(offer=lambda _observation: SimpleNamespace(binding=binding))

    monkeypatch.setattr(storage, "execute_route", travel)
    monkeypatch.setattr(storage, "face_pc_boundary",
                        lambda *_a: (calls.append("face"), tick(1, 1)))
    monkeypatch.setattr(storage, "RedBoxSwitchGoalProvider", provider)
    return SimpleNamespace(router=router, bindings=bindings, observation=observation,
        collection=collection, raw=raw, calls=calls, travel=travel)


def test_full_active_box_offers_action_free_routed_relief(monkeypatch):
    f = fixture(monkeypatch)
    result = storage.bind_routed_storage_relief(f.router, f.bindings, f.observation)
    assert f.calls == []
    selected = next(item for item in result.bindings if item.kind is GoalKind.MANAGE_STORAGE)
    report = selected.execute()
    assert report.evidence["routed_storage_relief"] == {
        "initial_box_index": 0, "target_box_index": 2, "headroom_gained": 20,
        "collection_preserved": True, "setup_training_rows": 0, "route_steps": 2,
    }
    assert selected.verify(report).status.value == "succeeded"
    assert f.calls == ["travel", "face", ("switch", 2)]
    with pytest.raises(storage.RedRoutedStorageReliefError, match="consumed"):
        selected.execute()


@pytest.mark.parametrize("condition", ["room", "no_target", "route", "existing"])
def test_relief_is_not_fabricated(monkeypatch, condition):
    f = fixture(monkeypatch)
    if condition == "room":
        f.collection.box_counts = (19, 3, 0) + (20,) * 9
        f.observation.immediate_capture_slots = 1
    elif condition == "no_target":
        f.collection.box_counts = (20,) * 12
    elif condition == "route":
        f.router.world.plan_feasible_to_map = lambda *_a, **_k: (_ for _ in ()).throw(
            RoutePlanningError("blocked"))
    else:
        existing = ExecutableGoalBinding("existing-storage", GoalKind.MANAGE_STORAGE,
            .1, .1, execute=lambda: pytest.fail("not executed"),
            verify=lambda _: GoalVerification.succeeded())
        f.bindings = GoalBindingSet((*f.bindings.opportunities, existing.opportunity),
                                    (*f.bindings.bindings, existing))
    assert storage.bind_routed_storage_relief(
        f.router, f.bindings, f.observation) is f.bindings
    assert f.calls == []


@pytest.mark.parametrize("change", ["location", "box", "ledger", "money"])
def test_relief_rejects_stale_start_before_input(monkeypatch, change):
    f = fixture(monkeypatch)
    selected = next(item for item in storage.bind_routed_storage_relief(
        f.router, f.bindings, f.observation).bindings
        if item.kind is GoalKind.MANAGE_STORAGE)
    if change == "location":
        f.raw.player_x += 1
    elif change == "box":
        f.collection.current_box_index = 1
    elif change == "ledger":
        f.collection.specimens = ("different",)
    else:
        f.raw.player_money += 1
    with pytest.raises(storage.RedRoutedStorageReliefError, match="changed before input"):
        selected.execute()
    assert f.calls == []


@pytest.mark.parametrize("change", ["ledger", "bag", "money", "not_ready", "failed"])
def test_transport_cannot_hide_protected_mutation(monkeypatch, change):
    f = fixture(monkeypatch)
    travel = storage.execute_route

    def corrupt(*args, **kwargs):
        result = travel(*args, **kwargs)
        if change == "ledger":
            f.collection.specimens = ("different",)
        elif change == "bag":
            f.raw.bag_items = ()
        elif change == "money":
            f.raw.player_money += 1
        elif change == "not_ready":
            f.observation.input_ready = False
        else:
            result.passed = False
        return result

    monkeypatch.setattr(storage, "execute_route", corrupt)
    selected = next(item for item in storage.bind_routed_storage_relief(
        f.router, f.bindings, f.observation).bindings
        if item.kind is GoalKind.MANAGE_STORAGE)
    with pytest.raises(storage.RedRoutedStorageReliefError, match="protected state"):
        selected.execute()
    assert not any(isinstance(item, tuple) and item[0] == "switch" for item in f.calls)
