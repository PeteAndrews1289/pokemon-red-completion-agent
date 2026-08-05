"""Live deployment bridge for integrity-checked battle move rankers."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from pokemon_red_completion.battle_model import MaskedLinearMoveRanker
from pokemon_red_completion.battle_runtime import (
    BattlePolicyObservation,
    RequiredMovePolicy,
)
from pokemon_red_completion.battle_semantics import (
    FEATURE_NAMES,
    BattleFeatureProjector,
    BattleMovePolicyContext,
)
from pokemon_red_completion.red_battle_catalog import (
    PokemonRedBattleCatalog,
    pokemon_red_move_ref,
)
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder


class LearnedBattlePolicyError(RuntimeError):
    """Raised when a private model artifact cannot be authenticated or deployed."""


@dataclass(slots=True)
class ModelAssistedBattlePolicy:
    """Use the ranker above a teacher fallback and expose correction coverage."""

    model: MaskedLinearMoveRanker
    encoder: PokemonRedObservationEncoder
    confidence_threshold: float
    require_teacher_agreement: bool = True
    projector: BattleFeatureProjector = field(
        default_factory=lambda: BattleFeatureProjector(PokemonRedBattleCatalog())
    )
    decisions: int = 0
    model_decisions: int = 0
    teacher_fallbacks: int = 0
    forced_decisions: int = 0
    fallback_reasons: Counter[str] = field(default_factory=Counter)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be between zero and one")
        if not isinstance(self.require_teacher_agreement, bool):
            raise TypeError("require_teacher_agreement must be a bool")
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
                confidence = float(probabilities[candidate])
                if confidence < self.confidence_threshold:
                    fallback_reason = "low_confidence"
                else:
                    predicted_slot = batch.slot_indices[candidate] + 1
        except Exception:
            fallback_reason = "unsupported_observation"
        if fallback_reason is not None:
            return self._fallback(fallback, fallback_reason)
        assert predicted_slot is not None
        if self.require_teacher_agreement:
            teacher_slot = fallback()
            if teacher_slot != predicted_slot:
                self.teacher_fallbacks += 1
                self.fallback_reasons["teacher_disagreement"] += 1
                return teacher_slot
        self.model_decisions += 1
        return predicted_slot

    def _fallback(self, fallback: Callable[[], int], reason: str) -> int:
        self.teacher_fallbacks += 1
        self.fallback_reasons[reason] += 1
        return fallback()

    def public_dict(self) -> dict[str, object]:
        return {
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
        }


def load_battle_model_artifact(model_stream: str | Path) -> MaskedLinearMoveRanker:
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
    model = MaskedLinearMoveRanker.from_dict(model_payload)
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
