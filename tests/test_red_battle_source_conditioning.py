from __future__ import annotations

from dataclasses import replace

import pytest

from pokemon_red_completion.battle_source_conditioning import (
    BATTLE_RESOURCE_CONDITIONING_V1,
    BattleSourceConditioningError,
)
from pokemon_red_completion.observation import RawGameState
from pokemon_red_completion.red_battle_source_conditioning import red_battle_party_identity


def _raw() -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=0,
        player_x=0,
        player_y=0,
        battle_state=0,
        party_count=2,
        party_species_ids=(1, 2),
        party_levels=(20, 21),
        party_moves=((1, 2, 0, 0), (3, 4, 5, 0)),
        party_hp=(1, 40),
        party_max_hp=(50, 50),
        party_status=(4, 0),
        party_pp=((0, 0, 0, 0), (1, 2, 3, 0)),
    )


def test_red_resource_restoration_may_change_hp_status_and_pp_only() -> None:
    before = _raw()
    after = replace(
        before,
        party_hp=(50, 50),
        party_status=(0, 0),
        party_pp=((35, 25, 0, 0), (20, 20, 15, 0)),
    )

    BATTLE_RESOURCE_CONDITIONING_V1.require_identity_preserved(
        red_battle_party_identity(before),
        red_battle_party_identity(after),
    )


def test_red_resource_restoration_rejects_move_or_level_change() -> None:
    before = _raw()
    changed = replace(before, party_levels=(20, 22))

    with pytest.raises(BattleSourceConditioningError, match="changed"):
        BATTLE_RESOURCE_CONDITIONING_V1.require_identity_preserved(
            red_battle_party_identity(before),
            red_battle_party_identity(changed),
        )


def test_red_resource_identity_requires_complete_party_arrays() -> None:
    with pytest.raises(BattleSourceConditioningError, match="arrays"):
        red_battle_party_identity(replace(_raw(), party_moves=None))
