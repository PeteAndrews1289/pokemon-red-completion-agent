from dataclasses import replace

import pytest
from test_gen1_route_runtime import FakeReader, raw, reader_as_real

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.gen1_route_runtime import (
    Gen1RouteInterruptionHandler,
    Gen1TraversalObserver,
    Gen1WildFleeHandler,
)
from pokemon_red_completion.observation import EventFlag, InputReadiness, MapId
from pokemon_red_completion.route_executor import RouteExecutionError, TraversalSnapshot


def flags(*events):
    result = bytearray(320)
    for event in events:
        result[int(event) // 8] |= 1 << (int(event) % 8)
    return bytes(result)


INITIAL = (EventFlag.GOT_HM01, EventFlag.RUBBED_CAPTAINS_BACK, EventFlag.SS_ANNE_LEFT)
FINISHED = INITIAL + (
    EventFlag.STARTED_WALKING_OUT_OF_DOCK,
    EventFlag.WALKED_PAST_GUARD_AFTER_SS_ANNE_LEFT,
)


def setup(fault=None):
    state = replace(raw(), map_id=MapId.VERMILION_DOCK, player_x=14, player_y=2,
                    event_flags=flags(*INITIAL), party_species_ids=(28,), party_levels=(36,),
                    party_hp=(40,), party_max_hp=(90,), party_stats=((60, 60, 60, 60),),
                    party_status=(0,), party_moves=((33, 0, 0, 0),),
                    party_pp=((10, 0, 0, 0),), player_money=7084, badge_bits=3)
    reader = FakeReader(state, ready=False)
    actions = []
    reader.read_input_readiness = lambda: InputReadiness(
        joy_ignore=0 if reader.ready else 255, simulated_joypad_index=0,
        npc_movement_script_table=0, player_moving_direction=0 if reader.ready else 8,
        status_flags_5=0, movement_flags=0 if reader.ready else 4,
    )
    reader.read_all_box_states = lambda: ("changed",) if fault == "boxes" and actions else ()
    reader.read_pokedex_state = lambda: ("changed",) if fault == "dex" and actions else ()

    class Port:
        def execute(self, action):
            actions.append(action)
            assert action.kind is MacroActionKind.WAIT and action.repeat == 96
            if fault == "stays_locked" or len(actions) < 2:
                return action
            reader.ready = True
            reader.raw = replace(reader.raw, map_id=MapId.VERMILION_CITY,
                                 player_y=29, player_x=18, event_flags=flags(*FINISHED))
            changes = {
                "cash": dict(player_money=7083), "hp": dict(party_hp=(39,)),
                "pp": dict(party_pp=((9, 0, 0, 0),)),
                "stats": dict(party_stats=((61, 60, 60, 60),)),
                "species": dict(party_species_ids=(150,)), "level": dict(party_levels=(37,)),
                "bag": dict(bag_items=((4, 1),)), "badge": dict(badge_bits=7),
                "events": dict(event_flags=flags(*FINISHED, 200)),
                "cleared_event": dict(event_flags=flags(*FINISHED[1:])),
                "incomplete_events": dict(event_flags=flags(*INITIAL)),
                "landing": dict(player_x=19), "battle": dict(battle_state=1),
            }
            if fault in changes:
                reader.raw = replace(reader.raw, **changes[fault])
            reader.dialogue_visible = fault == "dialogue"
            reader.trainer_engagement = fault == "trainer"
            return action

    port = Port()
    handler = Gen1WildFleeHandler(port, reader_as_real(reader), maximum_flees=0,
                                 stabilization_frames=24)
    observed = TraversalSnapshot(MapId.VERMILION_DOCK, (2, 14), False,
                                 "native_ship_departure", mode="land")
    return reader, port, handler, observed, actions


@pytest.mark.parametrize("fault", [None, "map", "tile", "cut", "rubbed", "left",
                                  "already_passed", "already_walked", "truncated",
                                  "battle", "dialogue", "trainer", "ready", "wrong_lock"])
def test_observer_only_identifies_the_native_unready_departure(fault):
    reader, _, handler, observed, actions = setup()
    changes = {
        "map": dict(map_id=MapId.VERMILION_CITY), "tile": dict(player_y=3),
        "cut": dict(event_flags=flags(*INITIAL[1:])),
        "rubbed": dict(event_flags=flags(INITIAL[0], INITIAL[2])),
        "left": dict(event_flags=flags(*INITIAL[:2])),
        "already_passed": dict(event_flags=flags(*INITIAL, FINISHED[-1])),
        "already_walked": dict(event_flags=flags(*INITIAL, EventFlag.WALKED_OUT_OF_DOCK)),
        "truncated": dict(event_flags=b""), "battle": dict(battle_state=1),
    }
    if fault in changes:
        reader.raw = replace(reader.raw, **changes[fault])
    reader.dialogue_visible, reader.trainer_engagement = fault == "dialogue", fault == "trainer"
    reader.ready = fault == "ready"
    if fault == "wrong_lock":
        reader.read_input_readiness = lambda: InputReadiness(1, 0, 0, 0, 0)
    actual = Gen1TraversalObserver(reader_as_real(reader)).observe()
    assert (actual.interruption == "native_ship_departure") is (fault is None)
    if fault:
        with pytest.raises(RouteExecutionError):
            handler.handle(observed)
        assert not actions
    else:
        assert not actual.ready and reader.occupancy_reads == 0


@pytest.mark.parametrize("fault", [None, "cash", "hp", "pp", "stats", "species", "level",
                                  "bag", "badge", "events", "cleared_event", "incomplete_events",
                                  "boxes", "dex", "landing", "battle", "dialogue", "trainer",
                                  "stays_locked"])
def test_native_ship_wait_requires_exact_landing_and_unchanged_resources(fault):
    reader, _, handler, observed, actions = setup(fault)
    if fault:
        with pytest.raises(RouteExecutionError):
            handler.handle(observed)
        assert len(actions) <= 32
        assert not handler.ship_departure_evidence
    else:
        receipt = handler.handle(observed)
        assert receipt.resumed_map == MapId.VERMILION_CITY and receipt.resumed_at == (29, 18)
        assert receipt.allows_relocation and receipt.allows_map_transition
        assert receipt.details["verified"] and receipt.details["model_queries"] == 0
        assert receipt.details["wait_actions"] == len(actions) == 2
        assert receipt.details["protected_resources_unchanged"]
        assert not handler.evidence
        with pytest.raises(RouteExecutionError):
            handler.handle(observed)
        assert len(actions) == 2
        assert Gen1TraversalObserver(reader_as_real(reader)).observe().ready


def test_combined_handler_reuses_the_same_wait_only_departure_guard():
    reader, port, _, observed, actions = setup()
    handler = Gen1RouteInterruptionHandler(port, reader_as_real(reader), maximum_flees=0,
                                          maximum_trainer_battles=0, stabilization_frames=24)
    receipt = handler.handle(observed)
    assert receipt.allows_map_transition and len(actions) == 2
    assert "native_ship_departure" in handler.handled_interruption_kinds
    assert not handler.trainer_evidence and not handler.scripted_dialogue_evidence


def test_ship_wait_rejects_unknown_party_evidence_before_input():
    reader, _, handler, observed, actions = setup()
    reader.raw = replace(reader.raw, party_stats=None)
    with pytest.raises(RouteExecutionError, match="resources are unavailable"):
        handler.handle(observed)
    assert not actions


@pytest.mark.parametrize("intermediate_y,early_ready", [(31, False), (30, False),
                                                      (31, True), (30, True),
                                                      (32, False), (28, False)])
def test_native_city_walk_only_accepts_its_final_ready_endpoint(intermediate_y, early_ready):
    reader, port, handler, observed, actions = setup()
    original_execute = port.execute

    def execute(action):
        returned = original_execute(action)
        if len(actions) == 1:
            reader.raw = replace(reader.raw, map_id=MapId.VERMILION_CITY,
                                 player_y=intermediate_y, player_x=18,
                                 event_flags=flags(*FINISHED))
            reader.ready = early_ready
        return returned

    port.execute = execute
    if intermediate_y in {30, 31} and not early_ready:
        receipt = handler.handle(observed)
        assert receipt.resumed_at == (29, 18) and len(actions) == 2
    else:
        with pytest.raises(RouteExecutionError):
            handler.handle(observed)
        assert len(actions) == 1


@pytest.mark.parametrize("fault", [None, "ready", "lock", "script_flag", "movement_flag",
                                  "direction", "joypad", "started", "guard", "coordinate"])
def test_half_loaded_native_warp_requires_its_exact_locked_script_boundary(fault):
    reader, port, handler, observed, actions = setup()
    execute0, readiness0 = port.execute, reader.read_input_readiness

    def readiness():
        value = readiness0()
        if len(actions) != 1:
            return value
        value = replace(value, status_flags_5=128)
        changes = {"lock": dict(joy_ignore=1), "script_flag": dict(status_flags_5=0),
                   "movement_flag": dict(movement_flags=0),
                   "direction": dict(player_moving_direction=4),
                   "joypad": dict(simulated_joypad_index=1)}
        return replace(value, **changes.get(fault, {}))

    def execute(action):
        returned = execute0(action)
        if len(actions) == 1:
            reader.raw = replace(reader.raw, map_id=MapId.VERMILION_CITY,
                                 player_y=0, player_x=14,
                                 event_flags=flags(*INITIAL, EventFlag.STARTED_WALKING_OUT_OF_DOCK))
            reader.ready = fault == "ready"
            if fault == "started":
                reader.raw = replace(reader.raw, event_flags=flags(*INITIAL))
            if fault == "guard":
                reader.raw = replace(reader.raw, event_flags=flags(*FINISHED))
            if fault == "coordinate":
                reader.raw = replace(reader.raw, player_x=13)
        return returned

    port.execute, reader.read_input_readiness = execute, readiness
    if fault is None:
        receipt = handler.handle(observed)
        assert receipt.resumed_at == (29, 18) and len(actions) == 2
    else:
        with pytest.raises(RouteExecutionError):
            handler.handle(observed)
        assert len(actions) == 1
