"""Reuse earned helper, native supplies and puzzles as selectable bird goals.

No legacy session/admission dispatcher, supplied species order, injected stock,
teacher combat, capture rollback or new learner. Preparation quantities and
puzzles remain disclosed support; the local model chooses these real peers.
"""

from contextlib import contextmanager
from dataclasses import asdict,dataclass,replace
from hashlib import sha256
from types import SimpleNamespace as N

from pokemon_red_completion.goal_manager import GoalAvailability,GoalKind,GoalOpportunity,GoalUnavailableReason
from pokemon_red_completion.goal_manager_runtime import GoalBindingSet,GoalExecutionReport,GoalVerification
from pokemon_red_completion.observation import ItemId,MapId,event_flag_is_set
from pokemon_red_completion.red_goal_skills import _raw_party_fully_restored
from pokemon_red_completion.red_player_field_goals import _field_ready
from pokemon_red_completion.red_static_capture import red_static_capture_targets
from red_mixed_postgame_delivery_20261009 import (
    learned_collection_transport,native_goal_binding,output_directory,quoted_native_arrival,
)

BIRDS=frozenset({144,145,146})
BALL_RESERVE=99


@dataclass(frozen=True)
class BirdRoute:
    rom: bytes
    route_world: object


def earned_status_helper(runtime):
    """Actual boxed Mewtwo, retaining its native Recover and an owned TM path."""
    raw=runtime.reader.read()
    supported_targets=BIRDS
    if getattr(getattr(runtime,'league_battle_controller',None),
               'income_snorlax_helper_support',False) is True:
        supported_targets=supported_targets|{143}
    if (not runtime.scripted_gifts or raw.badge_bits!=255 or not _field_ready(runtime)
            or not supported_targets-set(runtime.reader.read_pokedex_state().owned_species)):
        return None
    for member in runtime.reader.read_box_specimen_identities():
        if member.species_id!=131 or member.level<70:
            continue
        moves=next(row.moves for row in runtime.reader.read_box_move_members(member.box_index)
                   if row.box_slot==member.box_slot)
        if 105 in moves and (86 in moves or any(m in moves for m in (0,129,112))):
            return member,moves
    return None


def unmet_bird_stock_cash(runtime):
    if earned_status_helper(runtime) is None:
        return 0
    held=dict(runtime.reader.read().bag_items or ()).get(int(ItemId.ULTRA_BALL),0)
    return max(0,BALL_RESERVE-held)*1200


@contextmanager
def selected_learned_routes(runtime,actions,world):
    """Scope old pure helpers to the already qualified learned route owner."""
    import red_current_source_preparation_20261004 as prep
    original=prep.route_to
    wrapper=learned_collection_transport(runtime,actions,world)
    def route(*args,**kwargs):
        if kwargs.get('route_handler_wrapper') is not None:
            raise ValueError('bird support cannot replace an explicitly owned route handler')
        return original(*args,**{**kwargs,'route_handler_wrapper':wrapper})
    prep.route_to=route
    try:
        yield
    finally:
        prep.route_to=original


def native_support_api():
    from red_earned_run_completion_20261005 import strongest_field_lead
    from pokemon_red_completion.red_autonomous_player import _record
    return N(strongest_field_lead=strongest_field_lead,p=N(_record=_record,_field_ready=_field_ready))


