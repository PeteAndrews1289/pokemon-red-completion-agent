import hashlib
import sys
from pathlib import Path

import pytest

from pokemon_red_completion.battle_semantics import (
    FEATURE_NAMES,
    FEATURE_SCHEMA_ID,
    BattleFeatureBatch,
)
from pokemon_red_completion.red_battle_scenario import PreparedRedBattleScenario

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_red_trainer_practice_baseline as baseline  # noqa: E402


def test_baseline_requires_exact_bound_bytes(tmp_path):
    path = tmp_path / "private-model.json"
    path.write_bytes(b"{}")
    binding = {"path": str(path), "sha256": hashlib.sha256(b"{}").hexdigest()}
    assert baseline._bound_file(binding, "model") == b"{}"
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="model hash differs"):
        baseline._bound_file(binding, "model")


def test_baseline_rejects_wrong_plan_before_cartridge_access():
    with pytest.raises(ValueError, match="plan differs"):
        baseline._authenticate({"schema": "not-a-trainer-plan"})


def test_baseline_timing_must_be_a_bounded_integer():
    assert baseline._opening_idle_frames({}) == 0
    assert baseline._opening_idle_frames({"opening_idle_frames": 8}) == 8
    for value in (-1, 13, True, 2.5):
        with pytest.raises(ValueError, match="timing differs"):
            baseline._opening_idle_frames({"opening_idle_frames": value})


def test_all_legal_opening_includes_every_supported_move_and_living_reserve():
    vector = tuple(0.0 for _ in FEATURE_NAMES)
    prepared = PreparedRedBattleScenario(
        initial_observation_sha256="a" * 64,
        features=BattleFeatureBatch(
            feature_names=FEATURE_NAMES,
            candidate_vectors=(vector, vector, vector),
            legal_mask=(True, False, True),
            current_pp=(5.0, 0.0, 10.0),
            slot_indices=(0, 1, 3),
            schema_id=FEATURE_SCHEMA_ID,
        ),
    )
    choices = baseline._all_legal_opening_choices(prepared, (10, 20, 0, 30), 0)
    assert [choice.semantic_ref for choice in choices] == [
        "pokemon.core:battle:move:1",
        "pokemon.core:battle:move:4",
        "pokemon.core:battle:switch:2",
        "pokemon.core:battle:switch:4",
    ]
