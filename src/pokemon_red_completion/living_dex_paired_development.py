"""One descriptive, same-origin comparison using the existing selected-arm runtime.

Both choices are committed before either arm is opened. The deterministic
completion-first control is never represented as a learned prediction. No
outcome from this journal is a training target or a promotion decision.
"""

from __future__ import annotations

import hashlib
import traceback
from collections.abc import Callable, Mapping
from contextlib import suppress
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from pokemon_red_completion.claim_first_admission import (
    ClaimFirstAdmissionError,
    ClaimFirstRootPair,
    claim_first_pair_registry,
    read_root_pair_claim,
)
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalManagerQuestion,
    GoalOpportunity,
)
from pokemon_red_completion.goal_manager_runtime import CompletionFirstGoalTeacher
from pokemon_red_completion.living_dex_causal_journal import (
    LivingDexCausalResolvedArm,
    LivingDexCausalScenario,
    LivingDexControllerGate,
    restore_living_dex_observed_outcome,
)
from pokemon_red_completion.living_dex_goal_policy import DEFAULT_LIVING_DEX_GOAL_UTILITY
from pokemon_red_completion.living_dex_option_value import (
    LivingDexCensorReason,
    LivingDexObservedOutcome,
    LivingDexOptionKind,
    LivingDexOptionValueModel,
    LivingDexOutcomeStatus,
    LivingDexPredictedOutcome,
    living_dex_option_context_from_goal_situation,
)
from pokemon_red_completion.living_dex_policy_development import (
    LivingDexPolicyDevelopmentDecision,
    commit_living_dex_policy_development_decision,
    living_dex_option_utility_sha256,
)
from pokemon_red_completion.living_dex_policy_development_journal import (
    _ensure_store_anchor,
    _observe_after,
    _read_action_trace,
)
from pokemon_red_completion.private_artifacts import PrivateArtifactRoot
from pokemon_red_completion.provenance import canonical_sha256

_SCHEMA = "pokemon.core.private-living-dex-paired-development.v1"
_COLLECTION = "living-dex-paired-development-v1"
_KIND = "living_dex_paired_development"
_GOAL_BY_OPTION = {
    LivingDexOptionKind.UNLOCK_ACCESS: GoalKind.ADVANCE_STORY,
    LivingDexOptionKind.ACQUIRE: GoalKind.ACQUIRE_SPECIES,
    LivingDexOptionKind.DEVELOP: GoalKind.DEVELOP_TEAM,
    LivingDexOptionKind.EVOLVE: GoalKind.EVOLVE_SPECIES,
    LivingDexOptionKind.RESUPPLY: GoalKind.RESUPPLY,
    LivingDexOptionKind.MANAGE_STORAGE: GoalKind.MANAGE_STORAGE,
    LivingDexOptionKind.EXPLORE: GoalKind.EXPLORE,
}


class LivingDexPairedDevelopmentError(ValueError):
    """The declared same-origin pair cannot execute or recover honestly."""


def completion_first_question(scenario: LivingDexCausalScenario) -> GoalManagerQuestion:
    """Restore the original nine needs; never invert the lossy seven-need projection.

    Only inert bindings reach the deterministic control. Effort and risk are the
    exact prospective provider estimates already present in the learned menu.
    The learned scorer additionally sees the declared travel-cost feature.
    """

    opportunities = []
    for index, candidate in enumerate(scenario.menu.candidates):
        kind = _GOAL_BY_OPTION.get(candidate.features.kind)
        if kind is None or index not in scenario.menu.available_indices:
            raise LivingDexPairedDevelopmentError("paired provider menu is unsupported")
        opportunities.append(
            GoalOpportunity(
                f"inert-option-{index}",
                kind,
                GoalAvailability.AVAILABLE,
                candidate.features.execution_effort,
                candidate.features.party_risk,
            ).policy_dict()
        )
    question = GoalManagerQuestion.from_policy_input(
        {
            "schema": "pokemon.core.goal-manager-input.v1",
            "situation": scenario.origin_observation.get("situation"),
            "candidates": opportunities,
        }
    )
    if living_dex_option_context_from_goal_situation(question.situation) != scenario.menu.context:
        raise LivingDexPairedDevelopmentError("paired origin pressures differ from menu")
    return question


