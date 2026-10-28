from dataclasses import replace
from types import SimpleNamespace as N

import pytest
from test_red_live_option_menu import _binding, _situation

from pokemon_red_completion import red_player_collection_options as p
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.red_goal_context import RedGoalContextRuntime
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalMechanic,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.red_living_dex_wild_corridor import RedLivingDexWildCorridor
from pokemon_red_completion.resource_economy_observation import EconomyMode, EconomyOffer


def collection_runtime(providers=()):
    providers = tuple(
        sorted(
            (
                (GoalKind.ADVANCE_STORY, RedGoalMechanic.OAKS_ERRAND, {}),
                (GoalKind.RESTORE_TEAM, RedGoalMechanic.CENTER_RESTORE, {}),
                (GoalKind.RECOVER_CONTROL, RedGoalMechanic.CONTROL_RECOVERY, {}),
            )
            + providers,
            key=lambda row: tuple(GoalKind).index(row[0]),
        )
    )
    profile = parse_red_goal_context_profile(
        build_red_goal_context_profile_payload(
            profile_id="shared-collection-test",
            providers=providers,
        )
    )
    return RedGoalContextRuntime(
        profile, None, None, None, None, None, registration_policy=object()
    )


def corridor():
    return RedLivingDexWildCorridor("wild:Route1:grass", int(MapId.ROUTE_1), (4, 2), (3, 2))


def test_capability_binding_preserves_original_providers_and_does_not_select_a_goal():
    rt = collection_runtime()
    composed = p.bind_player_collection_capabilities(rt, seed_corridor=corridor())
    assert all(spec in composed.profile.providers for spec in rt.profile.providers)
    assert not rt.scripted_gifts and rt.profile != composed.profile
    assert composed.registration_policy is rt.registration_policy
    assert composed.scripted_gifts and composed.npc_trades and composed.npc_trade_dependencies
    assert composed.safari_indoor_departure and composed.safari_departure_recovery
    assert not rt.safari_departure_recovery
    capture = next(
        spec for spec in composed.profile.providers if spec.kind is GoalKind.ACQUIRE_SPECIES
    )
    assert capture.parameters["capture_weakening_support"] is True
    assert capture.parameters["capture_access_requirements"] is True
    assert capture.parameters["cut_transport"] is True
    assert capture.parameters["surf_transport"] is True
    assert capture.parameters["maximum_legs"] == 160
    assert (
        p.bind_player_collection_capabilities(composed, seed_corridor=corridor()).profile
        == composed.profile
    )


def test_existing_capture_seed_is_preserved_and_only_discovery_is_added():
    parameters = dict(corridor().profile_parameters(), maximum_legs=8)
    rt = collection_runtime(
        ((GoalKind.ACQUIRE_SPECIES, RedGoalMechanic.WILD_CORRIDOR_CAPTURE, parameters),)
    )
    composed = p.bind_player_collection_capabilities(rt, seed_corridor=corridor())
    capture = next(
        spec for spec in composed.profile.providers if spec.kind is GoalKind.ACQUIRE_SPECIES
    )
    assert capture.parameters["source_id"] == parameters["source_id"]
    assert capture.parameters["player_x"] == parameters["player_x"]
    assert sum(spec.kind is GoalKind.EXPLORE for spec in composed.profile.providers) == 1


def test_ordinary_safari_departure_recovery_is_not_gated_on_post_league_progress():
    # This pure composition has no badges, Hall-of-Fame fact or teacher actor.
    # The existing guarded handler remains responsible for real interruptions.
    original = collection_runtime()
    composed = p.bind_player_collection_capabilities(original, seed_corridor=corridor())
    assert composed.safari_departure_recovery is True
    assert original.safari_departure_recovery is False
    assert composed.registration_policy is original.registration_policy
    assert p.bind_player_collection_capabilities(
        composed, seed_corridor=corridor()
    ).safari_departure_recovery


