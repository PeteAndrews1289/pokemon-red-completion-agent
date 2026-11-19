"""M0: losing the first Oak's Lab rival battle is an ordinary Gen I outcome.

Observed on fresh seed 202611100001 (opus55-session29 pilot): the native lab
script restored the party, kept the player in the lab with unchanged money and set
only BATTLED_RIVAL_IN_OAKS_LAB; the generic blackout verifier stopped the run.
Only that exact encounter is admitted; every other loss keeps blackout proof.
ROM-free: no emulator, native input, model or fit.
"""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.battle_runtime import BattleRuntimeTiming
from pokemon_red_completion.observation import EventFlag, MapId, RawGameState
from pokemon_red_completion.red_learned_trainer import FROZEN_J_SHA256
from pokemon_red_completion.red_trainer_battle_lifecycle import (
    TrainerBattleLifecycleError,
    continue_learned_trainer_battle,
)

EVENT = int(EventFlag.BATTLED_RIVAL_IN_OAKS_LAB)


def _flags(*bits):
    data = bytearray(8)
    for bit in bits:
        data[bit // 8] |= 1 << (bit % 8)
    return bytes(data)


def _fixture(fault=None, *, identity=(225, 25, 1), map_id=int(MapId.OAKS_LAB)):
    initial = RawGameState(
        True,
        map_id,
        4,
        7,
        1,  # party_count
        2,  # trainer battle
        badge_bits=0,
        event_flags=_flags(),
        party_species_ids=(177,),
        party_hp=(12,),
        party_max_hp=(19,),
        party_status=(0,),
        bag_items=(),
        player_money=3000,
    )
    state = SimpleNamespace(raw=initial, dialogue=False, actions=[])
    reader = SimpleNamespace(
        read=lambda: state.raw,
        read_active_trainer_identity=lambda: identity,
        read_pokedex_state=lambda: SimpleNamespace(owned_species={7}),
        read_last_blackout_map=lambda: 0,
        read_input_readiness=lambda: SimpleNamespace(ready=True),
        read_bottom_dialogue_box_visible=lambda: state.dialogue,
        read_total_pay_day_money=lambda: 0,
    )

    def play(_reader, _executor, **kwargs):
        kwargs["decision_guard"](initial)
        state.raw = replace(initial, party_hp=(0,))
        state.dialogue = True
        return SimpleNamespace(battle_won=False, stop_reason="party_defeated", public_dict=lambda: {})

    def execute(action):
        state.actions.append(action)
        if action.kind is not MacroActionKind.CONFIRM:
            return
        settled = dict(battle_state=0, battle_result=1, party_hp=(19,), event_flags=_flags(EVENT))
        if fault == "money_halved":
            settled["player_money"] = 1500
        elif fault == "warped":
            settled["map_id"] = 0
        elif fault == "extra_event":
            settled["event_flags"] = _flags(EVENT, 3)
        elif fault == "event_missing":
            settled["event_flags"] = _flags()
        elif fault == "not_restored":
            settled["party_hp"] = (5,)
        state.raw = replace(initial, **settled)
        state.dialogue = False

    battler = SimpleNamespace(continue_battle=play, model_sha256=FROZEN_J_SHA256, qualification_sha256=None)
    return state, reader, battler, SimpleNamespace(execute=execute), identity


def _run(fixture):
    _, reader, battler, executor, identity = fixture
    return continue_learned_trainer_battle(
        battler,
        reader,
        executor,
        trainer_identity=identity,
        defeated_event=EVENT,
        ordinary_victory_money=175,
        timing=BattleRuntimeTiming(),
        maximum_settle_pulses=4,
    )


def test_lab_rival_loss_without_blackout_is_an_ordinary_lost_outcome():
    result = _run(_fixture())
    assert result.outcome == "lost" and result.field_ready
    assert result.money_delta == 0
    assert result.final_state.map_id == int(MapId.OAKS_LAB)


@pytest.mark.parametrize("fault", ["money_halved", "warped", "extra_event", "event_missing", "not_restored"])
def test_lab_rival_loss_still_requires_the_exact_native_script_outcome(fault):
    with pytest.raises(TrainerBattleLifecycleError, match="verification"):
        _run(_fixture(fault))


@pytest.mark.parametrize(
    "identity,map_id",
    [((230, 30, 4), int(MapId.OAKS_LAB)), ((225, 25, 1), int(MapId.ROUTE_22))],
)
def test_other_losses_keep_the_blackout_contract(identity, map_id):
    with pytest.raises(TrainerBattleLifecycleError, match="verification"):
        _run(_fixture(identity=identity, map_id=map_id))
