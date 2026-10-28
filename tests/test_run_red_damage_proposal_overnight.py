"""ROM-free guards for the one-fit overnight damage experiment."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_red_damage_proposal_overnight as packet
from audit_red_damage_proposal_overnight import classify_retention_record

from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.red_trainer_practice_features import (
    MOVE_FEATURE_NAMES,
    MOVE_SCHEMA_ID,
    project_trainer_move_features,
)
from pokemon_red_completion.red_trainer_practice_head import TrainerHeadModel


def test_compact_embedding_roundtrip_permutation_and_excluded_zeros():
    rng = np.random.default_rng(230902)
    compact = TrainerHeadModel(
        MOVE_SCHEMA_ID,
        packet.FEATURES,
        rng.normal(size=(len(packet.FEATURES), 16)),
        rng.normal(size=16),
        rng.normal(size=16),
        230902,
        "expected_regret",
    )
    full = packet.embed(compact)
    vectors = tuple(tuple(row) for row in rng.uniform(-1, 1, (4, len(MOVE_FEATURE_NAMES))))
    packet.assert_embedding(compact, full, vectors)
    restored = TrainerHeadModel.from_dict(
        full.to_dict(), schema_id=MOVE_SCHEMA_ID, feature_names=MOVE_FEATURE_NAMES
    )
    assert restored.to_dict() == full.to_dict()
    for order in ((0, 1, 2, 3), (3, 1, 0, 2), (2, 0, 3, 1)):
        permuted = tuple(vectors[i] for i in order)
        packet.assert_embedding(compact, restored, permuted)
        assert (
            order[restored.predict_index(permuted)]
            == order[compact.predict_index(packet.compact_rows(permuted))]
        )
    assert all(
        not full.weights1[i].any()
        for i in range(len(MOVE_FEATURE_NAMES))
        if i not in packet.FEATURE_INDICES
    )
    with pytest.raises(ValueError, match="finiteness"):
        packet.compact_rows(((float("nan"),) * len(MOVE_FEATURE_NAMES),))


def test_immunity_accuracy_and_pp_use_existing_observable_columns():
    catalog = PokemonRedBattleCatalog()
    lead = {
        "party_index": 0,
        "species_ref": "pokemon.red.gb.us.rev0:species:084",
        "level": 37,
        "hp": 70,
        "max_hp": 80,
        "hp_ratio": 0.875,
        "status": None,
        "stats": {"attack": 60, "defense": 50, "speed": 75, "special": 50},
        "moves": [
            {"slot_index": 0, "move_ref": "pokemon.red.gb.us.rev0:move:089", "pp": 5},
            {"slot_index": 1, "move_ref": "pokemon.red.gb.us.rev0:move:098", "pp": 10},
            {"slot_index": 2, "move_ref": "pokemon.red.gb.us.rev0:move:087", "pp": 3},
        ],
    }
    observation = {
        "mode": "battle",
        "features": {
            "menu": {"kind": "battle_main"},
            "party": {"count": 1, "active_index": 0, "lead": lead, "members": [lead]},
            "battle": {
                "active": True,
                "kind": "trainer",
                "opponent_species_ref": "pokemon.red.gb.us.rev0:species:005",
                "opponent_level": 37,
                "opponent_hp_ratio": 1.0,
                "opponent_public_base_stats": {
                    "hp": 35,
                    "attack": 85,
                    "defense": 45,
                    "speed": 75,
                    "special": 35,
                },
                "opponent_status": None,
                "player_attack_stage": 0,
                "player_special_stage": 0,
                "player_accuracy_stage": 0,
                "opponent_defense_stage": 0,
                "player_disabled_move_slot": None,
                "opponent_using_trapping_move": False,
            },
            "resources": {
                "healing_item_count": 0,
                "status_recovery_item_count": 0,
                "revive_item_count": 0,
                "accuracy_boost_count": 0,
                "attack_boost_count": 0,
                "special_boost_count": 0,
            },
            "progress": {"badge_count": 0},
        },
    }
    projected = project_trainer_move_features(
        observation, BattleFeatureProjector(catalog).project(observation)
    )
    rows = packet.compact_rows(projected.candidate_vectors)
    index = {name: i for i, name in enumerate(packet.FEATURES)}
    assert rows[0][index["move.type_effectiveness_fraction"]] == 0
    assert rows[0][index["move.pp_fraction"]] == pytest.approx(
        5 / catalog.resolve_move("pokemon.red.gb.us.rev0:move:089").max_pp
    )
    assert (
        rows[0][index["move.accuracy"]]
        == catalog.resolve_move("pokemon.red.gb.us.rev0:move:089").accuracy
    )
    assert rows[1][index["move.priority"]] > 0
    assert rows[2][index["move.accuracy"]] < 1


def test_family_split_rejects_cross_split_pair_and_context_leak():
    families = [
        {
            "role": "fit" if i < 32 else "holdout",
            "actor_species_id": i + 1,
            "opponent_species_id": i + 101,
            "contexts": [{"role": "fit" if i < 32 else "holdout"}] * 3,
        }
        for i in range(48)
    ]
    packet.validate_partitions(families)
    families[-1]["actor_species_id"] = families[0]["opponent_species_id"]
    families[-1]["opponent_species_id"] = families[0]["actor_species_id"]
    with pytest.raises(ValueError, match="unordered"):
        packet.validate_partitions(families)
    families[-1]["actor_species_id"] = 48
    families[-1]["opponent_species_id"] = 148
    families[-1]["contexts"][0] = {"role": "fit"}
    with pytest.raises(ValueError, match="context"):
        packet.validate_partitions(families)


def test_duplicate_claim_deadline_and_failed_branch_retention(tmp_path, monkeypatch):
    state_file = tmp_path / "run-state.json"
    state_file.write_text(
        json.dumps(
            {
                "completed_units": [],
                "started_monotonic_seconds": 10,
                "maximum_elapsed_seconds": 100,
                "native_dispatch_cutoff_seconds": 90,
            }
        )
    )
    monkeypatch.setattr(packet, "STATE", state_file)
    packet.state_update(unit="case-1")
    with pytest.raises(ValueError, match="duplicate"):
        packet.state_update(unit="case-1")
    monkeypatch.setattr(packet.time, "monotonic", lambda: 101)
    with pytest.raises(TimeoutError, match="native dispatch"):
        packet.deadline_check(native=True)
    monkeypatch.setattr(packet.time, "monotonic", lambda: 111)
    with pytest.raises(TimeoutError, match="eight-hour"):
        packet.deadline_check()
    monkeypatch.setattr(packet, "OUTPUT", tmp_path)
    branch = tmp_path / "case-1" / "branch-0-1"
    branch.mkdir(parents=True)
    (branch / "failure.json").write_text('{"error":"retained"}')
    with pytest.raises(ValueError, match="cannot replay"):
        packet._branch(None, None, None, None, {"id": "case-1"}, 0, 1)
    assert (branch / "failure.json").exists()


def test_untouched_component_parameters_are_exact():
    class Head:
        def __init__(self, value):
            self.value = value

        def to_dict(self):
            return {"weights": self.value}

    admitted = SimpleNamespace(move=Head([1.0]), control=Head([2.0]), switch=Head([3.0]))
    composed = SimpleNamespace(move=Head([1.0]), control=Head([2.0]), switch=Head([3.0]))
    packet.assert_untouched_components(admitted, composed)
    composed.switch.value = [3.0, 4.0]
    with pytest.raises(ValueError, match="switch"):
        packet.assert_untouched_components(admitted, composed)


def test_historical_forced_and_prompt_records_without_move_head_are_retained():
    catalog = PokemonRedBattleCatalog()
    assert (
        classify_retention_record({"heads": {"switch": {}}, "decision_context": "forced"}, catalog)
        == "no_move_head:forced"
    )
    assert (
        classify_retention_record({"heads": {"control": {}}, "decision_context": "prompt"}, catalog)
        == "no_move_head:prompt"
    )
