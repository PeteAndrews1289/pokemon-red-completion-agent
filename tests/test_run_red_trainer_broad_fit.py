import json

import pytest
from run_red_trainer_broad_fit import admitted_supply
from run_red_trainer_budgeted_fit import composed_offset

from pokemon_red_completion.red_trainer_practice_head import TrainerHeadExample


def test_composed_offset_includes_unselected_child_cost():
    rows = [TrainerHeadExample(((1.0,), (0.0,)), (0,), mean_returns=(4.0, 2.0))]
    targets = [{"heads": {"control": {"returns": [7.0, 4.0, 2.0]}}}]
    assert composed_offset(targets, rows) == 3.0
    # Choosing the second proposal incurs head regret2 plus unavoidable3,
    # exactly the gap between best physical action7 and selected action2.
    assert composed_offset(targets, rows) + 2.0 == 7.0 - 2.0


def test_composed_offset_rejects_mismatched_inventory():
    with pytest.raises(ValueError, match="inventory"):
        composed_offset([{"heads": {}}], [])


def test_supply_must_be_complete_and_unfitted(tmp_path):
    (tmp_path / "collection.json").write_text(json.dumps({"status": "incomplete", "fits": 0}))
    with pytest.raises(ValueError, match="unfitted terminal"):
        admitted_supply(tmp_path, set(), set())


def test_supply_rejects_changed_bytes_before_admission(tmp_path):
    (tmp_path / "collection.json").write_text(
        json.dumps(
            {
                "status": "terminal_collection_complete_train_only",
                "fits": 0,
                "plan": {"path": str(tmp_path / "plan.json"), "sha256": "wrong"},
            }
        )
    )
    (tmp_path / "plan.json").write_text("{}")
    with pytest.raises(ValueError, match="binding differs"):
        admitted_supply(tmp_path, set(), set())


def test_final_gates_independently_recheck_switch_retention():
    from copy import deepcopy

    from run_red_trainer_broad_fit import broad_gates

    before = {
        group: {
            head: {"model_mean_train_regret": 0.02}
            for head in ("move", "switch", "composed_action")
        }
        for group in ("original44", "retained52", "terminal128", "new80")
    }
    after = deepcopy(before)
    broad_before = {head: {"model_mean_train_regret": 1.0} for head in ("move", "composed_action")}
    broad_after = {head: {"model_mean_train_regret": 0.5} for head in ("move", "composed_action")}
    assert all(broad_gates(before, after, broad_before, broad_after).values())
    after["terminal128"]["switch"]["model_mean_train_regret"] = 0.021
    assert not broad_gates(before, after, broad_before, broad_after)["narrow_switch_retained"]
    after = deepcopy(before)
    after["retained52"]["switch"]["model_mean_train_regret"] = 0.021
    assert not broad_gates(before, after, broad_before, broad_after)["retained52_switch_retained"]


def test_late_supply_cannot_relabel_earlier_opening_supply(tmp_path, monkeypatch):
    import run_red_trainer_broad_fit as module

    plan = {
        "profile": "late",
        "supply_seed": 2026091904,
        "frozen_model": {"sha256": module.BROADER_MODEL_SHA},
        "capture_decisions": [2, 4],
    }
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    (tmp_path / "targets.json").write_text("[]")
    (tmp_path / "collection.json").write_text(
        json.dumps(
            {
                "status": "terminal_collection_complete_train_only",
                "fits": 0,
                "plan": module.common._binding(tmp_path / "plan.json"),
                "targets": module.common._binding(tmp_path / "targets.json"),
            }
        )
    )
    with pytest.raises(ValueError, match="semantic boundary"):
        admitted_supply(tmp_path, set(), set(), late=True)
    with pytest.raises(ValueError, match="recipe or trajectory"):
        admitted_supply(tmp_path, set(), set())
