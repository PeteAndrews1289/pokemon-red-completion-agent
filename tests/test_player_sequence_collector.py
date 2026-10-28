"""Prospective collection under the existing mocked actor, never native fitting."""

import json
from dataclasses import replace
from hashlib import sha256

import pytest
import test_red_continuous_player as continuous
from test_red_sequence_receipts import read

from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind
from pokemon_red_completion.living_dex_option_value import option_feature_names
from pokemon_red_completion.player_sequence_collector import SequenceTraceCollector
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_sequence_receipts import read_sequence_prefix


def collect(tmp_path, monkeypatch, *, horizon=2, fault=None, partition="development"):
    collector = SequenceTraceCollector(
        source_sha256=sha256(b"0").hexdigest(), partition=partition, horizon=horizon,
    )
    original_run = continuous.runner.run_autonomous_options
    original_binding = continuous._binding

    def run(**kwargs):
        return original_run(**kwargs, sequence_collector=collector)

    def binding(kind, **kwargs):
        b = original_binding(kind, **kwargs)
        return replace(b, story_objective_ref="private-story") if (
            kind is GoalKind.ADVANCE_STORY
        ) else b

    monkeypatch.setattr(continuous.runner, "run_autonomous_options", run)
    monkeypatch.setattr(continuous, "_binding", binding)
    continuous.test_setback_then_safety_recovery_then_fresh_choice(
        tmp_path, monkeypatch, fault, GoalKind.ADVANCE_STORY, GoalFailureReason.RESOURCE_LOST,
    )
    return tmp_path / "run", collector


def test_collector_captures_actual_preinput_features_and_attached_recovery(tmp_path, monkeypatch):
    root, collector = collect(tmp_path, monkeypatch)
    first = read(root / "sequence/anchor-000.json")
    second = read(root / "sequence/anchor-001.json")
    window = read(root / "sequence/window-000.json")
    assert len(first["features"]) == len(option_feature_names(6)) + 8
    assert first["previous_outcome_sha256"] == [] and first["features"][-8:] == [0.0] * 8
    assert len(second["previous_outcome_sha256"]) == 2
    assert second["features"][-8] == 0.5  # one prior story choice, not two including healing
    assert "private-story" not in json.dumps(first)
    assert window["complete_window"] and not window["training_eligible"]
    assert window["measurement"]["actions"] == 3
    assert window["measurement"]["frames"] == 30
    assert window["measurement"]["cash_debits"] == 60
    assert window["measurement"]["completed_quests"] == 0
    assert collector.finished
    assert read(root / "sequence/result.json")["projection_error"] is None


def test_window_waits_for_support_and_closes_before_next_model_execution(tmp_path, monkeypatch):
    original_record = continuous.runner._record

    def record(path, document):
        if path.name == "execution-started.json" and path.parent.name == "step-002":
            window = read(path.parent.parent / "sequence/window-000.json")
            assert window["measurement"]["actions"] == 2
            assert window["measurement"]["cash_debits"] == 40
        original_record(path, document)

    monkeypatch.setattr(continuous.runner, "_record", record)
    root, _ = collect(tmp_path, monkeypatch, horizon=1)
    windows = [read(p) for p in sorted((root / "sequence").glob("window-*.json"))]
    assert len(windows) == 2
    assert [w["first_model_choice"] for w in windows] == [0, 1]
    assert sum(w["measurement"]["actions"] for w in windows) == 3


def test_short_prefix_retains_cost_but_is_not_complete(tmp_path, monkeypatch):
    root, _ = collect(tmp_path, monkeypatch, horizon=4)
    window = read(root / "sequence/window-000.json")
    assert not window["complete_window"]
    assert window["measurement"]["end"] == "interrupted"
    assert window["measurement"]["cash_debits"] == 60
    assert window["measurement"]["observed_steps"] == 2


@pytest.mark.parametrize("fault", ["partial", "verdict", "unverified"])
def test_failed_projection_retains_raw_costs_without_inventing_complete_target(
    tmp_path, monkeypatch, fault,
):
    root, _ = collect(tmp_path, monkeypatch, fault=fault)
    result = read(root / "sequence/result.json")
    assert not result["training_eligible"]
    if fault in {"partial", "verdict"}:
        assert result["projection_error"] is not None and result["windows"] == 0
        assert result["unprojected_observed_costs"][0]["actions"] == 1
    else:
        assert not read(root / "sequence/window-000.json")["complete_window"]
    assert (root / "step-000/outcome.json").is_file()


def test_no_admitted_execution_produces_no_anchor_or_window(tmp_path, monkeypatch):
    root, _ = collect(tmp_path, monkeypatch, fault="budget")
    result = read(root / "sequence/result.json")
    assert result["anchors"] == result["windows"] == 0
    assert (root / "sequence/declaration.json").is_file()


def test_prefix_reader_does_not_open_future_steps_or_final_report(tmp_path, monkeypatch):
    root, _ = collect(tmp_path, monkeypatch)
    plan_sha = canonical_sha256(read(root / "plan.json"))
    digest = canonical_sha256(read(root / "step-000/outcome.json"))
    boundary = read(root / "step-000/outcome.json")["terminal_state_sha256"]
    for path in (root / "result.json", root / "step-001/outcome.json"):
        path.write_text("unreadable future")
    prefix = read_sequence_prefix(
        root, expected_plan_sha256=plan_sha, source_sha256=sha256(b"0").hexdigest(),
        outcome_sha256=(digest,), boundary_sha256=boundary,
    )
    assert len(prefix.choices) == 1 and prefix.choices[0].actions == 1


def test_changed_sealed_past_and_wrong_boundary_fail_closed(tmp_path, monkeypatch):
    root, _ = collect(tmp_path, monkeypatch)
    args = dict(
        expected_plan_sha256=canonical_sha256(read(root / "plan.json")),
        source_sha256=sha256(b"0").hexdigest(),
        outcome_sha256=(canonical_sha256(read(root / "step-000/outcome.json")),),
        boundary_sha256=read(root / "step-000/outcome.json")["terminal_state_sha256"],
    )
    with pytest.raises(ValueError, match="boundary"):
        read_sequence_prefix(root, **{**args, "boundary_sha256": "f" * 64})
    (root / "step-000/outcome.json").write_text("{}")
    with pytest.raises(ValueError, match="changed"):
        read_sequence_prefix(root, **args)


def test_train_annotation_alone_never_admits_or_promotes(tmp_path, monkeypatch):
    root, collector = collect(tmp_path, monkeypatch, partition="train")
    assert read(root / "sequence/declaration.json")["partition"] == "train"
    for path in (root / "sequence").glob("*.json"):
        assert read(path)["training_eligible"] is False
    result = read(root / "sequence/result.json")
    assert result["fit_calls"] == result["promotions"] == 0
    with pytest.raises(ValueError):
        collector.start(root)
    with pytest.raises(ValueError):
        collector.finish()


@pytest.mark.parametrize("kwargs", [
    {"horizon": 0}, {"horizon": 5}, {"horizon": True},
    {"partition": "sealed"}, {"source_sha256": "not-a-digest"},
])
def test_invalid_declaration_rejected(kwargs):
    with pytest.raises(ValueError):
        SequenceTraceCollector(**{
            "source_sha256": "a" * 64, "partition": "development", "horizon": 2, **kwargs,
        })
