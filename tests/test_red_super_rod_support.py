from dataclasses import replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.observation import (
    EventFlag,
    InputReadiness,
    ItemId,
    MapId,
    MenuCursorState,
    RawGameState,
)
from pokemon_red_completion.red_super_rod_support import (
    SUPER_ROD_FACING,
    SUPER_ROD_HOUSE_MAP_ID,
    SUPER_ROD_NPC_YX,
    SUPER_ROD_STANCE_YX,
    SUPER_ROD_STATUS_MASK,
    RedRoutedSuperRodSupport,
    RedRoutedSuperRodSupportResult,
    RedSuperRodSupportError,
    RedSuperRodSupportExecutor,
    observe_red_super_rod_support,
)
from pokemon_red_completion.route_executor import TraversalSnapshot


def _with_event(flags: bytes, event: EventFlag, enabled: bool) -> bytes:
    result = bytearray(flags)
    byte_index, bit_index = divmod(int(event), 8)
    if enabled:
        result[byte_index] |= 1 << bit_index
    else:
        result[byte_index] &= ~(1 << bit_index)
    return bytes(result)


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
        event_flags=bytes(320),
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

    def read_u8(self, _address):
        return 0


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


class _RoutedGiftActions(_GiftActions):
    def execute(self, action):
        if action.kind is MacroActionKind.MOVE:
            self.count += 1
            self.kinds.append(action.kind)
            self.emulator.frame_count += 24
            self.reader.facing = str(action.value)
            return
        super().execute(action)


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


def test_routed_receipt_keeps_support_out_of_learning_and_hides_coordinates():
    gift = RedSuperRodSupportExecutor(
        CountingExecutor(_GiftActions(reader := _Reader(), emulator := _Emulator())),
        reader,
        emulator,
    ).execute()
    result = RedRoutedSuperRodSupportResult(
        gift, 384, 1, 2, False, True, 410, 42_000
    )
    public = result.public_dict()
    assert public["training_examples"] == 0
    assert public["learned_goal_authority"] is False
    assert public["private_coordinates_published"] == 0
    assert SUPER_ROD_STANCE_YX not in public.values()


@pytest.mark.parametrize("mutation", ["actions", "frames", "route", "facing"])
def test_routed_receipt_rejects_invalid_accounting(mutation):
    gift = RedSuperRodSupportExecutor(
        CountingExecutor(_GiftActions(reader := _Reader(), emulator := _Emulator())),
        reader,
        emulator,
    ).execute()
    values = {
        "gift": gift,
        "route_steps": 384,
        "route_replans": 0,
        "route_interruptions": 0,
        "safari_exit_used": False,
        "facing_action_used": False,
        "actions": 410,
        "frames": 42_000,
    }
    if mutation == "actions":
        values["actions"] = gift.actions - 1
    elif mutation == "frames":
        values["frames"] = gift.frames - 1
    elif mutation == "route":
        values["route_steps"] = -1
    else:
        values["facing_action_used"] = 1
    with pytest.raises(ValueError):
        RedRoutedSuperRodSupportResult(**values)


def _patch_routed_dependencies(monkeypatch, reader):
    import pokemon_red_completion.red_super_rod_support as runtime

    plan = SimpleNamespace(steps=(object(),))
    report = SimpleNamespace(
        passed=True,
        executed_steps=(object(),),
        replans=(),
        interruptions=(),
    )

    class Observer:
        def observe(self):
            raw = reader.read()
            return TraversalSnapshot(
                raw.map_id,
                (raw.player_y, raw.player_x),
                True,
                mode="land",
            )

    monkeypatch.setattr(runtime, "Gen1FieldMovePort", lambda *args, **kwargs: object())
    monkeypatch.setattr(runtime, "Gen1TraversalObserver", lambda *args, **kwargs: Observer())
    monkeypatch.setattr(runtime, "Gen1TrainerSightProjector", lambda *args: object())
    monkeypatch.setattr(runtime, "Gen1RouteInterruptionHandler", lambda *args, **kwargs: object())
    monkeypatch.setattr(runtime, "_supported_plan", lambda *args, **kwargs: True)

    def execute_route(*args, **kwargs):
        reader.raw = replace(
            reader.raw,
            map_id=SUPER_ROD_HOUSE_MAP_ID,
            player_y=SUPER_ROD_STANCE_YX[0],
            player_x=SUPER_ROD_STANCE_YX[1],
        )
        return report

    monkeypatch.setattr(runtime, "execute_route", execute_route)
    world = SimpleNamespace(
        rom=b"rom",
        rules=SimpleNamespace(cut_block_swaps=()),
        plan_feasible_to_map=lambda *args, **kwargs: plan,
        replanner=lambda: object(),
    )
    return runtime, world


def test_routed_executor_reaches_faces_and_accepts_support_gift(monkeypatch):
    reader, emulator = _Reader(_raw(map_id=int(MapId.SAFARI_ZONE_EAST))), _Emulator()
    reader.facing = "up"
    _runtime, world = _patch_routed_dependencies(monkeypatch, reader)
    delegate = _RoutedGiftActions(reader, emulator, acquire_on=4, settle_on=5)
    result = RedRoutedSuperRodSupport(
        CountingExecutor(delegate), reader, emulator, world
    ).execute()
    assert delegate.kinds == [
        MacroActionKind.MOVE,
        MacroActionKind.INTERACT,
        MacroActionKind.CONFIRM,
        MacroActionKind.CONFIRM,
        MacroActionKind.CONFIRM,
    ]
    assert result.route_steps == 1
    assert result.facing_action_used
    assert result.actions == 5 and result.frames == 120
    assert result.gift.actions == 4 and result.gift.frames == 96


