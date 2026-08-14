from __future__ import annotations

import runpy
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MATERIALIZE = runpy.run_path(
    str(PROJECT_ROOT / "scripts" / "materialize_battle_scenario_capture.py")
)


def test_battle_capture_materializer_rejects_one_shared_output() -> None:
    error = MATERIALIZE["BattleScenarioMaterializationError"]
    require_distinct = MATERIALIZE["_require_distinct_outputs"]

    with pytest.raises(error, match="must be distinct"):
        require_distinct(Path("capture.state"), Path("capture.state"))


def test_battle_capture_materializer_accepts_distinct_outputs() -> None:
    require_distinct = MATERIALIZE["_require_distinct_outputs"]

    assert require_distinct(Path("capture.state"), Path("capture.state.json")) is None
