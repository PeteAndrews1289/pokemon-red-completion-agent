from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import test_red_trainer_practice_episode as fixtures

from pokemon_red_completion import red_trainer_practice_episode as ep
from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_actions import BattleAction
from pokemon_red_completion.battle_control_features import CONTROL_CLASS_REFS, CONTROL_FEATURE_NAMES
from pokemon_red_completion.battle_control_model import BattleControlMLP
from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_outcome_learning import BattleTurnOutcome
from pokemon_red_completion.battle_scenario_capture import OBSERVATION_SCHEMA_V2
from pokemon_red_completion.battle_semantics import FEATURE_NAMES
from pokemon_red_completion.battle_switch_target import SWITCH_TARGET_FEATURE_NAMES
from pokemon_red_completion.battle_switch_target_model import BattleSwitchTargetMLP
from pokemon_red_completion.red_trainer_practice_features import (
    MOVE_FEATURE_NAMES,
    MOVE_SCHEMA_ID,
    SWITCH_FEATURE_NAMES_V2,
    SWITCH_SCHEMA_ID,
)
from pokemon_red_completion.red_trainer_practice_fit import (
    CONTROL_ACTION_FEATURE_NAMES,
    CONTROL_ACTION_SCHEMA_ID,
    TrainerPracticeThreeHeadModel,
)
from pokemon_red_completion.red_trainer_practice_head import TrainerHeadModel
from pokemon_red_completion.red_trainer_practice_log import verify_trainer_practice_event_log
from pokemon_red_completion.scenario_lab import ScenarioPartition

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_red_trainer_practice_model as runner  # noqa: E402


def test_model_runner_requires_exact_bound_bytes(tmp_path):
    path = tmp_path / "private-model.json"
    path.write_bytes(b"{}")
    binding = {"path": str(path), "sha256": hashlib.sha256(b"{}").hexdigest()}
    assert runner._bound_file(binding, "model") == b"{}"
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="model hash differs"):
        runner._bound_file(binding, "model")


def test_model_runner_rejects_wrong_plan_before_cartridge_access():
    with pytest.raises(ValueError, match="plan differs"):
        runner._authenticate({"schema": "not-a-trainer-model-plan"})


@pytest.mark.parametrize(
    ("actions", "seconds"),
    [
        (None, 1),
        (1, None),
        (True, 1),
        (1, False),
        ("1", 1),
        (1, "1"),
        (0, 1),
        (1, 0),
        (-1, 1),
        (1, -1),
        (5001, 1),
        (1, 181),
        (1, float("inf")),
    ],
)
def test_model_runner_rejects_malformed_action_wall_pair_before_bound_reads(
    monkeypatch, actions, seconds
):
    plan = {
        "schema": runner.SCHEMA,
        "maximum_controller_actions": actions,
        "maximum_wall_seconds": seconds,
    }
    bound_reads = []
    monkeypatch.setattr(runner, "_bound_file", lambda *_args: bound_reads.append(True))

    with pytest.raises(ValueError, match="action and wall budgets differ"):
        runner._authenticate(plan)

    assert bound_reads == []


