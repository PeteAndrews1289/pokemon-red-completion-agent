from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from test_red_npc_trade import TRADE, TradePort

import pokemon_red_completion.red_npc_trade as trade_module
import pokemon_red_completion.red_npc_trade_options as options
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.observation import PokemonRedStateReader, RamAddress
from pokemon_red_completion.party import PartyObservation
from pokemon_red_completion.route_executor import TraversalSnapshot


@pytest.mark.parametrize("damage", [None, "party", "flag", "new_offer", "never_closes"])
def test_trade_settlement_waits_through_delayed_closing_text(damage):
    port = TradePort()
    port.phase = "done"
    port.flags = frozenset({1, 4})
    party = NS(read=lambda: PartyObservation(port.members))
    actions = []

    def execute(action):
        actions.append(action)
        if len(actions) == 1:
            port.phase = "thanks"
            if damage == "party":
                port.members = port.members[:-1]
            elif damage == "flag":
                port.flags |= {5}
            elif damage == "new_offer":
                port.read_npc_trade_input = lambda: ("offer", 0)
        elif action.kind is MacroActionKind.CANCEL and damage != "never_closes":
            port.phase = "done"

    if damage:
        with pytest.raises(trade_module.RedNPCTradeError):
            trade_module.settle_completed_trade(
                NS(execute=execute), port, party, trade_index=1, maximum_pulses=4
            )
    else:
        trade_module.settle_completed_trade(NS(execute=execute), port, party, trade_index=1)
        assert len(actions) == 4 and actions[1].kind is MacroActionKind.CANCEL
    assert all(a.kind in {MacroActionKind.WAIT, MacroActionKind.CANCEL} for a in actions)


def test_moving_decoder_authenticates_script_and_object(monkeypatch):
    from pokemon_red_completion.gen1_acquisition import MapObject
    from pokemon_red_completion.gen1_maps import MAP_HEADER_BANKS, MAP_HEADER_POINTERS

    rom = bytearray(0x10000)
    map_id, header, texts, script = 0xBF, 0x4000, 0x4020, 0x4030
    rom[MAP_HEADER_BANKS + map_id] = 1
    rom[MAP_HEADER_POINTERS + 2 * map_id : MAP_HEADER_POINTERS + 2 * map_id + 2] = header.to_bytes(
        2, "little"
    )
    rom[header + 5 : header + 7] = texts.to_bytes(2, "little")
    rom[texts : texts + 2] = script.to_bytes(2, "little")
    code = bytes((8, 62, 5)) + bytes.fromhex("ea3dcd3e54cd6d3ec3d724")
    rom[script : script + len(code)] = code
    obj = MapObject(map_id, 4, 2, 4, 254, 2, 1)
    monkeypatch.setattr(trade_module, "map_objects", lambda _: {map_id: (obj,)})
    monkeypatch.setattr(
        trade_module, "in_game_trades", lambda _: (NS(give_species=80, get_species=108),) * 10
    )
    (trade,) = trade_module.moving_npc_trades(bytes(rom))
    assert (trade.index, trade.give, trade.receive, trade.roaming) == (5, 80, 108, True)
    assert trade.at == (2, 4) and trade.sprite_index == 1
    monkeypatch.setattr(
        trade_module, "map_objects", lambda _: {map_id: (replace(obj, movement=255),)}
    )
    with pytest.raises(trade_module.CartridgeReadError, match="object"):
        trade_module.moving_npc_trades(bytes(rom))
    rom[script + 2] = 6
    with pytest.raises(trade_module.CartridgeReadError, match="script"):
        trade_module.moving_npc_trades(bytes(rom))


@pytest.mark.parametrize(
    "index,phase,expected", [(5, ("offer", 0), 5), (10, ("offer", 0), None), (5, None, None)]
)
def test_active_identity_requires_live_menu(monkeypatch, index, phase, expected):
    reader = PokemonRedStateReader(
        NS(read_u8=lambda address: index if address == RamAddress.NPC_TRADE_INDEX else 0)
    )
    monkeypatch.setattr(reader, "read_npc_trade_input", lambda: phase)
    assert reader.read_active_npc_trade_index() == expected


@pytest.mark.parametrize("identity", [1, 6, None])
def test_moving_trade_checks_actual_offer_before_accepting(identity):
    port = TradePort()
    port.read_current_map_objects = lambda: (
        NS(sprite_index=2, picture_id=55, at=TRADE.at, visible=True, moving=False),
    )
    port.read_active_npc_trade_index = lambda: identity
    party = NS(read=lambda: PartyObservation(port.members))
    if identity == 1:
        result = trade_module.execute_adjacent_trade(
            port,
            port,
            party,
            replace(TRADE, roaming=True),
            source_slot=2,
            source_species_id=148,
            target_species_id=42,
        )
        assert result["offer_accepted"]
    else:
        with pytest.raises(trade_module.RedNPCTradeError, match="active trade offer"):
            trade_module.execute_adjacent_trade(
                port,
                port,
                party,
                replace(TRADE, roaming=True),
                source_slot=2,
                source_species_id=148,
                target_species_id=42,
            )
        assert not any(a.kind is MacroActionKind.CONFIRM for a in port.actions)
        assert port.flags == frozenset({4})


