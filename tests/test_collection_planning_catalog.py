"""ROM-free unit tests for collection_planning_catalog.

Tests verify:
  - Three distinct gates: source declared, reachable/satisfied, executor qualified.
  - "Unknown is not true": unobserved reachability and resources fail closed.
  - Living-specimen precursor retention: preserving the last required copy,
    authorizing evolution only on surplus copies across multi-stage chains.
  - Branching alternatives and marginal non-additive demand with recomputation.
  - Defensive copying and mappingproxy immutability against external/direct mutation.
  - Strict edge declaration requirements for transformation options.
  - Rejection of mismatched living_counts and contradictory consumption flags.
  - Registered-only ownership tracked via registered_but_not_living without
    satisfying living target requirements.
"""

from __future__ import annotations

from collections import UserDict
from dataclasses import replace

import pytest

from pokemon_red_completion.collection_planning_catalog import (
    AcquisitionMethodKind,
    BlockerReason,
    CandidateOption,
    ExecutorStatus,
    PlanningObservation,
    ResourceRequirement,
    evaluate_collection_planning_catalog,
)


def _make_capture_option(
    option_id: str,
    target: str,
    source: str = "field:grass_1",
    executor_status: ExecutorStatus = ExecutorStatus.QUALIFIED,
    resource_requirements: tuple[ResourceRequirement, ...] = (),
    is_one_time: bool = False,
    is_consumed: bool = False,
    is_version_blocked: bool = False,
    is_trade_blocked: bool = False,
    is_event_blocked: bool = False,
) -> CandidateOption:
    return CandidateOption(
        option_id=option_id,
        target_species=target,
        method_kind=AcquisitionMethodKind.WILD_ENCOUNTER,
        source_id=source,
        executor_status=executor_status,
        resource_requirements=resource_requirements,
        is_one_time=is_one_time,
        is_consumed=is_consumed,
        is_version_blocked=is_version_blocked,
        is_trade_blocked=is_trade_blocked,
        is_event_blocked=is_event_blocked,
    )


def _make_evolution_option(
    option_id: str,
    precursor: str,
    target: str,
    source: str = "menu:evolution",
    method_kind: AcquisitionMethodKind = AcquisitionMethodKind.LEVEL_EVOLUTION,
    executor_status: ExecutorStatus = ExecutorStatus.QUALIFIED,
    resource_requirements: tuple[ResourceRequirement, ...] = (),
) -> CandidateOption:
    return CandidateOption(
        option_id=option_id,
        target_species=target,
        method_kind=method_kind,
        source_id=source,
        executor_status=executor_status,
        consumes_species=precursor,
        resource_requirements=resource_requirements,
    )


# ---------------------------------------------------------------------------
# 1. Hand-authored expectations & Three Explicit Gates
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("key", ["", "  ", None, 1])
def test_codex_invalid_zero_count_key_is_not_normalized_away(key):
    with pytest.raises(ValueError, match="species keys"):
        evaluate_collection_planning_catalog(("A",), {key: 0}, (), (), PlanningObservation({}))


def test_codex_report_copies_general_mapping_and_resource_alias_cannot_enable_capture():
    raw_resources = {"ball": 0}
    obs = PlanningObservation({}, reachable_sources=frozenset({"grass"}),
                              available_resources=raw_resources)
    raw_resources["ball"] = True
    option = _make_capture_option("catch", "A", source="grass",
                                 resource_requirements=(ResourceRequirement("ball"),))
    report = evaluate_collection_planning_catalog(("A",), {}, (), (option,), obs)
    assert report.evaluated_options[0].blocker_reasons == (BlockerReason.RESOURCE_INSUFFICIENT,)
    mutable_counts = UserDict({"A": 1})
    copied = replace(report, marginal_useful_counts=mutable_counts)
    mutable_counts["A"] = 999
    assert copied.marginal_useful_counts["A"] == 1
    with pytest.raises(TypeError):
        copied.marginal_useful_counts["A"] = 5


def test_codex_non_target_intermediate_is_useful_without_more_captures():
    # A surplus already covers C in demand accounting; A->B must still be allowed.
    counts = {"A": 2}
    obs = PlanningObservation(counts, reachable_sources=frozenset({"menu"}))
    option = _make_evolution_option("step", "A", "B", source="menu")
    report = evaluate_collection_planning_catalog(
        ("A", "C"), counts, (("A", "B"), ("B", "C")), (option,), obs,
    )
    assert report.marginal_useful_counts["B"] == 0
    assert report.ready_option_ids == ("step",)
    assert report.evaluated_options[0].marginal_useful_count == 1


