from __future__ import annotations

import json
from dataclasses import fields, replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from test_bounded_player_episode import _trajectory
from test_living_dex_goal_policy import _model, _question
from test_paired_red_bounded_player_script import _observation

from pokemon_red_completion.bounded_player_dashboard import (
    BoundedPlayerDashboard,
    ViewerGoalTrajectory,
)
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalSelectionMode
from pokemon_red_completion.goal_manager_composition_runtime import CompositionBudgetCheckpoint
from pokemon_red_completion.goal_manager_trajectory import GoalManagerTrajectoryObserver
from pokemon_red_completion.living_dex_goal_policy import LivingDexGoalShadowPolicy
from pokemon_red_completion.party import PartyMemberObservation, PartyObservation
from pokemon_red_completion.progress_dashboard import DashboardState
from pokemon_red_completion.red_goal_manager import RedGoalObservation


def _viewer():  # type: ignore[no-untyped-def]
    state = DashboardState()
    viewer = BoundedPlayerDashboard(state, decision_limit=3)
    policy = LivingDexGoalShadowPolicy(_model())
    viewer.start_arm(learned=True, model_sha256=policy.model.model_sha256, train_examples=8)
    base, sink = _trajectory()
    trajectory = ViewerGoalTrajectory(
        **{
            entry.name: getattr(base, entry.name)
            for entry in fields(GoalManagerTrajectoryObserver)
            if entry.init
        },
        viewer=viewer,
        displayed_authority=policy,
        learned_actor=True,
    )
    return viewer, state, policy, trajectory, sink


def _public(state: DashboardState) -> dict:
    return json.loads(state.status_bytes()[0])


def test_view_reports_only_durably_committed_model_choices_and_outcomes() -> None:
    viewer, state, policy, trajectory, sink = _viewer()
    source = _question()
    question = trajectory.ordered_question(source.situation, source.opportunities)
    selected = policy.select(question)
    assert _public(state)["model"]["decisions"] == 0
    pending = trajectory.record_selection(question, selected.selected_index)
    assert len(sink.decisions) == 1
    assert _public(state)["model"]["decisions"] == 1
    assert policy.decisions == 1  # Drawing scores must never ask the actor again.
    assert _public(state)["model"]["choice"] == "Model: acquire species"
    assert any("utility (not a confidence" in row for row in _public(state)["events"])
    assert trajectory.record_outcome(pending, status=GoalDecisionOutcome.SUCCEEDED)
    assert _public(state)["experiment"]["adaptation"]["completed"] == 1
    assert len(sink.events) == 1
    assert not viewer.disabled


def test_failed_durable_choice_is_not_advertised_as_a_model_action(monkeypatch) -> None:
    viewer, state, policy, trajectory, sink = _viewer()
    source = _question()
    question = trajectory.ordered_question(source.situation, source.opportunities)
    selection = policy.select(question)

    def fail(_self: object, _record: object) -> None:
        raise OSError("private storage failure")

    monkeypatch.setattr(type(sink), "record_decision", fail)
    trajectory.record_selection(question, selection.selected_index)
    assert trajectory.pending_was_recorded is False
    assert _public(state)["model"]["decisions"] == 0
    assert _public(state)["experiment"]["zero_shot"]["completed"] == 0
    assert not viewer.disabled


@pytest.mark.parametrize("forced", [False, True])
def test_safety_and_forced_steps_are_not_learned_decisions(forced: bool) -> None:
    viewer, state, policy, trajectory, _sink = _viewer()
    source = _question(safety=0.9, include_restore=True)
    question = trajectory.ordered_question(source.situation, source.opportunities)
    selection = policy.select(question)
    trajectory.record_selection(
        question,
        selection.selected_index,
        selection_mode=(
            GoalSelectionMode.FORCED_SINGLETON if forced else GoalSelectionMode.AUTHORITY
        ),
    )
    public = _public(state)
    assert public["model"]["decisions"] == 0
    assert public["model"]["fallbacks"] == 1
    assert ("Forced single option" if forced else "Deterministic safety") in public["stage"]
    assert not viewer.disabled


