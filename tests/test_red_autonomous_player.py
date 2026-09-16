import json
from dataclasses import replace

import pytest
from test_red_live_option_menu import _mixed, _model, _ordinary_bindings, _situation

from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport, GoalVerification
from pokemon_red_completion.red_autonomous_player import AutonomousSnapshot, run_autonomous_options
from pokemon_red_completion.red_live_option_menu import build_red_live_option_set
from pokemon_red_completion.resource_economy_observation import EconomySnapshot


def _environment(output, *, fail=False, verify_fails=False, unsafe=False):
    state = {"version": 0, "observations": [], "selected": []}

    def snapshot():
        return AutonomousSnapshot(
            str(state["version"]).encode(),
            {"version": state["version"]},
            not (unsafe and state["version"]),
        )

    def observe(ordinal):
        state["observations"].append(state["version"])
        options = _mixed([])
        # Avoid a deterministic resource emergency for the model-control tests.
        options = replace(options, situation=_situation(resources=0.1))
        bindings = []
        for index, binding in enumerate(options.bindings):

            def execute(index=index):
                saved = json.loads((output / f"step-{ordinal:03d}" / "decision.json").read_text())
                assert saved["selected_candidate_index"] == index
                state["selected"].append(index)
                state["version"] += 1
                if fail:
                    raise RuntimeError("failure after real state change")
                return GoalExecutionReport(1, 1, {})

            def verify(report):
                if verify_fails:
                    raise ValueError("verification failed after execution")
                return GoalVerification.succeeded()

            bindings.append(replace(binding, execute=execute, verify=verify))
        return replace(options, bindings=tuple(bindings))

    return state, snapshot, observe


def test_three_model_choices_execute_only_saved_arms_and_reobserve_earned_states(tmp_path):
    output = tmp_path / "run"
    state, snapshot, observe = _environment(output)
    result = run_autonomous_options(
        model=_model(),
        output=output,
        snapshot=snapshot,
        observe=observe,
        seed=17,
        provenance={},
    )
    assert result["successful_decisions"] == 3
    assert state["observations"] == [0, 1, 2]
    assert len(state["selected"]) == 3
    assert result["stop_reason"] == "decision_budget"
    assert (output / "step-002/terminal.state").read_bytes() == b"3"


@pytest.mark.parametrize("failure", ["execute", "verify", "unsafe"])
def test_partial_state_and_decision_survive_failure_without_next_query(tmp_path, failure):
    output = tmp_path / "run"
    state, snapshot, observe = _environment(
        output,
        fail=failure == "execute",
        verify_fails=failure == "verify",
        unsafe=failure == "unsafe",
    )
    result = run_autonomous_options(
        model=_model(),
        output=output,
        snapshot=snapshot,
        observe=observe,
        seed=17,
        provenance={},
    )
    assert result["executed_decisions"] == 1
    assert state["observations"] == [0]
    assert (output / "step-000/decision.json").exists()
    assert (output / "step-000/terminal.state").read_bytes() == b"1"
    assert not (output / "step-001").exists()


def test_decision_write_failure_prevents_every_controller_action(tmp_path, monkeypatch):
    import pokemon_red_completion.red_autonomous_player as module

    output = tmp_path / "run"
    state, snapshot, observe = _environment(output)
    original = module._record

    def fail_decision(path, payload):
        if path.name == "decision.json":
            raise OSError("disk failed")
        original(path, payload)

    monkeypatch.setattr(module, "_record", fail_decision)
    with pytest.raises(OSError, match="disk failed"):
        run_autonomous_options(
            model=_model(),
            output=output,
            snapshot=snapshot,
            observe=observe,
            seed=17,
            provenance={},
        )
    assert state["version"] == 0
    assert (output / "step-000/intent.json").exists()
    with pytest.raises(FileExistsError):
        run_autonomous_options(
            model=_model(),
            output=output,
            snapshot=snapshot,
            observe=observe,
            seed=17,
            provenance={},
        )


def test_teacher_safety_choice_is_persisted_but_never_executed(tmp_path):
    calls = []
    options = build_red_live_option_set(
        situation=_situation(resources=0.1, safety=1.0),
        binding_set=_ordinary_bindings(calls),
        supplements=(),
        model_feature_version=4,
        ordering_seed_sha256="b" * 64,
        economy_snapshot=EconomySnapshot(400, ()),
        target_cash=400,
    )
    output = tmp_path / "run"
    result = run_autonomous_options(
        model=_model(),
        output=output,
        snapshot=lambda: AutonomousSnapshot(b"same", {}, True),
        observe=lambda _: options,
        seed=17,
        provenance={},
    )
    assert result["executed_decisions"] == 0
    assert result["stop_reason"] == "safety_boundary_requires_separate_recovery"
    assert (output / "step-000/decision.json").exists()
    assert calls == []


def test_mutating_menu_is_rejected_before_model_query(tmp_path):
    output = tmp_path / "run"
    state, snapshot, observe = _environment(output)

    def bad_observe(ordinal):
        state["version"] += 1
        return observe(ordinal)

    result = run_autonomous_options(
        model=_model(),
        output=output,
        snapshot=snapshot,
        observe=bad_observe,
        seed=17,
        provenance={},
    )
    assert result["stop_reason"] == "menu_unavailable"
    assert not (output / "step-000/intent.json").exists()
    assert state["selected"] == []
