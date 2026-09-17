from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from pokemon_red_completion import red_trainer_practice_policy as policy_module
from pokemon_red_completion.battle_actions import BattleAction
from pokemon_red_completion.battle_control_features import CONTROL_CLASS_REFS
from pokemon_red_completion.battle_semantics import (
    FEATURE_NAMES,
    FEATURE_SCHEMA_ID,
    BattleFeatureBatch,
)
from pokemon_red_completion.battle_switch_target import (
    SWITCH_TARGET_FEATURE_NAMES,
    BattleSwitchTargetCandidate,
    BattleSwitchTargetSet,
)
from pokemon_red_completion.red_battle_scenario import PreparedRedBattleScenario


def _prepared() -> PreparedRedBattleScenario:
    vector = tuple(0.0 for _ in FEATURE_NAMES)
    return PreparedRedBattleScenario(
        initial_observation_sha256="b" * 64,
        features=BattleFeatureBatch(
            feature_names=FEATURE_NAMES,
            candidate_vectors=(vector, vector),
            legal_mask=(True, True),
            current_pp=(10.0, 5.0),
            slot_indices=(0, 1),
            schema_id=FEATURE_SCHEMA_ID,
        ),
    )


def _observation() -> dict[str, object]:
    return {"features": {"battle": {"opponent_species_ref": "species", "opponent_level": 30}}}


def _policy(monkeypatch, control_ref: str):
    monkeypatch.setattr(
        policy_module,
        "project_control_features",
        lambda *_args, **_kwargs: np.zeros(3),
    )
    candidate_features = (0.0,) * len(SWITCH_TARGET_FEATURE_NAMES)
    monkeypatch.setattr(
        policy_module,
        "project_switch_target_candidates",
        lambda *_args: BattleSwitchTargetSet(
            (
                BattleSwitchTargetCandidate(2, candidate_features),
                BattleSwitchTargetCandidate(3, candidate_features),
            )
        ),
    )
    return policy_module.RedTrainerPracticeModelPolicy(
        policy_id="frozen-composite-unit",
        battle_plan_id="trainer-unit",
        move_model=SimpleNamespace(predict=lambda *_args, **_kwargs: 1),
        control_model=SimpleNamespace(predict_ref=lambda _features: control_ref),
        switch_model=SimpleNamespace(probabilities=lambda _candidates: np.array([0.2, 0.8])),
    )


def test_composite_model_owns_move_and_voluntary_switch_targets(monkeypatch):
    attack = _policy(monkeypatch, CONTROL_CLASS_REFS[0])
    assert attack.choose_main(_observation(), _prepared()) == BattleAction.move(2)
    assert attack.last_decision_diagnostics["control_class_ref"] == CONTROL_CLASS_REFS[0]
    assert attack.last_decision_diagnostics["move_candidate_slots"] == [1, 2]
    switch = _policy(monkeypatch, CONTROL_CLASS_REFS[5])
    assert switch.choose_main(_observation(), _prepared()) == BattleAction.switch(3)
    assert switch.last_decision_diagnostics["switch_probabilities"] == [0.2, 0.8]


def test_composite_model_owns_prompt_and_forced_switch(monkeypatch):
    decline = _policy(monkeypatch, CONTROL_CLASS_REFS[0])
    assert decline.choose_switch(_observation(), (2, 3), forced=False, may_decline=True) is None
    forced = _policy(monkeypatch, CONTROL_CLASS_REFS[0])
    assert forced.choose_switch(_observation(), (2, 3), forced=True, may_decline=False) == 3


def test_composite_model_fails_closed_on_unavailable_action(monkeypatch):
    unsupported = _policy(monkeypatch, CONTROL_CLASS_REFS[1])
    with pytest.raises(policy_module.TrainerPracticeModelPolicyError, match="unsupported class"):
        unsupported.choose_main(_observation(), _prepared())
