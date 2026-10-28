"""Current-source native story composition, not a supplied chapter sequence.

Reuses native gym/arrival adapters, mixed inventory, frozen parent and authentic
continuation. Missing interaction capabilities are reported, never substituted
with the legacy teacher registry. This first command is strictly zero-input.
"""
import json
import sys
from contextlib import nullcontext
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

import player_coherent_session as shared
import red_configured_league_player_20261006 as d
from pokemon_red_completion.executor import CountingExecutor, FrameSafeExecutor, ReadOnlyController
from pokemon_red_completion.goal_manager import GoalKind, GoalOpportunity, GoalAvailability, GoalUnavailableReason
from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
from pokemon_red_completion.player_option_challenge import OptionChallenge
from pokemon_red_completion.red_autonomous_player import _record, _write
from pokemon_red_completion.red_development_story_scope import DevelopmentStoryScope
from pokemon_red_completion.red_development_preparation_scope import DevelopmentPreparationScope
from pokemon_red_completion.red_gym_reward import (
    BROCK_REWARD, MISTY_REWARD, SURGE_REWARD, ERIKA_REWARD,
    KOGA_REWARD, SABRINA_REWARD, BLAINE_REWARD, GIOVANNI_REWARD,
)
from pokemon_red_completion.red_live_option_menu import (
    RedLiveOptionSet, select_red_live_option, supplemental_live_option,
)
from pokemon_red_completion.living_dex_goal_policy import project_living_dex_goal_candidate
from pokemon_red_completion.red_player_battle_history import NativeBattlerHistory
from pokemon_red_completion.red_player_continuation import (
    restore_player_continuation, capture_player_continuation, accumulate_player_costs,
    _plan, _battle, refresh_preparation_roster,
)
from pokemon_red_completion.red_player_field_goals import (
    nearest_reachable_player_center, routed_restoration_binding, _raw_party_fully_restored,
    _field_ready,
)
from pokemon_red_completion.red_goal_skills import RedControlRecoveryGoalProvider
from pokemon_red_completion.red_player_gym import gym_story_option
from pokemon_red_completion.red_player_gym_switches import (
    gym_switch_binding, visible_locks, next_can, can_stances,
)
from pokemon_red_completion.red_player_cut_lesson import cut_lesson_binding
from pokemon_red_completion.red_player_lesson_runtime import observe_native_player_options
from pokemon_red_completion.red_player_story_menu import (
    NativeStoryBranchInventory, registered_story_branches,
)
from pokemon_red_completion.red_player_story_obstruction import obstructing_story_battle_binding
from pokemon_red_completion.red_player_early_story_options import (
    bill_story_option, cerulean_arrival_story_option, cut_story_option, early_story_travel_option, fuji_story_option,
    hideout_story_option, parcel_story_option, saffron_story_option,
)
from pokemon_red_completion.red_player_collection_options import (
    bind_player_collection_capabilities, player_collection_supplements,
)
from pokemon_red_completion.red_autonomous_fishing import (
    acquired_fishing_tool_dialogue_binding, autonomous_fishing_prerequisite_option,
)
from pokemon_red_completion.red_safari_exit import retained_safari_exit_binding
from pokemon_red_completion.red_player_fly import fly_dependency_options
from pokemon_red_completion.red_player_owned_machines import owned_machine_options
from pokemon_red_completion.red_game_corner_goals import (
    game_corner_options, game_corner_coin_options,
)
from red_eevee_gift_20261004 import eevee_gift_bindings, gift_route_world
from red_remaining_acquisitions_20261004 import amber_bindings
from red_mixed_static_options_20261009 import postgame_native_oneoff_bindings
from pokemon_red_completion.red_player_static_approach import static_approach_option
from pokemon_red_completion.red_player_story_travel import ARRIVAL_OBJECTIVES, DESTINATIONS, story_travel_binding
from pokemon_red_completion.global_router import find_macro_path, GlobalRouterError
from pokemon_red_completion.red_player_safari_rewards import safari_reward_story_option
from pokemon_red_completion.red_player_silph import (
    silph_card_key_story_option, silph_continuation_story_option, silph_continuation_phase,
)
from pokemon_red_completion.red_silph_continuation import silph_continuation_contract
from pokemon_red_completion.red_player_field_item import (
    field_item_story_option, field_item_resupply_binding,
)
from pokemon_red_completion.red_player_mansion import mansion_secret_key_option, mansion_exit_option, mansion_restoration_binding, mansion_departure_world
from pokemon_red_completion.red_player_hideout import hideout_restoration_binding
from pokemon_red_completion.red_player_wild_recovery import interrupted_wild_binding
from pokemon_red_completion.red_player_field_blackout import field_blackout_binding
from pokemon_red_completion.red_player_forced_motion import (
    interrupted_motion_binding, interrupted_pewter_escort_binding,
)
from pokemon_red_completion.red_player_victory_road import victory_road_story_option
from pokemon_red_completion.red_postgame import postgame_return_binding
from pokemon_red_completion.red_player_route22_rival import (
    route22_rival_contract, route22_preparation_contract,
)
from pokemon_red_completion.red_player_league_options import (
    bind_live_league_runtime, league_story_option, live_league_player_target,
    league_native_prerequisite,
    league_medicine_profiles, league_medicine_reserve_binding,
    league_pre_entry_healing_binding,
    LEAGUE_PLAYER_TARGETS, CHAMPION_PLAYER_TARGET,
)
from pokemon_red_completion.red_faint_recovery import RedFaintAwareFieldRestoreGoalProvider
from pokemon_red_completion.red_field_pp_restore import (
    RedCombinedFieldRestoreGoalProvider, RedFieldPpRestoreGoalProvider,
)
from pokemon_red_completion.red_player_engaged_story import (
    EngagedStoryRouteHandler, engaged_story_binding, retained_ordinary_transport_binding,
)
from pokemon_red_completion.red_story_item_storage import completed_key_storage_binding
from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_resource_goal_router import RedResourceGoalRouter
from pokemon_red_completion.red_snorlax_capture import route12_snorlax_target
from pokemon_red_completion.observation import event_flag_is_set
from pokemon_red_completion.red_native_player import NativePlayerLimits, run_native_continuous_player
from pokemon_red_completion.red_learned_trainer import (
    FROZEN_K_SHA256, K_QUALIFICATION_SHA256, FrozenTrainerBattler,
)
from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel
from pokemon_red_completion.red_trainer_practice_log import verify_trainer_practice_event_log
from pokemon_red_completion.red_capture_preparation import optional_status_static_offer
from pokemon_red_completion.red_capture_readiness import (
    CapturePreparationBudget, carried_static_capture_choice, capture_reserve_purchase,
)
from pokemon_red_completion.red_static_capture_goal import RedStaticCaptureGoalProvider
from pokemon_red_completion.observation import ItemId, MapId
from pokemon_red_completion.red_regional_trainer_funding import FundingGateTransit
from pokemon_red_completion.red_player_member_preparation import (
    member_preparation_options, preparation_venue_rank, preparation_venue_within_party_band,
)
from pokemon_red_completion.gen1_cartridge import wild_tables
from pokemon_red_completion.gen1_trainer_parties import trainer_party_quote
from pokemon_red_completion.gen1_route_runtime import Gen1TraversalObserver
from pokemon_red_completion.gen1_trainer_sight import (
    Gen1TrainerSightProjector, static_trainer_sight_zones, trainer_headers,
)
from pokemon_red_completion.local_router import without_coordinates
from pokemon_red_completion.gen1_traversal import cut_capabilities, map_object_events
from pokemon_red_completion.red_living_dex_wild_corridor import derive_red_living_dex_wild_corridor
from pokemon_red_completion.red_living_dex_provider_curriculum import RedEncounterSourceTarget
from pokemon_red_completion.red_living_dex_multifamily_curriculum import map_id_for_wild_source
from pokemon_red_completion.route_plan import RoutePlanningError
from pokemon_red_completion.hideout import HideoutTiming
from pokemon_red_completion.red_goal_context_profile import (
    _thaw, build_red_goal_context_profile_payload, parse_red_goal_context_profile,
    bind_ordinary_trainer_funding_profile, bind_resupply_fly_profile,
)

c = d.c
ROOT = c.BASE/'red-whole-player-inventory-20261006-v1'
SOURCE = c.BASE/'red-silph-coverage-20261005-v1/fresh-pilot/runs/segment-22'
SOURCE_SHA = '61ee538c0c0a075323e724e11c138006bf7843b4fdc5efae2bba460247a2cdfe'
CONTEXT_SHA = '94f268cf4aa263ef603a6b473f46cbc8decd843f10939e0e5d74f177d01efa5e'
REWARDS = (BROCK_REWARD, MISTY_REWARD, SURGE_REWARD, ERIKA_REWARD,
           KOGA_REWARD, SABRINA_REWARD, BLAINE_REWARD, GIOVANNI_REWARD)


def local_story_prefix_option(runtime, actions, *, objective_id, route):
    """Reuse a guarded first boundary when multiple field mutations block a full quote.

    Topology only establishes relevance. The existing binding independently quotes
    the original observed state, preserves every gate, and never credits completion.
    """
    if not _field_ready(runtime):
        return None
    raw = runtime.reader.read()
    try:
        corridor = find_macro_path(route.route_world.macro_graph, raw.map_id,
            DESTINATIONS[objective_id], last_outside=runtime.reader.read_retained_outside_map())
    except GlobalRouterError:
        return None
    if len(corridor.maps) < 3:
        return None
    binding = story_travel_binding(runtime, actions, objective_id=objective_id,
        route=route, intermediate_map=corridor.maps[1], stop_at_map_boundary=True)
    return (None if binding is None else
        (binding, OptionChallenge(False, False, 0., 0., 0.)))


def player_healing_route(runtime, *, route):
    """Quote and execute selected nursing with the existing noncombat lane mask.

    A cheap cross-map walk is not a healing capability if it needs an unhandled
    trainer fight. Reuse the Fly dependency's conservative future-map projection;
    the current map and defeated events remain live, and no battle is supplied.
    """
    if _raw_party_fully_restored(runtime.reader.read()):
        return route
    from pokemon_red_completion.red_player_fly import _noncombat_fly_world
    return replace(route, route_world=_noncombat_fly_world(
        route.route_world, runtime.reader.read()))


def player_nurse_binding(runtime, actions, *, route, home, include_rewards, bindings=None):
    """Use the existing dynamic-lift contract before generic ground recovery."""
    if (bindings is not None and getattr(runtime,'collection_dig_departure',False)
            and not _raw_party_fully_restored(runtime.reader.read())):
        from pokemon_red_completion.red_dig_recovery import bind_dig_recovery
        from pokemon_red_completion.red_goal_context_profile import bind_dig_recovery_profile
        router = RedResourceGoalRouter(replace(runtime,
            profile=bind_dig_recovery_profile(runtime.profile)),actions,route.route_world)
        escaped = bind_dig_recovery(router,bindings,runtime.adapter.observe(),
            Gen1TraversalObserver(runtime.reader).observe(),prepare_escort=lambda:None,
            require_pp_restore=True)
        nurse = next((b for b in escaped.bindings
                      if b.kind is GoalKind.RESTORE_TEAM
                      and b.binding_ref.startswith('pokemon.red:recovery:dig:')),None)
        if nurse is not None:
            return nurse
    specific = (hideout_restoration_binding(runtime, actions, route=route)
                if include_rewards else None)
    if specific is None and include_rewards:
        specific = mansion_restoration_binding(runtime, actions, route=route)
    if specific is not None:
        return specific
    return (routed_restoration_binding(runtime, actions, home_map=home, route=route,
        include_indigo_lobby=home == int(c.MapId.INDIGO_PLATEAU_LOBBY),
        observe_trainer_hazards=True, allow_blackout_return=True,
        alternate_centers=frozenset(int(value) for name, value in c.MapId.__members__.items()
                                   if name.endswith('POKECENTER')))
        if home is not None else None)


def paused_prefix_rows(parent):
    """Authenticate the user-stopped48prefix; never invent an episode result."""
    assert parent == ROOT/'native-48'
    path = ROOT/'PAUSE-AUDIT-48.json'
    assert c.digest(path) == '4054cd4e96fc7a58545551594a5d3695aadbd395e603a81d66bccc6052fd8937'
    proof = d.prior.doc(path)
    assert proof['passed'] and proof['paused_between_goals']
    assert proof['worker']['actual_stop_confirmed'] and proof['worker']['exit_code'] == 130
    assert proof['inputs'] == proof['frames'] == 0
    assert proof['terminal_equals_completed_step003'] and proof['completed_goal_prefix'] == 4
    result, context = (d.prior.doc(parent/name) for name in ('RESULT.json','CONTEXT.json'))
    assert not result['passed'] and 'episode' not in result and result['error'] is None
    assert result['released'] and result['native_session_released']
    assert c.digest(parent/'CONTEXT.json') == proof['context_sha256'] == result['context_sha256']
    assert c.digest(parent/'terminal.state') == proof['state_sha256'] == result['state_sha256']
    assert context['spent'] == result['spent'] == proof['recorded_spent']
    previous = proof['source_sha256']
    rows = []
    for ordinal in range(4):
        step = parent/'native/episode'/f'step-{ordinal:03d}'
        row = d.prior.doc(step/'outcome.json')
        assert row['before_state_sha256'] == previous == c.digest(step/'before.state')
        assert row['terminal_state_sha256'] == c.digest(step/'terminal.state')
        assert row['safe_terminal'] and (row['verification'] == 'succeeded'
            or (row['ordinary_setback'] and row['verification'] == 'failed'))
        previous = row['terminal_state_sha256']
        rows.append(row)
    assert previous == proof['state_sha256']
    assert rows[-1]['after']['player_lesson'] == context['lesson']
    debit = sum(max(0,row['before']['cash']-row['after']['cash']) for row in rows)
    assert debit == proof['additive_cash_debit_to_carry'] == 1654
    assert proof['corrected_spent'] == dict(context['spent'],cash_debits=context['spent']['cash_debits']+debit)
    meter = d.prior.doc(parent/'native/native-costs.json')
    assert meter['goal_attempts'] == 4 and meter['actions_attempted'] == 5162
    assert meter['frames'] == result['native_frames'] == 394830
    assert meter['buttons_released'] and meter['restore_attempts'] == 6
    return tuple(rows), proof


def carried_spent(parent, context):
    """Apply only previously audited omissions at their original boundary."""
    if parent.name == 'native-48':
        _, proof = paused_prefix_rows(parent)
        return proof['corrected_spent']
    if parent.name == 'native-43':
        proof = d.prior.doc(ROOT/'RETAINED-TRAINER-43-AUDIT.json')
        assert proof['passed'] and proof['terminal_sha256'] == context['state_sha256']
        assert proof['cash_debit_correction'] == 6617
        return dict(context['spent'],cash_debits=context['spent']['cash_debits']+6617)
    return context['spent']


def supply_profile(profile, *, early_supply=False):
    """Reuse the natively executed Saffron clerk; quantity is not learned."""
    providers = [(spec.kind, spec.mechanic, _thaw(spec.parameters))
                 for spec in profile.providers if spec.kind is not GoalKind.RESUPPLY]
    providers.append((GoalKind.RESUPPLY, c.RedGoalMechanic.MART_RESUPPLY,
        dict(map_id=int(c.MapId.VIRIDIAN_MART if early_supply else c.MapId.SAFFRON_MART), player_x=2, player_y=5,
             interaction_direction='left',
             purchases=[dict(absolute_index=0, item_id=int(ItemId.POKE_BALL if early_supply else ItemId.GREAT_BALL),
                             quantity=5 if early_supply else 8, unit_price=200 if early_supply else 600)],
             **(dict(affordable_ball_purchase=True, resource_choice_variants=True) if early_supply else
                dict(reserve_targets=[dict(item_id=int(ItemId.GREAT_BALL),quantity=8)])))))
    providers.sort(key=lambda row: tuple(GoalKind).index(row[0]))
    return parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id='whole-player-optional-eight-great-balls-v1', providers=tuple(providers)))


def player_supply_profile(profile, *, early_preparation, completed):
    """Retain early stock until earned Fuji unlocks the existing midgame supply.

    This offers a purchase only; it never forces a shop, supplies funds or
    fabricates route feasibility. The old early profile remains unchanged.
    """
    return supply_profile(profile, early_supply=(
        early_preparation and 'rescue_fuji' not in completed))


def player_supply_reserve(profile):
    """Use the existing costed top-up for the declared midgame eight-ball order."""
    spec = next((s for s in profile.providers if s.kind is GoalKind.RESUPPLY),None)
    if spec is None or spec.parameters.get('reserve_targets') != (
        {'item_id':int(ItemId.GREAT_BALL),'quantity':8},):
        return None
    return CapturePreparationBudget(ItemId.GREAT_BALL,8,8,require_status=True)


def _postgame_funding_gate_transit(runtime, world, *, include_legal_fly=False):
    """Reuse one fully inventoried ordinary gate, not a trainer target order."""
    start = Gen1TraversalObserver(runtime.reader).observe()
    if not start.ready or start.interruption is not None or start.mode != 'land':
        return None
    region=frozenset({int(MapId.FUCHSIA_CITY),int(MapId.ROUTE_13),
        int(MapId.ROUTE_14),int(MapId.ROUTE_15),int(MapId.ROUTE_15_GATE_1F)})
    if start.map_id not in region and start.last_outside_map not in region:
        # A second, explicitly requested inventory may reach the same fixed
        # region by native Fly. Never replace the ordinary town inventory.
        if include_legal_fly is not True:
            return None
        from pokemon_red_completion.red_regional_trainer_funding import (
            observed_fly_funding_gate_region,
        )
        return observed_fly_funding_gate_region(world,start,
            FundingGateTransit(region,frozenset({int(MapId.ROUTE_15_GATE_1F)}),6),
            runtime.reader.read_fly_destinations())
    maps = frozenset({start.map_id, int(MapId.FUCHSIA_CITY), int(MapId.ROUTE_13),
                      int(MapId.ROUTE_14), int(MapId.ROUTE_15),
                      int(MapId.ROUTE_15_GATE_1F)} | (
                          {start.last_outside_map} if start.last_outside_map is not None else set()))
    if (not maps <= set(world.macro_graph.edges)
            or not maps <= set(world.local_graphs)
            or not maps <= set(world.object_blockers)
            or any(world.macro_graph.retained_outside_overrides.get(m, m) not in maps
                   for m in maps)):
        return None
    return FundingGateTransit(maps, frozenset({int(MapId.ROUTE_15_GATE_1F)}), 6)


def declared_income_goal_model_sha256(declaration):
    """Income reuse binds the current authenticated learner, not a retired head."""
    from pokemon_red_completion.red_player_configuration import RedPlayerConfiguration

    if 'configuration' not in declaration:
        return 'f86aeecb94011a94988ea8bea30bf781bac76cbc1ee70c220ff6090d537b83f9'
    configured=RedPlayerConfiguration.from_dict(declaration['configuration'])
    if configured.sha256 != declaration.get('configuration_sha256'):
        raise ValueError('Income reuse player configuration binding differs')
    return configured.goal_model_sha256


def postgame_collection_funding_target_cash(runtime, economy, world):
    """Use the same real missing-resource quotes as renewable League income.

    A healthy ball reserve does not pay a Safari fee, stone, prize or bird lot.
    This is executable funding demand, not a prescribed purchase/target order,
    a standing wealth quota or a learned-budgeting claim. Alternatives are
    compared by maximum demand, not summed as if jointly funded.
    """
    if economy is None:
        return None
    from overnight_red_player_20261004 import unmet_stone_purchase
    from red_remaining_acquisitions_20261004 import unmet_prize_cash
    from red_mixed_bird_collection_20261009 import unmet_bird_stock_cash

    prize=unmet_prize_cash(runtime,economy,world.rom)
    if prize and getattr(getattr(runtime,'league_battle_controller',None),
                         'income_owned_stock_bootstrap',False) is True:
        from pokemon_red_completion.red_game_corner_resources import quote_game_corner_prize
        # Legacy unmet_prize_cash returns held cash when already satisfied.
        # Do not mistake that no-shortfall sentinel for another purchase price.
        if 137 in runtime.reader.read_pokedex_state().owned_species:
            prize=0
        else:
            raw=runtime.reader.read()
            quote=quote_game_corner_prize(world.rom,species=137,
                coins=runtime.reader.read_game_corner_coins(),cash=economy.cash,
                bag=raw.bag_items)
            if quote is not None:
                prize=quote.cash_cost
                if prize:
                    prize+=income_reserve_cost(raw,targets=(2,3,1))
    return max(1000,
        unmet_stone_purchase(runtime,runtime.adapter.observe(),world),
        prize,unmet_bird_stock_cash(runtime))


def postgame_ball_supply_peers(runtime, actions, world, *, interruption_handler_wrapper):
    """Quote existing ordinary-ball shops, never force a destination.

    A western postgame boundary may not reach the fixed midgame Saffron clerk.
    Reuse the native-qualified early Viridian profile as an alternative rather
    than hiding an affordable purchase behind an unrelated regional route.
    Postgame peers opt into existing guarded Fly/indoor-egress transport; the
    underlying early-story supply profiles retain their walking-only defaults.
    """
    observation = runtime.adapter.observe()
    from pokemon_red_completion.red_player_collection_options import ordinary_ball_resupply_peer_needed
    if not ordinary_ball_resupply_peer_needed(
            observation.raw, hall_of_fame='enter_hall_of_fame' in set(
                runtime.adapter.graph.completed_ids(observation.game_state))):
        return ()
    rows = []
    owner = getattr(runtime.trainer_battle_runner, '__self__', None)
    funding_enabled = (
        isinstance(owner, FrozenTrainerBattler)
        and owner.model_sha256 == FROZEN_K_SHA256
        and owner.qualification_sha256 == K_QUALIFICATION_SHA256
        and runtime.trainer_battle_model_sha256 == owner.model_sha256
        and runtime.trainer_battle_qualification_sha256 == owner.qualification_sha256)
    funding_target = None
    if funding_enabled:
        from pokemon_red_completion.red_resource_economy import red_economy_snapshot
        funding_target = postgame_collection_funding_target_cash(
            runtime,red_economy_snapshot(runtime.reader.read()),world)
    early = supply_profile(runtime.profile, early_supply=True)
    if funding_enabled:
        early = bind_ordinary_trainer_funding_profile(early)
    profiles = [early, supply_profile(runtime.profile)]
    from pokemon_red_completion.red_fossil_acquisition import LOCAL_CINNABAR_MAPS

    if runtime.reader.read().map_id in LOCAL_CINNABAR_MAPS:
        from pokemon_red_completion.red_living_dex_provider_curriculum import RedResupplyTarget

        providers = [(spec.kind, spec.mechanic, _thaw(spec.parameters))
                     for spec in runtime.profile.providers if spec.kind is not GoalKind.RESUPPLY]
        parameters = RedResupplyTarget(8).parameters()
        parameters['reserve_targets'] = [dict(item_id=int(ItemId.GREAT_BALL), quantity=8)]
        providers.append((GoalKind.RESUPPLY, c.RedGoalMechanic.MART_RESUPPLY, parameters))
        providers.sort(key=lambda row: tuple(GoalKind).index(row[0]))
        profiles.append(parse_red_goal_context_profile(build_red_goal_context_profile_payload(
            profile_id='whole-player-local-cinnabar-great-balls-v1', providers=tuple(providers))))
    for profile in profiles:
        profile = bind_resupply_fly_profile(profile)
        configured = replace(runtime, profile=profile)
        income = any(spec.kind is GoalKind.RESUPPLY
                     and spec.parameters.get('composable_trainer_funding') is True
                     for spec in profile.providers)
        gate = _postgame_funding_gate_transit(configured,world) if income else None
        # The fully inventoried local gate is an additional income capability,
        # not a replacement for independently qualified ordinary town flights.
        # Keep each router's exact scope; do not union maps or relax its guards.
        transits = (gate,None) if gate is not None else (None,)
        for transit in transits:
            inventory = RedResourceGoalRouter(configured, actions, world,
                quote_resource_costs=True, prepare_capture_party=False,
                prepare_capture_escort=False, include_recovery_offers=False,
                trainer_funding=income, regional_trainer_funding=income,
                observed_trainer_funding=income,
                trainer_funding_target_cash=funding_target if income else None,
                funding_gate_transit=transit,
                capture_reserve=player_supply_reserve(profile),
                interruption_handler_wrapper=interruption_handler_wrapper).enumerate_routed_kinds(
                    observation, frozenset({GoalKind.RESUPPLY}))
            rows.extend(b for b in inventory.bindings if b.kind is GoalKind.RESUPPLY)
    return tuple({b.binding_ref:b for b in rows}.values())