def test_model_runner_loads_all_three_heads_and_rejects_test_partition(
    tmp_path, monkeypatch
):
    move = MaskedMLPMoveRanker(
        feature_names=FEATURE_NAMES,
        input_weights=np.zeros((2, len(FEATURE_NAMES))),
        hidden_bias=np.zeros(2), output_weights=np.zeros(2), output_bias=0.0,
    )
    control = BattleControlMLP(
        feature_names=CONTROL_FEATURE_NAMES,
        class_refs=(CONTROL_CLASS_REFS[0], CONTROL_CLASS_REFS[5]),
        input_weights=np.zeros((2, len(CONTROL_FEATURE_NAMES))),
        hidden_bias=np.zeros(2), output_weights=np.zeros((2, 2)), output_bias=np.array([1, 0]),
    )
    switch = BattleSwitchTargetMLP(
        weights1=np.zeros((len(SWITCH_TARGET_FEATURE_NAMES), 2)),
        bias1=np.zeros(2), weights2=np.zeros(2),
        feature_mean=np.zeros(len(SWITCH_TARGET_FEATURE_NAMES)),
        feature_scale=np.ones(len(SWITCH_TARGET_FEATURE_NAMES)), training_seed=0,
    )
    payloads = {
        "ROM": b"rom",
        "move model": json.dumps(move.to_dict()).encode(),
        "control model": json.dumps(control.to_dict()).encode(),
        "switch model": json.dumps(switch.to_dict()).encode(),
        "capture state": b"state", "capture manifest": b"manifest",
    }
    monkeypatch.setattr(runner, "_bound_file", lambda _value, label: payloads[label])
    monkeypatch.setattr(runner, "ROM_SHA256", hashlib.sha256(b"rom").hexdigest())
    monkeypatch.setattr(
        runner.subprocess, "check_output",
        lambda args, **_kwargs: b"" if "status" in args else b"commit\n",
    )
    capture = SimpleNamespace(manifest=SimpleNamespace(partition=ScenarioPartition.TRAIN))
    monkeypatch.setattr(runner, "open_battle_scenario_capture", lambda *_args: capture)
    plan = {
        "schema": runner.SCHEMA, "source_commit": "commit", "rom": {},
        "move_model": {}, "control_model": {}, "switch_model": {},
        "capture_state": {"path": "state"}, "capture_manifest": {"path": "manifest"},
        "max_decisions": 2, "maximum_frames": 1000,
        "output": str(tmp_path / "new-output"),
    }
    _plan, _capture, loaded = runner._authenticate(plan)
    runner._authenticate(
        {**plan, "maximum_controller_actions": 5000, "maximum_wall_seconds": 180}
    )
    runner._authenticate({**plan, "max_decisions": 160, "maximum_frames": 240000})
    for field, value in (("max_decisions", 161), ("maximum_frames", 240001)):
        with pytest.raises(ValueError, match="budget differs"):
            runner._authenticate({**plan, field: value})
    capture.manifest.partition = ScenarioPartition.DEVELOPMENT
    with pytest.raises(ValueError, match="budget differs"):
        runner._authenticate({**plan, "max_decisions": 160})
    with pytest.raises(ValueError, match="budget differs"):
        runner._authenticate({**plan, "maximum_frames": 240000})
    capture.manifest.partition = ScenarioPartition.TRAIN
    loaded_move, loaded_control, loaded_switch = loaded
    assert loaded_move.feature_names == FEATURE_NAMES
    assert loaded_control.class_refs == (CONTROL_CLASS_REFS[0], CONTROL_CLASS_REFS[5])
    assert loaded_switch.training_seed == 0
    capture.manifest.partition = ScenarioPartition.TEST
    with pytest.raises(ValueError, match="partition is unavailable"):
        runner._authenticate(plan)


def test_outcome_runner_requires_rich_observation_and_disjoint_development(
    tmp_path, monkeypatch
):
    def head(schema, names):
        return TrainerHeadModel(
            schema, names, np.zeros((len(names), 2)), np.zeros(2), np.zeros(2), 0
        )

    model = TrainerPracticeThreeHeadModel(
        head(MOVE_SCHEMA_ID, MOVE_FEATURE_NAMES),
        head(CONTROL_ACTION_SCHEMA_ID, CONTROL_ACTION_FEATURE_NAMES),
        head(SWITCH_SCHEMA_ID, SWITCH_FEATURE_NAMES_V2),
        ("train-capture",), ("train-root",),
    )
    payloads = {
        "ROM": b"rom", "outcome model": json.dumps(model.to_dict()).encode(),
        "capture state": b"state", "capture manifest": b"manifest",
    }
    monkeypatch.setattr(runner, "_bound_file", lambda _value, label: payloads[label])
    monkeypatch.setattr(runner, "ROM_SHA256", hashlib.sha256(b"rom").hexdigest())
    monkeypatch.setattr(
        runner.subprocess, "check_output",
        lambda args, **_kwargs: b"" if "status" in args else b"commit\n",
    )
    manifest = SimpleNamespace(
        partition=ScenarioPartition.DEVELOPMENT,
        observation_schema=OBSERVATION_SCHEMA_V2,
        root_lineage_id="train-root",
    )
    capture = SimpleNamespace(manifest=manifest)
    monkeypatch.setattr(runner, "open_battle_scenario_capture", lambda *_args: capture)
    plan = {
        "schema": runner.OUTCOME_SCHEMA, "source_commit": "commit", "rom": {},
        "outcome_model": {}, "capture_state": {"path": "state"},
        "capture_manifest": {"path": "manifest"}, "max_decisions": 2,
        "maximum_frames": 1000, "output": str(tmp_path / "new-output"),
    }
    with pytest.raises(ValueError, match="overlaps"):
        runner._authenticate(plan)
    manifest.root_lineage_id = "disjoint-root"
    _plan, _capture, loaded = runner._authenticate(plan)
    runner._authenticate(
        {**plan, "maximum_controller_actions": 1, "maximum_wall_seconds": 1}
    )
    assert isinstance(loaded, TrainerPracticeThreeHeadModel)
    legacy = TrainerPracticeThreeHeadModel(
        model.move, model.control, model.switch,
        ("legacy-capture",), ("red-goal-v1-001-advance_story-train-01",),
    )
    payloads["outcome model"] = json.dumps(legacy.to_dict()).encode()
    manifest.root_lineage_id = "red-goal-v1-071-recover_control-validation-02"
    with pytest.raises(ValueError, match="overlaps"):
        runner._authenticate(plan)
    manifest.root_lineage_id = "red-goal-root-another-assignment-hash"
    with pytest.raises(ValueError, match="overlaps"):
        runner._authenticate(plan)
    manifest.root_lineage_id = "disjoint-root"
    payloads["outcome model"] = json.dumps(model.to_dict()).encode()
    plan["opening_idle_frames"] = 8
    runner._authenticate(plan)
    plan["opening_idle_frames"] = 13
    with pytest.raises(ValueError, match="budget differs"):
        runner._authenticate(plan)
    plan["opening_idle_frames"] = 0
    manifest.observation_schema = None
    with pytest.raises(ValueError, match="actor-visible battle stats"):
        runner._authenticate(plan)


