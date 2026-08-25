"""Pure Red adapter for the title-neutral living-Dex dependency ranker.

The rootless curriculum learned one deliberately small choice: acquire another
precursor when the retained collection has no surplus, otherwise transform the
surplus toward an unresolved evolved form.  This module projects Red's existing
collection observation and source-pinned acquisition graph into that exact
feature schema.

Species, source, item, and transformation identities remain in a private binding.
Only :class:`DependencyCandidateFeatures` cross the policy boundary.  The adapter
does not load a ROM, read private artifacts, score a model, or execute a skill.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum

from pokemon_red_completion.collection import CollectionContract, CollectionObservation
from pokemon_red_completion.living_dex_dependency_curriculum import (
    ROOTLESS_DEPENDENCY_FEATURE_SCHEMA,
    DependencyCandidateFeatures,
    DependencyMultiset,
    DependencyPredecisionFeatures,
    DependencyStructure,
    dependency_predecision_features,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_acquisition import (
    RED_ACQUISITION_CATALOG,
    RedAcquisitionCatalog,
    RedAcquisitionKind,
    RedAcquisitionMethod,
)
from pokemon_red_completion.red_collection import RED_SOLO_COLLECTION_CONTRACT

RED_LIVING_DEX_DEPENDENCY_ADAPTER_SCHEMA = (
    "pokemon.red.living-dex-dependency-observation-adapter.v1"
)
RED_LIVING_DEX_DEPENDENCY_BINDING_SCHEMA = "pokemon.red.private-living-dex-dependency-binding.v1"

_POLICY_KEYS = frozenset(
    {
        "schema",
        "precursor_count",
        "evolved_count",
        "required_precursor_count",
        "required_evolved_count",
        "precursor_surplus",
        "unresolved_evolution_count",
        "dependency_distance",
        "adds_precursor",
        "consumes_precursor",
        "adds_evolved",
    }
)


class RedLivingDexDependencyAdapterError(ValueError):
    """The Red observation cannot support an honest dependency projection."""


class RedDependencyOpportunityStatus(StrEnum):
    """Why one catalog transformation is or is not rankable."""

    RANKABLE = "rankable"
    COMPLETE = "dependency_complete"
    ZERO_RESERVE_UNSUPPORTED = "zero_precursor_reserve_outside_model_support"


class RedDependencyCandidateReadiness(StrEnum):
    """Title-neutral mechanical readiness for one bound candidate."""

    AVAILABLE = "available"
    CAPABILITY_NOT_ATTESTED = "capability_not_attested"
    PRECURSOR_ABSENT = "precursor_absent"
    LEVEL_REQUIREMENT_UNSATISFIED = "level_requirement_unsatisfied"
    ITEM_REQUIREMENT_UNSATISFIED = "item_requirement_unsatisfied"
    TRADE_REQUIREMENT_UNSATISFIED = "trade_requirement_unsatisfied"


@dataclass(frozen=True, slots=True)
class RedDependencyExecutionFacts:
    """Private, action-free facts supplied by a later Red skill adapter.

    ``acquirable_precursor_refs`` means that an independently authenticated skill
    can add one retained specimen of that exact precursor.
    ``trainable_evolution_pairs`` attests that a bounded participation-training
    skill can raise and evolve that exact precursor even when its current level is
    below the catalog threshold.  Item, trade, and training facts affect only
    mechanical readiness; none enter the ranker's feature rows.
    """

    acquirable_precursor_refs: frozenset[str] = frozenset()
    available_item_refs: frozenset[str] = frozenset()
    trainable_evolution_pairs: frozenset[tuple[str, str]] = frozenset()
    trade_available: bool = False

    def __post_init__(self) -> None:
        for name in ("acquirable_precursor_refs", "available_item_refs"):
            values = getattr(self, name)
            if not isinstance(values, frozenset) or any(
                not isinstance(value, str) or not value for value in values
            ):
                raise TypeError(f"{name} must be a frozenset of non-empty strings")
        if not isinstance(self.trainable_evolution_pairs, frozenset) or any(
            not isinstance(pair, tuple)
            or len(pair) != 2
            or any(not isinstance(value, str) or not value for value in pair)
            or pair[0] == pair[1]
            for pair in self.trainable_evolution_pairs
        ):
            raise TypeError(
                "trainable_evolution_pairs must be a frozenset of distinct species pairs"
            )
        if not isinstance(self.trade_available, bool):
            raise TypeError("trade_available must be boolean")


@dataclass(frozen=True, slots=True)
class RedDependencyPrivateBinding:
    """Red-only identity kept behind the model-visible feature boundary."""

    precursor_species_ref: str
    evolved_species_ref: str
    acquisition_kind: RedAcquisitionKind
    source_id: str
    required_item_ref: str | None

    def __post_init__(self) -> None:
        if (
            not self.precursor_species_ref
            or not self.evolved_species_ref
            or self.precursor_species_ref == self.evolved_species_ref
            or not isinstance(self.acquisition_kind, RedAcquisitionKind)
            or self.acquisition_kind
            not in {RedAcquisitionKind.EVOLUTION, RedAcquisitionKind.IN_GAME_TRADE}
            or not self.source_id
            or (
                self.required_item_ref is not None
                and (not isinstance(self.required_item_ref, str) or not self.required_item_ref)
            )
        ):
            raise RedLivingDexDependencyAdapterError("private dependency binding differs")

    @property
    def binding_sha256(self) -> str:
        """Return a private join identity; never include it in policy rows."""

        return canonical_sha256(
            {
                "schema": RED_LIVING_DEX_DEPENDENCY_BINDING_SCHEMA,
                "precursor_species_ref": self.precursor_species_ref,
                "evolved_species_ref": self.evolved_species_ref,
                "acquisition_kind": self.acquisition_kind.value,
                "source_id": self.source_id,
                "required_item_ref": self.required_item_ref,
            }
        )


@dataclass(frozen=True, slots=True)
class RedLivingDexDependencyOpportunity:
    """One Red transformation projected into the ranker's exact input schema."""

    binding: RedDependencyPrivateBinding
    status: RedDependencyOpportunityStatus
    state: DependencyPredecisionFeatures | None
    candidates: tuple[DependencyCandidateFeatures, ...]
    candidate_readiness: tuple[RedDependencyCandidateReadiness, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.binding, RedDependencyPrivateBinding) or not isinstance(
            self.status, RedDependencyOpportunityStatus
        ):
            raise RedLivingDexDependencyAdapterError("dependency opportunity differs")
        if self.status is RedDependencyOpportunityStatus.RANKABLE:
            if (
                not isinstance(self.state, DependencyPredecisionFeatures)
                or len(self.candidates) != 2
                or len(self.candidate_readiness) != 2
                or self.candidates
                != (
                    DependencyCandidateFeatures(self.state, 1, 0, 0),
                    DependencyCandidateFeatures(self.state, 0, 1, 1),
                )
                or any(
                    not isinstance(reason, RedDependencyCandidateReadiness)
                    for reason in self.candidate_readiness
                )
            ):
                raise RedLivingDexDependencyAdapterError("rankable dependency menu differs")
            _require_title_neutral_policy_rows(self.policy_rows())
        elif self.state is not None or self.candidates or self.candidate_readiness:
            raise RedLivingDexDependencyAdapterError(
                "non-rankable dependency cannot expose policy candidates"
            )

    @property
    def shadow_rankable(self) -> bool:
        return self.status is RedDependencyOpportunityStatus.RANKABLE

    @property
    def execution_qualified(self) -> bool:
        """Both candidates have independently supplied mechanical readiness."""

        return self.shadow_rankable and all(
            reason is RedDependencyCandidateReadiness.AVAILABLE
            for reason in self.candidate_readiness
        )

    def policy_rows(self) -> tuple[dict[str, int | str], ...]:
        """Return only the two identity-free ranker rows, acquire then evolve."""

        rows = tuple(candidate.policy_dict() for candidate in self.candidates)
        _require_title_neutral_policy_rows(rows)
        return rows


