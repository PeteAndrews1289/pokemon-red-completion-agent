from copy import deepcopy
from dataclasses import fields, replace
from types import SimpleNamespace

import pytest
from test_bounded_player_episode import _Meter
from test_goal_manager_trajectory import _observer, _Reader
from test_goal_resource_quote import _quote, _quoted_question, _supply_model
from test_red_living_dex_causal_adapter import _store_and_registry

from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalDecisionOutcome,
    GoalFailureReason,
    GoalKind,
    GoalOpportunity,
)
from pokemon_red_completion.goal_manager_trajectory import GoalManagerTrajectoryObserver
from pokemon_red_completion.goal_search_memory import GoalSearchHistory
from pokemon_red_completion.living_dex_option_value import (
    LivingDexOutcomeStatus,
    upgrade_option_value_model_for_search_history,
)
from pokemon_red_completion.living_dex_player_exploration import (
    EXPLORATION_POLICY_ID,
    ExploringLivingDexGoalPolicy,
)
from pokemon_red_completion.red_player_training import TRAINING_EVENT, RedPlayerTrainingTrajectory
from pokemon_red_completion.red_player_training_dataset import load_red_player_training_episode
from pokemon_red_completion.red_player_training_plan import (
    TRAINING_PLAN_SCHEMA,
    RedPlayerTrainingPlan,
)
from pokemon_red_completion.trajectory import SparseEvent
from pokemon_red_completion.trajectory_io import EpisodeTrajectorySink


def _plan(model):
    return RedPlayerTrainingPlan(
        {
            "schema": TRAINING_PLAN_SCHEMA,
            "episode_id": "goal-episode-1",
            "partition": "train",
            "seed": 17,
            "decision_limit": 4,
            "root_lineage_id": "goal-root-1",
            "model_sha256": model.model_sha256,
            "behavior_policy_id": EXPLORATION_POLICY_ID,
            "economic_contract": "known-spend-and-excess-reserve-v1",
            "context_catalog_sha256": "2" * 64,
            "context_id": "3" * 64,
            "binding_manifest_sha256": "6" * 64,
            "state_sha256": "4" * 64,
            "envelope_sha256": "5" * 64,
            "profile_sha256": "7" * 64,
            "source_commit": "1" * 40,
            "catalog_source_commit": "1" * 40,
            "source_bundle_sha256": "8" * 64,
            "independent_evaluation": False,
            "historical_trial_retry": False,
            "episode_retry_after_input": False,
        }
    )


def _facts(question, *, registered=1, balls=10):
    return {
        "schema": "pokemon.red.goal-observation.v1",
        "collection": {
            "registered": registered,
            "registered_target": 100,
            "living": registered,
            "living_target": 100,
            "level_cap": 0,
            "level_cap_target": 100,
        },
        "story": {"completed": 2, "target": 10},
        "capture_item_count": balls,
        "recovery_item_count": 0,
        "free_storage_slots": 20,
        "situation": question.situation.policy_dict(),
    }


