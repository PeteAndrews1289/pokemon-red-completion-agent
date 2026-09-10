from dataclasses import fields, replace
from types import SimpleNamespace

import pytest
from test_bounded_player_episode import _Meter, _trajectory
from test_goal_resource_quote import _quote, _quoted_question, _supply_model
from test_paired_red_bounded_player_script import _observation
from test_red_player_training import _facts

from pokemon_red_completion.bounded_player_episode import (
    BoundedPlayerLimits,
    run_bounded_player_episode,
)
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import (
    CompletionFirstGoalTeacher,
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.goal_manager_trajectory import GoalManagerTrajectoryObserver
from pokemon_red_completion.living_dex_player_exploration import ExploringLivingDexGoalPolicy
from pokemon_red_completion.red_bounded_player import preflight_red_bounded_player
from pokemon_red_completion.red_goal_context import _ProfileBoundProvider
from pokemon_red_completion.red_goal_manager import RedGoalBindingOffer
from pokemon_red_completion.red_player_training import TRAINING_EVENT, RedPlayerTrainingTrajectory


@pytest.mark.parametrize("failure", [False, True])
def test_quoted_goal_passes_preflight_and_actual_player_to_native_outcome(failure):
    source = _quoted_question(_quote())
    base, sink = _trajectory()
    state = {"actions": 0, "frames": 0, "stage": 0}
    meter = _Meter(state)
    recorder = base.recorder
    recorder.delegate = SimpleNamespace(execute=lambda _: SimpleNamespace(frames=60, buttons=()))

    def execute():
        recorder.execute({"kind": "bounded-specialist-test"})
        state.update(actions=1, frames=60, stage=1)
        if failure:
            raise RuntimeError("injected failure after observed progress")
        return GoalExecutionReport(1, 60, {})

    bindings = tuple(
        ExecutableGoalBinding(
            item.binding_ref,
            item.kind,
            item.estimated_effort,
            item.estimated_risk,
            execute,
            lambda _: GoalVerification.succeeded(),
            resource_quote=item.resource_quote,
        )
        for item in source.opportunities
    )

    def observe():
        base_observation = _observation(storage=state["stage"] + 1)
        available = {item.kind: item for item in source.opportunities}
        return replace(
            base_observation,
            semantic_state_sha256=f"{state['stage'] + 1:064x}",
            situation=source.situation,
            binding_set=GoalBindingSet(
                tuple(
                    available.get(item.kind, item)
                    for item in base_observation.binding_set.opportunities
                ),
                bindings,
            ),
        )

    preflight_red_bounded_player(
        observe=observe,
        budget_meter=meter,
        assignment_id="quoted-native-test",
        authorities=(
            ("model", ExploringLivingDexGoalPolicy(_supply_model(), seed=17)),
            ("control", CompletionFirstGoalTeacher()),
        ),
    )
    assert state == {"actions": 0, "frames": 0, "stage": 0} and not sink.decisions
    policy = ExploringLivingDexGoalPolicy(_supply_model(), seed=17)
    kwargs = {
        item.name: getattr(base, item.name)
        for item in fields(GoalManagerTrajectoryObserver)
        if item.init
    }
    kwargs.update(partition="train", actor="model", policy_id="sampled-goals-v1")
    trajectory = RedPlayerTrainingTrajectory(
        **kwargs,
        displayed_authority=policy,
        training_meter=meter,
        training_plan_sha256="e" * 64,
        observe_training=lambda: SimpleNamespace(
            public_dict=lambda: _facts(source, registered=1 + state["stage"])
        ),
    )
    result = run_bounded_player_episode(
        observe=observe,
        authority=policy,
        authority_id="model",
        trajectory=trajectory,
        budget_meter=meter,
        completion_satisfied=lambda _: state["stage"] == 1,
        limits=BoundedPlayerLimits(max_decisions=1, max_replans=0),
    )
    assert len(result.steps) == 1 and state["actions"] == 1
    records = [event.payload for event in sink.events if event.kind == TRAINING_EVENT]
    assert len(records) == 1
    assert records[0]["example"]["outcome"]["target_names"][0] == "verified_success"
    assert records[0]["example"]["outcome"]["target_values"][0] == float(not failure)
    assert records[0]["actions"] == 1 and records[0]["frames"] == 60
    assert any(
        item.resource_quote is not None
        for item in trajectory.ordered_question(
            source.situation, source.opportunities
        ).opportunities
    )


def test_profile_binding_wrapper_preserves_optional_semantic_facts():
    quote = _quote()
    binding = ExecutableGoalBinding(
        "supplies",
        GoalKind.RESUPPLY,
        0.1,
        0.1,
        lambda: GoalExecutionReport(0, 0, {}),
        lambda _: GoalVerification.succeeded(),
        resource_quote=quote,
    )
    provider = SimpleNamespace(
        kind=GoalKind.RESUPPLY, offer=lambda _: RedGoalBindingOffer.available(binding)
    )
    wrapped = _ProfileBoundProvider(provider, "a" * 64, "b" * 64).offer(None)
    assert wrapped.binding.resource_quote is quote
    assert wrapped.binding.execute is binding.execute
