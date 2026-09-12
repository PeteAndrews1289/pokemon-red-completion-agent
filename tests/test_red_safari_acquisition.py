from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.collection import (
    CollectionLocation,
    CollectionObservation,
    LivingSpecimen,
)
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.gen1_terrain import Terrain
from pokemon_red_completion.living_dex_option_value import LivingDexOptionContext
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.observation import MapId, RamAddress, RawGameState
from pokemon_red_completion.red_acquisition import RedAreaExecutionError
from pokemon_red_completion.red_collection import red_internal_species_id, red_species_ref
from pokemon_red_completion.red_safari_acquisition import (
    LiveSafariAreaExecutor,
    LiveSafariPatrol,
    RedSafariAdmissionReport,
    RedSafariPatrolPlan,
    RedSafariZoneOffer,
    derive_red_safari_patrol,
    red_safari_admission_route,
    red_safari_area_menu,
    red_safari_zone_offers,
    relocate_red_safari_origin_to_fuchsia_center,
    select_red_safari_area,
)
from pokemon_red_completion.safari import SafariChapterError, SafariTiming, _move, _steps


def _collection(*numbers: int) -> CollectionObservation:
    specimens = tuple(
        LivingSpecimen(
            red_species_ref(number),
            20,
            CollectionLocation.PARTY if index == 0 else CollectionLocation.BOX,
            container_index=0,
            slot_index=index,
        )
        for index, number in enumerate(numbers)
    )
    return CollectionObservation(
        owned_species=frozenset(red_species_ref(number) for number in numbers),
        specimens=specimens,
        party_size=min(1, len(specimens)),
        party_limit=6,
        box_counts=(max(0, len(specimens) - 1),) + (0,) * 11,
        current_box_index=0,
        box_capacity=20,
    )


def test_safari_inventory_derives_productive_areas_from_cartridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pokemon_red_completion.red_safari_acquisition as safari

    monkeypatch.setattr(safari, "internal_to_dex", lambda _rom: {10: 30, 11: 33, 12: 47})
    monkeypatch.setattr(
        safari,
        "wild_tables",
        lambda _rom, **_kwargs: {
            int(MapId.SAFARI_ZONE_CENTER): [(22, 10)] * 5 + [(23, 11)] * 5,
            int(MapId.SAFARI_ZONE_EAST): [(25, 11)] * 9 + [(25, 12)],
            int(MapId.SAFARI_ZONE_NORTH): [(30, 10)] * 10,
            int(MapId.SAFARI_ZONE_WEST): [(31, 11)] * 10,
        },
    )

    offers = red_safari_zone_offers(b"rom", {30, 33})

    assert len(offers) == 1
    assert offers[0].map_id == int(MapId.SAFARI_ZONE_EAST)
    assert offers[0].missing_species_numbers == (47,)
    assert offers[0].productive_slot_count == 1
    assert offers[0].public_dict() == {
        "cartridge_derived": True,
        "feature_values": {
            "admission_cost": 500,
            "encounter_slot_count": 10,
            "missing_species_count": 1,
            "productive_slot_count": 1,
        },
        "private_map_fields": 0,
        "private_species_fields": 0,
        "private_source_fields": 0,
        "raw_teacher_direction_steps": 0,
    }


def test_safari_offer_rejects_identity_and_slot_drift() -> None:
    slots = tuple((22, 30) for _ in range(10))
    with pytest.raises(ValueError, match="source and map"):
        RedSafariZoneOffer("wild:SafariZoneCenter:grass", int(MapId.SAFARI_ZONE_EAST), slots, (30,))
    with pytest.raises(ValueError, match="ten cartridge slots"):
        RedSafariZoneOffer(
            "wild:SafariZoneCenter:grass",
            int(MapId.SAFARI_ZONE_CENTER),
            slots[:-1],
            (30,),
        )


