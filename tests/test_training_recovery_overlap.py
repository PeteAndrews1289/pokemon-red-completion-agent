from dataclasses import replace
import json
import pytest
from pokemon_red_completion.actions import MacroAction,MacroActionKind
from pokemon_red_completion.goal_manager import GoalKind,GoalFailureReason,GoalAvailability,GoalOpportunity,GoalUnavailableReason
from pokemon_red_completion.goal_manager_runtime import GoalBindingSet,GoalExecutionReport,GoalVerification
from pokemon_red_completion import red_native_player as native
from test_red_native_player import setup,_binding


@pytest.mark.parametrize('fault',[None,'second_nested','after_scope','second_trip','verification','frame_budget','paid','wrong_binding','unknown_runtime','budget_text_runtime'])
def test_training_trip_and_nested_nurse_share_exactly_one_attempt(tmp_path,monkeypatch,fault):
    args,_=setup(tmp_path,monkeypatch)
    args['allow_collection_restoration']=True
    args['source']=dict(args['source'],partition='development')
    args['limits']=replace(args['limits'],decisions=1,heals=1,actions=10,frames=1 if fault=='frame_budget' else 20)
    continued=[]
    def bindings(rt,actions,boundary):
        def nurse():
            actions.execute(MacroAction(MacroActionKind.WAIT,repeat=2))
            return GoalExecutionReport(1,2,{'restore':True})
        restore=replace(_binding(GoalKind.RESTORE_TEAM,binding_ref='arbitrary' if fault=='wrong_binding' else 'pokemon.red:recovery:pokemon-center-pp',calls=[]),
            maximum_cash_debit=1 if fault=='paid' else 0,execute=nurse,
            verify=lambda _:GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED) if fault=='verification' else GoalVerification.succeeded())
        def trip(*_):
            actions.execute_restoration(restore)
            if fault=='second_nested':actions.execute_restoration(restore)
            if fault=='unknown_runtime':
                try:
                    raise ValueError('original unknown nursing cause')
                except ValueError as cause:
                    raise RuntimeError('unclassified nursing failure') from cause
            if fault=='budget_text_runtime':
                # Text alone cannot grant typed budget-stop authority.
                raise RuntimeError('native player restoration budget exhausted')
        def evolve():
            actions.execute_training_healing(trip,rt.reader,rt.emulator)
            if fault=='after_scope':actions.execute_restoration(restore)
            if fault=='second_trip':actions.execute_training_healing(trip,rt.reader,rt.emulator)
            continued.append(True)
            return GoalExecutionReport(1,2,{'target_unchanged':True})
        binding=replace(_binding(GoalKind.EVOLVE_SPECIES,binding_ref='selected-original',calls=[]),execute=evolve,verify=lambda _:GoalVerification.succeeded())
        blocked=GoalOpportunity('absent',GoalKind.EXPLORE,GoalAvailability.UNAVAILABLE,unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET)
        return GoalBindingSet((binding.opportunity,blocked),(binding,))
    args['enumerate_bindings']=bindings
    result=native.run_native_continuous_player(**args)
    costs=json.loads((args['output']/'native-costs.json').read_text())
    assert costs['restore_attempts']==costs['training_healing_attempts']==1
    invalid=fault in ('paid','wrong_binding')
    assert costs['nested_restore_attempts']==(0 if invalid else 1)
    assert costs.get('training_restoration_overlaps',0)==(0 if invalid else 1)
    assert result['model_decisions']==0 and continued==([True] if fault is None else [])
    exhausted=fault in ('second_nested','after_scope','second_trip')
    assert result['stop_reason']==('decision_budget' if fault is None else
        'restoration_budget' if exhausted else 'execution_failed')
    outcome=result['outcomes'][0]
    assert outcome['observed_cost']['actions']==costs['actions_attempted']
    assert outcome['observed_cost']['frames']==costs['frames']
    assert not outcome['ordinary_setback']
    assert json.loads((args['output']/'episode/step-000/outcome.json').read_text())['error_chain']==outcome['error_chain']
    if exhausted:
        assert outcome['error_type']=='RestorationBudgetExhausted'
        assert outcome['failure_reason']=='execution_budget_exhausted'
        assert outcome['error_chain']==[dict(error_type='RestorationBudgetExhausted',
            error='native player restoration budget exhausted')]
    if fault in ('unknown_runtime','budget_text_runtime'):
        assert outcome['error_type']=='RuntimeError' and outcome['failure_reason'] is None
        assert outcome['error_chain'][0]['error_type']=='RuntimeError'
        if fault=='unknown_runtime':
            assert outcome['error_chain']==[
                dict(error_type='RuntimeError',error='unclassified nursing failure'),
                dict(error_type='ValueError',error='original unknown nursing cause')]
        else:
            assert outcome['error']=='native player restoration budget exhausted'
            assert outcome['error_chain']==[dict(error_type='RuntimeError',error=outcome['error'])]
    assert costs['frames']==(0 if invalid or fault=='frame_budget' else 2)
    assert json.loads((args['output']/'training-healing-001/result.json').read_text())['succeeded']==(fault in (None,'after_scope','second_trip'))
    if not invalid:
        receipt=json.loads((args['output']/'restoration-000/intent.json').read_text())
        assert receipt['charged_by_training_trip'] is True and receipt['remaining_heals']==0
