"""Independent composition checks for finite, model-visible trainer income."""

import json
from dataclasses import dataclass, replace
from types import SimpleNamespace

import pytest

import pokemon_red_completion.red_routed_trainer_funding as funding
from pokemon_red_completion.gen1_trainer_parties import TrainerPartyMember, TrainerPartyQuote
from pokemon_red_completion.gen1_trainer_sight import TrainerFacing, TrainerSightZone
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalDecisionOutcome,
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
from pokemon_red_completion.observation import ItemId, MapId, RawGameState
from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    PartyObservation,
    StatusCondition,
)
from pokemon_red_completion.red_goal_skills import RedMartPurchase, RedMartResupplyGoalProvider
from pokemon_red_completion.red_trainer_funding import TrainerFundingCandidate


@dataclass
class TestReceipt:
    __test__ = False
    initial_money: int = 9
    final_money: int = 1059
    payout: int = 1050
    ordinary_victory_money: int = 1050
    pay_day_money: int = 0
    actor_terminal_handoff: bool = False


def fixture(monkeypatch):
    calls = []
    party = PartyObservation(
        (
            PartyMemberObservation(
                slot=1,
                species_id=28,
                level=66,
                hp=213,
                max_hp=213,
                status=StatusCondition.HEALTHY,
                moves=(MoveObservation(57, 10, 15),),
            ),
        )
    )
    raw = RawGameState(
        game_started=True,
        map_id=22,
        player_x=18,
        player_y=9,
        battle_state=0,
        battle_result=0,
        player_money=9,
        bag_items=((int(ItemId.FULL_RESTORE), 4),),
        party_count=1,
        party_species_ids=(28,),
        party_hp=(213,),
        event_flags=bytes(320),
    )
    state = SimpleNamespace(
        raw=raw, party=party, input_ready=True, collection_observation=(28, 48, 48)
    )
    reader = SimpleNamespace(
        read=lambda: state.raw,
        read_current_map_objects=lambda: (),
        read_bottom_dialogue_box_visible=lambda: False,
        read_pending_trainer_battle_identity=lambda: None,
        read_player_facing=lambda: "down",
    )
    actions = SimpleNamespace(actions_executed=0)
    emulator = SimpleNamespace(frame_count=0)
    provider = RedMartResupplyGoalProvider(
        MapId.VIRIDIAN_MART,
        3,
        4,
        "up",
        (RedMartPurchase(0, ItemId.POKE_BALL, 5, 200),),
        actions,
        reader,
        emulator,
        SimpleNamespace(observe=lambda: state),
        affordable_ball_purchase=True,
    )
    runtime = SimpleNamespace(
        trainer_battle_runner=None,
        trainer_battle_model_sha256=None,
        reader=reader,
        emulator=emulator,
        adapter=SimpleNamespace(observe=lambda: state),
        provider_for=lambda *_: provider,
        profile=SimpleNamespace(
            providers=(SimpleNamespace(kind=GoalKind.RESUPPLY, parameters={}),)
        ),
    )
    router = SimpleNamespace(
        runtime=runtime,
        actions=actions,
        world=SimpleNamespace(rom=b"test"),
        trainer_pending_recovery=True,
    )
    trainer = TrainerSightZone(22, 4, 212, 2, (11, 36), TrainerFacing.UP, 3, 1130, False, True)
    quote = TrainerPartyQuote(212, 2, (TrainerPartyMember(173, 81, 21),), 50, 1050)
    target = TrainerFundingCandidate(
        trainer, quote, SimpleNamespace(steps=(object(),), terminal_at=(10, 36)), TrainerFacing.DOWN
    )
    monkeypatch.setattr(funding, "_candidates", lambda _: (target,))
    monkeypatch.setattr(funding, "_observed_funding_target", lambda _router, quoted: quoted)
    monkeypatch.setattr(funding, "dependency_specimen_ledger", lambda c: tuple(sorted(c)))

    def checked_headers(*_args, **kwargs):
        assert kwargs == {"full_event_offsets": True}
        return ()

    monkeypatch.setattr(funding, "trainer_headers", checked_headers)
    monkeypatch.setattr(funding, "map_object_events", lambda *_: ())
    monkeypatch.setattr(funding, "trainer_sight_zones", lambda *_: (trainer,))
    monkeypatch.setattr(funding, "trainer_party_quote", lambda *_: quote)
    monkeypatch.setattr(funding, "Gen1TraversalObserver", lambda *_: object())

    def projector(*_, full_event_offsets=False):
        assert full_event_offsets is getattr(router, "regional_trainer_funding", False)
        return object()

    monkeypatch.setattr(funding, "Gen1TrainerSightProjector", projector)
    monkeypatch.setattr(funding, "Gen1WildFleeHandler", lambda *_a, **_k: object())

    def tick(name):
        calls.append(name)
        actions.actions_executed += 1
        emulator.frame_count += 10

    def travel(*_a, **_k):
        tick("route")
        state.raw = replace(state.raw, player_y=10, player_x=36)
        return SimpleNamespace(passed=True)

    def battle(_reader, _actions, **kwargs):
        kwargs["validate_target"]()
        tick("battle")
        flags = bytearray(320)
        flags[141] = 4  # Literal event 1130: not computed from the quote or implementation.
        state.raw = replace(state.raw, player_money=1059, event_flags=bytes(flags))
        return TestReceipt()

    monkeypatch.setattr(funding, "prepare_capture_escort", lambda *_: tick("escort"))
    monkeypatch.setattr(funding, "face_pc_boundary", lambda *_: tick("face"))
    monkeypatch.setattr(funding, "execute_route", travel)
    monkeypatch.setattr(
        "pokemon_red_completion.red_trainer_funding_battle.run_prepared_trainer_funding", battle
    )
    alternate = ExecutableGoalBinding(
        "evolve",
        GoalKind.EVOLVE_SPECIES,
        0.4,
        0.2,
        lambda: GoalExecutionReport(0, 0, {}),
        lambda _: GoalVerification.succeeded(),
    )
    unavailable = GoalOpportunity(
        "no-money",
        GoalKind.RESUPPLY,
        GoalAvailability.UNAVAILABLE,
        unavailable_reason=GoalUnavailableReason.MISSING_RESOURCE,
    )
    bindings = GoalBindingSet((unavailable, alternate.opportunity), (alternate,))
    return router, state, target, bindings, calls


@pytest.mark.parametrize("fault", (None, "goal", "position", "trainer", "reward", "facing"))
def test_live_funding_detour_keeps_exact_target_and_blockers(monkeypatch, fault):
    from pokemon_red_completion.local_router import LocalEdge, LocalGraph
    from pokemon_red_completion.route_executor import ReplanRequest, TraversalSnapshot
    from pokemon_red_completion.route_plan import RoutePlanningError

    router, state, target, _, _ = fixture(monkeypatch)
    graph = LocalGraph({(9, 18): (LocalEdge((9, 19), "right"), LocalEdge((10, 18), "down"))})

    @dataclass(frozen=True)
    class World:
        local_graphs: dict

        def with_current_observation(self, reader):
            assert reader is router.runtime.reader
            return self

    router.world = World({22: graph})
    request = ReplanRequest(
        TraversalSnapshot(22, (9, 18), True, mode="land"), 22, (10, 36),
        {22: frozenset({(9, 19)})}, 1,
    )
    if fault == "goal":
        request = replace(request, goal_at=(10, 35))
    if fault == "position":
        state.raw = replace(state.raw, player_x=17)
    fresh = replace(target, trainer=replace(target.trainer, visible=False))
    if fault == "trainer":
        fresh = replace(fresh, trainer=replace(fresh.trainer, trainer_set=3))
    if fault == "reward":
        fresh = replace(fresh, quote=replace(fresh.quote, base_money=51))
    if fault == "facing":
        fresh = replace(fresh, interaction_facing=TrainerFacing.LEFT)

    def observed(_router, *, world, required_interaction_at):
        assert _router is router and required_interaction_at == (10, 36)
        assert all(edge.target != (9, 19) for edge in world.local_graphs[22].neighbors((9, 18)))
        return (fresh,)

    monkeypatch.setattr(funding, "_candidates", observed)
    replan = funding._funding_approach_replanner(router, target)
    if fault in {"goal", "position"}:
        with pytest.raises(funding.RedTrainerFundingError):
            replan(request)
    elif fault:
        with pytest.raises(RoutePlanningError, match="same quoted trainer"):
            replan(request)
    else:
        assert replan(request) is target.approach


