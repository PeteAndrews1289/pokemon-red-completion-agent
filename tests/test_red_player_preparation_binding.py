from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_preparation_binding as p
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport
from pokemon_red_completion.party import MoveObservation


def setup(monkeypatch):
    raw = N(map_id=41, battle_state=0, player_y=3, player_x=3, player_money=3000, bag_items=())
    emulator = N(pressed_buttons=(), frame_count=0)
    mon = N(species_id=177, level=5, experience=135, known_moves=(MoveObservation(33, 35),))
    member = N(specimen_ref="starter", observation=mon)
    observation = N(raw=raw, input_ready=True, game_state=None)
    runtime = N(
        emulator=emulator,
        reader=N(
            read=lambda: raw,
            read_input_readiness=lambda: N(ready=True),
            read_bottom_dialogue_box_visible=lambda: False,
        ),
        adapter=N(
            observe=lambda: observation, graph=N(completed_ids=lambda _: frozenset({"starter"}))
        ),
    )
    monkeypatch.setattr(p, "_raw_party_fully_restored", lambda _: True)
    monkeypatch.setattr(p, "observe_preparation_members", lambda *a: (member,))
    monkeypatch.setattr(p, "preparation_trainee", lambda *a: member)

    def observer(reader, *, capability_projector):
        assert capability_projector is p.cut_capabilities
        return N(observe=lambda: None)

    monkeypatch.setattr(p, "Gen1TraversalObserver", observer)
    actions = N(actions_executed=0)
    kwargs = dict(
        battler=N(session=emulator),
        plan=N(targets=(("starter", 6),)),
        route=N(rom=b"rom", route_world=N(plan_feasible_to_map=lambda *a, **k: N(cost=12))),
        corridor=N(map_id=12, origin_at=(2, 2), private_dict=lambda: {}),
        record=lambda *a: None,
        hideout_timing=None,
    )

    def run(**kw):
        assert kw["restore_on_return"] is False
        assert kw["actions"] is actions and kw["emulator"] is emulator
        mon.level, mon.experience = 6, 180
        actions.actions_executed += 5
        emulator.frame_count += 200
        return {"xp_gained": 45}

    monkeypatch.setattr(p, "execute_wild_preparation", run)
    # Each observation must be immutable, just like native PartyMemberObservation.
    monkeypatch.setattr(
        p,
        "observe_preparation_members",
        lambda *a: (N(specimen_ref="starter", observation=N(**vars(mon))),),
    )
    return runtime, actions, kwargs, mon


def test_single_starter_supported_and_success_requires_fresh_xp(monkeypatch):
    rt, actions, kwargs, mon = setup(monkeypatch)
    binding = p.preparation_binding(rt, actions, **kwargs)
    assert binding.kind is GoalKind.DEVELOP_TEAM and actions.actions_executed == 0
    report = binding.execute()
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    mon.experience = 135
    assert binding.verify(report).status is GoalDecisionOutcome.FAILED
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()


@pytest.mark.parametrize("allow_surf,forced_bike,available", [
    (True, False, True), (False, False, False), (True, True, False),
])
def test_preparation_quote_reaches_a_water_connected_venue_only_with_real_permission(
    monkeypatch, allow_surf, forced_bike, available
):
    from pokemon_red_completion.gen1_traversal import SURF_CAPABILITY
    from pokemon_red_completion.observation import Badge, RawGameState
    from pokemon_red_completion.route_plan import RoutePlanningError

    rt, actions, kwargs, _ = setup(monkeypatch)
    raw = RawGameState(
        True, 41, 3, 3, 1, 0, badge_bits=int(Badge.CASCADE | Badge.SOUL),
        party_hp=(50,), party_moves=((15, 57, 0, 0),),
    )
    rt.reader.read = lambda: raw
    rt.emulator.read_u8 = lambda _: (1 << 5) if forced_bike else 0
    kwargs["route"].allow_surf = allow_surf

    def observe(reader, *, capability_projector):
        return N(observe=lambda: N(capabilities=capability_projector(reader.read())))

    def plan(start, *args, **kw):
        if SURF_CAPABILITY not in start.capabilities:
            raise RoutePlanningError("venue requires a legal water edge")
        return N(cost=12)

    monkeypatch.setattr(p, "Gen1TraversalObserver", observe)
    kwargs["route"].route_world.plan_feasible_to_map = plan
    offered = p.preparation_binding(rt, actions, **kwargs)
    assert (offered is not None) is available
    assert actions.actions_executed == rt.emulator.frame_count == 0