def _episode(
    tmp_path,
    *,
    status=GoalDecisionOutcome.SUCCEEDED,
    safety=False,
    zero=False,
    mutate=None,
    return_inputs=False,
    unsupported_restore=False,
    history=False,
):
    store, _ = _store_and_registry(tmp_path)
    base, recorder, _ = _observer()
    model = _supply_model()
    if history:
        model = upgrade_option_value_model_for_search_history(model)
    policy = ExploringLivingDexGoalPolicy(model, seed=17)
    plan = _plan(policy.model)
    store.publish_sealed_record(
        f"rp-plan-{plan.plan_sha256}", kind="red_player_training_plan", record=dict(plan.document)
    )
    writer = store.begin_episode("goal-episode-1")
    sink = EpisodeTrajectorySink(writer, "goal-episode-1", "pokemon.red", durable_writes=True)
    recorder.sink = sink
    recorder.delegate = SimpleNamespace(execute=lambda _: SimpleNamespace(frames=60, buttons=()))
    metadata = _Reader([], []).read_header()["metadata"]
    metadata.update(
        {
            key: plan.document[key]
            for key in (
                "source_commit",
                "source_bundle_sha256",
                "state_sha256",
                "envelope_sha256",
                "profile_sha256",
                "model_sha256",
            )
        }
    )
    metadata.update(
        {
            "player_training_plan": dict(plan.document),
            "player_training_plan_sha256": plan.plan_sha256,
            "teacher_queries": 0,
            "teacher_fallbacks": 0,
        }
    )
    sink.write_episode_header(metadata=metadata)
    counter = {"actions": 0, "frames": 0}
    source = _quoted_question(_quote())
    if history:
        source = replace(
            source,
            opportunities=tuple(
                replace(item, search_history=GoalSearchHistory(2, 1, 200, 6000))
                if item.kind is GoalKind.ACQUIRE_SPECIES
                else item
                for item in source.opportunities
            ),
        )
    if unsupported_restore:
        source = replace(
            source,
            opportunities=(
                *source.opportunities,
                GoalOpportunity(
                    "restore", GoalKind.RESTORE_TEAM, GoalAvailability.AVAILABLE, 0.1, 0.0
                ),
            ),
        )
    if safety:
        source = replace(source, situation=replace(source.situation, resource_pressure=0.99))
    facts = [_facts(source)]
    trajectory = RedPlayerTrainingTrajectory(
        **{
            item.name: getattr(base, item.name)
            for item in fields(GoalManagerTrajectoryObserver)
            if item.init and item.name != "sink"
        },
        sink=sink,
        displayed_authority=policy,
        training_plan_sha256=plan.plan_sha256,
        training_meter=_Meter(counter),
        observe_training=lambda: SimpleNamespace(public_dict=lambda: deepcopy(facts[0])),
    )
    question = trajectory.ordered_question(source.situation, source.opportunities)
    selected = policy.select(question)
    pending = trajectory.record_selection(
        question, selected.selected_index, behavior_policy=policy.selection_metadata()
    )
    # There is no target before execution.
    assert trajectory.pending_was_recorded and counter == {"actions": 0, "frames": 0}
    if not zero:
        recorder.execute({"kind": "bounded-specialist-work"})
        counter.update(actions=1, frames=60)
    facts[0] = _facts(question, registered=2, balls=9)
    reason = (
        None
        if status is GoalDecisionOutcome.SUCCEEDED
        else GoalFailureReason.EXTERNAL_INTERRUPTION
        if status is GoalDecisionOutcome.INTERRUPTED
        else GoalFailureReason.EXECUTION_BUDGET_EXHAUSTED
    )
    trajectory.record_outcome(pending, status=status, failure_reason=reason)
    sink.record_event(
        SparseEvent(
            "goal-episode-1:terminal",
            "goal-episode-1",
            recorder.next_step_index,
            "terminal",
            {"status": "complete"},
        )
    )
    sink.finalize()
    completed = writer.complete()
    if return_inputs:
        return store, plan, policy.model, completed
    if mutate is not None:
        # The mutation tests below use a reader proxy after genuine stream validation,
        # attacking semantic admission in addition to the private store's hash checks.
        original = store.open_episode("goal-episode-1")
        streams = {name: list(original.iter_stream(name)) for name in original.stream_names}
        mutate(streams)
        reader = SimpleNamespace(
            manifest_sha256=original.manifest_sha256,
            stream_names=original.stream_names,
            read_header=lambda: streams["episode"][0],
            iter_stream=lambda name: iter(streams[name]),
        )
        store = SimpleNamespace(
            open_episode=lambda _: reader, find_sealed_record=store.find_sealed_record
        )
    return load_red_player_training_episode(
        store,
        episode_id="goal-episode-1",
        expected_manifest_sha256=completed.manifest_sha256,
        plan=plan,
        behavior_model=policy.model,
    )


@pytest.mark.parametrize("status", list(GoalDecisionOutcome))
def test_native_choices_replay_and_keep_observed_success_failure_and_censor(tmp_path, status):
    dataset = _episode(tmp_path, status=status)
    assert len(dataset.examples) == 1
    row = dataset.examples[0]
    if status is GoalDecisionOutcome.INTERRUPTED:
        assert row.outcome.status is LivingDexOutcomeStatus.CENSORED
    else:
        assert row.outcome.verified_success is (status is GoalDecisionOutcome.SUCCEEDED)
        assert row.outcome.completion_gain == 0.01
        assert row.outcome.resource_cost == 0.1
        assert row.outcome.frame_cost == 0.0001
    assert all(p > 0 for p in row.behavior_probabilities)


def test_safety_choices_do_not_become_exploration_rows(tmp_path):
    dataset = _episode(tmp_path, safety=True)
    assert dataset.examples == () and dataset.excluded_nonexploratory == 1


def test_supported_menu_with_unsupported_option_survives_real_trajectory_admission(tmp_path):
    dataset = _episode(tmp_path, unsupported_restore=True)
    assert len(dataset.examples) == 1 and dataset.excluded_nonexploratory == 0
    assert len(dataset.examples[0].behavior_probabilities) == 2
    assert all(p > 0 for p in dataset.examples[0].behavior_probabilities)


def test_zero_input_is_retained_in_episode_but_not_used_for_fitting(tmp_path):
    dataset = _episode(tmp_path, zero=True)
    assert dataset.examples == () and dataset.excluded_zero_input == 1


@pytest.mark.parametrize(
    "field,value",
    [("plan_sha256", "b" * 64), ("option_indices", [9, 8]), ("actions", -1), ("maximum_frames", 1)],
)
def test_changed_outcome_bindings_are_rejected(tmp_path, field, value):
    def mutate(streams):
        event = next(row for row in streams["events"] if row["kind"] == TRAINING_EVENT)
        event["payload"][field] = value

    with pytest.raises(ValueError):
        _episode(tmp_path, mutate=mutate)


def test_invented_success_target_is_rejected(tmp_path):
    def mutate(streams):
        event = next(row for row in streams["events"] if row["kind"] == TRAINING_EVENT)
        event["payload"]["after"]["collection"]["registered"] = 50

    with pytest.raises(ValueError, match="target"):
        _episode(tmp_path, mutate=mutate)


def test_plan_is_immutable_and_not_an_evaluation(tmp_path):
    plan = _plan(_supply_model())
    with pytest.raises(TypeError):
        plan.document["partition"] = "development"
    with pytest.raises(ValueError):
        RedPlayerTrainingPlan({**plan.document, "partition": "development"})
