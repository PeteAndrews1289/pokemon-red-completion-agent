"""ROM-free tests for routed Pokémon Center recovery."""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

import pokemon_red_completion.red_routed_recovery as recovery
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.global_router import MacroPath
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalDecisionOutcome,
    GoalFailureReason,
    GoalKind,
    GoalOpportunity,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.local_router import LocalEdge, LocalPath
from pokemon_red_completion.observation import RawGameState
from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    PartyObservation,
    StatusCondition,
)
from pokemon_red_completion.red_goal_manager import RedGoalObservation
from pokemon_red_completion.red_routed_recovery import (
    RecoveryRouteInterruptionHandler,
    RedRoutedRecoveryError,
    bind_routed_center_recovery,
)
from pokemon_red_completion.route_executor import TraversalSnapshot
from pokemon_red_completion.route_plan import RoutePlan, RoutePlanningError


def make_test_party(
    hp1: int = 0,
    hp2: int = 15,
    st1: StatusCondition = StatusCondition.HEALTHY,
    st2: StatusCondition = StatusCondition.HEALTHY,
    sp1: int = 15,
    sp2: int = 25,
) -> PartyObservation:
    return PartyObservation(
        members=(
            PartyMemberObservation(
                slot=1,
                species_id=sp1,
                level=10,
                hp=hp1,
                max_hp=30,
                status=st1,
                moves=(
                    MoveObservation(1, 10, 10),
                    MoveObservation(2, 10, 10),
                ),
            ),
            PartyMemberObservation(
                slot=2,
                species_id=sp2,
                level=12,
                hp=hp2,
                max_hp=30,
                status=st2,
                moves=(
                    MoveObservation(3, 10, 10),
                    MoveObservation(4, 10, 10),
                ),
            ),
        )
    )


def make_test_raw(
    map_id: int = 64,
    x: int = 3,
    y: int = 7,
    hp: tuple[int, ...] = (0, 15),
    status: tuple[int, ...] = (0, 0),
    species: tuple[int, ...] = (15, 25),
) -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=map_id,
        player_x=x,
        player_y=y,
        party_count=len(species),
        battle_state=0,
        bag_items=((4, 2),),
        player_money=209,
        party_species_ids=species,
        party_levels=(10, 12),
        party_hp=hp,
        party_max_hp=(30, 30),
        party_status=status,
        party_moves=((1, 2), (3, 4)),
        party_pp=((10, 10), (10, 10)),
    )


def make_real_route(terminal_map: int = 64) -> RoutePlan:
    edge = LocalEdge((7, 3), "up")
    return RoutePlan(
        macro_path=MacroPath((terminal_map,), ()),
        start_at=(6, 5),
        start_mode="land",
        segments=(),
        terminal_approach=LocalPath(
            ((6, 5), (7, 3)),
            (edge,),
            ("land", "land"),
        ),
        terminal_at=(7, 3),
        terminal_mode="land",
    )


