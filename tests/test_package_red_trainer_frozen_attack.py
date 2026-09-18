"""The composed policy must retain exactly its declared component weights."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel
from scripts.package_red_trainer_frozen_attack import compose


def test_composition_preserves_heads_and_rejects_unrelated_lineage() -> None:
    def model(captures: tuple[str, ...], seed: int) -> TrainerPracticeThreeHeadModel:
        from pokemon_red_completion.red_trainer_practice_features import (
            MOVE_FEATURE_NAMES,
            MOVE_SCHEMA_ID,
            SWITCH_FEATURE_NAMES_V2,
            SWITCH_SCHEMA_ID,
        )
        from pokemon_red_completion.red_trainer_practice_fit import (
            CONTROL_ACTION_FEATURE_NAMES,
            CONTROL_ACTION_SCHEMA_ID,
        )
        from pokemon_red_completion.red_trainer_practice_head import TrainerHeadModel

        def head(schema: str, names: tuple[str, ...], head_seed: int) -> TrainerHeadModel:
            return TrainerHeadModel(
                schema, names, np.zeros((len(names), 2)),
                np.zeros(2), np.asarray([head_seed / 100, 0.0]), head_seed,
            )

        return TrainerPracticeThreeHeadModel(
            head(MOVE_SCHEMA_ID, MOVE_FEATURE_NAMES, seed),
            head(CONTROL_ACTION_SCHEMA_ID, CONTROL_ACTION_FEATURE_NAMES, seed + 1),
            head(SWITCH_SCHEMA_ID, SWITCH_FEATURE_NAMES_V2, seed + 2),
            captures, ("root",),
        )

    old = model(("first",), 11)
    corrected = model(("first", "second"), 31)
    composed = compose(old, corrected)
    assert composed.move.to_dict() == old.move.to_dict()
    assert composed.control.to_dict() == corrected.control.to_dict()
    assert composed.switch.to_dict() == corrected.switch.to_dict()
    with pytest.raises(ValueError, match="lineage"):
        compose(old, model(("unrelated",), 41))
    aligned = replace(corrected, control_target_mode="fitted_components")
    with pytest.raises(ValueError, match="fitted attack head"):
        compose(old, aligned)
    assert compose(aligned, aligned).control_target_mode == "fitted_components"
