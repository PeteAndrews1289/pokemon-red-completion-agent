from __future__ import annotations

import pytest

from pokemon_red_completion import red_trainer_practice_counterfactual as counterfactual
from pokemon_red_completion.battle_actions import BattleAction
from pokemon_red_completion.battle_scenario_capture import (
    build_battle_scenario_capture_payload,
    open_battle_scenario_capture,
)
from pokemon_red_completion.red_trainer_practice_episode import RedTrainerPracticeEpisode
from pokemon_red_completion.red_trainer_practice_log import (
    TrainerPracticeEventLog,
    verify_trainer_practice_event_log,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition


def _capture(tmp_path, *, partition=ScenarioPartition.TRAIN):
    state = b"synthetic trainer"
    path = tmp_path / "trainer.state"
    manifest = tmp_path / "trainer.state.json"
    path.write_bytes(state)
    manifest.write_bytes(
        build_battle_scenario_capture_payload(
            capture_id="trainer-cf-unit",
            root_lineage_id="trainer-cf-root",
            partition=partition,
            state_bytes=state,
            initial_observation_sha256="b" * 64,
            source_commit="c" * 40,
            expected_map=40,
            expected_battle_state=2,
        )
    )
    return open_battle_scenario_capture(path, manifest)


class Continuation:
    policy_id = "unit-continuation"

    def choose_main(self, _observation, _prepared):
        return BattleAction.move(2)

    def choose_switch(self, _observation, legal_party_slots, *, forced, may_decline):
        return legal_party_slots[0] if forced else None


def test_first_choice_owns_initial_action_and_then_defers_to_fresh_continuation():
    first = counterfactual._FirstChoicePolicy(
        counterfactual.TrainerPracticeFirstChoice(BattleAction.switch(4)), Continuation()
    )
    assert first.choose_main({}, object()) == BattleAction.switch(4)
    assert first.choose_main({}, object()) == BattleAction.move(2)
    assert first.consumed
    decline = counterfactual._FirstChoicePolicy(
        counterfactual.TrainerPracticeFirstChoice(None), Continuation()
    )
    assert decline.choose_switch({}, (2, 3), forced=False, may_decline=True) is None
    assert decline.choose_switch({}, (2, 3), forced=True, may_decline=False) == 2


@pytest.mark.parametrize("budget", [8, 160])
@pytest.mark.parametrize("bounded", [False, True])
def test_matched_branches_keep_one_root_and_fresh_policies(tmp_path, monkeypatch, budget, bounded):
    capture = _capture(tmp_path)
    policies = []
    retained = []
    executor = object() if bounded else None
    guard = (lambda _raw: None) if bounded else None

    def policy_factory():
        policy = Continuation()
        policies.append(policy)
        return policy

    def fake_run(_capture, *, session_factory, policy, max_decisions, max_player_turns,
                 event_sink=None, public_species_base_stats=None, opening_idle_frames=0,
                 action_executor=None, decision_guard=None):
        assert action_executor is executor
        assert decision_guard is guard
        assert max_decisions == budget
        assert max_player_turns == 2
        assert session_factory() is None
        action = policy.choose_main({}, object())
        return RedTrainerPracticeEpisode(
            capture_id=capture.manifest.capture_id,
            manifest_sha256=capture.manifest_sha256,
            policy_id=policy.policy_id,
            decisions=(
                {"kind": "voluntary_switch" if action.party_slot else "attack"},
                {"kind": "attack"},
            ),
            battle_won=False,
            final_battle_state=2,
            stop_reason="player_turn_budget",
            final_observation={"features": {"battle": {"kind": "trainer"}}},
        )

    monkeypatch.setattr(counterfactual, "run_red_trainer_practice_episode", fake_run)
    result = counterfactual.collect_trainer_practice_counterfactuals(
        capture,
        session_factory=lambda: None,
        continuation_policy_factory=policy_factory,
        max_decisions=budget,
        action_executor=executor,
        decision_guard=guard,
        first_choices=(
            counterfactual.TrainerPracticeFirstChoice(BattleAction.move(1)),
            counterfactual.TrainerPracticeFirstChoice(BattleAction.switch(2)),
        ),
        branch_sink=lambda index, choice, episode: retained.append(
            (index, choice.semantic_ref, episode.stop_reason)
        ),
    )
    assert policies[0] is not policies[1]
    assert [branch[0].semantic_ref for branch in result.branches] == [
        "pokemon.core:battle:move:1",
        "pokemon.core:battle:switch:2",
    ]
    assert result.public_dict()["new_independent_upstream_roots"] == 0
    assert retained == [
        (0, "pokemon.core:battle:move:1", "player_turn_budget"),
        (1, "pokemon.core:battle:switch:2", "player_turn_budget"),
    ]


def test_counterfactual_rejects_development_capture(tmp_path):
    capture = _capture(tmp_path, partition=ScenarioPartition.DEVELOPMENT)
    try:
        counterfactual.collect_trainer_practice_counterfactuals(
            capture,
            session_factory=lambda: None,
            continuation_policy_factory=Continuation,
            first_choices=(
                counterfactual.TrainerPracticeFirstChoice(BattleAction.move(1)),
                counterfactual.TrainerPracticeFirstChoice(BattleAction.switch(2)),
            ),
        )
    except counterfactual.TrainerPracticeCounterfactualError:
        pass
    else:
        raise AssertionError("development capture entered TRAIN counterfactual collector")


def test_failed_branch_retains_selected_choice_and_typed_failure(tmp_path, monkeypatch):
    capture = _capture(tmp_path)
    directory = tmp_path / "branch-events"
    retained = []

    def crash(_capture, *, session_factory, policy, max_decisions, max_player_turns,
              event_sink=None, public_species_base_stats=None, opening_idle_frames=0,
              action_executor=None, decision_guard=None):
        assert event_sink is not None
        event_sink({"event": "episode_started"})
        event_sink({"event": "decision_started"})
        event_sink({"event": "choice_recorded", "decision_index": 1,
                    "selected_action": {"kind": "select_move", "move_slot": 1}})
        raise RuntimeError("diagnostic switch boundary")

    monkeypatch.setattr(counterfactual, "run_red_trainer_practice_episode", crash)
    with pytest.raises(RuntimeError, match="diagnostic switch boundary"):
        counterfactual.collect_trainer_practice_counterfactuals(
            capture,
            session_factory=lambda: None,
            continuation_policy_factory=Continuation,
            first_choices=(
                counterfactual.TrainerPracticeFirstChoice(BattleAction.move(1)),
                counterfactual.TrainerPracticeFirstChoice(BattleAction.switch(2)),
            ),
            branch_sink=lambda *_args: retained.append(1),
            branch_event_log_factory=lambda _index, _choice: TrainerPracticeEventLog(
                directory, run_identity={"first_choice_ref": "pokemon.core:battle:move:1"}
            ),
        )
    verification = verify_trainer_practice_event_log(directory)
    assert verification["complete"] is True
    assert verification["terminal_event"] == "run_failed"
    assert retained == []
