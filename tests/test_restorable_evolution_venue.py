"""Recoverable venue discovery must preserve live defensive safety."""
from dataclasses import replace
import pytest
from pokemon_red_completion import red_native_boxed_evolution as evolution
from pokemon_red_completion.party import PartyMemberObservation, PartyObservation, MoveObservation, StatusCondition
from pokemon_red_completion.red_team_training import collection_escape_escort


def fixture_party(*, status=StatusCondition.HEALTHY, hp=150, level=48):
    return PartyObservation((
        PartyMemberObservation(1, 59, 22, 37, 37, moves=(MoveObservation(10, 35, 35),)),
        PartyMemberObservation(2, 28, level, hp, 150, status=status,
                               moves=(MoveObservation(57, 15, 15),)),
    ))


@pytest.mark.parametrize("status,hp", [(StatusCondition.POISON, 140), (StatusCondition.HEALTHY, 1)])
def test_discovery_can_nurse_the_only_adequate_escort_but_live_escape_cannot_skip_it(status, hp):
    party = fixture_party(status=status, hp=hp)
    policy = evolution.context.MANSION_TEAM_POLICY
    enemy = next(iter(evolution.context.MANSION_VOLATILE_ENEMY_SPECIES))
    # This existing distinction is the contract: nursing restores capability,
    # and current combat must still refuse an injured/poisoned escort.
    assert collection_escape_escort(party, 59, policy, enemy_level=35,
        enemy_species=enemy, resources=False) is not None
    assert collection_escape_escort(party, 59, policy, enemy_level=35,
        enemy_species=enemy) is None
    assert evolution.native_evolution_encounter_supported(party, 59, policy, 35,
        enemy, allow_guarded_escapes=True)
    # Admission must not mutate the live party or turn it into a healthy escort.
    assert party.members[1].status is status and party.members[1].hp == hp
    assert collection_escape_escort(party, 59, policy, enemy_level=35,
        enemy_species=enemy) is None


@pytest.mark.parametrize("blocked", ["disabled", "level", "excluded"])
def test_recoverability_keeps_defensive_permission_level_and_helper_exclusion(blocked):
    party = fixture_party(level=20 if blocked == "level" else 48)
    enemy = next(iter(evolution.context.MANSION_VOLATILE_ENEMY_SPECIES))
    assert not evolution.native_evolution_encounter_supported(
        party, 59, evolution.context.MANSION_TEAM_POLICY, 35, enemy,
        allow_guarded_escapes=blocked != "disabled",
        excluded_helper_species=frozenset({28}) if blocked == "excluded" else frozenset())


def test_actual_restoration_is_still_needed_to_enter_live_escape():
    party = fixture_party(status=StatusCondition.POISON, hp=140)
    enemy = next(iter(evolution.context.MANSION_VOLATILE_ENEMY_SPECIES))
    args = dict(enemy_level=35, enemy_species=enemy)
    assert collection_escape_escort(party, 59, evolution.context.MANSION_TEAM_POLICY, **args) is None
    restored = replace(party, members=(party.members[0], replace(party.members[1],
        status=StatusCondition.HEALTHY, hp=150)))
    assert collection_escape_escort(restored, 59, evolution.context.MANSION_TEAM_POLICY, **args) is restored.members[1]


def test_restorable_admission_keeps_actual_incoming_type_safety(monkeypatch):
    party = fixture_party()
    # A dangerous incoming type remains unsupported even at full health.
    electric_enemy = 84
    monkeypatch.setattr(evolution.context, "MANSION_VOLATILE_ENEMY_SPECIES", frozenset({electric_enemy}))
    assert not evolution.native_evolution_encounter_supported(
        party, 59, evolution.context.MANSION_TEAM_POLICY, 35, electric_enemy,
        allow_guarded_escapes=True)
