from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_wild_recovery as w
from pokemon_red_completion.goal_manager import GoalDecisionOutcome


@pytest.mark.parametrize("species,map_id", [(74,162),(75,83),(73,194),(131,227)])
def test_native_one_off_is_never_offered_ordinary_run(monkeypatch,species,map_id):
    from pokemon_red_completion import red_static_capture
    target=N(internal_species=species,map_id=map_id)
    raw=N(battle_state=1,map_id=map_id,party_hp=(100,))
    reader=N(read=lambda:raw,read_wild_capture_identity=lambda:N(original_species_id=species))
    monkeypatch.setattr(red_static_capture,"red_static_capture_targets",lambda _:(target,))
    monkeypatch.setattr(w,"flee_wild",lambda *a,**k:pytest.fail("unique encounter must not flee"))
    assert w.retained_native_static_target(reader,b"fixture") is target
    with pytest.raises(ValueError,match="retained capture allocation"):
        w.interrupted_wild_binding(N(reader=reader),N(actions_executed=0),rom=b"fixture",
                                  allow_fainted_active=True)


def test_one_off_map_unknown_identity_cannot_authorize_run(monkeypatch):
    from pokemon_red_completion import red_static_capture
    monkeypatch.setattr(red_static_capture,"red_static_capture_targets",
                        lambda _:(N(internal_species=131,map_id=227),))
    reader=N(read=lambda:N(battle_state=1,map_id=227),read_wild_capture_identity=lambda:None)
    with pytest.raises(ValueError,match="lacks wild identity"):
        w.retained_native_static_target(reader,b"fixture")
    reader.read_wild_capture_identity=lambda:N(original_species_id=85)
    assert w.retained_native_static_target(reader,b"fixture") is None


@pytest.mark.parametrize("species", (131, 141))
def test_fainted_retained_identity_still_protects_mewtwo(monkeypatch, species):
    from pokemon_red_completion import red_static_capture
    target = N(internal_species=131, map_id=227)
    monkeypatch.setattr(red_static_capture, "red_static_capture_targets", lambda _: (target,))
    reader = N(read=lambda: N(battle_state=1, map_id=227),
               read_wild_capture_identity=lambda: None,
               read_retained_wild_identity=lambda: N(original_species_id=species))
    assert w.retained_native_static_target(reader, b"fixture") is (
        target if species == 131 else None
    )


@pytest.mark.parametrize("active_hp", [0, 10])
@pytest.mark.parametrize("opt_in", [False, True])
def test_fainted_active_reuses_whole_party_escape_only_when_declared(
    monkeypatch, active_hp, opt_in
):
    from pokemon_red_completion import wild_party_flee

    raw = N(battle_state=1, party_hp=(42, 0), battler_hp=active_hp,
        map_id=161, player_money=14513, bag_items=((3, 10),),
        event_flags=b"events", badge_bits=255)
    state, called = [b"source"], []
    rt = N(reader=N(read=lambda: raw), emulator=N(frame_count=0,
        save_state_bytes=lambda: state[0]))
    actions = N(actions_executed=0)
    monkeypatch.setattr(w, "_field_ready", lambda _: raw.battle_state == 0)

    def escape(label, *args, **kwargs):
        assert args[2] is raw and kwargs["expected_map_id"] == 161
        called.append(label)
        if label == "whole-party":
            assert kwargs["allow_new_faints"] and kwargs["allow_status_changes"]
            assert kwargs["emulator"] is rt.emulator
        raw.battle_state = 0
        state[0] = b"terminal"
        return N(verified=True, public_dict=lambda: dict(verified=True))

    monkeypatch.setattr(w, "flee_wild", lambda *a, **kw: escape("historical", *a, **kw))
    monkeypatch.setattr(wild_party_flee, "flee_with_fainted_lead",
        lambda *a, **kw: escape("whole-party", *a, **kw))
    binding = w.interrupted_wild_binding(rt, actions, allow_fainted_active=opt_in)
    report = binding.execute()
    assert called == ["whole-party" if opt_in else "historical"]
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED


@pytest.mark.parametrize("flag", [1, None, "yes"])
def test_fainted_active_escape_rejects_non_boolean(flag):
    with pytest.raises(TypeError):
        w.interrupted_wild_binding(N(), N(), allow_fainted_active=flag)


def test_fainted_active_escape_cannot_consume_a_static_source():
    with pytest.raises(ValueError, match="ordinary"):
        w.interrupted_wild_binding(N(), N(), allow_fainted_active=True,
            consumed_static_target=object())


