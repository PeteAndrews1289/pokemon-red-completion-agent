from copy import deepcopy
from dataclasses import replace

import numpy as np
import pytest
from test_red_battle_scenario import Reader, _raw
from test_red_trainer_practice_features import _observation

from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog, pokemon_red_move_ref
from pokemon_red_completion.red_battle_scenario import prepare_red_battle_scenario
from pokemon_red_completion.red_status_battle_features import (
    STATUS_MOVE_NAMES,
    expand_frozen_move,
    project_status_moves,
    status_choice_slots,
)
from pokemon_red_completion.red_status_practice import (
    StatusPracticeConditions,
    condition_train_status,
)
from pokemon_red_completion.red_trainer_practice_features import MOVE_FEATURE_NAMES, MOVE_SCHEMA_ID
from pokemon_red_completion.red_trainer_practice_head import TrainerHeadModel
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder
from pokemon_red_completion.scenario_lab import ScenarioPartition


def status_observation():
    obs = _observation()
    obs["features"]["battle"]["status_context"] = {
        "schema": "pokemon.core.battle.status-context.v1",
        "player_confused": False,
        "opponent_confused": True,
        "player_stages": [0, 0, 0, 0, -3, 0],
        "opponent_stages": [0] * 6,
    }
    obs["features"]["party"]["lead"]["moves"].append(
        {"slot_index": 2, "move_ref": pokemon_red_move_ref(156), "pp": 10}
    )
    return obs


def test_status_features_have_exact_frozen_prefix_and_distinguish_rest():
    obs = status_observation()
    batch = BattleFeatureProjector(PokemonRedBattleCatalog()).project(obs)
    projected = project_status_moves(obs, batch)
    assert projected.candidate_slots == (1, 3)  # do not confuse sparse slots with list indices
    assert projected.candidate_vectors[1][STATUS_MOVE_NAMES.index("effect.rest")] == 1
    head = TrainerHeadModel(
        MOVE_SCHEMA_ID,
        MOVE_FEATURE_NAMES,
        np.ones((len(MOVE_FEATURE_NAMES), 2)),
        np.zeros(2),
        np.ones(2),
        1,
    )
    expanded = expand_frozen_move(head)
    assert np.array_equal(
        expanded.scores(projected.candidate_vectors),
        head.scores(tuple(row[: len(MOVE_FEATURE_NAMES)] for row in projected.candidate_vectors)),
    )
    changed = deepcopy(obs)
    changed["features"]["battle"]["player_disable_turns"] = 9
    changed["features"]["world"] = {"area_ref": "different-room"}
    assert project_status_moves(changed, batch) == projected  # no duration/room leak


@pytest.mark.parametrize(
    "field,value", [("player_confused", None), ("opponent_stages", [0]), ("player_stages", [7] * 6)]
)
def test_status_features_fail_closed_on_unknown_context(field, value):
    obs = status_observation()
    obs["features"]["battle"]["status_context"][field] = value
    with pytest.raises(ValueError):
        project_status_moves(obs, BattleFeatureProjector(PokemonRedBattleCatalog()).project(obs))


@pytest.mark.parametrize("move", [28, 45, 47, 48, 50, 73, 77, 78, 79, 86, 105, 156])
def test_status_move_opt_in_preserves_pp_and_disable(move):
    catalog = PokemonRedBattleCatalog()
    raw = replace(_raw(), active_party_moves=(33, move, 0, 0), active_party_pp=(20, 10, 0, 0))
    encoder = PokemonRedObservationEncoder(Reader())
    assert prepare_red_battle_scenario(encoder, raw).supported_candidate_mask == (True, False)
    supported = catalog.status_move_supported(pokemon_red_move_ref(move))
    assert prepare_red_battle_scenario(
        encoder, raw, allow_status_moves=True
    ).supported_candidate_mask == (True, supported)
    assert prepare_red_battle_scenario(
        encoder, replace(raw, player_disabled_move_slot=2), allow_status_moves=True
    ).supported_candidate_mask == (True, False)
    assert prepare_red_battle_scenario(
        encoder, replace(raw, active_party_pp=(20, 0, 0, 0)), allow_status_moves=True
    ).supported_candidate_mask == (True, False)


def test_legacy_encoder_unchanged_and_new_context_explicit():
    raw = replace(
        _raw(),
        player_confused=True,
        enemy_confused=False,
        player_stat_stages=(7, 7, 7, 7, 4, 7),
        enemy_stat_stages=(7,) * 6,
    )
    encoder = PokemonRedObservationEncoder(Reader())
    assert "status_context" not in encoder.snapshot_from_raw(raw).to_dict()["features"]["battle"]
    obs = replace(encoder, include_status_context=True).snapshot_from_raw(raw).to_dict()
    assert obs["features"]["battle"]["status_context"]["player_stages"] == [0, 0, 0, 0, -3, 0]


def test_status_factory_rejects_non_train_before_memory_access():
    for partition in (ScenarioPartition.DEVELOPMENT, ScenarioPartition.TEST):
        with pytest.raises(ValueError, match="TRAIN-only"):
            condition_train_status(None, None, StatusPracticeConditions(), partition=partition)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"player_status": "toxic"},
        {"player_accuracy": True},
        {"disabled_slot": 0},
        {"opponent_accuracy": -7},
    ],
)
def test_status_conditions_fail_closed(kwargs):
    with pytest.raises(ValueError):
        StatusPracticeConditions(**kwargs)