def test_observed_regional_funding_requotes_after_party_inputs(monkeypatch):
    router, _, target, bindings, calls = fixture(monkeypatch)
    target = replace(target, trainer=replace(target.trainer, facing=TrainerFacing.LEFT))
    monkeypatch.setattr(funding, "_candidates", lambda _: (target,))
    monkeypatch.setattr(funding, "trainer_sight_zones", lambda *_: (target.trainer,))
    router.regional_trainer_funding = True
    router.observed_trainer_funding = True
    stages = []

    def observe(_router, quoted):
        assert _router is router and quoted is target
        stages.append(tuple(calls))
        return target

    monkeypatch.setattr(funding, "_observed_funding_target", observe)
    selected = funding.bind_local_trainer_funding(
        router, bindings, router.runtime.adapter.observe()
    )
    binding = next(b for b in selected.bindings if b.kind is GoalKind.RESUPPLY)
    assert binding.verify(binding.execute()) == GoalVerification.succeeded()
    assert stages == [(), ("escort",)]


def test_changed_surf_scope_fails_before_input(monkeypatch):
    router, state, _, bindings, calls = fixture(monkeypatch)
    bound = funding.bind_local_trainer_funding(router, bindings, router.runtime.adapter.observe())
    binding = next(b for b in bound.bindings if b.kind is GoalKind.RESUPPLY)
    router.runtime.trainer_funding_surf = True
    with pytest.raises(funding.RedTrainerFundingError, match="Surf scope changed"):
        binding.execute()
    assert calls == []


def test_surf_approach_uses_existing_metered_port_and_requires_real_land_exit(monkeypatch):
    from pokemon_red_completion.actions import MacroAction, MacroActionKind
    from pokemon_red_completion.observation import OverworldMovementMode

    router, state, target, bindings, calls = fixture(monkeypatch)
    target = replace(
        target,
        approach=SimpleNamespace(
            steps=(SimpleNamespace(kind="water_entry"),),
            terminal_at=(10, 36),
        ),
    )
    monkeypatch.setattr(funding, "_candidates", lambda _: (target,))
    monkeypatch.setattr(funding, "Gen1TraversalObserver", lambda *_: SimpleNamespace())
    router.runtime.trainer_funding_surf = True
    router.runtime.reader.read_overworld_movement_mode = lambda: OverworldMovementMode.WALKING

    class FieldPort:
        def __init__(self, actions, reader, memory):
            assert actions is router.actions
            assert reader is router.runtime.reader and memory is router.runtime.emulator
            self.receipts = []

        def execute(self, action):
            assert action == MacroAction(MacroActionKind.FIELD_MOVE, "surf:down")
            router.actions.actions_executed += 1
            router.runtime.emulator.frame_count += 10
            self.receipts.append(object())
            calls.append("surf_meter")

    monkeypatch.setattr("pokemon_red_completion.gen1_field_moves.Gen1FieldMovePort", FieldPort)

    def travel(_plan, actions, observer, **_):
        assert isinstance(actions, FieldPort) and callable(observer.capability_projector)
        actions.execute(MacroAction(MacroActionKind.FIELD_MOVE, "surf:down"))
        state.raw = replace(state.raw, player_y=10, player_x=36)
        return SimpleNamespace(passed=True)

    monkeypatch.setattr(funding, "execute_route", travel)
    bound = funding.bind_local_trainer_funding(router, bindings, router.runtime.adapter.observe())
    binding = next(b for b in bound.bindings if b.kind is GoalKind.RESUPPLY)
    report = binding.execute()
    assert report.evidence["funding_verified_surfs"] == 1
    assert "surf_meter" in calls
    assert report.actions_executed == router.actions.actions_executed
    assert report.frames_executed == router.runtime.emulator.frame_count
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    before = router.actions.actions_executed
    router.runtime.reader.read_overworld_movement_mode = lambda: OverworldMovementMode.SURFING
    assert binding.verify(report).status is GoalDecisionOutcome.FAILED
    assert router.actions.actions_executed == before


def test_explicit_indoor_support_settles_before_party_preparation(monkeypatch):
    router, state, _, bindings, calls = fixture(monkeypatch)
    assert not funding._indoor_funding_enabled(router)
    router.runtime.profile.providers[0].parameters["indoor_funding_departure"] = True
    assert funding._indoor_funding_enabled(router)
    monkeypatch.setattr(funding, "prepare_center_departure", lambda *_: calls.append("departure"))
    bound = funding.bind_local_trainer_funding(router, bindings, state).bindings[-1]
    report = bound.execute()
    assert calls.index("departure") < calls.index("escort") < calls.index("route")
    assert report.actions_executed > 0


def resource_choice_fixture(monkeypatch, *, money=400, stock=0, enabled=True):
    from pokemon_red_completion.goal_resource_quote import GoalResourceQuote, GoalResourceReserve

    router, state, target, bindings, calls = fixture(monkeypatch)
    bag = ((int(ItemId.POKE_BALL), stock),) if stock else ()
    state.raw = replace(state.raw, player_money=money, bag_items=bag)
    state.capture_item_count = stock
    provider = router.runtime.provider_for(GoalKind.RESUPPLY, router.actions)
    provider.adapter.config = SimpleNamespace(desired_capture_items=5)
    router.runtime.profile.providers[0].parameters["resource_choice_variants"] = enabled
    buy = ExecutableGoalBinding(
        "affordable-buy",
        GoalKind.RESUPPLY,
        0.1,
        0.05,
        lambda: GoalExecutionReport(0, 0, {}),
        lambda _: GoalVerification.succeeded(),
        resource_quote=GoalResourceQuote(
            money, 200, (GoalResourceReserve("capture", stock, 5, 1),)
        ),
    )
    other = bindings.bindings[0]
    return (
        router,
        state,
        target,
        GoalBindingSet(
            (buy.opportunity, other.opportunity),
            (buy, other),
        ),
        calls,
    )


@pytest.mark.parametrize("money", [200, 400, 999])
def test_reserve_shortfall_keeps_affordable_purchase_and_adds_income(monkeypatch, money):
    router, state, _, original, calls = resource_choice_fixture(monkeypatch, money=money)
    offered = funding.bind_local_trainer_funding(router, original, state)
    assert offered.allow_resource_variants
    assert offered.bindings[:2] == original.bindings
    assert offered.opportunities[:2] == original.opportunities
    assert len(offered.bindings) == 3
    assert offered.bindings[2].resource_quote.expected_income == 1050
    assert offered.bindings[2].resource_quote.available_funds == money
    assert offered.bindings[0].resource_quote.purchase_cost == 200
    assert funding.bind_local_trainer_funding(router, offered, state) is offered
    assert calls == []
    assert router.actions.actions_executed == router.runtime.emulator.frame_count == 0