@pytest.mark.parametrize("move", [106, 120])
def test_structurally_attackless_roster_is_not_offered_as_a_healing_problem(monkeypatch, move):
    rt, actions, kwargs, mon = setup(monkeypatch)
    mon.known_moves = (MoveObservation(move, 30),)
    assert p.preparation_binding(rt, actions, **kwargs) is None
    assert actions.actions_executed == rt.emulator.frame_count == 0


def test_indigo_preparation_is_explicit_and_uses_actual_nurse_boundary(monkeypatch):
    from pokemon_red_completion.observation import MapId

    rt, actions, kwargs, mon = setup(monkeypatch)
    raw = rt.reader.read()
    raw.map_id = int(MapId.INDIGO_PLATEAU_LOBBY)
    raw.player_y = raw.player_x = 7
    assert p.preparation_binding(rt, actions, **kwargs) is None
    binding = p.preparation_binding(rt, actions, include_indigo_lobby=True, **kwargs)
    assert binding is not None and actions.actions_executed == 0
    report = binding.execute()
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    raw.player_x = 3
    assert binding.verify(report).status is GoalDecisionOutcome.FAILED
    assert p.preparation_binding(rt, actions, include_indigo_lobby=True, **kwargs) is None


@pytest.mark.parametrize("value", [None, 1, "true"])
def test_indigo_preparation_is_not_truthy_coercion(monkeypatch, value):
    rt, actions, kwargs, _ = setup(monkeypatch)
    with pytest.raises(ValueError, match="Indigo"):
        p.preparation_binding(rt, actions, include_indigo_lobby=value, **kwargs)


@pytest.mark.parametrize("minimum", [None, 1])
def test_existing_readiness_rule_reaches_wild_executor(monkeypatch, minimum):
    rt, actions, kwargs, _ = setup(monkeypatch)
    observed = []
    delegate = p.execute_wild_preparation

    def run(**kw):
        observed.append(kw["minimum_ready_members"])
        return delegate(**kw)

    monkeypatch.setattr(p, "execute_wild_preparation", run)
    default = p.preparation_binding(rt, actions, **kwargs)
    explicit_default = p.preparation_binding(rt, actions, minimum_ready_members=None, **kwargs)
    selected = p.preparation_binding(rt, actions, minimum_ready_members=minimum, **kwargs)
    assert default.binding_ref == explicit_default.binding_ref
    assert (selected.binding_ref == default.binding_ref) == (minimum is None)
    assert selected.verify(selected.execute()).status is GoalDecisionOutcome.SUCCEEDED
    assert observed == [minimum]


@pytest.mark.parametrize("minimum", [0, 2, 7, True, 1.5])
def test_invalid_readiness_count_rejected_before_input(monkeypatch, minimum):
    rt, actions, kwargs, _ = setup(monkeypatch)
    with pytest.raises(ValueError, match="minimum battle-ready"):
        p.preparation_binding(rt, actions, minimum_ready_members=minimum, **kwargs)
    assert actions.actions_executed == rt.emulator.frame_count == 0


@pytest.mark.parametrize("escort", [False, True])
def test_existing_transport_escort_is_opt_in_and_keeps_legacy_identity(monkeypatch, escort):
    rt, actions, kwargs, _ = setup(monkeypatch)
    observed = []
    delegate = p.execute_wild_preparation

    def run(**kw):
        observed.append(kw["prepare_transport_escort"])
        return delegate(**kw)

    monkeypatch.setattr(p, "execute_wild_preparation", run)
    default = p.preparation_binding(rt, actions, **kwargs)
    selected = p.preparation_binding(rt, actions, prepare_transport_escort=escort, **kwargs)
    assert (selected.binding_ref == default.binding_ref) is (not escort)
    assert selected.verify(selected.execute()).status is GoalDecisionOutcome.SUCCEEDED
    assert observed == [escort]


@pytest.mark.parametrize("escort", [1, None, "yes"])
def test_invalid_transport_escort_rejected_before_input(monkeypatch, escort):
    rt, actions, kwargs, _ = setup(monkeypatch)
    with pytest.raises(ValueError, match="transport escort"):
        p.preparation_binding(rt, actions, prepare_transport_escort=escort, **kwargs)
    assert not actions.actions_executed


@pytest.mark.parametrize("battles", [0, 129, True, 1.5])
def test_preparation_rejects_invalid_explicit_battle_cap(monkeypatch, battles):
    from pokemon_red_completion.red_player_field_goals import routed_preparation_binding

    rt, actions, kwargs, _ = setup(monkeypatch)
    with pytest.raises(ValueError, match="battle allowance"):
        p.preparation_binding(rt, actions, maximum_battles=battles, **kwargs)
    with pytest.raises(ValueError, match="battle allowance"):
        routed_preparation_binding(rt, actions, home_map=41, maximum_battles=battles, **kwargs)
    assert actions.actions_executed == rt.emulator.frame_count == 0


