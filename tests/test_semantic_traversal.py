from __future__ import annotations

import pytest

from pokemon_red_completion.local_router import (
    LocalEdge,
    LocalGraph,
    LocalRouterError,
    find_local_path,
)
from pokemon_red_completion.semantic_traversal import (
    LocalPassageRequirement,
    PredicateObservation,
    PredicateState,
    SemanticTraversalError,
    apply_local_passage_requirements,
    satisfied_predicates,
)


def test_only_independently_satisfied_predicates_become_capabilities() -> None:
    observations = (
        PredicateObservation("story:open", PredicateState.SATISFIED),
        PredicateObservation("story:closed", PredicateState.UNSATISFIED),
        PredicateObservation("story:unread", PredicateState.UNKNOWN),
    )

    assert satisfied_predicates(observations) == frozenset({"story:open"})


def test_contradictory_predicate_observations_fail_closed() -> None:
    with pytest.raises(SemanticTraversalError, match="contradictory"):
        satisfied_predicates(
            (
                PredicateObservation("story:door", PredicateState.SATISFIED),
                PredicateObservation("story:door", PredicateState.UNKNOWN),
            )
        )


def test_an_exact_passage_is_unavailable_until_its_predicate_is_present() -> None:
    graph = LocalGraph(
        {
            (0, 0): (LocalEdge((0, 1), "right"),),
            (0, 1): (LocalEdge((0, 2), "right"),),
            (0, 2): (),
        }
    )
    projected = apply_local_passage_requirements(
        {7: graph},
        (LocalPassageRequirement(7, (0, 1), (0, 2), "story:door"),),
    )[7]

    with pytest.raises(LocalRouterError, match="no permitted local route"):
        find_local_path(projected, (0, 0), (0, 2))

    opened = find_local_path(
        projected,
        (0, 0),
        (0, 2),
        capabilities=frozenset({"story:door"}),
    )
    assert opened.coordinates == ((0, 0), (0, 1), (0, 2))
    assert opened.edges[-1].requirements == frozenset({"story:door"})


def test_a_stale_adapter_binding_cannot_silently_leave_the_edge_open() -> None:
    graph = LocalGraph({(0, 0): (LocalEdge((0, 1), "right"),), (0, 1): ()})

    with pytest.raises(SemanticTraversalError, match="lacks semantic transitions"):
        apply_local_passage_requirements(
            {7: graph},
            (LocalPassageRequirement(7, (0, 1), (0, 2), "story:door"),),
        )
