from dataclasses import replace
from types import SimpleNamespace as N

import pytest
from test_red_player_story_battle import setup

from pokemon_red_completion import red_player_engaged_story as s
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.route_executor import RouteExecutionError, TraversalSnapshot


@pytest.mark.parametrize("objective", ("defeat_lorelei", "defeat_bruno", "defeat_agatha",
                                       "defeat_lance", "defeat_champion"))
@pytest.mark.parametrize("fault", (None, "absent", "different_room"))
def test_retained_league_uses_exact_existing_cartridge_contract(monkeypatch, objective, fault):
    from pokemon_red_completion import red_player_league_options as league

    contract = object()
    target = N(objective_id="other" if fault == "different_room" else objective)
    calls = []
    monkeypatch.setattr(league, "engaged_league_contract", lambda *a, **k: (
        calls.append((a, k)) or (None if fault == "absent" else (target, contract))))
    reader = N(read=lambda: N())
    assert s.engaged_story_contract(reader, b"rom", objective_id=objective) is (
        contract if fault is None else None)
    assert calls == [((reader, b"rom"), {"include_champion": True})]


@pytest.mark.parametrize("fault", [None, "unengaged", "wild", "no_context", "unknown",
                                  "defeated", "ambiguous", "scripted"])
def test_later_resource_transport_reuses_only_exact_engaged_ordinary_trainer(monkeypatch, fault):
    raw = N(map_id=23, battle_state=1 if fault == "wild" else 0, event_flags=bytes(320))
    identity = (231, 31, 2)
    calls = []
    reader = N(read=lambda: raw, trainer_engagement_active=lambda: fault != "unengaged",
               read_trainer_battle_identity=lambda: (0, 0, identity[0], identity[2]))
    runtime = N(reader=reader, adapter=N(observe=lambda: N(game_state=object()), graph=N(
        available_objectives=lambda _: () if fault == "no_context" else (N(id="reach_fuchsia"),))))
    zone = N(trainer_class=231, trainer_set=2, defeated=fault == "defeated")
    monkeypatch.setattr(s, "trainer_headers", lambda *a, **k: ())
    monkeypatch.setattr(s, "map_object_events", lambda *a, **k: ())
    monkeypatch.setattr(s, "static_trainer_sight_zones", lambda *a: (
        () if fault == "unknown" else (zone, zone) if fault == "ambiguous" else (zone,)))
    monkeypatch.setattr(s, "engaged_story_contract", lambda *a, **k: N(
        battle_plan_id="scripted" if fault == "scripted" else "retained-native-engagement"))
    expected = object()
    monkeypatch.setattr(s, "engaged_story_binding", lambda *a, **k: calls.append(k) or expected)
    if fault == "ambiguous":
        with pytest.raises(ValueError, match="one undefeated identity"):
            s.retained_ordinary_transport_binding(runtime, N(), rom=b"rom", battler="local")
    else:
        actual = s.retained_ordinary_transport_binding(runtime, N(), rom=b"rom", battler="local")
        assert actual is (expected if fault is None else None)
    assert len(calls) == int(fault is None)
    if calls:
        assert calls[0] == dict(rom=b"rom", battler="local", objective_id="reach_fuchsia")


def test_later_transport_live_battle_identity_and_closed_context_are_not_replaced(monkeypatch):
    raw = N(map_id=24, battle_state=2)
    read = []
    runtime = N(reader=N(read=lambda: raw, read_active_trainer_identity=lambda: (
        read.append("actual") or (231, 31, 2))), adapter=N(observe=lambda: N(game_state=object()),
        graph=N(available_objectives=lambda _: ())))
    assert s.retained_ordinary_transport_binding(runtime, N(), rom=b"rom", battler=N()) is None
    assert read == ["actual"]


@pytest.mark.parametrize("fault", [None, "wild", "unengaged", "defeated", "wrong_identity",
                                  "ambiguous", "league_room", "wrong_context"])
def test_league_frontier_transport_requires_unique_ordinary_sight_trainer(monkeypatch, fault):
    from pokemon_red_completion.observation import MapId

    raw=N(map_id=int(MapId.LORELEIS_ROOM) if fault == "league_room" else 177,
          battle_state=1 if fault == "wild" else 0,event_flags=bytes(320))
    reader=N(read=lambda:raw,trainer_engagement_active=lambda:fault != "unengaged",
             read_trainer_battle_identity=lambda:(0,0,224,5))
    zone=N(defeated=fault == "defeated",trainer_class=224,
           trainer_set=4 if fault == "wrong_identity" else 5,event_flag=853)
    monkeypatch.setattr(s,"trainer_headers",lambda *a,**k:())
    monkeypatch.setattr(s,"map_object_events",lambda *a,**k:())
    monkeypatch.setattr(s,"static_trainer_sight_zones",lambda *a:
        (zone,zone) if fault == "ambiguous" else (zone,))
    expected=object()
    monkeypatch.setattr(s.StoryTrainerContract,"from_cartridge",lambda *a,**k:
        expected if k["battle_plan_id"] == "retained-native-engagement"
        and k["objective_id"] == "defeat_lorelei" and k["defeated_event"] == 853 else
        pytest.fail("transport invented League credit"))
    kwargs=dict(objective_id="reach_fuchsia" if fault == "wrong_context" else "defeat_lorelei",
                ordinary_transport_context=True)
    if fault in {"defeated","wrong_identity","ambiguous","wrong_context"}:
        with pytest.raises(ValueError):
            s.engaged_story_contract(reader,b"rom",**kwargs)
    else:
        assert s.engaged_story_contract(reader,b"rom",**kwargs) is (
            expected if fault is None else None)