def test_safari_area_selection_uses_identity_free_existing_model_features() -> None:
    center = RedSafariZoneOffer(
        "wild:SafariZoneCenter:grass",
        int(MapId.SAFARI_ZONE_CENTER),
        tuple([(22, 30)] * 6 + [(25, 111)] * 4),
        (30, 111),
    )
    east = RedSafariZoneOffer(
        "wild:SafariZoneEast:grass",
        int(MapId.SAFARI_ZONE_EAST),
        tuple([(25, 47)] * 2 + [(23, 102)] * 8),
        (47,),
    )
    context = LivingDexOptionContext(0.5, 0.5, 0.5, 0.5, 0.2, 0.1, 0.4)
    menu = red_safari_area_menu(
        context,
        (center, east),
        route_steps=(0, 30),
        maximum_route_steps=100,
        available_money=558,
        free_storage_slots=4,
    )

    class Model:
        feature_version = 3
        model_sha256 = "a" * 64

        @staticmethod
        def scores(_menu: object, _utility: object) -> tuple[float, float]:
            return (0.8, 0.2)

    choice = select_red_safari_area(Model(), menu, (center, east), seed=7)  # type: ignore[arg-type]

    assert choice.selected_offer in (center, east)
    assert choice.public_dict()["private_species_fields"] == 0
    assert choice.public_dict()["teacher_labels"] == 0
    assert menu.candidates[0].binding_ref != center.source_id
    assert menu.candidate_vector(0) != menu.candidate_vector(1)


def test_safari_area_menu_rejects_singleton_and_unfunded_choices() -> None:
    offer = RedSafariZoneOffer(
        "wild:SafariZoneCenter:grass",
        int(MapId.SAFARI_ZONE_CENTER),
        tuple((22, 30) for _ in range(10)),
        (30,),
    )
    context = LivingDexOptionContext(0.5, 0.5, 0.5, 0.5, 0.2, 0.1, 0.4)
    with pytest.raises(ValueError, match="distinct candidate areas"):
        red_safari_area_menu(
            context,
            (offer,),
            route_steps=(0,),
            maximum_route_steps=1,
            available_money=558,
            free_storage_slots=4,
        )
    with pytest.raises(ValueError, match="funded admission"):
        red_safari_area_menu(
            context,
            (offer, replace(offer, source_id="wild:SafariZoneNorth:grass", map_id=218)),
            route_steps=(0, 1),
            maximum_route_steps=1,
            available_money=499,
            free_storage_slots=4,
        )


def test_safari_admission_routes_are_area_level_support_not_species_routes() -> None:
    center = RedSafariZoneOffer(
        "wild:SafariZoneCenter:grass",
        int(MapId.SAFARI_ZONE_CENTER),
        tuple((22, 30) for _ in range(10)),
        (30,),
    )
    east = RedSafariZoneOffer(
        "wild:SafariZoneEast:grass",
        int(MapId.SAFARI_ZONE_EAST),
        tuple((25, 47) for _ in range(10)),
        (47,),
    )
    west = RedSafariZoneOffer(
        "wild:SafariZoneWest:grass",
        int(MapId.SAFARI_ZONE_WEST),
        tuple((25, 47) for _ in range(10)),
        (47,),
    )

    assert red_safari_admission_route(center) == ()
    assert len(red_safari_admission_route(east)) == 29
    assert len(red_safari_admission_route(west)) == 179
    with pytest.raises(TypeError, match="one cartridge offer"):
        red_safari_admission_route(object())  # type: ignore[arg-type]


def test_safari_admission_report_requires_exact_fee_counters_and_terminal() -> None:
    report = RedSafariAdmissionReport(
        selected_source_id="wild:SafariZoneEast:grass",
        selected_map_id=int(MapId.SAFARI_ZONE_EAST),
        selected_position=(0, 23),
        route_steps=29,
        encounters_fled=1,
        money_before=558,
        money_after=58,
        safari_steps_remaining=472,
        safari_balls_remaining=30,
        actions_executed=100,
        frames_executed=10_000,
        controller_released=True,
    )

    assert report.passed
    assert report.public_dict()["private_map_fields"] == 0
    assert not replace(report, money_after=59).passed
    assert not replace(report, safari_balls_remaining=29).passed
    assert not replace(report, selected_position=(1, 23)).passed