def test_three_gates_explicitly_distinguished():
    """Verify (a) source declared, (b) reachable & satisfied, (c) executor qualified."""
    targets = ("A", "B", "C")
    living = {"A": 1, "B": 0, "C": 0}
    edges = (("A", "B"),)

    opt_b_evolve = _make_evolution_option("evolve_a_to_b", "A", "B")
    opt_c_wild = _make_capture_option("catch_c", "C", source="area:lake")

    obs_unknown = PlanningObservation(
        living_counts=living,
        reachable_sources=frozenset({"menu:evolution"}),
        known_unreachable_sources=frozenset(),
    )

    report = evaluate_collection_planning_catalog(
        targets, living, edges, [opt_b_evolve, opt_c_wild], obs_unknown
    )

    eval_b = next(e for e in report.evaluated_options if e.option.option_id == "evolve_a_to_b")
    assert not eval_b.is_ready
    assert eval_b.has_blocker(BlockerReason.PRECURSOR_LAST_RETAINED)

    eval_c = next(e for e in report.evaluated_options if e.option.option_id == "catch_c")
    assert not eval_c.is_ready
    assert eval_c.has_blocker(BlockerReason.SOURCE_REACHABILITY_UNKNOWN)


def test_unknown_is_not_true_for_reachability_and_resources():
    """Reachability or resources not explicitly observed must fail closed as unknown."""
    targets = ("X",)
    living = {"X": 0}
    edges = ()

    opt = _make_capture_option(
        "catch_x",
        "X",
        source="area:cave",
        resource_requirements=(ResourceRequirement("ball:ultra", 2),),
    )

    # 1. Source not in reachable_sources and ball not in available_resources
    obs_empty = PlanningObservation(living_counts=living)
    rep1 = evaluate_collection_planning_catalog(targets, living, edges, [opt], obs_empty)
    ev1 = rep1.evaluated_options[0]
    assert not ev1.is_ready
    assert ev1.has_blocker(BlockerReason.SOURCE_REACHABILITY_UNKNOWN)
    assert ev1.has_blocker(BlockerReason.RESOURCE_UNKNOWN)

    # 2. Source known unreachable, resource known but insufficient
    obs_unreach = PlanningObservation(
        living_counts=living,
        known_unreachable_sources=frozenset({"area:cave"}),
        available_resources={"ball:ultra": 1},
    )
    rep2 = evaluate_collection_planning_catalog(targets, living, edges, [opt], obs_unreach)
    ev2 = rep2.evaluated_options[0]
    assert not ev2.is_ready
    assert ev2.has_blocker(BlockerReason.SOURCE_UNREACHABLE)
    assert ev2.has_blocker(BlockerReason.RESOURCE_INSUFFICIENT)

    # 3. Source reachable, resource sufficient -> READY
    obs_ready = PlanningObservation(
        living_counts=living,
        reachable_sources=frozenset({"area:cave"}),
        available_resources={"ball:ultra": 2},
    )
    rep3 = evaluate_collection_planning_catalog(targets, living, edges, [opt], obs_ready)
    ev3 = rep3.evaluated_options[0]
    assert ev3.is_ready
    assert ev3.blockers == ()


# ---------------------------------------------------------------------------
# 2. Precursor Preservation & Surplus Evolution
# ---------------------------------------------------------------------------

def test_preserve_retained_precursor_vs_surplus_copy():
    """A single held precursor cannot be consumed; surplus copy can be consumed."""
    targets = ("P1", "P2")
    edges = (("P1", "P2"),)
    opt_catch_p1 = _make_capture_option("catch_p1", "P1", source="grass")
    opt_evolve = _make_evolution_option("evolve_p1", "P1", "P2", source="menu")

    obs = PlanningObservation(
        living_counts={"P1": 1, "P2": 0},
        reachable_sources=frozenset({"grass", "menu"}),
    )

    # State 1: 1 P1 held, 0 P2 held.
    rep1 = evaluate_collection_planning_catalog(
        targets, {"P1": 1, "P2": 0}, edges, [opt_catch_p1, opt_evolve], obs
    )
    eval_catch_1 = next(e for e in rep1.evaluated_options if e.option.option_id == "catch_p1")
    eval_evolve_1 = next(e for e in rep1.evaluated_options if e.option.option_id == "evolve_p1")

    assert eval_catch_1.is_ready
    assert eval_catch_1.marginal_useful_count == 1
    assert not eval_evolve_1.is_ready
    assert eval_evolve_1.has_blocker(BlockerReason.PRECURSOR_LAST_RETAINED)

    # State 2: 2 P1 held, 0 P2 held.
    obs2 = PlanningObservation(
        living_counts={"P1": 2, "P2": 0},
        reachable_sources=frozenset({"grass", "menu"}),
    )
    rep2 = evaluate_collection_planning_catalog(
        targets, {"P1": 2, "P2": 0}, edges, [opt_catch_p1, opt_evolve], obs2
    )
    eval_catch_2 = next(e for e in rep2.evaluated_options if e.option.option_id == "catch_p1")
    eval_evolve_2 = next(e for e in rep2.evaluated_options if e.option.option_id == "evolve_p1")

    assert not eval_catch_2.is_ready
    assert eval_catch_2.has_blocker(BlockerReason.NO_REMAINING_DEMAND)
    assert eval_catch_2.marginal_useful_count == 0

    assert eval_evolve_2.is_ready
    assert eval_evolve_2.blockers == ()


