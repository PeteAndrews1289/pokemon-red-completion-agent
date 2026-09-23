from copy import deepcopy
from types import SimpleNamespace

import pytest
import run_red_trainer_switching_comparison as comparison


def rows():
    return [
        {"capture_id": f"{prefix}-{root}-{index}", "root_lineage_id": str(root),
         "partition": "train", "decision_context": context,
         "observation": {"features": {"party": {"count": 5}}},
         "heads": {"control": {"returns": [1, -1]}}}
        for root in range(4)
        for prefix, context, index in (
            ("assisted-train", "main", 0), ("assisted-train", "main", 1),
            ("terminal-intermediate", "main", 0), ("terminal-intermediate", "main", 1),
            ("terminal-intermediate", "forced", 2),
        )
    ]


def test_selection_is_return_blind_and_interleaves_roots():
    source = rows()
    selected = comparison.select_cases(source)
    assert len(selected) == len({r["capture_id"] for r in selected}) == 16
    assert [r["root_lineage_id"] for r in selected[:4]] == ["0", "1", "2", "3"]
    assert all(r["decision_context"] == "forced" for r in selected[-4:])
    changed = deepcopy(source[::-1])
    for r in changed:
        r["heads"]["control"]["returns"] = [-999, 999]
    assert [r["capture_id"] for r in comparison.select_cases(changed)] == [
        r["capture_id"] for r in selected
    ]


def test_selection_uses_declared_later_main_fallback_without_replacement():
    source = [r for r in rows() if r["decision_context"] == "main"]
    selected = comparison.select_cases(source)
    assert len(selected) == 16
    assert all(r["capture_id"].endswith("-1") for r in selected[-4:])


@pytest.mark.parametrize("mutation", ["development", "missing_root", "duplicate", "small_party"])
def test_selection_rejects_inadmissible_or_missing_inputs(mutation):
    source = rows()
    if mutation == "development":
        source[0]["partition"] = "development"
    elif mutation == "missing_root":
        source = [r for r in source if r["root_lineage_id"] != "3"]
    elif mutation == "duplicate":
        source.append(source[0])
    else:
        for row in source:
            row["observation"]["features"]["party"]["count"] = 3
    with pytest.raises(ValueError):
        comparison.select_cases(source)


@pytest.mark.parametrize("stop", ["battle_won", "party_defeated"])
def test_normal_loss_is_admissible_not_a_retry_trigger(stop):
    comparison.require_terminal({"stop_reason": stop, "metrics": {"invalid_action_failures": 0}})


@pytest.mark.parametrize("stop,invalid", [
    ("player_turn_budget", 0), ("decision_budget", 0), ("battle_won", 1),
])
def test_invalid_or_censored_branch_stops(stop, invalid):
    with pytest.raises(ValueError, match="comparison stops"):
        comparison.require_terminal({"stop_reason": stop,
                                     "metrics": {"invalid_action_failures": invalid}})


def test_fit_gate_requires_gain_and_retention_without_perfect_wins():
    def report(composed, switch):
        return {"composed_action": {"model_mean_train_regret": composed},
                "switch": {"model_mean_train_regret": switch}}
    before, after = report(1, 1), report(0.8, 0.9)
    old = {"old": report(0.2, 0.3)}
    limits = {"old:composed_action": 0.2, "old:switch": 0.3}
    assert all(comparison.learning_checks(before, after, old, limits).values())
    assert not all(comparison.learning_checks(before, before, old, limits).values())
    assert not all(comparison.learning_checks(before, report(0.8, 1.1), old, limits).values())
    assert not all(comparison.learning_checks(before, after, {"old": report(0.3, 0.3)},
                                              limits).values())
    assert not comparison.learning_checks(report(0, 0), report(0, 0), old, limits)[
        "new_composed_improves_ten_percent"
    ]


def test_claim_and_bound_file_cannot_be_overwritten_or_tampered(tmp_path):
    path = tmp_path / "claim.json"
    comparison.write_new(path, {"one": "attempt"})
    pin = comparison.binding(path)
    assert comparison.bound(pin) == path
    with pytest.raises(FileExistsError):
        comparison.write_new(path, {"another": "attempt"})
    path.write_text("changed")
    with pytest.raises(ValueError, match="binding"):
        comparison.bound(pin)


def test_existing_output_rejected_before_loading_any_training(tmp_path, monkeypatch):
    monkeypatch.setattr(comparison, "revision", lambda: "a" * 40)
    with pytest.raises(ValueError, match="new comparison output"):
        comparison.prepare(SimpleNamespace(output=tmp_path, rom=None))


def test_schedule_satisfies_existing_five_timing_minimum():
    assert len(comparison.OFFSETS) >= 5
    assert len(set(comparison.OFFSETS)) == len(comparison.OFFSETS)
    assert {0, 4, 8} < set(comparison.OFFSETS)


def test_measure_rejects_old_schedule_before_claim_or_emulation(tmp_path, monkeypatch):
    monkeypatch.setattr(comparison, "authenticated_plan", lambda _: {"timing_offsets": [0, 4, 8]})
    with pytest.raises(ValueError, match="before execution"):
        comparison.measure(tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("mutation", [None, "fit", "cases", "replay"])
def test_amendment_changes_only_timing_schedule(tmp_path, mutation):
    failure = tmp_path / "failure.json"
    comparison.write_new(failure, {"error": "aggregation"})
    original = {"cases": [{"refs": ["a", "b"]}], "fit": {"maximum_fits": 1},
                "timing_offsets": [0, 4, 8], "maximum_branches": 6, "source_commit": "old"}
    amended = {**deepcopy(original), "source_commit": "new",
               "timing_offsets": list(comparison.OFFSETS),
               "maximum_branches": 10,
               "timing_amendment": {"replayed_branches": 0,
                    "retained_timings": [{"offset": i} for i in (0, 4, 8)],
                    "original_failure": comparison.binding(failure)}}
    if mutation == "fit":
        amended["fit"]["maximum_fits"] = 2
    elif mutation == "cases":
        amended["cases"][0]["refs"].append("c")
    elif mutation == "replay":
        amended["timing_amendment"]["replayed_branches"] = 24
    if mutation:
        with pytest.raises(ValueError, match="may not alter"):
            comparison.validate_timing_amendment(amended, original)
    else:
        comparison.validate_timing_amendment(amended, original)
