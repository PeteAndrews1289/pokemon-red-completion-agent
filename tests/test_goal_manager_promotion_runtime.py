from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.captured_progress import write_captured_progress
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalOpportunity,
    GoalSituation,
)
from pokemon_red_completion.goal_manager_collection_runtime import (
    goal_binding_manifest_sha256,
)
from pokemon_red_completion.goal_manager_context_catalog import (
    open_goal_manager_context_capture,
)
from pokemon_red_completion.goal_manager_model import (
    GOAL_MANAGER_FEATURE_NAMES,
    GoalManagerLinearModel,
    GoalManagerModelError,
)
from pokemon_red_completion.goal_manager_promotion_runtime import (
    GoalManagerPromotionRuntimeError,
    evaluate_goal_manager_promotion_context,
)
from pokemon_red_completion.goal_manager_protocol import (
    GOAL_MANAGER_REGISTRY_RELATIVE_PATH,
    parse_goal_manager_registry,
)
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.goal_manager_trajectory import (
    ordered_goal_manager_question,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _Adapter:
    def __init__(self, situation: GoalSituation) -> None:
        self.situation = situation

    def observe(self) -> SimpleNamespace:
        return SimpleNamespace(situation=self.situation)


class _World:
    def __init__(self) -> None:
        self.actions = 0

    def execute(self, action: MacroAction) -> MacroAction:
        self.actions += 1
        return action


def _assignment(
    slot_id: str = "red-goal-v1-007-advance_story-validation-01",
):  # type: ignore[no-untyped-def]
    registry = parse_goal_manager_registry(
        (PROJECT_ROOT / GOAL_MANAGER_REGISTRY_RELATIVE_PATH).read_bytes()
    )
    committed = replace(
        registry,
        execution=replace(registry.execution, source_commit="a" * 40),
    )
    return committed.assignment(slot_id)


def _capture(tmp_path: Path):  # type: ignore[no-untyped-def]
    state = tmp_path / "validation.state"
    envelope = tmp_path / "validation.state.json"
    state.write_bytes(b"promotion-validation-state")
    write_captured_progress(
        envelope,
        state_path=state,
        checkpoint_id="validation-context",
        checkpoint_label="Validation context",
        checkpoints_completed=1,
        checkpoints_total=1,
        verified_objective_ids=(),
    )
    return open_goal_manager_context_capture(state, envelope)


def _situation() -> GoalSituation:
    return GoalSituation(
        story_pressure=0.9,
        collection_pressure=0.8,
        team_pressure=0.1,
        evolution_pressure=0.1,
        safety_pressure=0.1,
        resource_pressure=0.1,
        storage_pressure=0.1,
        recovery_pressure=0.0,
        exploration_pressure=0.1,
    )


def _factory(executed: list[GoalKind]):  # type: ignore[no-untyped-def]
    opportunities = (
        GoalOpportunity(
            "private:story",
            GoalKind.ADVANCE_STORY,
            GoalAvailability.AVAILABLE,
            0.1,
            0.1,
        ),
        GoalOpportunity(
            "private:acquire",
            GoalKind.ACQUIRE_SPECIES,
            GoalAvailability.AVAILABLE,
            0.2,
            0.2,
        ),
    )

    def build(actions):  # type: ignore[no-untyped-def]
        bindings = []
        for opportunity in opportunities:
            kind = opportunity.kind

            def execute(selected_kind=kind):  # type: ignore[no-untyped-def]
                before = actions.actions_executed
                actions.execute(MacroAction(MacroActionKind.WAIT))
                executed.append(selected_kind)
                return GoalExecutionReport(
                    actions.actions_executed - before,
                    1,
                    {"bounded": True},
                )

            bindings.append(
                ExecutableGoalBinding(
                    binding_ref=opportunity.binding_ref,
                    kind=kind,
                    estimated_effort=float(opportunity.estimated_effort or 0.0),
                    estimated_risk=float(opportunity.estimated_risk or 0.0),
                    execute=execute,
                    verify=lambda _report: GoalVerification.succeeded(),
                )
            )
        return SimpleNamespace(enumerate=lambda _observation: GoalBindingSet(
            opportunities,
            tuple(bindings),
        ))

    return build


def _model(target: GoalKind, *, strength: float = 10.0) -> GoalManagerLinearModel:
    width = len(GOAL_MANAGER_FEATURE_NAMES)
    weights = np.zeros(width, dtype=np.float64)
    feature = GOAL_MANAGER_FEATURE_NAMES.index(f"candidate.kind.{target.value}")
    weights[feature] = strength
    return GoalManagerLinearModel(
        weights=weights,
        feature_mean=np.zeros(width, dtype=np.float64),
        feature_scale=np.ones(width, dtype=np.float64),
        l2=0.02,
        training_epochs=800,
    )


def _catalog(assignment, capture, factory):  # type: ignore[no-untyped-def]
    situation = _situation()
    bindings = factory(SimpleNamespace(actions_executed=0)).enumerate(None)
    question = ordered_goal_manager_question(
        assignment_id=assignment.assignment_id,
        decision_index=0,
        situation=situation,
        opportunities=bindings.opportunities,
    )
    reference_index = next(
        index
        for index, opportunity in enumerate(question.opportunities)
        if opportunity.kind is GoalKind.ADVANCE_STORY
    )
    context = SimpleNamespace(
        assignment_id=assignment.assignment_id,
        capture_id=capture.capture_id,
        state_sha256=capture.state_sha256,
        envelope_sha256=capture.envelope_sha256,
        question_sha256=question.ordered_policy_input_sha256,
        policy_context_sha256=question.policy_context_sha256,
        available_menu_sha256=question.available_menu_sha256,
        candidate_goal_kinds=tuple(item.kind for item in question.opportunities),
        available_goal_kinds=(GoalKind.ADVANCE_STORY, GoalKind.ACQUIRE_SPECIES),
        binding_manifest_sha256=goal_binding_manifest_sha256(bindings),
        selected_candidate_index=reference_index,
        selected_kind=GoalKind.ADVANCE_STORY,
        context_id=hashlib.sha256(b"context").hexdigest(),
    )
    return SimpleNamespace(entry=lambda _slot_id: context)


def test_shadow_observes_model_disagreement_but_executes_frozen_reference(
    tmp_path: Path,
) -> None:
    assignment = _assignment()
    capture = _capture(tmp_path)
    executed: list[GoalKind] = []
    factory = _factory(executed)
    catalog = _catalog(assignment, capture, factory)

    result = evaluate_goal_manager_promotion_context(
        mode="shadow",
        assignment=assignment,
        capture=capture,
        context_catalog=catalog,
        adapter=_Adapter(_situation()),
        action_delegate=_World(),
        enumerator_factory=factory,
        model=_model(GoalKind.ACQUIRE_SPECIES),
        confidence_threshold=0.8,
    )

    assert result.model_kind is GoalKind.ACQUIRE_SPECIES
    assert result.model_reference_agreement is False
    assert result.execution.selected_kind is GoalKind.ADVANCE_STORY
    assert result.model_had_execution_authority is False
    assert result.public_dict()["authority"]["teacher_fallbacks"] == 0
    assert executed == [GoalKind.ADVANCE_STORY]


def test_causal_mode_executes_exact_model_choice_without_teacher_fallback(
    tmp_path: Path,
) -> None:
    assignment = _assignment()
    capture = _capture(tmp_path)
    executed: list[GoalKind] = []
    factory = _factory(executed)
    catalog = _catalog(assignment, capture, factory)

    result = evaluate_goal_manager_promotion_context(
        mode="causal",
        assignment=assignment,
        capture=capture,
        context_catalog=catalog,
        adapter=_Adapter(_situation()),
        action_delegate=_World(),
        enumerator_factory=factory,
        model=_model(GoalKind.ACQUIRE_SPECIES),
        confidence_threshold=0.8,
    )

    assert result.execution.selected_kind is GoalKind.ACQUIRE_SPECIES
    assert result.model_had_execution_authority is True
    assert result.reference_had_execution_authority is False
    assert executed == [GoalKind.ACQUIRE_SPECIES]


def test_causal_mode_fails_before_action_below_frozen_confidence_floor(
    tmp_path: Path,
) -> None:
    assignment = _assignment()
    capture = _capture(tmp_path)
    executed: list[GoalKind] = []
    factory = _factory(executed)
    catalog = _catalog(assignment, capture, factory)

    with pytest.raises(GoalManagerModelError, match="below threshold"):
        evaluate_goal_manager_promotion_context(
            mode="causal",
            assignment=assignment,
            capture=capture,
            context_catalog=catalog,
            adapter=_Adapter(_situation()),
            action_delegate=_World(),
            enumerator_factory=factory,
            model=_model(GoalKind.ACQUIRE_SPECIES, strength=0.0),
            confidence_threshold=0.8,
        )

    assert executed == []


def test_promotion_rejects_training_partition_before_enumeration(tmp_path: Path) -> None:
    assignment = _assignment("red-goal-v1-001-advance_story-train-01")
    capture = _capture(tmp_path)

    with pytest.raises(GoalManagerPromotionRuntimeError, match="validation contexts only"):
        evaluate_goal_manager_promotion_context(
            mode="shadow",
            assignment=assignment,
            capture=capture,
            context_catalog=SimpleNamespace(),
            adapter=_Adapter(_situation()),
            action_delegate=_World(),
            enumerator_factory=lambda _actions: None,
            model=_model(GoalKind.ADVANCE_STORY),
            confidence_threshold=0.8,
        )