@dataclass(frozen=True, slots=True)
class RedLivingDexDependencyAdapterResult:
    """Deterministic projection of every Red transformation edge."""

    opportunities: tuple[RedLivingDexDependencyOpportunity, ...]

    def __post_init__(self) -> None:
        if not self.opportunities or any(
            not isinstance(item, RedLivingDexDependencyOpportunity) for item in self.opportunities
        ):
            raise RedLivingDexDependencyAdapterError("adapter result differs")
        binding_ids = tuple(item.binding.binding_sha256 for item in self.opportunities)
        if len(binding_ids) != len(set(binding_ids)):
            raise RedLivingDexDependencyAdapterError("adapter result duplicates a binding")
        for opportunity in self.opportunities:
            _require_title_neutral_policy_rows(opportunity.policy_rows())

    @property
    def rankable(self) -> tuple[RedLivingDexDependencyOpportunity, ...]:
        return tuple(item for item in self.opportunities if item.shadow_rankable)

    def public_dict(self) -> dict[str, object]:
        """Return aggregate qualification facts without Red identities or rows."""

        statuses = Counter(item.status.value for item in self.opportunities)
        return {
            "schema": RED_LIVING_DEX_DEPENDENCY_ADAPTER_SCHEMA,
            "transformation_edges": len(self.opportunities),
            "rankable_edges": len(self.rankable),
            "execution_qualified_edges": sum(
                item.execution_qualified for item in self.opportunities
            ),
            "status_counts": dict(sorted(statuses.items())),
            "policy_feature_schema": ROOTLESS_DEPENDENCY_FEATURE_SCHEMA,
            "model_predictions": 0,
            "controller_actions": 0,
            "private_binding_values_public": False,
            "species_identity_fields": 0,
            "source_identity_fields": 0,
            "item_identity_fields": 0,
            "route_identity_fields": 0,
        }


