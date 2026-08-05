from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pokemon_red_completion.battle_model import MaskedLinearMoveRanker
from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_runtime import BattleIntent, BattlePolicyObservation
from pokemon_red_completion.battle_semantics import (
    FEATURE_NAMES,
    BattleFeatureBatch,
)
from pokemon_red_completion.learned_battle_policy import (
    LearnedBattlePolicyError,
    ModelAssistedBattlePolicy,
    load_battle_model_artifact,
)
from pokemon_red_completion.observation import RawGameState


def _model(*, power_weight: float = 10.0) -> MaskedLinearMoveRanker:
    weights = [0.0] * len(FEATURE_NAMES)
    weights[FEATURE_NAMES.index("move.power_fraction")] = power_weight
    return MaskedLinearMoveRanker(feature_names=FEATURE_NAMES, weights=weights)


def _batch() -> BattleFeatureBatch:
    first = [0.0] * len(FEATURE_NAMES)
    second = [0.0] * len(FEATURE_NAMES)
    second[FEATURE_NAMES.index("move.power_fraction")] = 1.0
    return BattleFeatureBatch(
        feature_names=FEATURE_NAMES,
        candidate_vectors=(tuple(first), tuple(second)),
        legal_mask=(True, True),
        current_pp=(10.0, 10.0),
        slot_indices=(0, 2),
    )


def _observation() -> BattlePolicyObservation:
    return BattlePolicyObservation(
        RawGameState(
            game_started=True,
            map_id=1,
            player_x=1,
            player_y=1,
            party_count=1,
            battle_state=2,
            first_party_moves=(33, 0, 55),
            first_party_pp=(10, 0, 10),
        ),
        BattleIntent("test_battle", "battle-test"),
    )


class _Encoder:
    def snapshot_from_raw(self, raw: RawGameState) -> dict[str, object]:
        return {"battle_state": raw.battle_state}


class _Projector:
    def project(self, snapshot: object, *, policy_context: object) -> BattleFeatureBatch:
        return _batch()


def test_model_assisted_policy_uses_confident_prediction_and_counts_coverage() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        encoder=_Encoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.9,
    )

    assert policy.choose_move(_observation(), lambda: 3) == 3
    assert policy.public_dict()["model_coverage"] == 1.0
    assert policy.teacher_fallbacks == 0


def test_model_assisted_policy_executes_and_counts_teacher_correction() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        encoder=_Encoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.9,
    )

    assert policy.choose_move(_observation(), lambda: 1) == 1
    assert policy.model_decisions == 0
    assert policy.teacher_fallbacks == 1
    assert policy.fallback_reasons == {"teacher_disagreement": 1}


def test_model_assisted_policy_defers_low_confidence_state_to_teacher() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(power_weight=0.0),
        encoder=_Encoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.75,
    )

    assert policy.choose_move(_observation(), lambda: 1) == 1
    assert policy.model_decisions == 0
    assert policy.teacher_fallbacks == 1
    assert policy.fallback_reasons == {"low_confidence": 1}


def test_model_assisted_policy_emits_private_training_record_for_disagreement() -> None:
    records: list[dict[str, object]] = []
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        encoder=_Encoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.9,
        correction_sink=lambda record: records.append(dict(record)),
    )

    assert policy.choose_move(_observation(), lambda: 1) == 1
    assert policy.correction_records == 1
    assert len(records) == 1
    record = records[0]
    assert record["reason"] == "teacher_disagreement"
    assert record["battle_plan_id"] == "battle-test"
    assert record["model"] == {
        "predicted_candidate_index": 1,
        "confidence": pytest.approx(0.9999546021312976),
    }
    assert record["teacher"] == {"chosen_candidate_index": 0}
    features = record["features"]
    assert isinstance(features, dict)
    assert features["slot_indices"] == [0, 2]
    assert len(features["candidate_vectors"]) == 2
    assert policy.public_dict()["correction_records"] == 1


def test_model_assisted_policy_records_low_confidence_teacher_label() -> None:
    records: list[dict[str, object]] = []
    policy = ModelAssistedBattlePolicy(
        model=_model(power_weight=0.0),
        encoder=_Encoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.75,
        correction_sink=lambda record: records.append(dict(record)),
    )

    assert policy.choose_move(_observation(), lambda: 1) == 1
    assert records[0]["reason"] == "low_confidence"
    assert records[0]["teacher"] == {"chosen_candidate_index": 0}


def test_shadow_teacher_records_disagreement_but_model_still_acts() -> None:
    records: list[dict[str, object]] = []
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        encoder=_Encoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        require_teacher_agreement=False,
        observe_teacher_when_not_required=True,
        correction_sink=lambda record: records.append(dict(record)),
    )

    assert policy.choose_move(_observation(), lambda: 1) == 3
    assert policy.model_decisions == 1
    assert policy.teacher_fallbacks == 0
    assert policy.shadow_teacher_disagreements == 1
    assert records[0]["teacher"] == {"chosen_candidate_index": 0}


def test_shadow_teacher_preserves_non_move_control_signal() -> None:
    policy = ModelAssistedBattlePolicy(
        model=_model(),
        encoder=_Encoder(),  # type: ignore[arg-type]
        projector=_Projector(),  # type: ignore[arg-type]
        confidence_threshold=0.0,
        require_teacher_agreement=False,
        observe_teacher_when_not_required=True,
    )

    def request_recovery() -> int:
        raise RuntimeError("use recovery command")

    with pytest.raises(RuntimeError, match="recovery"):
        policy.choose_move(_observation(), request_recovery)
    assert policy.shadow_teacher_unavailable == 1
    assert policy.model_decisions == 0


@pytest.mark.parametrize(
    "model",
    (
        _model(),
        MaskedMLPMoveRanker(
            feature_names=FEATURE_NAMES,
            input_weights=[[0.0] * len(FEATURE_NAMES)] * 2,
            hidden_bias=[0.0, 0.0],
            output_weights=[0.0, 0.0],
            output_bias=0.0,
        ),
    ),
)
def test_model_loader_authenticates_typed_artifact_stream(
    tmp_path: Path,
    model: MaskedLinearMoveRanker | MaskedMLPMoveRanker,
) -> None:
    artifact = tmp_path / "candidate"
    artifact.mkdir()
    record = {
        "record_type": "battle_model_candidate",
        "model": model.to_dict(),
        "model_sha256": hashlib.sha256(model.to_json().encode("utf-8")).hexdigest(),
    }
    payload = (
        json.dumps(record, allow_nan=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")
    model_path = artifact / "model.jsonl"
    model_path.write_bytes(payload)
    (artifact / "manifest.json").write_text(
        json.dumps(
            {
                "status": "complete",
                "files": [
                    {
                        "filename": "model.jsonl",
                        "bytes": len(payload),
                        "records": 1,
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    loaded = load_battle_model_artifact(model_path)
    assert loaded.to_json() == model.to_json()

    model_path.write_bytes(payload + b" ")
    with pytest.raises(LearnedBattlePolicyError, match="authentication"):
        load_battle_model_artifact(model_path)