def test_routed_executor_rejects_unsupported_route_before_input(monkeypatch):
    reader, emulator = _Reader(_raw(map_id=int(MapId.SAFARI_ZONE_EAST))), _Emulator()
    runtime, world = _patch_routed_dependencies(monkeypatch, reader)
    monkeypatch.setattr(runtime, "_supported_plan", lambda *args, **kwargs: False)
    delegate = _RoutedGiftActions(reader, emulator)
    with pytest.raises(RedSuperRodSupportError, match="unsupported transport"):
        RedRoutedSuperRodSupport(
            CountingExecutor(delegate), reader, emulator, world
        ).execute()
    assert delegate.count == 0 and emulator.frame_count == 0


def test_active_safari_exit_selects_yes_and_settles_before_onward_route(monkeypatch):
    import pokemon_red_completion.red_super_rod_support as runtime

    flags = _with_event(bytes(320), EventFlag.IN_SAFARI_ZONE, True)
    reader = _Reader(
        _raw(
            map_id=int(MapId.SAFARI_ZONE_WEST),
            player_y=24,
            player_x=14,
            event_flags=flags,
        )
    )
    reader.menu = MenuCursorState(1, 0, 1, 14, 7)
    emulator = _Emulator()

    transition = SimpleNamespace(
        source_map=int(MapId.SAFARI_ZONE_CENTER),
        source_at=(25, 15),
        expected_map=int(MapId.SAFARI_ZONE_GATE),
        expected_at=(0, 4),
        stays_on_map=False,
        macro_action=MacroAction(MacroActionKind.MOVE, "down"),
    )
    onward = SimpleNamespace(steps=(transition,))
    prefix = SimpleNamespace(steps=(object(), object()))
    report = SimpleNamespace(
        passed=True,
        executed_steps=(object(), object()),
        replans=(object(),),
        interruptions=(object(), object()),
    )

    class Actions:
        def __init__(self):
            self.kinds = []

        def execute(self, action):
            self.kinds.append((action.kind, action.value))
            emulator.frame_count += 24
            if (
                action.kind is MacroActionKind.MOVE
                and action.value == "down"
                and reader.raw.map_id == int(MapId.SAFARI_ZONE_CENTER)
            ):
                reader.raw = replace(
                    reader.raw,
                    map_id=int(MapId.SAFARI_ZONE_GATE),
                    player_y=0,
                    player_x=4,
                )
                reader.ready = False
                reader.dialogue = True
            elif action.kind is MacroActionKind.MOVE and action.value == "up":
                reader.menu = replace(reader.menu, selected_visible_index=0)
            elif action.kind is MacroActionKind.CONFIRM and reader.dialogue:
                active = _with_event(
                    reader.raw.event_flags,
                    EventFlag.IN_SAFARI_ZONE,
                    False,
                )
                if active != reader.raw.event_flags:
                    reader.raw = replace(reader.raw, event_flags=active)
                else:
                    reader.raw = replace(reader.raw, player_y=3)
                    reader.ready = True
                    reader.dialogue = False

    def read_menu_cursor_state():
        return reader.menu

    reader.read_menu_cursor_state = read_menu_cursor_state
    delegate = Actions()
    actions = CountingExecutor(delegate)
    world = SimpleNamespace(
        plan_feasible_to_map=lambda *args, **kwargs: prefix,
        replanner=lambda: object(),
    )
    monkeypatch.setattr(runtime, "_supported_plan", lambda *args, **kwargs: True)

    def execute_route(*args, **kwargs):
        reader.raw = replace(
            reader.raw,
            map_id=int(MapId.SAFARI_ZONE_CENTER),
            player_y=25,
            player_x=15,
        )
        return report

    monkeypatch.setattr(runtime, "execute_route", execute_route)
    support = RedRoutedSuperRodSupport(actions, reader, emulator, world)
    receipt = support._leave_active_safari(
        onward,
        actions,
        SimpleNamespace(observe=lambda: TraversalSnapshot(0, (0, 0), True)),
        object(),
    )

    assert receipt.route_steps == 3
    assert receipt.route_replans == 1
    assert receipt.route_interruptions == 2
    assert delegate.kinds == [
        (MacroActionKind.MOVE, "down"),
        (MacroActionKind.WAIT, None),
        (MacroActionKind.MOVE, "up"),
        (MacroActionKind.CONFIRM, None),
        (MacroActionKind.CONFIRM, None),
    ]
    assert reader.raw.map_id == int(MapId.SAFARI_ZONE_GATE)
    assert (reader.raw.player_y, reader.raw.player_x) == (3, 4)
    assert _with_event(
        reader.raw.event_flags,
        EventFlag.IN_SAFARI_ZONE,
        False,
    ) == reader.raw.event_flags
    assert reader.ready and not reader.dialogue
