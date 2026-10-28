"""Configuration -> actual collector/log/admission/target seam, without a ROM."""

import json
from copy import deepcopy
from dataclasses import replace

import pytest
from test_red_trainer_practice_admission import _CHOICES, _capture, _document
from test_red_trainer_practice_counterfactual import Continuation

from pokemon_red_completion import red_trainer_practice_counterfactual as collector
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_switch_control_measurement import (
    SwitchMeasurementContract,
    collect_admitted_switch_timing,
)
from pokemon_red_completion.red_trainer_practice_episode import RedTrainerPracticeEpisode
from pokemon_red_completion.red_trainer_practice_targets import aggregate_trainer_timing_targets


@pytest.mark.parametrize(
    "changes",
    [
        {"player_turn_horizon": 81},
        {"player_turn_horizon": 100},
        {"player_turn_horizon": 160},
        {"player_turn_horizon": True},
        {"max_decisions": 161},
        {"max_decisions": 2, "player_turn_horizon": 3},
        {"offsets": (0, 4, 8)},
        {"offsets": (0, 0, 4, 8, 12)},
        {"offsets": (0, 4, 8, 11, 13)},
        {"offsets": (False, 4, 8, 11, 12)},
    ],
)
def test_contract_rejects_before_any_execution(changes):
    with pytest.raises((ValueError, RuntimeError)):
        SwitchMeasurementContract(**changes)


def _fake_native(
    capture, *, policy, max_decisions, max_player_turns, event_sink, opening_idle_frames, **kwargs
):
    assert (max_decisions, max_player_turns) == (160, 80)
    action = policy.choose_main({}, object())
    index = 0 if action.move_slot else 1
    row = deepcopy(_document(capture)["branches"][index]["episode"])
    decision = row["decisions"][0]
    if kwargs.get("allow_status_moves"):
        decision["observation"]["features"]["battle"]["status_context"] = CONTEXT
        decision["observation_sha256"] = canonical_sha256(decision["observation"])
    decision["state_after"]["party_hp"] = [0, 0]
    for member in row["final_observation"]["features"]["party"]["members"]:
        member["hp"] = 0
    decision["after_observation_sha256"] = canonical_sha256(row["final_observation"])
    episode = RedTrainerPracticeEpisode(
        capture_id=capture.manifest.capture_id,
        manifest_sha256=capture.manifest_sha256,
        policy_id=policy.policy_id,
        decisions=(decision,),
        battle_won=False,
        final_battle_state=2,
        stop_reason="party_defeated",
        final_observation=row["final_observation"],
        opening_idle_frames=opening_idle_frames,
    )
    event_sink(
        dict(
            event="episode_started",
            manifest_sha256=capture.manifest_sha256,
            policy_id=policy.policy_id,
            max_decisions=max_decisions,
            max_player_turns=max_player_turns,
            opening_idle_frames=opening_idle_frames,
            **({"allow_forced_struggle": True} if kwargs.get("allow_forced_struggle") else {}),
        )
    )
    event_sink(dict(event="decision_started"))
    event_sink(
        dict(
            event="choice_recorded",
            decision_index=1,
            selected_action={"kind": "select_move", "move_slot": 1}
            if index == 0
            else {"kind": "switch", "party_slot": 2},
        )
    )
    event_sink(dict(event="decision_completed", decision=decision))
    return episode


CONTEXT = dict(
    schema="pokemon.core.battle.status-context.v1",
    player_confused=False,
    opponent_confused=True,
    player_stages=[0] * 6,
    opponent_stages=[0] * 6,
)


def _run(tmp_path, monkeypatch, *, offset=0, contract=None, runner=_fake_native, context=None):
    source = tmp_path / "source"
    source.mkdir(exist_ok=True)
    capture = _capture(source, status=True)
    monkeypatch.setattr(collector, "run_red_trainer_practice_episode", runner)
    return collect_admitted_switch_timing(
        capture,
        contract=contract or SwitchMeasurementContract(),
        offset=offset,
        refs=_CHOICES,
        policy_id="unit-continuation",
        model_sha256="b" * 64,
        status_context=context,
        directory=tmp_path / f"timing-{offset:02d}",
        session_factory=lambda: None,
        continuation_policy_factory=Continuation,
        before_branch=lambda index: None,
    )