@pytest.mark.parametrize(
    "fault",
    [None, "living_reserve", "trainer", "fainted", "stale", "cash", "bag", "event", "unsettled"],
)
def test_interrupted_wild_uses_existing_escape_and_verifies_state(monkeypatch, fault):
    raw = N(
        battle_state=1,
        party_hp=(10,),
        map_id=15,
        player_money=501,
        bag_items=((4, 5),),
        event_flags=b"events",
        badge_bits=1,
    )
    state = [b"source"]
    rt = N(reader=N(read=lambda: raw), emulator=N(frame_count=0, save_state_bytes=lambda: state[0]))
    actions = N(actions_executed=0)
    monkeypatch.setattr(w, "_field_ready", lambda _: raw.battle_state == 0 and fault != "unsettled")

    def flee(*args, **kwargs):
        assert kwargs["expected_map_id"] == 15
        rt.reader.read = lambda: N(
            **(
                vars(raw)
                | {
                    "battle_state": 0,
                    "player_money": 500 if fault == "cash" else 501,
                    "bag_items": () if fault == "bag" else raw.bag_items,
                    "event_flags": b"changed" if fault == "event" else raw.event_flags,
                }
            )
        )
        raw.battle_state = 0
        actions.actions_executed = 3
        rt.emulator.frame_count = 200
        state[0] = b"terminal"
        return N(verified=True, public_dict=lambda: {"verified": True})

    monkeypatch.setattr(w, "flee_wild", flee)
    if fault == "living_reserve":
        raw.party_hp = (0, 42)
    if fault in {"trainer", "fainted"}:
        if fault == "trainer":
            raw.battle_state = 2
        else:
            raw.party_hp = (0,)
        assert w.interrupted_wild_binding(rt, actions) is None
        return
    binding = w.interrupted_wild_binding(rt, actions)
    if fault == "stale":
        state[0] = b"changed"
    if fault and fault != "living_reserve":
        with pytest.raises(ValueError):
            binding.execute()
    else:
        report = binding.execute()
        assert report.actions_executed == 3 and report.frames_executed == 200
        assert report.evidence["model_queries"] == 0
        assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
        with pytest.raises(ValueError, match="consumed"):
            binding.execute()


@pytest.mark.parametrize("fault", [None, "lost", "absent", "not_pending", "wrong_ref",
    "wrong_kind", "factory_mutation", "unsettled", "unverified", "wrong_source",
    "wrong_terminal", "not_native", "false_lost", "wrong_action_cost", "wrong_frame_cost",
    "resource_before"])
def test_escape_chains_only_exact_already_triggered_trainer(monkeypatch, fault):
    from hashlib import sha256

    from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind
    from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport, GoalVerification

    raw = N(battle_state=1, party_hp=(42,), map_id=23, player_y=3, player_x=4,
        player_money=500, bag_items=((4, 5),), event_flags=b"events", badge_bits=1)
    state, ready, calls = [b"wild"], [False], []
    em = N(frame_count=0, save_state_bytes=lambda: state[0])
    rt = N(reader=N(read=lambda: N(**vars(raw)),
        trainer_engagement_active=lambda: fault != "not_pending"),
        emulator=em)
    actions = N(actions_executed=0)
    monkeypatch.setattr(w, "_field_ready", lambda _: ready[0])
    monkeypatch.setattr(w, "retained_native_static_target", lambda *a: None)

    def escape(*args, **kwargs):
        raw.battle_state = 0
        raw.player_money = 499 if fault == "resource_before" else 500
        state[0], em.frame_count, actions.actions_executed = b"pending", 20, 2
        return N(verified=True, public_dict=lambda: dict(verified=True))

    monkeypatch.setattr(w, "flee_wild", escape)

    def factory():
        calls.append("inspect")
        pending_sha = sha256(state[0]).hexdigest()
        if fault == "factory_mutation":
            state[0] = b"mutated"

        def execute():
            calls.append("trainer")
            state[0], em.frame_count, actions.actions_executed = b"settled", 30, 3
            ready[0] = fault != "unsettled"
            lost = fault in {"lost", "false_lost"}
            raw.player_money = 250 if lost else 700
            battle = dict(schema="pokemon.red.learned-trainer-completion.v1",
                outcome="lost" if lost else "won", field_ready=ready[0])
            return GoalExecutionReport(2 if fault == "wrong_action_cost" else 1,
                11 if fault == "wrong_frame_cost" else 10, dict(battle=battle,
                    support="other" if fault == "not_native" else "already_engaged_native_trainer",
                    source_sha256="0"*64 if fault == "wrong_source" else pending_sha,
                    terminal_sha256="0"*64 if fault == "wrong_terminal"
                    else sha256(state[0]).hexdigest()))

        def verify(_):
            if fault == "unverified":
                return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
            if fault == "lost":
                return GoalVerification.failed(GoalFailureReason.RESOURCE_LOST)
            return GoalVerification.succeeded()

        return N(binding_ref="pokemon.red:retained-engagement:" + (
                "0"*64 if fault == "wrong_ref" else pending_sha),
            kind=GoalKind.RESTORE_TEAM if fault == "wrong_kind" else GoalKind.RECOVER_CONTROL,
            execute=execute, verify=verify)

    binding = w.interrupted_wild_binding(rt, actions, rom=b"fixture",
        pending_trainer_factory=None if fault == "absent" else factory)
    if fault in {None, "lost"}:
        report = binding.execute()
        assert calls == ["inspect", "trainer"]
        assert report.actions_executed == 3 and report.frames_executed == 30
        assert report.evidence["chained_trainer_recovery"]["new_trainer_approach"] is False
        verdict = binding.verify(report)
        assert verdict.status is (GoalDecisionOutcome.FAILED if fault == "lost"
                                  else GoalDecisionOutcome.SUCCEEDED)
        if fault == "lost":
            assert verdict.failure_reason is GoalFailureReason.RESOURCE_LOST
    else:
        with pytest.raises(ValueError):
            binding.execute()
        if fault in {"absent", "not_pending", "resource_before"}:
            assert not calls