def test_reserve_shortfall_can_compose_partial_trainer_income(monkeypatch):
    router, state, target, original, calls = fixture(monkeypatch)
    router.runtime.profile.providers[0].parameters["resource_choice_variants"] = True
    provider = router.runtime.provider_for(GoalKind.RESUPPLY, router.actions)
    provider.adapter.config = SimpleNamespace(desired_capture_items=5)
    state.capture_item_count = 0
    # 9 + 160 remains below this Mart's 200-unit ball price.  The battle is
    # still useful because a later finite reward can compose with this one.
    partial = replace(
        target,
        quote=replace(target.quote, expected_victory_money=160),
    )
    monkeypatch.setattr(funding, "_candidates", lambda _: (partial,))

    # Historical profiles retain the old one-payout affordability contract,
    # allowing their saved semantic states to authenticate under new source.
    assert funding.bind_local_trainer_funding(router, original, state) is original
    router.runtime.profile.providers[0].parameters["composable_trainer_funding"] = True

    offered = funding.bind_local_trainer_funding(router, original, state)

    assert not calls
    assert offered.bindings[0] is original.bindings[0]
    assert offered.bindings[1].kind is GoalKind.RESUPPLY
    assert offered.bindings[1].resource_quote.available_funds == 9
    assert offered.bindings[1].resource_quote.expected_income == 160
    assert offered.bindings[1].resource_quote.purchase_cost == 0


@pytest.mark.parametrize("case", ["legacy", "funded", "stocked", "no_trainer", "fainted"])
def test_resource_variants_do_not_invent_unneeded_or_unsafe_income(monkeypatch, case):
    router, state, _, original, calls = resource_choice_fixture(
        monkeypatch,
        money=1000 if case == "funded" else 400,
        stock=5 if case == "stocked" else 0,
        enabled=case != "legacy",
    )
    if case == "no_trainer":
        monkeypatch.setattr(funding, "_candidates", lambda _: ())
    if case == "fainted":
        state.raw = replace(state.raw, party_hp=(0,))
    assert funding.bind_local_trainer_funding(router, original, state) is original
    assert calls == []


def test_observed_route_rejection_stops_before_escort_or_input(monkeypatch):
    router, state, _, bindings, calls = fixture(monkeypatch)

    def reject(_router, _target):
        raise funding.RedTrainerFundingError("observed route blocked")

    monkeypatch.setattr(funding, "_observed_funding_target", reject)
    bound = funding.bind_local_trainer_funding(router, bindings, state).bindings[-1]
    with pytest.raises(funding.RedTrainerFundingError, match="observed route blocked"):
        bound.execute()
    assert calls == []


def test_execution_uses_requalified_approach_not_stale_quoted_plan(monkeypatch):
    router, state, target, bindings, calls = fixture(monkeypatch)
    revised = replace(
        target, approach=SimpleNamespace(steps=("observed-safe-step",), terminal_at=(10, 36))
    )
    monkeypatch.setattr(funding, "_observed_funding_target", lambda *_: revised)

    def travel(plan, *_args, **_kwargs):
        assert plan is revised.approach
        assert plan.steps == ("observed-safe-step",)
        calls.append("observed_route")
        state.raw = replace(state.raw, player_y=10, player_x=36)
        return SimpleNamespace(passed=True)

    monkeypatch.setattr(funding, "execute_route", travel)
    bound = funding.bind_local_trainer_funding(router, bindings, state).bindings[-1]
    bound.execute()
    assert "observed_route" in calls


def test_trainer_facing_settles_one_same_boundary_wild_interruption(monkeypatch):
    router, state, target, bindings, calls = fixture(monkeypatch)
    reader = router.runtime.reader
    reader.read_input_readiness = lambda: SimpleNamespace(ready=True)

    def interrupted_face(*_args):
        calls.append("face")
        state.raw = replace(state.raw, battle_state=1)
        raise funding.RedPCStorageError("PC facing did not preserve its bound position")

    class Observer:
        def observe(self):
            assert state.raw.battle_state == 1
            return SimpleNamespace(
                interruption="wild_battle",
                map_id=state.raw.map_id,
                at=(state.raw.player_y, state.raw.player_x),
            )

    class Flee:
        def __init__(self, _actions, _reader, **kwargs):
            self.kwargs = kwargs

        def handle(self, interruption):
            assert self.kwargs == {
                "maximum_flees": 1,
                "stabilization_frames": 180,
                "route_name": "ordinary trainer funding facing",
            }
            calls.append("flee")
            state.raw = replace(state.raw, battle_state=0)
            return funding.InterruptionReceipt(
                "wild_battle", interruption.map_id, interruption.at, {"verified": True}
            )

    monkeypatch.setattr(funding, "face_pc_boundary", interrupted_face)
    monkeypatch.setattr(funding, "Gen1TraversalObserver", lambda *_: Observer())
    monkeypatch.setattr(funding, "Gen1WildFleeHandler", Flee)
    bound = funding.bind_local_trainer_funding(router, bindings, state).bindings[-1]

    report = bound.execute()

    assert calls == ["escort", "route", "face", "flee", "battle"]
    assert report.evidence["funding_facing_interruption"] == {
        "kind": "wild_battle",
        "resumed_map": target.trainer.map_id,
        "resumed_at": [10, 36],
        "details": {"verified": True},
    }
    assert bound.verify(report).status is GoalDecisionOutcome.SUCCEEDED


def test_trainer_facing_never_recovers_wild_interruption_after_position_drift(monkeypatch):
    router, state, _target, bindings, calls = fixture(monkeypatch)

    def interrupted_face(*_args):
        calls.append("face")
        state.raw = replace(state.raw, player_y=9, battle_state=1)
        raise funding.RedPCStorageError("PC facing did not preserve its bound position")

    class Observer:
        def observe(self):
            return SimpleNamespace(
                interruption="wild_battle",
                map_id=state.raw.map_id,
                at=(state.raw.player_y, state.raw.player_x),
            )

    monkeypatch.setattr(funding, "face_pc_boundary", interrupted_face)
    monkeypatch.setattr(funding, "Gen1TraversalObserver", lambda *_: Observer())

    class Flee:
        def __init__(self, *_args, **_kwargs):
            pass

        def handle(self, _interruption):
            pytest.fail("drifted encounter must not be controlled")

    monkeypatch.setattr(funding, "Gen1WildFleeHandler", Flee)
    bound = funding.bind_local_trainer_funding(router, bindings, state).bindings[-1]

    with pytest.raises(funding.RedTrainerFundingError, match="unchanged wild interruption"):
        bound.execute()

    assert calls == ["escort", "route", "face"]


