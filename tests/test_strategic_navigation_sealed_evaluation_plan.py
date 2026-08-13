from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections import Counter
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
    expected_sha256 = (
        "f4429dce83b99c4c5dce05785b2222e590c6d670adc0966d8f6b86e5c88d4fec"
    )

    assert len(payload) == 11208
    assert hashlib.sha256(payload).hexdigest() == expected_sha256
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
        "schema": "pokemon-strategic-navigation-sealed-evaluation-plan-digest-v3",
        "sha256": expected_sha256,
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
    teacher = plan["teacher_execution"]
    assert isinstance(model, dict)
    assert isinstance(access, dict)
    assert isinstance(teacher, dict)

    assert model == {
        "canonical_sha256": (
            "753e3dbdb983d85acd9da5910fb92679a5406df39dfde84f68200d85378dd0c1"
        ),
        "enabled_feature_names": [
            "candidate.route_cost.relative_rank",
            "candidate.route_steps.relative_rank",
            "candidate.map_transitions.relative_rank",
            "candidate.field_actions.relative_rank",
            "candidate.mode_changes.relative_rank",
        ],
        "feature_schema_id": (
            "pokemon.core.strategic-navigation.destination-ranker.v1"
        ),
        "feature_set_id": "relative_route",
        "l2": 0.1,
        "model_id": "pokemon.core.strategic-navigation.destination-ranker.linear.v1",
        "parameter_count": 5,
        "private_file_sha256": (
            "6ef826bc92fae3092e9ccaefaad4107a687a564f7d35818f844fadba68540cdd"
        ),
        "training_epochs": 600,
    }
    assert plan["execution_source_bundle_sha256"] == (
        "585fab5b42d9b409b9d7d6659d191987ba5a31958f9ac39734f6d1e07f9833b7"
    )
    assert plan["training_development_receipt_sha256"] == (
        "ea6ab43761c4c274812b6fc38ed3ece25bc48f83d658cd8b22a391ab71ea5612"
    )
    assert access == {
        "private_test_inputs_opened_at_freeze": 0,
        "requires_clean_published_exact_source": True,
        "requires_external_audit": True,
        "requires_owner_authorization": True,
    }
    assert teacher == {
        "behavior_configuration_sha256": (
            "bdca346b2cbb97cf43d79a8cf7f0d8eab90dacfb6610bb5c2f97028435f985b8"
        ),
        "decision_contract_sha256": (
            "d62f16a23ad54742c97a52ffaa50b0617042d5e35518af4ae61b623631e539a6"
        ),
        "objective_graph_sha256": (
            "13c7cb5ef8b1d6c73e2d79d5d8e3a03b8acbafc593a9633370839fb18bf9b523"
        ),
        "source_bundle_sha256": (
            "585fab5b42d9b409b9d7d6659d191987ba5a31958f9ac39734f6d1e07f9833b7"
        ),
        "teacher_execution_sha256": (
            "07748caa2e1aa4a2d582c80d1d06ab1afc9b9f6725c6d0fc8224ef9b1946073e"
        ),
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


def test_sealed_plan_amendment_precedes_private_access_and_preserves_cases() -> None:
    plan = _plan()
    access = plan["access_policy"]
    amendments = plan["amendments"]
    assert isinstance(access, dict)
    assert isinstance(amendments, list)

    assert plan["schema"] == "pokemon-strategic-navigation-sealed-evaluation-plan-v3"
    assert access["private_test_inputs_opened_at_freeze"] == 0
    assert amendments == [
        {
            "amended_before_private_access": True,
            "change": "primary_endpoint_restricted_to_preregistered_challenge_cases",
            "reason": (
                "independent_power_audit_found_non_challenge_cases_"
                "asymmetric_for_primary_pairing"
            ),
            "supersedes_plan_sha256": (
                "ef9f823e6f5e0e766b071cf8a98bb5ff743af11bcf6bcb0eb3ec160344b7331b"
            ),
        },
        {
            "amended_before_private_access": True,
            "change": "bind_fail_closed_executor_and_optional_stopping_contract",
            "reason": (
                "external_audit_required_durable_claim_before_private_case_access"
            ),
            "supersedes_plan_sha256": (
                "230c90aa7120cd6badef8e933ccf014639889781fa1e32ecb4a486a6a2ef5537"
            ),
        },
    ]
    assert tuple(case["case_sha256"] for case in _cases(plan)) == (
        "7dcfa04cecc1e3db83a3f4d793128cf09a37771c7092008b92847ea6f885d22b",
        "dc4a8c0a0c96ef69803b4fe2babcc1935b07bdc3cbe531e2980bf34b3632098c",
        "6470d5721355b7fc7635ea49f5c23360fcf49cc05811aa2cfaffc5adf2bda055",
        "9be7cf03a58dbe2451bb29f84b8174da2e0443dfa39cab59d30bc297ad1047a1",
        "30678a582bc3d7e41b9f458a8f74642de9c4b559f672d75b16d5177b46c46982",
        "865bfb11ed9ce75dffaa031438eeb5a66068bf1e003a3edac4ce9983086c4dd2",
        "b99fb8c714ff0329151a18f2d187687b8c9abfeac44cc928998e6b12b054a213",
        "c247cdc0d4f3ba97cf3f04454caa0747c6eaa565fd995fb1832bdc7eb9089ac8",
        "d7829644cd7f9bf9774b14f916fdf8baf0c1dddfc7091e637efe83a9fbad7400",
        "bbe36f209ece330610c447579c11d9731fc9b390229b1f0a780a4182ebf5ae06",
        "33ffa87bba82a236369394a6eeb5f5509aaa4e0279bae2bfcca39b874e0d1d28",
        "c96c9d4f3fe7a81948ceb4f283866e18d5bb057277176cdc5dd28e5b699e7190",
    )


def test_sealed_plan_primary_endpoint_is_only_the_ten_challenge_cases() -> None:
    plan = _plan()
    cases = _cases(plan)
    endpoints = plan["endpoint_policy"]
    assert isinstance(endpoints, dict)
    primary = endpoints["primary"]
    assert isinstance(primary, dict)

    challenge_cases = tuple(
        case for case in cases if case["cost_baseline_challenge_hypothesis"] is True
    )
    assert len(challenge_cases) == primary["expected_case_count"] == 10
    assert primary == {
        "case_filter": "cost_baseline_challenge_hypothesis_true",
        "expected_case_count": 10,
        "minimum_measured_teacher_baseline_disagreements": 6,
        "paired_test": "two_sided_exact_mcnemar_on_discordant_correctness",
        "primary_unit": "one_unique_scenario",
        "required_direction": "model_paired_wins_exceed_losses",
        "required_successful_teacher_cases": 10,
        "significance_threshold": 0.05,
    }


def test_sealed_plan_reports_all_cases_and_keeps_non_challenges_as_safety() -> None:
    plan = _plan()
    cases = _cases(plan)
    endpoints = plan["endpoint_policy"]
    assert isinstance(endpoints, dict)
    all_cases = endpoints["all_case_accuracy"]
    candidate_counts = endpoints["candidate_count_accuracy"]
    safety = endpoints["safety"]
    assert isinstance(all_cases, dict)
    assert isinstance(candidate_counts, dict)
    assert isinstance(safety, dict)

    assert all_cases == {
        "case_filter": "all_registered_cases",
        "expected_case_count": 12,
        "metrics": ["model_accuracy", "route_cost_baseline_accuracy"],
        "role": "mandatory_descriptive_report",
    }
    assert candidate_counts == {
        "case_filter": "all_registered_cases",
        "group_by": "candidate_count",
        "metrics": ["model_accuracy", "route_cost_baseline_accuracy"],
        "role": "mandatory_descriptive_report",
    }
    safety_cases = tuple(
        case for case in cases if case["cost_baseline_challenge_hypothesis"] is False
    )
    assert len(safety_cases) == safety["expected_case_count"] == 2
    assert safety == {
        "case_filter": "cost_baseline_challenge_hypothesis_false",
        "criterion": "all_cases_succeed_and_zero_model_incorrect_baseline_correct",
        "expected_case_count": 2,
        "failure_effect": (
            "block_live_authority_and_report_without_changing_primary_test"
        ),
        "role": "preregistered_baseline_favorable_non_regression",
    }


def test_sealed_plan_preserves_the_public_candidate_count_composition() -> None:
    plan = _plan()
    cases = _cases(plan)
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    scenarios = {scenario.scenario_id: scenario for scenario in registry.scenarios}

    challenge_counts: Counter[int] = Counter()
    safety_counts: Counter[int] = Counter()
    for case in cases:
        scenario_id = case["source_scenario_id"]
        assert isinstance(scenario_id, str)
        candidate_count = len(scenarios[scenario_id].candidate_objective_ids)
        if case["cost_baseline_challenge_hypothesis"] is True:
            challenge_counts[candidate_count] += 1
        else:
            safety_counts[candidate_count] += 1

    assert challenge_counts == {2: 4, 3: 4, 4: 1, 5: 1}
    assert safety_counts == {2: 2}
    execution = plan["execution_policy"]
    assert isinstance(execution, dict)
    assert execution["candidate_counts_by_case"] == {
        case["case_id"]: len(scenarios[str(case["source_scenario_id"])].candidate_objective_ids)
        for case in cases
    }


def test_sealed_plan_scores_failures_and_ties_without_reruns_or_omissions() -> None:
    plan = _plan()

    assert plan["baseline"] == {
        "policy_id": "unique-minimum-route-cost-v1",
        "prediction_tie": "incorrect",
    }
    assert plan["attempt_policy"] == {
        "attempts_per_case": 1,
        "failed_attempt_is_consumed": True,
        "omission_allowed": False,
        "publish_every_case": True,
        "rerun_allowed": False,
    }
    assert plan["scoring_policy"] == {
        "candidate_unavailable_after_claim": (
            "case_consumed_model_and_baseline_incorrect"
        ),
        "failed_or_interrupted_after_claim": (
            "case_consumed_model_and_baseline_incorrect"
        ),
        "incomplete_episode": "case_consumed_model_and_baseline_incorrect",
        "missing_case": "publish_incomplete_evaluation_as_protocol_failure",
        "model_prediction_tie": "incorrect",
        "teacher_target": "successful_deterministic_teacher_choice_only",
        "preclaim_identity_or_catalog_failure": (
            "open_zero_cases_and_refuse_execution"
        ),
    }


def test_sealed_plan_forbids_optional_stopping_and_reopening_cases() -> None:
    plan = _plan()
    cases = _cases(plan)

    assert plan["execution_policy"] == {
        "candidate_counts_by_case": {
            case["case_id"]: count
            for case, count in zip(
                cases,
                (2, 2, 3, 5, 3, 4, 2, 3, 3, 2, 2, 2),
                strict=True,
            )
        },
        "case_claim": "durable_before_any_private_case_input_access",
        "case_order": [case["case_id"] for case in cases],
        "case_order_frozen": True,
        "halt_after_first_claim": "publish_protocol_failure",
        "intermediate_case_results": "forbidden",
        "intermediate_statistics": "forbidden",
        "prediction_commit": "durable_before_deterministic_teacher_action",
        "reopen_consumed_case": False,
        "restart_after_claim": (
            "consume_open_case_as_both_incorrect_continue_next_mark_protocol_failure"
        ),
        "score_after_consumed_cases": 12,
        "single_continuous_invocation_required": True,
    }