def test_safari_steps_are_read_as_one_two_byte_counter() -> None:
    class Memory:
        @staticmethod
        def read_u8(address: int) -> int:
            return {
                int(RamAddress.SAFARI_STEPS): 0x01,
                int(RamAddress.SAFARI_STEPS) + 1: 0xD8,
            }.get(address, 0)

    assert _steps(Memory()) == 472  # type: ignore[arg-type]


class _TransportSimulation:
    def __init__(self, *, mutate_party: bool = False) -> None:
        self.frame_count = 0
        self.pressed_buttons: frozenset[str] = frozenset()
        self.mutate_party = mutate_party
        self.city_moves = 0
        party = (99, 64, 120, 118, 28, 128)
        self.raw = RawGameState(
            game_started=True,
            map_id=MapId.ROUTE_11,
            player_x=0,
            player_y=6,
            party_count=len(party),
            battle_state=0,
            party_species_ids=party,
        )

    def read_u8(self, address: int) -> int:
        money = {
            int(RamAddress.PLAYER_MONEY): 0x00,
            int(RamAddress.PLAYER_MONEY) + 1: 0x05,
            int(RamAddress.PLAYER_MONEY) + 2: 0x58,
        }
        if address == int(RamAddress.SAFARI_BALLS):
            return 0
        return money.get(address, 0)

    def execute(self, action: MacroAction) -> None:
        if action.kind is MacroActionKind.WAIT:
            self.frame_count += action.repeat
            return
        if action.kind is not MacroActionKind.MOVE or self.raw.map_id != MapId.FUCHSIA_CITY:
            return
        self.city_moves += 1
        if self.city_moves == 5:
            party = self.raw.party_species_ids
            if self.mutate_party:
                party = (*tuple(party or ())[:-1], 1)
            self.raw = replace(
                self.raw,
                map_id=MapId.FUCHSIA_POKECENTER,
                player_x=3,
                player_y=3,
                party_species_ids=party,
            )
        else:
            self.raw = replace(self.raw, player_y=int(self.raw.player_y or 0) - 1)

    def read(self) -> RawGameState:
        return self.raw

    def read_input_readiness(self) -> SimpleNamespace:
        return SimpleNamespace(ready=True)


class _TransportFieldMoves:
    landing = (19, 28)

    def __init__(self, delegate: CountingExecutor, reader: object, memory: object) -> None:
        del reader, memory
        self.delegate = delegate
        self.simulation = delegate.delegate
        self.fly_receipts: list[object] = []

    def execute(self, action: MacroAction) -> object:
        assert action == MacroAction(MacroActionKind.FIELD_MOVE, "fly:fuchsia_city")
        self.delegate.execute(MacroAction(MacroActionKind.WAIT, repeat=1))
        self.simulation.raw = replace(  # type: ignore[attr-defined]
            self.simulation.raw,  # type: ignore[attr-defined]
            map_id=MapId.FUCHSIA_CITY,
            player_x=self.landing[0],
            player_y=self.landing[1],
        )
        receipt = object()
        self.fly_receipts.append(receipt)
        return receipt


