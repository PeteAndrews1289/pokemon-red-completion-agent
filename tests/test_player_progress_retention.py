from copy import deepcopy

import pytest

from pokemon_red_completion.red_player_lesson_runtime import review_player_progress_retention


def facts(*, objectives=(), owned=(), cash=0, xp=0, carry=0):
    return dict(completed_objectives=list(objectives),owned_species=list(owned),cash=cash,
                player_lesson=dict(party=[dict(specimen_ref="trainee",experience=xp),
                                          dict(specimen_ref="carry",experience=carry)]))


def episode(states, kinds=None):
    return [dict(before=a,after=b,selected_kind=(kinds or ["advance_story"]*(len(states)-1))[i],
                 before_state_sha256=f"{i:064x}",terminal_state_sha256=f"{i+1:064x}",
                 safe_terminal=True,error_type=None,error=None,verification="succeeded")
            for i,(a,b) in enumerate(zip(states,states[1:]))]


def review(rows, **kwargs):
    return review_player_progress_retention(rows,stall_window=4,repeat_window=3,**kwargs)


def test_required_story_endpoint_and_input_immutability():
    rows=episode([facts(),facts(),facts(objectives=("badge",))])
    original=deepcopy(rows)
    result=review(rows,required_objectives=("badge",))
    assert result["eligible_for_declared_retention_review"] and rows==original
    assert result["additional_inputs_authorized"] is False and result["automatic_stop"] is False


def test_frame_counters_and_changed_state_hashes_do_not_prove_progress():
    states=[dict(facts(),frames=i*100,actions=i*4) for i in range(6)]
    result=review(episode(states),required_objectives=("badge",))
    assert result["longest_known_no_progress_run"]==5
    assert result["endpoints_met"] is False and result["warnings"]


def test_repeated_or_alternating_healing_and_earning_requires_review():
    rows=episode([facts(cash=50) for _ in range(5)],
                 ["restore_team","resupply","restore_team","resupply"])
    result=review(rows,resource_target=50)
    assert result["endpoints_met"] is True
    assert result["longest_support_only_no_progress_run"]==4
    assert not result["eligible_for_declared_retention_review"]
    assert any(x["kind"]=="support_only_without_declared_progress_window" for x in result["warnings"])


def test_needed_income_reduces_declared_gap_even_during_many_support_steps():
    rows=episode([facts(cash=i*10) for i in range(9)],["resupply"]*8)
    result=review(rows,resource_target=80)
    assert result["eligible_for_declared_retention_review"] and not result["warnings"]


def test_income_after_declared_target_does_not_hide_a_loop():
    rows=episode([facts(cash=100+i*10,carry=i*100) for i in range(6)],["resupply"]*5)
    result=review(rows,resource_target=100)
    assert result["longest_support_only_no_progress_run"]==5
    assert not result["eligible_for_declared_retention_review"]


def test_declared_trainee_xp_is_useful_before_evolution_registration():
    rows=episode([facts(xp=i*10) for i in range(7)],["evolve_species"]*6)
    result=review(rows,training_specimen_refs=("trainee",),required_owned_species=("evolved",))
    assert not result["warnings"] and result["unknown_progress_rows"]==0
    assert result["endpoints_met"] is False


def test_incidental_carry_xp_is_not_declared_trainee_progress():
    rows=episode([facts(carry=i*10) for i in range(6)],["evolve_species"]*5)
    result=review(rows,training_specimen_refs=("trainee",),required_owned_species=("evolved",))
    assert result["longest_known_no_progress_run"]==5 and result["warnings"]


def test_missing_trainee_evidence_is_unknown_not_fabricated_no_progress():
    rows=episode([facts(carry=i*10) for i in range(6)],["evolve_species"]*5)
    result=review(rows,required_owned_species=("evolved",))
    assert result["unknown_progress_rows"]==5 and not result["warnings"]


def test_capture_retains_ordinary_setback_then_proves_registration():
    rows=episode([facts(),facts(),facts(owned=("captured",))],["acquire_species"]*2)
    rows[0].update(verification="failed",ordinary_setback=True)
    result=review(rows,required_owned_species=("captured",))
    assert result["eligible_for_declared_retention_review"] and result["ordinary_setbacks"]==1


def test_missing_endpoint_or_empty_episode_never_claims_acceptance():
    assert not review(episode([facts(),facts()]))["eligible_for_declared_retention_review"]
    assert review([],required_objectives=("badge",))["endpoints_met"] is None


def test_break_in_native_state_chain_is_not_continuous_progress():
    rows=episode([facts(),facts(),facts(objectives=("badge",))])
    rows[1]["before_state_sha256"]="f"*64
    assert review(rows,required_objectives=("badge",))["state_chain_breaks"]==1


@pytest.mark.parametrize("change",[
    dict(error_type="AssertionError",error=""),dict(safe_terminal=False),dict(safe_terminal=None),
    dict(before_state_sha256=None),
])
def test_error_or_unverified_terminal_cannot_pass(change):
    rows=episode([facts(),facts(objectives=("badge",))]);rows[0].update(change)
    assert not review(rows,required_objectives=("badge",))["eligible_for_declared_retention_review"]


@pytest.mark.parametrize("window",[0,-1,True,1.5])
def test_invalid_review_windows_are_rejected(window):
    with pytest.raises(ValueError):
        review_player_progress_retention([],stall_window=window,repeat_window=3)


def test_missing_native_facts_are_unknown():
    rows=episode([facts(),facts(objectives=("badge",))]);del rows[0]["before"]["owned_species"]
    result=review(rows,required_objectives=("badge",))
    assert result["unknown_progress_rows"]==1 and not result["eligible_for_declared_retention_review"]


@pytest.mark.parametrize("change",[dict(verification="failed"),dict(verification=None),dict(before_state_sha256="z"*64)])
def test_bad_verification_or_hash_is_not_accepted(change):
    rows=episode([facts(),facts(objectives=("badge",))]);rows[0].update(change)
    assert not review(rows,required_objectives=("badge",))["eligible_for_declared_retention_review"]


def test_null_native_facts_or_lesson_fail_closed():
    rows=episode([facts(),facts()]);rows[0]["after"]=None
    assert not review(rows,required_objectives=("badge",))["eligible_for_declared_retention_review"]
    rows=episode([facts(),facts()],["evolve_species"]);rows[0]["before"]["player_lesson"]=None
    assert review(rows,training_specimen_refs=("trainee",))["unknown_progress_rows"]==1
