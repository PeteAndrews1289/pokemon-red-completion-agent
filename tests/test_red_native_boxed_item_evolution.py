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
    monkeypatch.setattr(
        "pokemon_red_completion.red_native_boxed_item_evolution.restore_native_center_party",
        lambda runtime, actions: 0,
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
        plan_feasible_to_map=lambda *args, **kwargs: SimpleNamespace(
            steps=(object(),), segments=()),
        with_current_observation=lambda reader: world,
        replanner=lambda: (lambda request: None),
    )
    return bind_native_boxed_item_evolution(runtime, world), reader


@pytest.mark.parametrize("passed", [True, False])
@pytest.mark.parametrize("destination", [MapId.CELADON_MART_4F, MapId.CELADON_POKECENTER])
def test_stone_transport_refreshes_geometry_and_keeps_blocker_replanning(
    monkeypatch, passed, destination,
):
    import pokemon_red_completion.red_native_boxed_item_evolution as module
    from pokemon_red_completion.red_resource_goal_router import _ROUTE_LIMITS

    reader, snapshot, actions = object(), object(), object()
    plan = SimpleNamespace(segments=(
        SimpleNamespace(source_map=6, target_map=122, passage_kind="warp",
            transition=SimpleNamespace(exit_at=(13, 10), arrival_at=(7, 16))),
        SimpleNamespace(source_map=6, target_map=8, passage_kind="connection"),
    ))
    def replan(request):
        return request

    calls = []
    current = SimpleNamespace(
        plan_feasible_to_map=lambda start, goal, **kw: calls.append((start, goal, kw)) or plan,
        replanner=lambda: replan,
    )
    world = SimpleNamespace(
        with_current_observation=lambda actual: calls.append(actual) or current,
    )
    traversal = SimpleNamespace(observe=lambda: snapshot)

    def execute(actual_plan, actual_actions, actual_traversal, **kw):
        assert (actual_plan, actual_actions, actual_traversal) == (plan, actions, traversal)
        assert kw == dict(limits=_ROUTE_LIMITS, replanner=replan, interruption_handler=handler)
        return SimpleNamespace(passed=passed)

    monkeypatch.setattr(module, "execute_route", execute)
    handler = object()
    emulator = object()
    def bind_handler(actual_actions, actual_reader, **kwargs):
        assert actual_reader is reader and actual_actions is actions
        assert kwargs == dict(maximum_flees=0, stabilization_frames=120,
            allow_party_faints=True, emulator=emulator,
            allow_field_faint_dialogue=True, route_name="local item evolution transport",
            field_faint_warps=((6, (13, 10), 122, (7, 16)),))
        return handler
    monkeypatch.setattr(module, "Gen1WildFleeHandler", bind_handler)
    result = module._native_item_transport(SimpleNamespace(reader=reader, emulator=emulator), world,
        actions, traversal, int(destination), goal_at=(4, 13))
    assert result.passed is passed
    assert calls == [reader, (snapshot, int(destination), dict(goal_at=(4, 13)))]


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


def test_boxed_stone_admits_spare_of_a_retained_active_species(tmp_path, monkeypatch):
    runtime, reader = _runtime(tmp_path, monkeypatch, source=44, target=45, item=ItemId.LEAF_STONE)
    reader.raw = replace(
        reader.raw,
        party_species_ids=(red_internal_species_id(44), *reader.raw.party_species_ids[1:]),
    )
    before = reader.read(), runtime.emulator.frame_count
    assert runtime.boxed_item_evolution_readiness(runtime.adapter.observe()).executable
    assert before == (reader.read(), runtime.emulator.frame_count)


