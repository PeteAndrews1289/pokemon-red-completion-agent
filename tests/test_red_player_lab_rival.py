from dataclasses import replace
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_lab_rival as r
from pokemon_red_completion.observation import EventFlag, MapId
from pokemon_red_completion.goal_manager import GoalKind


@pytest.mark.parametrize("starter,team", [(176, 1), (153, 2), (177, 3)])
def test_lab_contract_matches_live_rival_not_a_supplied_opponent(monkeypatch, starter, team):
    monkeypatch.setattr(r, "trainer_party_quote", lambda rom, cls, n: N(
        party=(N(internal_species={1:176,2:153,3:177}[n]),),
        trainer_set=n, expected_victory_money=175))
    reader = N(read=lambda:N(event_flags=bytes(320)), read_rival_starter=lambda:starter)
    contract = r.lab_rival_contract(b"rom", reader)
    assert contract.trainer_identity == (225,25,team)
    assert contract.defeated_event == int(EventFlag.BATTLED_RIVAL_IN_OAKS_LAB)
    assert contract.objective_id == "receive_pokedex" and contract.victory_money == 175


@pytest.mark.parametrize("fault", ["consumed", "missing", "ambiguous", "unmatched"])
def test_lab_contract_fails_closed(monkeypatch, fault):
    flags = bytearray(320)
    event = int(EventFlag.BATTLED_RIVAL_IN_OAKS_LAB)
    if fault == "consumed":
        flags[event//8] |= 1 << (event%8)
    monkeypatch.setattr(r,"trainer_party_quote",lambda rom,cls,n:N(
        party=(N(internal_species=153 if fault == "ambiguous" else n),),
        trainer_set=n,expected_victory_money=175))
    reader = N(read=lambda:N(event_flags=None if fault == "missing" else bytes(flags)),
        read_rival_starter=lambda:153)
    with pytest.raises(ValueError):
        r.lab_rival_contract(b"rom",reader)


def test_lab_option_only_wires_existing_learned_lifecycle(monkeypatch):
    rt = N(reader=N(read=lambda:N(map_id=int(MapId.OAKS_LAB)),
        read_oaks_errand_state=lambda raw:N(battled_rival=False)))
    from pokemon_red_completion.goal_manager_runtime import ExecutableGoalBinding, GoalVerification
    binding = ExecutableGoalBinding("lab-rival",GoalKind.ADVANCE_STORY,.2,.4,
        lambda:None,lambda _:GoalVerification.succeeded())
    observed=[]
    monkeypatch.setattr(r,"scripted_rival_binding",lambda *a,**k:observed.append(k) or binding)
    actor=object()
    result = r.lab_rival_story_option(rt,object(),route=object(),battler=actor)
    assert result[0] == replace(binding,story_objective_ref="receive_pokedex")
    assert observed[0]["battler"] is actor
    assert observed[0]["entries"] == (((5,4),"down"),)
    assert result[1].combat_required and not result[1].opposition_known


def test_contract_selector_is_resolved_before_existing_controller(monkeypatch):
    rt = N(reader=N(read=lambda:N(map_id=int(MapId.OAKS_LAB)),
        read_oaks_errand_state=lambda raw:N(battled_rival=False)))
    contract, actor, called = object(), object(), []
    monkeypatch.setattr(r, "lab_rival_contract", lambda rom, reader: contract)
    def select(value):
        called.append(value)
        return actor
    def bind(*args, **kwargs):
        assert kwargs["battler"] is actor and called == [contract]
    monkeypatch.setattr(r, "scripted_rival_binding", bind)
    assert r.lab_rival_story_option(rt, object(), route=N(rom=b"rom"),
        battler=object(), battler_for_contract=select) is None


@pytest.mark.parametrize("map_id,resolved", [(0,False),(int(MapId.OAKS_LAB),True)])
def test_resolved_or_wrong_location_has_no_new_battle(monkeypatch,map_id,resolved):
    rt=N(reader=N(read=lambda:N(map_id=map_id),read_oaks_errand_state=lambda raw:N(battled_rival=resolved)))
    monkeypatch.setattr(r,"scripted_rival_binding",lambda *a,**k:pytest.fail("no battle replay"))
    assert r.lab_rival_story_option(rt,object(),route=object(),battler=object()) is None