def test_dig_departure_is_default_off_and_explicit_opt_in_preserves_profile():
    rt = collection_runtime()
    ordinary = p.bind_player_collection_capabilities(rt, seed_corridor=corridor())
    enabled = p.bind_player_collection_capabilities(
        rt, seed_corridor=corridor(), include_dig_departure=True,
    )
    assert not rt.collection_dig_departure and not ordinary.collection_dig_departure
    assert enabled.collection_dig_departure and enabled.profile == ordinary.profile
    assert enabled.registration_policy is rt.registration_policy
    assert p.bind_player_collection_capabilities(
        enabled, seed_corridor=corridor(),
    ).collection_dig_departure


@pytest.mark.parametrize("flag", [1, "yes", None])
def test_dig_departure_permission_requires_a_boolean(flag):
    with pytest.raises(TypeError, match="boolean"):
        p.bind_player_collection_capabilities(
            collection_runtime(), seed_corridor=corridor(), include_dig_departure=flag,
        )


def test_fly_transport_is_default_off_and_target_free_evolution_inherits_only_opt_in():
    from pokemon_red_completion.red_full_pokedex_direct_profile import (
        _evolution_capability_parameters,
    )
    runtime = collection_runtime()
    ordinary = p.bind_player_collection_capabilities(runtime, seed_corridor=corridor())
    assert _evolution_capability_parameters(ordinary.profile) == {}
    enabled = p.bind_player_collection_capabilities(
        runtime, seed_corridor=corridor(), include_fly_transport=True)
    capture = next(s for s in enabled.profile.providers if s.kind is GoalKind.ACQUIRE_SPECIES)
    assert capture.parameters["fly_transport"] is True
    assert capture.parameters["indoor_fly_departure"] is True
    assert _evolution_capability_parameters(enabled.profile) == {
        "fly_transport": True, "indoor_fly_departure": True}
    assert enabled.registration_policy is runtime.registration_policy
    assert runtime.profile == collection_runtime().profile
    with pytest.raises(TypeError, match="boolean"):
        p.bind_player_collection_capabilities(runtime, seed_corridor=corridor(),
                                             include_fly_transport=1)


def test_explicit_early_capture_uses_existing_plain_mode_and_keeps_transport_bounds():
    rt = collection_runtime()
    composed = p.bind_player_collection_capabilities(
        rt,
        seed_corridor=corridor(),
        add_capture_preparation_support=False,
    )
    capture = next(s for s in composed.profile.providers if s.kind is GoalKind.ACQUIRE_SPECIES)
    assert not capture.parameters.get("capture_status_support", False)
    assert not capture.parameters.get("capture_weakening_support", False)
    assert capture.parameters["cut_transport"] and capture.parameters["surf_transport"]
    assert capture.parameters["maximum_legs"] == 160
    assert composed.registration_policy is rt.registration_policy
    assert all(s in composed.profile.providers for s in rt.profile.providers)


def test_skipping_new_preparation_never_removes_explicit_existing_support():
    composed = p.bind_player_collection_capabilities(collection_runtime(), seed_corridor=corridor())
    preserved = p.bind_player_collection_capabilities(
        composed,
        seed_corridor=corridor(),
        add_capture_preparation_support=False,
    )
    assert preserved.profile == composed.profile


@pytest.mark.parametrize("permission", [None, 1, "false"])
def test_capture_preparation_permission_requires_boolean(permission):
    with pytest.raises(TypeError, match="boolean"):
        p.bind_player_collection_capabilities(
            collection_runtime(),
            seed_corridor=corridor(),
            add_capture_preparation_support=permission,
        )


@pytest.mark.parametrize("fault", ["registration", "corridor"])
def test_collection_capabilities_reject_unregistered_or_unverified_seed(fault):
    rt = collection_runtime()
    seed = corridor()
    if fault == "registration":
        rt.registration_policy = None
    else:
        seed = object()
    with pytest.raises(ValueError):
        p.bind_player_collection_capabilities(rt, seed_corridor=seed)


def fixture(monkeypatch):
    em = N(frame_count=0, pressed_buttons=frozenset(), save_state_bytes=lambda: b"same")
    rt = N(emulator=em, registration_policy=object(), adapter=N(
        observe=lambda: N(party=N(members=(N(hp=1),))),
    ))
    actions = N(actions_executed=0)
    monkeypatch.setattr(p, "_field_ready", lambda _: True)
    for name in (
        "enumerate_red_regional_acquisitions",
        "scripted_gift_bindings",
        "npc_trade_dependency_bindings",
        "npc_trade_bindings",
        "enumerate_red_item_evolutions",
        "enumerate_red_level_evolutions",
        "autonomous_fishing_options",
        "autonomous_safari_options",
    ):
        monkeypatch.setattr(p, name, lambda *a, **k: ())
    return rt, actions, N(situation=_situation())