def test_chain_evolution_preserves_last_required_intermediate():
    """A -> B -> C chain preserves intermediate B when only one B is held."""
    targets = ("A", "B", "C")
    edges = (("A", "B"), ("B", "C"))
    opt_ab = _make_evolution_option("evolve_a_b", "A", "B", source="menu")
    opt_bc = _make_evolution_option("evolve_b_c", "B", "C", source="menu")

    # 1 A, 1 B, 0 C: B is required living target, cannot consume the only B
    counts_1 = {"A": 1, "B": 1, "C": 0}
    obs_1 = PlanningObservation(living_counts=counts_1, reachable_sources=frozenset({"menu"}))
    rep_1 = evaluate_collection_planning_catalog(
        targets, counts_1, edges, [opt_ab, opt_bc], obs_1
    )
    ev_bc_1 = next(e for e in rep_1.evaluated_options if e.option.option_id == "evolve_b_c")
    ev_ab_1 = next(e for e in rep_1.evaluated_options if e.option.option_id == "evolve_a_b")

    assert not ev_bc_1.is_ready
    assert ev_bc_1.has_blocker(BlockerReason.PRECURSOR_LAST_RETAINED)
    assert not ev_ab_1.is_ready
    assert ev_ab_1.has_blocker(BlockerReason.PRECURSOR_LAST_RETAINED)

    # 2 A, 1 B, 0 C: surplus A can evolve to B
    counts_2 = {"A": 2, "B": 1, "C": 0}
    obs_2 = PlanningObservation(living_counts=counts_2, reachable_sources=frozenset({"menu"}))
    rep_2 = evaluate_collection_planning_catalog(
        targets, counts_2, edges, [opt_ab, opt_bc], obs_2
    )
    ev_ab_2 = next(e for e in rep_2.evaluated_options if e.option.option_id == "evolve_a_b")
    assert ev_ab_2.is_ready

    # After A -> B evolves: counts become 1 A, 2 B, 0 C -> now surplus B can evolve to C!
    counts_3 = {"A": 1, "B": 2, "C": 0}
    obs_3 = PlanningObservation(living_counts=counts_3, reachable_sources=frozenset({"menu"}))
    rep_3 = evaluate_collection_planning_catalog(
        targets, counts_3, edges, [opt_ab, opt_bc], obs_3
    )
    ev_bc_3 = next(e for e in rep_3.evaluated_options if e.option.option_id == "evolve_b_c")
    assert ev_bc_3.is_ready


def test_non_target_precursor_does_not_need_retention():
    """If precursor is not in target_species, even a single copy can be consumed."""
    targets = ("FINAL",)
    edges = (("BASE", "FINAL"),)
    opt = _make_evolution_option("evolve_base", "BASE", "FINAL", source="menu")
    obs = PlanningObservation(
        living_counts={"BASE": 1, "FINAL": 0},
        reachable_sources=frozenset({"menu"}),
    )

    rep = evaluate_collection_planning_catalog(
        targets, {"BASE": 1, "FINAL": 0}, edges, [opt], obs
    )
    ev = rep.evaluated_options[0]
    assert ev.is_ready
    assert ev.blockers == ()


# ---------------------------------------------------------------------------
# 3. Branching Evolution Alternatives & Recomputed Demand
# ---------------------------------------------------------------------------

