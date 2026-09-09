"""Independent literal expectations for a diagnostic, not a playing policy."""

import json
import runpy
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "diagnose_goal_horizon.py"


@pytest.fixture
def module():
    return runpy.run_path(str(SCRIPT))


def case(module, name):
    item = next(item for item in module["fixed_cases"]() if item.name == name)
    return module["diagnose_case"](item)


def plans(report):
    return {row["plan"]: row for row in report["plans"]}


def test_optional_positive_recovery_wins_local_score_but_only_adds_total_cost(module):
    report = case(module, "optional_positive_recovery")
    rows = plans(report)
    direct, restored = rows["story_now"], rows["recover_then_story"]
    assert direct["first_macro_utility"] == pytest.approx(3.853333333333333)
    assert restored["first_macro_utility"] == pytest.approx(3.972)
    assert restored["naive_sum_utility"] == pytest.approx(7.825333333333333)
    assert direct["cumulative_cost"] == pytest.approx(.23)
    assert restored["cumulative_cost"] == pytest.approx(.258)
    assert restored["positive_pp_restored"] == 1
    assert direct["completion_within_budget"] is restored["completion_within_budget"] is True
    assert report["first_macro_ranking"] == ["recover_then_story", "story_now"]
    assert report["naive_sum_ranking"] == ["recover_then_story", "story_now"]
    assert report["completion_once_hindsight_ranking"] == ["story_now", "recover_then_story"]


def test_necessary_recovery_is_not_rejected_by_a_blanket_progress_rule(module):
    report = case(module, "necessary_recovery")
    rows = plans(report)
    assert rows["story_now"]["first_macro_utility"] == pytest.approx(-.23)
    assert rows["story_now"]["completion_within_budget"] is False
    assert rows["recover_then_story"]["completion_within_budget"] is True
    assert rows["recover_then_story"]["cumulative_cost"] == pytest.approx(.258)
    assert rows["story_now"]["cumulative_cost"] == pytest.approx(.23)
    assert report["completion_once_hindsight_preferred"] == "recover_then_story"


def test_late_completion_cannot_be_reported_as_within_budget(module):
    report = case(module, "completion_after_budget_is_not_within_budget")
    rows = plans(report)
    assert report["budget"] == {"action_cost": .1, "frame_cost": .1}
    assert rows["story_now"]["completion_within_budget"] is True  # exact boundary admitted
    late = rows["recover_then_story"]
    assert late["action_cost"] == pytest.approx(.11)
    assert late["frame_cost"] == pytest.approx(.11)
    assert late["terminal_evidence"] == "complete"  # retain the stipulated late fact
    assert late["budget_exceeded"] is True
    assert late["completion_within_budget"] is False and late["censored"] is False
    assert report["completion_once_hindsight_preferred"] == "story_now"


@pytest.mark.parametrize("action_budget,frame_budget", [(.09, 1), (1, .09)])
def test_either_resource_budget_independently_blocks_completion(
    module, action_budget, frame_budget,
):
    original = module["fixed_cases"]()[0]
    report = module["diagnose_case"](replace(
        original, action_budget=action_budget, frame_budget=frame_budget,
    ))
    direct = plans(report)["story_now"]
    assert direct["budget_exceeded"] is True
    assert direct["completion_within_budget"] is False


def test_repeated_maintenance_inflates_success_sum_without_final_goal_progress(module):
    report = case(module, "repeated_maintenance_success_bonus")
    row = plans(report)["five_positive_recoveries"]
    assert row["macro_steps"] == row["positive_pp_restored"] == 5
    assert row["naive_sum_utility"] == pytest.approx(19.86)
    assert row["cumulative_cost"] == pytest.approx(.14)
    assert row["completion_within_budget"] is False
    assert report["naive_sum_ranking"] == ["five_positive_recoveries", "story_now"]
    assert report["completion_once_hindsight_preferred"] == "story_now"


def test_unknown_and_interrupted_terminal_evidence_stay_censored(module):
    report = case(module, "terminal_evidence_censored")
    rows = plans(report)
    assert rows["unknown_after_recovery"]["terminal_evidence"] == "unknown"
    assert rows["interrupted_after_recovery"]["terminal_evidence"] == "interrupted"
    for row in rows.values():
        assert row["completion_within_budget"] is None
        assert row["censored"] is True and row["budget_exceeded"] is False
        assert row["naive_sum_utility"] == pytest.approx(3.972)  # observed macro, not terminal
        assert row["cumulative_cost"] == pytest.approx(.028)
    assert report["completion_once_hindsight_ranking"] == []
    assert report["completion_once_hindsight_preferred"] is None


def test_exhausted_budget_does_not_fabricate_censored_terminal_labels(module):
    report = module["diagnose_case"](replace(
        module["fixed_cases"]()[-1], action_budget=.001, frame_budget=.001,
    ))
    assert all(row["budget_exceeded"] for row in report["plans"])
    assert all(row["completion_within_budget"] is None for row in report["plans"])
    assert all(row["censored"] is True for row in report["plans"])
    assert report["completion_once_hindsight_preferred"] is None


def test_actual_existing_utility_scores_each_macro_and_cost_component(module, monkeypatch):
    actual = module["DEFAULT_LIVING_DEX_GOAL_UTILITY"]
    calls = []
    original = type(actual).score

    def record(self, outcome):
        assert self is actual
        calls.append(outcome.vector())
        return original(self, outcome)

    monkeypatch.setattr(type(actual), "score", record)
    case(module, "optional_positive_recovery")
    assert (1.0, 0.0, 0.0, .01, .01, .05, 0.0, 0.0, 0.0) in calls
    assert (0.0, 0.0, 0.0, .01, .01, .05, 0.0, 0.0, 0.0) in calls
    assert (1.0, 0.0, 1 / 36, .1, .1, 0.0, .2, 0.0, 0.0) in calls


def test_stdout_cli_is_fixed_synthetic_json_without_artifact_arguments(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], cwd=tmp_path, text=True, capture_output=True, check=True,
    )
    report = json.loads(result.stdout)
    assert not result.stderr and list(tmp_path.iterdir()) == []
    assert report["schema"] == "pokemon.synthetic.goal-horizon-diagnostic.v1"
    assert report["scope"] == "hindsight_toy_diagnostic_not_a_deployable_actor"
    assert report["controller_actions"] == report["model_queries"] == 0
    assert report["training_labels_created"] == report["authority_promotions"] == 0
    assert report["production_policy_changed"] is False
    assert len(report["cases"]) == 5
    assert report["cases"][0]["completion_once_hindsight_preferred"] == "story_now"
    rejected = subprocess.run(
        [sys.executable, str(SCRIPT), "--model", "unused-model"],
        cwd=tmp_path, text=True, capture_output=True,
    )
    assert rejected.returncode == 2 and not rejected.stdout
