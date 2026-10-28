"""ROM-free V13 capture invocation integration and legacy default contracts."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as NS
import ast, json
import pytest
from test_red_live_safari import _area
from pokemon_red_completion.goal_manager import GoalKind, GoalSituation, GoalOpportunity, GoalAvailability, GoalUnavailableReason
from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.living_dex_option_value import LivingDexOptionMenu, LivingDexOptionCandidate, LivingDexOptionFeatures, LivingDexOptionKind, LivingDexOptionAvailability, living_dex_option_context_from_goal_situation
from pokemon_red_completion.player_option_capture_invocation import OptionCaptureInvocation
from pokemon_red_completion.red_live_option_menu import build_red_live_option_set, supplemental_live_option
import pokemon_red_completion.red_live_safari as live
HERE=Path(__file__).resolve().parent


def context():return living_dex_option_context_from_goal_situation(GoalSituation(0.,1.,0.,1.,0.,0.,0.,0.,0.))
def configure(monkeypatch,module):
    areas=(_area("wild:SafariZoneCenter:grass",int(MapId.SAFARI_ZONE_CENTER),3,4),
           _area("wild:SafariZoneNorth:grass",int(MapId.SAFARI_ZONE_NORTH),2,2))
    areas=tuple(module.RedReachableSafariArea(a.offer,a.patrol,a.route_steps)for a in areas)
    monkeypatch.setattr(module,"discover_reachable_red_safari_areas",lambda *a,**k:areas)
    monkeypatch.setattr(module,"resolve_red_safari_entry_mode",lambda *a,**k:module.RedSafariEntryMode.OUTDOOR_FLY)
    monkeypatch.setattr(module,"_price_paid_patrol_alternatives",lambda a,*rest:a)
    return dict(free_storage_slots=2,world=NS(),controller=NS(frame_count=0,pressed_buttons=frozenset()),
                actions=NS(actions_executed=0),reader=NS(read=lambda:NS(player_money=706)))
def empty_bindings():
    return GoalBindingSet(tuple(GoalOpportunity("absent-"+k.value,k,GoalAvailability.UNAVAILABLE,
        unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET)for k in(GoalKind.EXPLORE,GoalKind.RESUPPLY)),())

# Authenticated pre-integration P166 mock-menu outputs, retained without importing a legacy snapshot.
# Six policies coincide because legacy vectors omit the invocation; executor refs still bind each cap/lifecycle.
P166_MOCK_GOLDENS = [(None, False, '66a2c302691726fbcf1c45f2e91d1901cef5953a6a69495cc92aa57e79cc9323', ('pokemon.red:safari-live:c70a28c037ed7aa7a8bb4b908558ac23e16bf0af8eb6318a7833d754c79132ce', 'pokemon.red:safari-live:1dbfbd25bd14187ef82783e4e143c45634a8ea30824432e99958410bc76145d4')), (None, True, '66a2c302691726fbcf1c45f2e91d1901cef5953a6a69495cc92aa57e79cc9323', ('pokemon.red:safari-live:c1a834fe848fc3268a5c84ea3ba92a71cfbabb926870c2e6e6922633f11b7b1a', 'pokemon.red:safari-live:6786f2172a834b850b9ba494138069a4775d85940a5be8e07114ae9c2469c641')), (6, False, '66a2c302691726fbcf1c45f2e91d1901cef5953a6a69495cc92aa57e79cc9323', ('pokemon.red:safari-live:5b553e783d86f26b8f4c374cabf9b1e173e869ff7139da16986607893aaef4e7', 'pokemon.red:safari-live:fbfe05945e6baf2ee4e324d736f15cf00873a1af7ac06d9f808141cbe5ade22b')), (6, True, '66a2c302691726fbcf1c45f2e91d1901cef5953a6a69495cc92aa57e79cc9323', ('pokemon.red:safari-live:60ce63903a8422d5b6a6947597346d48d10e83dfe46a05de88f378afe3e42dfe', 'pokemon.red:safari-live:51b402a422e7fda91a0698dbcaf349329b86bcb6ea83a66517e0ac9febf1166e')), (500, False, '66a2c302691726fbcf1c45f2e91d1901cef5953a6a69495cc92aa57e79cc9323', ('pokemon.red:safari-live:fcfbc5a7205c1c57c92aa7707c94b2b47369f8d178a2191fb8656412cee6366b', 'pokemon.red:safari-live:2964899838275adfbe002fc52de6e7a563a267e5e90473e461b0b8a79e789a0a')), (500, True, '66a2c302691726fbcf1c45f2e91d1901cef5953a6a69495cc92aa57e79cc9323', ('pokemon.red:safari-live:c1a834fe848fc3268a5c84ea3ba92a71cfbabb926870c2e6e6922633f11b7b1a', 'pokemon.red:safari-live:6786f2172a834b850b9ba494138069a4775d85940a5be8e07114ae9c2469c641'))]

@pytest.mark.parametrize("cap,complete,policy_sha256,binding_refs", P166_MOCK_GOLDENS)
def test_default_menu_and_bindings_preserve_golden_contract(monkeypatch,cap,complete,policy_sha256,binding_refs):
    kwargs=configure(monkeypatch,live)
    calls=dict(maximum_encounters=cap,complete_paid_session=complete,expose_all_areas=True)
    implicit=live.build_red_live_safari_inventory(b"rom",(),context(),**kwargs,**calls)
    explicit=live.build_red_live_safari_inventory(b"rom",(),context(),**kwargs,**calls,include_capture_invocation=False)
    for inventory in (implicit,explicit):
        assert tuple(x.binding.binding_ref for x in inventory.supplements)==binding_refs
        menu=LivingDexOptionMenu(context(),tuple(x.candidate for x in inventory.supplements))
        assert menu.policy_sha256==policy_sha256
        assert all(x.candidate.capture_invocation is None for x in inventory.supplements)
    assert LivingDexOptionMenu(context(),tuple(x.candidate for x in implicit.supplements)).policy_dict()==LivingDexOptionMenu(context(),tuple(x.candidate for x in explicit.supplements)).policy_dict()

@pytest.mark.parametrize("complete",[False,True])
@pytest.mark.parametrize("cap",[None,6,500])
@pytest.mark.parametrize("all_areas",[False,True])
def test_every_opted_offer_matches_exact_executor_arguments(monkeypatch,complete,cap,all_areas):
    kwargs=configure(monkeypatch,live);original=live._live_safari_binding;seen=[]
    def binding(**kw):seen.append(kw);return original(**kw)
    monkeypatch.setattr(live,"_live_safari_binding",binding)
    inv=live.build_red_live_safari_inventory(b"rom",(),context(),**kwargs,maximum_encounters=cap,
        complete_paid_session=complete,expose_all_areas=all_areas,include_capture_invocation=True)
    resolved=(500 if complete else 32)if cap is None else cap
    assert len(inv.supplements)==(2 if all_areas else 1)==len(seen)
    for row,call in zip(inv.supplements,seen,strict=True):
        assert row.candidate.capture_invocation==OptionCaptureInvocation(resolved,complete)
        assert call["maximum_encounters"]==resolved and call["complete_paid_session"] is complete
        assert row.candidate.binding_ref==row.binding.binding_ref
        assert row.candidate.vector(context(),feature_version=13)[-2:]==((1.,resolved/(resolved+100))if complete else(0.,0.))
        with pytest.raises(ValueError):row.candidate.vector(context(),feature_version=9)

@pytest.mark.parametrize("bad",[None,0,1,"true"])
def test_invalid_optin_rejected_before_observation(bad):
    from pokemon_red_completion.red_indoor_safari import indoor_safari_inventory
    from pokemon_red_completion.red_autonomous_safari import autonomous_safari_options
    with pytest.raises(ValueError,match="explicit boolean"):
        live.build_red_live_safari_inventory(b"",(),None,free_storage_slots=1,world=None,controller=None,actions=None,reader=None,include_capture_invocation=bad)
    with pytest.raises(ValueError,match="explicit boolean"):
        indoor_safari_inventory(b"",(),None,free_storage_slots=1,world=None,controller=None,actions=None,reader=None,include_capture_invocation=bad)
    with pytest.raises(ValueError,match="explicit boolean"):
        autonomous_safari_options(None,None,None,None,include_capture_invocation=bad)

@pytest.mark.parametrize("cap",[None,6,500])
@pytest.mark.parametrize("complete",[False,True])
@pytest.mark.parametrize("mismatch",[False,True])
def test_indoor_projection_rebound_and_public_wrapper_agree(monkeypatch,cap,complete,mismatch):
    from test_red_indoor_safari import setup
    import pokemon_red_completion.red_indoor_safari as indoor
    original=indoor.indoor_safari_inventory;seen=[]
    def invoke(*args,**kwargs):
        fake=indoor.build_red_live_safari_inventory
        def inventory(*a,**k):
            assert k["include_capture_invocation"] is True
            resolved=(500 if complete else 32)if cap is None else cap
            seen.append((resolved,k["complete_paid_session"]))
            inv=fake(*a,**k)
            if mismatch and len(seen)>1:resolved+=1
            return replace(inv,supplements=tuple(supplemental_live_option(x.binding,
                replace(x.candidate,capture_invocation=OptionCaptureInvocation(resolved,complete)))for x in inv.supplements))
        monkeypatch.setattr(indoor,"build_red_live_safari_inventory",inventory)
        return original(*args,**kwargs,include_capture_invocation=True)
    monkeypatch.setattr(indoor,"indoor_safari_inventory",invoke)
    inv,state,calls=setup(monkeypatch,all_areas=True,maximum_encounters=cap,complete_paid_session=complete)
    selected=inv.supplements[1]
    assert selected.candidate.binding_ref==selected.binding.binding_ref
    if mismatch:
        with pytest.raises(ValueError,match="invocation changed"):selected.binding.execute()
        assert "spend" not in calls
    else:
        report=selected.binding.execute();assert selected.binding.verify(report).status.value=="succeeded"
        assert calls==["project","exit","rebind","spend","second"]
    assert len(seen)==2 and seen[0]==seen[1]

@pytest.mark.parametrize("enabled",[False,True])
def test_autonomous_flag_reaches_live_and_indoor_without_changing_defaults(monkeypatch,enabled):
    from test_red_autonomous_safari import _inputs
    import pokemon_red_completion.red_autonomous_safari as module
    import pokemon_red_completion.red_indoor_safari as indoor
    runtime,observation,actions,world=_inputs();runtime.safari_indoor_departure=True
    runtime.safari_complete_paid_session=True;seen=[]
    def direct(*a,**k):seen.append(k);return NS(supplements=())
    def fallback(*a,**k):seen.append(k);return NS(supplements=("paid",))
    monkeypatch.setattr(module,"build_red_live_safari_inventory",direct)
    monkeypatch.setattr(indoor,"indoor_safari_inventory",fallback)
    assert module.autonomous_safari_options(runtime,observation,actions,world,include_capture_invocation=enabled)==("paid",)
    assert len(seen)==2 and all(k["complete_paid_session"] is True for k in seen)
    assert all(k.get("include_capture_invocation",False) is enabled for k in seen)
    if not enabled:assert all("include_capture_invocation"not in k for k in seen)
    assert actions.actions_executed==runtime.emulator.frame_count==0

@pytest.mark.parametrize("kind",[LivingDexOptionKind.ACQUIRE,LivingDexOptionKind.DEVELOP,LivingDexOptionKind.EVOLVE])
def test_unknown_and_non_safari_local_gate_stays_zero(kind):
    c=LivingDexOptionCandidate("ordinary",LivingDexOptionFeatures(kind,*([.1]*9)),LivingDexOptionAvailability.AVAILABLE)
    assert c.vector(context(),feature_version=13)[-6:]==(0.,)*6

def test_full_menu_V13_maps_recorded_candidate_to_same_binding(monkeypatch):
    kw=configure(monkeypatch,live)
    inv=live.build_red_live_safari_inventory(b"rom",(),context(),**kw,expose_all_areas=True,complete_paid_session=True,include_capture_invocation=True)
    options=build_red_live_option_set(situation=GoalSituation(0.,1.,0.,1.,0.,0.,0.,0.,0.),binding_set=empty_bindings(),
        supplements=inv.supplements,model_feature_version=13,ordering_seed_sha256="a"*64)
    assert options.menu.feature_version==12
    for i,c in enumerate(options.menu.candidates):
        assert c.binding_ref==options.binding(i).binding_ref
        assert c.capture_invocation==OptionCaptureInvocation(500,True)
        assert options.menu.candidate_vector(i,feature_version=13)[-2:]==(1.,5/6)
    with pytest.raises(ValueError):build_red_live_option_set(situation=options.situation,binding_set=empty_bindings(),
        supplements=inv.supplements,model_feature_version=9,ordering_seed_sha256="a"*64)

def test_fake_native_V13_wrapper_records_actual_model_identity(tmp_path,monkeypatch):
    from test_red_native_player import setup
    import pokemon_red_completion.red_native_player as native
    import pokemon_red_completion.red_autonomous_player as autonomous
    from pokemon_red_completion.living_dex_option_value import upgrade_option_value_model_for_complete_paid_capture
    args,executed=setup(tmp_path,monkeypatch)
    args["model"]=upgrade_option_value_model_for_complete_paid_capture(args["model"])
    args["source"]=dict(args["source"],partition="development")
    args["limits"]=replace(args["limits"],decisions=1,actions=2)
    def supplements(rt,actions,observed,bindings):
        b=rt.enumerator(actions).enumerate(observed).bindings[0]
        b=replace(b,binding_ref="paid-safari-test",kind=GoalKind.ACQUIRE_SPECIES)
        c=LivingDexOptionCandidate(b.binding_ref,LivingDexOptionFeatures(LivingDexOptionKind.ACQUIRE,*([.1]*9)),
            LivingDexOptionAvailability.AVAILABLE,capture_invocation=OptionCaptureInvocation(500,True))
        return(supplemental_live_option(b,c),)
    args["enumerate_supplements"]=supplements;seen=[];select=autonomous.select_red_live_option
    def record(model,options,*a,**k):seen.append(options);return select(model,options,*a,**k)
    monkeypatch.setattr(autonomous,"select_red_live_option",record)
    result=native.run_native_continuous_player(**args)
    assert result["model_decisions"]==1 and len(executed)==1 and len(seen)==1
    offered=next(c for c in seen[0].menu.candidates if c.capture_invocation is not None)
    assert offered.binding_ref in{b.binding_ref for b in seen[0].bindings}
    assert offered.capture_invocation==OptionCaptureInvocation(500,True)
    receipt=json.loads((args["output"]/"episode/plan.json").read_text())
    assert receipt["model_sha256"]==args["model"].model_sha256 and args["model"].feature_version>=13


def test_fullmenu_default_off_and_challenge_gates_untouched():
    import inspect
    from pokemon_red_completion.red_player_collection_options import player_collection_supplements
    assert inspect.signature(player_collection_supplements).parameters["include_capture_invocation"].default is False
    root=Path(__file__).resolve().parents[1]
    helper_path=root/"runtime_helpers/red_whole_player_inventory_20261006.py"
    if not helper_path.is_file():helper_path=root.parent/"helpers/red_whole_player_inventory_20261006.py"
    assert helper_path.is_file()
    helper=helper_path.read_text();tree=ast.parse(helper)
    assembly=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=="assembly")
    defaults=dict(zip((x.arg for x in assembly.args.kwonlyargs),assembly.args.kw_defaults,strict=True))
    assert isinstance(defaults["include_capture_invocation"],ast.Constant) and defaults["include_capture_invocation"].value is False
    assert "**({'include_capture_invocation': True} if include_capture_invocation else {})"in helper
    import pokemon_red_completion.red_autonomous_player as autonomous
    runtime=Path(autonomous.__file__).read_text()
    assert "or model.feature_version not in (7, 9, 10, 11, 15)"in runtime


@pytest.mark.parametrize("version", [5,6,7,8,9,10,11,13,14,15])
def test_configured_actor_V13_alone_enables_capture_metadata(tmp_path,monkeypatch,version):
    from test_red_player_configuration import config
    from pokemon_red_completion.red_player_configuration import assemble_configured_player
    from pokemon_red_completion.red_player_story_menu import NativeStoryBranchInventory
    import pokemon_red_completion.red_player_owned_machines as machines
    calls=[];machine_calls=[]
    monkeypatch.setattr(machines,"connect_move_change_inventory",lambda menu,**kwargs:machine_calls.append(kwargs))
    def assembly(*args,**kwargs):
        calls.append(kwargs)
        return b"unchanged",None,NativeStoryBranchInventory(lambda *_:empty_bindings(),lambda *_:()),{},{"partition":"development"}
    rom=tmp_path/"mock.rom";rom.write_bytes(b"mock")
    configuration=config();before=configuration.to_dict()
    payload,_,_,_,_=assemble_configured_player(NS(assembly=assembly,c=NS(ROM=rom)),configuration,tmp_path,tmp_path,
        plan_path=tmp_path/"plan.json",model_feature_version=version)
    expected=dict(plan_path=tmp_path/"plan.json",origin_sha=configuration.origin_sha256,
        origin_id=configuration.origin_id,continuation_loan_refs=frozenset(configuration.loanable_specimen_refs),
        **dict(configuration.assembly_flags))
    if version>=9:expected["include_level_workload"]=True
    if version>=13:expected["include_capture_invocation"]=True
    if version>=15:expected["include_matchup_observation"]=True
    assert calls==[expected]
    assert configuration.to_dict()==before and payload==b"unchanged"
    assert len(machine_calls)==(1 if version>=10 else 0)

@pytest.mark.parametrize("version", [None,True,4,12,16,"13",13.0])
def test_configured_capture_actor_bad_versions_refuse_before_backend(tmp_path,version):
    from test_red_player_configuration import config
    from pokemon_red_completion.red_player_configuration import assemble_configured_player
    backend=NS(assembly=lambda *a,**k:pytest.fail("unsupported version reached backend"))
    with pytest.raises(ValueError,match="supported model feature version"):
        assemble_configured_player(backend,config(),tmp_path,tmp_path,plan_path=tmp_path/"plan.json",
                                  model_feature_version=version)