@pytest.mark.parametrize("fault", [None, "empty_move", "slot", "level", "detector"])
def test_prompt_capability_requires_explicit_scope_and_exact_boxed_moves(
    tmp_path, monkeypatch, fault,
):
    runtime, reader = _runtime(tmp_path, monkeypatch, source=33, target=34, item=ItemId.MOON_STONE)
    reader.raw = replace(reader.raw, bag_items=((int(ItemId.MOON_STONE), 1),))
    monkeypatch.setattr("pokemon_red_completion.red_native_boxed_item_evolution.level_up_learnsets",
                        lambda _: {34: ((30, 37),)})
    reader.read_move_learning_prompt = None if fault == "detector" else lambda *a, **k: None
    reader.read_box_move_members = lambda _: (SimpleNamespace(
        box_slot=2 if fault == "slot" else 1,
        species_id=red_internal_species_id(33), level=31 if fault == "level" else 30,
        moves=(33, 30, 40, 0 if fault == "empty_move" else 116),
    ),)
    assert not runtime.boxed_item_evolution_readiness(runtime.adapter.observe()).executable
    world = SimpleNamespace(rom=b"fixture", plan_feasible_to_map=lambda *a, **k: SimpleNamespace(
        steps=(object(),), segments=(),
    ))
    native = bind_native_boxed_item_evolution(runtime, world, allow_move_learning_preservation=True)
    before = reader.read(), runtime.emulator.frame_count
    ready = native.boxed_item_evolution_readiness(native.adapter.observe())
    assert ready.executable is (fault is None)
    assert before == (reader.read(), runtime.emulator.frame_count)


@pytest.mark.parametrize("fault", [None, "failed", "species", "drift", "wrong_count", "reordered"])
def test_withdrawn_stone_slot_never_selects_the_active_duplicate(fault):
    from pokemon_red_completion.red_goal_context import RedGoalContextError
    from pokemon_red_completion.red_native_boxed_item_evolution import _withdrawn_precursor_slot

    before = (186, 28, 151, 166, 114)
    after = (*before, 186)
    report = SimpleNamespace(
        passed=fault != "failed",
        species_id=28 if fault == "species" else 186,
        party_before=before[:4] if fault == "wrong_count" else before,
        party_after=(186, 186, 28, 151, 166, 114) if fault == "reordered" else after,
    )
    party = (*before, 28) if fault == "drift" else after
    if fault is None:
        assert _withdrawn_precursor_slot(party, report, 186) == 5
    else:
        with pytest.raises(RedGoalContextError, match="withdrawn precursor"):
            _withdrawn_precursor_slot(party, report, 186)


@pytest.mark.parametrize("stock", [0, 1, 2, 99])
def test_moon_stone_is_held_only_never_procured_from_mart(tmp_path, monkeypatch, stock):
    runtime, reader = _runtime(tmp_path, monkeypatch, source=30, target=31, item=ItemId.MOON_STONE)
    reader.raw = replace(
        reader.raw,
        player_money=999999,
        bag_items=((int(ItemId.MOON_STONE), stock),) if stock else (),
    )
    before = reader.read(), runtime.emulator.frame_count
    assert runtime.boxed_item_evolution_readiness(runtime.adapter.observe()).executable is bool(
        stock
    )
    assert before == (reader.read(), runtime.emulator.frame_count)


