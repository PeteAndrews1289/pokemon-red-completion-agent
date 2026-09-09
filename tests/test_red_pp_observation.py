from copy import deepcopy
from dataclasses import replace

import pytest
from test_red_elixir_plan import finished, state
from test_red_goal_skills import _adapter, _Reader

from pokemon_red_completion.red_goal_context_profile import (
    RedGoalMechanic,
    bind_field_pp_restore_profile,
)
from pokemon_red_completion.red_living_dex_causal_adapter import (
    red_living_dex_outcome_from_observations,
)
from pokemon_red_completion.red_pp_observation import (
    RedPpResourceObservation,
    observe_pp_resources,
)


def observation(raw, *, enabled):
    return replace(_adapter(_Reader(raw=raw, ready=True)),
                   include_pp_restoration=enabled).observe()


def project(before, after):
    return red_living_dex_outcome_from_observations(
        before, after, succeeded=True, actions=2, frames=60,
        maximum_actions=20, maximum_frames=600,
    )


def test_opt_in_keeps_historical_input_and_hp_counts_but_records_pp_cost():
    raw = replace(state(), bag_items=((53, 3), (82, 1)), bag_item_ids=(53, 82))
    after_raw = replace(finished(raw), bag_items=((53, 3),), bag_item_ids=(53,))
    old_before = observation(raw, enabled=False)
    old_after = observation(after_raw, enabled=False)
    before = observation(raw, enabled=True)
    after = observation(after_raw, enabled=True)
    assert old_before.public_dict()["schema"] == "pokemon.red.goal-observation.v1"
    assert "pp_restoration" not in old_before.public_dict()
    assert old_before.situation == before.situation
    assert old_after.situation == after.situation
    assert before.recovery_item_count == after.recovery_item_count == 3
    assert before.public_dict()["schema"] == after.public_dict()["schema"] == (
        "pokemon.red.goal-observation.v2")
    assert before.pp_restoration.item_count == 1 and after.pp_restoration.item_count == 0
    expected = deepcopy(old_before.public_dict())
    expected["schema"] = "pokemon.red.goal-observation.v2"
    expected["pp_restoration"] = {
        "schema": "pokemon.red.pp-resource-observation.v1", "item_count": 1,
        "party_slots": [[[1, 10], [35, 35], [0, 0], [0, 0]],
                        [[2, 15], [6, 10], [0, 0], [0, 0]]],
    }
    assert before.public_dict() == expected
    legacy = project(old_before.public_dict(), old_after.public_dict())
    outcome = project(before.public_dict(), after.public_dict())
    assert legacy.resource_cost == 0.0  # historical interpretation unchanged
    assert outcome.resource_cost == 0.25
    assert outcome.verified_success is True
    assert outcome.completion_gain == outcome.dependency_unlock_gain == 0.0
    assert outcome.action_cost == outcome.frame_cost == 0.1


@pytest.mark.parametrize("reverse", [False, True])
def test_outcome_rejects_mixed_observation_versions(reverse):
    old = observation(state(), enabled=False).public_dict()
    new = observation(state(), enabled=True).public_dict()
    with pytest.raises(ValueError, match="schema"):
        project(*(new, old) if reverse else (old, new))


def test_legacy_cannot_smuggle_unversioned_pp_consumption():
    old = observation(state(), enabled=False).public_dict()
    changed = {**old, "pp_restoration": observe_pp_resources(state()).public_dict()}
    with pytest.raises(ValueError, match="unversioned"):
        project(changed, old)


@pytest.mark.parametrize("bad", [
    {"item_count": True}, {"item_count": -1}, {"item_count": 100},
    {"party_slots": []}, {"party_slots": [[[1, 0]] * 4]},
    {"party_slots": [[[True, 10]] * 4]}, {"party_slots": [[[0, 64]] * 4]},
    {"party_slots": [[[0, 1]] * 3]}, {"party_slots": [[[0, 1, 2]] * 4]},
    {"schema": "unknown"}, {"undeclared": 1},
])
def test_public_pp_evidence_is_strict_not_an_unchecked_cost_label(bad):
    valid = observe_pp_resources(state()).public_dict()
    with pytest.raises(ValueError):
        RedPpResourceObservation.from_public({**valid, **bad})


def test_pp_evidence_retains_capacity_not_raw_species_move_or_address():
    raw = replace(state(), party_moves=((87, 33, 0, 0), (57, 58, 45, 0)),
                  party_pp=((1, 35, 0, 0), (0xC2, 0x4B, 0xF8, 0)))
    encoded = observe_pp_resources(raw).public_dict()
    assert encoded["party_slots"][1] == [[2, 24], [11, 12], [56, 61], [0, 0]]
    assert RedPpResourceObservation.from_public(encoded).public_dict() == encoded
    assert set(encoded) == {"schema", "item_count", "party_slots"}


def test_pp_profile_only_changes_its_explicit_restoration_binding():
    from test_red_goal_context_profile import _supply_transition_profile

    from pokemon_red_completion.goal_manager import GoalKind
    from pokemon_red_completion.red_goal_context_profile import (
        RedGoalContextProfileError,
        build_red_goal_context_profile_payload,
        parse_red_goal_context_profile,
    )

    old = _supply_transition_profile()
    new = bind_field_pp_restore_profile(old)
    assert new.profile_sha256 != old.profile_sha256
    for spec in old.providers:
        if spec.kind is not GoalKind.RESTORE_TEAM:
            assert spec in new.providers
    pp = next(spec for spec in new.providers if spec.kind is GoalKind.RESTORE_TEAM)
    assert pp.mechanic is RedGoalMechanic.FIELD_PP_RESTORE and pp.parameters == {}
    with pytest.raises(RedGoalContextProfileError):
        parse_red_goal_context_profile(build_red_goal_context_profile_payload(
            profile_id="invalid-pp", providers=(
                (GoalKind.RESTORE_TEAM, RedGoalMechanic.FIELD_PP_RESTORE, {"free_items": True}),
            ),
        ))
