from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_red_goal_context import _ActionDelegate
from test_red_native_boxed_evolution import runtime_fixture

from pokemon_red_completion.collection import CollectionLocation
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.gen1_cartridge import Evolution, EvolutionMethod
from pokemon_red_completion.goal_manager import GoalKind, GoalUnavailableReason
from pokemon_red_completion.observation import (
    ItemId,
    MapId,
    RedBoxCollectionState,
    RedCurrentBoxState,
)
from pokemon_red_completion.red_collection import (
    RED_COLLECTION_GAME_ID,
    red_internal_species_id,
    red_internal_species_number,
    red_species_ref,
)
from pokemon_red_completion.red_goal_context import build_red_goal_context_runtime
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalMechanic,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.red_goal_skills import RedGoalSkillError
from pokemon_red_completion.red_native_boxed_item_evolution import (
    bind_native_boxed_item_evolution,
)
from pokemon_red_completion.red_party import BLASTOISE_SPECIES_ID
from pokemon_red_completion.red_registration_policy import RedRegistrationPolicy
from pokemon_red_completion.registration_memory import (
    RegistrationSnapshot,
    observation_from_collection,
)
from pokemon_red_completion.route_executor import TraversalSnapshot


def _runtime(
    tmp_path,
    monkeypatch,
    *,
    source,
    target,
    item,
    bag_full=False,
    depositable=True,
    at_pc=False,
):
    original, reader, _ = runtime_fixture(tmp_path)
    party = (
        original.adapter.observe().party.species_ids()
        if depositable
        else (BLASTOISE_SPECIES_ID,) * 6
    )
    bag = (
        tuple((number, 1) for number in range(1, 21))
        if bag_full
        else ((int(ItemId.POKE_BALL), 10),)
    )
    reader.raw = replace(
        reader.raw,
        map_id=MapId.CELADON_POKECENTER,
        player_x=4 if at_pc else 3,
        player_y=13 if at_pc else 3,
        player_money=6_528,
        bag_items=bag,
        bag_item_ids=tuple(row[0] for row in bag),
        party_species_ids=party,
    )
    reader.boxes = RedBoxCollectionState(
        (
            RedCurrentBoxState(0, (red_internal_species_id(source),), (30,)),
            *(RedCurrentBoxState(index, (), ()) for index in range(1, 12)),
        ),
        0,
        True,
    )
    owned = {
        red_internal_species_number(species)
        for species in (*party, red_internal_species_id(source))
    }
    reader.read_pokedex_state = lambda: SimpleNamespace(
        seen_species=frozenset(owned),
        owned_species=frozenset(owned),
    )
    providers = tuple(
        (
            spec.kind,
            (
                RedGoalMechanic.TARGETED_ITEM_EVOLUTION
                if spec.kind is GoalKind.EVOLVE_SPECIES
                else spec.mechanic
            ),
            (
                {
                    "source_species_ref": red_species_ref(source),
                    "target_species_ref": red_species_ref(target),
                    "item_id": int(item),
                }
                if spec.kind is GoalKind.EVOLVE_SPECIES
                else dict(spec.parameters)
            ),
        )
        for spec in original.profile.providers
    )
    profile = parse_red_goal_context_profile(
        build_red_goal_context_profile_payload(
            profile_id=original.profile.profile_id,
            providers=providers,
        )
    )
    runtime = build_red_goal_context_runtime(
        profile=profile,
        capture=original.capture,
        emulator=original.emulator,
        reader=reader,
    )
    collection = runtime.adapter.observe().collection_observation
    national_ids = {red_species_ref(number): number for number in range(1, 152)}
    row = observation_from_collection(
        collection,
        seen_species=collection.owned_species,
        national_ids=national_ids,
        run_id="current",
        game_id=RED_COLLECTION_GAME_ID,
        adapter_id="red-v1",
        cartridge_sha256="a" * 64,
        snapshot_sha256="b" * 64,
        sequence=0,
    )
    runtime = replace(
        runtime,
        registration_policy=RedRegistrationPolicy(
            RegistrationSnapshot((row,)),
            "current",
            "b" * 64,
            collection,
            {},
        ),
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_native_boxed_item_evolution.evolution_graph",
        lambda rom: {source: (Evolution(source, target, EvolutionMethod.STONE, int(item)),)},
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_native_boxed_item_evolution.level_up_learnsets",
        lambda rom: {},
    )
    snapshot = TraversalSnapshot(
        int(MapId.CELADON_POKECENTER),
        (4, 13) if at_pc else (3, 3),
        True,
        mode="land",
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_native_boxed_item_evolution.Gen1TraversalObserver",
        lambda reader: SimpleNamespace(observe=lambda: snapshot),
    )
    world = SimpleNamespace(
        rom=b"fixture",
        plan_feasible_to_map=lambda *args, **kwargs: SimpleNamespace(steps=(object(),)),
    )
    return bind_native_boxed_item_evolution(runtime, world), reader


