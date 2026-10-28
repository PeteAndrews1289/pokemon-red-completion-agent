"""ROM-free prospective preparation facts, not downstream utility learning."""

import copy
from dataclasses import replace

import pytest
from test_red_player_lesson_runtime import fixture

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.player_option_challenge import OptionChallenge
from pokemon_red_completion.player_option_preparation import OptionPreparation
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_native_curriculum import (
    PREPARATION_OUTCOME_SCHEMA,
    NativeCurriculumInput,
    curriculum_projection,
    load_native_curriculum,
    reconstruct_native_curriculum,
)
from pokemon_red_completion.red_player_lesson_runtime import record_native_player_lesson


def observe(_rt, _binding, boundary):
    member = boundary.lesson_snapshot["party"][0]
    return OptionPreparation(
        member["level"], 22, 2648, member["hp"] / member["max_hp"], None, True, False, 36
    )


@pytest.mark.parametrize(
    "kind", [GoalKind.DEVELOP_TEAM, GoalKind.RESTORE_TEAM, GoalKind.ADVANCE_STORY]
)
@pytest.mark.parametrize("challenge", [False, True])
def test_preparation_record_matches_inference_and_preserves_atomic_outcome(
    tmp_path, monkeypatch, kind, challenge
):
    store, emulator, kwargs = fixture(tmp_path, monkeypatch, kind=kind)
    legacy = record_native_player_lesson(store, **kwargs, preflight_only=True)
    callback = observe if kind is GoalKind.DEVELOP_TEAM else lambda *_: None
    extra = dict(observe_preparation=callback)
    if challenge:
        extra["observe_challenge"] = lambda *_: OptionChallenge.from_levels(
            combat_levels=(20,), opponent_levels=(21, 24)
        )
    preflight = record_native_player_lesson(store, **kwargs, **extra, preflight_only=True)
    assert emulator.frame_count == 0 and not preflight["admitted"]
    assert preflight["declaration_sha256"] != legacy["declaration_sha256"]
    result = record_native_player_lesson(store, **kwargs, **extra)
    assert result["admitted"] and result["succeeded"]
    row = load_native_curriculum(store, NativeCurriculumInput(**result["outcome"]))
    context, candidate = curriculum_projection(preflight["declaration"])
    assert row.feature_version == 7
    assert row.features == candidate.vector(context, feature_version=7)
    # Change only the prospective representation, never historical reward semantics.
    from pokemon_red_completion.red_native_curriculum import READINESS_OUTCOME_SCHEMA

    outcome = store.find_sealed_record(
        "rnc-outcome-" + result["outcome"]["outcome_sha256"],
        expected_kind="red_native_curriculum_outcome",
    ).read()
    legacy_outcome = dict(
        outcome,
        schema=READINESS_OUTCOME_SCHEMA,
        declaration_sha256=legacy["declaration_sha256"],
    )
    assert row.outcome == reconstruct_native_curriculum(
        legacy["declaration"], legacy_outcome
    ).outcome
    assert (
        candidate.preparation is not None
        if kind is GoalKind.DEVELOP_TEAM
        else candidate.preparation is None
    )
    assert row.outcome.completion_gain == 0  # Never a fabricated registration.
    if kind is GoalKind.DEVELOP_TEAM:
        assert row.outcome.dependency_unlock_gain == 0  # No story completion.
    assert "red-preparation:" not in str(row.public_dict())
    assert "objective-" not in str(row.public_dict())


@pytest.mark.parametrize("mutation", ["level", "target", "hp", "pp", "untyped", "input", "extra"])
def test_preparation_preflight_rejects_mismatched_facts_before_input(
    tmp_path, monkeypatch, mutation
):
    store, emulator, kwargs = fixture(tmp_path, monkeypatch, kind=GoalKind.DEVELOP_TEAM)

    def callback(rt, binding, boundary):
        facts = observe(rt, binding, boundary)
        if mutation == "input":
            rt.emulator.tick(1)
        if mutation == "untyped":
            return facts.public_dict()
        changes = {
            "level": {"current_level": 19},
            "target": {"target_level": 23},
            "hp": {"hp_fraction": 0.5},
            "pp": {"pp_fraction": 0.5},
        }
        return replace(facts, **changes.get(mutation, {}))

    if mutation == "extra":
        pre = record_native_player_lesson(
            store, **kwargs, observe_preparation=callback, preflight_only=True
        )
        pre["declaration"]["downstream_success"] = True
        with pytest.raises(ValueError):
            curriculum_projection(pre["declaration"])
    else:
        with pytest.raises((ValueError, TypeError, RuntimeError)):
            record_native_player_lesson(
                store, **kwargs, observe_preparation=callback, preflight_only=True
            )
    assert emulator.frame_count == 0


def test_preparation_partial_progress_stays_failed_and_cannot_rename_target(tmp_path, monkeypatch):
    store, _, kwargs = fixture(tmp_path, monkeypatch, kind=GoalKind.DEVELOP_TEAM)
    plan = record_native_player_lesson(
        store, **kwargs, observe_preparation=observe, preflight_only=True
    )["declaration"]
    result = dict(
        schema=PREPARATION_OUTCOME_SCHEMA,
        declaration_sha256=canonical_sha256(plan),
        after=copy.deepcopy(plan["before"]),
        succeeded=False,
        trace=[dict(ordinal=0, before_frame=0, after_frame=100, succeeded=True)],
        terminal_state_sha256="f" * 64,
        interventions_during_execution=[],
        native_audit=dict(
            before_sha256=plan["source"]["state_sha256"],
            terminal_sha256="f" * 64,
            input_frames=0,
            passed=True,
        ),
        player_lesson=copy.deepcopy(plan["player_lesson"]["before"]),
    )
    result["after"]["semantic_observation"]["input_ready"] = True
    result["player_lesson"]["party"][0]["experience"] += 100
    row = reconstruct_native_curriculum(plan, result)
    assert not row.outcome.verified_success and row.outcome.completion_gain == 0
    assert row.outcome.dependency_unlock_gain == 0 and row.outcome.action_cost > 0
    result["succeeded"] = True
    with pytest.raises(ValueError, match="selected-goal progress"):
        reconstruct_native_curriculum(plan, result)
    plan["player_lesson"]["target"]["level"] = 21
    with pytest.raises(ValueError, match="preparation facts"):
        curriculum_projection(plan)


def test_nontraining_option_cannot_claim_another_members_preparation(tmp_path, monkeypatch):
    store, emulator, kwargs = fixture(tmp_path, monkeypatch)
    with pytest.raises(TypeError):
        record_native_player_lesson(
            store, **kwargs, observe_preparation=observe, preflight_only=True
        )
    assert emulator.frame_count == 0
