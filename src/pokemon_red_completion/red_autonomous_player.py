"""Bounded model decisions with durable choices and changed-state replanning.

The environment supplies observed executable options; it never supplies a chosen
goal. Every choice is persisted before checking its authority or executing it.
Existing run directories are refused, including incomplete ones.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from time import monotonic
from typing import cast

from .executor import RestorationBudgetExhausted
from .goal_manager import GoalDecisionOutcome, GoalFailureReason, GoalKind
from .goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalExecutionReport,
    GoalVerification,
)
from .goal_search_memory import GoalSearchMemory
from .living_dex_option_value import LivingDexOptionValueModel
from .provenance import canonical_sha256
from .red_integrated_play import (
    measured_cost,
    menu_with_search_history,
    objective_key,
    observable_player_boundary,
    observed_cost,
    ordinary_paid_search_setback,
    ordinary_player_setback,
    safe_route_setback,
    search_objective_key,
    settled_evolution_partial,
    settled_evolution_zero_progress,
    settled_player_boundary,
    spending_bound,
)
from .red_live_option_menu import (
    RedLiveOptionChoice,
    RedLiveOptionSelectionMode,
    RedLiveOptionSet,
    select_red_live_option,
)
from .red_player_curriculum import PlayerCurriculumCompletion
from .red_player_support import (
    PlayerBudgetStop,
    RedPlayerSupport,
    RedPlayerSupportChoice,
)
from .red_recorded_selection_authority import record_selection_authority


def _exception_chain(error: BaseException | None) -> list[dict[str, object]] | None:
    """Preserve bounded typed causes without losing the terminal state.

    Autonomous execution deliberately stops on the first failure.  Retaining
    only the wrapper text makes that safe stop needlessly opaque, especially
    when a route adapter has attached a more specific controller failure as
    ``__cause__``.  Eight links is well beyond the project's normal nesting
    depth while still bounding hostile or cyclic exception graphs.
    """

    if error is None:
        return None
    rows: list[dict[str, object]] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen and len(rows) < 8:
        seen.add(id(current))
        row: dict[str, object] = {
            "error_type": type(current).__name__,
            "error": str(current),
        }
        reason_code = getattr(current, "reason_code", None)
        if reason_code is None:
            reason_code = getattr(current, "reason", None)
        if isinstance(reason_code, str) and reason_code:
            row["reason_code"] = reason_code
        settlement = getattr(current, "settlement_error_chain", None)
        if type(settlement) is list:
            row["settlement_error_chain"] = settlement[:8]
        rows.append(row)
        current = current.__cause__
    return rows


@dataclass(frozen=True)
class AutonomousSnapshot:
    state: bytes
    facts: Mapping[str, object]
    safe: bool

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.state).hexdigest()


def _write(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _record(path: Path, document: Mapping[str, object]) -> None:
    _write(path, (json.dumps(document, sort_keys=True, indent=2) + "\n").encode())


def continuation_binding(
    options: RedLiveOptionSet | tuple[ExecutableGoalBinding, ...],
    prior_binding_ref: str,
) -> ExecutableGoalBinding:
    """Rebind one privately authenticated goal across changed origin states."""
    bindings = cast(tuple[ExecutableGoalBinding, ...], getattr(options, "bindings", options))
    if re.fullmatch(r"pokemon\.red:story:[a-z][a-z0-9_]*", prior_binding_ref):
        # Story references are stable objective identities, not origin-dependent
        # evolution configurations. Never substitute another available objective.
        matches = tuple(
            binding
            for binding in bindings
            if binding.kind is GoalKind.ADVANCE_STORY and binding.binding_ref == prior_binding_ref
        )
        if len(matches) != 1:
            raise ValueError("prior story goal has no unique live binding")
        return matches[0]
    fingerprint = prior_binding_ref.rsplit(":", 1)[-1]
    if re.fullmatch(r"[0-9a-f]{64}", fingerprint) is None:
        raise ValueError("prior goal has no valid configuration fingerprint")
    matches = tuple(
        binding
        for binding in bindings
        if binding.kind is GoalKind.EVOLVE_SPECIES
        and binding.binding_ref.rsplit(":", 1)[-1] == fingerprint
    )
    if len(matches) != 1:
        raise ValueError("prior evolution goal has no unique live binding")
    return matches[0]


def run_autonomous_goal_continuation(
    *,
    output: Path,
    snapshot: Callable[[], AutonomousSnapshot],
    observe: Callable[[int], RedLiveOptionSet],
    prior_binding_ref: str,
    prior_outcome_sha256: str,
    provenance: Mapping[str, object],
    targeted_observe: Callable[[], tuple[ExecutableGoalBinding, ...]] | None = None,
) -> dict[str, object]:
    """Execute a saved model goal once, with no new model query or reward fit."""
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    _record(
        output / "plan.json",
        {
            "schema": "pokemon.red.autonomous-goal-continuation.v1",
            "prior_binding_ref": prior_binding_ref,
            "prior_outcome_sha256": prior_outcome_sha256,
            "model_queries": 0,
            "teacher_actions_allowed": False,
            "provenance": dict(provenance),
        },
    )
    before = snapshot()
    _write(output / "before.state", before.state)
    _record(
        output / "before.json",
        {
            "state_sha256": before.sha256,
            "facts": dict(before.facts),
            "safe": before.safe,
        },
    )
    if not before.safe:
        raise ValueError("unsafe continuation origin")
    try:
        options = None if targeted_observe is not None else observe(0)
        targeted = None if targeted_observe is None else targeted_observe()
        if snapshot() != before:
            raise ValueError("continuation inventory changed the game")
        selected = continuation_binding(
            options if options is not None else targeted or (),
            prior_binding_ref,
        )
    except Exception as admission_error:
        _record(
            output / "admission-failure.json",
            {
                "error_type": type(admission_error).__name__,
                "error": str(admission_error),
            },
        )
        raise
    _record(
        output / "execution-started.json",
        {
            "selected_binding_ref": selected.binding_ref,
            "selected_kind": selected.kind.value,
            "prior_binding_ref": prior_binding_ref,
            "state_sha256": before.sha256,
            "menu_sha256": None if options is None else options.menu.policy_sha256,
            "private_inventory_sha256": (
                None
                if targeted is None
                else canonical_sha256([binding.binding_ref for binding in targeted])
            ),
            "binding_scope": (
                "full_menu"
                if targeted is None
                else "targeted_story"
                if selected.kind is GoalKind.ADVANCE_STORY
                else "targeted_evolution"
            ),
        },
    )
    report = None
    verification = None
    error: BaseException | None = None
    try:
        report = selected.execute()
        verification = selected.verify(report)
    except BaseException as caught:
        error = caught
    finally:
        terminal = snapshot()
        _write(output / "terminal.state", terminal.state)
        outcome = {
            "before_state_sha256": before.sha256,
            "terminal_state_sha256": terminal.sha256,
            "before": dict(before.facts),
            "after": dict(terminal.facts),
            "safe_terminal": terminal.safe,
            "verification": None if verification is None else verification.status.value,
            "evidence": None if report is None else dict(report.evidence),
            "error_chain": _exception_chain(error),
            "model_queries": 0,
            "learning_eligible": False,
        }
        _record(output / "outcome.json", outcome)
    if error is not None and not isinstance(error, Exception):
        raise error
    completed = (
        error is None
        and terminal.safe
        and verification is not None
        and verification.status is GoalDecisionOutcome.SUCCEEDED
    )
    status = (
        "complete"
        if completed
        else "pending"
        if (
            terminal.safe
            and terminal.sha256 != before.sha256
            and _party_experience_gain(before.facts, terminal.facts) > 0
        )
        else "stopped"
    )
    result = {
        "schema": "pokemon.red.autonomous-goal-continuation-result.v1",
        "status": status,
        "experience_gain": _party_experience_gain(before.facts, terminal.facts),
        "model_queries": 0,
        "model_decisions": 0,
        "teacher_actions": 0,
        "outcome": outcome,
    }
    _record(output / "result.json", result)
    return result


def _party_experience_gain(before: Mapping[str, object], after: Mapping[str, object]) -> int:
    """Conservative slot/species-matched training delta, not a reward label."""
    old = before.get("party_training")
    new = after.get("party_training")
    if not isinstance(old, list) or not isinstance(new, list):
        return 0
    return sum(
        max(0, current[2] - prior[2])
        for prior, current in zip(old, new, strict=False)
        if prior[0] == current[0] and prior[1] == current[1]
    )


def run_assisted_safari_probe(
    *,
    output: Path,
    snapshot: Callable[[], AutonomousSnapshot],
    observe: Callable[[int], RedLiveOptionSet],
    provenance: Mapping[str, object],
) -> dict[str, object]:
    """Exercise one teacher-selected Safari binding without a model query or fit."""
    assistance = provenance.get("training_assistance")
    if (
        not isinstance(assistance, Mapping)
        or assistance.get("kind") != "money_override"
        or assistance.get("final_run_eligible") is not False
    ):
        raise ValueError("Safari training probe requires marked non-final assistance")
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    _record(
        output / "plan.json",
        {
            "schema": "pokemon.red.assisted-safari-mechanics.v1",
            "teacher_selected_skill": "safari",
            "model_queries": 0,
            "goal_value_fit_allowed": False,
            "independent_evaluation": False,
            "provenance": dict(provenance),
        },
    )
    before = snapshot()
    _write(output / "before.state", before.state)
    _record(
        output / "before.json",
        {
            "state_sha256": before.sha256,
            "facts": dict(before.facts),
            "safe": before.safe,
        },
    )
    if not before.safe:
        raise ValueError("unsafe Safari training origin")
    try:
        options = observe(0)
        if snapshot() != before:
            raise ValueError("Safari training inventory changed the game")
        selected_indices = [
            index
            for index in options.menu.available_indices
            if options.bindings[index].kind is GoalKind.ACQUIRE_SPECIES
            and options.bindings[index].binding_ref.startswith("pokemon.red:safari-live:")
        ]
        if len(selected_indices) != 1:
            raise ValueError("Safari training needs exactly one available live binding")
        selected = options.bindings[selected_indices[0]]
    except Exception as admission_error:
        _record(
            output / "admission-failure.json",
            {
                "error_type": type(admission_error).__name__,
                "error": str(admission_error),
            },
        )
        raise
    _record(
        output / "execution-started.json",
        {
            "selected_binding_ref": selected.binding_ref,
            "selected_kind": selected.kind.value,
            "selected_candidate_index": selected_indices[0],
            "menu_sha256": options.menu.policy_sha256,
            "state_sha256": before.sha256,
            "selection_authority": "teacher_training_only",
            "model_queries": 0,
        },
    )
    report = None
    verification = None
    execution_error: BaseException | None = None
    try:
        report = selected.execute()
        verification = selected.verify(report)
    except BaseException as caught:
        execution_error = caught
    finally:
        terminal = snapshot()
        _write(output / "terminal.state", terminal.state)
        outcome = {
            "before_state_sha256": before.sha256,
            "terminal_state_sha256": terminal.sha256,
            "before": dict(before.facts),
            "after": dict(terminal.facts),
            "safe_terminal": terminal.safe,
            "verification": None if verification is None else verification.status.value,
            "failure_reason": (
                None
                if verification is None or verification.failure_reason is None
                else verification.failure_reason.value
            ),
            "evidence": None if report is None else dict(report.evidence),
            "error_chain": _exception_chain(execution_error),
            "model_queries": 0,
            "learning_eligible": False,
            "goal_value_fit_allowed": False,
        }
        _record(output / "outcome.json", outcome)
    if execution_error is not None and not isinstance(execution_error, Exception):
        raise execution_error
    complete = (
        execution_error is None
        and terminal.safe
        and verification is not None
        and verification.status is GoalDecisionOutcome.SUCCEEDED
    )
    result: dict[str, object] = {
        "schema": "pokemon.red.assisted-safari-mechanics-result.v1",
        "status": "complete" if complete else "stopped",
        "model_queries": 0,
        "model_decisions": 0,
        "teacher_training_selections": 1,
        "goal_value_fit_allowed": False,
        "outcome": outcome,
    }
    _record(output / "result.json", result)
    return result


def _private_story_contexts(options):
    """Pre-input bookkeeping only; never part of the policy menu or scorer."""
    bindings = (options.binding,) if isinstance(options, RedPlayerSupport) else options.bindings
    if not any(b.story_objective_ref is not None for b in bindings):
        return {}
    return {
        "private_story_contexts": [
            {"binding_ref": b.binding_ref, "objective_ref": b.story_objective_ref} for b in bindings
        ]
    }


def run_autonomous_options(
    *,
    model: LivingDexOptionValueModel,
    output: Path,
    snapshot: Callable[[], AutonomousSnapshot],
    observe: Callable[
        [int],
        RedLiveOptionSet | RedPlayerSupport | PlayerCurriculumCompletion | PlayerBudgetStop,
    ],
    seed: int,
    maximum_decisions: int = 3,
    maximum_seconds: float = 1_800,
    provenance: Mapping[str, object],
    integrated_play: bool = False,
    maximum_cash_spent: int | None = 0,
    continuous_player: bool = False,
    continue_safe_route_failures: bool = False,
    greedy_selection: bool = False,
    exploration_mix: float = 0.25,
    sequence_collector=None,
    sequence_policy=None,
    stop_after_outcome=None,
    consequence_head=None,
    consequence_challenge_ref=None,
    consequence_objective_ref=None,
    allow_greedy_branch_recovery: bool = False,
    refine_preparation: bool = False,
    defer_unbound_preparation: bool = False,
    allow_singleton_parent_support: bool = False,
    associate_unique_combat: bool = False,
    explore_outside_scope: bool = False,
    explore_on_movement_recurrence: bool = False,
    initial_search_memory: GoalSearchMemory | None = None,
    movement_revisit_saturation: bool = False,
    collection_cost_frame_horizon: int | None = None,
    train_inference_scope=None,
    train_selector_scope=None,
    train_form_balanced_exploration: bool = False,
    story_branch_head=None,
    story_branch_exploration: float = 0.0,
    story_branch_segment_lengths: tuple[int, int] | None = None,
    story_milestone_commitment: bool = False,
    story_kind_commitment: bool = False,
    respect_combat_preparation_choice: bool = False,
    story_kind_commitment_carrier=None,
) -> dict[str, object]:
    """Run up to N learned goals without a teacher action or resetting state.

    Primitive action/frame limits belong to the environment's executor. The
    wall-time limit here governs admission of the next decision. Outcomes and
    terminal saves survive ordinary execution/verification errors. By default
    every exception stops. The explicit DEVELOPMENT-only route-setback option
    can retain a narrowly certified failed route and re-query the model; it
    neither retries the same goal nor supplies a fallback target.

    The opt-in continuous player requires V5 live readiness and explicit settled
    boundary facts. Its declared game setbacks may replan, and safety restoration
    may execute as labeled support. This does not confer training admission or
    native qualification; the environment must still enforce total input budgets.
    """
    if type(movement_revisit_saturation) is not bool or (
        movement_revisit_saturation and (not continuous_player or model.feature_version != 16)
    ):
        raise ValueError("movement saturation requires explicit V16 continuous scope")
    if type(seed) is not int or seed < 0:
        raise ValueError("autonomous seed must be a nonnegative integer")
    if initial_search_memory is not None and (
        not isinstance(initial_search_memory, GoalSearchMemory)
        or not (integrated_play or continuous_player)
    ):
        raise ValueError("retained search memory requires a typed player scope")
    source_context = cast(Mapping[str, object], provenance.get("source", {}))
    if (
        isinstance(exploration_mix, bool)
        or not isinstance(exploration_mix, (int, float))
        or not math.isfinite(exploration_mix)
        or not 0 <= exploration_mix <= 1
    ):
        raise ValueError("autonomous exploration mix must be finite within zero and one")
    if type(train_form_balanced_exploration) is not bool or (
        train_form_balanced_exploration
        and (
            not continuous_player
            or source_context.get("partition") != "train"
            or greedy_selection
            or sequence_policy is not None
            or consequence_head is not None
            or allow_greedy_branch_recovery
        )
    ):
        raise ValueError("form-balanced exploration requires a continuous TRAIN-only scope")
    from .red_story_branch_value import StoryBranchHead
    if (
        (story_branch_head is not None and type(story_branch_head) is not StoryBranchHead)
        or isinstance(story_branch_exploration, bool)
        or not isinstance(story_branch_exploration, (int, float))
        or not 0 <= story_branch_exploration <= 1
        or ((story_branch_head is not None or story_branch_exploration > 0) and not continuous_player)
        or (story_branch_exploration > 0 and source_context.get("partition") != "train")
    ):
        raise ValueError("story-branch child requires continuous scope; its exploration is TRAIN-only")
    if story_branch_segment_lengths is not None and (
        source_context.get("partition") != "train"
        or not continuous_player
        or type(story_branch_segment_lengths) is not tuple
        or len(story_branch_segment_lengths) != 2
        or any(type(v) is not int for v in story_branch_segment_lengths)
        or not 1 <= story_branch_segment_lengths[0] <= story_branch_segment_lengths[1] <= 200
    ):
        raise ValueError("story-branch segments are TRAIN-only with an explicit length range")
    if type(story_milestone_commitment) is not bool or (
        story_milestone_commitment
        and (not continuous_player or story_branch_segment_lengths is not None or story_branch_exploration > 0)
    ):
        raise ValueError("milestone story commitment requires continuous play without TRAIN segments or exploration")
    if type(story_kind_commitment) is not bool or (story_kind_commitment and not story_milestone_commitment):
        raise ValueError("kind-level story commitment requires milestone story commitment")
    if type(respect_combat_preparation_choice) is not bool or (
        respect_combat_preparation_choice and (not story_kind_commitment or source_context.get("partition") != "development")
    ):
        raise ValueError("combat preparation choice requires declared DEVELOPMENT story commitment")
    if story_kind_commitment_carrier is not None:
        from .red_story_kind_commitment import StoryKindCommitmentCarrier

        if not story_kind_commitment or type(story_kind_commitment_carrier) is not StoryKindCommitmentCarrier:
            raise ValueError("kind-level story commitment carrier requires the declared commitment")
    if exploration_mix != 0.25 and not train_form_balanced_exploration and (
        not continuous_player
        or source_context.get("partition") != "development"
        or greedy_selection
        or sequence_collector is not None
        or sequence_policy is not None
        or consequence_head is not None
    ):
        raise ValueError("custom exploration requires separate continuous DEVELOPMENT scope")
    if (
        type(continuous_player) is not bool
        or type(integrated_play) is not bool
        or (continuous_player and integrated_play)
    ):
        raise ValueError("continuous player and legacy integrated scopes must be separate")
    if type(continue_safe_route_failures) is not bool or (
        continue_safe_route_failures
        and (
            not continuous_player
            or source_context.get("partition") != "development"
            or sequence_collector is not None
            or sequence_policy is not None
            or consequence_head is not None
        )
    ):
        raise ValueError("safe route continuation requires separate continuous DEVELOPMENT scope")
    if type(maximum_decisions) is not int or maximum_decisions < 1:
        raise ValueError("autonomous run requires a positive integer decision limit")
    if not continuous_player and maximum_decisions > 10:
        raise ValueError("legacy autonomous run requires one through ten decisions")
    if (
        type(maximum_seconds) not in (int, float)
        or not math.isfinite(maximum_seconds)
        or maximum_seconds <= 0
    ):
        raise ValueError("autonomous run requires a finite positive time limit")
    ordinary_economy = continuous_player and maximum_cash_spent is None
    from .red_consequence_choice import (
        valid_branch_recovery_objectives,
        validate_greedy_branch_recovery_scope,
    )

    train_inference = validate_greedy_branch_recovery_scope(
        allow=allow_greedy_branch_recovery,
        greedy_selection=greedy_selection,
        refine_preparation=refine_preparation,
        defer_unbound_preparation=defer_unbound_preparation,
        allow_singleton_parent_support=allow_singleton_parent_support,
        associate_unique_combat=associate_unique_combat,
        explore_outside_scope=explore_outside_scope,
        explore_on_movement_recurrence=explore_on_movement_recurrence,
        source=source_context,
        model=model,
        head=consequence_head,
        objective_ref=consequence_objective_ref,
        challenge_ref=consequence_challenge_ref,
        train_inference_scope=train_inference_scope,
        train_selector_scope=train_selector_scope,
    )
    if explore_on_movement_recurrence and movement_revisit_saturation is not True:
        raise ValueError("recurrence escape requires observed movement history")
    from .red_scoped_train_composition import validate_passive_train_sequence
    passive_collection = train_inference and validate_passive_train_sequence(
        train_selector_scope, getattr(sequence_collector, "horizon", None),
        sequence_policy=sequence_policy,
    )
    if type(greedy_selection) is not bool or (
        greedy_selection
        and (
            not continuous_player
            or (source_context.get("partition") != "development" and not train_inference)
            or (sequence_collector is not None and not passive_collection)
            or sequence_policy is not None
            or (consequence_head is not None and not allow_greedy_branch_recovery)
        )
    ):
        raise ValueError("highest-score selection requires separate continuous DEVELOPMENT scope")
    if not ordinary_economy and (
        type(maximum_cash_spent) is not int
        or (
            maximum_cash_spent < 0
            or (not integrated_play and not continuous_player and maximum_cash_spent != 0)
        )
    ):
        raise ValueError("integrated play requires explicit scope and cash bound")
    if sequence_collector is not None:
        from .player_sequence_collector import SequenceTraceCollector

        if not continuous_player or not isinstance(sequence_collector, SequenceTraceCollector):
            raise ValueError("sequence observer requires typed continuous-player scope")
    if sequence_policy is not None:
        from .player_sequence_policy import SequencePolicy

        if (
            type(sequence_policy) is not SequencePolicy
            or sequence_collector is None
            or not continuous_player
            or model.feature_version != sequence_policy.head.feature_version
            or sequence_policy.baseline_sha256 != model.model_sha256
            or sequence_policy.head.horizon != sequence_collector.horizon
            or sequence_policy.head.target_contract != sequence_collector.target_contract
        ):
            raise ValueError("sequence policy requires matching continuous model/history collector")
    if sequence_policy is not None and sequence_policy.selection_mode in {"stable_recurrence", "stable_costly_recurrence"} and movement_revisit_saturation is not True:
        raise ValueError("stable sequence recurrence requires observed movement history")
    if (consequence_head is None) != (consequence_challenge_ref is None):
        raise ValueError("consequence head and private context must accompany each other")
    if consequence_objective_ref is not None and (
        consequence_head is None or not valid_branch_recovery_objectives(consequence_objective_ref)
    ):
        raise ValueError("branch recovery requires a head and explicit objective dispatch")
    if consequence_head is not None:
        from .player_challenge_consequence import (
            ChallengeConsequenceHead,
            consequence_feature_versions_compatible,
        )

        if (
            type(consequence_head) is not ChallengeConsequenceHead
            or consequence_head.feedback_version != 2
            or not continuous_player
            or model.feature_version not in (7, 9, 10, 11, 15, 16)
            or not consequence_feature_versions_compatible(
                consequence_head.feature_version, model.feature_version
            )
            or sequence_policy is not None
            or (sequence_collector is not None and not passive_collection)
            or type(consequence_challenge_ref) is not str
            or not consequence_challenge_ref.strip()
        ):
            raise ValueError(
                "consequence adoption requires explicit matching provisional continuous scope"
            )
    policy_sha256 = (
        consequence_head.model_sha256
        if consequence_head is not None
        else model.model_sha256
        if sequence_policy is None
        else sequence_policy.model_sha256
    )
    if consequence_objective_ref is not None:
        from .red_consequence_choice import branch_recovery_identity

        policy_sha256 = branch_recovery_identity(
            model.model_sha256,
            consequence_head.model_sha256,
            consequence_objective_ref,
            greedy_selection=greedy_selection,
            refine_preparation=refine_preparation,
            defer_unbound_preparation=defer_unbound_preparation,
            allow_singleton_parent_support=allow_singleton_parent_support,
            associate_unique_combat=associate_unique_combat,
            explore_outside_scope=explore_outside_scope,
            explore_on_movement_recurrence=explore_on_movement_recurrence,
        )
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    _record(
        output / "plan.json",
        {
            "schema": "pokemon.red.autonomous-option-run.v1",
            "seed": seed,
            "maximum_decisions": maximum_decisions,
            "maximum_seconds": maximum_seconds,
            "model_sha256": policy_sha256,
            "exploration_mix": (
                0.0
                if consequence_head is not None
                else float(exploration_mix)
                if sequence_policy is None
                else sequence_policy.exploration_mix
            ),
            **({} if sequence_policy is None else {"sequence_policy": sequence_policy.document()}),
            **(
                {}
                if consequence_head is None
                else {
                    "consequence_policy": dict(
                        head=consequence_head.document(),
                        challenge_ref=consequence_challenge_ref,
                        baseline_sha256=model.model_sha256,
                        provisional=True,
                        **(
                            {}
                            if consequence_objective_ref is None
                            else dict(
                                objective_ref=consequence_objective_ref,
                                branch_recovery=True,
                                score_blending=False,
                            )
                        ),
                    )
                }
            ),
            **(
                {
                    "production_train_consequence_inference": train_inference_scope.document(),
                    "production_train_consequence_inference_sha256": train_inference_scope.identity,
                }
                if train_inference and train_inference_scope is not None
                else {}
            ),
            "teacher_actions_allowed": False,
            "independent_evaluation": False,
            "integrated_play": integrated_play,
            "continuous_player": continuous_player,
            **({"continue_safe_route_failures": True} if continue_safe_route_failures else {}),
            **({"scoped_train_selector_inference": train_selector_scope.document(),
                "scoped_train_selector_inference_sha256": train_selector_scope.identity}
               if train_selector_scope is not None else {}),
            **({"greedy_selection": True} if greedy_selection else {}),
            **(
                {"train_form_balanced_exploration": True}
                if train_form_balanced_exploration
                else {}
            ),
            **({"allow_greedy_branch_recovery": True} if allow_greedy_branch_recovery else {}),
            **({"refine_preparation": True} if refine_preparation else {}),
            **({"defer_unbound_preparation": True} if defer_unbound_preparation else {}),
            **({"allow_singleton_parent_support": True} if allow_singleton_parent_support else {}),
            **({"associate_unique_combat": True} if associate_unique_combat else {}),
            **({"explore_outside_scope": True} if explore_outside_scope else {}),
            **({"explore_on_movement_recurrence": True} if explore_on_movement_recurrence else {}),
            **({"collection_cost_frame_horizon": collection_cost_frame_horizon}
               if collection_cost_frame_horizon is not None else {}),
            **(
                {"story_branch_policy": dict(
                    schema="pokemon.red.story-branch-policy.v1",
                    head=None if story_branch_head is None else story_branch_head.document(),
                    head_sha256=None if story_branch_head is None else story_branch_head.model_sha256,
                    exploration_probability=float(story_branch_exploration),
                    **({"segment_lengths": list(story_branch_segment_lengths)} if story_branch_segment_lengths is not None else {}),
                    **({"milestone_commitment": True} if story_milestone_commitment else {}),
                    **(
                        {"kind_commitment": dict(
                            schema="pokemon.red.story-kind-commitment.v1",
                            rule="keep the story objective under way while the party is fit; release after 2 failed steps",
                            **({"respect_combat_preparation_choice": True} if respect_combat_preparation_choice else {}),
                        )}
                        if story_kind_commitment
                        else {}
                    ),
                    kind_level_authority=(model.model_sha256 if sequence_policy is None else sequence_policy.model_sha256),
                    scope=(
                        "story-vs-story, plus kind-level continuation of a fit, unfinished story objective"
                        if story_kind_commitment
                        else "story-vs-story only; kind-level choice unchanged"
                    ),
                )}
                if story_branch_head is not None or story_branch_exploration > 0 or story_branch_segment_lengths is not None
                or story_milestone_commitment
                else {}
            ),
            "maximum_cash_spent": maximum_cash_spent,
            "provenance": dict(provenance),
        },
    )
    if sequence_collector is not None:
        sequence_collector.start(output)
    from .red_story_branch_value import (
        StoryBranchTracker,
        refine_story_branch,
        segment_after_outcome,
        tracker_after_outcome,
    )
    story_branch_enabled = (story_branch_head is not None or story_branch_exploration > 0
                            or story_branch_segment_lengths is not None or story_milestone_commitment)
    from .red_story_branch_value import STORY_MILESTONE_UNITS
    segment_lengths_in_use = (
        story_branch_segment_lengths if story_branch_segment_lengths is not None
        else (STORY_MILESTONE_UNITS, STORY_MILESTONE_UNITS) if story_milestone_commitment else None
    )
    story_tracker = StoryBranchTracker()
    story_segment = None
    kind_commitment = (
        story_kind_commitment_carrier.current
        if story_kind_commitment and story_kind_commitment_carrier is not None
        else None
    )
    started = monotonic()
    outcomes: list[dict[str, object]] = []
    admission_failure = None
    stop = "decision_budget"
    if collection_cost_frame_horizon is not None and (
        type(collection_cost_frame_horizon) is not int or collection_cost_frame_horizon < 1 or not continuous_player
    ):
        raise ValueError("collection cost observation requires a positive continuous-player frame horizon")
    memory = initial_search_memory if initial_search_memory is not None else GoalSearchMemory()
    cash_spent = 0
    for ordinal in range(maximum_decisions):
        if monotonic() - started >= maximum_seconds:
            stop = "wall_time_budget"
            break
        step = output / f"step-{ordinal:03d}"
        step.mkdir()
        before = snapshot()
        _write(step / "before.state", before.state)
        _record(
            step / "before.json",
            {
                "state_sha256": before.sha256,
                "facts": dict(before.facts),
                "safe": before.safe,
            },
        )
        if not before.safe or (continuous_player and not observable_player_boundary(before)):
            stop = "unsafe_decision_boundary"
            break
        try:
            sequence_context = None
            menu_started = monotonic()
            options = observe(ordinal)
            after_menu = snapshot()
            menu_seconds = monotonic() - menu_started
            if after_menu != before:
                raise ValueError("menu construction changed the game")
            if isinstance(options, PlayerBudgetStop):
                if (
                    not continuous_player
                    or not settled_player_boundary(before)
                    or options.state_sha256 != before.sha256
                ):
                    raise ValueError("budget stop lacks a matching settled native boundary")
                _record(step / "budget-stop.json", options.public_dict())
                _write(step / "terminal.state", before.state)
                stop = options.reason
                break
            if isinstance(options, PlayerCurriculumCompletion):
                if (
                    not continuous_player
                    or not settled_player_boundary(before)
                    or options.state_sha256 != before.sha256
                ):
                    raise ValueError(
                        "curriculum completion lacks a matching settled native boundary"
                    )
                _record(step / "curriculum-complete.json", options.public_dict())
                _write(step / "terminal.state", before.state)
                stop = "curriculum_complete"
                break
            support = isinstance(options, RedPlayerSupport)
            if support and not continuous_player:
                raise ValueError("support requires the explicit continuous-player scope")
            if (
                continuous_player
                and not settled_player_boundary(before)
                and (
                    not isinstance(options, RedPlayerSupport)
                    or options.binding.kind is not GoalKind.RECOVER_CONTROL
                )
            ):
                raise ValueError("unsettled input requires an executable control-recovery binding")
            if (
                not isinstance(options, RedPlayerSupport)
                and len(options.menu.available_indices) < 2
            ):
                raise ValueError("autonomous decision requires real alternatives")
            if (
                continuous_player
                and not isinstance(options, RedPlayerSupport)
                and (
                    model.feature_version not in (5, 6, 7, 8, 9, 10, 11, 13, 14, 15, 16)
                    or not 5 <= options.menu.feature_version <= model.feature_version
                    or any(candidate.readiness is None for candidate in options.menu.candidates)
                )
            ):
                raise ValueError("continuous player requires observed readiness at every boundary")
            if integrated_play or (
                continuous_player
                and isinstance(options, RedLiveOptionSet)
                and any(b.tracks_search_effort for b in options.bindings)
            ):
                assert isinstance(options, RedLiveOptionSet)
                objective = objective_key(before.facts)
                options = menu_with_search_history(options, memory, objective)
                survey = source_context.get("verified_preceding_fishing_survey") if ordinal == 0 else None
                if survey is not None:
                    from .red_fishing_survey_history import declared_survey_comparison, observe_rebound_effort
                    if not continuous_player or not declared_survey_comparison(source_context):
                        raise ValueError("same-site fishing comparison requires a continuous DEVELOPMENT copy")
                    options, observation = observe_rebound_effort(options, before, survey)
                    if observation is not None:
                        _record(step / "observed-fishing-site-history.json", observation)
                _record(
                    step / "search-memory-before.json",
                    {
                        "state_sha256": before.sha256,
                        "objective_sha256": objective,
                        "objectives_by_binding": {
                            binding.binding_ref: search_objective_key(binding, objective)
                            for binding in options.bindings
                        },
                        "memory": memory.private_dict(),
                    },
                )
            if movement_revisit_saturation and not isinstance(options, RedPlayerSupport):
                from .red_movement_recurrence import menu_with_movement_history, movement_boundary
                options = menu_with_movement_history(options, memory, before.facts)
                _record(step / "movement-memory-before.json", dict(
                    schema="pokemon.red.movement-recurrence-observation.v1",
                    state_sha256=before.sha256, memory=memory.private_dict(),
                    observed_boundary=movement_boundary(before.facts),
                    binding_endpoints={b.binding_ref: b.movement_endpoint_sha256
                                       for b in options.bindings
                                       if b.movement_endpoint_sha256 is not None},
                    policy="observed-endpoint-marginal-success-v1"))
            collection_contexts = {}
            if collection_cost_frame_horizon is not None and isinstance(options, RedLiveOptionSet):
                from .collection_training_cost import menu_with_collection_costs

                original_menu = options.menu.policy_sha256
                options, quotes, collection_contexts = menu_with_collection_costs(
                    options, memory, before.facts, collection_cost_frame_horizon)
                _record(step / "collection-cost-before.json", dict(
                    state_sha256=before.sha256, original_menu_sha256=original_menu,
                    frame_horizon=collection_cost_frame_horizon, quotes=quotes, contexts=collection_contexts))
            if sequence_policy is not None and not isinstance(options, RedPlayerSupport):
                sequence_context = sequence_collector.choice_context(
                    options, boundary_sha256=before.sha256
                )
                if sequence_policy.selection_mode == "stable_costly_recurrence":
                    from dataclasses import replace
                    from .red_costly_search_recurrence import search_contexts, witnesses
                    costly_contexts = search_contexts(options, before.facts)
                    _record(step / "costly-search-memory-before.json", dict(
                        state_sha256=before.sha256, contexts=costly_contexts,
                        memory=memory.private_dict()))
                    sequence_context = replace(sequence_context, costly_search_witnesses=
                                               witnesses(costly_contexts, memory, before.facts))
                sequence_policy.validate_selection(
                    model,
                    options.menu,
                    sequence_context,
                    utility=sequence_policy.immediate_utility,
                    exploration_mix=sequence_policy.exploration_mix,
                )
        except Exception as error:
            admission_failure = {
                "error_type": type(error).__name__,
                "error": str(error),
                "error_chain": _exception_chain(error),
                "failure_phase": "admission",
            }
            _record(
                step / "admission-failure.json",
                admission_failure,
            )
            terminal = snapshot()
            _write(step / "terminal.state", terminal.state)
            stop = "menu_unavailable"
            break
        decision_seed = int(canonical_sha256({"seed": seed, "ordinal": ordinal})[:16], 16)
        parent_greedy = greedy_selection
        child_scope_available = False
        if explore_outside_scope and not isinstance(options, RedPlayerSupport):
            from .red_consequence_choice import _branch_scope_available, branch_recovery_objectives

            child_scope_available = _branch_scope_available(
                options, branch_recovery_objectives(consequence_objective_ref)
            )
            parent_greedy = greedy_selection and child_scope_available
        _record(
            step / "intent.json",
            {
                "menu": options.public_dict(),
                "state_sha256": before.sha256,
                "model_sha256": policy_sha256,
                "selection_seed": decision_seed,
                "query_may_be_consumed": not isinstance(options, RedPlayerSupport)
                and len(
                    {
                        (
                            options.menu.candidate_vector(i)
                            if sequence_context is None
                            else sequence_context.vectors(options.menu)[i]
                        )
                        for i in options.menu.available_indices
                    }
                )
                > 1,
                **(
                    {}
                    if sequence_context is None
                    else {"sequence_context": sequence_context.document()}
                ),
                **_private_story_contexts(options),
                "private_selection_authority": record_selection_authority(
                    options,
                    allow_earning_exploration=continuous_player,
                    greedy_selection=parent_greedy,
                ),
                **({"private_branch_sampling_policy": {
                    "explore_outside_scope": True,
                    "child_scope_available": child_scope_available,
                    "declared_greedy_selection": greedy_selection,
                    "effective_parent_greedy_selection": parent_greedy,
                }} if explore_outside_scope else {}),
                **({"private_recurrence_sampling_policy": {
                    "explore_on_movement_recurrence": True,
                    "trigger_rule": "greedy-selected-observed-unchanged-endpoint-v1",
                    "declared_greedy_selection": greedy_selection,
                }} if explore_on_movement_recurrence else {}),
            },
        )
        # Keep persistence adjacent to selection. No enum assertion, selected
        # callback resolution, or result-dependent validation precedes the write.
        choice: RedLiveOptionChoice | RedPlayerSupportChoice
        selection_started = monotonic()
        if isinstance(options, RedPlayerSupport):
            choice = RedPlayerSupportChoice(options)
        elif consequence_head is not None:
            from .red_consequence_choice import (
                select_branch_recovery_live_option,
                select_consequence_live_option,
            )

            try:
                choice = (
                    select_consequence_live_option(
                        options,
                        consequence_head,
                        challenge_ref=consequence_challenge_ref,
                        seed=decision_seed,
                    )
                    if consequence_objective_ref is None
                    else select_branch_recovery_live_option(
                        model,
                        options,
                        consequence_head,
                        objective_ref=consequence_objective_ref,
                        seed=decision_seed,
                        greedy_selection=greedy_selection,
                        refine_preparation=refine_preparation,
                        defer_unbound_preparation=defer_unbound_preparation,
                        allow_singleton_parent_support=allow_singleton_parent_support,
                        associate_unique_combat=associate_unique_combat,
                        explore_outside_scope=explore_outside_scope,
                        explore_on_movement_recurrence=explore_on_movement_recurrence,
                        source_state_sha256=before.sha256,
                    )
                )
            except (ValueError, TypeError) as error:
                _record(
                    step / "selection-failure.json",
                    dict(
                        error_type=type(error).__name__,
                        error=str(error),
                        teacher_fallback=False,
                        actions_executed=0,
                    ),
                )
                _write(step / "terminal.state", before.state)
                stop = "consequence_context_unavailable"
                break
        else:
            choice = (
                select_red_live_option(
                    model,
                    options,
                    seed=decision_seed,
                    allow_earning_exploration=True,
                    greedy_selection=greedy_selection,
                    **(
                        {"form_balanced_exploration": True}
                        if train_form_balanced_exploration
                        else {}
                    ),
                    **(
                        dict(exploration_mix=float(exploration_mix))
                        if sequence_policy is None
                        else dict(
                            sequence_policy=sequence_policy,
                            sequence_context=sequence_context,
                            utility=sequence_policy.immediate_utility,
                            exploration_mix=sequence_policy.exploration_mix,
                        )
                    ),
                )
                if continuous_player
                else select_red_live_option(model, options, seed=decision_seed)
            )
        deterministic_story_branch = False
        if (
            story_branch_enabled
            and isinstance(choice, RedLiveOptionChoice)
            and choice.mode in {RedLiveOptionSelectionMode.MODEL_GREEDY, RedLiveOptionSelectionMode.MODEL_EXPLORATION}
            and choice.consequence_receipt_json is None
            and (choice.branch_recovery is None
                 or (choice.branch_recovery.child is None and choice.branch_recovery.unique_combat_witness is None))
        ):
            story_decision = refine_story_branch(
                choice, head=story_branch_head, tracker=story_tracker,
                exploration_probability=float(story_branch_exploration), seed=decision_seed,
                **({"segment": story_segment, "segment_lengths": segment_lengths_in_use}
                   if segment_lengths_in_use is not None else {}),
            )
            if story_decision is not None:
                if segment_lengths_in_use is not None:
                    story_segment = story_decision.segment
                _record(step / "story-branch-private.json", dict(
                    story_decision.document(),
                    parent_choice=choice.public_dict(),
                    tracker=story_tracker.document(),
                    objective_refs=[options.binding(i).story_objective_ref for i in story_decision.story_indices],
                ))
                deterministic_story_branch = story_decision.deterministic_continuation
                choice = story_decision.choice()
        kind_receipt = None
        if story_kind_commitment and kind_commitment is not None:
            from .red_story_kind_commitment import commit_story_kind, commitment_after_choice

            choice, kind_receipt = commit_story_kind(choice, kind_commitment,
                **({"respect_combat_preparation_choice": True} if respect_combat_preparation_choice else {}))
            if kind_receipt is not None:
                _record(step / "story-kind-commitment.json", kind_receipt)
                kind_commitment = commitment_after_choice(kind_commitment, kind_receipt)
                if story_kind_commitment_carrier is not None:
                    story_kind_commitment_carrier.current = kind_commitment
        if isinstance(choice, RedLiveOptionChoice):
            cash_receipt = choice.private_consequence_receipt()
            if cash_receipt is not None:
                _record(step / "consequence-cash-private.json", cash_receipt)
        if (
            isinstance(choice, RedLiveOptionChoice)
            and choice.branch_recovery is not None
            and choice.branch_recovery.unique_combat_witness is not None
        ):
            witness = choice.branch_recovery.unique_combat_witness
            from .red_consequence_choice import branch_recovery_objectives

            witness.validate(
                choice.branch_recovery.parent,
                branch_recovery_objectives(choice.branch_recovery.objective_ref),
                source_state_sha256=before.sha256,
            )
            _record(step / "preparation-combat-private.json", witness.document())
        _record(step / "decision.json", choice.public_dict())
        selection_seconds = monotonic() - selection_started
        diagnostic_started = monotonic()
        diagnostics = None
        if (
            not isinstance(options, RedPlayerSupport)
            and isinstance(choice, RedLiveOptionChoice)
            and choice.mode
            in {
                RedLiveOptionSelectionMode.MODEL_GREEDY,
                RedLiveOptionSelectionMode.MODEL_EXPLORATION,
            }
            and sequence_policy is None
            and consequence_head is None
        ):
            from .living_dex_goal_policy import DEFAULT_LIVING_DEX_GOAL_UTILITY

            diagnostics = model.diagnose_menu(
                options.menu,
                DEFAULT_LIVING_DEX_GOAL_UTILITY
                if sequence_policy is None
                else sequence_policy.immediate_utility,
                selected_index=choice.selected_candidate_index,
            )
            diagnostics.update(
                selection_mode=choice.mode.value,
                actual_selection_scores=list(choice.scores),
                actual_selection_probabilities=list(choice.probabilities),
                baseline_head_used_for_selection=(
                    sequence_policy is None
                    and consequence_head is None
                    and choice.mode
                    in {
                        RedLiveOptionSelectionMode.MODEL_GREEDY,
                        RedLiveOptionSelectionMode.MODEL_EXPLORATION,
                    }
                ),
                selection_policy_sha256=policy_sha256,
                training_admission=False,
            )
            _record(step / "selection-diagnostics.json", diagnostics)
        diagnostic_seconds = monotonic() - diagnostic_started
        deterministic_storage = (
            choice.mode is RedLiveOptionSelectionMode.DETERMINISTIC_SAFETY
            and choice.selected_binding.kind is GoalKind.MANAGE_STORAGE
        )
        deterministic_support = continuous_player and (
            support
            or (
                choice.mode is RedLiveOptionSelectionMode.DETERMINISTIC_SAFETY
                and choice.selected_binding.kind
                in {
                    GoalKind.RESTORE_TEAM,
                    GoalKind.RESUPPLY,
                    GoalKind.MANAGE_STORAGE,
                }
            )
        )
        if (
            choice.mode
            not in {
                RedLiveOptionSelectionMode.MODEL_EXPLORATION,
                RedLiveOptionSelectionMode.MODEL_GREEDY,
                RedLiveOptionSelectionMode.EQUIVALENT_EXPLORATION,
            }
            and not deterministic_storage
            and not deterministic_support
        ):
            stop = "safety_boundary_requires_separate_recovery"
            break
        selected = choice.selected_binding
        if continuous_player:
            # Spending cannot borrow unearned income or offset a prior goal's
            # observed cash debit. Quote-free travel conservatively reserves all
            # current cash since a battle can lose money en route.
            cash = before.facts.get("cash")
            quote = selected.resource_quote
            debit = (
                selected.maximum_cash_debit
                if selected.maximum_cash_debit is not None
                else cash
                if quote is None or quote.expected_income
                else quote.purchase_cost
            )
            _record(
                step / "cash-admission.json",
                {
                    "binding_ref": selected.binding_ref,
                    "cash": cash,
                    "prior_debits": cash_spent,
                    "maximum_cash_spent": maximum_cash_spent,
                    "reserved_debit": debit,
                    "certified_exposure": selected.maximum_cash_debit,
                    "ordinary_game_economy": ordinary_economy,
                },
            )
            if (
                type(cash) is not int
                or cash < 0
                or type(debit) is not int
                or (quote is not None and quote.funding_proceeds)
                or (maximum_cash_spent is not None and cash_spent + debit > maximum_cash_spent)
            ):
                stop = "continuous_spending_boundary"
                break
        debit_bound = spending_bound(selected) if integrated_play else None
        if integrated_play and (
            debit_bound is None or cash_spent + debit_bound > maximum_cash_spent
        ):
            stop = "integrated_scope_or_spending_boundary"
            break
        if sequence_collector is not None:
            try:
                sequence_collector.before_execution(
                    ordinal=ordinal,
                    boundary_sha256=before.sha256,
                    choice=choice,
                )
            except Exception as error:
                # No input has started for this prepared choice. Retain every
                # earlier closed outcome and stop; do not fabricate an executor
                # result or let a collector error erase the episode closeout.
                admission_failure = dict(
                    error_type=type(error).__name__, error=str(error),
                    error_chain=_exception_chain(error), failure_phase="sequence_collection",
                )
                _record(step / "admission-failure.json", admission_failure)
                terminal = snapshot()
                _write(step / "terminal.state", terminal.state)
                stop = "sequence_collection_unavailable"
                break
        _record(
            step / "execution-started.json",
            {
                "selected_binding_ref": selected.binding_ref,
                "selected_kind": selected.kind.value,
                "menu_sha256": (
                    options.policy_sha256
                    if isinstance(options, RedPlayerSupport)
                    else options.menu.policy_sha256
                ),
                "state_sha256": before.sha256,
            },
        )
        report = None
        verification = None
        execution_error: BaseException | None = None
        execution_started = monotonic()
        execution_seconds = verification_seconds = None
        failure_phase = "execution"
        try:
            report = selected.execute()
            execution_seconds = monotonic() - execution_started
            if continuous_player and not isinstance(report, GoalExecutionReport):
                report = None
                raise ValueError("continuous player execution report is invalid")
            failure_phase = "verification"
            verification_started = monotonic()
            verification = selected.verify(report)
            verification_seconds = monotonic() - verification_started
            if continuous_player and not isinstance(verification, GoalVerification):
                verification = None
                raise ValueError("continuous player verification is invalid")
        except RestorationBudgetExhausted as error:
            # This is a measured pre-input limit, not a completed goal or a
            # recoverable game loss. Retain any paid tail and the original error.
            execution_error = error
            if failure_phase == "execution":
                verification = GoalVerification.failed(GoalFailureReason.EXECUTION_BUDGET_EXHAUSTED)
        except BaseException as error:
            execution_error = error
        finally:
            phase_ended = monotonic()
            if execution_seconds is None:
                execution_seconds = phase_ended - execution_started
            elif verification_seconds is None and failure_phase == "verification":
                verification_seconds = phase_ended - verification_started
            terminal_started = monotonic()
            terminal = snapshot()
            terminal_observation_seconds = monotonic() - terminal_started
            _write(step / "terminal.state", terminal.state)
            cost = measured_cost(before.facts, terminal.facts, report)
            counters = observed_cost(before.facts, terminal.facts)
            ordinary_setback = integrated_play and ordinary_paid_search_setback(
                selected,
                before,
                terminal,
                report,
                verification,
                execution_error,
            )
            if continuous_player:
                ordinary_setback = ordinary_player_setback(
                    selected,
                    before,
                    terminal,
                    report,
                    verification,
                    execution_error,
                )
            route_setback = (
                safe_route_setback(
                    selected, before, terminal, report, verification, execution_error
                )
                if continue_safe_route_failures
                else None
            )
            from .red_player_lesson_runtime import (
                player_diagnostic_delta,
                player_outcome_diagnostics,
            )

            outcome_phase_seconds: dict[str, float | None] = dict(
                menu_and_boundary_observation=menu_seconds,
                selection_and_receipt=selection_seconds,
                selection_diagnostics=diagnostic_seconds,
                execution=execution_seconds,
                verification=verification_seconds,
                terminal_observation=terminal_observation_seconds,
            )
            outcome: dict[str, object] = {
                "ordinal": ordinal,
                "selected_kind": selected.kind.value,
                "choice": choice.public_dict(),
                # A commitment may replace the model's kind choice. Its
                # model_exploration mode is a legacy selection receipt, not
                # evidence that the model chose the executed action.
                "learning_eligible": not (deterministic_story_branch or (kind_receipt and kind_receipt.get("overridden") is True))
                and choice.mode in {
                    RedLiveOptionSelectionMode.MODEL_EXPLORATION,
                    RedLiveOptionSelectionMode.MODEL_GREEDY,
                },
                "support_role": (
                    options.support_role
                    if isinstance(options, RedPlayerSupport)
                    else "deterministic_storage_safety"
                    if deterministic_storage
                    else "deterministic_player_safety"
                    if deterministic_support
                    else "equivalent_goal_exploration"
                    if choice.mode is RedLiveOptionSelectionMode.EQUIVALENT_EXPLORATION
                    else "deterministic_story_continuation"
                    if deterministic_story_branch or (kind_receipt and kind_receipt.get("overridden") is True)
                    else None
                ),
                "before_state_sha256": before.sha256,
                "terminal_state_sha256": terminal.sha256,
                "before": dict(before.facts),
                "after": dict(terminal.facts),
                "safe_terminal": terminal.safe,
                "verification": None if verification is None else verification.status.value,
                "failure_reason": (
                    None
                    if verification is None or verification.failure_reason is None
                    else verification.failure_reason.value
                ),
                "evidence": None if report is None else dict(report.evidence),
                "error_type": None if execution_error is None else type(execution_error).__name__,
                "error": None if execution_error is None else str(execution_error),
                "error_chain": _exception_chain(execution_error),
                "failure_phase": None if execution_error is None else failure_phase,
                "phase_seconds": outcome_phase_seconds,
                "measured_cost": cost,
                "observed_cost": counters,
                "diagnostic_delta": player_diagnostic_delta(before.facts, terminal.facts),
                "ordinary_setback": ordinary_setback,
                **(
                    {"recoverable_route_setback": route_setback}
                    if continue_safe_route_failures
                    else {}
                ),
                "elapsed_seconds": monotonic() - execution_started,
            }
            outcome_diagnostic_started = monotonic()
            outcome["diagnostic_review"] = player_outcome_diagnostics(
                outcome,
                resource_quote=(
                    None
                    if selected.resource_quote is None
                    else selected.resource_quote.public_dict()
                ),
                selection_diagnostics=diagnostics,
            )
            outcome_phase_seconds["outcome_diagnostics"] = monotonic() - outcome_diagnostic_started
            outcome["elapsed_seconds"] = monotonic() - execution_started
            _record(step / "outcome.json", outcome)
            outcomes.append(outcome)
            if collection_cost_frame_horizon is not None and selected.binding_ref in collection_contexts:
                from .collection_training_cost import measured_training_cost

                context = collection_contexts[selected.binding_ref]
                observation = measured_training_cost(outcome, context["transition"])
                if observation is not None:
                    memory.record_collection_training_cost(context["key"], observation)
                    _record(step / "collection-cost-after.json", dict(
                        state_sha256=terminal.sha256, context_sha256=context["key"],
                        observed=asdict(observation), outcome_sha256=canonical_sha256(outcome)))
            if story_branch_enabled:
                story_tracker = tracker_after_outcome(story_tracker, selected, outcome)
                story_segment = segment_after_outcome(story_segment, selected, outcome)
            if story_kind_commitment:
                from .red_story_kind_commitment import commitment_after_outcome

                kind_commitment = commitment_after_outcome(kind_commitment, selected, outcome)
                if story_kind_commitment_carrier is not None:
                    story_kind_commitment_carrier.current = kind_commitment
            if sequence_collector is not None:
                sequence_collector.after_outcome(outcome)
        if continuous_player and counters is not None:
            # Retain measured cash loss even when verification or control failed.
            # This is a sum of per-goal net debits, not inferred gross purchases.
            cash_spent += max(0, counters["cash_spent"])
            if (
                selected.maximum_cash_debit is not None
                and counters["cash_spent"] > selected.maximum_cash_debit
            ):
                stop = "cash_exposure_exceeded"
                if execution_error is not None and not isinstance(execution_error, Exception):
                    raise execution_error
                break
        if type(execution_error) is RestorationBudgetExhausted and failure_phase == "execution":
            stop = "restoration_budget"
            break
        if execution_error is not None:
            if not isinstance(execution_error, Exception):
                raise execution_error
            if route_setback is None:
                stop = "execution_failed"
                break
        if route_setback is None and (
            verification is None
            or (verification.status is not GoalDecisionOutcome.SUCCEEDED and not ordinary_setback)
        ):
            stop = "verification_failed"
            break
        if not terminal.safe or (continuous_player and not settled_player_boundary(terminal)):
            stop = "unsafe_terminal"
            break
        if terminal.state == before.state:
            stop = "no_state_progress"
            break
        if continuous_player:
            if cost is None and route_setback is None:
                stop = "unaccounted_continuous_cost"
                break
            if maximum_cash_spent is not None and cash_spent > maximum_cash_spent:
                stop = "continuous_spending_exceeded"
                break
            if ordinary_setback and (settled_evolution_partial(selected, report)
                    or settled_evolution_zero_progress(selected, report)):
                # Its measured dose reserved enough inputs to return the party.
                # Renew the finite execution port before offering another goal;
                # do not spend that return reserve starting a second PC loan.
                stop = "settlement_budget"
                break
        if integrated_play:
            if cost is None or not 0 <= cost["cash_spent"] <= debit_bound:
                stop = "unaccounted_integrated_cost"
                break
            cash_spent += cost["cash_spent"]
        if (integrated_play or continuous_player) and selected.tracks_search_effort:
            # A certified settled route exception has actual observed cost but
            # no completed executor report. Keep measured_cost unknown in the
            # failed receipt; reuse only that narrow certificate for memory.
            search_cost = (
                cost
                if cost is not None
                else (route_setback["cost"] if route_setback is not None else None)
            )
            if search_cost is None or search_cost["actions"] <= 0:
                stop = "unaccounted_search_cost"
                break
            selected_objective = search_objective_key(selected, objective_key(before.facts))
            if sequence_policy is not None and sequence_policy.selection_mode == "stable_costly_recurrence":
                from .red_costly_search_recurrence import record_failure, search_contexts
                from types import SimpleNamespace
                selected_context = search_contexts(SimpleNamespace(bindings=(selected,)), before.facts)[0]
                record_failure(memory, selected_context, before, terminal, report, verification, execution_error)
            memory.record(
                selected.search_memory_source,
                selected_objective,
                exhausted=ordinary_setback,
                actions=search_cost["actions"],
                frames=search_cost["frames"],
            )
            _record(
                step / "search-memory-after.json",
                {
                    "state_sha256": terminal.sha256,
                    "outcome_sha256": canonical_sha256(outcome),
                    "objective_sha256": selected_objective,
                    "memory": memory.private_dict(),
                    "cumulative_cash_spent": cash_spent,
                },
            )
        if movement_revisit_saturation and settled_player_boundary(terminal):
            from .player_option_story_unit import OptionStoryUnit
            from .red_movement_recurrence import observe_movement_boundary, record_movement_return
            recurrence = (record_movement_return(memory, before.facts, terminal.facts)
                          if selected.story_unit == OptionStoryUnit("movement", True)
                          else None)
            observe_movement_boundary(memory, terminal.facts)
            if story_kind_commitment and recurrence is not None:
                from .red_story_kind_commitment import commitment_after_movement_return

                kind_commitment = commitment_after_movement_return(kind_commitment, recurrence)
                if story_kind_commitment_carrier is not None:
                    story_kind_commitment_carrier.current = kind_commitment
            if recurrence is not None:
                _record(step / "movement-memory-after.json", dict(
                    state_sha256=terminal.sha256, memory=memory.private_dict(),
                    recurrence=recurrence, outcome_sha256=canonical_sha256(outcome)))
                if recurrence["stop_required"]:
                    stop = "repeated_movement_without_progress"
                    break
        # A declared consequence is an administrative stop after the admitted
        # outcome. Preserve its measured feedback before closing the segment.
        if stop_after_outcome is not None and stop_after_outcome():
            stop = "declared_consequence_complete"
            break
    from .red_player_lesson_runtime import player_stop_diagnostics

    result: dict[str, object] = {
        "schema": "pokemon.red.autonomous-option-result.v1",
        "stop_reason": stop,
        "stop_diagnostics": player_stop_diagnostics(
            stop,
            admission_failure or (outcomes[-1] if outcomes else None),
        ),
        **({"admission_failure": admission_failure} if admission_failure else {}),
        "executed_decisions": len(outcomes),
        "successful_decisions": sum(row["verification"] == "succeeded" for row in outcomes),
        "teacher_actions": 0,
        "model_decisions": sum(row["learning_eligible"] is True for row in outcomes),
        "support_decisions": sum(row["support_role"] is not None for row in outcomes),
        "model_sha256": policy_sha256,
        "integrated_play": integrated_play,
        "continuous_player": continuous_player,
        "accounted_cash_spent": cash_spent,
        "ordinary_setbacks": sum(row["ordinary_setback"] is True for row in outcomes),
        **(
            {
                "recoverable_route_setbacks": sum(
                    row.get("recoverable_route_setback") is not None for row in outcomes
                )
            }
            if continue_safe_route_failures
            else {}
        ),
        "outcomes": outcomes,
        **(
            {"search_memory": memory.private_dict()} if integrated_play or continuous_player else {}
        ),
    }
    if consequence_objective_ref is not None:
        queries = 0
        for row in outcomes:
            recorded_choice = row["choice"]
            if not isinstance(recorded_choice, dict):
                raise ValueError("recorded choice is not a policy receipt")
            receipt = recorded_choice.get("branch_recovery")
            if receipt is not None:
                if not isinstance(receipt, dict) or type(receipt.get("model_queries")) is not int:
                    raise ValueError("branch recovery query receipt differs")
                queries += receipt["model_queries"]
        result["strategic_policy_queries"] = queries
    _record(output / "result.json", result)
    if sequence_collector is not None:
        sequence_collector.finish()
    return result