def test_grass_gift_trade_and_evolution_keep_distinct_private_executors(monkeypatch):
    rt, actions, obs = fixture(monkeypatch)
    bindings = tuple(
        _binding(GoalKind.ACQUIRE_SPECIES, binding_ref=label, calls=[])
        for label in ("grass", "gift", "trade")
    )
    evolution = _binding(GoalKind.EVOLVE_SPECIES, binding_ref="level", calls=[])
    monkeypatch.setattr(
        p, "enumerate_red_regional_acquisitions", lambda *a, **k: (N(binding=bindings[0]),)
    )
    monkeypatch.setattr(p, "scripted_gift_bindings", lambda *a, **k: (bindings[1],))
    monkeypatch.setattr(p, "npc_trade_bindings", lambda *a, **k: (bindings[2],))
    offer = EconomyOffer(EconomyMode.OTHER, planned_spend=0)
    monkeypatch.setattr(
        p,
        "enumerate_red_level_evolutions",
        lambda *a, **k: (N(binding=evolution, economy_offer=offer, execution_effort=0.23),),
    )
    result = p.player_collection_supplements(rt, actions, obs, world=N())
    assert tuple(row.binding for row in result) == bindings + (evolution,)
    assert result[-1].candidate.features.execution_effort == 0.23
    assert result[-1].candidate.economy_offer is offer
    assert actions.actions_executed == rt.emulator.frame_count == 0


def test_no_capability_returns_no_manufactured_goal(monkeypatch):
    rt, actions, obs = fixture(monkeypatch)
    assert p.player_collection_supplements(rt, actions, obs, world=N()) == ()


@pytest.mark.parametrize("balls,expected", [(1, 1.0), (8, 0.125), (0, 0.0)])
def test_wild_capture_projects_known_stock_exposure_without_controller_changes(
    monkeypatch, balls, expected,
):
    rt, actions, obs = fixture(monkeypatch)
    live = N(situation=obs.situation, raw=N(bag_items=((4, balls), (1, 1))),
             party=N(members=(N(hp=1),)))
    rt.adapter.observe = lambda: live
    binding = replace(_binding(GoalKind.ACQUIRE_SPECIES, binding_ref="wild", calls=[]),
                      search_source_ref="pokemon.red:acquisition:wild:Route4:grass")
    monkeypatch.setattr(p, "enumerate_red_regional_acquisitions",
                        lambda *a, **k: (N(binding=binding),))
    result = p.player_collection_supplements(rt, actions, obs, world=N())
    assert result[0].candidate.features.resource_cost == expected
    assert result[0].binding is binding
    assert actions.actions_executed == rt.emulator.frame_count == 0
    assert live.raw.bag_items == ((4, balls), (1, 1))


@pytest.mark.parametrize("source", [None, "gift:Eevee", "fishing:Route12", "safari:Center"])
def test_nonwild_acquisition_does_not_inherit_bag_ball_cost(monkeypatch, source):
    rt, actions, obs = fixture(monkeypatch)
    rt.adapter.observe = lambda: N(situation=obs.situation, raw=N(bag_items=((4, 1),)),
                                   party=N(members=(N(hp=1),)))
    binding = replace(_binding(GoalKind.ACQUIRE_SPECIES, binding_ref="other", calls=[]),
                      search_source_ref=source)
    monkeypatch.setattr(p, "enumerate_red_regional_acquisitions",
                        lambda *a, **k: (N(binding=binding),))
    result = p.player_collection_supplements(rt, actions, obs, world=N())
    assert result[0].candidate.features.resource_cost == 0.0
    assert actions.actions_executed == rt.emulator.frame_count == 0