def make_fixture(monkeypatch):
    calls = []
    actions_executed = 0
    frame_count = 0

    state = {
        "raw": make_test_raw(map_id=22, x=5, y=6, hp=(0, 15)),
        "party": make_test_party(0, 15),
        "safety": 0.25,
    }

    collection_obs = SimpleNamespace(
        current_box_index=0,
        box_counts=(2, 0, 0),
        box_capacity=20,
        specimens=("beedrill_specimen", "pikachu_specimen"),
    )

    def read_raw() -> RawGameState:
        return state["raw"]

    def observe() -> RedGoalObservation:
        return RedGoalObservation(
            raw=state["raw"],
            game_state=GameState(GameMode.OVERWORLD, location="test-map"),
            party=state["party"],
            collection=SimpleNamespace(
                collection=SimpleNamespace(
                    pokedex_owned_count=2,
                    living_count=2,
                )
            ),
            collection_observation=collection_obs,
            evidence=SimpleNamespace(safety=state["safety"]),
            input_ready=True,
            capture_item_count=0,
            recovery_item_count=0,
            free_storage_slots=0,
            immediate_capture_slots=0,
        )

    class FakeActions:
        @property
        def actions_executed(self) -> int:
            return actions_executed

        def execute(self, action) -> None:
            nonlocal actions_executed, frame_count
            actions_executed += 1
            frame_count += 1
            raw = state["raw"]
            if (
                action.kind is MacroActionKind.MOVE
                and action.value == "up"
            ):
                if raw.player_y is not None and raw.player_y > 3:
                    state["raw"] = replace(raw, player_y=raw.player_y - 1)
            elif action.kind is MacroActionKind.CONFIRM and raw.player_y == 3:
                species = raw.party_species_ids or (15, 25)
                state["raw"] = replace(
                    raw,
                    party_hp=(30, 30),
                    party_status=(0, 0),
                    party_pp=((10, 10), (10, 10)),
                )
                state["party"] = make_test_party(
                    30, 30, sp1=species[0], sp2=species[1]
                )
                state["safety"] = 1.0

    class FakeEmulator:
        @property
        def frame_count(self) -> int:
            return frame_count

    reader = SimpleNamespace(
        read=read_raw,
        read_input_readiness=lambda: SimpleNamespace(ready=True),
        read_bottom_dialogue_box_visible=lambda: False,
        read_player_facing=lambda: "up",
    )
    adapter = SimpleNamespace(
        observe=observe,
        graph=SimpleNamespace(completed_ids=lambda _: frozenset()),
    )
    runtime = SimpleNamespace(
        reader=reader,
        emulator=FakeEmulator(),
        adapter=adapter,
        profile=SimpleNamespace(providers=()),
    )
    actions = FakeActions()

    route = make_real_route(terminal_map=64)
    world = SimpleNamespace(
        plan_feasible_to_map=lambda start, map_id, goal_at: route,
    )
    router = SimpleNamespace(
        runtime=runtime,
        actions=actions,
        world=world,
        _replan=lambda req: route,
    )

    traversal_obs = SimpleNamespace(
        observe=lambda: TraversalSnapshot(
            map_id=state["raw"].map_id or 0,
            at=(state["raw"].player_y or 0, state["raw"].player_x or 0),
            ready=True,
            mode="land",
        )
    )

    unavailable_restore = GoalOpportunity(
        binding_ref="pokemon.red:recovery:field-items",
        kind=GoalKind.RESTORE_TEAM,
        availability=GoalAvailability.UNAVAILABLE,
        unavailable_reason=GoalUnavailableReason.MISSING_CAPABILITY,
    )
    other_opp = GoalOpportunity(
        binding_ref="pokemon.red:acquisition:source",
        kind=GoalKind.ACQUIRE_SPECIES,
        availability=GoalAvailability.AVAILABLE,
        estimated_effort=0.4,
        estimated_risk=0.1,
    )
    other_binding = ExecutableGoalBinding(
        binding_ref="pokemon.red:acquisition:source",
        kind=GoalKind.ACQUIRE_SPECIES,
        estimated_effort=0.4,
        estimated_risk=0.1,
        execute=lambda: pytest.fail("other goal should not execute"),
        verify=lambda rep: GoalVerification.succeeded(),
    )
    bindings = GoalBindingSet((unavailable_restore, other_opp), (other_binding,))

    monkeypatch.setattr(recovery, "Gen1TraversalObserver", lambda _: traversal_obs)
    monkeypatch.setattr(recovery, "_POKEMON_CENTER_MAPS", frozenset({64}))
    monkeypatch.setattr(
        recovery,
        "dependency_specimen_ledger",
        lambda c: tuple(c.specimens),
    )
    monkeypatch.setattr(recovery, "prepare_center_departure", lambda *_: None)

    def mock_execute_route(
        active_route,
        action_port,
        observer,
        interruption_handler=None,
        replanner=None,
        limits=None,
    ):
        calls.append("transport")
        raw = state["raw"]
        state["raw"] = replace(raw, map_id=64, player_x=3, player_y=7)
        return SimpleNamespace(passed=True)

    monkeypatch.setattr(recovery, "execute_route", mock_execute_route)

    return router, bindings, observe, state, collection_obs, calls


