from dataclasses import replace
from types import SimpleNamespace

import pytest
import run_red_regional_source_choice as driver
from test_red_player_continuation import _completed
from test_red_player_continuation import case as checkpoint_case
from test_red_regional_acquisition import _candidate, _observation

from pokemon_red_completion.goal_search_memory import GoalSearchMemory
from pokemon_red_completion.red_player_training_plan import RedPlayerTrainingPlan
from pokemon_red_completion.red_regional_acquisition import regional_acquisition_menu

case = checkpoint_case


@pytest.mark.parametrize("bad_slot", [0, 1])
def test_fainted_member_refuses_before_prediction_commit_or_input(monkeypatch, bad_slot):
    from test_red_goal_skills import _adapter, _raw, _Reader

    raw = _raw()
    raw = replace(
        raw, party_count=2, party_species_ids=raw.party_species_ids * 2,
        party_levels=raw.party_levels * 2,
        party_hp=(0, 180) if bad_slot == 0 else (180, 0),
        party_max_hp=(180, 180), party_status=(0, 0),
        party_moves=raw.party_moves * 2, party_pp=raw.party_pp * 2,
    )
    observed = _adapter(_Reader(raw=raw, ready=True)).observe()
    root = SimpleNamespace(find_sealed_record=lambda *_a, **_k: None)
    ready = SimpleNamespace(
        decision_limit=1, save_terminal_checkpoints=True,
        training_plan=SimpleNamespace(document={"episode_id": "unclaimed-source"}),
        causal_record=object(), private_root=root,
    )
    monkeypatch.setattr(driver.base, "_prepare", lambda _: ready)
    monkeypatch.setattr(driver, "inspect_sources", lambda _: (observed, (), None))
    monkeypatch.setattr(driver, "sample_regional_acquisition",
                        lambda *_a, **_k: pytest.fail("unsafe source was sampled"))
    monkeypatch.setattr(driver.base, "_run_prepared",
                        lambda *_a: pytest.fail("unsafe source was executed"))
    with pytest.raises(ValueError, match="recovery before choice"):
        driver._run(SimpleNamespace())


def test_starting_health_check_preserves_a_healthy_source_context():
    driver.require_source_attempt_ready(_observation())


@pytest.mark.parametrize("mode", ["deterministic_unsupported", "deterministic_safety"])
def test_source_parent_accepts_capture_only_without_second_learned_label(mode):
    driver._require_capture_parent(
        {
            "living_dex_causal_shadow": {
                "decision": {
                    "selected_kind": "acquire_species",
                    "mode": mode,
                }
            }
        }
    )
    driver._require_capture_parent(
        {
            "status": "ready_for_forced_bridge",
            "available_goal_kinds": ["acquire_species"],
            "model_queries": 0,
        }
    )


@pytest.mark.parametrize(
    "kind,mode",
    [
        ("acquire_species", "model_shadow"),
        ("restore_team", "deterministic_safety"),
        ("explore", "deterministic_unsupported"),
    ],
)
def test_source_parent_rejects_overriding_or_double_counting(kind, mode):
    with pytest.raises(ValueError, match="override or duplicate"):
        driver._require_capture_parent(
            {
                "living_dex_causal_shadow": {
                    "decision": {
                        "selected_kind": kind,
                        "mode": mode,
                    }
                }
            }
        )


def test_source_identity_is_committed_before_run_and_never_resampled(case, monkeypatch):
    from test_goal_resource_quote import _supply_model
    from test_red_player_training import _plan

    from pokemon_red_completion.living_dex_option_value import (
        upgrade_option_value_model_for_search_history,
    )

    ready, _ = _completed(case)
    model = upgrade_option_value_model_for_search_history(_supply_model())
    plan = RedPlayerTrainingPlan({**_plan(model).document, "decision_limit": 1})
    ready = replace(
        ready, decision_limit=1, training_plan=plan, causal_record=SimpleNamespace(model=model)
    )
    candidates = (_candidate(), _candidate("wild:Route11:grass", 0.7))
    observed = _observation()
    menu = regional_acquisition_menu(observed, candidates, GoalSearchMemory())
    monkeypatch.setattr(driver.base, "_prepare", lambda _: ready)
    monkeypatch.setattr(driver, "inspect_sources", lambda _: (observed, candidates, menu))
    monkeypatch.setattr(
        driver.base,
        "_action_free_preflight",
        lambda _: {
            "status": "ready_for_forced_bridge",
            "available_goal_kinds": ["acquire_species"],
            "model_queries": 0,
        },
    )
    committed = []

    def stop_before_input(actual):
        record = ready.private_root.find_sealed_record(
            driver.regional_choice_record_id(plan.document["episode_id"]),
            expected_kind=driver.REGIONAL_CHOICE_KIND,
        )
        assert record is not None
        assert record.summary.record_sha256 == actual.regional_choice_record_sha256
        assert record.read()["parent_plan"]["profile_sha256"] == actual.profile.profile_sha256
        committed.append(record.summary.record_sha256)
        raise RuntimeError("simulated interruption after commit")

    monkeypatch.setattr(driver.base, "_run_prepared", stop_before_input)
    with pytest.raises(RuntimeError, match="simulated interruption"):
        driver._run(SimpleNamespace())
    monkeypatch.setattr(driver, "inspect_sources", lambda _: pytest.fail("resampled"))
    with pytest.raises(ValueError, match="already consumed"):
        driver._run(SimpleNamespace())
    assert len(committed) == 1


def test_regional_history_survives_local_vs_routed_binding_and_checks_ancestor(tmp_path):
    from test_red_regional_choice_learning import _recorded

    from pokemon_red_completion.red_player_checkpoint import CHECKPOINT_KIND, checkpoint_record_id

    store, item, _ = _recorded(tmp_path, failed=True)
    record = store.find_sealed_record(
        checkpoint_record_id(item.episode_id), expected_kind=CHECKPOINT_KIND
    )
    choice = store.find_sealed_record(
        driver.regional_choice_record_id(item.episode_id), expected_kind=driver.REGIONAL_CHOICE_KIND
    ).read()
    source = choice["candidates"][choice["selection"]["selected_candidate_index"]]["source_id"]
    ready = SimpleNamespace(
        private_root=store, continuation_chain=((item.episode_id, record.summary.record_sha256),)
    )
    memory = driver.source_search_memory(ready)
    history = memory.lookup(driver.regional_source_memory_key(source), "f" * 64)
    assert (history.attempts, history.exhausted, history.actions, history.frames) == (1, 1, 1, 60)
    assert memory.lookup(driver.regional_source_memory_key(source), "a" * 64).attempts == 0
    assert memory.lookup(driver.regional_source_memory_key("unplayed"), "f" * 64).attempts == 0
    ready.continuation_chain = ((item.episode_id, "0" * 64),)
    with pytest.raises(ValueError, match="history binding"):
        driver.source_search_memory(ready)


@pytest.mark.parametrize("kind,attempts", [("resupply", 0), ("acquire_species", 1)])
def test_mixed_parent_proposal_history_counts_only_played_acquisition(tmp_path, kind, attempts):
    from test_red_regional_goal_proposal import recorded
    store, terminal, *_ = recorded(tmp_path, kind=kind)
    ready = SimpleNamespace(private_root=store, continuation_chain=(
        ("goal-episode-1", terminal.summary.record_sha256),))
    memory = driver.source_search_memory(ready)
    history = memory.lookup(driver.regional_source_memory_key("wild:Route11:grass"), "f"*64)
    assert history.attempts == attempts
    assert history.actions == 7 * attempts
