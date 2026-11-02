from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

import pokemon_red_completion.red_npc_trade as module
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.collection import CollectionLocation as Location
from pokemon_red_completion.collection import LivingSpecimen
from pokemon_red_completion.observation import PokemonRedStateReader, RamAddress, RawGameState
from pokemon_red_completion.party import PartyMemberObservation, PartyObservation, StatusCondition
from pokemon_red_completion.red_collection import red_species_ref as ref

TRADE = module.RedNPCTrade(1, 63, 122, 48, 2, 55, (1, 4), 2, 58)


def observation(traded=False):
    # Preserve duplicate stock; neither sets nor registration counts suffice.
    specimens = tuple(LivingSpecimen(ref(1), 30, Location.BOX, 2, i) for i in range(2))
    specimens += (LivingSpecimen(ref(122 if traded else 63), 10, Location.PARTY),)
    return NS(
        raw=RawGameState(True, 48, 4, 2, 1, 0, player_money=1000, bag_items=((3, 6),)),
        input_ready=True,
        collection_observation=NS(
            specimens=specimens,
            owned_species=frozenset({ref(1), ref(63)} | ({ref(122)} if traded else set())),
        ),
    )


@pytest.mark.parametrize(
    "damage",
    [
        None,
        "flag_only",
        "no_flag",
        "reused",
        "extra_flag",
        "level",
        "missing_duplicate",
        "extra_mon",
        "owned_lost",
        "extra_owned",
        "money",
        "bag",
        "battle",
        "not_ready",
        "wrong_map",
        "protected",
    ],
)
def test_exact_exchange_not_just_new_registration(damage):
    before, after = observation(), observation(True)
    flags_before, flags_after, protected = frozenset({4}), frozenset({1, 4}), {ref(1): 2}
    c = after.collection_observation
    if damage == "flag_only":
        c.specimens = before.collection_observation.specimens
    elif damage == "no_flag":
        flags_after = flags_before
    elif damage == "reused":
        flags_before = flags_after
    elif damage == "extra_flag":
        flags_after |= {6}
    elif damage == "level":
        c.specimens = (*c.specimens[:-1], replace(c.specimens[-1], level=11))
    elif damage == "missing_duplicate":
        c.specimens = c.specimens[1:]
    elif damage == "extra_mon":
        c.specimens += (c.specimens[-1],)
    elif damage == "owned_lost":
        c.owned_species -= {ref(63)}
    elif damage == "extra_owned":
        c.owned_species |= {ref(150)}
    elif damage == "money":
        after.raw = replace(after.raw, player_money=999)
    elif damage == "bag":
        after.raw = replace(after.raw, bag_items=())
    elif damage == "battle":
        after.raw = replace(after.raw, battle_state=1)
    elif damage == "not_ready":
        after.input_ready = False
    elif damage == "wrong_map":
        after.raw = replace(after.raw, map_id=49)
    elif damage == "protected":
        protected[ref(63)] = 1
    assert module.verify_npc_exchange(
        before,
        after,
        TRADE,
        level=10,
        flags_before=flags_before,
        flags_after=flags_after,
        protected=protected,
    ) is (damage is None)


def test_completed_trade_observer_reads_both_native_bytes():
    reads = []

    def read(at):
        reads.append(at)
        return {int(RamAddress.NPC_TRADE_FLAGS): 2, int(RamAddress.NPC_TRADE_FLAGS) + 1: 2}[at]

    assert PokemonRedStateReader(NS(read_u8=read)).read_completed_npc_trades() == {1, 9}
    assert reads == [RamAddress.NPC_TRADE_FLAGS, int(RamAddress.NPC_TRADE_FLAGS) + 1]


@pytest.mark.parametrize(
    "phase,active,battle,expected",
    [
        ("offer", True, 0, ("offer", 0)),
        ("party", True, 0, ("party", 0)),
        ("party", False, 0, None),
        ("offer", False, 0, None),
        ("party", True, 1, None),
        ("other", True, 0, None),
    ],
)
def test_observed_input_requires_rendered_live_cursor(phase, active, battle, expected):
    base = int(RamAddress.TILE_MAP)
    menu = (8, 15, 1) if phase == "offer" else (1, 0, 1)
    memory = {
        RamAddress.IS_IN_BATTLE: battle,
        RamAddress.PARTY_COUNT: 2,
        RamAddress.TOP_MENU_ITEM_Y: menu[0],
        RamAddress.TOP_MENU_ITEM_X: menu[1],
        RamAddress.MAX_MENU_ITEM: menu[2],
        RamAddress.CURRENT_MENU_ITEM: 0,
        RamAddress.MENU_CURSOR_LOCATION: base & 255,
        int(RamAddress.MENU_CURSOR_LOCATION) + 1: base >> 8,
        base: 0xED if active else 0,
    }
    text = "YES NO" if phase == "offer" else "Choose a MON" if phase == "party" else "Stats"
    for i, char in enumerate(text):
        memory[base + 260 + i] = (
            ord(char) - ord("A") + 0x80
            if char.isupper()
            else (ord(char) - ord("a") + 0xA0 if char.islower() else 0x7F)
        )
    assert (
        PokemonRedStateReader(NS(read_u8=lambda at: memory.get(at, 0))).read_npc_trade_input()
        == expected
    )


