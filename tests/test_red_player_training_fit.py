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
    fit_red_player_update,
)


def _prior(rows):
    model = fit_living_dex_option_value(rows).model
    return LivingDexGoalModelRecord(model, "a" * 64, "b" * 40, "c" * 64, 1, 1)


def _fit(tmp_path, monkeypatch, *, failure=False):
    store, plan, behavior, completed = _episode(
        tmp_path,
        status=GoalDecisionOutcome.FAILED if failure else GoalDecisionOutcome.SUCCEEDED,
        return_inputs=True,
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
def test_fit_uses_real_episode_reader_and_retains_prior_rows_including_negative(
    tmp_path, monkeypatch, failure
):
    store, rows, prior, request, result = _fit(tmp_path, monkeypatch, failure=failure)
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
