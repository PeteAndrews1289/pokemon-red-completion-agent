"""Game-neutral semantic requirements for otherwise traversable passages.

Static terrain answers whether two coordinates touch. It cannot answer whether
a guard, story script, or durable world flag currently permits the transition.
Adapters attach opaque predicate names to exact local edges, observations
classify those predicates, and the existing local router admits only
requirements present in its capability set.

Unknown predicates deliberately contribute no capability. A missing read is
therefore unavailable rather than accidentally open.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum

from pokemon_red_completion.global_router import Coordinate
from pokemon_red_completion.local_router import LocalEdge, LocalGraph


class PredicateState(StrEnum):
    """What one live observation establishes about a semantic predicate."""

    SATISFIED = "satisfied"
    UNSATISFIED = "unsatisfied"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class PredicateObservation:
    """One predicate truth observation supplied by a title adapter."""

    name: str
    state: PredicateState

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("a semantic predicate needs a name")
        if not isinstance(self.state, PredicateState):
            raise TypeError("a semantic predicate needs a PredicateState")


@dataclass(frozen=True, slots=True)
class LocalPassageRequirement:
    """One directed coordinate edge that requires a semantic predicate."""

    map_id: int
    source_at: Coordinate
    target_at: Coordinate
    predicate: str

    def __post_init__(self) -> None:
        if type(self.map_id) is not int or self.map_id < 0:  # noqa: E721
            raise ValueError("a passage requirement needs a non-negative map id")
        if self.source_at == self.target_at:
            raise ValueError("a passage requirement must cross an edge")
        if not self.predicate:
            raise ValueError("a passage requirement needs a predicate")


class SemanticTraversalError(ValueError):
    """Raised when semantic observations or graph bindings disagree."""


def satisfied_predicates(
    observations: Iterable[PredicateObservation],
) -> frozenset[str]:
    """Return only predicates proved true, rejecting contradictory reads."""

    states: dict[str, PredicateState] = {}
    for observation in observations:
        previous = states.get(observation.name)
        if previous is not None and previous is not observation.state:
            raise SemanticTraversalError(
                f"predicate {observation.name!r} has contradictory observations"
            )
        states[observation.name] = observation.state
    return frozenset(
        name for name, state in states.items() if state is PredicateState.SATISFIED
    )


def apply_local_passage_requirements(
    graphs: Mapping[int, LocalGraph],
    requirements: Iterable[LocalPassageRequirement],
) -> dict[int, LocalGraph]:
    """Attach predicates to exact directed edges, failing on stale bindings."""

    grouped: dict[int, dict[tuple[Coordinate, Coordinate], set[str]]] = {}
    for requirement in requirements:
        keyed = grouped.setdefault(requirement.map_id, {})
        keyed.setdefault((requirement.source_at, requirement.target_at), set()).add(
            requirement.predicate
        )

    projected = dict(graphs)
    for map_id, bindings in grouped.items():
        graph = projected.get(map_id)
        if graph is None:
            raise SemanticTraversalError(
                f"semantic requirements name unavailable map {map_id}"
            )
        remaining = set(bindings)
        edges: dict[Coordinate, tuple[LocalEdge, ...]] = {}
        for source, outgoing in graph.edges.items():
            updated: list[LocalEdge] = []
            for edge in outgoing:
                predicates = bindings.get((source, edge.target))
                if predicates is None:
                    updated.append(edge)
                    continue
                remaining.discard((source, edge.target))
                updated.append(
                    replace(
                        edge,
                        requirements=edge.requirements | frozenset(predicates),
                    )
                )
            edges[source] = tuple(updated)
        if remaining:
            raise SemanticTraversalError(
                f"map {map_id} lacks semantic transitions {sorted(remaining)!r}"
            )
        projected[map_id] = LocalGraph(edges)
    return projected
