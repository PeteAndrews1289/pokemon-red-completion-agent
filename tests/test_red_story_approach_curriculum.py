"""ROM-free parity proofs; synthetic fixtures grant no native TRAIN credit."""

import copy
from dataclasses import replace

import pytest
from test_red_player_story_unit import unit_records

from pokemon_red_completion.goal_manager import GoalManagerQuestion
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.living_dex_goal_policy import project_living_dex_goal_candidate
from pokemon_red_completion.living_dex_option_value import curriculum_features, option_feature_names
from pokemon_red_completion.player_option_challenge import OptionChallenge
from pokemon_red_completion.player_readiness import PlayerReadiness
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_live_option_menu import (
    build_red_live_option_set,
    supplemental_live_option,
)
from pokemon_red_completion.red_native_curriculum import (
    APPROACH_STORY_UNIT_CONTRACT,
    APPROACH_STORY_UNIT_OUTCOME_SCHEMA,
    APPROACH_STORY_UNIT_PLAN_SCHEMA,
    NativeCurriculumInput,
    curriculum_projection,
    load_native_curriculum,
    reconstruct_native_curriculum,
)
from pokemon_red_completion.red_player_economy import restore_snapshot


def approach_records(tmp_path):
    plan, result = unit_records(tmp_path, arrival=True)
    plan.update(
        schema=APPROACH_STORY_UNIT_PLAN_SCHEMA,
        contract=APPROACH_STORY_UNIT_CONTRACT,
        story_approach_only=True,
    )
    result.update(
        schema=APPROACH_STORY_UNIT_OUTCOME_SCHEMA, declaration_sha256=canonical_sha256(plan)
    )
    return plan, result


def live_approach_vector(plan):
    """Use the real ordinary/supplemental live menu, without scoring it."""
    question = GoalManagerQuestion.from_policy_input(plan["question"])
    old = question.opportunities[plan["selected_index"]]
    binding = ExecutableGoalBinding(
        old.binding_ref,
        old.kind,
        old.estimated_effort,
        old.estimated_risk,
        lambda: GoalExecutionReport(0, 0, {}),
        lambda _: GoalVerification.succeeded(),
        resource_quote=old.resource_quote,
        story_approach_only=True,
    )
    other = replace(binding, binding_ref="private-comparison", story_approach_only=False)
    readiness = PlayerReadiness.from_public(plan["readiness"])
    extra = project_living_dex_goal_candidate(
        question,
        plan["selected_index"],
        feature_version=15,
        binding_ref=other.binding_ref,
        readiness=readiness,
    )
    challenge = OptionChallenge.from_public(plan["challenge"])
    options = build_red_live_option_set(
        situation=question.situation,
        binding_set=GoalBindingSet(question.opportunities, (binding,)),
        supplements=(supplemental_live_option(other, extra),),
        readiness=readiness,
        challenges={binding.binding_ref: challenge, other.binding_ref: challenge},
        model_feature_version=15,
        ordering_seed_sha256="f" * 64,
        economy_snapshot=restore_snapshot(plan["economy_before"]),
        target_cash=plan["target_cash"],
    )
    index = next(i for i, b in enumerate(options.bindings) if b.binding_ref == binding.binding_ref)
    assert option_feature_names(15)[: len(option_feature_names(9))] == option_feature_names(9)
    return options.menu.candidate_vector(index, feature_version=15)[: len(option_feature_names(9))]


def test_existing_v8_bytes_and_row_identity_remain_exact(tmp_path):
    plan, result = unit_records(tmp_path, arrival=True)
    row = reconstruct_native_curriculum(plan, result)
    assert (
        canonical_sha256(plan) == "5e28f43d2f20f97e80afbcd9a5da35e931d05f36759d0334c0f58ce9344527c6"
    )
    assert (
        canonical_sha256(result)
        == "2fe9d77e7822752afecbac65ef8f5852aace8b6e659fb426ed7bfd37b530905d"
    )
    assert (
        canonical_sha256(row.public_dict())
        == "9b49cda39beb75874d799b5f68e28b62f3e0985b66c6af814ceb686a33c0dcc3"
    )
    assert curriculum_projection(plan)[1].features.dependency_unlock_gain == 1.0
    # Historical rows stay historical: they are not silently relabeled as approaches.
    assert tuple(curriculum_features(row, 9)) != live_approach_vector(plan)


