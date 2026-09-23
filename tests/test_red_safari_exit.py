from dataclasses import replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.global_router import MacroEdge, MacroPath, MacroTransition
from pokemon_red_completion.local_router import LocalEdge, LocalPath
from pokemon_red_completion.observation import (
    EventFlag,
    InputReadiness,
    MapId,
    MenuCursorState,
    RawGameState,
)
from pokemon_red_completion.red_safari_exit import (
    RedSafariDepartureInterruptionHandler,
    RedSafariExitDialogueHandler,
    normalize_active_safari_exit_plan,
    safari_departure_within_steps,
)
from pokemon_red_completion.route_executor import (
    InterruptionReceipt,
    RouteExecutionError,
    TraversalSnapshot,
)
from pokemon_red_completion.route_plan import RoutePlan, RouteSegment


@pytest.mark.parametrize("remaining,expected", [(19, False), (20, True), (0, False)])
def test_departure_respects_paid_step_budget_and_escape_headroom(remaining, expected):
    reader = SimpleNamespace(read_safari_session_state=lambda: SimpleNamespace(
        in_safari_zone=True, safari_game_over=False, safari_steps=remaining))
    plan = SimpleNamespace(steps=tuple(SimpleNamespace(source_map=m) for m in
                                     (220, 220, 220, int(MapId.SAFARI_ZONE_GATE), 7)))
    assert safari_departure_within_steps(plan, reader) is expected


def test_departure_recovery_selects_safari_run_only_inside_paid_session():
    active = [True]
    reader = SimpleNamespace(read_safari_session_state=lambda: SimpleNamespace(
        in_safari_zone=active[0]))
    calls = []
    fallback = SimpleNamespace(handle=lambda event: calls.append("ordinary"))
    handler = RedSafariDepartureInterruptionHandler(object(), object(), reader, fallback)
    handler.safari_handler = SimpleNamespace(handle=lambda event: calls.append("safari_run"))
    wild = SimpleNamespace(interruption="wild_battle")
    handler.handle(wild)
    handler.handle(SimpleNamespace(interruption="scripted_dialogue"))
    active[0] = False
    handler.handle(wild)
    assert calls == ["safari_run", "ordinary", "ordinary"]


def _with_event(flags: bytes, event: EventFlag, enabled: bool) -> bytes:
    result = bytearray(flags)
    byte_index, bit_index = divmod(int(event), 8)
    if enabled:
        result[byte_index] |= 1 << bit_index
    else:
        result[byte_index] &= ~(1 << bit_index)
    return bytes(result)


def _safari_raw(**changes) -> RawGameState:
    flags = _with_event(bytes(320), EventFlag.IN_SAFARI_ZONE, True)
    raw = RawGameState(
        game_started=True,
        map_id=int(MapId.SAFARI_ZONE_GATE),
        player_x=3,
        player_y=0,
        party_count=2,
        battle_state=0,
        badge_bits=0xFF,
        bag_item_ids=(3,),
        bag_items=((3, 12),),
        event_flags=flags,
        party_species_ids=(9, 25),
        party_levels=(70, 30),
        party_hp=(200, 80),
        party_max_hp=(200, 80),
        party_status=(0, 0),
        party_moves=((1, 2, 3, 4), (5, 6, 7, 8)),
        party_pp=((10, 10, 10, 10), (10, 10, 10, 10)),
        player_money=206,
        status_flags_1=0,
    )
    return replace(raw, **changes)


class SafariReader:
    def __init__(self):
        self.raw = _safari_raw()
        self.ready = False
        self.dialogue = True
        self.menu = MenuCursorState(1, 0, 1, 14, 7)
        self.dex = "dex"
        self.boxes = "boxes"
        self.box_moves = tuple((index,) for index in range(12))

    def read(self):
        return self.raw

    def read_input_readiness(self):
        return InputReadiness(0 if self.ready else 1, 0, 0, 0, 0)

    def read_bottom_dialogue_box_visible(self):
        return self.dialogue

    def read_menu_cursor_state(self):
        return self.menu

    def read_pokedex_state(self):
        return self.dex

    def read_all_box_states(self):
        return self.boxes

    def read_box_move_members(self, index):
        return self.box_moves[index]


class SafariActions:
    def __init__(self, reader, *, fault=None):
        self.reader = reader
        self.fault = fault
        self.actions = []
        self.confirms = 0

    def execute(self, action):
        self.actions.append((action.kind, action.value, action.repeat))
        if action.kind is MacroActionKind.MOVE and action.value == "up":
            self.reader.menu = replace(self.reader.menu, selected_visible_index=0)
        elif action.kind is MacroActionKind.CONFIRM:
            self.confirms += 1
            if self.fault == "collection" and self.confirms == 1:
                self.reader.dex = "changed"
            elif self.fault in {"party", "money"} and self.confirms == 1:
                field = "party_hp" if self.fault == "party" else "player_money"
                value = (199, 80) if self.fault == "party" else 207
                self.reader.raw = replace(self.reader.raw, **{field: value})
            if self.fault == "never_settles":
                return
            if self.confirms == 1:
                self.reader.raw = replace(
                    self.reader.raw,
                    event_flags=_with_event(
                        self.reader.raw.event_flags,
                        EventFlag.IN_SAFARI_ZONE,
                        False,
                    ),
                )
            elif self.confirms == 2:
                y = 2 if self.fault == "wrong_landing" else 3
                self.reader.raw = replace(self.reader.raw, player_y=y)
                self.reader.dialogue = False
                self.reader.ready = True
        return action