def story_static_income_peers(runtime, actions, world, *, battler):
    """Connect existing earned income to the real unfinished Snorlax reserve gap.

    No capture minimum, model or battle qualifier changes. This offers income,
    not a capture/purchase or a supplied strategy; subsequent menus observe the
    earned wallet and existing shop/capture skills independently.
    """
    if not _field_ready(runtime):
        return ()
    observation = runtime.adapter.observe()
    raw = observation.raw
    if (raw.bag_items is None or raw.player_money is None
            or not dict(raw.bag_items).get(int(ItemId.POKE_FLUTE))
            or carried_static_capture_choice(dict(raw.bag_items)) is not None
            or 'reach_fuchsia' not in {
                o.id for o in runtime.adapter.graph.available_objectives(observation.game_state)}
            or 143 in runtime.reader.read_pokedex_state().owned_species):
        return ()
    target = route12_snorlax_target(world.rom)
    if event_flag_is_set(raw.event_flags, target.event_flag):
        return ()
    budget = player_supply_reserve(runtime.profile)
    if budget is None:
        return ()
    _, quote = capture_reserve_purchase(observation, budget,
        runtime.provider_for(GoalKind.RESUPPLY, actions))
    target_cash = quote['full_reserve_cost']
    if raw.player_money >= target_cash:
        return ()
    if (not isinstance(battler, FrozenTrainerBattler)
            or battler.model_sha256 != FROZEN_K_SHA256
            or battler.qualification_sha256 != K_QUALIFICATION_SHA256):
        return ()
    configured = replace(runtime,
        profile=bind_ordinary_trainer_funding_profile(supply_profile(runtime.profile,early_supply=True)),
        trainer_battle_runner=battler.run,
        trainer_battle_model_sha256=battler.model_sha256,
        trainer_battle_qualification_sha256=battler.qualification_sha256,
        trainer_funding_recovery=True,trainer_funding_ledges=True,
        trainer_funding_surf=True,trainer_funding_indoor_departure=True)
    inventory = RedResourceGoalRouter(configured,actions,world,
        quote_resource_costs=True,prepare_capture_party=False,prepare_capture_escort=False,
        include_recovery_offers=False,trainer_funding=True,regional_trainer_funding=True,
        observed_trainer_funding=True,trainer_funding_target_cash=target_cash
        ).enumerate_routed_kinds(observation,frozenset({GoalKind.RESUPPLY}))
    return tuple(b for b in inventory.bindings if b.kind is GoalKind.RESUPPLY
        and b.resource_quote is not None and b.resource_quote.expected_income > 0
        and b.resource_quote.purchase_cost == 0)


def pre_champion_medicine_income_peers(runtime, actions, world):
    """Expose existing ordinary income for an actual first/postgame reserve gap.

    The model chooses whether to earn. Trainer selection, travel and nursing
    remain existing execution support. No ball purchase, reward or medicine is
    invented; the cash target is only the priced missing approved stock.
    """
    observation = runtime.adapter.observe()
    raw = observation.raw
    completed = set(runtime.adapter.graph.completed_ids(observation.game_state))
    if raw.badge_bits != 255:
        return ()
    target = income_reserve_cost(raw, targets=(4,6,2))
    if raw.player_money is None or raw.player_money >= target:
        return ()
    owner = getattr(runtime.trainer_battle_runner, '__self__', None)
    if (not isinstance(owner,FrozenTrainerBattler)
            or owner.model_sha256 != FROZEN_K_SHA256
            or owner.qualification_sha256 != K_QUALIFICATION_SHA256
            or runtime.trainer_battle_model_sha256 != owner.model_sha256
            or runtime.trainer_battle_qualification_sha256 != owner.qualification_sha256):
        return ()
    profile = bind_ordinary_trainer_funding_profile(
        supply_profile(runtime.profile,early_supply=True))
    configured = replace(runtime,profile=profile)
    def enumerate_income(gate):
        inventory = RedResourceGoalRouter(configured,actions,world,
            quote_resource_costs=True,prepare_capture_party=False,
            prepare_capture_escort=False,include_recovery_offers=False,
            trainer_funding=True,regional_trainer_funding=True,
            observed_trainer_funding=True,trainer_funding_target_cash=target,
            funding_gate_transit=gate
            ).enumerate_routed_kinds(observation,frozenset({GoalKind.RESUPPLY}))
        return tuple(b for b in inventory.bindings if b.kind is GoalKind.RESUPPLY
            and b.resource_quote is not None and b.resource_quote.expected_income > 0
            and b.resource_quote.purchase_cost == 0)
    ordinary_gate = _postgame_funding_gate_transit(configured,world)
    ordinary = enumerate_income(ordinary_gate)
    if ordinary:
        return ordinary
    fly_gate = _postgame_funding_gate_transit(configured,world,include_legal_fly=True)
    return (() if fly_gate is None or fly_gate == ordinary_gate
            else enumerate_income(fly_gate))


def late_collection_deferred(runtime, *, league_first=False):
    """Explicit DEVELOPMENT work-order sequencing, not learned anticipation."""
    if type(league_first) is not bool:
        raise ValueError('League-first collection scope requires an explicit boolean')
    return (league_first and runtime.reader.read().badge_bits == 255
        and 'enter_hall_of_fame' not in set(runtime.adapter.graph.completed_ids(
            runtime.adapter.observe().game_state)))


def league_entry_medicine_ready(raw):
    """Lean disclosed entry floor; larger approved targets remain optional top-ups."""
    stock = dict(raw.bag_items or ())
    return all(stock.get(int(item),0) >= quantity for item,quantity in (
        (ItemId.FULL_RESTORE,2),(ItemId.REVIVE,3),(ItemId.FULL_HEAL,1),
    ))


def retained_preparation_opposition(preview_levels, lost):
    """A known harder loss does not disappear when a gauntlet restarts at Lorelei."""
    if lost is not None and lost.opponent_levels and (
            not preview_levels or max(lost.opponent_levels) > max(preview_levels)):
        return lost.opponent_levels
    return preview_levels


def postgame_field_supply_peers(runtime, actions, *, route, include_evolution_stones=False):
    """Expose finite native medicine pickups, never force a resource goal.

    The existing delivery binding verifies availability, transport and exact
    earned stock. Full Restore can establish the existing League-income reserve
    without fabricating money or weakening that qualification. No pickup is
    executed during inventory; held items cease to offer another copy.
    """
    if type(include_evolution_stones) is not bool:
        raise TypeError('finite evolution resources require an explicit boolean')
    if runtime.reader.read().badge_bits != 255:
        return ()
    raw = runtime.reader.read()
    # This peer promises no cash change. Reserve off-map undefeated trainer
    # lanes with the existing noncombat quote; live arrival still rebinds
    # objects and hazards. It neither settles a battle nor grants its payout.
    safe_route = replace(route, route_world=preparation_quote_world(
        route.rom, route.route_world, raw, route.route_world.local_graphs))
    rows = []
    items = (ItemId.ELIXIR, ItemId.FULL_RESTORE)
    if include_evolution_stones:
        from pokemon_red_completion.red_collection import red_species_ref
        registered = runtime.registration_policy.goal_registered(
            runtime.adapter.observe().collection_observation)
        if any(red_species_ref(n) not in registered for n in (31,34,36,40)):
            items += (ItemId.MOON_STONE,)
    for item in items:
        binding = field_item_resupply_binding(
            runtime, actions, route=safe_route, item_id=int(item),
            # A cheap prefix is not a proven supply delivery. Omit it until
            # the fresh guarded world can quote the actual stock endpoint.
            require_complete_quote=True,
            # This noncombat delivery does not compose the Mansion statue/drop
            # puzzle. Do not quote its basement Elixir as currently executable.
            unsupported_target_maps=frozenset({int(MapId.POKEMON_MANSION_B1F)}))
        if binding is not None:
            rows.append(binding)
    if include_evolution_stones:
        from red_mixed_postgame_delivery_20261009 import hidden_moon_peer
        hidden=hidden_moon_peer(runtime,actions,safe_route.route_world)
        if hidden is not None:
            rows.append(hidden)
    return tuple(rows)


def diagnostic_evolution_venue(runtime, world, venue):
    """Existing native venue mechanics for an explicit copy-only comparison."""
    if type(venue) is not str or venue not in {'cave', 'mansion'}:
        raise ValueError('unknown diagnostic evolution venue')
    from pokemon_red_completion.red_goal_context import (
        DIGLETTS_CAVE_TRAINING_VENUE, MANSION_TRAINING_VENUE)
    from red_mixed_static_options_20261009 import observed_cave_entrance_world
    geometry = gift_route_world(world.with_current_observation(runtime.reader))
    geometry = observed_cave_entrance_world(runtime, geometry)
    venues = local_collection_evolution_venues(runtime, geometry,
        include_measured_mansion=venue == 'mansion')
    target = (MANSION_TRAINING_VENUE if venue == 'mansion'
              else DIGLETTS_CAVE_TRAINING_VENUE).map_id
    selected = tuple(v for v in venues if v.map_id == target)
    if len(selected) != 1:
        raise ValueError('diagnostic native venue is not currently available')
    return geometry, selected


def local_collection_evolution_venues(runtime, world, *, include_measured_mansion=False):
    """Keep the measured faster Cave default; retain opt-in Mansion access.

    A named evolution goal still belongs to the model. Native venue access and
    the existing measured bands are mechanics, not a new species/level policy.
    """
    from red_earned_collection_connection_20261005 import declared_cave_training_venue, declared_mansion_training_venue
    from pokemon_red_completion.red_fossil_acquisition import LOCAL_CINNABAR_MAPS

    if type(include_measured_mansion) is not bool:
        raise TypeError('Mansion venue opt-in must be boolean')
    cave = declared_cave_training_venue(runtime, world)
    if not include_measured_mansion:
        return (cave,)
    raw = runtime.reader.read()
    from red_current_source_preparation_20261004 import native_fly_usable
    if (raw.map_id in LOCAL_CINNABAR_MAPS or raw.badge_bits == 255
            and 8 in runtime.reader.read_fly_destinations() and native_fly_usable(raw)):
        return (cave, declared_mansion_training_venue(runtime, world))
    return (cave,)


def postgame_income_return(runtime, actions):
    """Normalize the existing verified native Continue for the income receipt."""
    from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport, GoalVerification

    binding = postgame_return_binding(runtime, actions)
    if binding is None:
        raise ValueError('earned League income has no native Continue boundary')
    report = binding.execute()
    if (binding.verify(report) != GoalVerification.succeeded()
            or report.evidence.get('native_postgame_return_verified') is not True):
        raise ValueError('earned League income native return is unverified')
    runtime.adapter.party_guard.verify_active_roster_restored()
    return GoalExecutionReport(report.actions_executed, report.frames_executed,
        dict(report.evidence, native_league_return_verified=True,
             native_credits_and_continue=True, supplied_not_learned=True,
             nurse_visits=0))


def income_reserve_cost(raw, *, targets=(4,6,2)):
    """Exact missing approved medicine stock; not an invented expense or reward."""
    stock = dict(raw.bag_items or ())
    return sum(max(0, target-stock.get(int(item),0))*price
        for (item,price),target in zip(((ItemId.FULL_RESTORE,3000),
            (ItemId.REVIVE,1500),(ItemId.FULL_HEAL,600)),targets,strict=True))


def measured_owned_income_bootstrap_ready(runtime):
    """Explicit DEVELOPMENT bootstrap from the measured restored six-member cohort.

    One native copy of this current cohort won all five rooms using one Revive,
    one Full Heal and no Full Restore. This is a provisional reserve rule, not
    a survival guarantee, learned procurement or broader actor qualification.
    """
    from pokemon_red_completion.red_learned_league import learned_league_controller
    controller=learned_league_controller(runtime)
    if controller is None or getattr(controller,'income_owned_stock_bootstrap',False) is not True:
        return False
    raw=runtime.reader.read()
    levels=raw.party_levels
    stock=dict(raw.bag_items or ())
    return (type(levels) is tuple and len(levels)==6
        and all(type(level) is int and 54<=level<=100 for level in levels)
        and max(levels)>=62 and stock.get(int(ItemId.REVIVE),0)>=1
        and stock.get(int(ItemId.FULL_HEAL),0)>=1)


def declared_conserved_income_support(declaration):
    enabled = declaration.get('conserved_owned_medicine_income', False)
    if type(enabled) is not bool or enabled and declaration.get('partition') != 'development':
        raise ValueError('Conserved income support requires explicit DEVELOPMENT permission')
    return enabled


def conserved_income_entry_targets(runtime):
    """Native-qualified retained weak band with a stronger carry and full entry stock.

    The weaker cohort never receives the zero-Restore fallback. This is supplied
    DEVELOPMENT medicine support, not a learned readiness or independent-root claim.
    """
    controller = getattr(runtime, 'league_battle_controller', None)
    if (getattr(controller, 'income_owned_stock_bootstrap', False) is not True
            or getattr(controller, 'income_conserved_entry_support', False) is not True):
        return None
    raw = runtime.reader.read()
    levels = raw.party_levels
    if (type(levels) is not tuple or len(levels) != 6
            or any(type(level) is not int or not 50 <= level <= 100 for level in levels)
            or not 50 <= min(levels) < 54 or max(levels) < 67
            or type(raw.player_money) is not int
            or raw.player_money < income_reserve_cost(raw, targets=(2,3,1))):
        return None
    return (2,3,1)


def measured_income_bootstrap_targets(runtime):
    """Prefer the existing entry reserve; refill a smaller measured reserve only if needed.

    Procurement remains disclosed support. The first actual minimal-stock repeat
    lost to Lance, so affordability must not force the minimum when the existing
    two-Restore/three-Revive entry reserve can be bought normally.
    """
    from pokemon_red_completion.red_learned_league import learned_league_controller
    controller=learned_league_controller(runtime)
    if controller is None or getattr(controller,'income_owned_stock_bootstrap',False) is not True:
        return None
    conserved=conserved_income_entry_targets(runtime)
    if conserved is not None:
        return conserved
    raw=runtime.reader.read()
    levels=raw.party_levels
    if (type(levels) is not tuple or len(levels)!=6
            or any(type(level) is not int or not 54<=level<=100 for level in levels)
            or max(levels)<62):
        return None
    if type(raw.player_money) is not int or raw.player_money < 0:
        return None
    for targets in ((2,3,1),(0,1,1)):
        if raw.player_money >= income_reserve_cost(raw,targets=targets):
            return targets
    # One exact stronger-cohort copy wins the qualified repeat with two owned
    # Revives and no cure. Admit only that existing stock, never an uncured buy.
    if (min(levels)>=55 and max(levels)>=68
            and dict(raw.bag_items or ()).get(int(ItemId.REVIVE),0)>=2):
        return (0,2,0)
    return None


def income_with_existing_reserve(runtime, actions, route, binding):
    """Compose approved pre-entry procurement before the same learned income goal."""
    from pokemon_red_completion.goal_manager_runtime import (
        GoalExecutionReport, GoalVerification,
    )
    from pokemon_red_completion.goal_manager import GoalFailureReason
    from pokemon_red_completion.goal_resource_quote import GoalResourceQuote
    from pokemon_red_completion.red_league_funding_execution import bind_red_league_funding_execution
    from pokemon_red_completion.red_player_league_options import league_medicine_capacity_binding
    from pokemon_red_completion.gen1_field_moves import Gen1FieldMovePort, Gen1FlyReceipt
    from pokemon_red_completion.actions import MacroAction, MacroActionKind
    from pokemon_red_completion.route_executor import execute_route
    from pokemon_red_completion.observation import RED_FLY_TOWN_NAMES
    from pokemon_red_completion.red_league_funding_execution import _ROUTE_LIMITS

    raw = runtime.reader.read()
    targets = (4,6,2)
    cost = income_reserve_cost(raw)
    if cost > raw.player_money:
        from pokemon_red_completion.red_autonomous_league_funding import (
            level100_owned_income_reserve_targets,
        )
        targets = level100_owned_income_reserve_targets(raw)
        if targets is None:
            targets=measured_income_bootstrap_targets(runtime)
            if targets is None:
                return None
        cost = income_reserve_cost(raw,targets=targets)
    if not cost:
        return (binding if targets == (4,6,2) else replace(binding,
            binding_ref=binding.binding_ref+({
                (0,1,1):':declared-owned-stock-bootstrap-0-1-1',
                (2,3,1):':declared-entry-reserve-2-3-1',
                (0,2,0):':declared-stronger-owned-reserve-0-2-0',
            }.get(targets,':owned-reserve-0-6-1-level100'))))
    gross = binding.resource_quote.expected_income
    if cost > raw.player_money or cost >= gross:
        return None  # No advance credit, borrowing, item sale or unprofitable offer.
    quoted = bind_red_league_funding_execution(runtime,route.route_world).qualification
    origin = runtime.emulator.save_state_bytes()
    consumed = False
    committed = terminal = None

    def execute():
        nonlocal consumed,committed,terminal
        if consumed or runtime.emulator.save_state_bytes() != origin:
            raise ValueError('Medicine-supported income origin is stale or consumed')
        consumed = True
        first_actions,first_frames = actions.actions_executed,runtime.emulator.frame_count
        route_observer = Gen1TraversalObserver(runtime.reader)
        if quoted.exit_plan is not None:
            from pokemon_red_completion.gen1_route_runtime import Gen1WildFleeHandler
            result = execute_route(quoted.exit_plan,actions,route_observer,limits=_ROUTE_LIMITS,
                interruption_handler=Gen1WildFleeHandler(actions,runtime.reader,maximum_flees=16,
                                                       stabilization_frames=120),
                replanner=route.route_world.replanner())
            if not result.passed:
                raise ValueError('Medicine income source departure did not settle')
        receipt = None
        if quoted.fly_required:
            town = RED_FLY_TOWN_NAMES[quoted.fly_town].lower().replace(' ','_')
            receipt = Gen1FieldMovePort(actions,runtime.reader,runtime.emulator).execute(
                MacroAction(MacroActionKind.FIELD_MOVE,'fly:'+town))
        landed = runtime.reader.read()
        if ((quoted.fly_required and not isinstance(receipt,Gen1FlyReceipt))
                or landed.map_id != quoted.fly_town
                or (landed.player_y,landed.player_x) != quoted.fly_landing
                or not _field_ready(runtime)):
            raise ValueError('Medicine income Fly destination differs')
        result = execute_route(quoted.supply.route,actions,route_observer,
            limits=_ROUTE_LIMITS,replanner=route.route_world.replanner())
        if not result.passed or not _field_ready(runtime):
            raise ValueError('Medicine income shop arrival did not settle')
        arrived = runtime.reader.read()
        if (arrived.player_money != raw.player_money or arrived.bag_items != raw.bag_items
                or arrived.party_species_ids != raw.party_species_ids
                or arrived.party_hp != raw.party_hp or arrived.party_pp != raw.party_pp
                or arrived.party_status != raw.party_status or arrived.badge_bits != raw.badge_bits
                or arrived.map_id != int(MapId.INDIGO_PLATEAU_LOBBY)
                or (arrived.player_y,arrived.player_x) != (5,2)):
            raise ValueError('Medicine income transport changed its qualified resources/party')
        configured = replace(runtime,profile=league_profile(runtime.profile))
        receipts=[]
        for ordinal in range(12):
            obs = runtime.adapter.observe()
            support = league_medicine_capacity_binding(configured,actions,route=route,
                observation=obs,development_retry_reentry=True,
                full_restore_target=targets[0],revive_target=targets[1],full_heal_target=targets[2])
            if support is None:
                support = league_medicine_reserve_binding(configured,actions,
                    route_world=route.route_world,observation=obs,
                    development_retry_reentry=True,balanced_first_lots=True,
                    full_restore_target=targets[0],revive_target=targets[1],
                    full_heal_target=targets[2],minimum_revive_coverage=targets[1])
            if support is None:
                break
            report=support.execute()
            if support.verify(report) != GoalVerification.succeeded():
                raise ValueError('Approved income reserve/capacity support failed')
            receipts.append(dict(actions=report.actions_executed,frames=report.frames_executed,
                                 evidence=_thaw(dict(report.evidence))))
        if (income_reserve_cost(runtime.reader.read(),targets=targets)
                or runtime.reader.read().player_money != raw.player_money-cost):
            raise ValueError('Medicine income reserve lacks its exact owned stock/cash debit')
        inner = postgame_league_income_peer(runtime,actions,route=route)
        if inner is None:
            raise ValueError('Medicine-supported income lost its actual native qualifier')
        report=inner.execute()
        verdict=inner.verify(report)
        from pokemon_red_completion.red_autonomous_league_funding import compose_native_funding_loss
        failed=compose_native_funding_loss(report,verdict,
            actions=actions.actions_executed-first_actions,
            frames=runtime.emulator.frame_count-first_frames,
            cash_before=raw.player_money,cash_after=runtime.reader.read().player_money,
            purchase_cost=cost,pre_entry_support=receipts)
        if failed is not None:
            terminal=runtime.emulator.save_state_bytes()
            committed=failed
            return committed
        if verdict != GoalVerification.succeeded():
            raise ValueError('Medicine-supported learned cycle did not verify')
        if runtime.reader.read().player_money != raw.player_money-cost+gross:
            raise ValueError('Medicine-supported income net cash differs')
        prices = {20:300,19:700,18:1500,16:3000,52:600,53:1500}
        incoming_owned_cost = sum(min(quantity,dict(raw.bag_items).get(item,0))*prices[item]
            for item,quantity in report.evidence['league_funding']['field_items_spent'])
        if gross-cost-incoming_owned_cost <= 0:
            raise ValueError('Medicine-supported income is not profitable after owned replacement')
        terminal=runtime.emulator.save_state_bytes()
        committed=GoalExecutionReport(actions.actions_executed-first_actions,
            runtime.emulator.frame_count-first_frames,dict(report.evidence,
                pre_entry_support=receipts,medicine_procurement_learned=False,
                pre_entry_purchase_cost=cost,observed_total_net_income=gross-cost,
                approved_medicine_targets=targets,
                gross_battle_income=gross,incoming_owned_stock=raw.bag_items,
                incoming_owned_replacement_cost=incoming_owned_cost,
                net_after_purchase_and_incoming_owned_replacement=gross-cost-incoming_owned_cost,
                medicine_cost_already_in_net_cash=True))
        return committed

    def verify(report):
        if (committed is not None and report is committed
                and committed.evidence.get('failed_funding') is True
                and runtime.emulator.save_state_bytes()==terminal and _field_ready(runtime)):
            return GoalVerification.failed(GoalFailureReason.RESOURCE_LOST)
        return (GoalVerification.succeeded() if committed is not None and report is committed
            and runtime.emulator.save_state_bytes()==terminal and _field_ready(runtime)
            and runtime.reader.read().player_money==raw.player_money-cost+gross
            else GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED))
    return replace(binding,binding_ref=binding.binding_ref+':approved-reserve-'+str(cost),
        execute=execute,verify=verify,
        resource_quote=GoalResourceQuote(raw.player_money,0,(),expected_income=gross-cost))


