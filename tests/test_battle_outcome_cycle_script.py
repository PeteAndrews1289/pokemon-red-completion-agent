from __future__ import annotations

import runpy
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_semantics import FEATURE_NAMES, FEATURE_SCHEMA_ID
from pokemon_red_completion.scenario_lab import ScenarioPartition

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts" / "run_battle_outcome_learning_cycle.py")
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
                "artifact_id": "battle-outcome-test",
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
        assert artifact_id.startswith("red-battle-outcome-update-")
        assert kind == "battle_outcome_cycle"
        return self.writer


def _exercise(
    monkeypatch,
    *,
    train_informative: bool,
    development_informative: bool,
) -> tuple[dict[str, object], Writer]:  # type: ignore[no-untyped-def]
    commit = "a" * 40
    source = SimpleNamespace(
        git_commit=commit,
        public_dict=lambda: {"git_commit": commit},
    )
    train_capture = SimpleNamespace(
        manifest=SimpleNamespace(
            partition=ScenarioPartition.TRAIN,
            source_commit=commit,
        )
    )
    development_capture = SimpleNamespace(
        manifest=SimpleNamespace(
            partition=ScenarioPartition.DEVELOPMENT,
            source_commit=commit,
        )
    )
    train_collection = SimpleNamespace(
        example=SimpleNamespace(learner_update_eligible=train_informative),
        public_dict=lambda: {"split": "train"},
    )
    development_collection = SimpleNamespace(
        example=SimpleNamespace(learner_update_eligible=development_informative),
        public_dict=lambda: {"split": "development"},
    )
    base_model = _model()
    updated_model = _model()
    cycle = SimpleNamespace(
        update=SimpleNamespace(model=updated_model),
        public_dict=lambda: {"cycle": "ok"},
    )
    store = Store()

    monkeypatch.setitem(SCRIPT_GLOBALS, "detect_source_identity", lambda *args, **kwargs: source)
    monkeypatch.setitem(SCRIPT_GLOBALS, "require_clean_source", lambda value: None)
    monkeypatch.setitem(SCRIPT_GLOBALS, "require_published_source", lambda *args: None)
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "open_battle_scenario_capture",
        lambda state, manifest: (
            train_capture if Path(state).name.startswith("train") else development_capture
        ),
    )
    monkeypatch.setitem(SCRIPT_GLOBALS, "load_battle_model_artifact", lambda path: base_model)
    monkeypatch.setitem(SCRIPT_GLOBALS, "resolve_rom_path", lambda path: Path("red.gb"))
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "collect_red_battle_outcome_example",
        lambda capture, **kwargs: (
            train_collection if capture is train_capture else development_collection
        ),
    )
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "run_battle_outcome_learning_cycle",
        lambda *args, **kwargs: cycle,
    )
    monkeypatch.setitem(SCRIPT_GLOBALS, "open_private_root", lambda *args, **kwargs: store)

    args = SimpleNamespace(
        rom=None,
        private_root=Path("private"),
        base_model=Path("base/model.jsonl"),
        train_state=Path("train.state"),
        train_manifest=Path("train.state.json"),
        development_state=Path("development.state"),
        development_manifest=Path("development.state.json"),
        epochs=10,
        learning_rate=0.01,
        prior_l2=0.1,
    )
    return SCRIPT["_run"](args), store.writer


def test_cycle_script_writes_loadable_candidate_shape_for_informative_pair(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    receipt, writer = _exercise(
        monkeypatch,
        train_informative=True,
        development_informative=True,
    )

    assert receipt["status"] == "ok"
    assert receipt["authority_promoted"] is False
    assert [stream for stream, _ in writer.records] == [
        "outcomes",
        "outcomes",
        "model",
        "evaluation",
    ]
    model_record = writer.records[2][1]
    assert model_record["record_type"] == "battle_model_candidate"
    assert model_record["authority"] == "shadow_only"


def test_cycle_script_preserves_flat_outcomes_without_writing_a_model(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    receipt, writer = _exercise(
        monkeypatch,
        train_informative=False,
        development_informative=True,
    )

    assert receipt["status"] == "insufficient_signal"
    assert receipt["model_sha256"] is None
    assert [stream for stream, _ in writer.records] == [
        "outcomes",
        "outcomes",
        "evaluation",
    ]
    assert writer.records[-1][1]["record_type"] == "battle_outcome_no_update"
    assert writer.records[-1][1]["model_written"] is False
