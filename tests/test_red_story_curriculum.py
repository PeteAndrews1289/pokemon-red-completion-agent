"""Real ROM-free recordings: curriculum is outcome evidence, never a fake choice."""

from copy import deepcopy
from dataclasses import replace

import numpy as np
import pytest
from test_living_dex_option_value import _example, _settled
from test_red_player_training import _episode

from pokemon_red_completion.goal_manager import GoalDecisionOutcome
from pokemon_red_completion.living_dex_option_value import (
    LivingDexCurriculumOutcomeExample,
    LivingDexOptionMenu,
    LivingDexOptionValueModel,
    LivingDexOutcomeStatus,
    evaluate_living_dex_option_value,
    fit_living_dex_option_value,
    living_dex_option_train_dataset_sha256,
)
from pokemon_red_completion.red_player_checkpoint import CHECKPOINT_KIND, checkpoint_record_id
from pokemon_red_completion.red_player_training import CURRICULUM_EVENT, TRAINING_EVENT
from pokemon_red_completion.red_player_training_dataset import load_red_player_training_episode
from pokemon_red_completion.red_player_training_plan import (
    CONTINUATION_TRAINING_PLAN_SCHEMA,
    RedPlayerTrainingPlan,
    declare_completion_dose,
    declare_story_curriculum,
)
from pokemon_red_completion.trajectory import SparseEvent
from pokemon_red_completion.trajectory_io import EpisodeTrajectorySink


def curriculum_plan(store, plan):
    # Parent serialization itself is tested by checkpoint tests; this is a real
    # sealed training-lineage/header join, not a stub of admission.
    writer = store.begin_episode("parent-story")
    sink = EpisodeTrajectorySink(writer, "parent-story", "pokemon.red", durable_writes=True)
    sink.write_episode_header(
        metadata={"split": {"partition": "train", "root_lineage_id": "goal-root-1"}}
    )
    sink.record_event(
        SparseEvent("parent-terminal", "parent-story", 0, "terminal", {"status": "complete"})
    )
    sink.finalize()
    parent = writer.complete()
    checkpoint = store.publish_sealed_record(
        checkpoint_record_id("parent-story"),
        kind=CHECKPOINT_KIND,
        record={
            "episode_id": "parent-story",
            "trajectory_manifest_sha256": parent.manifest_sha256,
            "state_sha256": plan.document["state_sha256"],
            "profile_sha256": plan.document["profile_sha256"],
        },
    )
    continuation = RedPlayerTrainingPlan(
        {
            **plan.document,
            "schema": CONTINUATION_TRAINING_PLAN_SCHEMA,
            "origin_state_sha256": "1" * 64,
            "origin_envelope_sha256": "2" * 64,
            "restore_profile_sha256": plan.document["profile_sha256"],
            "continuation_episode_id": "parent-story",
            "continuation_checkpoint_sha256": checkpoint.summary.record_sha256,
        }
    )
    return declare_story_curriculum(declare_completion_dose(continuation))


@pytest.mark.parametrize("status", list(GoalDecisionOutcome))
@pytest.mark.parametrize("zero", [False, True])
def test_real_singleton_story_records_only_observed_curriculum(tmp_path, status, zero):
    data = _episode(
        tmp_path, forced_story=True, plan_transform=curriculum_plan, status=status, zero=zero
    )
    assert data.examples == () and data.excluded_nonexploratory == 1
    assert data.excluded_zero_input == int(zero)
    assert len(data.curriculum_examples) == int(not zero)
    if zero:
        return
    row = data.curriculum_examples[0]
    assert row.public_dict()["comparative_choice"] is False
    assert "behavior_probabilities" not in row.public_dict()
    if status is GoalDecisionOutcome.INTERRUPTED:
        assert row.outcome.status is LivingDexOutcomeStatus.CENSORED
        assert row.outcome.target_vector is None
    else:
        assert row.outcome.verified_success is (status is GoalDecisionOutcome.SUCCEEDED)
        assert row.outcome.dependency_unlock_gain == (
            pytest.approx(0.1) if status is GoalDecisionOutcome.SUCCEEDED else 0.0
        )
        assert row.outcome.completion_gain == 0
        assert row.outcome.action_cost == pytest.approx(1 / 30000)
        assert row.outcome.frame_cost == pytest.approx(60 / 3000000)


