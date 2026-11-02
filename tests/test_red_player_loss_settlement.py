from copy import deepcopy
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_preparation_binding as p


def fixture(monkeypatch):
    document = dict(in_battle=True, completed_objectives=["starter"],
                    objective_catalog=["starter"], party=[dict(specimen_ref="starter",
                    species_id=177, level=5, experience=159, moves=[[33, 27]])])
    before = N(raw=N(battle_state=1, party_hp=(0,)), input_ready=False)
    after = N(raw=N(battle_state=0, party_hp=(20,)), input_ready=True)
    terminal = deepcopy(document)
    terminal["in_battle"] = False
    terminal["party"][0]["moves"][0][1] = 35
    count = [0]
    def capture(_):
        count[0] += 1
        return (before, document) if count[0] == 1 else (after, terminal)
    monkeypatch.setattr(p, "capture_player_lesson_snapshot", capture)
    monkeypatch.setattr(p, "_raw_party_fully_restored", lambda _: True)
    calls = []
    def settle(actions, reader, emulator, **kw):
        calls.append(kw)
        return dict(blackout_verified=True, cash_before=3000, cash_after=1500,
                    cash_lost=1500, destination_map=41)
    monkeypatch.setattr(p, "settle_red_blackout", settle)
    runtime = N(emulator=N(pressed_buttons=(), save_state_bytes=lambda: b"state"),
                reader=N(read_bottom_dialogue_box_visible=lambda: False))
    records = []
    return runtime, before, after, terminal, calls, records


def test_settlement_preserves_xp_and_explicit_failed_training(monkeypatch):
    rt, _, _, _, calls, records = fixture(monkeypatch)
    result = p.settle_preparation_loss(rt, object(), record=lambda *a: records.append(a))
    assert result["status"] == "settled_loss"
    assert not result["successful_preparation"] and not result["learned_recovery"]
    assert result["blackout"]["cash_lost"] == 1500
    assert result["after"]["party"][0]["experience"] == 159
    assert calls == [{"maximum_pulses": 128}]
    assert [r[0] for r in records] == ["blackout-started", "blackout-settled"]


@pytest.mark.parametrize("field,value", [("experience", 160), ("level", 6),
    ("species_id", 1), ("specimen_ref", "replacement"), ("moves", [[39, 30]])])
def test_settlement_rejects_party_changes(monkeypatch, field, value):
    rt, _, _, terminal, _, _ = fixture(monkeypatch)
    terminal["party"][0][field] = value
    with pytest.raises(ValueError, match="preserve"):
        p.settle_preparation_loss(rt, None, record=lambda *a: None)


@pytest.mark.parametrize("fault", ["objectives", "dialogue", "unready", "still_battle", "pp"])
def test_settlement_requires_fresh_unchanged_ready_boundary(monkeypatch, fault):
    rt, _, after, terminal, _, _ = fixture(monkeypatch)
    if fault == "objectives":
        terminal["completed_objectives"].append("invented")
    elif fault == "dialogue":
        rt.reader.read_bottom_dialogue_box_visible = lambda: True
    elif fault == "unready":
        after.input_ready = False
    elif fault == "still_battle":
        terminal["in_battle"] = True
    else:
        monkeypatch.setattr(p, "_raw_party_fully_restored", lambda _: False)
    with pytest.raises(ValueError, match="preserve"):
        p.settle_preparation_loss(rt, None, record=lambda *a: None)


@pytest.mark.parametrize("fault", ["alive", "trainer", "field", "held"])
def test_settlement_rejects_invalid_start_without_support(monkeypatch, fault):
    rt, before, _, _, calls, _ = fixture(monkeypatch)
    if fault == "alive":
        before.raw.party_hp = (1,)
    elif fault == "held":
        rt.emulator.pressed_buttons = ("a",)
    else:
        before.raw.battle_state = 2 if fault == "trainer" else 0
    with pytest.raises(ValueError, match="observed released wild defeat"):
        p.settle_preparation_loss(rt, None, record=lambda *a: None)
    assert not calls
