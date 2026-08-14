from __future__ import annotations

import runpy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_semantics import FEATURE_NAMES, FEATURE_SCHEMA_ID
from pokemon_red_completion.scenario_lab import ScenarioPartition

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts" / "run_battle_outcome_learning_curve.py")
)
SCRIPT_GLOBALS = SCRIPT["_run"].__globals__


def _model() -> MaskedMLPMoveRanker:
    return MaskedMLPMoveRanker(
        feature_names=FEATURE_NAMES,
        feature_schema_id=FEATURE_SCHEMA_ID,
        input_weights=np.zeros((2, len(FEATURE_NAMES)), dtype=np.float64),
        hidden_bias=np.zeros(2, dtype=np.float64),
        output_weights=np.asarray((0.25, -0.5), dtype=np.float64),
        output_bias=0.0,
        training_seed=7,
    )


class Writer:
    def __init__(self) -> None:
        self.records: list[tuple[str, dict[str, object]]] = []
        self.summary = SimpleNamespace(
            public_dict=lambda: {
                "artifact_id": "battle-learning-curve-test",
                "status": "complete",
            }
        )

    def __enter__(self) -> Writer:
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def append(self, stream: str, record: dict[str, object]) -> None:
        self.records.append((stream, record))


class Store:
    def __init__(self) -> None:
        self.writer = Writer()

    def begin_artifact(self, artifact_id: str, *, kind: str) -> Writer:
        assert artifact_id.startswith("red-battle-learning-curve-")
        assert kind == "battle_outcome_learning_curve"
        return self.writer


def _capture(index: int, *, partition: ScenarioPartition, commit: str) -> SimpleNamespace:
    character = format(index + 1, "x")
    return SimpleNamespace(
        manifest=SimpleNamespace(
            capture_id=f"capture-{index}",
            root_lineage_id=f"root-{index}",
            partition=partition,
            source_commit=commit,
            source_state_sha256=format(index + 8, "x") * 64,
            state_sha256=character * 64,
            initial_observation_sha256=format(index + 9, "x") * 64,
        ),
        manifest_sha256=format(index + 2, "x") * 64,
    )


def test_curve_script_collects_exact_frozen_catalog_and_writes_each_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commit = "a" * 40
    source = SimpleNamespace(
        git_commit=commit,
        public_dict=lambda: {"git_commit": commit},
    )
    captures = tuple(
        _capture(
            index,
            partition=(
                ScenarioPartition.TRAIN
                if index < 4
                else ScenarioPartition.DEVELOPMENT
            ),
            commit=commit,
        )
        for index in range(8)
    )
    collections = {
        capture.manifest.capture_id: SimpleNamespace(
            example=SimpleNamespace(
                usable_mask=np.asarray((True, True)),
                learner_update_eligible=True,
            ),
            outcomes=(object(), object()),
            public_dict=lambda capture_id=capture.manifest.capture_id: {
                "capture_id": capture_id
            },
        )
        for capture in captures
    }
    model = _model()
    points = tuple(
        SimpleNamespace(
            training_size=size,
            update=SimpleNamespace(
                model=model,
                report=SimpleNamespace(updated_model_sha256=f"model-{size}"),
            ),
        )
        for size in (1, 2, 4)
    )
    curve = SimpleNamespace(
        points=points,
        public_dict=lambda: {"training_sizes": [1, 2, 4]},
    )
    store = Store()

    monkeypatch.setitem(SCRIPT_GLOBALS, "detect_source_identity", lambda *args, **kwargs: source)
    monkeypatch.setitem(SCRIPT_GLOBALS, "require_clean_source", lambda value: None)
    monkeypatch.setitem(SCRIPT_GLOBALS, "require_published_source", lambda *args: None)

    def open_capture(state: Path, manifest: Path) -> SimpleNamespace:
        del manifest
        return captures[int(state.stem.split("-")[-1])]

    monkeypatch.setitem(SCRIPT_GLOBALS, "open_battle_scenario_capture", open_capture)
    monkeypatch.setitem(SCRIPT_GLOBALS, "load_battle_model_artifact", lambda path: model)
    monkeypatch.setitem(SCRIPT_GLOBALS, "resolve_rom_path", lambda path: Path("red.gb"))
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "collect_red_battle_outcome_example",
        lambda capture, **kwargs: collections[capture.manifest.capture_id],
    )
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "run_battle_outcome_learning_curve",
        lambda *args, **kwargs: curve,
    )
    monkeypatch.setitem(SCRIPT_GLOBALS, "open_private_root", lambda *args, **kwargs: store)

    args = SimpleNamespace(
        rom=None,
        private_root=Path("private"),
        base_model=Path("base-model.jsonl"),
        train_capture=[
            [Path(f"capture-{index}.state"), Path(f"capture-{index}.json")]
            for index in range(4)
        ],
        development_capture=[
            [Path(f"capture-{index}.state"), Path(f"capture-{index}.json")]
            for index in range(4, 8)
        ],
    )
    receipt = SCRIPT["_run"](args)

    assert receipt["status"] == "ok"
    assert receipt["train_capture_ids"] == [f"capture-{index}" for index in range(4)]
    assert receipt["development_capture_ids"] == [
        f"capture-{index}" for index in range(4, 8)
    ]
    assert receipt["authority_promoted"] is False
    assert [stream for stream, _ in store.writer.records].count("outcomes") == 8
    assert [stream for stream, _ in store.writer.records].count("models") == 3
    assert [stream for stream, _ in store.writer.records].count("evaluation") == 1


def test_curve_catalog_rejects_duplicate_roots_before_any_collection() -> None:
    commit = "a" * 40
    captures = tuple(
        _capture(
            index,
            partition=(
                ScenarioPartition.TRAIN
                if index < 4
                else ScenarioPartition.DEVELOPMENT
            ),
            commit=commit,
        )
        for index in range(8)
    )
    captures = (
        captures[0],
        SimpleNamespace(
            manifest=SimpleNamespace(
                **{
                    **vars(captures[1].manifest),
                    "root_lineage_id": captures[0].manifest.root_lineage_id,
                }
            ),
            manifest_sha256=captures[1].manifest_sha256,
        ),
        *captures[2:],
    )

    with pytest.raises(SCRIPT["BattleOutcomeCurveError"], match="root lineage"):
        SCRIPT["_require_catalog"](captures, source_commit=commit)


def test_curve_catalog_requires_v2_source_state_bindings() -> None:
    commit = "a" * 40
    captures = tuple(
        _capture(
            index,
            partition=(
                ScenarioPartition.TRAIN
                if index < 4
                else ScenarioPartition.DEVELOPMENT
            ),
            commit=commit,
        )
        for index in range(8)
    )
    captures[0].manifest.source_state_sha256 = None

    with pytest.raises(SCRIPT["BattleOutcomeCurveError"], match="root state binding"):
        SCRIPT["_require_catalog"](captures, source_commit=commit)