def test_ordinary_transport_passes_qualified_frontier_override_only_for_league(monkeypatch):
    raw=N(map_id=177,battle_state=0,badge_bits=255,event_flags=bytes(320))
    reader=N(read=lambda:raw,trainer_engagement_active=lambda:True,
             read_trainer_battle_identity=lambda:(0,0,224,5))
    rt=N(reader=reader,adapter=N(observe=lambda:N(game_state=object()),graph=N(
        available_objectives=lambda _: (N(id="defeat_lorelei"),))))
    zone=N(trainer_class=224,trainer_set=5,defeated=False)
    monkeypatch.setattr(s,"trainer_headers",lambda *a,**k:())
    monkeypatch.setattr(s,"map_object_events",lambda *a,**k:())
    monkeypatch.setattr(s,"static_trainer_sight_zones",lambda *a:(zone,))
    calls=[]
    monkeypatch.setattr(s,"engaged_story_contract",lambda *a,**k:
        calls.append(k) or N(battle_plan_id="retained-native-engagement"))
    expected=object()
    monkeypatch.setattr(s,"engaged_story_binding",lambda *a,**k:
        calls.append(k) or expected)
    assert s.retained_ordinary_transport_binding(rt,N(),rom=b"rom",battler="local") is expected
    assert calls[0] == dict(objective_id="defeat_lorelei",ordinary_transport_context=True)
    assert calls[1]["ordinary_transport_context"] is True


@pytest.mark.parametrize("fault", [None, "script", "position", "dialogue", "defeated"])
def test_retained_cerulean_rival_introduction_uses_native_script_not_generic_text(
    monkeypatch, fault
):
    from pokemon_red_completion import red_player_cerulean_rival as rival

    flags = bytearray(320)
    if fault == "defeated":
        flags[152 // 8] |= 1 << (152 % 8)
    raw = N(
        map_id=3,
        battle_state=0,
        player_y=7 if fault == "position" else 6,
        player_x=20,
        event_flags=bytes(flags),
    )
    reader = N(
        read=lambda: raw,
        read_bottom_dialogue_box_visible=lambda: fault != "dialogue",
        read_cascade_state=lambda _: N(local_script=0 if fault == "script" else 1),
        trainer_engagement_active=lambda: False,
    )
    calls = []
    monkeypatch.setattr(rival, "cerulean_rival_contract", lambda *a: calls.append(a) or "exact")
    assert s.engaged_story_contract(reader, b"rom", objective_id="help_bill") == (
        "exact" if fault is None else None
    )
    assert len(calls) == int(fault is None)


@pytest.mark.parametrize("wrong", [False, True])
def test_retained_cerulean_rival_live_party_identity_is_not_substituted(monkeypatch, wrong):
    from pokemon_red_completion import red_player_cerulean_rival as rival

    contract = N(trainer_identity=(225, 25, 8))
    reader = N(
        read=lambda: N(map_id=3, battle_state=2),
        read_active_trainer_identity=lambda: (225, 25, 7) if wrong else (225, 25, 8),
    )
    monkeypatch.setattr(rival, "cerulean_rival_contract", lambda *a: contract)
    if wrong:
        with pytest.raises(ValueError, match="rival identity differs"):
            s.engaged_story_contract(reader, b"rom", objective_id="help_bill")
    else:
        assert s.engaged_story_contract(reader, b"rom", objective_id="help_bill") is contract


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "boundary",
        "missing",
        "kind",
        "ref",
        "lost",
        "battle",
        "relocated",
        "input",
        "dialogue",
    ],
)
def test_learned_resource_trainer_reuses_exact_skill_and_preserves_setbacks(fault):
    raw = N(map_id=14, player_y=8, player_x=33, battle_state=2)
    calls = []
    reader = N(
        read=lambda: raw,
        read_input_readiness=lambda: N(ready=fault != "input"),
        read_bottom_dialogue_box_visible=lambda: fault == "dialogue",
    )

    def execute():
        calls.append("learned-battle")
        raw.battle_state = 2 if fault == "battle" else 0
        if fault == "relocated":
            raw.map_id = 58
        return GoalExecutionReport(
            5,
            120,
            {
                "battle": {
                    "outcome": "lost" if fault == "lost" else "won",
                }
            },
        )

    binding = ExecutableGoalBinding(
        "unknown" if fault == "ref" else "pokemon.red:retained-engagement:exact",
        GoalKind.ADVANCE_STORY if fault == "kind" else GoalKind.RECOVER_CONTROL,
        0.3,
        0.4,
        execute,
        lambda _: (
            GoalVerification.failed(GoalFailureReason.RESOURCE_LOST)
            if fault == "lost"
            else GoalVerification.succeeded()
        ),
    )
    inner = N(
        handle=lambda _: calls.append("legacy-battle"),
        handled_hazard_kinds=frozenset({"trainer_sight"}),
        handled_interruption_kinds=frozenset(
            {"trainer_engagement", "battle:2", "wild_battle", "scripted_dialogue"}
        ),
    )
    handler = s.EngagedStoryRouteHandler(
        inner, reader, lambda: None if fault == "missing" else binding, maximum_trainers=1
    )
    assert not calls and handler.handled_hazard_kinds == inner.handled_hazard_kinds
    assert handler.handled_interruption_kinds == inner.handled_interruption_kinds
    interruption = TraversalSnapshot(
        14, (9 if fault == "boundary" else 8, 33), False, interruption="battle:2"
    )
    if fault:
        with pytest.raises(RouteExecutionError):
            handler.handle(interruption)
        assert "legacy-battle" not in calls and len(calls) <= 1
        assert not handler.trainer_evidence
    else:
        receipt = handler.handle(interruption)
        assert receipt.resumed_at == (8, 33) and receipt.resumed_map == 14
        assert receipt.details["verified"] and receipt.details["learned_combat"]
        assert calls == ["learned-battle"] and handler.trainer_evidence == [receipt]
        with pytest.raises(RouteExecutionError, match="allowance"):
            handler.handle(interruption)
        assert calls == ["learned-battle"]