def test_action_free_enumeration(monkeypatch):
    """Enumeration must not execute controller actions or emulator frames."""
    router, bindings, observe, state, collection_obs, calls = make_fixture(
        monkeypatch
    )
    initial_obs = observe()
    before_act = router.actions.actions_executed
    before_frame = router.runtime.emulator.frame_count

    result = bind_routed_center_recovery(
        router, bindings, initial_obs, prepare_escort=lambda: None
    )

    assert router.actions.actions_executed == before_act
    assert router.runtime.emulator.frame_count == before_frame
    assert len(result.bindings) == 2


def test_explicit_pp_recovery_replaces_available_field_items_with_center_only(monkeypatch):
    router, bindings, observe, state, _, calls = make_fixture(monkeypatch)
    state["safety"] = 1.0
    state["raw"] = replace(
        state["raw"], party_hp=(30, 30), party_status=(0, 0),
        party_pp=((0, 10), (10, 10)),
    )
    state["party"] = make_test_party(30, 30)
    field = ExecutableGoalBinding(
        binding_ref="field-items", kind=GoalKind.RESTORE_TEAM,
        estimated_effort=0.1, estimated_risk=0.1,
        execute=lambda: pytest.fail("PP recovery must not use field items"),
        verify=lambda report: GoalVerification.succeeded(),
    )
    original = GoalBindingSet(
        (field.opportunity, bindings.opportunities[1]), (field, bindings.bindings[0]),
    )
    # Historical behavior/restore hashes remain unchanged by default.
    assert bind_routed_center_recovery(
        router, original, observe(), prepare_escort=lambda: None,
    ) is original
    result = bind_routed_center_recovery(
        router, original, observe(), prepare_escort=lambda: None, require_pp_restore=True,
    )
    restore = next(b for b in result.bindings if b.kind is GoalKind.RESTORE_TEAM)
    assert restore is not field
    assert ":routed-center:" in restore.binding_ref
    assert router.actions.actions_executed == 0
    assert calls == []


def test_route_blocked(monkeypatch):
    """1. Unknown/blocked routes abstain without modifying unavailable goals."""
    router, bindings, observe, state, collection_obs, calls = make_fixture(
        monkeypatch
    )
    router.world.plan_feasible_to_map = lambda *a, **k: (_ for _ in ()).throw(
        RoutePlanningError("route blocked")
    )
    initial_obs = observe()
    result = bind_routed_center_recovery(
        router, bindings, initial_obs, prepare_escort=lambda: None
    )
    assert result == bindings
    assert not any(b.kind is GoalKind.RESTORE_TEAM for b in result.bindings)


def test_existing_available_goal_leave_alone(monkeypatch):
    """2. An already available restore skill must never be overwritten."""
    router, bindings, observe, state, collection_obs, calls = make_fixture(
        monkeypatch
    )
    existing_restore = ExecutableGoalBinding(
        "existing-restore",
        GoalKind.RESTORE_TEAM,
        0.1,
        0.01,
        execute=lambda: pytest.fail("should not execute"),
        verify=lambda _: GoalVerification.succeeded(),
    )
    avail_bindings = GoalBindingSet(
        (existing_restore.opportunity, bindings.opportunities[1]),
        (existing_restore, bindings.bindings[0]),
    )
    result = bind_routed_center_recovery(
        router, avail_bindings, observe(), prepare_escort=lambda: None
    )
    assert result == avail_bindings
    assert result.bindings[0].binding_ref == "existing-restore"


