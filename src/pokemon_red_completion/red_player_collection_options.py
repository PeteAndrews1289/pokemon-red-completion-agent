"""Existing collection mechanisms as peers of story, recovery and development.

Enumeration is action-free and selects no destination/species. All executors,
registration guards and native resource checks remain owned by their existing
providers. Missing capabilities remain absent, never teacher-selected chapters.
"""

from dataclasses import replace

from .goal_manager import GoalAvailability, GoalKind, GoalOpportunity, GoalUnavailableReason
from .goal_manager_runtime import GoalBindingSet
from .living_dex_goal_policy import project_living_dex_goal_candidate
from .red_autonomous_fishing import autonomous_fishing_options
from .red_autonomous_safari import autonomous_safari_options
from .red_fossil_acquisition import fossil_acquisition_bindings
from .red_goal_context_profile import (
    RedGoalMechanic,
    _thaw,
    bind_capture_access_requirements_profile,
    bind_capture_cut_profile,
    bind_capture_fly_profile,
    bind_capture_surf_profile,
    bind_evolution_fly_profile,
    bind_indoor_fly_departure_profile,
    bind_observed_local_capture_profile,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)
from .red_goal_skills import _ORDINARY_CAPTURE_ITEMS
from .red_item_evolution_options import enumerate_red_item_evolutions
from .red_level_evolution_options import enumerate_red_level_evolutions
from .red_live_option_menu import supplemental_live_option
from .red_living_dex_wild_corridor import (
    RedLivingDexWildCorridor,
    bind_red_capture_search_budget_profile,
    bind_red_capture_weakening_profile,
)
from .red_npc_trade_options import npc_trade_bindings
from .red_player_field_goals import _field_ready
from .red_regional_acquisition import enumerate_red_regional_acquisitions
from .red_scripted_gift import scripted_gift_bindings
from .red_trade_dependency_options import npc_trade_dependency_bindings


def ordinary_ball_resupply_peer_needed(raw, *, hall_of_fame: bool) -> bool:
    """Expose existing shop peers when observed ordinary balls are exhausted.

    Master Ball stock does not satisfy ordinary capture supply. This offers no
    target or inputs; the existing router still verifies cash, stock and earned
    transport, and the model still selects among the executable goals.
    """
    if type(hall_of_fame) is not bool:
        raise ValueError("Hall-of-Fame supply state requires an explicit boolean")
    if hall_of_fame:
        return True
    from .red_resource_economy import red_economy_snapshot

    if red_economy_snapshot(raw) is None:
        return False
    return not any(item in _ORDINARY_CAPTURE_ITEMS for item, _quantity in raw.bag_items)


def _wild_capture_stock_cost(candidate, binding, observation):
    """Expose one throw's share of observed ordinary-ball stock.

    This lower-bound resource exposure is not a capture probability, a purchase
    or a promise that one ball suffices. It selects no ball or action and never
    counts the protected Master Ball, gifts or paid Safari stock as bag supply.
    Existing providers alone decide whether a capture is actually executable.
    """
    source = binding.search_source_ref
    if not isinstance(source, str) or not source.startswith("pokemon.red:acquisition:wild:"):
        return candidate
    raw = getattr(observation, "raw", None)
    bag = getattr(raw, "bag_items", None)
    if bag is None:
        return candidate
    stock = sum(quantity for item, quantity in bag if item in _ORDINARY_CAPTURE_ITEMS)
    if stock <= 0:
        return candidate
    return replace(candidate, features=replace(candidate.features, resource_cost=1.0 / stock))


