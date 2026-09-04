"""Authenticate the stored zero-train supplement without inventing a mixed schedule."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import cast

from pokemon_red_completion.living_dex_capture_curriculum import LivingDexCapturePartition
from pokemon_red_completion.living_dex_clustered_curriculum import (
    LivingDexClusteredScenarioCapability,
)
from pokemon_red_completion.living_dex_development_supplement import (
    LivingDexDevelopmentSupplementCapability,
    LivingDexDevelopmentSupplementPlan,
    LivingDexDevelopmentSupplementPolicy,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_capture_plan import (
    build_red_living_dex_prospective_capture_plan,
)
from pokemon_red_completion.red_living_dex_clustered_schedule_plan import _validate_recipe
from pokemon_red_completion.red_living_dex_development_supplement_plan import (
    RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PLAN_RECORD_ID,
    RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PLAN_RECORD_KIND,
    RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PRIVATE_PLAN_SCHEMA,
    RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PRIVATE_PLAN_STATUS,
    RedLivingDexDevelopmentSupplementBindings,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RED_LIVING_DEX_SETUP_SLOT_RECIPE_SCHEMA,
)

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_ZERO_FIELDS = {
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
    "training_targets",
    "unselected_action_targets",
}
_BINDING_FIELDS = {item.name for item in fields(RedLivingDexDevelopmentSupplementBindings)}
_PLAN_KEYS = (
    _ZERO_FIELDS
    | _BINDING_FIELDS
    | {
        "assignments",
        "collection_authorized",
        "schema",
        "status",
        "supplement",
        "supplement_plan_sha256",
        "supplement_policy_sha256",
        "private_plan_sha256",
    }
)


class RedLivingDexDevelopmentSupplementReadError(ValueError):
    """The complete stored supplement or an exact recipe binding differs."""


@dataclass(frozen=True, slots=True)
class RedLivingDexDevelopmentSupplementBinding:
    private_plan_sha256: str
    supplement_plan_sha256: str
    plan_manifest_sha256: str
    plan_record_sha256: str
    model_sha256: str
    model_record_sha256: str
    record_id: str = RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PLAN_RECORD_ID
    record_kind: str = RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PLAN_RECORD_KIND

    def __post_init__(self) -> None:
        for value in (
            self.private_plan_sha256,
            self.supplement_plan_sha256,
            self.plan_manifest_sha256,
            self.plan_record_sha256,
            self.model_sha256,
            self.model_record_sha256,
        ):
            if not isinstance(value, str) or _SHA.fullmatch(value) is None:
                raise RedLivingDexDevelopmentSupplementReadError("supplement binding differs")
        if (
            self.record_id != RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PLAN_RECORD_ID
            or self.record_kind != RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PLAN_RECORD_KIND
        ):
            raise RedLivingDexDevelopmentSupplementReadError("supplement record kind differs")

    @property
    def train_scenarios(self) -> int:
        return 0

    @property
    def development_scenarios(self) -> int:
        return 3


def validate_red_living_dex_development_supplement(
    document: Mapping[str, object],
    *,
    binding: RedLivingDexDevelopmentSupplementBinding,
) -> LivingDexDevelopmentSupplementPlan:
    """Validate the whole record, all three rows and the shared coverage contract."""

    if not isinstance(binding, RedLivingDexDevelopmentSupplementBinding):
        raise TypeError("supplement reader needs its exact binding")
    binding.__post_init__()
    try:
        if not isinstance(document, Mapping) or set(document) != _PLAN_KEYS:
            raise ValueError("fields")
        payload = {k: v for k, v in document.items() if k != "private_plan_sha256"}
        if (
            document["schema"] != RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PRIVATE_PLAN_SCHEMA
            or document["status"] != RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PRIVATE_PLAN_STATUS
            or document["collection_authorized"] is not False
            or any(type(document[k]) is not int or document[k] != 0 for k in _ZERO_FIELDS)
            or document["private_plan_sha256"] != binding.private_plan_sha256
            or canonical_sha256(payload) != binding.private_plan_sha256
            or document["model_sha256"] != binding.model_sha256
            or document["model_record_sha256"] != binding.model_record_sha256
            or document["supplement_plan_sha256"] != binding.supplement_plan_sha256
        ):
            raise ValueError("commitment")
        RedLivingDexDevelopmentSupplementBindings(
            **{key: cast(str, document[key]) for key in _BINDING_FIELDS}
        )
        shared = _parse_shared(document["supplement"])
        if (
            shared.plan_sha256 != document["supplement_plan_sha256"]
            or shared.policy.policy_sha256 != document["supplement_policy_sha256"]
        ):
            raise ValueError("shared commitment")
        raw_rows = document["assignments"]
        if not isinstance(raw_rows, list) or len(raw_rows) != binding.development_scenarios:
            raise ValueError("rows")
        slots = build_red_living_dex_prospective_capture_plan().slots
        contexts: set[str] = set()
        logical_roots: set[str] = set()
        for ordinal, (row, expected) in enumerate(zip(raw_rows, shared.assignments, strict=True)):
            if not isinstance(row, dict) or set(row) != set(expected.private_dict()) | {
                "context_identity_sha256",
                "ordinal",
                "partition",
                "recipe",
                "recipe_sha256",
                "root_consumption_sha256",
                "root_envelope_sha256",
                "root_state_sha256",
                "template_ordinal",
                "template_sha256",
            }:
                raise ValueError("row fields")
            template = row["template_ordinal"]
            if type(template) is not int or not 0 <= template < len(slots):
                raise ValueError("template")
            slot = slots[template]
            projected = LivingDexClusteredScenarioCapability(
                lineage_sha256=expected.lineage_sha256,
                physical_root_sha256=expected.physical_root_sha256,
                partition="development",
                template_sha256=slot.slot_sha256,
                available_option_kinds=expected.available_option_kinds,
            )
            if (
                type(row["ordinal"]) is not int
                or row["ordinal"] != ordinal
                or row["partition"] != "development"
                or slot.partition is not LivingDexCapturePartition.DEVELOPMENT
                or row["template_sha256"] != slot.slot_sha256
                or expected.scenario_sha256 != projected.scenario_sha256
                or expected.available_option_kinds != slot.available_option_kinds
                or expected.family_scope_id != slot.family_scope_id
                or expected.location_scope_id != slot.location_scope_id
                or any(row[k] != v for k, v in expected.private_dict().items())
            ):
                raise ValueError("row join")
            for key in (
                "context_identity_sha256",
                "root_consumption_sha256",
                "root_state_sha256",
                "root_envelope_sha256",
                "recipe_sha256",
            ):
                if not isinstance(row[key], str) or _SHA.fullmatch(row[key]) is None:
                    raise ValueError("row digest")
            context = cast(str, row["context_identity_sha256"])
            logical_root = cast(str, row["root_consumption_sha256"])
            if context in contexts or logical_root in logical_roots:
                raise ValueError("duplicate context")
            contexts.add(context)
            logical_roots.add(logical_root)
            recipe = row["recipe"]
            if (
                not isinstance(recipe, dict)
                or recipe.get("schema") != RED_LIVING_DEX_SETUP_SLOT_RECIPE_SCHEMA
            ):
                raise ValueError("recipe schema")
            _validate_recipe(row)
        return shared
    except (KeyError, TypeError, ValueError, OverflowError):
        raise RedLivingDexDevelopmentSupplementReadError(
            "development supplement authentication failed"
        ) from None


def _parse_shared(raw: object) -> LivingDexDevelopmentSupplementPlan:
    if not isinstance(raw, dict) or not isinstance(raw.get("policy"), dict):
        raise ValueError("shared plan")
    p = raw["policy"]
    policy = LivingDexDevelopmentSupplementPolicy(
        **{
            name: p[name]
            for name in (
                "new_roots",
                "minimum_surviving_roots",
                "minimum_new_families",
                "minimum_new_locations",
                "held_root_count",
                "required_total_roots",
            )
        },
        held_option_kinds=tuple(LivingDexOptionKind(k) for k in p["held_option_kinds"]),
        required_option_kinds=tuple(LivingDexOptionKind(k) for k in p["required_option_kinds"]),
    )
    if (policy.new_roots, policy.minimum_surviving_roots, policy.held_root_count) != (3, 2, 2):
        raise ValueError("supplement policy")
    rows = raw.get("assignments")
    if not isinstance(rows, list):
        raise ValueError("shared rows")
    assignments = tuple(
        LivingDexDevelopmentSupplementCapability(
            **{
                key: row[key]
                for key in (
                    "lineage_sha256",
                    "physical_root_sha256",
                    "scenario_sha256",
                    "family_scope_id",
                    "location_scope_id",
                )
            },
            available_option_kinds=tuple(
                LivingDexOptionKind(k) for k in row["available_option_kinds"]
            ),
        )
        for row in rows
    )
    result = LivingDexDevelopmentSupplementPlan(policy, assignments)
    if canonical_sha256(result.private_dict()) != canonical_sha256(raw):
        raise ValueError("shared canonical form")
    return result