def member(slot, species):
    return PartyMemberObservation(
        slot=slot,
        species_id=species,
        level=10,
        hp=20,
        max_hp=20,
        status=StatusCondition.HEALTHY,
        moves=(),
    )


class TradePort:
    def __init__(self, damage=None):
        self.damage = damage
        self.phase = "field"
        self.cursor = 0
        self.members = (member(1, 1), member(2, 148))
        self.flags = frozenset({4})
        self.actions = []

    def read(self):
        return observation().raw

    def read_input_readiness(self):
        return NS(ready=self.phase in {"field", "done"})

    def read_bottom_dialogue_box_visible(self):
        return self.phase in {"text", "thanks"}

    def read_pending_trainer_battle_identity(self):
        return None

    def read_completed_npc_trades(self):
        return self.flags

    def read_current_map_objects(self):
        return (NS(sprite_index=2, picture_id=55, at=TRADE.at),)

    def read_player_facing(self):
        return "up"

    def read_npc_trade_input(self):
        return (self.phase, self.cursor) if self.phase in {"party", "offer"} else None

    def execute(self, action):
        self.actions.append(action)
        if action.kind is MacroActionKind.INTERACT:
            self.phase = "text"
        elif action.kind is MacroActionKind.CANCEL:
            self.phase = "offer" if self.phase == "text" else "done"
        elif action.kind is MacroActionKind.MOVE:
            self.cursor += 1 if action.value == "down" else -1
        elif action.kind is MacroActionKind.CONFIRM:
            if self.phase == "offer":
                self.phase = "party"
            elif self.phase == "party":
                assert self.cursor == 1
                self.phase = "thanks"
                self.flags |= {1}
                if self.damage != "flag_only":
                    self.members = (self.members[0], member(2, 42))
                    if self.damage == "other_party":
                        self.members = (replace(self.members[0], hp=19), self.members[1])


@pytest.mark.parametrize("damage", [None, "flag_only", "other_party", "wrong_source"])
def test_observed_dialogue_selects_exact_party_slot_and_proves_exchange(damage):
    port = TradePort(damage)
    kwargs = dict(
        source_slot=2,
        source_species_id=99 if damage == "wrong_source" else 148,
        target_species_id=42,
    )
    party = NS(read=lambda: PartyObservation(port.members))
    if damage:
        with pytest.raises(module.RedNPCTradeError):
            module.execute_adjacent_trade(port, port, party, TRADE, **kwargs)
        if damage == "wrong_source":
            assert not port.actions
    else:
        receipt = module.execute_adjacent_trade(port, port, party, TRADE, **kwargs)
        assert receipt["source_slot"] == 2 and receipt["received_level"] == 10


def test_cartridge_offer_rejects_changed_script(monkeypatch):
    from pokemon_red_completion.gen1_acquisition import MapObject
    from pokemon_red_completion.gen1_maps import MAP_HEADER_BANKS, MAP_HEADER_POINTERS

    rom = bytearray(0x10000)
    objects = {}
    for offset, (map_id, index) in enumerate(((48, 1), (63, 6))):
        header = 0x4000 + offset * 100
        text, script = header + 20, header + 30
        rom[MAP_HEADER_BANKS + map_id] = 1
        rom[MAP_HEADER_POINTERS + 2 * map_id : MAP_HEADER_POINTERS + 2 * map_id + 2] = (
            header.to_bytes(2, "little")
        )
        rom[header + 5 : header + 7] = text.to_bytes(2, "little")
        rom[text + 2 : text + 4] = script.to_bytes(2, "little")
        rom[script : script + 14] = bytes((8, 62, index)) + bytes.fromhex("ea3dcd3e54cd6d3ec3d724")
        objects[map_id] = (MapObject(map_id, 55, 1, 4, 255, 208, 2),)
    monkeypatch.setattr(module, "map_objects", lambda _: objects)
    monkeypatch.setattr(
        module,
        "in_game_trades",
        lambda _: tuple(NS(give_species=63, get_species=122) for _ in range(10)),
    )
    assert [t.index for t in module.stationary_npc_trades(bytes(rom))] == [1, 6]
    rom[0x4000 + 32] = 2
    with pytest.raises(module.CartridgeReadError):
        module.stationary_npc_trades(bytes(rom))