def postgame_league_income_peer(runtime, actions, *, route):
    """Reuse learned renewable income only against a real resource shortfall."""
    from pokemon_red_completion.red_autonomous_league_funding import bind_autonomous_league_funding
    from pokemon_red_completion.red_learned_league import learned_league_controller
    from pokemon_red_completion.red_resource_economy import red_economy_snapshot
    from overnight_red_player_20261004 import status_capable_k_preparation

    raw = runtime.reader.read()
    if (raw.badge_bits != 255 or not _field_ready(runtime)
            or not _raw_party_fully_restored(raw)
            or 'enter_hall_of_fame' not in runtime.adapter.graph.completed_ids(
                runtime.adapter.observe().game_state)
            or learned_league_controller(runtime) is None):
        return None  # Never fall through to the legacy teacher/medicine actor.
    economy = red_economy_snapshot(raw)
    if economy is None:
        return None
    # The existing first ball lot costs1000. Actual missing stone/prize quotes
    # can require more; these are resource needs, not a standing wealth target.
    target = postgame_collection_funding_target_cash(runtime,economy,route.route_world)
    if economy.cash >= target:
        return None
    learned = learned_league_controller(runtime)
    reuse = getattr(learned, 'income_reuse', None)
    if reuse is not None:
        from pokemon_red_completion.red_league_field_recovery import LeagueFieldRecovery
        learned.income_offer_count += 1
        learned.field_recovery = LeagueFieldRecovery(
            learned.income_goal_model, learned.income_goal_model.model_sha256,
            learned.income_output / ('field-recovery-%03d' % learned.income_offer_count),
            runtime.emulator.save_state_bytes, target, maximum_items=12,
            selection_mode='deterministic_safety',
            conserve_owned_medicine=conserved_income_entry_targets(runtime) is not None)
    binding = bind_autonomous_league_funding(runtime, actions, route.route_world,
        maximum_actions=20000, maximum_frames=2000000,
        postgame_return=lambda: postgame_income_return(runtime, actions),
        **({'development_reuse': reuse} if reuse is not None else {}))
    if binding is None:
        return None
    if reuse is not None:
        return income_with_existing_reserve(runtime,actions,route,binding)
    selected_execute = binding.execute
    def execute():
        # New-cycle qualification still requires the fully restored source.
        # Status acquired in real rooms does not create an artificial dead end:
        # exact K's already-disclosed DEVELOPMENT adapter owns legal combat.
        with status_capable_k_preparation(runtime):
            return selected_execute()
    return replace(binding, execute=execute)


def postgame_league_frontier_peer(runtime, actions, *, route):
    """Expose the real next room of an earned rematch, not a fresh entry.

    Historical story completion must not erase this cartridge prerequisite.
    Room admission and native payout guards are reused unchanged;
    ordinary field recovery can therefore be chosen between retained rooms.
    """
    from dataclasses import asdict
    from hashlib import sha256
    from pokemon_red_completion.goal_manager_runtime import (
        ExecutableGoalBinding, GoalExecutionReport, GoalVerification,
    )
    from pokemon_red_completion.goal_resource_quote import GoalResourceQuote
    from pokemon_red_completion.goal_manager import GoalFailureReason
    from pokemon_red_completion.gen1_champion_script import champion_script_binding
    from pokemon_red_completion.gen1_trainer_parties import trainer_party_quote
    from pokemon_red_completion.red_league_funding import _ROOMS, _room_quote
    from pokemon_red_completion.red_league_funding_execution import _run_battle
    from pokemon_red_completion.red_learned_league import learned_league_controller
    from pokemon_red_completion.red_trainer_story import RedCartridgeLoreleiSkill
    from pokemon_red_completion.red_champion_story import RedCartridgeChampionSkill
    from overnight_red_player_20261004 import status_capable_k_preparation

    raw = runtime.reader.read()
    if (raw.badge_bits != 255 or not _field_ready(runtime)
            or 'enter_hall_of_fame' not in runtime.adapter.graph.completed_ids(
                runtime.adapter.observe().game_state)
            or learned_league_controller(runtime) is None):
        return None
    target = live_league_player_target(raw, include_champion=True)
    if target is None or target is LEAGUE_PLAYER_TARGETS[0]:
        return None  # Never turn an outdoor/lobby quote into a new rematch.
    champion = target is CHAMPION_PLAYER_TARGET
    reuse = getattr(learned_league_controller(runtime), 'income_reuse', None)
    configured = (runtime if reuse is None else
                  reuse.bind(runtime, actions, route.route_world, target.objective_id))
    mode = ('frozen-k-development' if reuse is None else
            configured.league_story_battle_controller.controller_name)
    readiness = ({} if reuse is None else dict(maximum_level_deficit=
        configured.league_story_battle_controller.declared_level_deficit))
    skill = (RedCartridgeChampionSkill(configured, actions, route.route_world,
                 recovery_controller=mode, rematch=True, **readiness)
             if champion else RedCartridgeLoreleiSkill(configured, actions,
                 route.route_world, objective_id=target.objective_id,
                 recovery_controller=mode, rematch=True, **readiness))
    with (status_capable_k_preparation(runtime) if reuse is None else nullcontext()):
        if not skill.availability(runtime.adapter.observe().game_state).executable:
            return None
    if champion:
        script = champion_script_binding(route.rom,
            runtime.reader.read_final_league_scene().rival_starter)
        quote = trainer_party_quote(route.rom, script.opponent, script.trainer_set,
                                    allow_final_class=True)
    else:
        row = next(r for r in _ROOMS if r[0] == target.objective_id)
        quote = _room_quote(route.rom, raw.event_flags, *row)
    if raw.player_money is None or raw.player_money + quote.expected_victory_money > 999999:
        return None
    origin = runtime.emulator.save_state_bytes()
    consumed, terminal, committed = False, None, None

    def execute():
        nonlocal consumed, terminal, committed
        if consumed or runtime.emulator.save_state_bytes() != origin:
            raise ValueError('earned League frontier is stale or consumed')
        consumed = True
        first_actions, first_frames = actions.actions_executed, runtime.emulator.frame_count
        with (status_capable_k_preparation(runtime) if reuse is None else nullcontext()):
            battle = _run_battle(runtime, actions, route.route_world, target.objective_id,
                quote.expected_victory_money, 'frozen-k-development', 0,
                **({'development_reuse': reuse} if reuse is not None else {}))
        evidence = dict(partial_league_income=True, learned_battle_authority=True,
                        teacher_fallback=False, league_battle=asdict(battle),
                        disclosed_development_status_entry=True,
                        status_cured_by_scope=False)
        if champion:
            evidence['league_return'] = dict(postgame_income_return(runtime, actions).evidence)
        runtime.adapter.party_guard.verify_active_roster_restored()
        if runtime.reader.read().player_money != raw.player_money + quote.expected_victory_money:
            raise ValueError('earned League frontier payout differs')
        terminal = runtime.emulator.save_state_bytes()
        committed = GoalExecutionReport(actions.actions_executed-first_actions,
            runtime.emulator.frame_count-first_frames, evidence)
        return committed

    def verify(report):
        if (committed is None or report is not committed
                or runtime.emulator.save_state_bytes() != terminal
                or not _field_ready(runtime)
                or runtime.reader.read().player_money != raw.player_money + quote.expected_victory_money):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    return ExecutableGoalBinding(
        'pokemon.red:funding:earned-league-frontier:' + target.objective_id + ':'
        + sha256(origin).hexdigest(), GoalKind.RESUPPLY, .5, .5, execute, verify,
        maximum_cash_debit=None,
        resource_quote=GoalResourceQuote(raw.player_money, 0, (),
                                        expected_income=quote.expected_victory_money))


def masked_static_capture_inventory(ordinary, capture):
    """Keep the typed acquisition slot when its executable moves to supplements.

    The ordinary executor is replaced, not the opportunity schema. In particular,
    existing singleton support requires one masked acquisition slot; removing it
    made an otherwise legal adjacent capture disappear from an empty menu.
    """
    if capture.kind is not GoalKind.ACQUIRE_SPECIES:
        raise ValueError('static capture masking requires an acquisition')
    return GoalBindingSet(
        tuple(o for o in ordinary.opportunities if o.kind is not capture.kind)
        + (GoalOpportunity('static-capture:supplemental',capture.kind,
            GoalAvailability.UNAVAILABLE,
            unavailable_reason=GoalUnavailableReason.TEMPORARILY_BLOCKED),),
        tuple(b for b in ordinary.bindings if b.kind is not capture.kind),
        allow_resource_variants=ordinary.allow_resource_variants)


def progression_capture_supplement(binding, situation, *, opens_passage):
    """Project a real capture's observed access effect without changing its kind.

    It remains an acquisition with actual registration gain. Only the existing
    dependency field changes; neither a chapter identity nor a selected label
    reaches the learner, and no action/score/weights are supplied here.
    """
    if type(opens_passage) is not bool or binding.kind is not GoalKind.ACQUIRE_SPECIES:
        raise ValueError('progression capture requires explicit capture/access facts')
    masked = GoalOpportunity('projection-mask',GoalKind.EXPLORE,
        GoalAvailability.UNAVAILABLE,unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET)
    question = GoalBindingSet((binding.opportunity,masked), (binding,)).question(situation)
    candidate = project_living_dex_goal_candidate(question, 0,
        feature_version=5, binding_ref=binding.binding_ref)
    if opens_passage:
        candidate = replace(candidate,features=replace(candidate.features,dependency_unlock_gain=1.))
    return supplemental_live_option(binding,candidate)


def postgame_corner_options(runtime, actions, observed, world):
    """Expose actual case, affordable coins and prize peers, not a phase order."""
    if runtime.reader.read().badge_bits != 255:
        return ()
    actual = runtime.adapter.observe()
    cash_reserve=0
    if getattr(getattr(runtime,'league_battle_controller',None),
               'income_owned_stock_bootstrap',False) is True:
        targets=measured_income_bootstrap_targets(runtime)
        cash_reserve=income_reserve_cost(actual.raw,
            targets=(4,6,2) if targets is None else targets)
    kwargs = dict(situation=observed.situation,model_feature_version=5,
        maximum_actions=20000,maximum_frames=2000000,cash_reserve=cash_reserve)
    return (game_corner_options(runtime,actual,actions,world,**kwargs)
            + game_corner_coin_options(runtime,actual,actions,world,**kwargs))


def postgame_acquisition_options(runtime, actions, observed, world, *, bird_capture_loan=None,
                                snorlax_capture_loan=None,
                                bird_runtime=None):
    """Reuse native gift/Amber receipts as peers of ordinary capture/evolution.

    Held-fossil revival already has its own ordinary collection port. Amber's
    existing provider refuses while that fossil is held or pending; this seam
    never supplies an acquisition order or changes the source/stock contract.
    """
    if runtime.reader.read().badge_bits != 255:
        return ()
    actual=runtime.adapter.observe()
    from red_mixed_postgame_delivery_20261009 import routed_dojo_gift_bindings
    from red_mixed_bird_collection_20261009 import BirdRoute,routed_bird_bindings,routed_snorlax_bindings
    bindings=(eevee_gift_bindings(runtime,actual,actions,world)+amber_bindings(
        runtime,actual,actions,world)+postgame_native_oneoff_bindings(
        runtime,actual,actions,world)+routed_dojo_gift_bindings(runtime,actual,actions,world)
        +routed_bird_bindings(runtime if bird_runtime is None else bird_runtime,
                             actual,actions,BirdRoute(world.rom,world),
                             capture_loan=bird_capture_loan)
        +routed_snorlax_bindings(runtime if bird_runtime is None else bird_runtime,
                             actual,actions,BirdRoute(world.rom,world),
                             capture_loan=snorlax_capture_loan))
    gifts=tuple(progression_capture_supplement(b,observed.situation,opens_passage=False)
        for b in bindings)
    prizes=tuple(row for row in postgame_corner_options(runtime,actions,observed,world)
        if row.binding.kind is GoalKind.ACQUIRE_SPECIES)
    return gifts+prizes


def league_profile(profile):
    providers = [(spec.kind, spec.mechanic, _thaw(spec.parameters))
                 for spec in profile.providers if spec.kind is not GoalKind.RESUPPLY]
    providers.append((GoalKind.RESUPPLY, c.RedGoalMechanic.MART_RESUPPLY,
        dict(map_id=int(c.MapId.INDIGO_PLATEAU_LOBBY), player_x=2, player_y=5,
             interaction_direction='left', affordable_ball_purchase=True,
             resource_choice_variants=True,
             purchases=[dict(absolute_index=0, item_id=int(ItemId.ULTRA_BALL),
                             quantity=5, unit_price=1200)])))
    providers.sort(key=lambda row: tuple(GoalKind).index(row[0]))
    return parse_red_goal_context_profile(build_red_goal_context_profile_payload(
        profile_id='whole-player-observed-indigo-resources-v1', providers=tuple(providers)))


def control_inventory(binding):
    opportunities = tuple(binding.opportunity if binding is not None and kind is binding.kind
        else GoalOpportunity('wild-bridge:'+kind.value, kind, GoalAvailability.UNAVAILABLE,
                             unavailable_reason=GoalUnavailableReason.TEMPORARILY_BLOCKED)
        for kind in GoalKind)
    return GoalBindingSet(opportunities, () if binding is None else (binding,))


def retained_early_trainer_binding(runtime, actions, *, rom, battler):
    """Reuse exact native engagements without inventing a challenge or goal.

    Preserve existing early chapter guards. Completed postgame uses the public
    opt-in for an already engaged ordinary trainer, with no new story credit.
    """
    raw = runtime.reader.read()
    completed = set(runtime.adapter.graph.completed_ids(runtime.adapter.observe().game_state))
    if {'defeat_champion', 'enter_hall_of_fame'} <= completed:
        return engaged_story_binding(runtime, actions, rom=rom, battler=battler,
            objective_id='postgame_collection', allow_postgame_collection=True)
    if raw.map_id == int(c.MapId.FIGHTING_DOJO) and raw.badge_bits == 255:
        # An already-open exact Master introduction must settle even when
        # collection is being deferred prospectively. This supplies no approach,
        # gift or League credit; the old selected trip remains failed.
        for objective in runtime.adapter.graph.available_objectives(
                runtime.adapter.observe().game_state):
            if objective.id not in {t.objective_id for t in LEAGUE_PLAYER_TARGETS+(CHAMPION_PLAYER_TARGET,)}:
                continue
            binding = engaged_story_binding(runtime,actions,rom=rom,battler=battler,
                objective_id=objective.id,dojo_master_transport=True)
            if binding is not None:
                return binding
    # Route24's Nugget Rocket begins in reward dialogue before the ordinary
    # sight/battle latch. The existing public contract authenticates that exact
    # introduction (including all five bridge wins), not arbitrary field text.
    if raw.map_id == int(c.MapId.CERULEAN_CITY):
        # The already-triggered thief belongs to Vermilion's native passage,
        # not Bill's rival. Both existing exact contracts may decline; this
        # supplies neither an approach nor a strategic chapter preference.
        for objective in ('help_bill', 'reach_vermilion'):
            binding = engaged_story_binding(runtime, actions, rom=rom, battler=battler,
                                            objective_id=objective)
            if binding is not None:
                return binding
        return None
    if raw.map_id == int(c.MapId.ROUTE_24):
        binding = engaged_story_binding(runtime, actions, rom=rom, battler=battler,
                                        objective_id='help_bill')
        if binding is not None:
            return binding
        # An already-engaged ordinary trainer remains recoverable while a
        # selected collection trip backtracks through a completed Bill chapter.
        # Reuse the exact ordinary contract under a legal current accounting
        # context; scripted encounters and unknown identities still decline.
        return retained_ordinary_transport_binding(runtime, actions, rom=rom, battler=battler)
    if raw.map_id == int(c.MapId.ROUTE_22):
        if not event_flag_is_set(raw.event_flags, 0x520):
            return None  # The separately guarded later rival keeps its existing actor.
        for objective in sorted(runtime.adapter.graph.available_objectives(
                runtime.adapter.observe().game_state), key=lambda row: row.id):
            binding = engaged_story_binding(runtime, actions, rom=rom, battler=battler,
                                            objective_id=objective.id)
            if binding is not None:
                return binding
        return None
    if raw.map_id not in {14, 15, 17, 51, 59, 60, 61}:
        return retained_ordinary_transport_binding(runtime, actions, rom=rom, battler=battler)
    if raw.battle_state != 2 and not (
        raw.battle_state == 0 and runtime.reader.trainer_engagement_active()
    ):
        return None
    # This labels an unavoidable battle, not a destination/strategy. Once
    # Cerulean is earned, backtracking must not depend on its closed objective.
    contexts = ('reach_cerulean','help_bill','defeat_misty')
    if raw.map_id == 17:
        # Label only this already-engaged Route6 trainer with a legal current
        # chapter. The binding never approaches or completes that objective.
        contexts += ('reach_vermilion','obtain_cut','defeat_surge')
    for objective in contexts:
        binding=engaged_story_binding(runtime, actions, rom=rom, battler=battler,
                                      objective_id=objective)
        if binding is not None:
            return binding
    return retained_ordinary_transport_binding(runtime, actions, rom=rom, battler=battler)


def preparation_quote_world(rom, world, raw, map_ids):
    """Reserve decoded future-map trainer lanes for a noncombat training walk.

    Current-map moving objects/hazards remain live. Native undefeated event
    flags and cartridge facings conservatively reserve unvisited venue maps;
    this support quote neither fights a trainer nor supplies a progression goal.
    The original world and its story gates are immutable and unchanged.
    """
    future=set(map_ids)-{raw.map_id}
    zones=static_trainer_sight_zones(
        trainer_headers(rom,future,full_event_offsets=True),
        map_object_events(rom,future),raw.event_flags)
    blocked={map_id:frozenset(at for zone in zones if zone.map_id==map_id
                              for at in zone.lane) for map_id in future}
    graphs=dict(world.local_graphs)
    for map_id,lanes in blocked.items():
        if lanes:
            graphs[map_id]=without_coordinates(graphs[map_id],lanes)
    return replace(world,local_graphs=graphs)


def retained_gym_switch_history(parent):
    """Carry only observed lock attempts from this actual continuation ancestry."""
    from pokemon_red_completion.red_player_configuration import checkpoint_quiescent
    chunks, seen = [], set()
    recovered_raw = None
    while (parent/'PLAN.json').exists():
        assert parent not in seen, 'cyclic continuation ancestry'
        seen.add(parent)
        plan = d.prior.doc(parent/'PLAN.json')
        prior = plan.get('actual_parent')
        if prior is None:
            break
        if (parent/'RESULT.json').exists():
            result = d.prior.doc(parent/'RESULT.json')
            assert checkpoint_quiescent(result)
            assert c.digest(parent/'terminal.state') == result['state_sha256']
        elif parent == recovered_raw:
            meter = d.prior.doc(parent/'native/native-costs.json')
            if (meter.get('buttons_released') is not True
                    or c.digest(parent/'native/terminal.state')!=c.digest(parent/'terminal.state')):
                raise ValueError('recovered raw history is not its released native terminal')
            result = None
        else:
            raise ValueError('continuation history lacks a verified stopped result')
        from pokemon_red_completion.red_player_package import resolve_packaged_history_path
        ancestor = resolve_packaged_history_path(prior)
        assert c.digest(ancestor/'terminal.state') == plan['source_sha256']
        if plan.get('raw_failed_export_retained'):
            if (result is None or result.get('passed') is not True
                    or result.get('originals_returned') is not True
                    or plan.get('support_only') is not True):
                raise ValueError('raw history requires verified original-party repayment')
            guard_parent = resolve_packaged_history_path(plan['original_guard_parent'])
            raw_plan = d.prior.doc(ancestor/'PLAN.json')
            if (resolve_packaged_history_path(raw_plan['actual_parent'])!=guard_parent
                    or c.digest(guard_parent/'CONTEXT.json')!=plan['context_sha256']):
                raise ValueError('raw history recovery guard ancestry differs')
            recovered_raw = ancestor
        chunks.append(parent)
        parent = ancestor
    return [row['value'] for node in reversed(chunks)
            for path in sorted(node.glob('observed-*.json'))
            for row in (d.prior.doc(path),) if row.get('name') == 'gym_switch']


def surge_switch_option(runtime, actions, *, route, history, record, battler):
    """Expose the existing visible-lock skill; no hidden answer or leader credit."""
    if not _field_ready(runtime) or runtime.reader.read().map_id != int(c.MapId.VERMILION_GYM):
        return None
    locks = visible_locks(runtime.reader.read())
    if all(locks):
        return None
    binding = gym_switch_binding(runtime, actions, route=route, history=history, record=record)
    combat = False
    if binding is None:
        for at, _ in can_stances(next_can(history, locks)):
            binding = obstructing_story_battle_binding(runtime, actions,
                objective_id='defeat_surge', route=route, battler=battler,
                destination_at=at, allow_sequence=True)
            if binding is not None:
                combat = True
                break
    if binding is None:
        return None
    return (replace(binding, story_objective_ref='defeat_surge'),
            OptionChallenge(combat, False, 0., 0., 0.))


def gym_obstruction_scope_key(contract):
    rewards = (BROCK_REWARD,MISTY_REWARD,SURGE_REWARD,ERIKA_REWARD,
               KOGA_REWARD,SABRINA_REWARD,BLAINE_REWARD,GIOVANNI_REWARD)
    reward = next((r for r in rewards if r.objective_id == contract.objective_id),None)
    if (reward is None or contract.map_id != reward.map_id or
        contract.defeated_event in (None,reward.defeated_event) or
        contract.victory_items or contract.victory_badge_bits or
        contract.trainer_identity == (reward.trainer_class,reward.trainer_class-200,reward.trainer_set)):
        return None
    return 'gym-trainer-'+c.canonical_sha256(asdict(contract))


def silph_damage_component(useful_moves=False):
    if type(useful_moves) is not bool:
        raise ValueError('Silph component selection must be an explicit boolean')
    return ((c.BASE/'silph-useful-moves-20261002-v1/composition/candidate-model.json',
             '05a7afb42bfdf8b5d416782a516e78ae82d7a6d4cd72eea77134b484822c7333')
            if useful_moves else
            (d.ROOT/'reused-damage/candidate-model.json',
             '29792a3292e8d5c103e39d5914d8b1c9388c65af107c989141331e14503712ad'))