def test_resource_readiness_is_action_free_before_router_moves_from_pc(
    tmp_path,
    monkeypatch,
):
    runtime, reader = _runtime(
        tmp_path,
        monkeypatch,
        source=58,
        target=59,
        item=ItemId.FIRE_STONE,
        at_pc=True,
    )
    before = (reader.raw.player_money, reader.raw.bag_items, runtime.emulator.frame_count)
    assert runtime.boxed_item_evolution_readiness is not None

    availability = runtime.boxed_item_evolution_readiness(runtime.adapter.observe())

    assert availability.executable
    assert (reader.raw.player_money, reader.raw.bag_items, runtime.emulator.frame_count) == before


@pytest.mark.parametrize(
    ("source", "target", "item"),
    (
        (58, 59, ItemId.FIRE_STONE),
        (61, 62, ItemId.WATER_STONE),
    ),
)
def test_two_stone_families_are_ready_without_spending_or_input(
    tmp_path,
    monkeypatch,
    source,
    target,
    item,
):
    runtime, reader = _runtime(
        tmp_path,
        monkeypatch,
        source=source,
        target=target,
        item=item,
    )
    actions = CountingExecutor(_ActionDelegate())
    before = (reader.raw.player_money, reader.raw.bag_items, runtime.emulator.frame_count)

    offer = runtime.provider_for(GoalKind.EVOLVE_SPECIES, actions).offer(runtime.adapter.observe())

    assert offer.binding is not None
    assert actions.actions_executed == 0
    assert (reader.raw.player_money, reader.raw.bag_items, runtime.emulator.frame_count) == before
    specimens = runtime.adapter.observe().collection_observation.specimens
    assert any(
        specimen.species_ref == red_species_ref(source)
        and specimen.location is CollectionLocation.BOX
        for specimen in specimens
    )


@pytest.mark.parametrize("failure", ("full_bag", "no_depositable_party"))
def test_item_evolution_atomic_gate_rejects_partial_pipeline(
    tmp_path,
    monkeypatch,
    failure,
):
    runtime, reader = _runtime(
        tmp_path,
        monkeypatch,
        source=58,
        target=59,
        item=ItemId.FIRE_STONE,
        bag_full=failure == "full_bag",
        depositable=failure != "no_depositable_party",
    )
    actions = CountingExecutor(_ActionDelegate())
    before = (reader.raw.player_money, reader.raw.bag_items, runtime.emulator.frame_count)

    offer = runtime.provider_for(GoalKind.EVOLVE_SPECIES, actions).offer(runtime.adapter.observe())

    assert offer.binding is None
    assert offer.unavailable_reason in {
        GoalUnavailableReason.MISSING_CAPABILITY,
        GoalUnavailableReason.NO_LEGAL_TARGET,
    }
    assert actions.actions_executed == 0
    assert (reader.raw.player_money, reader.raw.bag_items, runtime.emulator.frame_count) == before


@pytest.mark.parametrize("dialogue_visible", [False, True])
def test_item_evolution_departure_from_unhealed_nurse_boundary(
    tmp_path, monkeypatch, dialogue_visible
):
    import pokemon_red_completion.red_native_boxed_item_evolution as module

    runtime, reader = _runtime(
        tmp_path, monkeypatch, source=58, target=59, item=ItemId.FIRE_STONE
    )
    reader.raw = replace(
        reader.raw, party_hp=(reader.raw.party_hp[0] - 1, *reader.raw.party_hp[1:])
    )
    assert reader.raw.party_hp != reader.raw.party_max_hp
    reader.read_bottom_dialogue_box_visible = lambda: dialogue_visible
    actions = CountingExecutor(_ActionDelegate())
    offer = runtime.provider_for(GoalKind.EVOLVE_SPECIES, actions).offer(runtime.adapter.observe())
    assert offer.binding is not None

    class ReachedRoute(RuntimeError):
        pass

    def route(*_args, **_kwargs):
        raise ReachedRoute

    monkeypatch.setattr(module, "execute_route", route)
    if dialogue_visible:
        with pytest.raises(RedGoalSkillError, match="healed nurse boundary"):
            offer.binding.execute()
    else:
        with pytest.raises(ReachedRoute):
            offer.binding.execute()
    assert actions.actions_executed == 0
