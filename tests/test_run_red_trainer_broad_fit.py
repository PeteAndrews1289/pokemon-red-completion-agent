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