def private_failure_diagnostic(error: BaseException) -> dict[str, object]:
    """Keep cause and source location while respecting the store's path-free contract."""
    message = str(error)
    return {
        "exception_type": type(error).__name__,
        "message": (
            "Path-bearing exception message withheld; exact text bound by digest"
            if any(token in message for token in ("/", "\\", "~", "file:"))
            else message[:4000]
        ),
        "message_sha256": hashlib.sha256(message.encode("utf-8")).hexdigest(),
        "frames": [
            {"module_file": Path(frame.filename).name, "function": frame.name, "line": frame.lineno}
            for frame in traceback.extract_tb(error.__traceback__, limit=12)
        ],
    }


def publish_paired_record(
    store: PrivateArtifactRoot,
    record_id: str,
    document: Mapping[str, object],
) -> dict[str, object]:
    """Idempotent immutable publication, rejecting rather than overwriting drift."""

    prior = read_paired_record(store, record_id)
    if prior is None:
        prior = store.publish_sealed_record(record_id, kind=_KIND, record=dict(document)).read()
    if prior != dict(document):
        raise LivingDexPairedDevelopmentError("paired durable record differs")
    return prior


def read_paired_record(store: PrivateArtifactRoot, record_id: str) -> dict[str, object] | None:
    record = store.find_sealed_record(record_id, expected_kind=_KIND)
    return None if record is None else record.read()


def ensure_paired_claim(registry: Path, claim: ClaimFirstRootPair) -> bool:
    """Return True only for a new claim; a different owner always fails closed."""

    try:
        existing = read_root_pair_claim(registry, claim.claim_sha256)
    except ClaimFirstAdmissionError:
        with claim_first_pair_registry(registry) as transaction:
            existing = transaction.claim(claim)
        if existing != claim:
            raise LivingDexPairedDevelopmentError("paired new root claim differs") from None
        return True
    if existing != claim:
        raise LivingDexPairedDevelopmentError("paired recovered root claim differs")
    return False


