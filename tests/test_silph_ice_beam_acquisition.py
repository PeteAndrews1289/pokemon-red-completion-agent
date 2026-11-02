from types import SimpleNamespace

import pytest

from pokemon_red_completion import silph as s


@pytest.fixture
def roof(monkeypatch):
    state = dict(
        cash=3326,
        bag={1: 1},
        event=False,
        x=15,
        y=3,
        ready=True,
        moves=((91, 70, 57, 55),),
        purchased=False,
    )

    def read():
        return SimpleNamespace(
            map_id=s.MapId.CELADON_MART_ROOF,
            player_x=state["x"],
            player_y=state["y"],
            battle_state=0,
            party_species_ids=(28,),
            party_levels=(48,),
            party_moves=state["moves"],
            party_pp=((10, 15, 15, 25),),
            party_hp=(150,),
            party_status=(0,),
        )

    reader = SimpleNamespace(
        read=read,
        read_input_readiness=lambda: SimpleNamespace(ready=state["ready"]),
        read_bottom_dialogue_box_visible=lambda: False,
    )
    monkeypatch.setattr(s, "_bag", lambda _: dict(state["bag"]))
    monkeypatch.setattr(s, "_money", lambda _: state["cash"])
    monkeypatch.setattr(
        s, "_event", lambda _, flag: state["event"] if flag == s.EventFlag.GOT_TM13 else False
    )
    monkeypatch.setattr(s, "_move", lambda *a: state.update(x=12, y=3))
    monkeypatch.setattr(s, "_interact", lambda *a: None)
    monkeypatch.setattr(s, "_select_cursor", lambda *a: None)
    monkeypatch.setattr(s, "_close_menus", lambda *a: None)
    monkeypatch.setattr(s, "_clear_field_text", lambda *a: None)

    def pulse(*args, **kwargs):
        if not state["purchased"]:
            state["bag"][s.ItemId.FRESH_WATER] = 1
            state["cash"] -= 200
            state["purchased"] = True

    monkeypatch.setattr(s, "_pulse", pulse)

    def exchange(*args):
        del state["bag"][s.ItemId.FRESH_WATER]
        state["bag"][s.ItemId.TM13_ICE_BEAM] = 1
        state["event"] = True

    monkeypatch.setattr(s, "_interact_with_roof_girl", exchange)
    monkeypatch.setattr(
        s, "_teach_ice_beam", lambda *a, **k: pytest.fail("acquisition must not teach")
    )
    return state, reader, SimpleNamespace(read_u8=lambda _: 0)


def test_acquisition_does_not_select_a_move(roof):
    state, reader, emulator = roof
    assert s.acquire_ice_beam_on_roof(None, reader, emulator, money_before=3326)
    assert state["cash"] == 3126 and state["bag"] == {1: 1, s.ItemId.TM13_ICE_BEAM: 1}
    assert reader.read().party_moves == ((91, 70, 57, 55),)


@pytest.mark.parametrize(
    "change",
    [
        dict(event=True),
        dict(cash=199),
        dict(ready=False),
        dict(bag={s.ItemId.FRESH_WATER: 1}),
        dict(bag={s.ItemId.TM13_ICE_BEAM: 1}),
        dict(bag={i: 1 for i in range(20)}),
        dict(cash=3325),
    ],
)
def test_acquisition_rejects_unsafe_start_before_input(roof, change):
    state, reader, emulator = roof
    state.update(change)
    with pytest.raises(s.SilphChapterError):
        s.acquire_ice_beam_on_roof(None, reader, emulator, money_before=3326)
    assert not state["purchased"]


def test_acquisition_rejects_unexpected_party_change(roof, monkeypatch):
    state, reader, emulator = roof
    original = s._clear_field_text

    def changed(*args):
        original(*args)
        state["moves"] = ((91, 70, 58, 55),)

    monkeypatch.setattr(s, "_clear_field_text", changed)
    with pytest.raises(s.SilphChapterError, match="party before teaching"):
        s.acquire_ice_beam_on_roof(None, reader, emulator, money_before=3326)


def test_legacy_combined_lesson_preserves_order_and_parameters(monkeypatch):
    calls = []
    monkeypatch.setattr(
        s, "acquire_ice_beam_on_roof", lambda *a, **k: calls.append(("acquire", k)) or True
    )
    monkeypatch.setattr(s, "_teach_ice_beam", lambda *a, **k: calls.append(("teach", k)))
    before = (130, 70, 61, 57)
    after = (130, 70, 58, 57)
    assert s._acquire_and_teach_ice_beam_on_roof(
        None,
        None,
        None,
        s.DEFAULT_SILPH_TIMING,
        money_before=900,
        expected_moves_before=before,
        expected_moves_after=after,
    )
    assert calls == [
        ("acquire", {"money_before": 900}),
        ("teach", {"expected_moves_before": before, "expected_moves_after": after}),
    ]
