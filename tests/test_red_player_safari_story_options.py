from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import red_player_safari_rewards as s
from pokemon_red_completion.player_option_challenge import OptionChallenge


def setup(monkeypatch, *, objective="obtain_surf", map_id=7, at=(4, 5), bag=()):
    raw = N(
        map_id=map_id,
        player_y=at[0],
        player_x=at[1],
        bag_items=bag,
        player_money=500,
        party_moves=((33, 39, 58, 61),),
    )
    runtime = N(reader=N(read=lambda: raw))
    calls = []
    monkeypatch.setattr(s, "_field_ready", lambda _: True)
    monkeypatch.setattr(s, "safari_rewards_binding", lambda *a, **k: None)
    monkeypatch.setattr(s, "strength_reward_binding", lambda *a, **k: None)

    def travel(*args, **kwargs):
        calls.append(kwargs)
        return N(story_objective_ref=kwargs["objective_id"])

    monkeypatch.setattr(s, "story_travel_binding", travel)
    kwargs = dict(
        objective_id=objective, route=object(), party_slot=1, replace_slot=4, record=lambda *a: None
    )
    return runtime, raw, calls, kwargs


@pytest.mark.parametrize("objective", ["obtain_surf", "obtain_strength"])
@pytest.mark.parametrize("local", [False, True])
def test_reward_approach_keeps_its_objective_and_sends_no_inputs(monkeypatch, objective, local):
    rt, raw, calls, kwargs = setup(
        monkeypatch,
        objective=objective,
        map_id=154 if local else 7,
        bag=((198, 1), (64, 1)) if objective == "obtain_strength" else (),
    )
    binding, challenge = s.safari_reward_story_option(rt, object(), **kwargs)
    assert binding.story_objective_ref == objective and isinstance(challenge, OptionChallenge)
    assert calls[0]["destination_at"] == ((3, 3) if local else None)
    assert calls[0]["frontier"] is (not local)
    assert calls[0]["stop_at_map_boundary"] is (not local)
    assert raw.player_money == 500


@pytest.mark.parametrize("objective", ["obtain_surf", "obtain_strength"])
def test_available_native_reward_is_used_without_other_story_priority(monkeypatch, objective):
    rt, _, calls, kwargs = setup(
        monkeypatch,
        objective=objective,
        map_id=154,
        at=(3, 3),
        bag=((198, 1), (64, 1)) if objective == "obtain_strength" else (),
    )
    expected = N(story_objective_ref=objective)
    name = "safari_rewards_binding" if objective == "obtain_surf" else "strength_reward_binding"
    observed = []
    monkeypatch.setattr(s, name, lambda *a, **k: observed.append(k) or expected)
    assert s.safari_reward_story_option(rt, object(), **kwargs)[0] is expected
    assert not calls
    if objective == "obtain_surf":
        assert observed[0]["party_slot"] == 1 and observed[0]["replace_slot"] == 4


@pytest.mark.parametrize("fault", ["cash", "bag_full", "unready", "claimed", "at_boundary"])
def test_unavailable_surf_does_not_manufacture_an_approach(monkeypatch, fault):
    rt, raw, calls, kwargs = setup(monkeypatch)
    if fault == "cash":
        raw.player_money = 499
    elif fault == "bag_full":
        raw.bag_items = tuple((i, 1) for i in range(1, 21))
    elif fault == "unready":
        monkeypatch.setattr(s, "_field_ready", lambda _: False)
    elif fault == "claimed":
        raw.bag_items = ((199, 1),)
    else:
        raw.map_id, raw.player_y, raw.player_x = 154, 3, 3
    assert s.safari_reward_story_option(rt, object(), **kwargs) is None and not calls


@pytest.mark.parametrize(
    "bag", [(), ((64, 1),), ((198, 1),), ((198, 1), (64, 2)), ((198, 1), (64, 1), (199, 1))]
)
def test_strength_requires_real_unexchanged_teeth_and_surf(monkeypatch, bag):
    rt, _, calls, kwargs = setup(monkeypatch, objective="obtain_strength", bag=bag)
    assert s.safari_reward_story_option(rt, object(), **kwargs) is None and not calls


def test_wrong_objective_or_missing_surf_recorder_is_rejected_before_dispatch(monkeypatch):
    rt, _, calls, kwargs = setup(monkeypatch)
    with pytest.raises(ValueError, match="undeclared"):
        s.safari_reward_story_option(rt, object(), **dict(kwargs, objective_id="defeat_koga"))
    with pytest.raises(TypeError, match="recorder"):
        s.safari_reward_story_option(rt, object(), **dict(kwargs, record=None))
    assert not calls


@pytest.mark.parametrize("enabled", [False, True])
def test_surf_composition_passes_explicit_center_approach_without_forcing_goal(
    monkeypatch, enabled
):
    rt, _, calls, kwargs = setup(monkeypatch, map_id=154, at=(7, 3))
    observed = []
    expected = N(story_objective_ref="obtain_surf")
    monkeypatch.setattr(
        s, "safari_rewards_binding", lambda *args, **kw: observed.append(kw) or expected
    )
    assert (
        s.safari_reward_story_option(rt, object(), **kwargs, complete_center_approach=enabled)[0]
        is expected
    )
    assert observed[0]["complete_center_approach"] is enabled and not calls


@pytest.mark.parametrize("flag", [None, 1, "True"])
def test_story_approach_flag_is_not_coerced(monkeypatch, flag):
    rt, _, calls, kwargs = setup(monkeypatch)
    with pytest.raises(TypeError, match="explicit boolean"):
        s.safari_reward_story_option(rt, object(), **kwargs, complete_center_approach=flag)
    assert not calls