def adapt_red_living_dex_dependencies(
    observation: CollectionObservation,
    *,
    execution_facts: RedDependencyExecutionFacts | None = None,
    catalog: RedAcquisitionCatalog = RED_ACQUISITION_CATALOG,
    contract: CollectionContract = RED_SOLO_COLLECTION_CONTRACT,
) -> RedLivingDexDependencyAdapterResult:
    """Project one typed Red collection observation without scoring or acting."""

    if not isinstance(observation, CollectionObservation):
        raise TypeError("observation must be a CollectionObservation")
    if execution_facts is None:
        execution_facts = RedDependencyExecutionFacts()
    if not isinstance(execution_facts, RedDependencyExecutionFacts):
        raise TypeError("execution_facts must be RedDependencyExecutionFacts")
    if not isinstance(catalog, RedAcquisitionCatalog):
        raise TypeError("catalog must be a RedAcquisitionCatalog")
    if not isinstance(contract, CollectionContract):
        raise TypeError("contract must be a CollectionContract")
    if catalog is RED_ACQUISITION_CATALOG and contract is not RED_SOLO_COLLECTION_CONTRACT:
        raise RedLivingDexDependencyAdapterError(
            "the canonical Red catalog requires the canonical living collection contract"
        )

    counts = Counter(specimen.species_ref for specimen in observation.specimens)
    transformations = tuple(method for method in catalog.methods if method.transforms_precursor)
    children = _transformation_children(transformations)
    subtree = {
        method.species_ref: _transformation_subtree(method.species_ref, children)
        for method in transformations
    }
    required_transformations = catalog.required_transformation_counts()
    living_targets = frozenset(contract.resolved_living_target_species)

    opportunities = tuple(
        _adapt_transformation(
            method,
            observation=observation,
            counts=counts,
            children=children,
            subtree=subtree,
            required_transformations=required_transformations,
            living_targets=living_targets,
            execution_facts=execution_facts,
        )
        for method in transformations
    )
    return RedLivingDexDependencyAdapterResult(opportunities)


def _adapt_transformation(
    method: RedAcquisitionMethod,
    *,
    observation: CollectionObservation,
    counts: Counter[str],
    children: dict[str, tuple[str, ...]],
    subtree: dict[str, frozenset[str]],
    required_transformations: dict[str, int],
    living_targets: frozenset[str],
    execution_facts: RedDependencyExecutionFacts,
) -> RedLivingDexDependencyOpportunity:
    precursor = method.consumes_species_ref
    if precursor is None or method.species_ref not in required_transformations:
        raise RedLivingDexDependencyAdapterError("transformation demand differs")
    binding = RedDependencyPrivateBinding(
        precursor_species_ref=precursor,
        evolved_species_ref=method.species_ref,
        acquisition_kind=method.kind,
        source_id=method.source_id,
        required_item_ref=method.required_item_ref,
    )
    evolved_count = _subtree_count(counts, subtree[method.species_ref])
    required_evolved_count = required_transformations[method.species_ref]
    if evolved_count >= required_evolved_count:
        return RedLivingDexDependencyOpportunity(
            binding,
            RedDependencyOpportunityStatus.COMPLETE,
            None,
            (),
            (),
        )

    sibling_reserve = sum(
        max(
            0,
            required_transformations[sibling] - _subtree_count(counts, subtree[sibling]),
        )
        for sibling in children.get(precursor, ())
        if sibling != method.species_ref
    )
    required_precursor_count = int(precursor in living_targets) + sibling_reserve
    if required_precursor_count == 0:
        return RedLivingDexDependencyOpportunity(
            binding,
            RedDependencyOpportunityStatus.ZERO_RESERVE_UNSUPPORTED,
            None,
            (),
            (),
        )

    structure = DependencyStructure(required_precursor_count, required_evolved_count)
    before = DependencyMultiset(counts[precursor], evolved_count)
    state = dependency_predecision_features(before, structure)
    candidates = (
        DependencyCandidateFeatures(state, 1, 0, 0),
        DependencyCandidateFeatures(state, 0, 1, 1),
    )
    readiness = (
        (
            RedDependencyCandidateReadiness.AVAILABLE
            if precursor in execution_facts.acquirable_precursor_refs
            else RedDependencyCandidateReadiness.CAPABILITY_NOT_ATTESTED
        ),
        _transformation_readiness(method, observation, execution_facts),
    )
    return RedLivingDexDependencyOpportunity(
        binding,
        RedDependencyOpportunityStatus.RANKABLE,
        state,
        candidates,
        readiness,
    )


