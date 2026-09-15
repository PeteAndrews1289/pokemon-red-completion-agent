"""Frozen, path-free campaign contract for disposable Red battle qualification."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass

from pokemon_red_completion.cartridge_qualification import (
    QualificationCampaign,
    QualificationLimits,
)
from pokemon_red_completion.private_artifacts import (
    PrivateArtifactError,
    PrivateArtifactRoot,
)
from pokemon_red_completion.red_battle_contingency import CONTINGENCY_POLICY, LEGACY_POLICY
from pokemon_red_completion.repeatable_battle_scenario_factory import (
    RepeatableBattlePartyOption,
    RepeatableBattleScenarioAssignment,
    RepeatableBattleScenarioKind,
    RepeatableBattleSourceKind,
    RepeatableBattleSourceObservation,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition

CAMPAIGN_SCHEMA = "pokemon.red.battle-cartridge-campaign.v2"
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_EXPECTED_COVERAGE_GAPS = ("forced_switch", "move_learning", "same_battler_move_replacement")


class RedBattleCartridgeCampaignError(ValueError):
    """The prospective campaign declaration is invalid."""


@dataclass(frozen=True, slots=True)
class RedBattleCartridgeCase:
    case_id: str
    episode_id: str
    venue_id: str
    party_index: int
    menu_semantic_sha256: str
    pre_encounter_wait_frames: int
    coverage: str


@dataclass(frozen=True, slots=True)
class RedBattleCartridgeCampaignPlan:
    campaign_id: str
    source_commit: str
    source_bundle_sha256: str
    qualification_ci_run_id: int
    rom_sha256: str
    source: RepeatableBattleSourceObservation
    case_limits: QualificationLimits
    campaign_limits: QualificationLimits
    maximum_cases: int
    maximum_encounter_steps: int
    cases: tuple[RedBattleCartridgeCase, ...]
    coverage_gaps: tuple[str, ...]
    sha256: str
    policy: str


def parse_red_battle_cartridge_campaign(payload: bytes) -> RedBattleCartridgeCampaignPlan:
    """Parse the exact canonical private campaign declaration without paths."""
    if not isinstance(payload, bytes) or not 1 <= len(payload) <= 64 * 1024:
        raise RedBattleCartridgeCampaignError("campaign payload size is invalid")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RedBattleCartridgeCampaignError("campaign payload is not valid JSON") from None
    if not isinstance(value, dict) or _canonical_line(value) != payload:
        raise RedBattleCartridgeCampaignError("campaign payload is not canonical")
    _require_keys(
        value,
        {
            "schema",
            "campaign_id",
            "source_commit",
            "source_bundle_sha256",
            "qualification_ci_run_id",
            "rom_sha256",
            "source",
            "limits",
            "cases",
            "coverage_gaps",
            "policy",
            "correlated_development_only",
            "learning_credit",
            "evaluation_credit",
            "retry_allowed",
        },
        "campaign",
    )
    if (
        value["schema"] != CAMPAIGN_SCHEMA
        or value["policy"] not in (LEGACY_POLICY, CONTINGENCY_POLICY)
        or value["correlated_development_only"] is not True
        or value["learning_credit"] is not False
        or value["evaluation_credit"] is not False
        or value["retry_allowed"] is not False
    ):
        raise RedBattleCartridgeCampaignError("campaign authority declaration differs")
    campaign_id = _safe_id(value["campaign_id"], "campaign")
    source_commit = _commit(value["source_commit"])
    source_bundle = _sha256(value["source_bundle_sha256"], "source bundle")
    rom_sha256 = _sha256(value["rom_sha256"], "ROM")
    ci_run = value["qualification_ci_run_id"]
    if type(ci_run) is not int or ci_run <= 0:  # noqa: E721
        raise RedBattleCartridgeCampaignError("qualification CI run is invalid")
    source = _source(value["source"], source_commit)
    case_limits, campaign_limits, maximum_cases, maximum_steps = _limits(value["limits"])
    raw_cases = value["cases"]
    if not isinstance(raw_cases, list) or not 1 <= len(raw_cases) <= maximum_cases:
        raise RedBattleCartridgeCampaignError("campaign cases are invalid")
    cases = tuple(_case(item, source) for item in raw_cases)
    if len({item.case_id for item in cases}) != len(cases) or len(
        {item.episode_id for item in cases}
    ) != len(cases):
        raise RedBattleCartridgeCampaignError("campaign case identities repeat")
    venues = {item.venue_id for item in cases}
    if "route_11" not in venues or len(venues) < 2:
        raise RedBattleCartridgeCampaignError("campaign lacks control and cross-venue cases")
    gaps = value["coverage_gaps"]
    if not isinstance(gaps, list) or tuple(gaps) != _EXPECTED_COVERAGE_GAPS:
        raise RedBattleCartridgeCampaignError("coverage gaps differ")
    return RedBattleCartridgeCampaignPlan(
        campaign_id=campaign_id,
        source_commit=source_commit,
        source_bundle_sha256=source_bundle,
        qualification_ci_run_id=ci_run,
        rom_sha256=rom_sha256,
        source=source,
        case_limits=case_limits,
        campaign_limits=campaign_limits,
        maximum_cases=maximum_cases,
        maximum_encounter_steps=maximum_steps,
        cases=cases,
        coverage_gaps=tuple(gaps),
        sha256=hashlib.sha256(payload).hexdigest(),
        policy=value["policy"],
    )


def assignment_for_case(
    plan: RedBattleCartridgeCampaignPlan,
    case: RedBattleCartridgeCase,
) -> RepeatableBattleScenarioAssignment:
    return RepeatableBattleScenarioAssignment(
        scenario_id=f"{plan.campaign_id}-{case.case_id}",
        source_id=plan.source.source_id,
        source_lineage_id=plan.source.source_lineage_id,
        partition=plan.source.partition,
        source_state_sha256=plan.source.state_sha256,
        source_commit=plan.source.source_commit,
        scenario_kind=RepeatableBattleScenarioKind.WILD,
        party_index=case.party_index,
        menu_semantic_sha256=case.menu_semantic_sha256,
        venue_id=case.venue_id,
        pre_encounter_wait_frames=case.pre_encounter_wait_frames,
    )


def execute_red_battle_cartridge_campaign(
    plan: RedBattleCartridgeCampaignPlan,
    run_case: Callable[
        [RedBattleCartridgeCase, RepeatableBattleScenarioAssignment, QualificationCampaign],
        Mapping[str, object],
    ],
    *,
    before_case: Callable[
        [int, RedBattleCartridgeCase, QualificationCampaign], None
    ] = lambda index, case, campaign: None,
    after_case: Callable[
        [Mapping[str, object], QualificationCampaign], None
    ] = lambda result, campaign: None,
) -> dict[str, object]:
    """Execute in declared order and stop permanently at the first failure."""
    budget = QualificationCampaign(plan.campaign_limits, maximum_cases=plan.maximum_cases)
    results: list[dict[str, object]] = []
    failure: dict[str, object] | None = None
    for index, case in enumerate(plan.cases, start=1):
        before_case(index, case, budget)
        try:
            result = dict(run_case(case, assignment_for_case(plan, case), budget))
        except Exception as error:
            failure = {
                "case_id": case.case_id,
                "episode_id": case.episode_id,
                "error_type": type(error).__name__,
            }
            after_case(failure, budget)
            break
        retained = {"case_id": case.case_id, "episode_id": case.episode_id, **result}
        after_case(retained, budget)
        results.append(retained)
    passed = failure is None and len(results) == len(plan.cases)
    return {
        "schema": "pokemon.red.battle-cartridge-campaign-result.v2",
        "campaign_id": plan.campaign_id,
        "status": "passed_with_declared_coverage_gaps" if passed else "stopped_on_first_failure",
        "plan_sha256": plan.sha256,
        "policy": plan.policy,
        "source_commit": plan.source_commit,
        "source_bundle_sha256": plan.source_bundle_sha256,
        "qualification_ci_run_id": plan.qualification_ci_run_id,
        "declared_cases": len(plan.cases),
        "completed_cases": len(results),
        "coverage_gaps": list(plan.coverage_gaps),
        "actions_attempted": budget.actions_attempted,
        "actions_completed": budget.actions_completed,
        "emulator_frames": budget.frames,
        "cost_known": budget.cost_known,
        "campaign_closed": budget.closed,
        "failure": failure,
        "results": results,
        "model_queries": 0,
        "teacher_labels": 0,
        "training_examples": 0,
        "authority_promoted": False,
    }


def execute_durable_red_battle_cartridge_campaign(
    store: PrivateArtifactRoot,
    plan: RedBattleCartridgeCampaignPlan,
    run_case: Callable[
        [RedBattleCartridgeCase, RepeatableBattleScenarioAssignment, QualificationCampaign],
        Mapping[str, object],
    ],
) -> dict[str, object]:
    """Persist one non-resumable campaign epoch around all durable case episodes."""
    writer = store.begin_episode(plan.campaign_id)
    failed_evidence: dict[str, object] | None = None
    assignment = {
        "schema": CAMPAIGN_SCHEMA,
        "campaign_id": plan.campaign_id,
        "plan_sha256": plan.sha256,
        "policy": plan.policy,
        "source_commit": plan.source_commit,
        "source_bundle_sha256": plan.source_bundle_sha256,
        "qualification_ci_run_id": plan.qualification_ci_run_id,
        "source_state_sha256": plan.source.state_sha256,
        "rom_sha256": plan.rom_sha256,
        "case_episode_ids": [case.episode_id for case in plan.cases],
        "maximum_cases": plan.maximum_cases,
        "maximum_case_actions": plan.case_limits.maximum_actions,
        "maximum_case_frames": plan.case_limits.maximum_frames,
        "maximum_campaign_actions": plan.campaign_limits.maximum_actions,
        "maximum_campaign_frames": plan.campaign_limits.maximum_frames,
        "maximum_encounter_steps": plan.maximum_encounter_steps,
        "retry_allowed": False,
        "resume_allowed": False,
        "learning_credit": False,
        "evaluation_credit": False,
    }
    try:
        writer.append("assignment", assignment, durable=True)
        writer.append(
            "claim",
            {
                "campaign_status_at_claim": "new",
                "failure_count": 0,
                "input_status_at_claim": "not_yet_sent",
                "resume_allowed": False,
            },
            durable=True,
        )

        def before_case(
            index: int,
            case: RedBattleCartridgeCase,
            campaign: QualificationCampaign,
        ) -> None:
            writer.append(
                "campaign_journal",
                {
                    "event": "case_opening",
                    "case_ordinal": index,
                    "case_id": case.case_id,
                    "episode_id": case.episode_id,
                    **_budget_snapshot(campaign),
                },
                durable=True,
            )

        def after_case(result: Mapping[str, object], campaign: QualificationCampaign) -> None:
            writer.append(
                "campaign_journal",
                {"event": "case_closed", "result": dict(result), **_budget_snapshot(campaign)},
                durable=True,
            )

        result = execute_red_battle_cartridge_campaign(
            plan,
            run_case,
            before_case=before_case,
            after_case=after_case,
        )
        if result["status"] == "stopped_on_first_failure":
            failed_evidence = {
                "status": result["status"],
                "failure": result["failure"],
                "actions_attempted": result["actions_attempted"],
                "actions_completed": result["actions_completed"],
                "emulator_frames": result["emulator_frames"],
                "cost_known": result["cost_known"],
                "retry_allowed": False,
                "resume_allowed": False,
            }
            writer.append("failure_diagnostic", failed_evidence, durable=True)
            writer.abort("campaign_stopped_on_first_failure")
        else:
            terminal = {**result, "resume_allowed": False}
            writer.append("terminal", terminal, durable=True)
    except BaseException:
        with suppress(PrivateArtifactError):
            writer.abort("campaign_journal_failed")
        raise
    if failed_evidence is not None:
        reopened_failure = store.read_failed_episode_diagnostic(plan.campaign_id)
        if (
            reopened_failure.assignment != assignment
            or reopened_failure.failure_diagnostic != failed_evidence
        ):
            raise RuntimeError("campaign failure readback differs")
        return result
    writer.complete()
    reopened = list(store.open_episode(plan.campaign_id).iter_stream("terminal", max_records=1))
    if reopened != [terminal]:
        raise RuntimeError("campaign terminal readback differs")
    return result


def _budget_snapshot(campaign: QualificationCampaign) -> dict[str, object]:
    return {
        "cases_started": campaign.cases_started,
        "actions_attempted": campaign.actions_attempted,
        "actions_completed": campaign.actions_completed,
        "emulator_frames": campaign.frames,
        "cost_known": campaign.cost_known,
        "campaign_closed": campaign.closed,
    }


def _source(value: object, source_commit: str) -> RepeatableBattleSourceObservation:
    if not isinstance(value, dict):
        raise RedBattleCartridgeCampaignError("source declaration is invalid")
    _require_keys(
        value,
        {
            "source_id",
            "source_lineage_id",
            "partition",
            "state_sha256",
            "source_commit",
            "expected_map",
            "source_kind",
            "active_party_index",
            "reachable_venue_ids",
            "party_options",
        },
        "source",
    )
    if value["source_commit"] != source_commit or value["partition"] != "development":
        raise RedBattleCartridgeCampaignError("source authority differs")
    options = value["party_options"]
    if not isinstance(options, list):
        raise RedBattleCartridgeCampaignError("source party options are invalid")
    try:
        return RepeatableBattleSourceObservation(
            source_id=value["source_id"],
            source_lineage_id=value["source_lineage_id"],
            partition=ScenarioPartition(value["partition"]),
            state_sha256=value["state_sha256"],
            source_commit=value["source_commit"],
            expected_map=value["expected_map"],
            source_kind=RepeatableBattleSourceKind(value["source_kind"]),
            active_party_index=value["active_party_index"],
            reachable_venue_ids=tuple(value["reachable_venue_ids"]),
            party_options=tuple(
                RepeatableBattlePartyOption(
                    party_index=item["party_index"],
                    menu_semantic_sha256=item["menu_semantic_sha256"],
                    supported_move_count=item["supported_move_count"],
                    hp_ratio=item["hp_ratio"],
                )
                for item in options
            ),
        )
    except (KeyError, TypeError, ValueError):
        raise RedBattleCartridgeCampaignError("source declaration is invalid") from None


def _case(value: object, source: RepeatableBattleSourceObservation) -> RedBattleCartridgeCase:
    if not isinstance(value, dict):
        raise RedBattleCartridgeCampaignError("case declaration is invalid")
    _require_keys(
        value,
        {
            "case_id",
            "episode_id",
            "venue_id",
            "party_index",
            "menu_semantic_sha256",
            "pre_encounter_wait_frames",
            "coverage",
        },
        "case",
    )
    case_id = _safe_id(value["case_id"], "case")
    episode_id = _safe_id(value["episode_id"], "episode")
    matching = tuple(
        option for option in source.party_options if option.party_index == value["party_index"]
    )
    if (
        len(matching) != 1
        or matching[0].menu_semantic_sha256 != value["menu_semantic_sha256"]
        or value["venue_id"] not in source.reachable_venue_ids
        or type(value["pre_encounter_wait_frames"]) is not int  # noqa: E721
        or not 0 <= value["pre_encounter_wait_frames"] <= 4096
        or not isinstance(value["coverage"], str)
        or not value["coverage"]
    ):
        raise RedBattleCartridgeCampaignError("case differs from source")
    return RedBattleCartridgeCase(
        case_id=case_id,
        episode_id=episode_id,
        venue_id=value["venue_id"],
        party_index=value["party_index"],
        menu_semantic_sha256=value["menu_semantic_sha256"],
        pre_encounter_wait_frames=value["pre_encounter_wait_frames"],
        coverage=value["coverage"],
    )


def _limits(value: object) -> tuple[QualificationLimits, QualificationLimits, int, int]:
    if not isinstance(value, dict):
        raise RedBattleCartridgeCampaignError("campaign limits are invalid")
    _require_keys(
        value,
        {
            "maximum_case_actions",
            "maximum_case_frames",
            "maximum_campaign_actions",
            "maximum_campaign_frames",
            "maximum_cases",
            "maximum_encounter_steps",
        },
        "limits",
    )
    if (
        value["maximum_case_actions"] != 2_000
        or value["maximum_case_frames"] != 200_000
        or value["maximum_campaign_actions"] != 12_000
        or value["maximum_campaign_frames"] != 2_000_000
        or type(value["maximum_cases"]) is not int  # noqa: E721
        or not 1 <= value["maximum_cases"] <= 12
        or value["maximum_encounter_steps"] != 512
    ):
        raise RedBattleCartridgeCampaignError("campaign limits differ")
    return (
        QualificationLimits(2_000, 200_000),
        QualificationLimits(12_000, 2_000_000),
        value["maximum_cases"],
        512,
    )


def _require_keys(value: Mapping[str, object], expected: set[str], subject: str) -> None:
    if set(value) != expected:
        raise RedBattleCartridgeCampaignError(f"{subject} fields differ")


def _safe_id(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise RedBattleCartridgeCampaignError(f"{subject} identity is invalid")
    return value


def _sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedBattleCartridgeCampaignError(f"{subject} digest is invalid")
    return value


def _commit(value: object) -> str:
    if not isinstance(value, str) or _COMMIT.fullmatch(value) is None:
        raise RedBattleCartridgeCampaignError("source commit is invalid")
    return value


def _canonical_line(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        + b"\n"
    )
