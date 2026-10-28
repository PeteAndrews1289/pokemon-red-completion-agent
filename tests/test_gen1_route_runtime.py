from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import cast

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
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
    dialogue_visible: bool = False
    retained_outside_map: int = MapId.VIRIDIAN_CITY
    moving_direction: int = 0

    def read(self) -> RawGameState:
        return self.raw

    def read_input_readiness(self) -> InputReadiness:
        return InputReadiness(
            joy_ignore=0 if self.ready else 1,
            simulated_joypad_index=0,
            npc_movement_script_table=0,
            player_moving_direction=self.moving_direction,
            status_flags_5=0,
        )

    def read_overworld_movement_mode(self) -> OverworldMovementMode:
        return OverworldMovementMode.WALKING

    def read_visible_object_coordinates(self) -> frozenset[tuple[int, int]]:
        self.occupancy_reads += 1
        return self.occupied

    def trainer_engagement_active(self) -> bool:
        return self.trainer_engagement

    def read_bottom_dialogue_box_visible(self) -> bool:
        return self.dialogue_visible

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


@dataclass
class ScriptedDialogueExecutor:
    reader: FakeReader
    cancel_pulses: int = 0
    actions: int = 0

    def execute(self, action: object) -> object:
        self.actions += 1
        if isinstance(action, MacroAction) and action.kind == MacroActionKind.CANCEL:
            self.cancel_pulses += 1
            if self.cancel_pulses == 1:
                self.reader.raw = replace(self.reader.raw, player_y=3)
            elif self.cancel_pulses == 3:
                self.reader.raw = replace(self.reader.raw, player_x=8)
                self.reader.dialogue_visible = False
                self.reader.ready = True
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


@pytest.mark.parametrize("fault", [None, "no_poison", "no_faint", "all_fainted", "script",
                                   "cash", "relocation", "disabled", "joy_ignore"])
def test_only_new_native_poison_faint_dialogue_can_resume_the_owned_route(fault):
    initial = replace(raw(), party_species_ids=(28, 150), party_hp=(100, 1),
                      party_status=(0, 0 if fault == "no_poison" else 8))
    # Native poison-faint text interrupts an in-progress walk, but does not
    # authorize dismissal while the game suppresses controller input.
    fake = FakeReader(initial, ready=fault != "joy_ignore", dialogue_visible=True,
                      moving_direction=4)
    fake.read_all_box_states = lambda: ()
    fake.read_pokedex_state = lambda: ()
    actions = []

    class Port:
        def execute(self, action):
            actions.append(action)
            if action.kind is MacroActionKind.CANCEL:
                fake.ready, fake.dialogue_visible = True, False
                fake.moving_direction = 0
                if fault == "cash":
                    fake.raw = replace(fake.raw, player_money=999)
                if fault == "relocation":
                    fake.raw = replace(fake.raw, player_y=9)
            return action

    handler = Gen1WildFleeHandler(Port(), reader_as_real(fake), maximum_flees=2,
        stabilization_frames=24, allow_party_faints=True,
        allow_field_faint_dialogue=fault != "disabled")
    fake.raw = replace(initial, party_hp=(0 if fault == "all_fainted" else 100,
                                        1 if fault == "no_faint" else 0))
    fake.trainer_engagement = fault == "script"
    interruption = TraversalSnapshot(MapId.ROUTE_1, (8, 7), False, "scripted_dialogue")
    if fault is None:
        receipt = handler.handle(interruption)
        assert receipt.details["new_fainted_slots"] == [2]
        assert receipt.details["model_queries"] == 0 and not receipt.allows_relocation
        assert handler.field_faint_evidence == [receipt] and not handler.evidence
        assert [a.kind for a in actions] == [MacroActionKind.CANCEL, MacroActionKind.WAIT]
        with pytest.raises(RouteExecutionError):
            handler.handle(interruption)
    else:
        with pytest.raises(RouteExecutionError):
            handler.handle(interruption)
        if fault not in {"cash", "relocation"}:
            assert not actions


@pytest.mark.parametrize("fault", [None, "same_tile", "undeclared_warp", "wrong_landing",
    "earlier_member", "unpoisoned", "two_damage", "extra_faint", "healing", "cash",
    "bag", "pp", "status", "max_hp", "stats", "species", "boxes", "dex"])
