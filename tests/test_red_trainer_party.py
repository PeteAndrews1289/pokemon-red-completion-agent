"""Non-uniform mechanic cases, not a fixture built from production thresholds."""

from dataclasses import replace

import pytest

from pokemon_red_completion.gen1_trainer_parties import TrainerPartyMember, TrainerPartyQuote
from pokemon_red_completion.party import (
    MoveObservation,
    PartyMemberObservation,
    PartyObservation,
    StatusCondition,
)
from pokemon_red_completion.red_trainer_party import (
    RedTrainerPartyError,
    plan_trainer_party,
    prepare_trainer_lead,
    trainer_matchup_candidates,
)


def party():
    # Jolteon has electric offense; Blastoise has water and ice. Neither fixture
    # depends on the planner's constants or recorded real-run outputs.
    return PartyObservation((
        PartyMemberObservation(1, 104, 55, 160, 160, moves=(MoveObservation(87, 10),)),
        PartyMemberObservation(2, 28, 55, 190, 190,
                               moves=(MoveObservation(57, 15), MoveObservation(58, 10))),
    ))


def quote(*opponents):
    members = tuple(TrainerPartyMember(internal, dex, level) for internal, dex, level in opponents)
    return TrainerPartyQuote(244, 1, members, 100, 100 * members[-1].level)


def test_opponent_mechanics_change_preference_without_chapter_rules():
    # Gyarados: electric is 4x; Onix: electric is immune, water is 4x.
    plan = plan_trainer_party(party(), quote((22, 130, 55), (34, 95, 55)))
    assert [rows[0].party_slot for rows in plan.matchups] == [1, 2]
    assert [row.party_slot for row in plan.matchups[1]] == [2]
    assert plan.lead.target_index == 0
    reversed_opponents = plan_trainer_party(party(), quote((34, 95, 55), (22, 130, 55)))
    assert reversed_opponents.lead.target_index == 1
    assert reversed_opponents.lead.requires_swap
    report = reversed_opponents.public_dict()
    assert report["training_examples"] == 0
    assert report["victory_predicted"] is report["battle_execution_qualified"] is False


def test_party_permutation_follows_capability_not_slot():
    observed = party()
    moved = PartyObservation(tuple(
        replace(member, slot=index + 1) for index, member in enumerate(reversed(observed.members))
    ))
    trainer = quote((22, 130, 55), (34, 95, 55))
    first, second = plan_trainer_party(observed, trainer), plan_trainer_party(moved, trainer)
    assert first.lead.target_member.species_id == second.lead.target_member.species_id == 104
    assert first.lead.target_index == 0 and second.lead.target_index == 1
    assert [rows[0].party_slot for rows in second.matchups] == [2, 1]


def test_changed_moves_move_the_preference_to_the_other_species():
    observed = party()
    changed = replace(observed, members=(
        replace(observed.members[0], moves=(MoveObservation(57, 15),)),
        replace(observed.members[1], moves=(MoveObservation(87, 10),)),
    ))
    trainer = quote((22, 130, 55))
    assert plan_trainer_party(observed, trainer).lead.target_index == 0
    assert plan_trainer_party(changed, trainer).lead.target_index == 1


@pytest.mark.parametrize("change", [
    {"hp": 79}, {"status": StatusCondition.PARALYSIS}, {"level": 49},
    {"moves": (MoveObservation(87, 0),)},
    {"moves": (MoveObservation(120, 5),)},  # Selfdestruct
    {"moves": (MoveObservation(153, 5),)},  # Explosion
    {"moves": (MoveObservation(49, 20),)},  # unsupported fixed damage
    {"moves": (MoveObservation(90, 5),)},  # unsupported one-hit KO
    {"moves": (MoveObservation(28, 15),)},  # status-only
])
def test_unfit_specialist_is_not_counted(change):
    observed = party()
    observed = replace(observed, members=(replace(observed.members[0], **change),
                                          observed.members[1]))
    candidates = trainer_matchup_candidates(observed, opponent_species=22, opponent_level=55)
    assert [row.party_slot for row in candidates] == [2]