@pytest.mark.parametrize(
    "damage", [None, "static", "live_identity", "live_facing", "not_visible", "not_opted_in"]
)
def test_regional_funding_rebinds_remote_quote_before_departure_and_live_arrival(
    monkeypatch, damage
):
    router, state, target, bindings, calls = fixture(monkeypatch)
    router.regional_trainer_funding = damage != "not_opted_in"
    quoted = replace(target.trainer, map_id=23, facing=TrainerFacing.RIGHT, visible=False)
    target = replace(target, trainer=quoted)
    monkeypatch.setattr(funding, "_candidates", lambda _: (target,))
    monkeypatch.setattr(
        funding,
        "static_trainer_sight_zones",
        lambda *_: (replace(quoted, defeated=True) if damage == "static" else quoted,),
    )
    live = replace(quoted, visible=True)
    if damage == "live_identity":
        live = replace(live, trainer_set=3)
    if damage == "live_facing":
        live = replace(live, facing=TrainerFacing.UP)
    if damage == "not_visible":
        live = replace(live, visible=False)
    monkeypatch.setattr(funding, "trainer_sight_zones", lambda *_: (live,))

    def travel(*_args, **_kwargs):
        calls.append("route")
        state.raw = replace(state.raw, map_id=23, player_y=10, player_x=36)
        return SimpleNamespace(passed=True)

    monkeypatch.setattr(funding, "execute_route", travel)
    bound = funding.bind_local_trainer_funding(router, bindings, state).bindings[-1]
    if damage:
        with pytest.raises(funding.RedTrainerFundingError):
            bound.execute()
        assert "face" not in calls and "battle" not in calls
        if damage in {"static", "not_opted_in"}:
            assert calls == []
    else:
        report = bound.execute()
        assert calls == ["escort", "route", "face", "battle"]
        assert bound.verify(report).status is GoalDecisionOutcome.SUCCEEDED


def test_funding_binding_preserves_alternatives_and_earns_not_buys(monkeypatch):
    router, state, _, bindings, calls = fixture(monkeypatch)
    result = funding.bind_local_trainer_funding(router, bindings, state)
    assert not calls and router.actions.actions_executed == 0
    assert result.bindings[0] is bindings.bindings[0]
    bound = result.bindings[1]
    assert bound.kind is GoalKind.RESUPPLY
    assert bound.resource_quote.expected_income == 1050
    assert bound.resource_quote.available_funds == 9
    assert bound.resource_quote.purchase_cost == 0 and bound.resource_quote.reserves == ()
    assert result.opportunities[0].availability is GoalAvailability.AVAILABLE
    report = bound.execute()
    assert calls == ["escort", "route", "face", "battle"]
    assert (report.actions_executed, report.frames_executed) == (4, 40)
    assert report.evidence["trainer_funding"]["payout"] == 1050
    assert report.evidence["balls_purchased"] == 0
    json.dumps(dict(report.evidence))  # No RawGameState bytes in journal evidence.
    assert bound.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    with pytest.raises(funding.RedTrainerFundingError, match="consumed"):
        bound.execute()
    assert calls == ["escort", "route", "face", "battle"]


@pytest.mark.parametrize("reserve_level,admitted", [(66, True), (30, False)])
def test_roster_preparation_keeps_ten_level_margin_on_actual_planned_lead(
    monkeypatch,
    reserve_level,
    admitted,
):
    router, state, _, bindings, calls = fixture(monkeypatch)
    original = state.party.members[0]
    state.party = PartyObservation(
        (replace(original, level=28), replace(original, slot=2, level=reserve_level))
    )
    state.raw = replace(state.raw, party_count=2, party_species_ids=(28, 28), party_hp=(213, 213))
    assert funding.bind_local_trainer_funding(router, bindings, state) is bindings
    router.runtime.trainer_funding_roster_preparation = True
    result = funding.bind_local_trainer_funding(router, bindings, state)
    assert any(b.kind is GoalKind.RESUPPLY for b in result.bindings) is admitted
    assert calls == []


def test_roster_funding_executes_declared_preparation_not_capture_escort(monkeypatch):
    import pokemon_red_completion.red_trainer_party as party

    router, state, target, bindings, calls = fixture(monkeypatch)
    router.runtime.trainer_funding_roster_preparation = True

    def prepare(runtime, actions, plan, *, current_quote):
        plan.require_current(state.party, current_quote)
        assert current_quote == target.quote
        calls.append("roster_preparation")

    monkeypatch.setattr(party, "prepare_trainer_lead", prepare)
    bound = funding.bind_local_trainer_funding(router, bindings, state).bindings[-1]
    report = bound.execute()
    assert calls == ["roster_preparation", "route", "face", "battle"]
    assert report.evidence["party_preparation"]["authority"] == "deterministic-matchup-preparation"
    assert bound.verify(report).status is GoalDecisionOutcome.SUCCEEDED


@pytest.mark.parametrize("mismatch", [None, "battle", "class", "facing", "defeated", "ambiguous"])
def test_active_recovery_identifies_only_exact_adjacent_cartridge_trainer(monkeypatch, mismatch):
    router, state, target, _bindings, calls = fixture(monkeypatch)
    state.raw = replace(state.raw, battle_state=2, player_y=10, player_x=36)
    reader = router.runtime.reader
    reader.read_active_trainer_identity = lambda: (212, 12, 2)
    if mismatch == "battle":
        state.raw = replace(state.raw, battle_state=1)
    elif mismatch == "class":
        reader.read_active_trainer_identity = lambda: (212, 11, 2)
    elif mismatch == "facing":
        reader.read_player_facing = lambda: "up"
    elif mismatch == "defeated":
        monkeypatch.setattr(
            funding, "trainer_sight_zones", lambda *_: (replace(target.trainer, defeated=True),)
        )
    elif mismatch == "ambiguous":
        monkeypatch.setattr(
            funding,
            "trainer_sight_zones",
            lambda *_: (target.trainer, replace(target.trainer, sprite_index=5)),
        )
    if mismatch is None:
        result = funding.active_trainer_funding_candidate(b"test", reader)
        assert result.trainer == target.trainer and not result.approach.steps
    else:
        with pytest.raises(funding.RedTrainerFundingError):
            funding.active_trainer_funding_candidate(b"test", reader)
    assert not calls


def test_active_recovery_explicitly_qualifies_final_trainer_class(monkeypatch):
    router, state, target, _bindings, _calls = fixture(monkeypatch)
    state.raw = replace(state.raw, battle_state=2, player_y=10, player_x=36)
    reader = router.runtime.reader
    reader.read_active_trainer_identity = lambda: (247, 47, 1)
    trainer = replace(target.trainer, trainer_class=247, trainer_set=1)
    monkeypatch.setattr(funding, "trainer_sight_zones", lambda *_: (trainer,))
    calls = []

    def quote(rom, trainer_class, trainer_set, **kwargs):
        calls.append((rom, trainer_class, trainer_set, kwargs))
        return target.quote

    monkeypatch.setattr(funding, "trainer_party_quote", quote)
    result = funding.active_trainer_funding_candidate(b"test", reader)
    assert result.trainer == trainer
    assert calls == [(b"test", 247, 1, {"allow_final_class": True})]


def test_pending_funding_resumes_without_party_menu_route_or_second_interaction(monkeypatch):
    router, state, target, bindings, calls = fixture(monkeypatch)
    state.raw = replace(state.raw, player_y=10, player_x=36)
    target = replace(target, approach=SimpleNamespace(steps=(), terminal_at=(10, 36)))
    monkeypatch.setattr(funding, "_candidates", lambda _: (target,))
    router.runtime.reader.read_pending_trainer_battle_identity = lambda: (212, 2)
    bound = funding.bind_local_trainer_funding(router, bindings, state).bindings[-1]
    assert bound.kind is GoalKind.RESUPPLY
    report = bound.execute()
    assert calls == ["battle"]
    assert bound.verify(report).status is GoalDecisionOutcome.SUCCEEDED


