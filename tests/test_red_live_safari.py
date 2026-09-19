"""Action-free coverage for the ranked live Safari acquisition."""

from types import SimpleNamespace

from pokemon_red_completion.collection import CollectionObservation
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalKind, GoalSituation
from pokemon_red_completion.living_dex_option_value import (
    living_dex_option_context_from_goal_situation,
)
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.red_acquisition import (
    RED_ACQUISITION_CATALOG,
    summarize_red_area_survey,
)
from pokemon_red_completion.red_collection import red_species_ref
from pokemon_red_completion.red_live_safari import (
    RedReachableSafariArea,
    _registered_safari_catalog,
    build_red_live_safari_inventory,
)
from pokemon_red_completion.red_safari_acquisition import (
    RedSafariPatrolPlan,
    RedSafariZoneOffer,
)


def _area(source: str, map_id: int, productive_slots: int, route_steps: int):
    slots = tuple((25, 111 if index < productive_slots else 30) for index in range(10))
    offer = RedSafariZoneOffer(source, map_id, slots, (111,))
    start = {
        int(MapId.SAFARI_ZONE_CENTER): (25, 15),
        int(MapId.SAFARI_ZONE_NORTH): (31, 39),
    }[map_id]
    patrol = RedSafariPatrolPlan(
        source,
        map_id,
        start,
        ("up",),
        (start[0] - 1, start[1]),
        (start[0] - 2, start[1]),
        2,
        "up",
        "down",
    )
    return RedReachableSafariArea(offer, patrol, route_steps)


def test_live_safari_builds_one_ranked_binding_without_input(monkeypatch) -> None:
    center = _area(
        "wild:SafariZoneCenter:grass",
        int(MapId.SAFARI_ZONE_CENTER),
        3,
        4,
    )
    north = _area(
        "wild:SafariZoneNorth:grass",
        int(MapId.SAFARI_ZONE_NORTH),
        2,
        2,
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_live_safari.discover_reachable_red_safari_areas",
        lambda *_args, **_kwargs: (center, north),
    )
    controller = SimpleNamespace(frame_count=0, pressed_buttons=frozenset())
    actions = CountingExecutor(
        SimpleNamespace(execute=lambda _action: (_ for _ in ()).throw(AssertionError("input")))
    )
    reader = SimpleNamespace(read=lambda: SimpleNamespace(player_money=706))
    situation = GoalSituation(
        story_pressure=0.0,
        collection_pressure=1.0,
        team_pressure=0.0,
        evolution_pressure=1.0,
        safety_pressure=0.0,
        resource_pressure=0.0,
        storage_pressure=0.0,
        recovery_pressure=0.0,
        exploration_pressure=0.0,
    )

    inventory = build_red_live_safari_inventory(
        b"rom",
        frozenset(),
        living_dex_option_context_from_goal_situation(situation),
        free_storage_slots=2,
        world=SimpleNamespace(),
        controller=controller,
        actions=actions,
        reader=reader,
    )

    assert inventory.areas == (center, north)
    assert len(inventory.supplements) == 1
    assert inventory.supplements[0].binding.kind is GoalKind.ACQUIRE_SPECIES
    assert inventory.supplements[0].candidate.binding_ref == (
        inventory.supplements[0].binding.binding_ref
    )
    assert actions.actions_executed == controller.frame_count == 0
    assert inventory.public_dict()["identity_fields_public"] == 0


def test_live_safari_empty_inventory_has_no_executor(monkeypatch) -> None:
    monkeypatch.setattr(
        "pokemon_red_completion.red_live_safari.discover_reachable_red_safari_areas",
        lambda *_args, **_kwargs: (),
    )
    actions = CountingExecutor(SimpleNamespace(execute=lambda _action: None))
    inventory = build_red_live_safari_inventory(
        b"rom",
        frozenset(),
        living_dex_option_context_from_goal_situation(
            GoalSituation(0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        ),
        free_storage_slots=1,
        world=SimpleNamespace(),
        controller=SimpleNamespace(frame_count=0, pressed_buttons=frozenset()),
        actions=actions,
        reader=SimpleNamespace(read=lambda: None),
    )
    assert inventory.areas == inventory.supplements == ()
    assert actions.actions_executed == 0


def test_live_safari_single_area_still_builds_top_level_acquisition(monkeypatch) -> None:
    center = _area(
        "wild:SafariZoneCenter:grass",
        int(MapId.SAFARI_ZONE_CENTER),
        3,
        4,
    )
    monkeypatch.setattr(
        "pokemon_red_completion.red_live_safari.discover_reachable_red_safari_areas",
        lambda *_args, **_kwargs: (center,),
    )
    controller = SimpleNamespace(frame_count=0, pressed_buttons=frozenset())
    actions = CountingExecutor(SimpleNamespace(execute=lambda _action: None))
    inventory = build_red_live_safari_inventory(
        b"rom",
        frozenset(),
        living_dex_option_context_from_goal_situation(
            GoalSituation(0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        ),
        free_storage_slots=1,
        world=SimpleNamespace(),
        controller=controller,
        actions=actions,
        reader=SimpleNamespace(read=lambda: SimpleNamespace(player_money=706)),
    )
    assert inventory.areas == (center,)
    assert len(inventory.supplements) == 1
    assert actions.actions_executed == 0


def test_live_safari_execution_catalog_excludes_registered_living_demand() -> None:
    center = _area(
        "wild:SafariZoneCenter:grass",
        int(MapId.SAFARI_ZONE_CENTER),
        3,
        4,
    )
    catalog = _registered_safari_catalog(center, frozenset({48}))
    observation = CollectionObservation(
        owned_species=frozenset({red_species_ref(48)}),
        specimens=(),
        party_size=0,
        party_limit=6,
        box_counts=(0,),
        current_box_index=0,
        box_capacity=20,
    )

    survey = summarize_red_area_survey(center.offer.source_id, observation, catalog)

    assert (
        red_species_ref(48)
        in summarize_red_area_survey(
            center.offer.source_id,
            observation,
            RED_ACQUISITION_CATALOG,
        ).missing_species_refs
    )
    assert survey.missing_species_refs == (red_species_ref(111),)
    assert red_species_ref(48) not in survey.missing_species_refs