def test_learned_resource_trainer_does_not_change_existing_wild_handler():
    calls, sentinel = [], object()
    inner = N(handle=lambda i: calls.append(i.interruption) or sentinel)
    handler = s.EngagedStoryRouteHandler(
        inner, N(), lambda: pytest.fail("nontrainer event queried battle binding")
    )
    assert handler.handle(N(interruption="wild_battle")) is sentinel and calls == ["wild_battle"]


@pytest.mark.parametrize("fault", [None, "unverified", "wrong_reason", "schema", "won",
    "source", "terminal", "cash", "delta", "battle", "input", "dialogue", "counts",
    "objective", "reward"])
def test_only_verified_settled_native_blackout_becomes_typed_route_loss(fault):
    raw = N(map_id=35, player_y=8, player_x=33, battle_state=2, player_money=1891)
    evidence = dict(support="already_engaged_native_trainer", source_sha256="a" * 64,
        terminal_sha256="b" * 64, objective_completed=False, reward=None,
        battle=dict(schema="pokemon.red.learned-trainer-completion.v1", outcome="lost",
                    field_ready=True, money_delta=-946))
    if fault in {"schema", "won", "delta"}:
        key = {"schema": "schema", "won": "outcome", "delta": "money_delta"}[fault]
        evidence["battle"][key] = (
            "unknown" if fault == "schema" else "won" if fault == "won" else -945)
    if fault == "source":
        evidence["source_sha256"] = "c" * 64
    if fault == "terminal":
        evidence["terminal_sha256"] = "not-a-hash"
    if fault == "objective":
        evidence["objective_completed"] = True
    if fault == "reward":
        evidence["reward"] = {"earned": True}

    def execute():
        raw.map_id, raw.player_y, raw.player_x = 64, 3, 4
        raw.battle_state = 2 if fault == "battle" else 0
        raw.player_money = 944 if fault == "cash" else 945
        return GoalExecutionReport(0 if fault == "counts" else 12, 400, evidence)

    binding = ExecutableGoalBinding("pokemon.red:retained-engagement:" + "a" * 64,
        GoalKind.RECOVER_CONTROL, 0.3, 0.4, execute, lambda _: (
            GoalVerification.succeeded() if fault == "unverified" else GoalVerification.failed(
                GoalFailureReason.OUTCOME_NOT_VERIFIED if fault == "wrong_reason"
                else GoalFailureReason.RESOURCE_LOST)))
    handler = s.EngagedStoryRouteHandler(N(handle=lambda _: pytest.fail("fallback")),
        N(read=lambda: raw, read_input_readiness=lambda: N(ready=fault != "input"),
          read_bottom_dialogue_box_visible=lambda: fault == "dialogue"), lambda: binding)
    with pytest.raises(RouteExecutionError) as stopped:
        handler.handle(TraversalSnapshot(35, (8, 33), False, interruption="battle:2"))
    assert isinstance(stopped.value, s.SettledNativeTrainerLoss) is (fault is None)
    assert not handler.trainer_evidence and handler.verified_trainer_income == 0
    if fault is None:
        assert stopped.value.evidence["cash_before"] == 1891
        assert stopped.value.evidence["cash_after"] == 945
        assert s.settled_route_trainer_loss_evidence(stopped.value.evidence)


@pytest.mark.parametrize("maximum", [8, 9, 32])
def test_declared_long_transport_still_stops_at_exact_trainer_allowance(maximum):
    raw = N(map_id=23, player_y=40, player_x=9, battle_state=2)
    calls = []
    reader = N(
        read=lambda: raw,
        read_input_readiness=lambda: N(ready=True),
        read_bottom_dialogue_box_visible=lambda: False,
    )

    def execute():
        calls.append("native-win")
        raw.battle_state = 0
        return GoalExecutionReport(5, 120, {"battle": {"outcome": "won", "money_delta": 10}})

    def binding():
        return ExecutableGoalBinding(
            "pokemon.red:retained-engagement:" + str(len(calls)),
            GoalKind.RECOVER_CONTROL, 0.3, 0.4, execute,
            lambda _: GoalVerification.succeeded(),
        )

    handler = s.EngagedStoryRouteHandler(
        N(handle=lambda _: pytest.fail("legacy trainer fallback")),
        reader, binding, maximum_trainers=maximum,
    )
    interruption = TraversalSnapshot(23, (40, 9), False, interruption="battle:2")
    for _ in range(maximum):
        raw.battle_state = 2
        assert handler.handle(interruption).details["learned_combat"]
    assert len(calls) == maximum
    assert handler.verified_trainer_income == maximum * 10
    with pytest.raises(RouteExecutionError, match="allowance"):
        handler.handle(interruption)
    assert len(calls) == maximum


@pytest.mark.parametrize("maximum", [False, True, 0, -1, 33, 8.0, None, "32"])
def test_declared_transport_trainer_allowance_remains_finite_and_typed(maximum):
    with pytest.raises(ValueError, match="trainer allowance"):
        s.EngagedStoryRouteHandler(N(handle=lambda _: None), N(), lambda: None,
                                  maximum_trainers=maximum)


def test_historical_transport_default_remains_eight_trainers():
    handler = s.EngagedStoryRouteHandler(N(handle=lambda _: None), N(), lambda: None)
    assert handler.maximum_trainers == 8