def assembly(parent, output, *, plan_path=None, continuous_travel=False, include_preparation=False,
             include_supply=False, include_rewards=False, origin_sha=None, origin_id=None,
             include_early_preparation=False, protect_party_species=True,
             include_silph_continuation=False, silph_useful_moves=False,
             continuation_loan_refs=frozenset(), quote_capture_route_work=False,
             include_level_workload=False, include_capture_invocation=False,
             include_matchup_observation=False, include_preparation_party_context=False, training_admission=None,
             preparation_encounter_quantum=None):
    from pokemon_red_completion.red_player_preparation_binding import preparation_encounter_limits
    preparation_battles, preparation_recoveries = preparation_encounter_limits(
        preparation_encounter_quantum)
    if type(include_matchup_observation) is not bool:
        raise ValueError('Matchup observation requires an explicit boolean')
    if type(include_preparation_party_context) is not bool or (include_preparation_party_context and not include_matchup_observation):
        raise ValueError('Preparation party context requires explicit V15 observation opt-in')
    if type(quote_capture_route_work) is not bool:
        raise ValueError('Capture route work requires an explicit boolean')
    if type(include_capture_invocation) is not bool:
        raise ValueError('Safari invocation observation requires an explicit boolean')
    if type(include_level_workload) is not bool:
        raise ValueError('Level workload observation requires an explicit boolean')
    if type(include_silph_continuation) is not bool or (include_silph_continuation and not include_rewards):
        raise ValueError('Silph continuation requires explicit reward-enabled composition')
    silph_damage_component(silph_useful_moves)
    if silph_useful_moves and not include_silph_continuation:
        raise ValueError('Useful-move reuse requires explicit remaining Silph composition')
    if training_admission is not None:
        from pokemon_red_completion.red_production_train_admission import ProductionTrainAdmission
        if type(training_admission) is not ProductionTrainAdmission:
            raise ValueError('typed production TRAIN admission required')
        training_admission.require_work_order(Path(plan_path).read_bytes())
    context = d.prior.doc(parent/'CONTEXT.json')
    payload = (parent/'terminal.state').read_bytes()
    if training_admission is not None:
        training_admission.require_source_context(payload, (parent/'CONTEXT.json').read_bytes())
    assert c.sha256(payload).hexdigest() == context['state_sha256']
    if training_admission is not None and (
        context['state_sha256'] != training_admission.source_state_sha256
        or origin_sha != training_admission.source_origin_sha256
        or origin_id != training_admission.root_lineage_id):
        raise ValueError('whole-player TRAIN source differs from admission')
    origin = (d.prior.doc(SOURCE/'PLAN.json')['source']['origin_sha256']
              if origin_sha is None else origin_sha)
    factory0, _, holder, source = shared.assembly(payload, output, origin_sha=origin,
        partition='development' if training_admission is None else 'train', origin_id=ROOT.name if origin_id is None else origin_id,
        objective_ids=context['lesson']['completed_objectives'],
        protect_party_species=protect_party_species)
    declared = ROOT/'PLAN.json' if plan_path is None else plan_path
    bird_capture_loan = d.prior.doc(declared).get('bird_capture_loan')
    snorlax_capture_loan = d.prior.doc(declared).get('snorlax_capture_loan')
    from pokemon_red_completion.red_player_party_guard import validate_snorlax_capture_loan_declaration
    validate_snorlax_capture_loan_declaration(snorlax_capture_loan)
    task_scope = d.prior.doc(declared).get('league_first_collection_scope')
    if task_scope is not None and (not isinstance(task_scope,dict)
            or set(task_scope) != {'mode','reason'}
            or task_scope['mode'] != 'defer_eight_badge_collection_until_hof_v1'
            or not isinstance(task_scope['reason'],str) or not task_scope['reason'].strip()):
        raise ValueError('Unsupported explicit League-first development scope')
    league_first = task_scope is not None
    source = dict(source, experiment_sha256=c.digest(declared))
    rom = c.ROM.read_bytes()
    cartridge = RedPracticeCartridge(rom) if include_rewards else None
    route = replace(shared.RedVermilionGroundTransition.from_rom(rom),
                    full_event_offsets=True, observe_terrain=True, allow_surf=include_rewards,
                    allow_wild_faints=include_rewards,
                    allow_field_faint_dialogue=include_rewards)
    if include_rewards:
        # The gift's proven stair arrivals also govern subsequent departures.
        # Keep raw doors/tiles and native transition checks; expose no new route.
        route = replace(route, route_world=gift_route_world(route.route_world))
    cartridge_route_world = route.route_world
    collection_seed = (derive_red_living_dex_wild_corridor(
        RedEncounterSourceTarget('wild:Route1:grass'),
        route.route_world.terrain[int(c.MapId.ROUTE_1)],
        route.route_world.local_graphs[int(c.MapId.ROUTE_1)],
        cartridge=rom) if include_rewards else None)
    records = [0]
    puzzle_history = retained_gym_switch_history(parent) if include_rewards else []

    def record(name, value):
        records[0] += 1
        _record(output/f'observed-{records[0]:04d}.json', dict(name=name, value=value))

    def configure_income_reuse(controller):
        from pokemon_red_completion.red_league_funding_execution import ScopedLeagueIncomeReuse
        from pokemon_red_completion.red_player_model import load_player_goal_model_record_bytes
        declaration = json.loads(declared.read_bytes())
        spec = declaration['goal_model_record']
        model_bytes = Path(spec['path']).read_bytes()
        if c.sha256(model_bytes).hexdigest() != spec['content_sha256']:
            raise ValueError('Income recovery goal-model record changed')
        goal = load_player_goal_model_record_bytes(model_bytes,
            expected_model_sha256=declared_income_goal_model_sha256(declaration)).model
        controller.income_reuse = ScopedLeagueIncomeReuse(
            '111ef28dd505a61c6c8b3c0c7521d0d395119afba6f3b0e090a86095a03a4ad2',
            c.digest(declared), bind_income_runtime,
            lambda objective: holder['observe_history']())
        controller.income_goal_model = goal
        controller.income_output = output / 'income-reuse'
        controller.income_offer_count = 0
        bootstrap=declaration.get('owned_stock_income_bootstrap',False)
        if type(bootstrap) is not bool or bootstrap and declaration.get('partition')!='development':
            raise ValueError('Owned-stock income bootstrap requires explicit DEVELOPMENT permission')
        controller.income_owned_stock_bootstrap=bootstrap
        controller.income_conserved_entry_support=declared_conserved_income_support(declaration)
        controller.income_snorlax_helper_support=snorlax_capture_loan is not None

    def factory(controller):
        rt = factory0(controller)
        if include_supply:
            rt = replace(rt, profile=player_supply_profile(rt.profile,
                early_preparation=include_early_preparation,
                completed=context['lesson']['completed_objectives']))
        if include_rewards:
            rt = bind_player_collection_capabilities(
                rt, seed_corridor=collection_seed,
                add_capture_preparation_support=not include_early_preparation,
                include_fly_transport=True)
            if {'defeat_champion','enter_hall_of_fame'} <= set(context['lesson']['completed_objectives']):
                rt = replace(rt, collection_dig_departure=True, collection_surf_departure=True,
                             safari_departure_recovery=True)
            completed = rt.adapter.graph.completed_ids(rt.adapter.observe().game_state)
            if 'enter_hall_of_fame' in completed or rt.reader.read().badge_bits == 255:
                actor = holder['actor']
                if (actor.model_sha256 != FROZEN_K_SHA256
                        or actor.qualification_sha256 != K_QUALIFICATION_SHA256):
                    raise ValueError('ordinary income requires the exact retained frozen K battler')
                rt = replace(rt, trainer_battle_runner=actor.run,
                    trainer_battle_model_sha256=actor.model_sha256,
                    trainer_battle_qualification_sha256=actor.qualification_sha256,
                    trainer_funding_recovery=True, trainer_funding_ledges=True,
                    trainer_funding_surf=True, trainer_funding_indoor_departure=True)
                # Same authenticated K and already-proved mechanics support.
                # Connect before history binds so rematches share its real logs;
                # never substitute the legacy teacher-controlled funding actor.
                if 'enter_hall_of_fame' in completed:
                    from overnight_red_player_20261004 import connect_existing_league_battler
                    rt = connect_existing_league_battler(rt)
                    holder['actor'] = rt.trainer_battle_runner.__self__
        restored = restore_player_continuation(rt, context,
            expected_sha256=c.canonical_sha256(context), evolution_rom=rom,
            loanable_refs=continuation_loan_refs)
        holder.update(plan=restored.preparation, prior_spent=restored.spent,
                      history=NativeBattlerHistory(holder['actor'], initial=restored.battle),
                      initial_battle=restored.battle, runtime=rt, scoped_actors={},
                      scoped_league_runtimes={},
                      last_calls={'wild': 0}, latest_battle=restored.battle)
        holder.pop('training_pool', None)
        if training_admission is not None:
            holder['training_reader'] = rt.reader
        holder['actor'].pp_depleted_switch_screen = True
        rt.adapter.include_pp_restoration = True
        holder['history'] = NativeBattlerHistory(holder['actor'], initial=restored.battle)
        holder['prior_spent'] = carried_spent(parent,context)
        if include_rewards and rt.league_battle_controller is not None:
            configure_income_reuse(rt.league_battle_controller)
        holder['postgame_income_controller'] = rt.league_battle_controller
        return rt

    def bind_income_runtime(runtime, actions, world, objective_id):
        path = c.BASE/'red-isolated-player-package-20261009-v1/assisted-exploration-recovery/diagnostics/agatha-control-reuse-20261010-v1/control52-model.json'
        pin = '111ef28dd505a61c6c8b3c0c7521d0d395119afba6f3b0e090a86095a03a4ad2'
        if c.digest(path) != pin:
            raise ValueError('Income reuse learned component changed')
        prototype = replace(holder['actor'],
            model=TrainerPracticeThreeHeadModel.from_dict(d.prior.doc(path)), model_sha256=pin)
        cycle = runtime.league_battle_controller.income_offer_count
        key = 'income-%s-offer-%03d' % (objective_id, cycle)
        composed = bind_live_league_runtime(replace(runtime, league_battle_controller=None),
            battler=prototype, rom=rom, route_world=world,
            output=output/key, work_order=declared.read_bytes(),
            include_champion=True, development_retry_reentry=True)
        if composed is None or composed[2].objective_id != objective_id:
            raise ValueError('Income reuse has no exact observed League room')
        configured, actor, target = composed
        existing = holder['scoped_actors'].get(key)
        if existing is not None and existing[0].calls:
            raise ValueError('Income reuse cannot silently replace an executed actor')
        holder['scoped_actors'][key] = (actor,
            NativeBattlerHistory(actor, initial=holder['latest_battle']))
        holder['last_calls'][key] = 0
        return configured

    def observed_income_runtime(runtime):
        # Phase capabilities follow observed progress, including a HOF earned
        # after construction. Reuse one controller and the same owned battler;
        # cloning it here would reset call/history counters and output names.
        if not include_rewards:
            return runtime
        completed = runtime.adapter.graph.completed_ids(runtime.adapter.observe().game_state)
        postgame = 'enter_hall_of_fame' in completed
        if not postgame and runtime.reader.read().badge_bits != 255:
            return runtime
        actor = holder['actor']
        if (actor.model_sha256 != FROZEN_K_SHA256
                or actor.qualification_sha256 != K_QUALIFICATION_SHA256):
            raise ValueError('ordinary income requires the exact retained frozen K battler')
        if getattr(runtime, 'league_story_battle_controller', None) is not None:
            raise ValueError('phase income cannot replace a bound story actor')
        configured = replace(runtime, trainer_battle_runner=actor.run,
            trainer_battle_model_sha256=actor.model_sha256,
            trainer_battle_qualification_sha256=actor.qualification_sha256,
            trainer_funding_recovery=True, trainer_funding_ledges=True,
            trainer_funding_surf=True, trainer_funding_indoor_departure=True)
        if not postgame:
            return configured
        from pokemon_red_completion.red_learned_league import FrozenLeagueController
        controller = holder.get('postgame_income_controller')
        observed = runtime.league_battle_controller
        if observed is not None:
            if controller is not None and controller is not observed:
                raise ValueError('phase income cannot replace its retained controller')
            controller = observed
        if controller is None:
            from pokemon_red_completion.red_learned_league import FrozenLeagueController
            controller = FrozenLeagueController(actor, 'league-profit-recovery-v1', True)
            controller.require_identity()
            configure_income_reuse(controller)
            record('native-postgame-income-refresh', dict(
                frame=runtime.emulator.frame_count, retained_actor_calls=actor.calls,
                retained_battler=controller.battler is actor,
                owned_stock_permission=controller.income_owned_stock_bootstrap,
                conserved_permission=controller.income_conserved_entry_support,
                automatic_fit=False, supplied_not_learned=True))
        if not isinstance(controller, FrozenLeagueController):
            raise ValueError('League actor must be the explicit frozen K adapter')
        if controller.battler is not actor:
            raise ValueError('phase income changed its owned battler/history')
        controller.require_identity()
        holder['postgame_income_controller'] = controller
        return replace(configured, league_battle_controller=controller,
            collection_dig_departure=True, collection_surf_departure=True,
            safari_departure_recovery=True)

    def route22_actor(runtime):
        objective = 'cross_victory_road'
        if objective not in holder['scoped_actors']:
            path, pin = silph_damage_component(silph_useful_moves)
            assert c.digest(path) == pin
            model = TrainerPracticeThreeHeadModel.from_dict(d.prior.doc(path))
            contract = route22_rival_contract(rom,runtime.reader)
            scope = DevelopmentStoryScope(source['state_sha256'],holder['actor'].root_lineage_id,pin,
                c.canonical_sha256(model.to_dict()),c.digest(declared),contract=contract,
                allow_learned_tactics=True,diagnostic_status_entry=True,
                screen_capped_status_moves=True)
            actor = replace(holder['actor'],calls=0,model=model,model_sha256=pin,
                qualification_sha256=scope.identity,development_story_scope=scope,
                output=output/'route22-rival')
            actor.require_story_contract(contract)
            holder['scoped_actors'][objective] = (
                actor,NativeBattlerHistory(actor,initial=holder['latest_battle']))
            holder['last_calls'][objective] = 0
        return holder['scoped_actors'][objective][0]

    def preparation_actor(map_id, *, _bind_pool=True):
        if training_admission is not None and map_id != 15:
            raise ValueError('production TRAIN preparation requires the declared Route4 venue')
        # Optional exact existing battler reuse, not a supplied training choice.
        # Each venue has its own typed wild-only source/model/work-order scope.
        spec = d.prior.doc(declared).get('preparation_battle_component')
        if spec is None:
            if training_admission is not None:
                raise ValueError('production TRAIN preparation requires its declared component')
            return holder['actor']
        if (set(spec) != {'path','sha256','reason'} or type(spec['reason']) is not str
            or not spec['reason']):
            raise ValueError('preparation battler requires an exact reuse declaration')
        path,pin = Path(spec['path']),spec['sha256']
        if c.digest(path) != pin:
            raise ValueError('declared preparation battler changed')
        key = 'preparation-map-'+str(map_id)
        if key not in holder['scoped_actors']:
            model = TrainerPracticeThreeHeadModel.from_dict(d.prior.doc(path))
            prototype = holder['actor']
            scope = DevelopmentPreparationScope(source['state_sha256'],prototype.root_lineage_id,
                pin,c.canonical_sha256(model.to_dict()),c.digest(declared),map_id,
                train_admission=training_admission)
            actor = replace(prototype,calls=0,model=model,model_sha256=pin,
                qualification_sha256=scope.identity,development_preparation_scope=scope,
                pp_depleted_switch_screen=False,output=output/key)
            actor.wild_authority(map_id)
            holder['scoped_actors'][key] = (actor,NativeBattlerHistory(actor,initial=holder['latest_battle']))
            holder['last_calls'][key] = 0
        if training_admission is not None and _bind_pool:
            ensure_training_pool(holder['runtime'])
        return holder['scoped_actors'][key][0]

    def retained_trainer(runtime, actions):
        from pokemon_red_completion.red_player_league_options import (
            engaged_league_contract, league_native_prerequisite,
        )

        retained = engaged_league_contract(runtime.reader,rom,include_champion=True)
        if retained is not None:
            target, _ = retained
            available = runtime.adapter.graph.available_objectives(
                runtime.adapter.observe().game_state)
            progress = next((o.id for o in available
                             if league_native_prerequisite(target,o.id)),None)
            if progress is None:
                return None
            league(target.objective_id,runtime,actions,None,allow_engaged=True)
            actor = holder['scoped_actors'][target.objective_id][0]
            return engaged_story_binding(runtime,actions,rom=rom,battler=actor,
                objective_id=target.objective_id,progress_objective_ref=progress)
        return engaged_story_binding(runtime,actions,rom=rom,
            battler=route22_actor(runtime),objective_id='cross_victory_road')
    holder['retained_trainer_binding'] = retained_trainer

    def tower_trainer_actor(runtime):
        # Existing explicit Tower DEVELOPMENT admission, never a wild actor
        # qualification. The native adapters still validate actual contracts.
        if not include_rewards or not 143 <= runtime.reader.read().map_id <= 148:
            return holder['actor']
        objective = 'rescue_fuji'
        if objective not in holder['scoped_actors']:
            path = d.ROOT/'reused-damage/candidate-model.json'
            pin = '29792a3292e8d5c103e39d5914d8b1c9388c65af107c989141331e14503712ad'
            assert c.digest(path) == pin
            model = TrainerPracticeThreeHeadModel.from_dict(d.prior.doc(path))
            prototype = holder['actor']
            scope = DevelopmentStoryScope(source['state_sha256'],prototype.root_lineage_id,pin,
                c.canonical_sha256(model.to_dict()),c.digest(declared),
                allow_learned_tactics=True,diagnostic_status_entry=True,
                screen_capped_status_moves=True)
            actor = replace(prototype,calls=0,model=model,model_sha256=pin,
                qualification_sha256=scope.identity,development_story_scope=scope,
                output=output/'tower-trainers')
            actor.require_story_identity()
            holder['scoped_actors'][objective] = (
                actor,NativeBattlerHistory(actor,initial=holder['latest_battle']))
            holder['last_calls'][objective] = 0
        return holder['scoped_actors'][objective][0]

    def gym_trainer_actor(contract):
        key = gym_obstruction_scope_key(contract) if include_rewards else None
        if key is None:
            return holder['actor']
        if key not in holder['scoped_actors']:
            path = d.ROOT/'reused-damage/candidate-model.json'
            pin = '29792a3292e8d5c103e39d5914d8b1c9388c65af107c989141331e14503712ad'
            assert c.digest(path) == pin
            model = TrainerPracticeThreeHeadModel.from_dict(d.prior.doc(path))
            prototype = holder['actor']
            scope = DevelopmentStoryScope(source['state_sha256'],prototype.root_lineage_id,pin,
                c.canonical_sha256(model.to_dict()),c.digest(declared),contract=contract,
                allow_learned_tactics=True,diagnostic_status_entry=True,
                screen_capped_status_moves=True)
            actor = replace(prototype,calls=0,model=model,model_sha256=pin,
                qualification_sha256=scope.identity,development_story_scope=scope,
                output=output/key)
            actor.require_story_contract(contract)
            holder['scoped_actors'][key] = (
                actor,NativeBattlerHistory(actor,initial=holder['latest_battle']))
            holder['last_calls'][key] = 0
        actor = holder['scoped_actors'][key][0]
        actor.require_story_contract(contract)
        return actor

    def silph_card_key_actor(contract):
        if not include_rewards:
            raise ValueError('Silph phase is not enabled')
        key = ('silph-contract-'+c.canonical_sha256(asdict(contract))
               if include_silph_continuation else 'silph-card-key')
        if key not in holder['scoped_actors']:
            path, pin = silph_damage_component(silph_useful_moves)
            assert c.digest(path) == pin
            model = TrainerPracticeThreeHeadModel.from_dict(d.prior.doc(path))
            prototype = holder['actor']
            scope = DevelopmentStoryScope(source['state_sha256'],prototype.root_lineage_id,pin,
                c.canonical_sha256(model.to_dict()),c.digest(declared),contract=contract,
                allow_learned_tactics=True,diagnostic_status_entry=True,
                screen_capped_status_moves=True)
            actor = replace(prototype,calls=0,model=model,model_sha256=pin,
                qualification_sha256=scope.identity,development_story_scope=scope,
                output=output/key)
            actor.require_story_contract(contract)
            holder['scoped_actors'][key] = (
                actor,NativeBattlerHistory(actor,initial=holder['latest_battle']))
            holder['last_calls'][key] = 0
        actor = holder['scoped_actors'][key][0]
        actor.require_story_contract(contract)
        return actor

    def observed_resource_runtime(runtime):
        league_maps = {int(c.MapId.INDIGO_PLATEAU), int(c.MapId.INDIGO_PLATEAU_LOBBY)}
        league_maps.update(int(t.room) for t in LEAGUE_PLAYER_TARGETS + (CHAMPION_PLAYER_TARGET,))
        return (replace(runtime,profile=league_profile(runtime.profile))
                if include_rewards and runtime.reader.read().map_id in league_maps else runtime)

    def league(objective,runtime,executor,_,*,allow_engaged=False):
        if not include_rewards:
            return None
        from pokemon_red_completion.red_player_league_options import engaged_league_contract
        retained = (engaged_league_contract(runtime.reader,rom,include_champion=True)
                    if allow_engaged else None)
        target = retained[0] if retained is not None else live_league_player_target(runtime.reader.read(),include_champion=True,
            development_retry_reentry=True,challenge_started=(
                runtime.reader.read_league_challenge_started()
                if runtime.reader.read().map_id == int(c.MapId.INDIGO_PLATEAU) else None))
        if target is None:
            return victory_road_story_option(runtime,executor,None,route=route,
                battler=holder['actor'],preparation_plan=holder['plan'],record=record,
                access_objective_ref=objective)
        if not league_native_prerequisite(target, objective):
            return None
        if (late_collection_deferred(runtime,league_first=league_first)
                and target is LEAGUE_PLAYER_TARGETS[0] and not allow_engaged
                and not league_entry_medicine_ready(runtime.reader.read())):
            return None  # No money/stock is invented and no replacement goal is chosen.
        native_objective = target.objective_id
        if native_objective not in holder['scoped_league_runtimes']:
            # Provisional League-only recombination of existing trained heads. Goal selection,
            # early/gym/Silph/wild actors and the frozen damage head are unchanged.
            path = c.BASE/'red-isolated-player-package-20261009-v1/assisted-exploration-recovery/diagnostics/agatha-control-reuse-20261010-v1/control52-model.json'
            pin = '111ef28dd505a61c6c8b3c0c7521d0d395119afba6f3b0e090a86095a03a4ad2'
            assert c.digest(path) == pin
            prototype = replace(holder['actor'],model=TrainerPracticeThreeHeadModel.from_dict(
                d.prior.doc(path)),model_sha256=pin)
            composed = bind_live_league_runtime(observed_resource_runtime(runtime),
                battler=prototype,rom=rom,route_world=route.route_world,
                output=output/('league-'+native_objective),work_order=declared.read_bytes(),
                include_champion=True,development_retry_reentry=True,allow_engaged=allow_engaged)
            if composed is None:
                return None
            configured, actor, _ = composed
            holder['scoped_league_runtimes'][native_objective] = configured
            holder['scoped_actors'][native_objective] = (
                actor,NativeBattlerHistory(actor,initial=holder['latest_battle']))
            holder['last_calls'][native_objective] = 0
        configured = holder['scoped_league_runtimes'][native_objective]
        if allow_engaged:
            return None  # Actor is bound for compulsory continuation,not a new challenge.
        levels = tuple(m.observation.level for m in d.observe_preparation_members(
            runtime.emulator,holder['plan']) if m.purpose.value == 'combat')
        return league_story_option(configured,executor,route=route,combat_levels=levels,
            record=record,history=holder['observe_history'],maximum_level_deficit=30,
            development_retry_reentry=True,include_champion=True,
            progress_objective_ref=objective)

    def ensure_training_pool(runtime):
        if training_admission is None:
            return None
        from pokemon_red_completion.executor import NativeLessonController
        from pokemon_red_completion.red_scoped_training_battlers import ScopedTrainingBattlers
        # Read-only construction/preflight shares the same source but cannot
        # register a counted executing pool. Native session construction does.
        if not isinstance(holder['actor'].session, NativeLessonController):
            return None
        owned = holder['runtime']
        if (runtime.reader is not holder['training_reader']
            or runtime.emulator is not owned.emulator or runtime.adapter is not owned.adapter):
            raise ValueError('production TRAIN pool cannot replace its reader/runtime')
        if 'training_pool' not in holder:
            wild = preparation_actor(15, _bind_pool=False)
            story = leader_actor(MISTY_REWARD, runtime, _bind_pool=False)
            if wild.session is not runtime.emulator or story.session is not runtime.emulator:
                raise ValueError('production TRAIN pool cannot replace its native session')
            pool = ScopedTrainingBattlers.for_production_source(wild, story,
                admission=training_admission, source=source, output=output/'scoped-battles',
                reader=runtime.reader,
                initial=holder['initial_battle'])
            holder['training_pool'] = pool
            for key, actor in (('preparation-map-15', pool.wild),
                               ('defeat_misty', pool.story(story.development_story_scope.contract))):
                holder['scoped_actors'][key] = (actor, NativeBattlerHistory(actor, initial=holder['initial_battle']))
        return holder['training_pool']

    def leader_actor(reward, runtime, *, _bind_pool=True):
        """Same prospective scoped actor for a selected or retained leader."""
        if training_admission is not None and reward.objective_id != 'defeat_misty':
            raise ValueError('production TRAIN story requires the declared Misty target')
        if reward.objective_id not in holder['scoped_actors']:
            path = d.ROOT/'reused-damage/candidate-model.json'
            pin = '29792a3292e8d5c103e39d5914d8b1c9388c65af107c989141331e14503712ad'
            assert c.digest(path) == pin
            model = TrainerPracticeThreeHeadModel.from_dict(d.prior.doc(path))
            contract = reward.contract(rom, runtime.reader.read())
            prototype = holder['actor']
            scope = DevelopmentStoryScope(source['state_sha256'], prototype.root_lineage_id, pin,
                c.canonical_sha256(model.to_dict()), c.digest(declared),
                contract=contract, gym_reward=reward, allow_learned_tactics=True,
                diagnostic_status_entry=True, screen_capped_status_moves=True,
                train_admission=training_admission)
            actor = replace(prototype, calls=0, model=model, model_sha256=pin,
                qualification_sha256=scope.identity, development_story_scope=scope,
                output=output/('gym-'+reward.objective_id),
                **({'train_story_contract': contract} if training_admission is not None else {}))
            actor.require_story_contract(contract)
            holder['scoped_actors'][reward.objective_id] = (
                actor, NativeBattlerHistory(actor, initial=holder['latest_battle']))
            holder['last_calls'][reward.objective_id] = 0
        if training_admission is not None and _bind_pool:
            ensure_training_pool(runtime)
        return holder['scoped_actors'][reward.objective_id][0]

    def base(rt, actions, observation):
        nonlocal route
        holder['progression_capture_option'] = None
        safari_exit = retained_safari_exit_binding(rt, actions)
        if safari_exit is not None:
            return control_inventory(safari_exit)
        rod_text = acquired_fishing_tool_dialogue_binding(rt, actions)
        if rod_text is not None:
            return control_inventory(rod_text)
        postgame = postgame_return_binding(rt, actions)
        if postgame is not None:
            return control_inventory(postgame)
        blackout = field_blackout_binding(rt,actions)
        if blackout is not None:
            return control_inventory(blackout)
        raw = rt.reader.read()
        if include_rewards and raw.battle_state == 2:
            for reward in REWARDS:
                if (raw.map_id != reward.map_id
                        or rt.reader.read_active_trainer_identity() != (
                            reward.trainer_class, reward.trainer_class - 200, reward.trainer_set)):
                    continue
                if reward.objective_id not in {
                    o.id for o in rt.adapter.graph.available_objectives(rt.adapter.observe().game_state)
                }:
                    continue
                retained = engaged_story_binding(rt, actions, rom=rom,
                    battler=leader_actor(reward, rt),
                    objective_id=reward.objective_id)
                if retained is not None:
                    return control_inventory(retained)
        if (include_rewards and raw.battle_state == 2 and raw.map_id in {
                int(t.room) for t in LEAGUE_PLAYER_TARGETS + (CHAMPION_PLAYER_TARGET,)}):
            retained = retained_trainer(rt,actions)
            if retained is not None:
                return control_inventory(retained)
        if include_early_preparation:
            retained = retained_early_trainer_binding(rt,actions,rom=rom,battler=holder['actor'])
            if retained is not None:
                return control_inventory(retained)
        if rt.reader.read().battle_state == 2 and rt.reader.read().map_id == int(c.MapId.ROUTE_22):
            return control_inventory(retained_trainer(rt,actions))
        if rt.reader.read().battle_state == 1:
            escape = interrupted_wild_binding(rt, actions, allow_fainted_active=True, rom=rom,
                pending_trainer_factory=(lambda: retained_early_trainer_binding(
                    rt, actions, rom=rom, battler=holder['actor']))
                if include_early_preparation else None)
            if escape is not None:
                return control_inventory(escape)
        motion = (interrupted_pewter_escort_binding(rt,actions)
                  or interrupted_motion_binding(rt,actions,rom=rom))
        if motion is not None:
            return control_inventory(motion)
        if not _field_ready(rt):
            # A timed-out earned rematch can leave its already-paid closing
            # text open even though the joypad is ready. Do not confirm an
            # arbitrary NPC transaction or silently replay the defeated room.
            closing_league_text = any(
                raw.map_id == int(t.room) and raw.battle_state == 0
                and event_flag_is_set(raw.event_flags,t.event)
                for t in LEAGUE_PLAYER_TARGETS
            )
            recovery = RedControlRecoveryGoalProvider(
                actions,rt.reader,rt.emulator,rt.adapter,
                settle_dialogue=closing_league_text).offer(observation)
            if recovery.binding is not None:
                return control_inventory(recovery.binding)
        route = replace(route, route_world=mansion_departure_world(
            route.route_world, cartridge_route_world, raw).with_current_observation(rt.reader))
        holder['plan'] = refresh_preparation_roster(rt.emulator, holder['plan'], evolution_rom=rom)
        resource_runtime = observed_resource_runtime(rt)
        def learned_transport_handler(inner,spec):
            if not include_early_preparation or spec.kind not in {
                    GoalKind.RESUPPLY, GoalKind.EVOLVE_SPECIES}:
                return inner
            return EngagedStoryRouteHandler(inner,rt.reader,
                lambda:retained_early_trainer_binding(rt,actions,rom=rom,battler=holder['actor']),
                maximum_trainers=32)
        ordinary = RedResourceGoalRouter(resource_runtime, actions, route.route_world,
            quote_resource_costs=True, prepare_capture_party=False,
            prepare_capture_escort=False, include_recovery_offers=False,
            routed_storage_relief=include_rewards,
            capture_reserve=player_supply_reserve(resource_runtime.profile),
            interruption_handler_wrapper=learned_transport_handler).enumerate(observation)
        if late_collection_deferred(rt,league_first=league_first):
            # The base mart is a capture-ball purchase. Existing income,
            # medicine and free PP resources stay in the supplemental menu.
            # Do not spend the declared League reserve on optional collection.
            ordinary = GoalBindingSet(tuple(o if o.kind is not GoalKind.RESUPPLY else
                GoalOpportunity('league-first:deferred-capture-stock',GoalKind.RESUPPLY,
                    GoalAvailability.UNAVAILABLE,
                    unavailable_reason=GoalUnavailableReason.TEMPORARILY_BLOCKED)
                for o in ordinary.opportunities),
                tuple(b for b in ordinary.bindings if b.kind is not GoalKind.RESUPPLY),
                allow_resource_variants=ordinary.allow_resource_variants)
        # This remains a model-owned storage peer, not the reserve safeguard.
        # Conserve unused reward TMs rather than sell/discard them when the
        # eight-badge bag needs room for both medicine and a finite PP resource.
        earned_capacity = rt.reader.read().badge_bits == 255
        capacity = (completed_key_storage_binding(rt, actions, route=route,
                    reserved_slots=3 if earned_capacity else 2,
                    include_indigo_lobby=earned_capacity,
                    allow_spare_tm_storage=earned_capacity)
                    if include_rewards else None)
        if capacity is not None:
            available = any(b.kind is capacity.kind for b in ordinary.bindings)
            ordinary = GoalBindingSet(
                tuple(o for o in ordinary.opportunities if available or o.kind is not capacity.kind)
                + (capacity.opportunity,), ordinary.bindings + (capacity,),
                allow_resource_variants=True)
        centers = frozenset({int(c.MapId.INDIGO_PLATEAU_LOBBY)} |
                           {int(value) for name, value in c.MapId.__members__.items()
                            if name.endswith('POKECENTER')})
        nurse_route = player_healing_route(rt, route=route)
        home = (None if _raw_party_fully_restored(rt.reader.read()) else
                nearest_reachable_player_center(rt, route=nurse_route, centers=centers,
                                                include_indigo_lobby=True))
        nurse = player_nurse_binding(rt, actions, route=nurse_route, home=home,
                                    include_rewards=include_rewards,bindings=ordinary)
        if nurse is None and include_rewards:
            combined = RedCombinedFieldRestoreGoalProvider(
                RedFaintAwareFieldRestoreGoalProvider(actions,rt.reader,rt.emulator,rt.adapter,
                    prioritize_status_cure=earned_capacity),
                RedFieldPpRestoreGoalProvider(actions,rt.reader,rt.emulator,rt.adapter,
                                             allow_fainted_reserves=True))
            nurse = combined.offer(observation).binding
        if nurse is not None:
            ordinary = GoalBindingSet(
                tuple(o for o in ordinary.opportunities if o.kind is not GoalKind.RESTORE_TEAM)
                + (nurse.opportunity,),
                tuple(b for b in ordinary.bindings if b.kind is not GoalKind.RESTORE_TEAM)
                + (nurse,), allow_resource_variants=ordinary.allow_resource_variants)
        # A real adjacent capture is a peer of every story/recovery alternative.
        # The ball allocation/status executor is disclosed mechanical support;
        # neither Snorlax nor the Fuchsia destination is selected here.
        target = route12_snorlax_target(rom)
        bag = dict(observation.raw.bag_items or ())
        choice = carried_static_capture_choice(bag)
        capture = None
        ball, allocation = choice if choice is not None else (None, None)
        if allocation is not None and not event_flag_is_set(observation.raw.event_flags, target.event_flag):
            provider = RedStaticCaptureGoalProvider(
                rom, target, ball, allocation, rt.reader, rt.adapter,
                rt.emulator, actions, output/('snorlax-'+c.sha256(
                    rt.emulator.save_state_bytes()).hexdigest()),
                prepare_status=True, maximum_status_attempts=3,
                preserve_viable_active=True, weaken_capture=True,
                prepare_facing=True, allow_snorlax=True, require_status_success=False,
                readiness_budget=CapturePreparationBudget(
                    ball,allocation,allocation,require_status=False),
            )
            capture = optional_status_static_offer(provider, rt, actions, observation).binding
        if capture is not None:
            opens_passage = 'reach_fuchsia' in {
                o.id for o in rt.adapter.graph.available_objectives(rt.adapter.observe().game_state)}
            holder['progression_capture_option'] = progression_capture_supplement(
                capture,observation.situation,opens_passage=opens_passage)
            ordinary = masked_static_capture_inventory(ordinary, capture)
        return GoalBindingSet(tuple(o for o in ordinary.opportunities
                                    if o.kind is not GoalKind.ADVANCE_STORY),
                              tuple(b for b in ordinary.bindings
                                    if b.kind is not GoalKind.ADVANCE_STORY),
                              allow_resource_variants=ordinary.allow_resource_variants)

    def branches(rt, actions, observation):
        if include_matchup_observation:
            holder['current_matchup_witnesses'] = []
        def gym(reward, runtime, executor, _):
            # TRAIN has one exact prospective leader contract. Bind its
            # admitted actor before the probe constructs any eager controller.
            # The default DEVELOPMENT path retains its historical two passes.
            probe_actor = (holder['actor'] if training_admission is None
                           else leader_actor(reward, runtime))
            if include_rewards and reward.objective_id == 'defeat_surge':
                switch = surge_switch_option(runtime, executor, route=route,
                    history=puzzle_history, record=lambda row:record('gym_switch', row),
                    battler=holder['actor'])
                if switch is not None:
                    return switch
            leader_quotes = []
            preliminary_matchups = []
            row = gym_story_option(runtime, executor, reward=reward, route=route,
                battler=probe_actor, preparation_plan=holder['plan'],
                continuous_travel=continuous_travel,allow_surf=include_rewards,
                trainer_battler_for_contract=gym_trainer_actor,
                observe_leader_binding=lambda contract, binding: leader_quotes.append((contract, binding)),
                **({'observe_matchup_binding': preliminary_matchups.append}
                   if include_matchup_observation else {}))
            if row is None and include_rewards and reward.objective_id == 'defeat_surge':
                lesson = cut_lesson_binding(runtime, executor, rom=rom, allow_status_replacement=True)
                if lesson is not None:
                    return (replace(lesson, story_objective_ref=reward.objective_id),
                            OptionChallenge(False, False, 0., 0., 0.))
            if row is None and reward.objective_id == 'defeat_blaine':
                row = mansion_exit_option(runtime,executor,None,route=route)
            if row is None or not leader_quotes:
                if include_matchup_observation:
                    holder['current_matchup_witnesses'].extend(preliminary_matchups)
                return row
            if len(leader_quotes) != 1 or leader_quotes[0][1] is not row[0]:
                raise ValueError('leader actor qualification lost its exact binding witness')
            if training_admission is not None:
                if include_matchup_observation:
                    holder['current_matchup_witnesses'].extend(preliminary_matchups)
                return row  # First pass already used the exact admitted TRAIN actor.
            # Leaders and exact ordinary gym obstructions use separate scopes.
            # Other ordinary route trainers remain qualified K. No lead swap,
            # productive-stay override or guessed preparation is introduced.
            actor = leader_actor(reward, runtime)
            return gym_story_option(runtime, executor, reward=reward, route=route,
                battler=actor, preparation_plan=holder['plan'],
                continuous_travel=continuous_travel,allow_surf=include_rewards,
                trainer_battler_for_contract=gym_trainer_actor,
                **({'observe_matchup_binding': holder['current_matchup_witnesses'].append}
                   if include_matchup_observation else {}))

        def arrival(objective, runtime, executor, _):
            if objective == 'reach_cerulean':
                levels = tuple(m.observation.level for m in d.observe_preparation_members(
                    runtime.emulator,holder['plan']) if m.purpose.value == 'combat')
                return cerulean_arrival_story_option(runtime,executor,route=route,
                    battler=holder['actor'],combat_levels=levels)
            # Fuchsia's real Snorlax gate is an observed prerequisite, not a
            # supplied phase preference. Reuse its already-qualified approach;
            # this never activates the one-off or fabricates an open passage.
            target = route12_snorlax_target(rom) if objective == 'reach_fuchsia' else None
            if target is not None and not event_flag_is_set(runtime.reader.read().event_flags,
                                                           target.event_flag):
                members = d.observe_preparation_members(runtime.emulator, holder['plan'])
                levels = tuple(m.observation.level for m in members if m.purpose.value == 'combat')
                return static_approach_option(runtime, executor, route=route, target=target,
                    objective_id=objective, battler=holder['actor'], combat_levels=levels,
                    continuous_travel=continuous_travel)
            if objective == 'reach_vermilion' and runtime.reader.read().map_id == int(c.MapId.BILLS_HOUSE):
                return early_story_travel_option(runtime,executor,objective_id=objective,
                    route=route,battler=holder['actor'])
            binding = story_travel_binding(runtime, executor, objective_id=objective,
                route=route, frontier=True, stop_at_map_boundary=True,
                allow_surf=include_rewards and objective == 'reach_cinnabar')
            combat = False
            if binding is None:
                binding = obstructing_story_battle_binding(runtime, executor,
                    objective_id=objective, route=route, battler=holder['actor'],
                    frontier=True, allow_sequence=True,
                    allow_surf=include_rewards and objective == 'reach_cinnabar')
                combat = binding is not None
            return (None if binding is None else
                    (replace(binding, story_objective_ref=objective),
                     OptionChallenge(combat, False, 0., 0., 0.)))

        observers = {r.objective_id: lambda *args, r=r: gym(r, *args) for r in REWARDS}
        observers.update({o: lambda *args, o=o: arrival(o, *args) for o in ARRIVAL_OBJECTIVES})
        if include_rewards:
            levels = tuple(m.observation.level for m in d.observe_preparation_members(
                rt.emulator,holder['plan']) if m.purpose.value == 'combat')
            early = dict(route=route,battler=holder['actor'],combat_levels=levels)
            def silph(runtime, executor, observed):
                kwargs = dict(route=route,battler=holder['actor'],
                    battler_for_contract=silph_card_key_actor,continuous_travel=continuous_travel,
                    allow_surf=include_rewards,record=record)
                row = silph_card_key_story_option(runtime,executor,observed,**kwargs)
                return row if row is not None or not include_silph_continuation else (
                    silph_continuation_story_option(runtime,executor,observed,
                        combat_levels=levels,**kwargs))
            def early_errand(runtime, executor, observed):
                from pokemon_red_completion.red_player_lab_rival import lab_rival_story_option
                def lab_actor(contract):
                    key = 'lab-rival-gate'
                    if key not in holder['scoped_actors']:
                        path,pin = silph_damage_component(False)
                        assert c.digest(path) == pin
                        model = TrainerPracticeThreeHeadModel.from_dict(d.prior.doc(path))
                        prototype = holder['actor']
                        scope = DevelopmentStoryScope(source['state_sha256'],prototype.root_lineage_id,
                            pin,c.canonical_sha256(model.to_dict()),c.digest(declared),contract=contract,
                            allow_learned_tactics=True,diagnostic_status_entry=True,
                            screen_capped_status_moves=True)
                        actor = replace(prototype,calls=0,model=model,model_sha256=pin,
                            qualification_sha256=scope.identity,development_story_scope=scope,
                            output=output/key)
                        actor.require_story_contract(contract)
                        holder['scoped_actors'][key] = (
                            actor,NativeBattlerHistory(actor,initial=holder['latest_battle']))
                        holder['last_calls'][key] = 0
                    return holder['scoped_actors'][key][0]
                row = lab_rival_story_option(runtime,executor,observed,route=route,
                    battler=holder['actor'],battler_for_contract=lab_actor)
                return row if row is not None else parcel_story_option(runtime,executor,observed,route=route)
            observers.update({
                'receive_pokedex': early_errand,
                'help_bill': lambda *args: bill_story_option(*args,**early),
                'obtain_cut': lambda *args: cut_story_option(*args,**early),
                'rescue_fuji': lambda *args: fuji_story_option(*args,**early,
                    trainer_battler=tower_trainer_actor(args[0])),
                'reach_saffron': lambda *args: saffron_story_option(*args,route=route,battler=holder['actor']),
                'liberate_silph': silph,
            })
            holder['partial_native_capabilities'] = ({} if include_silph_continuation else
                {'liberate_silph':'first trainer and Card Key only'})
            def hideout(objective, runtime, executor, observation):
                row = hideout_story_option(runtime, executor, observation,
                    objective_id=objective, **early)
                return row if row is not None else local_story_prefix_option(
                    runtime, executor, objective_id=objective, route=route)
            observers.update({o: lambda *args,o=o: hideout(o,*args)
                for o in ('clear_rocket_hideout','obtain_silph_scope')})
            def reward(objective, runtime, executor, _):
                kwargs = {}
                if objective == 'obtain_surf':
                    raw = runtime.reader.read()
                    compatible = sorted(((-level, slot) for slot, (species, level) in enumerate(
                        zip(raw.party_species_ids or (), raw.party_levels or ()), 1)
                        if 57 in cartridge.species(species).tmhm_moves))
                    if not compatible:
                        return None
                    _, slot = compatible[0]
                    moves = raw.party_moves[slot-1]
                    legal = [index for index, move in enumerate(moves, 1)
                             if move not in {15, 19, 57, 70, 148}]
                    if not legal:
                        return None
                    replaced = moves.index(0)+1 if 0 in moves else max(legal)
                    holder['hm_mechanics'] = dict(party_slot=slot, replace_slot=replaced,
                        species_id=raw.party_species_ids[slot-1], before_move=moves[replaced-1],
                        supplied_selection='strongest compatible member;last non-HM slot',
                        learned_recipient_selection=False)
                    kwargs = dict(party_slot=slot, replace_slot=replaced, record=record)
                return safari_reward_story_option(runtime, executor, objective_id=objective,
                    route=route, complete_center_approach=True, **kwargs)
            observers.update({o: lambda *args, o=o: reward(o, *args)
                              for o in ('obtain_surf', 'obtain_strength')})
            observers['obtain_secret_key'] = lambda *args: mansion_secret_key_option(*args, route=route)
            def victory(runtime, executor, observed):
                actor = holder['actor']
                raw = runtime.reader.read()
                if raw.map_id == int(c.MapId.ROUTE_22) and not event_flag_is_set(raw.event_flags,1318):
                    actor = route22_actor(runtime)
                return victory_road_story_option(runtime,executor,observed,route=route,
                    battler=actor,preparation_plan=holder['plan'],record=record)
            observers['cross_victory_road'] = victory
            observers.update({t.objective_id: lambda *args,o=t.objective_id: league(o,*args)
                              for t in LEAGUE_PLAYER_TARGETS + (CHAMPION_PLAYER_TARGET,)})
        if training_admission is not None:
            # This prospective TRAIN lesson admits only its declared leader;
            # unsupported story callbacks must not construct a different actor.
            objective = training_admission.declaration()['objective_id']
            observers = {objective: observers[objective]}
        full_capabilities = set(observers) - set(holder.get('partial_native_capabilities', {}))
        holder['configured_native_capabilities'] = sorted(full_capabilities)
        legal = {o.id for o in rt.adapter.graph.available_objectives(observation.game_state)}
        holder['legal_native_objectives'] = sorted(legal)
        holder['missing_native_capabilities'] = sorted(legal - full_capabilities)
        result = registered_story_branches(rt, actions, observers=observers)
        holder['available_native_branches'] = [b.story_objective_ref for b, _ in result]
        return result

    def history(*, checkpoint_error_type=None, checkpoint_error=None):
        actors = {'wild': (holder['actor'], holder['history']), **holder['scoped_actors']}
        changed = []
        for name, (actor, observe) in actors.items():
            try:
                current = observe()
            except FileNotFoundError:
                if checkpoint_error_type is None:
                    raise
                checkpoint = (observe.checkpoint_after_execution_failure
                    if checkpoint_error_type in {'BattleRuntimeError','BattleRuntimeTimeoutError',
                                                 'ProtectedRecoveryError','KeyboardInterrupt'}
                    else observe.checkpoint_after_budget_stop)
                current, censored = checkpoint(
                    terminal_state_sha256=c.sha256(holder['runtime'].emulator.save_state_bytes()).hexdigest(),
                    error_type=checkpoint_error_type,
                    **({'error': checkpoint_error}
                       if checkpoint_error_type == 'ControllerFrameBudgetError' else {}))
                holder['censored_battle_checkpoint'] = censored
            if actor.calls != holder['last_calls'][name]:
                changed.append(current)
            holder['last_calls'][name] = actor.calls
        if len(changed) > 1:
            raise ValueError('multiple actors changed between native history boundaries')
        if changed:
            holder['latest_battle'] = changed[0]
        return holder['latest_battle']

    holder['observe_history'] = history

    def preparation(rt, actions, observation):
        # Reconnect the existing optional member-dose machinery after a real
        # observed loss. No target, trainee, training or recovery is selected.
        latest = holder['observe_history']()
        lost = latest if latest is not None and latest.result.value == 'lost' else None
        if not observation.input_ready:
            return ()
        raw = rt.reader.read()
        if raw.battle_state or not _raw_party_fully_restored(raw):
            return ()
        preview = None
        if (include_silph_continuation and raw.map_id == int(c.MapId.SAFFRON_POKECENTER)
            and 'liberate_silph' in {o.id for o in rt.adapter.graph.available_objectives(observation.game_state)}):
            silph_phase = silph_continuation_phase(raw)
            if silph_phase is not None:
                preview = silph_continuation_contract(rom,raw,silph_phase,
                    rival_starter=rt.reader.read_rival_starter() if silph_phase == 'rival' else None)
        if raw.map_id == int(c.MapId.ROUTE_22):
            preview = route22_preparation_contract(rom,rt.reader,
                available_objectives={o.id for o in rt.adapter.graph.available_objectives(
                    observation.game_state)})
        target = live_league_player_target(raw,include_champion=True,
            development_retry_reentry=True,challenge_started=(
                rt.reader.read_league_challenge_started()
                if raw.map_id == int(c.MapId.INDIGO_PLATEAU) else None))
        if target is not None and target.objective_id in holder['scoped_league_runtimes']:
            preview = holder['scoped_league_runtimes'][target.objective_id].league_story_battle_controller.contract
        if preview is None and include_early_preparation:
            completed = set(rt.adapter.graph.completed_ids(observation.game_state))
            legal = {o.id for o in rt.adapter.graph.available_objectives(observation.game_state)}
            # Reuse the existing anticipatory Brock preview; after him only an
            # actually legal nearby leader may supply the opposition forecast.
            reward = (BROCK_REWARD if 'defeat_brock' not in completed else
                      next((r for r in REWARDS if r.objective_id in legal
                            and (raw.map_id == r.map_id or r.objective_id == 'defeat_misty')),None))
            if reward is not None:
                preview = reward.contract(rom,raw)
        if preview is not None:
            quote = trainer_party_quote(rom,preview.trainer_identity[0],preview.trainer_identity[2],
                allow_final_class=preview.objective_id=='defeat_lance')
            opponent_levels = tuple(m.level for m in quote.party)
        elif lost is not None:
            opponent_levels = lost.opponent_levels
        else:
            return ()
        opponent_levels = retained_preparation_opposition(opponent_levels,lost)
        centers = frozenset({int(c.MapId.INDIGO_PLATEAU_LOBBY)} |
                           {int(value) for name, value in c.MapId.__members__.items()
                            if name.endswith('POKECENTER')})
        home = nearest_reachable_player_center(rt, route=route, centers=centers,
                                               include_indigo_lobby=True)
        if home is None:
            return ()
        # Quote the same observed trainer hazards reserved by native execution.
        # Geometric reachability must not advertise grass behind an uncleared
        # bridge as a currently executable dose. This changes availability,
        # never chooses story instead of training or bypasses a trainer.
        start = Gen1TraversalObserver(rt.reader, capability_projector=cut_capabilities,
            hazard_projector=Gen1TrainerSightProjector(rom,rt.reader,
                full_event_offsets=True)).observe()
        venues = []
        tables = wild_tables(rom,medium='grass')
        if target is not None and home == int(c.MapId.INDIGO_PLATEAU_LOBBY):
            import lorelei_current_party_20260929 as venue
            try:
                corridor = venue.preparation_corridor(route,start)
                travel = route.route_world.plan_feasible_to_map(start,corridor.map_id,
                                                               goal_at=corridor.origin_at)
                levels = tuple(level for level,_ in tables[corridor.map_id])
                venues.append((preparation_venue_rank(levels,travel.cost),corridor.map_id,
                               corridor,corridor.source_id,home,levels))
            except (RoutePlanningError,RuntimeError):
                record('preparation-venue-unavailable',dict(source='existing-victory-road-venue'))
        early_venues = ('wild:Route1:grass','wild:Route2:grass','wild:Route3:grass',
                        'wild:Route4:grass','wild:Route24:grass','wild:Route25:grass')
        later_venues = ('wild:Route7:grass', 'wild:Route8:grass', 'wild:Route11:grass',
                        'wild:Route13:grass', 'wild:Route14:grass', 'wild:Route15:grass',
                        'wild:Route21:grass')
        completed = set(rt.adapter.graph.completed_ids(observation.game_state))
        if include_early_preparation and 'receive_pokedex' not in completed:
            # Viridian's old man closes the north exit until Oak's errand.
            # Route1 remains a real optional dose; do not advertise Route2
            # merely because the ungated map topology quotes a path to it.
            early_venues,later_venues = early_venues[:1],()
        elif include_early_preparation and 'defeat_brock' not in completed:
            # Pewter's native east-exit guide blocks Route3 until Brock, even
            # though bare map topology quotes it. This is an access constraint,
            # not a supplied decision to fight him or train another member.
            early_venues,later_venues = early_venues[:2],()
        sources=(early_venues if include_early_preparation else ()) + later_venues
        quote_world=preparation_quote_world(rom,route.route_world,raw,
            {int(map_id_for_wild_source(source_id)) for source_id in sources})
        for source_id in sources:
            map_id = int(map_id_for_wild_source(source_id))
            try:
                corridor = derive_red_living_dex_wild_corridor(RedEncounterSourceTarget(source_id),
                    route.route_world.terrain[map_id], route.route_world.local_graphs[map_id],
                    excluded=route.route_world.object_blockers.get(map_id, frozenset()), cartridge=rom)
                travel = quote_world.plan_feasible_to_map(start, map_id, goal_at=corridor.origin_at)
                levels = tuple(level for level,_ in tables[map_id])
                if include_early_preparation and not preparation_venue_within_party_band(levels,raw.party_levels):
                    # The same venue selector must not send a level-six fresh
                    # party to late-game grass simply because topology quotes
                    # a path. Keep native encounter bands manageable relative
                    # to its actual strongest member; no training goal is forced.
                    continue
                # The venue's local service, not the source's nearest nurse.
                # This is disclosed adapter support; actual approach/return
                # remain guarded native routes and must prove their terminals.
                venue_home = int({
                    c.MapId.ROUTE_1:c.MapId.VIRIDIAN_POKECENTER,
                    c.MapId.ROUTE_2:c.MapId.VIRIDIAN_POKECENTER,
                    c.MapId.ROUTE_3:c.MapId.PEWTER_POKECENTER,
                    c.MapId.ROUTE_4:c.MapId.CERULEAN_POKECENTER,
                    c.MapId.ROUTE_24:c.MapId.CERULEAN_POKECENTER,
                    c.MapId.ROUTE_25:c.MapId.CERULEAN_POKECENTER,
                    c.MapId.ROUTE_7:c.MapId.CELADON_POKECENTER,
                    c.MapId.ROUTE_8:c.MapId.LAVENDER_POKECENTER,
                    c.MapId.ROUTE_11:c.MapId.VERMILION_POKECENTER,
                    c.MapId.ROUTE_13:c.MapId.FUCHSIA_POKECENTER,
                    c.MapId.ROUTE_14:c.MapId.FUCHSIA_POKECENTER,
                    c.MapId.ROUTE_15:c.MapId.FUCHSIA_POKECENTER,
                    # The northern grass is approached from Pallet, not by
                    # traversing the full sea route to the Cinnabar nurse.
                    c.MapId.ROUTE_21:c.MapId.VIRIDIAN_POKECENTER,
                }[map_id])
                # Quote the actual approach to this service, not a fictional
                # source teleported into the grass. Its future return is still
                # independently verified by the existing preparation executor.
                quote_world.plan_feasible_to_map(start,venue_home,
                    goal_at=(3,3))
                venues.append((preparation_venue_rank(levels,travel.cost),map_id,corridor,
                               source_id,venue_home,levels))
            except (RoutePlanningError, ValueError):
                continue
        if not venues:
            return ()
        _, _, corridor, source_id, home, levels = min(venues, key=lambda v: v[:2])
        selected_battler = preparation_actor(corridor.map_id)
        rows = []
        for gain in (1, 3):
            rows.extend(member_preparation_options(rt, actions, plan=holder['plan'],
                opponent_levels=opponent_levels, forecast_ref=(
                    'actual-cartridge-frontier' if preview is not None else 'observed-native-story-loss'),
                home_map=home, route=replace(route,route_world=quote_world),
                maximum_level_gain=gain, reference_mode='strongest',
                allow_above_reference=lost is not None, observed_defeat=lost, battler=selected_battler,
                corridor=corridor, record=record, hideout_timing=HideoutTiming(),
                include_indigo_lobby=home==int(c.MapId.INDIGO_PLATEAU_LOBBY),
                # A declared quantum returns to a fresh model decision sooner.
                # Targets and outer input/time allowances remain unchanged;
                # normal nurse trips stay metered within this selected dose.
                maximum_battles=preparation_battles, maximum_recoveries=preparation_recoveries,
                repeat_health_limited_zero_progress=True, prepare_transport_escort=True,
                # One metered final nurse return closes an exhausted partial
                # dose truthfully; the target stays failed and needs a new choice.
                restore_exhausted_partial=True))
        holder['preparation_inventory'] = dict(opponent_levels=opponent_levels,
            source_id=source_id, home_map=home, options=len(rows), automatic_training=False,
            current_native_opposition_preview=preview is not None,
            venue_selection_learned=False,venue_support='highest reachable decoded grass band',
            encounter_levels=levels,reachable_venues=len(venues),
            weak_party_band_screen=include_early_preparation,
            maximum_battles_per_selected_dose=preparation_battles,
            maximum_recoveries_per_dose=preparation_recoveries,
            final_partial_restoration="metered_support_after_exhausted_productive_dose",
            repeat_health_limited_zero_progress=True,
            preparation_battler_sha256=selected_battler.model_sha256,
            max_no_progress=holder['plan'].budget.max_no_progress)
        return tuple({b.binding_ref:(b, p) for b, p in rows}.values())

    def resources(rt,actions,observation):
        rt = observed_income_runtime(rt)
        from pokemon_red_completion.red_player_story_menu import merge_resource_observer_bindings
        deferred = late_collection_deferred(rt,league_first=league_first)
        rows = list(postgame_ball_supply_peers(rt,actions,route.route_world,
            interruption_handler_wrapper=(
                (lambda inner, spec: EngagedStoryRouteHandler(inner,rt.reader,
                    lambda:retained_early_trainer_binding(
                        rt,actions,rom=rom,battler=holder['actor']),maximum_trainers=32))
                if include_early_preparation else None)))
        rows.extend(story_static_income_peers(rt,actions,route.route_world,battler=holder['actor']))
        rows.extend(pre_champion_medicine_income_peers(rt,actions,route.route_world))
        if not deferred:
            rows.extend(row for row in postgame_corner_options(
                rt,actions,observation,route.route_world.with_current_observation(rt.reader))
                if row.binding.kind is GoalKind.RESUPPLY)
        if rt.reader.read().badge_bits == 255:
            from red_mixed_bird_collection_20261009 import bird_resource_peers
            rows.extend(bird_resource_peers(rt,actions,observation,
                replace(route,route_world=route.route_world.with_current_observation(rt.reader))))
            rows.extend(postgame_field_supply_peers(
                rt,actions,route=route,include_evolution_stones=not deferred))
            frontier = postgame_league_frontier_peer(rt,actions,route=route)
            if frontier is not None:
                rows.append(frontier)
            income = postgame_league_income_peer(rt,actions,route=route)
            if income is not None:
                rows.append(income)
            if include_early_preparation and not deferred:
                def rod_transport_handler(inner):
                    return EngagedStoryRouteHandler(inner,rt.reader,
                        lambda:retained_early_trainer_binding(
                            rt,actions,rom=rom,battler=holder['actor']),maximum_trainers=32)
                rod = autonomous_fishing_prerequisite_option(
                    rt,observation,actions,route.route_world.with_current_observation(rt.reader),
                    interruption_handler_wrapper=rod_transport_handler)
                if rod is not None:
                    rows.append(rod.binding)
        configured = observed_resource_runtime(rt)
        if configured is rt:
            return merge_resource_observer_bindings(tuple(rows))
        for profile in league_medicine_profiles(configured, revive_target=6, full_heal_target=2):
            inventory = RedResourceGoalRouter(replace(configured,profile=profile),actions,
                route.route_world,quote_resource_costs=True,prepare_capture_party=False,
                prepare_capture_escort=False,include_recovery_offers=False).enumerate_routed_kinds(
                    observation,frozenset({GoalKind.RESUPPLY}))
            rows.extend(b for b in inventory.bindings if b.kind is GoalKind.RESUPPLY)
        return merge_resource_observer_bindings(tuple(rows))

    def supplied_medicine(rt,actions,observation):
        rt = observed_income_runtime(rt)
        configured = observed_resource_runtime(rt)
        if configured is rt:
            return None
        return league_medicine_reserve_binding(configured,actions,route_world=route.route_world,
            observation=observation,development_retry_reentry=True,record=record,
            balanced_first_lots=True,revive_target=6,full_heal_target=2,
            minimum_revive_coverage=3 if league_first else 6)

    def supplied_league_healing(rt,actions,observation):
        rt = observed_income_runtime(rt)
        return league_pre_entry_healing_binding(rt,actions,route=route,
            development_retry_reentry=True,record=record,require_indigo_checkpoint=True)

    def supplied_league_capacity(rt,actions,observation):
        rt = observed_income_runtime(rt)
        from pokemon_red_completion.red_player_league_options import league_medicine_capacity_binding
        return league_medicine_capacity_binding(observed_resource_runtime(rt),actions,
            route=route,observation=observation,development_retry_reentry=True,record=record,
            revive_target=6,full_heal_target=2)

    def collection(rt,actions,observed):
        rt = observed_income_runtime(rt)
        if late_collection_deferred(rt,league_first=league_first):
            return ()
        bird_runtime = rt  # Nursing/snapshots must see the same selected loan guard.
        earned_eight_badges = rt.reader.read().badge_bits == 255
        if earned_eight_badges:
            from red_mixed_collection_dependencies_20261009 import (
                retained_collection_runtime, retained_level_acquisition_edges,
            )
            from pokemon_red_completion.red_living_dex_wild_corridor import (
                bind_red_capture_search_budget_profile,
            )
            rt = retained_collection_runtime(rt,rom)
            rt = replace(rt, level_evolution_acquisition_edges=retained_level_acquisition_edges(
                rom, rt.registration_policy.goal_registered(
                    rt.adapter.observe().collection_observation)))
            # Reuse the already-tested longer full-run search preset. The
            # primary runtime/old checkpoint profile and short probes stay
            # unchanged; only freshly enumerated regional capture peers gain
            # 320legs/512semantic actions/64encounters within native budgets.
            rt = replace(rt,profile=bind_red_capture_search_budget_profile(
                rt.profile,maximum_legs=320))
        # Reuse the prior native vertical Cave entry/return adapter. Highest
        # band alone does not certify an executable Mansion transition.
        geometry = route.route_world.with_current_observation(rt.reader)
        from red_mixed_static_options_20261009 import observed_cave_entrance_world
        geometry=observed_cave_entrance_world(rt,geometry)
        venues = local_collection_evolution_venues(rt,geometry)
        if not earned_eight_badges:
            # Keep the original lower-band fallback if a trainee/helper cannot
            # safely cover the declared Cave encounters. Admission remains in
            # the native evolution referee, with the same loan and HP/PP guards.
            from pokemon_red_completion.red_goal_context import ROUTE_11_TRAINING_VENUE
            venues = (*venues, ROUTE_11_TRAINING_VENUE)
        def fishing_transport_handler(inner):
            return EngagedStoryRouteHandler(inner, rt.reader,
                lambda: retained_early_trainer_binding(
                    rt, actions, rom=rom, battler=holder['actor']),maximum_trainers=32)
        from red_remaining_acquisitions_20261004 import existing_remaining_acquisitions
        with (existing_remaining_acquisitions(include_shared_player=True)
              if earned_eight_badges else nullcontext()):
            rows = player_collection_supplements(rt,actions,observed,world=geometry,
                quote_capture_route_work=quote_capture_route_work,
                **({'include_level_workload': True} if include_level_workload else {}),
                **({'include_capture_invocation': True} if include_capture_invocation else {}),
                prefer_highest_evolution_venue=True,
                maximum_evolution_quanta=512 if earned_eight_badges else 64,
                maximum_evolution_actions=120000 if earned_eight_badges else None,
                maximum_evolution_frames=12000000 if earned_eight_badges else None,
                maximum_evolution_seconds=1800 if earned_eight_badges else None,
                allow_guarded_evolution_escapes=True,
                evolution_training_venues=venues, include_fossil_acquisition=earned_eight_badges,
                capture_interruption_handler_wrapper=(
                    (lambda inner, spec: fishing_transport_handler(inner))
                    if include_early_preparation else None),
                fishing_interruption_handler_wrapper=(fishing_transport_handler
                                                      if include_early_preparation else None),
                evolution_interruption_handler_wrapper=(
                    (lambda inner, spec: fishing_transport_handler(inner))
                    if include_early_preparation else None),
                # The shared capture route lacks Mansion's statue/drop entry skill.
                # All its Red species have native ordinary upper-floor alternatives.
                # Do not misquote that entry; already-local basement capture stays legal.
                unsupported_remote_capture_maps=frozenset({int(c.MapId.POKEMON_MANSION_B1F)}))
        progression = holder.get('progression_capture_option')
        return rows + postgame_acquisition_options(rt,actions,observed,geometry,
            bird_capture_loan=bird_capture_loan,snorlax_capture_loan=snorlax_capture_loan,
            bird_runtime=bird_runtime) + (
            () if progression is None else (progression,))

    def field_dependencies(rt,actions,observed):
        return fly_dependency_options(rt,actions,route=route)

    def matchup_observer(rt, bindings, supplements, boundary):
        from pokemon_red_completion.red_player_matchup import project_current_trainer_matchups
        members = d.observe_preparation_members(rt.emulator, holder['plan'])
        descriptors, proofs = project_current_trainer_matchups(boundary=boundary,
            bindings=bindings, supplements=supplements, members=members,
            witnesses=tuple(holder.get('current_matchup_witnesses', ())))
        record('matchup_boundary', dict(source_sha256=c.sha256(boundary.state).hexdigest(),
            private_receipts=proofs, measurement_only=True))
        return descriptors

    def preparation_party_observer(rt,bindings,supplements,boundary):
        from pokemon_red_completion.player_preparation_party_context import PreparationPartyWitness
        members=d.observe_preparation_members(rt.emulator,holder['plan'])
        return PreparationPartyWitness.from_members(c.sha256(boundary.state).hexdigest(),members).validate_lesson(
            boundary.lesson_snapshot,c.sha256(boundary.state).hexdigest())

    return payload, factory, NativeStoryBranchInventory(base, branches,
        observe_matchups=matchup_observer if include_matchup_observation else None,
        observe_preparation_party=preparation_party_observer if include_preparation_party_context else None,
        reuse_local_route_queries=True,
        enumerate_preparation=preparation if include_preparation else None,
        enumerate_resources=resources if include_rewards else None,
        enumerate_medicine_reserve=supplied_medicine if include_rewards else None,
        enumerate_league_healing=supplied_league_healing if include_rewards else None,
        enumerate_league_capacity=supplied_league_capacity if include_rewards else None,
        enumerate_collection=collection if include_rewards else None,
        enumerate_owned_machines=field_dependencies if include_rewards else None), holder, source


