"""Private Red binding for one title-neutral development supplement.

The shared planner selects identity-bearing but outcome-blind capabilities.
This adapter binds those selections back to exact Red roots, contexts, and
setup recipes.  It is a development-only plan: it cannot contain train rows,
model scores, behavior choices, outcomes, claims, or controller authority.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pokemon_red_completion.living_dex_development_supplement import (
    LivingDexDevelopmentSupplementCapability,
    LivingDexDevelopmentSupplementPlan,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_causal_inventory import (
    RedLivingDexCausalRootCapability,
)
from pokemon_red_completion.red_living_dex_development_supply import (
    build_red_living_dex_development_supplement_capabilities,
)

RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PRIVATE_PLAN_SCHEMA = (
    "pokemon.red.private-living-dex-development-supplement-plan.v1"
)
RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PRIVATE_PLAN_STATUS = (
    "frozen_before_claim_controller_input_model_prediction_or_outcome"
)
RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PLAN_RECORD_ID = (
    "red-living-dex-development-supplement-plan-v1"
)
RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PLAN_RECORD_KIND = (
    "red-living-dex-development-supplement-plan-v1"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


class RedLivingDexDevelopmentSupplementPlanError(ValueError):
    """A Red supplement does not exactly bind its title-neutral selection."""


@dataclass(frozen=True, slots=True)
class RedLivingDexDevelopmentSupplementBindings:
    """Exact inputs to one action-free supplement freeze."""

    source_commit: str
    source_bundle_sha256: str
    rom_sha256: str
    goal_registry_sha256: str
    route_registry_sha256: str
    context_catalog_sha256: str
    context_plan_sha256: str
    runtime_identity_sha256: str
    supply_audit_evidence_sha256: str
    model_sha256: str
    model_record_sha256: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source_commit, str)
            or _COMMIT.fullmatch(self.source_commit) is None
        ):
            raise RedLivingDexDevelopmentSupplementPlanError(
                "supplement source commit differs"
            )
        for value, subject in (
            (self.source_bundle_sha256, "source bundle"),
            (self.rom_sha256, "ROM"),
            (self.goal_registry_sha256, "goal registry"),
            (self.route_registry_sha256, "route registry"),
            (self.context_catalog_sha256, "context catalog"),
            (self.context_plan_sha256, "context plan"),
            (self.runtime_identity_sha256, "runtime identity"),
            (self.supply_audit_evidence_sha256, "supply audit evidence"),
            (self.model_sha256, "model"),
            (self.model_record_sha256, "model record"),
        ):
            _require_sha256(value, subject)

    def private_dict(self) -> dict[str, str]:
        return {
            "context_catalog_sha256": self.context_catalog_sha256,
            "context_plan_sha256": self.context_plan_sha256,
            "goal_registry_sha256": self.goal_registry_sha256,
            "model_record_sha256": self.model_record_sha256,
            "model_sha256": self.model_sha256,
            "rom_sha256": self.rom_sha256,
            "route_registry_sha256": self.route_registry_sha256,
            "runtime_identity_sha256": self.runtime_identity_sha256,
            "source_bundle_sha256": self.source_bundle_sha256,
            "source_commit": self.source_commit,
            "supply_audit_evidence_sha256": (
                self.supply_audit_evidence_sha256
            ),
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexDevelopmentSupplementFrozenScenario:
    """One selected shared capability joined to one executable Red recipe."""

    ordinal: int
    assignment: LivingDexDevelopmentSupplementCapability
    capability: RedLivingDexCausalRootCapability
    context_identity_sha256: str

    def __post_init__(self) -> None:
        if type(self.ordinal) is not int or self.ordinal < 0:  # noqa: E721
            raise RedLivingDexDevelopmentSupplementPlanError(
                "supplement assignment ordinal differs"
            )
        if not isinstance(
            self.assignment,
            LivingDexDevelopmentSupplementCapability,
        ):
            raise TypeError("supplement frozen scenario needs its assignment")
        if not isinstance(self.capability, RedLivingDexCausalRootCapability):
            raise TypeError("supplement frozen scenario needs its Red capability")
        self.assignment.__post_init__()
        self.capability.__post_init__()
        _require_sha256(self.context_identity_sha256, "context identity")
        projected = build_red_living_dex_development_supplement_capabilities(
            (self.capability,)
        )
        if len(projected) != 1 or projected[0] != self.assignment:
            raise RedLivingDexDevelopmentSupplementPlanError(
                "supplement assignment does not join its Red capability"
            )

    def private_dict(self) -> dict[str, object]:
        root = self.capability.root.root
        recipe = self.capability.recipe
        return {
            **self.assignment.private_dict(),
            "context_identity_sha256": self.context_identity_sha256,
            "ordinal": self.ordinal,
            "partition": "development",
            "recipe": recipe.private_dict(),
            "recipe_sha256": recipe.recipe_sha256,
            "root_consumption_sha256": root.root_consumption_sha256,
            "root_envelope_sha256": root.envelope_sha256,
            "root_state_sha256": root.state_sha256,
            "template_ordinal": self.capability.template_ordinal,
            "template_sha256": self.capability.slot.slot_sha256,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexDevelopmentSupplementPrivatePlan:
    """One immutable three-root Red development supplement."""

    bindings: RedLivingDexDevelopmentSupplementBindings
    supplement: LivingDexDevelopmentSupplementPlan
    assignments: tuple[RedLivingDexDevelopmentSupplementFrozenScenario, ...]

    def __post_init__(self) -> None:
        if not isinstance(
            self.bindings,
            RedLivingDexDevelopmentSupplementBindings,
        ):
            raise TypeError("supplement private plan needs its bindings")
        if not isinstance(self.supplement, LivingDexDevelopmentSupplementPlan):
            raise TypeError("supplement private plan needs its shared plan")
        self.bindings.__post_init__()
        self.supplement.__post_init__()
        if (
            not isinstance(self.assignments, tuple)
            or len(self.assignments) != len(self.supplement.assignments)
            or any(
                not isinstance(
                    item,
                    RedLivingDexDevelopmentSupplementFrozenScenario,
                )
                for item in self.assignments
            )
        ):
            raise RedLivingDexDevelopmentSupplementPlanError(
                "supplement private assignments differ"
            )
        for ordinal, (expected, frozen) in enumerate(
            zip(self.supplement.assignments, self.assignments, strict=True)
        ):
            frozen.__post_init__()
            if frozen.ordinal != ordinal or frozen.assignment != expected:
                raise RedLivingDexDevelopmentSupplementPlanError(
                    "supplement private assignment order differs"
                )

    @property
    def private_plan_sha256(self) -> str:
        return canonical_sha256(self.payload_dict())

    def payload_dict(self) -> dict[str, object]:
        return {
            "assignments": [item.private_dict() for item in self.assignments],
            "behavior_commitments": 0,
            **self.bindings.private_dict(),
            "collection_authorized": False,
            "controller_actions": 0,
            "development_outcomes_opened": 0,
            "emulator_frames": 0,
            "model_fits": 0,
            "model_predictions": 0,
            "outcomes_observed": 0,
            "provider_executions": 0,
            "root_claims": 0,
            "schema": RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PRIVATE_PLAN_SCHEMA,
            "status": RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PRIVATE_PLAN_STATUS,
            "supplement": self.supplement.private_dict(),
            "supplement_plan_sha256": self.supplement.plan_sha256,
            "supplement_policy_sha256": self.supplement.policy.policy_sha256,
            "teacher_queries": 0,
            "training_targets": 0,
            "unselected_action_targets": 0,
        }

    def private_dict(self) -> dict[str, object]:
        return {
            **self.payload_dict(),
            "private_plan_sha256": self.private_plan_sha256,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            **self.supplement.public_dict(),
            "collection_authorized": False,
            "model_sha256": self.bindings.model_sha256,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "schema": (
                "pokemon.red.living-dex-development-supplement-freeze-result.v1"
            ),
            "status": "authenticated_action_free_development_supplement_frozen",
            "training_targets": 0,
        }


def _require_sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedLivingDexDevelopmentSupplementPlanError(
            f"supplement {subject} differs"
        )
    return value


__all__ = [
    "RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PLAN_RECORD_ID",
    "RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PLAN_RECORD_KIND",
    "RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PRIVATE_PLAN_SCHEMA",
    "RED_LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PRIVATE_PLAN_STATUS",
    "RedLivingDexDevelopmentSupplementBindings",
    "RedLivingDexDevelopmentSupplementFrozenScenario",
    "RedLivingDexDevelopmentSupplementPlanError",
    "RedLivingDexDevelopmentSupplementPrivatePlan",
]
