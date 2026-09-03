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
RepeatableBattleCollectionError = SCRIPT["RepeatableBattleCollectionError"]


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


def test_collection_quarantines_interruption_and_continues_only_untouched_siblings(
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
        _capture(
            "train-capture-2",
            ScenarioPartition.TRAIN,
            root="train-root",
            state_character="3",
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
        "train-capture-2": _example(
            ScenarioPartition.TRAIN,
            root="train-root",
            state_character="3",
            scale=1.0,
        ),
    }
    _install_provenance_fakes(monkeypatch)
    monkeypatch.setitem(GLOBALS, "resolve_rom_path", lambda path: Path("red.gb"))
    monkeypatch.setitem(
        GLOBALS,
        "verify_rom",
        lambda path: SimpleNamespace(sha256="c" * 64),
    )
    monkeypatch.setitem(
        GLOBALS,
        "_capture_pairs",
        lambda directories: (
            (Path("one"), Path("one.json")),
            (Path("two"), Path("two.json")),
            (Path("three"), Path("three.json")),
        ),
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
    assert len(list((tmp_path / "journal").glob("*.claim.json"))) == 2
    assert len(list((tmp_path / "journal").glob("*.terminal.json"))) == 1

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

    assert second_calls == ["train-capture-2"]
    assert summary["examples"] == 2
    assert summary["quarantined_captures"] == 1
    assert summary["training_semantic_clusters"] == 1
    assert summary["development_semantic_clusters"] == 0
    assert summary["semantic_partition_overlap"] == 0
    assert len(output.read_text("ascii").splitlines()) == 2
    assert len(list((tmp_path / "journal").glob("*.json"))) == 7
    assert summary["collector_source_commit"] == "d" * 40

    opened = iter(captures)
    monkeypatch.setitem(GLOBALS, "open_battle_scenario_capture", lambda *args: next(opened))
    monkeypatch.setitem(
        GLOBALS,
        "collect_red_battle_outcome_example",
        lambda *args, **kwargs: pytest.fail("completed capture executed again"),
    )
    assert SCRIPT["_run"](args) == summary
    assert all(
        json.loads(line)["capture_id"] in {"train-capture", "train-capture-2"}
        for line in output.read_text("ascii").splitlines()
    )


def test_collection_requires_published_source_before_claim_or_controller_input(
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
    )
    _install_collection_fakes(tmp_path, monkeypatch, captures)
    monkeypatch.setitem(
        GLOBALS,
        "require_published_source",
        lambda *args: (_ for _ in ()).throw(RuntimeError("source is not published")),
    )
    monkeypatch.setitem(
        GLOBALS,
        "collect_red_battle_outcome_example",
        lambda *args, **kwargs: pytest.fail("controller input must remain closed"),
    )

    with pytest.raises(RuntimeError, match="not published"):
        SCRIPT["_run"](_args(tmp_path))

    assert not (tmp_path / "journal").exists()


def test_collection_allows_sibling_states_from_one_training_lineage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captures = (
        _capture("train-a", ScenarioPartition.TRAIN, root="shared-train-root", state_character="1"),
        _capture("train-b", ScenarioPartition.TRAIN, root="shared-train-root", state_character="2"),
        _capture("dev", ScenarioPartition.DEVELOPMENT, root="dev-root", state_character="3"),
    )
    _install_collection_fakes(tmp_path, monkeypatch, captures)

    summary = SCRIPT["_run"](_args(tmp_path))

    assert summary["examples"] == 3


def test_collection_rejects_lineage_crossing_partitions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captures = (
        _capture("train", ScenarioPartition.TRAIN, root="crossing-root", state_character="1"),
        _capture("dev", ScenarioPartition.DEVELOPMENT, root="crossing-root", state_character="2"),
    )
    _install_collection_fakes(tmp_path, monkeypatch, captures)

    with pytest.raises(RepeatableBattleCollectionError, match="crosses"):
        SCRIPT["_run"](_args(tmp_path))


def _args(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        rom=None,
        capture_dir=[tmp_path],
        output=tmp_path / "outcomes.jsonl",
        journal_dir=tmp_path / "journal",
        failure_report=None,
    )


def _install_collection_fakes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    captures: tuple[SimpleNamespace, ...],
) -> None:
    _install_provenance_fakes(monkeypatch)
    monkeypatch.setitem(GLOBALS, "resolve_rom_path", lambda path: Path("red.gb"))
    monkeypatch.setitem(
        GLOBALS,
        "verify_rom",
        lambda path: SimpleNamespace(sha256="c" * 64),
    )
    monkeypatch.setitem(
        GLOBALS,
        "_capture_pairs",
        lambda directories: tuple(
            (tmp_path / f"{index}.state", tmp_path / f"{index}.json")
            for index in range(len(captures))
        ),
    )
    opened = iter(captures)
    monkeypatch.setitem(GLOBALS, "open_battle_scenario_capture", lambda *args: next(opened))

    def collect(capture, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        state_character = capture.manifest.state_sha256[0]
        return SimpleNamespace(
            example=_example(
                capture.manifest.partition,
                root=capture.manifest.root_lineage_id,
                state_character=state_character,
                scale=(
                    1.0
                    if capture.manifest.partition is ScenarioPartition.TRAIN
                    else 0.5
                ),
            ),
            capture_id=capture.manifest.capture_id,
            manifest_sha256=capture.manifest_sha256,
        )

    monkeypatch.setitem(GLOBALS, "collect_red_battle_outcome_example", collect)


def _install_provenance_fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        GLOBALS,
        "detect_source_identity",
        lambda *args, **kwargs: SimpleNamespace(git_commit="d" * 40),
    )
    monkeypatch.setitem(GLOBALS, "require_clean_source", lambda value: None)
    monkeypatch.setitem(GLOBALS, "require_published_source", lambda *args: None)
