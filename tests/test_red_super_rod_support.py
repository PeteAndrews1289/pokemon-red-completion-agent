from dataclasses import replace

import pytest

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.observation import (
    InputReadiness,
    ItemId,
    MapId,
    RawGameState,
)
from pokemon_red_completion.red_super_rod_support import (
    SUPER_ROD_FACING,
    SUPER_ROD_HOUSE_MAP_ID,
    SUPER_ROD_NPC_YX,
    SUPER_ROD_STANCE_YX,
    SUPER_ROD_STATUS_MASK,
    RedSuperRodSupportError,
    RedSuperRodSupportExecutor,
    observe_red_super_rod_support,
)


def _raw(**changes) -> RawGameState:
    base = RawGameState(
        game_started=True,
        map_id=SUPER_ROD_HOUSE_MAP_ID,
        player_x=2,
        player_y=3,
        party_count=2,
        battle_state=0,
        badge_bits=0xFF,
        bag_item_ids=(3,),
        bag_items=((3, 12),),
        event_flags=b"events",
        party_species_ids=(9, 25),
        party_levels=(70, 30),
        party_hp=(200, 80),
        party_max_hp=(200, 80),
        party_status=(0, 0),
        party_moves=((1, 2, 3, 4), (5, 6, 7, 8)),
        party_pp=((10, 10, 10, 10), (10, 10, 10, 10)),
        player_money=58,
        status_flags_1=0,
    )
    return replace(base, **changes)


class _Reader:
    def __init__(self, raw=None):
        self.raw = raw or _raw()
        self.ready = True
        self.facing = "down"
        self.dialogue = False

    def read(self):
        return self.raw

    def read_input_readiness(self):
        return InputReadiness(0 if self.ready else 1, 0, 0, 0, 0)

    def read_player_facing(self):
        return self.facing

    def read_bottom_dialogue_box_visible(self):
        return self.dialogue


class _Emulator:
    frame_count = 0


class _GiftActions:
    def __init__(self, reader, emulator, acquire_on=3, settle_on=4):
        self.reader = reader
        self.emulator = emulator
        self.acquire_on = acquire_on
        self.settle_on = settle_on
        self.count = 0
        self.kinds = []

    def execute(self, action):
        self.count += 1
        self.kinds.append(action.kind)
        self.emulator.frame_count += 24
        self.reader.ready = False
        self.reader.dialogue = True
        if (
            self.count >= self.acquire_on
            and int(ItemId.SUPER_ROD) not in dict(self.reader.raw.bag_items)
        ):
            self.reader.raw = replace(
                self.reader.raw,
                bag_items=(*self.reader.raw.bag_items, (int(ItemId.SUPER_ROD), 1)),
                bag_item_ids=(*self.reader.raw.bag_item_ids, int(ItemId.SUPER_ROD)),
                status_flags_1=self.reader.raw.status_flags_1 | SUPER_ROD_STATUS_MASK,
            )
        if self.count >= self.settle_on:
            self.reader.ready = True
            self.reader.dialogue = False


def test_red_super_rod_constants_match_cartridge_contract():
    assert MapId.ROUTE_12_SUPER_ROD_HOUSE == 0xBD
    assert ItemId.SUPER_ROD == 0x4E
    assert SUPER_ROD_STATUS_MASK == 1 << 5
    assert SUPER_ROD_NPC_YX == (4, 2)
    assert SUPER_ROD_STANCE_YX == (3, 2)
    assert SUPER_ROD_FACING == "down"


def test_observation_distinguishes_ready_and_acquired():
    reader = _Reader()
    before = observe_red_super_rod_support(reader)
    assert before.ready_to_receive and not before.acquired
    reader.raw = replace(
        reader.raw,
        bag_items=((3, 12), (int(ItemId.SUPER_ROD), 1)),
        status_flags_1=SUPER_ROD_STATUS_MASK,
    )
    after = observe_red_super_rod_support(reader)
    assert after.acquired and not after.ready_to_receive