def test_stale_hp_no_prep_input(monkeypatch):
    """3. Stale starting party HP rejects BEFORE input or preparation."""
    router, bindings, observe, state, collection_obs, calls = make_fixture(
        monkeypatch
    )
    prep_called = False

    def prepare():
        nonlocal prep_called
        prep_called = True

    result = bind_routed_center_recovery(
        router, bindings, observe(), prepare_escort=prepare
    )
    routed = result.require(
        next(b.binding_ref for b in result.bindings if b.kind is GoalKind.RESTORE_TEAM)
    )

    # Mutate HP before execute() is invoked
    state["raw"] = replace(state["raw"], party_hp=(5, 15))
    with pytest.raises(
        RedRoutedRecoveryError, match="party state changed before execution"
    ):
        routed.execute()

    assert not prep_called
    assert router.actions.actions_executed == 0


def test_prep_before_transport(monkeypatch):
    """4. Escort preparation must be invoked BEFORE any transport action."""
    router, bindings, observe, state, collection_obs, calls = make_fixture(
        monkeypatch
    )

    def prepare():
        calls.append("prep")

    result = bind_routed_center_recovery(
        router, bindings, observe(), prepare_escort=prepare
    )
    routed = result.require(
        next(b.binding_ref for b in result.bindings if b.kind is GoalKind.RESTORE_TEAM)
    )

    routed.execute()
    assert calls[:2] == ["prep", "transport"]


def test_duplicate_call_rejected(monkeypatch):
    """5. Reused binding execution must be rejected."""
    router, bindings, observe, state, collection_obs, calls = make_fixture(
        monkeypatch
    )
    result = bind_routed_center_recovery(
        router, bindings, observe(), prepare_escort=lambda: None
    )
    routed = result.require(
        next(b.binding_ref for b in result.bindings if b.kind is GoalKind.RESTORE_TEAM)
    )

    routed.execute()
    with pytest.raises(RedRoutedRecoveryError, match="already consumed"):
        routed.execute()


def test_real_verification_requires_hp_change(monkeypatch):
    """6. Real verification fails if HP did not actually change from damaged start."""
    router, bindings, observe, state, collection_obs, calls = make_fixture(
        monkeypatch
    )

    def no_hp_change_center(_):
        def offer(obs):
            return SimpleNamespace(
                binding=ExecutableGoalBinding(
                    "pokemon.red:recovery:pokemon-center",
                    GoalKind.RESTORE_TEAM,
                    0.04,
                    0.01,
                    execute=lambda: GoalExecutionReport(
                        1, 1, {"bounded": True}
                    ),
                    verify=lambda rep: GoalVerification.succeeded(),
                )
            )

        return SimpleNamespace(offer=offer)

    monkeypatch.setattr(recovery, "_make_center_provider", no_hp_change_center)

    result = bind_routed_center_recovery(
        router, bindings, observe(), prepare_escort=lambda: None
    )
    routed = result.require(
        next(b.binding_ref for b in result.bindings if b.kind is GoalKind.RESTORE_TEAM)
    )

    report = routed.execute()
    verif = routed.verify(report)
    assert verif.status is GoalDecisionOutcome.FAILED
    assert verif.failure_reason is GoalFailureReason.OUTCOME_NOT_VERIFIED


def test_partial_heal_refuse(monkeypatch):
    """7. Refuse incomplete or partial party healing."""
    router, bindings, observe, state, collection_obs, calls = make_fixture(
        monkeypatch
    )

    def partial_heal_center(_):
        def offer(obs):
            def exec_partial():
                # Only heal member 0; member 1 stays damaged
                state["raw"] = replace(state["raw"], party_hp=(30, 15))
                return GoalExecutionReport(5, 20, {"bounded": True})

            return SimpleNamespace(
                binding=ExecutableGoalBinding(
                    "pokemon.red:recovery:pokemon-center",
                    GoalKind.RESTORE_TEAM,
                    0.04,
                    0.01,
                    execute=exec_partial,
                    verify=lambda rep: GoalVerification.succeeded(),
                )
            )

        return SimpleNamespace(offer=offer)

    monkeypatch.setattr(recovery, "_make_center_provider", partial_heal_center)

    result = bind_routed_center_recovery(
        router, bindings, observe(), prepare_escort=lambda: None
    )
    routed = result.require(
        next(b.binding_ref for b in result.bindings if b.kind is GoalKind.RESTORE_TEAM)
    )

    report = routed.execute()
    verif = routed.verify(report)
    assert verif.status is GoalDecisionOutcome.FAILED
    assert verif.failure_reason is GoalFailureReason.OUTCOME_NOT_VERIFIED


