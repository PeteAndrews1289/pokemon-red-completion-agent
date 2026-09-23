from dataclasses import replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion.observation import EventFlag, MapId, RawGameState
from pokemon_red_completion.red_prepared_gym_continuation import (
    prepared_erika_available,
    run_prepared_erika_continuation,
)


def _prepared():
    events = bytearray(320)
    events[int(EventFlag.GOT_TM13) // 8] |= 1 << (int(EventFlag.GOT_TM13) % 8)
    return RawGameState(
        True,
        MapId.CELADON_CITY,
        41,
        10,
        4,
        0,
        party_species_ids=(28, 64, 59, 104),
        party_hp=(116, 59, 37, 68),
        party_max_hp=(116, 59, 37, 68),
        party_status=(0, 0, 0, 0),
        first_party_moves=(44, 39, 58, 55),
        first_party_pp=(25, 30, 10, 25),
        event_flags=bytes(events),
        badge_bits=7,
        bag_items=((19, 5),),
        player_money=1209,
    )


def test_prepared_continuation_admits_earned_party_without_rebuying_lesson():
    assert prepared_erika_available(_prepared())
    assert prepared_erika_available(replace(_prepared(), map_id=MapId.CELADON_GYM))


@pytest.mark.parametrize("options", [
    {"resume_battle": True}, {"remaining_potions": 7}, {"remaining_status_items": 4},
    {"remaining_potions": -1}, {"remaining_status_items": True}, {"resume_battle": 1},
])
def test_continuation_rejects_missing_or_reset_resource_allowances(options):
    reader = SimpleNamespace(read=_prepared)
    with pytest.raises((ValueError, TypeError)):
        run_prepared_erika_continuation(None, reader, None, rom=b"unused", **options)


@pytest.mark.parametrize(
    "changes",
    [
        {"battle_state": 2},
        {"badge_bits": 15},
        {"event_flags": bytes(320)},
        {"party_hp": (0, 59, 37, 68)},
        {"party_species_ids": (28, 59, 64, 104)},
        {"first_party_pp": (25, 30, 0, 25)},
        {"first_party_moves": (44, 39, 61, 55)},
        {"bag_items": ((221, 1),)},
        {"map_id": MapId.VIRIDIAN_CITY},
        {"first_party_moves": (44,)},
        {"first_party_pp": (25,)},
        {"party_status": ()},
        {"party_count": 3},
        {"party_hp": (116,), "party_max_hp": (116,)},
    ],
)
def test_prepared_continuation_rejects_incompatible_or_complete_origins(changes):
    assert not prepared_erika_available(replace(_prepared(), **changes))
