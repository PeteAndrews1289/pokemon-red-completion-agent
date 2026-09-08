from dataclasses import replace
from types import SimpleNamespace

import pytest

import pokemon_red_completion.red_field_party as module
from pokemon_red_completion.observation import (
    RawGameState,
    RedBoxCollectionState,
    RedBoxMoveMember,
    RedCurrentBoxState,
)
from pokemon_red_completion.party import MoveObservation, PartyMemberObservation, PartyObservation


def fixture():
    party = PartyObservation(
        tuple(
            PartyMemberObservation(
                i,
                species,
                level,
                70,
                80,
                moves=tuple(MoveObservation(m, 10 if m else 0) for m in moves),
            )
            for i, species, level, moves in (
                (1, 28, 66, (57, 70, 58, 66)),
                (2, 104, 55, (87, 84, 98, 28)),
                (3, 118, 55, (91, 89, 45, 28)),
                (4, 48, 13, (95, 1, 50, 0)),
                (5, 132, 55, (34, 38, 156, 133)),
                (6, 141, 30, (49, 120, 103, 113)),
            )
        )
    )
    helper = RedBoxMoveMember(2, 64, 55, (163, 28, 15, 19), (20, 15, 30, 15))
    inventories = (
        (RedBoxMoveMember(1, 48, 15, (1, 0, 0, 0), (10, 0, 0, 0)), helper),
        (),
        *([()] * 10),
    )
    boxes = RedBoxCollectionState(
        tuple(
            RedCurrentBoxState(i, tuple(m.species_id for m in rows), tuple(m.level for m in rows))
            for i, rows in enumerate(inventories)
        ),
        1,
        True,
    )
    return party, boxes, inventories


def test_capabilities_preserved_instead_of_depositing_lowest_level():
    party, boxes, inventory = fixture()
    plan = module.plan_field_party(party, boxes, inventory, move_id=19)
    assert plan.deposit_slot == 6  # Keep level13 sleep helper, all field carriers and escort.
    assert plan.target_box == 0 and plan.helper.box_slot == 2
    changed = replace(party, members=tuple(replace(m, species_id=1) for m in party.members))
    assert module.plan_field_party(changed, boxes, inventory, move_id=19).deposit_slot == 6


def test_changed_party_slot_moves_the_deposit_choice():
    party, boxes, inventory = fixture()
    members = list(party.members)
    members[4], members[5] = replace(members[5], slot=5), replace(members[4], slot=6)
    assert (
        module.plan_field_party(
            replace(party, members=tuple(members)), boxes, inventory, move_id=19
        ).deposit_slot
        == 5
    )


def test_full_party_box_capacity_and_stale_inventory_fail_closed():
    party, boxes, inventory = fixture()
    with pytest.raises(module.RedFieldPartyError, match="differs"):
        module.plan_field_party(party, boxes, ((), *inventory[1:]), move_id=19)
    full = tuple(replace(inventory[0][0], box_slot=i) for i in range(1, 21))
    expanded = replace(
        boxes,
        boxes=(boxes.boxes[0], RedCurrentBoxState(1, (48,) * 20, (15,) * 20), *boxes.boxes[2:]),
    )
    with pytest.raises(module.RedFieldPartyError, match="capacity"):
        module.plan_field_party(party, expanded, (inventory[0], full, *inventory[2:]), move_id=19)


def test_existing_holder_needs_no_pc_and_small_party_needs_no_deposit():
    party, boxes, inventory = fixture()
    assert module.plan_field_party(party, boxes, inventory, move_id=57) is None
    smaller = replace(party, members=party.members[:-1])
    assert module.plan_field_party(smaller, boxes, inventory, move_id=19).deposit_slot is None