@pytest.mark.parametrize(
    "mutation",
    ["map", "position", "facing", "input", "dialogue", "battle", "full_bag"],
)
def test_ready_boundary_rejects_each_missing_precondition(mutation):
    reader = _Reader()
    if mutation == "map":
        reader.raw = replace(reader.raw, map_id=int(MapId.ROUTE_12))
    elif mutation == "position":
        reader.raw = replace(reader.raw, player_y=4)
    elif mutation == "facing":
        reader.facing = "left"
    elif mutation == "input":
        reader.ready = False
    elif mutation == "dialogue":
        reader.dialogue = True
    elif mutation == "battle":
        reader.raw = replace(reader.raw, battle_state=1)
    else:
        reader.raw = replace(reader.raw, bag_items=tuple((i, 1) for i in range(1, 21)))
    assert not observe_red_super_rod_support(reader).ready_to_receive


@pytest.mark.parametrize("mutation", ["missing", "item_only", "bit_only", "duplicate", "zero"])
def test_observation_fails_closed_on_incomplete_or_inconsistent_evidence(mutation):
    reader = _Reader()
    if mutation == "missing":
        reader.raw = replace(reader.raw, status_flags_1=None)
    elif mutation == "item_only":
        reader.raw = replace(reader.raw, bag_items=((3, 12), (0x4E, 1)))
    elif mutation == "bit_only":
        reader.raw = replace(reader.raw, status_flags_1=SUPER_ROD_STATUS_MASK)
    elif mutation == "duplicate":
        reader.raw = replace(reader.raw, bag_items=((3, 12), (3, 1)))
    else:
        reader.raw = replace(reader.raw, bag_items=((3, 0),))
    with pytest.raises(RedSuperRodSupportError):
        observe_red_super_rod_support(reader)


def test_executor_verifies_gift_and_settles_dialogue_without_learning():
    reader, emulator = _Reader(), _Emulator()
    delegate = _GiftActions(reader, emulator)
    result = RedSuperRodSupportExecutor(
        CountingExecutor(delegate), reader, emulator
    ).execute()
    assert delegate.kinds == [
        MacroActionKind.INTERACT,
        MacroActionKind.CONFIRM,
        MacroActionKind.CONFIRM,
        MacroActionKind.CONFIRM,
    ]
    assert result.actions == 4 and result.frames == 96
    assert result.public_dict()["training_examples"] == 0
    assert result.public_dict()["learned_goal_authority"] is False


@pytest.mark.parametrize("mutation", ["party", "money", "bad_item", "bad_bit"])
def test_executor_rejects_each_invalid_transition(mutation):
    reader, emulator = _Reader(), _Emulator()
    delegate = _GiftActions(reader, emulator, acquire_on=2, settle_on=3)
    original_execute = delegate.execute

    def execute(action):
        original_execute(action)
        if delegate.count != 2:
            return
        if mutation == "party":
            reader.raw = replace(reader.raw, party_hp=(199, 80))
        elif mutation == "money":
            reader.raw = replace(reader.raw, player_money=57)
        elif mutation == "bad_item":
            reader.raw = replace(reader.raw, bag_items=((3, 12), (0x4E, 2)))
        else:
            reader.raw = replace(reader.raw, status_flags_1=0)

    delegate.execute = execute
    with pytest.raises(RedSuperRodSupportError):
        RedSuperRodSupportExecutor(CountingExecutor(delegate), reader, emulator).execute()


def test_executor_refuses_to_guess_after_dialogue_disappears_or_bound_expires():
    reader, emulator = _Reader(), _Emulator()
    vanished = _GiftActions(reader, emulator, acquire_on=99, settle_on=1)
    with pytest.raises(RedSuperRodSupportError, match="left its dialogue"):
        RedSuperRodSupportExecutor(CountingExecutor(vanished), reader, emulator).execute()

    reader, emulator = _Reader(), _Emulator()
    stalled = _GiftActions(reader, emulator, acquire_on=99, settle_on=99)
    with pytest.raises(RedSuperRodSupportError, match="confirmation bound"):
        RedSuperRodSupportExecutor(
            CountingExecutor(stalled), reader, emulator, maximum_confirm_pulses=2
        ).execute()
