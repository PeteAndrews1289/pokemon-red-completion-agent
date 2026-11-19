"""Connect existing hidden-item and Dojo executors to the current mixed player.

No old admission/session dispatcher, selected target order, resource injection,
teacher combat or fitting. Each offer is read-only and binds one native source.
"""

from dataclasses import replace
from functools import partial
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace as N

from pokemon_red_completion.gen1_route_runtime import Gen1TraversalObserver
from pokemon_red_completion.goal_manager import GoalDecisionOutcome,GoalFailureReason,GoalKind
from pokemon_red_completion.goal_manager_runtime import ExecutableGoalBinding,GoalExecutionReport,GoalVerification
from pokemon_red_completion.observation import EventFlag,MapId,event_flag_is_set
from pokemon_red_completion.red_player_field_goals import _field_ready
from pokemon_red_completion.route_plan import RoutePlanningError
from red_mixed_static_options_20261009 import NoncombatStaticTransport


def output_directory(runtime):
    actor = getattr(runtime.trainer_battle_runner,'__self__',None)
    return None if actor is None or not hasattr(actor,'output') else Path(actor.output).parent


def native_goal_binding(runtime,actions,kind,label,execute_native,verify_native,
                        *,estimated_effort=.3,estimated_risk=.1,maximum_cash_debit=0,
                        retain_trainer_recovery=False):
    """Use the existing goal protocol with exact source/terminal conservation."""
    source = runtime.emulator.save_state_bytes()
    counters = actions.actions_executed,runtime.emulator.frame_count
    observation = runtime.adapter.observe()
    if retain_trainer_recovery and (kind is not GoalKind.ACQUIRE_SPECIES or label!='dojo-gift'):
        raise ValueError('native trainer recovery scope differs')
    used,result,terminal,recovery = False,None,None,None
    def execute():
        nonlocal used,result,terminal,recovery
        if (used or runtime.emulator.save_state_bytes()!=source
                or runtime.adapter.observe()!=observation
                or counters!=(actions.actions_executed,runtime.emulator.frame_count)):
            raise ValueError('selected postgame delivery is stale or consumed')
        used = True
        from pokemon_red_completion.red_player_engaged_story import SettledNativeTrainerRecovery
        from pokemon_red_completion.red_integrated_play import native_delivery_trainer_recovery_evidence
        try:
            evidence = execute_native()
        except SettledNativeTrainerRecovery as stop:
            if not retain_trainer_recovery:
                raise
            raw = runtime.reader.read()
            evidence = dict(schema='pokemon.red.native-delivery-recovery.v1',
                delivery=label,selected_kind=kind.value,source_sha256=sha256(source).hexdigest(),
                source_cash=observation.raw.player_money,
                terminal_sha256=sha256(runtime.emulator.save_state_bytes()).hexdigest(),
                native_trainer_recovery=dict(stop.evidence),objective_completed=False,reward=None)
            if (not _field_ready(runtime) or not native_delivery_trainer_recovery_evidence(
                evidence,kind=kind,source_sha256=sha256(source).hexdigest(),
                terminal_sha256=sha256(runtime.emulator.save_state_bytes()).hexdigest(),
                cash=raw.player_money,party_hp=raw.party_hp,
                actions=actions.actions_executed-counters[0],
                frames=runtime.emulator.frame_count-counters[1])):
                raise
            recovery = stop
        result = GoalExecutionReport(actions.actions_executed-counters[0],
            runtime.emulator.frame_count-counters[1],evidence)
        terminal = runtime.emulator.save_state_bytes()
        return result
    def verify(report):
        if recovery is not None:
            from pokemon_red_completion.red_integrated_play import native_delivery_trainer_recovery_evidence
            raw = runtime.reader.read()
            passed = (used and report is result and terminal is not None
                and runtime.emulator.save_state_bytes()==terminal and _field_ready(runtime)
                and native_delivery_trainer_recovery_evidence(report.evidence,kind=kind,
                    source_sha256=sha256(source).hexdigest(),terminal_sha256=sha256(terminal).hexdigest(),
                    cash=raw.player_money,party_hp=raw.party_hp,
                    actions=report.actions_executed,frames=report.frames_executed))
            return GoalVerification.failed(GoalFailureReason.RECOVERY_REQUIRED if passed
                else GoalFailureReason.OUTCOME_NOT_VERIFIED)
        passed = (used and report is result and terminal is not None
            and runtime.emulator.save_state_bytes()==terminal and _field_ready(runtime)
            and verify_native() is True)
        return GoalVerification.succeeded() if passed else GoalVerification.failed(
            GoalFailureReason.OUTCOME_NOT_VERIFIED)
    return ExecutableGoalBinding('red-native-delivery:'+label+':'+sha256(source).hexdigest(),
        kind,estimated_effort,estimated_risk,execute,verify,maximum_cash_debit=maximum_cash_debit)


