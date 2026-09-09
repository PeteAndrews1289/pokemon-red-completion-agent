"""Pure, side-effect-free candidate catalog for living-collection planning.

This module connects living-specimen accounting and marginal acquisition demand
to a typed candidate catalog that explicitly separates three operational gates:
  (a) A species exists and has a declared acquisition source option.
  (b) The source is presently reachable and all required resources/precursors are satisfied.
  (c) An implemented and qualified runtime executor exists for that option.

Unknown is not true: missing reachability or resource knowledge is treated as unverified,
never silently presumed available. The catalog never selects a preferred actor goal,
never alters policy weights, never performs state mutations or rollouts, and never claims
an option is ready to execute without verified reachability, satisfied resources, and a
qualified executor.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from pokemon_red_completion.collection_acquisition_demand import useful_capture_counts


class AcquisitionMethodKind(StrEnum):
    """How a candidate species can enter the collection."""

    WILD_ENCOUNTER = "wild_encounter"
    SAFARI_ENCOUNTER = "safari_encounter"
    FISHING = "fishing"
    STATIC_ENCOUNTER = "static_encounter"
    GIFT = "gift"
    FOSSIL_REVIVAL = "fossil_revival"
    GAME_CORNER = "game_corner"
    LEVEL_EVOLUTION = "level_evolution"
    ITEM_EVOLUTION = "item_evolution"
    TRADE_EVOLUTION = "trade_evolution"
    IN_GAME_TRADE = "in_game_trade"


class ExecutorStatus(StrEnum):
    """Qualification status of the runtime executor for an option.

    Distinguishes declared/hypothetical acquisition methods from currently
    implemented and qualified executor capabilities.
    """

    QUALIFIED = "qualified"
    UNQUALIFIED = "unqualified"
    UNIMPLEMENTED = "unimplemented"


class OptionReadiness(StrEnum):
    """Overall readiness state of an acquisition option."""

    READY = "ready"
    BLOCKED = "blocked"


class BlockerReason(StrEnum):
    """Typed blocker reasons explaining why an option cannot execute right now."""

    NO_REMAINING_DEMAND = "no_remaining_demand"
    SOURCE_UNREACHABLE = "source_unreachable"
    SOURCE_REACHABILITY_UNKNOWN = "source_reachability_unknown"
    RESOURCE_INSUFFICIENT = "resource_insufficient"
    RESOURCE_UNKNOWN = "resource_unknown"
    PRECURSOR_UNAVAILABLE = "precursor_unavailable"
    PRECURSOR_LAST_RETAINED = "precursor_last_retained"
    ONE_TIME_CONSUMED = "one_time_consumed"
    VERSION_EXCLUSIVE_BLOCKED = "version_exclusive_blocked"
    LINK_TRADE_BLOCKED = "link_trade_blocked"
    EVENT_BLOCKED = "event_blocked"
    EXECUTOR_UNQUALIFIED = "executor_unqualified"
    EXECUTOR_UNIMPLEMENTED = "executor_unimplemented"


@dataclass(frozen=True, slots=True)
class ResourceRequirement:
    """One consumable or threshold resource requirement for an acquisition option."""

    resource_id: str
    quantity: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.resource_id, str) or not self.resource_id.strip():
            raise ValueError("resource_id must be a non-empty string")
        if type(self.quantity) is not int or self.quantity <= 0:
            raise ValueError("resource quantity must be a positive integer")


@dataclass(frozen=True, slots=True)
class CandidateOption:
    """Declared specification of one way to acquire or produce a target species."""

    option_id: str
    target_species: str
    method_kind: AcquisitionMethodKind
    source_id: str
    executor_status: ExecutorStatus
    consumes_species: str | None = None
    resource_requirements: tuple[ResourceRequirement, ...] = ()
    is_one_time: bool = False
    is_consumed: bool = False
    is_version_blocked: bool = False
    is_trade_blocked: bool = False
    is_event_blocked: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.option_id, str) or not self.option_id.strip():
            raise ValueError("option_id must be a non-empty string")
        if not isinstance(self.target_species, str) or not self.target_species.strip():
            raise ValueError("target_species must be a non-empty string")
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("source_id must be a non-empty string")
        if not isinstance(self.method_kind, AcquisitionMethodKind):
            raise TypeError("method_kind must be an AcquisitionMethodKind")
        if not isinstance(self.executor_status, ExecutorStatus):
            raise TypeError("executor_status must be an ExecutorStatus")

        if self.consumes_species is not None:
            if not isinstance(self.consumes_species, str) or not self.consumes_species.strip():
                raise ValueError("consumes_species must be a non-empty string if specified")
            if self.consumes_species == self.target_species:
                raise ValueError("consumes_species cannot equal target_species")

        transforms = {
            AcquisitionMethodKind.LEVEL_EVOLUTION,
            AcquisitionMethodKind.ITEM_EVOLUTION,
            AcquisitionMethodKind.TRADE_EVOLUTION,
            AcquisitionMethodKind.IN_GAME_TRADE,
        }
        if (self.method_kind in transforms) != (self.consumes_species is not None):
            raise ValueError(
                f"method {self.method_kind} requires consumes_species if and only if "
                "it is a transformation"
            )

        if not isinstance(self.resource_requirements, tuple):
            object.__setattr__(
                self, "resource_requirements", tuple(self.resource_requirements)
            )
        seen_res: set[str] = set()
        for req in self.resource_requirements:
            if not isinstance(req, ResourceRequirement):
                raise TypeError(
                    "resource_requirements items must be ResourceRequirement instances"
                )
            if req.resource_id in seen_res:
                raise ValueError(f"duplicate resource requirement: {req.resource_id}")
            seen_res.add(req.resource_id)

        for bool_field in (
            "is_one_time",
            "is_consumed",
            "is_version_blocked",
            "is_trade_blocked",
            "is_event_blocked",
        ):
            if type(getattr(self, bool_field)) is not bool:
                raise TypeError(f"{bool_field} must be a bool")

        if self.is_consumed and not self.is_one_time:
            raise ValueError(
                "repeatable option (is_one_time=False) cannot be marked is_consumed=True"
            )


@dataclass(frozen=True, slots=True)
class PlanningObservation:
    """Read-only environment, inventory, and reachability snapshot."""

    living_counts: Mapping[str, int]
    reachable_sources: frozenset[str] = frozenset()
    known_unreachable_sources: frozenset[str] = frozenset()
    available_resources: Mapping[str, int] = field(default_factory=dict)
    consumed_options: frozenset[str] = frozenset()
    registered_species: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not isinstance(self.living_counts, Mapping):
            raise TypeError("living_counts must be a Mapping")
        copied_counts: dict[str, int] = {}
        for k, v in self.living_counts.items():
            if not isinstance(k, str) or not k.strip():
                raise ValueError("living_counts species keys must be non-empty strings")
            if type(v) is not int or v < 0:
                raise ValueError("living_counts values must be non-negative integers")
            copied_counts[k] = v
        object.__setattr__(self, "living_counts", MappingProxyType(copied_counts))

        for set_name in (
            "reachable_sources",
            "known_unreachable_sources",
            "consumed_options",
            "registered_species",
        ):
            val = getattr(self, set_name)
            if not isinstance(val, frozenset):
                object.__setattr__(self, set_name, frozenset(val))
            for item in getattr(self, set_name):
                if not isinstance(item, str) or not item.strip():
                    raise ValueError(f"{set_name} items must be non-empty strings")

        overlap = self.reachable_sources & self.known_unreachable_sources
        if overlap:
            raise ValueError(
                f"sources cannot be both reachable and unreachable: {sorted(overlap)}"
            )

        if not isinstance(self.available_resources, Mapping):
            raise TypeError("available_resources must be a Mapping")
        copied_resources: dict[str, int] = {}
        for r_id, qty in self.available_resources.items():
            if not isinstance(r_id, str) or not r_id.strip():
                raise ValueError("available_resources keys must be non-empty strings")
            if type(qty) is not int or qty < 0:
                raise ValueError("available_resources values must be non-negative integers")
            copied_resources[r_id] = qty
        object.__setattr__(self, "available_resources", MappingProxyType(copied_resources))


@dataclass(frozen=True, slots=True)
class CandidateBlocker:
    """One concrete, typed reason an option cannot execute right now."""

    reason: BlockerReason
    detail: str

    def __post_init__(self) -> None:
        if not isinstance(self.reason, BlockerReason):
            raise TypeError("reason must be a BlockerReason")
        if not isinstance(self.detail, str) or not self.detail.strip():
            raise ValueError("detail must be a non-empty string")


@dataclass(frozen=True, slots=True)
class EvaluatedCandidateOption:
    """Evaluated status and blocker report for a single candidate option."""

    option: CandidateOption
    readiness: OptionReadiness
    blockers: tuple[CandidateBlocker, ...]
    marginal_useful_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.option, CandidateOption):
            raise TypeError("option must be a CandidateOption")
        if not isinstance(self.readiness, OptionReadiness):
            raise TypeError("readiness must be an OptionReadiness")
        if not isinstance(self.blockers, tuple):
            object.__setattr__(self, "blockers", tuple(self.blockers))
        for b in self.blockers:
            if not isinstance(b, CandidateBlocker):
                raise TypeError("blockers items must be CandidateBlocker instances")
        if type(self.marginal_useful_count) is not int or self.marginal_useful_count < 0:
            raise ValueError("marginal_useful_count must be a non-negative integer")

        if (self.readiness is OptionReadiness.READY) != (len(self.blockers) == 0):
            raise ValueError("option is READY if and only if blockers is empty")

    @property
    def is_ready(self) -> bool:
        return self.readiness is OptionReadiness.READY

    @property
    def blocker_reasons(self) -> tuple[BlockerReason, ...]:
        return tuple(b.reason for b in self.blockers)

    def has_blocker(self, reason: BlockerReason) -> bool:
        return any(b.reason == reason for b in self.blockers)


@dataclass(frozen=True, slots=True)
class CollectionPlanningReport:
    """Deterministic, side-effect-free living-collection candidate evaluation report."""

    target_species: tuple[str, ...]
    missing_living_targets: tuple[str, ...]
    retained_living_targets: tuple[str, ...]
    marginal_useful_counts: Mapping[str, int]
    evaluated_options: tuple[EvaluatedCandidateOption, ...]
    unsupported_targets: tuple[str, ...]
    registered_but_not_living: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for seq_name in (
            "target_species",
            "missing_living_targets",
            "retained_living_targets",
            "evaluated_options",
            "unsupported_targets",
            "registered_but_not_living",
        ):
            val = getattr(self, seq_name)
            if not isinstance(val, tuple):
                object.__setattr__(self, seq_name, tuple(val))

        object.__setattr__(
            self,
            "marginal_useful_counts",
            MappingProxyType(dict(self.marginal_useful_counts)),
        )

    @property
    def ready_options(self) -> tuple[EvaluatedCandidateOption, ...]:
        return tuple(opt for opt in self.evaluated_options if opt.is_ready)

    @property
    def blocked_options(self) -> tuple[EvaluatedCandidateOption, ...]:
        return tuple(opt for opt in self.evaluated_options if not opt.is_ready)

    @property
    def ready_option_ids(self) -> tuple[str, ...]:
        return tuple(opt.option.option_id for opt in self.ready_options)

    @property
    def blocked_option_ids(self) -> tuple[str, ...]:
        return tuple(opt.option.option_id for opt in self.blocked_options)


def evaluate_collection_planning_catalog(
    target_species: Iterable[str],
    living_counts: Mapping[str, int],
    transformation_edges: Iterable[tuple[str, str]],
    options: Iterable[CandidateOption],
    observation: PlanningObservation,
) -> CollectionPlanningReport:
    """Evaluate candidate acquisition options without side effects or actor goal choice.

    Input requirements:
      - target_species: declared unique living targets.
      - living_counts: observed current physical specimen counts.
      - transformation_edges: directed, acyclic species transformation graph.
      - options: declared candidate acquisition options.
      - observation: reachability, resources, and consumption observations.

    Guarantees:
      - Validates all input types, identifiers, and bounds; rejects malformed inputs.
      - Preserves at least one retained instance of every required living precursor.
      - Recomputes marginal useful demand using augmenting paths (non-additive).
      - Enforces the three explicit gates: source declared, reachable/satisfied, executor qualified.
      - Unknown reachability or resources fail closed (not presumed available).
      - Returns a deterministic display ordering (sorted by target species, then option_id).
    """
    # 1. Validate target species
    targets_tuple = tuple(target_species)
    if not targets_tuple:
        raise ValueError("target_species must not be empty")
    if any(not isinstance(s, str) or not s.strip() for s in targets_tuple):
        raise ValueError("target_species items must be non-empty strings")
    if len(set(targets_tuple)) != len(targets_tuple):
        raise ValueError("target_species items must be unique")
    targets_set = frozenset(targets_tuple)

    # 2. Validate observation
    if not isinstance(observation, PlanningObservation):
        raise TypeError("observation must be a PlanningObservation instance")

    # 3. Validate living counts and reject mismatch with observation.living_counts
    if not isinstance(living_counts, Mapping):
        raise TypeError("living_counts must be a Mapping")
    all_living_keys = set(living_counts.keys()) | set(observation.living_counts.keys())
    for s in all_living_keys:
        if not isinstance(s, str) or not s.strip():
            raise ValueError("living_counts species keys must be non-empty strings")
        ext_count = living_counts.get(s, 0)
        obs_count = observation.living_counts.get(s, 0)
        if type(ext_count) is not int or ext_count < 0:
            raise ValueError(f"living_counts for species '{s}' must be non-negative integer")
        if ext_count != obs_count:
            raise ValueError(
                f"mismatch between living_counts and observation.living_counts for species '{s}': "
                f"{ext_count} != {obs_count}"
            )

    canonical_living = observation.living_counts

    # 4. Validate transformation edges
    edges_tuple = tuple(transformation_edges)
    adjacency: dict[str, set[str]] = {}
    for edge in edges_tuple:
        if (
            not isinstance(edge, tuple)
            or len(edge) != 2
            or any(not isinstance(s, str) or not s.strip() for s in edge)
        ):
            raise ValueError("transformation edges must be 2-tuples of non-empty species strings")
        src, dst = edge
        if src == dst:
            raise ValueError(f"self-loop transformation edge: {src} -> {dst}")
        adjacency.setdefault(src, set()).add(dst)

    # Check acyclicity
    visiting: set[str] = set()
    visited: set[str] = set()

    def check_acyclic(node: str) -> None:
        if node in visiting:
            raise ValueError("transformation graph must be acyclic")
        if node in visited:
            return
        visiting.add(node)
        for child in adjacency.get(node, ()):
            check_acyclic(child)
        visiting.remove(node)
        visited.add(node)

    for node in adjacency:
        check_acyclic(node)

    edges_set = set(edges_tuple)

    # 5. Validate options
    options_tuple = tuple(options)
    seen_option_ids: set[str] = set()
    for opt in options_tuple:
        if not isinstance(opt, CandidateOption):
            raise TypeError("options items must be CandidateOption instances")
        if opt.option_id in seen_option_ids:
            raise ValueError(f"duplicate option_id: {opt.option_id}")
        seen_option_ids.add(opt.option_id)

        # Transformation options must exist in declared transformation_edges
        if opt.consumes_species is not None:
            edge_pair = (opt.consumes_species, opt.target_species)
            if edge_pair not in edges_set:
                raise ValueError(
                    f"option {opt.option_id} declares transformation {edge_pair[0]} -> "
                    f"{edge_pair[1]} not present in declared transformation_edges"
                )

        # Reject observed consumed option if declared repeatable
        if opt.option_id in observation.consumed_options and not opt.is_one_time:
            raise ValueError(
                f"repeatable option {opt.option_id} cannot be marked consumed in observation"
            )

    # 6. Compute living census
    missing_living = tuple(s for s in targets_tuple if canonical_living.get(s, 0) == 0)
    retained_living = tuple(s for s in targets_tuple if canonical_living.get(s, 0) > 0)

    # Registered but physically absent targets
    registered_absent = tuple(
        s for s in targets_tuple
        if s in observation.registered_species and canonical_living.get(s, 0) == 0
    )

    # 7. Compute marginal useful counts via augmenting paths
    all_candidate_species = set(targets_tuple)
    for opt in options_tuple:
        all_candidate_species.add(opt.target_species)
        if opt.consumes_species is not None:
            all_candidate_species.add(opt.consumes_species)
    for src, dst in edges_tuple:
        all_candidate_species.add(src)
        all_candidate_species.add(dst)

    capture_candidates = tuple(sorted(all_candidate_species))
    marginal_demand = useful_capture_counts(
        targets_set,
        canonical_living,
        edges_tuple,
        capture_candidates,
    )

    # 8. Evaluate each candidate option independently
    evaluated: list[EvaluatedCandidateOption] = []
    declared_targets: set[str] = set()

    for opt in options_tuple:
        declared_targets.add(opt.target_species)
        blockers: list[CandidateBlocker] = []

        # Gate (a) / Demand check:
        # Does the target species have remaining living collection demand?
        is_missing_target = (
            (opt.target_species in targets_set)
            and (canonical_living.get(opt.target_species, 0) == 0)
        )
        marginal_useful = marginal_demand.get(opt.target_species, 0)

        # Capture demand can be zero because this very precursor already covers
        # a downstream target. To assess a transformation, remove the consumed
        # specimen before asking whether its replacement is useful. This is
        # physical stock accounting, not a predicted gameplay outcome or reward.
        if opt.consumes_species is not None:
            remaining = dict(canonical_living)
            precursor_count = remaining.get(opt.consumes_species, 0)
            if precursor_count:
                remaining[opt.consumes_species] = precursor_count - 1
                marginal_useful = min(1, useful_capture_counts(
                    targets_set, remaining, edges_tuple, (opt.target_species,),
                )[opt.target_species])

        if not is_missing_target and marginal_useful == 0:
            blockers.append(
                CandidateBlocker(
                    BlockerReason.NO_REMAINING_DEMAND,
                    f"species {opt.target_species} is already retained and has no downstream "
                    "transformation demand",
                )
            )

        # Gate (b): Reachability, resources, precursor preservation, and event/version/one-time
        # Reachability
        if opt.source_id in observation.known_unreachable_sources:
            blockers.append(
                CandidateBlocker(
                    BlockerReason.SOURCE_UNREACHABLE,
                    f"source {opt.source_id} is explicitly unreachable",
                )
            )
        elif opt.source_id not in observation.reachable_sources:
            blockers.append(
                CandidateBlocker(
                    BlockerReason.SOURCE_REACHABILITY_UNKNOWN,
                    f"source {opt.source_id} reachability has not been observed (unknown != true)",
                )
            )

        # Precursor retention / surplus check for transformations
        if opt.consumes_species is not None:
            precursor = opt.consumes_species
            held_precursor = canonical_living.get(precursor, 0)
            required_to_retain = 1 if precursor in targets_set else 0
            surplus = max(0, held_precursor - required_to_retain)

            if held_precursor == 0:
                blockers.append(
                    CandidateBlocker(
                        BlockerReason.PRECURSOR_UNAVAILABLE,
                        f"no specimens of precursor {precursor} are currently held",
                    )
                )
            elif surplus == 0:
                blockers.append(
                    CandidateBlocker(
                        BlockerReason.PRECURSOR_LAST_RETAINED,
                        f"only held specimen of precursor {precursor} must be preserved for "
                        "living target",
                    )
                )

        # Resource requirements
        for req in opt.resource_requirements:
            if req.resource_id not in observation.available_resources:
                blockers.append(
                    CandidateBlocker(
                        BlockerReason.RESOURCE_UNKNOWN,
                        f"resource {req.resource_id} is unobserved / unknown (unknown != true)",
                    )
                )
            else:
                available_qty = observation.available_resources[req.resource_id]
                if available_qty < req.quantity:
                    blockers.append(
                        CandidateBlocker(
                            BlockerReason.RESOURCE_INSUFFICIENT,
                            f"resource {req.resource_id} requires {req.quantity}, "
                            f"but only {available_qty} available",
                        )
                    )

        # One-time consumed check
        if opt.is_one_time and (opt.is_consumed or opt.option_id in observation.consumed_options):
            blockers.append(
                CandidateBlocker(
                    BlockerReason.ONE_TIME_CONSUMED,
                    f"one-time option {opt.option_id} has already been consumed",
                )
            )

        # Version, Trade, and Event blockers
        if opt.is_version_blocked:
            blockers.append(
                CandidateBlocker(
                    BlockerReason.VERSION_EXCLUSIVE_BLOCKED,
                    f"option {opt.option_id} is blocked by version exclusivity",
                )
            )
        if opt.is_trade_blocked:
            blockers.append(
                CandidateBlocker(
                    BlockerReason.LINK_TRADE_BLOCKED,
                    f"option {opt.option_id} requires an unsupported external link trade",
                )
            )
        if opt.is_event_blocked:
            blockers.append(
                CandidateBlocker(
                    BlockerReason.EVENT_BLOCKED,
                    f"option {opt.option_id} requires an unsupported external event distribution",
                )
            )

        # Gate (c): Implemented and qualified executor status
        if opt.executor_status is ExecutorStatus.UNIMPLEMENTED:
            blockers.append(
                CandidateBlocker(
                    BlockerReason.EXECUTOR_UNIMPLEMENTED,
                    f"option {opt.option_id} has no implemented runtime executor",
                )
            )
        elif opt.executor_status is ExecutorStatus.UNQUALIFIED:
            blockers.append(
                CandidateBlocker(
                    BlockerReason.EXECUTOR_UNQUALIFIED,
                    f"option {opt.option_id} executor exists but is not currently qualified",
                )
            )

        readiness = OptionReadiness.READY if not blockers else OptionReadiness.BLOCKED

        # Marginal useful count for display/reporting
        effective_useful = max(marginal_useful, 1 if is_missing_target else 0)
        evaluated.append(
            EvaluatedCandidateOption(
                option=opt,
                readiness=readiness,
                blockers=tuple(blockers),
                marginal_useful_count=effective_useful,
            )
        )

    # 9. Deterministic display ordering (sorted by target species, then option_id)
    evaluated.sort(key=lambda item: (item.option.target_species, item.option.option_id))

    # 10. Unsupported targets
    unsupported = tuple(s for s in missing_living if s not in declared_targets)

    return CollectionPlanningReport(
        target_species=targets_tuple,
        missing_living_targets=missing_living,
        retained_living_targets=retained_living,
        marginal_useful_counts=MappingProxyType(dict(marginal_demand)),
        evaluated_options=tuple(evaluated),
        unsupported_targets=unsupported,
        registered_but_not_living=registered_absent,
    )
