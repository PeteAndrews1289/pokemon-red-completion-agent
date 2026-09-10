"""Exercise registered stock through the real boxed bridge and adapter."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_boxed_level_evolution import (
    EVOLVED,
    HITMONLEE_SPECIES_ID,
    PRECURSOR,
    RESET,
    _patch_storage,
    _routes,
    _world,
)

from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.red_boxed_level_evolution import BoundedEvolutionTrainingResult
from pokemon_red_completion.red_collection import RED_COLLECTION_GAME_ID, red_species_ref
from pokemon_red_completion.red_goal_boxed_evolution import RedGoalBoxedEvolutionExecutor
from pokemon_red_completion.red_goal_context import RedBoxedLevelEvolutionGoalRequest
from pokemon_red_completion.red_registration_policy import RedRegistrationPolicy
from pokemon_red_completion.registration_memory import (
    RegistrationSnapshot,
    observation_from_collection,
)


def bridge_fixture(monkeypatch, *, copies=3, reserve=0, damage=None):
    world = _world()
    world.box = [PRECURSOR] * copies + [0x54]
    _patch_storage(monkeypatch, world)
    initial_owned = world.collection().owned_species
    finished = False

    def observe():
        current = world.collection()
        owned = current.owned_species | initial_owned
        if finished and damage == "owned_flag":
            owned -= {red_species_ref(11)}
        return replace(current, owned_species=owned)

    initial = observe()
    row = observation_from_collection(
        initial, seen_species=initial.owned_species,
        national_ids={red_species_ref(n): n for n in range(1, 152)},
        run_id="native-stock", game_id=RED_COLLECTION_GAME_ID, adapter_id="red-v1",
        cartridge_sha256="a" * 64, snapshot_sha256="b" * 64, sequence=0,
    )
    policy = RedRegistrationPolicy(
        RegistrationSnapshot((row,)), "native-stock", "b" * 64, initial,
        {red_species_ref(11): reserve},
    )

    def train(source, target):
        nonlocal finished
        assert source == PRECURSOR and target == EVOLVED
        world.party[world.party.index(source)] = target
        if damage == "other_stock":
            world.box.pop()
        finished = True
        return BoundedEvolutionTrainingResult(3, 0)

    to_pc, to_training = _routes()
    bridge = RedGoalBoxedEvolutionExecutor(
        reset_state_sha256=RESET, route_to_pc=to_pc, route_to_training=to_training,
        training_binding_sha256="d" * 64, reader=world, traversal_observer=world,
        observe_collection=observe, train_evolution=train,
        emulator=SimpleNamespace(frame_count=0), registration_policy=policy,
    )
    request = RedBoxedLevelEvolutionGoalRequest(
        PRECURSOR, EVOLVED, 0, copies, 6, HITMONLEE_SPECIES_ID,
    )
    return bridge, request, CountingExecutor(world), world


@pytest.mark.parametrize("copies,reserve", [(1, 0), (3, 2), (5, 4)])
def test_registered_bridge_executes_exact_one_copy_transition(monkeypatch, copies, reserve):
    bridge, request, actions, world = bridge_fixture(monkeypatch, copies=copies, reserve=reserve)
    report = bridge(request, actions)
    assert report.evidence["exact_evolution_transition"] is True
    assert world.box.count(PRECURSOR) == copies - 1
    assert world.party.count(EVOLVED) == 1
    assert HITMONLEE_SPECIES_ID in world.box
    assert actions.actions_executed == 2
    assert "required_living_preserved" not in report.evidence


def test_registered_bridge_refuses_fully_reserved_stock_before_input(monkeypatch):
    bridge, request, actions, world = bridge_fixture(monkeypatch, copies=3, reserve=3)
    with pytest.raises(Exception, match="reserve"):
        bridge(request, actions)
    assert actions.actions_executed == 0 and world.log == []


@pytest.mark.parametrize("damage", ["other_stock", "owned_flag"])
def test_registered_bridge_rejects_real_post_execution_loss(monkeypatch, damage):
    bridge, request, actions, _ = bridge_fixture(monkeypatch, copies=1, damage=damage)
    with pytest.raises((RuntimeError, ValueError), match="collection|registration|owned"):
        bridge(request, actions)
    assert actions.actions_executed > 0