def quoted_native_arrival(runtime,world,*,town,map_id,at):
    """Quote supported departure/arrival; remote outdoor travel retains Fly scope."""
    import red_current_source_preparation_20261004 as prep
    from pokemon_red_completion.red_collection_fly import red_fly_landings
    from pokemon_red_completion.red_resource_goal_router import _supported_plan
    start = Gen1TraversalObserver(runtime.reader,
        capability_projector=partial(prep.source_field_capabilities,runtime.emulator)).observe()
    if not start.ready or start.interruption is not None or start.mode != 'land':
        return None
    if town not in runtime.reader.read_fly_destinations():
        return None
    raw = runtime.reader.read()
    world = world.with_current_observation(runtime.reader)
    if start.map_id != map_id:
        cave_transit = prep.same_cave_transit(start.map_id,map_id)
        if start.map_id >= 0x25 and not cave_transit:
            # A party Fly move does not establish that this indoor source can
            # reach a usable outdoor boundary. Use the executor's same preview.
            departure = prep.source_departure(start,world,raw)
            if departure is None:
                return None
            start = replace(start,map_id=departure.terminal_map,at=departure.terminal_at,
                mode=departure.terminal_mode or start.mode,
                last_outside_map=departure.terminal_map,occupied=frozenset(),hazards=())
        if start.map_id != town and not cave_transit:
            if not prep.native_fly_usable(raw):
                return None
            start = replace(start,map_id=town,at=dict(red_fly_landings(world.rom))[town],
                last_outside_map=town,occupied=frozenset(),hazards=())
    try:
        plan = world.plan_feasible_to_map(start,map_id,goal_at=at)
    except RoutePlanningError:
        return None
    return (plan if plan.terminal_mode in (None,'land') and len(plan.steps)<=1500
            and _supported_plan(plan,allow_cut=True,allow_surf=True,
                                seafoam_state=raw) else None)


def hidden_moon_peer(runtime,actions,world):
    from pokemon_red_completion.red_collection import red_species_ref
    from red_hidden_stone_20261004 import hidden_stones,obtained,collect_hidden_stone
    import red_current_source_preparation_20261004 as prep
    from red_pc_registration_20261004 import stock_signature
    raw = runtime.reader.read()
    registered = runtime.registration_policy.goal_registered(runtime.adapter.observe().collection_observation)
    if (raw.badge_bits != 255 or not _field_ready(runtime) or raw.bag_items is None
            or dict(raw.bag_items).get(10,0) or len(raw.bag_items)>=20
            or not any(red_species_ref(n) not in registered for n in (31,34,36,40))):
        return None
    choices=[]
    for target in hidden_stones(world.rom):
        if obtained(runtime.reader,target):
            continue
        town = 8 if target.map_id == 165 else 2
        y,x=target.at
        for at in ((y+1,x),(y,x-1),(y,x+1),(y-1,x)):
            if min(at)<0:
                continue
            plan=quoted_native_arrival(runtime,world,town=town,map_id=target.map_id,at=at)
            if plan is not None:
                choices.append((plan.cost,target.map_id,at,target,town))
    if not choices:
        return None
    _,_,at,target,town=min(choices,key=lambda row:row[:3])
    stock=stock_signature(runtime)
    expected=dict(raw.bag_items);expected[10]=1
    def execute():
        prep.route_to(N(rt=runtime,em=runtime.emulator,actions=actions),world,
            town=town,map_id=target.map_id,at=at,route_handler_wrapper=NoncombatStaticTransport)
        collect_hidden_stone(actions,runtime.reader,runtime.emulator,world.rom,target)
        runtime.adapter.party_guard.verify_active_roster_restored()
        if (runtime.reader.read().player_money!=raw.player_money
                or dict(runtime.reader.read().bag_items or ())!=expected
                or not prep.preparation_stock_preserved(stock,stock_signature(runtime))):
            raise ValueError('hidden stone delivery changed protected resources or stock')
        return dict(native_hidden_moon_stone=True,native_hidden_flag=target.flag_index,
            native_map=target.map_id,item_added=1,transport_and_pickup_learned=False)
    return native_goal_binding(runtime,actions,GoalKind.RESUPPLY,'hidden-moon',execute,
        lambda:obtained(runtime.reader,target) and dict(runtime.reader.read().bag_items or ())==expected
            and runtime.reader.read().player_money==raw.player_money
            and prep.preparation_stock_preserved(stock,stock_signature(runtime)))