def bird_resource_peers(runtime,actions,observed,route):
    """Actual finite TM and affordable native Ultra Balls, never auto-purchase."""
    helper=earned_status_helper(runtime)
    if helper is None:
        return ()
    import red_current_source_preparation_20261004 as prep
    from red_earned_unique_collection_20261006 import native_ultra_provider
    from red_mixed_static_options_20261009 import NoncombatStaticTransport
    from red_pc_registration_20261004 import stock_signature
    from pokemon_red_completion.red_player_field_item import field_item_resupply_binding
    from pokemon_red_completion.living_dex_goal_policy import project_living_dex_goal_candidate
    from pokemon_red_completion.red_live_option_menu import supplemental_live_option
    from pokemon_red_completion.resource_economy_observation import EconomyMode,EconomyOffer
    raw=runtime.reader.read()
    rows=[]
    if 86 not in helper[1] and not dict(raw.bag_items or ()).get(245,0):
        from red_whole_player_inventory_20261006 import preparation_quote_world
        safe=replace(route,route_world=preparation_quote_world(
            route.rom,route.route_world,raw,route.route_world.local_graphs))
        tm=field_item_resupply_binding(runtime,actions,route=safe,item_id=245)
        if tm is not None:
            rows.append(tm)
    cash=unmet_bird_stock_cash(runtime)
    if not cash or raw.player_money<cash or raw.bag_items is None:
        return tuple(rows)
    if not dict(raw.bag_items).get(int(ItemId.ULTRA_BALL),0) and len(raw.bag_items)>=20:
        return tuple(rows)
    if quoted_native_arrival(runtime,route.route_world,town=8,
            map_id=int(MapId.CINNABAR_MART),at=(5,2)) is None:
        return tuple(rows)
    order=prep.ultra_ball_order(raw,BALL_RESERVE)
    if order is None:
        return tuple(rows)
    before=stock_signature(runtime)
    bag=dict(raw.bag_items);bag[int(ItemId.ULTRA_BALL)]=BALL_RESERVE
    def execute():
        prep.route_to(N(rt=runtime,em=runtime.emulator,actions=actions),route.route_world,
            town=8,map_id=int(MapId.CINNABAR_MART),at=(5,2),
            route_handler_wrapper=NoncombatStaticTransport)
        binding=native_ultra_provider(runtime,actions,order).offer(runtime.adapter.observe()).binding
        if binding is None:
            raise ValueError('selected bird stock did not requalify at its actual Mart')
        report=binding.execute()
        if binding.verify(report)!=GoalVerification.succeeded():
            raise ValueError('native bird stock purchase was not verified')
        return dict(native_ultra_procurement=True,quantity=order.quantity,cash_spent=cash,
                    learned_quantity=False,original_reserve=BALL_RESERVE)
    binding=native_goal_binding(runtime,actions,GoalKind.RESUPPLY,'bird-ultra',execute,
        lambda:runtime.reader.read().player_money==raw.player_money-cash
            and dict(runtime.reader.read().bag_items or ())==bag
            and prep.preparation_stock_preserved(before,stock_signature(runtime)),
        maximum_cash_debit=cash)
    unavailable=GoalOpportunity('bird-stock:other',GoalKind.EXPLORE,GoalAvailability.UNAVAILABLE,
        unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET)
    question=GoalBindingSet((binding.opportunity,unavailable),(binding,)).question(observed.situation)
    candidate=project_living_dex_goal_candidate(question,0,feature_version=5,binding_ref=binding.binding_ref)
    candidate=replace(candidate,economy_offer=EconomyOffer(EconomyMode.PURCHASE,planned_spend=cash))
    rows.append(supplemental_live_option(binding,candidate))
    return tuple(rows)


def bird_loan_guard(runtime,declaration=None):
    """Authenticate the approved capture-only individual; no slot/species fallback."""
    from pokemon_red_completion.red_player_party_guard import (
        BIRD_CAPTURE_LOAN_POLICY, observed_transport_safe_bird_guard,
        validate_bird_capture_loan_declaration,
    )
    validate_bird_capture_loan_declaration(declaration)
    guard=runtime.adapter.party_guard
    guard.verify_active_roster_restored()
    if declaration is None:
        return guard
    if declaration.get('schema')==BIRD_CAPTURE_LOAN_POLICY['schema']:
        helper=earned_status_helper(runtime)
        return (None if helper is None else observed_transport_safe_bird_guard(
            runtime,declaration,helper_moves=helper[1]))
    if (type(declaration) is not dict
            or declaration.get('schema')!='pokemon.red.bird-capture-loan.v1'
            or declaration.get('user_authorized') is not True
            or declaration.get('purpose')!='bird_capture_only'
            or declaration.get('species_id')!=166
            or type(declaration.get('original_refs')) is not list
            or len(declaration['original_refs'])!=6
            or set(declaration['original_refs'])!=set(guard.refs)):
        raise ValueError('bird capture loan requires its approved original roster')
    ref=declaration.get('specimen_ref')
    refs=guard.reader.preparation_specimen_refs()
    raw=runtime.reader.read()
    if (ref not in guard.refs or ref not in refs
            or raw.party_species_ids[refs.index(ref)]!=166):
        raise ValueError('approved bird capture individual is not the exact active Raticate')
    scoped=replace(guard,loanable_refs=frozenset({ref}))
    scoped.verify_active_roster_restored()
    return scoped