def test_historical_singleton_remains_zero_rows_and_cannot_opt_in_after_recording(tmp_path):
    store, plan, model, manifest = _episode(tmp_path, forced_story=True, return_inputs=True)
    reader = store.open_episode("goal-episode-1")
    assert not any(
        e.get("kind") in (CURRICULUM_EVENT, TRAINING_EVENT) for e in reader.iter_stream("events")
    )
    revised = curriculum_plan(store, plan)
    store.publish_sealed_record(
        f"rp-plan-{revised.plan_sha256}",
        kind="red_player_training_plan",
        record=dict(revised.document),
    )
    with pytest.raises(ValueError, match="header differs"):
        load_red_player_training_episode(
            store,
            episode_id="goal-episode-1",
            expected_manifest_sha256=manifest.manifest_sha256,
            plan=revised,
            behavior_model=model,
        )


def test_opted_in_actual_choice_is_not_duplicated_as_curriculum(tmp_path):
    data = _episode(tmp_path, plan_transform=curriculum_plan)
    assert len(data.examples) == 1 and data.curriculum_examples == ()


def test_unreadable_curriculum_is_retained_but_has_no_fit_target(tmp_path):
    data = _episode(
        tmp_path, plan_transform=curriculum_plan, forced_story=True, unreadable_after=True
    )
    assert data.examples == () and len(data.curriculum_examples) == 1
    row = data.curriculum_examples[0]
    assert row.outcome.censor_reason.value == "observation_failed"
    assert row.outcome.target_vector is None


@pytest.mark.parametrize("failure", [False, True])
def test_real_curriculum_fit_roundtrip_retains_prior_choices_and_separate_inventory(
    tmp_path,
    monkeypatch,
    failure,
):
    from test_red_player_training_fit import _fit

    from pokemon_red_completion.provenance import canonical_sha256
    from pokemon_red_completion.red_player_incremental_fit import load_prior_player_inventory
    from pokemon_red_completion.red_player_model import load_player_goal_model_record_bytes
    from pokemon_red_completion.red_player_training_fit import fit_red_player_update

    store, choices, prior, request, result = _fit(
        tmp_path,
        monkeypatch,
        forced_story=True,
        plan_transform=curriculum_plan,
        failure=failure,
        optional_recovery=True,
    )
    assert result["new_settled_examples"] == 1
    assert result["curriculum_outcomes"] == 1
    assert result["comparative_choice_outcomes"] == 2
    assert result["curriculum_is_comparative_evidence"] is False
    assert result["authority_promotions"] == 0
    sha = result["model"]["model_sha256"]
    record = store.find_sealed_record(f"rp-model-{sha}", expected_kind="red_player_model")
    loaded = load_player_goal_model_record_bytes(record.read_bytes(), expected_model_sha256=sha)
    corpus = store.find_sealed_record(
        f"rp-corpus-{loaded.corpus_sha256}", expected_kind="red_player_training_corpus"
    ).read()
    assert len(corpus["examples"]) == 2 and len(corpus["curriculum_examples"]) == 1
    assert {canonical_sha256(row.public_dict()) for row in choices}.issubset(
        loaded.retained_example_sha256
    )
    curriculum_row = corpus["curriculum_examples"][0]
    assert canonical_sha256(curriculum_row) in loaded.retained_example_sha256
    episodes, regional = load_prior_player_inventory(
        store, loaded, lambda _: request.behavior_record
    )
    assert episodes == (request,) and regional == ()
    reconstructed = load_red_player_training_episode(
        store,
        episode_id=request.episode_id,
        expected_manifest_sha256=request.manifest_sha256,
        plan=request.plan,
        behavior_model=request.behavior_record.model,
    )
    assert reconstructed.curriculum_examples[0].public_dict() == curriculum_row
    assert reconstructed.examples == ()
    with pytest.raises(ValueError, match="additional settled"):
        fit_red_player_update(
            store,
            prior=loaded,
            episodes=episodes,
            source_commit="e" * 40,
            source_bundle_sha256="f" * 64,
        )


