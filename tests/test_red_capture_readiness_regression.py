"""Discriminating regression tests for capture helper readiness and error diagnostics.

Validates that capture helper readiness strictly enforces living escort, healthy
status, HP ratio > 0.5 threshold, and usable sleep/paralysis moves, and verifies
that semantic error diagnostics clearly explain readiness failures without
exposing private paths or memory addresses.
"""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from pokemon_red_completion.observation import (
    RawGameState,
    RedBoxMoveMember,
    RedCurrentBoxState,
)
from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    PartyObservation,
    StatusCondition,
)
from pokemon_red_completion.red_capture_party import (
    RedCapturePartyError,
    capture_party_ready,
    execute_capture_party_at_pc,
    explain_capture_party_unready,
    plan_capture_party,
)


def _base_escort_members() -> tuple[PartyMemberObservation, ...]:
    """Five healthy escort members with field moves and combat moves, but no status moves."""
    return (
        PartyMemberObservation(
            slot=1,
            species_id=28,
            level=63,
            hp=50,
            max_hp=50,
            status=StatusCondition.HEALTHY,
            moves=(
                MoveObservation(move_id=57, current_pp=15),  # Surf (field move)
                MoveObservation(move_id=70, current_pp=15),  # Strength (field move)
                MoveObservation(move_id=1, current_pp=35),  # Pound
            ),
        ),
        PartyMemberObservation(
            slot=2,
            species_id=64,
            level=55,
            hp=50,
            max_hp=50,
            status=StatusCondition.HEALTHY,
            moves=(
                MoveObservation(move_id=15, current_pp=30),  # Cut (field move)
                MoveObservation(move_id=19, current_pp=15),  # Fly (field move)
                MoveObservation(move_id=1, current_pp=35),  # Pound
            ),
        ),
        PartyMemberObservation(
            slot=3,
            species_id=118,
            level=55,
            hp=50,
            max_hp=50,
            status=StatusCondition.HEALTHY,
            moves=(
                MoveObservation(move_id=89, current_pp=10),
                MoveObservation(move_id=1, current_pp=35),
            ),
        ),
        PartyMemberObservation(
            slot=4,
            species_id=132,
            level=55,
            hp=50,
            max_hp=50,
            status=StatusCondition.HEALTHY,
            moves=(
                MoveObservation(move_id=34, current_pp=15),
                MoveObservation(move_id=1, current_pp=35),
            ),
        ),
        PartyMemberObservation(
            slot=5,
            species_id=104,
            level=55,
            hp=50,
            max_hp=50,
            status=StatusCondition.HEALTHY,
            moves=(
                MoveObservation(move_id=84, current_pp=20),
                MoveObservation(move_id=1, current_pp=35),
            ),
        ),
    )


def _make_party_with_helper(
    *,
    helper_slot: int = 6,
    helper_species: int = 48,
    helper_level: int = 13,
    helper_hp: int = 50,
    helper_max_hp: int = 50,
    helper_status: StatusCondition = StatusCondition.HEALTHY,
    helper_moves: tuple[MoveObservation, ...] = (
        MoveObservation(move_id=95, current_pp=20),  # Hypnosis (sleep move)
        MoveObservation(move_id=1, current_pp=35),  # Pound
    ),
) -> PartyObservation:
    """Build a 6-member party containing 5 escorts and 1 candidate capture helper."""
    helper = PartyMemberObservation(
        slot=helper_slot,
        species_id=helper_species,
        level=helper_level,
        hp=helper_hp,
        max_hp=helper_max_hp,
        status=helper_status,
        moves=helper_moves,
    )
    return PartyObservation((*_base_escort_members(), helper))


def _make_boxed_helper(
    *,
    box_slot: int = 2,
    species_id: int = 48,
    level: int = 13,
    moves: tuple[int, ...] = (1, 95, 50, 0),
    pp: tuple[int, ...] = (35, 20, 20, 0),
) -> RedBoxMoveMember:
    """A boxed mon representation containing only box inventory: no fabricated HP."""
    return RedBoxMoveMember(
        box_slot=box_slot,
        species_id=species_id,
        level=level,
        moves=moves,
        pp=pp,
    )


