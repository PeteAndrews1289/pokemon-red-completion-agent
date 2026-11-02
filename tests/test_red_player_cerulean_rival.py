from types import SimpleNamespace as N

import pytest
from test_red_player_story_battle import setup as battle_setup

from pokemon_red_completion import red_player_cerulean_rival as r
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalFailureReason


@pytest.mark.parametrize("starter,team", [(176, 7), (153, 8), (177, 9)])
def test_contract_uses_observed_rival_starter_not_player_first_party(monkeypatch, starter, team):
    monkeypatch.setattr(r, "verify_rom_bytes", lambda _: None)
    monkeypatch.setattr(
        r, "map_object_events", lambda *a: (N(object_index=1, sprite_id=2, movement=255),)
    )
    monkeypatch.setattr(
        r,
        "trainer_party_quote",
        lambda rom, cls, n: N(
            trainer_set=n,
            party=(N(internal_species={7: 176, 8: 153, 9: 177}[n]),),
            expected_victory_money=595,
        ),
    )
    reader = N(read=lambda: N(event_flags=bytes(256)), read_rival_starter=lambda: starter)
    contract = r.cerulean_rival_contract(b"rom", reader)
    assert contract.trainer_identity == (225, 25, team)
    assert contract.objective_id == "help_bill" and contract.victory_money == 595