def test_branching_evolution_alternatives_recompute_after_shared_surplus_spent():
    """Branching alternatives are evaluated independently; spending surplus blocks the other."""
    targets = ("ROOT", "BRANCH_A", "BRANCH_B")
    edges = (("ROOT", "BRANCH_A"), ("ROOT", "BRANCH_B"))

    opt_catch = _make_capture_option("catch_root", "ROOT", source="gift")
    opt_a = _make_evolution_option("evolve_a", "ROOT", "BRANCH_A", source="stone_shop")
    opt_b = _make_evolution_option("evolve_b", "ROOT", "BRANCH_B", source="stone_shop")

    # Start: ROOT: 1, BRANCH_A: 0, BRANCH_B: 0
    obs1 = PlanningObservation(
        living_counts={"ROOT": 1, "BRANCH_A": 0, "BRANCH_B": 0},
        reachable_sources=frozenset({"gift", "stone_shop"}),
    )
    rep1 = evaluate_collection_planning_catalog(
        targets, {"ROOT": 1, "BRANCH_A": 0, "BRANCH_B": 0}, edges, [opt_catch, opt_a, opt_b], obs1
    )
    ev_catch1 = next(e for e in rep1.evaluated_options if e.option.option_id == "catch_root")
    ev_a1 = next(e for e in rep1.evaluated_options if e.option.option_id == "evolve_a")
    ev_b1 = next(e for e in rep1.evaluated_options if e.option.option_id == "evolve_b")

    assert not ev_a1.is_ready
    assert ev_a1.has_blocker(BlockerReason.PRECURSOR_LAST_RETAINED)
    assert not ev_b1.is_ready
    assert ev_b1.has_blocker(BlockerReason.PRECURSOR_LAST_RETAINED)
    assert ev_catch1.is_ready
    assert ev_catch1.marginal_useful_count == 2

    # 1 more ROOT acquired -> counts: ROOT: 2
    obs2 = PlanningObservation(
        living_counts={"ROOT": 2, "BRANCH_A": 0, "BRANCH_B": 0},
        reachable_sources=frozenset({"gift", "stone_shop"}),
    )
    rep2 = evaluate_collection_planning_catalog(
        targets, {"ROOT": 2, "BRANCH_A": 0, "BRANCH_B": 0}, edges, [opt_catch, opt_a, opt_b], obs2
    )
    ev_a2 = next(e for e in rep2.evaluated_options if e.option.option_id == "evolve_a")
    ev_b2 = next(e for e in rep2.evaluated_options if e.option.option_id == "evolve_b")

    # Both options are READY as alternative choices
    assert ev_a2.is_ready
    assert ev_b2.is_ready

    # Branch A chosen and evolved -> counts: ROOT: 1, BRANCH_A: 1, BRANCH_B: 0
    obs3 = PlanningObservation(
        living_counts={"ROOT": 1, "BRANCH_A": 1, "BRANCH_B": 0},
        reachable_sources=frozenset({"gift", "stone_shop"}),
    )
    rep3 = evaluate_collection_planning_catalog(
        targets, {"ROOT": 1, "BRANCH_A": 1, "BRANCH_B": 0}, edges, [opt_catch, opt_a, opt_b], obs3
    )
    ev_a3 = next(e for e in rep3.evaluated_options if e.option.option_id == "evolve_a")
    ev_b3 = next(e for e in rep3.evaluated_options if e.option.option_id == "evolve_b")

    assert not ev_a3.is_ready
    assert ev_a3.has_blocker(BlockerReason.NO_REMAINING_DEMAND)
    # Branch B is blocked again because surplus ROOT was consumed
    assert not ev_b3.is_ready
    assert ev_b3.has_blocker(BlockerReason.PRECURSOR_LAST_RETAINED)


# ---------------------------------------------------------------------------
# 4. Executor Status & Qualification
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status,expected_blocker", [
    (ExecutorStatus.QUALIFIED, None),
    (ExecutorStatus.UNQUALIFIED, BlockerReason.EXECUTOR_UNQUALIFIED),
    (ExecutorStatus.UNIMPLEMENTED, BlockerReason.EXECUTOR_UNIMPLEMENTED),
])
def test_executor_qualification_distinguishes_executable_capability(status, expected_blocker):
    """Catalog distinguishes hypothetical methods from qualified runtime capabilities."""
    targets = ("M",)
    living = {"M": 0}
    opt = _make_capture_option("catch_m", "M", source="grass", executor_status=status)
    obs = PlanningObservation(living_counts=living, reachable_sources=frozenset({"grass"}))

    rep = evaluate_collection_planning_catalog(targets, living, (), [opt], obs)
    ev = rep.evaluated_options[0]

    if expected_blocker is None:
        assert ev.is_ready
        assert ev.blockers == ()
    else:
        assert not ev.is_ready
        assert ev.has_blocker(expected_blocker)


# ---------------------------------------------------------------------------
# 5. One-time, Version, Link-Trade, and Event Blockers
# ---------------------------------------------------------------------------