@contextmanager
def selected_bird_loan(runtime,declaration=None):
    """Keep the exact loan guard through failure recovery until originals return."""
    scoped=bird_loan_guard(runtime,declaration)
    if scoped is None:
        raise ValueError('selected bird lacks an observed transport-safe original loan')
    with selected_capture_loan(runtime,scoped):
        yield


@contextmanager
def selected_capture_loan(runtime,scoped):
    """Mechanical exact-original return shared by separately authorized targets."""
    original=runtime.adapter.party_guard
    runtime.adapter.party_guard=scoped
    try:
        yield
    finally:
        active=scoped.reader.preparation_specimen_refs()
        if set(original.refs)<=set(active):
            original.verify_active_roster_restored()
            runtime.adapter.party_guard=original
        # If a failure leaves the original boxed, compulsory existing settlement
        # must retain this exact guard. Export still requires all originals active.


def execute_bird_recipe(runtime,actions,route,target,helper,*,capture_loan=None):
    if target.species_number not in BIRDS:
        raise ValueError('bird-only loan cannot activate another static source')
    with selected_bird_loan(runtime,capture_loan):
        return _execute_bird_recipe(runtime,actions,route,target,helper)


def snorlax_loan_guard(runtime,declaration):
    from pokemon_red_completion.red_player_party_guard import (
        observed_transport_safe_snorlax_guard,validate_snorlax_capture_loan_declaration,
    )
    validate_snorlax_capture_loan_declaration(declaration)
    if declaration is None:
        return None
    helper=earned_status_helper(runtime)
    return (None if helper is None else observed_transport_safe_snorlax_guard(
        runtime,declaration,helper_moves=helper[1]))


def execute_snorlax_recipe(runtime,actions,route,target,helper,*,capture_loan):
    from red_remaining_static_20261004 import route16_snorlax_target
    if target!=route16_snorlax_target(route.rom):
        raise ValueError('Snorlax loan cannot activate another static source')
    scoped=snorlax_loan_guard(runtime,capture_loan)
    if scoped is None:
        raise ValueError('selected Snorlax lacks its observed transport-safe original loan')
    with selected_capture_loan(runtime,scoped):
        return _execute_bird_recipe(runtime,actions,route,target,helper)


