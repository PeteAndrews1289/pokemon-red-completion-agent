from dataclasses import replace
from types import SimpleNamespace as N

import pytest
from test_route22_learned_entry import available, cartridge

from pokemon_red_completion import gen1_route22_script as script
from pokemon_red_completion import red_player_route22_rival as s
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import ExecutableGoalBinding


@pytest.mark.parametrize("starter,trainer_set", [(7, 10), (9, 11), (11, 12)])
def test_contract_keeps_decoded_identity_event_and_cartridge_cash(
    monkeypatch, starter, trainer_set
):
    monkeypatch.setattr(
        s, "route22_script_binding", lambda _, value: script._decode(cartridge(), value)
    )
    quotes = []
    monkeypatch.setattr(
        s,
        "trainer_party_quote",
        lambda rom, cls, n: quotes.append((cls, n)) or N(expected_victory_money=1737),
    )
    contract = s.route22_rival_contract(
        b"rom", N(read=available, read_rival_starter=lambda: starter)
    )
    assert contract.trainer_identity == (242, 42, trainer_set)
    assert contract.defeated_event == 1318 and contract.victory_money == 1737
    assert contract.objective_id == s.OBJECTIVE and quotes == [(242, trainer_set)]


@pytest.mark.parametrize("badges", [0, 1, 3, 127, 254])
def test_early_route22_preparation_never_requests_late_rival(monkeypatch, badges):
    raw = replace(available(), badge_bits=badges)
    monkeypatch.setattr(s, "route22_rival_contract", lambda *a: pytest.fail("late preview"))
    assert s.route22_preparation_contract(
        b"rom", N(read=lambda: raw), available_objectives={s.OBJECTIVE, "help_bill"}
    ) is None


@pytest.mark.parametrize("fault", ["other_map", "unavailable_objective", "consumed"])
def test_irrelevant_or_consumed_late_preview_is_not_requested(monkeypatch, fault):
    raw = available()
    objectives = {s.OBJECTIVE}
    if fault == "other_map":
        raw = replace(raw, map_id=1)
    elif fault == "unavailable_objective":
        objectives = {"defeat_misty", "help_bill"}
    else:
        flags = bytearray(raw.event_flags)
        flags[1318 // 8] |= 1 << (1318 % 8)
        raw = replace(raw, event_flags=bytes(flags))
    monkeypatch.setattr(s, "route22_rival_contract", lambda *a: pytest.fail("late preview"))
    assert s.route22_preparation_contract(
        b"rom", N(read=lambda: raw), available_objectives=objectives
    ) is None


@pytest.mark.parametrize("fault", [None, "no_events", "not_active", "no_wants", "first_rival"])
def test_relevant_late_preview_preserves_strict_native_script_checks(monkeypatch, fault):
    raw = available()
    if fault == "no_events":
        raw = replace(raw, event_flags=None)
    elif fault:
        flags = bytearray(raw.event_flags)
        bit = {"not_active": 1313, "no_wants": 1319, "first_rival": 1312}[fault]
        flags[bit // 8] ^= 1 << (bit % 8)
        raw = replace(raw, event_flags=bytes(flags))
    monkeypatch.setattr(
        s, "route22_script_binding", lambda _, starter: script._decode(cartridge(), starter)
    )
    monkeypatch.setattr(s, "trainer_party_quote", lambda *a: N(expected_victory_money=1737))
    reader = N(read=lambda: raw, read_rival_starter=lambda: 7)
    before = raw
    if fault is None:
        contract = s.route22_preparation_contract(
            b"rom", reader, available_objectives={s.OBJECTIVE}
        )
        assert contract.trainer_identity == (242, 42, 10) and contract.defeated_event == 1318
    else:
        with pytest.raises(ValueError, match="second rival unavailable"):
            s.route22_preparation_contract(b"rom", reader, available_objectives={s.OBJECTIVE})
    assert reader.read() == before


def test_option_reuses_native_safe_prefix_and_battle_lifecycle_without_input(monkeypatch):
    raw = available()
    rt = N(reader=N(read=lambda: raw, read_rival_starter=lambda: 7), emulator=object())
    route = N(rom=b"rom", route_world=object())
    calls = []
    monkeypatch.setattr(s, "_field_ready", lambda _: True)
    monkeypatch.setattr(
        s, "route22_script_binding", lambda _, starter: script._decode(cartridge(), starter)
    )
    monkeypatch.setattr(
        s, "Gen1TrainerSightProjector", lambda *a, **k: N(observe_hazards=lambda _: ())
    )
    monkeypatch.setattr(s, "Gen1TraversalObserver", lambda *a: N(observe=lambda: object()))
    monkeypatch.setattr(
        s, "plan_scripted_approaches", lambda *a: (N(prefix=(3, 9), edge=N(action="left")),)
    )
    monkeypatch.setattr(s, "engage_scripted_rival", lambda *a, **k: calls.append(k))
    captured = []

    def lifecycle(*args, **kwargs):
        captured.append(kwargs)
        return ExecutableGoalBinding(
            "rival", GoalKind.ADVANCE_STORY, 0.2, 0.4, kwargs["scripted_entry"], lambda _: None
        )

    monkeypatch.setattr(s, "scripted_rival_binding", lifecycle)
    binding = s.route22_rival_binding(rt, object(), route=route, battler=object())
    assert not calls and binding.story_objective_ref == s.OBJECTIVE
    kwargs = captured[0]
    assert kwargs["entries"] == (((3, 9), "left"),)
    assert kwargs["map_id"] == 33 and kwargs["objective_id"] == s.OBJECTIVE
    hazards = kwargs["hazard_projector"].observe_hazards(raw)
    assert {h.at for h in hazards} == {(2, 8), (3, 8)}
    assert all(h.kind == "scripted_rival" for h in hazards)
    binding.execute()
    assert len(calls) == 1 and calls[0]["binding"].identity == (242, 42, 10)
    rt.reader.read = lambda: replace(raw, map_id=1)
    assert s.route22_rival_binding(rt, object(), route=route, battler=object()) is None
