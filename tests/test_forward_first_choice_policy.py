"""No cartridge, future outcome, or simulated controller is needed by the actor."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_goal_resource_quote import _quote, _quoted_question, _supply_model

from pokemon_red_completion.forward_first_choice_policy import (
    FORWARD_FIRST_CHOICE_POLICY_ID,
    FirstChoiceForwardTrainingPolicy,
)
from pokemon_red_completion.forward_goal import ForwardGoalPlan
from pokemon_red_completion.forward_goal_learning import ForwardGoalModel
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalOpportunity,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_composition_runtime import CompositionBudgetCheckpoint
from pokemon_red_completion.living_dex_goal_policy import LivingDexGoalShadowPolicy
from pokemon_red_completion.living_dex_option_value import (
    option_feature_names,
    upgrade_option_value_model_for_optional_recovery,
)
from pokemon_red_completion.living_dex_player_exploration import ExploringLivingDexGoalPolicy


def fixture(*, acquire_completion=0.4, acquire_cost=0.0, context_weight=0.0):
    plan = ForwardGoalPlan("synthetic-story", "a" * 64, "b" * 64, 1000, 10000, 2, 2)
    names = option_feature_names(3)
    width = (1 + 4 + 1) * (len(names) + 1) - 1
    weights = [(0.0, 0.0)] * width
    # One context + four budget features precede the unmodified candidate row.
    weights[5 + names.index("kind.acquire")] = (acquire_completion, acquire_cost)
    # Literal first context × acquire interaction; no outcome-dependent input.
    weights[5 + len(names) + names.index("kind.acquire")] = (context_weight, 0.0)
    model = ForwardGoalModel(
        plan.contract,
        ("readiness",),
        names,
        (0.0,) * width,
        (1.0,) * width,
        tuple(weights),
        (0.5, 0.2),
        "c" * 64,
        4,
        0,
        1.0,
        10.0,
    )
    tail = upgrade_option_value_model_for_optional_recovery(_supply_model())
    logs = []
    counters = [0, 0]
    meter = SimpleNamespace(checkpoint=lambda: CompositionBudgetCheckpoint(*counters))
    policy = FirstChoiceForwardTrainingPolicy(
        model,
        plan,
        tail,
        17,
        lambda: (0.25,),
        meter,
        logs.append,
        True,
    )
    return SimpleNamespace(
        policy=policy,
        model=model,
        tail=tail,
        plan=plan,
        logs=logs,
        counters=counters,
        question=_quoted_question(_quote()),
    )


def test_forward_head_really_controls_first_choice_not_tail_recommendation():
    f = fixture()
    assert LivingDexGoalShadowPolicy(f.tail).select(f.question).kind is GoalKind.RESUPPLY
    assert f.policy.select(f.question).kind is GoalKind.ACQUIRE_SPECIES
    poisoned = fixture(acquire_completion=-0.4)
    assert poisoned.policy.select(poisoned.question).kind is GoalKind.RESUPPLY
    assert f.policy.forward_decisions == f.policy.decisions == 1
    assert not f.policy.training_eligible and not f.policy.poisoned
    record = f.logs[0]
    assert record["role"] == "forward_first"
    assert record["question_sha256"] == f.question.ordered_policy_input_sha256
    assert record["context"] == [0.25]
    assert record["predictions"] == [
        {"completion": 0.9, "cost": 0.2},
        {"completion": 0.5, "cost": 0.2},
    ]
    assert record["forward_model_sha256"] == f.model.sha256
    assert record["tail_model_sha256"] == f.tail.model_sha256
    assert record["fitted_continuation_sha256"] == "b" * 64
    assert "hidden-mart" not in str(record)
    metadata = f.policy.selection_metadata()
    assert metadata == {
        "schema": "pokemon.core.goal-manager-behavior-policy.v1",
        "behavior_policy_id": FORWARD_FIRST_CHOICE_POLICY_ID,
        "candidate_probabilities": [1.0, 0.0],
        "selected_probability": 1.0,
        "base_selected_probability": 1.0,
        "exploration_mix": 0.0,
        "temperature": 1.0,
    }
    metadata["candidate_probabilities"][0] = 0.0
    assert f.policy.selection_metadata()["candidate_probabilities"] == [1.0, 0.0]


def test_candidate_permutation_preserves_semantic_choice_and_actual_index():
    f = fixture()
    reverse = replace(f.question, opportunities=tuple(reversed(f.question.opportunities)))
    choice = f.policy.select(reverse)
    assert choice.kind is GoalKind.ACQUIRE_SPECIES and choice.selected_index == 1
    assert f.logs[0]["selected_menu_index"] == 1
    assert f.policy.selection_metadata()["candidate_probabilities"] == [0.0, 1.0]


@pytest.mark.parametrize("cost,expected", [(0.1, 1), (-0.1, 0), (0.0, 0)])
def test_equal_completion_uses_cost_then_stable_index(cost, expected):
    f = fixture(acquire_completion=0.0, acquire_cost=cost)
    assert f.policy.select(f.question).selected_index == expected


def test_changed_current_context_can_reverse_preference_without_future_inputs():
    f = fixture(acquire_completion=-0.2, context_weight=0.4)
    assert f.policy.select(f.question).kind is GoalKind.RESUPPLY
    g = fixture(acquire_completion=-0.2, context_weight=0.4)
    g.policy.observe_context = lambda: (0.75,)
    assert g.policy.select(g.question).kind is GoalKind.ACQUIRE_SPECIES


def test_tail_is_first_draw_of_separately_seeded_old_policy_not_recursive_forward(monkeypatch):
    f = fixture()
    calls = []
    original = ForwardGoalModel.predict

    def predict(self, **kwargs):
        calls.append(kwargs)
        return original(self, **kwargs)

    monkeypatch.setattr(ForwardGoalModel, "predict", predict)
    f.policy.select(f.question)
    old = ExploringLivingDexGoalPolicy(f.tail, seed=17)
    expected = old.select(f.question)
    f.counters[:] = [19, 1200]  # Only actions between decisions are allowed.
    f.policy.observe_context = lambda: pytest.fail("tail must not ask the forward observer")
    assert f.policy.select(f.question) == expected
    assert f.policy.selection_metadata() == old.selection_metadata()
    assert len(calls) == 1 and len(f.logs) == 2
    assert f.logs[1]["role"] == "frozen_tail"
    assert "predictions" not in f.logs[1]
    assert f.policy.forward_decisions == f.policy.tail_decisions == 1
    assert f.policy.decisions == 2
    with pytest.raises(ValueError, match="exhausted"):
        f.policy.select(f.question)
    assert len(calls) == 1 and len(f.logs) == 2


@pytest.mark.parametrize("mode", ["safety", "partial", "unsupported", "singleton"])
def test_unsafe_or_incomplete_first_menu_rejects_without_fallback_or_context(mode):
    f = fixture()
    question = f.question
    if mode == "safety":
        question = replace(question, situation=replace(question.situation, resource_pressure=0.99))
    else:
        unsupported = GoalOpportunity(
            "control", GoalKind.RECOVER_CONTROL, GoalAvailability.AVAILABLE, 0.1, 0.0
        )
        if mode == "partial":
            # The real control safety gate must reject even a larger menu.
            question = replace(question, opportunities=(*question.opportunities, unsupported))
        elif mode == "unsupported":
            question = replace(question, opportunities=(question.opportunities[0], unsupported))
        else:
            unavailable = GoalOpportunity(
                "masked",
                GoalKind.RESUPPLY,
                GoalAvailability.UNAVAILABLE,
                unavailable_reason=GoalUnavailableReason.MISSING_CAPABILITY,
            )
            question = replace(question, opportunities=(question.opportunities[0], unavailable))
    f.policy.observe_context = lambda: pytest.fail("rejected menus cannot read forward context")
    with pytest.raises(ValueError):
        f.policy.select(question)
    assert f.policy.poisoned and not f.logs and f.policy.decisions == 0
    with pytest.raises(ValueError, match="poisoned"):
        f.policy.select(f.question)


@pytest.mark.parametrize("error", [OSError("uncertain durable append"), KeyboardInterrupt()])
def test_uncertain_append_poison_preserves_original_exception_and_never_reselects(error):
    f = fixture()

    def append(record):
        f.logs.append(record)  # Write may have happened before the failure.
        raise error

    f.policy.append_decision = append
    with pytest.raises(type(error)) as raised:
        f.policy.select(f.question)
    assert raised.value is error
    assert f.policy.poisoned and f.policy.decisions == 0 and len(f.logs) == 1
    with pytest.raises(ValueError, match="poisoned"):
        f.policy.select(f.question)
    with pytest.raises(ValueError, match="durable"):
        f.policy.selection_metadata()
    assert len(f.logs) == 1


@pytest.mark.parametrize("stage", ["observe", "append"])
def test_action_performing_read_or_append_poison_before_selection_return(stage):
    f = fixture()

    def observe():
        f.counters[1] += 1
        return (0.25,)

    def append(record):
        f.logs.append(record)
        f.counters[0] += 1

    if stage == "observe":
        f.policy.observe_context = observe
    else:
        f.policy.append_decision = append
    with pytest.raises(ValueError, match="performed actions"):
        f.policy.select(f.question)
    assert f.policy.poisoned and f.policy.decisions == 0
    assert len(f.logs) == int(stage == "append")


@pytest.mark.parametrize("context", [(), (True,), (float("nan"),), [0.2], (0.2, 0.3)])
def test_invalid_context_cannot_produce_a_record(context):
    f = fixture()
    f.policy.observe_context = lambda: context
    with pytest.raises(ValueError):
        f.policy.select(f.question)
    assert f.policy.poisoned and not f.logs


def test_partial_projection_rejected_even_when_shadow_has_two_supported_options(monkeypatch):
    import pokemon_red_completion.living_dex_goal_policy as projection

    f = fixture()
    extra = GoalOpportunity(
        "unmapped-in-this-test", GoalKind.EXPLORE, GoalAvailability.AVAILABLE, 0.9, 0.1
    )
    question = replace(f.question, opportunities=(*f.question.opportunities, extra))
    original = projection.project_living_dex_goal_candidate

    def incomplete(question, index, **kwargs):
        return None if index == 2 else original(question, index, **kwargs)

    monkeypatch.setattr(projection, "project_living_dex_goal_candidate", incomplete)
    shell = LivingDexGoalShadowPolicy(f.tail)
    shell.select(question)
    assert shell.last_menu_indices == (0, 1)
    assert len(question.available_indices) == 3
    with pytest.raises(ValueError, match="incomplete"):
        f.policy.select(question)
    assert f.policy.poisoned and not f.logs


def test_unavailable_candidate_is_not_assigned_probability_or_reindexed():
    f = fixture()
    unavailable = GoalOpportunity(
        "masked",
        GoalKind.EXPLORE,
        GoalAvailability.UNAVAILABLE,
        unavailable_reason=GoalUnavailableReason.MISSING_CAPABILITY,
    )
    question = replace(f.question, opportunities=(unavailable, *f.question.opportunities))
    assert f.policy.select(question).selected_index == 1
    assert f.logs[0]["menu_question_indices"] == [1, 2]
    assert f.policy.selection_metadata()["candidate_probabilities"] == [0.0, 1.0, 0.0]


def test_nonmonotone_between_calls_poison_without_drawing_tail():
    f = fixture()
    f.counters[:] = [10, 100]
    f.policy.select(f.question)
    f.counters[:] = [9, 100]
    with pytest.raises(ValueError, match="backwards"):
        f.policy.select(f.question)
    assert f.policy.poisoned and f.policy.tail_decisions == 0 and len(f.logs) == 1


def test_observer_exception_is_original_and_poisoned():
    f = fixture()
    error = KeyboardInterrupt()

    def observe():
        raise error

    f.policy.observe_context = observe
    with pytest.raises(KeyboardInterrupt) as caught:
        f.policy.select(f.question)
    assert caught.value is error and f.policy.poisoned and not f.logs


@pytest.mark.parametrize(
    "field,value",
    [
        ("training_probe", False),
        ("training_probe", 1),
        ("tail_seed", True),
        ("tail_seed", -1),
        ("observe_context", None),
        ("append_decision", None),
        ("meter", None),
    ],
)
def test_constructor_rejects_undeclared_or_invalid_probe(field, value):
    f = fixture()
    with pytest.raises(ValueError):
        replace(f.policy, **{field: value})


def test_wrong_plan_schema_tail_version_and_bad_meter_are_rejected():
    f = fixture()
    with pytest.raises(ValueError, match="contract"):
        replace(f.policy, fitted_plan=replace(f.plan, continuation_sha256="d" * 64))
    with pytest.raises(ValueError, match="v3"):
        replace(f.policy, tail_model=_supply_model())
    f.policy.meter = SimpleNamespace(checkpoint=lambda: None)
    with pytest.raises(ValueError, match="budget"):
        f.policy.select(f.question)
    assert f.policy.poisoned and not f.logs


def test_changed_model_identity_is_rejected_before_any_forward_read():
    f = fixture()
    f.policy.forward_model = replace(f.model, intercept=(0.1, 0.2))
    f.policy.observe_context = lambda: pytest.fail("mutated actor must not observe")
    with pytest.raises(ValueError, match="frozen model changed"):
        f.policy.select(f.question)
    assert f.policy.poisoned and not f.logs


@pytest.mark.parametrize("predictions", [(), (None, None)])
def test_invalid_or_partial_prediction_return_poisoned(monkeypatch, predictions):
    f = fixture()
    monkeypatch.setattr(ForwardGoalModel, "predict", lambda *args, **kwargs: predictions)
    with pytest.raises(ValueError, match="complete menu"):
        f.policy.select(f.question)
    assert f.policy.poisoned and not f.logs


def test_tail_append_failure_does_not_permit_retrying_the_consumed_tail_draw():
    f = fixture()
    f.policy.select(f.question)
    error = OSError("tail log failed")

    def append(record):
        f.logs.append(record)
        raise error

    f.policy.append_decision = append
    with pytest.raises(OSError) as raised:
        f.policy.select(f.question)
    assert raised.value is error
    assert f.policy.poisoned and f.policy.decisions == 1
    assert [r["role"] for r in f.logs] == ["forward_first", "frozen_tail"]
    with pytest.raises(ValueError, match="poisoned"):
        f.policy.select(f.question)
    assert len(f.logs) == 2


def test_append_cannot_hide_a_reentrant_attempt_and_resume_outer_selection():
    f = fixture()

    def append(record):
        f.logs.append(record)
        with pytest.raises(ValueError, match="poisoned"):
            f.policy.select(f.question)

    f.policy.append_decision = append
    with pytest.raises(ValueError, match="reentrant"):
        f.policy.select(f.question)
    assert f.policy.poisoned and f.policy.decisions == 0 and len(f.logs) == 1
