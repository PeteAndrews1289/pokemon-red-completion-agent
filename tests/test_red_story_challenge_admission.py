"""A challenge cap rejects before routing or starting another native fight."""

import pytest
from test_red_player_story_battle import setup

from pokemon_red_completion import red_player_story_battle as s


def test_rejected_challenge_sends_no_input(monkeypatch):
    rt, actions, route, _, _, inputs, battles, contract, _=setup(monkeypatch)
    def reject(actual):
        assert actual==contract
        raise RuntimeError('attempt cap')
    binding=s.story_battle_binding(rt,actions,contract=contract,route=route,battler=object(),
        before_challenge=reject)
    with pytest.raises(RuntimeError,match='attempt cap'):
        binding.execute()
    assert not inputs and not battles and actions.actions_executed==rt.emulator.frame_count==0
    with pytest.raises(ValueError,match='consumed'):
        binding.execute()


def test_admission_receives_exact_contract_once_before_inputs(monkeypatch):
    rt,actions,route,_,_,inputs,battles,contract,_=setup(monkeypatch)
    seen=[]
    def admit(actual):
        assert not inputs and not battles and actions.actions_executed==0
        seen.append(actual)
    binding=s.story_battle_binding(rt,actions,contract=contract,route=route,battler=object(),
        before_challenge=admit)
    binding.execute()
    assert seen==[contract] and len(battles)==1


def test_admission_must_be_callable(monkeypatch):
    rt,actions,route,_,_,_,_,contract,_=setup(monkeypatch)
    with pytest.raises(TypeError,match='admission'):
        s.story_battle_binding(rt,actions,contract=contract,route=route,battler=object(),
            before_challenge=True)