def test_one_time_consumed_option_static_and_observation_paths():
    """One-time consumed option is blocked via both static flag and observation set."""
    targets = ("STATIC",)
    living = {"STATIC": 0}

    # Static flag path
    opt_static = _make_capture_option(
        "snorlax_1", "STATIC", source="route12", is_one_time=True, is_consumed=True
    )
    obs1 = PlanningObservation(living_counts=living, reachable_sources=frozenset({"route12"}))
    rep1 = evaluate_collection_planning_catalog(targets, living, (), [opt_static], obs1)
    assert not rep1.evaluated_options[0].is_ready
    assert rep1.evaluated_options[0].has_blocker(BlockerReason.ONE_TIME_CONSUMED)

    # Observation set path
    opt_obs = _make_capture_option(
        "snorlax_2", "STATIC", source="route12", is_one_time=True, is_consumed=False
    )
    obs2 = PlanningObservation(
        living_counts=living,
        reachable_sources=frozenset({"route12"}),
        consumed_options=frozenset({"snorlax_2"}),
    )
    rep2 = evaluate_collection_planning_catalog(targets, living, (), [opt_obs], obs2)
    assert not rep2.evaluated_options[0].is_ready
    assert rep2.evaluated_options[0].has_blocker(BlockerReason.ONE_TIME_CONSUMED)


def test_rejects_contradictory_consumption_declarations():
    """Repeatable options cannot be marked consumed statically or via observation."""
    with pytest.raises(ValueError, match="repeatable option .* cannot be marked is_consumed=True"):
        CandidateOption(
            option_id="repeatable_bad",
            target_species="A",
            method_kind=AcquisitionMethodKind.WILD_ENCOUNTER,
            source_id="grass",
            executor_status=ExecutorStatus.QUALIFIED,
            is_one_time=False,
            is_consumed=True,
        )

    opt_repeatable = _make_capture_option("repeatable_obs_bad", "A", is_one_time=False)
    obs = PlanningObservation(
        living_counts={"A": 0},
        consumed_options=frozenset({"repeatable_obs_bad"}),
    )
    with pytest.raises(ValueError, match="repeatable option .* cannot be marked consumed"):
        evaluate_collection_planning_catalog(("A",), {"A": 0}, (), [opt_repeatable], obs)


@pytest.mark.parametrize("flag_name,blocker", [
    ("is_version_blocked", BlockerReason.VERSION_EXCLUSIVE_BLOCKED),
    ("is_trade_blocked", BlockerReason.LINK_TRADE_BLOCKED),
    ("is_event_blocked", BlockerReason.EVENT_BLOCKED),
])
def test_explicit_environmental_blockers(flag_name, blocker):
    targets = ("T",)
    living = {"T": 0}
    kwargs = {flag_name: True}
    opt = _make_capture_option("opt_t", "T", source="grass", **kwargs)
    obs = PlanningObservation(living_counts=living, reachable_sources=frozenset({"grass"}))

    rep = evaluate_collection_planning_catalog(targets, living, (), [opt], obs)
    ev = rep.evaluated_options[0]
    assert not ev.is_ready
    assert ev.has_blocker(blocker)


# ---------------------------------------------------------------------------
# 6. Registered-Only Ownership vs Living Specimen
# ---------------------------------------------------------------------------

def test_registered_but_not_living_tracks_flags_without_satisfying_living_target():
    """Registered targets physically absent appear in registered_but_not_living."""
    targets = ("LIVING_TARGET",)
    living = {"LIVING_TARGET": 0}
    opt = _make_capture_option("catch_it", "LIVING_TARGET", source="grass")

    obs_registered = PlanningObservation(
        living_counts=living,
        reachable_sources=frozenset({"grass"}),
        registered_species=frozenset({"LIVING_TARGET"}),
    )

    rep1 = evaluate_collection_planning_catalog(targets, living, (), [opt], obs_registered)
    assert rep1.registered_but_not_living == ("LIVING_TARGET",)
    assert "LIVING_TARGET" in rep1.missing_living_targets
    assert rep1.marginal_useful_counts["LIVING_TARGET"] == 1
    assert rep1.evaluated_options[0].is_ready

    # When not registered, registered_but_not_living becomes empty while living demand is identical
    obs_unregistered = PlanningObservation(
        living_counts=living,
        reachable_sources=frozenset({"grass"}),
        registered_species=frozenset(),
    )
    rep2 = evaluate_collection_planning_catalog(targets, living, (), [opt], obs_unregistered)
    assert rep2.registered_but_not_living == ()
    assert "LIVING_TARGET" in rep2.missing_living_targets
    assert rep2.marginal_useful_counts["LIVING_TARGET"] == 1
    assert rep2.evaluated_options[0].is_ready


# ---------------------------------------------------------------------------
# 7. Multiple Resources & Partial Sufficiency
# ---------------------------------------------------------------------------