@pytest.mark.parametrize("hp", [(30, 25), (0, 25), (30, 0)])
@pytest.mark.parametrize("pending", [False, True])
def test_learned_route_win_requests_recovery_before_resuming_with_fainted_reserves(hp, pending):
    """A native win is retained; an adjacent trainer keeps control until settled."""
    from pokemon_red_completion.goal_manager_runtime import GoalRecoveryRequired

    raw = N(map_id=143, player_y=7, player_x=7, battle_state=2,
            party_count=2, party_hp=(30, 25), player_money=100)
    waiting = [pending]
    calls = []

    def execute():
        calls.append("learned-combat")
        raw.battle_state, raw.party_hp = 0, hp
        raw.player_money += 10
        return GoalExecutionReport(5, 120, {
            "support": "already_engaged_native_trainer", "source_sha256": "a" * 64,
            "terminal_sha256": "b" * 64,
            "battle": {"schema": "pokemon.red.learned-trainer-completion.v1",
                       "outcome": "won", "money_delta": 10, "field_ready": True},
        })

    binding = ExecutableGoalBinding(
        "pokemon.red:retained-engagement:" + "a" * 64,
        GoalKind.RECOVER_CONTROL, 0.3, 0.4, execute, lambda _: GoalVerification.succeeded(),
    )
    handler = s.EngagedStoryRouteHandler(
        N(handle=lambda _: pytest.fail("transport continued before recovery")),
        N(read=lambda: raw, read_input_readiness=lambda: N(ready=True),
          read_bottom_dialogue_box_visible=lambda: False,
          trainer_engagement_active=lambda: waiting[0]),
        lambda: binding,
    )
    interruption = TraversalSnapshot(143, (7, 7), False, interruption="battle:2")
    if 0 in hp and not pending:
        with pytest.raises(GoalRecoveryRequired, match="verified trainer exit"):
            handler.handle(interruption)
    else:
        receipt = handler.handle(interruption)
        assert receipt.details.get("pending_interruption_kind") == (
            "trainer_engagement" if pending else None)
    assert calls == ["learned-combat"] and handler.verified_trainer_income == 10
    assert handler.trainer_evidence[0].details["battle"]["outcome"] == "won"
    if pending and 0 in hp:
        waiting[0] = False
        raw.battle_state = 2
        with pytest.raises(GoalRecoveryRequired, match="verified trainer exit"):
            handler.handle(interruption)
        assert calls == ["learned-combat", "learned-combat"]
        assert handler.verified_trainer_income == 20


@pytest.mark.parametrize("hp,count", [((0, 0), 2), ((0,), 2), ((-1, 20), 2)])
def test_trainer_recovery_does_not_admit_an_unproved_surviving_roster(hp, count):
    raw = N(map_id=143, player_y=7, player_x=7, battle_state=0,
            party_count=count, party_hp=hp, player_money=100)
    binding = ExecutableGoalBinding(
        "pokemon.red:retained-engagement:" + "a" * 64,
        GoalKind.RECOVER_CONTROL, 0.3, 0.4,
        lambda: GoalExecutionReport(5, 120, {"battle": {"outcome": "won"}}),
        lambda _: GoalVerification.succeeded(),
    )
    handler = s.EngagedStoryRouteHandler(
        N(handle=lambda _: pytest.fail("fallback")),
        N(read=lambda: raw, read_input_readiness=lambda: N(ready=True),
          read_bottom_dialogue_box_visible=lambda: False), lambda: binding,
    )
    with pytest.raises(RouteExecutionError, match="verified living field party"):
        handler.handle(TraversalSnapshot(143, (7, 7), False, interruption="battle:2"))


def test_unrecognized_scripted_dialogue_keeps_existing_text_handler_without_battle_inputs():
    calls, sentinel = [], object()
    raw = N(map_id=3, player_y=6, player_x=20, battle_state=0)
    inner = N(handle=lambda i: calls.append("ordinary-text") or sentinel)
    handler = s.EngagedStoryRouteHandler(
        inner,
        N(read=lambda: raw),
        lambda: calls.append("exact-contract-check") or None,
        maximum_trainers=1,
    )
    # Exhausting the trainer quota must not block unrelated text.
    handler.trainer_evidence.append(object())
    interruption = TraversalSnapshot(3, (6, 20), False, interruption="scripted_dialogue")
    assert handler.handle(interruption) is sentinel
    assert calls == ["exact-contract-check", "ordinary-text"]


@pytest.mark.parametrize("fault", [None, "lost", "kind", "ref", "boundary", "quota"])
def test_exact_scripted_trainer_introduction_uses_learned_engagement_not_text_dismissal(fault):
    raw = N(map_id=3, player_y=6, player_x=20, battle_state=0)
    calls = []
    reader = N(
        read=lambda: raw,
        read_input_readiness=lambda: N(ready=True),
        read_bottom_dialogue_box_visible=lambda: False,
    )
    binding = ExecutableGoalBinding(
        "wrong" if fault == "ref" else "pokemon.red:retained-engagement:scripted-rival",
        GoalKind.ADVANCE_STORY if fault == "kind" else GoalKind.RECOVER_CONTROL,
        0.3,
        0.4,
        lambda: (
            calls.append("learned-combat")
            or GoalExecutionReport(
                12, 400, {"battle": {"outcome": "lost" if fault == "lost" else "won"}}
            )
        ),
        lambda _: (
            GoalVerification.failed(GoalFailureReason.RESOURCE_LOST)
            if fault == "lost"
            else GoalVerification.succeeded()
        ),
    )
    handler = s.EngagedStoryRouteHandler(
        N(handle=lambda _: calls.append("ordinary-text")),
        reader,
        lambda: binding,
        maximum_trainers=1,
    )
    if fault == "quota":
        handler.trainer_evidence.append(object())
    interruption = TraversalSnapshot(
        3, (7 if fault == "boundary" else 6, 20), False, interruption="scripted_dialogue"
    )
    if fault is not None:
        with pytest.raises(RouteExecutionError):
            handler.handle(interruption)
        assert "ordinary-text" not in calls
        assert calls == (["learned-combat"] if fault == "lost" else [])
    else:
        receipt = handler.handle(interruption)
        assert receipt.kind == "trainer_engagement" and receipt.details["learned_combat"]
        assert calls == ["learned-combat"]