@pytest.mark.parametrize("hps", [(30, 20), (0, 20), (30, 0)])
def test_current_menu_omits_known_zero_action_survey_but_keeps_other_mechanics(monkeypatch, hps):
    rt, actions, obs = fixture(monkeypatch)
    live = N(party=N(members=tuple(N(hp=hp) for hp in hps)))
    rt.adapter.observe = lambda: live
    calls = []
    wild = _binding(GoalKind.ACQUIRE_SPECIES, binding_ref="wild", calls=[])
    gift = _binding(GoalKind.ACQUIRE_SPECIES, binding_ref="gift", calls=[])

    def regional(*args, **kwargs):
        calls.append("enumerate")
        return (N(binding=wild),)

    monkeypatch.setattr(p, "enumerate_red_regional_acquisitions", regional)
    monkeypatch.setattr(p, "scripted_gift_bindings", lambda *a, **k: (gift,))
    result = p.player_collection_supplements(rt, actions, obs, world=N())
    ready = all(hp > 0 for hp in hps)
    assert tuple(row.binding for row in result) == ((wild, gift) if ready else (gift,))
    assert calls == (["enumerate"] if ready else [])
    assert tuple(m.hp for m in live.party.members) == hps
    assert actions.actions_executed == rt.emulator.frame_count == 0


def test_long_evolution_limits_do_not_expand_ordinary_capture(monkeypatch):
    rt,actions,obs=fixture(monkeypatch)
    calls={}
    monkeypatch.setattr(p,'enumerate_red_regional_acquisitions',
        lambda *a,**k:calls.update(capture=k) or ())
    monkeypatch.setattr(p,'enumerate_red_level_evolutions',
        lambda *a,**k:calls.update(evolve=k) or ())
    assert p.player_collection_supplements(rt,actions,obs,world=N(),
        maximum_evolution_quanta=256,maximum_evolution_actions=80000,
        maximum_evolution_frames=8000000,maximum_evolution_seconds=1800)==()
    assert calls['capture']['maximum_actions']==20000
    assert calls['capture']['maximum_frames']==2000000
    assert calls['evolve']['maximum_actions']==80000
    assert calls['evolve']['maximum_frames']==8000000
    assert calls['evolve']['maximum_quanta']==256
    assert calls['evolve']['maximum_wall_seconds']==1800
    assert 'maximum_wall_seconds' not in calls['capture']


@pytest.mark.parametrize('value',[0,-1,True,1.5])
def test_explicit_evolution_limits_remain_finite_positive_integers(monkeypatch,value):
    rt,actions,obs=fixture(monkeypatch)
    with pytest.raises(ValueError,match='positive integers'):
        p.player_collection_supplements(rt,actions,obs,world=N(),maximum_evolution_actions=value)
    with pytest.raises(ValueError,match='positive integers'):
        p.player_collection_supplements(rt,actions,obs,world=N(),maximum_evolution_seconds=value)


@pytest.mark.parametrize("enabled", [False, True])
def test_capture_transport_forwards_existing_battle_wrapper_without_choosing(monkeypatch, enabled):
    rt, actions, obs = fixture(monkeypatch)
    calls = []
    def wrapper(inner, spec):
        pytest.fail("observation invoked battle wrapper")
    monkeypatch.setattr(p, "enumerate_red_regional_acquisitions",
                        lambda *a, **kw: calls.append(kw) or ())
    assert p.player_collection_supplements(rt, actions, obs, world=N(),
        capture_interruption_handler_wrapper=wrapper if enabled else None) == ()
    assert calls[0].get("interruption_handler_wrapper") is (wrapper if enabled else None)
    assert actions.actions_executed == rt.emulator.frame_count == 0


@pytest.mark.parametrize("wrapper", [True, 3, object()])
def test_capture_transport_rejects_noncallable_wrapper_before_observation(monkeypatch, wrapper):
    rt, actions, obs = fixture(monkeypatch)
    with pytest.raises(TypeError, match="wrapper must be callable"):
        p.player_collection_supplements(rt, actions, obs, world=N(),
                                       capture_interruption_handler_wrapper=wrapper)
    assert actions.actions_executed == rt.emulator.frame_count == 0