@pytest.mark.parametrize("fault", ["wrong_sprite", "absent", "duplicate", "invisible", "moving"])
def test_identity_rejects_without_input(fault):
    port = TradePort()
    obj = NS(sprite_index=2, picture_id=55, at=TRADE.at, visible=True, moving=False)
    if fault == "wrong_sprite":
        obj.picture_id = 56
    if fault == "invisible":
        obj.visible = False
    if fault == "moving":
        obj.moving = True
    port.read_current_map_objects = lambda: (
        () if fault == "absent" else (obj, obj) if fault == "duplicate" else (obj,)
    )
    with pytest.raises(trade_module.RedNPCTradeError):
        trade_module.execute_adjacent_trade(
            port,
            port,
            NS(read=lambda: PartyObservation(port.members)),
            replace(TRADE, roaming=True),
            source_slot=2,
            source_species_id=148,
            target_species_id=42,
        )
    assert not port.actions


def approach_fixture(monkeypatch):
    w = NS(
        at=(4, 4),
        npc=(1, 4),
        moving=False,
        facing="up",
        steps=0,
        actions=[],
        route_targets=[],
        map_id=48,
    )
    reader = NS(
        read=lambda: NS(map_id=w.map_id),
        read_bottom_dialogue_box_visible=lambda: False,
        read_player_facing=lambda: w.facing,
        read_current_map_objects=lambda: (
            NS(sprite_index=2, picture_id=55, at=w.npc, visible=True, moving=w.moving),
        ),
    )
    observer = NS(observe=lambda: TraversalSnapshot(w.map_id, w.at, True, mode="land"))
    world = NS(with_current_observation=lambda _: world)

    def plan(world, start, trade):
        w.route_targets.append(trade.at)
        return NS(steps=(1,), terminal_at=(trade.at[0] + 1, trade.at[1]))

    monkeypatch.setattr(options, "_approach", plan)

    def route(p):
        w.at = p.terminal_at
        w.steps += 1
        if w.steps == 1:
            w.npc = (1, 5)
        return 1

    def action(a):
        w.actions.append(a)
        if a.kind is MacroActionKind.MOVE:
            w.facing = a.value

    return w, NS(execute=action), reader, observer, world, route


def test_live_approach_replans_after_npc_moves(monkeypatch):
    w, actions, reader, observer, world, route = approach_fixture(monkeypatch)
    bound, steps = options._moving_approach(
        actions, reader, observer, world, replace(TRADE, roaming=True), route
    )
    assert w.route_targets == [(1, 4), (1, 5)] and steps == 2
    assert bound.at == (1, 5) and bound.index == TRADE.index
    assert not any(a.kind is MacroActionKind.INTERACT for a in w.actions)


def test_offscreen_present_npc_can_be_approached_but_not_interacted_with(monkeypatch):
    w, actions, reader, observer, world, route = approach_fixture(monkeypatch)
    reader.read_current_map_objects = lambda: (
        NS(sprite_index=2, picture_id=55, at=w.npc, moving=False, visible=w.steps > 0),
    )
    bound, steps = options._moving_approach(actions, reader, observer, world, TRADE, route)
    assert steps == 2 and bound.at == w.npc


def test_moving_approach_stops_under_its_wait_budget(monkeypatch):
    w, actions, reader, observer, world, route = approach_fixture(monkeypatch)
    w.moving = True
    with pytest.raises(trade_module.RedNPCTradeError, match="budget"):
        options._moving_approach(actions, reader, observer, world, TRADE, route, maximum_attempts=3)
    assert len(w.actions) == 3 and not w.route_targets


def test_turn_reobserves_both_actors_instead_of_using_stale_facing(monkeypatch):
    w, actions, reader, observer, world, route = approach_fixture(monkeypatch)
    w.at = (2, 4)
    w.facing = "left"
    original = actions.execute

    def move(a):
        original(a)
        if a.kind is MacroActionKind.MOVE:
            w.npc = (1, 5)
            w.at = (1, 4)

    actions.execute = move
    # Both actors moving on every turn must exhaust,not interact with a guessed tile.
    with pytest.raises(trade_module.RedNPCTradeError, match="budget"):
        options._moving_approach(actions, reader, observer, world, TRADE, route, maximum_attempts=1)
    assert not any(a.kind is MacroActionKind.INTERACT for a in w.actions)