def test_zero_pp_helper_fails_capture_readiness():
    """A helper with a sleep move but 0 remaining PP cannot provide capture support."""
    party = _make_party_with_helper(
        helper_moves=(
            MoveObservation(move_id=95, current_pp=0),  # Hypnosis exhausted
            MoveObservation(move_id=1, current_pp=35),
        ),
    )
    assert capture_party_ready(party) is False

    boxed = _make_boxed_helper()
    diag = explain_capture_party_unready(party, boxed)
    assert "status moves out of PP (move 95)" in diag
    assert "party has no usable sleep/paralysis moves" in diag


def test_unsuitable_moves_helper_fails_capture_readiness():
    """A helper without any sleep or paralysis move cannot provide capture support."""
    party = _make_party_with_helper(
        helper_moves=(
            MoveObservation(move_id=33, current_pp=35),  # Tackle
            MoveObservation(move_id=77, current_pp=35),  # Poison Powder (not sleep/paralysis)
        ),
    )
    assert capture_party_ready(party) is False

    boxed = _make_boxed_helper()
    diag = explain_capture_party_unready(party, boxed)
    assert "unsuitable moves (no sleep/paralysis move)" in diag
    assert "party has no usable sleep/paralysis moves" in diag


def test_fainted_helper_fails_capture_readiness():
    """A fainted helper (hp=0) with full PP cannot provide capture support."""
    party = _make_party_with_helper(
        helper_hp=0,
        helper_max_hp=50,
        helper_moves=(MoveObservation(move_id=95, current_pp=20),),
    )
    assert capture_party_ready(party) is False

    boxed = _make_boxed_helper()
    diag = explain_capture_party_unready(party, boxed)
    assert "fainted (hp 0/50)" in diag
    assert "slot 6 (fainted)" in diag


def test_low_hp_helper_below_half_fails_capture_readiness():
    """A helper with HP ratio strictly below 0.50 (e.g. 20/50 = 40%) is not ready."""
    party = _make_party_with_helper(
        helper_hp=20,
        helper_max_hp=50,
        helper_moves=(MoveObservation(move_id=95, current_pp=20),),
    )
    assert capture_party_ready(party) is False

    boxed = _make_boxed_helper()
    diag = explain_capture_party_unready(party, boxed)
    assert "low HP (20/50 = 40.0%, requires > 50.0%)" in diag
    assert "HP 40.0% <= 50%" in diag


def test_exact_half_hp_threshold_boundary():
    """Readiness requires hp_ratio > 0.5 strictly: 50.0% fails, 52.0% succeeds."""
    # Exactly 50.0% HP (25 / 50): strictly fails the > 0.50 threshold
    party_half = _make_party_with_helper(
        helper_hp=25,
        helper_max_hp=50,
        helper_moves=(MoveObservation(move_id=95, current_pp=20),),
    )
    assert capture_party_ready(party_half) is False

    boxed = _make_boxed_helper()
    diag_half = explain_capture_party_unready(party_half, boxed)
    assert "low HP (25/50 = 50.0%, requires > 50.0%)" in diag_half

    # Above 50.0% HP (26 / 50 = 52.0%): satisfies the > 0.50 threshold
    party_above = _make_party_with_helper(
        helper_hp=26,
        helper_max_hp=50,
        helper_moves=(MoveObservation(move_id=95, current_pp=20),),
    )
    assert capture_party_ready(party_above) is True


@pytest.mark.parametrize(
    "status_condition",
    [
        StatusCondition.POISON,
        StatusCondition.BURN,
        StatusCondition.SLEEP,
        StatusCondition.PARALYSIS,
        StatusCondition.FREEZE,
        StatusCondition.TOXIC,
    ],
)
def test_status_afflicted_helper_fails_capture_readiness(status_condition: StatusCondition):
    """Any non-healthy persistent status disqualifies a capture helper despite full HP and PP."""
    party = _make_party_with_helper(
        helper_hp=50,
        helper_max_hp=50,
        helper_status=status_condition,
        helper_moves=(MoveObservation(move_id=95, current_pp=20),),
    )
    assert capture_party_ready(party) is False

    boxed = _make_boxed_helper()
    diag = explain_capture_party_unready(party, boxed)
    assert f"status condition '{status_condition.value}'" in diag
    assert f"status '{status_condition.value}'" in diag