def test_multiple_resources_reports_exact_insufficient_or_unknown():
    """Multiple resources report exact blocker reasons when only one is satisfied."""
    targets = ("R",)
    living = {"R": 0}
    opt = _make_capture_option(
        "catch_r",
        "R",
        source="grass",
        resource_requirements=(
            ResourceRequirement("ball", 5),
            ResourceRequirement("money", 200),
        ),
    )

    # Ball sufficient (5 >= 5), money insufficient (100 < 200)
    obs_insufficient = PlanningObservation(
        living_counts=living,
        reachable_sources=frozenset({"grass"}),
        available_resources={"ball": 5, "money": 100},
    )
    rep1 = evaluate_collection_planning_catalog(targets, living, (), [opt], obs_insufficient)
    ev1 = rep1.evaluated_options[0]
    assert not ev1.is_ready
    assert ev1.blocker_reasons == (BlockerReason.RESOURCE_INSUFFICIENT,)
    assert "money" in ev1.blockers[0].detail
    assert "ball" not in ev1.blockers[0].detail

    # Ball sufficient (5 >= 5), money unobserved / unknown
    obs_unknown = PlanningObservation(
        living_counts=living,
        reachable_sources=frozenset({"grass"}),
        available_resources={"ball": 5},
    )
    rep2 = evaluate_collection_planning_catalog(targets, living, (), [opt], obs_unknown)
    ev2 = rep2.evaluated_options[0]
    assert not ev2.is_ready
    assert ev2.blocker_reasons == (BlockerReason.RESOURCE_UNKNOWN,)
    assert "money" in ev2.blockers[0].detail


# ---------------------------------------------------------------------------
# 8. Defensive Copying & Immutability
# ---------------------------------------------------------------------------

def test_defensive_copying_and_frozen_mapping_immutability():
    """PlanningObservation mappings are defensively copied and reject direct mutation."""
    raw_living = {"A": 0}
    raw_resources = {"ball": 0}

    obs = PlanningObservation(
        living_counts=raw_living,
        available_resources=raw_resources,
        reachable_sources=frozenset({"grass"}),
    )

    # External alias mutation must NOT affect the observation
    raw_resources["ball"] = 999
    raw_living["A"] = 999
    assert obs.available_resources["ball"] == 0
    assert obs.living_counts["A"] == 0

    # Direct item assignment on snapshot mappings must raise TypeError (MappingProxyType)
    with pytest.raises(TypeError):
        obs.available_resources["ball"] = 1  # type: ignore[index]

    with pytest.raises(TypeError):
        obs.living_counts["A"] = 1  # type: ignore[index]

    # Report marginal counts must also be read-only
    opt = _make_capture_option("opt_a", "A", source="grass")
    rep = evaluate_collection_planning_catalog(("A",), {"A": 0}, (), [opt], obs)
    with pytest.raises(TypeError):
        rep.marginal_useful_counts["A"] = 5  # type: ignore[index]


# ---------------------------------------------------------------------------
# 9. Transformation Edge Validation & living_counts Consistency
# ---------------------------------------------------------------------------

def test_transformation_option_requires_declared_edge():
    """Transformation options must have their (consumes, target) edge in transformation_edges."""
    targets = ("A", "B")
    living = {"A": 2, "B": 0}
    opt = _make_evolution_option("evolve_ab", "A", "B", source="menu")
    obs = PlanningObservation(living_counts=living, reachable_sources=frozenset({"menu"}))

    # Empty edges tuple -> must reject undeclared transformation
    with pytest.raises(ValueError, match="not present in declared transformation_edges"):
        evaluate_collection_planning_catalog(targets, living, (), [opt], obs)

    # Matching edge -> valid
    rep = evaluate_collection_planning_catalog(targets, living, (("A", "B"),), [opt], obs)
    assert rep.evaluated_options[0].is_ready


def test_rejects_mismatched_living_counts_and_observation():
    """Mismatches between living_counts and observation.living_counts raise ValueError."""
    targets = ("A", "B")
    edges = (("A", "B"),)
    opt = _make_evolution_option("evolve_ab", "A", "B", source="menu")

    obs = PlanningObservation(
        living_counts={"A": 1, "B": 0},
        reachable_sources=frozenset({"menu"}),
    )

    # External living_counts says A: 2, but observation says A: 1 -> must reject
    with pytest.raises(ValueError, match="mismatch between living_counts and observation"):
        evaluate_collection_planning_catalog(
            targets, {"A": 2, "B": 0}, edges, [opt], obs
        )

    # Missing species key vs explicit 0 normalizes without mismatch
    obs_zero = PlanningObservation(living_counts={"A": 1, "B": 0})
    rep = evaluate_collection_planning_catalog(
        targets, {"A": 1}, edges, [opt], obs_zero
    )
    assert rep.missing_living_targets == ("B",)