def test_observer_values_are_real_and_frame_updates_do_not_reread_the_game() -> None:
    viewer, state, _policy, _trajectory, _sink = _viewer()
    live = Mock(spec=RedGoalObservation)
    live.game_state = SimpleNamespace(location="viridian_city")
    live.evidence = SimpleNamespace(level_collection=SimpleNamespace(completed=0))
    live.capture_item_count = 7
    live.free_storage_slots = 12
    live.party = PartyObservation(
        (
            PartyMemberObservation(
                slot=1,
                species_id=153,
                level=12,
                hp=17,
                max_hp=31,
            ),
        )
    )
    viewer.observed(live, _observation(storage=12))
    public = _public(state)
    assert public["location"] == "viridian_city"
    assert public["resources"] == {"capture_items": 7, "free_storage_slots": 12}
    assert public["party"][0]["label"] == "Pokédex #001"
    assert public["party"][0]["hp"] == 17
    viewer.bind_budget(lambda: CompositionBudgetCheckpoint(5, 20))
    viewer.publish_frame(1, 1, b"\x01\x02\x03", 20)
    assert _public(state)["actions"] == 5
    assert _public(state)["party"] == public["party"]
    assert live.method_calls == []
    assert not viewer.disabled


def test_same_state_comparison_keeps_frame_counters_monotonic() -> None:
    viewer, state, policy, _trajectory, _sink = _viewer()
    viewer.bind_budget(lambda: CompositionBudgetCheckpoint(5, 20))
    viewer.publish_frame(1, 1, b"\x01\x02\x03", 20)
    viewer.start_arm(learned=False, model_sha256=policy.model.model_sha256, train_examples=8)
    assert _public(state)["collection"]["observed"] is False
    assert _public(state)["run_status"] == "waiting"
    viewer.bind_budget(lambda: CompositionBudgetCheckpoint(3, 10))
    viewer.publish_frame(1, 1, b"\x04\x05\x06", 10)
    public = _public(state)
    assert public["frame_count"] == public["dashboard"]["logical_frame"] == 30
    assert public["actions"] == 8
    assert not viewer.disabled


def test_viewer_failure_disables_only_the_view_and_hides_private_errors(monkeypatch) -> None:
    viewer, state, _policy, _trajectory, _sink = _viewer()

    def fail(*_args: object) -> None:
        raise RuntimeError("secret instrument failure")

    monkeypatch.setattr(viewer, "observed", fail)
    viewer.safely("observed", None, None)
    assert viewer.disabled and viewer.failure_count == 1
    assert not viewer.wants_frame(200)
    assert _public(state)["run_status"] == "blocked"
    assert "secret instrument failure" not in state.status_bytes()[0].decode()


def test_terminal_cost_uses_the_meter_even_without_a_final_video_frame() -> None:
    viewer, state, _policy, _trajectory, _sink = _viewer()
    meter = [CompositionBudgetCheckpoint(5, 20)]
    viewer.bind_budget(lambda: meter[0])
    viewer.publish_frame(1, 1, b"\x01\x02\x03", 20)
    meter[0] = CompositionBudgetCheckpoint(31, 140)
    viewer.failed()
    public = _public(state)
    assert public["actions"] == 31
    assert public["frame_count"] == 140
    assert public["dashboard"]["logical_frame"] == 20  # Video is correctly still the last frame.
    assert public["run_status"] == "failed"


@pytest.mark.parametrize("decision_limit", [True, 0, 5])
def test_viewer_rejects_unbounded_episode_limits(decision_limit: int) -> None:
    with pytest.raises(ValueError, match="bounded"):
        BoundedPlayerDashboard(DashboardState(), decision_limit=decision_limit)


def test_completed_collection_observation_changes_the_display_without_crediting_a_fit() -> None:
    viewer, state, _policy, _trajectory, _sink = _viewer()
    before = _observation(storage=2)
    after = replace(
        before,
        collection=replace(
            before.collection,
            living_species=11,
            registered_species=11,
            specimen_counts=(("pokemon:red:living:starter", 11),),
        ),
    )
    live = Mock(spec=RedGoalObservation)
    live.game_state = SimpleNamespace(location="viridian_city")
    live.evidence = SimpleNamespace(level_collection=SimpleNamespace(completed=0))
    live.capture_item_count = 4
    live.free_storage_slots = 2
    live.party = PartyObservation()
    viewer.observed(live, before)
    assert _public(state)["collection"]["living"] == 10
    viewer.observed(live, after)
    assert _public(state)["collection"]["living"] == 11
    assert _public(state)["experiment"]["sealed_test"]["completed"] == 0
    assert _public(state)["model"]["decisions"] == 0