@pytest.mark.parametrize("maximum_battles", [32, 128])
def test_explicit_battle_cap_keeps_default_and_shared_controller(monkeypatch, maximum_battles):
    rt, actions, kwargs, _ = setup(monkeypatch)
    observed = []
    delegate = p.execute_wild_preparation

    def run(**kw):
        observed.append(kw["maximum_battles"])
        return delegate(**kw)

    monkeypatch.setattr(p, "execute_wild_preparation", run)
    binding = p.preparation_binding(rt, actions, maximum_battles=maximum_battles, **kwargs)
    assert binding.verify(binding.execute()).status is GoalDecisionOutcome.SUCCEEDED
    assert observed == [maximum_battles]


def test_routed_recovery_cap_is_checked_before_travel(monkeypatch):
    from pokemon_red_completion.red_player_field_goals import routed_preparation_binding

    rt, actions, kwargs, _ = setup(monkeypatch)
    with pytest.raises(ValueError, match="recovery allowance"):
        routed_preparation_binding(rt, actions, home_map=41, maximum_recoveries=128, **kwargs)
    assert actions.actions_executed == rt.emulator.frame_count == 0


def test_default_health_retreat_leaves_recovery_to_next_selection(monkeypatch):
    rt, actions, kwargs, mon = setup(monkeypatch)
    healthy = [True]
    monkeypatch.setattr(p, "_raw_party_fully_restored", lambda _: healthy[0])
    actions.execute_restoration = lambda _: pytest.fail("next goal owns recovery")

    def retreat(**kw):
        assert kw["allow_health_retreat"] is True
        healthy[0] = False
        mon.experience += 11
        actions.actions_executed += 2
        rt.emulator.frame_count += 40
        return dict(battles=1, health_limited_return=True, stop_reason="party_hp_below_half")

    monkeypatch.setattr(p, "execute_wild_preparation", retreat)
    binding = p.preparation_binding(rt, actions, **kwargs)
    report = binding.execute()
    assert binding.verify(report).failure_reason is GoalFailureReason.RECOVERY_REQUIRED
    assert mon.level == 5 and mon.experience == 146


def test_depleted_party_masks_training_without_input(monkeypatch):
    rt, actions, kwargs, _ = setup(monkeypatch)
    monkeypatch.setattr(p, "_raw_party_fully_restored", lambda _: False)
    assert p.preparation_binding(rt, actions, **kwargs) is None
    assert actions.actions_executed == 0


@pytest.mark.parametrize("opposition", [17, 30, 45])
@pytest.mark.parametrize("case", ["useful_reserve", "ready", "new_catch", "completed_intent"])
def test_real_role_and_target_planner_controls_offer_without_implicit_retargeting(
    monkeypatch,
    opposition,
    case,
):
    """Synthetic declared roles, not inferred usefulness or native role reassignment."""
    from dataclasses import replace

    from test_party_preparation import enemies, team

    from pokemon_red_completion.party_preparation import (
        PreparationPurpose,
        build_preparation_plan,
    )
    from pokemon_red_completion.red_party_preparation import preparation_trainee

    rt, actions, kwargs, _ = setup(monkeypatch)
    reserve_level = opposition if case == "ready" else opposition - 10
    members = team(opposition, reserve_level)
    if case in {"new_catch", "completed_intent"}:
        members = (
            members[0],
            replace(
                members[1],
                purpose=PreparationPurpose.UNDECIDED,
                purpose_reason="",
            ),
        )
    if case == "completed_intent":
        # An earlier carry-only target is now satisfied. Refreshing observations
        # must not turn the undecided reserve into a new combat target.
        original = (
            replace(
                members[0],
                observation=replace(
                    members[0].observation,
                    level=opposition - 6,
                ),
            ),
            members[1],
        )
        plan = build_preparation_plan(original, enemies(opposition))
        assert plan.targets == ((members[0].specimen_ref, opposition - 3),)
    else:
        plan = build_preparation_plan(members, enemies(opposition))
    targets, roster = plan.targets, plan.roster
    kwargs["plan"] = plan
    monkeypatch.setattr(p, "preparation_trainee", preparation_trainee)
    monkeypatch.setattr(p, "observe_preparation_members", lambda *args: members)
    monkeypatch.setattr(
        p,
        "execute_wild_preparation",
        lambda **kw: pytest.fail(
            "offer enumeration must not execute training",
        ),
    )
    binding = p.preparation_binding(rt, actions, **kwargs)
    if case == "useful_reserve":
        assert binding is not None and binding.kind is GoalKind.DEVELOP_TEAM
        assert preparation_trainee(plan, members).specimen_ref == members[1].specimen_ref
        assert targets == ((members[1].specimen_ref, opposition - 3),)
    else:
        assert binding is None
    assert plan.targets == targets and plan.roster == roster
    assert actions.actions_executed == rt.emulator.frame_count == 0