def current_menu_probe():
    """Inspect the actual latest configured menu; never choose or execute a goal."""
    d.authenticate()
    latest = max(int(p.name.removeprefix('native-')) for p in ROOT.glob('native-*') if p.is_dir())
    parent = ROOT/f'native-{latest:02d}'
    context = d.prior.doc(parent/'CONTEXT.json')
    ordinal = len(tuple(ROOT.glob('current-menu-probe-*'))) + 1
    output = ROOT/f'current-menu-probe-{ordinal:02d}'
    output.mkdir(mode=0o700)
    plan = output/'PLAN.json'
    _record(plan, dict(partition='development', fit_allowed=False, native_inputs_permitted=False,
        source_sha256=context['state_sha256'], context_sha256=c.digest(parent/'CONTEXT.json'),
        helper_sha256=c.digest(Path(__file__)), purpose='actual configured menu after existing adapter wiring'))
    payload, factory, menu, holder, source = assembly(parent, output, plan_path=plan,
        continuous_travel=True, include_preparation=True, include_supply=True, include_rewards=True)
    with c.PyBoyAdapter(c.ROM) as em:
        em.load_state_bytes(payload)
        rt = factory(ReadOnlyController(em))
        actions = CountingExecutor(FrameSafeExecutor(ReadOnlyController(em)))
        roles = tuple(m.specimen_ref for m in holder['plan'].roster if m.purpose.value == 'combat')
        options = observe_native_player_options(rt, actions, battle=holder['observe_history'](),
            combat_specimen_refs=roles, remaining_budget=(1.,)*5, target_cash=0,
            ordering_seed_sha256=c.canonical_sha256(dict(ordinal=0)), allow_support=True,
            model_feature_version=7, force_resource_safety=False, **menu.native_callbacks())
        bindings = (options.bindings if isinstance(options,RedLiveOptionSet) else
                    (options.binding,) if hasattr(options,'binding') else ())
        assert em.frame_count == actions.actions_executed == 0 and not em.pressed_buttons
        assert em.save_state_bytes() == payload
        result = dict(passed=bool(bindings), inputs=0, frames=0, source_preserved=True,
            source_sha256=context['state_sha256'], source_node=parent.name,
            kinds=[b.kind.value for b in bindings],
            configured_native_capabilities=holder.get('configured_native_capabilities'),
            missing_native_capabilities=holder.get('missing_native_capabilities'),
            story_objectives=[b.story_objective_ref for b in bindings if b.kind is GoalKind.ADVANCE_STORY])
        _record(output/'RESULT.json', result)
    d.authenticate()
    print(json.dumps(result),flush=True)