@pytest.mark.parametrize(
    "mismatch", [None, "facing", "identity", "hidden", "defeated", "ambiguous"]
)
def test_pending_candidate_does_not_route_out_of_armed_trainers_sight_lane(monkeypatch, mismatch):
    # Real candidate-builder path, not the fixture's mocked _candidates seam.
    from pokemon_red_completion.red_routed_trainer_funding import _candidates

    router, state, target, _bindings, _calls = fixture(monkeypatch)
    state.raw = replace(state.raw, player_y=10, player_x=36)
    router.runtime.reader.read_pending_trainer_battle_identity = lambda: (212, 2)
    zone = target.trainer
    if mismatch == "facing":
        router.runtime.reader.read_player_facing = lambda: "up"
    elif mismatch == "identity":
        zone = replace(zone, trainer_set=3)
    elif mismatch == "hidden":
        zone = replace(zone, visible=False)
    elif mismatch == "defeated":
        zone = replace(zone, defeated=True)
    zones = (zone, replace(zone, sprite_index=5)) if mismatch == "ambiguous" else (zone,)
    assert (10, 36) in zone.lane or mismatch == "defeated"
    monkeypatch.setattr(funding, "trainer_headers", lambda *_args, **_kwargs: ())
    monkeypatch.setattr(funding, "trainer_sight_zones", lambda *_: zones)

    def no_route(*_):
        raise AssertionError("pending battle must not invoke travel planning")

    monkeypatch.setattr(funding, "Gen1TraversalObserver", no_route)
    candidates = _candidates(router)
    if mismatch is None:
        assert len(candidates) == 1
        assert candidates[0].approach.steps == ()
        assert candidates[0].approach.terminal_at == (10, 36)
    else:
        assert candidates == ()


@pytest.mark.parametrize("native_hidden", [frozenset({4}), frozenset(), frozenset({5})])
def test_missing_regional_trainer_requires_exact_native_hidden_slot(monkeypatch, native_hidden):
    from pokemon_red_completion.red_routed_trainer_funding import _candidates

    router, state, target, _bindings, calls = fixture(monkeypatch)
    router.regional_trainer_funding = True
    router.runtime.reader.read_pending_trainer_battle_identity = lambda: (212, 2)
    router.runtime.reader.read_hidden_current_sprite_indices = lambda: native_hidden
    monkeypatch.setattr(
        funding,
        "trainer_headers",
        lambda *_args, **_kwargs: (SimpleNamespace(map_id=22, sprite_index=4),),
    )
    monkeypatch.setattr(funding, "trainer_sight_zones", lambda *_: ())
    if native_hidden == frozenset({4}):
        # A deliberately removed trainer supplies no candidate or reward.
        assert _candidates(router) == ()
    else:
        with pytest.raises(funding.RedTrainerFundingError, match="complete live trainer inventory"):
            _candidates(router)
    assert calls == []


def test_regional_inventory_rejects_a_live_zone_also_marked_hidden(monkeypatch):
    from pokemon_red_completion.red_routed_trainer_funding import _candidates

    router, state, target, _bindings, _calls = fixture(monkeypatch)
    router.regional_trainer_funding = True
    router.runtime.reader.read_hidden_current_sprite_indices = lambda: frozenset({4, 5})
    monkeypatch.setattr(
        funding,
        "trainer_headers",
        lambda *_args, **_kwargs: (
            SimpleNamespace(map_id=22, sprite_index=4),
            SimpleNamespace(map_id=22, sprite_index=5),
        ),
    )
    monkeypatch.setattr(funding, "trainer_sight_zones", lambda *_: (target.trainer,))
    with pytest.raises(funding.RedTrainerFundingError, match="complete live trainer inventory"):
        _candidates(router)


@pytest.mark.parametrize("mismatch", ["identity", "position", "facing", "pending_changed"])
def test_pending_funding_never_dispatches_unrelated_or_stale_work(monkeypatch, mismatch):
    router, state, target, bindings, calls = fixture(monkeypatch)
    state.raw = replace(state.raw, player_y=10, player_x=36)
    target = replace(target, approach=SimpleNamespace(steps=(), terminal_at=(10, 36)))
    monkeypatch.setattr(funding, "_candidates", lambda _: (target,))
    router.runtime.reader.read_pending_trainer_battle_identity = lambda: (212, 2)
    if mismatch == "identity":
        router.runtime.reader.read_pending_trainer_battle_identity = lambda: (212, 3)
    elif mismatch == "position":
        state.raw = replace(state.raw, player_x=35)
    elif mismatch == "facing":
        router.runtime.reader.read_player_facing = lambda: "up"
    result = funding.bind_local_trainer_funding(router, bindings, state)
    if mismatch == "pending_changed":
        router.runtime.reader.read_pending_trainer_battle_identity = lambda: None
        with pytest.raises(funding.RedTrainerFundingError, match="transition changed"):
            result.bindings[-1].execute()
    else:
        assert result is bindings
    assert not calls


@pytest.mark.parametrize("money", [200, 1059, None, -1])
def test_funding_is_unavailable_if_not_a_cash_shortage(monkeypatch, money):
    router, state, _, bindings, calls = fixture(monkeypatch)
    state.raw = replace(state.raw, player_money=money)
    assert funding.bind_local_trainer_funding(router, bindings, state) is bindings
    assert not calls


def test_explicit_cash_reserve_can_offer_income_before_ball_stock_is_low(monkeypatch):
    router, state, _, bindings, calls = fixture(monkeypatch)
    state.raw = replace(state.raw, player_money=200)
    router.trainer_funding_target_cash = 1000

    offered = funding.bind_local_trainer_funding(router, bindings, state)

    assert len(offered.bindings) == 2
    assert offered.bindings[-1].kind is GoalKind.RESUPPLY
    assert offered.bindings[-1].resource_quote.expected_income == 1050
    assert not calls


@pytest.mark.parametrize(
    "stock,cash,earn", [(5, 1, False), (4, 200, False), (4, 199, True), (0, 1, True)]
)
def test_exact_capture_reserve_controls_income_shortfall(monkeypatch, stock, cash, earn):
    from pokemon_red_completion.red_capture_readiness import CapturePreparationBudget

    router, state, _, bindings, calls = fixture(monkeypatch)
    router.capture_reserve = CapturePreparationBudget(ItemId.POKE_BALL, 1, 5)
    router.runtime.profile.providers[0].parameters["resource_choice_variants"] = True
    bag = ((int(ItemId.FULL_RESTORE), 4),) + (((4, stock),) if stock else ())
    state.raw = replace(state.raw, player_money=cash, bag_items=bag)
    offered = funding.bind_local_trainer_funding(router, bindings, state)
    assert (
        any(b.resource_quote and b.resource_quote.expected_income > 0 for b in offered.bindings)
        == earn
    )
    assert router.runtime.provider_for(GoalKind.RESUPPLY, router.actions).affordable_ball_purchase
    assert not calls


@pytest.mark.parametrize("change", ["fainted", "short-hp", "no-flags", "weak", "no-target"])
def test_unsafe_or_unreadable_opportunities_remain_unavailable(monkeypatch, change):
    router, state, _, bindings, calls = fixture(monkeypatch)
    if change == "fainted":
        state.raw = replace(state.raw, party_hp=(0,))
    if change == "short-hp":
        state.raw = replace(state.raw, party_hp=())
    if change == "no-flags":
        state.raw = replace(state.raw, event_flags=None)
    if change == "weak":
        state.party = replace(state.party, members=(replace(state.party.members[0], level=10),))
    if change == "no-target":
        monkeypatch.setattr(funding, "_candidates", lambda _: ())
    assert funding.bind_local_trainer_funding(router, bindings, state) is bindings
    assert not calls