@pytest.mark.parametrize("progress", [True, False])
def test_bounded_partial_xp_keeps_target_incomplete_and_requires_recovery(monkeypatch, progress):
    rt, actions, kwargs, mon = setup(monkeypatch)
    healthy = [True]
    monkeypatch.setattr(p, "_raw_party_fully_restored", lambda _: healthy[0])

    def bounded(**kw):
        healthy[0] = False
        mon.experience += 10 if progress else 0
        actions.actions_executed += 5
        rt.emulator.frame_count += 200
        return dict(battles=3, stop_reason="encounter_limit", health_limited_return=False)

    monkeypatch.setattr(p, "execute_wild_preparation", bounded)
    binding = p.preparation_binding(rt, actions, **kwargs)
    result = binding.verify(binding.execute())
    assert result.failure_reason is (
        GoalFailureReason.RECOVERY_REQUIRED if progress else GoalFailureReason.OUTCOME_NOT_VERIFIED
    )


@pytest.mark.parametrize("progress", [True, False])
def test_final_retained_dose_encounter_bound_preserves_partial_progress_without_success(
    monkeypatch, progress
):
    rt, actions, kwargs, mon = setup(monkeypatch)
    rt.emulator.save_state_bytes = lambda: b"retained-dose-terminal"
    healthy = [True]
    monkeypatch.setattr(p, "_raw_party_fully_restored", lambda _: healthy[0])
    actions.execute_restoration = lambda _: pytest.fail(
        "exhausted encounters must not grant another dose"
    )

    def bounded(**kw):
        healthy[0] = False
        mon.experience += 10 if progress else 0
        actions.actions_executed += 5
        rt.emulator.frame_count += 200
        return dict(
            battles=3, encounters=3, stop_reason="encounter_limit", health_limited_return=False
        )

    monkeypatch.setattr(p, "execute_wild_preparation", bounded)
    binding = p.preparation_binding(rt, actions, **kwargs, maximum_recoveries=3)
    report = binding.execute()
    verdict = binding.verify(report)
    assert verdict.status is GoalDecisionOutcome.FAILED
    assert verdict.failure_reason is (
        GoalFailureReason.RECOVERY_REQUIRED if progress else GoalFailureReason.OUTCOME_NOT_VERIFIED
    )
    assert report.evidence["retained_doses"][0]["target_reached"] is False


def test_verified_level_evolution_does_not_discard_preparation_gain(monkeypatch):
    rt, actions, kwargs, mon = setup(monkeypatch)
    monkeypatch.setattr(p, "level_evolution_edges", lambda _: frozenset({(177, 178, 16)}))

    def evolve(**kw):
        mon.species_id, mon.level, mon.experience = 178, 16, 3500
        actions.actions_executed += 5
        rt.emulator.frame_count += 200
        return dict(battles=1, stop_reason="target_reached")

    monkeypatch.setattr(p, "execute_wild_preparation", evolve)
    binding = p.preparation_binding(rt, actions, **kwargs)
    assert binding.verify(binding.execute()).status is GoalDecisionOutcome.SUCCEEDED


def test_dialogue_masks_training_even_when_controls_are_ready(monkeypatch):
    rt, actions, kwargs, _ = setup(monkeypatch)
    rt.reader.read_bottom_dialogue_box_visible = lambda: True
    assert p.preparation_binding(rt, actions, **kwargs) is None
    assert actions.actions_executed == 0


@pytest.mark.parametrize("change", ["dialogue", "input", "pressed"])
def test_preparation_rechecks_control_boundary_before_input(monkeypatch, change):
    rt, actions, kwargs, _ = setup(monkeypatch)
    binding = p.preparation_binding(rt, actions, **kwargs)
    if change == "dialogue":
        rt.reader.read_bottom_dialogue_box_visible = lambda: True
    elif change == "input":
        rt.reader.read_input_readiness = lambda: N(ready=False)
    else:
        rt.emulator.pressed_buttons = ("a",)
    with pytest.raises(ValueError, match="stale"):
        binding.execute()
    assert actions.actions_executed == 0


