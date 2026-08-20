import pytest

from pokemon_red_completion.participation import summarize_party_participation


def test_participation_exposes_single_member_dominance() -> None:
    report = summarize_party_participation((0, 0, 0, 0, 0, 0), party_size=6)

    assert report.public_dict() == {
        "turns_per_member": [6, 0, 0, 0, 0, 0],
        "observed_turns": 6,
        "unobserved_turns": 0,
        "participating_members": 1,
        "busiest_member_turns": 6,
        "busiest_member_share": 1.0,
    }


def test_participation_keeps_unknown_and_invalid_indexes_visible() -> None:
    report = summarize_party_participation((0, 2, None, -1, 6), party_size=6)

    assert report.turns_per_member == (1, 0, 1, 0, 0, 0)
    assert report.observed_turns == 2
    assert report.total_turns == 5
    assert report.unobserved_turns == 3
    assert report.participating_members == 2
    assert report.busiest_member_share == 0.5


def test_participation_rejects_an_empty_party() -> None:
    with pytest.raises(ValueError, match="party_size must be positive"):
        summarize_party_participation((), party_size=0)
