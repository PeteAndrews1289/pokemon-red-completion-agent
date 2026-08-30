"""Private, action-free Red schedule plan for the clustered living-Dex curriculum.

The title-neutral scheduler decides which root/template scenarios belong in the
integration tranche.  This module binds those decisions back to authenticated
Red contexts and executable setup recipes without choosing an arm, observing an
outcome, or granting controller authority.  The private document is deliberately
redundant: an independent reader can cross-check the cluster assignment, Red
template, root commitments, and recipe before any later execution is armed.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexCapturePartition,
)
from pokemon_red_completion.living_dex_clustered_curriculum import (
    LIVING_DEX_CLUSTERED_CURRICULUM_SCHEMA,
    LIVING_DEX_CLUSTERED_PRIVATE_SCHEDULE_SCHEMA,
    LivingDexClusteredCurriculumPolicy,
    LivingDexClusteredCurriculumSchedule,
    LivingDexClusteredScenarioAssignment,
    LivingDexClusteredScenarioCapability,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_capture_plan import (
    build_red_living_dex_prospective_capture_plan,
)
from pokemon_red_completion.red_living_dex_causal_inventory import (
    RedLivingDexCausalRootCapability,
)

RED_LIVING_DEX_CLUSTERED_PRIVATE_PLAN_SCHEMA = (
    "pokemon.red.private-living-dex-clustered-schedule-plan.v1"
)
RED_LIVING_DEX_CLUSTERED_PRIVATE_PLAN_STATUS = (
    "frozen_before_claim_controller_input_arm_selection_outcome_or_fit"
)
RED_LIVING_DEX_CLUSTERED_PLAN_RECORD_ID = "red-living-dex-clustered-schedule-plan-v1"
RED_LIVING_DEX_CLUSTERED_PLAN_RECORD_KIND = "red-living-dex-clustered-schedule-plan-v1"
RED_LIVING_DEX_CLUSTERED_SUCCESSOR_PLAN_RECORD_ID = (
    "red-living-dex-clustered-successor-plan-v1"
)
RED_LIVING_DEX_CLUSTERED_SUCCESSOR_PLAN_RECORD_KIND = (
    "red-living-dex-clustered-successor-plan-v1"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_ZERO_FIELDS = (
    "behavior_commitments",
    "controller_actions",
    "development_outcomes_opened",
    "emulator_frames",
    "model_fits",
    "model_predictions",
    "outcomes_observed",
    "provider_executions",
    "root_claims",
    "teacher_queries",
    "unselected_action_targets",
)
_PLAN_KEYS = {
    "assignments",
    "behavior_commitments",
    "census_receipt_sha256",
    "clustered_schedule",
    "clustered_schedule_sha256",
    "collection_authorized",
    "context_catalog_sha256",
    "context_plan_sha256",
    "controller_actions",
    "development_outcomes_opened",
    "emulator_frames",
    "goal_registry_sha256",
    "model_fits",
    "model_predictions",
    "outcomes_observed",
    "policy_sha256",
    "private_plan_sha256",
    "provider_executions",
    "rom_sha256",
    "root_claims",
    "route_registry_sha256",
    "runtime_identity_sha256",
    "schema",
    "source_bundle_sha256",
    "source_commit",
    "status",
    "teacher_queries",
    "unselected_action_targets",
}
_ASSIGNMENT_KEYS = {
    "available_option_kinds",
    "context_identity_sha256",
    "lineage_sha256",
    "ordinal",
    "partition",
    "physical_root_sha256",
    "recipe",
    "recipe_sha256",
    "root_consumption_sha256",
    "root_envelope_sha256",
    "root_state_sha256",
    "scenario_sha256",
    "template_ordinal",
    "template_sha256",
    "within_lineage_ordinal",
}
_RECIPE_KEYS = {
    "available_option_kinds",
    "base_boundary_sha256",
    "construction_route_sha256",
    "origin_boundary_sha256",
    "partition",
    "providers",
    "root_consumption_sha256",
    "root_envelope_sha256",
    "root_state_sha256",
    "schema",
    "slot_sha256",
}
_POLICY_KEYS = {
    "cluster_weighting",
    "development_scenarios",
    "eventual_minimum_train_outcomes",
    "maximum_scenarios_per_lineage",
    "minimum_development_lineages",
    "minimum_development_option_kinds",
    "minimum_train_lineages",
    "minimum_train_option_kinds",
    "schema",
    "train_scenarios",
}


class RedLivingDexClusteredSchedulePlanError(ValueError):
    """A private clustered plan is incomplete, mutated, or cross-bound."""


@dataclass(frozen=True, slots=True)
class RedLivingDexClusteredScheduleBindings:
    """Exact public and private-input commitments for one action-free freeze."""

    source_commit: str
    source_bundle_sha256: str
    rom_sha256: str
    goal_registry_sha256: str
    route_registry_sha256: str
    context_catalog_sha256: str
    context_plan_sha256: str
    runtime_identity_sha256: str
    census_receipt_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.source_commit, str) or _COMMIT.fullmatch(self.source_commit) is None:
            raise RedLivingDexClusteredSchedulePlanError("clustered plan source commit differs")
        for value, subject in (
            (self.source_bundle_sha256, "source bundle"),
            (self.rom_sha256, "ROM"),
            (self.goal_registry_sha256, "goal registry"),
            (self.route_registry_sha256, "route registry"),
            (self.context_catalog_sha256, "context catalog"),
            (self.context_plan_sha256, "context plan"),
            (self.runtime_identity_sha256, "runtime identity"),
            (self.census_receipt_sha256, "census receipt"),
        ):
            _require_sha256(value, subject)

    def private_dict(self) -> dict[str, str]:
        return {
            "census_receipt_sha256": self.census_receipt_sha256,
            "context_catalog_sha256": self.context_catalog_sha256,
            "context_plan_sha256": self.context_plan_sha256,
            "goal_registry_sha256": self.goal_registry_sha256,
            "rom_sha256": self.rom_sha256,
            "route_registry_sha256": self.route_registry_sha256,
            "runtime_identity_sha256": self.runtime_identity_sha256,
            "source_bundle_sha256": self.source_bundle_sha256,
            "source_commit": self.source_commit,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexClusteredFrozenScenario:
    """One cluster assignment joined to its authentic Red context and recipe."""

    assignment: LivingDexClusteredScenarioAssignment
    capability: RedLivingDexCausalRootCapability
    context_identity_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.assignment, LivingDexClusteredScenarioAssignment):
            raise TypeError("clustered frozen scenario needs an assignment")
        if not isinstance(self.capability, RedLivingDexCausalRootCapability):
            raise TypeError("clustered frozen scenario needs a Red capability")
        self.assignment.__post_init__()
        self.capability.__post_init__()
        _require_sha256(self.context_identity_sha256, "context identity")
        cluster = self.assignment.capability
        root = self.capability.root
        slot_partition = (
            "train"
            if self.capability.slot.partition is LivingDexCapturePartition.TRAIN
            else "development"
        )
        if (
            cluster.lineage_sha256 != root.independence_lineage_sha256
            or cluster.physical_root_sha256 != root.root.physical_root_sha256
            or cluster.partition != root.cluster_partition
            or cluster.partition != slot_partition
            or cluster.template_sha256 != self.capability.slot.slot_sha256
            or cluster.available_option_kinds != self.capability.slot.available_option_kinds
            or self.capability.recipe.slot_sha256 != cluster.template_sha256
        ):
            raise RedLivingDexClusteredSchedulePlanError(
                "cluster assignment does not join its Red capability"
            )

    def private_dict(self) -> dict[str, object]:
        cluster = self.assignment.capability
        root = self.capability.root.root
        recipe = self.capability.recipe
        return {
            "available_option_kinds": [item.value for item in cluster.available_option_kinds],
            "context_identity_sha256": self.context_identity_sha256,
            "lineage_sha256": cluster.lineage_sha256,
            "ordinal": self.assignment.ordinal,
            "partition": cluster.partition,
            "physical_root_sha256": cluster.physical_root_sha256,
            "recipe": recipe.private_dict(),
            "recipe_sha256": recipe.recipe_sha256,
            "root_consumption_sha256": root.root_consumption_sha256,
            "root_envelope_sha256": root.envelope_sha256,
            "root_state_sha256": root.state_sha256,
            "scenario_sha256": cluster.scenario_sha256,
            "template_ordinal": self.capability.template_ordinal,
            "template_sha256": cluster.template_sha256,
            "within_lineage_ordinal": self.assignment.within_lineage_ordinal,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexClusteredPrivatePlan:
    """One canonical, identity-bearing schedule frozen before every effect."""

    bindings: RedLivingDexClusteredScheduleBindings
    schedule: LivingDexClusteredCurriculumSchedule
    assignments: tuple[RedLivingDexClusteredFrozenScenario, ...]

    def __post_init__(self) -> None:
        if not isinstance(
            self.bindings,
            RedLivingDexClusteredScheduleBindings,
        ):
            raise TypeError("clustered private plan bindings differ")
        if not isinstance(self.schedule, LivingDexClusteredCurriculumSchedule):
            raise TypeError("clustered private plan schedule differs")
        self.bindings.__post_init__()
        self.schedule.__post_init__()
        if (
            not isinstance(self.assignments, tuple)
            or len(self.assignments) != len(self.schedule.assignments)
            or any(
                not isinstance(item, RedLivingDexClusteredFrozenScenario)
                for item in self.assignments
            )
        ):
            raise RedLivingDexClusteredSchedulePlanError(
                "clustered private plan assignments differ"
            )
        for expected, frozen in zip(
            self.schedule.assignments,
            self.assignments,
            strict=True,
        ):
            frozen.__post_init__()
            if frozen.assignment != expected:
                raise RedLivingDexClusteredSchedulePlanError(
                    "clustered private plan assignment order differs"
                )

    @property
    def private_plan_sha256(self) -> str:
        return canonical_sha256(self.payload_dict())

    def payload_dict(self) -> dict[str, object]:
        return {
            "assignments": [item.private_dict() for item in self.assignments],
            "behavior_commitments": 0,
            **self.bindings.private_dict(),
            "clustered_schedule": self.schedule.private_dict(),
            "clustered_schedule_sha256": self.schedule.schedule_sha256,
            "collection_authorized": False,
            "controller_actions": 0,
            "development_outcomes_opened": 0,
            "emulator_frames": 0,
            "model_fits": 0,
            "model_predictions": 0,
            "outcomes_observed": 0,
            "policy_sha256": self.schedule.policy.policy_sha256,
            "provider_executions": 0,
            "root_claims": 0,
            "schema": RED_LIVING_DEX_CLUSTERED_PRIVATE_PLAN_SCHEMA,
            "status": RED_LIVING_DEX_CLUSTERED_PRIVATE_PLAN_STATUS,
            "teacher_queries": 0,
            "unselected_action_targets": 0,
        }

    def private_dict(self) -> dict[str, object]:
        return {
            **self.payload_dict(),
            "private_plan_sha256": self.private_plan_sha256,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            **self.schedule.public_dict(),
            "collection_authorized": False,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "private_plan_sha256": self.private_plan_sha256,
            "schema": "pokemon.red.living-dex-clustered-schedule-freeze-result.v1",
            "status": "authenticated_action_free_clustered_schedule_frozen",
        }


def validate_red_living_dex_clustered_private_plan(
    document: Mapping[str, object],
    *,
    expected_bindings: RedLivingDexClusteredScheduleBindings | None = None,
    expected_schedule_sha256: str | None = None,
    expected_policy_sha256: str | None = None,
) -> LivingDexClusteredCurriculumSchedule:
    """Independently parse and cross-check one reopened private plan."""

    if not isinstance(document, Mapping) or set(document) != _PLAN_KEYS:
        raise RedLivingDexClusteredSchedulePlanError("clustered private plan fields differ")
    payload = {key: value for key, value in document.items() if key != "private_plan_sha256"}
    if (
        document.get("schema") != RED_LIVING_DEX_CLUSTERED_PRIVATE_PLAN_SCHEMA
        or document.get("status") != RED_LIVING_DEX_CLUSTERED_PRIVATE_PLAN_STATUS
        or document.get("collection_authorized") is not False
        or any(document.get(field) != 0 for field in _ZERO_FIELDS)
        or _require_sha256(
            document.get("private_plan_sha256"),
            "private plan",
        )
        != canonical_sha256(payload)
    ):
        raise RedLivingDexClusteredSchedulePlanError("clustered private plan commitment differs")
    bindings = _parse_bindings(document)
    if expected_bindings is not None and bindings != expected_bindings:
        raise RedLivingDexClusteredSchedulePlanError("clustered private plan bindings differ")
    schedule = _parse_schedule(document.get("clustered_schedule"))
    schedule_sha256 = _require_sha256(
        document.get("clustered_schedule_sha256"),
        "clustered schedule",
    )
    policy_sha256 = _require_sha256(
        document.get("policy_sha256"),
        "clustered policy",
    )
    if (
        schedule.schedule_sha256 != schedule_sha256
        or schedule.policy.policy_sha256 != policy_sha256
        or (
            expected_schedule_sha256 is not None
            and _require_sha256(expected_schedule_sha256, "expected schedule") != schedule_sha256
        )
        or (
            expected_policy_sha256 is not None
            and _require_sha256(expected_policy_sha256, "expected policy") != policy_sha256
        )
    ):
        raise RedLivingDexClusteredSchedulePlanError(
            "clustered private schedule commitment differs"
        )
    _validate_red_assignments(document.get("assignments"), schedule)
    return schedule


def _parse_bindings(
    document: Mapping[str, object],
) -> RedLivingDexClusteredScheduleBindings:
    try:
        return RedLivingDexClusteredScheduleBindings(
            source_commit=cast(str, document["source_commit"]),
            source_bundle_sha256=cast(str, document["source_bundle_sha256"]),
            rom_sha256=cast(str, document["rom_sha256"]),
            goal_registry_sha256=cast(str, document["goal_registry_sha256"]),
            route_registry_sha256=cast(str, document["route_registry_sha256"]),
            context_catalog_sha256=cast(str, document["context_catalog_sha256"]),
            context_plan_sha256=cast(str, document["context_plan_sha256"]),
            runtime_identity_sha256=cast(str, document["runtime_identity_sha256"]),
            census_receipt_sha256=cast(str, document["census_receipt_sha256"]),
        )
    except (KeyError, TypeError, ValueError):
        raise RedLivingDexClusteredSchedulePlanError(
            "clustered private plan bindings differ"
        ) from None


def _parse_schedule(value: object) -> LivingDexClusteredCurriculumSchedule:
    if not isinstance(value, Mapping) or set(value) != {
        "assignments",
        "outcomes_observed",
        "policy",
        "schema",
        "teacher_queries",
    }:
        raise RedLivingDexClusteredSchedulePlanError("clustered private schedule fields differ")
    policy = _parse_policy(value.get("policy"))
    if (
        value.get("schema") != LIVING_DEX_CLUSTERED_PRIVATE_SCHEDULE_SCHEMA
        or value.get("outcomes_observed") != 0
        or value.get("teacher_queries") != 0
        or value.get("policy") != policy.public_dict()
    ):
        raise RedLivingDexClusteredSchedulePlanError("clustered private schedule policy differs")
    raw_assignments = value.get("assignments")
    if not isinstance(raw_assignments, list):
        raise RedLivingDexClusteredSchedulePlanError(
            "clustered private schedule assignments differ"
        )
    assignments = tuple(_parse_cluster_assignment(raw) for raw in raw_assignments)
    try:
        schedule = LivingDexClusteredCurriculumSchedule(
            policy=policy,
            assignments=assignments,
        )
    except (TypeError, ValueError):
        raise RedLivingDexClusteredSchedulePlanError(
            "clustered private schedule assignments differ"
        ) from None
    if schedule.private_dict() != dict(value):
        raise RedLivingDexClusteredSchedulePlanError(
            "clustered private schedule canonical form differs"
        )
    return schedule


def _parse_policy(value: object) -> LivingDexClusteredCurriculumPolicy:
    """Restore the exact frozen policy instead of assuming the V1 pilot size."""

    if (
        not isinstance(value, Mapping)
        or set(value) != _POLICY_KEYS
        or value.get("schema") != LIVING_DEX_CLUSTERED_CURRICULUM_SCHEMA
        or value.get("cluster_weighting") != "equal_total_weight_per_lineage"
    ):
        raise RedLivingDexClusteredSchedulePlanError(
            "clustered private schedule policy differs"
        )
    try:
        return LivingDexClusteredCurriculumPolicy(
            train_scenarios=cast(int, value["train_scenarios"]),
            development_scenarios=cast(int, value["development_scenarios"]),
            minimum_train_lineages=cast(int, value["minimum_train_lineages"]),
            minimum_development_lineages=cast(
                int,
                value["minimum_development_lineages"],
            ),
            minimum_train_option_kinds=cast(
                int,
                value["minimum_train_option_kinds"],
            ),
            minimum_development_option_kinds=cast(
                int,
                value["minimum_development_option_kinds"],
            ),
            maximum_scenarios_per_lineage=cast(
                int,
                value["maximum_scenarios_per_lineage"],
            ),
            eventual_minimum_train_outcomes=cast(
                int,
                value["eventual_minimum_train_outcomes"],
            ),
        )
    except (KeyError, TypeError, ValueError):
        raise RedLivingDexClusteredSchedulePlanError(
            "clustered private schedule policy differs"
        ) from None


def _parse_cluster_assignment(value: object) -> LivingDexClusteredScenarioAssignment:
    if not isinstance(value, Mapping) or set(value) != {
        "capability",
        "ordinal",
        "within_lineage_ordinal",
    }:
        raise RedLivingDexClusteredSchedulePlanError("cluster assignment fields differ")
    raw_capability = value.get("capability")
    if not isinstance(raw_capability, Mapping) or set(raw_capability) != {
        "available_option_kinds",
        "lineage_sha256",
        "partition",
        "physical_root_sha256",
        "scenario_sha256",
        "template_sha256",
    }:
        raise RedLivingDexClusteredSchedulePlanError("cluster capability fields differ")
    raw_kinds = raw_capability.get("available_option_kinds")
    if not isinstance(raw_kinds, list):
        raise RedLivingDexClusteredSchedulePlanError("cluster capability option kinds differ")
    try:
        capability = LivingDexClusteredScenarioCapability(
            lineage_sha256=cast(str, raw_capability["lineage_sha256"]),
            physical_root_sha256=cast(str, raw_capability["physical_root_sha256"]),
            partition=cast(str, raw_capability["partition"]),  # type: ignore[arg-type]
            template_sha256=cast(str, raw_capability["template_sha256"]),
            available_option_kinds=tuple(LivingDexOptionKind(item) for item in raw_kinds),
        )
        if raw_capability.get("scenario_sha256") != capability.scenario_sha256:
            raise RedLivingDexClusteredSchedulePlanError("cluster capability identity differs")
        return LivingDexClusteredScenarioAssignment(
            ordinal=cast(int, value["ordinal"]),
            capability=capability,
            within_lineage_ordinal=cast(int, value["within_lineage_ordinal"]),
        )
    except (KeyError, TypeError, ValueError):
        raise RedLivingDexClusteredSchedulePlanError("cluster assignment differs") from None


def _validate_red_assignments(
    value: object,
    schedule: LivingDexClusteredCurriculumSchedule,
) -> None:
    if not isinstance(value, list) or len(value) != len(schedule.assignments):
        raise RedLivingDexClusteredSchedulePlanError("Red clustered assignment count differs")
    slots = build_red_living_dex_prospective_capture_plan().slots
    for raw, cluster in zip(value, schedule.assignments, strict=True):
        if not isinstance(raw, Mapping) or set(raw) != _ASSIGNMENT_KEYS:
            raise RedLivingDexClusteredSchedulePlanError("Red clustered assignment fields differ")
        capability = cluster.capability
        kinds = [item.value for item in capability.available_option_kinds]
        template_ordinal = raw.get("template_ordinal")
        if type(template_ordinal) is not int or not 0 <= template_ordinal < len(slots):  # noqa: E721
            raise RedLivingDexClusteredSchedulePlanError("Red clustered template ordinal differs")
        slot = slots[template_ordinal]
        expected_partition = (
            "train" if slot.partition is LivingDexCapturePartition.TRAIN else "development"
        )
        for field in (
            "context_identity_sha256",
            "lineage_sha256",
            "physical_root_sha256",
            "recipe_sha256",
            "root_consumption_sha256",
            "root_envelope_sha256",
            "root_state_sha256",
            "scenario_sha256",
            "template_sha256",
        ):
            _require_sha256(raw.get(field), field)
        if (
            raw.get("ordinal") != cluster.ordinal
            or raw.get("within_lineage_ordinal") != cluster.within_lineage_ordinal
            or raw.get("partition") != capability.partition
            or raw.get("partition") != expected_partition
            or raw.get("lineage_sha256") != capability.lineage_sha256
            or raw.get("physical_root_sha256") != capability.physical_root_sha256
            or raw.get("scenario_sha256") != capability.scenario_sha256
            or raw.get("template_sha256") != capability.template_sha256
            or raw.get("template_sha256") != slot.slot_sha256
            or raw.get("available_option_kinds") != kinds
            or kinds != [item.value for item in slot.available_option_kinds]
        ):
            raise RedLivingDexClusteredSchedulePlanError(
                "Red clustered assignment differs from its schedule"
            )
        _validate_recipe(raw)


def _validate_recipe(raw: Mapping[str, object]) -> None:
    recipe = raw.get("recipe")
    if not isinstance(recipe, Mapping) or set(recipe) != _RECIPE_KEYS:
        raise RedLivingDexClusteredSchedulePlanError("Red clustered recipe fields differ")
    if canonical_sha256(recipe) != raw.get("recipe_sha256"):
        raise RedLivingDexClusteredSchedulePlanError("Red clustered recipe commitment differs")
    kinds = raw.get("available_option_kinds")
    providers = recipe.get("providers")
    if (
        recipe.get("slot_sha256") != raw.get("template_sha256")
        or recipe.get("partition") != raw.get("partition")
        or recipe.get("available_option_kinds") != kinds
        or recipe.get("root_consumption_sha256") != raw.get("root_consumption_sha256")
        or recipe.get("root_envelope_sha256") != raw.get("root_envelope_sha256")
        or recipe.get("root_state_sha256") != raw.get("root_state_sha256")
        or not isinstance(providers, list)
        or not isinstance(kinds, list)
        or len(providers) != len(kinds)
        or any(not isinstance(item, Mapping) for item in providers)
        or [item.get("option_kind") for item in providers] != kinds
    ):
        raise RedLivingDexClusteredSchedulePlanError(
            "Red clustered recipe does not join its assignment"
        )


def _require_sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedLivingDexClusteredSchedulePlanError(f"{subject} differs")
    return value


__all__ = [
    "RED_LIVING_DEX_CLUSTERED_PLAN_RECORD_ID",
    "RED_LIVING_DEX_CLUSTERED_PLAN_RECORD_KIND",
    "RED_LIVING_DEX_CLUSTERED_PRIVATE_PLAN_SCHEMA",
    "RED_LIVING_DEX_CLUSTERED_PRIVATE_PLAN_STATUS",
    "RED_LIVING_DEX_CLUSTERED_SUCCESSOR_PLAN_RECORD_ID",
    "RED_LIVING_DEX_CLUSTERED_SUCCESSOR_PLAN_RECORD_KIND",
    "RedLivingDexClusteredFrozenScenario",
    "RedLivingDexClusteredPrivatePlan",
    "RedLivingDexClusteredScheduleBindings",
    "RedLivingDexClusteredSchedulePlanError",
    "validate_red_living_dex_clustered_private_plan",
]