def test_exact_health_and_level_boundaries_and_pp_supply():
    observed = party()
    observed = replace(observed, members=(replace(observed.members[0], hp=80, level=50,
                                               moves=(MoveObservation(87, 1),)),))
    plan = plan_trainer_party(observed, quote((22, 130, 55)))
    assert plan.lead.target_index == 0
    # Coverage explicitly does not claim that this single PP can win the battle.
    assert plan.public_dict()["battle_execution_qualified"] is False


def test_no_coverage_is_a_refusal_not_an_empty_or_status_move_choice():
    observed = replace(party(), members=(party().members[0],))
    with pytest.raises(RedTrainerPartyError, match="positions \\(2,\\)"):
        plan_trainer_party(observed, quote((22, 130, 55), (34, 95, 55)))


def test_fainted_passenger_refuses_trainer_preparation():
    observed = party()
    observed = replace(observed, members=(observed.members[0],
                                          replace(observed.members[1], hp=0)))
    with pytest.raises(RedTrainerPartyError, match="fully living"):
        plan_trainer_party(observed, quote((22, 130, 55)))


@pytest.mark.parametrize("moves", [(MoveObservation(0, 1),), (MoveObservation(87, 64),),
                                    (MoveObservation(255, 1),)])
def test_malformed_or_unknown_moves_do_not_silently_qualify(moves):
    observed = replace(party(), members=(replace(party().members[0], moves=moves),))
    with pytest.raises(ValueError):
        plan_trainer_party(observed, quote((22, 130, 55)))


@pytest.mark.parametrize("change", ["hp", "pp", "quote", "forgery"])
def test_snapshot_and_derived_plan_revalidation(change):
    observed, trainer = party(), quote((22, 130, 55), (34, 95, 55))
    plan = plan_trainer_party(observed, trainer)
    if change == "hp":
        observed = replace(observed, members=(replace(observed.members[0], hp=159),
                                              observed.members[1]))
    elif change == "pp":
        observed = replace(observed, members=(replace(observed.members[0],
                                                      moves=(MoveObservation(87, 9),)),
                                              observed.members[1]))
    elif change == "quote":
        trainer = replace(trainer, party=tuple(reversed(trainer.party)))
    else:
        plan = replace(plan, matchups=tuple(reversed(plan.matchups)))
    with pytest.raises(RedTrainerPartyError, match="changed"):
        plan.require_current(observed, trainer)


def test_verified_executor_swaps_the_matchup_lead_and_preserves_resources(monkeypatch):
    from test_red_capture_preparation import runtime, swap_raw

    import pokemon_red_completion.red_capture_preparation as preparation

    state = runtime(weak=False)
    # The existing lead has no usable non-immune move here; the second does.
    state.reader.raw = replace(
        state.reader.raw, party_species_ids=(104, 28), party_levels=(55, 55),
        party_moves=((87, 0, 0, 0), (57, 58, 0, 0)),
        party_pp=((10, 0, 0, 0), (15, 10, 0, 0)),
    )
    before = state.adapter.observe()
    trainer = quote((34, 95, 55))
    plan = plan_trainer_party(before.party, trainer)
    calls = []
    monkeypatch.setattr(preparation, "close_menu", lambda *_: None)
    def swap(_emulator, _actions, reader, **kwargs):
        calls.append((kwargs["source_index"], kwargs["destination_index"]))
        swap_raw(reader)
    monkeypatch.setattr(preparation, "swap_party_slots", swap)
    assert prepare_trainer_lead(state, object(), plan, current_quote=trainer)
    assert calls == [(1, 0)]
    after = state.adapter.observe()
    assert after.party.lead.species_id == 28
    assert after.raw.player_money == before.raw.player_money
    assert after.raw.bag_items == before.raw.bag_items
    assert after.raw.battle_state == 0
    # Reuse of the old plan is rejected before any second input.
    with pytest.raises(RedTrainerPartyError):
        prepare_trainer_lead(state, object(), plan, current_quote=trainer)
    assert calls == [(1, 0)]