@pytest.mark.parametrize('enabled', [False, True])
def test_fishing_transport_forwards_existing_battle_wrapper_without_execution(monkeypatch, enabled):
    rt, actions, obs = fixture(monkeypatch)
    calls = []
    def wrapper(inner):
        pytest.fail('observation invoked the fishing battle wrapper')
    monkeypatch.setattr(p, 'autonomous_fishing_options',
                        lambda *a, **kw: calls.append(kw) or ())
    assert p.player_collection_supplements(rt, actions, obs, world=N(),
        fishing_interruption_handler_wrapper=wrapper if enabled else None) == ()
    assert calls[0].get('interruption_handler_wrapper') is (wrapper if enabled else None)
    assert actions.actions_executed == rt.emulator.frame_count == 0


@pytest.mark.parametrize('enabled', [False, True])
def test_both_evolution_sources_forward_exact_wrapper_without_execution(monkeypatch, enabled):
    rt, actions, obs = fixture(monkeypatch)
    calls = []

    def wrapper(inner, spec):
        pytest.fail('enumeration invoked the evolution battle wrapper')

    for name in ('enumerate_red_item_evolutions', 'enumerate_red_level_evolutions'):
        monkeypatch.setattr(p, name, lambda *args, **kwargs: calls.append(kwargs) or ())
    assert p.player_collection_supplements(
        rt, actions, obs, world=N(),
        evolution_interruption_handler_wrapper=wrapper if enabled else None,
    ) == ()
    assert len(calls) == 2
    assert all(call.get('interruption_handler_wrapper') is
               (wrapper if enabled else None) for call in calls)
    assert actions.actions_executed == rt.emulator.frame_count == 0


@pytest.mark.parametrize('wrapper', [True, 3, object()])
def test_evolution_transport_refuses_noncallable_before_observation(monkeypatch, wrapper):
    rt, actions, obs = fixture(monkeypatch)
    with pytest.raises(TypeError, match='evolution interruption wrapper must be callable'):
        p.player_collection_supplements(
            rt, actions, obs, world=N(), evolution_interruption_handler_wrapper=wrapper,
        )
    assert actions.actions_executed == rt.emulator.frame_count == 0


@pytest.mark.parametrize('wrapper', [True, 3, object()])
def test_fishing_transport_rejects_noncallable_wrapper_before_observation(monkeypatch, wrapper):
    rt, actions, obs = fixture(monkeypatch)
    with pytest.raises(TypeError, match='wrapper must be callable'):
        p.player_collection_supplements(rt, actions, obs, world=N(),
                                       fishing_interruption_handler_wrapper=wrapper)
    assert actions.actions_executed == rt.emulator.frame_count == 0


@pytest.mark.parametrize("enabled", [False, True])
def test_fossil_revival_is_an_explicit_peer_not_a_replacement(monkeypatch, enabled):
    rt, actions, obs = fixture(monkeypatch)
    capture = _binding(GoalKind.ACQUIRE_SPECIES, binding_ref="wild", calls=[])
    fossil = _binding(GoalKind.ACQUIRE_SPECIES, binding_ref="fossil", calls=[])
    calls = []
    monkeypatch.setattr(p, "enumerate_red_regional_acquisitions",
                        lambda *a, **kw: (N(binding=capture),))
    monkeypatch.setattr(p, "fossil_acquisition_bindings",
                        lambda *a, **kw: calls.append(kw) or (fossil,))
    rows = p.player_collection_supplements(rt, actions, obs, world=N(),
                                         include_fossil_acquisition=enabled)
    assert tuple(row.binding for row in rows) == ((capture, fossil) if enabled else (capture,))
    assert calls == ([dict(maximum_actions=20000, maximum_frames=2000000)] if enabled else [])
    assert actions.actions_executed == rt.emulator.frame_count == 0


