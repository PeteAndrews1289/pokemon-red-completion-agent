from dataclasses import replace
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_scripted_story_trainer as scripted
from pokemon_red_completion.red_eventless_trainer import (
    eventless_battle_finished,
    eventless_battle_ready,
)
from pokemon_red_completion.red_story_battle import StoryTrainerContract


@pytest.mark.parametrize(
    "map_id,present,ready,won,lost",
    [
        (135, True, True, False, False),
        (135, False, False, True, False),
        (133, False, False, False, True),
        (202, True, False, False, True),
    ],
)
def test_poster_guard_requires_correct_room_and_native_disappearance(
    map_id, present, ready, won, lost
):
    reader = N(
        read=lambda: N(map_id=map_id),
        read_current_map_objects=lambda: (N(sprite_index=11, picture_id=24),) if present else (),
    )
    assert eventless_battle_ready(reader, (230, 30, 7)) is ready
    assert eventless_battle_finished(reader, (230, 30, 7), won=True) is won
    assert eventless_battle_finished(reader, (230, 30, 7), won=False) is lost
    assert not eventless_battle_ready(reader, (230, 30, 8))
    assert not eventless_battle_finished(reader, (230, 30, 8), won=True)


@pytest.mark.parametrize("fault", [None, "map", "object", "team", "defeated"])
@pytest.mark.parametrize("map_id", [135, 202])
def test_hideout_contract_is_cartridge_bound(monkeypatch, fault, map_id):
    cls, team, index, picture = (230, 7, 11, 24) if map_id == 135 else (229, 1, 1, 23)
    monkeypatch.setattr(scripted, "verify_rom_bytes", lambda _: None)
    monkeypatch.setattr(
        scripted,
        "map_object_events",
        lambda *a: (
            N(
                object_index=index,
                sprite_id=99 if fault == "object" else picture,
                trainer_class=cls,
                trainer_set=team + 1 if fault == "team" else team,
                movement=255,
            ),
        ),
    )
    monkeypatch.setattr(scripted, "trainer_party_quote", lambda *a: N(expected_victory_money=600))
    flags = bytearray(320)
    if fault == "defeated":
        flags[1703 // 8] |= 1 << (1703 % 8)
    raw = N(map_id=134 if fault == "map" else map_id, event_flags=bytes(flags))
    if fault in ("map", "object", "team") or (fault == "defeated" and map_id == 202):
        with pytest.raises(ValueError):
            scripted.hideout_scripted_contract(b"rom", raw)
    else:
        contract = scripted.hideout_scripted_contract(b"rom", raw)
        assert contract.trainer_identity == (cls, cls - 200, team)
        assert contract.defeated_event == (None if map_id == 135 else 1703)


def test_eventless_authority_is_not_generic():
    contract = StoryTrainerContract(
        "clear_rocket_hideout", "game-corner-poster-guard", 135, (230, 30, 7), None, 600
    )
    for changes in (
        {"map_id": 202},
        {"objective_id": "obtain_cut"},
        {"battle_plan_id": "other"},
        {"trainer_identity": (230, 30, 8)},
        {"victory_items": ((4, 1),)},
        {"victory_badge_bits": 1},
    ):
        with pytest.raises(ValueError):
            replace(contract, **changes)
