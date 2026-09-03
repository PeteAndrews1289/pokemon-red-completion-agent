from __future__ import annotations

import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.battle_expected_utility import (
    parse_expected_utility_record,
)
from pokemon_red_completion.battle_outcome_learning import (
    BattleOutcomeExample,
    BattleTurnOutcome,
)
from pokemon_red_completion.battle_semantics import FEATURE_NAMES, BattleFeatureBatch
from pokemon_red_completion.scenario_lab import ScenarioPartition

SCRIPT = runpy.run_path("scripts/collect_repeatable_battle_expected_utilities.py")
SCRIPT_GLOBALS = SCRIPT["_run"].__globals__


def _features() -> BattleFeatureBatch:
    vector = tuple(0.0 for _ in FEATURE_NAMES)
    return BattleFeatureBatch(
        feature_names=FEATURE_NAMES,
        candidate_vectors=(vector, vector),
        legal_mask=(True, True),
        current_pp=(10.0, 10.0),
        slot_indices=(0, 1),
    )


def _capture(name: str, state_character: str) -> SimpleNamespace:
    return SimpleNamespace(
        manifest=SimpleNamespace(
            partition=ScenarioPartition.TRAIN,
            capture_id=f"capture-{name}",
            state_sha256=state_character * 64,
            root_lineage_id=f"root-{name}",
        ),
        manifest_sha256=("f" if name == "one" else "e") * 64,
    )


def _collection(capture: SimpleNamespace, frame_target: int) -> SimpleNamespace:
    high = 3.0 if frame_target % 2 else 0.0
    outcomes = (
        BattleTurnOutcome(True, 0.5, 0.0, False, False, False, 1, frame_target + 10, frame_target),
        BattleTurnOutcome(
            True,
            1.0 if high else 0.0,
            0.0,
            bool(high),
            False,
            False,
            1,
            frame_target + 10,
            frame_target,
        ),
    )
    example = BattleOutcomeExample(
        root_lineage_id=capture.manifest.root_lineage_id,
        initial_state_sha256=capture.manifest.state_sha256,
        partition=capture.manifest.partition,
        features=_features(),
        outcomes=outcomes,
    )
    return SimpleNamespace(
        example=example,
        capture_id=capture.manifest.capture_id,
        manifest_sha256=capture.manifest_sha256,
    )


def _args(tmp_path: Path, *, two_captures: bool = False) -> SimpleNamespace:
    capture_dir = tmp_path / "captures"
    capture_dir.mkdir()
    names = ("one", "two") if two_captures else ("one",)
    for name in names:
        (capture_dir / f"{name}.state").write_bytes(name.encode("ascii"))
        (capture_dir / f"{name}.state.json").write_text("{}", encoding="ascii")
    return SimpleNamespace(
        rom=tmp_path / "red.gb",
        capture_dir=[capture_dir],
        output=tmp_path / "expected.jsonl",
        journal_dir=tmp_path / "journal",
        failure_report=tmp_path / "failures.json",
        frame_target=[2_048, 2_059],
    )


def _patch_common(monkeypatch: pytest.MonkeyPatch) -> None:
    captures = {
        "one": _capture("one", "a"),
        "two": _capture("two", "b"),
    }
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "detect_source_identity",
        lambda *_args, **_kwargs: SimpleNamespace(git_commit="c" * 40),
    )
    monkeypatch.setitem(SCRIPT_GLOBALS, "require_clean_source", lambda *_args: None)
    monkeypatch.setitem(SCRIPT_GLOBALS, "require_published_source", lambda *_args: None)
    monkeypatch.setitem(SCRIPT_GLOBALS, "resolve_rom_path", lambda path: path)
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "verify_rom",
        lambda _path: SimpleNamespace(sha256="d" * 64),
    )
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "open_battle_scenario_capture",
        lambda state, _manifest: captures[state.name.removesuffix(".state")],
    )


def test_collects_and_aggregates_complete_rng_schedule(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _args(tmp_path)
    _patch_common(monkeypatch)
    calls = 0

    def collect(capture: SimpleNamespace, **kwargs: int) -> SimpleNamespace:
        nonlocal calls
        calls += 1
        return _collection(capture, kwargs["minimum_pre_attack_frames"])

    monkeypatch.setitem(SCRIPT_GLOBALS, "collect_red_battle_outcome_example", collect)

    report = SCRIPT["_run"](args)

    assert report["trials_complete"] == 2
    assert report["examples"] == 1
    record = json.loads(args.output.read_text("ascii"))
    example = parse_expected_utility_record(record)
    assert example.pre_attack_frame_targets == (2_048, 2_059)
    assert example.expected_utilities == pytest.approx((0.5, 1.5))
    assert len(tuple(args.journal_dir.glob("*.claim.json"))) == 2
    assert len(tuple(args.journal_dir.glob("*.terminal.json"))) == 2

    repeated = SCRIPT["_run"](args)

    assert repeated == report
    assert calls == 2


def test_existing_output_without_complete_journal_fails_before_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _args(tmp_path)
    _patch_common(monkeypatch)
    args.output.write_text("partial", encoding="ascii")
    calls = 0

    def collect(_capture: SimpleNamespace, **_kwargs: int) -> SimpleNamespace:
        nonlocal calls
        calls += 1
        raise AssertionError("controller input must remain unreachable")

    monkeypatch.setitem(SCRIPT_GLOBALS, "collect_red_battle_outcome_example", collect)

    with pytest.raises(
        SCRIPT["RepeatableBattleExpectedUtilityCollectionError"],
        match="lacks one exact completed journal",
    ):
        SCRIPT["_run"](args)

    assert calls == 0


def test_restart_quarantines_claimed_trial_and_continues_untouched_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _args(tmp_path, two_captures=True)
    _patch_common(monkeypatch)
    first = True

    def interrupted(capture: SimpleNamespace, **kwargs: int) -> SimpleNamespace:
        nonlocal first
        if first:
            first = False
            raise KeyboardInterrupt
        return _collection(capture, kwargs["minimum_pre_attack_frames"])

    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "collect_red_battle_outcome_example",
        interrupted,
    )
    with pytest.raises(KeyboardInterrupt):
        SCRIPT["_run"](args)

    report = SCRIPT["_run"](args)

    assert report["trials_quarantined"] == 1
    assert report["captures_excluded"] == 1
    assert report["examples"] == 1
    failures = json.loads(args.failure_report.read_text("ascii"))
    assert failures["trial_failures"][0]["error_type"] == "InterruptedTrial"
    assert failures["excluded_captures"][0]["capture_id"] == "capture-one"
