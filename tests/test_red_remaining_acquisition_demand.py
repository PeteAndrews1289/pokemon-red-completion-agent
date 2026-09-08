"""Independent remaining-demand falsifiers, including a tiny exhaustive game."""

from collections import deque
from dataclasses import replace
from itertools import product

import pytest
from test_red_acquisition import _observation

from pokemon_red_completion.red_acquisition import (
    RED_ACQUISITION_CATALOG,
    RedAcquisitionKind,
    RedAreaDirective,
    RedAreaExecutionPolicy,
    plan_red_area_encounter,
    rank_red_sources,
    run_red_area_survey,
    summarize_red_area_survey,
)
from pokemon_red_completion.red_collection import red_species_ref

CURRENT = replace(RED_ACQUISITION_CATALOG, remaining_demand=True)


@pytest.mark.parametrize("enabled", [False, True])
def test_runtime_mode_reaches_native_and_routed_observers_without_mutating_parent(
    monkeypatch, enabled,
):
    from types import SimpleNamespace

    import run_paired_red_bounded_player as runner

    from pokemon_red_completion.red_goal_context import RedGoalContextRuntime

    runtime = RedGoalContextRuntime(
        profile=SimpleNamespace(providers=()), capture=None, emulator=None,
        reader=None, observer=None, adapter=None, remaining_acquisition_demand=not enabled,
    )
    routed_modes = []

    def router(actual, *_args, **_kwargs):
        routed_modes.append(actual.remaining_acquisition_demand)
        return SimpleNamespace(enumerate=lambda _: None)

    monkeypatch.setattr(runner, "RedResourceGoalRouter", router)
    monkeypatch.setattr(runner, "RedBoundedPlayerObserver", lambda **kw: SimpleNamespace(**kw))
    for world in (None, object()):
        observer = runner._player_observer(
            runtime, None, world, remaining_acquisition_demand=enabled,
        )
        assert observer.runtime.remaining_acquisition_demand is enabled
    assert routed_modes == [enabled]
    assert runtime.remaining_acquisition_demand is not enabled