@pytest.mark.parametrize(
    "damage",
    [
        "features",
        "target",
        "actions",
        "frames",
        "interval",
        "contract",
        "probability",
        "top_probability",
        "boolean_weight",
        "boolean_version",
        "censor_after",
        "duplicate",
        "missing",
    ],
)
def test_curriculum_mutations_fail_admission(tmp_path, damage):
    def mutate(streams):
        event = next(e for e in streams["events"] if e.get("kind") == CURRICULUM_EVENT)
        payload = event["payload"]
        if damage == "features":
            payload["example"]["features"][0] += 0.25
        elif damage == "target":
            payload["example"]["outcome"]["target_values"][2] = 0.9
        elif damage == "actions":
            payload["actions"] += 1
        elif damage == "frames":
            payload["frames"] += 1
        elif damage == "interval":
            payload["start_step"] += 1
        elif damage == "contract":
            payload["curriculum_contract"] = "retroactive"
        elif damage == "probability":
            payload["example"]["behavior_probabilities"] = [1.0]
        elif damage == "top_probability":
            payload["behavior_probabilities"] = [1.0]
        elif damage == "boolean_weight":
            payload["example"]["regression_weight"] = True
        elif damage == "boolean_version":
            payload["example"]["feature_version"] = True
        elif damage == "censor_after":
            payload["observation_failed"] = True
        elif damage == "duplicate":
            streams["events"].append(deepcopy(event))
        else:
            streams["events"].remove(event)

    with pytest.raises(ValueError):
        _episode(tmp_path, forced_story=True, plan_transform=curriculum_plan, mutate=mutate)


def test_mixed_regression_has_unit_curriculum_weight_without_changing_choice_rows():
    choices = tuple(
        _example(
            i,
            selected=i,
            outcome=_settled(success=bool(i), completion=i * 0.1, unlock=0, action_cost=0.2),
        )
        for i in range(2)
    )
    original = [row.public_dict() for row in choices]
    base = fit_living_dex_option_value(choices)
    row = LivingDexCurriculumOutcomeExample(
        "f" * 64,
        "train",
        1,
        choices[0].selected_vector,
        _settled(success=True, completion=0, unlock=0.7, action_cost=0.8),
    )
    fit = fit_living_dex_option_value(choices, curriculum_examples=(row,))
    assert fit.model.settled_examples == 3
    assert fit.model.objective == "selected-arm-ips-plus-unit-curriculum-multioutcome-ridge-v1"
    assert fit.model.model_sha256 != base.model.model_sha256
    assert (
        LivingDexOptionValueModel.from_dict(fit.model.to_dict()).model_sha256
        == fit.model.model_sha256
    )
    assert [r.public_dict() for r in choices] == original
    weights = [choices[0].importance_weight(), choices[1].importance_weight(), 1.0]
    expected_mean = np.average(
        [choices[0].selected_vector, choices[1].selected_vector, row.features],
        axis=0,
        weights=weights,
    )
    np.testing.assert_allclose(fit.model.feature_mean, expected_mean)
    assert living_dex_option_train_dataset_sha256(choices) == base.model.train_dataset_sha256
    assert (
        evaluate_living_dex_option_value(
            fit.model, choices, expected_partition="train", curriculum_examples=(row,)
        ).settled_examples
        == 3
    )
    with pytest.raises(ValueError, match="training-only"):
        evaluate_living_dex_option_value(
            fit.model,
            tuple(replace(r, partition="development") for r in choices),
            curriculum_examples=(row,),
        )
    with pytest.raises(ValueError, match="identities repeat"):
        fit_living_dex_option_value(
            choices, curriculum_examples=(replace(row, decision_sha256=choices[0].decision_sha256),)
        )
    with pytest.raises(ValueError, match="two candidates"):
        LivingDexOptionMenu(choices[0].menu.context, (choices[0].menu.candidates[0],))
