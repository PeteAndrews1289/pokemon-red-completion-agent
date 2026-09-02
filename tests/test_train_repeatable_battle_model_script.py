from __future__ import annotations

import json
import runpy
from pathlib import Path

SCRIPT = runpy.run_path("scripts/train_repeatable_battle_model.py")


def test_training_script_writes_new_model_and_honest_report(tmp_path: Path) -> None:
    model = tmp_path / "model.json"
    report = tmp_path / "report.json"

    result = SCRIPT["main"](
        [
            "--training-examples",
            "24",
            "--development-examples",
            "12",
            "--epochs",
            "10",
            "--hidden-units",
            "8",
            "--out-model",
            str(model),
            "--out-report",
            str(report),
        ]
    )

    assert result == 0
    assert model.exists()
    payload = json.loads(report.read_text())
    assert payload["synthetic_pretraining"] is True
    assert payload["authentic_outcomes"] == 0
    assert payload["gameplay_authority"] is False
