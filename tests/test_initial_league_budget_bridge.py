"""ROM-free initial League censor bridge; no inference or emulator execution."""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace as N

import pytest
import test_red_lorelei_story as legacy
import test_red_scoped_league_retry as scoped
from pokemon_red_completion import red_trainer_story as skill_module
from pokemon_red_completion.red_lorelei_story import LoreleiStoryBattleStopped
from pokemon_red_completion.red_player_story_battle import StoryBattleDecisionBudgetReached


def setup_case(tmp_path, monkeypatch, objective=None):
    controller = legacy.controller(tmp_path) if objective is None else scoped.controller(tmp_path, objective)
    contract = controller.contract
    raw = N(battle_state=2, map_id=contract.map_id, party_hp=(50, 0))
    episode = N(stop_reason="decision_budget", battle_won=False,
                decisions=tuple({"kind": "attack"} for _ in range(controller.maximum_decisions)),
                final_battle_state=2)
    controller.last_completion = N(outcome="unresolved", field_ready=False, episode=episode)
    state = b"exact unfinished League state"
    saves = []
    def save():
        saves.append(True)
        return state
    reader = N(read=lambda: raw, read_active_trainer_identity=lambda: contract.trainer_identity)
    runtime = N(reader=reader, emulator=N(save_state_bytes=save, frame_count=1300, pressed_buttons=set()))
    records, inputs, calls = [], [], []
    actions = N(record_diagnostic_event=lambda *args: records.append(args), execute=lambda action: inputs.append(action), actions_executed=91)
    skill = N(runtime=runtime, objective_id=contract.objective_id,
              _prepared_learned_controller=controller, _prepared_story_binding=controller.binding_identity)
    original = LoreleiStoryBattleStopped(f"retained {contract.objective_id} outcome: unresolved")
    def funding(got_reader, got_actions, **kwargs):
        calls.append((got_reader, got_actions, kwargs))
        raise original
    monkeypatch.setattr(skill_module, "run_prepared_trainer_funding", funding)
    return N(controller=controller, raw=raw, episode=episode, runtime=runtime, reader=reader,
             actions=actions, skill=skill, original=original, records=records, inputs=inputs,
             calls=calls, saves=saves, state=state)


def invoke(case, **kwargs):
    return skill_module.RedCartridgeLoreleiSkill._run_prepared_battle(
        case.skill, case.controller, case.reader, case.actions, **kwargs)


@pytest.mark.parametrize("objective", [None, "defeat_lorelei", "defeat_bruno", "defeat_agatha", "defeat_lance"])
def test_exact_owned_budget_gets_existing_typed_censor_and_keeps_original(tmp_path, monkeypatch, objective):
    case = setup_case(tmp_path, monkeypatch, objective)
    completion = deepcopy(case.controller.last_completion)
    with pytest.raises(StoryBattleDecisionBudgetReached) as caught:
        invoke(case, battle_runner_override=case.controller.run, target="exact prepared target")
    assert type(caught.value) is StoryBattleDecisionBudgetReached
    assert str(caught.value) == "story battle reached its bounded decision limit"
    assert caught.value.reason_code == "story_battle_decision_budget"
    assert caught.value.__cause__ is case.original
    assert str(case.original).startswith("retained defeat_")
    assert case.controller.last_completion == completion
    assert case.actions.actions_executed == 91 and case.runtime.emulator.frame_count == 1300
    assert case.inputs == [] and case.saves == [True]
    assert case.runtime.emulator.pressed_buttons == set()
    assert len(case.calls) == 1
    assert case.calls[0][2] == dict(battle_runner_override=case.controller.run, target="exact prepared target")
    assert len(case.records) == 1
    name, evidence = case.records[0]
    assert name == "story_battle_decision_budget"
    assert evidence["terminal_state_sha256"] == sha256(case.state).hexdigest()
    assert evidence["decisions_consumed"] == case.controller.maximum_decisions
    assert evidence["outcome_and_costs_retained"] is True
    assert evidence["new_controller_inputs"] == 0
    assert evidence["declared_whole_battle_allowance"] is False


@pytest.mark.parametrize("fault", ["won", "lost", "field_ready", "other_stop", "battle_won",
    "short_count", "terminal_closed", "live_closed", "wrong_map", "wrong_trainer",
    "missing_hp", "all_fainted", "missing_completion", "different_prepared", "changed_binding",
    "wrong_objective", "deterministic_controller"])
def test_unproved_or_settled_result_keeps_original_exception_without_grant(tmp_path, monkeypatch, fault):
    case = setup_case(tmp_path, monkeypatch)
    if fault in {"won", "lost"}: case.controller.last_completion.outcome = fault
    elif fault == "field_ready": case.controller.last_completion.field_ready = True
    elif fault == "other_stop": case.episode.stop_reason = "runtime_budget"
    elif fault == "battle_won": case.episode.battle_won = True
    elif fault == "short_count": case.episode.decisions = case.episode.decisions[:-1]
    elif fault == "terminal_closed": case.episode.final_battle_state = 0
    elif fault == "live_closed": case.raw.battle_state = 0
    elif fault == "wrong_map": case.raw.map_id += 1
    elif fault == "wrong_trainer": case.reader.read_active_trainer_identity = lambda: (244, 44, 2)
    elif fault == "missing_hp": case.raw.party_hp = None
    elif fault == "all_fainted": case.raw.party_hp = (0, 0)
    elif fault == "missing_completion": case.controller.last_completion = None
    elif fault == "different_prepared": case.skill._prepared_learned_controller = object()
    elif fault == "changed_binding": case.skill._prepared_story_binding = ("changed",)
    elif fault == "wrong_objective": case.skill.objective_id = "defeat_bruno"
    elif fault == "deterministic_controller":
        case.controller = N(last_completion=case.controller.last_completion)
        case.skill._prepared_learned_controller = case.controller
    with pytest.raises(LoreleiStoryBattleStopped) as caught:
        invoke(case)
    assert caught.value is case.original
    assert case.records == case.inputs == case.saves == []
    assert case.actions.actions_executed == 91 and case.runtime.emulator.frame_count == 1300
    assert len(case.calls) == 1


@pytest.mark.parametrize("mode", ["receipt", "other_error", "keyboard_interrupt"])
def test_normal_receipt_and_unrelated_failures_are_not_reclassified(tmp_path, monkeypatch, mode):
    case = setup_case(tmp_path, monkeypatch)
    sentinel = object()
    original = RuntimeError("unrelated native error") if mode == "other_error" else KeyboardInterrupt()
    def funding(*args, **kwargs):
        if mode == "receipt": return sentinel
        raise original
    monkeypatch.setattr(skill_module, "run_prepared_trainer_funding", funding)
    if mode == "receipt": assert invoke(case) is sentinel
    else:
        with pytest.raises(type(original)) as caught: invoke(case)
        assert caught.value is original
    assert case.records == case.inputs == case.saves == []