def test_runner_time_failure_retains_released_endpoint_and_budget_receipts(
    tmp_path, monkeypatch
):
    def head(schema, names):
        return TrainerHeadModel(
            schema, names, np.zeros((len(names), 2)), np.zeros(2), np.zeros(2), 0
        )

    model = TrainerPracticeThreeHeadModel(
        head(MOVE_SCHEMA_ID, MOVE_FEATURE_NAMES),
        head(CONTROL_ACTION_SCHEMA_ID, CONTROL_ACTION_FEATURE_NAMES),
        head(SWITCH_SCHEMA_ID, SWITCH_FEATURE_NAMES_V2),
        ("train-capture",),
        ("train-root",),
    )
    output = tmp_path / "output"
    plan = {
        "schema": runner.OUTCOME_SCHEMA,
        "source_commit": "c" * 40,
        "rom": {"path": str(tmp_path / "rom.gb"), "sha256": "r" * 64},
        "outcome_model": {"sha256": "m" * 64},
        "max_decisions": 2,
        "maximum_frames": 100,
        "maximum_controller_actions": 1,
        "maximum_wall_seconds": 1,
        "output": str(output),
    }
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan))
    manifest = SimpleNamespace(
        capture_id="synthetic-capture",
        root_lineage_id="synthetic-root",
        partition=ScenarioPartition.DEVELOPMENT,
    )
    capture = SimpleNamespace(manifest=manifest, manifest_sha256="f" * 64)
    monkeypatch.setattr(runner, "_authenticate", lambda _plan: (plan, capture, model))
    monkeypatch.setattr(
        runner, "RedPracticeCartridge", lambda _rom: SimpleNamespace(public_base_stats={})
    )
    monkeypatch.setattr(runner, "_bound_file", lambda *_args: b"synthetic-rom")
    calls = []

    class Emulator:
        frame_count = 10

        def __init__(self):
            self.pressed_buttons = set()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            calls.append("close")
            return False

        def press(self, button):
            calls.append(("press", button))
            self.pressed_buttons.add(button)

        def release(self, button):
            calls.append(("release", button))
            self.pressed_buttons.remove(button)

        def tick(self, frames):
            calls.append(("tick", frames))
            self.frame_count += frames

        def save_state_bytes(self):
            calls.append(("save", tuple(sorted(self.pressed_buttons))))
            return b"synthetic-final-state"

    monkeypatch.setattr(runner, "PyBoyAdapter", lambda *_args, **_kwargs: Emulator())

    def fail_during_tick(_capture, *, session_factory, action_executor, **_kwargs):
        with session_factory():
            action_executor.execute(MacroAction(MacroActionKind.CONFIRM))

    monkeypatch.setattr(runner, "run_red_trainer_practice_episode", fail_during_tick)
    readings = iter((0.0, 0.0, 0.5, 1.0, 1.1))

    with pytest.raises(runner.ControllerWallTimeBudgetExhausted):
        runner.run(plan_path, monotonic_clock=lambda: next(readings))

    assert calls == [
        ("press", "a"),
        ("release", "a"),
        ("save", ()),
        "close",
    ]
    endpoint = json.loads((output / "final-state.json").read_bytes())
    failure = json.loads((output / "failure.json").read_bytes())
    verification = json.loads((output / "event-log-verification.json").read_bytes())
    assert hashlib.sha256((output / "final.state").read_bytes()).hexdigest() == endpoint[
        "state_sha256"
    ]
    assert endpoint["controller_actions_attempted"] == 1
    assert endpoint["controller_actions_completed"] == 0
    assert endpoint["wall_elapsed_seconds"] == 1.1
    assert endpoint["frame_delta"] == 0
    assert endpoint["pressed_buttons"] == []
    assert endpoint["continuation_qualified"] is False
    assert failure["reason"] == "controller_wall_time_budget_exhausted"
    assert failure["maximum_wall_seconds"] == 1
    assert verification["complete"] is True
    assert verification["terminal_event"] == "run_failed"
    assert not (output / "outcome.json").exists()


