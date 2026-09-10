"""Executable ROM-free macro tests using the production sampler and recorders."""

from dataclasses import fields, replace
from types import SimpleNamespace

import pytest
from test_goal_manager_trajectory import _observer
from test_goal_resource_quote import _supply_model
from test_red_elixir_plan import finished, state
from test_red_forward_goal import Meter, champion_raw, declared, observation

from pokemon_red_completion.forward_goal import ForwardGoalTerminal
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalDecisionOutcome,
    GoalFailureReason,
    GoalKind,
    GoalOpportunity,
    GoalSelectionMode,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_trajectory import GoalManagerTrajectoryObserver
from pokemon_red_completion.living_dex_option_value import (
    upgrade_option_value_model_for_optional_recovery,
)
from pokemon_red_completion.living_dex_player_exploration import ExploringLivingDexGoalPolicy
from pokemon_red_completion.red_forward_goal import RedForwardGoalCollector
from pokemon_red_completion.red_forward_training import RedForwardTrainingTrajectory
from pokemon_red_completion.red_player_training import (
    CURRICULUM_EVENT,
    TRAINING_EVENT,
    RedPlayerTrainingTrajectory,
)


def opportunities(*, singleton=False, unsupported=False):
    return (
        GoalOpportunity("story", GoalKind.ADVANCE_STORY, GoalAvailability.AVAILABLE, 0.25, 0.2),
        *(
            (
                GoalOpportunity(
                    "resource",
                    GoalKind.RESTORE_TEAM,
                    GoalAvailability.UNAVAILABLE,
                    None,
                    None,
                    GoalUnavailableReason.MISSING_RESOURCE,
                ),
            )
            if singleton
            else (
                GoalOpportunity(
                    "resource",
                    GoalKind.ACQUIRE_SPECIES if unsupported else GoalKind.RESTORE_TEAM,
                    GoalAvailability.AVAILABLE,
                    0.1,
                    0.01,
                ),
            )
        ),
    )


def harness(*, forward=True, legacy_model=False, seed=17):
    base, executor, sink = _observer()
    meter = Meter()
    holder = [observation()]
    events = []
    model = _supply_model()
    if not legacy_model:
        model = upgrade_option_value_model_for_optional_recovery(model)
    policy = ExploringLivingDexGoalPolicy(model, seed=seed)
    collector = RedForwardGoalCollector(
        declared(),
        "defeat_champion",
        lambda: holder[0],
        meter,
        events.append,
    )
    common = {
        item.name: getattr(base, item.name)
        for item in fields(GoalManagerTrajectoryObserver)
        if item.init
    }
    common.update(
        displayed_authority=policy,
        training_plan_sha256="d" * 64,
        training_meter=meter,
        observe_training=lambda: holder[0],
        maximum_actions=100,
        maximum_frames=1000,
    )
    trajectory = (
        RedForwardTrainingTrajectory(**common, forward=collector)
        if forward
        else RedPlayerTrainingTrajectory(**common)
    )
    queued = []

    class MacroExecutor:
        def execute(self, action):
            assert len(sink.decisions) >= 1
            if forward:
                assert [event["kind"] for event in events[:2]] == [
                    "forward_goal_declaration",
                    "forward_goal_anchor",
                ]
            meter.spend(1, 60)
            if queued:
                holder[0] = queued.pop(0)
            return SimpleNamespace(frames=60, buttons=())

    executor.delegate = MacroExecutor()
    if forward:
        collector.prepare()
    return SimpleNamespace(
        trajectory=trajectory,
        collector=collector,
        policy=policy,
        executor=executor,
        sink=sink,
        meter=meter,
        holder=holder,
        events=events,
        queued=queued,
    )


def sampled(h, *, unsafe=False, unsupported=False):
    situation = h.holder[0].situation
    if unsafe:
        situation = replace(situation, safety_pressure=0.99, recovery_pressure=0.99)
    question = h.trajectory.ordered_question(situation, opportunities(unsupported=unsupported))
    selection = h.policy.select(question)
    pending = h.trajectory.record_selection(
        question,
        selection.selected_index,
        behavior_policy=h.policy.selection_metadata(),
    )
    return pending