@pytest.mark.parametrize("remaining,passes", [(2, True), (3, False), (1, False), (0, False)])
def test_boxed_pipeline_requires_exact_one_stone_from_stack(
    tmp_path, monkeypatch, remaining, passes
):
    import pokemon_red_completion.red_native_boxed_item_evolution as module
    from pokemon_red_completion.red_goal_context import RedGoalContextError

    runtime, reader = _runtime(tmp_path, monkeypatch, source=30, target=31, item=ItemId.MOON_STONE)
    reader.raw = replace(reader.raw, bag_items=((int(ItemId.MOON_STONE), 3),))
    old_owned = reader.read_pokedex_state().owned_species
    reader.read_current_box_state = lambda: reader.boxes.boxes[reader.boxes.current_box_index]
    monkeypatch.setattr(module, "prepare_center_departure", lambda *a: None)
    monkeypatch.setattr(module, "execute_route", lambda *a, **k: SimpleNamespace(passed=True))
    for name in ("face_pc_boundary", "open_bills_pc", "close_generic_pc_session"):
        monkeypatch.setattr(module, name, lambda *a, **k: None)
    monkeypatch.setattr(
        module, "deposit_party_member", lambda *a, **k: SimpleNamespace(passed=True)
    )

    def withdraw(*args, **kwargs):
        deposited = reader.raw.party_species_ids[-1]
        reader.raw = replace(
            reader.raw,
            party_species_ids=(*reader.raw.party_species_ids[:-1], red_internal_species_id(30)),
        )
        reader.boxes = replace(
            reader.boxes,
            boxes=(
                RedCurrentBoxState(0, (deposited,), (reader.raw.party_levels[-1],)),
                *reader.boxes.boxes[1:],
            ),
        )
        return SimpleNamespace(
            passed=True,
            species_id=red_internal_species_id(30),
            party_before=reader.raw.party_species_ids[:-1],
            party_after=reader.raw.party_species_ids,
        )

    monkeypatch.setattr(module, "withdraw_box_member", withdraw)

    def evolve(*args):
        reader.raw = replace(
            reader.raw,
            party_species_ids=(*reader.raw.party_species_ids[:-1], red_internal_species_id(31)),
            bag_items=((int(ItemId.MOON_STONE), remaining),) if remaining else (),
        )
        reader.read_pokedex_state = lambda: SimpleNamespace(
            owned_species=old_owned | {31}, seen_species=old_owned | {31}
        )
        return SimpleNamespace(success=True)

    monkeypatch.setattr(
        module, "RedPartyItemEvolutionExecutor", lambda *a: SimpleNamespace(execute=evolve)
    )
    monkeypatch.setattr(
        module,
        "purchase_celadon_evolution_stone",
        lambda *a, **k: pytest.fail("finite stone purchased"),
    )
    actions = CountingExecutor(_ActionDelegate())
    settlements = []
    monkeypatch.setattr(
        module,
        "settle_native_evolution",
        lambda rt, port: (
            settlements.append((rt, port)) or {"retained_active_roster_restored": True}
        ),
    )
    offer = runtime.provider_for(GoalKind.EVOLVE_SPECIES, actions).offer(runtime.adapter.observe())
    assert offer.binding is not None
    if passes:
        report = offer.binding.execute()
        assert report.evidence["money_spent"] == 0
        assert report.evidence["procurement_executed"] is False
        assert reader.raw.player_money == 6528
        assert len(settlements) == 1
        assert settlements[0][1] is actions
        assert report.evidence["retained_active_roster_restored"] is True
    else:
        with pytest.raises(RedGoalContextError, match="pipeline failed verification"):
            offer.binding.execute()
        assert settlements == []


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

    runtime, reader = _runtime(tmp_path, monkeypatch, source=58, target=59, item=ItemId.FIRE_STONE)
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

    recovered = []
    def restore(actual_runtime, actual_actions):
        assert actual_runtime.reader is reader and actual_actions is actions
        assert not dialogue_visible
        recovered.append("counted normal nurse recovery")
        reader.raw = replace(reader.raw, party_hp=reader.raw.party_max_hp,
                             party_status=(0,) * len(reader.raw.party_hp))
        return 1
    monkeypatch.setattr(module, "restore_native_center_party", restore)

    def route(*_args, **_kwargs):
        raise ReachedRoute

    monkeypatch.setattr(module, "execute_route", route)
    if dialogue_visible:
        with pytest.raises(RedGoalSkillError, match="healed nurse boundary"):
            offer.binding.execute()
    else:
        with pytest.raises(ReachedRoute):
            offer.binding.execute()
    assert bool(recovered) is (not dialogue_visible)
    assert actions.actions_executed == 0


def test_failed_existing_nurse_recovery_cannot_start_item_procurement(tmp_path, monkeypatch):
    import pokemon_red_completion.red_native_boxed_item_evolution as module
    from pokemon_red_completion.red_goal_context import RedGoalContextError
    runtime, reader = _runtime(tmp_path, monkeypatch, source=58, target=59, item=ItemId.FIRE_STONE)
    reader.read_bottom_dialogue_box_visible = lambda: False
    actions = CountingExecutor(_ActionDelegate())
    offer = runtime.provider_for(GoalKind.EVOLVE_SPECIES, actions).offer(runtime.adapter.observe())
    assert offer.binding is not None
    def refuse(*args):
        raise RedGoalContextError("native Center recovery did not preserve and heal the party")
    monkeypatch.setattr(module, "restore_native_center_party", refuse)
    monkeypatch.setattr(module, "execute_route",
                        lambda *a, **k: pytest.fail("procurement after failed heal"))
    with pytest.raises(RedGoalContextError, match="preserve and heal"):
        offer.binding.execute()
    assert actions.actions_executed == 0