def test_postbattle_new_faint_stop(monkeypatch):
    """8. Stop transport immediately if a new faint occurs after an interruption."""
    router, bindings, observe, state, collection_obs, calls = make_fixture(
        monkeypatch
    )

    def route_with_interruption(
        active_route,
        actions,
        traversal,
        interruption_handler,
        replanner=None,
        limits=None,
    ):
        assert isinstance(
            interruption_handler, RecoveryRouteInterruptionHandler
        )
        assert interruption_handler.post_prep_living_slots == (1,)
        interruption = TraversalSnapshot(
            map_id=22, at=(6, 5), ready=True, interruption="wild_battle"
        )
        interruption_handler.inner = SimpleNamespace(
            handled_hazard_kinds=frozenset({"trainer_sight"}),
            handle=lambda intr: SimpleNamespace(
                kind="wild_battle",
                resumed_map=22,
                resumed_at=(6, 5),
                details={},
            ),
        )
        state["raw"] = replace(state["raw"], party_hp=(0, 0))
        interruption_handler.handle(interruption)

    monkeypatch.setattr(recovery, "execute_route", route_with_interruption)

    result = bind_routed_center_recovery(
        router, bindings, observe(), prepare_escort=lambda: None
    )
    routed = result.require(
        next(b.binding_ref for b in result.bindings if b.kind is GoalKind.RESTORE_TEAM)
    )

    with pytest.raises(
        RedRoutedRecoveryError,
        match="party slot 1 fainted during route interruption",
    ):
        routed.execute()


def test_postbattle_missing_slot_stop(monkeypatch):
    """8b. Stop transport if roster truncates or members disappear during battle."""
    router, bindings, observe, state, collection_obs, calls = make_fixture(
        monkeypatch
    )

    def route_with_missing_slot(
        active_route,
        actions,
        traversal,
        interruption_handler,
        replanner=None,
        limits=None,
    ):
        interruption = TraversalSnapshot(
            map_id=22, at=(6, 5), ready=True, interruption="wild_battle"
        )
        interruption_handler.inner = SimpleNamespace(
            handled_hazard_kinds=frozenset({"trainer_sight"}),
            handle=lambda intr: SimpleNamespace(
                kind="wild_battle",
                resumed_map=22,
                resumed_at=(6, 5),
                details={},
            ),
        )
        # Member disappeared!
        state["raw"] = replace(
            state["raw"], party_species_ids=(15,), party_hp=(0,)
        )
        interruption_handler.handle(interruption)

    monkeypatch.setattr(recovery, "execute_route", route_with_missing_slot)

    result = bind_routed_center_recovery(
        router, bindings, observe(), prepare_escort=lambda: None
    )
    routed = result.require(
        next(b.binding_ref for b in result.bindings if b.kind is GoalKind.RESTORE_TEAM)
    )

    with pytest.raises(
        RedRoutedRecoveryError, match="party roster truncated or changed"
    ):
        routed.execute()


def test_ledger_change_fail(monkeypatch):
    """9. Fail if escort preparation alters the complete living Pokédex ledger."""
    router, bindings, observe, state, collection_obs, calls = make_fixture(
        monkeypatch
    )

    def bad_escort():
        collection_obs.specimens = ("beedrill_specimen",)

    result = bind_routed_center_recovery(
        router, bindings, observe(), prepare_escort=bad_escort
    )
    routed = result.require(
        next(b.binding_ref for b in result.bindings if b.kind is GoalKind.RESTORE_TEAM)
    )

    with pytest.raises(
        RedRoutedRecoveryError, match="living collection ledger"
    ):
        routed.execute()