@pytest.mark.parametrize("change", ["money", "party", "ledger", "location", "quote", "trainer"])
def test_changed_origin_or_cartridge_binding_stops_before_input(monkeypatch, change):
    router, state, target, bindings, calls = fixture(monkeypatch)
    bound = funding.bind_local_trainer_funding(router, bindings, state).bindings[1]
    if change == "money":
        state.raw = replace(state.raw, player_money=10)
    if change == "party":
        state.party = replace(state.party, members=())
    if change == "ledger":
        state.collection_observation = (28, 48)
    if change == "location":
        state.raw = replace(state.raw, player_x=19)
    if change == "quote":
        monkeypatch.setattr(funding, "trainer_party_quote", lambda *_: None)
    if change == "trainer":
        monkeypatch.setattr(
            funding, "trainer_sight_zones", lambda *_: (replace(target.trainer, trainer_set=3),)
        )
    with pytest.raises(funding.RedTrainerFundingError):
        bound.execute()
    assert not calls


@pytest.mark.parametrize("change", ["money", "bag", "ledger", "event", "hp", "quote", "report"])
def test_independent_verifier_rejects_unproved_reward_or_preservation(monkeypatch, change):
    router, state, _, bindings, _ = fixture(monkeypatch)
    bound = funding.bind_local_trainer_funding(router, bindings, state).bindings[1]
    report = bound.execute()
    if change == "money":
        state.raw = replace(state.raw, player_money=1058)
    if change == "bag":
        state.raw = replace(state.raw, bag_items=())
    if change == "ledger":
        state.collection_observation = (28, 48)
    if change == "event":
        state.raw = replace(state.raw, event_flags=bytes(320))
    if change == "hp":
        state.raw = replace(state.raw, party_hp=())
    if change == "quote":
        monkeypatch.setattr(funding, "trainer_party_quote", lambda *_: None)
    if change == "report":
        report = GoalExecutionReport(4, 40, {})
    assert bound.verify(report).status is GoalDecisionOutcome.FAILED


def test_existing_affordable_purchase_is_not_replaced(monkeypatch):
    router, state, _, bindings, calls = fixture(monkeypatch)
    purchase = replace(bindings.bindings[0], kind=GoalKind.RESUPPLY, binding_ref="purchase")
    existing = GoalBindingSet(
        (purchase.opportunity, bindings.opportunities[1]), (purchase, bindings.bindings[0])
    )
    assert funding.bind_local_trainer_funding(router, existing, state) is existing
    assert not calls


def test_checkpoint_funding_mode_is_explicit_and_old_headers_stay_legacy():
    import run_paired_red_bounded_player as runner

    assert runner._checkpoint_trainer_funding({"metadata": {}}) is False
    assert runner._checkpoint_trainer_funding({"metadata": {"trainer_funding": True}}) is True
    for bad in (1, "true", None, []):
        with pytest.raises(runner.PairedRedBoundedPlayerRunError):
            runner._checkpoint_trainer_funding({"metadata": {"trainer_funding": bad}})


def test_j_bound_six_member_party_remains_unavailable_for_trainer_funding(monkeypatch):
    router, state, _, bindings, _ = fixture(monkeypatch)
    # Set J trainer battle runner
    router.runtime.trainer_battle_runner = lambda *a, **k: None
    from pokemon_red_completion.red_learned_trainer import FROZEN_J_SHA256

    router.runtime.trainer_battle_model_sha256 = FROZEN_J_SHA256

    # Supported small party (size 1) receives trainer funding
    bound_small = funding.bind_local_trainer_funding(router, bindings, state)
    assert any(b.kind is GoalKind.RESUPPLY for b in bound_small.bindings)

    # 6-member party (like the main save) is rejected under J's 1-3 member limit
    six_party_members = tuple(
        PartyMemberObservation(
            slot=i + 1,
            species_id=28,
            level=66,
            hp=213,
            max_hp=213,
            status=StatusCondition.HEALTHY,
            moves=(MoveObservation(57, 10, 15),),
        )
        for i in range(6)
    )
    six_state = SimpleNamespace(
        raw=replace(
            state.raw,
            party_count=6,
            party_species_ids=(28,) * 6,
            party_hp=(213,) * 6,
        ),
        party=PartyObservation(six_party_members),
        input_ready=True,
        collection_observation=state.collection_observation,
    )
    bound_six = funding.bind_local_trainer_funding(router, bindings, six_state)
    assert bound_six is bindings
    assert not any(b.kind is GoalKind.RESUPPLY for b in bound_six.bindings)
    from pokemon_red_completion.red_learned_trainer import (
        FROZEN_K_SHA256,
        K_QUALIFICATION_SHA256,
    )

    router.runtime.trainer_battle_model_sha256 = FROZEN_K_SHA256
    assert funding.bind_local_trainer_funding(router, bindings, six_state) is bindings
    router.runtime.trainer_battle_qualification_sha256 = K_QUALIFICATION_SHA256
    qualified = funding.bind_local_trainer_funding(router, bindings, six_state)
    assert any(b.kind is GoalKind.RESUPPLY for b in qualified.bindings)


def recovery_fixture(monkeypatch, *, mock_restore=True):
    from types import MethodType

    from pokemon_red_completion.red_learned_trainer import (
        FROZEN_K_SHA256,
        K_QUALIFICATION_SHA256,
        FrozenTrainerBattler,
    )

    router, state, target, bindings, calls = fixture(monkeypatch)
    owner = object.__new__(FrozenTrainerBattler)
    owner.model_sha256 = FROZEN_K_SHA256
    owner.qualification_sha256 = K_QUALIFICATION_SHA256
    owner.run = MethodType(lambda *_a, **_k: None, owner)
    router.runtime.trainer_battle_runner = owner.run
    router.runtime.trainer_battle_model_sha256 = FROZEN_K_SHA256
    router.runtime.trainer_battle_qualification_sha256 = K_QUALIFICATION_SHA256
    router.runtime.trainer_funding_recovery = True
    router.runtime.trainer_funding_surf = False
    router.runtime.emulator.pressed_buttons = ()
    router.runtime.adapter.party_guard = SimpleNamespace(verify=lambda: None)
    state.party = PartyObservation(
        (state.party.members[0], replace(state.party.members[0], slot=2, level=21))
    )
    state.raw = replace(
        state.raw,
        party_count=2,
        party_species_ids=(28, 28),
        party_hp=(213, 213),
        party_max_hp=(213, 213),
        party_status=(0, 0),
        party_moves=((57, 0, 0, 0),) * 2,
        party_pp=((15, 0, 0, 0),) * 2,
    )

    def battle(_reader, _actions, **kwargs):
        assert kwargs["story_income_recovery"] is True
        kwargs["validate_target"]()
        calls.append("battle-faint")
        flags = bytearray(320)
        flags[141] = 4
        state.raw = replace(
            state.raw,
            player_money=1059,
            event_flags=bytes(flags),
            party_hp=(190, 0),
            party_pp=((14, 0, 0, 0),) * 2,
        )
        return TestReceipt()

    def restore(_router):
        assert state.raw.party_hp == (190, 0)
        calls.append("nurse")
        state.raw = replace(
            state.raw,
            map_id=int(MapId.CINNABAR_POKECENTER),
            player_y=3,
            player_x=3,
            party_hp=(213, 213),
            party_pp=((15, 0, 0, 0),) * 2,
        )
        return {"center_map_id": int(MapId.CINNABAR_POKECENTER), "whole_party_restore": True}

    monkeypatch.setattr(
        "pokemon_red_completion.red_trainer_funding_battle.run_prepared_trainer_funding", battle
    )
    if mock_restore:
        monkeypatch.setattr(funding, "_restore_funding_party", restore)
    return router, state, target, bindings, calls


