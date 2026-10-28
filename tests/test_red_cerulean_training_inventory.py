"""Exercise the closed assembly with the real scoped pool and plural inventory."""

from dataclasses import dataclass, replace
from types import SimpleNamespace as N

import pytest
from test_red_live_option_menu import _binding, _situation
from test_red_scoped_training_battlers import A, B, prototype

import pokemon_red_completion.red_cerulean_training_inventory as module
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.party_preparation import PreparationPurpose
from pokemon_red_completion.player_option_challenge import OptionChallenge
from pokemon_red_completion.red_goal_context import RedGoalContextRuntime
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalMechanic,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.red_scoped_training_battlers import ScopedTrainingBattlers


@dataclass(frozen=True)
class Route:
    route_world: object


def fixture(tmp_path, monkeypatch):
    actor = prototype(tmp_path)
    actor.session.save_state_bytes = lambda: b"retained"
    pool = ScopedTrainingBattlers(actor, contracts=(A, B), output=tmp_path / "pool",
                                  experiment_sha256="c" * 64)
    profile = parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id="scoped-sequence-test", providers=(
            (GoalKind.RESTORE_TEAM, RedGoalMechanic.CENTER_RESTORE, {}),
            (GoalKind.RESUPPLY, RedGoalMechanic.MART_RESUPPLY, dict(
                map_id=int(MapId.VIRIDIAN_MART), player_x=2, player_y=5,
                interaction_direction="left",
                purchases=[dict(absolute_index=0, item_id=4, quantity=5, unit_price=200)],
            )),
            (GoalKind.RECOVER_CONTROL, RedGoalMechanic.CONTROL_RECOVERY, {}),
        ),
    ))
    runtime = RedGoalContextRuntime(profile, N(), actor.session, N(), N(), N(),
                                    registration_policy=N())
    world = N()
    world.with_current_observation = lambda reader: world
    config = dict(pool=pool, route=Route(world), plan=N(), corridor=N(), record=lambda *a: None,
                  hideout_timing=N())
    calls, executed = [], []
    def base(rt, actions, observation, **kwargs):
        calls.append(("base", kwargs["preparation"]["battler"], kwargs))
        bindings = tuple(_binding(k, calls=executed, binding_ref=k.value) for k in (
            GoalKind.DEVELOP_TEAM, GoalKind.RESTORE_TEAM, GoalKind.RESUPPLY,
        ))
        return GoalBindingSet(tuple(b.opportunity for b in bindings), bindings)

    def branches(rt, actions, **kwargs):
        calls.append(("branches", kwargs["battler"], kwargs))
        return tuple(N(binding=replace(_binding(
            GoalKind.ADVANCE_STORY, calls=executed, binding_ref=name,
        ), story_objective_ref=name), challenge=OptionChallenge(False, False, 0., 0., 0.))
            for name in ("defeat_misty", "help_bill"))

    monkeypatch.setattr(module, "enumerate_routed_player_goals", base)
    monkeypatch.setattr(module, "cerulean_story_options", branches)
    monkeypatch.setattr(module, "observe_preparation_members", lambda *a: (
        N(purpose=PreparationPurpose.COMBAT, observation=N(level=17)),
        N(purpose=PreparationPurpose.UNDECIDED, observation=N(level=5)),
    ))
    return runtime, config, calls, executed


def test_scoped_actors_feed_both_branches_and_wild_only_preparation(tmp_path, monkeypatch):
    rt, config, calls, executed = fixture(tmp_path, monkeypatch)
    inventory = module.CeruleanTrainingInventory(rt, **config)
    observation = N(situation=_situation())
    bindings = inventory.enumerate(rt, N(), observation)
    extras = inventory.supplements(rt, N(), observation, bindings)
    inventory.challenges(rt, bindings, extras, N(state=b"retained"))
    assert calls[0][1] is config["pool"].wild
    assert calls[1][1] is config["pool"]
    assert calls[1][2]["combat_levels"] == (17,)
    assert calls[0][2]["preparation"]["plan"] is config["plan"]
    choices = (*bindings.bindings, *(s.binding for s in extras))
    assert {b.story_objective_ref for b in choices if b.kind is GoalKind.ADVANCE_STORY} == {
        "defeat_misty", "help_bill",
    }
    assert {b.kind for b in choices} >= {
        GoalKind.DEVELOP_TEAM, GoalKind.RESTORE_TEAM, GoalKind.RESUPPLY,
    }
    assert not executed and rt.emulator.frame_count == 0
    for b in choices:
        b.execute()
    assert len(executed) == len(choices)


