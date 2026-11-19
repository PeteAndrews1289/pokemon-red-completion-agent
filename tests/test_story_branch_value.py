"""Story-branch child: identity-free features, TRAIN-only fit, kind-level choice unchanged."""

from __future__ import annotations

import math
from dataclasses import replace
from types import SimpleNamespace as N

import pytest
from test_red_live_option_menu import _binding, _situation

from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalOpportunity,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_runtime import GoalBindingSet, GoalManagerRuntimeError
from pokemon_red_completion.living_dex_goal_policy import project_living_dex_goal_candidate
from pokemon_red_completion.player_option_story_unit import (
    OptionStoryUnit,
    StoryRouteQuote,
    planned_route_quote,
)
from pokemon_red_completion.recorded_branch_history import RecordedBranchHistory
from pokemon_red_completion.red_live_option_menu import (
    RedLiveOptionChoice,
    RedLiveOptionSelectionMode,
    build_red_live_option_set,
    supplemental_live_option,
)
from pokemon_red_completion.red_story_branch_value import (
    DEFAULT_STORY_BRANCH_UTILITY,
    FEATURE_WIDTH,
    STORY_BRANCH_FEATURE_NAMES,
    STORY_BRANCH_TARGET_NAMES,
    StoryBranchHead,
    StoryBranchRow,
    StoryBranchTracker,
    fit_story_branch_head,
    refine_story_branch,
    story_branch_features,
    story_branch_indices,
)
from pokemon_red_completion.resource_economy_observation import EconomySnapshot

CONT = STORY_BRANCH_FEATURE_NAMES.index("continues_previous_story_choice")
COST = STORY_BRANCH_FEATURE_NAMES.index("route.remaining_cost")
DONE = STORY_BRANCH_TARGET_NAMES.index("completed_quests")


def _story(ref, objective, quote=None, calls=None):
    return replace(_binding(GoalKind.ADVANCE_STORY, binding_ref=ref, calls=calls if calls is not None else []),
                   story_objective_ref=objective, story_approach_only=True,
                   story_unit=OptionStoryUnit("movement", True), story_route_quote=quote)


def _options(stories, *, restore=True):
    calls = []
    mask = GoalOpportunity("masked", GoalKind.EXPLORE, GoalAvailability.UNAVAILABLE,
                           unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET)
    first, *rest = stories
    ordinary_bindings = (first,) + ((_binding(GoalKind.RESTORE_TEAM, binding_ref="private:restore", calls=calls),) if restore else ())
    ordinary = GoalBindingSet(tuple(b.opportunity for b in ordinary_bindings) + (mask,), ordinary_bindings)
    supplements = []
    for extra in rest:
        question = GoalBindingSet((extra.opportunity, mask), (extra,)).question(_situation(resources=0.1))
        candidate = replace(project_living_dex_goal_candidate(question, 0, feature_version=16, binding_ref=extra.binding_ref),
                            story_unit=extra.story_unit)
        supplements.append(supplemental_live_option(extra, candidate))
    return build_red_live_option_set(
        situation=_situation(resources=0.1), binding_set=ordinary, supplements=tuple(supplements),
        model_feature_version=16, ordering_seed_sha256="a" * 64,
        economy_snapshot=EconomySnapshot(58, ()), target_cash=0)


def _parent(options, ref):
    at = next(i for i, b in enumerate(options.bindings) if b.binding_ref == ref)
    n = len(options.bindings)
    return RedLiveOptionChoice(options, at, RedLiveOptionSelectionMode.MODEL_EXPLORATION,
                               tuple(1.0 for _ in range(n)), tuple(float(i == at) for i in range(n)), 3, "b" * 64)


def _index(options, ref):
    return next(i for i, b in enumerate(options.bindings) if b.binding_ref == ref)


def _branch_menu():
    return _options([_story("s-erika", "obj-a", StoryRouteQuote(900.0, 4)),
                     _story("s-fuji", "obj-b", StoryRouteQuote(120.0, 1)),
                     _story("s-other", "obj-c")])