def test_safari_transport_flies_from_current_field_and_preserves_full_party(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pokemon_red_completion.red_safari_acquisition as acquisition

    simulation = _TransportSimulation()
    monkeypatch.setattr(acquisition, "Gen1FieldMovePort", _TransportFieldMoves)

    report = relocate_red_safari_origin_to_fuchsia_center(
        simulation,  # type: ignore[arg-type]
        CountingExecutor(simulation),
        simulation,  # type: ignore[arg-type]
        timing=SafariTiming(wait_frames=1, movement_frames=1),
    )

    assert report.passed
    assert report.initial_map_id == int(MapId.ROUTE_11)
    assert report.landing_position == (19, 28)
    assert report.party_species_before == (99, 64, 120, 118, 28, 128)
    assert report.party_species_after == report.party_species_before
    assert report.public_dict()["private_map_fields"] == 0


def test_safari_transport_rejects_wrong_fly_landing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pokemon_red_completion.red_safari_acquisition as acquisition

    class WrongLanding(_TransportFieldMoves):
        landing = (18, 28)

    simulation = _TransportSimulation()
    monkeypatch.setattr(acquisition, "Gen1FieldMovePort", WrongLanding)

    with pytest.raises(RedAreaExecutionError) as error:
        relocate_red_safari_origin_to_fuchsia_center(
            simulation,  # type: ignore[arg-type]
            CountingExecutor(simulation),
            simulation,  # type: ignore[arg-type]
            timing=SafariTiming(wait_frames=1, movement_frames=1),
        )
    assert error.value.reason_code == "safari_transport_fly_failed"


def test_safari_walk_exact_party_guard_accepts_growth_but_rejects_mutation() -> None:
    simulation = _TransportSimulation(mutate_party=True)
    simulation.raw = replace(
        simulation.raw,
        map_id=MapId.FUCHSIA_CITY,
        player_x=19,
        player_y=28,
    )
    expected = tuple(simulation.raw.party_species_ids or ())

    with pytest.raises(SafariChapterError, match="changed party"):
        _move(
            CountingExecutor(simulation),
            simulation,  # type: ignore[arg-type]
            simulation,  # type: ignore[arg-type]
            ("up",) * 5,
            SafariTiming(wait_frames=1, movement_frames=1),
            "evolved-party walk",
            expected_party_species_ids=expected,
        )


def test_safari_patrol_is_derived_from_reachable_reversible_grass() -> None:
    grid = tuple(tuple(True for _ in range(4)) for _ in range(4))
    grass = tuple(
        tuple((y, x) in {(1, 1), (2, 1)} for x in range(4)) for y in range(4)
    )
    terrain = Terrain(
        int(MapId.SAFARI_ZONE_EAST),
        0,
        grid,
        grass,
        tuple(tuple(False for _ in range(4)) for _ in range(4)),
        tuple(tuple(0 for _ in range(4)) for _ in range(4)),
    )
    graph = LocalGraph(
        {
            (2, 0): (LocalEdge((2, 1), "right"),),
            (2, 1): (LocalEdge((2, 0), "left"), LocalEdge((1, 1), "up")),
            (1, 1): (LocalEdge((2, 1), "down"),),
        }
    )
    offer = RedSafariZoneOffer(
        "wild:SafariZoneEast:grass",
        int(MapId.SAFARI_ZONE_EAST),
        tuple((25, 47) for _ in range(10)),
        (47,),
    )

    plan = derive_red_safari_patrol(offer, terrain, graph, start_at=(2, 0))

    assert plan.approach_directions == ("right",)
    assert plan.first_at == (2, 1)
    assert plan.second_at == (1, 1)
    assert plan.forward_direction == "up"
    assert plan.public_dict()["private_coordinate_fields"] == 0
    assert derive_red_safari_patrol(
        offer,
        terrain,
        graph,
        start_at=(2, 0),
        excluded={(2, 0)},
    ) == plan


class _PatrolSimulation:
    def __init__(self) -> None:
        self.frame_count = 0
        self.pressed_buttons: frozenset[str] = frozenset()
        self.raw = RawGameState(
            True,
            MapId.SAFARI_ZONE_EAST,
            0,
            2,
            3,
            0,
            party_species_ids=(0x1C, 0x40, 0x3B),
        )
        self.encounter_on_move = False

    def read_u8(self, address: int) -> int:
        return 30 if address == int(RamAddress.SAFARI_BALLS) else 0

    def execute(self, action: MacroAction) -> None:
        if action.kind is MacroActionKind.WAIT:
            self.frame_count += action.repeat
        elif action.kind is MacroActionKind.MOVE:
            if self.encounter_on_move:
                self.encounter_on_move = False
                self.raw = replace(self.raw, battle_state=1)
                return
            dx, dy = {
                "up": (0, -1),
                "down": (0, 1),
                "left": (-1, 0),
                "right": (1, 0),
            }[str(action.value)]
            self.raw = replace(
                self.raw,
                player_x=int(self.raw.player_x or 0) + dx,
                player_y=int(self.raw.player_y or 0) + dy,
            )

    def read(self) -> RawGameState:
        return self.raw

    def read_input_readiness(self) -> SimpleNamespace:
        return SimpleNamespace(ready=True)


def test_live_safari_patrol_enters_once_then_oscillates_without_fleeing() -> None:
    simulation = _PatrolSimulation()
    actions = CountingExecutor(simulation)
    plan = RedSafariPatrolPlan(
        "wild:SafariZoneEast:grass",
        int(MapId.SAFARI_ZONE_EAST),
        (2, 0),
        ("right",),
        (2, 1),
        (1, 1),
        2,
        "up",
        "down",
    )
    patrol = LiveSafariPatrol(
        simulation,
        actions,
        simulation,  # type: ignore[arg-type]
        plan,
    )

    with pytest.raises(RedAreaExecutionError) as not_entered:
        patrol.seek_step()
    assert not_entered.value.reason_code == "safari_patrol_not_entered"
    assert patrol.enter() == 0
    patrol.seek_step()
    assert (simulation.raw.player_y, simulation.raw.player_x) == (1, 1)
    patrol.seek_step()
    assert (simulation.raw.player_y, simulation.raw.player_x) == (2, 1)
    with pytest.raises(RedAreaExecutionError) as repeated:
        patrol.enter()
    assert repeated.value.reason_code == "safari_patrol_approach_repeated"


def test_live_safari_patrol_hands_pre_displacement_encounter_to_battle_mechanic() -> None:
    simulation = _PatrolSimulation()
    actions = CountingExecutor(simulation)
    plan = RedSafariPatrolPlan(
        "wild:SafariZoneEast:grass",
        int(MapId.SAFARI_ZONE_EAST),
        (2, 0),
        ("right",),
        (2, 1),
        (1, 1),
        2,
        "up",
        "down",
    )
    patrol = LiveSafariPatrol(
        simulation,
        actions,
        simulation,  # type: ignore[arg-type]
        plan,
    )
    patrol.enter()
    simulation.encounter_on_move = True

    patrol.seek_step()

    assert simulation.raw.battle_state == 1
    assert (simulation.raw.player_y, simulation.raw.player_x) == (2, 1)
    simulation.raw = replace(simulation.raw, battle_state=0)
    patrol.seek_step()
    assert (simulation.raw.player_y, simulation.raw.player_x) == (1, 1)


def test_live_safari_patrol_resumes_from_retained_endpoint_encounter() -> None:
    simulation = _PatrolSimulation()
    simulation.raw = replace(
        simulation.raw,
        player_x=1,
        player_y=2,
        battle_state=1,
    )
    plan = RedSafariPatrolPlan(
        "wild:SafariZoneEast:grass",
        int(MapId.SAFARI_ZONE_EAST),
        (2, 0),
        ("right",),
        (2, 1),
        (1, 1),
        2,
        "up",
        "down",
    )
    patrol = LiveSafariPatrol(
        simulation,
        CountingExecutor(simulation),
        simulation,  # type: ignore[arg-type]
        plan,
    )

    patrol.resume_from_encounter()
    simulation.raw = replace(simulation.raw, battle_state=0)
    patrol.seek_step()

    assert (simulation.raw.player_y, simulation.raw.player_x) == (1, 1)
    with pytest.raises(RedAreaExecutionError) as repeated:
        patrol.resume_from_encounter()
    assert repeated.value.reason_code == "safari_patrol_recovery_repeated"


def test_live_safari_patrol_recovery_rejects_nonendpoint_battle() -> None:
    simulation = _PatrolSimulation()
    simulation.raw = replace(simulation.raw, player_x=3, player_y=3, battle_state=1)
    plan = RedSafariPatrolPlan(
        "wild:SafariZoneEast:grass",
        int(MapId.SAFARI_ZONE_EAST),
        (2, 0),
        ("right",),
        (2, 1),
        (1, 1),
        2,
        "up",
        "down",
    )
    patrol = LiveSafariPatrol(
        simulation,
        CountingExecutor(simulation),
        simulation,  # type: ignore[arg-type]
        plan,
    )

    with pytest.raises(RedAreaExecutionError) as error:
        patrol.resume_from_encounter()
    assert error.value.reason_code == "safari_patrol_recovery_boundary_invalid"


class _SafariSimulation:
    def __init__(self, *, capture_on_throw: bool) -> None:
        self.frame_count = 0
        self.pressed_buttons: frozenset[str] = frozenset()
        self.balls = 3
        self.cursor = 0
        self.capture_on_throw = capture_on_throw
        self.captured = False
        self.raw = RawGameState(
            game_started=True,
            map_id=MapId.SAFARI_ZONE_CENTER,
            player_x=15,
            player_y=25,
            party_count=1,
            battle_state=1,
            bag_items=((4, 12),),
            party_species_ids=(red_internal_species_id(9),),
            party_levels=(50,),
            party_hp=(150,),
            party_max_hp=(150,),
            party_status=(0,),
            party_moves=((55, 44, 57, 70),),
            party_pp=((25, 25, 15, 15),),
            enemy_species_id=red_internal_species_id(30),
            enemy_level=22,
        )
        self.collection = _collection(9)
        self.actions: list[MacroAction] = []

    def read_u8(self, address: int) -> int:
        if address == RamAddress.SAFARI_BALLS:
            return self.balls
        if address == RamAddress.CURRENT_MENU_ITEM:
            return self.cursor
        return 0

    def execute(self, action: MacroAction) -> None:
        self.actions.append(action)
        if action.kind is MacroActionKind.WAIT:
            self.frame_count += action.repeat
        elif action.kind is MacroActionKind.MOVE:
            if action.value == "up":
                self.cursor &= 1
            elif action.value == "left":
                self.cursor &= 2
            elif action.value == "down":
                self.cursor |= 2
            elif action.value == "right":
                self.cursor |= 1
        elif action.kind is MacroActionKind.CONFIRM and self.raw.battle_state:
            if self.cursor == 0:
                self.balls -= 1
                if self.capture_on_throw:
                    self.captured = True
                    self.collection = _collection(9, 30)
                    self.raw = replace(self.raw, battle_state=0, enemy_species_id=None)
            elif self.cursor == 3:
                self.raw = replace(self.raw, battle_state=0, enemy_species_id=None)

    def read(self) -> RawGameState:
        return self.raw

    def read_input_readiness(self) -> SimpleNamespace:
        return SimpleNamespace(ready=self.raw.battle_state == 0)


def _live(simulation: _SafariSimulation, *, maximum_throws: int = 1) -> LiveSafariAreaExecutor:
    return LiveSafariAreaExecutor(
        simulation,
        CountingExecutor(simulation),
        simulation,  # type: ignore[arg-type]
        source_id="wild:SafariZoneCenter:grass",
        map_id=int(MapId.SAFARI_ZONE_CENTER),
        seek_step=lambda: None,
        maximum_throws_per_encounter=maximum_throws,
        collection_reader=lambda: simulation.collection,
    )


def test_live_safari_capture_retains_exact_target_and_spends_one_safari_ball() -> None:
    simulation = _SafariSimulation(capture_on_throw=True)

    assert _live(simulation).capture_encounter(red_species_ref(30))
    assert simulation.balls == 2
    assert simulation.collection == _collection(9, 30)
    assert simulation.raw.bag_items == ((4, 12),)


def test_live_safari_failed_throw_flees_and_returns_false() -> None:
    simulation = _SafariSimulation(capture_on_throw=False)

    assert not _live(simulation).capture_encounter(red_species_ref(30))
    assert simulation.balls == 2
    assert simulation.raw.battle_state == 0
    assert simulation.collection == _collection(9)


def test_live_safari_refuses_wrong_area_and_box_switch() -> None:
    simulation = _SafariSimulation(capture_on_throw=True)
    live = _live(simulation)
    simulation.raw = replace(simulation.raw, map_id=MapId.SAFARI_ZONE_EAST)

    with pytest.raises(RedAreaExecutionError) as mismatch:
        live.encountered_species_ref()
    assert mismatch.value.reason_code == "safari_encounter_boundary_invalid"
    with pytest.raises(RedAreaExecutionError) as storage:
        live.switch_box(1)
    assert storage.value.reason_code == "box_switch_requires_source_exit"
