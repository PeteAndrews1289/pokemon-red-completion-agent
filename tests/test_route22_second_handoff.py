"""An incidental late-rival introduction must use the native battle lifecycle."""

from dataclasses import replace
from types import SimpleNamespace as N

import pytest
from test_route22_learned_entry import available, cartridge

from pokemon_red_completion import gen1_route22_script as script
from pokemon_red_completion import red_player_engaged_story as engaged
from pokemon_red_completion import red_player_route22_rival as rival


def fixture(monkeypatch, *, phase=4, starter=7):
    raw = replace(available(), player_y=2, player_x=8, battle_state=0)
    reader = N(read=lambda: raw, read_rival_starter=lambda: starter,
        read_route22_script=lambda: phase,
        read_pending_trainer_battle_identity=lambda: None,
        read_input_readiness=lambda: N(ready=False),
        read_bottom_dialogue_box_visible=lambda: phase == 4)
    monkeypatch.setattr(rival, "route22_script_binding",
        lambda _, value: script._decode(cartridge(), value))
    monkeypatch.setattr(rival, "trainer_party_quote",
        lambda *args: N(expected_victory_money=1737))
    return reader, raw


@pytest.mark.parametrize("phase", [4, 5])
@pytest.mark.parametrize("starter,team", [(7, 10), (9, 11), (11, 12)])
def test_pending_late_rival_uses_decoded_identity_without_approach_or_chapter_credit(
    monkeypatch, phase, starter, team,
):
    reader, raw = fixture(monkeypatch, phase=phase, starter=starter)
    contract = engaged.engaged_story_contract(reader, b"rom",
        objective_id="cross_victory_road")
    assert contract.trainer_identity == (242, 42, team)
    assert contract.defeated_event == 1318 and contract.victory_money == 1737
    assert contract.battle_plan_id == "route22-rival-gate"
    assert contract.victory_badge_bits == 0 and contract.victory_items == ()
    assert reader.read() == raw


@pytest.mark.parametrize("phase", [0, 1, 2, 3, 6, 7])
def test_untriggered_or_other_native_script_phases_are_not_recovery(monkeypatch, phase):
    reader, _ = fixture(monkeypatch, phase=phase)
    assert rival.retained_second_route22_contract(b"rom", reader) is None


@pytest.mark.parametrize("fault", ["wrong_map", "early_badges", "wild", "live_battle"])
def test_unowned_control_never_enters_the_introduction(monkeypatch, fault):
    reader, raw = fixture(monkeypatch)
    changed = {
        "wrong_map": dict(map_id=1), "early_badges": dict(badge_bits=127),
        "wild": dict(battle_state=1), "live_battle": dict(battle_state=2),
    }[fault]
    reader.read = lambda: replace(raw, **changed)
    assert rival.retained_second_route22_contract(b"rom", reader) is None


@pytest.mark.parametrize("fault", ["trigger", "ready", "pending", "text", "events",
    "no_second", "no_wants", "first_rival", "consumed"])
def test_ambiguous_introduction_is_rejected_before_any_execution(monkeypatch, fault):
    reader, raw = fixture(monkeypatch)
    if fault == "trigger":
        reader.read = lambda: replace(raw, player_x=9)
    elif fault == "ready":
        reader.read_input_readiness = lambda: N(ready=True)
    elif fault == "pending":
        reader.read_pending_trainer_battle_identity = lambda: (242, 12)
    elif fault == "text":
        reader.read_bottom_dialogue_box_visible = lambda: False
    elif fault == "events":
        reader.read = lambda: replace(raw, event_flags=None)
    else:
        flags = bytearray(raw.event_flags)
        bit = {"no_second": 1313, "no_wants": 1319,
               "first_rival": 1312, "consumed": 1318}[fault]
        flags[bit // 8] ^= 1 << (bit % 8)
        reader.read = lambda: replace(raw, event_flags=bytes(flags))
    with pytest.raises(ValueError):
        rival.retained_second_route22_contract(b"rom", reader)


@pytest.mark.parametrize("introduction", [False, True])
def test_composition_uses_its_existing_scoped_actor_only_for_exact_introduction(
    monkeypatch, introduction,
):
    from pokemon_red_completion.red_player_configuration import connect_retained_route22_recovery

    reader, _ = fixture(monkeypatch, phase=4 if introduction else 0)
    runtime, actions, generic_actor = N(reader=reader), object(), object()
    scoped_binding, ordinary_binding, calls = object(), object(), []
    backend = N(retained_early_trainer_binding=lambda *a, **kw:
        calls.append(("ordinary", a, kw)) or ordinary_binding)
    holder = dict(retained_trainer_binding=lambda *a:
        calls.append(("scoped", a)) or scoped_binding)
    connect_retained_route22_recovery(backend, holder)
    assert not calls  # Wiring and exact observation never execute a binding.
    got = backend.retained_early_trainer_binding(runtime, actions,
        rom=b"rom", battler=generic_actor)
    assert got is (scoped_binding if introduction else ordinary_binding)
    assert calls[0][:2] == (("scoped" if introduction else "ordinary"), (runtime, actions))
    if not introduction:
        assert calls[0][2] == dict(rom=b"rom", battler=generic_actor)


def test_reassembly_never_reuses_a_stale_rival_actor_or_duplicates_fallback(monkeypatch):
    from pokemon_red_completion.red_player_configuration import connect_retained_route22_recovery

    reader, _ = fixture(monkeypatch)
    runtime, calls = N(reader=reader), []
    original = lambda *a, **kw: calls.append("original")
    backend = N(retained_early_trainer_binding=original)
    connect_retained_route22_recovery(backend,
        dict(retained_trainer_binding=lambda *a: calls.append("stale")))
    connect_retained_route22_recovery(backend,
        dict(retained_trainer_binding=lambda *a: calls.append("current")))
    backend.retained_early_trainer_binding(runtime, object(), rom=b"rom", battler=object())
    assert calls == ["current"]
    assert backend.retained_early_trainer_binding.configured_route22_fallback is original


def test_backend_without_existing_scoped_callback_is_unchanged():
    from pokemon_red_completion.red_player_configuration import connect_retained_route22_recovery

    original = object()
    backend = N(retained_early_trainer_binding=original)
    connect_retained_route22_recovery(backend, {})
    assert backend.retained_early_trainer_binding is original