def test_uncontrolled_battler_is_rejected(monkeypatch):
    rt, actions, kwargs, _ = setup(monkeypatch)
    kwargs["battler"].session = object()
    with pytest.raises(ValueError, match="guarded"):
        p.preparation_binding(rt, actions, **kwargs)


def test_typed_defeat_settles_as_failed_goal_not_success(monkeypatch):
    rt, actions, kwargs, mon = setup(monkeypatch)
    rt.emulator.save_state_bytes = lambda: b"settled"

    def defeat(**kw):
        mon.experience += 24
        actions.actions_executed += 4
        raise p.WildPreparationDefeat("observed defeat")

    def settle(*a, **kw):
        actions.actions_executed += 2
        return dict(
            terminal_sha256=p.sha256(b"settled").hexdigest(),
            blackout=dict(cash_lost=1500),
            successful_preparation=False,
        )

    monkeypatch.setattr(p, "execute_wild_preparation", defeat)
    monkeypatch.setattr(p, "settle_preparation_loss", settle)
    binding = p.preparation_binding(rt, actions, **kwargs)
    report = binding.execute()
    assert report.actions_executed == 6
    assert binding.verify(report).failure_reason is GoalFailureReason.RESOURCE_LOST
    rt.emulator.save_state_bytes = lambda: b"changed"
    assert binding.verify(report).failure_reason is GoalFailureReason.OUTCOME_NOT_VERIFIED


def test_unknown_error_is_not_silently_settled(monkeypatch):
    rt, actions, kwargs, _ = setup(monkeypatch)

    def broken(**kw):
        raise RuntimeError("wild preparation stopped: party_defeated")

    monkeypatch.setattr(p, "execute_wild_preparation", broken)
    monkeypatch.setattr(
        p, "settle_preparation_loss", lambda *a, **k: pytest.fail("must not recover")
    )
    with pytest.raises(RuntimeError, match="party_defeated"):
        p.preparation_binding(rt, actions, **kwargs).execute()


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "recovery_limit",
        "battle_limit",
        "no_xp",
        "search",
        "restored",
        "cash",
        "dialogue",
        "bad_count",
        "heal_error",
        "heal_incomplete",
        "target_swap",
        "heal_xp",
        "unknown_error",
        "second_error",
    ],
)
def test_retained_training_intent_recovers_only_verified_partial_dose(monkeypatch, fault):
    rt, actions, kwargs, mon = setup(monkeypatch)
    mutable_raw = rt.reader.read()
    rt.reader.read = lambda: N(**vars(mutable_raw))
    kwargs.update(maximum_battles=1 if fault == "battle_limit" else 3, maximum_recoveries=1)
    state = N(healthy=True, dialogue=False, healed=False)
    rt.emulator.save_state_bytes = lambda: repr(
        (mon.level, mon.experience, actions.actions_executed, state.healthy)
    ).encode()
    rt.reader.read_bottom_dialogue_box_visible = lambda: state.dialogue
    monkeypatch.setattr(p, "_raw_party_fully_restored", lambda _: state.healthy)
    rows, limits = [], []
    kwargs["record"] = lambda name, value: rows.append((name, value))

    def run(**kw):
        limits.append(kw["maximum_battles"])
        assert kw["plan"] is kwargs["plan"]
        assert kw["battler"] is kwargs["battler"]
        actions.actions_executed += 5
        rt.emulator.frame_count += 200
        if fault == "unknown_error":
            raise RuntimeError("unexpected battle failure")
        if fault == "second_error" and len(limits) == 2:
            raise RuntimeError("failure after the retained recovery")
        if len(limits) > 1 and fault != "recovery_limit":
            mon.level = 6
        mon.experience += 0 if fault == "no_xp" else 10
        state.healthy = fault == "restored"
        state.dialogue = fault == "dialogue"
        if fault == "cash":
            mutable_raw.player_money -= 10
        return dict(
            xp_gained=10,
            battles=4 if fault == "bad_count" else 1,
            stop_reason="encounter_search_exhausted"
            if fault == "search"
            else "party_hp_below_half",
        )

    def heal(binding):
        assert rows[-1][0] == "retained-recovery-intent"
        assert rows[-2][0] == "retained-dose"
        assert rows[-2][1]["verification"] == "failed"
        actions.actions_executed += 2
        rt.emulator.frame_count += 50
        if fault == "heal_error":
            raise RuntimeError("shared heal budget exhausted")
        state.healthy = fault != "heal_incomplete"
        state.healed = True
        if fault == "heal_xp":
            mon.experience += 1
        return GoalExecutionReport(2, 50, {})

    monkeypatch.setattr(p, "execute_wild_preparation", run)
    monkeypatch.setattr(
        p, "RedCenterRestoreGoalProvider", lambda *a, **k: N(offer=lambda _: N(binding=object()))
    )
    if fault == "target_swap":
        monkeypatch.setattr(
            p,
            "preparation_trainee",
            lambda *a: N(specimen_ref="different" if state.healed else "starter"),
        )
    actions.execute_restoration = heal
    binding = p.preparation_binding(rt, actions, **kwargs)
    errors = {
        "cash",
        "dialogue",
        "bad_count",
        "heal_error",
        "heal_incomplete",
        "target_swap",
        "heal_xp",
        "unknown_error",
        "second_error",
    }
    if fault in errors:
        with pytest.raises((ValueError, RuntimeError)):
            binding.execute()
        assert len(limits) == (2 if fault == "second_error" else 1)
        if fault == "second_error":
            assert limits == [3, 2]
            assert actions.actions_executed == 12 and rt.emulator.frame_count == 450
            assert [name for name, _ in rows] == ["retained-dose", "retained-recovery-intent"]
            assert rows[0][1]["verification"] == "failed"
            assert rows[0][1]["target_level"] == 6
    else:
        report = binding.execute()
        assert binding.verify(report).status is (
            GoalDecisionOutcome.SUCCEEDED if fault is None else GoalDecisionOutcome.FAILED
        )
        resumed = fault in (None, "recovery_limit")
        assert limits == ([3, 2] if resumed else [1] if fault == "battle_limit" else [3])
        assert report.actions_executed == (12 if resumed else 5)
        assert report.frames_executed == (450 if resumed else 200)
        assert report.evidence["original_target"] == dict(specimen_ref="starter", level=6)
        assert report.evidence["retained_doses"][0]["verification"] == "failed"
        assert all(x[1]["target_level"] == 6 for x in rows if x[0] == "retained-dose")