def test_pending_trainer_factory_requires_declared_ordinary_rom():
    with pytest.raises(TypeError, match="callable"):
        w.interrupted_wild_binding(N(), N(), pending_trainer_factory=True)
    with pytest.raises(ValueError, match="ordinary"):
        w.interrupted_wild_binding(N(), N(), pending_trainer_factory=lambda: None)
    with pytest.raises(ValueError, match="ordinary"):
        w.interrupted_wild_binding(N(), N(), rom=b"fixture", consumed_static_target=object(),
            pending_trainer_factory=lambda: None)


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "identity",
        "level",
        "map",
        "consumed",
        "event_missing",
        "extra_event",
        "owned",
        "visible",
        "pp",
    ],
)
def test_declared_snorlax_loss_preserves_every_other_event_and_resource(monkeypatch, fault):
    from dataclasses import replace

    from pokemon_red_completion import red_snorlax_capture as snorlax
    from pokemon_red_completion.observation import RawGameState
    from pokemon_red_completion.red_static_capture import RedStaticCaptureTarget

    target = RedStaticCaptureTarget(143, 132, 30, 23, 1, 67, (62, 10), 164)
    flags = bytearray(256)
    if fault == "consumed":
        flags[164 // 8] |= 1 << (164 % 8)
    before = RawGameState(
        True,
        22 if fault == "map" else 23,
        10,
        61,
        1,
        1,
        badge_bits=47,
        bag_items=((1, 1),),
        event_flags=bytes(flags),
        party_species_ids=(186,),
        party_levels=(27,),
        party_hp=(50,),
        party_max_hp=(79,),
        party_status=(0,),
        party_moves=((79,),),
        party_pp=((10,),),
        first_party_hp=50,
        enemy_level=29 if fault == "level" else 30,
        player_money=8841,
    )
    raws, state = [before], [b"source"]
    owned = [frozenset((44,))]
    rt = N(
        reader=N(
            read=lambda: raws[0],
            read_wild_capture_identity=lambda: N(
                original_species_id=133 if fault == "identity" else 132
            ),
            read_pokedex_state=lambda: N(owned_species=owned[0]),
            read_current_map_objects=lambda: (N(sprite_index=1, visible=fault == "visible"),),
        ),
        emulator=N(frame_count=0, save_state_bytes=lambda: state[0]),
    )
    actions = N(actions_executed=0)
    monkeypatch.setattr(snorlax, "route12_snorlax_target", lambda _: target)
    monkeypatch.setattr(w, "_field_ready", lambda _: raws[0].battle_state == 0)

    def flee(*args, **kwargs):
        events = bytearray(before.event_flags)
        if fault != "event_missing":
            events[164 // 8] |= 1 << (164 % 8)
        if fault == "extra_event":
            events[0] |= 1
        raws[0] = replace(
            before,
            battle_state=0,
            event_flags=bytes(events),
            party_pp=((9,),) if fault == "pp" else before.party_pp,
        )
        if fault == "owned":
            owned[0] |= {143}
        state[0] = b"terminal"
        actions.actions_executed = 3
        rt.emulator.frame_count = 200
        return N(verified=True, public_dict=lambda: {"verified": True})

    monkeypatch.setattr(w, "flee_wild", flee)
    if fault in {"identity", "level", "map", "consumed"}:
        with pytest.raises(ValueError):
            w.interrupted_wild_binding(rt, actions, consumed_static_target=target, rom=b"rom")
        assert not actions.actions_executed
        return
    binding = w.interrupted_wild_binding(rt, actions, consumed_static_target=target, rom=b"rom")
    if fault:
        with pytest.raises(ValueError):
            binding.execute()
    else:
        report = binding.execute()
        assert report.evidence["captured"] is False
        assert report.evidence["lost_static_target"]["species_number"] == 143
        assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
