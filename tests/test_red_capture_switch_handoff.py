from copy import deepcopy

import pytest

from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_capture_switch_handoff import (
    ERROR, catcher_switch_failure, completed_catcher_handoff, confirmed_catcher_settlement,
    development_recovery, qualified_catcher_parent, valid_catcher_handoff,
)


def failure():
    return dict(error_type="ProtectedRecoveryError", error=ERROR, selected_kind="acquire_species",
                failure_phase="execution", safe_terminal=False, terminal_state_sha256="1" * 64,
                error_chain=[dict(error_type="ProtectedRecoveryError", error=ERROR)])


def receipt():
    row = failure()
    return dict(schema="pokemon.red.qualified-native-control-handoff.v1", state_sha256="1" * 64,
                binding_ref="pokemon.red:interrupted-wild:" + "1" * 64, qualified=True,
                original_failure_reason="native_execution_error", failed_transport_preserved=True,
                strategic_substitution=False, original_terminal_safe=False, compulsory_settlement_required=True,
                ordinary_capture_switch_faint=True, failed_outcome_sha256=canonical_sha256(row),
                inputs=0, frames=0, model_queries=0)


def episode():
    return dict(outcomes=[dict(before_state_sha256="1" * 64, terminal_state_sha256="2" * 64,
        selected_kind="recover_control", support_role="deterministic_control_recovery", verification="succeeded",
        safe_terminal=True, before=dict(battle_state=1), after=dict(battle_state=0,input_ready=True,buttons_released=True),
        evidence=dict(learned_recovery=False,model_queries=0,escape=dict(hp_scope="whole_party",
        initial_battle_state=1,final_battle_state=0,control_ready=True,verified=True,party_preserved=True,
        pp_preserved=True,level_preserved=True,battle_result=0,ordinary_opponent_ko_exit=True)))])


@pytest.mark.parametrize("key,val", [("error_type","RuntimeError"),("error","different"),("selected_kind","explore"),
                                    ("safe_terminal",None),("failure_phase","verification"),("error_chain",[])])
def test_matching_error_is_exact(key,val):
    assert not catcher_switch_failure({**failure(),key:val})


@pytest.mark.parametrize("key,val", [("inputs",1),("frames",True),("original_terminal_safe",0),
    ("ordinary_capture_switch_faint",False),("binding_ref","pokemon.red:interrupted-wild:"+"f"*64),
    ("failed_outcome_sha256","missing"),("compulsory_settlement_required",False)])
def test_receipt_needs_the_typed_witness(key,val):
    assert not valid_catcher_handoff({**receipt(),key:val})


def test_original_failure_and_settlement_have_distinct_evidence():
    row, r = failure(),receipt()
    outer=dict(continuation_reason="automatic_control_recovery",state_sha256=row["terminal_state_sha256"],
               qualified_native_control_handoff=r)
    assert qualified_catcher_parent(outer,row)
    assert not qualified_catcher_parent(outer,{**row,"safe_terminal":True})
    assert not completed_catcher_handoff(r)
    next_episode=episode()
    confirmed=confirmed_catcher_settlement(r,next_episode)
    assert completed_catcher_handoff(confirmed)
    assert confirmed["verified_settlement_outcome_sha256"]==canonical_sha256(next_episode["outcomes"][0])
    assert confirmed["original_terminal_safe"] is False


@pytest.mark.parametrize("layer,key,val", [
    ("outcome","before_state_sha256","e"*64),("outcome","support_role","model"),("outcome","verification","failed"),
    ("outcome","safe_terminal",False),("after","input_ready",False),("after","buttons_released",False),
    ("escape","ordinary_opponent_ko_exit",False),("escape","party_preserved",False),("escape","pp_preserved",False),
    ("escape","battle_result",1),("escape","final_battle_state",1)])
def test_unsettled_or_wrong_success_does_not_clear_the_failure(layer,key,val):
    e=episode();o=e["outcomes"][0]
    row={"outcome":o,"after":o["after"],"escape":o["evidence"]["escape"]}[layer]
    row[key]=val
    assert confirmed_catcher_settlement(receipt(),e) is None


def test_settled_flee_and_native_faint_prompt_are_supported():
    for escape in (dict(battle_result=2,run_attempts=1),dict(battle_result=2,faint_prompt_exit=True)):
        e=episode();details=e["outcomes"][0]["evidence"]["escape"]
        details.update(escape,ordinary_opponent_ko_exit=False)
        assert completed_catcher_handoff(confirmed_catcher_settlement(receipt(),e))


def test_authority_preserves_actual_acceptance_and_train_boundaries():
    copy=dict(partition="development",diagnostic_only=True,new_campaign=False,official_acceptance=False,
              fit_allowed=False,copy_back=False,force_resource_safety=True)
    assert development_recovery(copy)
    assert development_recovery({**copy,"development_campaign":True,"new_campaign":True,"diagnostic_only":False})
    for changes in (dict(copy_back=True),dict(partition="train"),dict(fit_allowed=True),dict(official_acceptance=True),
                    dict(actual_gameplay_resume_authorized=True),dict(force_resource_safety=False)):
        assert not development_recovery({**copy,**changes})