class Fallback:
    handled_hazard_kinds = frozenset({"trainer_sight"})
    handled_interruption_kinds = frozenset({"wild_battle"})

    def __init__(self):
        self.calls = []

    def handle(self, interruption):
        self.calls.append(interruption)
        return InterruptionReceipt("scripted_dialogue", interruption.map_id, interruption.at)


def _handler(*, fault=None, settle_limit=16):
    reader = SafariReader()
    actions = SafariActions(reader, fault=fault)
    fallback = Fallback()
    handler = RedSafariExitDialogueHandler(
        actions, reader, fallback, settle_limit=settle_limit
    )
    interruption = TraversalSnapshot(
        int(MapId.SAFARI_ZONE_GATE), (0, 3), False, "scripted_dialogue"
    )
    return SimpleNamespace(
        reader=reader,
        actions=actions,
        fallback=fallback,
        handler=handler,
        interruption=interruption,
    )


def _safari_plan(*, lane=3):
    source_x = lane + 11
    first = RouteSegment(
        int(MapId.SAFARI_ZONE_CENTER),
        int(MapId.SAFARI_ZONE_GATE),
        LocalPath(((25, source_x),), (), ("land",)),
        MacroTransition((25, source_x), (0, lane), "down"),
        "warp",
        False,
    )
    coordinates = tuple((y, lane) for y in range(6))
    second = RouteSegment(
        int(MapId.SAFARI_ZONE_GATE),
        int(MapId.FUCHSIA_CITY),
        LocalPath(
            coordinates,
            tuple(LocalEdge((y, lane), "down") for y in range(1, 6)),
            ("land",) * 6,
        ),
        MacroTransition((5, lane), (4, 18), "down"),
        "connection",
        False,
    )
    return RoutePlan(
        MacroPath(
            (
                int(MapId.SAFARI_ZONE_CENTER),
                int(MapId.SAFARI_ZONE_GATE),
                int(MapId.FUCHSIA_CITY),
            ),
            (MacroEdge(int(MapId.SAFARI_ZONE_GATE)), MacroEdge(int(MapId.FUCHSIA_CITY))),
        ),
        (25, source_x),
        "land",
        (first, second),
        None,
        (4, 18),
        "land",
    )


def test_normalizer_accounts_for_the_scripted_three_step_gate_walk():
    original = _safari_plan()
    normalized = normalize_active_safari_exit_plan(original)

    assert normalized is not None
    assert normalized.segments[0].transition.arrival_at == (3, 3)
    assert normalized.segments[1].approach.coordinates == ((3, 3), (4, 3), (5, 3))
    assert len(normalized.steps) == len(original.steps) - 3
    assert normalized.terminal_at == original.terminal_at


def test_normalizer_rejects_an_unrecognized_gate_lane():
    with pytest.raises(RouteExecutionError, match="unsupported gate boundary"):
        normalize_active_safari_exit_plan(_safari_plan(lane=2))


def test_active_safari_dialogue_selects_yes_and_verifies_the_settled_lane():
    scene = _handler()
    receipt = scene.handler.handle(scene.interruption)

    assert receipt.resumed_at == (3, 3)
    assert receipt.details == {
        "semantic": "active_safari_exit",
        "confirm_pulses": 2,
        "selection_moves": 1,
        "safari_events_cleared": True,
        "verified": True,
    }
    assert [kind for kind, _value, _repeat in scene.actions.actions] == [
        MacroActionKind.MOVE,
        MacroActionKind.CONFIRM,
        MacroActionKind.CONFIRM,
    ]
    assert scene.fallback.calls == []


def test_non_safari_dialogue_keeps_the_generic_cancel_handler():
    scene = _handler()
    scene.reader.raw = replace(scene.reader.raw, map_id=int(MapId.ROUTE_1), player_y=8, player_x=7)
    interruption = TraversalSnapshot(
        int(MapId.ROUTE_1), (8, 7), False, "scripted_dialogue"
    )

    receipt = scene.handler.handle(interruption)

    assert receipt.resumed_at == (8, 7)
    assert scene.fallback.calls == [interruption]
    assert scene.actions.actions == []


@pytest.mark.parametrize("fault", ["collection", "party", "money"])
def test_active_safari_exit_rejects_protected_state_changes(fault):
    scene = _handler(fault=fault)
    with pytest.raises(RouteExecutionError, match="changed"):
        scene.handler.handle(scene.interruption)


def test_active_safari_exit_rejects_the_wrong_landing():
    scene = _handler(fault="wrong_landing")
    with pytest.raises(RouteExecutionError, match="wrong tile"):
        scene.handler.handle(scene.interruption)


def test_active_safari_exit_is_bounded_when_dialogue_never_settles():
    scene = _handler(fault="never_settles", settle_limit=2)
    with pytest.raises(RouteExecutionError, match="within its bound"):
        scene.handler.handle(scene.interruption)
    assert len(scene.actions.actions) == 4  # one cursor correction, then three confirms
