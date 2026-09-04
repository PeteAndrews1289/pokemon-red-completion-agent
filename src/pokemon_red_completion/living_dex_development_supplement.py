"""Title-neutral planner for the smallest missing development supplement.

A fitted policy should not trigger a full replacement curriculum when part of
its prospectively held development supply is still valid.  This module accepts
identity-bearing but outcome-free capabilities from any title adapter and
selects the smallest fixed supplement that closes the measured root and option
coverage gaps while surviving one setup censor.

The planner has no game runtime, scorer, teacher, outcome, claim writer, or
controller.  Title adapters remain responsible for authenticating roots and
binding selected scenarios to deterministic executors.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import combinations, product

from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.provenance import canonical_sha256

LIVING_DEX_DEVELOPMENT_SUPPLEMENT_POLICY_SCHEMA = (
    "pokemon.core.living-dex-development-supplement-policy.v1"
)
LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PLAN_SCHEMA = (
    "pokemon.core.private-living-dex-development-supplement-plan.v1"
)
LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PUBLIC_SCHEMA = (
    "pokemon.core.living-dex-development-supplement-plan.v1"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_SCOPE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_KIND_ORDER = {kind: index for index, kind in enumerate(LivingDexOptionKind)}


class LivingDexDevelopmentSupplementError(ValueError):
    """Outcome-free capabilities cannot satisfy the fixed supplement contract."""


@dataclass(frozen=True, slots=True)
class LivingDexDevelopmentSupplementCapability:
    """One independent root can expose one semantic development menu."""

    lineage_sha256: str
    physical_root_sha256: str
    scenario_sha256: str
    family_scope_id: str
    location_scope_id: str
    available_option_kinds: tuple[LivingDexOptionKind, ...]

    def __post_init__(self) -> None:
        for value in (
            self.lineage_sha256,
            self.physical_root_sha256,
            self.scenario_sha256,
        ):
            if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                raise LivingDexDevelopmentSupplementError(
                    "development supplement identity differs"
                )
        for value in (self.family_scope_id, self.location_scope_id):
            if not isinstance(value, str) or _SAFE_SCOPE.fullmatch(value) is None:
                raise LivingDexDevelopmentSupplementError(
                    "development supplement scope differs"
                )
        if (
            not isinstance(self.available_option_kinds, tuple)
            or len(self.available_option_kinds) < 2
            or len(set(self.available_option_kinds))
            != len(self.available_option_kinds)
            or any(
                not isinstance(item, LivingDexOptionKind)
                for item in self.available_option_kinds
            )
            or tuple(
                sorted(
                    self.available_option_kinds,
                    key=_KIND_ORDER.__getitem__,
                )
            )
            != self.available_option_kinds
        ):
            raise LivingDexDevelopmentSupplementError(
                "development supplement option menu differs"
            )

    def private_dict(self) -> dict[str, object]:
        return {
            "available_option_kinds": [
                item.value for item in self.available_option_kinds
            ],
            "family_scope_id": self.family_scope_id,
            "lineage_sha256": self.lineage_sha256,
            "location_scope_id": self.location_scope_id,
            "physical_root_sha256": self.physical_root_sha256,
            "scenario_sha256": self.scenario_sha256,
        }


@dataclass(frozen=True, slots=True)
class LivingDexDevelopmentSupplementPolicy:
    """Exact shortfall and robustness requirements frozen before selection."""

    new_roots: int
    minimum_surviving_roots: int
    minimum_new_families: int
    minimum_new_locations: int
    held_root_count: int
    required_total_roots: int
    held_option_kinds: tuple[LivingDexOptionKind, ...]
    required_option_kinds: tuple[LivingDexOptionKind, ...]
    maximum_setup_censors: int = field(init=False)

    def __post_init__(self) -> None:
        values = (
            self.new_roots,
            self.minimum_surviving_roots,
            self.minimum_new_families,
            self.minimum_new_locations,
            self.held_root_count,
            self.required_total_roots,
        )
        if any(type(value) is not int or value <= 0 for value in values):  # noqa: E721
            raise LivingDexDevelopmentSupplementError(
                "development supplement policy counts differ"
            )
        object.__setattr__(
            self,
            "maximum_setup_censors",
            self.new_roots - self.minimum_surviving_roots,
        )
        if (
            self.maximum_setup_censors < 0
            or self.held_root_count + self.minimum_surviving_roots
            < self.required_total_roots
            or self.minimum_new_families > self.new_roots
            or self.minimum_new_locations > self.new_roots
        ):
            raise LivingDexDevelopmentSupplementError(
                "development supplement policy is arithmetically impossible"
            )
        for kinds, subject in (
            (self.held_option_kinds, "held"),
            (self.required_option_kinds, "required"),
        ):
            if (
                not isinstance(kinds, tuple)
                or not kinds
                or len(set(kinds)) != len(kinds)
                or any(not isinstance(item, LivingDexOptionKind) for item in kinds)
                or tuple(sorted(kinds, key=_KIND_ORDER.__getitem__)) != kinds
            ):
                raise LivingDexDevelopmentSupplementError(
                    f"development supplement {subject} option kinds differ"
                )
        if not set(self.held_option_kinds).issubset(self.required_option_kinds):
            raise LivingDexDevelopmentSupplementError(
                "held option kinds exceed the required vocabulary"
            )

    @property
    def policy_sha256(self) -> str:
        return canonical_sha256(self.public_dict())

    @property
    def missing_option_kinds(self) -> tuple[LivingDexOptionKind, ...]:
        held = set(self.held_option_kinds)
        return tuple(item for item in self.required_option_kinds if item not in held)

    def public_dict(self) -> dict[str, object]:
        return {
            "held_option_kinds": [item.value for item in self.held_option_kinds],
            "held_root_count": self.held_root_count,
            "maximum_setup_censors": self.maximum_setup_censors,
            "minimum_new_families": self.minimum_new_families,
            "minimum_new_locations": self.minimum_new_locations,
            "minimum_surviving_roots": self.minimum_surviving_roots,
            "missing_option_kinds": [
                item.value for item in self.missing_option_kinds
            ],
            "new_roots": self.new_roots,
            "required_option_kinds": [
                item.value for item in self.required_option_kinds
            ],
            "required_total_roots": self.required_total_roots,
            "schema": LIVING_DEX_DEVELOPMENT_SUPPLEMENT_POLICY_SCHEMA,
        }


@dataclass(frozen=True, slots=True)
class LivingDexDevelopmentSupplementPlan:
    """One deterministic private selection plus an aggregate-only projection."""

    policy: LivingDexDevelopmentSupplementPolicy
    assignments: tuple[LivingDexDevelopmentSupplementCapability, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.policy, LivingDexDevelopmentSupplementPolicy):
            raise TypeError("development supplement plan needs its policy")
        self.policy.__post_init__()
        if (
            not isinstance(self.assignments, tuple)
            or len(self.assignments) != self.policy.new_roots
            or any(
                not isinstance(item, LivingDexDevelopmentSupplementCapability)
                for item in self.assignments
            )
        ):
            raise LivingDexDevelopmentSupplementError(
                "development supplement assignment count differs"
            )
        for item in self.assignments:
            item.__post_init__()
        if tuple(sorted(item.scenario_sha256 for item in self.assignments)) != tuple(
            item.scenario_sha256 for item in self.assignments
        ):
            raise LivingDexDevelopmentSupplementError(
                "development supplement assignment order differs"
            )
        if (
            len({item.lineage_sha256 for item in self.assignments})
            != len(self.assignments)
            or len({item.physical_root_sha256 for item in self.assignments})
            != len(self.assignments)
            or len({item.family_scope_id for item in self.assignments})
            < self.policy.minimum_new_families
            or len({item.location_scope_id for item in self.assignments})
            < self.policy.minimum_new_locations
            or not self._coverage_survives_every_allowed_censor()
        ):
            raise LivingDexDevelopmentSupplementError(
                "development supplement coverage differs"
            )

    @property
    def plan_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    def private_dict(self) -> dict[str, object]:
        return {
            "assignments": [item.private_dict() for item in self.assignments],
            "outcomes_opened": 0,
            "policy": self.policy.public_dict(),
            "policy_sha256": self.policy.policy_sha256,
            "schema": LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PLAN_SCHEMA,
            "teacher_queries": 0,
        }

    def public_dict(self) -> dict[str, object]:
        option_kinds = sorted(
            {
                item.value
                for assignment in self.assignments
                for item in assignment.available_option_kinds
            }
        )
        return {
            "controller_actions": 0,
            "coverage_survives_any_allowed_censor": True,
            "emulator_frames": 0,
            "model_fits": 0,
            "model_predictions": 0,
            "new_families": len(
                {item.family_scope_id for item in self.assignments}
            ),
            "new_locations": len(
                {item.location_scope_id for item in self.assignments}
            ),
            "new_option_kinds": option_kinds,
            "new_roots": len(self.assignments),
            "outcomes_opened": 0,
            "plan_sha256": self.plan_sha256,
            "policy": self.policy.public_dict(),
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "root_claims": 0,
            "schema": LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PUBLIC_SCHEMA,
            "teacher_queries": 0,
        }

    def _coverage_survives_every_allowed_censor(self) -> bool:
        surviving_count = self.policy.minimum_surviving_roots
        required = set(self.policy.required_option_kinds)
        held = set(self.policy.held_option_kinds)
        return all(
            held
            | {
                kind
                for assignment in survivors
                for kind in assignment.available_option_kinds
            }
            >= required
            for survivors in combinations(self.assignments, surviving_count)
        )


def select_living_dex_development_supplement(
    capabilities: Sequence[LivingDexDevelopmentSupplementCapability],
    *,
    policy: LivingDexDevelopmentSupplementPolicy,
    excluded_lineages: frozenset[str] = frozenset(),
    excluded_physical_roots: frozenset[str] = frozenset(),
) -> LivingDexDevelopmentSupplementPlan:
    """Select the lexicographically first censor-safe independent supplement."""

    if isinstance(capabilities, (str, bytes)) or not isinstance(
        capabilities,
        Sequence,
    ):
        raise TypeError("development supplement capabilities need a sequence")
    if not isinstance(policy, LivingDexDevelopmentSupplementPolicy):
        raise TypeError("development supplement selection needs a policy")
    policy.__post_init__()
    for excluded in (excluded_lineages, excluded_physical_roots):
        if not isinstance(excluded, frozenset) or any(
            not isinstance(item, str) or _SHA256.fullmatch(item) is None
            for item in excluded
        ):
            raise LivingDexDevelopmentSupplementError(
                "development supplement exclusion identities differ"
            )
    eligible: list[LivingDexDevelopmentSupplementCapability] = []
    keys: set[tuple[str, str]] = set()
    for capability in capabilities:
        if not isinstance(capability, LivingDexDevelopmentSupplementCapability):
            raise TypeError("development supplement capability differs")
        capability.__post_init__()
        key = (capability.physical_root_sha256, capability.scenario_sha256)
        if key in keys:
            raise LivingDexDevelopmentSupplementError(
                "development supplement repeats a capability"
            )
        keys.add(key)
        if (
            capability.lineage_sha256 not in excluded_lineages
            and capability.physical_root_sha256 not in excluded_physical_roots
        ):
            eligible.append(capability)

    by_root: dict[str, list[LivingDexDevelopmentSupplementCapability]] = {}
    for item in eligible:
        by_root.setdefault(item.physical_root_sha256, []).append(item)
    root_groups = tuple(
        tuple(sorted(by_root[root], key=lambda item: item.scenario_sha256))
        for root in sorted(by_root)
    )
    for groups in combinations(root_groups, policy.new_roots):
        for candidate_tuple in product(*groups):
            ordered = tuple(
                sorted(candidate_tuple, key=lambda item: item.scenario_sha256)
            )
            try:
                return LivingDexDevelopmentSupplementPlan(policy, ordered)
            except LivingDexDevelopmentSupplementError:
                continue
    raise LivingDexDevelopmentSupplementError(
        "development supplement capacity is insufficient"
    )


__all__ = [
    "LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PLAN_SCHEMA",
    "LIVING_DEX_DEVELOPMENT_SUPPLEMENT_POLICY_SCHEMA",
    "LIVING_DEX_DEVELOPMENT_SUPPLEMENT_PUBLIC_SCHEMA",
    "LivingDexDevelopmentSupplementCapability",
    "LivingDexDevelopmentSupplementError",
    "LivingDexDevelopmentSupplementPlan",
    "LivingDexDevelopmentSupplementPolicy",
    "select_living_dex_development_supplement",
]