def test_all_five_timings_pass_actual_collector_log_admission_and_aggregation(
    tmp_path, monkeypatch
):
    contract = SwitchMeasurementContract()
    targets = [_run(tmp_path, monkeypatch, offset=o) for o in contract.offsets]
    result = aggregate_trainer_timing_targets(tuple(targets), expected_offsets=contract.offsets)
    assert result["timing_count"] == 5
    assert result["scenario_count"] == 1
    assert result["decision_context"] == "main"
    for o in contract.offsets:
        directory = tmp_path / f"timing-{o:02d}"
        admission = json.loads((directory / "admission.json").read_text())
        assert admission["execution_proof_complete"] and admission["return_proof_complete"]
        assert admission["player_turn_horizon"] == 80
    with pytest.raises(FileExistsError):
        _run(tmp_path, monkeypatch)


def test_censoring_preserves_branch_but_never_creates_target(tmp_path, monkeypatch):
    def censored(*args, **kwargs):
        return replace(_fake_native(*args, **kwargs), stop_reason="player_turn_budget")

    with pytest.raises(ValueError, match="horizon"):
        _run(tmp_path, monkeypatch, runner=censored)
    assert not (tmp_path / "timing-00/target.json").exists()
    assert (tmp_path / "timing-00/branch-00-events").exists()


def test_bad_runtime_offset_has_no_branch_or_plan_effects(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="identity"):
        _run(tmp_path, monkeypatch, offset=13)
    assert not (tmp_path / "timing-13").exists()


def test_native_status_context_is_bound_through_collection_and_admission(tmp_path, monkeypatch):
    target = _run(tmp_path, monkeypatch, context=CONTEXT)
    assert target["observation"]["features"]["battle"]["status_context"] == CONTEXT


def test_admission_compares_exact_serialized_receipt_for_native_tuples(tmp_path, monkeypatch):
    def native_tuples(*args, **kwargs):
        sink = kwargs["event_sink"]

        def emit(event):
            if event.get("event") == "decision_completed":
                event["decision"]["model_diagnostics"] = {"runtime_sequence": (1, 2)}
            sink(event)

        return _fake_native(*args, **{**kwargs, "event_sink": emit})

    target = _run(tmp_path, monkeypatch, runner=native_tuples)
    assert target
    receipt = json.loads((tmp_path / "timing-00/choices.json").read_text())
    assert receipt["branches"][0]["episode"]["decisions"][0]["model_diagnostics"] == {
        "runtime_sequence": [1, 2]
    }


def test_serialized_receipt_does_not_hide_changed_execution_log(tmp_path, monkeypatch):
    def changed_log(*args, **kwargs):
        sink = kwargs["event_sink"]

        def emit(event):
            if event.get("event") == "decision_completed":
                event["decision"]["model_diagnostics"] = {"runtime_sequence": (1, 2)}
                logged = deepcopy(event)
                logged["decision"]["model_diagnostics"]["runtime_sequence"] = (1, 3)
                sink(logged)
            else:
                sink(event)

        return _fake_native(*args, **{**kwargs, "event_sink": emit})

    with pytest.raises(ValueError, match="decisions differ"):
        _run(tmp_path, monkeypatch, runner=changed_log)
    assert not (tmp_path / "timing-00/target.json").exists()


def test_invalid_status_context_has_no_branch_effects(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="status"):
        _run(tmp_path, monkeypatch, context={**CONTEXT, "player_stages": [0]})
    assert not (tmp_path / "timing-00").exists()


def test_struggle_opt_in_bound_in_plan_collector_and_admission(tmp_path, monkeypatch):
    contract = SwitchMeasurementContract(allow_forced_struggle=True)
    target = _run(tmp_path, monkeypatch, contract=contract)
    assert target
    assert json.loads((tmp_path / "timing-00/plan.json").read_text())["allow_forced_struggle"]


def test_struggle_flag_missing_from_execution_rejects_admission(tmp_path, monkeypatch):
    def missing(*args, **kwargs):
        kwargs.pop("allow_forced_struggle")
        return _fake_native(*args, **kwargs)

    with pytest.raises(ValueError, match="decisions differ"):
        _run(
            tmp_path,
            monkeypatch,
            contract=SwitchMeasurementContract(allow_forced_struggle=True),
            runner=missing,
        )
    assert not (tmp_path / "timing-00/target.json").exists()
