"""Native Champion escort may reach HoF before generic field readiness."""

from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from test_red_story_copy import setup as _shared_setup
from test_red_trainer_battle_lifecycle import fixture

from pokemon_red_completion.battle_runtime import BattleRuntimeTiming
from pokemon_red_completion.red_learned_trainer import FROZEN_K_SHA256, K_QUALIFICATION_SHA256
from pokemon_red_completion.red_story_battle import StoryTrainerContract
from pokemon_red_completion.red_trainer_battle_lifecycle import (
    TrainerBattleLifecycleError,
    continue_learned_trainer_battle,
)

setup = _shared_setup  # pytest fixture, not a direct call.


@pytest.mark.parametrize("authority", ["copy", "story"])
@pytest.mark.parametrize(
    "fault",
    [
        None,
        "map",
        "start_map",
        "event",
        "identity",
        "money",
        "result",
        "bag",
        "party",
        "registrations",
        "blackout_map",
    ],
)
def test_exact_champion_escort_preserves_other_guards(setup, authority, fault):
    state, reader, ordinary, executor = fixture()
    flags = bytearray(320)
    state.raw = replace(
        state.raw, map_id=113 if fault == "start_map" else 120, event_flags=bytes(flags)
    )
    identity = (242, 42, 2) if fault == "identity" else (243, 43, 2)
    reader.read_active_trainer_identity = lambda: identity
    initial = state.raw
    scope, battler, _ = setup
    scope = replace(
        scope,
        contract=StoryTrainerContract(
            "defeat_champion", "cartridge-final-story", 120, identity, 2305, 6435
        ),
    )
    battler.scope = scope
    if authority == "story":
        battler = ordinary
        battler.model_sha256 = FROZEN_K_SHA256
        battler.qualification_sha256 = K_QUALIFICATION_SHA256

    def play(_reader, _executor, **kwargs):
        kwargs["decision_guard"](initial)
        if fault != "event":
            flags[2305 // 8] |= 1 << (2305 % 8)
        state.raw = replace(
            initial,
            map_id=9 if fault == "map" else 118,
            player_y=2,
            player_x=4,
            battle_state=0,
            battle_result=1 if fault == "result" else 0,
            event_flags=bytes(flags),
            player_money=initial.player_money + 6435 + (fault == "money"),
            bag_items=() if fault == "bag" else initial.bag_items,
            party_species_ids=(1, 2) if fault == "party" else initial.party_species_ids,
        )
        if fault == "registrations":
            reader.read_pokedex_state = lambda: NS(owned_species=set())
        if fault == "blackout_map":
            reader.read_last_blackout_map = lambda: 9
        return NS(battle_won=True, stop_reason="battle_won")

    battler.continue_battle = play
    kwargs = dict(
        trainer_identity=identity,
        defeated_event=2305,
        ordinary_victory_money=6435,
        timing=BattleRuntimeTiming(),
        **({"copy_scope": scope} if authority == "copy" else {"story_authority": True}),
    )
    if fault:
        with pytest.raises(TrainerBattleLifecycleError):
            continue_learned_trainer_battle(battler, reader, executor, **kwargs)
    else:
        result = continue_learned_trainer_battle(battler, reader, executor, **kwargs)
        assert result.outcome == "won" and result.field_ready and result.money_delta == 6435
        assert result.final_state.map_id == 118
    assert not state.actions


def test_ordinary_nonstory_battle_cannot_use_escort_exception():
    state, reader, battler, executor = fixture()
    original = battler.continue_battle

    def play(*args, **kwargs):
        result = original(*args, **kwargs)
        state.raw = replace(state.raw, map_id=118, player_y=2, player_x=4)
        return result

    battler.continue_battle = play
    with pytest.raises(TrainerBattleLifecycleError):
        continue_learned_trainer_battle(
            battler,
            reader,
            executor,
            trainer_identity=(230, 30, 4),
            defeated_event=8,
            ordinary_victory_money=480,
            timing=BattleRuntimeTiming(),
        )
