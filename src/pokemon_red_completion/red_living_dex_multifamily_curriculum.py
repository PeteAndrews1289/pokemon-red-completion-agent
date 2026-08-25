"""Path-free Red inventory and counterbalanced multi-family curriculum planning.

The title-neutral dependency ranker must not learn one species lineage by
repetition.  This module inventories independently qualified Red dependency
menus across authenticated reset roots, then freezes one family for fitting and
a different family for development comparison.  Species, source, family, root,
and context identities remain private; public projections contain only counts
and the already-approved identity-free policy rows.

Everything here is action-free.  It does not open captures, load a ROM, score a
model, claim a root, or execute a capability.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from pokemon_red_completion.collection import CollectionObservation
from pokemon_red_completion.living_dex_dependency_curriculum import (
    ROOTLESS_DEPENDENCY_FEATURE_SCHEMA,
)
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.red_living_dex_dependency_adapter import (
    RedDependencyExecutionFacts,
    RedLivingDexDependencyOpportunity,
    adapt_red_living_dex_dependencies,
)

RED_MULTIFAMILY_INVENTORY_SCHEMA = "pokemon.red.living-dex-multifamily-inventory.v1"
RED_MULTIFAMILY_PLAN_SCHEMA = "pokemon.red.living-dex-multifamily-plan.v1"

RedMultifamilyPartition = Literal["train", "development"]

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PARTITIONS = frozenset({"train", "development"})


class RedLivingDexMultifamilyError(ValueError):
    """The action-free inventory or frozen family split is not trustworthy."""


@dataclass(frozen=True, slots=True)
class RedMultifamilyContext:
    """One authenticated private reset and its action-free collection facts."""

    context_identity_sha256: str
    root_consumption_sha256: str
    partition: RedMultifamilyPartition
    observation: CollectionObservation
    execution_facts: RedDependencyExecutionFacts
    root_available: bool

    def __post_init__(self) -> None:
        _require_sha256(self.context_identity_sha256, "context")
        _require_sha256(self.root_consumption_sha256, "root consumption")
        if self.partition not in _PARTITIONS:
            raise RedLivingDexMultifamilyError("multifamily context partition differs")
        if not isinstance(self.observation, CollectionObservation):
            raise TypeError("multifamily context needs a collection observation")
        if not isinstance(self.execution_facts, RedDependencyExecutionFacts):
            raise TypeError("multifamily context needs execution facts")
        if type(self.root_available) is not bool:  # noqa: E721
            raise TypeError("multifamily root availability must be boolean")


@dataclass(frozen=True, slots=True)
class RedMultifamilyOpportunity:
    """One complete executable menu joined privately to one untouched root."""

    context: RedMultifamilyContext
    opportunity: RedLivingDexDependencyOpportunity

    def __post_init__(self) -> None:
        if not isinstance(self.context, RedMultifamilyContext):
            raise TypeError("multifamily opportunity needs a context")
        if not isinstance(self.opportunity, RedLivingDexDependencyOpportunity):
            raise TypeError("multifamily opportunity needs an adapter opportunity")
        if not self.opportunity.execution_qualified:
            raise RedLivingDexMultifamilyError(
                "multifamily opportunity is not independently executable"
            )
        rows = self.opportunity.policy_rows()
        if len(rows) != 2 or any(
            row.get("schema") != ROOTLESS_DEPENDENCY_FEATURE_SCHEMA for row in rows
        ):
            raise RedLivingDexMultifamilyError("multifamily menu is incomplete")

    @property
    def family_identity_sha256(self) -> str:
        """Private family join key; never include it in a public projection."""

        return self.opportunity.binding.binding_sha256

    def policy_rows(self) -> tuple[dict[str, int | str], ...]:
        return self.opportunity.policy_rows()


@dataclass(frozen=True, slots=True)
class RedMultifamilyInventory:
    """Complete adapter audit plus the subset with two executable candidates."""

    contexts: tuple[RedMultifamilyContext, ...]
    rankable_opportunity_count: int
    opportunities: tuple[RedMultifamilyOpportunity, ...]

    def __post_init__(self) -> None:
        if not self.contexts or any(
            not isinstance(item, RedMultifamilyContext) for item in self.contexts
        ):
            raise RedLivingDexMultifamilyError("multifamily inventory contexts differ")
        if type(self.rankable_opportunity_count) is not int or (  # noqa: E721
            self.rankable_opportunity_count < len(self.opportunities)
        ):
            raise RedLivingDexMultifamilyError("multifamily rankable count differs")
        if any(
            not isinstance(item, RedMultifamilyOpportunity) for item in self.opportunities
        ):
            raise RedLivingDexMultifamilyError("multifamily opportunities differ")
        context_ids = tuple(item.context_identity_sha256 for item in self.contexts)
        roots = tuple(item.root_consumption_sha256 for item in self.contexts)
        if len(context_ids) != len(set(context_ids)) or len(roots) != len(set(roots)):
            raise RedLivingDexMultifamilyError(
                "multifamily inventory repeats a context or physical root"
            )
        context_objects = {id(item) for item in self.contexts}
        if any(id(item.context) not in context_objects for item in self.opportunities):
            raise RedLivingDexMultifamilyError(
                "multifamily opportunity is detached from its inventory"
            )

    @property
    def available_opportunities(self) -> tuple[RedMultifamilyOpportunity, ...]:
        return tuple(item for item in self.opportunities if item.context.root_available)

    def public_dict(self) -> dict[str, object]:
        partitions = Counter(item.partition for item in self.contexts)
        available = self.available_opportunities
        return {
            "schema": RED_MULTIFAMILY_INVENTORY_SCHEMA,
            "contexts": len(self.contexts),
            "partition_context_counts": dict(sorted(partitions.items())),
            "available_roots": sum(item.root_available for item in self.contexts),
            "retired_roots": sum(not item.root_available for item in self.contexts),
            "rankable_opportunities": self.rankable_opportunity_count,
            "execution_qualified_opportunities": len(self.opportunities),
            "available_execution_qualified_opportunities": len(available),
            "qualified_families": len(
                {item.family_identity_sha256 for item in self.opportunities}
            ),
            "policy_feature_schema": ROOTLESS_DEPENDENCY_FEATURE_SCHEMA,
            "complete_candidate_menus": all(len(item.policy_rows()) == 2 for item in available),
            "model_predictions": 0,
            "controller_actions": 0,
            "family_identity_fields": 0,
            "root_identity_fields": 0,
            "context_identity_fields": 0,
            "species_identity_fields": 0,
            "source_identity_fields": 0,
        }


@dataclass(frozen=True, slots=True)
class RedMultifamilyTrial:
    """One preregistered candidate intervention on one never-reused root."""

    opportunity: RedMultifamilyOpportunity
    candidate_index: int

    def __post_init__(self) -> None:
        if not isinstance(self.opportunity, RedMultifamilyOpportunity):
            raise TypeError("multifamily trial needs an opportunity")
        if type(self.candidate_index) is not int or self.candidate_index not in {0, 1}:  # noqa: E721
            raise RedLivingDexMultifamilyError("multifamily trial candidate differs")
        if not self.opportunity.context.root_available:
            raise RedLivingDexMultifamilyError("multifamily trial root is already retired")
        if len(self.opportunity.policy_rows()) != 2:
            raise RedLivingDexMultifamilyError("multifamily trial menu is incomplete")

    @property
    def partition(self) -> RedMultifamilyPartition:
        return self.opportunity.context.partition

    def public_dict(self) -> dict[str, object]:
        return {
            "partition": self.partition,
            "candidate_count": 2,
            "intervention_candidate_index": self.candidate_index,
            "candidate_rows": [dict(row) for row in self.opportunity.policy_rows()],
            "outcome_observed": False,
            "model_predictions": 0,
            "teacher_queries": 0,
            "private_identity_fields": 0,
        }


@dataclass(frozen=True, slots=True)
class RedMultifamilyCurriculumPlan:
    """A balanced train/development split with both family and root isolation."""

    train_trials: tuple[RedMultifamilyTrial, ...]
    development_trials: tuple[RedMultifamilyTrial, ...]

    def __post_init__(self) -> None:
        if not self.train_trials or not self.development_trials:
            raise RedLivingDexMultifamilyError("multifamily plan needs both partitions")
        trials = (*self.train_trials, *self.development_trials)
        if any(not isinstance(item, RedMultifamilyTrial) for item in trials):
            raise RedLivingDexMultifamilyError("multifamily plan trials differ")
        if any(item.partition != "train" for item in self.train_trials) or any(
            item.partition != "development" for item in self.development_trials
        ):
            raise RedLivingDexMultifamilyError("multifamily plan partition differs")
        roots = tuple(
            item.opportunity.context.root_consumption_sha256 for item in trials
        )
        contexts = tuple(
            item.opportunity.context.context_identity_sha256 for item in trials
        )
        if len(roots) != len(set(roots)) or len(contexts) != len(set(contexts)):
            raise RedLivingDexMultifamilyError(
                "multifamily plan reuses a physical root or context"
            )
        train_families = {
            item.opportunity.family_identity_sha256 for item in self.train_trials
        }
        development_families = {
            item.opportunity.family_identity_sha256 for item in self.development_trials
        }
        if train_families & development_families:
            raise RedLivingDexMultifamilyError(
                "training and development families overlap"
            )
        for partition_trials in (self.train_trials, self.development_trials):
            counts = Counter(item.candidate_index for item in partition_trials)
            if set(counts) != {0, 1} or counts[0] != counts[1]:
                raise RedLivingDexMultifamilyError(
                    "multifamily candidate interventions are not counterbalanced"
                )

    def public_dict(self) -> dict[str, object]:
        trials = (*self.train_trials, *self.development_trials)
        return {
            "schema": RED_MULTIFAMILY_PLAN_SCHEMA,
            "status": "frozen_before_outcomes",
            "train_trials": len(self.train_trials),
            "development_trials": len(self.development_trials),
            "candidate_count_per_menu": 2,
            "train_candidate_counts": _candidate_count_document(self.train_trials),
            "development_candidate_counts": _candidate_count_document(
                self.development_trials
            ),
            "distinct_physical_roots": len(trials),
            "train_families": len(
                {item.opportunity.family_identity_sha256 for item in self.train_trials}
            ),
            "development_families": len(
                {
                    item.opportunity.family_identity_sha256
                    for item in self.development_trials
                }
            ),
            "family_overlap": 0,
            "root_overlap": 0,
            "complete_menus": all(len(item.opportunity.policy_rows()) == 2 for item in trials),
            "fit_partition": "train_only",
            "comparison_partition": "development_only",
            "outcomes_observed": 0,
            "model_predictions": 0,
            "teacher_queries": 0,
            "family_identity_fields": 0,
            "root_identity_fields": 0,
            "context_identity_fields": 0,
            "species_identity_fields": 0,
            "source_identity_fields": 0,
        }


def _candidate_count_document(
    trials: Sequence[RedMultifamilyTrial],
) -> dict[str, int]:
    """Return strict-JSON counters whose in-memory keys match their encoded keys.

    ``json.dumps`` silently converts integer mapping keys to strings.  Private
    artifact validation intentionally does not, so the curriculum projection
    must make that canonical representation explicit before hashing or sealed
    publication.
    """

    counts = Counter(item.candidate_index for item in trials)
    return {str(index): counts[index] for index in sorted(counts)}


def inventory_red_multifamily_contexts(
    contexts: Sequence[RedMultifamilyContext],
) -> RedMultifamilyInventory:
    """Run the complete Red adapter over every supplied context without acting."""

    if not isinstance(contexts, Sequence) or not contexts or any(
        not isinstance(item, RedMultifamilyContext) for item in contexts
    ):
        raise RedLivingDexMultifamilyError("multifamily contexts differ")
    typed = tuple(contexts)
    context_ids = tuple(item.context_identity_sha256 for item in typed)
    roots = tuple(item.root_consumption_sha256 for item in typed)
    if len(context_ids) != len(set(context_ids)) or len(roots) != len(set(roots)):
        raise RedLivingDexMultifamilyError(
            "multifamily inventory repeats a context or physical root"
        )

    qualified: list[RedMultifamilyOpportunity] = []
    rankable = 0
    for context in typed:
        adapted = adapt_red_living_dex_dependencies(
            context.observation,
            execution_facts=context.execution_facts,
        )
        rankable += len(adapted.rankable)
        qualified.extend(
            RedMultifamilyOpportunity(context, opportunity)
            for opportunity in adapted.rankable
            if opportunity.execution_qualified
        )
    return RedMultifamilyInventory(typed, rankable, tuple(qualified))


def freeze_two_family_curriculum(
    inventory: RedMultifamilyInventory,
    *,
    train_family_identity_sha256: str,
    development_family_identity_sha256: str,
    trials_per_candidate: int = 4,
) -> RedMultifamilyCurriculumPlan:
    """Freeze balanced interventions on disjoint families and distinct roots."""

    if not isinstance(inventory, RedMultifamilyInventory):
        raise TypeError("inventory must be a RedMultifamilyInventory")
    _require_sha256(train_family_identity_sha256, "training family")
    _require_sha256(development_family_identity_sha256, "development family")
    if train_family_identity_sha256 == development_family_identity_sha256:
        raise RedLivingDexMultifamilyError("training and development families overlap")
    if type(trials_per_candidate) is not int or trials_per_candidate < 1:  # noqa: E721
        raise RedLivingDexMultifamilyError("trials per candidate must be positive")

    def select(
        partition: RedMultifamilyPartition,
        family: str,
    ) -> tuple[RedMultifamilyTrial, ...]:
        candidates = sorted(
            (
                item
                for item in inventory.available_opportunities
                if item.context.partition == partition
                and item.family_identity_sha256 == family
            ),
            key=lambda item: item.context.context_identity_sha256,
        )
        needed = 2 * trials_per_candidate
        if len(candidates) < needed:
            raise RedLivingDexMultifamilyError(
                f"{partition} family has {len(candidates)} roots; {needed} are required"
            )
        # Interleave the two interventions so collection order cannot be a
        # disguised candidate label.  Every trial still starts from its own root.
        return tuple(
            RedMultifamilyTrial(opportunity, index % 2)
            for index, opportunity in enumerate(candidates[:needed])
        )

    return RedMultifamilyCurriculumPlan(
        select("train", train_family_identity_sha256),
        select("development", development_family_identity_sha256),
    )


def map_id_for_wild_source(source_id: str) -> MapId:
    """Resolve a Red wild-source location without a species-specific table."""

    if not isinstance(source_id, str):
        raise TypeError("wild source must be a string")
    parts = source_id.split(":")
    if len(parts) != 3 or parts[0] != "wild" or parts[2] != "grass" or not parts[1]:
        raise RedLivingDexMultifamilyError("wild source is not a grass-map source")
    wanted = _normalized_map_name(parts[1])
    matches = tuple(map_id for map_id in MapId if _normalized_map_name(map_id.name) == wanted)
    if len(matches) != 1:
        raise RedLivingDexMultifamilyError("wild source does not resolve to one Red map")
    return matches[0]


def raw_exit_coordinates(
    router_coordinates: Sequence[tuple[int, int]],
) -> frozenset[tuple[int, int]]:
    """Convert router ``(y, x)`` warp cells into raw-game ``(x, y)`` guards."""

    if not isinstance(router_coordinates, Sequence) or any(
        not isinstance(coordinate, tuple)
        or len(coordinate) != 2
        or any(type(value) is not int or value < 0 for value in coordinate)  # noqa: E721
        for coordinate in router_coordinates
    ):
        raise RedLivingDexMultifamilyError("router exit coordinates differ")
    return frozenset((x, y) for y, x in router_coordinates)


def _normalized_map_name(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def _require_sha256(value: str, subject: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedLivingDexMultifamilyError(f"{subject} SHA-256 is invalid")


__all__ = [
    "RED_MULTIFAMILY_INVENTORY_SCHEMA",
    "RED_MULTIFAMILY_PLAN_SCHEMA",
    "RedLivingDexMultifamilyError",
    "RedMultifamilyContext",
    "RedMultifamilyCurriculumPlan",
    "RedMultifamilyInventory",
    "RedMultifamilyOpportunity",
    "RedMultifamilyPartition",
    "RedMultifamilyTrial",
    "freeze_two_family_curriculum",
    "inventory_red_multifamily_contexts",
    "map_id_for_wild_source",
    "raw_exit_coordinates",
]