def test_selector_preserves_frozen_damage_choice_and_disabled_mask():
    obs = status_observation()
    lead = obs["features"]["party"]["lead"]
    lead["moves"].append({"slot_index": 3, "move_ref": pokemon_red_move_ref(57), "pp": 15})
    projected = project_status_moves(
        obs, BattleFeatureProjector(PokemonRedBattleCatalog()).project(obs)
    )
    rng = np.random.default_rng(4)
    for _ in range(12):
        head = TrainerHeadModel(
            MOVE_SCHEMA_ID,
            MOVE_FEATURE_NAMES,
            rng.normal(size=(len(MOVE_FEATURE_NAMES), 4)),
            np.zeros(4),
            rng.normal(size=4),
            4,
        )
        damage_rows = tuple(
            projected.candidate_vectors[i][: len(MOVE_FEATURE_NAMES)] for i in (0, 2)
        )
        expected = (1, 4)[head.predict_index(damage_rows)]
        assert status_choice_slots(projected, (1, 3, 4), head) == tuple(
            s for s in (1, 3, 4) if s in {3, expected}
        )
        assert status_choice_slots(projected, (1, 4), head) == (expected,)
        assert status_choice_slots(projected, (3, 4), head) == (3, 4)
        assert status_choice_slots(projected, (3,), head) == (3,)


def test_status_model_roundtrip_and_legacy_checkpoint_identity():
    from test_red_trainer_practice_fit import _target

    from pokemon_red_completion.red_trainer_practice_fit import (
        TrainerPracticeThreeHeadModel,
        fit_trainer_practice_three_heads,
    )

    model = fit_trainer_practice_three_heads(
        [_target()], seed=1, epochs=2, require_corpus_floor=False
    )
    old = deepcopy(model.to_dict())
    candidate = replace(model, move=expand_frozen_move(model.move), damage_reference=model.move)
    assert (
        TrainerPracticeThreeHeadModel.from_dict(candidate.to_dict()).to_dict()
        == candidate.to_dict()
    )
    assert model.to_dict() == old and "damage_reference" not in old
    for invalid in (None, [], "missing"):
        with pytest.raises(ValueError, match="damage reference"):
            TrainerPracticeThreeHeadModel.from_dict(
                {**candidate.to_dict(), "damage_reference": invalid}
            )


@pytest.mark.parametrize("status", ["none", "sleep", "poison", "burn", "freeze", "paralysis"])
def test_teacher_conditions_keep_status_mirrors_and_live_stat_penalties_consistent(status):
    from collections import defaultdict
    from types import SimpleNamespace

    from pokemon_red_completion.observation import BattleMenuPhase, RamAddress
    from pokemon_red_completion.red_battle_practice_factory import _put_u16, _u16
    from pokemon_red_completion.red_status_practice import STATUSES

    memory = defaultdict(int)
    for address in (int(RamAddress.PLAYER_ATTACK_STAGE), int(RamAddress.ENEMY_DEFENSE_STAGE) - 1):
        for offset in range(6):
            memory[address + offset] = 7
    for address in (
        RamAddress.BATTLE_MON_ATTACK,
        RamAddress.BATTLE_MON_SPEED,
        RamAddress.ENEMY_ATTACK,
        RamAddress.ENEMY_SPEED,
    ):
        _put_u16(memory, int(address), 100)

    class StatusReader:
        def read(self):
            disabled = memory[int(RamAddress.PLAYER_DISABLED_MOVE)]
            return replace(
                _raw(),
                battle_state=2,
                enemy_party_count=1,
                enemy_party_position=0,
                active_party_status=memory[int(RamAddress.PARTY_MON_1) + 4],
                enemy_status=memory[int(RamAddress.ENEMY_STATUS)],
                player_confused=False,
                enemy_confused=False,
                player_stat_stages=tuple(
                    memory[int(RamAddress.PLAYER_ATTACK_STAGE) + i] for i in range(6)
                ),
                enemy_stat_stages=tuple(
                    memory[int(RamAddress.ENEMY_DEFENSE_STAGE) - 1 + i] for i in range(6)
                ),
                player_accuracy_stage=memory[int(RamAddress.PLAYER_ACCURACY_STAGE)],
                player_disabled_move_slot=disabled >> 4 or None,
                player_disable_turns=disabled & 15,
            )

        def read_battle_menu_state(self, _):
            return SimpleNamespace(phase=BattleMenuPhase.MAIN)

    conditions = StatusPracticeConditions(status, status, -3, 2, 2)
    receipt = condition_train_status(
        StatusReader(), memory, conditions, partition=ScenarioPartition.TRAIN
    )
    assert receipt["actor_memory_writes"] == 0
    assert memory[0xD018] == memory[int(RamAddress.PARTY_MON_1) + 4] == STATUSES[status]
    assert (
        memory[int(RamAddress.ENEMY_STATUS)]
        == memory[int(RamAddress.ENEMY_PARTY_MON_1) + 4]
        == STATUSES[status]
    )
    assert _u16(memory, int(RamAddress.BATTLE_MON_ATTACK)) == (50 if status == "burn" else 100)
    assert _u16(memory, int(RamAddress.ENEMY_SPEED)) == (25 if status == "paralysis" else 100)
