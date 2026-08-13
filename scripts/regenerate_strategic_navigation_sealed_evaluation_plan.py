#!/usr/bin/env python3
"""Freeze a capable one-shot sealed evaluation plan from public metadata only."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pokemon_red_completion.collection_protocol import working_source_bundle_sha256
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.route import COMPLETION_QUEST
from pokemon_red_completion.strategic_navigation_model import (
    STRATEGIC_NAVIGATION_FEATURE_SCHEMA_ID,
    STRATEGIC_NAVIGATION_LINEAR_MODEL_ID,
)
from pokemon_red_completion.strategic_navigation_protocol import (
    parse_strategic_navigation_registry,
)
from pokemon_red_completion.strategic_navigation_scenarios import (
    load_strategic_navigation_scenario_registry,
)
from pokemon_red_completion.strategic_navigation_test_design import (
    STRATEGIC_SEALED_TEST_MINIMUM_CHALLENGE_HYPOTHESES,
)

ROOT = Path(__file__).resolve().parent.parent
PLAN_PATH = ROOT / "configs" / "red-strategic-navigation-sealed-evaluation-v1.json"
DIGEST_PATH = (
    ROOT / "configs" / "red-strategic-navigation-sealed-evaluation-v1.digest.json"
)
DEVELOPMENT_RECEIPT = (
    ROOT
    / "docs"
    / "evidence"
    / "strategic-navigation-linear-development-2026-08-13.json"
)
STRATEGIC_COLLECTION_REGISTRY = (
    ROOT / "configs" / "red-strategic-navigation-collection-v1.json"
)
PLAN_SCHEMA = "pokemon-strategic-navigation-sealed-evaluation-plan-v3"
DIGEST_SCHEMA = "pokemon-strategic-navigation-sealed-evaluation-plan-digest-v3"
CASE_SCHEMA = "pokemon-strategic-navigation-sealed-evaluation-case-v1"
EVALUATION_ID = "red-strategic-navigation-sealed-evaluation-v1"
V1_PLAN_SHA256 = (
    "ef9f823e6f5e0e766b071cf8a98bb5ff743af11bcf6bcb0eb3ec160344b7331b"
)
V2_PLAN_SHA256 = (
    "230c90aa7120cd6badef8e933ccf014639889781fa1e32ecb4a486a6a2ef5537"
)
FROZEN_MODEL_SHA256 = (
    "753e3dbdb983d85acd9da5910fb92679a5406df39dfde84f68200d85378dd0c1"
)
FROZEN_MODEL_FILE_SHA256 = (
    "6ef826bc92fae3092e9ccaefaad4107a687a564f7d35818f844fadba68540cdd"
)
FROZEN_FEATURES = (
    "candidate.route_cost.relative_rank",
    "candidate.route_steps.relative_rank",
    "candidate.map_transitions.relative_rank",
    "candidate.field_actions.relative_rank",
    "candidate.mode_changes.relative_rank",
)


def _canonical_line(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _generated_payloads() -> tuple[bytes, bytes, dict[str, object]]:
    registry = load_strategic_navigation_scenario_registry(ROOT)
    teacher_execution = parse_strategic_navigation_registry(
        STRATEGIC_COLLECTION_REGISTRY.read_bytes()
    ).execution
    test_scenarios = tuple(
        scenario for scenario in registry.scenarios if scenario.partition == "test"
    )
    cases = []
    for ordinal, scenario in enumerate(test_scenarios, start=1):
        completed_regions = {
            COMPLETION_QUEST.objective(objective_id).target_region
            for objective_id in scenario.completed_objective_ids
        }
        local_non_teacher = tuple(
            objective_id
            for objective_id in scenario.candidate_objective_ids
            if objective_id != scenario.teacher_objective_id
            and COMPLETION_QUEST.objective(objective_id).target_region
            in completed_regions
        )
        challenge = bool(local_non_teacher)
        challenged_objective_id = local_non_teacher[0] if local_non_teacher else None
        origin_region = scenario.origin_region
        if challenged_objective_id is not None:
            target_region = COMPLETION_QUEST.objective(
                challenged_objective_id
            ).target_region
            if target_region is None:
                raise RuntimeError("sealed challenge objective lacks a target region")
            origin_region = target_region
        case = {
            "case_id": f"red-strategic-sealed-v1-{ordinal:03d}-test",
            "challenged_non_teacher_objective_id": challenged_objective_id,
            "cost_baseline_challenge_hypothesis": challenge,
            "origin_region": origin_region,
            "schema": CASE_SCHEMA,
            "source_scenario_id": scenario.scenario_id,
            "source_scenario_sha256": scenario.scenario_sha256,
        }
        case["case_sha256"] = canonical_sha256(case)
        cases.append(case)
    challenge_count = sum(
        bool(case["cost_baseline_challenge_hypothesis"]) for case in cases
    )
    if len(cases) != 12 or challenge_count != 10:
        raise RuntimeError("sealed evaluation case capability differs")
    candidate_counts_by_case = {
        str(case["case_id"]): len(scenario.candidate_objective_ids)
        for case, scenario in zip(cases, test_scenarios, strict=True)
    }
    case_order = [str(case["case_id"]) for case in cases]

    source_bundle_sha256 = working_source_bundle_sha256(ROOT)
    if teacher_execution.source_bundle_sha256 != source_bundle_sha256:
        raise RuntimeError("sealed teacher execution source differs")
    document = {
        "access_policy": {
            "private_test_inputs_opened_at_freeze": 0,
            "requires_clean_published_exact_source": True,
            "requires_external_audit": True,
            "requires_owner_authorization": True,
        },
        "attempt_policy": {
            "attempts_per_case": 1,
            "failed_attempt_is_consumed": True,
            "omission_allowed": False,
            "publish_every_case": True,
            "rerun_allowed": False,
        },
        "amendments": [
            {
                "amended_before_private_access": True,
                "change": (
                    "primary_endpoint_restricted_to_preregistered_challenge_cases"
                ),
                "reason": (
                    "independent_power_audit_found_non_challenge_cases_"
                    "asymmetric_for_primary_pairing"
                ),
                "supersedes_plan_sha256": V1_PLAN_SHA256,
            },
            {
                "amended_before_private_access": True,
                "change": "bind_fail_closed_executor_and_optional_stopping_contract",
                "reason": (
                    "external_audit_required_durable_claim_before_private_case_access"
                ),
                "supersedes_plan_sha256": V2_PLAN_SHA256,
            },
        ],
        "baseline": {
            "policy_id": "unique-minimum-route-cost-v1",
            "prediction_tie": "incorrect",
        },
        "cases": cases,
        "endpoint_policy": {
            "all_case_accuracy": {
                "case_filter": "all_registered_cases",
                "expected_case_count": len(cases),
                "metrics": ["model_accuracy", "route_cost_baseline_accuracy"],
                "role": "mandatory_descriptive_report",
            },
            "candidate_count_accuracy": {
                "case_filter": "all_registered_cases",
                "group_by": "candidate_count",
                "metrics": ["model_accuracy", "route_cost_baseline_accuracy"],
                "role": "mandatory_descriptive_report",
            },
            "primary": {
                "case_filter": "cost_baseline_challenge_hypothesis_true",
                "expected_case_count": challenge_count,
                "minimum_measured_teacher_baseline_disagreements": 6,
                "paired_test": (
                    "two_sided_exact_mcnemar_on_discordant_correctness"
                ),
                "primary_unit": "one_unique_scenario",
                "required_direction": "model_paired_wins_exceed_losses",
                "required_successful_teacher_cases": challenge_count,
                "significance_threshold": 0.05,
            },
            "safety": {
                "case_filter": "cost_baseline_challenge_hypothesis_false",
                "criterion": (
                    "all_cases_succeed_and_zero_model_incorrect_baseline_correct"
                ),
                "expected_case_count": len(cases) - challenge_count,
                "failure_effect": (
                    "block_live_authority_and_report_without_changing_primary_test"
                ),
                "role": "preregistered_baseline_favorable_non_regression",
            },
        },
        "evaluation_id": EVALUATION_ID,
        "execution_policy": {
            "candidate_counts_by_case": candidate_counts_by_case,
            "case_claim": "durable_before_any_private_case_input_access",
            "case_order": case_order,
            "case_order_frozen": True,
            "halt_after_first_claim": "publish_protocol_failure",
            "intermediate_case_results": "forbidden",
            "intermediate_statistics": "forbidden",
            "prediction_commit": "durable_before_deterministic_teacher_action",
            "reopen_consumed_case": False,
            "restart_after_claim": (
                "consume_open_case_as_both_incorrect_continue_next_mark_protocol_failure"
            ),
            "score_after_consumed_cases": len(cases),
            "single_continuous_invocation_required": True,
        },
        "execution_source_bundle_sha256": source_bundle_sha256,
        "frozen_model": {
            "canonical_sha256": FROZEN_MODEL_SHA256,
            "enabled_feature_names": list(FROZEN_FEATURES),
            "feature_schema_id": STRATEGIC_NAVIGATION_FEATURE_SCHEMA_ID,
            "feature_set_id": "relative_route",
            "l2": 0.1,
            "model_id": STRATEGIC_NAVIGATION_LINEAR_MODEL_ID,
            "parameter_count": 5,
            "private_file_sha256": FROZEN_MODEL_FILE_SHA256,
            "training_epochs": 600,
        },
        "minimum_challenge_hypotheses": (
            STRATEGIC_SEALED_TEST_MINIMUM_CHALLENGE_HYPOTHESES
        ),
        "preregistered_challenge_hypotheses": challenge_count,
        "scoring_policy": {
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
        },
        "schema": PLAN_SCHEMA,
        "source_scenario_registry_sha256": registry.registry_sha256,
        "teacher_execution": {
            "behavior_configuration_sha256": (
                teacher_execution.behavior_configuration_sha256
            ),
            "decision_contract_sha256": teacher_execution.decision_contract_sha256,
            "objective_graph_sha256": teacher_execution.objective_graph_sha256,
            "source_bundle_sha256": teacher_execution.source_bundle_sha256,
            "teacher_execution_sha256": teacher_execution.teacher_execution_sha256,
        },
        "training_development_receipt_sha256": hashlib.sha256(
            DEVELOPMENT_RECEIPT.read_bytes()
        ).hexdigest(),
    }
    payload = _canonical_line(document)
    digest = hashlib.sha256(payload).hexdigest()
    digest_payload = _canonical_line(
        {
            "bytes": len(payload),
            "schema": DIGEST_SCHEMA,
            "sha256": digest,
        }
    )
    summary = {
        "bytes": len(payload),
        "evaluation_id": EVALUATION_ID,
        "plan_sha256": digest,
        "primary_endpoint_cases": challenge_count,
        "case_order_sha256": canonical_sha256(case_order),
        "intermediate_metrics_allowed": False,
        "preregistered_challenge_hypotheses": challenge_count,
        "private_test_inputs_opened": 0,
        "safety_endpoint_cases": len(cases) - challenge_count,
        "test_cases": len(cases),
    }
    return payload, digest_payload, summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    payload, digest_payload, summary = _generated_payloads()
    if args.check:
        if (
            not PLAN_PATH.is_file()
            or not DIGEST_PATH.is_file()
            or PLAN_PATH.read_bytes() != payload
            or DIGEST_PATH.read_bytes() != digest_payload
        ):
            raise SystemExit("strategic sealed evaluation plan is stale")
    else:
        PLAN_PATH.parent.mkdir(parents=True, exist_ok=True)
        PLAN_PATH.write_bytes(payload)
        DIGEST_PATH.write_bytes(digest_payload)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
