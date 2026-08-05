"""Live deployment bridge for integrity-checked battle move rankers."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from pokemon_red_completion.battle_actions import BattleAction, BattleControlRequest
from pokemon_red_completion.battle_control_features import (
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


@dataclass(slots=True)
class ModelAssistedBattlePolicy:
    """Use the ranker above a teacher fallback and expose correction coverage."""

    model: BattleMoveRanker
    encoder: PokemonRedObservationEncoder
    confidence_threshold: float
    control_model: BattleControlMLP | None = None
    require_teacher_agreement: bool = True
    projector: BattleFeatureProjector = field(
        default_factory=lambda: BattleFeatureProjector(PokemonRedBattleCatalog())
    )
    correction_sink: BattleCorrectionSink | None = None
    control_sink: BattleControlSink | None = None
    observe_teacher_when_not_required: bool = False
    decisions: int = 0
    model_decisions: int = 0
    teacher_fallbacks: int = 0
    forced_decisions: int = 0
    fallback_reasons: Counter[str] = field(default_factory=Counter)
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

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be between zero and one")
        if not isinstance(self.require_teacher_agreement, bool):
            raise TypeError("require_teacher_agreement must be a bool")
        if not isinstance(self.observe_teacher_when_not_required, bool):
            raise TypeError("observe_teacher_when_not_required must be a bool")
        if self.observe_teacher_when_not_required and self.require_teacher_agreement:
            raise ValueError("shadow teacher observation requires model-disagreement execution")
        if tuple(self.model.feature_names) != FEATURE_NAMES:
            raise LearnedBattlePolicyError(
                "battle model feature names do not match the live transferable schema"
            )

    def choose_move(
        self,
        observation: BattlePolicyObservation,
        fallback: Callable[[], int],
        /,
    ) -> int:
        self.decisions += 1
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
        except Exception:
            fallback_reason = "unsupported_observation"
        if fallback_reason == "low_confidence":
            teacher_slot = fallback()
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
            teacher_slot = self._fallback(fallback, fallback_reason)
            self._record_control_action(observation, BattleAction.move(teacher_slot))
            return teacher_slot
        assert predicted_slot is not None
        if self.require_teacher_agreement:
            teacher_slot = fallback()
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
                teacher_slot = fallback()
            except BattleControlRequest as request:
                self.shadow_teacher_unavailable += 1
                self._record_control_action(observation, request.action)
                raise
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
            index
            for index, slot_index in enumerate(slot_indices)
            if slot_index + 1 == teacher_slot
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
            "actor": "learned_policy_with_teacher_fallback",
            "decisions": self.decisions,
            "model_decisions": self.model_decisions,
            "teacher_fallbacks": self.teacher_fallbacks,
            "forced_decisions": self.forced_decisions,
            "model_coverage": (self.model_decisions / self.decisions if self.decisions else 0.0),
            "confidence_threshold": self.confidence_threshold,
            "teacher_agreement_required": self.require_teacher_agreement,
            "fallback_reasons": dict(sorted(self.fallback_reasons.items())),
            "correction_records": self.correction_records,
            "shadow_teacher_disagreements": self.shadow_teacher_disagreements,
            "shadow_teacher_unavailable": self.shadow_teacher_unavailable,
            "control_records": self.control_records,
            "typed_non_move_control_records": self.typed_non_move_control_records,
            "control_signals": dict(sorted(self.control_signals.items())),
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
        return result

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
        if self.control_model is not None:
            self._observe_control_model(snapshot, action)
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
                "observation": snapshot.to_dict(),
                "teacher_action": action.public_dict(),
            }
        )

    def _observe_control_model(
        self,
        snapshot: SemanticSnapshot,
        action: BattleAction,
    ) -> None:
        """Score one live teacher action without allowing the controller to act."""

        assert self.control_model is not None
        try:
            observation = snapshot.to_dict()
            move_batch = self.projector.project(snapshot)
            features = project_control_features(observation, move_batch=move_batch)
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
