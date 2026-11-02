from types import SimpleNamespace

import pytest
import run_red_reference_battle as reference


def test_reference_scores_only_legal_moves_and_uses_accuracy(monkeypatch):
    rows = ((0.2,), (1.0,), (1.0,))
    monkeypatch.setattr(reference, "project_trainer_move_features", lambda *args: SimpleNamespace(
        feature_names=("move.accuracy",), candidate_slots=(1, 2, 3), candidate_vectors=rows,
    ))
    monkeypatch.setattr(reference, "estimated_finishing_features", lambda obs, row: (1, 0.5, 0))
    actor = reference.PublicDamageReference()
    prepared = SimpleNamespace(features=None, supported_candidate_mask=(True, False, True))
    assert actor.choose_main({}, prepared).move_slot == 3
    assert actor.last_decision_diagnostics["teacher"]
    assert not actor.last_decision_diagnostics["learned"]
    prepared.supported_candidate_mask = (True, False, False)
    assert actor.choose_main({}, prepared).move_slot == 1
    prepared.supported_candidate_mask = (False, False, False)
    with pytest.raises(ValueError, match="exhausted"):
        actor.choose_main({}, prepared)


def test_reference_declines_optional_and_uses_legal_highest_hp():
    actor = reference.PublicDamageReference()
    obs = {"features": {"party": {"members": [
        {"party_index": 0, "hp": 0}, {"party_index": 1, "hp": 30},
        {"party_index": 2, "hp": 40}, {"party_index": 3, "hp": 40},
    ]}}}
    assert actor.choose_switch(obs, (2, 3, 4), forced=False, may_decline=True) is None
    assert actor.choose_switch(obs, (2, 3, 4), forced=True, may_decline=False) == 3
    assert actor.choose_switch(obs, (2,), forced=True, may_decline=False) == 2
    with pytest.raises(ValueError, match="no living"):
        actor.choose_switch(obs, (1,), forced=True, may_decline=False)
    with pytest.raises(ValueError, match="mode"):
        actor.choose_switch(obs, (2,), forced=True, may_decline=True)