def bind_player_collection_capabilities(
    runtime,
    *,
    seed_corridor,
    add_capture_preparation_support=True,
    include_fly_transport=False,
    include_dig_departure=False,
):
    """Opt an existing player runtime into its existing collection executors.

    The corridor is a schema seed, not a selected destination. Regional
    enumeration retargets it from live missing registrations and verifies each
    route. Existing providers and their resource settings remain unchanged;
    conflicting capture/discovery providers are not silently replaced.
    """
    if any(type(v) is not bool for v in (
        add_capture_preparation_support, include_fly_transport, include_dig_departure
    )):
        raise TypeError("capture preparation support permission must be boolean")
    if runtime.registration_policy is None:
        raise ValueError("shared collection requires the registered objective")
    if not isinstance(seed_corridor, RedLivingDexWildCorridor):
        raise ValueError("collection composition requires a verified corridor")
    providers = tuple(
        (spec.kind, spec.mechanic, _thaw(spec.parameters)) for spec in runtime.profile.providers
    )
    required = (
        (GoalKind.ACQUIRE_SPECIES, RedGoalMechanic.WILD_CORRIDOR_CAPTURE),
        (GoalKind.EXPLORE, RedGoalMechanic.WILD_CORRIDOR_DISCOVERY),
    )
    for kind, mechanic in required:
        existing = tuple(row for row in providers if row[0] is kind)
        if existing and existing[0][1] is not mechanic:
            raise ValueError("collection composition would replace a different mechanic")
        if not existing:
            providers += ((kind, mechanic, seed_corridor.profile_parameters()),)
    profile = parse_red_goal_context_profile(
        build_red_goal_context_profile_payload(
            profile_id=runtime.profile.profile_id,
            providers=tuple(sorted(providers, key=lambda row: tuple(GoalKind).index(row[0]))),
        )
    )
    profile = bind_observed_local_capture_profile(
        bind_capture_surf_profile(bind_capture_cut_profile(profile))
    )
    # Use the existing native prerequisites before offering a destination.
    # Encounter-table knowledge alone does not make a Tower ghost capturable.
    profile = bind_capture_access_requirements_profile(profile)
    # Early parties may have no status helper yet. Plain-ball capture already
    # exists;do not make acquiring that first helper depend on owning one.
    # Explicit existing preparation parameters are never removed here.
    if add_capture_preparation_support:
        profile = bind_red_capture_weakening_profile(profile)
    profile = bind_red_capture_search_budget_profile(profile)
    if include_fly_transport:
        profile = bind_capture_fly_profile(profile)
        if any(s.mechanic in {RedGoalMechanic.TARGETED_LEVEL_EVOLUTION,
                              RedGoalMechanic.TARGETED_ITEM_EVOLUTION}
               for s in profile.providers):
            profile = bind_evolution_fly_profile(profile)
        profile = bind_indoor_fly_departure_profile(profile)
    return replace(
        runtime,
        profile=profile,
        scripted_gifts=True,
        npc_trades=True,
        moving_npc_trades=True,
        npc_trade_dependencies=True,
        safari_indoor_departure=True,
        safari_departure_recovery=True,
        safari_departure_surf=True,
        safari_complete_paid_session=True,
        collection_dig_departure=include_dig_departure or runtime.collection_dig_departure,
    )


