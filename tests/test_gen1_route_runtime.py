from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import cast

import pytest

from pokemon_red_completion.battle_runtime import BattleRuntimeError
from pokemon_red_completion.gen1_route_runtime import (
    Gen1RouteInterruptionHandler,
    Gen1TraversalObserver,
    Gen1WildFleeHandler,
    strongest_usable_move_slot,
)
from pokemon_red_completion.observation import (
    SAFFRON_GUARD_ACCESS_MASK,
    InputReadiness,
    MapId,
    OverworldMovementMode,
    PokemonRedStateReader,
    RawGameState,
)
from pokemon_red_completion.route_1_wild import Route1WildFleeEvidence
from pokemon_red_completion.route_executor import (
    RouteExecutionError,
    TraversalResource,
    TraversalSnapshot,
)


@dataclass
class FakeReader:
    raw: RawGameState
    ready: bool = True
    occupied: frozenset[tuple[int, int]] = frozenset()
    occupancy_reads: int = 0
    trainer_engagement: bool = False
    retained_outside_map: int = MapId.VIRIDIAN_CITY

    def read(self) -> RawGameState:
        return self.raw

    def read_input_readiness(self) -> InputReadiness:
        return InputReadiness(
            joy_ignore=0 if self.ready else 1,
            simulated_joypad_index=0,
            npc_movement_script_table=0,
            player_moving_direction=0,
            status_flags_5=0,
        )

    def read_overworld_movement_mode(self) -> OverworldMovementMode:
        return OverworldMovementMode.WALKING

    def read_visible_object_coordinates(self) -> frozenset[tuple[int, int]]:
        self.occupancy_reads += 1
        return self.occupied

    def trainer_engagement_active(self) -> bool:
        return self.trainer_engagement

    def read_retained_outside_map(self) -> int:
        return self.retained_outside_map


@dataclass
class FakeExecutor:
    def execute(self, action: object) -> object:
        return action


@dataclass
class FakeHazardProjector:
    calls: int = 0

    def observe_hazards(self, raw: RawGameState) -> tuple[object, ...]:
        self.calls += 1
        raise AssertionError("transient map state must not be projected")


@dataclass
class TrainerIntroExecutor:
    reader: FakeReader
    actions: int = 0

    def execute(self, action: object) -> object:
        self.actions += 1
        self.reader.raw = replace(self.reader.raw, battle_state=2)
        self.reader.trainer_engagement = False
        return action


@dataclass
class TrainerDialogueExecutor:
    reader: FakeReader
    actions: int = 0

    def execute(self, action: object) -> object:
        self.actions += 1
        self.reader.trainer_engagement = False
        return action


def raw(*, battle_state: int = 0) -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=MapId.ROUTE_1,
        player_x=7,
        player_y=8,
        party_count=1,
        battle_state=battle_state,
        bag_items=(),
        repel_remaining_steps=0,
    )


def reader_as_real(fake: FakeReader) -> PokemonRedStateReader:
    return cast(PokemonRedStateReader, fake)


def test_observer_keeps_coordinates_game_neutral_and_marks_wild_battle() -> None:
    fake = FakeReader(raw(battle_state=1), occupied=frozenset({(8, 8)}))

    observed = Gen1TraversalObserver(reader_as_real(fake)).observe()

    assert observed == TraversalSnapshot(
        map_id=MapId.ROUTE_1,
        at=(8, 7),
        ready=False,
        interruption="wild_battle",
        mode="land",
        occupied=frozenset(),
        resources=(TraversalResource("encounter_suppression", 0, 0),),
        last_outside_map=MapId.VIRIDIAN_CITY,
    )
    assert fake.occupancy_reads == 0, "overworld sprite RAM is not decoded during battle"


def test_observer_projects_current_visible_object_occupancy() -> None:
    fake = FakeReader(raw(), occupied=frozenset({(7, 7), (9, 8)}))

    observed = Gen1TraversalObserver(reader_as_real(fake)).observe()

    assert observed.occupied == frozenset({(7, 7), (9, 8)})
    assert fake.occupancy_reads == 1