def _transformation_readiness(
    method: RedAcquisitionMethod,
    observation: CollectionObservation,
    execution_facts: RedDependencyExecutionFacts,
) -> RedDependencyCandidateReadiness:
    precursor = method.consumes_species_ref
    if precursor is None:
        raise RedLivingDexDependencyAdapterError("transformation precursor differs")
    specimens = tuple(item for item in observation.specimens if item.species_ref == precursor)
    if not specimens:
        return RedDependencyCandidateReadiness.PRECURSOR_ABSENT
    if method.kind is RedAcquisitionKind.IN_GAME_TRADE:
        return (
            RedDependencyCandidateReadiness.AVAILABLE
            if execution_facts.trade_available
            else RedDependencyCandidateReadiness.TRADE_REQUIREMENT_UNSATISFIED
        )
    if method.required_item_ref is not None:
        return (
            RedDependencyCandidateReadiness.AVAILABLE
            if method.required_item_ref in execution_facts.available_item_refs
            else RedDependencyCandidateReadiness.ITEM_REQUIREMENT_UNSATISFIED
        )
    if (
        precursor,
        method.species_ref,
    ) in execution_facts.trainable_evolution_pairs:
        return RedDependencyCandidateReadiness.AVAILABLE
    minimum_level = method.minimum_level
    if minimum_level is None or not any(item.level >= minimum_level for item in specimens):
        return RedDependencyCandidateReadiness.LEVEL_REQUIREMENT_UNSATISFIED
    return RedDependencyCandidateReadiness.AVAILABLE


def _transformation_children(
    transformations: tuple[RedAcquisitionMethod, ...],
) -> dict[str, tuple[str, ...]]:
    values: dict[str, list[str]] = {}
    for method in transformations:
        precursor = method.consumes_species_ref
        if precursor is None:
            raise RedLivingDexDependencyAdapterError("transformation precursor differs")
        values.setdefault(precursor, []).append(method.species_ref)
    return {key: tuple(sorted(items)) for key, items in values.items()}


def _transformation_subtree(
    species_ref: str,
    children: dict[str, tuple[str, ...]],
) -> frozenset[str]:
    pending = [species_ref]
    seen: set[str] = set()
    while pending:
        current = pending.pop()
        if current in seen:
            raise RedLivingDexDependencyAdapterError("transformation graph contains a cycle")
        seen.add(current)
        pending.extend(children.get(current, ()))
    return frozenset(seen)


def _subtree_count(counts: Counter[str], species_refs: frozenset[str]) -> int:
    return sum(counts[species_ref] for species_ref in species_refs)


def _require_title_neutral_policy_rows(
    rows: tuple[dict[str, int | str], ...],
) -> None:
    for row in rows:
        if (
            frozenset(row) != _POLICY_KEYS
            or row.get("schema") != ROOTLESS_DEPENDENCY_FEATURE_SCHEMA
        ):
            raise RedLivingDexDependencyAdapterError("policy row contains a title-specific field")
        if any(
            isinstance(value, str) and value != ROOTLESS_DEPENDENCY_FEATURE_SCHEMA
            for value in row.values()
        ):
            raise RedLivingDexDependencyAdapterError("policy row contains a title identity")


__all__ = [
    "RED_LIVING_DEX_DEPENDENCY_ADAPTER_SCHEMA",
    "RedDependencyCandidateReadiness",
    "RedDependencyExecutionFacts",
    "RedDependencyOpportunityStatus",
    "RedDependencyPrivateBinding",
    "RedLivingDexDependencyAdapterError",
    "RedLivingDexDependencyAdapterResult",
    "RedLivingDexDependencyOpportunity",
    "adapt_red_living_dex_dependencies",
]
