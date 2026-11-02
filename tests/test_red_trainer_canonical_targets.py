from copy import deepcopy

import pytest
import run_red_trainer_canonical_targets as canonical


def rows():
    return [{"capture_id": str(i), "partition": "train", "root_lineage_id": "root",
             "observation": {"hp": 10 + i}, "manifest_sha256": str(i) * 64,
             "timing_offsets": [0, 2, 4, 6, 8], "timing_target_sha256s": ["old"],
             "heads": {"switch": {"choice_refs": ["slot-2", "slot-3"],
                                  "returns": [1.0, 0.0], "best_indices": [0]}}}
            for i in range(4)]


def replacement(old):
    current = deepcopy(old[:1])
    current[0]["heads"]["switch"].update(returns=[0.0, 1.0], best_indices=[1])
    current[0]["timing_target_sha256s"] = ["new"]
    return current


def test_exact_state_new_returns_replace_only_overlap_without_mutation():
    old = rows()
    snapshot = deepcopy(old)
    current = replacement(old)
    groups = {"mixed": old[:2], "unrelated": old[2:]}
    result, audit = canonical.retention_groups(groups, old, current)
    assert old == snapshot
    assert result["mixed-canonical"] == [current[0], old[1]]
    assert result["mixed-nonoverlap"] == [old[1]]
    assert result["unrelated"] == old[2:]
    assert result["all-nonoverlap"] == old[1:]
    assert audit[0]["old_new_disjoint_best"] == {"switch": True}


@pytest.mark.parametrize("change", ["partition", "observation", "root_lineage_id",
                                   "manifest_sha256", "timing_offsets", "choices", "heads"])
def test_replacement_rejects_any_change_to_state_or_legal_inventory(change):
    old = rows()
    current = replacement(old)
    if change == "choices":
        current[0]["heads"]["switch"]["choice_refs"] = ["slot-2", "slot-4"]
    elif change == "heads":
        current[0]["heads"]["control"] = deepcopy(current[0]["heads"]["switch"])
    else:
        current[0][change] = "changed"
    with pytest.raises(ValueError):
        canonical.same_capture_replacements(old, current)


@pytest.mark.parametrize("change", ["duplicate_old", "duplicate_new", "unknown", "empty"])
def test_replacement_inventory_is_exact(change):
    old = rows()
    current = replacement(old)
    if change == "duplicate_old":
        old.append(old[0])
    elif change == "duplicate_new":
        current.append(current[0])
    elif change == "unknown":
        current[0]["capture_id"] = "unknown"
    else:
        current = []
    with pytest.raises(ValueError, match="distinct existing"):
        canonical.same_capture_replacements(old, current)


def test_cannot_remove_an_entire_retention_group():
    old = rows()
    with pytest.raises(ValueError, match="nonoverlap"):
        canonical.retention_groups({"all_changed": old[:1]}, old, replacement(old))


def test_existing_output_rejected_without_reading_inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(canonical, "revision", lambda: "clean")
    with pytest.raises(ValueError, match="new successor"):
        canonical.prepare(None, tmp_path)


def test_unknown_completed_comparison_cannot_authorize_a_fit(tmp_path, monkeypatch):
    monkeypatch.setattr(canonical, "revision", lambda: "clean")
    canonical.write_new(tmp_path / "amended-plan.json", {"unrelated": "campaign"})
    with pytest.raises(ValueError, match="only the completed"):
        canonical.prepare(tmp_path, tmp_path / "output")
    assert not (tmp_path / "output").exists()