@pytest.mark.parametrize("limit", [-1, 128, True, 1.0])
def test_retained_training_requires_explicit_bounded_recovery_count(monkeypatch, limit):
    rt, actions, kwargs, _ = setup(monkeypatch)
    with pytest.raises(ValueError, match="recovery allowance"):
        p.preparation_binding(rt, actions, **kwargs, maximum_recoveries=limit)


def test_retained_training_requires_metered_port(monkeypatch):
    rt, actions, kwargs, _ = setup(monkeypatch)
    with pytest.raises(ValueError, match="metered"):
        p.preparation_binding(rt, actions, **kwargs, maximum_recoveries=1)


@pytest.mark.parametrize("member_ref,start_level", [("reserve-a", 9), ("reserve-b", 23)])
@pytest.mark.parametrize("recoveries", [1, 2, 6, 127])
@pytest.mark.parametrize("encounters_per_dose", [1, 2])
@pytest.mark.parametrize("required_doses", [3, 6])
def test_repeated_health_retreat_keeps_absolute_target_and_total_battle_limit(
    monkeypatch, member_ref, start_level, recoveries, encounters_per_dose, required_doses
):
    rt, actions, kwargs, mon = setup(monkeypatch)
    mon.level = start_level
    target = start_level + 1
    kwargs.update(
        plan=N(targets=((member_ref, target),)),
        maximum_battles=required_doses,
        maximum_recoveries=recoveries,
    )
    healthy, calls, heals, rows = [True], [], [], []
    monkeypatch.setattr(p, "_raw_party_fully_restored", lambda _: healthy[0])
    monkeypatch.setattr(
        p,
        "observe_preparation_members",
        lambda *_: (N(specimen_ref=member_ref, observation=N(**vars(mon))),),
    )

    def trainee(plan, members):
        assert plan.targets == ((member_ref, target),)
        if mon.level >= target:
            raise ValueError("original target complete")
        return members[0]

    monkeypatch.setattr(p, "preparation_trainee", trainee)
    rt.emulator.save_state_bytes = lambda: repr((mon.level, mon.experience, healthy[0])).encode()
    kwargs["record"] = lambda name, value: rows.append((name, value))

    def run(**kw):
        assert kw["plan"] is kwargs["plan"]
        assert kw["continue_after_nonwinning_exit"] is True
        calls.append(kw["maximum_battles"])
        mon.experience += 10
        if len(calls) == required_doses:
            mon.level = target
        healthy[0] = False
        actions.actions_executed += 1
        rt.emulator.frame_count += 20
        return dict(
            battles=1,
            encounters=min(encounters_per_dose, kw["maximum_battles"]),
            xp_gained=10,
            health_limited_return=True,
            stop_reason="party_hp_below_half",
        )

    def heal(_):
        heals.append(mon.experience)
        healthy[0] = True
        actions.actions_executed += 1
        rt.emulator.frame_count += 10

    monkeypatch.setattr(p, "execute_wild_preparation", run)
    monkeypatch.setattr(
        p, "RedCenterRestoreGoalProvider", lambda *a, **k: N(offer=lambda _: N(binding=object()))
    )
    actions.execute_restoration = heal
    binding = p.preparation_binding(rt, actions, **kwargs)
    report = binding.execute()
    expected_calls = list(range(required_doses, 0, -encounters_per_dose))[: recoveries + 1]
    reached = len(expected_calls) == required_doses
    assert calls == expected_calls
    assert len(heals) == len(calls) - 1
    assert report.evidence["encounters_across_doses"] == sum(
        min(encounters_per_dose, remainder) for remainder in calls
    )
    assert report.evidence["completed_battles_across_doses"] == len(calls)
    assert report.evidence["original_target"] == dict(specimen_ref=member_ref, level=target)
    assert report.actions_executed == len(calls) + len(heals)
    assert binding.verify(report).status is (
        GoalDecisionOutcome.SUCCEEDED if reached else GoalDecisionOutcome.FAILED
    )
    if reached:
        healthy[0] = True
        assert p.preparation_binding(rt, actions, **kwargs) is None