def world(monkeypatch, fault=""):
    party, boxes, inventory = fixture()
    plan = module.plan_field_party(party, boxes, inventory, move_id=19)
    state = SimpleNamespace(
        party=party,
        boxes=boxes,
        inventory=list(inventory),
        active=False,
        calls=[],
        raw=RawGameState(
            True, 64, 13, 4, 6, 0, bag_items=((16, 4),), player_money=619, event_flags=b"\0" * 320
        ),
    )
    reader = SimpleNamespace(
        read=lambda: state.raw,
        read_all_box_states=lambda: state.boxes,
        read_box_move_members=lambda i: state.inventory[i],
        read_generic_pc_session_active=lambda: state.active,
        read_input_readiness=lambda: SimpleNamespace(ready=True),
    )

    def face(*_args):
        state.calls.append("face")

    def open_pc(*_args):
        state.calls.append("open")
        state.active = True

    def close(*_args):
        state.calls.append("close")
        state.active = False
        if fault == "money":
            state.raw = replace(state.raw, player_money=600)
        if fault == "retained_hp":
            state.party = replace(
                state.party,
                members=(replace(state.party.members[0], hp=1), *state.party.members[1:]),
            )

    def deposit(*_args, party_slot, expected_species_id):
        state.calls.append("deposit")
        assert party_slot == 6 and expected_species_id == 141
        state.party = replace(state.party, members=state.party.members[:-1])
        current = RedCurrentBoxState(1, (141,), (30,))
        state.boxes = replace(
            state.boxes, boxes=(state.boxes.boxes[0], current, *state.boxes.boxes[2:])
        )
        if fault == "deposit_interruption":
            raise RuntimeError("interrupted after deposit")
        return SimpleNamespace(passed=True)

    def switch(*_args, target_box_index):
        state.calls.append("switch")
        assert target_box_index == 0
        state.boxes = replace(state.boxes, current_box_index=0)
        if fault == "helper_changed":
            state.inventory[0] = (
                inventory[0][0],
                replace(plan.helper, moves=(1, 0, 0, 0), pp=(10, 0, 0, 0)),
            )
        return SimpleNamespace(passed=True)

    def withdraw(*_args, box_slot, expected_species_id):
        state.calls.append("withdraw")
        assert box_slot == 2 and expected_species_id == 64
        helper = PartyMemberObservation(
            6,
            64,
            55,
            0 if fault == "fainted" else 90,
            100,
            moves=tuple(
                MoveObservation(m, pp)
                for m, pp in zip(plan.helper.moves, plan.helper.pp, strict=True)
            ),
        )
        state.party = replace(state.party, members=(*state.party.members, helper))
        target = RedCurrentBoxState(0, (48,), (15,))
        state.boxes = replace(state.boxes, boxes=(target, *state.boxes.boxes[1:]))
        if fault == "box_loss":
            state.boxes = replace(
                state.boxes, boxes=(target, RedCurrentBoxState(1, (), ()), *state.boxes.boxes[2:])
            )
        return SimpleNamespace(passed=True)

    for name, fun in (
        ("face_pc_boundary", face),
        ("open_bills_pc", open_pc),
        ("close_generic_pc_session", close),
        ("deposit_party_member", deposit),
        ("switch_box", switch),
        ("withdraw_box_member", withdraw),
    ):
        monkeypatch.setattr(module, name, fun)
    return plan, reader, state


def execute(plan, reader, state):
    return module.retrieve_field_party_at_pc(
        plan, object(), reader, pc_map=64, read_party=lambda: state.party
    )


def test_cross_box_retrieval_keeps_every_species_and_has_no_training_label(monkeypatch):
    plan, reader, state = world(monkeypatch)
    result = execute(plan, reader, state)
    assert state.calls == ["face", "open", "deposit", "switch", "withdraw", "close"]
    assert state.boxes.boxes[1].species_ids == (141,)
    assert state.boxes.boxes[0].species_ids == (48,)
    assert result["setup_training_rows"] == 0 and result["collection_preserved"]


def test_forged_protected_deposit_is_rejected_before_input(monkeypatch):
    plan, reader, state = world(monkeypatch)
    with pytest.raises(module.RedFieldPartyError, match="safe substitution"):
        execute(replace(plan, deposit_slot=4), reader, state)
    assert state.calls == []


@pytest.mark.parametrize("fault", ["fainted", "money", "retained_hp", "box_loss"])
def test_postcondition_failure_never_releases_or_retries(monkeypatch, fault):
    plan, reader, state = world(monkeypatch, fault)
    with pytest.raises(module.RedFieldPartyError):
        execute(plan, reader, state)
    assert state.calls.count("deposit") == state.calls.count("withdraw") == 1


@pytest.mark.parametrize(
    "fault,last", [("deposit_interruption", "deposit"), ("helper_changed", "switch")]
)
def test_partial_operations_stop_at_the_first_failed_boundary(monkeypatch, fault, last):
    plan, reader, state = world(monkeypatch, fault)
    with pytest.raises(RuntimeError):
        execute(plan, reader, state)
    assert state.calls[-1] == last and "withdraw" not in state.calls