@pytest.mark.parametrize("enabled", (False, True))
@pytest.mark.parametrize("venue_override", (False, True))
def test_evolution_venue_reuse_is_explicit_and_zero_input(monkeypatch, enabled, venue_override):
    from pokemon_red_completion.red_goal_context import DIGLETTS_CAVE_TRAINING_VENUE
    rt, actions, obs = fixture(monkeypatch)
    calls = []
    monkeypatch.setattr(p, "enumerate_red_level_evolutions",
                        lambda *a, **kw: calls.append(kw) or ())
    assert p.player_collection_supplements(
        rt, actions, obs, world=N(), prefer_highest_evolution_venue=enabled,
        allow_guarded_evolution_escapes=enabled,
        evolution_training_venues=(DIGLETTS_CAVE_TRAINING_VENUE,) if venue_override else None,
    ) == ()
    assert calls == [dict(maximum_actions=20000, maximum_frames=2000000, maximum_quanta=64,
                         **(dict(prefer_highest_supported_venue=True,
                                 allow_guarded_venue_escapes=True) if enabled else {}),
                         **({"training_venues": (DIGLETTS_CAVE_TRAINING_VENUE,)}
                            if venue_override else {}))]
    assert actions.actions_executed == rt.emulator.frame_count == 0


@pytest.mark.parametrize("value", (None, 0, 1, "yes"))
def test_evolution_venue_permission_cannot_be_coerced(monkeypatch, value):
    rt, actions, obs = fixture(monkeypatch)
    with pytest.raises(ValueError, match="explicit booleans"):
        p.player_collection_supplements(rt, actions, obs, world=N(),
                                       prefer_highest_evolution_venue=value)


def test_unsettled_controls_skip_all_collection(monkeypatch):
    rt, actions, obs = fixture(monkeypatch)
    monkeypatch.setattr(p, "_field_ready", lambda _: False)
    monkeypatch.setattr(
        p,
        "enumerate_red_regional_acquisitions",
        lambda *a, **k: pytest.fail("unsettled collection"),
    )
    assert p.player_collection_supplements(rt, actions, obs, world=N()) == ()


@pytest.mark.parametrize(
    "fault", ["actions", "frames", "state", "buttons", "duplicate", "registration"]
)
def test_native_changes_and_invalid_registration_are_rejected(monkeypatch, fault):
    rt, actions, obs = fixture(monkeypatch)
    b = _binding(GoalKind.ACQUIRE_SPECIES, binding_ref="same", calls=[])
    if fault == "registration":
        rt.registration_policy = None
    elif fault == "duplicate":
        monkeypatch.setattr(p, "scripted_gift_bindings", lambda *a, **k: (b, b))
    else:

        def changed(*a, **k):
            if fault == "actions":
                actions.actions_executed += 1
            elif fault == "frames":
                rt.emulator.frame_count += 1
            elif fault == "state":
                rt.emulator.save_state_bytes = lambda: b"changed"
            else:
                rt.emulator.pressed_buttons = frozenset({"a"})
            return ()

        monkeypatch.setattr(p, "scripted_gift_bindings", changed)
    with pytest.raises(ValueError):
        p.player_collection_supplements(rt, actions, obs, world=N())


@pytest.mark.parametrize(
    "limits",
    [dict(maximum_actions=0), dict(maximum_frames=True), dict(maximum_evolution_quanta=-1)],
)
def test_execution_limits_are_explicit_positive_integers(monkeypatch, limits):
    rt, actions, obs = fixture(monkeypatch)
    with pytest.raises(ValueError, match="positive integers"):
        p.player_collection_supplements(rt, actions, obs, world=N(), **limits)


@pytest.mark.parametrize("stock,expected", [
    ((), True), (((1, 1),), True), (((3, 1),), False),
    (((2, 1), (1, 1)), False), (((4, 1),), False), (None, False),
])
def test_ordinary_supply_gap_uses_observed_balls_and_preserves_master(stock, expected):
    from pokemon_red_completion.observation import RawGameState

    raw = RawGameState(True, 159, 21, 11, 6, 0, player_money=2117, bag_items=stock)
    assert p.ordinary_ball_resupply_peer_needed(raw, hall_of_fame=False) is expected
    assert p.ordinary_ball_resupply_peer_needed(raw, hall_of_fame=True)
    assert raw.bag_items == stock


@pytest.mark.parametrize("flag", [None, 1, "yes"])
def test_ordinary_supply_gap_does_not_invent_completion(flag):
    from pokemon_red_completion.observation import RawGameState

    with pytest.raises(ValueError, match="explicit boolean"):
        p.ordinary_ball_resupply_peer_needed(RawGameState(True, 159, 21, 11, 6, 0),
                                              hall_of_fame=flag)
