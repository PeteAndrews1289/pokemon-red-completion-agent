from __future__ import annotations

import pytest

from scripts.fit_red_trainer_practice_outcomes import SCHEMA
from scripts.refit_red_trainer_practice_outcomes import build_refit_plan


def test_refit_plan_preserves_exact_scenarios_and_changes_only_fit_binding(tmp_path):
    scenarios = [{"binding": index} for index in range(16)]
    old = {
        "schema": SCHEMA,
        "scenarios": scenarios,
        "source_commit": "a" * 40,
        "seed": 12,
        "output": "old",
    }
    plan = build_refit_plan(old, commit="b" * 40, epochs=2400, output=tmp_path / "fit")
    assert plan["scenarios"] == scenarios
    assert plan["scenarios"] is scenarios
    assert plan["epochs"] == 2400
    assert plan["source_commit"] == "b" * 40
    assert old["source_commit"] == "a" * 40
    with pytest.raises(ValueError, match="optimizer"):
        build_refit_plan(old, commit="b" * 40, epochs=4000, output=tmp_path / "fit")


def test_refit_plan_binds_one_declared_move_continuation(tmp_path):
    old = {"schema": SCHEMA, "scenarios": [{}] * 16}
    model = tmp_path / "model.json"
    receipt = tmp_path / "receipt.json"
    model.write_text("old model")
    receipt.write_text("old receipt")
    plan = build_refit_plan(
        old, commit="b" * 40, epochs=2400, output=tmp_path / "fit",
        warm_start_move_model=model, warm_start_move_receipt=receipt,
        warm_start_move_epochs=100,
    )
    assert plan["warm_start_move_model"]["path"] == str(model)
    assert len(plan["warm_start_move_receipt"]["sha256"]) == 64
    assert plan["warm_start_move_epochs"] == 100
    with pytest.raises(ValueError, match="schedule"):
        build_refit_plan(
            old, commit="b" * 40, epochs=2400, output=tmp_path / "fit",
            warm_start_move_model=model, warm_start_move_receipt=receipt,
            warm_start_move_epochs=0,
        )
