"""One synthetic numerical fit seam; no native evidence or seven-row model fit."""
import numpy as np
import pytest

from pokemon_red_completion.living_dex_option_value import option_feature_names
from pokemon_red_completion.player_challenge_consequence import (
    ChallengeConsequence,ChallengeConsequenceHead,ConsequenceExample,
    fit_challenge_consequence,
)
from pokemon_red_completion.player_consequence_projection import (
    PROSPECTIVE_CONTEXT,consequence_feature_names,project_consequence_features,
)
from pokemon_red_completion.player_option_preparation import OptionPreparation,preparation_feature_names
from pokemon_red_completion.player_option_level_workload import OptionLevelWorkload,level_workload_feature_names


def test_prospective_synthetic_fit_document_roundtrip_and_raw_inference():
    """Exercise real ridge fitting, codec and predictor on synthetic raw V15 rows."""
    names=option_feature_names(15)
    def raw(kind,hp,*,history='won',budget=1.):
        values=[0.]*len(names)
        facts={f'kind.{kind}':1.,f'readiness.{kind}_x_observed':1.,
            f'readiness.{kind}_x_current.hp_fraction':hp,
            f'readiness.{kind}_x_current.pp_known':1.,
            f'readiness.{kind}_x_current.pp_fraction':.8,
            f'readiness.{kind}_x_current.combat_level_spread':.1,
            f'challenge.{kind}_x_present':1.,f'challenge.{kind}_x_combat_required':1.,
            f'challenge.{kind}_x_opposition_known':1.,f'challenge.{kind}_x_opponent_fraction':2/6,
            f'challenge.{kind}_x_maximum_level_deficit':.03,
            f'challenge.{kind}_x_median_level_deficit':.02,
            f'readiness.{kind}_x_recent.won':float(history=='won'),
            f'readiness.{kind}_x_recent.lost':float(history=='lost'),
            f'readiness.{kind}_x_current.median_combat_level_gap':-.1 if history=='won' else .3,
            f'readiness.{kind}_x_current.lowest_combat_level_gap':.05 if history=='won' else .4}
        for suffix in ('attempts','actions','frames','seconds','heals'):
            facts[f'readiness.{kind}_x_budget.{suffix}']=budget
        if kind=='develop':
            facts.update(zip(preparation_feature_names(),OptionPreparation(19,20,1141,hp,None,True,False,20).vector(),strict=True))
            facts.update(zip(level_workload_feature_names(),OptionLevelWorkload(19,20,1141).vector(),strict=True))
        for name,value in facts.items():values[names.index(name)]=value
        return tuple(values)
    rows=[]
    for hp in (.1,.3,.7,.9):
        for kind in ('unlock_access','develop'):
            won=hp>.5
            rows.append(ConsequenceExample(f'{len(rows)+1:064x}','f'*64,
                raw(kind,hp,history='won' if won else 'lost',budget=hp),
                ChallengeConsequence(True,won,100+(20 if kind=='develop' else 0),1000,50*(not won),0,0,
                    feedback_version=2,initial_goal_failed=False,challenge_progress=float(won)),
                None,provenance='synthetic',feature_version=15,feedback_version=2))
    # One real fitter call on deliberately synthetic rows, with the existing recipe.
    model=fit_challenge_consequence(tuple(rows),feature_version=15,feedback_version=2,
        ridge=1.,context_projection=PROSPECTIVE_CONTEXT)
    assert model.provenance=='synthetic' and model.examples==8
    assert model.coefficients.shape==(317,9) and len(names)==506
    assert all(len(row.features)==506 for row in rows)
    document=model.document()
    assert document['feature_names']==list(consequence_feature_names(15,PROSPECTIVE_CONTEXT))
    restored=ChallengeConsequenceHead.from_document(document,expected_sha256=model.model_sha256)
    assert restored.model_sha256==model.model_sha256
    for vector in [row.features for row in rows]+[raw('unlock_access',.6),raw('develop',.6)]:
        prediction=model.predict(vector)
        projected=np.asarray(project_consequence_features(vector,feature_version=15,context_projection=PROSPECTIVE_CONTEXT))
        expected=np.maximum(0.,((projected-model.feature_mean)/model.feature_scale)@model.coefficients+model.intercept)
        expected[:2]=np.clip(expected[:2],0.,1.);expected[1]=min(expected[0],expected[1]);expected[7:]=np.clip(expected[7:],0.,1.)
        assert prediction==restored.predict(vector)
        assert np.allclose(prediction,expected)
    assert model.predict(raw('unlock_access',.9))[1]>model.predict(raw('unlock_access',.1))[1]+.3
    assert model.predict(raw('develop',.6,history='won',budget=1.))==model.predict(raw('develop',.6,history='lost',budget=.1))
    with pytest.raises(ValueError):restored.predict((0.,)*317)
