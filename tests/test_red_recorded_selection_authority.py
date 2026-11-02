"""Recorded selector replay keeps actual executor callbacks inaccessible."""

import copy
import json
from dataclasses import replace

import pytest
from test_red_live_option_menu import _model, _ordinary_bindings, _situation
from test_red_native_player import setup
from test_red_sequence_native_audit import read

from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_live_option_menu import (
    build_red_live_option_set,
    select_red_live_option,
)
from pokemon_red_completion.red_native_player import run_native_continuous_player
from pokemon_red_completion.red_recorded_selection_authority import (
    record_selection_authority,
    replay_selection_authority,
)
from pokemon_red_completion.red_sequence_native_audit import audit_native_sequence_trace
from pokemon_red_completion.resource_economy_observation import EconomySnapshot


def records(safety=0.1):
    calls = []
    options = build_red_live_option_set(
        situation=_situation(resources=0.1, safety=safety), binding_set=_ordinary_bindings(calls),
        supplements=(), model_feature_version=4, ordering_seed_sha256="a" * 64,
        economy_snapshot=EconomySnapshot(58, ()), target_cash=3000,
    )
    model = _model()
    choice = select_red_live_option(model, options, seed=23, allow_earning_exploration=True)
    document = record_selection_authority(options, allow_earning_exploration=True)
    intent = dict(menu=options.public_dict(), selection_seed=23,
                  private_selection_authority=document)
    return model, json.loads(json.dumps(intent)), choice, calls


@pytest.mark.parametrize("safety", [0.1, 0.99])
def test_selector_replays_model_and_safety_without_executing(safety):
    model, intent, choice, calls = records(safety)
    assert replay_selection_authority(
        model, intent, choice.public_dict(), allow_earning_exploration=True,
    ) == choice.selected_binding.binding_ref
    assert calls == []
    assert choice.mode.value == ("deterministic_safety" if safety > 0.9 else "model_exploration")
    assert "private_selection_authority" not in json.dumps(intent["menu"])


@pytest.mark.parametrize("fault", ["earning", "kind", "ref", "extra", "safety", "selection"])
def test_changed_private_authority_or_choice_rejects(fault):
    model, intent, choice, calls = records(0.99)
    private = intent["private_selection_authority"]
    decision = choice.public_dict()
    if fault == "earning":
        private["allow_earning_exploration"] = False
    elif fault == "kind":
        private["live_bindings"][0]["policy"]["kind"] = "advance_story"
    elif fault == "ref":
        private["live_bindings"][0]["binding_ref"] = "wrong-ref"
    elif fault == "extra":
        private["invented"] = True
    elif fault == "safety":
        private["situation"]["safety_pressure"] = 0.0
    else:
        decision = copy.deepcopy(decision)
        decision["selected_candidate_index"] = 1 - decision["selected_candidate_index"]
    with pytest.raises(ValueError):
        replay_selection_authority(model, intent, decision, allow_earning_exploration=True)
    assert calls == []


@pytest.mark.parametrize("support", ["control", "restore"])
def test_native_support_replay_and_selected_binding_check(tmp_path, monkeypatch, support):
    args, executed = setup(tmp_path, monkeypatch, support=support)
    args["limits"] = replace(args["limits"], actions=3, decisions=3)
    run_native_continuous_player(**args)
    root = args["output"]
    audit_args = dict(
        store=args["store"], model=args["model"],
        expected_native_plan_sha256=canonical_sha256(read(root / "native-plan.json")),
        expected_actor_result_sha256=canonical_sha256(read(root / "episode/result.json")),
        source_sha256=args["source"]["state_sha256"],
    )
    audit = audit_native_sequence_trace(root, **audit_args)
    assert audit.recorded_selector_and_binding_replayed == 3 and executed == [2, 4, 6]
    assert not audit.safety_and_executor_authority_verified  # native truth is a separate check
    path = root / "episode/step-000/execution-started.json"
    value = read(path)
    value["selected_binding_ref"] = "some-other-executor"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="different binding"):
        audit_native_sequence_trace(root, **audit_args)
