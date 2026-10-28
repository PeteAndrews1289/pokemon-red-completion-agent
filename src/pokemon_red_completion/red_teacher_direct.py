"""Shared one-load direct TRAIN collector extracted from qualified 047/049 workers.

Caller authenticates package/plan and lifecycle; this module owns only the same
native assembly, observed menu gate, one declared teacher phase, and cleanup.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, time, traceback, signal

def run_direct(plan, *, output, worker_path, loader_definitions, started, write):
 OUT=Path(output);PLAN=OUT/'PLAN.json';package=Path(plan['package']).parent
 read=lambda p:json.loads(Path(p).read_bytes())
 sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
 profile_marks=[]
 def profile(label):profile_marks.append(dict(phase=label,elapsed_seconds=time.monotonic()-started))
 physical=dict(construction_attempts=0,emulators_constructed=0,load_attempts=0,state_loads=0)
 result=dict(schema='pokemon.red.prospective-v9-train-preparation-arm.v1',started_at_utc=datetime.now(timezone.utc).isoformat(),passed=False,admitted=False,condition=plan['condition'],role=plan['role'],teacher_selected=True,goal_policy_queries=0,new_fits=0,new_weights=0,copy_back=False,campaign_progress=False,training_admission=False)
 session=None;emulator=None;holder={}
 try:
  from .red_teacher_case import validate_plan_case,build_teacher_session_kwargs,validate_retained_menu,validate_source_boundary,story_binding_settings
  profile('worker_identity_ready')
  assert datetime.now(timezone.utc)<datetime.fromisoformat(plan['cutoff_utc'])
  for p,v in plan['pins'].items():assert sha(p)==v
  catalog=read(plan['source_catalog']);row,=[r for r in catalog['sources']if r['condition']==plan['condition']]
  case_spec=validate_plan_case(plan,row);case=case_spec.document()
  assert plan['fit_allowed'] and plan['caps']['new_fits']==0
  assert catalog['metadata_gate_passed'] and row['source_partition']=='train' and row['role']==plan['role']=='train_sampling' and row['fit_allowed']
  payload=Path(plan['source']).read_bytes();assert hashlib.sha256(payload).hexdigest()==plan['source_sha256'] and row['state_sha256']==plan['original_TRAIN_state_sha256']
  custody=read(plan['retained_source_custody'])
  allowance=loader_definitions['validate_diagnostic_startup'](plan,custody,row)
  remaining=min(allowance,plan['worker_wall_seconds']-(time.monotonic()-started))
  if remaining<=2:raise TimeoutError('Insufficient diagnostic cleanup allowance')
  signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('Declared TRAINcase cutoff')))
  signal.alarm(max(1,int(remaining-2)))
  from pokemon_red_completion.red_player_package import bind_player_package,package_read_guard
  profile('plan_pins_and_custody_verified')
  manifest=bind_player_package(Path(plan['package']),plan['package_sha256'],history_output=OUT)
  profile('frozen_package_bound')
  result['verified_data_cache_release']=manifest.get('_verified_data_cache_release')
  import sdl2,pyboy
  assert str(Path(sdl2.get_dll_file()).resolve())in manifest['environment_pins']
  assert str(Path(pyboy.__file__).resolve())in manifest['environment_pins']
  reads,writes=package_read_guard(manifest,manifest_path=Path(plan['package']),output=OUT,extra_inputs=[str(PLAN),str(Path(worker_path).resolve()),str(Path(__file__).resolve()),plan['qualification'],*plan['pins']])
  from dataclasses import replace,asdict
  import player_coherent_session as shared
  import player_first_restore_lesson as c
 
  import pokemon_red_completion.red_trainer_practice_episode as timing_episode
  original_episode=timing_episode.run_red_trainer_practice_episode
  timing_calls=[]
  def timed_episode(capture,**kwargs):
   assert capture.manifest.partition.value=='train' and not kwargs.get('wild_training',False)
   assert not timing_calls and kwargs.get('action_executor') is not None
   assert capture.manifest.expected_map==plan['exact_contract']['map_id'] and capture.manifest.expected_battle_state==2
   assert holder['runtime'].reader.read_active_trainer_identity()==holder['contract'].trainer_identity==tuple(plan['exact_contract']['trainer_identity'])
   assert not kwargs.get('allow_status_moves',False) and not kwargs.get('opening_idle_frames',0)
   offset=plan['opening_idle_frames'];timing_episode.validate_opening_idle_frames(offset)
   assert offset==0
   before=len(timing_calls);timing_calls.append(dict(capture_sha256=capture.manifest_sha256,opening_idle_frames=offset))
   write(OUT/('TIMING-INTERVENTION-%02d.json'%before),timing_calls[-1])
   episode=original_episode(capture,**dict(kwargs,opening_idle_frames=offset))
   assert episode.opening_idle_frames==offset
   return episode
  timing_episode.run_red_trainer_practice_episode=timed_episode
  from pokemon_red_completion.emulator import PyBoyAdapter
  from pokemon_red_completion.executor import ReadOnlyController
  from pokemon_red_completion.private_artifacts import initialize_private_root,gitless_fast_path_worktree_probe
  from pokemon_red_completion.red_native_player import NativePlayerSession,NativeExecutionIdentity,NativePlayerLimits
  from pokemon_red_completion.red_challenge_consequence import ChallengeConsequenceSpec,load_challenge_consequence
  from pokemon_red_completion.red_player_model import load_player_goal_model_record
  from pokemon_red_completion.red_party import PokemonRedPartyReader
  from pokemon_red_completion.observation import MapId,EventFlag
  from pokemon_red_completion.scenario_lab import ScenarioPartition
  from pokemon_red_completion.red_goal_skills import _raw_party_fully_restored
  from pokemon_red_completion.red_player_field_goals import routed_restoration_binding,routed_preparation_binding,_field_ready
  from pokemon_red_completion.red_player_member_preparation import member_preparation_plans
  from pokemon_red_completion.red_party_preparation import observe_preparation_members
  from pokemon_red_completion.red_player_continuation import refresh_preparation_roster
  from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
  from pokemon_red_completion.gen1_cartridge import internal_to_dex,evolution_graph,EvolutionMethod
  from pokemon_red_completion.gen1_route_runtime import Gen1TraversalObserver
  from pokemon_red_completion.gen1_traversal import cut_capabilities
  from pokemon_red_completion.route_plan import RoutePlanningError
  from pokemon_red_completion.red_party_preparation import preparation_trainee
  from pokemon_red_completion.red_wild_preparation import wild_training_has_attack_capacity
  from pokemon_red_completion.red_player_story_battle import story_battle_binding
  from pokemon_red_completion.red_story_battle import StoryTrainerContract
  from pokemon_red_completion.red_gym_reward import BLAINE_REWARD
  from pokemon_red_completion.red_player_gym import gym_story_option
  from pokemon_red_completion.gen1_trainer_sight import trainer_headers,map_object_events,static_trainer_sight_zones
  from pokemon_red_completion.red_player_story_menu import NativeStoryBranchInventory
  from pokemon_red_completion.goal_manager import GoalKind,GoalOpportunity,GoalAvailability,GoalUnavailableReason
  from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
  from pokemon_red_completion.red_training_ground_route import RedVermilionGroundTransition
  from pokemon_red_completion.red_training_ground_route import ground_route_capability_projector
  from pokemon_red_completion.red_living_dex_wild_corridor import derive_red_living_dex_wild_corridor
  from pokemon_red_completion.red_living_dex_provider_curriculum import RedEncounterSourceTarget
  from pokemon_red_completion.red_learned_trainer import FROZEN_K_SHA256
  from pokemon_red_completion.red_scoped_training_battlers import ScopedTrainingBattlers
  from pokemon_red_completion.gen1_trainer_parties import trainer_party_quote
  from pokemon_red_completion.gen1_scripted_arrival import trainer_room_arrival,with_scripted_trainer_arrival
  from pokemon_red_completion.player_option_challenge import OptionChallenge
  from pokemon_red_completion.red_live_option_menu import RedLiveOptionSet
  from pokemon_red_completion.provenance import canonical_sha256
  from pokemon_red_completion.hideout import HideoutTiming
  from pokemon_red_completion.red_player_preparation_binding import preparation_binding
  profile('imports_complete')
  c.FROZEN_SOURCE_COMMIT=manifest['source_commit']
  rom_path=package/'data/storage-migration/roms/PokemonRoms/Pokemon Red.gb';rom=rom_path.read_bytes()
  envelope=read(plan['source_envelope']);progress=read(plan['assisted_progress'])
  assert envelope['state_sha256']==plan['source_sha256'] and progress['campaign_eligible'] is False
  assert progress['partition']=='train' and progress['envelope']==envelope
  runtime_case=OUT/'runtime';runtime_case.mkdir(mode=0o700)
  # Source partition is supplied to the existing TRAIN constructor before the
  # runtime and battlers exist. No DEVELOPMENT runtime is relabeled.
  factory0,_,holder,source=shared.assembly(payload,runtime_case,origin_sha=row['source_origin_sha256'],partition='train',origin_id=plan['shared_origin_id'],objective_ids=envelope['verified_objective_ids'],protect_party_species=False)
  source=dict(source,experiment_sha256=sha(PLAN),setup_receipt_sha256=sha(plan['assisted_progress']),historical_train_source=row['historical_source'],campaign_eligible=False)
  assert source['partition']=='train' and source['state_sha256']==plan['source_sha256']
  route=replace(RedVermilionGroundTransition.from_rom(rom),full_event_offsets=True,observe_terrain=True,allow_surf=False,allow_wild_faints=True,allow_field_faint_dialogue=True)
  from pokemon_red_completion.red_living_dex_multifamily_curriculum import map_id_for_wild_source
  quote=trainer_party_quote(rom,plan['exact_contract']['trainer_identity'][0],plan['exact_contract']['trainer_identity'][2]);opponent_levels=tuple(m.level for m in quote.party)
  def factory(controller):
   rt=factory0(controller);prototype=holder['actor']
   assert prototype.source_partition is ScenarioPartition.TRAIN and prototype.development_story_scope is None
   exact=plan['exact_contract']
   contract=(BLAINE_REWARD.contract(rom,rt.reader.read()) if case_spec.mode=='blaine_leader' else
    StoryTrainerContract.from_cartridge(rom,rt.reader.read(),objective_id=exact['objective_id'],battle_plan_id=exact['battle_plan_id'],map_id=exact['map_id'],defeated_event=exact['defeated_event']))
   assert prototype.model_sha256==plan['battler_sha256']==FROZEN_K_SHA256
   raw=rt.reader.read()
   write(OUT/'SOURCE-BATTLE-BOUNDARY.json',dict(observed_contract=asdict(contract),expected_contract=plan['exact_contract'],
    actor_partition=prototype.source_partition.value,actor_model_sha256=prototype.model_sha256,inputs=0,frames=emulator.frame_count))
   assert json.loads(json.dumps(asdict(contract)))==plan['exact_contract']
   contracts=(contract,)
   write(OUT/'EXACT-TRAIN-BATTLE-SCOPES.json',dict(contracts=[asdict(c)for c in contracts],partition='train',declared_before_inputs=True))
   pool=ScopedTrainingBattlers(prototype,contracts=contracts,output=OUT/'scoped-battles',experiment_sha256=sha(PLAN),native_plan_sha256=sha(PLAN))
   holder.update(runtime=rt,pool=pool,wild=pool.wild,story=pool.story(contract),contract=contract)
   rt.adapter.include_pp_restoration=True
   return rt
  def live_route(rt):
   return replace(route,route_world=route.route_world.with_current_observation(rt.reader))
  def base(rt,actions,observation):
   holder['plan']=refresh_preparation_roster(rt.emulator,holder['plan'],evolution_rom=rom)
   restore=routed_restoration_binding(rt,actions,home_map=case['restoration_home_map'],route=live_route(rt),include_indigo_lobby=False)
   bindings=()if restore is None else(restore,);kinds={b.kind for b in bindings}
   masked=tuple(GoalOpportunity('train-unavailable:'+k.value,k,GoalAvailability.UNAVAILABLE,unavailable_reason=GoalUnavailableReason.TEMPORARILY_BLOCKED)for k in GoalKind if k not in kinds)
   return GoalBindingSet(tuple(b.opportunity for b in bindings)+masked,bindings)
  def branches(rt,actions,observation):
   binding=story_battle_binding(rt,actions,contract=holder['contract'],route=live_route(rt),battler=holder['story'],
     **story_binding_settings(case_spec,BLAINE_REWARD))
   if binding is None:
    raise ValueError('Exact local trainer approach unavailable; lawful setup needed before any consequence label')
   return ((replace(binding,story_objective_ref=case['exact_contract']['objective_id']),challenge(rt)),)
  def challenge(rt):
   return OptionChallenge.from_levels(combat_levels=tuple(m.level for m in PokemonRedPartyReader(rt.emulator).read().members),opponent_levels=opponent_levels)
  def machines(rt,actions,observation):
   from pokemon_red_completion.red_player_owned_machines import owned_machine_options
   rows=owned_machine_options(rt,actions,rom=rom,include_move_change_facts=True)
   # The prospective TRAIN task declares this observed native opponent roster.
   # This is context, not a selected lesson or a promised result.
   return tuple(replace(row,candidate=replace(row.candidate,challenge=challenge(rt)))for row in rows)
  menu=NativeStoryBranchInventory(base,branches,enumerate_preparation=lambda *_:(),enumerate_owned_machines=machines)
  callbacks=menu.native_callbacks()
  def all_challenges(rt,bindings,supplements,boundary):
   previews=menu.challenges(rt,bindings,supplements,boundary);peer=challenge(rt)
   return{b.binding_ref:previews.get(b.binding_ref,peer)for b in(*bindings.bindings,*(x.binding for x in supplements))}
  callbacks['observe_challenges']=all_challenges
  original_init=PyBoyAdapter.__init__;original_load=PyBoyAdapter.load_state_bytes
  def one_emulator(self,*args,**kwargs):
   physical['construction_attempts']+=1
   if physical['construction_attempts']>1:raise ValueError('one declared TRAINemulator')
   original_init(self,*args,**kwargs);physical['emulators_constructed']+=1
  def one_load(self,state):
   physical['load_attempts']+=1
   if physical['load_attempts']>1:raise ValueError('one declared TRAINsource load')
   original_load(self,state);physical['state_loads']+=1
  PyBoyAdapter.__init__=one_emulator;PyBoyAdapter.load_state_bytes=one_load
  baseline=load_player_goal_model_record(Path(plan['goal_model_record']['path']),expected_model_sha256=plan['goal_model_sha256']).model
  from pokemon_red_completion.living_dex_option_value import upgrade_option_value_model_for_move_change
  model=upgrade_option_value_model_for_move_change(baseline)
  assert model.model_sha256==plan['zero_extended_goal_model_sha256']
  q=read(plan['qualification'])
  assert q['passed'] and q['plan_sha256']==sha(PLAN) and q['worker_sha256']==sha(worker_path)
  assert q['teacher_case']==case and q['phase']=='preflight' and q['emulators']==q['loads']==q['inputs']==0
  parent=read(plan['source_parent_authentication'])
  assert parent['all_original_processes_absent'] and parent['controls_released'] and parent['preinput_verified'] and parent['passed'] and parent['terminal_sha256']==plan['source_sha256']
  journal=OUT/'journal';journal.mkdir(mode=0o700);store=initialize_private_root(journal,repository_root=package/'checkout',allow_same_device=True,git_worktree_probe=gitless_fast_path_worktree_probe,native_input_storage='flat_sealed_v1')
  profile('assembly_and_store_ready')
  native_limits=NativePlayerLimits(**plan['native_limits'])
  with PyBoyAdapter(rom_path)as emulator:
   try:
    emulator.load_state_bytes(payload);party=PokemonRedPartyReader(ReadOnlyController(emulator));refs=party.preparation_specimen_refs();mons=party.read().members;slot=plan['member_slot']
    from pokemon_red_completion.observation import PokemonRedStateReader
    raw_source=PokemonRedStateReader(ReadOnlyController(emulator)).read()
    validate_source_boundary(case_spec,dict(source_sha256=hashlib.sha256(emulator.save_state_bytes()).hexdigest(),
     combat_specimen_refs=list(refs),map_id=raw_source.map_id,player_x=raw_source.player_x,player_y=raw_source.player_y,
     inputs=0,frames=emulator.frame_count,pressed_buttons=sorted(emulator.pressed_buttons)),lambda value:write(OUT/'SOURCE-BOUNDARY.json',value))
    profile('emulator_constructed_and_source_loaded')
    initial=GoalKind(plan['initial_kind'])
    session=NativePlayerSession(**build_teacher_session_kwargs(case_spec,store=store,emulator=emulator,
     runtime_factory=factory,source=source,execution=NativeExecutionIdentity(OUT.name,'teacher-assigned-train',model.model_sha256,case['seed']),
     output=OUT/'native',battle_observer=lambda:holder['pool'].history(),teacher_receipt_sha256=sha(plan['assisted_progress']),callbacks=callbacks))
    def choose(options,kind):
     bindings=options.bindings if hasattr(options,'menu')else options.bindings.bindings
     candidates=[b for b in bindings if b.kind is kind]
     if len(candidates)!=1:raise ValueError('assigned TRAINoption unavailable:'+kind.value+':'+str(len(candidates)))
     return candidates[0]
    options = session.observe(0)
    binding = choose(options, initial)
    assert isinstance(options, RedLiveOptionSet)
    assert emulator.frame_count == 0 and emulator.save_state_bytes() == payload and not emulator.pressed_buttons
    assert holder['wild'].source_partition is holder['story'].source_partition is ScenarioPartition.TRAIN
    machine_peers = [b for b in options.bindings if b.binding_ref.startswith('pokemon.red:owned-machine:')]
    story_peers = [b for b in options.bindings if b.kind is GoalKind.ADVANCE_STORY]
    assert machine_peers and len(story_peers) == 1
    assert _raw_party_fully_restored(session.runtime.reader.read())
    assert tuple(session.snapshot().facts['completed_objectives']) == tuple(envelope['verified_objective_ids'])
    from pokemon_red_completion.red_consequence_choice import consequence_cash_exposures
    cash_exposures=consequence_cash_exposures(options,challenge_refs=(case['exact_contract']['objective_id'],)*len(options.bindings))
    wallet=session.runtime.reader.read().player_money
    assert cash_exposures[options.bindings.index(binding)]==wallet-wallet//2
    write(OUT/'NATIVE-CASH-CERTIFICATES.json',dict(source_state_sha256=plan['source_sha256'],wallet=wallet,exposures=list(cash_exposures),bindings=[dict(binding_ref=b.binding_ref,certificate=asdict(b.cash_outcome)if b.cash_outcome else None)for b in options.bindings],inputs=0,frames=0,teacher_assigned=True,goal_policy_queries=0))
    # Zero-input gate compares genuine prior observation; no old row is changed.
    from pokemon_red_completion.red_pp_observation import observe_pp_resources
    old_shadow=read(plan['retained_menu'])
    new_bindings=[dict(binding_ref=x.binding_ref,kind=x.kind.value)for x in options.bindings]
    pp=observe_pp_resources(session.runtime.reader.read()).public_dict()
    write(OUT/'OBSERVATION-BEFORE-INPUT.json',dict(menu=options.menu.policy_dict(),bindings=new_bindings,
     raw_pp=pp,combat_specimen_refs=list(refs),history=holder['pool'].history(),exact_contract=asdict(holder['contract']),
     source_sha256=hashlib.sha256(emulator.save_state_bytes()).hexdigest(),inputs=len(session.recorder.trace),frames=emulator.frame_count,
     pressed_buttons=sorted(emulator.pressed_buttons),goal_policy_queries=0,teacher_selected=True))
    pp_gate=validate_retained_menu(case_spec,old_shadow,options.menu.policy_dict(),new_bindings,pp)
    assert holder['pool'].history() is None and list(refs)==plan['expected_combat_specimen_refs']
    assert emulator.frame_count==0 and emulator.save_state_bytes()==payload and not emulator.pressed_buttons and not session.recorder.trace
    write(OUT/'LIVE-PP-PREINPUT-GATE.json',dict(pp_gate,source_bytes_exact=True,source_sha256=plan['source_sha256'],combat_specimen_refs=list(refs),inputs=0,frames=0,new_fits=0,actual_credit=0,related_family=True,independence_claim=False))
    prospective = session.consequence.begin(options, binding, preflight_only=True)
    write(OUT/'PREINPUT-QUALIFICATION.json', dict(passed=True, source_bytes_exact=True,
        source_state_sha256=plan['source_sha256'], source_partition='train', feature_version=10,
        feature_width=len(options.menu.candidate_vector(options.bindings.index(binding),feature_version=10)),
        selected_kind=initial.value, selected_binding=binding.binding_ref, machine_alternatives=len(machine_peers),
        direct_challenge_alternatives=1, inputs=0, frames=0, goal_policy_queries=0,
        teacher_selected=True, consequence_plan=prospective))
    profile('preinput_qualified')
    for ordinal in range(plan['native_limits']['decisions']):
     if ordinal:
      options = session.observe(ordinal)
      kind = GoalKind.RESTORE_TEAM if not _raw_party_fully_restored(session.runtime.reader.read()) else GoalKind.ADVANCE_STORY
      binding = choose(options, kind)
     else:
      kind = initial
     write(OUT/('choice-%02d.json'%ordinal), dict(kind=kind.value, binding_ref=binding.binding_ref,
         teacher_assigned=True, model_query=False))
     report = binding.execute()
     verdict = binding.verify(report)
     session.finish_decision()
     write(OUT/('phase-verdict-%02d.json'%ordinal),dict(kind=kind.value,status=verdict.status.value,evidence=report.evidence))
     if session.consequence.done:
      break
     assert session.snapshot().safe
    profile('native_decisions_complete')
    assert len(timing_calls)==1,'timing experiment requires exactly one observed declared trainer battle'
    assert session.decisions==1, 'one direct native phase only'
    recorded = session.consequence.finish()
    admitted = load_challenge_consequence(store, declaration_sha256=recorded['declaration_sha256'],
        result_sha256=canonical_sha256(recorded))
    result.update(passed=True, opening_idle_frames=plan['opening_idle_frames'], timing_interventions=timing_calls, admitted=admitted.outcome is not None, row=admitted.document(),
        training_admission=admitted.outcome is not None, declaration_sha256=recorded['declaration_sha256'],
        result_sha256=canonical_sha256(recorded), field_ready=_field_ready(session.runtime),
        acquisition_is_preexisting_sunk_cost=plan['separate_acquisition_cost'],
        actual_credit=0, model_feature_version=10, goal_policy_queries=0)
 
   finally:
    result['release_only_cleanup']=sorted(emulator.pressed_buttons)
    from .executor import release_pressed_buttons
    release_pressed_buttons(emulator)
    if session is not None:
     session.controller.input_enabled=False;session.recorder.enabled=False
     try:
      if session.consequence and session.consequence.plan and not(session.output/'consequence-result.json').exists():session.consequence.finish()
     except Exception as exc:result.update(passed=False,finish_error=str(exc),finish_traceback=traceback.format_exc())
     result.update(actions=len(session.recorder.trace),frames=session.controller.frames_executed,goal_attempts=session.decisions,heals=session.heals,native_seconds=session.wall.elapsed_seconds,controls_released=not session.controller.pressed_buttons,wild_battles=holder['wild'].calls,story_battles=sum(a.calls for a in holder['pool']._actors)-holder['wild'].calls)
     terminal=session.controller.save_state_bytes();(OUT/'terminal.state').write_bytes(terminal)
     result['terminal_sha256']=hashlib.sha256(terminal).hexdigest()
    else:
     terminal=emulator.save_state_bytes();(OUT/'terminal.state').write_bytes(terminal)
     result.update(actions=0,frames=emulator.frame_count,goal_attempts=0,heals=0,native_seconds=0,controls_released=not emulator.pressed_buttons,terminal_sha256=hashlib.sha256(terminal).hexdigest())
 
 except BaseException as exc:
  result.update(passed=False,error_type=type(exc).__name__,error=str(exc),traceback=traceback.format_exc())
 finally:
  signal.alarm(0)
  if 'original_episode' in locals():timing_episode.run_red_trainer_practice_episode=original_episode
  if 'original_init' in locals():PyBoyAdapter.__init__=original_init;PyBoyAdapter.load_state_bytes=original_load
  profile('terminal_saved_and_emulator_closed')
  result.update(setup_profile=profile_marks,physical_emulator_accounting=physical,outer_seconds=time.monotonic()-started,finished_at_utc=datetime.now(timezone.utc).isoformat())
 return result
