from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest

from pokemon_red_completion.battle_control_features import (
    CONTROL_FEATURE_NAMES,
    CONTROL_FEATURE_SCHEMA_ID,
    BattleControlExample,
)
from pokemon_red_completion.battle_control_model import (
    BattleControlMLP,
    BattleControlModelError,
    _canonical_sha256,
    evaluate_control_model,
)


def _examples() -> tuple[BattleControlExample, ...]:
    rows: list[BattleControlExample] = []
    for index in range(20):
        move = np.zeros(len(CONTROL_FEATURE_NAMES), dtype=np.float64)
        move[3] = 0.8 + index / 200
        rows.append(BattleControlExample(move, 0, f"move-{index // 2}", index * 2 + 1))
        recovery = np.zeros(len(CONTROL_FEATURE_NAMES), dtype=np.float64)
        recovery[3] = 0.05 + index / 1000
        recovery[24] = 0.5
        rows.append(
            BattleControlExample(recovery, 1, f"heal-{index // 2}", index * 2 + 2)
        )
    return tuple(rows)


def test_control_mlp_learns_balanced_action_boundary_and_round_trips() -> None:
    examples = _examples()
    model = BattleControlMLP.fit(examples, seed=17, epochs=250)

    metrics = evaluate_control_model(model, examples)
    restored = BattleControlMLP.from_dict(model.to_dict())

    assert metrics.accuracy >= 0.95
    assert metrics.balanced_accuracy >= 0.95
    assert restored.predict_ref(examples[0].features) == model.predict_ref(
        examples[0].features
    )
    assert restored.to_dict() == model.to_dict()


def test_control_mlp_rejects_one_class_training() -> None:
    with pytest.raises(BattleControlModelError, match="at least two"):
        BattleControlMLP.fit(_examples()[::2])

    with pytest.raises(BattleControlModelError, match="class-balance"):
        BattleControlMLP.fit(_examples(), class_balance_power=1.1)


def test_control_model_digest_matches_canonical_artifact_writer_contract() -> None:
    model = BattleControlMLP.fit(_examples(), seed=7, epochs=2)
    payload = json.dumps(
        model.to_dict(),
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")

    assert _canonical_sha256(model.to_dict()) == hashlib.sha256(payload).hexdigest()


def test_control_model_rejects_the_pre_reserve_feature_schema() -> None:
    model = BattleControlMLP.fit(_examples(), seed=7, epochs=2)
    payload = model.to_dict()
    payload["feature_schema_id"] = "pokemon.core.battle.control.features.v3"

    with pytest.raises(BattleControlModelError, match="feature schema"):
        BattleControlMLP.from_dict(payload)

    assert CONTROL_FEATURE_SCHEMA_ID == "pokemon.core.battle.control.features.v4"
