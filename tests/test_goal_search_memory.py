import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_living_dex_goal_policy import _model, _question
from test_red_bounded_player import _binding_set, _collection, _live
from test_red_player_checkpoint import _complete, _open
from test_red_player_checkpoint import case as checkpoint_case

from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import GoalKind, GoalManagerQuestion
from pokemon_red_completion.goal_search_memory import GoalSearchHistory, GoalSearchMemory
from pokemon_red_completion.living_dex_goal_policy import (
    LivingDexGoalPolicyError,
    LivingDexGoalShadowPolicy,
)
from pokemon_red_completion.red_bounded_player import RedBoundedPlayerObserver
from pokemon_red_completion.red_player_checkpoint import (
    MEMORY_CHECKPOINT_SCHEMA,
    capture_red_player_terminal,
    publish_red_player_checkpoint,
    recover_completed_red_player_checkpoint,
)

case = checkpoint_case


def test_restore_keeps_distinct_sources_and_costs_without_private_policy_keys():
    memory = GoalSearchMemory()
    memory.record("private-source-a", "1" * 64, exhausted=True, actions=7, frames=91)
    memory.record("private-source-b", "1" * 64, exhausted=False, actions=13, frames=123)
    restored = GoalSearchMemory.from_private_dict(json.loads(json.dumps(memory.private_dict())))
    assert restored.lookup("private-source-a", "1" * 64) == GoalSearchHistory(1, 1, 7, 91)
    assert restored.lookup("private-source-b", "1" * 64) == GoalSearchHistory(1, 0, 13, 123)
    restored.record("private-source-a", "1" * 64, exhausted=True, actions=3, frames=29)
    assert restored.lookup("private-source-a", "1" * 64) == GoalSearchHistory(2, 2, 10, 120)
    assert memory.lookup("private-source-a", "1" * 64).attempts == 1
    assert restored.lookup("private-source-a", "2" * 64).attempts == 0
    assert restored.lookup("unvisited", "1" * 64).public_dict()["earlier_history_known"] is False
    encoded = json.dumps(restored.lookup("private-source-a", "1" * 64).public_dict())
    assert "private-source" not in encoded and "1" * 64 not in encoded


@pytest.mark.parametrize("changes", [
    {"attempts": True}, {"attempts": -1}, {"exhausted": 2}, {"frames": -1},
    {"actions": 0}, {"frames": float("nan")}, {"actions": 2**53},
])
def test_invalid_history_cannot_become_observed_effort(changes):
    with pytest.raises(ValueError):
        GoalSearchHistory(**{**dict(attempts=1, exhausted=1, actions=4, frames=9), **changes})


@pytest.mark.parametrize("actions,frames", [(0, 1), (True, 1), (3, -1), (3, True)])
def test_invalid_increment_does_not_modify_memory(actions, frames):
    memory = GoalSearchMemory()
    memory.record("source", "a" * 64, exhausted=True, actions=10, frames=30)
    before = memory.private_dict()
    with pytest.raises(ValueError):
        memory.record("source", "a" * 64, exhausted=True, actions=actions, frames=frames)
    assert memory.private_dict() == before


def test_versioned_policy_roundtrip_preserves_history_and_legacy_bytes():
    original = _question()
    legacy = dict(original.policy_input)
    changed = replace(original, opportunities=tuple(
        replace(row, search_history=GoalSearchHistory(2, 1, 17, 250))
        if row.kind is GoalKind.ACQUIRE_SPECIES else row
        for row in original.opportunities
    ))
    assert changed.policy_input["schema"] == "pokemon.core.goal-manager-input.v3"
    restored = GoalManagerQuestion.from_policy_input(changed.policy_input)
    assert restored.ordered_policy_input_sha256 == changed.ordered_policy_input_sha256
    assert original.policy_input == legacy
    assert original.policy_input["schema"] == "pokemon.core.goal-manager-input.v1"
    with pytest.raises(ValueError):
        GoalManagerQuestion.from_policy_input({
            **changed.policy_input, "schema": "pokemon.core.goal-manager-input.v1",
        })
    with pytest.raises(LivingDexGoalPolicyError, match="history-trained"):
        LivingDexGoalShadowPolicy(_model()).select(changed)