def test_field_faint_only_finishes_declared_warp_and_pending_later_poison_tick(fault):
    initial = replace(raw(), map_id=6, player_y=13, player_x=10, party_count=3,
        party_species_ids=(28, 166, 151), party_hp=(5, 1, 3), party_status=(8, 8, 8),
        party_max_hp=(5, 20, 30), party_stats=((1, 2, 3, 4),) * 3,
        party_pp=((5,),) * 3, player_money=100)
    fake = FakeReader(initial, dialogue_visible=True, moving_direction=8)
    box, dex = [()], [()]
    fake.read_all_box_states = lambda: box[0]
    fake.read_pokedex_state = lambda: dex[0]
    actions = []

    class Port:
        def execute(self, action):
            actions.append(action)
            if action.kind is MacroActionKind.CANCEL:
                fake.ready, fake.dialogue_visible, fake.moving_direction = True, False, 0
                changes = dict(party_hp=(5, 0, 2), map_id=122, player_y=7, player_x=16)
                if fault == "same_tile":
                    changes.update(map_id=6, player_y=13, player_x=10)
                elif fault == "wrong_landing":
                    changes["player_x"] = 15
                elif fault == "earlier_member":
                    changes["party_hp"] = (4, 0, 3)
                elif fault == "two_damage":
                    changes["party_hp"] = (5, 0, 1)
                elif fault == "extra_faint":
                    changes["party_hp"] = (5, 0, 0)
                elif fault == "healing":
                    changes["party_hp"] = (5, 0, 4)
                elif fault == "cash":
                    changes["player_money"] = 101
                elif fault == "bag":
                    changes["bag_items"] = ((4, 1),)
                elif fault == "pp":
                    changes["party_pp"] = ((5,), (5,), (4,))
                elif fault == "status":
                    changes["party_status"] = (8, 0, 0)
                elif fault == "max_hp":
                    changes["party_max_hp"] = (5, 20, 31)
                elif fault == "stats":
                    changes["party_stats"] = ((1, 2, 3, 5),) * 3
                elif fault == "species":
                    changes["party_species_ids"] = (28, 166, 150)
                elif fault == "boxes":
                    box[0] = ("changed",)
                elif fault == "dex":
                    dex[0] = ("changed",)
                fake.raw = replace(fake.raw, **changes)
            return action

    handler = Gen1WildFleeHandler(Port(), reader_as_real(fake), 0, 24,
        allow_party_faints=True, allow_field_faint_dialogue=True,
        field_faint_warps=() if fault == "undeclared_warp" else ((6, (13, 10), 122, (7, 16)),))
    fake.raw = replace(initial, party_hp=(5, 0, 3),
                       party_status=(8, 0, 0 if fault == "unpoisoned" else 8))
    snapshot = TraversalSnapshot(6, (13, 10), False, "scripted_dialogue")
    if fault in (None, "same_tile"):
        receipt = handler.handle(snapshot)
        assert receipt.details["pending_native_poison_tick_slots"] == [3]
        assert receipt.details["new_fainted_slots"] == [2]
        assert receipt.allows_map_transition is (fault is None)
        assert receipt.allows_relocation is (fault is None)
        if fault is None:
            assert receipt.details["source_map"] == 6
            assert receipt.resumed_map == 122 and receipt.resumed_at == (7, 16)
    else:
        with pytest.raises(RouteExecutionError, match="protected resources"):
            handler.handle(snapshot)
        assert not handler.field_faint_evidence
    assert [a.kind for a in actions] == [MacroActionKind.CANCEL, MacroActionKind.WAIT]


@pytest.mark.parametrize("warps", [[], ((6, (13, 10), 6, (7, 16)),),
    ((True, (13, 10), 122, (7, 16)),), ((6, (13,), 122, (7, 16)),),
    ((6, (13, 10), 122, (-1, 16)),)])
def test_field_faint_warp_declarations_fail_closed_without_inputs(warps):
    with pytest.raises(ValueError, match="native endpoints"):
        Gen1WildFleeHandler(FakeExecutor(), reader_as_real(FakeReader(raw())), 0, 24,
            allow_party_faints=True, allow_field_faint_dialogue=True, field_faint_warps=warps)


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