def cinnabar_probe():
    """Use the actually earned HM/badge state; never supply arrival or a route."""
    d.authenticate()
    parent = ROOT/'native-14'
    context = d.prior.doc(parent/'CONTEXT.json')
    assert {'defeat_koga','obtain_surf','obtain_strength'} <= set(context['lesson']['completed_objectives'])
    output = ROOT/'cinnabar-probe-01'
    output.mkdir(mode=0o700)
    plan = output/'PLAN.json'
    _record(plan, dict(partition='development', fit_allowed=False, native_inputs_permitted=False,
        source_sha256=context['state_sha256'], context_sha256=c.digest(parent/'CONTEXT.json'),
        helper_sha256=c.digest(Path(__file__)), source_code_sha256=c.source_code_identity(c.REPO),
        purpose='quote the actual next Cinnabar/Surf branch without a teacher route or movement'))
    payload, factory, menu, holder, source = assembly(parent, output, plan_path=plan,
        continuous_travel=True, include_preparation=True, include_supply=True, include_rewards=True)
    with c.PyBoyAdapter(c.ROM) as em:
        em.load_state_bytes(payload)
        rt = factory(ReadOnlyController(em))
        actions = CountingExecutor(FrameSafeExecutor(ReadOnlyController(em)))
        roles = tuple(m.specimen_ref for m in holder['plan'].roster if m.purpose.value == 'combat')
        options = observe_native_player_options(rt, actions, battle=holder['observe_history'](),
            combat_specimen_refs=roles, remaining_budget=(1.,)*5, target_cash=0,
            ordering_seed_sha256=c.canonical_sha256(dict(ordinal=0)), allow_support=True,
            model_feature_version=7, force_resource_safety=False, **menu.native_callbacks())
        bindings = (options.bindings if isinstance(options,RedLiveOptionSet) else
                    (options.binding,) if hasattr(options,'binding') else ())
        refs = [b.story_objective_ref for b in bindings if b.kind is GoalKind.ADVANCE_STORY]
        assert em.frame_count == actions.actions_executed == 0 and not em.pressed_buttons
        assert em.save_state_bytes() == payload
        result = dict(passed='reach_cinnabar' in refs, source_sha256=context['state_sha256'],
            inputs=0, frames=0, source_preserved=True, story_objectives=refs,
            legal_native_objectives=holder['legal_native_objectives'],
            configured_native_capabilities=holder['configured_native_capabilities'],
            missing_native_capabilities=holder['missing_native_capabilities'],
            kinds=[b.kind.value for b in bindings], supplied_destination_preference=False,
            surf_requires_living_holder_badge_and_native_permission=True,
            fitted_examples=0, final_fresh_red_gates=0)
        _record(output/'RESULT.json', result)
    d.authenticate()
    print(json.dumps(result),flush=True)