def test_runner_retains_budget_cause_when_endpoint_receipt_write_fails(tmp_path, monkeypatch):
    def head(schema, names):
        return TrainerHeadModel(
            schema, names, np.zeros((len(names), 2)), np.zeros(2), np.zeros(2), 0
        )

    model = TrainerPracticeThreeHeadModel(
        head(MOVE_SCHEMA_ID, MOVE_FEATURE_NAMES),
        head(CONTROL_ACTION_SCHEMA_ID, CONTROL_ACTION_FEATURE_NAMES),
        head(SWITCH_SCHEMA_ID, SWITCH_FEATURE_NAMES_V2),
        ("train-capture",), ("train-root",),
    )
    output = tmp_path / "output"
    plan = {
        "schema": runner.OUTCOME_SCHEMA,
        "source_commit": "c" * 40,
        "rom": {"path": str(tmp_path / "rom.gb"), "sha256": "r" * 64},
        "outcome_model": {"sha256": "m" * 64},
        "max_decisions": 2,
        "maximum_frames": 100,
        "maximum_controller_actions": 1,
        "maximum_wall_seconds": 10,
        "output": str(output),
    }
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan))
    capture = SimpleNamespace(
        manifest=SimpleNamespace(
            capture_id="synthetic-capture",
            root_lineage_id="synthetic-root",
            partition=ScenarioPartition.DEVELOPMENT,
        ),
        manifest_sha256="f" * 64,
    )
    monkeypatch.setattr(runner, "_authenticate", lambda _plan: (plan, capture, model))
    monkeypatch.setattr(
        runner, "RedPracticeCartridge", lambda _rom: SimpleNamespace(public_base_stats={})
    )
    monkeypatch.setattr(runner, "_bound_file", lambda *_args: b"synthetic-rom")

    class Emulator:
        frame_count = 10

        def __init__(self):
            self.pressed_buttons = set()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def press(self, button):
            self.pressed_buttons.add(button)

        def release(self, button):
            self.pressed_buttons.remove(button)

        def tick(self, frames):
            self.frame_count += frames

        def save_state_bytes(self):
            return b"synthetic-final-state"

    monkeypatch.setattr(runner, "PyBoyAdapter", lambda *_args, **_kwargs: Emulator())

    def exhaust_actions(_capture, *, session_factory, action_executor, **_kwargs):
        with session_factory():
            action_executor.execute(MacroAction(MacroActionKind.CONFIRM))
            action_executor.execute(MacroAction(MacroActionKind.CONFIRM))

    monkeypatch.setattr(runner, "run_red_trainer_practice_episode", exhaust_actions)
    record = runner._record

    def fail_endpoint_receipt(path, value):
        if path.name == "final-state.json":
            raise OSError("synthetic endpoint receipt failure")
        record(path, value)

    monkeypatch.setattr(runner, "_record", fail_endpoint_receipt)

    with pytest.raises(OSError, match="synthetic endpoint receipt failure"):
        runner.run(plan_path, monotonic_clock=lambda: 0.0)

    failure = json.loads((output / "failure.json").read_bytes())
    verification = json.loads((output / "event-log-verification.json").read_bytes())
    terminal = json.loads(
        sorted((output / "events").glob("event-*.json"))[-2].read_bytes()
    )["payload"]
    assert failure["reason"] == "controller_action_budget_exhausted"
    assert failure["error_type"] == "OSError"
    assert failure["budget_failure"]["error_type"] == "ControllerActionBudgetExhausted"
    assert failure["secondary_failure"]["error_type"] == "OSError"
    assert failure["controller_actions_attempted"] == 1
    assert failure["controller_actions_completed"] == 1
    assert failure["frame_delta"] == 2
    assert terminal["event"] == "budget_failure_retained"
    assert verification["complete"] is True
    assert not (output / "final-state.json").exists()
    assert not (output / "outcome.json").exists()