def learned_collection_transport(runtime,actions,world):
    """Only exact K engagements replace transport's forbidden teacher fallback."""
    from pokemon_red_completion.red_player_engaged_story import EngagedStoryRouteHandler
    from red_whole_player_inventory_20261006 import retained_early_trainer_binding
    actor=getattr(runtime.trainer_battle_runner,'__self__',None)
    return lambda inner:EngagedStoryRouteHandler(NoncombatStaticTransport(inner),runtime.reader,
        lambda:retained_early_trainer_binding(runtime,actions,rom=world.rom,battler=actor))


def routed_dojo_gift_bindings(runtime,observation,actions,world):
    from red_dojo_gift_20261004 import dojo_gift,local_dojo_gift_bindings
    from pokemon_red_completion.red_learned_trainer import FROZEN_K_SHA256,K_QUALIFICATION_SHA256
    from pokemon_red_completion.red_pc_storage import face_pc_boundary
    from pokemon_red_completion.actions import MacroActionKind
    from pokemon_red_completion.surge import _pulse
    from red_whole_player_inventory_20261006 import retained_early_trainer_binding
    import red_current_source_preparation_20261004 as prep
    raw=observation.raw
    actor=getattr(runtime.trainer_battle_runner,'__self__',None)
    if (not runtime.scripted_gifts or raw.badge_bits!=255 or not _field_ready(runtime)
            or observation.immediate_capture_slots<1 or actor is None
            or getattr(actor,'model_sha256',None)!=FROZEN_K_SHA256
            or getattr(actor,'qualification_sha256',None)!=K_QUALIFICATION_SHA256
            or raw.event_flags is None or 106 in runtime.reader.read_pokedex_state().owned_species
            or any(event_flag_is_set(raw.event_flags,int(e)) for e in
                (EventFlag.GOT_HITMONLEE,EventFlag.GOT_HITMONCHAN,EventFlag.DEFEATED_FIGHTING_DOJO))):
        return ()
    gift=dojo_gift(world.rom)
    if local_dojo_gift_bindings(runtime,observation,actions,world):
        return ()  # Existing exact local gift remains the sole executor.
    at=(2,4) if event_flag_is_set(raw.event_flags,EventFlag.BEAT_KARATE_MASTER) else (3,4)
    if quoted_native_arrival(runtime,world,town=10,map_id=gift.map_id,at=at) is None:
        return ()
    source_owned=runtime.reader.read_pokedex_state().owned_species
    wrapper=learned_collection_transport(runtime,actions,world)
    def execute():
        session=N(rt=runtime,em=runtime.emulator,actions=actions)
        routes=prep.route_to(session,world,town=10,map_id=gift.map_id,at=at,
                             route_handler_wrapper=wrapper)
        master=None
        if not event_flag_is_set(runtime.reader.read().event_flags,EventFlag.BEAT_KARATE_MASTER):
            objects=[o for o in runtime.reader.read_current_map_objects() if o.sprite_index==1]
            if len(objects)!=1 or not objects[0].visible or objects[0].at!=(3,5):
                raise ValueError('actual Dojo Master object differs')
            face_pc_boundary(actions,runtime.reader,'right')
            _pulse(actions,MacroActionKind.INTERACT,frames=120)
            for _ in range(32):
                if runtime.reader.read().battle_state==2:
                    break
                _pulse(actions,MacroActionKind.CONFIRM,frames=144)
            else:
                raise RuntimeError('native Dojo Master introduction did not engage')
            binding=retained_early_trainer_binding(runtime,actions,rom=world.rom,battler=actor)
            if binding is None:
                raise ValueError('actual Dojo Master lacks an exact K contract')
            master=binding.execute()
            if binding.verify(master).status is not GoalDecisionOutcome.SUCCEEDED:
                raise RuntimeError('native Dojo Master loss retained, not retried')
        routes+=prep.route_to(session,world,town=10,map_id=gift.map_id,at=(2,4),
                              route_handler_wrapper=wrapper)
        offers=local_dojo_gift_bindings(runtime,runtime.adapter.observe(),actions,world)
        if len(offers)!=1:
            raise RuntimeError('selected Dojo gift did not requalify from actual arrival')
        report=offers[0].execute()
        if offers[0].verify(report).status is not GoalDecisionOutcome.SUCCEEDED:
            raise RuntimeError('native Dojo gift failed independent verification')
        runtime.adapter.party_guard.verify_active_roster_restored()
        return dict(native_dojo_gift=dict(report.evidence),routes=routes,
                    master=None if master is None else dict(master.evidence),
                    prerequisite_combat='frozen K',navigation_and_gift_learned=False)
    return (native_goal_binding(runtime,actions,GoalKind.ACQUIRE_SPECIES,'dojo-gift',execute,
        lambda:runtime.reader.read_pokedex_state().owned_species==source_owned|{106}
            and event_flag_is_set(runtime.reader.read().event_flags,EventFlag.GOT_HITMONLEE),
        retain_trainer_recovery=True),)
