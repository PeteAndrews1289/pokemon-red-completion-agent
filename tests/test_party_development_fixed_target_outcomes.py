"""ROM-free contract checks for fixed-level full-ready cost evidence."""
from dataclasses import replace
import pytest

from pokemon_red_completion.party_development_fixed_target_outcomes import (
    FIXED_LEVEL_READY_OBJECTIVE, FixedLevelReadyContract, ReadyEndpointEvidence,
    observed_party_sha256, freeze_fixed_level_ready_binding, adapt_fixed_level_ready_outcomes,
)
from pokemon_red_completion.party import PartyObservation
from pokemon_red_completion.party_development_outcomes import (
    PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE, PARTY_DEVELOPMENT_TOTAL_TASK_OBJECTIVE,
)
from pokemon_red_completion.party_development_rank import (
    PartyDevelopmentCandidateSet, PartyDevelopmentGoal, PARTY_DEVELOPMENT_WORKLOAD_FEATURE_NAMES,
    VenueOperationalPrior, VenuePriorFeatureMode,
)
from pokemon_red_completion.player_option_level_workload import OptionLevelWorkload
from pokemon_red_completion.scenario_lab import ScenarioPartition
from pokemon_red_completion.scenario_outcomes import ScenarioOutcomeError
from test_party_development_workload import _project
from test_party_development_outcomes import _trial, _completion, _before_party

def _fixture():
    menu = _project(remaining_xp=500)
    names = menu.feature_names
    rows = []
    for c in menu.candidates:
        features = list(c.features)
        features[names.index("context.goal.evolution")] = 0.
        features[names.index("context.goal.balance")] = 1.
        rows.append(replace(c, features=tuple(features)))
    menu = PartyDevelopmentCandidateSet(menu.kind, PartyDevelopmentGoal.BALANCE, tuple(rows))
    before = _before_party()
    contract = FixedLevelReadyContract(OptionLevelWorkload(25,26,500),
        observed_party_sha256(before),1,"5"*64,("6"*64,"7"*64))
    binding = freeze_fixed_level_ready_binding(menu,contract,
        original_semantic_snapshot_sha256="3"*64,
        scenario_id="unit-ready",root_lineage_id="unit-ready-root",initial_state_sha256="a"*64,
        partition=ScenarioPartition.TRAIN,source_commit="1"*40,source_bundle_sha256="2"*64,
        venue_priors=(VenueOperationalPrior(),)*2,venue_prior_registry_sha256="4"*64,
        venue_prior_feature_mode=VenuePriorFeatureMode.MASKED_UNCALIBRATED)
    trials=[];endpoints=[]
    for index,gain,frames in ((0,500,1000),(1,900,2000)):
        trial=_trial(menu,index,gain=gain,frames=frames,
            completion_after=_completion(level_deficit=24))
        mons=tuple(replace(m,level=26 if m.slot==1 else m.level,
                          moves=tuple(replace(move,current_pp=move.max_pp)for move in m.moves))
                   for m in trial.after_party.members)
        trial=replace(trial,after_party=PartyObservation(members=mons))
        endpoint=ReadyEndpointEvidence(index,"a"*64,str(index+8)*64,
            observed_party_sha256(trial.after_party),"5"*64,contract.home_binding_sha256_by_candidate[index],
            str(index+1)*64,True,20+index,frames)
        trials.append(trial);endpoints.append(endpoint)
    return menu,contract,binding,tuple(trials),tuple(endpoints)

def _adapt(f):
    menu,contract,binding,trials,endpoints=f
    return adapt_fixed_level_ready_outcomes(menu,trials,endpoints,contract=contract,
        prospective_binding=binding,original_semantic_snapshot_sha256="3"*64)

def test_completed_cost_precedes_overshoot_and_caps_useful_xp():
    example=_adapt(_fixture())
    a,b=example.outcomes
    assert a.criterion_values[-1]==b.criterion_values[-1]==500
    assert example.objective.preference_key(a.criterion_values)>example.objective.preference_key(b.criterion_values)

@pytest.mark.parametrize("fault",["pp_deficit","unknown_pp","hp_deficit","target_not_met","xp_short","evolution"])
def test_nonready_or_false_completion_is_not_a_cheap_label(fault):
    menu,contract,binding,trials,endpoints=_fixture()
    trial=trials[0];target=trial.after_party.members[0]
    if fault=="pp_deficit":target=replace(target,moves=(replace(target.moves[0],current_pp=19),))
    elif fault=="unknown_pp":target=replace(target,moves=(replace(target.moves[0],max_pp=None),))
    elif fault=="hp_deficit":target=replace(target,hp=99)
    elif fault=="target_not_met":target=replace(target,level=25)
    elif fault=="xp_short":target=replace(target,experience=1499)
    elif fault=="evolution":trial=replace(trial,evolution_completed=True)
    trial=replace(trial,after_party=PartyObservation(members=(target,*trial.after_party.members[1:])))
    endpoint=replace(endpoints[0],terminal_party_sha256=observed_party_sha256(trial.after_party))
    with pytest.raises(ScenarioOutcomeError):
        _adapt((menu,contract,binding,(trial,trials[1]),(endpoint,endpoints[1])))

@pytest.mark.parametrize("field,value",[
    ("source_state_sha256","b"*64),("recipient_binding_sha256","b"*64),
    ("home_binding_sha256","b"*64),("field_return_verified",False),("frames_executed",999)])
def test_endpoint_proof_must_match_exact_private_bindings(field,value):
    menu,contract,binding,trials,endpoints=_fixture()
    with pytest.raises(ScenarioOutcomeError):
        _adapt((menu,contract,binding,trials,(replace(endpoints[0],**{field:value}),endpoints[1])))

def test_target_contract_cannot_be_swapped_after_binding():
    menu,contract,binding,trials,endpoints=_fixture()
    changed=replace(contract,recipient_binding_sha256="b"*64)
    with pytest.raises(ScenarioOutcomeError):
        _adapt((menu,changed,binding,trials,endpoints))

def test_workload_must_equal_every_preinput_candidate():
    menu,contract,binding,trials,endpoints=_fixture()
    changed=replace(contract,workload=OptionLevelWorkload(25,26,499))
    with pytest.raises(ScenarioOutcomeError):
        _adapt((menu,changed,binding,trials,endpoints))

def test_reordering_uses_verified_recipient_slot_mapping():
    menu,contract,binding,trials,endpoints=_fixture()
    trial=trials[0]
    a,b=trial.after_party.members
    trial=replace(trial,after_party=PartyObservation(members=(replace(b,slot=1),replace(a,slot=2))),
                  after_target_slot=2)
    endpoint=replace(endpoints[0],terminal_party_sha256=observed_party_sha256(trial.after_party))
    assert _adapt((menu,contract,binding,(trial,trials[1]),(endpoint,endpoints[1]))).fully_measured

def test_old_objectives_are_distinct_and_unchanged_by_new_adapter():
    old=(PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE.public_dict(),PARTY_DEVELOPMENT_TOTAL_TASK_OBJECTIVE.public_dict())
    _adapt(_fixture())
    assert old==(PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE.public_dict(),PARTY_DEVELOPMENT_TOTAL_TASK_OBJECTIVE.public_dict())
    assert FIXED_LEVEL_READY_OBJECTIVE.objective_sha256 not in {
        PARTY_DEVELOPMENT_COMPLETION_OBJECTIVE.objective_sha256,PARTY_DEVELOPMENT_TOTAL_TASK_OBJECTIVE.objective_sha256}