@pytest.mark.parametrize("ready", [False, True])
def test_observer_types_visible_scripted_dialogue_during_a_route(ready) -> None:
    # Text may accept confirm/cancel while it still owns overworld movement.
    fake = FakeReader(raw(), ready=ready, dialogue_visible=True)

    observed = Gen1TraversalObserver(reader_as_real(fake)).observe()

    assert observed.interruption == "scripted_dialogue"
    assert not observed.ready
    assert observed.occupied == frozenset()


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


def test_route_battle_policy_prefers_a_credible_accurate_finisher() -> None:
    state = replace(
        raw(battle_state=2),
        party_species_ids=(179,),
        active_party_index=0,
        active_party_species_id=179,
        active_party_moves=(33, 39, 145, 0),
        active_party_pp=(18, 30, 29, 0),
        enemy_species_id=124,
        enemy_hp=9,
        enemy_max_hp=29,
    )

    assert strongest_usable_move_slot(state) == 3
    assert strongest_usable_move_slot(replace(state, enemy_hp=10)) == 1
    assert (
        strongest_usable_move_slot(
            replace(state, player_disabled_move_slot=3, player_disable_turns=2)
        )
        == 1
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


def test_combined_handler_boundedly_dismisses_a_scripted_route_dialogue() -> None:
    fake = FakeReader(raw(), ready=False, dialogue_visible=True)
    executor = ScriptedDialogueExecutor(fake)
    handler = Gen1RouteInterruptionHandler(
        cast(object, executor),  # type: ignore[arg-type]
        reader_as_real(fake),
        maximum_flees=1,
        maximum_trainer_battles=0,
        stabilization_frames=120,
        maximum_scripted_dialogues=1,
        max_scripted_dialogue_pulses=4,
    )

    receipt = handler.handle(TraversalSnapshot(MapId.ROUTE_1, (8, 7), False, "scripted_dialogue"))

    assert receipt.kind == "scripted_dialogue"
    assert receipt.allows_relocation
    assert receipt.resumed_at == (3, 8)
    assert receipt.details == {
        "cancel_pulses": 3,
        "position_changed": True,
        "verified": True,
    }
    assert executor.actions == 6
    assert handler.scripted_dialogue_evidence == [receipt]
    with pytest.raises(RouteExecutionError, match="dialogue budget"):
        handler.handle(TraversalSnapshot(MapId.ROUTE_1, (3, 8), False, "scripted_dialogue"))


def test_completed_trainer_reports_an_already_pending_native_intro(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeReader(raw(battle_state=2), trainer_engagement=True)

    def finish_battle(*_args: object, **_kwargs: object) -> RawGameState:
        fake.raw = replace(fake.raw, battle_state=0)
        return fake.raw

    monkeypatch.setattr(
        "pokemon_red_completion.gen1_route_runtime.run_adaptive_trainer_battle",
        finish_battle,
    )
    handler = Gen1RouteInterruptionHandler(
        cast(object, FakeExecutor()),
        reader_as_real(fake),  # type: ignore[arg-type]
        maximum_flees=0,
        maximum_trainer_battles=2,
        stabilization_frames=24,
    )
    receipt = handler.handle(TraversalSnapshot(MapId.ROUTE_1, (8, 7), False, "battle:2"))
    assert receipt.details["verified"] is True
    assert receipt.details["pending_interruption_kind"] == "trainer_engagement"
    assert (
        Gen1TraversalObserver(reader_as_real(fake)).observe().interruption == "trainer_engagement"
    )


def test_combined_handler_declares_only_configured_interruption_capabilities() -> None:
    fake = FakeReader(raw())
    handler = Gen1RouteInterruptionHandler(
        cast(object, FakeExecutor()),  # type: ignore[arg-type]
        reader_as_real(fake),
        maximum_flees=1,
        maximum_trainer_battles=0,
        stabilization_frames=24,
        maximum_scripted_dialogues=2,
    )

    assert handler.handled_interruption_kinds == frozenset({
        "wild_battle", "scripted_dialogue", "native_ship_departure",
    })


def test_combined_handler_rejects_a_disappeared_but_unready_dialogue() -> None:
    fake = FakeReader(raw(), ready=False, dialogue_visible=True)

    @dataclass
    class DisappearingExecutor:
        def execute(self, action: object) -> object:
            if isinstance(action, MacroAction) and action.kind == MacroActionKind.CANCEL:
                fake.dialogue_visible = False
            return action

    handler = Gen1RouteInterruptionHandler(
        cast(object, DisappearingExecutor()),  # type: ignore[arg-type]
        reader_as_real(fake),
        maximum_flees=1,
        maximum_trainer_battles=0,
        stabilization_frames=120,
        maximum_scripted_dialogues=1,
    )

    with pytest.raises(RouteExecutionError, match="without restoring input readiness"):
        handler.handle(TraversalSnapshot(MapId.ROUTE_1, (8, 7), False, "scripted_dialogue"))


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

    receipt = handler.handle(TraversalSnapshot(MapId.ROUTE_1, (8, 7), False, "trainer_engagement"))

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


@pytest.mark.parametrize("fault", [None, "no_successor", "battle", "map", "tile", "unverified"])
def test_wild_escape_reports_only_a_verified_observed_trainer_successor(monkeypatch, fault):
    from pokemon_red_completion.route_executor import _pending_verified_interruption

    fake = FakeReader(raw(battle_state=1))
    evidence = Route1WildFleeEvidence(
        initial_battle_state=1, final_battle_state=0, battle_result=2,
        expected_map_id=MapId.ROUTE_1, map_id=MapId.ROUTE_1, player_x=7, player_y=8,
        enemy_species_id=16, enemy_level=3, initial_hp=20, final_hp=20,
        maximum_hp_preserved=True, party_preserved=True, level_preserved=True,
        pp_preserved=True, status_preserved=True, control_ready=fault != "unverified",
        run_attempts=1, stabilization_frames=24,
    )
    calls = []

    def escape(*_args, **_kwargs):
        calls.append("wild-escape")
        fake.raw = replace(fake.raw, battle_state=2 if fault == "battle" else 0,
                           map_id=2 if fault == "map" else MapId.ROUTE_1,
                           player_x=6 if fault == "tile" else 7)
        fake.trainer_engagement = fault != "no_successor"
        return evidence

    monkeypatch.setattr("pokemon_red_completion.gen1_route_runtime.flee_wild", escape)
    handler = Gen1WildFleeHandler(FakeExecutor(), reader_as_real(fake), 1, 24)
    initial = TraversalSnapshot(MapId.ROUTE_1, (8, 7), False, "wild_battle")
    if fault not in {None, "no_successor"}:
        with pytest.raises(RouteExecutionError, match="verified field boundary"):
            handler.handle(initial)
    else:
        receipt = handler.handle(initial)
        assert receipt.kind == "wild_battle" and receipt.details["verified"]
        successor = TraversalSnapshot(MapId.ROUTE_1, (8, 7), False, "trainer_engagement")
        assert _pending_verified_interruption(receipt, successor) is (fault is None)
        assert ("pending_interruption_kind" in receipt.details) is (fault is None)
        assert not _pending_verified_interruption(
            receipt, TraversalSnapshot(MapId.ROUTE_1, (8, 7), False, "scripted_dialogue")
        )
    assert calls == ["wild-escape"] and handler.evidence == [evidence]


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

    receipt = handler.handle(TraversalSnapshot(route_20_map_id, (15, 53), False, "wild_battle"))

    assert expected_maps == [route_20_map_id]
    assert receipt.resumed_map == route_20_map_id


def test_wild_handler_native_faint_opt_in_uses_whole_party_controller(monkeypatch):
    from types import SimpleNamespace

    calls = []
    evidence = SimpleNamespace(
        map_id=MapId.ROUTE_1,
        player_y=8,
        player_x=7,
        public_dict=lambda: dict(verified=True, party_faints_allowed=True, new_fainted_slots=[1]),
    )

    def escape(*args, **kwargs):
        calls.append(kwargs)
        return evidence

    monkeypatch.setattr("pokemon_red_completion.wild_party_flee.flee_with_fainted_lead", escape)
    monkeypatch.setattr(
        "pokemon_red_completion.gen1_route_runtime.flee_wild",
        lambda *a, **k: pytest.fail("strict controller must not be selected"),
    )
    handler = Gen1WildFleeHandler(
        cast(object, FakeExecutor()),
        reader_as_real(FakeReader(raw(battle_state=1))),
        maximum_flees=1,
        stabilization_frames=24,
        allow_party_faints=True,
    )
    result = handler.handle(TraversalSnapshot(MapId.ROUTE_1, (8, 7), False, "wild_battle"))
    assert calls[0]["allow_new_faints"] is True
    assert calls[0]["expected_map_id"] == MapId.ROUTE_1
    assert result.details["new_fainted_slots"] == [1]


@pytest.mark.parametrize("observer_kind", ["live", "captured"])
def test_traversal_latches_only_actual_intermediate_visits(observer_kind):
    from pokemon_red_completion.captured_progress import CapturedProgressEnvelope
    from pokemon_red_completion.red_player_observer import (
        CapturedPokemonRedObserver,
        LivePokemonRedObserver,
    )
    from pokemon_red_completion.route import COMPLETION_QUEST

    prefix = (
        "power_on", "begin_adventure", "choose_starter", "receive_pokedex",
        "reach_pewter", "defeat_brock", "reach_cerulean", "help_bill",
        "defeat_misty", "reach_vermilion", "obtain_cut", "defeat_surge",
    )
    reader = FakeReader(replace(raw(), map_id=MapId.ROCK_TUNNEL_1F))
    if observer_kind == "captured":
        semantic = CapturedPokemonRedObserver(reader, COMPLETION_QUEST,
            CapturedProgressEnvelope("a" * 64, "retained", "Rock Tunnel", 1, 2, prefix))
    else:
        semantic = LivePokemonRedObserver(reader, COMPLETION_QUEST)
        semantic.latch_verified_facts(frozenset(
            fact for name in prefix for fact in COMPLETION_QUEST.objective(name).completion_facts))
    traversal = Gen1TraversalObserver(reader, observe_progress=semantic.observe_raw)
    traversal.observe()
    assert "reach_lavender" not in semantic.public_dict()["verified_objectives"]
    assert "reach_celadon" not in semantic.public_dict()["verified_objectives"]
    reader.raw = replace(reader.raw, map_id=MapId.LAVENDER_TOWN)
    traversal.observe()
    reader.raw = replace(reader.raw, map_id=MapId.ROUTE_8)
    traversal.observe()
    assert "reach_lavender" in semantic.public_dict()["verified_objectives"]
    assert "reach_celadon" not in semantic.public_dict()["verified_objectives"]
    reader.raw = replace(reader.raw, map_id=MapId.CELADON_CITY)
    traversal.observe()
    assert {"reach_lavender", "reach_celadon"} <= set(semantic.public_dict()["verified_objectives"])


@pytest.mark.parametrize("fault", ["not_ready", "battle", "trainer", "dialogue"])
def test_unsettled_traversal_cannot_supply_progress(fault):
    reader = FakeReader(replace(raw(), map_id=MapId.LAVENDER_TOWN),
        ready=fault != "not_ready", trainer_engagement=fault == "trainer",
        dialogue_visible=fault == "dialogue")
    if fault == "battle":
        reader.raw = replace(reader.raw, battle_state=1)
    observed = []
    traversal = Gen1TraversalObserver(reader, observe_progress=observed.append)
    assert not traversal.observe().ready
    assert observed == []


def test_traversal_progress_does_not_invent_missing_prerequisite():
    from pokemon_red_completion.red_player_observer import LivePokemonRedObserver, ResumedStateError
    from pokemon_red_completion.route import COMPLETION_QUEST

    reader = FakeReader(replace(raw(), map_id=MapId.CELADON_CITY))
    semantic = LivePokemonRedObserver(reader, COMPLETION_QUEST)
    traversal = Gen1TraversalObserver(reader, observe_progress=semantic.observe_raw)
    with pytest.raises(ResumedStateError, match="prerequisites"):
        traversal.observe()


def test_traversal_progress_receives_the_same_actual_raw_frame():
    reader = FakeReader(raw())
    observed = []
    Gen1TraversalObserver(reader, observe_progress=observed.append).observe()
    assert observed == [reader.raw] and observed[0] is reader.raw