def _execute_bird_recipe(runtime,actions,route,target,helper):
    """Selected native loan/puzzle/capture/return, never an old session recipe."""
    import red_current_source_preparation_20261004 as prep
    import red_pc_registration_20261004 as pc
    import red_earned_unique_collection_20261006 as unique
    from red_remaining_static_20261004 import native_catcher_recovery
    from pokemon_red_completion.red_capture_lead import RedCaptureLeadPlan
    from pokemon_red_completion.red_capture_preparation import prepare_observed_lead,status_prepared_static_offer
    from pokemon_red_completion.red_machine_teaching import plan_machine_lesson,execute_machine_lesson
    from pokemon_red_completion.red_static_capture_goal import RedStaticCaptureGoalProvider
    api=native_support_api()
    output=output_directory(runtime)
    if output is None:
        raise ValueError('native bird recipe lacks its configured evidence owner')
    a0,f0=actions.actions_executed,runtime.emulator.frame_count
    original=pc.stock_signature(runtime)
    with selected_learned_routes(runtime,actions,route.route_world):
        ref=unique.borrow_helper(api,runtime,actions,route.route_world,output,helper,
                                 reserve_capture_box=True)
        slot=runtime.adapter.party_guard.reader.preparation_specimen_refs().index(ref)+1
        replace_slot=prep.capture_helper_lesson_slot(runtime.reader.read(),slot)
        if replace_slot is not None:
            lesson=plan_machine_lesson(route.rom,runtime.reader,item_id=245,
                                      party_slot=slot,replace_slot=replace_slot)
            execute_machine_lesson(runtime.emulator,actions,runtime.reader,lesson,rom=route.rom)
            api.p._record(output/f'BIRD-OWNED-LESSON-{a0:08d}.json',dict(lesson=asdict(lesson),learned=False))
        s=unique.session(runtime,actions,output)
        unique.strong_lead(api,runtime,actions)
        town,map_id,at=prep.STATIC_CAPTURE_DESTINATIONS[target.species_number]
        if target.species_number==144:
            for floor in (192,159,160,161):
                unique.seafoam_floor(api,s,route,floor)
        elif target.species_number==146:
            route,_=prep.prepare_moltres_cave(s,route,town)
        prep.route_to(s,route.route_world,town=town,map_id=map_id,at=at,
                      capture_loan=True,allow_surf_origin=True)
        index=runtime.adapter.party_guard.reader.preparation_specimen_refs().index(ref)
        prepare_observed_lead(runtime,actions,RedCaptureLeadPlan(index,runtime.adapter.observe().party),
                              label='disclosed earned bird status helper')
        prep.prepare_static_facing(s,target)
        balls=dict(runtime.reader.read().bag_items or ()).get(int(ItemId.ULTRA_BALL),0)
        if balls<BALL_RESERVE:
            raise ValueError('selected bird lacks its original99-ball allocation')
        directory=output/f'mixed-bird-{target.species_number}-{sha256(runtime.emulator.save_state_bytes()).hexdigest()[:16]}'
        from contextlib import nullcontext
        from red_remaining_static_20261004 import native_snorlax_source
        with (native_snorlax_source(route.rom,target)
              if target.species_number==143 else nullcontext()):
            provider=RedStaticCaptureGoalProvider(route.rom,target,ItemId.ULTRA_BALL,BALL_RESERVE,
                runtime.reader,runtime.adapter,runtime.emulator,actions,directory,
                prepare_status=True,maximum_status_attempts=10,preserve_viable_active=True,
                minimum_prepared_helper_level=70,weaken_capture=False,prepare_facing=False,
                require_status_success=True,allow_snorlax=target.species_number==143)
            binding=status_prepared_static_offer(provider,runtime,actions,runtime.adapter.observe()).binding
            if binding is None:
                raise ValueError('selected static source lacks actual native status/capture admission')
            with native_catcher_recovery():
                report=binding.execute()
            if binding.verify(report)!=GoalVerification.succeeded():
                raise ValueError('selected static capture was not verified')
        if not prep.capture_stock_preserved(original,pc.stock_signature(runtime),target):
            raise ValueError('bird capture changed original individual stock')
        unique.return_helper(api,runtime,actions,route.route_world,output)
        if not prep.capture_stock_preserved(original,pc.stock_signature(runtime),target):
            raise ValueError('bird return changed original individual stock')
    return GoalExecutionReport(actions.actions_executed-a0,runtime.emulator.frame_count-f0,
        {**report.evidence,('native_snorlax_registered' if target.species_number==143
            else 'native_bird_registered'):target.species_number,
         'native_helper_return':True,'puzzle_and_capture_preparation_learned':False})