def test_empty_and_completed_collection_limits():
    from pokemon_red_completion.collection import (
        CollectionLocation,
        CollectionObservation,
        LivingSpecimen,
    )
    from pokemon_red_completion.red_collection import RED_SOLO_COLLECTION_CONTRACT

    roots = CURRENT.required_root_holdings(_observation())
    assert {s: n for s, n in roots.items() if n} == CURRENT.required_root_acquisitions()
    specimens = tuple(
        LivingSpecimen(s, 50, CollectionLocation.BOX, container_index=i // 20, slot_index=i % 20)
        for i, s in enumerate(RED_SOLO_COLLECTION_CONTRACT.resolved_living_target_species)
    )
    complete = CollectionObservation(frozenset(), specimens, 0, 6, (20,) * 6 + (0,) * 6, 0, 20)
    assert rank_red_sources(complete, catalog=CURRENT) == ()


def requirement(catalog, source, number, *living, owned_numbers=()):
    survey = summarize_red_area_survey(
        source, _observation(*living, owned_numbers=owned_numbers), catalog,
    )
    return next(row for row in survey.requirements if row.species_ref == red_species_ref(number))


@pytest.mark.parametrize("living,expected", [
    ((), (2, 0, 2)), ((56,), (2, 1, 1)), ((56, 56), (2, 2, 0)),
    ((56, 57), (1, 1, 0)), ((57, 57), (1, 0, 1)), ((56, 57, 57), (1, 1, 0)),
])
def test_actual_mankey_family(living, expected):
    row = requirement(CURRENT, "wild:Route5:grass", 56, *living)
    assert (row.required_count, row.retained_count, row.missing_count) == expected


def test_registration_and_historical_catalog_do_not_credit_living_descendants():
    row = requirement(CURRENT, "wild:Route5:grass", 56, 56, owned_numbers=(56, 57))
    assert row.missing_count == 1
    legacy = requirement(RED_ACQUISITION_CATALOG, "wild:Route5:grass", 56, 56, 57)
    assert (legacy.required_count, legacy.retained_count, legacy.missing_count) == (2, 1, 1)
    assert (CURRENT.required_root_acquisitions()
            == RED_ACQUISITION_CATALOG.required_root_acquisitions())


def test_completed_consuming_trade_no_longer_requests_its_precursor():
    row = requirement(CURRENT, "wild:Route22:grass", 21, 21, 83)
    assert (row.required_count, row.retained_count, row.missing_count) == (1, 1, 0)
    assert requirement(CURRENT, "wild:Route22:grass", 21, 83, 83).missing_count == 1
    # Slowbro is a directly caught root in this catalog; Lickitung consumes it.
    assert requirement(CURRENT, "wild:SeafoamIslandsB2F:grass", 80, 80, 108).missing_count == 0
    assert requirement(CURRENT, "wild:SeafoamIslandsB2F:grass", 80, 80).missing_count == 1


def _catalog(edges):
    # All unrelated methods remain intact. Each test supplies a different graph
    # over Spearow/Fearow/Farfetch'd, including a consuming trade edge.
    methods = []
    for method in CURRENT.methods:
        number = int(method.species_ref[-3:])
        if number in edges:
            method = replace(
                method, kind=(RedAcquisitionKind.IN_GAME_TRADE if number == 83
                              else RedAcquisitionKind.EVOLUTION),
                consumes_species_ref=red_species_ref(edges[number]),
                source_id=f"test-transform:{number}",
            )
        methods.append(method)
    return replace(CURRENT, methods=tuple(methods))


def _fewest_captures(initial, edges):
    """Search concrete capture/consume actions; do not reproduce graph accounting."""
    numbers = (21, 22, 83)
    queue = deque([(initial, 0)])
    visited = {initial}
    while queue:
        state, captures = queue.popleft()
        if all(state):
            return captures
        actions = []
        if captures < 3:
            actions.append(((state[0] + 1, *state[1:]), 1))
        for target, precursor in edges.items():
            source_index, target_index = numbers.index(precursor), numbers.index(target)
            if state[source_index]:
                changed = list(state)
                changed[source_index] -= 1
                changed[target_index] += 1
                actions.append((tuple(changed), 0))
        for child, cost in actions:
            if child not in visited:
                visited.add(child)
                if cost:
                    queue.append((child, captures + cost))
                else:
                    queue.appendleft((child, captures))
    raise AssertionError("tiny graph must be completable with three captures")


@pytest.mark.parametrize("edges", [{22: 21, 83: 22}, {22: 21, 83: 21}, {83: 21, 22: 83}])
def test_multistage_branch_and_trade_demands_match_exhaustive_actions(edges):
    catalog = _catalog(edges)
    for counts in product(range(4), repeat=3):
        living = tuple(n for n, count in zip((21, 22, 83), counts, strict=True)
                       for _ in range(count))
        expected = _fewest_captures(counts, edges)
        row = requirement(catalog, "wild:Route22:grass", 21, *living)
        assert row.missing_count == expected, (edges, counts, row)
        reverse = requirement(replace(catalog, methods=tuple(reversed(catalog.methods))),
                              "wild:Route22:grass", 21, *living)
        assert reverse == row


def test_rank_encounter_and_executor_share_completed_family_accounting():
    observation = _observation(56, 57)
    assert summarize_red_area_survey("wild:Route5:grass", observation, CURRENT).complete
    assert "wild:Route5:grass" not in {
        p.source_id for p in rank_red_sources(observation, catalog=CURRENT)
    }
    decision = plan_red_area_encounter("wild:Route5:grass", observation, catalog=CURRENT)
    assert decision.directive is RedAreaDirective.STOP

    class Executor:
        def read_collection(self):
            return observation

        def encountered_species_ref(self):
            return None

        def __getattr__(self, name):
            raise AssertionError(f"completed source must never call {name}")

    result = run_red_area_survey("wild:Route5:grass", Executor(), catalog=CURRENT)
    assert result.passed and result.actions_executed == result.captures == 0


def test_execution_stops_after_last_needed_copy_without_waiting_for_evolution():
    class Executor:
        living = (57,)
        encountered = None

        def read_collection(self):
            return _observation(*self.living)

        def encountered_species_ref(self):
            return self.encountered

        def seek_encounter(self):
            assert self.living == (57,)
            self.encountered = red_species_ref(56)

        def capture_encounter(self, species):
            assert species == self.encountered == red_species_ref(56)
            self.living += (56,)
            self.encountered = None

    result = run_red_area_survey(
        "wild:Route5:grass", Executor(), catalog=CURRENT,
        policy=RedAreaExecutionPolicy(max_actions=3),
    )
    assert result.passed and result.captures == 1 and result.actions_executed == 2


@pytest.mark.parametrize("value", [None, 1, "true"])
def test_catalog_rejects_non_boolean_mode(value):
    with pytest.raises(TypeError, match="remaining_demand"):
        replace(CURRENT, remaining_demand=value)
