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
        raw=raw,
        input_ready=True,
        immediate_capture_slots=2,
        free_storage_slots=99,
        collection_observation=object(),
        situation=object(),
    )
    runtime = SimpleNamespace(
        reader=SimpleNamespace(read=lambda: raw),
        emulator=SimpleNamespace(frame_count=17),
        registration_policy=SimpleNamespace(goal_registered=lambda _: {"pokemon:national:099"}),
    )
    actions = SimpleNamespace(actions_executed=0)
    world = SimpleNamespace(rom=b"test", rules=SimpleNamespace(cut_block_swaps=()))
    return runtime, observation, actions, world


@pytest.mark.parametrize("blocker", [None, "stock", "final_credit", "wrong_edge"])
def test_fishing_dependency_requires_missing_final_and_actual_spare_demand(
    tmp_path, monkeypatch, blocker,
):
    from dataclasses import replace
    from test_registered_runtime_binding import bound_fixture
    from pokemon_red_completion.gen1_cartridge import EvolutionMethod
    from pokemon_red_completion.red_collection import red_species_ref

    runtime, _, _ = bound_fixture(tmp_path, inherited=(61,))
    observation = runtime.adapter.observe()
    collection = replace(observation.collection_observation,
                         owned_species=observation.collection_observation.owned_species | {
                             red_species_ref(61),
                         })
    if blocker == "stock":
        specimen = collection.specimens[0]
        collection = replace(collection, specimens=(
            replace(specimen, species_ref=red_species_ref(61)), *collection.specimens[1:],
        ))
    if blocker == "final_credit":
        collection = replace(collection, owned_species=collection.owned_species | {red_species_ref(62)})
    observation = replace(observation, collection_observation=collection)
    monkeypatch.setattr(fishing, "evolution_graph", lambda _: {} if blocker == "wrong_edge" else {
        61: (SimpleNamespace(method=EvolutionMethod.STONE, to_species=62),),
    })
    before = runtime.registration_policy.goal_registered(collection)
    assert fishing.stone_precursor_fishing_demand(runtime, observation, b"rom") == (
        (61,) if blocker is None else ()
    )
    assert runtime.registration_policy.goal_registered(collection) == before


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
        fishing,
        "build_red_live_fishing_inventory",
        lambda *a, **k: pytest.fail("ineligible fishing must not search routes"),
    )
    assert fishing.autonomous_fishing_options(runtime, observation, actions, world) == ()
    assert actions.actions_executed == 0 and runtime.emulator.frame_count == 17


@pytest.mark.parametrize("mutation", (None, "actions", "frames", "observation"))
@pytest.mark.parametrize("safari", (False, True))
@pytest.mark.parametrize("wrapped", (False, True))
def test_fishing_reuses_budget_chain_and_goal_registration_and_rejects_mutation(
    monkeypatch,
    mutation,
    safari,
    wrapped,
):
    runtime, observation, actions, world = _inputs()
    if safari:
        observation.raw.map_id = 217
        observation.raw.bag_items = ((int(ItemId.SUPER_ROD), 1),)
        monkeypatch.setattr(
            fishing, "require_safari_session", lambda _: SimpleNamespace(safari_steps=129)
        )
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
        fishing,
        "living_dex_option_context_from_goal_situation",
        lambda _: context,
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
    def wrapper(inner):
        pytest.fail('inventory invoked the battle wrapper')
    options = {} if not wrapped else {'interruption_handler_wrapper': wrapper}
    if mutation:
        with pytest.raises(ValueError, match="changed the game"):
            fishing.autonomous_fishing_options(runtime, observation, actions, world, **options)
    else:
        actual = fishing.autonomous_fishing_options(runtime, observation, actions, world, **options)
        assert actual is supplements
    assert observed.get('interruption_handler_wrapper') is (wrapper if wrapped else None)
    assert observed["actions"] is actions
    assert observed["controller"] is observed["emulator"] is runtime.emulator
    assert observed["reader"] is runtime.reader
    assert observed["observer"] is observer and observed["traversal"] is traversal
    assert observed["field"] is field
    assert observed["free_storage_slots"] == 2  # Not total remote-box capacity.
    assert observed["maximum_candidates"] == 4 and observed["maximum_casts"] == 24
    assert observed["safari_session_steps"] == (129 if safari else None)


@pytest.mark.parametrize('wrapper', [True, 1, object()])
def test_fishing_rejects_noncallable_battle_wrapper(wrapper):
    runtime, observation, actions, world = _inputs()
    with pytest.raises(TypeError, match='wrapper must be callable'):
        fishing.autonomous_fishing_options(runtime, observation, actions, world,
                                           interruption_handler_wrapper=wrapper)
    assert actions.actions_executed == 0 and runtime.emulator.frame_count == 17


def test_fishing_rejects_legacy_completion_policy():
    runtime, observation, actions, world = _inputs()
    runtime.registration_policy = None
    with pytest.raises(ValueError, match="registered collection"):
        fishing.autonomous_fishing_options(runtime, observation, actions, world)
