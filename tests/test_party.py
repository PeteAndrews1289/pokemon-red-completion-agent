import pytest

from pokemon_red_completion.party import (
    MAX_LEVEL,
    MOVE_SLOT_LIMIT,
    PARTY_SLOT_LIMIT,
    MoveObservation,
    PartyMemberObservation,
    PartyObservation,
    PartyRole,
    StatusCondition,
)


def move(move_id: int = 55, current_pp: int = 15, max_pp: int | None = 15) -> MoveObservation:
    return MoveObservation(move_id=move_id, current_pp=current_pp, max_pp=max_pp)


def member(slot: int = 1, **changes: object) -> PartyMemberObservation:
    values: dict[str, object] = {
        "slot": slot,
        "species_id": 0x09,
        "level": 50,
        "hp": 150,
        "max_hp": 160,
        "moves": (move(), move(57, 10, 10)),
    }
    values.update(changes)
    return PartyMemberObservation(**values)  # type: ignore[arg-type]


def party(
    levels: tuple[int, ...] = (50, 51, 52, 53, 54, 55),
    **changes: object,
) -> PartyObservation:
    members = tuple(
        member(slot=index, level=level, species_id=index, **changes)
        for index, level in enumerate(levels, start=1)
    )
    return PartyObservation(members=members)


# --- membership and active-party position -----------------------------------


def test_party_reports_membership_size_capacity_and_open_slots() -> None:
    full = party()
    assert full.size == PARTY_SLOT_LIMIT
    assert full.is_complete
    assert not full.is_incomplete
    assert full.open_slots == 0

    partial = party((50, 52))
    assert partial.size == 2
    assert partial.is_incomplete
    assert not partial.is_complete
    assert partial.open_slots == 4


def test_empty_party_is_legal_and_reports_incomplete_without_metrics() -> None:
    empty = PartyObservation()
    assert empty.size == 0
    assert empty.is_incomplete
    assert empty.open_slots == PARTY_SLOT_LIMIT
    assert empty.lead is None
    assert empty.minimum_level is None
    assert empty.maximum_level is None
    assert empty.level_spread is None
    assert empty.average_level is None
    assert empty.fainted_count == 0
    assert empty.weakest_trainable_member is None
    assert not empty.is_wiped_out


def test_active_party_position_is_one_based_contiguous_and_addressable() -> None:
    full = party()
    assert full.lead is not None
    assert full.lead.slot == 1
    assert full.member_in_slot(4) is full.members[3]
    assert full.member_in_slot(PARTY_SLOT_LIMIT + 1) is None

    with pytest.raises(ValueError, match="contiguous one-based slots"):
        PartyObservation(members=(member(slot=2),))
    with pytest.raises(ValueError, match="contiguous one-based slots"):
        PartyObservation(members=(member(slot=1), member(slot=3)))
    with pytest.raises(ValueError, match="one-based position"):
        member(slot=PARTY_SLOT_LIMIT + 1)
    with pytest.raises(ValueError, match="one-based position"):
        member(slot=0)


def test_party_rejects_more_members_than_capacity() -> None:
    with pytest.raises(ValueError, match="capacity"):
        PartyObservation(members=tuple(member(slot=index) for index in range(1, 4)), capacity=2)
    with pytest.raises(ValueError, match="capacity must be"):
        PartyObservation(capacity=PARTY_SLOT_LIMIT + 1)


# --- species, level, health, status -----------------------------------------


def test_party_reports_species_membership() -> None:
    full = party()
    assert full.species_ids() == (1, 2, 3, 4, 5, 6)
    assert full.has_species(3)
    assert not full.has_species(99)

    with pytest.raises(ValueError, match="species_id"):
        member(species_id=0)


def test_member_level_is_bounded() -> None:
    assert member(level=MAX_LEVEL).level == MAX_LEVEL
    with pytest.raises(ValueError, match="level must be between"):
        member(level=0)
    with pytest.raises(ValueError, match="level must be between"):
        member(level=MAX_LEVEL + 1)


def test_member_health_ratio_and_faint_state() -> None:
    healthy = member(hp=160, max_hp=160)
    assert healthy.hp_ratio == 1.0
    assert not healthy.is_fainted

    hurt = member(hp=40, max_hp=160)
    assert hurt.hp_ratio == pytest.approx(0.25)
    assert not hurt.is_fainted

    fainted = member(hp=0, max_hp=160)
    assert fainted.hp_ratio == 0.0
    assert fainted.is_fainted
    assert not fainted.can_battle

    with pytest.raises(ValueError, match="hp must be between"):
        member(hp=200, max_hp=160)
    with pytest.raises(ValueError, match="max_hp must be"):
        member(max_hp=0)


def test_member_status_is_a_typed_condition_and_survives_fainting() -> None:
    poisoned = member(status=StatusCondition.POISON)
    assert poisoned.status is StatusCondition.POISON
    assert poisoned.can_battle

    fainted_and_burned = member(hp=0, status=StatusCondition.BURN)
    assert fainted_and_burned.is_fainted
    assert fainted_and_burned.status is StatusCondition.BURN

    with pytest.raises(TypeError, match="StatusCondition"):
        member(status="poison")


# --- moves ------------------------------------------------------------------