def test_multiple_concurrent_blockers_reported_comprehensively():
    """An option blocked by reachability, resources, and executor reports all three."""
    targets = ("MULTI",)
    living = {"MULTI": 0}
    opt = _make_capture_option(
        "catch_multi",
        "MULTI",
        source="unreachable_mountain",
        executor_status=ExecutorStatus.UNIMPLEMENTED,
        resource_requirements=(ResourceRequirement("key_item", 1),),
    )
    obs = PlanningObservation(
        living_counts=living,
        known_unreachable_sources=frozenset({"unreachable_mountain"}),
        available_resources={},  # key_item unknown
    )

    rep = evaluate_collection_planning_catalog(targets, living, (), [opt], obs)
    ev = rep.evaluated_options[0]
    assert not ev.is_ready
    assert set(ev.blocker_reasons) == {
        BlockerReason.SOURCE_UNREACHABLE,
        BlockerReason.RESOURCE_UNKNOWN,
        BlockerReason.EXECUTOR_UNIMPLEMENTED,
    }


def test_unsupported_targets_identified_when_no_options_declared():
    """Missing living targets with zero declared options appear in unsupported_targets."""
    targets = ("SUPPORTED", "ORPHAN")
    living = {"SUPPORTED": 0, "ORPHAN": 0}
    opt = _make_capture_option("catch_sup", "SUPPORTED", source="grass")
    obs = PlanningObservation(living_counts=living, reachable_sources=frozenset({"grass"}))

    rep = evaluate_collection_planning_catalog(targets, living, (), [opt], obs)
    assert rep.missing_living_targets == ("SUPPORTED", "ORPHAN")
    assert rep.unsupported_targets == ("ORPHAN",)


def test_permutation_invariance_and_deterministic_display_order():
    """Evaluated options must be deterministically sorted and order-invariant."""
    targets = ("SPECIES_B", "SPECIES_A")
    living = {"SPECIES_A": 0, "SPECIES_B": 0}
    opt_b2 = _make_capture_option("b_opt_2", "SPECIES_B", source="grass")
    opt_b1 = _make_capture_option("b_opt_1", "SPECIES_B", source="grass")
    opt_a = _make_capture_option("a_opt", "SPECIES_A", source="grass")

    obs = PlanningObservation(living_counts=living, reachable_sources=frozenset({"grass"}))

    # Pass in shuffled order
    rep1 = evaluate_collection_planning_catalog(
        targets, living, (), [opt_b2, opt_a, opt_b1], obs
    )
    rep2 = evaluate_collection_planning_catalog(
        tuple(reversed(targets)), living, (), [opt_a, opt_b1, opt_b2], obs
    )

    ids1 = [e.option.option_id for e in rep1.evaluated_options]
    ids2 = [e.option.option_id for e in rep2.evaluated_options]

    # Deterministic order: target_species first, then option_id
    expected_order = ["a_opt", "b_opt_1", "b_opt_2"]
    assert ids1 == expected_order
    assert ids2 == expected_order

# Original draft coverage retained through the revision.

