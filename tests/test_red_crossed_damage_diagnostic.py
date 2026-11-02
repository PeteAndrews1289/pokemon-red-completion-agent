"""ROM-free factorial-design and honest-score guards."""

from copy import deepcopy
from itertools import product

import numpy as np
import pytest
import run_red_crossed_damage_diagnostic as packet


def rows():
    return [
        {
            "id": f"f{f}-r{r}-l{level}",
            "family_id": f"f{f}",
            "source_index": r,
            "practice": {
                "actor_level": level,
                "actor_species_ref": f"actor{f}",
                "opponent_species_ref": f"foe{f}",
                "actor_moves": [{"move_ref": "move1"}],
                "opponent_moves": [{"move_ref": "move2"}],
            },
        }
        for f, r, level in product(range(4), packet.ROOTS, packet.LEVELS)
    ]


def test_crossing_accepts_full_factorial_and_rejects_confounding():
    data = rows()
    packet.validate_crossing(data)
    for row in data:
        row["source_index"] = packet.LEVELS.index(row["practice"]["actor_level"])
    with pytest.raises(ValueError, match="every root and level"):
        packet.validate_crossing(data)


@pytest.mark.parametrize("mutation", ["duplicate", "missing", "moves", "pair"])
def test_crossing_rejects_missing_repeated_or_changing_cells(mutation):
    data = rows()
    if mutation == "duplicate":
        data[-1]["id"] = data[0]["id"]
    elif mutation == "missing":
        data.pop()
    elif mutation == "moves":
        data[0]["practice"]["actor_moves"].append({"move_ref": "newmove"})
    else:
        for row in data:
            if row["family_id"] == "f3":
                row["practice"]["actor_species_ref"] = "foe0"
                row["practice"]["opponent_species_ref"] = "actor0"
    with pytest.raises(ValueError):
        packet.validate_crossing(data)


def test_exact_best_and_near_best_are_distinct():
    class Head:
        def predict_index(self, _):
            return 0

        def scores(self, _):
            return np.asarray([2.0, 1.0, 0.0, -1.0])

    result = packet.choice_metrics((0.49, 0.5, 0.0, 0.1), (), {"K": Head()})["K"]
    assert result["slot"] == 1
    assert result["regret"] == pytest.approx(0.01)
    assert result["strict_best"] is False
    assert result["near_best_002"] is True


def test_summary_keeps_root_variance_separate_from_feature_variance():
    targets = []
    for root in packet.ROOTS:
        targets.append(
            {
                "family_id": "f0",
                "level": 31,
                "source_index": root,
                "vectors": [[0.0, 1.0]] * 4,
                "mean_damage": [0.1 + root * 0.05] * 4,
                "choices": {
                    name: {"regret": 0.0, "slot": 1, "strict_best": True, "near_best_002": True}
                    for name in ("K", "rejected")
                },
            }
        )
    # Supply all levels so summaries cannot quietly omit any required level.
    full = []
    for level in packet.LEVELS:
        group = deepcopy(targets)
        for row in group:
            row["level"] = level
        full.extend(group)
    result = packet.summarize(full)
    assert result["root_checks"][0]["max_feature_delta_across_roots"] == 0
    assert result["root_checks"][0]["max_slot_mean_damage_spread"] == pytest.approx(0.15)
    assert result["scores"]["K"]["strict_best"] == 16
    full.pop()
    with pytest.raises(ValueError, match="incomplete root group"):
        packet.summarize(full)


def test_consumed_directory_cannot_resume(tmp_path):
    from types import SimpleNamespace

    with pytest.raises(ValueError, match="consumed output"):
        packet.run(SimpleNamespace(output=tmp_path))