def probe():
    d.authenticate()
    assert c.digest(SOURCE/'terminal.state') == SOURCE_SHA
    assert c.digest(SOURCE/'CONTEXT.json') == CONTEXT_SHA
    ROOT.mkdir(mode=0o700, exist_ok=True)
    if not (ROOT/'PLAN.json').exists():
        _record(ROOT/'PLAN.json', dict(partition='development', fit_allowed=False,
        independent=False, native_inputs_permitted=False, purpose='remove supplied phase ordering',
        source_sha256=SOURCE_SHA, context_sha256=CONTEXT_SHA,
        source_code_sha256=c.source_code_identity(c.REPO), helper_sha256=c.digest(Path(__file__)),
        parent_sha256=d.prior.PARENT_SHA, declared_at=datetime.now(UTC).isoformat(),
        mission_check=dict(reusable_capability='all legal configured native story branches',
            learned_authority='unchanged highest-score parent, no supplied stage preference',
            transfer_test='exposed zero-input DEVELOPMENT seam, not independent transfer',
            cheapest_falsifier='actual midgame menu contains both native branches',
            time_box='18:11-21:11UTC whole-player integration block',
            stop_condition='missing capability stays absent; no teacher fallback or inputs')))
    ordinal = len(tuple(ROOT.glob('probe-*'))) + 1
    output = ROOT/f'probe-{ordinal:02d}'
    output.mkdir(mode=0o700)
    _record(output/'PLAN.json', dict(partition='development', fit_allowed=False,
        helper_sha256=c.digest(Path(__file__)), source_code_sha256=c.source_code_identity(c.REPO),
        native_inputs_permitted=False, previous_assertion_failure_retained=ordinal > 1,
        source_sha256=SOURCE_SHA, context_sha256=CONTEXT_SHA,
        purpose='inspect actual singleton/missing branch rather than substitute a winner'))
    payload, factory, menu, holder, source = assembly(SOURCE, output)
    with c.PyBoyAdapter(c.ROM) as em:
        em.load_state_bytes(payload)
        readonly = ReadOnlyController(em)
        rt = factory(readonly)
        actions = CountingExecutor(FrameSafeExecutor(readonly))
        roles = tuple(m.specimen_ref for m in holder['plan'].roster
                      if m.purpose.value == 'combat')
        options = observe_native_player_options(rt, actions, battle=holder['observe_history'](),
            combat_specimen_refs=roles, remaining_budget=(1.,)*5, target_cash=0,
            ordering_seed_sha256=c.canonical_sha256(dict(ordinal=0)), allow_support=True,
            model_feature_version=7, force_resource_safety=False,
            **menu.native_callbacks())
        parent, _ = d.prior.models()
        choice = (select_red_live_option(parent, options, seed=202610060901, greedy_selection=True)
                  if isinstance(options, RedLiveOptionSet) else None)
        bindings = options.bindings if isinstance(options, RedLiveOptionSet) else (options.binding,)
        refs = [b.story_objective_ref for b in bindings if b.kind is GoalKind.ADVANCE_STORY]
        passed = isinstance(options, RedLiveOptionSet) and {'defeat_sabrina', 'reach_fuchsia'} <= set(refs)
        assert em.frame_count == actions.actions_executed == 0
        assert em.save_state_bytes() == payload and not em.pressed_buttons
        result = dict(passed=passed, source=source, inputs=0, frames=0,
            prior_spent=holder['prior_spent'], source_preserved=True,
            genuine_alternatives=len(bindings), story_objectives=refs,
            legal_native_objectives=holder['legal_native_objectives'],
            available_native_branches=holder['available_native_branches'],
            missing_native_capabilities=holder['missing_native_capabilities'],
            selected_objective=None if choice is None else choice.selected_binding.story_objective_ref,
            choice=None if choice is None else choice.public_dict(), menu=options.public_dict(),
            stage_from_used=False, legacy_teacher_registry_used=False,
            fitted_examples=0, emulator_released=True)
        _record(output/'RESULT.json', result)
    d.authenticate()
    print(json.dumps({k:v for k,v in result.items() if k not in {'source','choice','menu'}}), flush=True)


def finalize():
    """Recover the report from already sealed native bytes; never replay input."""
    d.authenticate()
    output = ROOT/'native-01'
    declaration = d.prior.doc(ROOT/'NATIVE-PLAN.json')
    assert c.digest(ROOT/'executed-native-01.py') == declaration['helper_sha256']
    metered = d.prior.doc(output/'native/native-costs.json')
    episode = d.prior.doc(output/'native/episode/result.json')
    original = d.prior.doc(SOURCE/'CONTEXT.json')
    payload = (output/'terminal.state').read_bytes()
    assert payload == (output/'native/terminal.state').read_bytes()
    assert payload == (output/'native/episode/step-006/terminal.state').read_bytes()
    assert episode['executed_decisions'] == metered['goal_attempts'] == 6
    assert episode['model_decisions'] == 6 and episode['support_decisions'] == 0
    assert all(o['verification']=='succeeded' and o['evidence']['support']=='observed_static_approach'
               and not o['evidence']['activated'] for o in episode['outcomes'])
    assert episode['outcomes'][-1]['terminal_state_sha256'] == c.sha256(payload).hexdigest()
    spent = accumulate_player_costs(original['spent'], decisions=metered['goal_attempts'],
        actions=metered['actions_attempted'], frames=metered['frames'], seconds=metered['seconds'],
        heals=metered['restore_attempts'], cash_deltas=tuple(o['before']['cash']-o['after']['cash']
                                                          for o in episode['outcomes']))
    ids = episode['outcomes'][-1]['after']['completed_objectives']
    assert set(ids) == set(original['lesson']['completed_objectives'])
    case = output/'readonly-finalization'
    case.mkdir(mode=0o700)
    factory, _, _, _ = shared.assembly(payload, case,
        origin_sha=d.prior.doc(SOURCE/'PLAN.json')['source']['origin_sha256'],
        partition='development', origin_id=ROOT.name, objective_ids=ids)
    with c.PyBoyAdapter(c.ROM) as em:
        em.load_state_bytes(payload)
        rt = factory(ReadOnlyController(em))
        preparation = refresh_preparation_roster(rt.emulator, _plan(original['preparation']),
                                                evolution_rom=c.ROM.read_bytes())
        context = capture_player_continuation(rt, preparation=preparation,
            battle=_battle(original['battle']), spent=spent)
        assert c.canonical_sha256(context['lesson']) == c.canonical_sha256(
            episode['outcomes'][-1]['after']['player_lesson'])
        assert em.frame_count == 0 and em.save_state_bytes() == payload and not em.pressed_buttons
        raw = rt.reader.read()
        _record(output/'CONTEXT.json', context)
        result = dict(passed=False, prefix_verified=True, actual_worker_stopped=True,
            retained_admission_error='story registry requires its own typed native branch',
            retained_reporting_error='accumulate_player_costs called with positional arguments',
            no_native_replay=True, finalizer_inputs=0, finalizer_frames=0,
            finalized_helper_sha256=c.digest(Path(__file__)), episode=episode,
            state_sha256=c.sha256(payload).hexdigest(), context_sha256=c.digest(output/'CONTEXT.json'),
            spent=spent, costs=metered, cash=raw.player_money, map_id=raw.map_id,
            at=[raw.player_y, raw.player_x], released=True, original_source_preserved=True,
            one_emulator_native_prefix=True, native_load_state_count=1,
            final_fresh_red_gates=0, fit_allowed=False)
        _record(output/'RESULT.json', result)
    d.authenticate()
    print(json.dumps({k:v for k,v in result.items() if k not in {'episode'}}), flush=True)


def audit_prefix():
    """Verify retained eight-goal chain and costs without replaying anything."""
    d.authenticate()
    original = d.prior.doc(SOURCE/'CONTEXT.json')
    expected_state = SOURCE_SHA
    prior = original['spent']
    outcomes = []
    totals = dict(actions=0, frames=0, seconds=0., decisions=0, heals=0, cash_debits=0)
    for name in ('native-01', 'native-02'):
        node = ROOT/name
        result = d.prior.doc(node/'RESULT.json')
        context = d.prior.doc(node/'CONTEXT.json')
        episode = result['episode']
        meter = d.prior.doc(node/'native/native-costs.json')
        assert episode['support_decisions'] == 0
        assert episode['model_decisions'] == episode['strategic_policy_queries'] == meter['goal_attempts']
        for row in episode['outcomes']:
            assert row['before_state_sha256'] == expected_state
            assert row['verification'] == 'succeeded'
            expected_state = row['terminal_state_sha256']
            outcomes.append(row)
        assert expected_state == c.digest(node/'terminal.state') == context['state_sha256']
        assert c.digest(node/'CONTEXT.json') == result['context_sha256']
        spent = accumulate_player_costs(prior, decisions=meter['goal_attempts'],
            actions=meter['actions_attempted'], frames=meter['frames'], seconds=meter['seconds'],
            heals=meter['restore_attempts'],
            cash_deltas=tuple(o['before']['cash']-o['after']['cash'] for o in episode['outcomes']))
        assert spent == context['spent'] == result['spent']
        prior = spent
    totals = {key: prior[key]-original['spent'][key] for key in totals}
    battle = outcomes[6]['evidence']['battle']['episode']
    assert battle['battle_won'] and battle['decision_count'] == 5
    assert battle['memory_write_actions'] == battle['teacher_queries'] == battle['authority_promotions'] == 0
    assert not any(any(v for k, v in row['model_diagnostics'].items() if 'override' in k)
                   for row in battle['decisions'])
    logs = [verify_trainer_practice_event_log(path)
            for path in (ROOT/'native-02/battles').glob('*/events')]
    assert len(logs) == 1 and logs[0]['complete'] and not logs[0]['failed_runs']
    assert logs[0]['completed_decisions'] == 5
    assert outcomes[-1]['after']['cash']-original['cash'] == 770
    assert d.prior.doc(ROOT/'native-02/RESULT.json')['released']
    assert c.digest(SOURCE/'terminal.state') == SOURCE_SHA
    assert c.digest(SOURCE/'CONTEXT.json') == CONTEXT_SHA
    result = dict(passed=True, goals=len(outcomes), genuine_goals=8, strategic_queries=8,
        support_goals=0, learned_combat_choices=5, battle_wins=1, earned_cash=770,
        totals=totals, source_preserved=True, native_inputs=0, native_frames=0,
        terminal_sha256=expected_state, battle_event_logs=logs,
        interrupted_after_six_for_repair=True, uninterrupted_eight=False,
        fuchsia_complete=False, snorlax_captured=False, fitted_examples=0,
        fresh_red_acceptance=False, workers_actually_stopped=True)
    _record(ROOT/'PREFIX-AUDIT.json', result)
    print(json.dumps(result), flush=True)


def earned_probe(*, continuous=False, with_preparation=False, with_supply=False):
    """Inspect capture versus story/recovery at the actual earned terminal."""
    parent = ROOT/('native-06' if with_supply else 'native-05' if with_preparation else
                  'native-03' if continuous else 'native-02')
    output = ROOT/('optional-supply-probe-01' if with_supply else
                  'post-loss-preparation-probe-01' if with_preparation else
                  'continuous-travel-probe-01' if continuous else 'earned-capture-probe-01')
    if with_supply:
        output = ROOT / f'optional-supply-probe-{len(tuple(ROOT.glob("optional-supply-probe-*"))) + 1:02d}'
    output.mkdir(mode=0o700)
    _record(output/'PLAN.json', dict(partition='development', fit_allowed=False,
        source_sha256=c.digest(parent/'terminal.state'),
        context_sha256=c.digest(parent/'CONTEXT.json'), helper_sha256=c.digest(Path(__file__)),
        purpose=('zero-input full guarded gym journey, no destination override' if continuous else
                 'zero-input real Snorlax capture peer, no supplied phase winner'),
        native_inputs_permitted=False, master_ball_permitted=False,
        allocation='up to8actual ordinary balls;status preparation supplied',
        continuous_travel=continuous, include_preparation=with_preparation, include_supply=with_supply,
        purpose_detail='real optional post-loss member choices, not a supplied grind' if with_preparation else None))
    payload, factory, menu, holder, _ = assembly(parent, output, plan_path=output/'PLAN.json',
        continuous_travel=continuous, include_preparation=with_preparation, include_supply=with_supply)
    with c.PyBoyAdapter(c.ROM) as em:
        em.load_state_bytes(payload)
        rt = factory(ReadOnlyController(em))
        actions = CountingExecutor(FrameSafeExecutor(ReadOnlyController(em)))
        roles = tuple(m.specimen_ref for m in holder['plan'].roster if m.purpose.value == 'combat')
        options = observe_native_player_options(rt, actions, battle=holder['observe_history'](),
            combat_specimen_refs=roles, remaining_budget=(1.,)*5, target_cash=0,
            ordering_seed_sha256=c.canonical_sha256(dict(ordinal=0)), allow_support=True,
            model_feature_version=7, force_resource_safety=False, **menu.native_callbacks())
        assert isinstance(options, RedLiveOptionSet)
        parent_model, _ = d.prior.models()
        choice = select_red_live_option(parent_model, options, seed=202610060904,
                                       greedy_selection=True)
        assert em.frame_count == actions.actions_executed == 0
        assert em.save_state_bytes() == payload and not em.pressed_buttons
        kinds = [b.kind.value for b in options.bindings]
        assert GoalKind.ADVANCE_STORY.value in kinds
        if not continuous and not with_preparation:
            assert GoalKind.ACQUIRE_SPECIES.value in kinds
        assert any(b.story_objective_ref == ('reach_fuchsia' if with_supply else 'defeat_sabrina')
                   for b in options.bindings)
        result = dict(passed=True, menu=options.public_dict(), choice=choice.public_dict(),
            kinds=kinds, selected_kind=choice.selected_binding.kind.value,
            selected_objective=choice.selected_binding.story_objective_ref,
            actual_ball_stack=dict(rt.reader.read().bag_items).get(int(ItemId.POKE_BALL), 0),
            inputs=0, frames=0, source_preserved=True, fitted_examples=0,
            supplied_phase_order=False, master_ball_available_but_excluded=True)
        result['continuous_travel'] = continuous
        if with_preparation and not with_supply:
            assert GoalKind.DEVELOP_TEAM.value in kinds
            result['preparation_inventory'] = holder.get('preparation_inventory')
        if with_supply:
            assert GoalKind.RESUPPLY.value in kinds
            supplies = [b for b in options.bindings if b.kind is GoalKind.RESUPPLY]
            assert len(supplies) == 1 and supplies[0].resource_quote.purchase_cost == 4800
            result.update(include_supply=True, quoted_purchase_cost=4800,
                          supplied_quantity=8, learned_procurement=False)
        _record(output/'RESULT.json', result)
    d.authenticate()
    print(json.dumps({k:v for k,v in result.items() if k not in {'menu','choice'}}), flush=True)


