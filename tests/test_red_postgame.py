from copy import deepcopy
from types import SimpleNamespace

import pytest

from pokemon_red_completion import red_postgame as s
from pokemon_red_completion.goal_manager import GoalDecisionOutcome
from pokemon_red_completion.observation import (
    EventFlag,
    MapId,
    MenuCursorState,
    PokemonRedStateReader,
    RamAddress,
)
from pokemon_red_completion.red_postgame import continue_menu_visible, require_continue_selection


def test_text_observation_is_read_only_and_preserves_menu_rows():
    cells = {}
    for row, text in ((2, 'CONTINUE'), (4, 'NEW GAME'), (6, 'OPTION')):
        for col, char in enumerate(text, 2):
            cells[int(RamAddress.TILE_MAP) + row * 20 + col] = (
                ord(char) - ord('A') + 0x80 if char != ' ' else 0x7F)
    reader = PokemonRedStateReader(SimpleNamespace(read_u8=lambda at: cells.get(at, 0x7F)))
    rows = reader.read_screen_text_rows()
    assert continue_menu_visible(rows)
    cursor = MenuCursorState(0, 0, 2, 1, 2)
    require_continue_selection(rows, cursor)
    with pytest.raises(ValueError):
        require_continue_selection(rows, MenuCursorState(1, 0, 2, 1, 2))
    changed = list(rows)
    changed[2] = '  NEW GAME          '
    assert not continue_menu_visible(tuple(changed))
    with pytest.raises(ValueError):
        require_continue_selection(tuple(changed), cursor)


def menu_rows(*, summary=False):
    rows = [" " * 20 for _ in range(18)]
    rows[2], rows[4], rows[6] = (
        "  CONTINUE          ", "  NEW GAME          ", "  OPTION            "
    )
    if summary:
        rows[9], rows[11] = "PLAYER", "BADGES"
    return tuple(rows)


