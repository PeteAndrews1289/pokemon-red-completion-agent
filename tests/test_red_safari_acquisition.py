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
from pokemon_red_completion.gen1_story_routing import (
    SAFARI_ADMISSION_SUPPORTED,
    apply_gen1_safari_admission_requirement,
)
from pokemon_red_completion.gen1_terrain import Terrain
from pokemon_red_completion.gen1_traversal import TraversalRules, surf_local_graph
from pokemon_red_completion.living_dex_option_value import LivingDexOptionContext
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    BattleMenuState,
    EventFlag,
    MapId,
    OverworldMovementMode,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
    RedSafariSessionState,
)
from pokemon_red_completion.red_acquisition import RedAreaExecutionError
from pokemon_red_completion.red_collection import red_internal_species_id, red_species_ref
from pokemon_red_completion.red_safari_acquisition import (
    LiveSafariAreaExecutor,
    LiveSafariPatrol,
    RedSafariAdmissionReport,
    RedSafariGateContinuation,
    RedSafariPatrolPlan,
    RedSafariZoneOffer,
    derive_red_safari_patrol,
    enter_red_safari_area_from_gate,
    prepare_red_safari_gate_origin,
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
    def __init__(self, *, mutate_party: bool = False, safari_balls: int = 0) -> None:
        self.frame_count = 0
        self.pressed_buttons: frozenset[str] = frozenset()
        self.mutate_party = mutate_party
        self.safari_balls = safari_balls
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
            return self.safari_balls
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


def test_safari_transport_preserves_stale_pre_admission_ball_byte(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pokemon_red_completion.red_safari_acquisition as acquisition

    simulation = _TransportSimulation(safari_balls=23)
    monkeypatch.setattr(acquisition, "Gen1FieldMovePort", _TransportFieldMoves)

    report = relocate_red_safari_origin_to_fuchsia_center(
        simulation,  # type: ignore[arg-type]
        CountingExecutor(simulation),
        simulation,  # type: ignore[arg-type]
        timing=SafariTiming(wait_frames=1, movement_frames=1),
    )

    assert report.passed
    assert simulation.safari_balls == 23


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


class _GateSimulation:
    def __init__(
        self,
        *,
        map_id: int = int(MapId.SAFARI_ZONE_GATE),
        player_x: int = 3,
        player_y: int = 4,
        party: tuple[int, ...] = (99, 64, 120, 118, 28, 128),
        battle_state: int = 0,
        money: int = 500,
        safari_balls: int = 0,
        safari_steps: int = 0,
        event_flags: bytes | None = b"\x00" * 320,
        input_ready: bool = True,
        movement_mode: OverworldMovementMode = OverworldMovementMode.WALKING,
        dialogue_visible: bool = False,
        pending_trainer: object = None,
        tamper_admission_fee: int | None = None,
        tamper_ball_grant: int | None = None,
        owned_species: tuple[int, ...] = (99, 64, 120, 118, 28, 128),
        mutate_party_after_confirm: bool = False,
        mutate_pokedex_after_confirm: bool = False,
        gate_script: int = 0,
        player_facing: str = "down",
        dialogue_kind: str | None = None,
    ) -> None:
        self.frame_count = 0
        self.pressed_buttons: frozenset[str] = frozenset()
        self.money = money
        self.safari_balls = safari_balls
        self.safari_steps = safari_steps
        self.input_ready = input_ready
        self.movement_mode = movement_mode
        self.dialogue_visible = dialogue_visible
        self.pending_trainer = pending_trainer
        self.dialogue_confirms = 0
        self.tamper_admission_fee = tamper_admission_fee
        self.tamper_ball_grant = tamper_ball_grant
        self.owned_species = owned_species
        self.mutate_party_after_confirm = mutate_party_after_confirm
        self.mutate_pokedex_after_confirm = mutate_pokedex_after_confirm
        self.gate_script = gate_script
        self.player_facing = player_facing
        self.dialogue_kind = dialogue_kind
        self.lateral_step_done = False
        self.raw = RawGameState(
            game_started=True,
            map_id=map_id,
            player_x=player_x,
            player_y=player_y,
            party_count=len(party),
            battle_state=battle_state,
            party_species_ids=party,
            event_flags=event_flags,
            player_money=money,
        )

    def read_u8(self, address: int) -> int:
        if address == RamAddress.CURRENT_MAP:
            return int(self.raw.map_id)
        if address == RamAddress.TRAINER_TEXT_SPRITE_INDEX:
            if self.dialogue_kind is not None:
                return {"greeting": 3, "admission": 4}.get(self.dialogue_kind, 2)
            return 3 if self.gate_script == 0 else 4
        s = f"{max(0, min(999999, self.money)):06d}"
        bcd = (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
        if address == int(RamAddress.PLAYER_MONEY):
            return bcd[0]
        if address == int(RamAddress.PLAYER_MONEY) + 1:
            return bcd[1]
        if address == int(RamAddress.PLAYER_MONEY) + 2:
            return bcd[2]
        if address == int(RamAddress.SAFARI_BALLS):
            return self.safari_balls
        if address == int(RamAddress.SAFARI_STEPS):
            return (self.safari_steps >> 8) & 0xFF
        if address == int(RamAddress.SAFARI_STEPS) + 1:
            return self.safari_steps & 0xFF
        if address == int(RamAddress.SAFARI_ZONE_GATE_SCRIPT):
            return self.gate_script
        if address == int(RamAddress.PLAYER_FACING_DIRECTION):
            return {"down": 0, "up": 4, "left": 8, "right": 12}.get(self.player_facing, 0)
        return 0

    def execute(self, action: MacroAction) -> None:
        if action.kind is MacroActionKind.WAIT:
            self.frame_count += action.repeat
            return
        if action.kind is MacroActionKind.MOVE:
            delta_y = {"up": -1, "down": 1}.get(str(action.value), 0)
            delta_x = {"left": -1, "right": 1}.get(str(action.value), 0)
            cur_x = int(self.raw.player_x or 0)
            cur_y = int(self.raw.player_y or 0)
            new_x = cur_x + delta_x
            new_y = cur_y + delta_y
            self.raw = replace(
                self.raw,
                player_x=new_x,
                player_y=new_y,
            )
            if self.raw.map_id == MapId.SAFARI_ZONE_CENTER:
                self.safari_steps = max(0, self.safari_steps - 1)
            elif (
                self.raw.map_id == MapId.SAFARI_ZONE_GATE
                and (new_x, new_y) in {(3, 2), (4, 2)}
            ):
                self.dialogue_visible = True
                self.input_ready = False
                self.gate_script = 0
                self.player_facing = str(action.value)
        elif action.kind is MacroActionKind.CONFIRM:
            self.dialogue_confirms += 1
            if (
                self.raw.map_id == MapId.SAFARI_ZONE_GATE
                and (self.raw.player_x, self.raw.player_y) in {(3, 2), (4, 2)}
            ):
                if self.gate_script == 0:
                    self.player_facing = "right"
                    if (self.raw.player_x, self.raw.player_y) == (3, 2):
                        self.lateral_step_done = True
                        self.gate_script = 1
                        self.raw = replace(self.raw, player_x=4, player_y=2)
                    else:
                        self.gate_script = 2
                elif self.gate_script in {1, 2} or (
                    not self.dialogue_visible and self.dialogue_confirms >= 2
                ):
                    fee = (
                        self.tamper_admission_fee
                        if self.tamper_admission_fee is not None
                        else 500
                    )
                    balls = (
                        self.tamper_ball_grant
                        if self.tamper_ball_grant is not None
                        else 30
                    )
                    self.money = max(0, self.money - fee)
                    self.safari_balls = balls
                    self.safari_steps = 500
                    new_party = (
                        (99,)
                        if self.mutate_party_after_confirm
                        else self.raw.party_species_ids
                    )
                    new_count = (
                        1
                        if self.mutate_party_after_confirm
                        else self.raw.party_count
                    )
                    if self.mutate_pokedex_after_confirm:
                        self.owned_species = ()
                    self.gate_script = 3
                    self.raw = replace(
                        self.raw,
                        map_id=MapId.SAFARI_ZONE_CENTER,
                        player_x=15,
                        player_y=25,
                        player_money=self.money,
                        party_species_ids=new_party,
                        party_count=new_count,
                    )
                    self.dialogue_visible = False
                    self.input_ready = True
                    self.gate_script = 0

    def read(self) -> RawGameState:
        return self.raw

    def read_input_readiness(self) -> SimpleNamespace:
        return SimpleNamespace(ready=self.input_ready)

    def read_overworld_movement_mode(self) -> OverworldMovementMode:
        return self.movement_mode

    def read_bottom_dialogue_box_visible(self) -> bool:
        return self.dialogue_visible

    def read_safari_zone_gate_script(self) -> int:
        return self.gate_script

    def read_safari_clerk_dialogue(self) -> str | None:
        return PokemonRedStateReader(self).read_safari_clerk_dialogue()

    def read_player_facing(self) -> str:
        return self.player_facing

    def read_pending_trainer_battle_identity(self) -> object:
        return self.pending_trainer

    def read_safari_session_state(self) -> RedSafariSessionState:
        flag_byte = 0
        byte_idx = int(EventFlag.IN_SAFARI_ZONE) // 8
        if self.raw.event_flags and len(self.raw.event_flags) > byte_idx:
            flag_byte = self.raw.event_flags[byte_idx]
        in_safari = bool(flag_byte & (1 << (int(EventFlag.IN_SAFARI_ZONE) % 8)))
        game_over = bool(flag_byte & (1 << (int(EventFlag.SAFARI_GAME_OVER) % 8)))
        return RedSafariSessionState(
            safari_balls=self.safari_balls,
            safari_steps=self.safari_steps,
            in_safari_zone=in_safari,
            safari_game_over=game_over,
        )

    def read_pokedex_state(self) -> SimpleNamespace:
        return SimpleNamespace(owned_species=self.owned_species)


def _gate_world(*, blocked_coords: frozenset[tuple[int, int]] = frozenset()) -> SimpleNamespace:
    walkable = tuple(tuple(2 <= y <= 5 and x in (3, 4) for x in range(10)) for y in range(10))
    grass = tuple(tuple(False for _ in range(10)) for _ in range(10))
    water = tuple(tuple(False for _ in range(10)) for _ in range(10))
    tiles = tuple(tuple(0 for _ in range(10)) for _ in range(10))
    terrain = Terrain(int(MapId.SAFARI_ZONE_GATE), 0, walkable, grass, water, tiles)
    graph = surf_local_graph(terrain, TraversalRules((), (), (), (), ()))
    return SimpleNamespace(
        terrain={int(MapId.SAFARI_ZONE_GATE): terrain},
        local_graphs=apply_gen1_safari_admission_requirement({int(MapId.SAFARI_ZONE_GATE): graph}),
        object_blockers={int(MapId.SAFARI_ZONE_GATE): blocked_coords},
    )


def test_safari_gate_preparation_positive_reaches_clerk_with_zero_fly_receipts() -> None:
    simulation = _GateSimulation(player_x=3, player_y=4, money=500)
    world = _gate_world()

    report = prepare_red_safari_gate_origin(
        simulation,  # type: ignore[arg-type]
        CountingExecutor(simulation),
        simulation,  # type: ignore[arg-type]
        world,  # type: ignore[arg-type]
        timing=SafariTiming(wait_frames=1, movement_frames=1),
    )

    assert report.passed
    assert report.entry_mode == "gate"
    assert report.verified_fly_receipts == 0
    assert report.initial_map_id == int(MapId.SAFARI_ZONE_GATE)
    assert report.initial_position == (3, 4)
    assert report.final_map_id == int(MapId.SAFARI_ZONE_GATE)
    assert report.final_position == (3, 2)
    assert report.money_before == 500
    assert report.money_after == 500
    assert report.actions_executed == 4
    assert report.controller_released
    assert report.public_dict()["entry_mode"] == "gate"
    assert report.public_dict()["verified_fly_receipts"] == 0


def test_safari_gate_preparation_already_at_stance_executes_zero_actions() -> None:
    simulation = _GateSimulation(player_x=3, player_y=2, money=500)
    world = _gate_world()

    report = prepare_red_safari_gate_origin(
        simulation,  # type: ignore[arg-type]
        CountingExecutor(simulation),
        simulation,  # type: ignore[arg-type]
        world,  # type: ignore[arg-type]
        timing=SafariTiming(wait_frames=1, movement_frames=1),
    )

    assert report.passed
    assert report.actions_executed == 0
    assert report.initial_position == (3, 2)
    assert report.final_position == (3, 2)


def test_safari_gate_preparation_rejects_unready_and_ambiguous_states() -> None:
    world = _gate_world()

    # Battle active
    with pytest.raises(RedAreaExecutionError) as err:
        sim = _GateSimulation(battle_state=1)
        prepare_red_safari_gate_origin(
            sim,  # type: ignore[arg-type]
            CountingExecutor(sim),
            sim,  # type: ignore[arg-type]
            world,  # type: ignore[arg-type]
        )
    assert err.value.reason_code == "safari_gate_origin_unready"

    # Input not ready
    with pytest.raises(RedAreaExecutionError) as err:
        sim = _GateSimulation(input_ready=False)
        prepare_red_safari_gate_origin(
            sim,  # type: ignore[arg-type]
            CountingExecutor(sim),
            sim,  # type: ignore[arg-type]
            world,  # type: ignore[arg-type]
        )
    assert err.value.reason_code == "safari_gate_origin_unready"

    # Dialogue box visible
    with pytest.raises(RedAreaExecutionError) as err:
        sim = _GateSimulation(dialogue_visible=True)
        prepare_red_safari_gate_origin(
            sim,  # type: ignore[arg-type]
            CountingExecutor(sim),
            sim,  # type: ignore[arg-type]
            world,  # type: ignore[arg-type]
        )
    assert err.value.reason_code == "safari_gate_origin_unready"

    # Pending trainer
    with pytest.raises(RedAreaExecutionError) as err:
        sim = _GateSimulation(pending_trainer="trainer_1")
        prepare_red_safari_gate_origin(
            sim,  # type: ignore[arg-type]
            CountingExecutor(sim),
            sim,  # type: ignore[arg-type]
            world,  # type: ignore[arg-type]
        )
    assert err.value.reason_code == "safari_gate_origin_unready"

    # Outside corridor
    with pytest.raises(RedAreaExecutionError) as err:
        sim = _GateSimulation(player_x=1, player_y=1)
        prepare_red_safari_gate_origin(
            sim,  # type: ignore[arg-type]
            CountingExecutor(sim),
            sim,  # type: ignore[arg-type]
            world,  # type: ignore[arg-type]
        )
    assert err.value.reason_code == "safari_gate_corridor_invalid"

    # Event flags None (ambiguous unpaid status)
    with pytest.raises(RedAreaExecutionError) as err:
        sim = _GateSimulation(event_flags=None)
        prepare_red_safari_gate_origin(
            sim,  # type: ignore[arg-type]
            CountingExecutor(sim),
            sim,  # type: ignore[arg-type]
            world,  # type: ignore[arg-type]
        )
    assert err.value.reason_code == "safari_gate_unpaid_status_ambiguous"

    # Active Safari session flag set
    flags_active = bytearray(320)
    byte_idx, bit = divmod(int(EventFlag.IN_SAFARI_ZONE), 8)
    flags_active[byte_idx] |= 1 << bit
    with pytest.raises(RedAreaExecutionError) as err:
        sim = _GateSimulation(event_flags=bytes(flags_active))
        prepare_red_safari_gate_origin(
            sim,  # type: ignore[arg-type]
            CountingExecutor(sim),
            sim,  # type: ignore[arg-type]
            world,  # type: ignore[arg-type]
        )
    assert err.value.reason_code == "safari_gate_already_active"

    # Active Safari game over flag set
    flags_over = bytearray(320)
    byte_idx, bit = divmod(int(EventFlag.SAFARI_GAME_OVER), 8)
    flags_over[byte_idx] |= 1 << bit
    with pytest.raises(RedAreaExecutionError) as err:
        sim = _GateSimulation(event_flags=bytes(flags_over))
        prepare_red_safari_gate_origin(
            sim,  # type: ignore[arg-type]
            CountingExecutor(sim),
            sim,  # type: ignore[arg-type]
            world,  # type: ignore[arg-type]
        )
    assert err.value.reason_code == "safari_gate_game_over_active"

    # A leaving/transition script is not an inactive settled origin, even with clear flags.
    with pytest.raises(RedAreaExecutionError) as err:
        sim = _GateSimulation(safari_balls=5, gate_script=4)
        prepare_red_safari_gate_origin(
            sim,  # type: ignore[arg-type]
            CountingExecutor(sim),
            sim,  # type: ignore[arg-type]
            world,  # type: ignore[arg-type]
        )
    assert err.value.reason_code == "safari_gate_script_unsupported"

    # Blocked approach path (both lanes blocked)
    world_blocked = _gate_world(blocked_coords=frozenset({(3, 3), (3, 4)}))
    with pytest.raises(RedAreaExecutionError) as err:
        sim = _GateSimulation(player_x=3, player_y=4)
        prepare_red_safari_gate_origin(
            sim,  # type: ignore[arg-type]
            CountingExecutor(sim),
            sim,  # type: ignore[arg-type]
            world_blocked,  # type: ignore[arg-type]
        )
    assert err.value.reason_code == "safari_gate_approach_blocked"


def test_safari_gate_admission_positive_pays_500_and_enters_safari_center() -> None:
    simulation = _GateSimulation(player_x=3, player_y=2, money=500)
    offer = RedSafariZoneOffer(
        "wild:SafariZoneCenter:grass",
        int(MapId.SAFARI_ZONE_CENTER),
        tuple((25, 30) for _ in range(10)),
        (30,),
    )

    report = enter_red_safari_area_from_gate(
        simulation,  # type: ignore[arg-type]
        CountingExecutor(simulation),
        simulation,  # type: ignore[arg-type]
        offer,
        timing=SafariTiming(wait_frames=1, movement_frames=1),
    )

    assert report.passed
    assert report.selected_source_id == "wild:SafariZoneCenter:grass"
    assert report.selected_map_id == int(MapId.SAFARI_ZONE_CENTER)
    assert report.selected_position == (15, 25)
    assert report.money_before == 500
    assert report.money_after == 0
    assert report.safari_balls_remaining == 30
    assert report.safari_steps_remaining == 500
    assert report.controller_released


def test_safari_gate_admission_rejects_insufficient_funds_and_wrong_boundary() -> None:
    offer = RedSafariZoneOffer(
        "wild:SafariZoneCenter:grass",
        int(MapId.SAFARI_ZONE_CENTER),
        tuple((25, 30) for _ in range(10)),
        (30,),
    )

    # Insufficient funds (198 < 500)
    simulation = _GateSimulation(player_x=3, player_y=2, money=198)
    with pytest.raises(RedAreaExecutionError) as err:
        enter_red_safari_area_from_gate(
            simulation,  # type: ignore[arg-type]
            CountingExecutor(simulation),
            simulation,  # type: ignore[arg-type]
            offer,
        )
    assert err.value.reason_code == "safari_admission_funds_insufficient"

    # Wrong position (not at clerk stance: e.g. 3, 4)
    simulation = _GateSimulation(player_x=3, player_y=4, money=500)
    with pytest.raises(RedAreaExecutionError) as err:
        enter_red_safari_area_from_gate(
            simulation,  # type: ignore[arg-type]
            CountingExecutor(simulation),
            simulation,  # type: ignore[arg-type]
            offer,
        )
    assert err.value.reason_code == "safari_gate_admission_boundary_invalid"

    # In battle
    simulation = _GateSimulation(player_x=3, player_y=2, money=500, battle_state=1)
    with pytest.raises(RedAreaExecutionError) as err:
        enter_red_safari_area_from_gate(
            simulation,  # type: ignore[arg-type]
            CountingExecutor(simulation),
            simulation,  # type: ignore[arg-type]
            offer,
        )
    assert err.value.reason_code == "safari_admission_origin_unready"

    # Direct entry with unready input, regardless of residual counters (Finding 4).
    simulation_unready = _GateSimulation(
        player_x=3, player_y=2, money=500, input_ready=False, safari_balls=5, safari_steps=10
    )
    with pytest.raises(RedAreaExecutionError) as err:
        enter_red_safari_area_from_gate(
            simulation_unready,  # type: ignore[arg-type]
            CountingExecutor(simulation_unready),
            simulation_unready,  # type: ignore[arg-type]
            offer,
        )
    assert err.value.reason_code == "safari_admission_origin_unready"

    # The semantic session observation must also reject activity independently.
    simulation_active = _GateSimulation(
        player_x=3, player_y=2, money=500, safari_balls=5
    )
    simulation_active.read_safari_session_state = lambda: RedSafariSessionState(5, 0, True, False)
    with pytest.raises(RedAreaExecutionError) as err:
        enter_red_safari_area_from_gate(
            simulation_active,  # type: ignore[arg-type]
            CountingExecutor(simulation_active),
            simulation_active,  # type: ignore[arg-type]
            offer,
        )
    assert err.value.reason_code == "safari_admission_session_state_active"

    # Zero-length center route with mutated party species/count (Finding 5)
    simulation_mut_party = _GateSimulation(
        player_x=3, player_y=2, money=500, mutate_party_after_confirm=True
    )
    with pytest.raises(RedAreaExecutionError) as err:
        enter_red_safari_area_from_gate(
            simulation_mut_party,  # type: ignore[arg-type]
            CountingExecutor(simulation_mut_party),
            simulation_mut_party,  # type: ignore[arg-type]
            offer,
            timing=SafariTiming(wait_frames=1, movement_frames=1),
        )
    assert err.value.reason_code == "safari_admission_party_invalid"

    # Zero-length center route with lost pokedex registrations (Finding 5)
    simulation_mut_dex = _GateSimulation(
        player_x=3, player_y=2, money=500, mutate_pokedex_after_confirm=True
    )
    with pytest.raises(RedAreaExecutionError) as err:
        enter_red_safari_area_from_gate(
            simulation_mut_dex,  # type: ignore[arg-type]
            CountingExecutor(simulation_mut_dex),
            simulation_mut_dex,  # type: ignore[arg-type]
            offer,
            timing=SafariTiming(wait_frames=1, movement_frames=1),
        )
    assert err.value.reason_code == "safari_admission_pokedex_invalid"


def test_safari_gate_admission_rejects_deviated_fee_or_balls() -> None:
    offer = RedSafariZoneOffer(
        "wild:SafariZoneCenter:grass",
        int(MapId.SAFARI_ZONE_CENTER),
        tuple((25, 30) for _ in range(10)),
        (30,),
    )

    # Wrong fee deduction (e.g. only 400 charged)
    simulation = _GateSimulation(player_x=3, player_y=2, money=500, tamper_admission_fee=400)
    with pytest.raises(RedAreaExecutionError) as err:
        enter_red_safari_area_from_gate(
            simulation,  # type: ignore[arg-type]
            CountingExecutor(simulation),
            simulation,  # type: ignore[arg-type]
            offer,
            timing=SafariTiming(wait_frames=1, movement_frames=1),
        )
    assert err.value.reason_code == "safari_admission_resources_changed"

    # Wrong ball grant (e.g. 20 balls granted instead of 30)
    simulation = _GateSimulation(player_x=3, player_y=2, money=500, tamper_ball_grant=20)
    with pytest.raises(RedAreaExecutionError) as err:
        enter_red_safari_area_from_gate(
            simulation,  # type: ignore[arg-type]
            CountingExecutor(simulation),
            simulation,  # type: ignore[arg-type]
            offer,
            timing=SafariTiming(wait_frames=1, movement_frames=1),
        )
    assert err.value.reason_code == "safari_admission_resources_changed"


@pytest.mark.parametrize("balls,steps", [(0, 0), (28, 473), (5, 0), (0, 10)])
def test_real_prep_then_admission_left_lane_with_rightward_auto_walk(balls, steps) -> None:
    simulation = _GateSimulation(
        player_x=3, player_y=4, money=500, safari_balls=balls, safari_steps=steps
    )
    world = _gate_world()
    actions = CountingExecutor(simulation)

    report_prep = prepare_red_safari_gate_origin(
        simulation,  # type: ignore[arg-type]
        actions,
        simulation,  # type: ignore[arg-type]
        world,  # type: ignore[arg-type]
        timing=SafariTiming(wait_frames=1, movement_frames=1),
    )
    assert report_prep.passed
    assert report_prep.final_position == (3, 2)
    assert report_prep.continuation is not None
    assert not report_prep.continuation.consumed
    assert (simulation.safari_balls, simulation.safari_steps) == (balls, steps)
    assert simulation.money == 500

    # On arrival at (3, 2), clerk greeting dialogue is automatically visible in script 0
    assert simulation.dialogue_visible
    assert not simulation.input_ready
    assert simulation.gate_script == 0
    assert simulation.read_player_facing() == "up"  # Greeting precedes the forced turn.

    offer = RedSafariZoneOffer(
        "wild:SafariZoneCenter:grass",
        int(MapId.SAFARI_ZONE_CENTER),
        tuple((25, 30) for _ in range(10)),
        (30,),
    )

    report_adm = enter_red_safari_area_from_gate(
        simulation,  # type: ignore[arg-type]
        actions,
        simulation,  # type: ignore[arg-type]
        offer,
        continuation=report_prep.continuation,
        timing=SafariTiming(wait_frames=1, movement_frames=1),
    )
    assert report_adm.passed
    assert report_adm.selected_map_id == int(MapId.SAFARI_ZONE_CENTER)
    assert report_adm.money_before == 500
    assert report_adm.money_after == 0
    assert report_adm.safari_balls_remaining == 30
    assert report_adm.safari_steps_remaining == 500
    assert report_prep.continuation.consumed
    assert simulation.lateral_step_done


@pytest.mark.parametrize("balls,steps", [(0, 0), (28, 473), (5, 0), (0, 10)])
def test_real_prep_then_admission_right_lane_without_lateral_movement(balls, steps) -> None:
    simulation = _GateSimulation(
        player_x=4, player_y=4, money=500, safari_balls=balls, safari_steps=steps
    )
    world = _gate_world()
    actions = CountingExecutor(simulation)

    report_prep = prepare_red_safari_gate_origin(
        simulation,  # type: ignore[arg-type]
        actions,
        simulation,  # type: ignore[arg-type]
        world,  # type: ignore[arg-type]
        timing=SafariTiming(wait_frames=1, movement_frames=1),
    )
    assert report_prep.passed
    assert report_prep.final_position == (4, 2)
    assert report_prep.continuation is not None
    assert (simulation.safari_balls, simulation.safari_steps) == (balls, steps)
    assert simulation.money == 500

    # On arrival at (4, 2), clerk greeting dialogue is automatically visible in script 0
    assert simulation.dialogue_visible
    assert not simulation.input_ready
    assert simulation.gate_script == 0
    assert simulation.read_player_facing() == "up"  # Greeting precedes the forced turn.

    offer = RedSafariZoneOffer(
        "wild:SafariZoneCenter:grass",
        int(MapId.SAFARI_ZONE_CENTER),
        tuple((25, 30) for _ in range(10)),
        (30,),
    )

    report_adm = enter_red_safari_area_from_gate(
        simulation,  # type: ignore[arg-type]
        actions,
        simulation,  # type: ignore[arg-type]
        offer,
        continuation=report_prep.continuation,
        timing=SafariTiming(wait_frames=1, movement_frames=1),
    )
    assert report_adm.passed
    assert not simulation.lateral_step_done
    assert report_adm.selected_map_id == int(MapId.SAFARI_ZONE_CENTER)
    assert report_adm.money_after == 0
    assert report_adm.safari_balls_remaining == 30


@pytest.mark.parametrize("phase", [1, 2, 3, 4, 5, 6, None, False, "0"])
def test_gate_preparation_rejects_unsettled_or_invalid_script_without_inputs(phase) -> None:
    sim = _GateSimulation(gate_script=phase, safari_balls=28, safari_steps=473)
    actions = CountingExecutor(sim)
    with pytest.raises(RedAreaExecutionError) as err:
        prepare_red_safari_gate_origin(sim, actions, sim, _gate_world())
    assert err.value.reason_code == "safari_gate_script_unsupported"
    assert actions.actions_executed == sim.frame_count == 0


@pytest.mark.parametrize("missing", [True, False])
def test_gate_preparation_rejects_unreadable_script_without_inputs(missing) -> None:
    sim = _GateSimulation(safari_balls=28, safari_steps=473)

    def unreadable():
        raise ValueError("unreadable phase")

    sim.read_safari_zone_gate_script = None if missing else unreadable
    actions = CountingExecutor(sim)
    with pytest.raises(RedAreaExecutionError) as err:
        prepare_red_safari_gate_origin(sim, actions, sim, _gate_world())
    assert err.value.reason_code == "safari_gate_script_unreadable"
    assert actions.actions_executed == sim.frame_count == 0


@pytest.mark.parametrize("counter", ["safari_balls", "safari_steps"])
def test_gate_preparation_rejects_counter_drift_before_payment(counter) -> None:
    class DriftingSimulation(_GateSimulation):
        def execute(self, action):
            super().execute(action)
            if action.kind is MacroActionKind.MOVE:
                setattr(self, counter, getattr(self, counter) - 1)

    sim = DriftingSimulation(player_x=4, player_y=3, safari_balls=28, safari_steps=473)
    actions = CountingExecutor(sim)
    with pytest.raises((RedAreaExecutionError, SafariChapterError)):
        prepare_red_safari_gate_origin(
            sim, actions, sim, _gate_world(), timing=SafariTiming(wait_frames=1, movement_frames=1)
        )
    assert sim.money == 500
    assert sim.dialogue_confirms == 0


def test_correction_a_continuation_cannot_be_reused_to_cause_second_payment() -> None:
    simulation = _GateSimulation(player_x=3, player_y=4, money=500)
    world = _gate_world()
    actions = CountingExecutor(simulation)

    report_prep = prepare_red_safari_gate_origin(
        simulation,  # type: ignore[arg-type]
        actions,
        simulation,  # type: ignore[arg-type]
        world,  # type: ignore[arg-type]
        timing=SafariTiming(wait_frames=1, movement_frames=1),
    )
    continuation = report_prep.continuation
    assert continuation is not None

    offer = RedSafariZoneOffer(
        "wild:SafariZoneCenter:grass",
        int(MapId.SAFARI_ZONE_CENTER),
        tuple((25, 30) for _ in range(10)),
        (30,),
    )

    enter_red_safari_area_from_gate(
        simulation,  # type: ignore[arg-type]
        actions,
        simulation,  # type: ignore[arg-type]
        offer,
        continuation=continuation,
        timing=SafariTiming(wait_frames=1, movement_frames=1),
    )
    assert continuation.consumed

    # Re-using the same continuation must fail closed immediately
    with pytest.raises(RedAreaExecutionError) as err:
        enter_red_safari_area_from_gate(
            simulation,  # type: ignore[arg-type]
            actions,
            simulation,  # type: ignore[arg-type]
            offer,
            continuation=continuation,
            timing=SafariTiming(wait_frames=1, movement_frames=1),
        )
    assert err.value.reason_code == "safari_continuation_consumed"


def test_correction_a_rejects_stale_or_mismatched_continuation() -> None:
    offer = RedSafariZoneOffer(
        "wild:SafariZoneCenter:grass",
        int(MapId.SAFARI_ZONE_CENTER),
        tuple((25, 30) for _ in range(10)),
        (30,),
    )

    # Mismatched position
    simulation_mismatch = _GateSimulation(
        player_x=4, player_y=2, money=500, dialogue_visible=True, input_ready=False, gate_script=1
    )
    mismatched_continuation = RedSafariGateContinuation(
        target_map_id=int(MapId.SAFARI_ZONE_GATE),
        target_position=(3, 2),  # Target stance does not match player_x=4
        actions_at_handoff=0,
        frames_at_handoff=0,
    )
    with pytest.raises(RedAreaExecutionError) as err_mismatch:
        enter_red_safari_area_from_gate(
            simulation_mismatch,  # type: ignore[arg-type]
            CountingExecutor(simulation_mismatch),
            simulation_mismatch,  # type: ignore[arg-type]
            offer,
            continuation=mismatched_continuation,
        )
    assert err_mismatch.value.reason_code == "safari_continuation_mismatched"

    # Stale actions count
    simulation_stale = _GateSimulation(
        player_x=3,
        player_y=2,
        money=500,
        dialogue_visible=True,
        input_ready=False,
        gate_script=0,
        player_facing="right",
    )
    actions = CountingExecutor(simulation_stale)
    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=1))
    stale_continuation = RedSafariGateContinuation(
        target_map_id=int(MapId.SAFARI_ZONE_GATE),
        target_position=(3, 2),
        actions_at_handoff=0,  # 1 action has executed since handoff
        frames_at_handoff=0,
    )
    with pytest.raises(RedAreaExecutionError) as err_stale:
        enter_red_safari_area_from_gate(
            simulation_stale,  # type: ignore[arg-type]
            actions,
            simulation_stale,  # type: ignore[arg-type]
            offer,
            continuation=stale_continuation,
        )
    assert err_stale.value.reason_code == "safari_continuation_stale"

    # Stale frames count (frames elapsed without actions)
    simulation_stale_frames = _GateSimulation(
        player_x=3,
        player_y=2,
        money=500,
        dialogue_visible=True,
        input_ready=False,
        gate_script=0,
        player_facing="right",
    )
    simulation_stale_frames.frame_count += 5
    stale_frames_continuation = RedSafariGateContinuation(
        target_map_id=int(MapId.SAFARI_ZONE_GATE),
        target_position=(3, 2),
        actions_at_handoff=0,
        frames_at_handoff=0,
    )
    with pytest.raises(RedAreaExecutionError) as err_frames:
        enter_red_safari_area_from_gate(
            simulation_stale_frames,  # type: ignore[arg-type]
            CountingExecutor(simulation_stale_frames),
            simulation_stale_frames,  # type: ignore[arg-type]
            offer,
            continuation=stale_frames_continuation,
        )
    assert err_frames.value.reason_code == "safari_continuation_stale"


def test_correction_a_rejects_unrelated_dialogue_or_unsupported_script() -> None:
    offer = RedSafariZoneOffer(
        "wild:SafariZoneCenter:grass",
        int(MapId.SAFARI_ZONE_CENTER),
        tuple((25, 30) for _ in range(10)),
        (30,),
    )

    # 1. Unsupported script state (e.g. script 4: leaving/can't pay)
    simulation_bad_script = _GateSimulation(
        player_x=3,
        player_y=2,
        money=500,
        dialogue_visible=True,
        input_ready=False,
        gate_script=4,
        player_facing="right",
    )
    cont = RedSafariGateContinuation(
        target_map_id=int(MapId.SAFARI_ZONE_GATE),
        target_position=(3, 2),
        actions_at_handoff=0,
        frames_at_handoff=0,
    )
    with pytest.raises(RedAreaExecutionError) as err_script:
        enter_red_safari_area_from_gate(
            simulation_bad_script,  # type: ignore[arg-type]
            CountingExecutor(simulation_bad_script),
            simulation_bad_script,  # type: ignore[arg-type]
            offer,
            continuation=cont,
        )
    assert err_script.value.reason_code == "safari_admission_script_unsupported"
    assert simulation_bad_script.money == 500

    # 2. Missing phase observation (sim.read_safari_zone_gate_script = None)
    simulation_missing_script = _GateSimulation(
        player_x=3,
        player_y=2,
        money=500,
        dialogue_visible=True,
        input_ready=False,
        gate_script=0,
        player_facing="right",
    )
    simulation_missing_script.read_safari_zone_gate_script = None  # type: ignore[assignment]
    cont2 = RedSafariGateContinuation(
        target_map_id=int(MapId.SAFARI_ZONE_GATE),
        target_position=(3, 2),
        actions_at_handoff=0,
        frames_at_handoff=0,
    )
    with pytest.raises(RedAreaExecutionError) as err_missing:
        enter_red_safari_area_from_gate(
            simulation_missing_script,  # type: ignore[arg-type]
            CountingExecutor(simulation_missing_script),
            simulation_missing_script,  # type: ignore[arg-type]
            offer,
            continuation=cont2,
        )
    assert err_missing.value.reason_code == "safari_admission_script_unreadable"
    assert simulation_missing_script.money == 500

    # 3. Raising phase observation (read_safari_zone_gate_script raises)
    simulation_raising_script = _GateSimulation(
        player_x=3,
        player_y=2,
        money=500,
        dialogue_visible=True,
        input_ready=False,
        gate_script=0,
        player_facing="right",
    )
    def _raising_script() -> int:
        raise RuntimeError("bus error reading script")
    simulation_raising_script.read_safari_zone_gate_script = _raising_script  # type: ignore[assignment]
    cont3 = RedSafariGateContinuation(
        target_map_id=int(MapId.SAFARI_ZONE_GATE),
        target_position=(3, 2),
        actions_at_handoff=0,
        frames_at_handoff=0,
    )
    with pytest.raises(RedAreaExecutionError) as err_raising:
        enter_red_safari_area_from_gate(
            simulation_raising_script,  # type: ignore[arg-type]
            CountingExecutor(simulation_raising_script),
            simulation_raising_script,  # type: ignore[arg-type]
            offer,
            continuation=cont3,
        )
    assert err_raising.value.reason_code == "safari_admission_script_unreadable"
    assert simulation_raising_script.money == 500

    # 4. Facing does not authenticate text: reject a different dialogue identity.
    simulation_unrelated_facing = _GateSimulation(
        player_x=3,
        player_y=2,
        money=500,
        dialogue_visible=True,
        input_ready=False,
        gate_script=0,
        player_facing="up",
        dialogue_kind="unrelated",
    )
    cont4 = RedSafariGateContinuation(
        target_map_id=int(MapId.SAFARI_ZONE_GATE),
        target_position=(3, 2),
        actions_at_handoff=0,
        frames_at_handoff=0,
    )
    with pytest.raises(RedAreaExecutionError) as err_unrelated:
        enter_red_safari_area_from_gate(
            simulation_unrelated_facing,  # type: ignore[arg-type]
            CountingExecutor(simulation_unrelated_facing),
            simulation_unrelated_facing,  # type: ignore[arg-type]
            offer,
            continuation=cont4,
        )
    assert err_unrelated.value.reason_code == "safari_admission_dialogue_unrelated"
    assert simulation_unrelated_facing.money == 500


def test_correction_a_direct_admission_without_continuation_rejects_unready() -> None:
    offer = RedSafariZoneOffer(
        "wild:SafariZoneCenter:grass",
        int(MapId.SAFARI_ZONE_CENTER),
        tuple((25, 30) for _ in range(10)),
        (30,),
    )

    # Direct call without continuation when dialogue is visible
    simulation_dialogue = _GateSimulation(
        player_x=3, player_y=2, money=500, dialogue_visible=True, input_ready=True
    )
    with pytest.raises(RedAreaExecutionError) as err_diag:
        enter_red_safari_area_from_gate(
            simulation_dialogue,  # type: ignore[arg-type]
            CountingExecutor(simulation_dialogue),
            simulation_dialogue,  # type: ignore[arg-type]
            offer,
            continuation=None,
        )
    assert err_diag.value.reason_code == "safari_admission_origin_unready"

    # Direct call without continuation when input is not ready
    simulation_unready = _GateSimulation(
        player_x=3, player_y=2, money=500, dialogue_visible=False, input_ready=False
    )
    with pytest.raises(RedAreaExecutionError) as err_unready:
        enter_red_safari_area_from_gate(
            simulation_unready,  # type: ignore[arg-type]
            CountingExecutor(simulation_unready),
            simulation_unready,  # type: ignore[arg-type]
            offer,
            continuation=None,
        )
    assert err_unready.value.reason_code == "safari_admission_origin_unready"


def test_correction_a_real_prep_handoff_rejects_stale_frames_or_missing_phase() -> None:
    world = _gate_world()
    offer = RedSafariZoneOffer(
        "wild:SafariZoneCenter:grass",
        int(MapId.SAFARI_ZONE_CENTER),
        tuple((25, 30) for _ in range(10)),
        (30,),
    )

    # 1. Real prep followed by intervening frames fails closed
    sim_frames = _GateSimulation(player_x=3, player_y=4, money=500)
    actions_frames = CountingExecutor(sim_frames)
    prep_frames = prepare_red_safari_gate_origin(
        sim_frames,
        actions_frames,
        sim_frames,
        world,
        timing=SafariTiming(wait_frames=1, movement_frames=1),
    )
    assert prep_frames.passed
    sim_frames.frame_count += 1  # Intervening frame
    with pytest.raises(RedAreaExecutionError) as err_f:
        enter_red_safari_area_from_gate(
            sim_frames, actions_frames, sim_frames, offer, continuation=prep_frames.continuation
        )
    assert err_f.value.reason_code == "safari_continuation_stale"
    assert sim_frames.money == 500

    # 2. Real prep followed by missing gate script reader method fails closed
    sim_missing = _GateSimulation(player_x=3, player_y=4, money=500)
    actions_missing = CountingExecutor(sim_missing)
    prep_missing = prepare_red_safari_gate_origin(
        sim_missing,
        actions_missing,
        sim_missing,
        world,
        timing=SafariTiming(wait_frames=1, movement_frames=1),
    )
    assert prep_missing.passed
    sim_missing.read_safari_zone_gate_script = None  # type: ignore[assignment]
    with pytest.raises(RedAreaExecutionError) as err_m:
        enter_red_safari_area_from_gate(
            sim_missing, actions_missing, sim_missing, offer, continuation=prep_missing.continuation
        )
    assert err_m.value.reason_code == "safari_admission_script_unreadable"
    assert sim_missing.money == 500

    # 3. Real prep followed by a different text identity fails closed.
    sim_facing = _GateSimulation(player_x=3, player_y=4, money=500)
    actions_facing = CountingExecutor(sim_facing)
    prep_facing = prepare_red_safari_gate_origin(
        sim_facing,
        actions_facing,
        sim_facing,
        world,
        timing=SafariTiming(wait_frames=1, movement_frames=1),
    )
    assert prep_facing.passed
    sim_facing.dialogue_kind = "unrelated"
    with pytest.raises(RedAreaExecutionError) as err_face:
        enter_red_safari_area_from_gate(
            sim_facing, actions_facing, sim_facing, offer, continuation=prep_facing.continuation
        )
    assert err_face.value.reason_code == "safari_admission_dialogue_unrelated"
    assert sim_facing.money == 500



@pytest.mark.parametrize("fault", ["missing", "raises", "unknown", "wrong_phase"])
def test_gate_handoff_rejects_missing_or_wrong_observed_text(fault) -> None:
    sim = _GateSimulation(player_x=3, player_y=4, money=500)
    actions = CountingExecutor(sim)
    prep = prepare_red_safari_gate_origin(
        sim, actions, sim, _gate_world(),
        timing=SafariTiming(wait_frames=1, movement_frames=1),
    )
    assert sim.player_facing == "up" and sim.gate_script == 0
    before = actions.actions_executed, sim.frame_count, sim.money
    if fault == "missing":
        sim.read_safari_clerk_dialogue = None
    elif fault == "raises":
        def unreadable():
            raise RuntimeError("unreadable retained text identity")
        sim.read_safari_clerk_dialogue = unreadable
    else:
        sim.dialogue_kind = "unrelated" if fault == "unknown" else "admission"
    offer = RedSafariZoneOffer(
        "wild:SafariZoneCenter:grass", int(MapId.SAFARI_ZONE_CENTER),
        tuple((25, 30) for _ in range(10)), (30,),
    )
    with pytest.raises(RedAreaExecutionError) as error:
        enter_red_safari_area_from_gate(sim, actions, sim, offer, continuation=prep.continuation)
    assert error.value.reason_code == "safari_admission_dialogue_unrelated"
    assert (actions.actions_executed, sim.frame_count, sim.money) == before


@pytest.mark.parametrize(
    "edge",
    [LocalEdge((2, 3), "up", kind="ledge"),
     LocalEdge((2, 3), "up", action_kind=MacroActionKind.CONFIRM),
     LocalEdge((2, 3), "up", required_mode="land", result_mode="water")],
)
def test_gate_plan_never_flattens_nonwalking_actions(edge) -> None:
    from pokemon_red_completion.red_safari_acquisition import plan_red_safari_gate_approach

    assert plan_red_safari_gate_approach(
        LocalGraph({(3, 3): (edge,)}), (3, 3), (2, 3), frozenset(),
    ) is None


@pytest.mark.parametrize("lane", [3, 4])
def test_only_metered_gate_planner_can_cross_admission_requirement(lane) -> None:
    from pokemon_red_completion.local_router import LocalRouterError, find_local_path
    from pokemon_red_completion.red_safari_acquisition import plan_red_safari_clerk_approach

    start, goal = (3, lane), (2, lane)
    graph = apply_gen1_safari_admission_requirement({
        int(MapId.SAFARI_ZONE_GATE): LocalGraph({
            (3, x): (LocalEdge((2, x), "up"),) for x in (3, 4)
        }),
    })[int(MapId.SAFARI_ZONE_GATE)]
    assert graph.edges[start][0].requirements == frozenset({SAFARI_ADMISSION_SUPPORTED})
    with pytest.raises(LocalRouterError):
        find_local_path(graph, start, goal, start_mode="land")
    assert plan_red_safari_clerk_approach(graph, start, frozenset()) is not None
    # Other requirements remain barriers; the paid-service planner is not a general bypass.
    guarded = LocalGraph({start: (
        replace(graph.edges[start][0], requirements=frozenset({
            SAFARI_ADMISSION_SUPPORTED, "unobserved:other_requirement",
        })),
    )})
    assert plan_red_safari_clerk_approach(guarded, start, frozenset()) is None


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


def test_live_safari_patrol_resumes_from_retained_overworld_endpoint() -> None:
    simulation = _PatrolSimulation()
    simulation.raw = replace(simulation.raw, player_x=1, player_y=1, battle_state=0)
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

    patrol.resume_from_endpoint()
    patrol.seek_step()

    assert (simulation.raw.player_y, simulation.raw.player_x) == (2, 1)


class _SafariSimulation:
    def __init__(
        self,
        *,
        capture_on_throw: bool,
        menu_ready: bool = True,
        flee_on_throw: bool = False,
    ) -> None:
        self.frame_count = 0
        self.pressed_buttons: frozenset[str] = frozenset()
        self.balls = 3
        self.cursor = 0
        self.capture_on_throw = capture_on_throw
        self.menu_ready = menu_ready
        self.flee_on_throw = flee_on_throw
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
                self.cursor &= 2
            elif action.value == "left":
                self.cursor &= 1
            elif action.value == "down":
                self.cursor |= 1
            elif action.value == "right":
                self.cursor |= 2
        elif action.kind is MacroActionKind.CONFIRM and self.raw.battle_state:
            if self.cursor == 0:
                self.balls -= 1
                if self.capture_on_throw:
                    self.captured = True
                    self.collection = _collection(9, 30)
                    self.raw = replace(self.raw, battle_state=0, enemy_species_id=None)
                elif self.flee_on_throw:
                    self.raw = replace(self.raw, battle_state=0, enemy_species_id=None)
            elif self.cursor == 3:
                self.raw = replace(self.raw, battle_state=0, enemy_species_id=None)
        elif action.kind is MacroActionKind.CANCEL and self.raw.battle_state:
            self.menu_ready = True

    def read(self) -> RawGameState:
        return self.raw

    def read_input_readiness(self) -> SimpleNamespace:
        return SimpleNamespace(ready=self.raw.battle_state == 0)

    def read_battle_menu_state(self, raw: RawGameState) -> BattleMenuState:
        if not raw.battle_state or not self.menu_ready:
            return BattleMenuState(BattleMenuPhase.UNKNOWN)
        return BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=self.cursor)


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


