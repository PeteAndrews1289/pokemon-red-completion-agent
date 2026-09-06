import json
from types import SimpleNamespace

import pytest
from test_living_dex_option_value import _example, _settled
from test_red_player_training import _episode

import pokemon_red_completion.red_player_training_fit as fitting
from pokemon_red_completion.goal_manager import GoalDecisionOutcome
from pokemon_red_completion.living_dex_goal_model_record import LivingDexGoalModelRecord
from pokemon_red_completion.living_dex_option_value import fit_living_dex_option_value
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_player_model import (
    RedPlayerModelRecord,
    load_player_goal_model_record_bytes,
)
from pokemon_red_completion.red_player_training_fit import (
    RedPlayerEpisodeInput,
    bootstrap_red_player_search_history,
    fit_red_player_update,
)


def _prior(rows):
    model = fit_living_dex_option_value(rows).model
    return LivingDexGoalModelRecord(model, "a" * 64, "b" * 40, "c" * 64, 1, 1)


def _fit(tmp_path, monkeypatch, *, failure=False, history=False):
    store, plan, behavior, completed = _episode(
        tmp_path,
        status=GoalDecisionOutcome.FAILED if failure else GoalDecisionOutcome.SUCCEEDED,
        return_inputs=True,
        history=history,
    )
    rows = tuple(
        _example(
            i,
            selected=i,
            outcome=_settled(success=bool(i), completion=i * 0.1, unlock=0, action_cost=0.2),
        )
        for i in range(2)
    )
    monkeypatch.setattr(
        fitting,
        "load_living_dex_authenticated_causal_examples",
        lambda _: tuple(SimpleNamespace(example=row) for row in rows),
    )
    prior = _prior(rows)
    behavior_record = LivingDexGoalModelRecord(behavior, "d" * 64, "b" * 40, "c" * 64, 1, 1)
    request = RedPlayerEpisodeInput(
        plan, "goal-episode-1", completed.manifest_sha256, behavior_record
    )
    result = fit_red_player_update(
        store,
        prior=prior,
        episodes=(request,),
        source_commit="e" * 40,
        source_bundle_sha256="f" * 64,
    )
    return store, rows, prior, request, result


@pytest.mark.parametrize("failure", [False, True])
@pytest.mark.parametrize("history", [False, True])
def test_fit_uses_real_episode_reader_and_retains_prior_rows_including_negative(
    tmp_path, monkeypatch, failure, history
):
    store, rows, prior, request, result = _fit(
        tmp_path, monkeypatch, failure=failure, history=history
    )
    assert result["new_settled_examples"] == 1
    assert result["fit_report"]["settled_examples"] == 3
    assert result["controller_actions"] == result["authority_promotions"] == 0
    assert result["in_sample_only"] is True
    model_hash = result["model"]["model_sha256"]
    record = store.find_sealed_record(f"rp-model-{model_hash}", expected_kind="red_player_model")
    loaded = load_player_goal_model_record_bytes(
        record.read_bytes(), expected_model_sha256=model_hash
    )
    assert isinstance(loaded, RedPlayerModelRecord)
    assert loaded.model.feature_version == (2 if history else 1)
    assert set(canonical_sha256(row.public_dict()) for row in rows).issubset(
        loaded.retained_example_sha256
    )
    assert loaded.model.model_sha256 != prior.model.model_sha256
    assert "exact_ci_run" not in loaded.public_dict()
    with pytest.raises(ValueError, match="additional"):
        fit_red_player_update(
            store,
            prior=loaded,
            episodes=(request,),
            source_commit="e" * 40,
            source_bundle_sha256="f" * 64,
        )


def test_native_model_rejects_missing_retained_row_and_wrong_expected_weights(
    tmp_path, monkeypatch
):
    store, _, _, _, result = _fit(tmp_path, monkeypatch)
    model_hash = result["model"]["model_sha256"]
    record = store.find_sealed_record(f"rp-model-{model_hash}", expected_kind="red_player_model")
    with pytest.raises(ValueError):
        load_player_goal_model_record_bytes(record.read_bytes(), expected_model_sha256="0" * 64)
    document = record.read()
    document["retained_example_sha256"].pop()
    with pytest.raises(ValueError):
        load_player_goal_model_record_bytes(
            json.dumps(document).encode(), expected_model_sha256=model_hash
        )


def test_history_bootstrap_authenticates_actual_retained_corpus_without_refitting(
    tmp_path, monkeypatch
):
    store, _, _, _, result = _fit(tmp_path, monkeypatch)
    model_hash = result["model"]["model_sha256"]
    record = store.find_sealed_record(f"rp-model-{model_hash}", expected_kind="red_player_model")
    prior = load_player_goal_model_record_bytes(
        record.read_bytes(), expected_model_sha256=model_hash
    )
    monkeypatch.setattr(
        fitting,
        "fit_living_dex_option_value",
        lambda *_args, **_kwargs: pytest.fail("bootstrap must not fit"),
    )
    before = record.read_bytes()
    report = bootstrap_red_player_search_history(
        store, prior=prior, source_commit="e" * 40, source_bundle_sha256="f" * 64
    )
    assert report["new_examples"] == report["fits"] == report["controller_actions"] == 0
    assert report["retained_examples"] == report["unknown_history_examples"] == 3
    assert report["history_effect_learned"] is False and record.read_bytes() == before
    upgraded_hash = report["model"]["model_sha256"]
    upgraded_record = store.find_sealed_record(
        f"rp-model-{upgraded_hash}", expected_kind="red_player_model"
    )
    upgraded = load_player_goal_model_record_bytes(
        upgraded_record.read_bytes(), expected_model_sha256=upgraded_hash
    )
    assert upgraded.model.feature_version == 2
    assert upgraded.corpus_sha256 == prior.corpus_sha256
    assert upgraded.retained_example_sha256 == prior.retained_example_sha256
    with pytest.raises(ValueError, match="legacy"):
        bootstrap_red_player_search_history(
            store, prior=upgraded, source_commit="e" * 40, source_bundle_sha256="f" * 64
        )


@pytest.mark.parametrize("damage", ["fingerprint", "dataset"])
def test_history_bootstrap_refuses_mismatched_retained_evidence(tmp_path, monkeypatch, damage):
    from dataclasses import replace

    store, _, _, _, result = _fit(tmp_path, monkeypatch)
    model_hash = result["model"]["model_sha256"]
    record = store.find_sealed_record(f"rp-model-{model_hash}", expected_kind="red_player_model")
    prior = load_player_goal_model_record_bytes(
        record.read_bytes(), expected_model_sha256=model_hash
    )
    if damage == "fingerprint":
        prior = replace(
            prior, retained_example_sha256=("0" * 64, *prior.retained_example_sha256[1:])
        )
    else:
        prior = replace(prior, model=replace(prior.model, train_dataset_sha256="0" * 64))
    with pytest.raises(ValueError, match="retained"):
        bootstrap_red_player_search_history(
            store, prior=prior, source_commit="e" * 40, source_bundle_sha256="f" * 64
        )
