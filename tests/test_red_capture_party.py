from dataclasses import replace
from types import SimpleNamespace

import pytest

import pokemon_red_completion.red_capture_party as support
from pokemon_red_completion.observation import RawGameState, RedBoxMoveMember, RedCurrentBoxState
from pokemon_red_completion.party import MoveObservation, PartyMemberObservation, PartyObservation


def party():
    return PartyObservation(tuple(
        PartyMemberObservation(slot, species, level, 50, 50,
                               moves=tuple(MoveObservation(move, 10) for move in moves))
        for slot, species, level, moves in (
            (1, 28, 63, (57, 70, 1, 0)), (2, 64, 55, (15, 19, 1, 0)),
            (3, 118, 55, (89, 1, 0, 0)), (4, 132, 55, (34, 1, 0, 0)),
            (5, 104, 55, (84, 1, 0, 0)), (6, 164, 40, (83, 1, 0, 0)),
        )
    ))


def box():
    return (
        RedBoxMoveMember(1, 185, 13, (71, 0, 0, 0), (20, 0, 0, 0)),
        RedBoxMoveMember(2, 48, 13, (1, 95, 50, 0), (35, 20, 20, 0)),
    )


def test_actual_moves_select_helper_and_preserve_last_field_carriers():
    plan = support.plan_capture_party(party(), box(), box_index=0)
    assert plan.helper == box()[1]
    assert plan.deposit_party_slot == 6
    # Same moves under a different species: capability choice does not change.
    swapped = (box()[0], replace(box()[1], species_id=164))
    assert support.plan_capture_party(party(), swapped, box_index=0).helper == swapped[1]
    changed = replace(party(), members=party().members[:-1] + (
        replace(party().members[-1], moves=(MoveObservation(148, 10),)),
    ))
    assert support.plan_capture_party(changed, box(), box_index=0).deposit_party_slot == 5


def test_no_box_slot_needed_for_an_existing_healthy_status_move():
    ready = replace(party(), members=(
        replace(party().members[0], moves=(MoveObservation(95, 10),)),
        *party().members[1:],
    ))
    assert support.plan_capture_party(ready, (), box_index=0) is None


def test_empty_pp_and_full_box_do_not_invent_support():
    with pytest.raises(support.RedCapturePartyError, match='no usable'):
        exhausted = (box()[0], replace(box()[1], pp=(35, 0, 20, 0)))
        support.plan_capture_party(party(), exhausted, box_index=0)
    full = tuple(replace(box()[1], box_slot=i) for i in range(1, 21))
    with pytest.raises(support.RedCapturePartyError, match='free box slot'):
        support.plan_capture_party(party(), full, box_index=0)
    smaller = replace(party(), members=party().members[:-1])
    assert support.plan_capture_party(smaller, box(), box_index=0).deposit_party_slot is None


def fixture(monkeypatch):
    original = party()
    plan = support.plan_capture_party(original, box(), box_index=0)
    state = SimpleNamespace(
        raw=RawGameState(True, 64, 13, 4, 6, 0,
                         party_species_ids=plan.party_species_ids, party_moves=plan.party_moves,
                         bag_items=((4, 4),), player_money=1109),
        box=RedCurrentBoxState(
            0, tuple(r.species_id for r in box()), tuple(r.level for r in box()),
        ),
        calls=[],
    )
    reader = SimpleNamespace(
        read=lambda: state.raw, read_current_box_state=lambda: state.box,
        read_current_box_move_members=box,
        read_input_readiness=lambda: SimpleNamespace(ready=True),
    )
    for name in ('face_pc_boundary', 'open_bills_pc', 'close_menu'):
        monkeypatch.setattr(support, name, lambda *_args, _name=name: state.calls.append(_name))
    def deposit(_actions, _reader, *, party_slot, expected_species_id):
        state.calls.append(('deposit', party_slot, expected_species_id))
        assert party_slot == 6 and expected_species_id == 164
        state.raw = replace(state.raw, party_species_ids=state.raw.party_species_ids[:-1])
        state.box = replace(
            state.box, species_ids=(*state.box.species_ids, 164), levels=(13, 13, 40),
        )
        return SimpleNamespace(passed=True)
    def withdraw(_actions, _reader, *, box_slot, expected_species_id):
        state.calls.append(('withdraw', box_slot, expected_species_id))
        assert box_slot == 2 and expected_species_id == 48
        state.raw = replace(state.raw, party_species_ids=(*state.raw.party_species_ids, 48))
        state.box = replace(state.box, species_ids=(185, 164), levels=(13, 40))
        return SimpleNamespace(passed=True)
    monkeypatch.setattr(support, 'deposit_party_member', deposit)
    monkeypatch.setattr(support, 'withdraw_box_member', withdraw)
    ready = replace(original, members=(*original.members[:-1],
        PartyMemberObservation(6, 48, 13, 40, 40, moves=(MoveObservation(95, 20),))))
    return plan, state, reader, ready


def test_pc_substitution_preserves_specimen_multiset_and_counts_no_training_row(monkeypatch):
    plan, state, reader, ready = fixture(monkeypatch)
    result = support.execute_capture_party_at_pc(plan, object(), reader, pc_map_id=64,
                                                read_party=lambda: ready)
    assert result == {'capture_party_prepared': True, 'specimens_preserved': 8,
                      'setup_training_rows': 0, 'new_acquisitions': 0}
    assert state.calls == ['face_pc_boundary', 'open_bills_pc', ('deposit', 6, 164),
                           ('withdraw', 2, 48), 'close_menu']


def test_stale_helper_plan_rejected_before_input(monkeypatch):
    plan, state, reader, ready = fixture(monkeypatch)
    state.raw = replace(state.raw, party_moves=((1, 0, 0, 0),)*6)
    with pytest.raises(support.RedCapturePartyError, match='before PC input'):
        support.execute_capture_party_at_pc(plan, object(), reader, pc_map_id=64,
                                            read_party=lambda: ready)
    assert state.calls == []


def test_withdrawal_does_not_assume_box_hp_is_healthy(monkeypatch):
    plan, _, reader, ready = fixture(monkeypatch)
    fainted = replace(ready, members=(*ready.members[:-1], replace(ready.members[-1], hp=0)))
    with pytest.raises(support.RedCapturePartyError, match='not actually ready'):
        support.execute_capture_party_at_pc(plan, object(), reader, pc_map_id=64,
                                            read_party=lambda: fainted)
