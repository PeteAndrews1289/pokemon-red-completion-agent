from __future__ import annotations

import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.battle_outcome_learning import (
    BattleOutcomeExample,
    BattleTurnOutcome,
)
from pokemon_red_completion.battle_semantics import FEATURE_NAMES, BattleFeatureBatch
from pokemon_red_completion.scenario_lab import ScenarioPartition

SCRIPT = runpy.run_path("scripts/collect_repeatable_battle_outcomes.py")
GLOBALS = SCRIPT["_run"].__globals__


def _example(
    partition: ScenarioPartition,
    *,
    root: str,
    state_character: str,
    scale: float,
) -> BattleOutcomeExample:
    rows = (
        tuple([0.1 * scale] + [0.0] * (len(FEATURE_NAMES) - 1)),
        tuple([0.8 * scale] + [0.0] * (len(FEATURE_NAMES) - 1)),
    )
    return BattleOutcomeExample(
        root_lineage_id=root,
        initial_state_sha256=state_character * 64,
        partition=partition,
        features=BattleFeatureBatch(
            feature_names=FEATURE_NAMES,
            candidate_vectors=rows,
            legal_mask=(True, True),
            current_pp=(10.0, 10.0),
            slot_indices=(0, 1),
        ),
        outcomes=(
            BattleTurnOutcome(True, 0.1, 0.0, False, False, False, 1, 3, 1),
            BattleTurnOutcome(True, 0.8, 0.0, False, False, False, 1, 3, 1),
        ),
    )


def _capture(
    capture_id: str,
    partition: ScenarioPartition,
    *,
    root: str,
    state_character: str,
) -> SimpleNamespace:
    return SimpleNamespace(
        manifest=SimpleNamespace(
            capture_id=capture_id,
            partition=partition,
            state_sha256=state_character * 64,
            root_lineage_id=root,
        ),
        manifest_sha256=("a" if partition is ScenarioPartition.TRAIN else "b") * 64,
    )


def test_collection_resumes_after_interruption_without_reexecuting_completed_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captures = (
        _capture(
            "train-capture",
            ScenarioPartition.TRAIN,
            root="train-root",
            state_character="1",
        ),
        _capture(
            "development-capture",
            ScenarioPartition.DEVELOPMENT,
            root="development-root",
            state_character="2",
        ),
    )
    examples = {
        "train-capture": _example(
            ScenarioPartition.TRAIN,
            root="train-root",
            state_character="1",
            scale=1.0,
        ),
        "development-capture": _example(
            ScenarioPartition.DEVELOPMENT,
            root="development-root",
            state_character="2",
            scale=0.5,
        ),
    }
    monkeypatch.setitem(GLOBALS, "resolve_rom_path", lambda path: Path("red.gb"))
    monkeypatch.setitem(
        GLOBALS,
        "verify_rom",
        lambda path: SimpleNamespace(sha256="c" * 64),
    )
    monkeypatch.setitem(
        GLOBALS,
        "_capture_pairs",
        lambda directories: ((Path("one"), Path("one.json")), (Path("two"), Path("two.json"))),
    )
    opened = iter(captures)
    monkeypatch.setitem(GLOBALS, "open_battle_scenario_capture", lambda *args: next(opened))
    output = tmp_path / "outcomes.jsonl"
    args = SimpleNamespace(
        rom=None,
        capture_dir=[tmp_path],
        output=output,
        journal_dir=tmp_path / "journal",
        failure_report=None,
    )
    first_calls: list[str] = []

    def interrupt_second(capture, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        capture_id = capture.manifest.capture_id
        first_calls.append(capture_id)
        if capture_id == "development-capture":
            raise KeyboardInterrupt
        return SimpleNamespace(
            example=examples[capture_id],
            capture_id=capture_id,
            manifest_sha256=capture.manifest_sha256,
        )

    monkeypatch.setitem(GLOBALS, "collect_red_battle_outcome_example", interrupt_second)
    with pytest.raises(KeyboardInterrupt):
        SCRIPT["_run"](args)
    assert first_calls == ["train-capture", "development-capture"]
    assert not output.exists()

    second_calls: list[str] = []

    def finish(capture, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        capture_id = capture.manifest.capture_id
        second_calls.append(capture_id)
        return SimpleNamespace(
            example=examples[capture_id],
            capture_id=capture_id,
            manifest_sha256=capture.manifest_sha256,
        )

    opened = iter(captures)
    monkeypatch.setitem(GLOBALS, "open_battle_scenario_capture", lambda *args: next(opened))
    monkeypatch.setitem(GLOBALS, "collect_red_battle_outcome_example", finish)
    summary = SCRIPT["_run"](args)

    assert second_calls == ["development-capture"]
    assert summary["examples"] == 2
    assert summary["quarantined_captures"] == 0
    assert summary["training_semantic_clusters"] == 1
    assert summary["development_semantic_clusters"] == 1
    assert summary["semantic_partition_overlap"] == 0
    assert len(output.read_text("ascii").splitlines()) == 2
    assert len(list((tmp_path / "journal").glob("*.json"))) == 3

    opened = iter(captures)
    monkeypatch.setitem(GLOBALS, "open_battle_scenario_capture", lambda *args: next(opened))
    monkeypatch.setitem(
        GLOBALS,
        "collect_red_battle_outcome_example",
        lambda *args, **kwargs: pytest.fail("completed capture executed again"),
    )
    assert SCRIPT["_run"](args) == summary
    assert all(
        json.loads(line)["capture_id"] in {"train-capture", "development-capture"}
        for line in output.read_text("ascii").splitlines()
    )
