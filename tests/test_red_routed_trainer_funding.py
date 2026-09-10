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
        reader=reader,
        emulator=emulator,
        adapter=SimpleNamespace(observe=lambda: state),
        provider_for=lambda *_: provider,
        profile=SimpleNamespace(providers=(SimpleNamespace(kind=GoalKind.RESUPPLY),)),
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
    revised = replace(target, approach=SimpleNamespace(
        steps=("observed-safe-step",), terminal_at=(10, 36)))
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
    monkeypatch.setattr(funding, 'trainer_sight_zones', lambda *_: (trainer,))
    calls = []

    def quote(rom, trainer_class, trainer_set, **kwargs):
        calls.append((rom, trainer_class, trainer_set, kwargs))
        return target.quote

    monkeypatch.setattr(funding, 'trainer_party_quote', quote)
    result = funding.active_trainer_funding_candidate(b'test', reader)
    assert result.trainer == trainer
    assert calls == [(b'test', 247, 1, {'allow_final_class': True})]


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