def test_route_quote_validation_and_binding_scope():
    for bad in (-1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            StoryRouteQuote(bad, 0)
    with pytest.raises(ValueError):
        StoryRouteQuote(1.0, -1)
    assert StoryRouteQuote(3, 2).remaining_cost == 3.0
    with pytest.raises(GoalManagerRuntimeError):
        replace(_binding(GoalKind.RESTORE_TEAM, binding_ref="r", calls=[]), story_route_quote=StoryRouteQuote(1.0, 0))
    with pytest.raises(GoalManagerRuntimeError):
        replace(_binding(GoalKind.ADVANCE_STORY, binding_ref="s", calls=[]), story_route_quote=StoryRouteQuote(1.0, 0))


def test_planned_route_quote_counts_map_changes_only():
    plan = N(cost=250, steps=[N(expected_map=1), N(expected_map=1), N(expected_map=2), N(expected_map=2), N(expected_map=3)])
    assert planned_route_quote(1, plan) == StoryRouteQuote(250.0, 2)
    assert planned_route_quote(9, N(cost=0, steps=[])) == StoryRouteQuote(0.0, 0)
    assert planned_route_quote(9, N(cost=248)) is None
    assert planned_route_quote(9, N(cost=None, steps=[])) is None


def test_tracker_counts_only_story_outcomes_and_remembers_previous_branch():
    t = StoryBranchTracker()
    t = t.after(kind=GoalKind.RESTORE_TEAM, objective_ref=None, actions=50, frames=900)
    assert t == StoryBranchTracker()
    t = t.after(kind=GoalKind.ADVANCE_STORY, objective_ref="obj-a", actions=40, frames=800, quest_gains=1)
    t = t.after(kind=GoalKind.ADVANCE_STORY, objective_ref="obj-a", actions=10, frames=100)
    t = t.after(kind=GoalKind.ADVANCE_STORY, objective_ref=None, actions=5, frames=5)
    assert t.previous_objective_ref == "obj-a"
    assert t.history("obj-a") == RecordedBranchHistory(2, 50, 900, 0, 0, 0, 1, 0)
    assert t.history("obj-b").attempts == 0 and t.unattributed_story_choices == 1
    with pytest.raises(ValueError):
        t.after(kind=GoalKind.ADVANCE_STORY, objective_ref="obj-a", actions=-1, frames=0)
    assert StoryBranchTracker(t.histories, t.previous_objective_ref, t.unattributed_story_choices).sha256 == t.sha256


def test_tracker_folds_recorded_outcomes():
    from pokemon_red_completion.red_story_branch_value import tracker_after_outcome
    story = _story("s-a", "obj-a")
    outcome = dict(observed_cost=dict(actions=70, frames=1400, cash_spent=-120),
                   before=dict(completed_objectives=["x"]), after=dict(completed_objectives=["x", "obj-a"]))
    t = tracker_after_outcome(StoryBranchTracker(), story, outcome)
    assert t.history("obj-a") == RecordedBranchHistory(1, 70, 1400, 0, 120, 0, 1, 0)
    heal = _binding(GoalKind.RESTORE_TEAM, binding_ref="h", calls=[])
    assert tracker_after_outcome(t, heal, outcome) == t
    assert tracker_after_outcome(t, story, dict(observed_cost=None, before={}, after={})).history("obj-a").attempts == 2


def test_features_are_bounded_identity_free_and_use_the_route_quote():
    options = _branch_menu()
    tracker = StoryBranchTracker().after(kind=GoalKind.ADVANCE_STORY, objective_ref="obj-b", actions=30, frames=600)
    rows = {b.binding_ref: story_branch_features(options.menu.candidates[i], b, tracker)
            for i, b in enumerate(options.bindings) if b.kind is GoalKind.ADVANCE_STORY}
    assert all(len(v) == FEATURE_WIDTH and all(-1 <= x <= 1 for x in v) for v in rows.values())
    assert rows["s-fuji"][CONT] == 1.0 and rows["s-erika"][CONT] == 0.0
    assert math.isclose(rows["s-erika"][COST], 900 / 1400) and math.isclose(rows["s-fuji"][COST], 120 / 620)
    assert rows["s-other"][:3] == (0.0, 0.0, 0.0)
    # Renaming a private objective (with the same history) cannot change features.
    i = _index(options, "s-erika")
    renamed = replace(options.bindings[i], story_objective_ref="obj-z")
    assert story_branch_features(options.menu.candidates[i], renamed, StoryBranchTracker()) == \
        story_branch_features(options.menu.candidates[i], options.bindings[i], StoryBranchTracker())


def test_not_a_branch_point_passes_through():
    options = _branch_menu()
    assert refine_story_branch(_parent(options, "private:restore"), head=None, tracker=StoryBranchTracker(), seed=1) is None
    single = _options([_story("s-one", "obj-a", StoryRouteQuote(10.0, 1)), _story("s-two", "obj-a")])
    assert story_branch_indices(_parent(single, "s-one")) == ()
    assert refine_story_branch(_parent(single, "s-one"), head=None, tracker=StoryBranchTracker(), seed=1) is None


def test_without_head_and_exploration_the_parent_choice_is_returned_verbatim():
    options = _branch_menu()
    parent = _parent(options, "s-erika")
    decision = refine_story_branch(parent, head=None, tracker=StoryBranchTracker(), seed=4)
    assert decision.selected_candidate_index == parent.selected_candidate_index and not decision.explored
    assert decision.choice() is parent


def test_train_exploration_records_exact_behaviour_probabilities():
    options = _branch_menu()
    parent = _parent(options, "s-erika")
    seen = set()
    for seed in range(40):
        d = refine_story_branch(parent, head=None, tracker=StoryBranchTracker(), exploration_probability=0.5, seed=seed)
        assert math.isclose(sum(d.probabilities), 1.0)
        assert math.isclose(d.probabilities[parent.selected_candidate_index], 0.5 + 0.5 / 3)
        assert all(d.probabilities[i] == 0.0 for i in range(len(options.bindings)) if i not in d.story_indices)
        c = d.choice()
        assert c.selected_binding.kind is GoalKind.ADVANCE_STORY and c.probabilities[c.selected_candidate_index] > 0
        seen.add(d.selected_candidate_index)
    assert seen == set(story_branch_indices(parent))


def _rows(n=40):
    rows = []
    for k in range(n):
        cont = float(k % 2)
        cost = (k % 5) / 5
        f = [0.0] * FEATURE_WIDTH
        f[0], f[COST], f[CONT] = 1.0, cost, cont
        targets = [None] * len(STORY_BRANCH_TARGET_NAMES)
        targets[DONE] = 0.5 * cont + 0.2 * (1 - cost)
        targets[STORY_BRANCH_TARGET_NAMES.index("actions")] = 0.3 + 0.2 * (1 - cont)
        rows.append(StoryBranchRow(f"{k:064x}", tuple(f), tuple(targets), "train"))
    return tuple(rows)


def test_fit_is_train_only_masked_and_roundtrips():
    rows = _rows()
    head = fit_story_branch_head(rows, ridge=0.25)
    assert head.sample_counts[DONE] == 40 and head.parameters[0] is None and head.utility[0] == 0.0
    assert head.utility[DONE] == DEFAULT_STORY_BRANCH_UTILITY[DONE]
    again = StoryBranchHead.from_document(head.document(), expected_sha256=head.model_sha256)
    assert again == head
    with pytest.raises(ValueError):
        fit_story_branch_head((replace(rows[0], partition="development"),) + rows[1:], ridge=0.25)
    one = tuple(replace(r, targets=tuple(None if i != DONE else (v if j == 0 else None) for i, v in enumerate(r.targets)))
                for j, r in enumerate(rows))
    with pytest.raises(ValueError):
        fit_story_branch_head(one, ridge=0.25)
    with pytest.raises(ValueError):
        StoryBranchHead(head.parameters, head.sample_counts, head.dataset_sha256, 0.25,
                        (1.0,) + head.utility[1:])  # utility on an unlearned channel


def test_learned_head_continues_the_closer_previous_branch_and_keeps_story_kind():
    head = fit_story_branch_head(_rows(), ridge=0.25)
    options = _branch_menu()
    parent = _parent(options, "s-erika")  # immediate model's near-tie pick
    tracker = StoryBranchTracker().after(kind=GoalKind.ADVANCE_STORY, objective_ref="obj-b", actions=30, frames=600)
    d = refine_story_branch(parent, head=head, tracker=tracker, seed=2)
    assert options.bindings[d.selected_candidate_index].binding_ref == "s-fuji"
    c = d.choice()
    assert c.selected_binding.kind is GoalKind.ADVANCE_STORY
    assert c.mode is RedLiveOptionSelectionMode.MODEL_EXPLORATION and c.model_sha256 == d.sha256
    assert d.document()["kind_level_choice_unchanged"] is True and d.head_sha256 == head.model_sha256


def test_segment_starts_with_exact_objective_probability_then_continues_deterministically():
    from pokemon_red_completion.red_story_branch_value import StoryBranchSegment
    options = _branch_menu()
    parent = _parent(options, "s-erika")
    d = refine_story_branch(parent, head=None, tracker=StoryBranchTracker(), exploration_probability=0.5, seed=11, segment_lengths=(3, 9))
    assert d.segment_started and type(d.segment) is StoryBranchSegment and 3 <= d.segment.length <= 9
    sel_obj = options.bindings[d.selected_candidate_index].story_objective_ref
    assert d.segment.objective_ref == sel_obj and d.segment.remaining == d.segment.length
    expected = d.probabilities[d.selected_candidate_index]
    assert math.isclose(d.segment.start_probability, expected)
    assert d.document()["segment"]["objective_ref"] == sel_obj
    # next decision: the parent prefers another objective; the segment keeps its own.
    other = next(b.binding_ref for b in options.bindings if b.kind is GoalKind.ADVANCE_STORY and b.story_objective_ref != sel_obj)
    c = refine_story_branch(_parent(options, other), head=None, tracker=StoryBranchTracker(), exploration_probability=0.5, seed=12,
                            segment=d.segment, segment_lengths=(3, 9))
    assert options.bindings[c.selected_candidate_index].story_objective_ref == sel_obj
    assert not c.segment_started and c.segment == d.segment and not c.explored
    assert c.probabilities[c.selected_candidate_index] == 1.0 and math.isclose(sum(c.probabilities), 1.0)
    assert c.choice().selected_binding.kind is GoalKind.ADVANCE_STORY


def test_segment_closes_on_completion_units_or_unavailability():
    from pokemon_red_completion.red_story_branch_value import StoryBranchSegment, segment_after_outcome
    seg = StoryBranchSegment("obj-a", 2, 2, 0.5, True, 1)
    story_a, story_b = _story("s-a", "obj-a"), _story("s-b", "obj-b")
    heal = _binding(GoalKind.RESTORE_TEAM, binding_ref="h", calls=[])
    plain = dict(after=dict(completed_objectives=["x"]))
    assert segment_after_outcome(seg, heal, plain) == seg
    assert segment_after_outcome(seg, story_b, plain) == seg
    one = segment_after_outcome(seg, story_a, plain)
    assert one.remaining == 1 and segment_after_outcome(one, story_a, plain) is None
    assert segment_after_outcome(seg, heal, dict(after=dict(completed_objectives=["obj-a"]))) is None
    assert segment_after_outcome(None, story_a, plain) is None
    # committed objective not offered -> a fresh segment starts
    options = _branch_menu()
    gone = StoryBranchSegment("obj-gone", 5, 5, 0.5, False, 2)
    d = refine_story_branch(_parent(options, "s-fuji"), head=None, tracker=StoryBranchTracker(), seed=3, segment=gone, segment_lengths=(2, 2))
    assert d.segment_started and d.segment.objective_ref == "obj-b" and d.segment.length == 2


def test_segment_arguments_are_validated():
    from pokemon_red_completion.red_story_branch_value import StoryBranchSegment
    options = _branch_menu(); parent = _parent(options, "s-erika")
    for bad in ((0, 3), (5, 2), (1, 201), [1, 3], (1.0, 3)):
        with pytest.raises(ValueError):
            refine_story_branch(parent, head=None, tracker=StoryBranchTracker(), seed=1, segment_lengths=bad)
    with pytest.raises(ValueError):
        refine_story_branch(parent, head=None, tracker=StoryBranchTracker(), seed=1, segment=StoryBranchSegment("obj-a", 2, 2, 0.5, True, 1))
    with pytest.raises(ValueError):
        StoryBranchSegment("obj-a", 2, 3, 0.5, True, 1)
    # without segment_lengths the decision is byte-identical to the plain child
    a = refine_story_branch(parent, head=None, tracker=StoryBranchTracker(), exploration_probability=0.5, seed=9)
    assert a.segment is None and "segment" not in a.document()


def test_milestone_commitment_keeps_the_objective_without_exploration():
    from pokemon_red_completion.red_story_branch_value import STORY_MILESTONE_UNITS, segment_after_outcome
    options = _branch_menu()
    lengths = (STORY_MILESTONE_UNITS, STORY_MILESTONE_UNITS)
    d = refine_story_branch(_parent(options, "s-fuji"), head=None, tracker=StoryBranchTracker(), seed=5, segment_lengths=lengths)
    assert d.segment_started and not d.explored and d.segment.start_probability == 1.0
    assert options.bindings[d.selected_candidate_index].story_objective_ref == "obj-b" == d.segment.objective_ref
    # the immediate model now prefers Erika; the milestone keeps Fuji
    c = refine_story_branch(_parent(options, "s-erika"), head=None, tracker=StoryBranchTracker(), seed=6, segment=d.segment, segment_lengths=lengths)
    assert options.bindings[c.selected_candidate_index].story_objective_ref == "obj-b"
    # completion closes the milestone; the next branch point follows the immediate model again
    assert segment_after_outcome(d.segment, _story("s-x", "obj-a"), dict(after=dict(completed_objectives=["obj-b"]))) is None
    e = refine_story_branch(_parent(options, "s-erika"), head=None, tracker=StoryBranchTracker(), seed=7, segment=None, segment_lengths=lengths)
    assert options.bindings[e.selected_candidate_index].story_objective_ref == "obj-a"


@pytest.mark.parametrize("kwargs", [dict(continuous_player=False), dict(continuous_player=True, story_branch_exploration=0.5),
                                    dict(continuous_player=True, story_branch_segment_lengths=(3, 9))])
def test_milestone_commitment_scope_is_validated(tmp_path, kwargs):
    from pokemon_red_completion.red_autonomous_player import run_autonomous_options
    with pytest.raises(ValueError, match="milestone story commitment|story-branch"):
        run_autonomous_options(model=N(feature_version=16), output=tmp_path / "out", snapshot=None, observe=None, seed=1,
                               provenance=dict(source=dict(partition="development")), story_milestone_commitment=True, **kwargs)
    assert not (tmp_path / "out").exists()


def test_exact_head_ties_keep_the_parent_selection():
    head = fit_story_branch_head(_rows(), ridge=0.25)
    options = _options([_story("s-x", "obj-a", StoryRouteQuote(100.0, 1)), _story("s-y", "obj-b", StoryRouteQuote(100.0, 1))])
    for ref in ("s-x", "s-y"):
        d = refine_story_branch(_parent(options, ref), head=head, tracker=StoryBranchTracker(), seed=0)
        assert options.bindings[d.selected_candidate_index].binding_ref == ref
