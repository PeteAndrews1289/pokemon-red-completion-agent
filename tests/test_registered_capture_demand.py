import itertools

import pytest

from pokemon_red_completion.collection_acquisition_demand import useful_registered_capture_counts


def demand(targets, registered=(), counts=None, edges=(), candidates=("A",), protected=None):
    return useful_registered_capture_counts(
        frozenset(targets), frozenset(registered), counts or {}, edges, candidates,
        protected_counts=protected,
    )


def test_one_capture_covers_whole_line_without_living_form_duplicates():
    assert demand("ABC", edges=(("A", "B"), ("B", "C"))) == {"A": 1}
    assert demand("ABC", "A", {"A": 1}, (("A", "B"), ("B", "C"))) == {"A": 0}


def test_branching_requires_two_specimens_not_three_living_forms():
    edges = (("A", "B"), ("A", "C"))
    assert demand("ABC", edges=edges) == {"A": 2}
    assert demand("ABC", "A", {"A": 1}, edges) == {"A": 1}
    assert demand("ABC", "A", {"A": 2}, edges) == {"A": 0}


def test_red_credit_skips_blue_grind_but_new_branch_can_require_known_base():
    assert demand("ABC", "ABC", edges=(("A", "B"), ("B", "C"))) == {"A": 0}
    assert demand("ABCD", "ABC", edges=(("A", "D"),)) == {"A": 1}
    assert demand("ABCD", "ABC", {"A": 1}, (("A", "D"),)) == {"A": 0}


def test_story_or_trade_dependency_reserve_is_physical_not_registration_quota():
    edges = (("A", "B"),)
    assert demand("AB", "A", {"A": 1}, edges, protected={"A": 1}) == {"A": 1}
    assert demand("AB", "A", {"A": 2}, edges, protected={"A": 1}) == {"A": 0}


def test_competing_sources_and_merging_paths_do_not_double_credit():
    edges = (("A", "C"), ("B", "C"), ("B", "D"), ("C", "E"))
    assert demand("CDE", "AB", {"A": 1, "B": 1}, edges,
                  candidates=("A", "B")) == {"A": 0, "B": 0}
    assert demand("CDE", "AB", {"B": 1}, edges,
                  candidates=("A", "B")) == {"A": 1, "B": 1}


@pytest.mark.parametrize("args", [
    dict(targets="B", counts={"A": 1}),
    dict(targets="B", registered="A", counts={"A": 1}, protected={"A": 2}),
    dict(targets="B", registered="A", counts={"A": 1}, protected={"A": True}),
    dict(targets="B", edges=(("A", "B"), ("B", "A"))),
])
def test_invalid_inputs_fail(args):
    with pytest.raises(ValueError):
        demand(**args)


def test_all_small_dags_against_independent_exhaustive_physical_path_enumeration():
    # An independent tiny oracle: enumerate every actual path each specimen can
    # take and union its registrations. No matching/flow code is reused.
    nodes = "ABCD"
    possible = tuple(itertools.combinations(nodes, 2))
    for mask in range(1 << len(possible)):
        edges = tuple(e for i, e in enumerate(possible) if mask & (1 << i))

        def paths(start, edges=edges):
            found = [frozenset({start})]
            for a, b in edges:
                if a == start:
                    found.extend(p | {start} for p in paths(b))
            return found

        registered = frozenset("A")
        missing = frozenset(nodes) - registered
        def brute(copies, missing=missing):
            return max((len(set().union(*chosen) & missing)
                        for chosen in itertools.product(paths("A"), repeat=copies)), default=0)

        for initial in (0, 1, 2):
            previous = brute(initial)
            wanted = 0
            for extra in range(1, 4):
                current = brute(initial + extra)
                if current <= previous:
                    break
                previous = current
                wanted += 1
            actual = demand(nodes, registered, {"A": initial}, edges)
            assert actual == {"A": wanted}, (edges, initial)