def test_callback_silent_heal_rejected(monkeypatch):
    """Callback preparation must not silently heal members."""
    router, bindings, observe, state, collection_obs, calls = make_fixture(
        monkeypatch
    )

    def sneaky_heal():
        # Sneakily heal Beedrill during escort preparation
        state["raw"] = replace(state["raw"], party_hp=(30, 15))

    result = bind_routed_center_recovery(
        router, bindings, observe(), prepare_escort=sneaky_heal
    )
    routed = result.require(
        next(b.binding_ref for b in result.bindings if b.kind is GoalKind.RESTORE_TEAM)
    )

    with pytest.raises(
        RedRoutedRecoveryError,
        match="escort preparation altered member health",
    ):
        routed.execute()


def test_successful_routed_recovery_end_to_end(monkeypatch):
    """Success fixture with actual RedCenterRestoreGoalProvider movement and heal."""
    router, bindings, observe, state, collection_obs, calls = make_fixture(
        monkeypatch
    )

    def prepare():
        calls.append("prep")
        # Escort preparation reorders party slots without healing
        raw = state["raw"]
        state["raw"] = replace(
            raw,
            party_species_ids=(25, 15),
            party_hp=(15, 0),
            party_levels=(12, 10),
            party_moves=((3, 4), (1, 2)),
            party_pp=((10, 10), (10, 10)),
        )
        state["party"] = make_test_party(15, 0, sp1=25, sp2=15)

    result = bind_routed_center_recovery(
        router, bindings, observe(), prepare_escort=prepare
    )
    routed = result.require(
        next(b.binding_ref for b in result.bindings if b.kind is GoalKind.RESTORE_TEAM)
    )

    report = routed.execute()
    assert calls[:2] == ["prep", "transport"]
    assert report.actions_executed > 0
    assert report.frames_executed > 0
    assert report.evidence["routed_recovery"]["escort_prepared"] is True
    assert report.evidence["routed_recovery"]["center_map_id"] == 64

    verif = routed.verify(report)
    assert verif.status is GoalDecisionOutcome.SUCCEEDED


def test_already_at_nurse_boundary_avoids_meaningless_route(monkeypatch):
    """Support already at nurse boundary via existing provider, avoiding route."""
    router, bindings, observe, state, collection_obs, calls = make_fixture(
        monkeypatch
    )
    state["raw"] = replace(
        state["raw"], map_id=64, player_x=3, player_y=7
    )

    result = bind_routed_center_recovery(
        router,
        bindings,
        observe(),
        prepare_escort=lambda: calls.append("prep"),
    )
    routed = result.require(
        next(b.binding_ref for b in result.bindings if b.kind is GoalKind.RESTORE_TEAM)
    )

    report = routed.execute()
    assert "transport" not in calls
    assert calls == ["prep"]

    verif = routed.verify(report)
    assert verif.status is GoalDecisionOutcome.SUCCEEDED


def test_all_alive_and_restored_abstains(monkeypatch):
    """If party is already completely healthy and full, recovery abstains."""
    router, bindings, observe, state, collection_obs, calls = make_fixture(
        monkeypatch
    )
    state["raw"] = replace(
        state["raw"],
        party_hp=(30, 30),
        party_status=(0, 0),
        party_pp=((10, 10), (10, 10)),
    )
    state["party"] = make_test_party(30, 30)
    state["safety"] = 1.0

    result = bind_routed_center_recovery(
        router, bindings, observe(), prepare_escort=lambda: None
    )
    assert result == bindings
    assert not any(b.kind is GoalKind.RESTORE_TEAM for b in result.bindings)
