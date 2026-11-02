from types import SimpleNamespace as N

import pytest
from test_red_player_story_travel import setup as travel_setup

from pokemon_red_completion import red_player_story_battle as s
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalFailureReason
from pokemon_red_completion.red_story_battle import StoryTrainerContract


def setup(monkeypatch, *, lost=False, badge=True):
    rt, actions, route, raw, lesson = travel_setup(monkeypatch)
    raw.event_flags, raw.battle_state, raw.player_y, raw.player_x = bytes(32), 0, 3, 3
    target = N(
        map_id=54,
        sprite_index=1,
        at=(1, 4),
        lane=(),
        trainer_class=234,
        trainer_set=1,
        event_flag=119,
        defeated=False,
    )
    objective = N(id="defeat_brock", completion_facts=frozenset({"badge:boulder"}))
    rt.adapter.graph.objective = lambda _: objective
    rt.adapter.graph.available_objectives = lambda _: (objective,)
    rt.observer.latch_verified_facts = lambda _: lesson["completed_objectives"].append(
        "defeat_brock"
    )
    rt.reader.read_current_map_objects = lambda: ()
    monkeypatch.setattr(s, "_field_ready", lambda _: True)
    monkeypatch.setattr(
        s,
        "capture_player_lesson_snapshot",
        lambda _: (N(raw=raw, game_state=object()), {k: list(v) for k, v in lesson.items()}),
    )
    monkeypatch.setattr(s, "Gen1TraversalObserver", lambda *a, **k: N(observe=lambda: object()))
    monkeypatch.setattr(s, "Gen1TrainerSightProjector", lambda *a, **k: object())
    monkeypatch.setattr(s, "trainer_headers", lambda *a, **k: ())
    monkeypatch.setattr(s, "map_object_events", lambda *a, **k: ())
    monkeypatch.setattr(s, "static_trainer_sight_zones", lambda *a: (target,))
    monkeypatch.setattr(s, "trainer_sight_zones", lambda *a: (target,))
    monkeypatch.setattr(s, "face_trainer_boundary", lambda *a, **k: None)
    monkeypatch.setattr(
        type(route),
        "route_world",
        property(lambda _: N(plan_feasible_to_map=lambda *a, **k: N(terminal_at=(2, 4), cost=20))),
    )

    def travel(self, *args):
        raw.map_id = self.destination_map
        raw.player_y, raw.player_x = self.destination_at
        actions.actions_executed += 1
        rt.emulator.frame_count += 16

    monkeypatch.setattr(type(route), "__call__", travel)
    inputs = []

    def act(action):
        inputs.append(action)
        actions.actions_executed += 1
        raw.battle_state = 2

    actions.execute = act
    battle_calls = []

    def battle(*args, **kwargs):
        battle_calls.append(kwargs)
        raw.battle_state = 0
        if not lost:
            flags = bytearray(raw.event_flags)
            flags[119 // 8] |= 1 << (119 % 8)
            raw.event_flags = bytes(flags)
            raw.badge_bits = int(badge)
            raw.player_money += 1386
        else:
            raw.player_money //= 2
            raw.map_id = 41
        return N(
            outcome="lost" if lost else "won",
            field_ready=True,
            money_delta=-800 if lost else 1386,
            public_dict=lambda: {"outcome": "lost" if lost else "won"},
        )

    monkeypatch.setattr(s, "FrozenStoryBattleController", lambda *a, **k: N(run=battle))
    contract = StoryTrainerContract(
        "defeat_brock", "brock", 54, (234, 34, 1), 119, 1386, victory_badge_bits=1
    )
    return rt, actions, route, raw, lesson, inputs, battle_calls, contract, target


@pytest.mark.parametrize("lost", [False, True])
def test_selected_battle_preserves_win_or_paid_loss(monkeypatch, lost):
    rt, actions, route, raw, lesson, inputs, calls, contract, _ = setup(monkeypatch, lost=lost)
    binding = s.story_battle_binding(rt, actions, contract=contract, route=route, battler=object())
    assert binding.story_objective_ref == contract.objective_id
    assert not calls and not inputs
    report = binding.execute()
    assert len(calls) == 1 and not report.evidence["automatic_preparation"]
    result = binding.verify(report)
    if lost:
        assert raw.player_money == 800 and "defeat_brock" not in lesson["completed_objectives"]
        assert result.failure_reason is GoalFailureReason.RESOURCE_LOST
    else:
        assert raw.badge_bits == 1 and result.status is GoalDecisionOutcome.SUCCEEDED
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()


def test_battle_approach_projects_observed_field_move_capabilities(monkeypatch):
    rt, actions, route, _, _, inputs, calls, contract, _ = setup(monkeypatch)
    observed = []

    def observer(reader, *, capability_projector, hazard_projector):
        observed.append(capability_projector)
        return N(observe=lambda: object())

    monkeypatch.setattr(s, "Gen1TraversalObserver", observer)
    assert s.story_battle_binding(rt, actions, contract=contract, route=route, battler=object())
    assert observed == [s.cut_capabilities] and not inputs and not calls


def test_victory_without_native_badge_is_not_success(monkeypatch):
    rt, actions, route, _, lesson, _, _, contract, _ = setup(monkeypatch, badge=False)
    binding = s.story_battle_binding(rt, actions, contract=contract, route=route, battler=object())
    with pytest.raises(RuntimeError, match="badge proof"):
        binding.execute()
    assert "defeat_brock" not in lesson["completed_objectives"]


@pytest.mark.parametrize("fault", [None, "early_stop", "other_stop", "won",
    "field_ready", "battle_exited", "wrong_map", "wrong_trainer", "party_defeated"])
def test_story_decision_budget_retains_exact_active_battle_without_extra_inputs(monkeypatch, fault):
    rt, actions, route, raw, lesson, inputs, _, contract, _ = setup(monkeypatch)
    rt.reader.read_active_trainer_identity = lambda: (
        (0, 0, 0) if fault == "wrong_trainer" else contract.trainer_identity
    )
    events, counts = [], []
    actions.record_diagnostic_event = lambda kind, payload: events.append((kind, payload))

    def exhausted(*args, **kwargs):
        counts.append((len(inputs), actions.actions_executed, rt.emulator.frame_count))
        raw.battle_state = 0 if fault == "battle_exited" else 2
        if fault == "wrong_map":
            raw.map_id += 1
        if fault == "party_defeated":
            raw.party_hp = tuple(0 for _ in raw.party_hp)
        return N(outcome="unresolved", field_ready=fault == "field_ready", episode=N(
            stop_reason="unsupported_boundary" if fault == "other_stop" else "decision_budget",
            battle_won=fault == "won", final_battle_state=raw.battle_state,
            decisions=(None,) * (79 if fault == "early_stop" else 80),
        ))

    monkeypatch.setattr(s, "FrozenStoryBattleController", lambda *a, **k: N(
        run=exhausted, maximum_decisions=80,
    ))
    binding = s.story_battle_binding(rt, actions, contract=contract, route=route, battler=object())
    expected = s.StoryBattleDecisionBudgetReached if fault is None else RuntimeError
    with pytest.raises(expected) as caught:
        binding.execute()
    assert (len(inputs), actions.actions_executed, rt.emulator.frame_count) == counts[0]
    assert "defeat_brock" not in lesson["completed_objectives"]
    if fault is None:
        assert caught.value.reason_code == "story_battle_decision_budget"
        assert events[0][1]["decisions_consumed"] == 80
        assert events[0][1]["maximum_decisions"] == 80
        assert events[0][1]["new_controller_inputs"] == 0
    else:
        assert type(caught.value) is RuntimeError
        assert events == []
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()


def test_intermediate_trainer_does_not_fabricate_destination_completion(monkeypatch):
    rt, actions, route, _, lesson, _, _, contract, _ = setup(monkeypatch)
    binding = s.story_battle_binding(
        rt, actions, contract=contract, route=route, battler=object(), completes_objective=False
    )
    report = binding.execute()
    assert report.evidence["objective_completed"] is False
    assert "defeat_brock" not in lesson["completed_objectives"]
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED


def test_scripted_leader_uses_object_identity_and_separate_reward_settlement(monkeypatch):
    from pokemon_red_completion.red_gym_reward import BROCK_REWARD, GymReward

    rt, actions, route, _, _, _, _, contract, _ = setup(monkeypatch)
    monkeypatch.setattr(GymReward, "contract", lambda *a: contract)
    leader = N(
        object_index=1, movement=255, trainer_class=234, trainer_set=1, at=(1, 4), sprite_id=7
    )
    monkeypatch.setattr(s, "map_object_events", lambda *a, **k: (leader,))
    monkeypatch.setattr(s, "static_trainer_sight_zones", lambda *a: ())
    monkeypatch.setattr(s, "trainer_sight_zones", lambda *a: ())
    rt.reader.read_current_map_objects = lambda: (N(sprite_index=1, at=(1, 4), picture_id=7),)
    settled = []

    def settle(self, reader, port, *, before, victory_money):
        settled.append(victory_money)
        return dict(badge=1, item=self.item)

    monkeypatch.setattr(GymReward, "settle", settle)
    binding = s.story_battle_binding(
        rt, actions, contract=contract, route=route, battler=object(), reward=BROCK_REWARD
    )
    report = binding.execute()
    assert settled == [1386] and report.evidence["reward"]["badge"] == 1
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED


def test_changed_target_and_stale_source_fail_before_battle(monkeypatch):
    rt, actions, route, _, _, inputs, calls, contract, target = setup(monkeypatch)
    binding = s.story_battle_binding(rt, actions, contract=contract, route=route, battler=object())
    rt.emulator.save_state_bytes = lambda: b"different"
    with pytest.raises(ValueError, match="stale"):
        binding.execute()
    assert not inputs and not calls and actions.actions_executed == 0
    target.trainer_class = 201
    with pytest.raises(ValueError, match="differs from contract"):
        s.story_battle_binding(rt, actions, contract=contract, route=route, battler=object())


@pytest.mark.parametrize("failure", [None, "drift", "trainer", "unsettled", "facing", "target"])
def test_story_facing_reuses_exact_wild_recovery_and_rechecks_target(monkeypatch, failure):
    from copy import copy

    from pokemon_red_completion import red_routed_trainer_funding as funding
    from pokemon_red_completion.route_executor import InterruptionReceipt

    rt, actions, route, raw, _, inputs, battles, contract, target = setup(monkeypatch)
    rt.reader.read = lambda: copy(raw)
    rt.reader.read_input_readiness = lambda: N(ready=raw.battle_state == 0)
    rt.reader.read_bottom_dialogue_box_visible = lambda: False
    requested = []
    rt.reader.read_player_facing = lambda: "up" if failure == "facing" else requested[-1]
    stages = []

    def interrupted_face(_actions, _reader, direction):
        stages.append("face")
        requested.append(direction)
        if len(stages) > 1:
            return
        raw.battle_state = 2 if failure == "trainer" else 1
        if failure == "drift":
            raw.player_x += 1
        raise funding.RedPCStorageError("PC facing did not preserve its bound position")

    def observe():
        return N(interruption="trainer_battle" if failure == "trainer" else "wild_battle",
                 map_id=raw.map_id, at=(raw.player_y, raw.player_x))

    class Flee:
        def __init__(self, port, reader, **kwargs):
            assert port is actions and reader is rt.reader
            assert kwargs["maximum_flees"] == 1

        def handle(self, interruption):
            stages.append("flee")
            raw.battle_state = 1 if failure == "unsettled" else 0
            if failure == "target":
                moved = N(**{**vars(target), "at": (1, 5)})
                monkeypatch.setattr(s, "trainer_sight_zones", lambda *a: (moved,))
            return InterruptionReceipt("wild_battle", interruption.map_id,
                                       interruption.at, {"verified": True})

    monkeypatch.setattr(s, "face_trainer_boundary", funding._face_trainer_boundary)
    monkeypatch.setattr(funding, "face_pc_boundary", interrupted_face)
    monkeypatch.setattr(funding, "Gen1TraversalObserver", lambda _: N(observe=observe))
    monkeypatch.setattr(funding, "Gen1WildFleeHandler", Flee)
    binding = s.story_battle_binding(rt, actions, contract=contract, route=route, battler=object())
    if failure:
        message = "target moved" if failure == "target" else "trainer"
        with pytest.raises((ValueError, funding.RedTrainerFundingError), match=message):
            binding.execute()
        assert not battles and not inputs
        assert stages == (
            ["face"] if failure in {"drift", "trainer"}
            else ["face", "flee", "face"] if failure == "facing" else ["face", "flee"]
        )
    else:
        report = binding.execute()
        assert stages == ["face", "flee"] and len(battles) == 1
        assert report.evidence["facing_interruption"] == {
            "kind": "wild_battle", "resumed_map": 54, "resumed_at": (2, 4),
            "details": {"verified": True},
            "allows_map_transition": False, "allows_relocation": False,
        }
        assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED


def test_wrong_story_route_endpoint_rejected_before_facing(monkeypatch):
    rt, actions, route, raw, _, inputs, battles, contract, _ = setup(monkeypatch)
    monkeypatch.setattr(type(route), "__call__", lambda *a: None)
    monkeypatch.setattr(s, "face_trainer_boundary", lambda *a, **k: pytest.fail("wrong square"))
    binding = s.story_battle_binding(rt, actions, contract=contract, route=route, battler=object())
    with pytest.raises(ValueError, match="interaction boundary"):
        binding.execute()
    assert not inputs and not battles and raw.map_id == 41


@pytest.mark.parametrize("retry_failure", [None, "displacement", "second_wild", "still_wrong"])
def test_interrupted_turn_is_finished_once_after_verified_wild_return(monkeypatch, retry_failure):
    from dataclasses import replace

    from pokemon_red_completion import red_routed_trainer_funding as funding
    from pokemon_red_completion.observation import RawGameState
    from pokemon_red_completion.route_executor import InterruptionReceipt

    state = N(raw=RawGameState(game_started=True, map_id=61, player_y=16, player_x=10,
                              party_count=1, battle_state=0), facing="up")
    reader = N(read=lambda: state.raw,
               read_input_readiness=lambda: N(ready=state.raw.battle_state == 0),
               read_bottom_dialogue_box_visible=lambda: False,
               read_player_facing=lambda: state.facing)
    stages = []
    def face(_actions, _reader, direction):
        stages.append("face")
        if len(stages) == 1:
            state.raw = replace(state.raw, battle_state=1)
            raise funding.RedPCStorageError("PC facing did not preserve its bound position")
        if retry_failure == "second_wild":
            state.raw = replace(state.raw, battle_state=1)
            raise funding.RedPCStorageError("PC facing did not preserve its bound position")
        if retry_failure == "displacement":
            state.raw = replace(state.raw, player_x=11)
        if retry_failure != "still_wrong":
            state.facing = direction

    class Flee:
        def __init__(self, *args, **kwargs):
            assert kwargs["maximum_flees"] == 1
        def handle(self, _interruption):
            stages.append("flee")
            state.raw = replace(state.raw, battle_state=0)
            return InterruptionReceipt("wild_battle", 61, (16, 10), {})

    monkeypatch.setattr(funding, "face_pc_boundary", face)
    monkeypatch.setattr(funding, "Gen1WildFleeHandler", Flee)
    monkeypatch.setattr(funding, "Gen1TraversalObserver", lambda _: N(
        observe=lambda: N(interruption="wild_battle", map_id=61, at=(16, 10))))
    if retry_failure:
        with pytest.raises((funding.RedPCStorageError, funding.RedTrainerFundingError)):
            funding._face_trainer_boundary(object(), reader, "right")
    else:
        receipt = funding._face_trainer_boundary(object(), reader, "right")
        assert receipt.resumed_at == (16, 10) and state.facing == "right"
    assert stages == ["face", "flee", "face"]