def test_changed_party_state_species_mismatch():
    """When the withdrawn slot does not contain the expected helper, diagnostics report mismatch."""
    party = _make_party_with_helper(
        helper_species=164,  # Pidgeot instead of expected Venonat (48)
        helper_moves=(MoveObservation(move_id=1, current_pp=35),),
    )
    boxed = _make_boxed_helper(species_id=48)
    diag = explain_capture_party_unready(party, boxed)
    assert "expected helper species 48 not found in party (last slot 6 is species 164)" in diag


def test_empty_party_state_diagnostic():
    """An empty party observation reports that party has no members."""
    empty = PartyObservation(())
    assert capture_party_ready(empty) is False
    diag = explain_capture_party_unready(empty)
    assert diag == "party has no members"


def _mock_pc_fixture(monkeypatch, withdrawn_member: PartyMemberObservation):
    """Set up PC execution mocks returning a specific withdrawn member in party."""
    initial_party = PartyObservation(
        (
            *_base_escort_members(),
            PartyMemberObservation(
                slot=6,
                species_id=164,
                level=40,
                hp=50,
                max_hp=50,
                status=StatusCondition.HEALTHY,
                moves=(MoveObservation(move_id=83, current_pp=10),),
            ),
        )
    )
    box_mon = (
        RedBoxMoveMember(1, 185, 13, (71, 0, 0, 0), (20, 0, 0, 0)),
        _make_boxed_helper(box_slot=2, species_id=48, level=13),
    )
    plan = plan_capture_party(initial_party, box_mon, box_index=0)
    assert plan is not None

    state = SimpleNamespace(
        raw=RawGameState(
            True,
            64,
            13,
            4,
            6,
            0,
            party_species_ids=plan.party_species_ids,
            party_moves=plan.party_moves,
            bag_items=((4, 4),),
            player_money=1109,
        ),
        box=RedCurrentBoxState(
            0,
            tuple(r.species_id for r in box_mon),
            tuple(r.level for r in box_mon),
        ),
        calls=[],
    )
    reader = SimpleNamespace(
        read=lambda: state.raw,
        read_current_box_state=lambda: state.box,
        read_current_box_move_members=lambda: box_mon,
        read_input_readiness=lambda: SimpleNamespace(ready=True),
    )

    import pokemon_red_completion.red_capture_party as party_module

    for name in ("face_pc_boundary", "open_bills_pc", "close_menu"):
        monkeypatch.setattr(party_module, name, lambda *_a, _n=name: state.calls.append(_n))

    def deposit(_actions, _reader, *, party_slot, expected_species_id):
        state.calls.append(("deposit", party_slot, expected_species_id))
        state.raw = replace(state.raw, party_species_ids=state.raw.party_species_ids[:-1])
        state.box = replace(
            state.box,
            species_ids=(*state.box.species_ids, expected_species_id),
            levels=(13, 13, 40),
        )
        return SimpleNamespace(passed=True)

    def withdraw(_actions, _reader, *, box_slot, expected_species_id):
        state.calls.append(("withdraw", box_slot, expected_species_id))
        state.raw = replace(
            state.raw, party_species_ids=(*state.raw.party_species_ids, expected_species_id)
        )
        state.box = replace(state.box, species_ids=(185, 164), levels=(13, 40))
        return SimpleNamespace(passed=True)

    monkeypatch.setattr(party_module, "deposit_party_member", deposit)
    monkeypatch.setattr(party_module, "withdraw_box_member", withdraw)

    party_after_withdraw = PartyObservation((*_base_escort_members(), withdrawn_member))
    return plan, reader, party_after_withdraw


def test_execute_capture_party_at_pc_reports_fainted_diagnostic(monkeypatch):
    """execute_capture_party_at_pc includes fainted diagnostic in error message."""
    fainted_helper = PartyMemberObservation(
        slot=6,
        species_id=48,
        level=13,
        hp=0,
        max_hp=40,
        status=StatusCondition.HEALTHY,
        moves=(MoveObservation(move_id=95, current_pp=20),),
    )
    plan, reader, party = _mock_pc_fixture(monkeypatch, fainted_helper)
    with pytest.raises(RedCapturePartyError) as exc_info:
        execute_capture_party_at_pc(plan, object(), reader, pc_map_id=64, read_party=lambda: party)
    err = str(exc_info.value)
    assert err.startswith("withdrawn capture helper is not actually ready: ")
    assert "fainted (hp 0/40)" in err