def test_observer_withholds_map_objects_and_hazards_during_transition() -> None:
    fake = FakeReader(raw(), ready=False, occupied=frozenset({(7, 7)}))
    hazards = FakeHazardProjector()

    observed = Gen1TraversalObserver(
        reader_as_real(fake),
        hazard_projector=cast(object, hazards),  # type: ignore[arg-type]
    ).observe()

    assert not observed.ready
    assert observed.interruption is None
    assert observed.occupied == frozenset()
    assert observed.hazards == ()
    assert fake.occupancy_reads == 0
    assert hazards.calls == 0


def test_observer_projects_live_nested_return_context() -> None:
    fake = FakeReader(raw(), retained_outside_map=MapId.ROUTE_7)

    observed = Gen1TraversalObserver(reader_as_real(fake)).observe()

    assert observed.last_outside_map == MapId.ROUTE_7


def test_observer_projects_only_observed_open_story_capabilities() -> None:
    closed = FakeReader(raw())
    opened = FakeReader(replace(raw(), status_flags_1=SAFFRON_GUARD_ACCESS_MASK))

    assert Gen1TraversalObserver(reader_as_real(closed)).observe().capabilities == frozenset()
    assert Gen1TraversalObserver(reader_as_real(opened)).observe().capabilities == frozenset(
        {"story:saffron_guards_open"}
    )


def test_observer_unions_explicit_title_capability_projection() -> None:
    fake = FakeReader(replace(raw(), status_flags_1=SAFFRON_GUARD_ACCESS_MASK))

    observed = Gen1TraversalObserver(
        reader_as_real(fake),
        capability_projector=lambda _raw: frozenset({"field:cut", "field:surf"}),
    ).observe()

    assert observed.capabilities == frozenset(
        {"field:cut", "field:surf", "story:saffron_guards_open"}
    )


def test_observer_rejects_malformed_title_capability_projection() -> None:
    fake = FakeReader(raw())
    observer = Gen1TraversalObserver(
        reader_as_real(fake),
        capability_projector=lambda _raw: {"move:cut"},  # type: ignore[arg-type,return-value]
    )

    with pytest.raises(RouteExecutionError, match="invalid capability set"):
        observer.observe()


def test_observer_requires_a_started_coordinate_state() -> None:
    fake = FakeReader(
        RawGameState(False, None, None, None, None, None),
    )

    with pytest.raises(RouteExecutionError, match="state is unavailable"):
        Gen1TraversalObserver(reader_as_real(fake)).observe()


def test_nonwild_battles_are_typed_but_not_dismissed() -> None:
    fake = FakeReader(raw(battle_state=2))
    observer = Gen1TraversalObserver(reader_as_real(fake))
    interruption = observer.observe()
    handler = Gen1WildFleeHandler(
        cast(object, FakeExecutor()),  # type: ignore[arg-type]
        reader_as_real(fake),
        maximum_flees=1,
        stabilization_frames=24,
    )

    assert interruption.interruption == "battle:2"
    with pytest.raises(RouteExecutionError, match="cannot dismiss"):
        handler.handle(interruption)


def test_trainer_walkup_is_typed_before_battle_ram_changes() -> None:
    fake = FakeReader(raw(), trainer_engagement=True)

    observed = Gen1TraversalObserver(reader_as_real(fake)).observe()

    assert observed.interruption == "trainer_engagement"
    assert not observed.ready
    assert observed.occupied == frozenset()
    assert fake.occupancy_reads == 0


def test_route_battle_policy_prefers_effective_damaging_move_evidence() -> None:
    state = replace(
        raw(battle_state=2),
        party_species_ids=(179,),
        active_party_index=0,
        active_party_species_id=179,
        active_party_moves=(39, 55, 61, 0),
        active_party_pp=(30, 25, 20, 0),
        enemy_species_id=165,
    )

    assert strongest_usable_move_slot(state) == 3
    assert (
        strongest_usable_move_slot(
            replace(state, player_disabled_move_slot=3, player_disable_turns=2)
        )
        == 2
    )


