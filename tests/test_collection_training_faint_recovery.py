"""Ordinary faint recovery retains native costs and exact trainee identity."""

from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion import battle_recovery as shared
from pokemon_red_completion import red_team_training as training
from pokemon_red_completion import wild_party_flee
from pokemon_red_completion.party import MoveObservation, PartyMemberObservation, PartyObservation


def fixture(monkeypatch, fault=None):
    trainee = PartyMemberObservation(
        1, 59, 22, 0, 39, experience=10666, moves=(MoveObservation(10, 35, 35),)
    )
    escort = PartyMemberObservation(
        2, 28, 48, 150, 150, experience=109000, moves=(MoveObservation(57, 15, 15),)
    )
    state = NS(
        party=PartyObservation((trainee, escort)),
        raw=NS(
            map_id=197,
            battle_state=1,
            battler_hp=0,
            active_party_index=0,
            enemy_hp=14,
            enemy_level=17,
            enemy_species_id=59,
            player_money=1000,
            bag_items=((4, 3),),
        ),
    )
    calls = []
    events = []

    class PartyReader:
        def __init__(self, em):
            pass

        def read(self):
            return state.party

        def preparation_specimen_refs(self):
            return tuple(str(m.species_id) for m in state.party.members)

    monkeypatch.setattr(training, "PokemonRedPartyReader", PartyReader)
    monkeypatch.setattr(
        training,
        "collection_escape_escort",
        lambda *a, **k: None if fault == "no_escort" else state.party.members[1],
    )

    def switch(*args, **kwargs):
        assert args[3] == 1 and kwargs["expected_battle_state"] == 1
        calls.append("switch")
        state.raw.active_party_index = 1
        state.raw.battler_hp = 150
        if fault == "bad_switch":
            state.raw.active_party_index = 0

    monkeypatch.setattr(shared, "switch_active_battler", switch)

    def flee(*args, **kwargs):
        calls.append("flee")
        state.raw.battle_state = 0
        if fault == "xp_drift":
            state.party = replace(state.party, members=(replace(trainee, experience=10667), escort))
        if fault == "item_drift":
            state.raw.bag_items = ()
        if fault == "cash_drift":
            state.raw.player_money = 999

        return NS(verified=True)

    monkeypatch.setattr(wild_party_flee, "flee_with_fainted_lead", flee)

    def heal(*args):
        calls.append("heal")
        if fault != "failed_heal":
            state.party = replace(
                state.party, members=tuple(replace(m, hp=m.max_hp) for m in state.party.members)
            )
        if fault == "identity_drift":
            state.party = replace(
                state.party,
                members=(replace(state.party.members[0], species_id=60), state.party.members[1]),
            )

    def metered(healer, reader, em):
        calls.append("meter")
        healer(None, reader, em)

    actions = NS(
        record_diagnostic_event=lambda name, data: events.append((name, data)),
        execute_training_healing=metered,
    )
    reader = NS(read=lambda: state.raw, read_input_readiness=lambda: NS(ready=True))
    return (
        state,
        calls,
        events,
        lambda: training.recover_collection_training_faint(
            actions,
            reader,
            object(),
            recipient_species_id=59,
            policy=object(),
            heal_and_return=heal,
        ),
    )


def test_forced_switch_escape_and_metered_heal_preserve_faint_and_zero_xp(monkeypatch):
    state, calls, events, run = fixture(monkeypatch)
    run()
    assert calls == ["switch", "flee", "meter", "heal"]
    assert state.party.members[0].experience == 10666 and state.party.members[0].hp == 39
    assert [x[0] for x in events] == ["wild_training_faint", "wild_training_faint_recovery"]
    assert all(x[1]["observed_faints"] == 1 and x[1]["training_win"] is False for x in events)
    assert events[-1][1]["target_xp_gained"] == 0


@pytest.mark.parametrize(
    "fault",
    [
        "xp_drift",
        "item_drift",
        "cash_drift",
        "failed_heal",
        "identity_drift",
        "bad_switch",
        "no_escort",
    ],
)
def test_drift_or_unsettled_recovery_never_becomes_success(monkeypatch, fault):
    _, _, events, run = fixture(monkeypatch, fault)
    with pytest.raises(RuntimeError):
        run()
    assert not any(name == "wild_training_faint_recovery" for name, _ in events)


@pytest.mark.parametrize("fault", ["trainer", "not_fainted", "all_fainted", "enemy_knocked_out"])
def test_unsupported_boundaries_issue_no_inputs(monkeypatch, fault):
    state, calls, _, run = fixture(monkeypatch)
    if fault == "trainer":
        state.raw.battle_state = 2
    if fault == "not_fainted":
        state.raw.battler_hp = 1
    if fault == "all_fainted":
        state.party = replace(
            state.party, members=tuple(replace(m, hp=0) for m in state.party.members)
        )
    if fault == "enemy_knocked_out":
        state.raw.enemy_hp = 0
    with pytest.raises(RuntimeError):
        run()
    assert calls == []