def test_live_bridge_projects_memory_without_changing_availability_or_bindings():
    memory = GoalSearchMemory()
    bindings = _binding_set()
    acquisition = next(row for row in bindings.bindings if row.kind is GoalKind.ACQUIRE_SPECIES)
    memory.record(acquisition.binding_ref, "3" * 64, exhausted=True, actions=11, frames=70)
    live = _live()
    runtime = SimpleNamespace(adapter=SimpleNamespace(observe=lambda: live))
    observer = RedBoundedPlayerObserver(
        runtime, CountingExecutor(SimpleNamespace()), collection_projector=lambda _: _collection(),
        enumerate_bindings=lambda _: bindings, search_memory=memory,
    )
    observed = observer()
    current = observed.binding_set.require(acquisition.binding_ref)
    assert current.search_history == GoalSearchHistory(1, 1, 11, 70)
    assert current.execute is acquisition.execute
    assert current.verify is acquisition.verify
    assert len(observed.binding_set.bindings) == len(bindings.bindings)
    assert observer.actions.actions_executed == 0
    # Reordering and unrelated party/resource changes do not reset source history.
    live.situation = replace(live.situation, resource_pressure=0.8, team_pressure=0.7)
    observer.enumerate_bindings = lambda _: replace(
        bindings, opportunities=tuple(reversed(bindings.opportunities)),
    )
    assert (
        observer().binding_set.require(acquisition.binding_ref).search_history
        == current.search_history
    )
    observer.collection_projector = lambda _: replace(
        _collection(), required_specimens_sha256="4" * 64,
    )
    assert observer().binding_set.require(acquisition.binding_ref).search_history.attempts == 0


def test_child_memory_must_retain_prior_records_and_cannot_regress():
    prior = GoalSearchMemory()
    prior.record("source", "a" * 64, exhausted=True, actions=5, frames=51)
    with pytest.raises(ValueError, match="lost"):
        GoalSearchMemory().require_extension(prior)
    child = GoalSearchMemory.from_private_dict(prior.private_dict())
    child.require_extension(prior)
    child.record("source", "a" * 64, exhausted=False, actions=4, frames=49)
    child.require_extension(prior)
    with pytest.raises(ValueError):
        prior.require_extension(child)


@pytest.mark.parametrize("reason,expected", [("search_exhausted", 1), ("outcome_not_verified", 0)])
@pytest.mark.parametrize("stable_source", [None, "private-stable-source"])
def test_player_records_only_metered_settled_searches(reason, expected, stable_source):
    from test_bounded_player_episode import _observer, _trajectory

    from pokemon_red_completion.bounded_player_episode import run_bounded_player_episode
    from pokemon_red_completion.goal_manager import GoalFailureReason
    from pokemon_red_completion.goal_manager_runtime import GoalBindingSet, GoalVerification

    base, meter, state = _observer(same_failure_context=True)
    memory = GoalSearchMemory()

    def observe():
        obs = base()
        bindings = tuple(replace(
            binding, kind=GoalKind.ACQUIRE_SPECIES,
            search_source_ref=stable_source,
            verify=lambda _: GoalVerification.failed(GoalFailureReason(reason)),
        ) if binding.kind is GoalKind.RESTORE_TEAM else binding
            for binding in obs.binding_set.bindings)
        by_ref = {b.binding_ref: b.opportunity for b in bindings}
        return replace(obs, binding_set=GoalBindingSet(tuple(
            replace(row, kind=GoalKind.RESTORE_TEAM)
            if row.kind is GoalKind.ACQUIRE_SPECIES
            else by_ref.get(row.binding_ref, row)
            for row in obs.binding_set.opportunities
        ), bindings))

    authority = SimpleNamespace(select=lambda q: next(
        i for i in q.available_indices if q.opportunities[i].kind is GoalKind.ACQUIRE_SPECIES
    ))
    trajectory, _ = _trajectory()
    result = run_bounded_player_episode(
        observe=observe, authority=authority, authority_id="search-test",
        trajectory=trajectory, budget_meter=meter, completion_satisfied=lambda _: False,
        search_memory=memory,
    )
    assert len(result.steps) == 1 and state["actions"] == 5
    history = memory.lookup(stable_source or "private:red:restore_team", "3" * 64)
    assert history.attempts == history.exhausted == expected
    assert (history.actions, history.frames) == ((5, 50) if expected else (0, 0))


