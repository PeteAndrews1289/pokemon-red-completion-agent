"""The forward stream is opt-in and cannot silently expand gameplay authority."""

import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_red_goal_context_profile import _payload, _provider

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalMechanic,
    parse_red_goal_context_profile,
)

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/run_paired_red_bounded_player.py"


@pytest.fixture
def module():
    return runpy.run_path(str(SCRIPT))


def readiness(
    *, recovery=RedGoalMechanic.FIELD_PP_RESTORE, parameters=None, objective="defeat_champion"
):
    profile = parse_red_goal_context_profile(
        _payload(
            _provider(
                GoalKind.ADVANCE_STORY,
                RedGoalMechanic.MIDGAME_STORY,
                {"trainer_objective": objective},
            ),
            _provider(GoalKind.RESTORE_TEAM, recovery, parameters),
            _provider(GoalKind.RECOVER_CONTROL, RedGoalMechanic.CONTROL_RECOVERY),
        )
    )
    return SimpleNamespace(
        forward_story_objective=objective,
        forward_resource_budget=2,
        training_plan=SimpleNamespace(document={"behavior_policy_id": "frozen-policy", "seed": 1}),
        decision_limit=2,
        causal_record=SimpleNamespace(model=SimpleNamespace(feature_version=3)),
        profile=profile,
        completion_dose=False,
        model_sha256="a" * 64,
        source_bundle_sha256="b" * 64,
    )


def test_no_opt_in_means_no_forward_contract_or_changed_authority(module):
    old = SimpleNamespace(training_plan=None)
    assert module["_forward_goal_plan"](old) is None
    assert module["_forward_goal_header"](old) == {}
    old.forward_resource_budget = 2
    with pytest.raises(RuntimeError, match="requires_objective"):
        module["_forward_goal_plan"](old)


@pytest.mark.parametrize(
    "recovery,parameters",
    [
        (RedGoalMechanic.FIELD_PP_RESTORE, {}),
        (RedGoalMechanic.FIELD_RESTORE, {"affordable_single_item": True}),
    ],
)
def test_forward_declaration_uses_actual_limits_and_recording_only_authority(
    module,
    recovery,
    parameters,
):
    ready = readiness(recovery=recovery, parameters=parameters)
    plan = module["_forward_goal_plan"](ready)
    assert plan.max_actions == 12000 and plan.max_frames == 1200000
    assert plan.max_resources == plan.max_macros == 2
    header = module["_forward_goal_header"](ready)
    assert header["forward_goal_plan"] == plan.public_dict()
    assert header["forward_goal_plan_sha256"] == plan.sha256
    assert header["forward_goal_authority"] == "recording-only-existing-actor"
    assert header["forward_story_objective"] == "defeat_champion"


@pytest.mark.parametrize(
    "field,value",
    [
        ("training_plan", None),
        ("decision_limit", 1),
        ("forward_resource_budget", None),
        ("forward_resource_budget", True),
        ("forward_resource_budget", 1),
        ("causal_record", None),
        ("routed_recovery", True),
        ("trainer_funding", True),
        ("trainer_pending_recovery", True),
        ("regional_trainer_funding", True),
        ("routed_resource_goals", True),
    ],
)
def test_unsupported_forward_scope_rejects_before_execution(module, field, value):
    ready = readiness()
    setattr(ready, field, value)
    with pytest.raises(RuntimeError, match="forward_goal_scope"):
        module["_forward_goal_plan"](ready)


def test_guided_curriculum_and_legacy_features_cannot_be_forward_choices(module):
    ready = readiness()
    ready.training_plan.document["curriculum_contract"] = "guided"
    with pytest.raises(RuntimeError, match="forward_goal_scope"):
        module["_forward_goal_plan"](ready)
    del ready.training_plan.document["curriculum_contract"]
    ready.causal_record.model.feature_version = 2
    with pytest.raises(RuntimeError, match="forward_goal_scope"):
        module["_forward_goal_plan"](ready)


def test_multi_item_healer_or_different_story_goal_cannot_enter_pilot(module):
    with pytest.raises(RuntimeError, match="single_item_recovery"):
        module["_forward_goal_plan"](readiness(recovery=RedGoalMechanic.FIELD_RESTORE))
    ready = readiness()
    ready.forward_story_objective = "defeat_lance"
    with pytest.raises(RuntimeError, match="story_binding_differs"):
        module["_forward_goal_plan"](ready)


@pytest.mark.parametrize("field", ["model_sha256", "source_bundle_sha256"])
def test_frozen_continuation_changes_when_executable_or_actor_changes(module, field):
    ready = readiness()
    first = module["_forward_goal_plan"](ready)
    setattr(ready, field, "c" * 64)
    assert module["_forward_goal_plan"](ready).continuation_sha256 != first.continuation_sha256


def test_continuation_binds_policy_and_profile_but_not_individual_rng_realization(module):
    ready = readiness()
    first = module["_forward_goal_plan"](ready)
    ready.training_plan.document["seed"] = 2
    assert module["_forward_goal_plan"](ready) == first
    ready.training_plan.document["behavior_policy_id"] = "other-policy"
    assert module["_forward_goal_plan"](ready).continuation_sha256 != first.continuation_sha256
    different_profile = readiness(
        recovery=RedGoalMechanic.FIELD_RESTORE,
        parameters={"affordable_single_item": True},
    )
    assert module["_forward_goal_plan"](different_profile).continuation_sha256 != (
        first.continuation_sha256
    )