def run_macro(h, pending, *, after=None, status=GoalDecisionOutcome.SUCCEEDED):
    if after is not None:
        h.queued.append(after)
    h.executor.execute({"kind": "bounded-specialist-work"})
    reason = (
        None
        if status is GoalDecisionOutcome.SUCCEEDED
        else GoalFailureReason.EXTERNAL_INTERRUPTION
        if status is GoalDecisionOutcome.INTERRUPTED
        else GoalFailureReason.EXECUTION_BUDGET_EXHAUSTED
    )
    return h.trajectory.record_outcome(pending, status=status, failure_reason=reason)


def training_records(h):
    return [event.to_dict() for event in h.sink.events if event.kind == TRAINING_EVENT]


def test_first_real_sample_is_durably_anchored_before_executable_macro():
    h = harness()
    before = h.meter.checkpoint()
    pending = sampled(h)
    assert h.policy.training_eligible is True and h.policy.decisions == 1
    assert h.meter.checkpoint() == before
    assert h.trajectory.pending_was_recorded is True
    anchor = h.events[1]["choice"]
    assert anchor["probabilities"] == list(h.policy.option_probabilities)
    assert len(anchor["candidates"]) == 2
    assert all(0 < p < 1 for p in anchor["probabilities"])
    assert h.policy.last_menu_indices[anchor["selected_index"]] == pending.selected_candidate_index
    assert not training_records(h)
    assert run_macro(h, pending)
    assert len(training_records(h)) == 1
    assert h.collector.outcome is None
    assert h.meter.actions - before.controller_actions == 1


def test_forced_story_continuation_finishes_forward_goal_without_second_anchor_or_label():
    h = harness(seed=1)
    first = sampled(h)
    assert (
        first.question.opportunities[first.selected_candidate_index].kind is GoalKind.RESTORE_TEAM
    )
    run_macro(h, first, after=observation(finished(state())))
    question = h.trajectory.ordered_question(h.holder[0].situation, opportunities(singleton=True))
    later = h.trajectory.record_selection(
        question,
        question.available_indices[0],
        selection_mode=GoalSelectionMode.FORCED_SINGLETON,
    )
    assert h.policy.decisions == 1  # No made-up singleton model query.
    assert run_macro(h, later, after=observation(finished(champion_raw())))
    assert h.collector.outcome.terminal is ForwardGoalTerminal.REACHED
    assert h.collector.outcome.target == pytest.approx((1.0, 0.13))
    assert h.collector.outcome.counters.macros == 2
    assert [event["kind"] for event in h.events].count("forward_goal_anchor") == 1
    assert len(h.sink.decisions) == 2
    assert len(training_records(h)) == 1
    assert not any(event.kind == CURRICULUM_EVENT for event in h.sink.events)


@pytest.mark.parametrize(
    "status",
    [GoalDecisionOutcome.SUCCEEDED, GoalDecisionOutcome.FAILED, GoalDecisionOutcome.INTERRUPTED],
)
def test_immediate_records_are_byte_for_byte_unchanged_from_parent(status):
    wrapped, legacy = harness(), harness(forward=False)
    left, right = sampled(wrapped), sampled(legacy)
    assert left == right
    after = observation(replace(state(), bag_items=((53, 3), (4, 2)), bag_item_ids=(53, 4)))
    run_macro(wrapped, left, after=after, status=status)
    run_macro(legacy, right, after=after, status=status)
    assert [record.to_dict() for record in wrapped.sink.decisions] == [
        record.to_dict() for record in legacy.sink.decisions
    ]
    assert [event.to_dict() for event in wrapped.sink.events] == [
        event.to_dict() for event in legacy.sink.events
    ]
    assert len(training_records(wrapped)) == 1


@pytest.mark.parametrize("bad_start", ["unsafe", "unsupported", "legacy", "forced"])
def test_ineligible_first_choice_rejects_before_input(bad_start):
    h = harness(legacy_model=bad_start == "legacy")
    before = h.meter.checkpoint()
    with pytest.raises(ValueError):
        if bad_start == "forced":
            question = h.trajectory.ordered_question(
                h.holder[0].situation, opportunities(singleton=True)
            )
            h.trajectory.record_selection(
                question,
                question.available_indices[0],
                selection_mode=GoalSelectionMode.FORCED_SINGLETON,
            )
        else:
            sampled(h, unsafe=bad_start == "unsafe", unsupported=bad_start == "unsupported")
    assert h.meter.checkpoint() == before
    assert len(h.events) == 1 and not h.sink.decisions


