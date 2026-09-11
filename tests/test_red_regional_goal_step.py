from dataclasses import replace
from types import SimpleNamespace

import pytest
import run_red_regional_goal_step as driver
from test_goal_resource_quote import _supply_model
from test_red_player_continuation import _completed
from test_red_player_continuation import case as checkpoint_case
from test_red_player_training import _plan
from test_red_regional_acquisition import _candidate, _observation

from pokemon_red_completion.goal_search_memory import GoalSearchMemory
from pokemon_red_completion.living_dex_option_value import (
    upgrade_option_value_model_for_search_history,
)
from pokemon_red_completion.red_player_training_plan import RedPlayerTrainingPlan
from pokemon_red_completion.red_regional_acquisition import regional_acquisition_menu

case = checkpoint_case


def prepared(case, monkeypatch):
    ready, _ = _completed(case)
    model = upgrade_option_value_model_for_search_history(_supply_model())
    ready = replace(
        ready,
        decision_limit=1,
        model_sha256=model.model_sha256,
        training_plan=RedPlayerTrainingPlan({**_plan(model).document, "decision_limit": 1}),
        causal_record=SimpleNamespace(model=model),
    )
    candidates = (_candidate(), _candidate("wild:Route11:grass", 0.7))
    ready = replace(ready, profile=candidates[0].profile)
    observed = _observation()
    menu = regional_acquisition_menu(observed, candidates, GoalSearchMemory())
    monkeypatch.setattr(driver.source.base, "_prepare", lambda _: ready)
    monkeypatch.setattr(driver.source, "inspect_sources",
                        lambda _, **kw: (observed, candidates, menu))
    # The diagnostic greedy choice is resupply. Actual runtime sampling owns
    # the decision and may instead choose acquisition.
    monkeypatch.setattr(
        driver.source.base,
        "_action_free_preflight",
        lambda _: {
            "status": "ready",
            "living_dex_causal_shadow": {
                "decision": {"mode": "model_shadow", "selected_kind": "resupply"}
            },
        },
    )
    return ready, candidates


@pytest.mark.parametrize("actual_kind", ["resupply", "acquire_species"])
def test_native_parent_keeps_authority_and_is_the_only_learning_target(
    case, monkeypatch, actual_kind
):
    ready, candidates = prepared(case, monkeypatch)
    calls = []

    def run(actual):
        assert actual.regional_choice_record_sha256 is None
        record = actual.private_root.find_sealed_record(
            driver.regional_proposal_record_id(actual.training_plan.document["episode_id"]),
            expected_kind=driver.REGIONAL_PROPOSAL_KIND,
        )
        doc = record.read()
        assert record.summary.record_sha256 == actual.regional_proposal_record_sha256
        assert doc["source_proposal_fitted"] is False
        assert doc["controller_input_before_commit"] is False
        assert doc["parent_overridden"] is False
        assert doc["parent_plan"] == dict(actual.training_plan.document)
        assert doc["selection"]["seed"] == driver.regional_proposal_seed(17)
        assert actual.profile in [row.profile for row in candidates]
        calls.append(actual)
        return {
            "episode": {"steps": [{"selected_kind": actual_kind, "status": "succeeded"}]},
            "terminal_checkpoints": [{"record_sha256": "c" * 64}],
            "trajectory_manifest_sha256": "d" * 64,
        }

    monkeypatch.setattr(driver.source.base, "_run_prepared", run)
    monkeypatch.setattr(
        driver,
        "regional_proposal_source_effort",
        lambda *_: None if actual_kind == "resupply" else ("source", "e" * 64, False, 3, 180),
    )

    def dataset(_store, **kwargs):
        assert kwargs["plan"] is calls[0].training_plan
        assert kwargs["behavior_model"] is ready.causal_record.model
        return SimpleNamespace(examples=(object(),), curriculum_examples=())

    monkeypatch.setattr(driver, "load_red_player_training_episode", dataset)
    result = driver._run(SimpleNamespace())
    assert result["parent_episode"]["steps"][0]["selected_kind"] == actual_kind
    assert result["eligible_examples"] == 1
    assert result["eligible_source_examples"] == 0
    assert result["source_proposal_fitted"] is False
    assert result["source_acquisition_attempted"] is (actual_kind == "acquire_species")
    with pytest.raises(ValueError, match="already consumed"):
        driver._run(SimpleNamespace())
    assert len(calls) == 1


def test_interruption_after_proposal_does_not_retry_or_fit(case, monkeypatch):
    prepared(case, monkeypatch)

    def stop(_):
        raise RuntimeError("interrupted after proposal")

    monkeypatch.setattr(driver.source.base, "_run_prepared", stop)
    monkeypatch.setattr(
        driver,
        "load_red_player_training_episode",
        lambda *_a, **_k: pytest.fail("interruption must not fit"),
    )
    with pytest.raises(RuntimeError, match="interrupted after proposal"):
        driver._run(SimpleNamespace())
    with pytest.raises(ValueError, match="already consumed"):
        driver._run(SimpleNamespace())


@pytest.mark.parametrize("count", [0, 1, 2])
def test_native_goals_do_not_require_or_sample_multiple_sources(case, monkeypatch, count):
    ready, candidates = prepared(case, monkeypatch)
    candidates = candidates[:count]
    def inspect(actual, *, allow_no_choice):
        assert actual is ready and allow_no_choice is True
        return _observation(), candidates, None
    monkeypatch.setattr(driver.source, "inspect_sources", inspect)
    monkeypatch.setattr(driver.source, "sample_regional_acquisition",
                        lambda *_a, **_k: pytest.fail("no genuine source choice exists"))
    def run(actual):
        assert actual.profile == (candidates[0].profile if count else ready.profile)
        doc = actual.private_root.find_sealed_record(
            driver.regional_proposal_record_id(actual.training_plan.document["episode_id"]),
            expected_kind=driver.REGIONAL_PROPOSAL_KIND,
        ).read()
        assert doc["selection"] is None and doc["menu"] is None
        assert doc["source_mode"] == (
            "no_source" if count == 0 else (
                "unique_binding" if count == 1 else "deterministic_undifferentiated"
            )
        )
        assert doc["selected_source"] == (candidates[0].source_id if count else None)
        return {
            "episode": {"steps": [{"selected_kind": "evolve_species", "status": "succeeded"}]},
            "terminal_checkpoints": [{"record_sha256": "c" * 64}],
            "trajectory_manifest_sha256": "d" * 64,
        }
    monkeypatch.setattr(driver.source.base, "_run_prepared", run)
    monkeypatch.setattr(driver, "regional_proposal_source_effort", lambda *_: None)
    monkeypatch.setattr(driver, "load_red_player_training_episode",
                        lambda *_a, **_k: SimpleNamespace(
                            examples=(object(),), curriculum_examples=()))
    result = driver._run(SimpleNamespace())
    assert result["eligible_examples"] == 1 and result["eligible_source_examples"] == 0
    assert result["candidate_count"] == count
    assert result["parent_episode"]["steps"][0]["selected_kind"] == "evolve_species"