def _restore_decision(document: object) -> LivingDexPolicyDevelopmentDecision:
    if not isinstance(document, dict):
        raise LivingDexPairedDevelopmentError("paired model decision is missing")
    try:
        decision = LivingDexPolicyDevelopmentDecision(
            causal_identity_sha256=document["causal_identity_sha256"],
            menu_sha256=document["menu_sha256"],
            model_sha256=document["model_sha256"],
            utility_sha256=document["utility_sha256"],
            selected_candidate_index=document["selected_candidate_index"],
            candidate_scores=tuple(document["candidate_scores"]),
            predicted_outcomes=tuple(
                None if row is None else tuple(row) for row in document["predicted_outcomes"]
            ),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise LivingDexPairedDevelopmentError("paired model decision is invalid") from error
    if decision.private_dict() != document:
        raise LivingDexPairedDevelopmentError("paired model decision fields differ")
    return decision


@dataclass(frozen=True, slots=True)
class LivingDexPairedDevelopmentReceipt:
    commitment: dict[str, object]
    arms: tuple[dict[str, object], dict[str, object]]

    def public_dict(self) -> dict[str, object]:
        public_arms = []
        utilities: list[float | None] = []
        losses: list[float | None] = []
        for actor, arm in zip(("model", "control"), self.arms, strict=True):
            raw = arm.get("outcome")
            outcome = restore_living_dex_observed_outcome(raw) if isinstance(raw, Mapping) else None
            vector = None if outcome is None else outcome.target_vector
            utility = (
                None
                if vector is None
                else DEFAULT_LIVING_DEX_GOAL_UTILITY.score(LivingDexPredictedOutcome(*vector))
            )
            utilities.append(utility)
            losses.append(None if outcome is None else outcome.irreversible_loss)
            public_arms.append(
                {
                    "actor": actor,
                    "status": arm["status"],
                    "selected_candidate_index": arm["selected_candidate_index"],
                    "outcome": None if outcome is None else outcome.public_dict(),
                    "realized_utility": utility,
                    "controller_actions": arm.get("controller_actions"),
                    "emulator_frames": arm.get("emulator_frames"),
                    "execution_raised": arm.get("execution_raised", False),
                    "result_sha256": canonical_sha256(arm),
                }
            )
        settled = all(value is not None for value in utilities)
        delta = float(utilities[0]) - float(utilities[1]) if settled else None  # type: ignore[arg-type]
        safety_regression = (
            None if not settled else float(losses[0]) > float(losses[1])  # type: ignore[arg-type]
        )
        return {
            "schema": "pokemon.core.living-dex-paired-development.v1",
            "commitment_sha256": canonical_sha256(self.commitment),
            "model_sha256": self.commitment["model_sha256"],
            "arms": public_arms,
            "utility_delta": delta,
            "model_only_irreversible_loss": safety_regression,
            "descriptive_model_win": (
                delta is not None
                and delta > 0
                and safety_regression is False
                and not any(arm.get("execution_raised", False) for arm in self.arms)
            ),
            "evidence_scope": "descriptive_development_only",
            "promotion_authorized": False,
            "training_targets_emitted": 0,
            "model_fits": 0,
            "private_path_fields": 0,
        }


def execute_living_dex_paired_development(
    scenario: LivingDexCausalScenario,
    model: LivingDexOptionValueModel,
    *,
    expected_model_sha256: str,
    store: PrivateArtifactRoot,
    claim_registry: Path,
    failpoint: Callable[[str], None] | None = None,
    observer: Callable[[str, Mapping[str, object]], None] | None = None,
) -> LivingDexPairedDevelopmentReceipt:
    """Commit both choices, then execute/recover exactly two origin-reset arms.

    The adapter restores and verifies identical origin bytes inside each resolver.
    An attempted arm never retries, including a pre-input construction failure.
    Recovery may continue only the other, never-started arm. No fit is imported.
    """

    scenario.__post_init__()
    model.__post_init__()
    if scenario.identity.partition != "development":
        raise LivingDexPairedDevelopmentError("paired runner requires development")
    if model.model_sha256 != expected_model_sha256:
        raise LivingDexPairedDevelopmentError("paired model identity differs")
    question = completion_first_question(scenario)
    control = CompletionFirstGoalTeacher()
    control_index = control.select(question).selected_index
    utility = DEFAULT_LIVING_DEX_GOAL_UTILITY
    binding = {
        "schema": _SCHEMA,
        "causal_identity": scenario.identity.private_dict(),
        "model_sha256": expected_model_sha256,
        "origin_observation": dict(scenario.origin_observation),
        "utility_sha256": living_dex_option_utility_sha256(utility),
        "control": control.public_dict(),
        "control_question": {
            "schema": "pokemon.core.goal-manager-input.v1",
            "situation": question.situation.policy_dict(),
            "candidates": [item.policy_dict() for item in question.opportunities],
        },
        "control_selected_candidate_index": control_index,
        "arm_order": ["model", "control"],
    }
    prefix = "lpd-pair-" + scenario.identity.identity_sha256[:32]
    with store.collection_session(_COLLECTION):
        anchor = _ensure_store_anchor(store)
        claim = ClaimFirstRootPair(
            logical_root_sha256=scenario.identity.logical_root_sha256,
            physical_root_sha256=scenario.identity.physical_root_sha256,
            stage="living-dex-paired-development",
            execution_identity_sha256=canonical_sha256({"binding": binding, "store": anchor}),
            plan_sha256=canonical_sha256(binding),
            slot_sha256=scenario.identity.identity_sha256,
            runner_sha256=scenario.identity.runner_sha256,
            source_commit=scenario.identity.source_commit,
        )
        ensure_paired_claim(claim_registry, claim)
        saved = read_paired_record(store, prefix + "-choices")
        if saved is None:
            decision = commit_living_dex_policy_development_decision(
                scenario,
                model,
                utility=utility,
                expected_model_sha256=expected_model_sha256,
            )
        else:
            decision = _restore_decision(saved.get("model_decision"))
        if (
            decision.causal_identity_sha256 != scenario.identity.identity_sha256
            or decision.menu_sha256 != scenario.menu.policy_sha256
            or decision.model_sha256 != expected_model_sha256
            or decision.utility_sha256 != binding["utility_sha256"]
        ):
            raise LivingDexPairedDevelopmentError("paired restored decision binding differs")
        commitment = publish_paired_record(
            store,
            prefix + "-choices",
            {
                **binding,
                "model_decision": decision.private_dict(),
                "pair_claim_sha256": claim.claim_sha256,
            },
        )
        _notify(observer, "choices_committed", commitment)
        _trip(failpoint, "after_both_choices")
        model_arm = _execute_arm(
            scenario,
            "model",
            decision.selected_candidate_index,
            commitment,
            store,
            prefix,
            failpoint,
            observer,
        )
        control_arm = _execute_arm(
            scenario,
            "control",
            control_index,
            commitment,
            store,
            prefix,
            failpoint,
            observer,
        )
        return LivingDexPairedDevelopmentReceipt(commitment, (model_arm, control_arm))
    raise AssertionError("paired collection session suppressed an exception")


def _execute_arm(
    scenario: LivingDexCausalScenario,
    actor: str,
    index: int,
    commitment: Mapping[str, object],
    store: PrivateArtifactRoot,
    prefix: str,
    failpoint: Callable[[str], None] | None,
    observer: Callable[[str, Mapping[str, object]], None] | None,
) -> dict[str, object]:
    arm_id = prefix + "-" + actor
    binding = {
        "actor": actor,
        "selected_candidate_index": index,
        "binding_sha256": scenario.binding_sha256s[index],
        "commitment_sha256": canonical_sha256(commitment),
        "schema": _SCHEMA,
    }
    terminal = read_paired_record(store, arm_id + "-terminal")
    if terminal is not None:
        if any(terminal.get(key) != value for key, value in binding.items()):
            raise LivingDexPairedDevelopmentError("paired arm recovery binding differs")
        return terminal
    if read_paired_record(store, arm_id + "-attempt") is not None:
        return publish_paired_record(
            store,
            arm_id + "-terminal",
            {
                **binding,
                "status": "interrupted",
                "outcome": None,
            },
        )
    before = scenario.effect_meter.checkpoint()
    publish_paired_record(
        store,
        arm_id + "-attempt",
        {
            **binding,
            "effect_checkpoint": before.private_dict(),
        },
    )
    _notify(observer, "arm_started", binding)
    _trip(failpoint, "after_" + actor + "_attempt")
    gate = LivingDexControllerGate()
    stage = "runtime_construction"
    try:
        with scenario.resolve_selected(index, gate) as arm:
            if not isinstance(arm, LivingDexCausalResolvedArm):
                raise LivingDexPairedDevelopmentError("paired runtime type differs")
            arm.__post_init__()
            if (
                gate.released
                or arm.binding_sha256 != scenario.binding_sha256s[index]
                or arm.effect_meter is not scenario.effect_meter
                or scenario.effect_meter.checkpoint() != before
            ):
                raise LivingDexPairedDevelopmentError("paired runtime changed before release")
            publish_paired_record(store, arm_id + "-release", binding)
            stage = "controller_release"
            _trip(failpoint, "after_" + actor + "_release")
            gate.authorize_controller_input()
            execution_error = None
            try:
                arm.execute(gate)
            except Exception as error:
                execution_error = private_failure_diagnostic(error)
            stage = "outcome_observation"
            after = scenario.effect_meter.checkpoint()
            trace, trace_valid = _read_action_trace(arm)
            observation = _observe_after(scenario, after)
            outcome = observation.outcome
            if not trace_valid or scenario.effect_meter.checkpoint() != after:
                outcome = LivingDexObservedOutcome(
                    LivingDexOutcomeStatus.CENSORED,
                    censor_reason=LivingDexCensorReason.PROVENANCE_FAILED,
                )
            actions, frames = before.delta(after)
            terminal = publish_paired_record(
                store,
                arm_id + "-terminal",
                {
                    **binding,
                    "status": outcome.status.value,
                    "outcome": outcome.public_dict(),
                    "controller_actions": actions,
                    "emulator_frames": frames,
                    "action_trace": trace,
                    "observation": dict(observation.provenance),
                    "execution_raised": execution_error is not None,
                    "private_diagnostic": execution_error,
                },
            )
            _trip(failpoint, "after_" + actor + "_terminal")
    except BaseException as error:
        existing = read_paired_record(store, arm_id + "-terminal")
        if existing is not None:
            raise
        terminal = publish_paired_record(
            store,
            arm_id + "-terminal",
            {
                **binding,
                "status": "failed" if isinstance(error, Exception) else "interrupted",
                "outcome": None,
                "failure_phase": stage,
                "private_diagnostic": private_failure_diagnostic(error),
                "controller_actions": scenario.effect_meter.checkpoint().controller_actions
                - before.controller_actions,
                "emulator_frames": scenario.effect_meter.checkpoint().emulator_frames
                - before.emulator_frames,
            },
        )
        if not isinstance(error, Exception):
            raise
    _notify(observer, "arm_terminal", terminal)
    return terminal


def _trip(failpoint: Callable[[str], None] | None, stage: str) -> None:
    if failpoint is not None:
        failpoint(stage)


def _notify(
    observer: Callable[[str, Mapping[str, object]], None] | None,
    stage: str,
    document: Mapping[str, object],
) -> None:
    if observer is not None:
        # The view gets a detached copy; it cannot mutate the stored policy
        # commitment or replace an action even accidentally.
        with suppress(Exception):
            observer(stage, deepcopy(dict(document)))
