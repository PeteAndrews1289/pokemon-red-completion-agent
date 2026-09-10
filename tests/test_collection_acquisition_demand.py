"""Hand-computed cases and independent exhaustive physical transformations."""

from itertools import product

import pytest

from pokemon_red_completion.collection_acquisition_demand import useful_capture_counts


# Flash independently proposed these eight shapes from a tool-free contract.
# Abstract names avoid claiming later-game conditional evolutions are supported.
@pytest.mark.parametrize("targets,counts,edges,candidates,expected", [
    ("BC", {"A": 1}, ("AB", "AC"), "ABCD", {"A": 1, "B": 1, "C": 1, "D": 0}),
    ("ABC", {"A": 1}, ("AB", "BC"), "ABC", {"A": 2, "B": 2, "C": 1}),
    ("ABC", {"C": 1}, ("AB", "BC"), "ABC", {"A": 2, "B": 1, "C": 0}),
    ("AB", {"B": 3}, ("AB",), "AB", {"A": 1, "B": 0}),
    ("ABC", {"A": 2, "B": 1, "C": 1}, ("AB", "BC"), "ABC", {"A": 0, "B": 0, "C": 0}),
    ("ABC", {"A": 1}, ("AB", "AC"), "ABC", {"A": 2, "B": 1, "C": 1}),
    ("ABCD", {"A": 1, "B": 1}, ("AB", "BC", "BD"), "ABCD",
     {"A": 2, "B": 2, "C": 1, "D": 1}),
    ("ABCDE", {"B": 2, "E": 1}, ("AB", "BC", "AD", "DE"), "ABDCE",
     {"A": 2, "B": 0, "D": 1, "C": 0, "E": 0}),
])
def test_independently_drafted_literal_cases(targets, counts, edges, candidates, expected):
    graph = tuple(tuple(edge) for edge in edges)
    assert useful_capture_counts(frozenset(targets), counts, graph, tuple(candidates)) == expected


def _physical_maximum(counts, edges):
    """Enumerate consume/produce state transitions, not bipartite matching."""
    protected = tuple(int(n > 0) for n in counts)
    seen, pending, best = {counts}, [counts], sum(protected)
    while pending:
        state = pending.pop()
        best = max(best, sum(n > 0 for n in state))
        for source, target in edges:
            if state[source] > protected[source]:
                child = list(state)
                child[source] -= 1
                child[target] += 1
                child = tuple(child)
                if child not in seen:
                    seen.add(child)
                    pending.append(child)
    return best


@pytest.mark.parametrize("edges", [((0, 1), (1, 2)), ((0, 1), (0, 2)), ((0, 2), (1, 2))])
def test_all_small_stocks_match_concrete_transformations_and_are_order_invariant(edges):
    nodes = ("A", "B", "C")
    graph = tuple((nodes[a], nodes[b]) for a, b in edges)
    for counts in product(range(4), repeat=3):
        baseline = _physical_maximum(counts, edges)
        expected = {}
        for index, species in enumerate(nodes):
            child, useful = list(counts), 0
            for extra in range(1, 4):
                child[index] += 1
                if _physical_maximum(tuple(child), edges) != baseline + extra:
                    break
                useful += 1
            expected[species] = useful
        stock = dict(zip(nodes, counts, strict=True))
        assert useful_capture_counts(frozenset(nodes), stock, graph, nodes) == expected
        assert useful_capture_counts(
            frozenset(nodes), dict(reversed(tuple(stock.items()))), tuple(reversed(graph)),
            tuple(reversed(nodes)),
        ) == expected


def test_alternatives_recompute_after_capture_instead_of_adding_up():
    graph = (("A", "B"), ("A", "C"))
    initial = useful_capture_counts(frozenset("ABC"), {"A": 1}, graph, tuple("ABC"))
    assert initial == {"A": 2, "B": 1, "C": 1}
    one_spare = useful_capture_counts(frozenset("ABC"), {"A": 2}, graph, tuple("ABC"))
    assert one_spare == {"A": 1, "B": 1, "C": 1}
    assert useful_capture_counts(frozenset("ABC"), {"A": 3}, graph, tuple("ABC")) == {
        "A": 0, "B": 0, "C": 0,
    }


@pytest.mark.parametrize("edges", [(("A", "A"),), (("A", "B"), ("B", "A"))])
def test_cycles_reject_even_when_collection_complete(edges):
    with pytest.raises(ValueError, match="acyclic"):
        useful_capture_counts(frozenset("AB"), {"A": 1, "B": 1}, edges, tuple("AB"))


@pytest.mark.parametrize("count", [-1, True, 1.0])
def test_invalid_stock_rejects(count):
    with pytest.raises(ValueError, match="nonnegative"):
        useful_capture_counts(frozenset("A"), {"A": count}, (), ("A",))


def test_non_target_stock_is_available_but_never_cloned():
    assert useful_capture_counts(frozenset("BC"), {"A": 2}, (("A", "B"), ("A", "C")),
                                 tuple("ABC")) == {"A": 0, "B": 0, "C": 0}