def test_combined_handler_advances_a_trainer_intro_and_restores_the_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeReader(raw(), trainer_engagement=True)
    executor = TrainerIntroExecutor(fake)

    def finish_battle(*args: object, **kwargs: object) -> RawGameState:
        assert fake.raw.battle_state == 2
        fake.raw = replace(fake.raw, battle_state=0)
        return fake.raw

    monkeypatch.setattr(
        "pokemon_red_completion.gen1_route_runtime.run_adaptive_trainer_battle",
        finish_battle,
    )
    handler = Gen1RouteInterruptionHandler(
        cast(object, executor),  # type: ignore[arg-type]
        reader_as_real(fake),
        maximum_flees=1,
        maximum_trainer_battles=1,
        stabilization_frames=24,
    )

    receipt = handler.handle(TraversalSnapshot(MapId.ROUTE_1, (8, 7), False, "trainer_engagement"))

    assert receipt.kind == "trainer_engagement"
    assert receipt.resumed_at == (8, 7)
    assert receipt.details == {
        "battle_plan_id": "generated-route-map-12-trainer-1",
        "battle_started": True,
        "intro_pulses": 1,
        "recoveries": 0,
        "verified": True,
    }
    assert executor.actions == 1
    assert handler.trainer_evidence == [receipt]
    with pytest.raises(RouteExecutionError, match="trainer budget"):
        handler.handle(TraversalSnapshot(MapId.ROUTE_1, (8, 7), False, "trainer_engagement"))


def test_combined_handler_closes_defeated_trainer_dialogue_without_a_battle() -> None:
    fake = FakeReader(raw(), trainer_engagement=True)
    executor = TrainerDialogueExecutor(fake)
    handler = Gen1RouteInterruptionHandler(
        cast(object, executor),  # type: ignore[arg-type]
        reader_as_real(fake),
        maximum_flees=1,
        maximum_trainer_battles=1,
        stabilization_frames=24,
    )

    receipt = handler.handle(TraversalSnapshot(MapId.ROUTE_1, (8, 7), False, "trainer_engagement"))

    assert receipt.kind == "trainer_engagement"
    assert receipt.details == {
        "battle_started": False,
        "intro_pulses": 1,
        "verified": True,
    }
    assert executor.actions == 1


def test_combined_handler_resumes_after_one_bounded_trainer_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeReader(raw(), trainer_engagement=True)
    executor = TrainerIntroExecutor(fake)
    recoveries: list[str] = []

    def finish_after_recovery(
        _reader: object,
        _executor: object,
        policy: object,
        **_kwargs: object,
    ) -> RawGameState:
        if not recoveries:
            try:
                cast(Callable[[RawGameState], int], policy)(fake.raw)
            except Exception as request:
                raise BattleRuntimeError("recovery requested") from request
        fake.raw = replace(fake.raw, battle_state=0)
        return fake.raw

    monkeypatch.setattr(
        "pokemon_red_completion.gen1_route_runtime.run_adaptive_trainer_battle",
        finish_after_recovery,
    )
    handler = Gen1RouteInterruptionHandler(
        cast(object, executor),  # type: ignore[arg-type]
        reader_as_real(fake),
        maximum_flees=1,
        maximum_trainer_battles=1,
        stabilization_frames=24,
        trainer_recovery_required=lambda _raw: not recoveries,
        trainer_recovery_action=lambda: recoveries.append("potion"),
        maximum_trainer_recoveries=1,
    )

    receipt = handler.handle(
        TraversalSnapshot(MapId.ROUTE_1, (8, 7), False, "trainer_engagement")
    )

    assert recoveries == ["potion"]
    assert receipt.details["recoveries"] == 1


def test_combined_handler_rejects_incomplete_trainer_recovery_configuration() -> None:
    fake = FakeReader(raw())

    with pytest.raises(ValueError, match="configured together"):
        Gen1RouteInterruptionHandler(
            cast(object, FakeExecutor()),  # type: ignore[arg-type]
            reader_as_real(fake),
            maximum_flees=1,
            maximum_trainer_battles=1,
            stabilization_frames=24,
            trainer_recovery_required=lambda _raw: True,
            maximum_trainer_recoveries=1,
        )
    with pytest.raises(ValueError, match="positive recovery budget"):
        Gen1RouteInterruptionHandler(
            cast(object, FakeExecutor()),  # type: ignore[arg-type]
            reader_as_real(fake),
            maximum_flees=1,
            maximum_trainer_battles=1,
            stabilization_frames=24,
            trainer_recovery_required=lambda _raw: True,
            trainer_recovery_action=lambda: None,
        )