def native(*, continuation=False, advance=False, segment=3, sampled=False, with_preparation=False,
           with_supply=False, with_rewards=False, maximum_goals=None):
    d.authenticate()
    assert d.prior.doc(ROOT/'probe-03/RESULT.json')['passed']
    assert c.digest(SOURCE/'terminal.state') == SOURCE_SHA
    assert c.digest(SOURCE/'CONTEXT.json') == CONTEXT_SHA
    assert not (continuation and advance)
    assert type(segment) is int and segment >= 3
    assert maximum_goals is None or (type(maximum_goals) is int and maximum_goals > 0)
    parent = (ROOT/f'native-{segment-1:02d}' if advance else
              ROOT/'native-01' if continuation else SOURCE)
    original = d.prior.doc(ROOT/'NATIVE-PLAN.json') if continuation else None
    previous = d.prior.doc(parent/'RESULT.json') if continuation else None
    used = previous['costs'] if continuation else None
    limits = (dict(decisions=8-used['goal_attempts'], actions=16000-used['actions_attempted'],
                   frames=1600000-used['frames'], seconds=int(600-used['seconds']),
                   heals=1000-used['restore_attempts']) if continuation else
              dict(decisions=8, actions=16000, frames=1600000, seconds=600, heals=1000))
    if advance:
        assert d.prior.doc(ROOT/'PREFIX-AUDIT.json')['passed']
        assert d.prior.doc(ROOT/'earned-capture-probe-01/RESULT.json')['passed']
        assert c.digest(ROOT/'executed-native-02.py') == d.prior.doc(
            ROOT/'NATIVE-PLAN-02.json')['helper_sha256']
        if segment > 3:
            previous_segment = d.prior.doc(parent/'RESULT.json')
            assert previous_segment['native_session_released'] and previous_segment['released']
            zero_input_preface_admission = segment in {24,25} and not previous_segment['passed']
            if zero_input_preface_admission:
                assert (previous_segment['error_type'],previous_segment['error']) == (
                    ('ValueError','existing blackout preface requires separate continuous DEVELOPMENT scope')
                    if segment == 24 else
                    ('GoalManagerRuntimeError','goal binding set needs at least two opportunities'))
                assert previous_segment['native_frames'] == 0
                assert previous_segment['state_sha256'] == d.prior.doc(ROOT/'native-22/RESULT.json')['state_sha256']
                assert all(previous_segment['spent'][k] == d.prior.doc(ROOT/'native-22/CONTEXT.json')['spent'][k]
                           for k in previous_segment['spent'] if k != 'seconds')
            elif segment in {28,29} and not previous_segment['passed']:
                assert (previous_segment['error_type'],previous_segment['error']) == ('RuntimeError','party escape transition budget')
                proof = d.prior.doc(ROOT/f'mansion-boundary-probe-{segment-24:02d}/RESULT.json')
                assert proof['passed'] and proof['inputs'] == proof['frames'] == 0
                assert proof['source_sha256'] == previous_segment['state_sha256']
                assert proof['battle_state'] == 1 and proof['battler_hp'] == 0
                assert proof['at'] == [20,19] and proof['map_id'] == 165 and proof['mansion_switch_on']
                assert not proof['field_ready'] and any(proof['party_hp'])
                assert d.prior.doc(parent/'CONTEXT.json')['lesson'] == d.prior.doc(ROOT/'native-26/CONTEXT.json')['lesson']
            elif segment == 41 and not previous_segment['passed']:
                assert previous_segment['checkpoint_recovered'] and previous_segment['actual_worker_stopped']
                assert previous_segment['original_worker_exit_code'] == 1
                assert previous_segment['checkpoint_recovery_inputs'] == previous_segment['checkpoint_recovery_frames'] == 0
                assert previous_segment['state_sha256'] == 'f94d13544633b3271cfcd67a3adb398b766b8e97f2b7ff7fdb16d328058f32f8'
            elif segment == 43:
                assert previous_segment['checkpoint_recovered'] and previous_segment['actual_worker_stopped']
                assert previous_segment['original_worker_exit_code'] == 1
                assert previous_segment['checkpoint_recovery_inputs'] == previous_segment['checkpoint_recovery_frames'] == 0
                assert previous_segment['state_sha256'] == 'dafaa8bd075706903e0dc81c4f4442d4abf470355f8ed89965a68f53ec113235'
                assert previous_segment['checkpoint_recovery_helper_sha256'] == c.digest(
                    Path(__file__).with_name('red_whole_player_checkpoint42_20261006.py'))
            elif segment == 44:
                proof = d.prior.doc(ROOT/'RETAINED-TRAINER-43-AUDIT.json')
                assert proof['passed'] and proof['actual_worker_stopped']
                assert proof['terminal_sha256'] == previous_segment['state_sha256']
                assert previous_segment['error_type'] == 'ValueError'
                assert previous_segment['error'] == 'native blackout/wild escape preface did not independently settle'
            elif segment == 49:
                paused_prefix_rows(parent)
            else:
                assert previous_segment['passed'] and previous_segment['error'] is None
            previous_rows = previous_segment.get('episode', {}).get('outcomes', [])
            if segment == 49:
                previous_rows, _ = paused_prefix_rows(parent)
            repair_proof = None
            if segment == 9 and previous_segment['episode']['stop_reason'] == 'execution_failed':
                repair_proof = d.prior.doc(ROOT/'CENSORED-RESTORATION-08-AUDIT.json')
                assert repair_proof['passed'] and repair_proof['failed_route_retained']
                assert repair_proof['state_sha256'] == previous_segment['state_sha256']
                assert repair_proof['context_sha256'] == previous_segment['context_sha256']
                last = previous_rows[-1]
                assert last['selected_kind'] == 'restore_team' and last['safe_terminal']
                assert last['error_type'] == 'RouteExecutionError'
                assert last['error_chain'][0]['reason_code'] == 'planner_no_route'
                assert last['verification'] is None and last['evidence'] is None
            if segment == 12 and previous_segment['episode']['stop_reason'] == 'execution_failed':
                repair_proof = d.prior.doc(ROOT/'CENSORED-DEADLINE-11-AUDIT.json')
                assert repair_proof['passed'] and repair_proof['unchanged_attempt']
                assert repair_proof['field_ready'] and repair_proof['verification_stays_null']
                assert repair_proof['state_sha256'] == previous_segment['state_sha256']
                assert repair_proof['context_sha256'] == previous_segment['context_sha256']
                last = previous_rows[-1]
                assert last['error_type'] == 'ControllerWallTimeBudgetExhausted'
                assert last['verification'] is None and last['evidence'] is None and last['safe_terminal']
                assert last['before_state_sha256'] == last['terminal_state_sha256']
            if segment == 22 and previous_segment['episode']['stop_reason'] == 'execution_failed':
                repair_proof = d.prior.doc(ROOT/'mansion-boundary-probe-02/RESULT.json')
                assert repair_proof['passed'] and repair_proof['inputs'] == repair_proof['frames'] == 0
                assert repair_proof['source_sha256'] == previous_segment['state_sha256']
                assert repair_proof['battle_state'] == 1 and not repair_proof['field_ready']
                assert repair_proof['map_id'] == int(c.MapId.POKEMON_MANSION_3F)
                assert repair_proof['at'] == [6,10] and not repair_proof['mansion_switch_on']
                assert any(p['hp'] > 0 for p in d.prior.doc(parent/'CONTEXT.json')['lesson']['party'])
                last = previous_rows[-1]
                assert last['error_type'] == 'BlaineChapterError' and not last['safe_terminal']
                assert last['verification'] is None and last['evidence'] is None
            if segment == 27 and previous_segment['episode']['stop_reason'] == 'execution_failed':
                repair_proof = d.prior.doc(ROOT/'mansion-boundary-probe-03/RESULT.json')
                assert repair_proof['passed'] and repair_proof['inputs'] == repair_proof['frames'] == 0
                assert repair_proof['source_sha256'] == previous_segment['state_sha256']
                assert repair_proof['battle_state'] == 1 and not repair_proof['field_ready']
                assert repair_proof['map_id'] == int(c.MapId.POKEMON_MANSION_1F)
                assert repair_proof['at'] == [20,19] and repair_proof['mansion_switch_on']
                party = d.prior.doc(parent/'CONTEXT.json')['lesson']['party']
                assert party[0]['hp'] == 0 and any(p['hp'] > 0 for p in party)
                last = previous_rows[-1]
                assert last['selected_kind'] == 'restore_team' and not last['safe_terminal']
                assert last['error_type'] == 'RouteExecutionError'
                assert last['error'] == 'Red observed ground transition flee lost its protected encounter boundary.'
                assert last['verification'] is None and last['evidence'] is None
            if segment == 34 and previous_segment['episode']['stop_reason'] == 'execution_failed':
                repair_proof = d.prior.doc(ROOT/'current-menu-probe-06/RESULT.json')
                geometry = d.prior.doc(ROOT/'mansion-probe-07/RESULT.json')
                assert repair_proof['passed'] and repair_proof['inputs'] == repair_proof['frames'] == 0
                assert repair_proof['source_sha256'] == geometry['source_sha256'] == previous_segment['state_sha256']
                assert geometry['passed'] and geometry['inputs'] == geometry['frames'] == 0
                assert geometry['map_id'] == 165 and geometry['at'] == [18,20]
                assert not geometry['mansion_switch_on'] and dict(geometry['bag']).get(43) == 1
                last = previous_rows[-1]
                assert last['error_type'] == 'RouteExecutionError' and last['safe_terminal']
                assert last['error_chain'][0]['reason_code'] == 'planner_no_route'
                assert last['selected_kind'] == 'advance_story' and last['verification'] is None and last['evidence'] is None
            if segment == 35 and previous_segment['episode']['stop_reason'] == 'execution_failed':
                repair_proof = d.prior.doc(ROOT/'current-menu-probe-07/RESULT.json')
                boundary = d.prior.doc(ROOT/'mansion-boundary-probe-07/RESULT.json')
                assert repair_proof['passed'] and repair_proof['inputs'] == repair_proof['frames'] == 0
                assert boundary['passed'] and boundary['inputs'] == boundary['frames'] == 0
                assert repair_proof['source_sha256'] == boundary['source_sha256'] == previous_segment['state_sha256']
                assert boundary['field_ready'] and not boundary['bottom_dialogue']
                assert boundary['map_id'] == 171 and boundary['at'] == [3,3] and boundary['facing'] == 'left'
                assert 'restore_team' in repair_proof['kinds']
                last = previous_rows[-1]
                assert last['selected_kind'] == 'restore_team' and last['safe_terminal']
                assert last['error_type'] == 'RedGoalSkillError' and last['error'] == 'Center recovery did not restore the party'
                assert last['verification'] is None and last['evidence'] is None
                assert last['before']['player_lesson'] == last['after']['player_lesson']
                assert last['before']['cash'] == last['after']['cash'] == boundary['cash']
                assert boundary['party_hp'] == [p['hp'] for p in d.prior.doc(parent/'CONTEXT.json')['lesson']['party']]
            if segment == 38 and previous_segment['episode']['stop_reason'] == 'execution_failed':
                repair_proof = d.prior.doc(ROOT/'mansion-boundary-probe-09/RESULT.json')
                quote = d.prior.doc(ROOT/'mansion-boundary-probe-10/RESULT.json')
                assert quote['passed'] and quote['inputs'] == quote['frames'] == 0
                assert quote['source_sha256'] == previous_segment['state_sha256']
                assert quote['native_motion_binding_ref'] == 'pokemon.red:retained-motion:'+previous_segment['state_sha256']
                assert repair_proof['passed'] and repair_proof['inputs'] == repair_proof['frames'] == 0
                assert repair_proof['source_sha256'] == previous_segment['state_sha256']
                assert not repair_proof['field_ready'] and not repair_proof['bottom_dialogue']
                assert repair_proof['map_id'] == 45 and repair_proof['at'] == [3,19]
                assert repair_proof['readiness']['joy_ignore'] == 255 and repair_proof['readiness']['simulated_joypad_index'] == 1
                last = previous_rows[-1]
                assert last['error_type'] == 'RouteExecutionError' and last['error'] == 'forced motion did not settle at its endpoint'
                assert last['verification'] is None and last['evidence'] is None
                assert last['before']['player_lesson'] == last['after']['player_lesson']
                assert last['before']['cash'] == last['after']['cash'] == repair_proof['cash']
            if segment == 41 and previous_segment['episode']['stop_reason'] == 'execution_failed':
                repair_proof = d.prior.doc(ROOT/'mansion-boundary-probe-11/RESULT.json')
                assert repair_proof['passed'] and repair_proof['inputs'] == repair_proof['frames'] == 0
                assert repair_proof['source_sha256'] == previous_segment['state_sha256']
                assert repair_proof['battle_state'] == 1 and repair_proof['map_id'] == 22
                assert repair_proof['at'] == [8,18] and not repair_proof['field_ready']
                last = previous_rows[-1]
                assert last['selected_kind'] == 'develop_team' and not last['safe_terminal']
                assert last['error_type'] == 'ControllerWallTimeBudgetExhausted'
                assert last['verification'] is None and last['evidence'] is None
                censored = previous_segment['censored_battle_checkpoint']
                assert censored['terminal_state_sha256'] == previous_segment['state_sha256']
                assert censored['outcome'] is None and censored['fresh_inference'] is False
            if segment == 43:
                repair_proof = previous_segment
                last = previous_rows[-1]
                assert last['error_type'] == 'BattleRuntimeError' and last['verification'] is None
                assert last['selected_kind'] == 'advance_story' and not last['safe_terminal']
                assert previous_segment['censored_battle_checkpoint']['outcome'] is None
                assert previous_segment['retained_trainer_identity'] == [242,42,11]
            if segment == 47 and previous_segment['episode']['stop_reason']=='execution_failed':
                repair_proof=d.prior.doc(ROOT/'mansion-boundary-probe-12/RESULT.json')
                assert repair_proof['passed'] and repair_proof['inputs']==repair_proof['frames']==0
                assert repair_proof['source_sha256']==previous_segment['state_sha256']
                assert not repair_proof['field_ready'] and not repair_proof['bottom_dialogue']
                assert repair_proof['map_id']==17 and repair_proof['at']==[27,9]
                assert repair_proof['readiness']['player_moving_direction']==4
                assert repair_proof['readiness']['walk_counter']==1
                last=previous_rows[-1]
                assert last['selected_kind']=='develop_team' and last['error_type']=='RouteExecutionError'
                assert last['verification'] is None and last['evidence'] is None
                assert last['after']['player_lesson']==d.prior.doc(parent/'CONTEXT.json')['lesson']
            if segment == 48 and previous_segment['episode']['stop_reason']=='execution_failed':
                repair_proof=d.prior.doc(ROOT/'mansion-boundary-probe-14/RESULT.json')
                assert repair_proof['passed'] and repair_proof['inputs']==repair_proof['frames']==0
                assert repair_proof['source_sha256']==previous_segment['state_sha256']
                assert not repair_proof['field_ready'] and repair_proof['bottom_dialogue']
                assert repair_proof['map_id']==1 and repair_proof['at']==[11,18]
                assert previous_rows[-1]['error']=="Gen I route cannot dismiss 'scripted_dialogue'"
                assert previous_rows[-1]['verification'] is None and previous_rows[-1]['evidence'] is None
            assert all(o['verification'] == 'succeeded' or (o['ordinary_setback'] and o['safe_terminal'])
                       or (segment == 31 and index == len(previous_rows)-1
                           and previous_rows[index]['error_type'] == 'RouteExecutionError'
                           and previous_rows[index]['error'] == 'Red observed ground transition: escape party resources changed'
                           and previous_rows[index]['verification'] is None and not previous_rows[index]['safe_terminal']
                           and d.prior.doc(ROOT/'mansion-boundary-probe-06/RESULT.json')['source_sha256'] == previous_segment['state_sha256']
                           and d.prior.doc(ROOT/'mansion-boundary-probe-06/RESULT.json')['battle_state'] == 1)
                       or (repair_proof is not None and index == len(previous_rows)-1)
                       for index, o in enumerate(previous_rows))
            assert d.prior.doc(ROOT/'continuous-travel-probe-01/RESULT.json')['passed']
        baseline = d.prior.doc(SOURCE/'CONTEXT.json')['spent']
        carried = carried_spent(parent,d.prior.doc(parent/'CONTEXT.json'))
        used = {key: carried[key]-baseline[key] for key in baseline}
        # Standing completion goal authorizes the next outcome block. Prior
        # sealed declarations retain their original21:11 cutoff and all costs.
        resumed = segment >= 49
        cutoff = datetime(2026, 10, 7, 2, 58, 53, tzinfo=UTC) if resumed else datetime(2026, 10, 7, 0, 10, tzinfo=UTC)
        wall_remaining = (cutoff-datetime.now(UTC)).total_seconds()
        goal_allowance = 400 if resumed else 320 if with_rewards else 96 if with_supply else 48 if with_preparation else 32
        action_allowance = 80000 if resumed else 60000
        frame_allowance = 6500000 if resumed else 5000000
        # Longer mechanical/member doses must not be cut merely by the old
        # 15-minute observation chunk. Extend prospectively, never refund a
        # retained timeout or alter its declaration. Input/frame and the same
        # overall outcome-block deadline remain hard admission limits.
        native_allowance = 12500 if resumed else 9000 if with_rewards else 1800
        if with_preparation:
            assert d.prior.doc(ROOT/'post-loss-preparation-probe-01/RESULT.json')['passed']
        if with_supply:
            assert d.prior.doc(ROOT/'optional-supply-probe-02/RESULT.json')['passed']
        if with_rewards and segment >= 15:
            assert d.prior.doc(ROOT/'cinnabar-probe-01/RESULT.json')['passed']
        limits = dict(decisions=min(24 if with_rewards else 8, goal_allowance-used['decisions']),
            actions=min(20000, action_allowance-used['actions']), frames=min(2000000, frame_allowance-used['frames']),
            seconds=int(min(1800 if with_rewards else 900, native_allowance-used['seconds'], wall_remaining)),
            heals=1000-used['heals'])
        assert all(v > 0 for k, v in limits.items() if k != 'heals')
    if maximum_goals is not None:
        limits['decisions'] = min(limits['decisions'],maximum_goals)
    if continuation:
        assert previous['actual_worker_stopped'] and previous['prefix_verified']
        assert all(v > 0 for k,v in limits.items() if k != 'heals')
    wild_bridge = advance and segment in {24,25,27,28,29,31,41}
    motion_bridge = advance and segment == 38
    trainer_bridge = advance and segment == 43
    control_bridge = wild_bridge or motion_bridge or trainer_bridge
    if control_bridge:
        limits['decisions'] = min(2, limits['decisions'])
    declared = ROOT/(f'NATIVE-PLAN-{segment:02d}.json' if advance else
                    'NATIVE-PLAN-02.json' if continuation else 'NATIVE-PLAN.json')
    # Retain the exact executed helper prospectively, before any native input.
    # Exclusive writes reject duplicate dispatch; earlier sealed copies stay intact.
    _write(ROOT/f'executed-native-{segment:02d}.py',Path(__file__).read_bytes())
    _record(declared, dict(partition='development', fit_allowed=False, independent=False,
        purpose=('ordinary real-option continuation with earned HM/Surf prerequisites'
                 if with_rewards else 'one bounded existing stochastic-policy continuation after retained greedy loop'
                 if sampled else 'one-emulator model-selected native branch prefix, no phase order or reload'),
        declared_at=datetime.now(UTC).isoformat(), source_sha256=c.digest(parent/'terminal.state'),
        context_sha256=c.digest(parent/'CONTEXT.json'), helper_sha256=c.digest(Path(__file__)),
        source_code_sha256=c.source_code_identity(c.REPO), source_edits=0,
        limits=limits, prior_native_costs=used, prior_plan_sha256=(
            c.digest(ROOT/f'NATIVE-PLAN-{segment-1:02d}.json') if advance else
            None if original is None else c.digest(ROOT/'NATIVE-PLAN.json')),
        actual_continuation=continuation or advance,
        chunk_goal_allowance=24 if with_rewards else 8,
        requested_maximum_goals=maximum_goals,
        no_old_budget_reset=True, previous_probe_failures_retained=2,
        scoped_battle_component='29792a3292e8d5c103e39d5914d8b1c9388c65af107c989141331e14503712ad',
        parent_sha256=d.prior.PARENT_SHA, child_sha256=d.prior.HEAD_SHA,
        support='native navigation/status/capture allocation;zero supplied strategic phase or tactical override',
        continuous_travel=advance,
        greedy_selection=not sampled, weights_changed=False,
        include_optional_post_loss_preparation=with_preparation,
        include_optional_ball_purchase=with_supply, supplied_ball_purchase_quantity=8 if with_supply else None,
        include_safari_rewards=with_rewards, hm_recipient_and_move_selection_learned=False,
        include_native_surf_transport=with_rewards,
        include_current_frontier_league=with_rewards,
        include_existing_early_story_callbacks=with_rewards,
        include_shared_collection_peers=with_rewards,
        include_existing_collection_capability_bindings=with_rewards,
        approved_temporary_league_medicine_safeguard=with_rewards,
        preparation_venue_support='highest reachable decoded band from six existing grass routes;local native nurse',
        include_completed_key_storage=with_rewards,
        include_interrupted_wild_settlement=with_rewards,
        include_ordinary_route_native_faint_recovery=with_rewards,
        include_ordinary_route_native_status_costs=with_rewards,
        include_bounded_native_poison_faint_dialogue=with_rewards,
        field_faint_dialogue_authority='mechanical settlement only;no relocation,healing or goal choice',
        ordinary_escape_forced_replacement_authority='mechanical first living member;not learned' if with_rewards else None,
        mechanical_wild_bridge_only=wild_bridge,
        mechanical_motion_bridge_only=motion_bridge,
        mechanical_retained_trainer_bridge_only=trainer_bridge,
        consequence_head_temporarily_unused_for_no_choice_bridge=control_bridge,
        trainer_aware_restoration_quote=True,
        retained_restoration_error_repair_restart=advance and segment==9,
        retained_unchanged_deadline_restart=advance and segment==12,
        retained_sideways_nurse_restart=advance and segment==35,
        retained_pending_wild_statue_restart=advance and segment==22,
        previous_greedy_no_objective_progress_retained=sampled,
        ordinary_continuation_authorized=True, fresh_acceptance=False))
    if advance:
        _record(ROOT/f'CONTINUATION-ALLOWANCE-{segment:02d}.json', dict(
            earlier_eight_goal_prefix_closed=True, original_outcomes_unchanged=True,
            original_remaining_costs_carried=used, current_segment_limits=limits,
            aggregate_whole_player_limits=dict(decisions=goal_allowance, actions=action_allowance,
                frames=frame_allowance, seconds=native_allowance, cutoff=cutoff.isoformat()),
            prior_outcome_block_cutoff_unchanged='2026-10-06T21:11:00Z',
            current_outcome_block=('23:58:53-02:58:53UTC:authenticated continuation,existing shared callbacks'
                if resumed else '21:10-00:10UTC:earned Mansion return,Blaine,next existing story capability'),
            actual_parent=parent.name, no_replay_or_reset=True,
            purpose='follow the genuine next choice, Sabrina/capture/recovery are peers',
            captured_species_policy='ordinary balls only;Master excluded;status support disclosed',
            goal_allowance_prospectively_extended=with_preparation,
            original_32_goal_results_closed_unchanged=True,
            original_48_goal_results_closed_unchanged=with_supply,
            admin_goal_count_extended_not_native_time=with_supply and not with_rewards,
            prospective_native_allowance_extended=with_rewards,
        original_1800_second_receipts_unchanged=with_rewards,
            original_5400_second_receipts_unchanged=with_rewards,
            prospective_chunk_seconds=1800 if with_rewards else 900,
        ))
    output = ROOT/(f'native-{segment:02d}' if advance else 'native-02' if continuation else 'native-01')
    output.mkdir(mode=0o700)
    payload, factory, menu, holder, source = assembly(parent, output, plan_path=declared,
        continuous_travel=advance, include_preparation=with_preparation, include_supply=with_supply,
        include_rewards=with_rewards)
    result = dict(passed=False, error=None, source=source, original_source_sha256=SOURCE_SHA,
                  one_emulator=True, load_state_count=1, fit_allowed=False)
    with c.PyBoyAdapter(c.ROM) as em:
        em.load_state_bytes(payload)
        factory(ReadOnlyController(em))
        roles = tuple(m.specimen_ref for m in holder['plan'].roster if m.purpose.value == 'combat')
        model, head = d.prior.models()
        if control_bridge:
            bridge_rom = c.ROM.read_bytes()
            def bridge_base(rt, actions, observation):
                escape = (holder['retained_trainer_binding'](rt,actions) if trainer_bridge else
                          interrupted_motion_binding(rt,actions,rom=bridge_rom)
                          if motion_bridge else interrupted_wild_binding(rt, actions, allow_fainted_active=True))
                return control_inventory(escape)
            menu = NativeStoryBranchInventory(bridge_base, lambda *args: ())
        store = c.open_private_root(c.BASE/'goal-manager-v1', repository_root=c.REPO,
                                    allow_same_device=True)
        try:
            result['episode'] = run_native_continuous_player(store=store, emulator=em,
                runtime_factory=factory, source=source, output=output/'native', model=model,
                seed=202610060901+segment if advance else 202610060903 if continuation else 202610060902,
                run_id=ROOT.name, arm_id=output.name,
                limits=NativePlayerLimits(**limits, cash_debits=None),
                combat_specimen_refs=roles, battle_observer=holder['observe_history'],
                target_cash=0, greedy_selection=not sampled,
                allow_greedy_branch_recovery=not sampled,
                consequence_head=None if control_bridge else head,
                consequence_objective_ref=None if control_bridge else 'defeat_sabrina',
                consequence_challenge_ref=None if control_bridge else 'current-native-sabrina',
                force_resource_safety=False, include_live_pp_readiness=True,
                settle_existing_wild=wild_bridge,
                settle_existing_motion=motion_bridge,
                settle_existing_trainer=trainer_bridge,
                **menu.native_callbacks())
            result['passed'] = True
        except Exception as error:
            result.update(error_type=type(error).__name__, error=str(error))
        finally:
            _write(output/'terminal.state', em.save_state_bytes())
            costs = output/'native/native-costs.json'
            if costs.exists():
                metered = d.prior.doc(costs)
                outcomes = result.get('episode', {}).get('outcomes', [])
                spent = accumulate_player_costs(holder['prior_spent'],
                    decisions=metered['goal_attempts'], actions=metered['actions_attempted'],
                    frames=metered['frames'], seconds=metered['seconds'],
                    heals=metered['restore_attempts'],
                    cash_deltas=tuple(o['before']['cash'] - o['after']['cash'] for o in outcomes)
                    + (metered.get('control_recovery_cash_debits',0),))
            else:
                spent = holder['prior_spent']
            last_error = result.get('episode',{}).get('outcomes',[])
            checkpoint_error = last_error[-1]['error_type'] if last_error else None
            if checkpoint_error not in {'ControllerWallTimeBudgetExhausted',
                                        'ControllerFrameBudgetExhausted','ControllerActionBudgetExhausted',
                                        'BattleRuntimeError','BattleRuntimeTimeoutError'}:
                checkpoint_error = None
            observed_history = holder['observe_history'](checkpoint_error_type=checkpoint_error)
            context = capture_player_continuation(holder['runtime'], preparation=holder['plan'],
                battle=observed_history, spent=spent)
            if holder.get('censored_battle_checkpoint') is not None:
                result['censored_battle_checkpoint'] = holder['censored_battle_checkpoint']
            _record(output/'CONTEXT.json', context)
            raw = holder['runtime'].reader.read()
            result.update(state_sha256=c.digest(output/'terminal.state'),
                context_sha256=c.digest(output/'CONTEXT.json'), spent=spent,
                cash=raw.player_money, map_id=raw.map_id, at=[raw.player_y, raw.player_x],
                released=not em.pressed_buttons, native_frames=em.frame_count,
                missing_native_capabilities=holder.get('missing_native_capabilities'),
                native_session_released=True, original_source_preserved=c.digest(
                    SOURCE/'terminal.state') == SOURCE_SHA)
            _record(output/'RESULT.json', result)
    d.authenticate()
    print(json.dumps({k:v for k,v in result.items() if k not in {'source','episode'}}), flush=True)


if __name__ == '__main__':
    if sys.argv[1:] == ['--native']:
        native()
    elif sys.argv[1:] == ['--finalize']:
        finalize()
    elif sys.argv[1:] == ['--continue']:
        native(continuation=True)
    elif sys.argv[1:] == ['--audit-prefix']:
        audit_prefix()
    elif sys.argv[1:] == ['--earned-probe']:
        earned_probe()
    elif sys.argv[1:] == ['--advance']:
        native(advance=True)
    elif sys.argv[1:] == ['--travel-probe']:
        earned_probe(continuous=True)
    elif sys.argv[1:] == ['--next']:
        latest = max(int(p.name.removeprefix('native-')) for p in ROOT.glob('native-*') if p.is_dir())
        native(advance=True, segment=latest+1)
    elif sys.argv[1:] == ['--sample-next']:
        latest = max(int(p.name.removeprefix('native-')) for p in ROOT.glob('native-*') if p.is_dir())
        native(advance=True, segment=latest+1, sampled=True)
    elif sys.argv[1:] == ['--preparation-probe']:
        earned_probe(continuous=True, with_preparation=True)
    elif sys.argv[1:] == ['--prepared-next']:
        latest = max(int(p.name.removeprefix('native-')) for p in ROOT.glob('native-*') if p.is_dir())
        native(advance=True, segment=latest+1, sampled=True, with_preparation=True)
    elif sys.argv[1:] == ['--supply-probe']:
        earned_probe(continuous=True, with_preparation=True, with_supply=True)
    elif sys.argv[1:] == ['--resource-next']:
        latest = max(int(p.name.removeprefix('native-')) for p in ROOT.glob('native-*') if p.is_dir())
        native(advance=True, segment=latest+1, sampled=True, with_preparation=True, with_supply=True)
    elif sys.argv[1:] == ['--rewards-next']:
        latest = max(int(p.name.removeprefix('native-')) for p in ROOT.glob('native-*') if p.is_dir())
        native(advance=True, segment=latest+1, sampled=True, with_preparation=True,
               with_supply=True, with_rewards=True)
    elif sys.argv[1:] == ['--cinnabar-probe']:
        cinnabar_probe()
    elif sys.argv[1:] == ['--current-menu-probe']:
        current_menu_probe()
    else:
        probe()
