from __future__ import annotations

import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_semantics import (
    FEATURE_NAMES,
    FEATURE_SCHEMA_ID,
    BattleFeatureBatch,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition

SCRIPT = runpy.run_path("scripts/commit_repeatable_battle_development_predictions.py")
SCRIPT_GLOBALS = SCRIPT["_run"].__globals__
CommitmentError = SCRIPT["RepeatableBattlePredictionCommitmentError"]


def _model(*, output_weight: float) -> MaskedMLPMoveRanker:
    power = FEATURE_NAMES.index("move.accuracy_weighted_effective_power_fraction")
    weights = np.zeros((1, len(FEATURE_NAMES)), dtype=np.float64)
    weights[0, power] = 1.0
    return MaskedMLPMoveRanker(
        feature_names=FEATURE_NAMES,
        feature_schema_id=FEATURE_SCHEMA_ID,
        input_weights=weights,
        hidden_bias=np.zeros(1, dtype=np.float64),
        output_weights=np.asarray((output_weight,), dtype=np.float64),
        output_bias=0.0,
        training_seed=7,
    )


def _features() -> BattleFeatureBatch:
    power = FEATURE_NAMES.index("move.accuracy_weighted_effective_power_fraction")
    rows = [[0.0] * len(FEATURE_NAMES) for _ in range(2)]
    rows[0][power] = 0.2
    rows[1][power] = 0.8
    return BattleFeatureBatch(
        feature_names=FEATURE_NAMES,
        candidate_vectors=tuple(tuple(row) for row in rows),
        legal_mask=(True, True),
        current_pp=(10.0, 10.0),
        slot_indices=(0, 1),
    )


def _args(tmp_path: Path, *, output: Path | None = None) -> SimpleNamespace:
    capture_dir = tmp_path / "captures"
    capture_dir.mkdir()
    (capture_dir / "one.state").write_bytes(b"state")
    (capture_dir / "one.state.json").write_text("{}", encoding="ascii")
    base = tmp_path / "base.json"
    updated = tmp_path / "updated.json"
    base.write_text(_model(output_weight=-1.0).to_json() + "\n", encoding="ascii")
    updated.write_text(_model(output_weight=1.0).to_json() + "\n", encoding="ascii")
    return SimpleNamespace(
        rom=tmp_path / "red.gb",
        base_model=base,
        updated_model=updated,
        capture_dir=[capture_dir],
        output=output or tmp_path / "commitment.json",
    )


def _patch_runtime(
    monkeypatch: pytest.MonkeyPatch,
    *,
    partition: ScenarioPartition = ScenarioPartition.DEVELOPMENT,
) -> None:
    capture = SimpleNamespace(
        manifest=SimpleNamespace(
            partition=partition,
            capture_id="development-capture",
            state_sha256="a" * 64,
            root_lineage_id="development-root",
        ),
        manifest_sha256="b" * 64,
    )
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
        lambda _state, _manifest: capture,
    )
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "prepare_red_battle_outcome_capture",
        lambda _capture, **_kwargs: SimpleNamespace(
            features=_features(),
            initial_observation_sha256="e" * 64,
        ),
    )


def test_commits_choices_without_actions_or_outcomes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _args(tmp_path)
    _patch_runtime(monkeypatch)

    report = SCRIPT["_run"](args)

    assert report["capture_count"] == 1
    assert report["development_outcomes_opened"] == 0
    assert report["controller_actions"] == 0
    assert report["teacher_queries"] == 0
    assert report["authority_promoted"] is False
    commitment = report["commitments"][0]
    assert commitment["base_candidate_index"] == 0
    assert commitment["updated_candidate_index"] == 1
    assert json.loads(args.output.read_text("ascii")) == report
    assert args.output.stat().st_mode & 0o777 == 0o600


def test_rejects_non_development_capture_before_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _args(tmp_path)
    _patch_runtime(monkeypatch, partition=ScenarioPartition.TRAIN)
    observed = False

    def observe(*_args: object, **_kwargs: object) -> object:
        nonlocal observed
        observed = True
        raise AssertionError("train capture must be rejected before observation")

    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "prepare_red_battle_outcome_capture",
        observe,
    )

    with pytest.raises(CommitmentError, match="development captures only"):
        SCRIPT["_run"](args)

    assert observed is False
    assert not args.output.exists()


def test_output_is_exclusive_and_private(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = _args(tmp_path)
    args.output.write_text("occupied", encoding="ascii")
    _patch_runtime(monkeypatch)

    with pytest.raises(CommitmentError, match="already exists"):
        SCRIPT["_run"](args)
