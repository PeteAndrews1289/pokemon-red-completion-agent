from types import SimpleNamespace as NS
import pytest
import run_configured_red_player as driver

@pytest.mark.parametrize("values,reported", [((3,1,2,0),2),((9,9,8,8),9),((0,0,0,0),0)])
def test_native_charges_and_skill_subset_have_distinct_scopes(values,reported):
    s=NS(heals=values[0],training_healing_trips=values[1],support_restorations=values[2],training_restoration_overlaps=values[3])
    proof=driver.evolution_recovery_accounting(s,{"healing_trips":reported})
    assert proof["passed"] and proof["charged_recovery_attempts"]==values[0]
    assert proof["reported_skill_healing_trips"]==reported

@pytest.mark.parametrize("values,reported", [((1,1,0,0),2),((17,9,8,8),9),((1,1,0,1),1),((True,1,0,0),1)])
def test_lost_costs_duplicate_charges_and_invalid_overlap_fail(values,reported):
    s=NS(heals=values[0],training_healing_trips=values[1],support_restorations=values[2],training_restoration_overlaps=values[3])
    assert not driver.evolution_recovery_accounting(s,{"healing_trips":reported})["passed"]
