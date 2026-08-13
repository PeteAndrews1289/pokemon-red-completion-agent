from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.route import COMPLETION_QUEST
from pokemon_red_completion.strategic_navigation_scenarios import (
    load_strategic_navigation_scenario_registry,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLAN_PATH = (
    PROJECT_ROOT / "configs" / "red-strategic-navigation-sealed-evaluation-v1.json"
)
DIGEST_PATH = PLAN_PATH.with_name(
    "red-strategic-navigation-sealed-evaluation-v1.digest.json"
)


def _plan() -> dict[str, object]:
    value = json.loads(PLAN_PATH.read_text(encoding="ascii"))
    assert isinstance(value, dict)
    return value


def _cases(plan: dict[str, object]) -> list[dict[str, object]]:
    values = plan["cases"]
    assert isinstance(values, list)
    assert all(isinstance(value, dict) for value in values)
    return values


def test_sealed_plan_is_canonical_digest_bound_and_reproducible() -> None:
    payload = PLAN_PATH.read_bytes()
    plan = _plan()
    digest = json.loads(DIGEST_PATH.read_text(encoding="ascii"))

    assert payload == (
        json.dumps(
            plan,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )
    assert digest == {
        "bytes": len(payload),
        "schema": "pokemon-strategic-navigation-sealed-evaluation-plan-digest-v1",
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    subprocess.run(
        [
            sys.executable,
            "scripts/regenerate_strategic_navigation_sealed_evaluation_plan.py",
            "--check",
        ],
        cwd=PROJECT_ROOT,
        check=True,
    )


def test_sealed_plan_binds_the_five_parameter_model_without_opening_test() -> None:
    plan = _plan()
    model = plan["frozen_model"]
    access = plan["access_policy"]
    assert isinstance(model, dict)
    assert isinstance(access, dict)

    assert model["model_id"] == (
        "pokemon.core.strategic-navigation.destination-ranker.linear.v1"
    )
    assert model["canonical_sha256"] == (
        "753e3dbdb983d85acd9da5910fb92679a5406df39dfde84f68200d85378dd0c1"
    )
    assert model["parameter_count"] == 5
    assert model["feature_set_id"] == "relative_route"
    assert access == {
        "private_test_inputs_opened_at_freeze": 0,
        "requires_clean_published_exact_source": True,
        "requires_external_audit": True,
        "requires_owner_authorization": True,
    }


def test_sealed_plan_uses_all_public_test_frontiers_and_ten_real_hypotheses() -> None:
    plan = _plan()
    cases = _cases(plan)
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    scenarios = {
        scenario.scenario_id: scenario
        for scenario in registry.scenarios
        if scenario.partition == "test"
    }

    assert len(cases) == len(scenarios) == 12
    assert plan["source_scenario_registry_sha256"] == registry.registry_sha256
    assert plan["minimum_challenge_hypotheses"] == 6
    assert plan["preregistered_challenge_hypotheses"] == 10
    assert {case["source_scenario_id"] for case in cases} == set(scenarios)
    assert sum(bool(case["cost_baseline_challenge_hypothesis"]) for case in cases) == 10

    for case in cases:
        case_payload = dict(case)
        case_sha256 = case_payload.pop("case_sha256")
        assert case_sha256 == canonical_sha256(case_payload)
        scenario_id = case["source_scenario_id"]
        assert isinstance(scenario_id, str)
        scenario = scenarios[scenario_id]
        assert case["source_scenario_sha256"] == scenario.scenario_sha256
        challenged = case["challenged_non_teacher_objective_id"]
        if challenged is None:
            assert case["cost_baseline_challenge_hypothesis"] is False
            continue
        assert isinstance(challenged, str)
        assert challenged in scenario.candidate_objective_ids
        assert challenged != scenario.teacher_objective_id
        assert case["origin_region"] == COMPLETION_QUEST.objective(
            challenged
        ).target_region


def test_sealed_plan_scores_failures_and_ties_without_reruns_or_omissions() -> None:
    plan = _plan()

    assert plan["attempt_policy"] == {
        "attempts_per_case": 1,
        "failed_attempt_is_consumed": True,
        "omission_allowed": False,
        "publish_every_case": True,
        "rerun_allowed": False,
    }
    scoring = plan["scoring_policy"]
    assert isinstance(scoring, dict)
    assert scoring["model_prediction_tie"] == "incorrect"
    assert scoring["failed_or_interrupted_after_open"] == (
        "case_consumed_model_and_baseline_incorrect"
    )
    assert scoring["incomplete_episode"] == (
        "case_consumed_model_and_baseline_incorrect"
    )
    assert scoring["minimum_measured_teacher_baseline_disagreements"] == 6
    assert scoring["paired_test"] == (
        "two_sided_exact_mcnemar_on_discordant_correctness"
    )