@pytest.mark.parametrize("undeclared", [False, True])
def test_retained_engagement_resolves_existing_declared_train_actor(
    tmp_path, monkeypatch, undeclared,
):
    from test_red_scoped_training_battlers import A, prototype

    from pokemon_red_completion.red_scoped_training_battlers import ScopedTrainingBattlers

    actor = prototype(tmp_path)
    actor.session.save_state_bytes = lambda: b"unchanged"
    pool = ScopedTrainingBattlers(actor, contracts=(A,), output=tmp_path / "pool",
                                 experiment_sha256="c" * 64)
    contract = replace(A, victory_money=1) if undeclared else A
    monkeypatch.setattr(s, "engaged_story_contract", lambda *a, **k: contract)
    runtime = N(adapter=N(observe=lambda: N(game_state=object()),
                          graph=N(available_objectives=lambda _: (N(id=A.objective_id),))),
                reader=object(), emulator=actor.session)
    if undeclared:
        with pytest.raises(ValueError, match="undeclared"):
            s.engaged_story_binding(runtime, N(), rom=b"rom", battler=pool,
                                   objective_id=A.objective_id)
    else:
        binding = s.engaged_story_binding(runtime, N(), rom=b"rom", battler=pool,
                                         objective_id=A.objective_id)
        assert binding.kind is GoalKind.RECOVER_CONTROL
    assert actor.session.frame_count == 0 and not pool.receipts


@pytest.mark.parametrize("limit", [0, 33, True, 1.5])
def test_learned_resource_trainer_limit_rejected_before_input(limit):
    with pytest.raises(ValueError, match="allowance"):
        s.EngagedStoryRouteHandler(N(handle=lambda _: None), N(), lambda: None, limit)


@pytest.mark.parametrize(
    "fault", [None, "not_opted_in", "no_champion", "no_hall", "other_objective"]
)
def test_postgame_recovery_requires_explicit_completed_story_and_retains_no_new_story_credit(
    monkeypatch,
    fault,
):
    rt, actions, route, raw, lesson, inputs, calls, contract, _ = setup(monkeypatch)
    before_objectives = tuple(lesson["completed_objectives"])
    rt.adapter.observe = lambda: N(game_state=object())
    rt.adapter.graph.available_objectives = lambda _: ()
    completed = {"defeat_champion", "enter_hall_of_fame"}
    if fault == "no_champion":
        completed.remove("defeat_champion")
    if fault == "no_hall":
        completed.remove("enter_hall_of_fame")
    rt.adapter.graph.completed_ids = lambda _: completed
    contract = replace(contract, objective_id="postgame_collection", victory_badge_bits=0)
    raw.map_id, raw.battle_state = contract.map_id, 2
    monkeypatch.setattr(s, "engaged_story_contract", lambda *a, **k: contract)
    from pokemon_red_completion import red_player_story_battle as old

    monkeypatch.setattr(s, "FrozenStoryBattleController", old.FrozenStoryBattleController)
    monkeypatch.setattr(s, "_field_ready", lambda _: True)
    binding = s.engaged_story_binding(
        rt,
        actions,
        rom=route.rom,
        battler=object(),
        objective_id="rescue_fuji" if fault == "other_objective" else "postgame_collection",
        allow_postgame_collection=fault != "not_opted_in",
    )
    assert not inputs and not calls
    if fault is not None:
        assert binding is None
    else:
        report = binding.execute()
        assert len(calls) == 1 and not report.evidence["objective_completed"]
        assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
        assert tuple(lesson["completed_objectives"]) == before_objectives


@pytest.mark.parametrize("battle", [False, True])
def test_nugget_script_uses_existing_exact_contract_before_and_during_combat(monkeypatch, battle):
    from pokemon_red_completion import red_scripted_story_trainer as scripted

    raw = N(map_id=35, battle_state=2 if battle else 0)
    reader = N(read=lambda: raw, read_active_trainer_identity=lambda: (230, 30, 6))
    expected = object()
    monkeypatch.setattr(scripted, "nugget_rocket_contract", lambda *a: expected)
    monkeypatch.setattr(scripted, "nugget_rocket_introduction_contract", lambda *a: expected)
    assert s.engaged_story_contract(reader, b"rom", objective_id="help_bill") is expected


@pytest.mark.parametrize("wrong", [False, True])
def test_retained_route22_uses_decoded_script_and_exact_live_identity(monkeypatch, wrong):
    from pokemon_red_completion import red_player_route22_rival as rival

    raw = N(map_id=33, battle_state=2)
    contract = N(trainer_identity=(242, 42, 11))
    reader = N(
        read=lambda: raw,
        read_active_trainer_identity=lambda: (242, 42, 12) if wrong else contract.trainer_identity,
    )
    calls = []
    monkeypatch.setattr(rival, "route22_rival_contract", lambda *a: calls.append(a) or contract)
    if wrong:
        with pytest.raises(ValueError, match="rival identity differs"):
            s.engaged_story_contract(reader, b"rom", objective_id="cross_victory_road")
    else:
        assert (
            s.engaged_story_contract(reader, b"rom", objective_id="cross_victory_road") is contract
        )
    assert len(calls) == 1