def routed_bird_bindings(runtime,observation,actions,route,*,capture_loan=None):
    from pokemon_red_completion.red_routed_static_capture import prepared_static_acquisition_binding
    from red_earned_unique_collection_20261006 import capture_box_for_loan
    from pokemon_red_completion.red_pc_storage import RedPCStorageError
    helper=earned_status_helper(runtime)
    raw=runtime.reader.read()
    if (helper is None or observation.party.fainted_count or observation.immediate_capture_slots<1
            or dict(raw.bag_items or ()).get(int(ItemId.ULTRA_BALL),0)<BALL_RESERVE
            or (86 not in helper[1] and not dict(raw.bag_items or ()).get(245,0))
            or output_directory(runtime) is None):
        return ()
    guard=bird_loan_guard(runtime,capture_loan)
    if guard is None or len(guard.loanable_refs)!=1 or raw.party_moves is None:
        return ()
    loan,=guard.loanable_refs
    refs=guard.reader.preparation_specimen_refs()
    loan_slot=refs.index(loan)
    remaining_moves={move for i,moves in enumerate(raw.party_moves) if i!=loan_slot
                     for move in moves}|set(helper[1])
    try:
        capture_box_for_loan(runtime.reader.read_all_box_states(),helper[0].box_index)
    except RedPCStorageError:
        return ()
    owned=runtime.reader.read_pokedex_state().owned_species
    rows=[]
    for target in red_static_capture_targets(route.rom):
        if (target.species_number not in BIRDS or target.species_number in owned
                or event_flag_is_set(raw.event_flags,target.event_flag)):
            continue
        # Check the physical party after the named exchange. Both boulder routes
        # call the native Strength skill, including on the return through Victory Road.
        if target.species_number in (144,146) and 70 not in remaining_moves:
            continue
        if target.species_number in (144,145) and 57 not in remaining_moves:
            continue  # The quoted water route must remain executable after the named loan.
        town,stage=(7,192) if target.species_number==144 else (9,198) if target.species_number==146 else (3,83)
        if quoted_native_arrival(runtime,route.route_world,town=town,map_id=stage,at=None) is None:
            continue
        def returned():
            runtime.adapter.party_guard.verify_active_roster_restored()
            return _field_ready(runtime) and _raw_party_fully_restored(runtime.reader.read())
        binding=prepared_static_acquisition_binding(runtime,actions,rom=route.rom,target=target,
            execute_prepared=lambda t:execute_bird_recipe(runtime,actions,route,t,helper[0],
                                                         capture_loan=capture_loan),
            verify_return=returned,estimated_effort=.65 if target.species_number==144 else .45,
            estimated_risk=.25)
        if binding is not None:
            rows.append(binding)
    return tuple(rows)


def routed_snorlax_bindings(runtime,observation,actions,route,*,capture_loan=None):
    """Quote only the protected Route16 source; keep the model's capture choice."""
    from red_remaining_static_20261004 import route16_snorlax_target
    from pokemon_red_completion.red_routed_static_capture import prepared_static_acquisition_binding
    from red_earned_unique_collection_20261006 import capture_box_for_loan
    from pokemon_red_completion.red_pc_storage import RedPCStorageError
    from pokemon_red_completion.red_player_party_guard import validate_snorlax_capture_loan_declaration
    validate_snorlax_capture_loan_declaration(capture_loan)
    if capture_loan is None:
        return ()
    raw=runtime.reader.read()
    target=route16_snorlax_target(route.rom)
    helper=earned_status_helper(runtime)
    if (helper is None or target.species_number in runtime.reader.read_pokedex_state().owned_species
            or event_flag_is_set(raw.event_flags,target.event_flag)
            or observation.party.fainted_count or observation.immediate_capture_slots<1
            or dict(raw.bag_items or ()).get(int(ItemId.ULTRA_BALL),0)<BALL_RESERVE
            or not dict(raw.bag_items or ()).get(int(ItemId.POKE_FLUTE),0)
            or (86 not in helper[1] and not dict(raw.bag_items or ()).get(245,0))
            or output_directory(runtime) is None):
        return ()
    scoped=snorlax_loan_guard(runtime,capture_loan)
    if scoped is None or len(scoped.loanable_refs)!=1:
        return ()
    try:
        capture_box_for_loan(runtime.reader.read_all_box_states(),helper[0].box_index)
    except RedPCStorageError:
        return ()
    if quoted_native_arrival(runtime,route.route_world,town=6,map_id=target.map_id,
            at=(10,27)) is None:
        return ()
    def returned():
        runtime.adapter.party_guard.verify_active_roster_restored()
        return _field_ready(runtime) and _raw_party_fully_restored(runtime.reader.read())
    binding=prepared_static_acquisition_binding(runtime,actions,rom=route.rom,target=target,
        execute_prepared=lambda t:execute_snorlax_recipe(runtime,actions,route,t,helper[0],
                                                       capture_loan=capture_loan),
        verify_return=returned,estimated_effort=.4,estimated_risk=.25,
        allow_route16_snorlax=True)
    return () if binding is None else (binding,)