def test_execute_capture_party_at_pc_reports_low_hp_diagnostic(monkeypatch):
    """execute_capture_party_at_pc includes exact low HP diagnostic in error message."""
    low_hp_helper = PartyMemberObservation(
        slot=6,
        species_id=48,
        level=13,
        hp=20,
        max_hp=40,  # 50.0% exactly
        status=StatusCondition.HEALTHY,
        moves=(MoveObservation(move_id=95, current_pp=20),),
    )
    plan, reader, party = _mock_pc_fixture(monkeypatch, low_hp_helper)
    with pytest.raises(RedCapturePartyError) as exc_info:
        execute_capture_party_at_pc(plan, object(), reader, pc_map_id=64, read_party=lambda: party)
    err = str(exc_info.value)
    assert err.startswith("withdrawn capture helper is not actually ready: ")
    assert "low HP (20/40 = 50.0%, requires > 50.0%)" in err


def test_execute_capture_party_at_pc_reports_status_diagnostic(monkeypatch):
    """execute_capture_party_at_pc includes status condition diagnostic in error message."""
    poisoned_helper = PartyMemberObservation(
        slot=6,
        species_id=48,
        level=13,
        hp=40,
        max_hp=40,
        status=StatusCondition.POISON,
        moves=(MoveObservation(move_id=95, current_pp=20),),
    )
    plan, reader, party = _mock_pc_fixture(monkeypatch, poisoned_helper)
    with pytest.raises(RedCapturePartyError) as exc_info:
        execute_capture_party_at_pc(plan, object(), reader, pc_map_id=64, read_party=lambda: party)
    err = str(exc_info.value)
    assert err.startswith("withdrawn capture helper is not actually ready: ")
    assert "status condition 'poison'" in err


def test_execute_capture_party_at_pc_reports_zero_pp_diagnostic(monkeypatch):
    """execute_capture_party_at_pc includes zero-PP diagnostic in error message."""
    zero_pp_helper = PartyMemberObservation(
        slot=6,
        species_id=48,
        level=13,
        hp=40,
        max_hp=40,
        status=StatusCondition.HEALTHY,
        moves=(MoveObservation(move_id=95, current_pp=0),),
    )
    plan, reader, party = _mock_pc_fixture(monkeypatch, zero_pp_helper)
    with pytest.raises(RedCapturePartyError) as exc_info:
        execute_capture_party_at_pc(plan, object(), reader, pc_map_id=64, read_party=lambda: party)
    err = str(exc_info.value)
    assert err.startswith("withdrawn capture helper is not actually ready: ")
    assert "status moves out of PP (move 95)" in err


def test_execute_capture_party_at_pc_reports_unsuitable_moves_diagnostic(monkeypatch):
    """execute_capture_party_at_pc includes unsuitable moves diagnostic in error message."""
    unsuitable_helper = PartyMemberObservation(
        slot=6,
        species_id=48,
        level=13,
        hp=40,
        max_hp=40,
        status=StatusCondition.HEALTHY,
        moves=(MoveObservation(move_id=33, current_pp=35),),  # Tackle only
    )
    plan, reader, party = _mock_pc_fixture(monkeypatch, unsuitable_helper)
    with pytest.raises(RedCapturePartyError) as exc_info:
        execute_capture_party_at_pc(plan, object(), reader, pc_map_id=64, read_party=lambda: party)
    err = str(exc_info.value)
    assert err.startswith("withdrawn capture helper is not actually ready: ")
    assert "unsuitable moves (no sleep/paralysis move)" in err


def test_execute_capture_party_at_pc_succeeds_when_helper_is_ready(monkeypatch):
    """execute_capture_party_at_pc succeeds when the withdrawn helper is healthy and has PP."""
    ready_helper = PartyMemberObservation(
        slot=6,
        species_id=48,
        level=13,
        hp=40,
        max_hp=40,
        status=StatusCondition.HEALTHY,
        moves=(MoveObservation(move_id=95, current_pp=20),),
    )
    plan, reader, party = _mock_pc_fixture(monkeypatch, ready_helper)
    result = execute_capture_party_at_pc(
        plan,
        object(),
        reader,
        pc_map_id=64,
        read_party=lambda: party,
    )
    assert result["capture_party_prepared"] is True
    assert result["specimens_preserved"] == 8
    assert result["setup_training_rows"] == 0
    assert result["new_acquisitions"] == 0