def test_qualified_faint_income_requires_and_verifies_healed_return(monkeypatch):
    router, state, _, bindings, calls = recovery_fixture(monkeypatch)
    bound = funding.bind_local_trainer_funding(router, bindings, state).bindings[-1]
    report = bound.execute()
    assert calls[-2:] == ["battle-faint", "nurse"]
    assert report.evidence["whole_party_restore"] is True
    assert report.evidence["trainer_funding"]["payout"] == 1050
    assert bound.verify(report) == GoalVerification.succeeded()


@pytest.mark.parametrize("last_result", [0, 1, 2, None])
def test_verified_income_return_can_supersede_win_with_wild_flee(monkeypatch, last_result):
    router, state, _, bindings, _ = recovery_fixture(monkeypatch)
    bound = funding.bind_local_trainer_funding(router, bindings, state).bindings[-1]
    report = bound.execute()
    state.raw = replace(state.raw, battle_result=last_result)
    verified = bound.verify(report)
    assert (verified == GoalVerification.succeeded()) == (last_result in (0, 2))


def test_strict_income_does_not_accept_a_later_flee(monkeypatch):
    router, state, _, bindings, _ = fixture(monkeypatch)
    bound = funding.bind_local_trainer_funding(router, bindings, state).bindings[-1]
    report = bound.execute()
    state.raw = replace(state.raw, battle_result=2)
    assert bound.verify(report).status is GoalDecisionOutcome.FAILED


@pytest.mark.parametrize("change", ["flag", "actor", "model", "qualification"])
def test_recovery_change_rejected_before_any_input(monkeypatch, change):
    router, state, _, bindings, calls = recovery_fixture(monkeypatch)
    bound = funding.bind_local_trainer_funding(router, bindings, state).bindings[-1]
    if change == "flag":
        router.runtime.trainer_funding_recovery = False
    elif change == "actor":
        router.runtime.trainer_battle_runner = lambda *_a, **_k: None
    elif change == "model":
        router.runtime.trainer_battle_model_sha256 = "0" * 64
    else:
        router.runtime.trainer_battle_qualification_sha256 = "0" * 64
    with pytest.raises(funding.RedTrainerFundingError, match="changed before input"):
        bound.execute()
    assert not calls


def test_unqualified_recovery_never_offers_fainting_income(monkeypatch):
    router, state, _, bindings, calls = fixture(monkeypatch)
    router.runtime.trainer_funding_recovery = True
    assert funding.bind_local_trainer_funding(router, bindings, state) is bindings
    assert not calls


@pytest.mark.parametrize("change", ["defeat", "flee", "money", "event", "bag", "individual"])
def test_unproven_win_never_runs_recovery(monkeypatch, change):
    router, state, _, bindings, calls = recovery_fixture(monkeypatch)
    import pokemon_red_completion.red_trainer_funding_battle as battle_module

    original = battle_module.run_prepared_trainer_funding

    def bad_battle(*args, **kwargs):
        receipt = original(*args, **kwargs)
        changes = {
            "defeat": {"battle_result": 1},
            "flee": {"battle_result": 2},
            "money": {"player_money": 1060},
            "event": {"event_flags": bytes(320)},
            "bag": {"bag_items": ()},
        }
        if change == "individual":
            router.runtime.adapter.party_guard.verify = lambda: (_ for _ in ()).throw(
                ValueError("original individual changed")
            )
        else:
            state.raw = replace(state.raw, **changes[change])
        return receipt

    monkeypatch.setattr(battle_module, "run_prepared_trainer_funding", bad_battle)
    bound = funding.bind_local_trainer_funding(router, bindings, state).bindings[-1]
    with pytest.raises((funding.RedTrainerFundingError, ValueError)):
        bound.execute()
    assert "nurse" not in calls


@pytest.mark.parametrize(
    "change", ["hp", "status", "pp", "bag", "money", "event", "map", "position", "buttons"]
)
def test_recovery_verifier_independently_rejects_false_terminal(monkeypatch, change):
    router, state, _, bindings, _ = recovery_fixture(monkeypatch)
    bound = funding.bind_local_trainer_funding(router, bindings, state).bindings[-1]
    report = bound.execute()
    changes = {
        "hp": {"party_hp": (213, 0)},
        "status": {"party_status": (0, 8)},
        "pp": {"party_pp": ((14, 0, 0, 0),) * 2},
        "bag": {"bag_items": ()},
        "money": {"player_money": 1058},
        "event": {"event_flags": bytes(320)},
        "map": {"map_id": 22},
        "position": {"player_y": 4},
    }
    if change == "buttons":
        router.runtime.emulator.pressed_buttons = ("a",)
    else:
        state.raw = replace(state.raw, **changes[change])
    assert bound.verify(report).status is GoalDecisionOutcome.FAILED


def test_failed_return_cannot_be_a_successful_income_goal(monkeypatch):
    router, state, _, bindings, _ = recovery_fixture(monkeypatch)
    bound = funding.bind_local_trainer_funding(router, bindings, state).bindings[-1]

    def failed(_):
        raise funding.RedTrainerFundingError("no legal return")

    monkeypatch.setattr(funding, "_restore_funding_party", failed)
    with pytest.raises(funding.RedTrainerFundingError, match="no legal return"):
        bound.execute()
    assert state.raw.player_money == 1059  # Real win is retained, not reset or relabeled.
    assert bound.verify(GoalExecutionReport(0, 0, {})).status is GoalDecisionOutcome.FAILED


@pytest.mark.parametrize("failure", [None, "no-surf", "route", "nurse", "unrestored"])
@pytest.mark.parametrize("native_journal", [False, True])
def test_real_return_composition_uses_observed_surf_not_fainted_fly(
    monkeypatch, failure, native_journal
):
    from pokemon_red_completion.route_plan import RoutePlanningError

    router, state, _, _, calls = recovery_fixture(monkeypatch, mock_restore=False)
    state.raw = replace(
        state.raw,
        party_hp=(190, 0),
        party_moves=((57, 0, 0, 0), (19, 0, 0, 0)),
        party_pp=((14, 0, 0, 0), (14, 0, 0, 0)),
    )
    router.runtime.trainer_funding_surf = True
    router.runtime.reader.read_current_map_blocks = lambda: ()
    router.regional_trainer_funding = True
    router.runtime.reader.read_input_readiness = lambda: SimpleNamespace(ready=True)
    # This outdoor Surf fixture has no escapable interior or Dig holder.
    monkeypatch.setattr(
        "pokemon_red_completion.red_dig_recovery.plan_dig_escape", lambda *_: None
    )

    def capabilities(_memory, observed, *, allow_cut, allow_surf):
        assert observed is state.raw and allow_surf is True and allow_cut is True
        assert observed.party_hp[1] == 0 and observed.party_moves[1][0] == 19
        return frozenset() if failure == "no-surf" else frozenset({"move:surf"})

    monkeypatch.setattr(
        "pokemon_red_completion.red_resource_goal_router.collection_field_capabilities",
        capabilities,
    )

    class Traversal:
        def __init__(self, _reader, _projector, *, capability_projector):
            self.capabilities = capability_projector(state.raw)

        def observe(self):
            return SimpleNamespace(capabilities=self.capabilities)

    monkeypatch.setattr(funding, "Gen1TraversalObserver", Traversal)

    def plan(start, center, *, goal_at):
        assert goal_at == (3, 3)
        if center != int(MapId.CINNABAR_POKECENTER) or "move:surf" not in start.capabilities:
            raise RoutePlanningError("no live route")
        return SimpleNamespace(steps=("surf",), terminal_map=center)

    world = SimpleNamespace(rom=b"test", plan_feasible_to_map=plan)
    world.with_current_blocks = lambda _: world
    router.world = world

    class Transition:
        def __init__(self, **kwargs):
            assert kwargs["allow_surf"] is True
            assert kwargs["destination_map"] == int(MapId.CINNABAR_POKECENTER)

        def __call__(self, *_):
            calls.append("ground-surf")
            if failure == "route":
                raise RuntimeError("route blocked")
            state.raw = replace(
                state.raw, map_id=int(MapId.CINNABAR_POKECENTER), player_y=3, player_x=3
            )

    monkeypatch.setattr(
        "pokemon_red_completion.red_training_ground_route.RedVermilionGroundTransition", Transition
    )

    def nurse():
        calls.append("nurse")
        if failure != "unrestored":
            state.raw = replace(
                state.raw, party_hp=(213, 213), party_pp=((15, 0, 0, 0), (15, 0, 0, 0))
            )
        return GoalExecutionReport(1, 10, {"whole_party_restore": True})

    binding = SimpleNamespace(
        execute=nurse,
        verify=lambda _: (
            GoalVerification.failed(funding.GoalFailureReason.OUTCOME_NOT_VERIFIED)
            if failure == "nurse"
            else GoalVerification.succeeded()
        ),
    )
    monkeypatch.setattr(
        funding,
        "RedCenterRestoreGoalProvider",
        lambda *_a, **_k: SimpleNamespace(offer=lambda _: SimpleNamespace(binding=binding)),
    )
    if native_journal:

        def recorded_restore(actual):
            assert actual is binding
            calls.append("recorded-nurse")
            return actual.execute()

        router.actions.execute_restoration = recorded_restore
    if failure is None:
        result = funding._restore_funding_party(router)
        assert result["whole_party_restore"] is True
        assert calls == (
            ["ground-surf", "recorded-nurse", "nurse"]
            if native_journal
            else ["ground-surf", "nurse"]
        )
    else:
        with pytest.raises((funding.RedTrainerFundingError, RuntimeError)):
            funding._restore_funding_party(router)
        if failure == "no-surf":
            assert calls == []
        elif failure == "route":
            assert calls == ["ground-surf"]


