import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.battle_semantics import (
    FEATURE_NAMES,
    FEATURE_SCHEMA_ID,
    BattleFeatureBatch,
)
from pokemon_red_completion.red_battle_scenario import PreparedRedBattleScenario
from pokemon_red_completion.scenario_lab import ScenarioPartition

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


def test_terminal_pair_horizon_is_explicit_and_bounded():
    assert baseline._matched_player_turn_horizon({}) == 2
    assert baseline._matched_player_turn_horizon({"matched_player_turn_horizon": 4}) == 4
    for value in (0, 3, 5, True, 4.0):
        with pytest.raises(ValueError, match="horizon differs"):
            baseline._matched_player_turn_horizon({"matched_player_turn_horizon": value})


def test_timed_prompt_can_be_collected_without_unrequested_main_branches():
    schema = baseline.OBSERVATION_SCHEMA_V2
    prompt_only = {
        "matched_prompt_choices": True,
        "matched_timing_offsets": [0, 2, 4, 6, 8],
    }
    assert baseline._timed_choice_plan_supported(prompt_only, schema)
    assert not baseline._timed_choice_plan_supported(
        {"matched_timing_offsets": [0, 2, 4, 6, 8]}, schema
    )
    assert not baseline._timed_choice_plan_supported(
        {**prompt_only, "matched_timing_offsets": [0, 2, 4]}, schema
    )
    assert not baseline._timed_choice_plan_supported(prompt_only, None)
    forced_only = {
        "matched_forced_choices": True,
        "matched_timing_offsets": [0, 2, 4, 6, 8],
    }
    assert baseline._timed_choice_plan_supported(forced_only, schema)


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


def test_depleted_opening_offers_only_living_switches():
    vector = tuple(0.0 for _ in FEATURE_NAMES)
    prepared = PreparedRedBattleScenario(
        initial_observation_sha256="a" * 64,
        allow_no_attack=True,
        features=BattleFeatureBatch(
            feature_names=FEATURE_NAMES,
            candidate_vectors=(vector, vector),
            legal_mask=(False, False),
            current_pp=(0.0, 0.0),
            slot_indices=(0, 1),
            schema_id=FEATURE_SCHEMA_ID,
        ),
    )
    choices = baseline._all_legal_opening_choices(prepared, (10, 20, 0, 30), 0)
    assert [choice.semantic_ref for choice in choices] == [
        "pokemon.core:battle:switch:2",
        "pokemon.core:battle:switch:4",
    ]


def test_no_attack_baseline_switch_uses_only_visible_living_party_member():
    observation = {"features": {"party": {"active_index": 0, "members": [
        {"party_index": 0, "hp": 10},
        {"party_index": 1, "hp": 0},
        {"party_index": 2, "hp": 20},
    ]}}}
    assert baseline._first_living_switch_from_observation(observation) == 3
    with pytest.raises(ValueError, match="no living switch target"):
        baseline._first_living_switch_from_observation({
            "features": {"party": {"active_index": 0, "members": [
                {"party_index": 0, "hp": 10},
                {"party_index": 1, "hp": 0},
            ]}}
        })


def test_fixed_development_control_has_no_model_or_branch_targets(tmp_path, monkeypatch):
    monkeypatch.setattr(
        baseline.subprocess,
        "check_output",
        lambda args, **_kwargs: b"" if "status" in args else b"commit\n",
    )
    monkeypatch.setattr(baseline, "ROM_SHA256", hashlib.sha256(b"rom").hexdigest())
    monkeypatch.setattr(baseline, "_bound_file", lambda *_args: b"rom")
    capture = SimpleNamespace(manifest=SimpleNamespace(
        partition=ScenarioPartition.DEVELOPMENT,
        expected_battle_state=2,
        observation_schema=baseline.OBSERVATION_SCHEMA_V2,
    ))
    monkeypatch.setattr(baseline, "open_battle_scenario_capture", lambda *_args: capture)
    plan = {
        "schema": baseline.SCHEMA,
        "source_commit": "commit",
        "rom": {},
        "capture_state": {"path": "state"},
        "capture_manifest": {"path": "manifest"},
        "baseline_policy": "first-legal-attack",
        "max_decisions": 80,
        "maximum_frames": 120000,
        "output": str(tmp_path / "new-run"),
    }
    _, _, model = baseline._authenticate(plan)
    assert model is None
    with pytest.raises(ValueError, match="DEVELOPMENT baseline cannot collect"):
        baseline._authenticate({**plan, "matched_choices": "all_legal_opening"})
