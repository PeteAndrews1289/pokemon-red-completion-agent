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
