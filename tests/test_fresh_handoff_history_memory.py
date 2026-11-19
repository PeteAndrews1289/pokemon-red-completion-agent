from copy import deepcopy
import gc
import weakref

import pytest
import run_fresh_red_player as fresh


STATE = "a" * 64


def recovery(**changes):
    row = dict(schema="pokemon.red.qualified-native-control-handoff.v1",
               state_sha256=STATE, qualified=True, failed_transport_preserved=True,
               strategic_substitution=False, inputs=0, frames=0, model_queries=0,
               binding_ref="pokemon.red:retained-engagement:" + STATE)
    row.update(changes)
    return row


@pytest.mark.parametrize("error_type,error,kind", [
    (None, None, "advance_story"),
    ("RouteExecutionError", "field dialogue lacks a newly poisoned member faint", "advance_story"),
    ("RouteExecutionError", "field dialogue is not an admitted native faint", "advance_story"),
    ("RouteExecutionError", "Gen I route cannot dismiss 'trainer_engagement'", "advance_story"),
    ("RedGoalContextError", "PC loan settlement requires settled field control", "evolve_species"),
    ("RedGoalContextError", "PC loan settlement requires settled field control", "advance_story"),
    ("RouteExecutionError", "unrecognized route failure", "advance_story"),
    ("UnexpectedError", "unknown failure", "develop_team"),
])
@pytest.mark.parametrize("receipts", [(), (recovery(),)])
def test_projection_preserves_failure_and_exact_recovery_decisions(error_type, error, kind, receipts):
    episode = dict(model_decisions=2, outcomes=[dict(error_type=error_type, error=error,
                   selected_kind=kind, terminal_state_sha256=STATE,
                   evidence={"large_diagnostics": "unused" * 5000})])
    original = deepcopy(episode)
    compact = fresh.compact_handoff_episode(episode)
    assert fresh.model_handoff_verified([episode], recovered_control_handoffs=receipts) == fresh.model_handoff_verified([compact], recovered_control_handoffs=receipts)
    assert episode == original


@pytest.mark.parametrize("changes", [dict(state_sha256="b" * 64), dict(strategic_substitution=True),
    dict(inputs=1), dict(frames=1), dict(model_queries=1), dict(qualified=False),
    dict(failed_transport_preserved=False), dict(schema="wrong")])
def test_compaction_does_not_weaken_handoff_admission(changes):
    episode = dict(model_decisions=1, outcomes=[dict(error_type="RouteExecutionError",
        error="field dialogue lacks a newly poisoned member faint", selected_kind="advance_story",
        terminal_state_sha256=STATE)])
    assert not fresh.model_handoff_verified([fresh.compact_handoff_episode(episode)],
        recovered_control_handoffs=[recovery(**changes)])


def test_prior_large_diagnostic_objects_are_not_retained():
    class Evidence:
        def __init__(self):
            self.payload = bytearray(1024 * 1024)
    refs = []
    history = []
    for index in range(30):
        evidence = Evidence()
        refs.append(weakref.ref(evidence))
        episode = dict(model_decisions=index % 2, outcomes=[dict(error_type=None,
            terminal_state_sha256=STATE, evidence=evidence)], diagnostic_history=evidence)
        history.append(fresh.compact_handoff_episode(episode))
        del episode, evidence
    gc.collect()
    assert all(ref() is None for ref in refs)
    assert fresh.model_handoff_verified(history)


def test_compact_prefix_still_requires_a_real_model_decision():
    episodes = [{"model_decisions": 0, "outcomes": []}, {"outcomes": []}]
    assert not fresh.model_handoff_verified([fresh.compact_handoff_episode(e) for e in episodes])
    episodes.append({"model_decisions": 1, "outcomes": []})
    assert fresh.model_handoff_verified([fresh.compact_handoff_episode(e) for e in episodes])


def test_chunk_budget_error_semantics_remain_unchanged():
    for name in fresh.CHUNK_BUDGET_ERRORS:
        episode = dict(model_decisions=1, outcomes=[dict(error_type=name, error="bounded",
            selected_kind="advance_story", terminal_state_sha256=STATE)])
        assert fresh.model_handoff_verified([episode]) == fresh.model_handoff_verified([fresh.compact_handoff_episode(episode)])
