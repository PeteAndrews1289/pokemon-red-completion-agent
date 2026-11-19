"""Exact retained K funding diagnostics may reuse the ordinary PP screen."""
import pytest
from pokemon_red_completion.red_learned_trainer import (
    FrozenTrainerBattler,FROZEN_K_SHA256,K_QUALIFICATION_SHA256,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition


def actor():
    # Scope predicate only; this object has no session, model or input port.
    value=object.__new__(FrozenTrainerBattler)
    value.source_partition=ScenarioPartition.TRAIN
    value.train_funding_diagnostic=True
    value.pp_depleted_switch_screen=True
    value.model_sha256=FROZEN_K_SHA256
    value.qualification_sha256=K_QUALIFICATION_SHA256
    return value


def test_funding_pp_screen_preserves_story_only_scope_and_flag():
    a=actor()
    assert a.pp_reentry_screen_active('frozen-k-story-development') is True
    assert a.pp_reentry_screen_active('frozen-k-wild-training-development') is False
    a.pp_depleted_switch_screen=False
    assert a.pp_reentry_screen_active('frozen-k-story-development') is False


@pytest.mark.parametrize('field,value',[
    ('train_funding_diagnostic',False),('model_sha256','f'*64),
    ('qualification_sha256','f'*64),('train_story_contract',object()),
    ('development_preparation_scope',object()),('train_risk_story_scope',object()),
])
def test_no_arbitrary_train_model_or_conflicting_role(field,value):
    a=actor();setattr(a,field,value)
    with pytest.raises(ValueError):a.pp_reentry_screen_active('frozen-k-story-development')
