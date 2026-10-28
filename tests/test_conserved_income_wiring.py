import ast
from pathlib import Path
import pytest
import run_configured_red_player as script

@pytest.mark.parametrize('partition,bootstrap,flag,valid',[
    ('development',True,True,True),('development',True,False,True),
    ('development',False,True,False),('train',True,True,False),
    ('development',True,1,False),('development',True,'true',False),
])
def test_conserved_support_is_explicit_boolean_and_existing_development_permission(monkeypatch,partition,bootstrap,flag,valid):
    for name in ('declared_greedy_selection','declared_readiness_refinement','declared_preparation_component','declared_input_recording','declared_owned_machine_options','declared_league_first_collection_scope'):
        monkeypatch.setattr(script,name,lambda _:None)
    plan=dict(partition=partition,owned_stock_income_bootstrap=bootstrap,conserved_owned_medicine_income=flag)
    if valid:
        wiring=script.player_wiring_declaration(plan)
        assert wiring['conserved_owned_medicine_income'] is flag
        assert wiring['owned_stock_income_bootstrap'] is bootstrap
    else:
        with pytest.raises(ValueError,match='DEVELOPMENT'):script.player_wiring_declaration(plan)

def test_old_plans_forward_false_default_instead_of_none(monkeypatch):
    for name in ('declared_greedy_selection','declared_readiness_refinement','declared_preparation_component','declared_input_recording','declared_owned_machine_options','declared_league_first_collection_scope'):
        monkeypatch.setattr(script,name,lambda _:None)
    assert script.player_wiring_declaration({'partition':'development'})['conserved_owned_medicine_income'] is False

@pytest.mark.parametrize("flag", [False, True])
def test_actual_declaration_forwards_the_same_flag_as_copy_assembly(flag):
    from test_run_configured_red_player import _initial_work_order_wiring
    plan = dict(partition="development", owned_stock_income_bootstrap=True,
        conserved_owned_medicine_income=flag)
    assert _initial_work_order_wiring(plan) == script.player_wiring_declaration(plan)
    assert _initial_work_order_wiring(plan)["conserved_owned_medicine_income"] is flag
    assert "conserved_owned_medicine_income" in script.PLAYER_WIRING_FIELDS
