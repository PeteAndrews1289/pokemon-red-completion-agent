import pytest
from test_red_player_story_fly import indoor_setup
from pokemon_red_completion import red_player_story_fly as fly
from pokemon_red_completion import red_player_story_travel as travel


@pytest.mark.parametrize("unsupported",[True,False])
def test_indoor_fly_prefix_unavailable_without_hiding_other_admission_failures(monkeypatch,unsupported):
    rt,actions,args,live,world,distances,lesson=indoor_setup(monkeypatch)
    before=rt.emulator.save_state_bytes();quotes=[]
    def walking(*a,**kw):
        quotes.append(kw)
        if unsupported:
            raise travel.StoryIntermediateBoundaryUnavailable("intermediate boundary is not on the planned story route")
        raise ValueError("unrelated invalid story contract")
    monkeypatch.setattr(travel,"story_travel_binding",walking)
    if unsupported:
        assert fly.story_fly_binding(rt,actions,**args)is None
    else:
        with pytest.raises(ValueError,match="unrelated invalid story contract"):
            fly.story_fly_binding(rt,actions,**args)
    assert len(quotes)==1 and quotes[0]["objective_id"]==args["objective_id"]
    assert quotes[0]["certify_cash_approach"]is True
    assert rt.emulator.save_state_bytes()==before
    assert live.walk_calls==live.calls==actions.actions_executed==0
    assert lesson["completed_objectives"]==["receive_pokedex"]