def player_collection_supplements(
    runtime,
    actions,
    observation,
    *,
    world,
    maximum_actions=20000,
    maximum_frames=2000000,
    maximum_evolution_quanta=64,
    maximum_evolution_actions=None,
    maximum_evolution_frames=None,
    maximum_evolution_seconds=None,
    prefer_highest_evolution_venue=False,
    allow_guarded_evolution_escapes=False,
    evolution_training_venues=None,
    evolution_venue_model=None,
    evolution_venue_model_sha256=None,
    include_fossil_acquisition=False,
    unsupported_remote_capture_maps=frozenset(),
    capture_interruption_handler_wrapper=None,
    fishing_interruption_handler_wrapper=None,
    evolution_interruption_handler_wrapper=None,
    quote_capture_route_work=False,
    include_level_workload=False,
    include_capture_invocation=False,
):
    if evolution_venue_model is not None or evolution_venue_model_sha256 is not None:
        from .red_native_boxed_evolution import validate_native_evolution_venue_model
        validate_native_evolution_venue_model(evolution_venue_model, evolution_venue_model_sha256)
        if prefer_highest_evolution_venue:
            raise ValueError("native model choice cannot be prefiltered by highest-level preference")
    for bound in (maximum_evolution_actions, maximum_evolution_frames, maximum_evolution_seconds):
        if bound is not None and (type(bound) is not int or bound <= 0):
            raise ValueError('explicit evolution bounds must be positive integers')
    for permission in (prefer_highest_evolution_venue, allow_guarded_evolution_escapes,
                       include_fossil_acquisition, quote_capture_route_work, include_level_workload,
                       include_capture_invocation):
        if type(permission) is not bool:
            raise ValueError("collection evolution options require explicit booleans")
    policy = getattr(runtime, "native_evolution_venue_policy", None)
    if policy is not None:
        from .red_native_boxed_evolution import NativeEvolutionVenuePolicy
        if not isinstance(policy, NativeEvolutionVenuePolicy):
            raise ValueError("configured native venue policy differs")
        if evolution_venue_model is not None and (
            evolution_venue_model_sha256 != policy.model_sha256
            or evolution_training_venues is not None
            and evolution_training_venues != policy.training_venues
        ):
            raise ValueError("explicit native venue authority conflicts with configured policy")
        # The explicit configured learned mode owns its full declared scope.
        # The ordinary backend's legacy band preference/shortlist cannot narrow
        # that model question. Native access, safety and settlement guards remain.
        prefer_highest_evolution_venue = False
        evolution_training_venues = policy.training_venues
    if (not isinstance(unsupported_remote_capture_maps, frozenset)
            or any(type(m) is not int or not 0 <= m <= 255
                   for m in unsupported_remote_capture_maps)):
        raise ValueError("unsupported capture entries must be explicit native map IDs")
    if (capture_interruption_handler_wrapper is not None
            and not callable(capture_interruption_handler_wrapper)):
        raise TypeError("capture interruption wrapper must be callable")
    if (fishing_interruption_handler_wrapper is not None
            and not callable(fishing_interruption_handler_wrapper)):
        raise TypeError("fishing interruption wrapper must be callable")
    if (evolution_interruption_handler_wrapper is not None
            and not callable(evolution_interruption_handler_wrapper)):
        raise TypeError("evolution interruption wrapper must be callable")
    if any(
        type(n) is not int or n < 1
        for n in (maximum_actions, maximum_frames, maximum_evolution_quanta)
    ):
        raise ValueError("collection execution limits must be positive integers")
    if not _field_ready(runtime):
        return ()
    if runtime.registration_policy is None:
        raise ValueError("shared collection requires the registered objective")
    state, frames, buttons, inputs = (
        runtime.emulator.save_state_bytes(),
        runtime.emulator.frame_count,
        runtime.emulator.pressed_buttons,
        actions.actions_executed,
    )
    live = runtime.adapter.observe()
    # The regional survey already stops before input if any member is fainted.
    # Keep legacy provider fingerprints intact, but do not present that known
    # zero-action capture as a real alternative in the current player menu.
    capture_party_ready = all(member.hp > 0 for member in live.party.members)
    acquisitions = tuple(
        row.binding
        for row in enumerate_red_regional_acquisitions(
            runtime,
            live,
            actions,
            world,
            maximum_actions=maximum_actions,
            maximum_frames=maximum_frames,
            **({"unsupported_remote_maps": unsupported_remote_capture_maps}
               if unsupported_remote_capture_maps else {}),
            **({"interruption_handler_wrapper": capture_interruption_handler_wrapper}
               if capture_interruption_handler_wrapper is not None else {}),
            **({"quote_capture_route_work": True} if quote_capture_route_work else {}),
        )
    ) if capture_party_ready else ()
    acquisitions += scripted_gift_bindings(runtime, live, actions, world)
    if include_fossil_acquisition:
        acquisitions += fossil_acquisition_bindings(
            runtime, live, actions, world,
            maximum_actions=maximum_actions, maximum_frames=maximum_frames,
        )
    acquisitions += npc_trade_dependency_bindings(
        runtime,
        live,
        actions,
        world,
        maximum_actions=maximum_actions,
        maximum_frames=maximum_frames,
        maximum_quanta=maximum_evolution_quanta,
    )
    acquisitions += npc_trade_bindings(
        runtime, live, actions, world, include_moving=getattr(runtime, "moving_npc_trades", False)
    )
    evolutions = enumerate_red_item_evolutions(
        runtime,
        live,
        actions,
        world,
        maximum_actions=maximum_actions,
        maximum_frames=maximum_frames,
        **({"interruption_handler_wrapper": evolution_interruption_handler_wrapper}
           if evolution_interruption_handler_wrapper is not None else {}),
    )
    evolutions += enumerate_red_level_evolutions(
        runtime,
        live,
        actions,
        world,
        maximum_actions=(maximum_actions if maximum_evolution_actions is None
                         else maximum_evolution_actions),
        maximum_frames=(maximum_frames if maximum_evolution_frames is None
                        else maximum_evolution_frames),
        maximum_quanta=maximum_evolution_quanta,
        **({"include_level_workload": True} if include_level_workload else {}),
        **({'maximum_wall_seconds':maximum_evolution_seconds}
           if maximum_evolution_seconds is not None else {}),
        **({"prefer_highest_supported_venue": True} if prefer_highest_evolution_venue else {}),
        **({"allow_guarded_venue_escapes": True} if allow_guarded_evolution_escapes else {}),
        **({"training_venues": evolution_training_venues}
           if evolution_training_venues is not None else {}),
        **({"venue_model": evolution_venue_model, "venue_model_sha256": evolution_venue_model_sha256}
           if evolution_venue_model is not None else {}),
        **({"interruption_handler_wrapper": evolution_interruption_handler_wrapper}
           if evolution_interruption_handler_wrapper is not None else {}),
    )
    result = []
    for binding, evolution in tuple((b, None) for b in acquisitions) + tuple(
        (row.binding, row) for row in evolutions
    ):
        mask = GoalOpportunity(
            "collection:projection-mask",
            GoalKind.EXPLORE,
            GoalAvailability.UNAVAILABLE,
            unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET,
        )
        question = GoalBindingSet((binding.opportunity, mask), (binding,)).question(
            observation.situation
        )
        candidate = project_living_dex_goal_candidate(
            question, 0, feature_version=5, binding_ref=binding.binding_ref
        )
        if candidate is None:
            raise ValueError("collection mechanism lacks its portable projection")
        candidate = _wild_capture_stock_cost(candidate, binding, live)
        if evolution is not None:
            candidate = replace(candidate, economy_offer=evolution.economy_offer)
            if include_level_workload:
                candidate = replace(candidate, level_workload=evolution.level_workload)
            if evolution.execution_effort is not None:
                candidate = replace(
                    candidate,
                    features=replace(
                        candidate.features, execution_effort=evolution.execution_effort
                    ),
                )
        result.append(supplemental_live_option(binding, candidate))
    result.extend(autonomous_fishing_options(runtime, live, actions, world, **(
        {} if fishing_interruption_handler_wrapper is None else {
            "interruption_handler_wrapper": fishing_interruption_handler_wrapper,
        }
    )))
    result.extend(autonomous_safari_options(runtime, live, actions, world,
        **({"include_capture_invocation": True} if include_capture_invocation else {})))
    if len({row.binding.binding_ref for row in result}) != len(result):
        raise ValueError("collection mechanisms repeat a native executor")
    if (
        runtime.emulator.save_state_bytes(),
        runtime.emulator.frame_count,
        runtime.emulator.pressed_buttons,
        actions.actions_executed,
    ) != (state, frames, buttons, inputs):
        raise ValueError("collection observer changed native state")
    return tuple(result)