def test_observer_reuses_source_memory_when_execution_binding_changes():
    memory = GoalSearchMemory()
    memory.record("stable-source", "3" * 64, exhausted=True, actions=50, frames=500)
    bindings = _binding_set()
    acquire = next(b for b in bindings.bindings if b.kind is GoalKind.ACQUIRE_SPECIES)
    from pokemon_red_completion.goal_manager_runtime import GoalBindingSet

    for execution_ref in ("origin-a", "origin-b"):
        changed = replace(acquire, binding_ref=execution_ref, search_source_ref="stable-source")
        current = GoalBindingSet(
            tuple(changed.opportunity if row.kind is GoalKind.ACQUIRE_SPECIES else row
                  for row in bindings.opportunities),
            tuple(changed if row.kind is GoalKind.ACQUIRE_SPECIES else row
                  for row in bindings.bindings),
        )
        observer = RedBoundedPlayerObserver(
            SimpleNamespace(adapter=SimpleNamespace(observe=_live)),
            CountingExecutor(SimpleNamespace()), collection_projector=lambda _: _collection(),
            enumerate_bindings=lambda _, value=current: value, search_memory=memory,
        )
        observed = observer().binding_set.require(execution_ref)
        assert observed.search_history == GoalSearchHistory(1, 1, 50, 500)
        question = GoalManagerQuestion(_live().situation, observer().binding_set.opportunities)
        assert "stable-source" not in str(question.policy_input)


def test_memory_checkpoint_authenticates_and_restores_independent_mutable_copy(case):
    store, arguments, _ = case
    memory = GoalSearchMemory()
    memory.record("search-source", "a" * 64, exhausted=True, actions=9, frames=87)
    captured = capture_red_player_terminal(**arguments, search_memory=memory)
    assert captured["schema"] == MEMORY_CHECKPOINT_SCHEMA
    memory.record("search-source", "a" * 64, exhausted=False, actions=1, frames=5)
    _complete(store, captured)
    # Simulate stopping after durable trajectory close, before publication.
    summary = recover_completed_red_player_checkpoint(store, arguments["episode_id"])
    saved = _open(store, arguments, summary)
    restored = GoalSearchMemory.from_private_dict(saved.search_memory)
    assert restored.lookup("search-source", "a" * 64) == GoalSearchHistory(1, 1, 9, 87)
    assert memory.lookup("search-source", "a" * 64).attempts == 2


def test_legacy_checkpoint_does_not_invent_empty_complete_history(case):
    store, arguments, _ = case
    captured = capture_red_player_terminal(**arguments)
    assert "search_memory" not in captured
    _complete(store, captured)
    saved = _open(store, arguments, publish_red_player_checkpoint(store, captured))
    assert saved.search_memory is None


def test_continuation_rejects_a_child_that_drops_authenticated_history(case):
    import run_paired_red_bounded_player as runner
    from test_red_player_continuation import _readiness

    store, arguments, _ = case
    memory = GoalSearchMemory()
    memory.record("source", "a" * 64, exhausted=True, actions=3, frames=40)
    first = capture_red_player_terminal(**arguments, search_memory=memory)
    _complete(store, first, alter_header={
        "split": {"partition": "train", "root_lineage_id": "original-training-root"},
    })
    first_record = publish_red_player_checkpoint(store, first)
    first_link = (arguments["episode_id"], first_record["record_sha256"])
    readiness = _readiness(store, arguments)
    continued = runner._continue_readiness(readiness, (first_link,))
    child = capture_red_player_terminal(**{
        **arguments, "parent": continued.capture, "episode_id": "memory-losing-child",
    })
    _complete(store, child, alter_header=runner._continuation_header(continued))
    child_record = publish_red_player_checkpoint(store, child)
    with pytest.raises(runner.PairedRedBoundedPlayerRunError, match="search_history_lost"):
        runner._continue_readiness(readiness, (
            first_link, ("memory-losing-child", child_record["record_sha256"]),
        ))