def test_live_safari_capture_waits_for_observed_command_menu() -> None:
    simulation = _SafariSimulation(capture_on_throw=True, menu_ready=False)

    assert _live(simulation).capture_encounter(red_species_ref(30))
    assert simulation.balls == 2
    assert simulation.menu_ready


@pytest.mark.parametrize("initial_command", [1, 2, 3])
def test_live_safari_capture_observes_each_menu_move(initial_command: int) -> None:
    simulation = _SafariSimulation(capture_on_throw=True)
    simulation.cursor = initial_command

    assert _live(simulation).capture_encounter(red_species_ref(30))
    assert simulation.balls == 2


def test_live_safari_failed_throw_flees_and_returns_false() -> None:
    simulation = _SafariSimulation(capture_on_throw=False)

    assert not _live(simulation).capture_encounter(red_species_ref(30))
    assert simulation.balls == 2
    assert simulation.raw.battle_state == 0
    assert simulation.collection == _collection(9)


def test_live_safari_natural_flee_after_throw_is_a_settled_failed_capture() -> None:
    simulation = _SafariSimulation(capture_on_throw=False, flee_on_throw=True)

    assert not _live(simulation, maximum_throws=8).capture_encounter(red_species_ref(30))
    assert simulation.balls == 2
    assert simulation.raw.battle_state == 0


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
