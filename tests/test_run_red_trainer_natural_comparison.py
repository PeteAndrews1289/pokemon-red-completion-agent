"""ROM-free checks for the natural DEVELOPMENT comparison boundary."""

from __future__ import annotations

import hashlib
import json
import sys
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.scenario_lab import ScenarioPartition

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_red_trainer_natural_comparison as comparison  # noqa: E402


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def _setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Namespace:
    rom = tmp_path / "red.gb"
    rom.write_bytes(b"private-test-rom")
    monkeypatch.setattr(comparison, "ROM_SHA256", hashlib.sha256(rom.read_bytes()).hexdigest())
    monkeypatch.setattr(
        comparison.subprocess,
        "check_output",
        lambda args, **_kwargs: b"" if "status" in args else b"test-commit\n",
    )
    model = tmp_path / "fit" / "model.json"
    _write(model, {})
    _write(
        model.parent / "receipt.json",
        {
            "qualification_tier": "independent_root_train",
            "independent_train_supply_gate_passed": True,
            "distinct_upstream_train_roots": 4,
            "scenario_count": 16,
            "model_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
        },
    )
    monkeypatch.setattr(
        comparison.TrainerPracticeThreeHeadModel,
        "from_dict",
        lambda _value: SimpleNamespace(train_root_ids=("fresh-1", "fresh-2")),
    )
    capture = tmp_path / "capture"
    capture.mkdir()
    (capture / "source.state").write_bytes(b"state")
    (capture / "source.state.json").write_bytes(b"{}")
    opened = SimpleNamespace(
        manifest=SimpleNamespace(
            partition=ScenarioPartition.DEVELOPMENT,
            root_lineage_id="red-goal-v1-071-recover_control-validation-02",
            capture_id="natural-development",
        ),
        manifest_sha256="a" * 64,
    )
    monkeypatch.setattr(comparison, "open_battle_scenario_capture", lambda *_args: opened)
    frozen_model = tmp_path / "frozen-model.json"
    _write(frozen_model, {})
    return Namespace(
        rom=rom,
        fit=model.parent,
        capture=capture,
        frozen_model=frozen_model,
        output=tmp_path / "comparison",
    )


def test_natural_comparison_freezes_all_arms_before_development_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args = _setup(tmp_path, monkeypatch)
    calls: list[tuple[str, bool]] = []

    def run_arm(plan: Path, *, check_only: bool = False) -> None:
        name = plan.stem.removesuffix("-plan")
        calls.append((name, check_only))
        if check_only:
            return
        for arm in ("fixed", "frozen", "challenger"):
            assert (args.output / f"{arm}-plan.json").is_file()
        output = args.output / name
        output.mkdir()
        _write(
            output / "outcome.json",
            {
                "battle_won": True,
                "stop_reason": "battle_won",
                "decision_count": 2,
                "action_counts": {"attack": 2},
                "teacher_queries": 0,
                "metrics": {
                    "invalid_action_failures": 0,
                    "opponent_faints": 1,
                    "party_faints": 0,
                    "party_hp_lost": 0,
                    "attack_turn_utility_sum": 3.0,
                    "policy_latency_ns_mean": 100,
                },
            },
        )
        _write(
            output / "event-log-verification.json",
            {
                "complete": True,
                "failed_runs": 0,
                "incomplete_decisions": 0,
                "event_count": 8,
            },
        )

    monkeypatch.setattr(comparison.baseline, "run", run_arm)
    monkeypatch.setattr(comparison.challenger, "run", run_arm)
    summary = comparison.run(args)
    assert calls == [
        ("fixed", True),
        ("frozen", True),
        ("challenger", True),
        ("fixed", False),
        ("frozen", False),
        ("challenger", False),
    ]
    assert summary["model_updates"] == 0
    assert summary["authority_promotions"] == 0
    assert all(result["event_log_complete"] for result in summary["results"].values())


def test_natural_comparison_rejects_train_overlap_before_creating_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        comparison,
        "open_battle_scenario_capture",
        lambda *_args: SimpleNamespace(
            manifest=SimpleNamespace(
                partition=ScenarioPartition.DEVELOPMENT,
                root_lineage_id="fresh-1",
            )
        ),
    )
    with pytest.raises(ValueError, match="overlaps TRAIN ancestry"):
        comparison.run(args)
    assert not args.output.exists()


def test_natural_comparison_rejects_unqualified_fit_before_opening_development(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args = _setup(tmp_path, monkeypatch)
    receipt = args.fit / "receipt.json"
    value = json.loads(receipt.read_text())
    value["independent_train_supply_gate_passed"] = False
    _write(receipt, value)
    monkeypatch.setattr(
        comparison,
        "open_battle_scenario_capture",
        lambda *_args: pytest.fail("DEVELOPMENT was opened before fit admission"),
    )
    with pytest.raises(ValueError, match="not TRAIN-qualified"):
        comparison.run(args)
    assert not args.output.exists()


def test_retention_result_cannot_bypass_qualification_with_true_boolean(tmp_path, monkeypatch):
    args = _setup(tmp_path, monkeypatch)
    _write(args.fit / "plan.json", {})
    _write(args.fit / "result.json", {"model": {"sha256": "wrong"}, "train_qualified": True})
    monkeypatch.setattr(
        comparison,
        "open_battle_scenario_capture",
        lambda *_: pytest.fail("unqualified DEVELOPMENT access"),
    )
    with pytest.raises(ValueError, match="unchanged TRAIN gates"):
        comparison.run(args)


def test_champion_capture_is_separate_natural_boundary_not_consumed_lance():
    from capture_red_league_development_sources import SOURCES

    from pokemon_red_completion.observation import EventFlag, MapId

    champion = SOURCES["champion"]
    assert champion["file"] == "portable-loop-post-lance.state"
    assert champion["map"] == MapId.CHAMPIONS_ROOM
    assert champion["required_event"] == EventFlag.BEAT_LANCE
    assert champion["unplayed_event"] == EventFlag.BEAT_CHAMPION_RIVAL
    assert champion["trigger"] == "automatic_dialogue"
    assert len(champion["party"]) == 6
    assert champion["sha256"] != SOURCES["lance"]["sha256"]


def test_winning_does_not_override_worse_natural_cost_or_promote():
    arm = {
        "battle_won": True,
        "event_log_complete": True,
        "teacher_queries": 0,
        "invalid_actions": 0,
        "party_faints": 0,
        "party_hp_lost": 156,
        "decision_count": 16,
    }
    summary = {
        "model_sha256": "test",
        "capture_id": "test",
        "results": {
            "fixed": arm,
            "frozen": arm,
            "challenger": {**arm, "party_faints": 1, "party_hp_lost": 389, "decision_count": 22},
        },
    }
    verdict = comparison.comparison_verdict(summary)
    assert verdict["checks"]["candidate_won"]
    assert not verdict["natural_comparison_passed"]
    assert not verdict["final_player_ready"]
    summary["results"]["challenger"] = {**arm, "decision_count": 15}
    verdict = comparison.comparison_verdict(summary)
    assert verdict["natural_comparison_passed"]
    assert not verdict["final_player_ready"]
