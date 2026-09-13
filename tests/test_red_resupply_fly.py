import pytest
from test_red_goal_context_profile import _supply_transition_profile

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfileError,
    _thaw,
    bind_resupply_fly_profile,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)


def mart_profile(**flags):
    before = _supply_transition_profile()
    providers = []
    for spec in before.providers:
        parameters = _thaw(spec.parameters)
        if spec.kind is GoalKind.RESUPPLY:
            parameters.update(map_id=89, player_x=3, player_y=3, **flags)
        providers.append((spec.kind, spec.mechanic, parameters))
    return parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id=before.profile_id, providers=tuple(providers),
    ))


def supply_spec(scene, *, enabled=True):
    profile = mart_profile()
    if enabled:
        profile = bind_resupply_fly_profile(profile)
    scene.router.runtime.profile = profile
    scene.provider.kind = GoalKind.RESUPPLY
    return next(s for s in profile.providers if s.kind is GoalKind.RESUPPLY)


def test_supply_transition_only_changes_mart_and_is_idempotent():
    before = mart_profile()
    after = bind_resupply_fly_profile(before)
    assert after.providers[:2] == before.providers[:2]
    old, new = before.providers[2], after.providers[2]
    assert "fly_transport" not in old.parameters
    assert new.parameters["fly_transport"] is True
    assert new.parameters["indoor_fly_departure"] is True
    assert "surf_transport" not in new.parameters and "cut_transport" not in new.parameters
    assert new.parameters["purchases"] == old.parameters["purchases"]
    assert bind_resupply_fly_profile(after) == after


@pytest.mark.parametrize("key", ["fly_transport", "indoor_fly_departure"])
@pytest.mark.parametrize("value", [0, 1, "true", None])
def test_supply_transport_rejects_non_boolean_flags(key, value):
    with pytest.raises(RedGoalContextProfileError):
        mart_profile(**{"fly_transport": True, key: value})


def test_supply_departure_cannot_enable_flight_implicitly():
    with pytest.raises(RedGoalContextProfileError, match="requires Fly"):
        mart_profile(indoor_fly_departure=True)


def test_supply_flags_do_not_allow_cut_or_surf():
    with pytest.raises(RedGoalContextProfileError):
        mart_profile(fly_transport=True, surf_transport=True)
