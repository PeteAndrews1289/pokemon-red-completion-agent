"""Live deployment bridge for integrity-checked battle move rankers."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from pokemon_red_completion.battle_action_targets import (
    BattleActionTargetError,
    ResolvedBattleAction,
    authorize_recovery_target,
    authorize_switch_target,
    resolve_battle_action_target,
    resolve_learned_switch_target,
)
from pokemon_red_completion.battle_actions import (
    BattleAction,
    BattleActionKind,
    BattleControlRequest,
    LearnedBattleControlRequest,
)
from pokemon_red_completion.battle_control_features import (
    CONTROL_CLASS_REFS,
    BattleControlHistory,
    BattleControlHistoryTracker,
    action_from_control_class_ref,
    control_class_ref,
    project_control_features,
)
from pokemon_red_completion.battle_control_model import BattleControlMLP
from pokemon_red_completion.battle_model import (
    BATTLE_MODEL_ID,
    CURRENT_BATTLE_FEATURE_SCHEMA_ID,
    MaskedLinearMoveRanker,
)
from pokemon_red_completion.battle_neural_model import (
    BATTLE_MLP_MODEL_ID,
    BattleMoveRanker,
    MaskedMLPMoveRanker,
)
from pokemon_red_completion.battle_runtime import (
    BattlePolicyObservation,
    RequiredMovePolicy,
)
from pokemon_red_completion.battle_semantics import (
    FEATURE_NAMES,
    BattleFeatureBatch,
    BattleFeatureProjector,
    BattleMovePolicyContext,
)
from pokemon_red_completion.battle_switch_target import project_switch_target_candidates
from pokemon_red_completion.battle_switch_target_model import (
    BattleSwitchTargetMLP,
    canonical_switch_target_model_sha256,
)
from pokemon_red_completion.red_battle_catalog import (
    PokemonRedBattleCatalog,
    pokemon_red_move_ref,
)
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder
from pokemon_red_completion.trajectory import SemanticSnapshot


class LearnedBattlePolicyError(RuntimeError):
    """Raised when a private model artifact cannot be authenticated or deployed."""


BattleCorrectionSink = Callable[[Mapping[str, object]], None]
BattleControlSink = Callable[[Mapping[str, object]], None]
BattleProgressSink = Callable[[Mapping[str, object]], None]


@dataclass(slots=True)
class ModelAssistedBattlePolicy:
    """Use the ranker above a teacher fallback and expose correction coverage."""

    model: BattleMoveRanker
    encoder: PokemonRedObservationEncoder
    confidence_threshold: float
    control_model: BattleControlMLP | None = None
    execute_control_model: bool = False
    control_confidence_threshold: float = 0.0
    switch_target_model: BattleSwitchTargetMLP | None = None
    execute_switch_target_model: bool = False
    require_teacher_agreement: bool = True
    projector: BattleFeatureProjector = field(
        default_factory=lambda: BattleFeatureProjector(PokemonRedBattleCatalog())
    )
    correction_sink: BattleCorrectionSink | None = None
    control_sink: BattleControlSink | None = None
    progress_sink: BattleProgressSink | None = None
    observe_teacher_when_not_required: bool = False
    allow_teacher_queries: bool = True
    decisions: int = 0
    model_decisions: int = 0
    teacher_queries: int = 0
    teacher_fallbacks: int = 0
    forced_decisions: int = 0
    fallback_reasons: Counter[str] = field(default_factory=Counter)
    unsupported_observation_errors: Counter[str] = field(default_factory=Counter)
    last_unsupported_observation: dict[str, object] | None = None
    correction_records: int = 0
    shadow_teacher_disagreements: int = 0
    shadow_teacher_unavailable: int = 0
    control_records: int = 0
    typed_non_move_control_records: int = 0
    control_signals: Counter[str] = field(default_factory=Counter)
    control_shadow_decisions: int = 0
    control_shadow_agreements: int = 0
    control_shadow_confidence_total: float = 0.0
    control_shadow_unavailable: Counter[str] = field(default_factory=Counter)
    control_shadow_confusion: Counter[str] = field(default_factory=Counter)
    control_history: BattleControlHistoryTracker = field(
        default_factory=BattleControlHistoryTracker
    )
    control_execution_decisions: int = 0
    control_execution_requests: int = 0
    control_suppressed_teacher_requests: int = 0
    control_safety_fallbacks: int = 0
    control_affordance_masked_decisions: int = 0
    control_affordance_masks: Counter[str] = field(default_factory=Counter)
    control_low_confidence_fallbacks: int = 0
    control_resolved_targets: Counter[str] = field(default_factory=Counter)
    control_target_resolution_failures: Counter[str] = field(default_factory=Counter)
    control_teacher_free_requests: int = 0
    control_intent_forced_requests: int = 0
    control_last_intent_mask: dict[str, object] | None = None
    switch_target_shadow_decisions: int = 0
    switch_target_shadow_agreements: int = 0
    switch_target_shadow_confidence_total: float = 0.0
    switch_target_shadow_unavailable: Counter[str] = field(default_factory=Counter)
    switch_target_execution_decisions: int = 0
    switch_target_execution_rebindings: int = 0
    switch_target_execution_fallbacks: Counter[str] = field(default_factory=Counter)
    progress_sink_errors: int = 0

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be between zero and one")
        if not isinstance(self.require_teacher_agreement, bool):
            raise TypeError("require_teacher_agreement must be a bool")
        if not isinstance(self.observe_teacher_when_not_required, bool):
            raise TypeError("observe_teacher_when_not_required must be a bool")
        if not isinstance(self.allow_teacher_queries, bool):
            raise TypeError("allow_teacher_queries must be a bool")
        if self.observe_teacher_when_not_required and self.require_teacher_agreement:
            raise ValueError("shadow teacher observation requires model-disagreement execution")
        if not self.allow_teacher_queries and self.require_teacher_agreement:
            raise ValueError("teacher-free execution requires model-disagreement execution")
        if not self.allow_teacher_queries and self.observe_teacher_when_not_required:
            raise ValueError("teacher-free execution cannot observe the shadow teacher")
        if tuple(self.model.feature_names) != FEATURE_NAMES:
            raise LearnedBattlePolicyError(
                "battle model feature names do not match the live transferable schema"
            )
        if self.execute_control_model and self.control_model is None:
            raise ValueError("control execution requires a control model")
        if self.execute_switch_target_model and self.switch_target_model is None:
            raise ValueError("switch target execution requires a switch target model")
        if (
            self.execute_switch_target_model
            and not self.allow_teacher_queries
            and not self.execute_control_model
        ):
            raise ValueError(
                "teacher-free switch target execution requires control-model execution"
            )
        if not 0.0 <= self.control_confidence_threshold <= 1.0:
            raise ValueError("control_confidence_threshold must be between zero and one")

    def choose_move(
        self,
        observation: BattlePolicyObservation,
        fallback: Callable[[], int],
        /,
    ) -> int:
        """Choose one move and publish observer-only counters after the attempt."""

        try:
            return self._choose_move(observation, fallback)
        finally:
            self._publish_progress()

    def _choose_move(
        self,
        observation: BattlePolicyObservation,
        fallback: Callable[[], int],
        /,
    ) -> int:
        self.decisions += 1

        def query_teacher() -> int:
            if not self.allow_teacher_queries:
                raise LearnedBattlePolicyError(
                    "teacher-free battle evaluation forbids teacher queries"
                )
            self.teacher_queries += 1
            return fallback()

        fallback_reason: str | None = None
        predicted_slot: int | None = None
        predicted_candidate: int | None = None
        confidence: float | None = None
        batch: BattleFeatureBatch | None = None
        context: BattleMovePolicyContext | None = None
        legal_mask: list[bool] = []
        try:
            context = _policy_context(observation)
            snapshot = self.encoder.snapshot_from_raw(observation.state)
            batch = self.projector.project(snapshot, policy_context=context)
            legal_mask = list(batch.legal_mask)
            if context is not None and context.forced_choice:
                required = context.required_move_ref
                moves = observation.state.battler_moves or ()
                legal_mask = [
                    legal
                    and index < len(moves)
                    and moves[index] > 0
                    and pokemon_red_move_ref(moves[index]) == required
                    for index, legal in enumerate(legal_mask)
                ]
                if not any(legal_mask):
                    fallback_reason = "required_move_unavailable"
                else:
                    self.forced_decisions += 1
            if fallback_reason is None:
                probabilities = self.model.predict_proba(
                    batch.candidate_vectors,
                    legal_mask=legal_mask,
                    current_pp=batch.current_pp,
                )
                candidate = int(np.argmax(probabilities))
                predicted_candidate = candidate
                confidence = float(probabilities[candidate])
                if confidence < self.confidence_threshold:
                    fallback_reason = "low_confidence"
                else:
                    predicted_slot = batch.slot_indices[candidate] + 1
        except Exception as error:
            self.unsupported_observation_errors[type(error).__name__] += 1
            self.last_unsupported_observation = _unsupported_observation_context(observation)
            if not self.allow_teacher_queries:
                raise LearnedBattlePolicyError(
                    "teacher-free battle evaluation rejected an unsupported live observation"
                ) from error
            fallback_reason = "unsupported_observation"
        if fallback_reason == "low_confidence":
            teacher_slot = query_teacher()
            assert batch is not None
            assert predicted_candidate is not None
            assert confidence is not None
            self._record_correction(
                observation=observation,
                context=context,
                batch=batch,
                legal_mask=legal_mask,
                predicted_candidate=predicted_candidate,
                confidence=confidence,
                teacher_slot=teacher_slot,
                reason=fallback_reason,
            )
            self.teacher_fallbacks += 1
            self.fallback_reasons[fallback_reason] += 1
            self._record_control_action(observation, BattleAction.move(teacher_slot))
            return teacher_slot
        if fallback_reason is not None:
            teacher_slot = self._fallback(query_teacher, fallback_reason)
            self._record_control_action(observation, BattleAction.move(teacher_slot))
            return teacher_slot
        assert predicted_slot is not None
        if self.execute_control_model:
            assert batch is not None
            assert predicted_candidate is not None
            assert confidence is not None
            return self._execute_control_decision(
                observation,
                query_teacher,
                predicted_slot=predicted_slot,
                move_context=context,
                move_batch=batch,
                move_legal_mask=legal_mask,
                move_predicted_candidate=predicted_candidate,
                move_confidence=confidence,
            )
        if self.require_teacher_agreement:
            try:
                teacher_slot = query_teacher()
            except BattleControlRequest as request:
                # Move-level teacher gating and high-level control shadowing are
                # independent boundaries. Preserve the teacher request for the
                # executor while still recording it for the controller audit.
                replacement = self._handle_teacher_request(observation, request)
                if replacement is request:
                    raise
                raise replacement from request
            if teacher_slot != predicted_slot:
                assert batch is not None
                assert predicted_candidate is not None
                assert confidence is not None
                self._record_correction(
                    observation=observation,
                    context=context,
                    batch=batch,
                    legal_mask=legal_mask,
                    predicted_candidate=predicted_candidate,
                    confidence=confidence,
                    teacher_slot=teacher_slot,
                    reason="teacher_disagreement",
                )
                self.teacher_fallbacks += 1
                self.fallback_reasons["teacher_disagreement"] += 1
                self._record_control_action(observation, BattleAction.move(teacher_slot))
                return teacher_slot
        elif self.observe_teacher_when_not_required:
            try:
                teacher_slot = query_teacher()
            except BattleControlRequest as request:
                self.shadow_teacher_unavailable += 1
                replacement = self._handle_teacher_request(observation, request)
                if replacement is request:
                    raise
                raise replacement from request
            except Exception:
                self.shadow_teacher_unavailable += 1
                raise
            else:
                if teacher_slot != predicted_slot:
                    assert batch is not None
                    assert predicted_candidate is not None
                    assert confidence is not None
                    self._record_correction(
                        observation=observation,
                        context=context,
                        batch=batch,
                        legal_mask=legal_mask,
                        predicted_candidate=predicted_candidate,
                        confidence=confidence,
                        teacher_slot=teacher_slot,
                        reason="teacher_disagreement",
                    )
                    self.shadow_teacher_disagreements += 1
        self.model_decisions += 1
        self._record_control_action(observation, BattleAction.move(predicted_slot))
        return predicted_slot

    def _fallback(self, fallback: Callable[[], int], reason: str) -> int:
        self.teacher_fallbacks += 1
        self.fallback_reasons[reason] += 1
        return fallback()

    def _record_correction(
        self,
        *,
        observation: BattlePolicyObservation,
        context: BattleMovePolicyContext | None,
        batch: BattleFeatureBatch,
        legal_mask: list[bool],
        predicted_candidate: int,
        confidence: float,
        teacher_slot: int,
        reason: str,
    ) -> None:
        if self.correction_sink is None:
            return
        candidate_vectors = tuple(tuple(row) for row in batch.candidate_vectors)
        slot_indices = tuple(batch.slot_indices)
        teacher_matches = [
            index for index, slot_index in enumerate(slot_indices) if slot_index + 1 == teacher_slot
        ]
        if len(teacher_matches) != 1:
            raise LearnedBattlePolicyError(
                "teacher correction is absent from the projected candidates"
            )
        teacher_candidate = teacher_matches[0]
        if not legal_mask[teacher_candidate]:
            raise LearnedBattlePolicyError("teacher correction selected a masked candidate")
        intent = observation.intent
        self.correction_records += 1
        self.correction_sink(
            {
                "record_type": "battle_policy_correction",
                "schema_version": 1,
                "decision_index": self.decisions,
                "correction_index": self.correction_records,
                "reason": reason,
                "objective_id": intent.objective_id if intent is not None else None,
                "battle_plan_id": intent.battle_plan_id if intent is not None else None,
                "policy_context": (
                    {
                        "goal": context.goal,
                        "move_policy": context.move_policy,
                        "required_move_ref": context.required_move_ref,
                    }
                    if context is not None
                    else None
                ),
                "features": {
                    "feature_schema_id": CURRENT_BATTLE_FEATURE_SCHEMA_ID,
                    "feature_names": list(self.model.feature_names),
                    "candidate_vectors": [list(row) for row in candidate_vectors],
                    "legal_mask": list(legal_mask),
                    "current_pp": list(batch.current_pp),
                    "slot_indices": list(slot_indices),
                },
                "model": {
                    "predicted_candidate_index": predicted_candidate,
                    "confidence": confidence,
                },
                "teacher": {"chosen_candidate_index": teacher_candidate},
            }
        )

    def public_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "schema": "pokemon-model-assisted-battle-policy-v1",
            "actor": (
                "learned_policy_with_teacher_fallback"
                if self.allow_teacher_queries
                else "learned_policy_teacher_free"
            ),
            "decisions": self.decisions,
            "model_decisions": self.model_decisions,
            "teacher_queries": self.teacher_queries,
            "teacher_queries_allowed": self.allow_teacher_queries,
            "teacher_fallbacks": self.teacher_fallbacks,
            "forced_decisions": self.forced_decisions,
            "model_coverage": (self.model_decisions / self.decisions if self.decisions else 0.0),
            "confidence_threshold": self.confidence_threshold,
            "teacher_agreement_required": self.require_teacher_agreement,
            "fallback_reasons": dict(sorted(self.fallback_reasons.items())),
            "unsupported_observation_errors": dict(
                sorted(self.unsupported_observation_errors.items())
            ),
            "last_unsupported_observation": self.last_unsupported_observation,
            "correction_records": self.correction_records,
            "shadow_teacher_disagreements": self.shadow_teacher_disagreements,
            "shadow_teacher_unavailable": self.shadow_teacher_unavailable,
            "control_records": self.control_records,
            "typed_non_move_control_records": self.typed_non_move_control_records,
            "control_signals": dict(sorted(self.control_signals.items())),
            "progress_sink_errors": self.progress_sink_errors,
        }
        if self.control_model is not None:
            control_model_payload = json.dumps(
                self.control_model.to_dict(),
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("ascii")
            result["control_model_shadow"] = {
                "model_id": self.control_model.model_id,
                "model_sha256": hashlib.sha256(control_model_payload).hexdigest(),
                "decisions": self.control_shadow_decisions,
                "agreements": self.control_shadow_agreements,
                "accuracy": (
                    self.control_shadow_agreements / self.control_shadow_decisions
                    if self.control_shadow_decisions
                    else 0.0
                ),
                "mean_confidence": (
                    self.control_shadow_confidence_total / self.control_shadow_decisions
                    if self.control_shadow_decisions
                    else 0.0
                ),
                "unavailable": dict(sorted(self.control_shadow_unavailable.items())),
                "confusion": dict(sorted(self.control_shadow_confusion.items())),
            }
        if self.switch_target_model is not None:
            result["switch_target_model"] = {
                "model_id": self.switch_target_model.model_id,
                "model_sha256": canonical_switch_target_model_sha256(self.switch_target_model),
                "shadow": {
                    "decisions": self.switch_target_shadow_decisions,
                    "agreements": self.switch_target_shadow_agreements,
                    "accuracy": (
                        self.switch_target_shadow_agreements / self.switch_target_shadow_decisions
                        if self.switch_target_shadow_decisions
                        else 0.0
                    ),
                    "mean_confidence": (
                        self.switch_target_shadow_confidence_total
                        / self.switch_target_shadow_decisions
                        if self.switch_target_shadow_decisions
                        else 0.0
                    ),
                    "unavailable": dict(sorted(self.switch_target_shadow_unavailable.items())),
                },
                "execution": {
                    "enabled": self.execute_switch_target_model,
                    "decisions": self.switch_target_execution_decisions,
                    "rebindings": self.switch_target_execution_rebindings,
                    "fallbacks": dict(sorted(self.switch_target_execution_fallbacks.items())),
                },
            }
        if self.execute_control_model:
            result["control_model_execution"] = {
                "decisions": self.control_execution_decisions,
                "typed_requests_executed": self.control_execution_requests,
                "teacher_requests_suppressed": self.control_suppressed_teacher_requests,
                "safety_fallbacks": self.control_safety_fallbacks,
                "affordance_masked_decisions": self.control_affordance_masked_decisions,
                "affordance_masks": dict(sorted(self.control_affordance_masks.items())),
                "low_confidence_fallbacks": self.control_low_confidence_fallbacks,
                "confidence_threshold": self.control_confidence_threshold,
                "resolved_targets": dict(sorted(self.control_resolved_targets.items())),
                "target_resolution_failures": dict(
                    sorted(self.control_target_resolution_failures.items())
                ),
                "teacher_free_requests": self.control_teacher_free_requests,
                "intent_forced_requests": self.control_intent_forced_requests,
                "last_intent_mask": self.control_last_intent_mask,
            }
        return result

    def _publish_progress(self) -> None:
        if self.progress_sink is None:
            return
        try:
            self.progress_sink(self.public_dict())
        except Exception:
            # A dashboard or metrics observer never gains authority over play.
            self.progress_sink_errors += 1

    def _execute_control_decision(
        self,
        observation: BattlePolicyObservation,
        fallback: Callable[[], int],
        *,
        predicted_slot: int,
        move_context: BattleMovePolicyContext | None,
        move_batch: BattleFeatureBatch,
        move_legal_mask: list[bool],
        move_predicted_candidate: int,
        move_confidence: float,
    ) -> int:
        """Execute high-level control without implicitly promoting move selection."""

        assert self.control_model is not None
        intent = observation.intent
        if intent is None:
            raise LearnedBattlePolicyError("control execution lacks planner intent")
        snapshot = self.encoder.snapshot_from_raw(observation.state)
        encoded = snapshot.to_dict()
        history = self.control_history.before(intent.battle_plan_id, encoded)
        try:
            probabilities = self.control_model.predict_proba(
                project_control_features(
                    encoded,
                    move_batch=self.projector.project(snapshot),
                    history=history,
                    catalog=getattr(self.projector, "catalog", None),
                )
            )
            predicted_ref, confidence, resolved_action = self._rank_executable_control_action(
                observation,
                encoded=encoded,
                history=history,
                probabilities=probabilities,
            )
        except Exception as error:
            raise LearnedBattlePolicyError(
                "control execution could not project the live decision"
            ) from error
        if intent.require_status_clear_before_move and bool(observation.state.battler_status):
            predicted_action = (
                BattleAction.move(predicted_slot)
                if predicted_ref == CONTROL_CLASS_REFS[0]
                else action_from_control_class_ref(predicted_ref)
            )
            intent_mask = "status_clear_before_move_mask"
            self.control_target_resolution_failures[intent_mask] += 1
            self.control_last_intent_mask = _control_intent_mask_context(
                observation,
                predicted_action,
                history=history,
                reason=intent_mask,
            )
            try:
                forced_recovery = authorize_recovery_target(
                    resolve_battle_action_target(
                        BattleAction.recovery(),
                        encoded,
                        catalog=getattr(self.projector, "catalog", None),
                    ),
                    intent.recovery_capabilities,
                )
            except BattleActionTargetError as error:
                raise LearnedBattlePolicyError(
                    "intent-forced status recovery lacks an executable target"
                ) from error
            self.control_execution_decisions += 1
            self.control_execution_requests += 1
            self.control_intent_forced_requests += 1
            self._record_control_action(observation, forced_recovery.action)
            assert forced_recovery.recovery_need is not None
            raise LearnedBattleControlRequest(
                forced_recovery.action,
                party_slot=forced_recovery.party_slot,
                recovery_need=forced_recovery.recovery_need.value,
                status=forced_recovery.status,
            )
        if (
            predicted_ref == CONTROL_CLASS_REFS[0]
            and intent.minimum_hp_before_move is not None
            and (observation.state.battler_hp or 0) < intent.minimum_hp_before_move
        ):
            predicted_action = BattleAction.move(predicted_slot)
            intent_mask = "minimum_hp_before_move_mask"
            self.control_target_resolution_failures[intent_mask] += 1
            self.control_last_intent_mask = _control_intent_mask_context(
                observation,
                predicted_action,
                history=history,
                reason=intent_mask,
            )
            try:
                forced_recovery = authorize_recovery_target(
                    resolve_battle_action_target(
                        BattleAction.recovery(),
                        encoded,
                        catalog=getattr(self.projector, "catalog", None),
                    ),
                    intent.recovery_capabilities,
                )
            except BattleActionTargetError as error:
                raise LearnedBattlePolicyError(
                    "intent-forced HP recovery lacks an executable target"
                ) from error
            self.control_execution_decisions += 1
            self.control_execution_requests += 1
            self.control_intent_forced_requests += 1
            self._record_control_action(observation, forced_recovery.action)
            assert forced_recovery.recovery_need is not None
            raise LearnedBattleControlRequest(
                forced_recovery.action,
                party_slot=forced_recovery.party_slot,
                recovery_need=forced_recovery.recovery_need.value,
                status=forced_recovery.status,
            )
        required_boost = intent.required_boost_before_first_move
        if required_boost is not None:
            move_class_index = CONTROL_CLASS_REFS.index("pokemon.core:battle:select_move")
            switch_class_index = CONTROL_CLASS_REFS.index("pokemon.core:battle:switch")
            boost_ref = f"pokemon.core:battle:boost:{required_boost.value}"
            boost_class_index = CONTROL_CLASS_REFS.index(boost_ref)
            first_switch_is_available = (
                predicted_ref == CONTROL_CLASS_REFS[switch_class_index]
                and history.action_counts[switch_class_index] == 0
            )
            recovery_is_available = predicted_ref == CONTROL_CLASS_REFS[1]
            required_boost_is_selected = predicted_ref == boost_ref
            if (
                history.action_counts[move_class_index] == 0
                and history.action_counts[boost_class_index] == 0
                and not first_switch_is_available
                and not recovery_is_available
                and not required_boost_is_selected
            ):
                predicted_action = (
                    BattleAction.move(predicted_slot)
                    if predicted_ref == CONTROL_CLASS_REFS[0]
                    else action_from_control_class_ref(predicted_ref)
                )
                intent_mask = "required_boost_before_first_move_mask"
                self.control_target_resolution_failures[intent_mask] += 1
                self.control_last_intent_mask = _control_intent_mask_context(
                    observation,
                    predicted_action,
                    history=history,
                    reason=intent_mask,
                )
                forced_boost = BattleAction.boost(required_boost)
                try:
                    resolve_battle_action_target(
                        forced_boost,
                        encoded,
                        catalog=getattr(self.projector, "catalog", None),
                    )
                except BattleActionTargetError as error:
                    raise LearnedBattlePolicyError(
                        "intent-forced pre-move boost lacks an observable resource"
                    ) from error
                self.control_execution_decisions += 1
                self.control_execution_requests += 1
                self.control_intent_forced_requests += 1
                self._record_control_action(observation, forced_boost)
                raise LearnedBattleControlRequest(forced_boost)
        if confidence < self.control_confidence_threshold:
            self.control_low_confidence_fallbacks += 1
            try:
                teacher_slot = fallback()
            except BattleControlRequest as request:
                replacement = self._handle_teacher_request(observation, request)
                if replacement is request:
                    raise
                raise replacement from request
            self._record_control_action(observation, BattleAction.move(teacher_slot))
            return teacher_slot

        if predicted_ref == CONTROL_CLASS_REFS[0] and not self.allow_teacher_queries:
            self.control_execution_decisions += 1
            return self._return_control_move(
                observation,
                fallback,
                predicted_slot=predicted_slot,
                move_context=move_context,
                move_batch=move_batch,
                move_legal_mask=move_legal_mask,
                move_predicted_candidate=move_predicted_candidate,
                move_confidence=move_confidence,
            )

        if predicted_ref != CONTROL_CLASS_REFS[0]:
            assert resolved_action is not None
            target_key = predicted_ref
            if resolved_action.recovery_need is not None:
                target_key = f"{target_key}:{resolved_action.recovery_need.value}"
            if resolved_action.party_slot is not None:
                target_key = f"{target_key}:party_slot"
            if resolved_action.switch_basis is not None:
                target_key = f"{target_key}:{resolved_action.switch_basis.value}"
            self.control_resolved_targets[target_key] += 1
            if resolved_action.action.kind is BattleActionKind.USE_BOOST:
                self.control_execution_decisions += 1
                self.control_execution_requests += 1
                self.control_teacher_free_requests += 1
                self._record_control_action(observation, resolved_action.action)
                raise LearnedBattleControlRequest(resolved_action.action)
            if resolved_action.action.kind is BattleActionKind.USE_RECOVERY:
                self.control_execution_decisions += 1
                self.control_execution_requests += 1
                self.control_teacher_free_requests += 1
                self._record_control_action(observation, resolved_action.action)
                raise LearnedBattleControlRequest(
                    resolved_action.action,
                    party_slot=resolved_action.party_slot,
                    recovery_need=resolved_action.recovery_need.value,
                    status=resolved_action.status,
                )
            if resolved_action.action.kind is BattleActionKind.SWITCH:
                self.control_execution_decisions += 1
                self.control_execution_requests += 1
                self.control_teacher_free_requests += 1
                if self.execute_switch_target_model:
                    self.switch_target_execution_decisions += 1
                    self.switch_target_execution_rebindings += 1
                assert resolved_action.party_slot is not None
                self._record_control_action(
                    observation,
                    BattleAction.switch(resolved_action.party_slot),
                )
                raise LearnedBattleControlRequest(
                    resolved_action.action,
                    party_slot=resolved_action.party_slot,
                )

        if not self.allow_teacher_queries:
            raise LearnedBattlePolicyError(
                f"teacher-free control cannot execute unresolved action {predicted_ref!r}"
            )

        teacher_request: BattleControlRequest | None = None
        teacher_slot: int | None = None
        try:
            teacher_slot = fallback()
        except BattleControlRequest as request:
            teacher_request = request

        self.control_execution_decisions += 1
        if predicted_ref == CONTROL_CLASS_REFS[0]:
            return self._return_control_move(
                observation,
                fallback,
                predicted_slot=predicted_slot,
                move_context=move_context,
                move_batch=move_batch,
                move_legal_mask=move_legal_mask,
                move_predicted_candidate=move_predicted_candidate,
                move_confidence=move_confidence,
                teacher_observed=True,
                teacher_slot=teacher_slot,
                teacher_request=teacher_request,
            )

        if (
            teacher_request is not None
            and control_class_ref(teacher_request.action) == predicted_ref
        ):
            self.control_execution_requests += 1
            replacement = self._handle_teacher_request(observation, teacher_request)
            if replacement is teacher_request:
                raise teacher_request
            raise replacement from teacher_request

        # The class model intentionally does not yet own cartridge-specific item or
        # party targets. A false-positive special action therefore degrades to the
        # learned legal move rather than spending an unverified resource.
        self.control_safety_fallbacks += 1
        return self._return_control_move(
            observation,
            fallback,
            predicted_slot=predicted_slot,
            move_context=move_context,
            move_batch=move_batch,
            move_legal_mask=move_legal_mask,
            move_predicted_candidate=move_predicted_candidate,
            move_confidence=move_confidence,
            teacher_observed=True,
            teacher_slot=teacher_slot,
            teacher_request=teacher_request,
        )

    def _rank_executable_control_action(
        self,
        observation: BattlePolicyObservation,
        *,
        encoded: Mapping[str, object],
        history: BattleControlHistory,
        probabilities: np.ndarray,
    ) -> tuple[str, float, ResolvedBattleAction | None]:
        """Rank only executable high-level affordances without querying a teacher."""

        intent = observation.intent
        assert intent is not None
        assert self.control_model is not None
        catalog = getattr(self.projector, "catalog", None)
        masked: list[tuple[str, str]] = []
        raw_index = int(np.argmax(probabilities))
        for index in np.argsort(-probabilities, kind="stable"):
            predicted_ref = self.control_model.class_refs[int(index)]
            if predicted_ref == CONTROL_CLASS_REFS[0]:
                resolved: ResolvedBattleAction | None = None
            else:
                predicted_action = action_from_control_class_ref(predicted_ref)
                intent_mask = _control_action_intent_mask(
                    predicted_action,
                    observation=observation,
                    history=history,
                )
                if intent_mask is not None:
                    masked.append((predicted_ref, intent_mask))
                    continue
                try:
                    if (
                        predicted_action.kind is BattleActionKind.SWITCH
                        and self.execute_switch_target_model
                    ):
                        assert self.switch_target_model is not None
                        if catalog is None:
                            raise BattleActionTargetError(
                                "learned switch target catalog is unavailable"
                            )
                        resolved = resolve_learned_switch_target(
                            predicted_action,
                            encoded,
                            catalog=catalog,
                            model=self.switch_target_model,
                        )
                    else:
                        resolved = resolve_battle_action_target(
                            predicted_action,
                            encoded,
                            catalog=catalog,
                        )
                    if predicted_action.kind is BattleActionKind.USE_RECOVERY:
                        resolved = authorize_recovery_target(
                            resolved,
                            intent.recovery_capabilities,
                        )
                    elif predicted_action.kind is BattleActionKind.SWITCH:
                        resolved = authorize_switch_target(
                            resolved,
                            intent.switch_capabilities,
                            observation=encoded,
                        )
                    elif (
                        predicted_action.kind is BattleActionKind.USE_BOOST
                        and predicted_action.boost_stat not in intent.boost_capabilities
                    ):
                        raise BattleActionTargetError(
                            "boost action lacks an executor capability"
                        )
                except BattleActionTargetError:
                    masked.append((predicted_ref, "capability_or_target_mask"))
                    continue
            if int(index) != raw_index:
                self.control_affordance_masked_decisions += 1
                for _class_ref, reason in masked:
                    self.control_affordance_masks[reason] += 1
                raw_ref, reason = masked[0]
                raw_action = action_from_control_class_ref(raw_ref)
                self.control_last_intent_mask = _control_intent_mask_context(
                    observation,
                    raw_action,
                    history=history,
                    reason=reason,
                )
            return predicted_ref, float(probabilities[int(index)]), resolved
        raise LearnedBattlePolicyError("control execution has no legal action class")

    def _return_control_move(
        self,
        observation: BattlePolicyObservation,
        fallback: Callable[[], int],
        *,
        predicted_slot: int,
        move_context: BattleMovePolicyContext | None,
        move_batch: BattleFeatureBatch,
        move_legal_mask: list[bool],
        move_predicted_candidate: int,
        move_confidence: float,
        teacher_observed: bool = False,
        teacher_slot: int | None = None,
        teacher_request: BattleControlRequest | None = None,
    ) -> int:
        """Return a legal move without bypassing the configured move authority."""

        if self.require_teacher_agreement and not teacher_observed:
            try:
                teacher_slot = fallback()
            except BattleControlRequest as request:
                teacher_request = request
        if teacher_request is not None:
            self.control_suppressed_teacher_requests += 1
        elif self.require_teacher_agreement:
            assert teacher_slot is not None
            if teacher_slot != predicted_slot:
                self._record_correction(
                    observation=observation,
                    context=move_context,
                    batch=move_batch,
                    legal_mask=move_legal_mask,
                    predicted_candidate=move_predicted_candidate,
                    confidence=move_confidence,
                    teacher_slot=teacher_slot,
                    reason="teacher_disagreement",
                )
                self.teacher_fallbacks += 1
                self.fallback_reasons["teacher_disagreement"] += 1
                self._record_control_action(
                    observation,
                    BattleAction.move(teacher_slot),
                )
                return teacher_slot
        self.model_decisions += 1
        self._record_control_action(observation, BattleAction.move(predicted_slot))
        return predicted_slot

    def _handle_teacher_request(
        self,
        observation: BattlePolicyObservation,
        request: BattleControlRequest,
    ) -> BattleControlRequest:
        """Audit a teacher switch and optionally replace only its target binding."""

        action = request.action
        if action.kind is not BattleActionKind.SWITCH or self.switch_target_model is None:
            self._record_control_action(observation, action)
            return request

        snapshot = self.encoder.snapshot_from_raw(observation.state)
        encoded = snapshot.to_dict()
        teacher_action = action
        if teacher_action.party_slot is None:
            try:
                resolved_teacher = resolve_battle_action_target(
                    teacher_action,
                    encoded,
                    catalog=getattr(self.projector, "catalog", None),
                )
            except BattleActionTargetError:
                self.switch_target_shadow_unavailable["teacher_target_unavailable"] += 1
            else:
                assert resolved_teacher.party_slot is not None
                teacher_action = BattleAction.switch(resolved_teacher.party_slot)

        try:
            predicted_party_slot, confidence = self._predict_switch_target(encoded)
        except Exception as error:
            self.switch_target_shadow_unavailable[type(error).__name__] += 1
            self._record_control_action(observation, teacher_action)
            if self.execute_switch_target_model:
                self.switch_target_execution_decisions += 1
                self.switch_target_execution_fallbacks[type(error).__name__] += 1
            return request

        if teacher_action.party_slot is not None:
            self.switch_target_shadow_decisions += 1
            self.switch_target_shadow_confidence_total += confidence
            self.switch_target_shadow_agreements += int(
                predicted_party_slot == teacher_action.party_slot
            )
        self._record_control_action(observation, teacher_action)
        if not self.execute_switch_target_model:
            return request
        self.switch_target_execution_decisions += 1
        self.switch_target_execution_rebindings += 1
        return LearnedBattleControlRequest(
            BattleAction.switch(),
            party_slot=predicted_party_slot,
        )

    def _predict_switch_target(
        self,
        encoded: Mapping[str, object],
    ) -> tuple[int, float]:
        assert self.switch_target_model is not None
        catalog = getattr(self.projector, "catalog", None)
        if catalog is None:
            raise LearnedBattlePolicyError("switch target mechanics catalog is unavailable")
        candidates = project_switch_target_candidates(encoded, catalog)
        probabilities = self.switch_target_model.probabilities(candidates)
        selected = int(np.argmax(probabilities))
        return candidates.candidates[selected].party_slot, float(probabilities[selected])

    def _record_control_action(
        self,
        observation: BattlePolicyObservation,
        action: BattleAction,
    ) -> None:
        if self.control_sink is None and self.control_model is None:
            return
        intent = observation.intent
        if intent is None:
            raise LearnedBattlePolicyError("battle control label lacks planner intent")
        snapshot = self.encoder.snapshot_from_raw(observation.state)
        snapshot_payload = snapshot.to_dict()
        if action.kind is BattleActionKind.SWITCH and action.party_slot is None:
            try:
                resolved = resolve_battle_action_target(
                    action,
                    snapshot_payload,
                    catalog=getattr(self.projector, "catalog", None),
                )
            except BattleActionTargetError as error:
                raise LearnedBattlePolicyError(
                    "battle control switch label lacks a resolvable reserve target"
                ) from error
            assert resolved.party_slot is not None
            action = BattleAction.switch(resolved.party_slot)
        if self.control_model is not None:
            history = self.control_history.before(intent.battle_plan_id, snapshot_payload)
            self._observe_control_model(snapshot, action, history)
            self.control_history.advance(action, snapshot_payload)
        if self.control_sink is None:
            return
        self.control_records += 1
        if action.kind.value != "select_move":
            self.typed_non_move_control_records += 1
        self.control_signals[action.semantic_ref] += 1
        self.control_sink(
            {
                "record_type": "battle_control_label",
                "schema_version": 1,
                "label_index": self.control_records,
                "decision_index": self.decisions,
                "battle_plan_id": intent.battle_plan_id,
                "objective_id": intent.objective_id,
                "observation": snapshot_payload,
                "teacher_action": action.public_dict(),
            }
        )

    def _observe_control_model(
        self,
        snapshot: SemanticSnapshot,
        action: BattleAction,
        history: BattleControlHistory,
    ) -> None:
        """Score one live teacher action without allowing the controller to act."""

        assert self.control_model is not None
        try:
            observation = snapshot.to_dict()
            move_batch = self.projector.project(snapshot)
            features = project_control_features(
                observation,
                move_batch=move_batch,
                history=history,
                catalog=getattr(self.projector, "catalog", None),
            )
            probabilities = self.control_model.predict_proba(features)
            predicted = self.control_model.class_refs[int(np.argmax(probabilities))]
            confidence = float(np.max(probabilities))
            actual = control_class_ref(action)
        except Exception as error:
            self.control_shadow_unavailable[type(error).__name__] += 1
            return
        self.control_shadow_decisions += 1
        self.control_shadow_confidence_total += confidence
        self.control_shadow_confusion[f"{actual} -> {predicted}"] += 1
        if predicted == actual:
            self.control_shadow_agreements += 1


def _control_action_intent_mask(
    action: BattleAction,
    *,
    observation: BattlePolicyObservation,
    history: BattleControlHistory,
) -> str | None:
    """Return the game-neutral planner constraint that masks one typed action."""

    intent = observation.intent
    if intent is None:
        return None
    if action.kind is BattleActionKind.USE_BOOST:
        assert action.boost_stat is not None
        limit = dict(intent.boost_use_limits).get(action.boost_stat)
        if limit is None:
            return None
        class_ref = f"pokemon.core:battle:boost:{action.boost_stat.value}"
        if history.action_counts[CONTROL_CLASS_REFS.index(class_ref)] >= limit:
            return "budget_mask"
        return None
    if action.kind is BattleActionKind.SWITCH:
        class_ref = "pokemon.core:battle:switch"
        class_index = CONTROL_CLASS_REFS.index(class_ref)
        move_class_index = CONTROL_CLASS_REFS.index("pokemon.core:battle:select_move")
        if (
            intent.switch_limit is not None
            and history.action_counts[class_index] >= intent.switch_limit
        ):
            return "budget_mask"
        if (
            intent.require_move_before_first_switch
            and history.action_counts[class_index] == 0
            and history.action_counts[move_class_index] == 0
        ):
            return "initial_switch_residency_mask"
        if (
            intent.require_move_between_switches
            and history.action_counts[class_index] > 0
            and history.action_counts[move_class_index] <= history.move_count_at_last_switch
        ):
            return "switch_residency_mask"
    return None


def _control_intent_mask_context(
    observation: BattlePolicyObservation,
    action: BattleAction,
    *,
    history: BattleControlHistory,
    reason: str,
) -> dict[str, object]:
    """Sanitize the latest constrained decision for failed-run diagnosis."""

    raw = observation.state
    intent = observation.intent
    return {
        "reason": reason,
        "predicted_action": control_class_ref(action),
        "battle_plan_id": intent.battle_plan_id if intent is not None else None,
        "objective_id": intent.objective_id if intent is not None else None,
        "history": {
            "battle_turn": history.battle_turn,
            "opponent_index": history.opponent_index,
            "opponent_turn": history.opponent_turn,
            "previous_action": (
                CONTROL_CLASS_REFS[history.previous_class_index]
                if history.previous_class_index is not None
                else None
            ),
            "action_counts": {
                class_ref: history.action_counts[index]
                for index, class_ref in enumerate(CONTROL_CLASS_REFS)
            },
            "move_count_at_last_switch": history.move_count_at_last_switch,
        },
        "active": {
            "party_index": raw.active_party_index,
            "species_id": raw.active_party_species_id,
            "level": raw.active_party_level,
            "hp": raw.active_party_hp,
            "max_hp": raw.active_party_max_hp,
            "status": raw.active_party_status,
        },
        "opponent": {
            "species_id": raw.enemy_species_id,
            "level": raw.enemy_level,
            "hp": raw.enemy_hp,
            "max_hp": raw.enemy_max_hp,
        },
    }


def _unsupported_observation_context(
    observation: BattlePolicyObservation,
) -> dict[str, object]:
    raw = observation.state
    intent = observation.intent
    return {
        "active_party_hp": raw.active_party_hp,
        "active_party_index": raw.active_party_index,
        "active_party_level": raw.active_party_level,
        "active_party_max_hp": raw.active_party_max_hp,
        "active_party_moves": list(raw.active_party_moves or ()),
        "active_party_pp": list(raw.active_party_pp or ()),
        "active_party_species_id": raw.active_party_species_id,
        "battle_plan_id": intent.battle_plan_id if intent is not None else None,
        "battle_state": raw.battle_state,
        "disabled_move_slot": raw.player_disabled_move_slot,
        "enemy_hp": raw.enemy_hp,
        "enemy_species_id": raw.enemy_species_id,
        "objective_id": intent.objective_id if intent is not None else None,
        "required_move_policy": (intent.required_move_policy.value if intent is not None else None),
        "required_move_ref": intent.required_move_ref if intent is not None else None,
    }


def load_battle_model_artifact(model_stream: str | Path) -> BattleMoveRanker:
    """Authenticate one finalized model stream against its typed manifest."""

    path = Path(model_stream)
    if path.name != "model.jsonl" or path.is_symlink() or not path.is_file():
        raise LearnedBattlePolicyError("battle model must name a regular model.jsonl stream")
    manifest_path = path.parent / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise LearnedBattlePolicyError("battle model manifest is absent")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload = path.read_bytes()
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise LearnedBattlePolicyError("battle model artifact cannot be read") from error
    if not isinstance(manifest, Mapping) or manifest.get("status") != "complete":
        raise LearnedBattlePolicyError("battle model artifact is not complete")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise LearnedBattlePolicyError("battle model manifest has no file inventory")
    entry = next(
        (item for item in files if isinstance(item, Mapping) and item.get("filename") == path.name),
        None,
    )
    if (
        entry is None
        or entry.get("bytes") != len(payload)
        or entry.get("sha256") != hashlib.sha256(payload).hexdigest()
        or entry.get("records") != 1
    ):
        raise LearnedBattlePolicyError("battle model stream failed manifest authentication")
    try:
        record = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise LearnedBattlePolicyError("battle model stream is invalid") from error
    if not isinstance(record, Mapping) or record.get("record_type") not in {
        "battle_model_candidate",
        "battle_model",
    }:
        raise LearnedBattlePolicyError("battle model stream has the wrong record type")
    model_payload = record.get("model")
    if not isinstance(model_payload, Mapping):
        raise LearnedBattlePolicyError("battle model payload is absent")
    model_id = model_payload.get("model_id")
    if model_id == BATTLE_MODEL_ID:
        model = MaskedLinearMoveRanker.from_dict(model_payload)
    elif model_id == BATTLE_MLP_MODEL_ID:
        model = MaskedMLPMoveRanker.from_dict(model_payload)
    else:
        raise LearnedBattlePolicyError("battle model payload has an unsupported model ID")
    expected_sha256 = record.get("model_sha256")
    if expected_sha256 != hashlib.sha256(model.to_json().encode("utf-8")).hexdigest():
        raise LearnedBattlePolicyError("battle model payload digest does not match")
    return model


def _policy_context(
    observation: BattlePolicyObservation,
) -> BattleMovePolicyContext | None:
    intent = observation.intent
    if intent is None:
        return None
    return BattleMovePolicyContext(
        goal=intent.goal.value,
        move_policy=intent.required_move_policy.value,
        required_move_ref=(
            intent.required_move_ref
            if intent.required_move_policy is RequiredMovePolicy.EXACT_REQUIRED
            else None
        ),
    )
