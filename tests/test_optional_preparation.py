from dataclasses import replace

import pytest
from test_party_preparation import team

from pokemon_red_completion.party_preparation import (
    PreparationPurpose,
    build_optional_preview_preparation_plan,
    build_preview_preparation_plan,
)


def test_preparation_is_optional_even_when_old_trigger_does_not_fire():
    members = team(17)
    old = build_preview_preparation_plan(members, (18, 21), forecast_ref="old")
    assert not old.targets
    new = build_optional_preview_preparation_plan(members, (18, 21), forecast_ref="new")
    assert new.targets == ((members[0].specimen_ref, 20),)
    assert new.evidence_basis == "cartridge_preview" and not new.observed_opponents
    assert not old.targets and new.roster == old.roster


@pytest.mark.parametrize("level,opposition,expected", [(5, 20, 8), (19, 20, 20), (20, 20, None),
                                                     (25, 20, None), (99, 100, 100)])
def test_optional_dose_never_exceeds_cap_or_parity(level, opposition, expected):
    members = team(level)
    plan = build_optional_preview_preparation_plan(members, (opposition,), forecast_ref="private")
    assert plan.targets == (() if expected is None else ((members[0].specimen_ref, expected),))


def test_optional_dose_does_not_promote_newly_caught_or_utility_members():
    members = tuple(replace(m, purpose=p, purpose_reason="existing role") for m, p in zip(
        team(17, 3, 7), (PreparationPurpose.COMBAT, PreparationPurpose.UNDECIDED,
                        PreparationPurpose.FIELD_UTILITY), strict=True))
    plan = build_optional_preview_preparation_plan(members, (18, 21), forecast_ref="private")
    assert plan.targets == ((members[0].specimen_ref, 20),)
    assert plan.roster == members


@pytest.mark.parametrize("cap", [0, 4, True, 1.5])
def test_optional_dose_rejects_unbounded_or_ambiguous_caps(cap):
    with pytest.raises(ValueError):
        build_optional_preview_preparation_plan(team(17), (21,), forecast_ref="private",
                                                maximum_level_gain=cap)
