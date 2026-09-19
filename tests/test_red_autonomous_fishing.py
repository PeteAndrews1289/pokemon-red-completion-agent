from types import SimpleNamespace

import pytest

import pokemon_red_completion.red_autonomous_fishing as fishing
from pokemon_red_completion.observation import ItemId


def _inputs():
    raw = SimpleNamespace(
        battle_state=0,
        bag_items=((int(ItemId.SUPER_ROD), 1), (int(ItemId.GREAT_BALL), 6)),
    )
    observation = SimpleNamespace(
        raw=raw, input_ready=True, immediate_capture_slots=2,
        free_storage_slots=99, collection_observation=object(), situation=object(),
    )
    runtime = SimpleNamespace(
        reader=SimpleNamespace(read=lambda: raw),
        emulator=SimpleNamespace(frame_count=17),
        registration_policy=SimpleNamespace(goal_registered=lambda _: {"pokemon:national:099"}),
    )
    actions = SimpleNamespace(actions_executed=0)
    world = SimpleNamespace(rom=b"test", rules=SimpleNamespace(cut_block_swaps=()))
    return runtime, observation, actions, world


@pytest.mark.parametrize("blocked", ("rod", "balls", "storage", "battle", "input"))
def test_fishing_requires_observed_resources_and_safe_input(monkeypatch, blocked):
    runtime, observation, actions, world = _inputs()
    if blocked == "rod":
        observation.raw.bag_items = ((int(ItemId.GREAT_BALL), 6),)
    elif blocked == "balls":
        observation.raw.bag_items = ((int(ItemId.SUPER_ROD), 1),)
    elif blocked == "storage":
        observation.immediate_capture_slots = 0
    elif blocked == "battle":
        observation.raw.battle_state = 1
    else:
        observation.input_ready = False
    monkeypatch.setattr(
        fishing, "build_red_live_fishing_inventory",
        lambda *a, **k: pytest.fail("ineligible fishing must not search routes"),
    )
    assert fishing.autonomous_fishing_options(runtime, observation, actions, world) == ()
    assert actions.actions_executed == 0 and runtime.emulator.frame_count == 17


@pytest.mark.parametrize("mutation", (None, "actions", "frames", "observation"))
def test_fishing_reuses_budget_chain_and_goal_registration_and_rejects_mutation(
    monkeypatch, mutation,
):
    runtime, observation, actions, world = _inputs()
    context, traversal, field = object(), object(), object()
    supplements = (object(), object())
    observed = {}

    def registrations(collection):
        assert collection is observation.collection_observation
        return {"pokemon:national:099"}

    runtime.registration_policy.goal_registered = registrations
    observer = SimpleNamespace(observe=lambda: traversal)
    monkeypatch.setattr(fishing, "Gen1TraversalObserver", lambda *a, **k: observer)
    monkeypatch.setattr(fishing, "Gen1TrainerSightProjector", lambda *a: object())
    monkeypatch.setattr(fishing, "Gen1FieldMovePort", lambda *a, **k: field)
    monkeypatch.setattr(
        fishing, "living_dex_option_context_from_goal_situation", lambda _: context,
    )

    def inventory(rom, registered, passed_context, **kwargs):
        assert rom == world.rom and registered == frozenset({99})
        assert passed_context is context
        observed.update(kwargs)
        if mutation == "actions":
            actions.actions_executed += 1
        elif mutation == "frames":
            runtime.emulator.frame_count += 1
        elif mutation == "observation":
            runtime.reader.read = lambda: object()
        return SimpleNamespace(supplements=supplements)

    monkeypatch.setattr(fishing, "build_red_live_fishing_inventory", inventory)
    if mutation:
        with pytest.raises(ValueError, match="changed the game"):
            fishing.autonomous_fishing_options(runtime, observation, actions, world)
    else:
        actual = fishing.autonomous_fishing_options(runtime, observation, actions, world)
        assert actual is supplements
    assert observed["actions"] is actions
    assert observed["controller"] is observed["emulator"] is runtime.emulator
    assert observed["reader"] is runtime.reader
    assert observed["observer"] is observer and observed["traversal"] is traversal
    assert observed["field"] is field
    assert observed["free_storage_slots"] == 2  # Not total remote-box capacity.
    assert observed["maximum_candidates"] == 4 and observed["maximum_casts"] == 24


def test_fishing_rejects_legacy_completion_policy():
    runtime, observation, actions, world = _inputs()
    runtime.registration_policy = None
    with pytest.raises(ValueError, match="registered collection"):
        fishing.autonomous_fishing_options(runtime, observation, actions, world)