def test_approach_projection_matches_live_v15_named_prefix_exactly(tmp_path):
    plan, result = approach_records(tmp_path)
    row = reconstruct_native_curriculum(plan, result)
    assert tuple(curriculum_features(row, 9)) == live_approach_vector(plan)
    assert curriculum_projection(plan)[1].features.dependency_unlock_gain == 0.5
    assert row.outcome.verified_success
    assert row.outcome.completion_gain == row.outcome.dependency_unlock_gain == 0
    assert row.outcome.action_cost > 0 and row.outcome.frame_cost > 0
    assert (
        result["player_lesson"]["completed_objectives"]
        == plan["player_lesson"]["before"]["completed_objectives"]
    )
    assert "story_approach_only" not in str(row.public_dict())


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "false",
        "integer",
        "string",
        "old_schema",
        "wrong_kind",
        "missing_endpoint",
        "already_there",
        "wrong_arrival",
        "wrong_outcome_schema",
    ],
)
def test_new_contract_rejects_forged_scope_or_endpoint(tmp_path, fault):
    plan, result = approach_records(tmp_path)
    if fault == "missing":
        plan.pop("story_approach_only")
    elif fault in {"false", "integer", "string"}:
        plan["story_approach_only"] = {"false": False, "integer": 1, "string": "yes"}[fault]
    elif fault == "old_schema":
        plan["schema"] = "pokemon.red.native-curriculum-declaration.v8"
    elif fault == "wrong_kind":
        plan["question"]["candidates"][0]["kind"] = "restore_team"
    elif fault == "missing_endpoint":
        plan.pop("story_unit")
    elif fault == "already_there":
        plan["story_unit"]["before"] = copy.deepcopy(result["story_unit"])
    elif fault == "wrong_arrival":
        result["story_unit"]["map_id"] = 3
    else:
        result["schema"] = "pokemon.red.native-curriculum-outcome.v8"
    result["declaration_sha256"] = canonical_sha256(plan)
    with pytest.raises(ValueError):
        reconstruct_native_curriculum(plan, result)


def recorder_fixture(tmp_path, monkeypatch):
    from test_red_player_lesson_runtime import fixture

    import pokemon_red_completion.red_player_story_unit as unit

    store, emulator, kwargs = fixture(tmp_path, monkeypatch, record_factory=unit_records)
    kwargs["observe_challenge"] = lambda *args: OptionChallenge(False, False, 0.0, 0.0, 0.0)
    kwargs["story_unit_target"] = dict(kind="events", map_id=88, events=[1360, 1371, 1373])
    monkeypatch.setattr(
        unit,
        "capture_story_unit",
        lambda rt, target: dict(
            map_id=88,
            at=[4, 1],
            events=[bool(emulator.frame_count)] * 3,
        ),
    )

    def enumerate_bindings(runtime, actions, observation):
        original = runtime.enumerator(actions).enumerate(observation)
        binding = replace(original.bindings[0], story_approach_only=True)
        return GoalBindingSet(original.opportunities, (binding,))

    kwargs["enumerate_bindings"] = enumerate_bindings
    return store, emulator, kwargs


def test_recorder_uses_actual_binding_scope_and_roundtrips_same_features(tmp_path, monkeypatch):
    import pokemon_red_completion.red_player_lesson_runtime as runtime

    store, emulator, kwargs = recorder_fixture(tmp_path, monkeypatch)
    before = emulator.save_state_bytes()
    preflight = runtime.record_native_player_lesson(store, **kwargs, preflight_only=True)
    plan = preflight["declaration"]
    assert plan["schema"] == APPROACH_STORY_UNIT_PLAN_SCHEMA
    assert plan["story_approach_only"] is True
    assert emulator.save_state_bytes() == before and preflight["input_frames"] == 0
    expected = live_approach_vector(plan)
    actual = runtime.record_native_player_lesson(store, **kwargs)
    assert actual["admitted"] and actual["succeeded"]
    assert actual["declaration_sha256"] == preflight["declaration_sha256"]
    row = load_native_curriculum(store, NativeCurriculumInput(**actual["outcome"]))
    assert tuple(curriculum_features(row, 9)) == expected
    assert row.outcome.dependency_unlock_gain == 0
    assert not row.public_dict()["comparative_choice"]


def test_approach_without_endpoint_is_rejected_before_input(tmp_path, monkeypatch):
    import pokemon_red_completion.red_player_lesson_runtime as runtime

    store, emulator, kwargs = recorder_fixture(tmp_path, monkeypatch)
    kwargs.pop("story_unit_target")
    with pytest.raises(ValueError, match="declared native story-unit endpoint"):
        runtime.record_native_player_lesson(store, **kwargs)
    assert emulator.frame_count == 0 and not emulator.pressed_buttons