def test_branching_evolution_alternatives_are_independent_options():
    """Branching evolutions (Eevee -> Vaporeon / Jolteon) are evaluated independently."""
    targets = ("ROOT", "BRANCH_A", "BRANCH_B")
    edges = (("ROOT", "BRANCH_A"), ("ROOT", "BRANCH_B"))

    opt_catch = _make_capture_option("catch_root", "ROOT", source="gift")
    opt_a = _make_evolution_option("evolve_a", "ROOT", "BRANCH_A", source="stone_shop")
    opt_b = _make_evolution_option("evolve_b", "ROOT", "BRANCH_B", source="stone_shop")

    # Start: ROOT: 1, BRANCH_A: 0, BRANCH_B: 0
    obs1 = PlanningObservation(
        living_counts={"ROOT": 1, "BRANCH_A": 0, "BRANCH_B": 0},
        reachable_sources=frozenset({"gift", "stone_shop"}),
    )
    rep1 = evaluate_collection_planning_catalog(
        targets, {"ROOT": 1, "BRANCH_A": 0, "BRANCH_B": 0}, edges, [opt_catch, opt_a, opt_b], obs1
    )
    ev_catch1 = next(e for e in rep1.evaluated_options if e.option.option_id == "catch_root")
    ev_a1 = next(e for e in rep1.evaluated_options if e.option.option_id == "evolve_a")
    ev_b1 = next(e for e in rep1.evaluated_options if e.option.option_id == "evolve_b")

    # With only 1 ROOT, both branches are blocked by PRECURSOR_LAST_RETAINED
    assert not ev_a1.is_ready
    assert ev_a1.has_blocker(BlockerReason.PRECURSOR_LAST_RETAINED)
    assert not ev_b1.is_ready
    assert ev_b1.has_blocker(BlockerReason.PRECURSOR_LAST_RETAINED)
    # ROOT marginal demand is 2 (need 2 more to satisfy both branches)
    assert ev_catch1.is_ready
    assert ev_catch1.marginal_useful_count == 2

    # Advance state: 1 more ROOT acquired -> counts: ROOT: 2
    obs2 = PlanningObservation(
        living_counts={"ROOT": 2, "BRANCH_A": 0, "BRANCH_B": 0},
        reachable_sources=frozenset({"gift", "stone_shop"}),
    )
    rep2 = evaluate_collection_planning_catalog(
        targets, {"ROOT": 2, "BRANCH_A": 0, "BRANCH_B": 0}, edges, [opt_catch, opt_a, opt_b], obs2
    )
    ev_a2 = next(e for e in rep2.evaluated_options if e.option.option_id == "evolve_a")
    ev_b2 = next(e for e in rep2.evaluated_options if e.option.option_id == "evolve_b")

    # Both options are READY as alternative choices (neither assumes the other ran)
    assert ev_a2.is_ready
    assert ev_b2.is_ready

    # Advance state: Branch A evolved -> counts: ROOT: 1, BRANCH_A: 1, BRANCH_B: 0
    obs3 = PlanningObservation(
        living_counts={"ROOT": 1, "BRANCH_A": 1, "BRANCH_B": 0},
        reachable_sources=frozenset({"gift", "stone_shop"}),
    )
    rep3 = evaluate_collection_planning_catalog(
        targets, {"ROOT": 1, "BRANCH_A": 1, "BRANCH_B": 0}, edges, [opt_catch, opt_a, opt_b], obs3
    )
    ev_a3 = next(e for e in rep3.evaluated_options if e.option.option_id == "evolve_a")
    ev_b3 = next(e for e in rep3.evaluated_options if e.option.option_id == "evolve_b")

    # Branch A is satisfied (NO_REMAINING_DEMAND)
    assert not ev_a3.is_ready
    assert ev_a3.has_blocker(BlockerReason.NO_REMAINING_DEMAND)
    # Branch B is blocked again because surplus ROOT was spent on A!
    assert not ev_b3.is_ready
    assert ev_b3.has_blocker(BlockerReason.PRECURSOR_LAST_RETAINED)


@pytest.mark.parametrize("invalid_counts", [
    {"A": -1},
    {"A": 1.5},
    {"A": True},
    {"": 1},
    {"   ": 2},
])
def test_rejects_malformed_specimen_counts(invalid_counts):
    targets = ("A",)
    obs = PlanningObservation(living_counts={"A": 0})
    with pytest.raises((ValueError, TypeError)):
        evaluate_collection_planning_catalog(targets, invalid_counts, (), [], obs)


def test_rejects_duplicate_option_ids():
    targets = ("A",)
    living = {"A": 0}
    opt1 = _make_capture_option("opt_dup", "A", source="grass")
    opt2 = _make_capture_option("opt_dup", "A", source="water")
    obs = PlanningObservation(living_counts=living)

    with pytest.raises(ValueError, match="duplicate option_id"):
        evaluate_collection_planning_catalog(targets, living, (), [opt1, opt2], obs)


def test_rejects_conflicting_reachability():
    """A source cannot be declared both reachable and known unreachable."""
    with pytest.raises(ValueError, match="cannot be both reachable and unreachable"):
        PlanningObservation(
            living_counts={"A": 0},
            reachable_sources=frozenset({"grass"}),
            known_unreachable_sources=frozenset({"grass"}),
        )


@pytest.mark.parametrize("edges", [
    (("A", "A"),),  # Self-loop
    (("A", "B"), ("B", "A")),  # Cycle
    (("A", "B"), ("B", "C"), ("C", "A")),  # 3-cycle
])
def test_rejects_cyclic_transformation_graphs(edges):
    targets = ("A", "B")
    living = {"A": 0, "B": 0}
    obs = PlanningObservation(living_counts=living)

    with pytest.raises(ValueError):
        evaluate_collection_planning_catalog(targets, living, edges, [], obs)


def test_rejects_invalid_option_fields():
    with pytest.raises(ValueError, match="consumes_species cannot equal target_species"):
        CandidateOption(
            option_id="bad",
            target_species="SAME",
            method_kind=AcquisitionMethodKind.LEVEL_EVOLUTION,
            source_id="menu",
            executor_status=ExecutorStatus.QUALIFIED,
            consumes_species="SAME",
        )

    with pytest.raises(ValueError, match="requires consumes_species"):
        # Wild encounter cannot declare consumes_species
        CandidateOption(
            option_id="bad_wild",
            target_species="A",
            method_kind=AcquisitionMethodKind.WILD_ENCOUNTER,
            source_id="grass",
            executor_status=ExecutorStatus.QUALIFIED,
            consumes_species="B",
        )
