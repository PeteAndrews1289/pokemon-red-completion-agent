from dataclasses import replace

import pytest

from pokemon_red_completion.capture_support import (
    CaptureStatusOption,
    CaptureSupportSummary,
    choose_capture_status,
)
from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    PartyObservation,
    StatusCondition,
)
from pokemon_red_completion.red_battle_catalog import RED_BATTLE_CATALOG, pokemon_red_move_ref
from pokemon_red_completion.red_capture_support import red_capture_status_options


def member(slot=1, species=48, level=20, hp=50, moves=(95, 86, 92, 34)):
    return PartyMemberObservation(
        slot, species, level, hp, 50,
        moves=tuple(MoveObservation(move, 5) for move in moves),
    )


def test_move_effects_exclude_poison_damage_and_self_sleep():
    assert RED_BATTLE_CATALOG.capture_status_effect(pokemon_red_move_ref(95)) == "sleep"
    assert RED_BATTLE_CATALOG.capture_status_effect(pokemon_red_move_ref(86)) == "paralysis"
    assert RED_BATTLE_CATALOG.capture_status_effect(pokemon_red_move_ref(147)) == "sleep"
    for move in (34, 85, 92, 156, 77, 120):
        assert RED_BATTLE_CATALOG.capture_status_effect(pokemon_red_move_ref(move)) is None
    assert RED_BATTLE_CATALOG.capture_status_effect(pokemon_red_move_ref(79)) == "sleep"


def test_capture_diagnostics_allowlist_fields_and_preserve_observed_counts():
    summary = CaptureSupportSummary(3, 1, 1)
    evidence = {'capture_support': summary.public_dict()}
    assert CaptureSupportSummary.from_evidence(evidence) == summary
    assert CaptureSupportSummary.from_evidence({}) is None
    for values in ((True, 0, 0), (1, 2, 0), (0, 0, 2), (-1, 0, 0)):
        with pytest.raises(ValueError):
            CaptureSupportSummary(*values)
    with pytest.raises(ValueError):
        CaptureSupportSummary.from_evidence({'capture_support': {
            **summary.public_dict(), 'private_path': 'must never be forwarded'}})


def test_status_options_follow_moves_not_species_and_filter_electric_immunity():
    a = red_capture_status_options(PartyObservation((member(species=48),)))
    b = red_capture_status_options(PartyObservation((member(species=164),)))
    assert a == b
    assert [(row.move_slot, row.condition) for row in a] == [
        (1, StatusCondition.SLEEP), (2, StatusCondition.PARALYSIS),
    ]
    ground = red_capture_status_options(PartyObservation((member(),)), enemy_species_id=59)
    assert [row.move_slot for row in ground] == [1]
    ghost = red_capture_status_options(
        PartyObservation((member(moves=(47,)),)), enemy_species_id=25,
    )
    assert ghost[0].condition is StatusCondition.SLEEP


def test_choose_active_then_accuracy_without_species_ranking():
    party = PartyObservation((member(), member(2, species=164, level=30, moves=(147,))))
    options = red_capture_status_options(party)
    args = dict(target_status=StatusCondition.HEALTHY, attempts_used=0)
    assert choose_capture_status(party, options, **args).party_slot == 2
    chosen = choose_capture_status(party, options, active_party_slot=1, **args)
    assert (chosen.party_slot, chosen.move_slot) == (1, 2)
    assert choose_capture_status(party, options, attempts_used=3,
                                 target_status=StatusCondition.HEALTHY) is None
    assert choose_capture_status(party, options, attempts_used=0,
                                 target_status=StatusCondition.SLEEP) is None


@pytest.mark.parametrize("condition", list(StatusCondition))
def test_already_statused_target_never_gets_relabelled(condition):
    party = PartyObservation((member(),))
    result = choose_capture_status(
        party, red_capture_status_options(party), target_status=condition, attempts_used=0,
    )
    assert (result is not None) is (condition is StatusCondition.HEALTHY)


def test_safety_pp_and_attempt_bounds_are_observed():
    for candidate in (
        member(hp=25), member(hp=0),
        replace(member(), status=StatusCondition.PARALYSIS),
        replace(member(), moves=(MoveObservation(95, 0),)),
    ):
        party = PartyObservation((candidate,))
        assert choose_capture_status(
            party, red_capture_status_options(party),
            target_status=StatusCondition.HEALTHY, attempts_used=0,
        ) is None
    party = PartyObservation((member(),))
    for value in (-1, True, 0.5):
        with pytest.raises(ValueError):
            choose_capture_status(party, (), target_status=StatusCondition.HEALTHY,
                                  attempts_used=value)
    with pytest.raises(ValueError):
        choose_capture_status(party, (
            CaptureStatusOption(2, 1, StatusCondition.SLEEP, 0.6),
        ), target_status=StatusCondition.HEALTHY, attempts_used=0)
    with pytest.raises(ValueError):
        CaptureStatusOption(1, 1, StatusCondition.POISON, 1.0)
