"""Prospective unit-outcome admission from the existing continuous native player.

No selector, retries, fits or comparative labels. Forced support and model choices
both produce observed unit outcomes, while the outer decision ledger keeps their
actual selection authority. Exceptions remain diagnostics, never invented labels.
"""

from dataclasses import asdict
from hashlib import sha256

from .goal_manager import GoalDecisionOutcome
from .red_native_curriculum import (
    CONTINUOUS_RESOURCE_CONTRACT,
    CONTINUOUS_RESOURCE_OUTCOME_SCHEMA,
    CONTINUOUS_RESOURCE_PLAN_SCHEMA,
    curriculum_projection,
    publish_declaration,
    publish_outcome,
)
from .red_player_economy import snapshot_document
from .red_player_lesson_runtime import observe_native_player_boundary
from .red_player_support import RedPlayerSupport
from .registered_collection import REGISTERED_OBJECTIVE


def begin_resource_recording(session, options, binding, remaining):
    boundary = observe_native_player_boundary(
        session.runtime, battle=session.battle_observer(),
        combat_specimen_refs=session.roles, remaining_budget=remaining,
    )
    support = isinstance(options, RedPlayerSupport)
    inventory = options.bindings if support else options.original_bindings
    situation = boundary.registered.situation if support else options.situation
    if support and session.capture_reserve is not None:
        from .red_capture_readiness import assess_capture_readiness, capture_preparation_situation

        situation = capture_preparation_situation(
            boundary.registered,
            assess_capture_readiness(boundary.registered, session.capture_reserve),
        )
    question = inventory.question(situation)
    index = next(i for i, o in enumerate(question.opportunities)
                 if o.binding_ref == binding.binding_ref)
    source = {
        **session.source,
        "state_sha256": sha256(boundary.state).hexdigest(),
        "setup_receipt_sha256": session.resource_setup_receipt,
    }
    resource = ("native_acquisition" if binding.kind.value == "acquire_species" else
                "earn_cash" if binding.resource_quote.expected_income else "purchase_stock")
    plan = dict(
        schema=CONTINUOUS_RESOURCE_PLAN_SCHEMA, contract=CONTINUOUS_RESOURCE_CONTRACT,
        partition="train", objective=REGISTERED_OBJECTIVE,
        question=dict(schema=question.policy_input["schema"],
                      situation=question.situation.policy_dict(),
                      candidates=[o.policy_dict() for o in question.opportunities]),
        selected_index=index,
        before=boundary.registered.public_dict(),
        economy_before=snapshot_document(boundary.economy),
        target_cash=session.target_cash, source=source,
        maximum_actions=session.limits.actions - len(session.recorder.trace),
        maximum_frames=session.limits.frames - session.controller.frames_executed,
        teacher_selected=False, comparative_choice=False,
        player_lesson=dict(before=boundary.lesson_snapshot, target={"resource": resource}),
        readiness=boundary.readiness.public_dict(), execution_identity=asdict(session.execution),
        capture_reserve=(None if session.capture_reserve is None
                         else asdict(session.capture_reserve)),
    )
    context, candidate = curriculum_projection(plan)
    if not support:
        actual = next(i for i, b in enumerate(options.bindings)
                      if b.binding_ref == binding.binding_ref)
        if candidate.vector(context, feature_version=5) != options.menu.candidate_vector(actual):
            raise ValueError("continuous resource lesson differs from actual inference vector")
    declaration = publish_declaration(session.store, plan)
    return dict(declaration=declaration, plan=plan, action_start=len(session.recorder.trace),
                frame_start=session.controller.frames_executed, remaining=remaining)


def finish_resource_recording(session, record, report, verdict):
    if (
        report.actions_executed != len(session.recorder.trace) - record["action_start"]
        or report.frames_executed != session.controller.frames_executed - record["frame_start"]
    ):
        raise ValueError("resource report costs differ from the guarded trace")
    boundary = observe_native_player_boundary(
        session.runtime, battle=session.battle_observer(),
        combat_specimen_refs=session.roles, remaining_budget=record["remaining"],
    )
    terminal_sha = sha256(boundary.state).hexdigest()
    trace = [dict(row, ordinal=i,
                  before_frame=row["before_frame"] - record["frame_start"],
                  after_frame=row["after_frame"] - record["frame_start"])
             for i, row in enumerate(session.recorder.trace[record["action_start"]:])]
    result = dict(
        schema=CONTINUOUS_RESOURCE_OUTCOME_SCHEMA, declaration_sha256=record["declaration"],
        after=boundary.registered.public_dict(),
        succeeded=verdict.status is GoalDecisionOutcome.SUCCEEDED, trace=trace,
        terminal_state_sha256=terminal_sha, interventions_during_execution=[],
        native_audit=dict(before_sha256=record["plan"]["source"]["state_sha256"],
                          terminal_sha256=terminal_sha, input_frames=0, passed=True),
        player_lesson=boundary.lesson_snapshot, economy_after=snapshot_document(boundary.economy),
    )
    return publish_outcome(session.store, record["declaration"], result)