def fixture(monkeypatch, *, lost=False, identity=(225, 25, 8), proof=True, include_route=False):
    rt, actions, route, raw, lesson, inputs, calls, _, _ = battle_setup(monkeypatch)
    raw.map_id, raw.player_y, raw.player_x = 3, 18, 0
    rt.adapter.observe = lambda: N(raw=raw, game_state=object())
    rt.adapter.graph.available_objectives = lambda _: (N(id="help_bill"),)
    rt.reader.read_active_trainer_identity = lambda: identity
    contract = r.StoryTrainerContract("help_bill", "rival", 3, (225, 25, 8), 152, 595)
    monkeypatch.setattr(r, "cerulean_rival_contract", lambda *a: contract)
    monkeypatch.setattr(r, "_field_ready", lambda _: True)
    monkeypatch.setattr(r, "Gen1TraversalObserver", lambda *a, **k: N(observe=lambda: object()))
    monkeypatch.setattr(r, "Gen1TrainerSightProjector", lambda *a, **k: object())
    monkeypatch.setattr(
        type(route),
        "route_world",
        property(
            lambda _: N(plan_feasible_to_map=lambda *a, **k: N(terminal_at=k["goal_at"], cost=25))
        ),
    )

    def battle(*args, **kwargs):
        calls.append(kwargs)
        raw.battle_state = 0
        if lost:
            raw.player_money //= 2
            raw.map_id = 64
        elif proof:
            flags = bytearray(raw.event_flags)
            flags[152 // 8] |= 1 << (152 % 8)
            raw.event_flags = bytes(flags)
            raw.player_money += 595
        return N(
            outcome="lost" if lost else "won",
            field_ready=True,
            public_dict=lambda: {"outcome": "lost" if lost else "won"},
        )

    monkeypatch.setattr(r, "FrozenStoryBattleController", lambda *a, **k: N(run=battle))
    binding = r.cerulean_rival_binding(rt, actions, route=route, battler=object())
    result = (rt, actions, raw, binding, calls, inputs, lesson)
    return result + (route,) if include_route else result


@pytest.mark.parametrize("lost", [False, True])
def test_rival_execution_is_learned_and_never_completes_bill(monkeypatch, lost):
    rt, actions, raw, binding, calls, inputs, lesson = fixture(monkeypatch, lost=lost)
    assert not calls and not inputs and actions.actions_executed == 0
    report = binding.execute()
    assert len(calls) == 1 and not report.evidence["objective_completed"]
    assert "help_bill" not in lesson["completed_objectives"]
    verdict = binding.verify(report)
    if lost:
        assert verdict.failure_reason is GoalFailureReason.RESOURCE_LOST
        assert raw.player_money == 800
    else:
        assert verdict.status is GoalDecisionOutcome.SUCCEEDED
        assert raw.player_money == 2195
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()


def test_wrong_native_rival_identity_never_calls_battler(monkeypatch):
    _, _, _, binding, calls, _, _ = fixture(monkeypatch, identity=(225, 25, 7))
    with pytest.raises(ValueError, match="identity"):
        binding.execute()
    assert not calls


def test_rival_missing_event_is_not_success(monkeypatch):
    _, _, _, binding, _, _, _ = fixture(monkeypatch, proof=False)
    assert binding.verify(binding.execute()).status is GoalDecisionOutcome.FAILED


def test_stale_rival_binding_does_not_act(monkeypatch):
    rt, actions, _, binding, calls, inputs, _ = fixture(monkeypatch)
    rt.emulator.save_state_bytes = lambda: b"changed"
    with pytest.raises(ValueError, match="stale"):
        binding.execute()
    assert not calls and not inputs and actions.actions_executed == 0


@pytest.mark.parametrize("fault", [None, "identity", "entry_failure", "missing_event", "lost"])
def test_revision_bound_entry_reuses_owned_battle_and_paid_loss(monkeypatch, fault):
    rt, actions, raw, _, calls, inputs, lesson, route = fixture(
        monkeypatch, identity=(242, 42, 11), include_route=True
    )
    raw.map_id, raw.player_x = 33, 9
    raw.event_flags = bytes(320)
    rt.adapter.graph.available_objectives = lambda _: (N(id="cross_victory_road"),)
    contract = r.StoryTrainerContract(
        "cross_victory_road", "route22-rival-gate", 33, (242, 42, 11), 1318, 1500
    )
    entry_calls = []

    def entry():
        entry_calls.append("decoded native entry")
        if fault == "entry_failure":
            raise RuntimeError("retained script failure")
        raw.battle_state = 2
        if fault == "identity":
            rt.reader.read_active_trainer_identity = lambda: (242, 42, 10)

    def battle(*args, **kwargs):
        calls.append(kwargs)
        raw.battle_state = 0
        if fault == "lost":
            raw.player_money //= 2
            raw.map_id = 41
        elif fault != "missing_event":
            flags = bytearray(raw.event_flags)
            flags[1318 // 8] |= 1 << (1318 % 8)
            raw.event_flags = bytes(flags)
            raw.player_money += 1500
        return N(
            outcome="lost" if fault == "lost" else "won",
            field_ready=True,
            public_dict=lambda: {"outcome": "lost" if fault == "lost" else "won"},
        )

    monkeypatch.setattr(r, "FrozenStoryBattleController", lambda *a, **k: N(run=battle))
    binding = r.scripted_rival_binding(
        rt,
        actions,
        route=route,
        battler=object(),
        objective_id="cross_victory_road",
        map_id=33,
        contract_factory=lambda *a: contract,
        already_defeated=lambda: r.event_flag_is_set(raw.event_flags, 1318),
        entries=(((3, 9), "left"),),
        scripted_entry=entry,
        hazard_projector=object(),
    )
    assert not calls and not inputs and not entry_calls
    if fault in {"entry_failure", "identity"}:
        with pytest.raises((RuntimeError, ValueError)):
            binding.execute()
        assert not calls
    else:
        report = binding.execute()
        assert len(calls) == 1 and not inputs
        verdict = binding.verify(report)
        assert verdict.status is (
            GoalDecisionOutcome.SUCCEEDED if fault is None else GoalDecisionOutcome.FAILED
        )
        if fault == "lost":
            assert verdict.failure_reason is GoalFailureReason.RESOURCE_LOST
            assert raw.player_money == 800
        assert not report.evidence["objective_completed"]
        assert "cross_victory_road" not in lesson["completed_objectives"]
    assert entry_calls == ["decoded native entry"]


@pytest.mark.parametrize("proof", [True, False])
def test_ship_reuses_gate_with_declared_direction_and_native_script(monkeypatch, proof):
    rt, actions, raw, _, calls, inputs, _, route = fixture(
        monkeypatch, identity=(242, 42, 2), include_route=True
    )
    raw.map_id = 96
    rt.adapter.graph.available_objectives = lambda _: (N(id="obtain_cut"),)
    contract = r.StoryTrainerContract(
        "obtain_cut", "ss-anne-rival-gate", 96, (242, 42, 2), None, 1300
    )
    phase = [0]

    def battle(*args, **kwargs):
        calls.append(kwargs)
        raw.battle_state = 0
        phase[0] = 4 if proof else 3
        return N(outcome="won", field_ready=True, public_dict=lambda: {"outcome": "won"})

    monkeypatch.setattr(r, "FrozenStoryBattleController", lambda *a, **k: N(run=battle))
    binding = r.scripted_rival_binding(
        rt,
        actions,
        route=route,
        battler=object(),
        objective_id="obtain_cut",
        map_id=96,
        contract_factory=lambda *a: contract,
        already_defeated=lambda: phase[0] == 4,
        entries=(((8, 35), "right"),),
    )
    report = binding.execute()
    assert len(calls) == 1 and inputs[0] == r.MacroAction(r.MacroActionKind.MOVE, "right")
    assert len(inputs) == 1  # No confirm may select an unowned combat move.
    assert report.evidence["objective"] == "obtain_cut"
    assert binding.verify(report).status is (
        GoalDecisionOutcome.SUCCEEDED if proof else GoalDecisionOutcome.FAILED
    )