@pytest.mark.parametrize("fault", [None, "position", "dialogue", "defeated"])
def test_tower_trigger_dialogue_is_owned_before_trainer_identity_is_armed(monkeypatch, fault):
    from pokemon_red_completion import red_scripted_story_trainer as scripted

    flags = bytearray(320)
    if fault == "defeated":
        flags[239 // 8] |= 1 << (239 % 8)
    raw = N(
        map_id=143,
        battle_state=0,
        player_y=7 if fault == "position" else 6,
        player_x=14,
        event_flags=bytes(flags),
    )
    reader = N(
        read=lambda: raw,
        trainer_engagement_active=lambda: False,
        read_bottom_dialogue_box_visible=lambda: fault != "dialogue",
    )
    monkeypatch.setattr(scripted, "tower_rival_contract", lambda *a: "exact-rival")
    assert s.engaged_story_contract(reader, b"rom", objective_id="rescue_fuji") == (
        "exact-rival" if fault is None else None
    )


@pytest.mark.parametrize("fault", [None, "wrong_identity", "defeated", "unengaged"])
def test_retained_giovanni_uses_existing_exact_scripted_contract(monkeypatch, fault):
    from pokemon_red_completion import red_silph_continuation as silph

    flags = bytearray(320)
    if fault == "defeated":
        flags[1935 // 8] |= 1 << (1935 % 8)
    raw = N(map_id=235, battle_state=0 if fault == "unengaged" else 2, event_flags=bytes(flags))
    reader = N(
        read=lambda: raw,
        trainer_engagement_active=lambda: False,
        read_active_trainer_identity=lambda: (
            (229, 29, 1) if fault == "wrong_identity" else (229, 29, 2)
        ),
    )
    calls = []
    monkeypatch.setattr(
        silph, "silph_continuation_contract", lambda *a: calls.append(a) or "exact-giovanni"
    )
    monkeypatch.setattr(s, "trainer_headers", lambda *a, **k: ())
    monkeypatch.setattr(s, "map_object_events", lambda *a, **k: ())
    monkeypatch.setattr(s, "static_trainer_sight_zones", lambda *a: ())
    if fault in {"wrong_identity", "defeated"}:
        with pytest.raises(ValueError, match="one undefeated"):
            s.engaged_story_contract(reader, b"rom", objective_id="liberate_silph")
        assert not calls
    else:
        assert s.engaged_story_contract(reader, b"rom", objective_id="liberate_silph") == (
            None if fault == "unengaged" else "exact-giovanni"
        )
        assert len(calls) == (fault is None)


@pytest.mark.parametrize("lost", [False, True])
def test_retained_engagement_uses_learned_battle_without_story_credit(monkeypatch, lost):
    rt, actions, route, raw, lesson, inputs, calls, contract, target = setup(monkeypatch, lost=lost)
    rt.adapter.observe = lambda: N(game_state=object())
    raw.map_id = contract.map_id
    from pokemon_red_completion import red_player_story_battle as old

    monkeypatch.setattr(s, "engaged_story_contract", lambda *a, **k: contract)
    monkeypatch.setattr(s, "FrozenStoryBattleController", old.FrozenStoryBattleController)
    monkeypatch.setattr(s, "_field_ready", lambda _: True)
    binding = s.engaged_story_binding(
        rt, actions, rom=route.rom, battler=object(), objective_id="defeat_brock"
    )
    assert not inputs and not calls
    report = binding.execute()
    assert len(calls) == 1 and not report.evidence["objective_completed"]
    assert "defeat_brock" not in lesson["completed_objectives"]
    result = binding.verify(report)
    if lost:
        assert result.failure_reason is GoalFailureReason.RESOURCE_LOST
    else:
        assert result.status is GoalDecisionOutcome.SUCCEEDED
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()


@pytest.mark.parametrize("fault", [None, "unavailable", "backwards", "unrelated",
                                  "different_room", "absent", "not_opted_in"])
@pytest.mark.parametrize("lost", [False, True])
def test_retained_league_retry_uses_unfinished_progress_without_claiming_later_win(
    monkeypatch, fault, lost,
):
    from pokemon_red_completion import red_player_league_options as league
    from pokemon_red_completion import red_player_story_battle as old

    rt, actions, route, raw, lesson, inputs, calls, contract, _ = setup(monkeypatch, lost=lost)
    contract = replace(contract, objective_id="defeat_lance", battle_plan_id="retained-lance",
                       victory_badge_bits=0)
    raw.map_id, raw.battle_state = contract.map_id, 2
    rt.adapter.observe = lambda: N(game_state=object())
    progress = {"backwards": "defeat_bruno", "unrelated": "help_bill"}.get(
        fault, "defeat_champion")
    rt.adapter.graph.available_objectives = lambda _: (
        () if fault == "unavailable" else (N(id=progress),))
    target = next(t for t in league.LEAGUE_PLAYER_TARGETS if t.objective_id == (
        "defeat_agatha" if fault == "different_room" else "defeat_lance"))
    monkeypatch.setattr(league, "engaged_league_contract", lambda *a, **k: (
        None if fault == "absent" else (target, contract)))
    monkeypatch.setattr(s, "engaged_story_contract", lambda *a, **k: contract)
    monkeypatch.setattr(s, "FrozenStoryBattleController", old.FrozenStoryBattleController)
    monkeypatch.setattr(s, "_field_ready", lambda _: True)
    before = tuple(lesson["completed_objectives"])
    binding = s.engaged_story_binding(
        rt, actions, rom=route.rom, battler=object(), objective_id="defeat_lance",
        progress_objective_ref=None if fault == "not_opted_in" else progress,
    )
    assert not inputs and not calls
    if fault is not None:
        assert binding is None
        return
    assert binding.kind is GoalKind.RECOVER_CONTROL
    report = binding.execute()
    assert len(calls) == 1 and not report.evidence["objective_completed"]
    assert report.evidence["progress_objective"] == "defeat_champion"
    assert report.evidence["native_prerequisite"] == "defeat_lance"
    assert tuple(lesson["completed_objectives"]) == before
    assert binding.verify(report).status is (
        GoalDecisionOutcome.FAILED if lost else GoalDecisionOutcome.SUCCEEDED)


@pytest.mark.parametrize("mode", ["battle", "introduction", "wrong", "none"])
def test_retained_sabrina_contract_is_exact_before_inputs(monkeypatch, mode):
    from pokemon_red_completion import red_sabrina_continuation as sabrina

    raw = N(
        map_id=178, battle_state=2 if mode in {"battle", "wrong"} else 0, event_flags=bytes(320)
    )
    reader = N(
        read=lambda: raw,
        read_active_trainer_identity=lambda: (240, 40, 2) if mode == "wrong" else (240, 40, 1),
        read_trainer_battle_identity=lambda: (0, 0, 240, 1),
        trainer_engagement_active=lambda: mode != "none",
    )
    calls = []
    monkeypatch.setattr(sabrina, "sabrina_contract", lambda *a: calls.append(a) or "sabrina")
    monkeypatch.setattr(s, "trainer_headers", lambda *a, **k: ())
    monkeypatch.setattr(s, "map_object_events", lambda *a, **k: ())
    monkeypatch.setattr(s, "static_trainer_sight_zones", lambda *a: ())
    if mode == "wrong":
        with pytest.raises(ValueError, match="one undefeated"):
            s.engaged_story_contract(reader, b"rom", objective_id="defeat_sabrina")
        assert not calls
    else:
        assert s.engaged_story_contract(reader, b"rom", objective_id="defeat_sabrina") == (
            None if mode == "none" else "sabrina"
        )


@pytest.mark.parametrize("mode", ["field", "battle", "none", "ambiguous", "defeated"])
@pytest.mark.parametrize("map_id,objective_id", [
    (14, "reach_cerulean"), (23, "postgame_collection"),
])
def test_contract_requires_native_engagement_and_unique_live_identity(
    monkeypatch, mode, map_id, objective_id,
):
    raw = N(map_id=map_id, battle_state=2 if mode == "battle" else 0, event_flags=bytes(128))
    reader = N(
        read=lambda: raw,
        trainer_engagement_active=lambda: mode != "none",
        read_trainer_battle_identity=lambda: (0, 0, 202, 4),
        read_active_trainer_identity=lambda: (202, 2, 4),
    )
    zone = N(trainer_class=202, trainer_set=4, event_flag=994, defeated=mode == "defeated")
    monkeypatch.setattr(s, "trainer_headers", lambda *a, **k: ())
    monkeypatch.setattr(s, "map_object_events", lambda *a, **k: ())
    monkeypatch.setattr(
        s, "static_trainer_sight_zones", lambda *a: (zone, zone) if mode == "ambiguous" else (zone,)
    )
    monkeypatch.setattr(s.StoryTrainerContract, "from_cartridge", lambda *a, **k: k)
    if mode in {"ambiguous", "defeated"}:
        with pytest.raises(ValueError, match="one undefeated"):
            s.engaged_story_contract(reader, b"rom", objective_id=objective_id)
    else:
        result = s.engaged_story_contract(reader, b"rom", objective_id=objective_id)
        assert (result is None) == (mode == "none")
        if result is not None:
            assert result["map_id"] == map_id and result["objective_id"] == objective_id


@pytest.mark.parametrize("mode", ["battle", "introduction", "wrong", "none", "wrong_map"])
@pytest.mark.parametrize("leader", ["brock", "misty", "surge", "koga", "blaine", "giovanni"])
def test_retained_gym_contract_requires_exact_native_leader(monkeypatch, mode, leader):
    from pokemon_red_completion.red_gym_reward import GymReward

    trainer_class, map_id = {
        "brock": (234, int(s.MapId.PEWTER_GYM)),
        "misty": (235, int(s.MapId.CERULEAN_GYM)),
        "surge": (236, int(s.MapId.VERMILION_GYM)),
        "koga": (238, int(s.MapId.FUCHSIA_GYM)),
        "blaine": (239, int(s.MapId.CINNABAR_GYM)),
        "giovanni": (229, int(s.MapId.VIRIDIAN_GYM)),
    }[leader]
    trainer_set = 3 if leader == "giovanni" else 1
    raw = N(
        map_id=182 if mode == "wrong_map" else map_id,
        battle_state=2 if mode in {"battle", "wrong", "wrong_map"} else 0,
        event_flags=bytes(320),
    )
    reader = N(
        read=lambda: raw,
        read_active_trainer_identity=lambda: (
            trainer_class,
            trainer_class - 200,
            2 if mode == "wrong" else trainer_set,
        ),
        read_trainer_battle_identity=lambda: (0, 0, trainer_class, trainer_set),
        trainer_engagement_active=lambda: mode != "none",
    )
    calls = []
    monkeypatch.setattr(GymReward, "contract", lambda *a: calls.append(a) or "exact-leader")
    monkeypatch.setattr(s, "trainer_headers", lambda *a, **k: ())
    monkeypatch.setattr(s, "map_object_events", lambda *a, **k: ())
    monkeypatch.setattr(s, "static_trainer_sight_zones", lambda *a: ())
    if mode in {"wrong", "wrong_map"}:
        with pytest.raises(ValueError, match="one undefeated"):
            s.engaged_story_contract(reader, b"rom", objective_id=f"defeat_{leader}")
        assert not calls
    else:
        assert s.engaged_story_contract(reader, b"rom", objective_id=f"defeat_{leader}") == (
            None if mode == "none" else "exact-leader"
        )


@pytest.mark.parametrize("mode", ["battle", "introduction", "ordinary", "none"])
def test_erika_retained_contract_uses_exact_leader_identity_without_sight_headers(
    monkeypatch, mode
):
    from pokemon_red_completion.red_gym_reward import GymReward

    raw = N(
        map_id=134, battle_state=2 if mode in {"battle", "ordinary"} else 0, event_flags=bytes(320)
    )
    identity = (202, 2, 4) if mode == "ordinary" else (237, 37, 1)
    reader = N(
        read=lambda: raw,
        read_active_trainer_identity=lambda: identity,
        read_trainer_battle_identity=lambda: (0, 0, 237, 1),
        trainer_engagement_active=lambda: mode != "none",
    )
    expected = object()
    monkeypatch.setattr(GymReward, "contract", lambda *a: expected)
    monkeypatch.setattr(s, "trainer_headers", lambda *a, **k: ())
    monkeypatch.setattr(s, "map_object_events", lambda *a, **k: ())
    monkeypatch.setattr(s, "static_trainer_sight_zones", lambda *a: ())
    if mode == "ordinary":
        with pytest.raises(ValueError, match="one undefeated"):
            s.engaged_story_contract(reader, b"rom", objective_id="defeat_erika")
    else:
        actual = s.engaged_story_contract(reader, b"rom", objective_id="defeat_erika")
        assert actual is (None if mode == "none" else expected)


@pytest.mark.parametrize("lost,settlement_error", [(False, False), (True, False), (False, True)])
@pytest.mark.parametrize("leader", [
    "brock", "misty", "surge", "erika", "sabrina", "koga", "blaine", "giovanni",
])
def test_retained_leader_settles_reward_before_latching_story_completion(
    monkeypatch, lost, settlement_error, leader
):
    from dataclasses import replace

    from pokemon_red_completion import red_player_story_battle as old
    from pokemon_red_completion.red_gym_reward import GymReward

    rt, actions, route, raw, lesson, inputs, calls, contract, _ = setup(monkeypatch, lost=lost)
    name = "defeat_" + leader
    contract = replace(
        contract, objective_id=name, battle_plan_id="sabrina" if leader == "sabrina" else name
    )
    rt.adapter.observe = lambda: N(game_state=object())
    objective = N(id=name, completion_facts=frozenset({"badge:" + leader}))
    rt.adapter.graph.available_objectives = lambda _: (objective,)
    rt.adapter.graph.objective = lambda _: objective
    latched, rewards = [], []
    rt.observer.latch_verified_facts = lambda facts: latched.append(facts)
    raw.map_id, raw.battle_state = contract.map_id, 2
    monkeypatch.setattr(s, "engaged_story_contract", lambda *a, **k: contract)
    monkeypatch.setattr(GymReward, "contract", lambda *a: contract)
    from pokemon_red_completion import red_sabrina_continuation as sabrina

    monkeypatch.setattr(sabrina, "sabrina_contract", lambda *a: contract)
    monkeypatch.setattr(s, "FrozenStoryBattleController", old.FrozenStoryBattleController)
    monkeypatch.setattr(s, "_field_ready", lambda _: True)

    def settle(self, reader, port, *, before, victory_money):
        assert not latched
        rewards.append(victory_money)
        if settlement_error:
            raise RuntimeError("unverified native reward")
        return dict(badge=self.badge, item=self.item)

    monkeypatch.setattr(GymReward, "settle", settle)
    binding = s.engaged_story_binding(
        rt, actions, rom=route.rom, battler=object(), objective_id=name
    )
    assert not rewards and not latched and not inputs and not calls
    if settlement_error:
        with pytest.raises(RuntimeError, match="unverified native reward"):
            binding.execute()
        assert not latched and rewards == [1386]
        return
    report = binding.execute()
    assert report.evidence["objective_completed"] is (not lost)
    assert rewards == ([] if lost else [1386])
    assert latched == ([] if lost else [objective.completion_facts])
    assert binding.verify(report).status is (
        GoalDecisionOutcome.FAILED if lost else GoalDecisionOutcome.SUCCEEDED
    )


def test_travel_stops_before_unobserved_next_map_trainers(monkeypatch):
    from test_red_player_story_travel import setup as travel_setup

    from pokemon_red_completion import red_player_story_travel as travel

    rt, actions, route, raw, lesson = travel_setup(monkeypatch)
    plan = N(
        terminal_map=2,
        terminal_at=(35, 18),
        cost=200,
        steps=(
            N(expected_map=41, expected_at=(7, 3)),
            N(expected_map=1, expected_at=(4, 8)),
            N(expected_map=2, expected_at=(35, 18)),
        ),
    )
    monkeypatch.setattr(
        type(route), "route_world", property(lambda _: N(plan_feasible_to_map=lambda *a: plan))
    )
    binding = travel.story_travel_binding(
        rt, actions, objective_id="reach_pewter", route=route, stop_at_map_boundary=True
    )
    report = binding.execute()
    assert raw.map_id == 1 and not report.evidence["objective_completed"]
    assert lesson["completed_objectives"] == ["receive_pokedex"]
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