def postgame_fixture(monkeypatch, fault=None):
    events = bytearray(320)
    event = int(EventFlag.BEAT_CHAMPION_RIVAL)
    events[event // 8] |= 1 << (event % 8)
    raw = SimpleNamespace(
        map_id=int(MapId.HALL_OF_FAME), event_flags=bytes(events), game_started=True,
        battle_state=0, party_count=1, party_species_ids=(28,), party_levels=(80,),
        party_max_hp=(260,), party_moves=((70, 91, 145, 57),), badge_bits=255,
        player_money=29886, bag_items=((16, 1),),
    )
    state = SimpleNamespace(phase="hall", payload=b"hall", rows=(" " * 20,) * 18,
        boxes=("owned-box",), dex=(25,), pc=((211, 1),))
    em = SimpleNamespace(frame_count=0, pressed_buttons=(), save_state_bytes=lambda: state.payload)
    cursor = SimpleNamespace(selected_visible_index=0, maximum_visible_index=2, top_x=1, top_y=2)
    reader = SimpleNamespace(
        read=lambda: deepcopy(raw), read_screen_text_rows=lambda: state.rows,
        read_all_box_states=lambda: state.boxes, read_pokedex_state=lambda: state.dex,
        read_pc_items=lambda: state.pc, read_menu_cursor_state=lambda: cursor,
        read_final_league_scene=lambda: SimpleNamespace(queued_movement=False, script_stage=2),
        read_bottom_dialogue_box_visible=lambda: False,
    )
    completed = ("defeat_champion", "enter_hall_of_fame")
    rt = SimpleNamespace(reader=reader, emulator=em,
        adapter=SimpleNamespace(observe=lambda: SimpleNamespace(game_state=object()),
            graph=SimpleNamespace(completed_ids=lambda _: completed)))
    calls = []

    class Actions:
        actions_executed = 0

        def execute(self, action):
            self.actions_executed += 1
            em.frame_count += max(1, action.repeat)
            calls.append(action.kind)
            if action.kind is s.MacroActionKind.CONFIRM:
                if state.phase == "hall":
                    state.phase, raw.map_id, raw.game_started = "title", None, False
                    raw.event_flags = bytes(320)
                elif state.phase == "title":
                    state.phase, state.rows = "summary", menu_rows(summary=True)
                elif state.phase == "summary":
                    state.phase = "field"
                    raw.map_id, raw.game_started = int(MapId.PALLET_TOWN), True
                    if fault in s.PRESERVED_PARTY:
                        setattr(raw, fault, ("changed",))
                    if fault in {"boxes", "dex", "pc"}:
                        setattr(state, fault, ("changed",))
                    if fault == "event":
                        raw.event_flags = bytes(events)
            elif action.kind is s.MacroActionKind.OPEN_MENU:
                state.rows = menu_rows()
                if fault == "new_game":
                    cursor.selected_visible_index = 1
            state.payload = str((state.phase, self.actions_executed)).encode()

    monkeypatch.setattr(s, "_field_ready", lambda _: state.phase == "field")
    return rt, Actions(), raw, state, calls


def test_postgame_return_is_zero_input_then_conserved_control_support(monkeypatch):
    rt, actions, _, state, calls = postgame_fixture(monkeypatch)
    binding = s.postgame_return_binding(rt, actions)
    assert binding.kind is s.GoalKind.RECOVER_CONTROL
    assert not calls and actions.actions_executed == 0 and state.payload == b"hall"
    report = binding.execute()
    assert report.evidence["native_postgame_return_verified"]
    assert not report.evidence["learned_return"] and not report.evidence["story_credit"]
    assert report.evidence["model_queries"] == 0 and report.evidence["new_game_selected"] is False
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    assert calls.count(s.MacroActionKind.CONFIRM) == 3
    with pytest.raises(ValueError, match="consumed"):
        binding.execute()
    state.payload = b"changed-later"
    assert binding.verify(report).status is GoalDecisionOutcome.FAILED


@pytest.mark.parametrize("fault", [*s.PRESERVED_PARTY, "boxes", "dex", "pc", "event"])
def test_postgame_return_rejects_unexplained_native_terminal_change(monkeypatch, fault):
    rt, actions, _, _, _ = postgame_fixture(monkeypatch, fault)
    binding = s.postgame_return_binding(rt, actions)
    with pytest.raises(RuntimeError, match="preserve"):
        binding.execute()


def test_postgame_return_never_confirms_new_game(monkeypatch):
    rt, actions, _, _, calls = postgame_fixture(monkeypatch, "new_game")
    binding = s.postgame_return_binding(rt, actions)
    with pytest.raises(ValueError, match="Continue"):
        binding.execute()
    assert calls.count(s.MacroActionKind.CONFIRM) == 1


def test_postgame_return_stale_source_refuses_before_inputs(monkeypatch):
    rt, actions, _, state, calls = postgame_fixture(monkeypatch)
    binding = s.postgame_return_binding(rt, actions)
    state.payload = b"another-source"
    with pytest.raises(ValueError, match="stale"):
        binding.execute()
    assert not calls and actions.actions_executed == 0


@pytest.mark.parametrize(
    "fault", ["field", "unfinished", "battle", "party", "cash", "bag", "pressed"]
)
def test_postgame_return_requires_an_earned_scene_without_inputs(monkeypatch, fault):
    rt, actions, raw, _, calls = postgame_fixture(monkeypatch)
    if fault == "field":
        raw.map_id = int(MapId.PALLET_TOWN)
    if fault == "unfinished":
        raw.event_flags = bytes(320)
        rt.adapter.graph.completed_ids = lambda _: ()
    if fault == "battle":
        raw.battle_state = 1
    if fault == "party":
        raw.party_count = 0
    if fault == "cash":
        raw.player_money = None
    if fault == "bag":
        raw.bag_items = None
    if fault == "pressed":
        rt.emulator.pressed_buttons = ("a",)
    assert s.postgame_return_binding(rt, actions) is None
    assert not calls and actions.actions_executed == 0


@pytest.mark.parametrize("cursor", [0, 1])
def test_reset_hall_with_visible_title_checks_continue_instead_of_blind_confirm(cursor):
    selected = SimpleNamespace(
        selected_visible_index=cursor, maximum_visible_index=2, top_x=1, top_y=2
    )
    if cursor:
        with pytest.raises(ValueError, match="Continue"):
            s.continue_action("hall", menu_rows(), SimpleNamespace(map_id=118), None,
                selected, dialogue=False, saw_reset=True)
    else:
        phase, action = s.continue_action("hall", menu_rows(), SimpleNamespace(map_id=118), None,
            selected, dialogue=False, saw_reset=True)
        assert phase == "summary" and action.kind is s.MacroActionKind.CONFIRM