@pytest.mark.parametrize("fault", [None, "unknown", "restored", "dialogue"])
@pytest.mark.parametrize("recoveries", [1, 127])
def test_verified_zero_xp_health_retreat_is_failed_recovery_not_training_success(
    monkeypatch, fault, recoveries
):
    rt, actions, kwargs, mon = setup(monkeypatch)
    healthy = [True]
    rt.emulator.save_state_bytes = lambda: repr((actions.actions_executed, healthy[0])).encode()
    monkeypatch.setattr(p, "_raw_party_fully_restored", lambda _: healthy[0])
    actions.execute_restoration = lambda _: pytest.fail("zero-progress dose must not auto-repeat")

    def retreat(**kw):
        assert kw["allow_health_retreat"] is True
        actions.actions_executed += 2
        rt.emulator.frame_count += 40
        healthy[0] = fault == "restored"
        if fault == "dialogue":
            rt.reader.read_bottom_dialogue_box_visible = lambda: True
        return dict(
            battles=0,
            xp_gained=0,
            status="no_progress",
            stop_reason="party_hp_below_half",
            health_limited_return=fault != "unknown",
        )

    monkeypatch.setattr(p, "execute_wild_preparation", retreat)
    binding = p.preparation_binding(rt, actions, **kwargs, maximum_recoveries=recoveries)
    if fault == "dialogue":
        with pytest.raises(ValueError, match="dose boundary"):
            binding.execute()
        return
    report = binding.execute()
    verdict = binding.verify(report)
    assert verdict.failure_reason is (
        GoalFailureReason.RECOVERY_REQUIRED
        if fault is None
        else GoalFailureReason.OUTCOME_NOT_VERIFIED
    )
    assert report.evidence["retained_doses"][0]["verification"] == "failed"
    assert mon.level == 5 and mon.experience == 135


def zero_progress_recovery_setup(
    monkeypatch, progress, *, stop_reason="party_status", verified=True
):
    rt, actions, kwargs, mon = setup(monkeypatch)
    kwargs.update(
        maximum_battles=8,
        maximum_recoveries=7,
        repeat_health_limited_zero_progress=True,
    )
    kwargs["plan"].budget = N(max_no_progress=3)
    healthy, calls, heals, rows = [True], [], [], []
    monkeypatch.setattr(p, "_raw_party_fully_restored", lambda _: healthy[0])
    rt.emulator.save_state_bytes = lambda: repr(
        (mon.level, mon.experience, actions.actions_executed, healthy[0])
    ).encode()
    kwargs["record"] = lambda name, value: rows.append((name, value))

    def run(**kw):
        assert kw["plan"] is kwargs["plan"]
        assert kw["continue_after_nonwinning_exit"] is True
        assert healthy[0]
        index = len(calls)
        calls.append(kw["maximum_battles"])
        earned = progress[index]
        if earned:
            mon.experience += 10
            if index == len(progress) - 1:
                mon.level = 6
        healthy[0] = False
        actions.actions_executed += 2
        rt.emulator.frame_count += 40
        return dict(
            battles=int(earned),
            encounters=1,
            xp_gained=10 if earned else 0,
            health_limited_return=verified,
            stop_reason=stop_reason,
        )

    def heal(_):
        assert rows[-1][0] == "retained-recovery-intent"
        assert rows[-2][0] == "retained-dose"
        heals.append(mon.experience)
        healthy[0] = True
        actions.actions_executed += 1
        rt.emulator.frame_count += 20

    monkeypatch.setattr(p, "execute_wild_preparation", run)
    monkeypatch.setattr(
        p, "RedCenterRestoreGoalProvider", lambda *a, **k: N(offer=lambda _: N(binding=object()))
    )
    actions.execute_restoration = heal
    return rt, actions, kwargs, mon, calls, heals, rows