def test_move_reports_known_and_usable_state() -> None:
    assert move().is_known
    assert move().is_usable
    assert not move(move_id=0, current_pp=0, max_pp=0).is_known
    assert not move(current_pp=0).is_usable

    with pytest.raises(ValueError, match="current_pp cannot exceed max_pp"):
        MoveObservation(move_id=55, current_pp=20, max_pp=15)
    with pytest.raises(ValueError, match="non-negative"):
        MoveObservation(move_id=55, current_pp=-1)


def test_member_move_derivations_separate_known_usable_and_total_pp() -> None:
    subject = member(
        moves=(move(55, 15), move(57, 0), move(0, 0, 0), move(58, 5)),
    )
    assert len(subject.known_moves) == 3
    assert tuple(entry.move_id for entry in subject.usable_moves) == (55, 58)
    assert subject.total_pp == 20
    assert subject.can_battle

    no_pp = member(moves=(move(55, 0), move(57, 0)))
    assert no_pp.total_pp == 0
    assert not no_pp.can_battle
    assert not no_pp.is_trainable

    with pytest.raises(ValueError, match="more than"):
        member(moves=tuple(move() for _ in range(MOVE_SLOT_LIMIT + 1)))
    with pytest.raises(TypeError, match="MoveObservation"):
        member(moves=(55,))


# --- experience and level progress ------------------------------------------


def test_level_progress_is_none_without_a_complete_experience_window() -> None:
    assert member().level_progress is None
    assert member(experience=1_000).level_progress is None
    assert member(experience=1_000, experience_floor=900).level_progress is None
    assert member(experience=1_000, experience_next=1_100).level_progress is None


def test_level_progress_is_a_clamped_fraction_when_the_curve_is_known() -> None:
    subject = member(experience=1_050, experience_floor=1_000, experience_next=1_100)
    assert subject.level_progress == pytest.approx(0.5)

    at_floor = member(experience=1_000, experience_floor=1_000, experience_next=1_100)
    assert at_floor.level_progress == pytest.approx(0.0)

    overflowing = member(experience=9_999, experience_floor=1_000, experience_next=1_100)
    assert overflowing.level_progress == pytest.approx(1.0)


def test_experience_window_is_validated() -> None:
    with pytest.raises(ValueError, match="experience must be"):
        member(experience=-1)
    with pytest.raises(ValueError, match="experience_next must exceed"):
        member(experience=10, experience_floor=100, experience_next=100)


# --- derived team metrics ---------------------------------------------------


def test_team_level_metrics_report_minimum_maximum_spread_and_average() -> None:
    subject = party((48, 50, 52, 52, 54, 56))
    assert subject.minimum_level == 48
    assert subject.maximum_level == 56
    assert subject.level_spread == 8
    assert subject.average_level == pytest.approx(52.0)
    assert subject.levels == (48, 50, 52, 52, 54, 56)


def test_level_balance_and_minimum_level_gates() -> None:
    balanced = party((50, 51, 52, 53, 54, 55))
    assert balanced.is_level_balanced(5)
    assert balanced.meets_minimum_level(50)
    assert not balanced.meets_minimum_level(51)

    spread_out = party((44, 50, 52, 53, 54, 60))
    assert not spread_out.is_level_balanced(5)
    assert not spread_out.meets_minimum_level(50)
    assert tuple(entry.level for entry in spread_out.members_below_level(50)) == (44,)

    incomplete = party((50, 51))
    assert not incomplete.meets_minimum_level(50)

    with pytest.raises(ValueError, match="maximum_spread"):
        balanced.is_level_balanced(-1)


def test_fainted_and_battle_ready_counts_track_health_and_pp() -> None:
    members = (
        member(slot=1, level=50),
        member(slot=2, level=51, hp=0),
        member(slot=3, level=52, moves=(move(55, 0),)),
        member(slot=4, level=53),
    )
    subject = PartyObservation(members=members)
    assert subject.fainted_count == 1
    assert subject.battle_ready_count == 2
    assert not subject.is_wiped_out


def test_wiped_out_party_has_no_member_able_to_act() -> None:
    subject = PartyObservation(
        members=(member(slot=1, hp=0), member(slot=2, hp=0)),
    )
    assert subject.is_wiped_out
    assert subject.fainted_count == 2
    assert subject.weakest_trainable_member is None


def test_weakest_trainable_member_skips_unusable_members_and_breaks_ties_by_slot() -> None:
    subject = PartyObservation(
        members=(
            member(slot=1, level=52),
            member(slot=2, level=44, hp=0),
            member(slot=3, level=47),
            member(slot=4, level=47),
            member(slot=5, level=45, moves=(move(55, 0),)),
        )
    )
    weakest = subject.weakest_trainable_member
    assert weakest is not None
    assert weakest.level == 47
    assert weakest.slot == 3


def test_members_at_the_level_ceiling_are_not_trainable() -> None:
    capped = member(level=MAX_LEVEL)
    assert capped.can_battle
    assert not capped.is_trainable
    assert PartyObservation(members=(capped,)).weakest_trainable_member is None


def test_party_roles_are_species_neutral_labels() -> None:
    assert len(set(PartyRole)) == PARTY_SLOT_LIMIT
    assert PartyRole.FIELD_UTILITY.value == "field_utility"