@pytest.mark.parametrize(
    "case", ["direct", "dig", "no-escape", "escape-failed", "still-blocked", "nurse", "unrestored"]
)
def test_funding_return_uses_one_verified_escape_then_fresh_center_route(monkeypatch, case):
    from pokemon_red_completion.red_dig_recovery import RedDigRecoveryError
    from pokemon_red_completion.route_plan import RoutePlanningError

    router, state, _, _, calls = recovery_fixture(monkeypatch, mock_restore=False)
    state.raw = replace(
        state.raw,
        map_id=int(MapId.VICTORY_ROAD_2F), player_y=8, player_x=12,
        player_money=1078, party_hp=(190, 88),
        party_moves=((91, 0, 0, 0), (19, 0, 0, 0)),
        party_pp=((9, 0, 0, 0), (14, 0, 0, 0)),
    )
    original = state.raw
    reader = router.runtime.reader
    reader.read_current_map_blocks = lambda: state.raw.map_id
    reader.read_input_readiness = lambda: SimpleNamespace(ready=True)
    router.runtime.trainer_funding_surf = False
    router.regional_trainer_funding = True
    refreshes = []

    monkeypatch.setattr(
        "pokemon_red_completion.red_resource_goal_router.collection_field_capabilities",
        lambda *_a, **_k: frozenset(),
    )

    class Traversal:
        def __init__(self, _reader, _projector, **_kwargs):
            pass

        def observe(self):
            return SimpleNamespace(map_id=state.raw.map_id, at=(state.raw.player_y, state.raw.player_x))

    monkeypatch.setattr(funding, "Gen1TraversalObserver", Traversal)
    center = int(MapId.VIRIDIAN_POKECENTER)

    def plan(start, target, *, goal_at):
        assert goal_at == (3, 3)
        reachable = case == "direct" or (start.map_id == int(MapId.VIRIDIAN_CITY) and case != "still-blocked")
        if target != center or not reachable:
            raise RoutePlanningError("no walking return")
        return SimpleNamespace(steps=("walk",), terminal_map=center)

    world = SimpleNamespace(rom=b"test", plan_feasible_to_map=plan)

    def refresh(blocks):
        assert blocks == state.raw.map_id
        refreshes.append(blocks)
        return world

    world.with_current_blocks = refresh
    router.world = world
    quote = object()

    def escape_plan(actual_world, actual_reader, raw, start):
        assert actual_world is world and actual_reader is reader
        assert raw is state.raw and start.map_id == int(MapId.VICTORY_ROAD_2F)
        calls.append("escape-quoted")
        return None if case == "no-escape" else quote

    def escape(actual_world, actual_reader, emulator, actions, actual_plan):
        assert actual_world is world and actual_reader is reader and actual_plan is quote
        assert actions is router.actions and emulator is router.runtime.emulator
        calls.append("escape")
        if case == "escape-failed":
            raise RedDigRecoveryError("landing failed to verify")
        state.raw = replace(state.raw, map_id=int(MapId.VIRIDIAN_CITY), player_y=5, player_x=5)
        assert state.raw.player_money == original.player_money and state.raw.party_hp == original.party_hp
        return {"verified_escape": True, "anchor_map": int(MapId.VIRIDIAN_CITY)}

    monkeypatch.setattr("pokemon_red_completion.red_dig_recovery.plan_dig_escape", escape_plan)
    monkeypatch.setattr("pokemon_red_completion.red_dig_recovery.execute_dig_escape", escape)

    class Transition:
        def __init__(self, **kwargs):
            assert kwargs["destination_map"] == center and kwargs["allow_surf"] is False

        def __call__(self, *_):
            calls.append("walk")
            state.raw = replace(state.raw, map_id=center, player_y=3, player_x=3)

    monkeypatch.setattr("pokemon_red_completion.red_training_ground_route.RedVermilionGroundTransition", Transition)

    def nurse():
        calls.append("nurse")
        if case != "unrestored":
            state.raw = replace(
                state.raw, party_hp=(213, 213),
                party_pp=((10, 0, 0, 0), (15, 0, 0, 0)),
            )
        return GoalExecutionReport(1, 10, {"whole_party_restore": True})

    binding = SimpleNamespace(execute=nurse, verify=lambda _: (
        GoalVerification.failed(funding.GoalFailureReason.OUTCOME_NOT_VERIFIED)
        if case == "nurse" else GoalVerification.succeeded()
    ))
    monkeypatch.setattr(funding, "RedCenterRestoreGoalProvider", lambda *_a, **_k: SimpleNamespace(
        offer=lambda _: SimpleNamespace(binding=binding)))
    if case in {"direct", "dig"}:
        result = funding._restore_funding_party(router)
        assert result["whole_party_restore"] is True and state.raw.player_money == 1078
        assert state.raw.party_species_ids == original.party_species_ids
        if case == "direct":
            assert calls == ["walk", "nurse"] and "dig_escape" not in result
            assert refreshes == [int(MapId.VICTORY_ROAD_2F)]
        else:
            assert calls == ["escape-quoted", "escape", "walk", "nurse"]
            assert result["dig_escape"]["verified_escape"] is True
            assert refreshes == [int(MapId.VICTORY_ROAD_2F), int(MapId.VIRIDIAN_CITY)]
    else:
        with pytest.raises((funding.RedTrainerFundingError, RedDigRecoveryError)):
            funding._restore_funding_party(router)
        assert calls.count("escape") <= 1
        if case in {"no-escape", "escape-failed", "still-blocked"}:
            assert "nurse" not in calls and "walk" not in calls
        if case == "no-escape":
            assert state.raw is original