@pytest.mark.parametrize("progress", [(False, True), (False, True, False, True)])
def test_explicit_zero_xp_health_recovery_keeps_costs_and_original_target(monkeypatch, progress):
    rt, actions, kwargs, mon, calls, heals, rows = zero_progress_recovery_setup(
        monkeypatch, progress
    )
    binding = p.preparation_binding(rt, actions, **kwargs)
    report = binding.execute()
    assert calls == list(range(8, 8 - len(progress), -1))
    assert len(heals) == len(progress) - 1
    assert mon.level == 6 and mon.experience == 135 + 10 * sum(progress)
    assert report.actions_executed == 2 * len(progress) + len(heals)
    assert report.frames_executed == 40 * len(progress) + 20 * len(heals)
    assert report.evidence["encounters_across_doses"] == len(progress)
    assert report.evidence["original_target"] == dict(specimen_ref="starter", level=6)
    assert report.evidence["no_progress_limit"] == 3
    doses = [value for name, value in rows if name == "retained-dose"]
    assert doses[0]["verification"] == "failed" and doses[0]["consecutive_no_progress"] == 1
    assert all(d["verification"] == "failed" for d in doses[:-1])
    assert doses[-1]["verification"] == "succeeded"
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED


def test_zero_xp_health_recovery_stops_at_declared_consecutive_limit(monkeypatch):
    rt, actions, kwargs, mon, calls, heals, rows = zero_progress_recovery_setup(
        monkeypatch, (False, False, False)
    )
    binding = p.preparation_binding(rt, actions, **kwargs)
    report = binding.execute()
    assert calls == [8, 7, 6] and len(heals) == 2
    assert mon.level == 5 and mon.experience == 135
    assert report.evidence["encounters_across_doses"] == 3
    assert [v["consecutive_no_progress"] for k, v in rows if k == "retained-dose"] == [1, 2, 3]
    assert binding.verify(report).failure_reason is GoalFailureReason.RECOVERY_REQUIRED


@pytest.mark.parametrize("stop_reason,verified", [("unknown", True), ("party_status", False)])
def test_zero_xp_retry_does_not_resume_an_unverified_health_return(
    monkeypatch, stop_reason, verified
):
    rt, actions, kwargs, mon, calls, heals, _ = zero_progress_recovery_setup(
        monkeypatch, (False,), stop_reason=stop_reason, verified=verified
    )
    binding = p.preparation_binding(rt, actions, **kwargs)
    binding.execute()
    assert calls == [8] and not heals and mon.experience == 135


@pytest.mark.parametrize("flag", [None, 1, "yes"])
def test_zero_xp_recovery_requires_explicit_boolean(monkeypatch, flag):
    rt, actions, kwargs, _ = setup(monkeypatch)
    with pytest.raises(ValueError, match="explicit boolean"):
        p.preparation_binding(rt, actions, **kwargs, repeat_health_limited_zero_progress=flag)
    assert actions.actions_executed == rt.emulator.frame_count == 0


@pytest.mark.parametrize("limit", [None, 0, -1, True, 1.0])
def test_zero_xp_recovery_requires_original_plan_limit(monkeypatch, limit):
    rt, actions, kwargs, _, _, _, _ = zero_progress_recovery_setup(monkeypatch, (False,))
    kwargs["plan"].budget.max_no_progress = limit
    with pytest.raises(ValueError, match="declared no-progress/recovery limit"):
        p.preparation_binding(rt, actions, **kwargs)
    assert actions.actions_executed == rt.emulator.frame_count == 0


def test_zero_xp_recovery_changes_offer_identity_only_when_explicitly_enabled(monkeypatch):
    rt, actions, kwargs, _, _, _, _ = zero_progress_recovery_setup(monkeypatch, (False,))
    explicit = p.preparation_binding(rt, actions, **kwargs)
    kwargs["repeat_health_limited_zero_progress"] = False
    default0 = p.preparation_binding(rt, actions, **kwargs)
    kwargs.pop("repeat_health_limited_zero_progress")
    default1 = p.preparation_binding(rt, actions, **kwargs)
    assert default0.binding_ref == default1.binding_ref != explicit.binding_ref
    assert actions.actions_executed == rt.emulator.frame_count == 0