def test_combined_handler_stops_at_the_trainer_recovery_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeReader(raw(), trainer_engagement=True)
    executor = TrainerIntroExecutor(fake)
    recoveries: list[str] = []

    def always_request_recovery(
        _reader: object,
        _executor: object,
        policy: object,
        **_kwargs: object,
    ) -> RawGameState:
        try:
            cast(Callable[[RawGameState], int], policy)(fake.raw)
        except Exception as request:
            raise BattleRuntimeError("recovery requested") from request
        raise AssertionError("policy should request recovery")

    monkeypatch.setattr(
        "pokemon_red_completion.gen1_route_runtime.run_adaptive_trainer_battle",
        always_request_recovery,
    )
    handler = Gen1RouteInterruptionHandler(
        cast(object, executor),  # type: ignore[arg-type]
        reader_as_real(fake),
        maximum_flees=1,
        maximum_trainer_battles=1,
        stabilization_frames=24,
        trainer_recovery_required=lambda _raw: True,
        trainer_recovery_action=lambda: recoveries.append("potion"),
        maximum_trainer_recoveries=1,
    )

    with pytest.raises(RouteExecutionError, match="exhausted its trainer recovery budget"):
        handler.handle(TraversalSnapshot(MapId.ROUTE_1, (8, 7), False, "trainer_engagement"))

    assert recoveries == ["potion"]


def test_wild_handler_publishes_the_existing_authenticated_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeReader(raw(battle_state=1))
    evidence = Route1WildFleeEvidence(
        initial_battle_state=1,
        final_battle_state=0,
        battle_result=2,
        expected_map_id=MapId.ROUTE_1,
        map_id=MapId.ROUTE_1,
        player_x=7,
        player_y=8,
        enemy_species_id=16,
        enemy_level=3,
        initial_hp=20,
        final_hp=20,
        maximum_hp_preserved=True,
        party_preserved=True,
        level_preserved=True,
        pp_preserved=True,
        status_preserved=True,
        control_ready=True,
        run_attempts=1,
        stabilization_frames=24,
    )

    def fake_flee(*args: object, **kwargs: object) -> Route1WildFleeEvidence:
        return evidence

    monkeypatch.setattr(
        "pokemon_red_completion.gen1_route_runtime.flee_wild",
        fake_flee,
    )
    handler = Gen1WildFleeHandler(
        cast(object, FakeExecutor()),  # type: ignore[arg-type]
        reader_as_real(fake),
        maximum_flees=1,
        stabilization_frames=24,
    )

    receipt = handler.handle(TraversalSnapshot(MapId.ROUTE_1, (8, 7), False, "wild_battle"))

    assert receipt.kind == "wild_battle"
    assert receipt.resumed_at == (8, 7)
    assert receipt.details["verified"] is True
    assert handler.evidence == [evidence]
    with pytest.raises(RouteExecutionError, match="flee budget"):
        handler.handle(TraversalSnapshot(MapId.ROUTE_1, (8, 7), False, "wild_battle"))


def test_wild_handler_accepts_a_cartridge_map_not_named_by_the_legacy_enum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route_20_map_id = 0x1F
    fake = FakeReader(
        replace(raw(battle_state=1), map_id=route_20_map_id, player_x=53, player_y=15)
    )
    expected_maps: list[int] = []
    evidence = Route1WildFleeEvidence(
        initial_battle_state=1,
        final_battle_state=0,
        battle_result=2,
        expected_map_id=route_20_map_id,
        map_id=route_20_map_id,
        player_x=53,
        player_y=15,
        enemy_species_id=24,
        enemy_level=10,
        initial_hp=43,
        final_hp=43,
        maximum_hp_preserved=True,
        party_preserved=True,
        level_preserved=True,
        pp_preserved=True,
        status_preserved=True,
        control_ready=True,
        run_attempts=1,
        stabilization_frames=24,
    )

    def fake_flee(*args: object, **kwargs: object) -> Route1WildFleeEvidence:
        expected_maps.append(cast(int, kwargs["expected_map_id"]))
        return evidence

    monkeypatch.setattr("pokemon_red_completion.gen1_route_runtime.flee_wild", fake_flee)
    handler = Gen1WildFleeHandler(
        cast(object, FakeExecutor()),  # type: ignore[arg-type]
        reader_as_real(fake),
        maximum_flees=1,
        stabilization_frames=24,
    )

    receipt = handler.handle(
        TraversalSnapshot(route_20_map_id, (15, 53), False, "wild_battle")
    )

    assert expected_maps == [route_20_map_id]
    assert receipt.resumed_map == route_20_map_id