def test_interrupt_censors_both_streams_without_reading_unknown_state():
    h = harness()
    pending = sampled(h)
    h.executor.execute({"kind": "bounded-specialist-work"})

    def unreadable():
        raise AssertionError("unknown state must not be read after interruption")

    h.trajectory.observe_training = h.collector.observe = unreadable
    assert h.trajectory.record_outcome(
        pending,
        status=GoalDecisionOutcome.INTERRUPTED,
        failure_reason=GoalFailureReason.EXTERNAL_INTERRUPTION,
    )
    assert h.collector.outcome.terminal is ForwardGoalTerminal.INTERRUPTED
    assert h.collector.outcome.target is None
    record = training_records(h)[0]
    assert record["payload"]["example"]["outcome"]["status"] == "censored"


def test_terminal_collector_rejects_any_additional_choice_before_input():
    h = harness()
    pending = sampled(h)
    run_macro(h, pending, after=observation(champion_raw()))
    before = h.meter.checkpoint()
    question = h.trajectory.ordered_question(h.holder[0].situation, opportunities(singleton=True))
    with pytest.raises(ValueError, match="terminal"):
        h.trajectory.record_selection(
            question,
            question.available_indices[0],
            selection_mode=GoalSelectionMode.FORCED_SINGLETON,
        )
    assert len(h.sink.decisions) == 1 and h.meter.checkpoint() == before


@pytest.mark.parametrize("failed_observer", ["immediate", "forward"])
def test_observation_failure_preserves_already_durable_parent_outcome(failed_observer):
    h = harness()
    pending = sampled(h)
    h.executor.execute({"kind": "bounded-specialist-work"})
    error = OSError("unavailable observation")

    def unreadable():
        raise error

    if failed_observer == "immediate":
        h.trajectory.observe_training = unreadable
    else:
        h.collector.observe = unreadable
    with pytest.raises(OSError) as raised:
        h.trajectory.record_outcome(pending, status=GoalDecisionOutcome.SUCCEEDED)
    assert raised.value is error
    assert len(h.sink.decisions) == 1
    basic = [event for event in h.sink.events if event.kind != TRAINING_EVENT]
    assert len(basic) == 1 and basic[0].payload["status"] == "succeeded"
    assert len(training_records(h)) == (0 if failed_observer == "immediate" else 1)
    assert h.collector.outcome is None
    assert h.collector.finish(interrupted=True).target is None


def test_bad_behavior_metadata_never_creates_anchor_or_input():
    h = harness()
    question = h.trajectory.ordered_question(h.holder[0].situation, opportunities())
    selected = h.policy.select(question)
    metadata = h.policy.selection_metadata()
    metadata["selected_probability"] = 1.0
    before = h.meter.checkpoint()
    with pytest.raises(ValueError):
        h.trajectory.record_selection(question, selected.selected_index, behavior_policy=metadata)
    assert h.meter.checkpoint() == before and len(h.events) == 1


def test_stale_prepared_resource_snapshot_prevents_first_anchor_and_macro():
    h = harness()
    h.holder[0] = observation(replace(state(), player_money=1235))
    before = h.meter.checkpoint()
    with pytest.raises(ValueError, match="start changed"):
        sampled(h)
    assert h.meter.checkpoint() == before
    assert len(h.events) == 1 and h.collector.outcome is None
    assert len(h.sink.decisions) == 1  # Preserve attempted parent commitment before refusal.


def test_actionful_extra_anchor_observation_is_detected_before_forward_anchor():
    h = harness()
    reads = []

    def observe_training():
        reads.append(True)
        if len(reads) == 2:  # Parent's before snapshot is first; extra forward read is second.
            h.meter.spend(1, 1)
        return h.holder[0]

    h.trajectory.observe_training = observe_training
    with pytest.raises(ValueError, match="anchor observation attempted actions"):
        sampled(h)
    assert len(reads) == 2 and len(h.events) == 1
    assert len(h.sink.decisions) == 1 and not training_records(h)


def test_curriculum_contract_cannot_be_combined_with_forward_choice_recorder():
    from pokemon_red_completion.red_player_training_plan import STORY_CURRICULUM_CONTRACT

    h = harness()
    with pytest.raises(ValueError, match="singleton curriculum"):
        replace(h.trajectory, curriculum_contract=STORY_CURRICULUM_CONTRACT)
