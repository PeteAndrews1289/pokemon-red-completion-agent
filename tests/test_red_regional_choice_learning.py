import json
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_goal_resource_quote import _quote, _quoted_question, _supply_model
from test_red_player_training import _episode, _facts
from test_red_regional_acquisition import _candidate, _observation

import pokemon_red_completion.red_regional_choice_learning as learning
from pokemon_red_completion.goal_manager import GoalDecisionOutcome
from pokemon_red_completion.goal_search_memory import GoalSearchMemory
from pokemon_red_completion.living_dex_goal_model_record import LivingDexGoalModelRecord
from pokemon_red_completion.living_dex_option_value import (
    LivingDexObservedArmExample,
    living_dex_option_context_from_goal_situation,
    upgrade_option_value_model_for_search_history,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_goal_context_profile import (
    _thaw,
    build_red_goal_context_profile_payload,
)
from pokemon_red_completion.red_player_checkpoint import CHECKPOINT_KIND, checkpoint_record_id
from pokemon_red_completion.red_regional_acquisition import (
    regional_acquisition_menu,
    sample_regional_acquisition,
)


def _recorded(tmp_path, *, failed=False, omit_commit=False, registered_pair=None):
    candidates = (_candidate(), _candidate("wild:Route11:grass", 0.7))
    question = _quoted_question(_quote())
    source_menu = regional_acquisition_menu(_observation(), candidates, GoalSearchMemory())
    menu = replace(
        source_menu,
        context=living_dex_option_context_from_goal_situation(question.situation),
        candidates=tuple(
            replace(
                row,
                features=replace(
                    row.features,
                    storage_cost=question.situation.storage_pressure,
                ),
            )
            for row in source_menu.candidates
        ),
    )
    model = upgrade_option_value_model_for_search_history(_supply_model())
    selected = sample_regional_acquisition(model, menu, seed=17)
    profile = candidates[selected["selected_candidate_index"]].profile
    before, after = _facts(question), _facts(question, registered=2, balls=9)
    choice_schema = learning.REGIONAL_CHOICE_SCHEMA
    outcome_schema = learning.REGIONAL_OUTCOME_SCHEMA
    plan_transform = None
    if registered_pair is not None:
        from pokemon_red_completion.red_player_training_plan import (
            REGISTERED_TRAINING_PLAN_SCHEMA,
            RedPlayerTrainingPlan,
        )
        from pokemon_red_completion.registered_collection import REGISTERED_OBJECTIVE

        before, after = (o.public_dict() for o in registered_pair)
        choice_schema = learning.REGISTERED_REGIONAL_CHOICE_SCHEMA
        outcome_schema = learning.REGISTERED_REGIONAL_OUTCOME_SCHEMA

        def plan_transform(store, plan):
            return RedPlayerTrainingPlan(
                {
                    **plan.document,
                    "schema": REGISTERED_TRAINING_PLAN_SCHEMA,
                    "objective": REGISTERED_OBJECTIVE,
                    "maximum_actions": 30_000,
                    "maximum_frames": 3_000_000,
                    "registration_binding_sha256": before["registration"]["binding_sha256"],
                    "origin_state_sha256": "a" * 64,
                    "origin_envelope_sha256": "b" * 64,
                    "restore_profile_sha256": "c" * 64,
                    "continuation_episode_id": "parent",
                    "continuation_checkpoint_sha256": "d" * 64,
                }
            )

    committed = {}

    def declare(store, plan, actual_model):
        assert actual_model.model_sha256 == model.model_sha256
        record = store.publish_sealed_record(
            learning.regional_choice_record_id("goal-episode-1"),
            kind=learning.REGIONAL_CHOICE_KIND,
            record={
                "schema": choice_schema,
                "episode_id": "goal-episode-1",
                "parent_plan": dict(plan.document),
                "before": before,
                "menu": menu.policy_dict(),
                "selection": selected,
                "candidates": [
                    {
                        "source_id": row.source_id,
                        "profile_sha256": row.profile.profile_sha256,
                        "profile": json.loads(
                            build_red_goal_context_profile_payload(
                                profile_id=row.profile.profile_id,
                                providers=tuple(
                                    (spec.kind, spec.mechanic, _thaw(spec.parameters))
                                    for spec in row.profile.providers
                                ),
                            )
                        ),
                        "estimated_effort": row.binding.estimated_effort,
                        "estimated_risk": row.binding.estimated_risk,
                    }
                    for row in candidates
                ],
                "controller_input_before_commit": False,
                "independent_evaluation": False,
            },
        )
        committed["choice"] = record
        return (
            {} if omit_commit else {"regional_choice_record_sha256": record.summary.record_sha256}
        )

    store, plan, behavior, complete = _episode(
        tmp_path,
        status=GoalDecisionOutcome.FAILED if failed else GoalDecisionOutcome.SUCCEEDED,
        history=True,
        acquire_only=True,
        plan_profile_sha=profile.profile_sha256,
        before_episode=declare,
        return_inputs=True,
        plan_transform=plan_transform,
        registration_observations=registered_pair,
    )
    status = "failed" if failed else "succeeded"
    checkpoint = store.publish_sealed_record(
        checkpoint_record_id("goal-episode-1"),
        kind=CHECKPOINT_KIND,
        record={
            "episode_id": "goal-episode-1",
            "trajectory_manifest_sha256": complete.manifest_sha256,
            "profile_sha256": plan.document["profile_sha256"],
            "original_state_sha256": plan.document["state_sha256"],
            "model_sha256": behavior.model_sha256,
            "context_origin": "training",
            "collection": after["registration"] if registered_pair else {"living_species": 2},
            "terminal_result": {
                "total_actions": 1,
                "total_frames": 60,
                "steps": [
                    {
                        "actions_executed": 1,
                        "frames_executed": 60,
                        "selected_kind": "acquire_species",
                        "status": status,
                        "failure_reason": "search_exhausted" if failed else None,
                        "collection_before": (
                            before["registration"]
                            if registered_pair
                            else {"required_specimens_sha256": "f" * 64}
                        ),
                        "collection_after": (
                            after["registration"] if registered_pair else {"living_species": 2}
                        ),
                    }
                ],
            },
        },
    )
    choice_sha = committed["choice"].summary.record_sha256
    outcome = learning.regional_observed_outcome(
        plan,
        before,
        after,
        succeeded=not failed,
        actions=1,
        frames=60,
        maximum_actions=plan.maximum_actions,
        maximum_frames=plan.maximum_frames,
    )
    example = LivingDexObservedArmExample(
        canonical_sha256(
            {
                "schema": choice_schema,
                "choice_record_sha256": choice_sha,
            }
        ),
        "train",
        menu,
        selected["selected_candidate_index"],
        tuple(selected["probabilities"]),
        outcome,
    )
    result = store.publish_sealed_record(
        learning.regional_outcome_record_id("goal-episode-1"),
        kind=learning.REGIONAL_OUTCOME_KIND,
        record={
            "schema": outcome_schema,
            "episode_id": "goal-episode-1",
            "choice_record_sha256": choice_sha,
            "manifest_sha256": complete.manifest_sha256,
            "terminal_checkpoint_sha256": checkpoint.summary.record_sha256,
            "after": after,
            "example": example.public_dict(),
        },
    )
    item = learning.RedRegionalChoiceInput(
        "goal-episode-1",
        choice_sha,
        result.summary.record_sha256,
        LivingDexGoalModelRecord(behavior, "d" * 64, "b" * 40, "c" * 64, 1, 1),
    )
    return store, item, example


@pytest.mark.parametrize("failed", [False, True])
def test_real_parent_trace_admits_only_the_selected_source_outcome(tmp_path, failed):
    store, item, expected = _recorded(tmp_path, failed=failed)
    actual = learning.load_red_regional_choice_example(store, item)
    assert actual.public_dict() == expected.public_dict()
    assert actual.outcome.verified_success is not failed
    assert actual.outcome.action_cost > 0
    assert actual.outcome.resource_cost > 0
    assert len(actual.behavior_probabilities) == 2 and min(actual.behavior_probabilities) > 0


def test_source_commit_must_be_in_parent_header_before_controller_trace(tmp_path):
    store, item, _ = _recorded(tmp_path, omit_commit=True)
    with pytest.raises(ValueError, match="before parent controller input"):
        learning.load_red_regional_choice_example(store, item)


@pytest.mark.parametrize(
    "damage",
    ["choice_sha", "outcome_sha", "sample", "profile", "target", "cost", "terminal", "extra_field"],
)
def test_record_and_semantic_mutations_are_distinguishable(tmp_path, damage):
    store, item, _ = _recorded(tmp_path)
    if damage.endswith("_sha"):
        item = replace(
            item,
            **{
                "choice_record_sha256" if damage == "choice_sha" else "outcome_record_sha256": "0"
                * 64,
            },
        )
        proxy = store
    else:
        original = store.find_sealed_record

        def changed(identity, **kwargs):
            record = original(identity, **kwargs)
            if record is None:
                return None
            doc = deepcopy(record.read())
            if identity == learning.regional_choice_record_id(item.episode_id):
                if damage == "sample":
                    doc["selection"]["probabilities"] = [0.9, 0.1]
                if damage == "profile":
                    for row in doc["candidates"]:
                        row["profile_sha256"] = "0" * 64
                if damage == "extra_field":
                    doc["future_hint"] = "not allowed"
            if identity == learning.regional_outcome_record_id(item.episode_id):
                if damage == "target":
                    doc["example"]["outcome"]["target_values"][0] = 0.0
                if damage == "terminal":
                    doc["terminal_checkpoint_sha256"] = "0" * 64
            if identity == checkpoint_record_id(item.episode_id) and damage == "cost":
                doc["terminal_result"]["steps"][0]["actions_executed"] = 2
            return SimpleNamespace(summary=record.summary, read=lambda: doc)

        proxy = SimpleNamespace(find_sealed_record=changed, open_episode=store.open_episode)
    with pytest.raises(ValueError):
        learning.load_red_regional_choice_example(proxy, item)