@pytest.mark.parametrize("field", module._FORBIDDEN_CALLBACKS)
def test_inherited_callback_is_rejected_not_silently_removed(tmp_path, monkeypatch, field):
    rt, config, _, _ = fixture(tmp_path, monkeypatch)
    def callback(*a):
        pytest.fail("undeclared callback cannot run")
    setattr(rt, field, callback)
    with pytest.raises(ValueError, match="undeclared"):
        module.CeruleanTrainingInventory(rt, **config)
    assert getattr(rt, field) is callback and rt.emulator.frame_count == 0


@pytest.mark.parametrize("fault", ["runner", "pool", "runtime", "profile", "flag"])
def test_replacement_after_menu_is_rejected_before_selected_input(tmp_path, monkeypatch, fault):
    rt, config, _, executed = fixture(tmp_path, monkeypatch)
    inventory = module.CeruleanTrainingInventory(rt, **config)
    bindings = inventory.enumerate(rt, N(), N(situation=_situation()))
    if fault == "runner":
        rt.trainer_battle_runner = lambda *a: None
    elif fault == "pool":
        config["pool"].wild.session = N(frame_count=0)
    elif fault == "runtime":
        rt.emulator = N(frame_count=0)
    elif fault == "profile":
        rt.profile = replace(rt.profile)
    else:
        rt.scripted_gifts = True
    with pytest.raises(ValueError):
        bindings.bindings[0].execute()
    assert not executed


def test_dose_cannot_expand_and_missing_registration_rejects(tmp_path, monkeypatch):
    rt, config, _, _ = fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        module.CeruleanTrainingInventory(rt, **config, maximum_battles=9)
    rt.registration_policy = None
    with pytest.raises(ValueError):
        module.CeruleanTrainingInventory(rt, **config)


def test_resource_router_cannot_enable_incidental_funding_or_capture(tmp_path, monkeypatch):
    rt, config, calls, _ = fixture(tmp_path, monkeypatch)
    inventory = module.CeruleanTrainingInventory(rt, **config)
    observation = N(situation=_situation())
    inventory.enumerate(rt, N(), observation)
    routed = []

    def router(runtime, actions, world, **kwargs):
        routed.append(kwargs)
        return N(enumerate=lambda observed: observed)

    monkeypatch.setattr(module, "RedResourceGoalRouter", router)
    assert calls[0][2]["enumerate_base"](rt, N(), observation) is observation
    assert routed == [dict(quote_resource_costs=True, prepare_capture_party=False,
                           prepare_capture_escort=False, include_recovery_offers=False,
                           trainer_funding=False)]


def test_broader_profile_is_rejected_without_hiding_its_story_provider(tmp_path, monkeypatch):
    rt, config, _, _ = fixture(tmp_path, monkeypatch)
    from pokemon_red_completion.red_goal_context_profile import _thaw

    providers = tuple((s.kind, s.mechanic, _thaw(s.parameters)) for s in rt.profile.providers)
    rt.profile = parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id="too-broad-for-this-trial", providers=(
            (GoalKind.ADVANCE_STORY, RedGoalMechanic.OAKS_ERRAND, {}),
        ) + providers,
    ))
    original = rt.profile
    with pytest.raises(ValueError, match="undeclared"):
        module.CeruleanTrainingInventory(rt, **config)
    assert rt.profile is original