def test_budget_failure_follows_typed_causes_and_terminates_on_cycles():
    budget = runner.ControllerWallTimeBudgetExhausted(
        maximum_wall_seconds=1, elapsed_seconds=1.0
    )
    release = RuntimeError("release")
    cleanup = RuntimeError("cleanup")
    release.__context__ = budget
    cleanup.__cause__ = release
    budget.__context__ = cleanup
    assert runner._budget_failure(cleanup) is budget
    release.__context__ = cleanup
    assert runner._budget_failure(cleanup) is None
    assert runner._budget_failure(RuntimeError("ControllerWallTimeBudgetExhausted")) is None


# Ported from the independent c01 rejection probes; real runner and episode wiring.
def _compound_failure_case(
    tmp_path,
    name,
    *,
    policy_path="main",
    deadline=None,
    budget=None,
    secondary=None,
    release_once=False,
    held=False,
):
    root = tmp_path / name
    root.mkdir()
    with pytest.MonkeyPatch.context() as mp:
        capture = fixtures._capture(root)

        def head(schema, names):
            return TrainerHeadModel(
                schema, names, np.zeros((len(names), 2)), np.zeros(2), np.zeros(2), 0
            )

        model = TrainerPracticeThreeHeadModel(
            head(MOVE_SCHEMA_ID, MOVE_FEATURE_NAMES),
            head(CONTROL_ACTION_SCHEMA_ID, CONTROL_ACTION_FEATURE_NAMES),
            head(SWITCH_SCHEMA_ID, SWITCH_FEATURE_NAMES_V2),
            ("train-capture",),
            ("train-root",),
        )
        output = root / "output"
        plan = dict(
            schema=runner.OUTCOME_SCHEMA,
            source_commit="c" * 40,
            rom={"path": str(root / "synthetic.gb"), "sha256": "r" * 64},
            outcome_model={"sha256": "m" * 64},
            max_decisions=1,
            maximum_frames=100,
            maximum_controller_actions=1 if budget == "action" else 10,
            maximum_wall_seconds=1,
            output=str(output),
        )
        clock, calls, choices, chains = [0.0], [], [], []

        class Emulator(fixtures.Session):
            def __init__(self):
                super().__init__()
                self.frame_count = 100
                self.pressed_buttons = {"b"} if held else set()
                self.release_failures = 0
                if policy_path == "forced":
                    self.raw = replace(self.raw, party_hp=(0, 35), active_party_hp=0)

            def press(self, button):
                calls.append(["press", button])
                self.pressed_buttons.add(button)
                if budget == "wall" and secondary == "release":
                    clock[0] = 1.0

            def release(self, button):
                calls.append(["release", button])
                if (
                    secondary == "release"
                    and (budget == "wall" or button == "b")
                    and (not release_once or self.release_failures == 0)
                ):
                    self.release_failures += 1
                    raise RuntimeError("synthetic release failure")
                self.pressed_buttons.remove(button)

            def tick(self, frames):
                calls.append(["tick", frames])
                self.frame_count += frames

            def save_state_bytes(self):
                calls.append(["save", sorted(self.pressed_buttons)])
                if secondary == "save":
                    raise RuntimeError("synthetic snapshot failure")
                return b"synthetic-integration-audit-endpoint"

            def __exit__(self, *args):
                calls.append(["close"])
                return False

        emulator = Emulator()
        if policy_path == "prompt":
            emulator.trainer_switch_prompt_visible = lambda raw: True

        class Policy:
            policy_id = "synthetic-independent-policy"

            def choose_main(self, *args):
                choices.append(["main", clock[0]])
                return BattleAction.move(1)

            def choose_switch(self, *args, **kwargs):
                choices.append(["switch", clock[0]])
                return 2

        mp.setattr(runner, "_authenticate", lambda unused: (plan, capture, model))
        mp.setattr(runner, "_bound_file", lambda *args: b"synthetic-rom")
        mp.setattr(
            runner, "RedPracticeCartridge", lambda *args: SimpleNamespace(public_base_stats={})
        )
        mp.setattr(runner, "RedTrainerPracticeOutcomePolicy", lambda **kwargs: Policy())
        mp.setattr(runner, "PyBoyAdapter", lambda *args, **kwargs: emulator)
        mp.setattr(ep, "PokemonRedStateReader", lambda loaded: loaded)
        snap = SimpleNamespace(to_dict=lambda: {"features": {"battle": {"kind": "trainer"}}})
        mp.setattr(
            ep.PokemonRedObservationEncoder,
            "from_state_reader",
            lambda *args, **kwargs: SimpleNamespace(snapshot_from_raw=lambda raw: snap),
        )
        mp.setattr(ep, "prepare_red_battle_scenario", lambda *args, **kwargs: fixtures._prepared())
        mp.setattr(ep, "canonical_sha256", lambda value: "b" * 64)
        mp.setattr(
            ep,
            "project_red_battle_turn_outcome",
            lambda result: BattleTurnOutcome(True, 1.0, 0.0, True, False, True, 2, 500, 0),
        )

        def execute(reader, actions, **kwargs):
            actions.execute(MacroAction(MacroActionKind.CONFIRM))
            if budget == "wall":
                clock[0] = 1.0
            if budget is not None:
                actions.execute(MacroAction(MacroActionKind.CONFIRM))
            emulator.raw = replace(emulator.raw, battle_state=0)
            return object()

        mp.setattr(ep, "execute_bounded_battle_move_turn", execute)
        mp.setattr(
            ep,
            "switch_active_battler",
            lambda actions, *args, **kwargs: actions.execute(MacroAction(MacroActionKind.CONFIRM)),
        )
        emit = runner.TrainerPracticeEventLog.emit

        def emit_and_expire(self, event):
            emit(self, event)
            target = "model_input_prepared" if policy_path == "main" else "decision_started"
            if deadline is not None and event["event"] == target:
                clock[0] = deadline

        mp.setattr(runner.TrainerPracticeEventLog, "emit", emit_and_expire)
        record = runner._record

        def record_or_fail(path, value):
            if secondary == "receipt" and path.name == "final-state.json":
                raise OSError("synthetic endpoint receipt failure")
            return record(path, value)

        mp.setattr(runner, "_record", record_or_fail)
        plan_path = root / "plan.json"
        plan_path.write_text(json.dumps(plan))
        error = None
        try:
            runner.run(plan_path, monotonic_clock=lambda: clock[0])
        except Exception as exc:
            error = type(exc).__name__
            cursor = exc
            while cursor is not None:
                chains.append({"type": type(cursor).__name__, "message": str(cursor)})
                cursor = cursor.__context__

        def read(filename):
            path = output / filename
            return json.loads(path.read_bytes()) if path.exists() else None

        failure, endpoint, outcome, verification = [
            read(n)
            for n in (
                "failure.json",
                "final-state.json",
                "outcome.json",
                "event-log-verification.json",
            )
        ]
        events = [
            json.loads(p.read_bytes())["payload"]
            for p in sorted((output / "events").glob("event-*.json"))
        ]
        verified = verify_trainer_practice_event_log(output / "events")
        violations = []

        def require(condition, message):
            if not condition:
                violations.append(message)

        require(error is not None, "failure must propagate")
        require(outcome is None, "must not fabricate outcome")
        require(
            verified["complete"] is True and verified["terminal_event"] == "run_failed",
            "hash chain must verify as failed",
        )
        require(
            verification == verified, "persisted verification must match independent verification"
        )
        if endpoint:
            require(
                endpoint["state_sha256"]
                == hashlib.sha256((output / "final.state").read_bytes()).hexdigest(),
                "endpoint hash must match",
            )
            require(
                endpoint["episode_returned"] is False
                and endpoint["continuation_qualified"] is False,
                "endpoint cannot claim normal/qualified return",
            )
            require(
                endpoint["pressed_buttons"] == sorted(emulator.pressed_buttons),
                "endpoint must record actual held inputs",
            )
        if deadline is not None:
            require(choices == [], "no policy callback at or after deadline")
            require(
                not any(c[0] in ("press", "tick") for c in calls),
                "no controller actions at or after deadline",
            )
            require(error == "ControllerWallTimeBudgetExhausted", "typed deadline error required")
            require(
                endpoint is not None
                and endpoint["controller_actions_attempted"] == 0
                and endpoint["frame_delta"] == 0,
                "truthful zero-action endpoint required",
            )
        if budget:
            expected = (
                "ControllerActionBudgetExhausted"
                if budget == "action"
                else "ControllerWallTimeBudgetExhausted"
            )
            reason = (
                "controller_action_budget_exhausted"
                if budget == "action"
                else "controller_wall_time_budget_exhausted"
            )
            require(
                failure.get("budget_failure", {}).get("error_type") == expected,
                "original typed budget cause absent from failure.json",
            )
            require(
                failure.get("reason") == reason, "original budget reason absent from failure.json"
            )
            require(
                failure.get("secondary_failure", {}).get("error_type") == error,
                "secondary cause absent from failure.json",
            )
            retained = [e for e in events if e["event"] == "budget_failure_retained"]
            require(
                len(retained) == 1 and retained[0]["budget_failure"]["error_type"] == expected,
                "both causes absent from hash-chained budget event",
            )
            completed = 0 if budget == "wall" and secondary == "release" else 1
            require(
                failure.get("controller_actions_attempted") == 1
                and failure.get("controller_actions_completed") == completed,
                "attempted/completed accounting differs",
            )
            require(
                failure.get("frames") == emulator.frame_count
                and failure.get("frame_delta") == emulator.frame_count - 100,
                "frame accounting differs",
            )
            require(failure.get("wall_elapsed_seconds") == clock[0], "elapsed accounting differs")
            require(
                failure.get("pressed_buttons") == sorted(emulator.pressed_buttons),
                "last obtainable pressed-button state absent or wrong",
            )
            if secondary in ("save", "receipt") or (secondary == "release" and not release_once):
                require(endpoint is None, "failed persistence cannot claim endpoint receipt")
            require(
                error == ("OSError" if secondary == "receipt" else "RuntimeError"),
                "secondary error must propagate",
            )
        result = dict(
            name=name,
            configuration=dict(
                policy_path=policy_path,
                deadline=deadline,
                budget=budget,
                secondary=secondary,
                release_once=release_once,
                held=held,
            ),
            error=error,
            exception_context_chain=chains,
            policy_entries=choices,
            calls=calls,
            actual_pressed_buttons=sorted(emulator.pressed_buttons),
            failure=failure,
            endpoint=endpoint,
            state_file_exists=(output / "final.state").exists(),
            outcome=outcome,
            verification=verification,
            events=events,
            violations=violations,
        )
        (root / "observation.json").write_text(json.dumps(result, indent=2) + "\n")
        print(
            json.dumps(
                {
                    "name": name,
                    "violations": violations,
                    "reason": failure.get("reason"),
                    "error_chain": [c["type"] for c in chains],
                }
            ),
            flush=True,
        )
        return result


@pytest.mark.parametrize("policy_path", ["main", "prompt", "forced"])
@pytest.mark.parametrize("deadline", [1.0, 1.5])
def test_runner_admission_after_logging_deadline(tmp_path, policy_path, deadline):
    result = _compound_failure_case(
        tmp_path, "admission", policy_path=policy_path, deadline=deadline
    )
    assert result["violations"] == []


@pytest.mark.parametrize(
    ("budget", "secondary", "release_once", "held"),
    [
        ("action", "release", False, True),
        ("action", "save", False, False),
        ("action", "receipt", False, False),
        ("wall", "release", False, False),
        ("wall", "save", False, False),
        ("wall", "receipt", False, False),
        ("wall", "release", True, False),
        ("action", "save", False, True),
    ],
)
def test_runner_compound_failure_matrix(tmp_path, budget, secondary, release_once, held):
    result = _compound_failure_case(
        tmp_path,
        "compound",
        budget=budget,
        secondary=secondary,
        release_once=release_once,
        held=held,
    )
    assert result["violations"] == []
