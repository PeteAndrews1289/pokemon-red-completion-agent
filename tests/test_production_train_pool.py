"""Pool/codec tests; private immutable data opt-in, zero emulator construction.

POKEMON_PRODUCTION_TRAIN_COMPONENTS supplies state/envelope/progress/wild/story
file paths. Bytes are read only. Fake controller and synthetic event receipts do
not constitute native qualification or fit admission.
"""
import ast
from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
from types import SimpleNamespace as N

import pytest
from test_red_post_battle_strategy import episode

from pokemon_red_completion.battle_scenario_capture import build_battle_scenario_capture_payload,open_battle_scenario_capture
from pokemon_red_completion.executor import NativeLessonController
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_development_preparation_scope import DevelopmentPreparationScope
from pokemon_red_completion.red_development_story_scope import DevelopmentStoryScope
from pokemon_red_completion.red_gym_reward import MISTY_REWARD
from pokemon_red_completion.red_learned_trainer import FrozenTrainerBattler,TrainerPracticeThreeHeadModel,FROZEN_K_SHA256
from pokemon_red_completion.red_player_battle_history import NativeBattlerHistory
from pokemon_red_completion.red_production_train_admission import ProductionTrainAdmission,WILD_MODEL,WILD_CONTENT,STORY_MODEL,STORY_CONTENT
from pokemon_red_completion.red_production_train_readback import read_production_train_pool
from pokemon_red_completion.red_scoped_training_battlers import ScopedTrainingBattlers
from pokemon_red_completion.red_story_battle import StoryTrainerContract
from pokemon_red_completion.red_trainer_practice_log import TrainerPracticeEventLog
from pokemon_red_completion.scenario_lab import ScenarioPartition


@pytest.fixture
def components(tmp_path):
    configured=os.environ.get("POKEMON_PRODUCTION_TRAIN_COMPONENTS")
    if configured is None:
        pytest.skip("private immutable model/source bytes not supplied; no emulation required")
    paths={k:Path(v) for k,v in json.loads(configured).items()}
    state=paths["state"].read_bytes();envelope=paths["envelope"].read_bytes();progress=paths["progress"].read_bytes()
    capsule=dict(schema="pokemon.red.production-train-components.v1",source_state_sha256=sha256(state).hexdigest(),
        source_envelope_sha256=sha256(envelope).hexdigest(),assisted_progress_sha256=sha256(progress).hexdigest(),
        wild_model_sha256=WILD_MODEL,story_model_sha256=STORY_MODEL,wild_map_id=15,objective_id="defeat_misty")
    plan=json.dumps(dict(partition="train",production_train_components=capsule),sort_keys=True).encode()
    admission=ProductionTrainAdmission.authenticate(source_state=state,envelope_bytes=envelope,
        progress_bytes=progress,plan_bytes=plan,source_commit="a"*40)
    models={k:TrainerPracticeThreeHeadModel.from_dict(json.loads(paths[k].read_bytes())) for k in ("wild","story")}
    assert sha256(paths["wild"].read_bytes()).hexdigest()==WILD_MODEL
    assert sha256(paths["story"].read_bytes()).hexdigest()==STORY_MODEL
    assert canonical_sha256(models["wild"].to_dict())==WILD_CONTENT
    assert canonical_sha256(models["story"].to_dict())==STORY_CONTENT
    delegate=N(frame_count=0,save_state_bytes=lambda:state)
    port=NativeLessonController(delegate,maximum_frames=1000)
    reader=N(read=lambda:N(map_id=65,battle_state=0))
    wild_scope=DevelopmentPreparationScope(admission.source_state_sha256,admission.root_lineage_id,
        WILD_MODEL,WILD_CONTENT,admission.work_order_sha256,15,train_admission=admission)
    contract=StoryTrainerContract("defeat_misty","defeat_misty",65,(235,35,1),191,2079,((211,1),),2)
    story_scope=DevelopmentStoryScope(admission.source_state_sha256,admission.root_lineage_id,
        STORY_MODEL,STORY_CONTENT,admission.work_order_sha256,contract=contract,gym_reward=MISTY_REWARD,
        allow_learned_tactics=True,diagnostic_status_entry=True,screen_capped_status_moves=True,
        train_admission=admission)
    wild=FrozenTrainerBattler(port,models["wild"],tmp_path/"unused-wild","a"*40,
        admission.root_lineage_id,admission.source_state_sha256,{},model_sha256=WILD_MODEL,
        qualification_sha256=wild_scope.identity,source_partition=ScenarioPartition.TRAIN,
        development_preparation_scope=wild_scope)
    story=replace(wild,model=models["story"],model_sha256=STORY_MODEL,qualification_sha256=story_scope.identity,
        development_preparation_scope=None,development_story_scope=story_scope,
        pp_depleted_switch_screen=True,output=tmp_path/"unused-story")
    source=dict(partition="train",state_sha256=admission.source_state_sha256,
        origin_sha256=admission.source_origin_sha256,source_commit=admission.source_commit,
        experiment_sha256=admission.work_order_sha256)
    return N(admission=admission,wild=wild,story=story,reader=reader,source=source,
        contract=contract,delegate=delegate,port=port,tmp=tmp_path,plan=plan)


def bind(c):
    return ScopedTrainingBattlers.for_production_source(c.wild,c.story,admission=c.admission,
        source=c.source,output=c.tmp/"pool",reader=c.reader)


def publish(actor,reader,executor,**kwargs):
    wild=kwargs.get("wild_training",False);actor.calls+=1
    directory=actor.output/f"battle-{actor.calls:04d}";directory.mkdir(parents=True)
    initial,final=b"synthetic initial capture",b"synthetic final capture"
    (directory/"initial.state").write_bytes(initial)
    (directory/"initial.state.json").write_bytes(build_battle_scenario_capture_payload(
        capture_id=f"player-trainer-{actor.calls:04d}",root_lineage_id=actor.root_lineage_id,
        partition=actor.source_partition,state_bytes=initial,initial_observation_sha256="c"*64,
        source_commit=actor.source_commit,expected_map=15 if wild else 65,
        expected_battle_state=1 if wild else 2,source_state_sha256=actor.source_state_sha256))
    capture=open_battle_scenario_capture(directory/"initial.state",directory/"initial.state.json")
    row=episode();row.update(capture_id=capture.manifest.capture_id,manifest_sha256=capture.manifest_sha256)
    for decision in row["decisions"]:decision["observation"]["features"]["battle"]["kind"]="wild" if wild else "trainer"
    (directory/"outcome.json").write_text(json.dumps(row));(directory/"final.state").write_bytes(final)
    endpoint=dict(final_state_sha256=sha256(final).hexdigest(),outcome_sha256=canonical_sha256(row),
        model_sha256=actor.model_sha256,qualification_sha256=actor.qualification_sha256,
        actor_returned_win=False,outer_goal_verification_required=True)
    (directory/"endpoint.json").write_text(json.dumps(endpoint))
    scope=actor.development_preparation_scope if wild else actor.development_story_scope
    identity=dict(model_sha256=actor.model_sha256,qualification_sha256=actor.qualification_sha256,
        source_commit=actor.source_commit,root_lineage_id=actor.root_lineage_id,
        parent_state_sha256=actor.source_state_sha256,source_partition="train",fit_allowed=False,
        authority="scoped-wild-preparation-train" if wild else "scoped-exact-story-train",
        wild_training=wild,mechanics_aware_choices=True,diagnostic_stay_when_productive=False,
        allow_status_moves=True,allow_forced_struggle=not wild,
        **({"development_preparation_scope":scope.document()} if wild else
            {"development_story_scope":scope.document(),"pp_depleted_switch_screen":True,
             "train_story_contract":actor._train_story_document()}))
    log=TrainerPracticeEventLog(directory/"events",run_identity=identity);log.finish(endpoint)
    actor.session._delegate.frame_count+=10
    return "synthetic retained loss"


def play_wild(pool,c):
    c.reader.read=lambda:N(map_id=15,battle_state=1)
    return pool.wild.run_wild_training(c.reader,None,expected_map=15,timing=None,decision_guard=lambda _:None)


def play_story(pool,c):
    c.reader.read=lambda:N(map_id=65,battle_state=2)
    return pool.story(c.contract).continue_battle(c.reader,None,expected_map=65,timing=None,
        decision_guard=lambda _:None,story_authority=True)


def read_pool(pool,c,calls):
    return read_production_train_pool(pool.output,expected_declaration_sha256=pool.declaration_sha256,
        expected_admission=c.admission,source=c.source,expected_story_calls=calls)


def test_exact_components_registered_before_inputs_and_default_prototypes_unchanged(components):
    c=components;pool=bind(c)
    assert pool.wild.model_sha256==WILD_MODEL and pool.story(c.contract).model_sha256==STORY_MODEL
    assert c.wild.calls==c.story.calls==0 and c.delegate.frame_count==0
    assert pool.story(c.contract).train_story_contract==c.contract
    assert read_pool(pool,c,0).episodes==()


@pytest.mark.parametrize("fault",["fallback_k","foreign_session","development","wrong_plan","wrong_source","changed_pp"])
def test_bad_component_binding_rejects_before_native_reads_or_output(components,fault):
    c=components
    if fault=="fallback_k":c.wild.model_sha256=FROZEN_K_SHA256
    elif fault=="foreign_session":c.story.session=object()
    elif fault=="development":c.source["partition"]="development"
    elif fault=="wrong_plan":c.source["experiment_sha256"]="f"*64
    elif fault=="wrong_source":c.source["state_sha256"]="f"*64
    else:c.story.pp_depleted_switch_screen=False
    with pytest.raises(ValueError):bind(c)
    assert not (c.tmp/"pool").exists() and c.delegate.frame_count==0


def test_registered_reader_cannot_be_replaced(components):
    c=components;pool=bind(c)
    with pytest.raises(ValueError,match="registered reader"):
        pool.wild._play(object(),None)
    assert c.delegate.frame_count==0 and not tuple(pool.output.glob("battle-*"))


def test_wild_prefix_then_exact_story_has_ordered_readback(components,monkeypatch):
    c=components;pool=bind(c);monkeypatch.setattr(FrozenTrainerBattler,"_play",publish)
    play_wild(pool,c);prefix=read_pool(pool,c,0)
    assert len(prefix.episodes)==1 and prefix.episodes[0]["scope"]=="wild"
    play_story(pool,c);complete=read_pool(pool,c,1)
    assert [r["actor"] for r in complete.invocations]==[1,0]
    assert pool.history() is not None and c.delegate.frame_count==20
    with pytest.raises(ValueError,match="story call census"):read_pool(pool,c,0)


@pytest.mark.parametrize("fault",["missing_start","frame_overlap","extra_actor","model","scope","event"])
def test_readback_rejects_missing_or_tampered_actor_evidence(components,monkeypatch,fault):
    c=components;pool=bind(c);monkeypatch.setattr(FrozenTrainerBattler,"_play",publish)
    play_wild(pool,c);play_story(pool,c)
    if fault=="missing_start":(pool.output/"battle-000-start.json").rename(pool.output/"not-start.json")
    elif fault=="extra_actor":(pool.output/"actor-002").mkdir()
    else:
        path=pool.output/("battle-001-start.json" if fault=="frame_overlap" else "declaration.json")
        if fault=="event":path=pool.output/"actor-000/battle-0001/events/event-00001.json"
        d=json.loads(path.read_bytes())
        if fault=="frame_overlap":d["before_frame"]=0
        elif fault=="model":d["actors"][0]["model_sha256"]=FROZEN_K_SHA256
        elif fault=="scope":d["actors"][0]["production_scope"]["contract"]["defeated_event"]=192
        else:d["payload"]["identity"]["source_partition"]="development"
        path.write_text(json.dumps(d))
    with pytest.raises(ValueError):read_pool(pool,c,1)


def test_existing_helper_pool_hook_reuses_one_registered_runtime(components):
    c=components
    helper=Path(__file__).resolve().parents[1]/"runtime_helpers/red_whole_player_inventory_20261006.py"
    if not helper.exists():
        helper=Path(__file__).resolve().parents[1]/"staged/runtime_helpers/red_whole_player_inventory_20261006.py"
    # Staged tests resolve to staged/, and integrated tests resolve to Code/.
    tree=ast.parse(helper.read_text());assembly=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="assembly")
    hook=next(n for n in assembly.body if isinstance(n,ast.FunctionDef) and n.name=="ensure_training_pool")
    runtime=N(emulator=c.port,reader=c.reader,adapter=object());holder=dict(actor=c.wild,runtime=runtime,
        training_reader=c.reader,initial_battle=None,scoped_actors={})
    namespace=dict(training_admission=c.admission,holder=holder,source=c.source,output=c.tmp,
        MISTY_REWARD=MISTY_REWARD,NativeBattlerHistory=NativeBattlerHistory,
        preparation_actor=lambda map_id,**kwargs:c.wild,leader_actor=lambda reward,rt,**kwargs:c.story)
    exec(compile(ast.Module(body=[hook],type_ignores=[]),str(helper),"exec"),namespace)
    ensure=namespace["ensure_training_pool"];pool=ensure(runtime)
    assert ensure(runtime) is pool and holder["scoped_actors"]["defeat_misty"][0].model_sha256==STORY_MODEL
    wrapper=N(emulator=c.port,reader=c.reader,adapter=runtime.adapter,evolution_stop_requested=lambda:False)
    assert ensure(wrapper) is pool  # NativePlayerSession may shallow-replace its runtime.
    for foreign in (N(emulator=object(),reader=c.reader,adapter=runtime.adapter),
                    N(emulator=c.port,reader=c.reader,adapter=object())):
        with pytest.raises(ValueError,match="reader/runtime"):ensure(foreign)
    runtime.reader=object()
    with pytest.raises(ValueError,match="reader/runtime"):ensure(runtime)
    assert c.delegate.frame_count==0


@pytest.mark.parametrize("fault",[None,"different_parent","different_target","not_attempted","interrupted","outcome","frames","extra_wild_tail","wild_outside_phase"])
def test_consequence_bridge_binds_exact_native_target_and_preserves_failed_prefix_rejection(
    components,monkeypatch,fault,
):
    from pokemon_red_completion import red_challenge_consequence as rcc
    from pokemon_red_completion.player_challenge_consequence import ChallengeConsequence,ConsequenceExample
    from pokemon_red_completion.living_dex_option_value import option_feature_names
    from pokemon_red_completion.red_production_train_readback import load_production_train_challenge_consequence
    c=components;pool=bind(c);monkeypatch.setattr(FrozenTrainerBattler,"_play",publish)
    play_wild(pool,c);play_story(pool,c);e=read_pool(pool,c,1).episodes[-1]
    row=ConsequenceExample("c"*64,c.admission.source_origin_sha256,
        (0.0,)*len(option_feature_names(15)),
        ChallengeConsequence(True,False,2,20,0,0,0,feedback_version=2,
            initial_goal_failed=False,challenge_progress=0),None,provenance="synthetic",
        feedback_version=2,feature_version=15)
    # The core authenticated RCC loader is separately covered. Here its
    # synthetic unit result isolates target/event/history composition only.
    monkeypatch.setattr(rcc,"load_challenge_consequence",lambda *a,**k:row)
    plan=dict(source=c.source,spec=dict(challenge_target=dict(kind="events",map_id=65,events=[191])),
        preparation_parent_witness=dict(parent_index=0,bindings=[dict(story_objective_ref="defeat_misty")]))
    phase=dict(battle="lost",challenge_episode=e["outcome"],before=dict(frames=10),after=dict(frames=20))
    preparation=dict(before=dict(frames=0),after=dict(frames=10))
    result=dict(interrupted=False,phases=[preparation,phase])
    if fault=="different_parent":plan["preparation_parent_witness"]["bindings"][0]["story_objective_ref"]="defeat_erika"
    elif fault=="different_target":plan["spec"]["challenge_target"]["events"]=[192]
    elif fault=="not_attempted":row=replace(row,outcome=ChallengeConsequence(False,False,2,20,0,0,0,
        feedback_version=2,initial_goal_failed=True,challenge_progress=0))
    elif fault=="interrupted":result["interrupted"]=True
    elif fault=="outcome":phase["battle"]="won"
    elif fault=="frames":phase["after"]["frames"]=19
    elif fault=="extra_wild_tail":play_wild(pool,c)
    elif fault=="wild_outside_phase":preparation["after"]["frames"]=9
    class Store:
        def find_sealed_record(self,key,**kwargs):
            return N(read=lambda:result if key.startswith("rcc-result-") else plan)
    kwargs=dict(declaration_sha256="c"*64,result_sha256="d"*64,scoped_output=pool.output,
        expected_scoped_declaration_sha256=pool.declaration_sha256,expected_admission=c.admission)
    if fault:
        with pytest.raises(ValueError):load_production_train_challenge_consequence(Store(),**kwargs)
    else:
        loaded=load_production_train_challenge_consequence(Store(),**kwargs)
        assert loaded.row is row and loaded.invocation_ordinal==1 and loaded.actor_index==0
        assert loaded.row.provenance=="synthetic"  # Never a fit-eligible native proof from a unit fixture.


@pytest.mark.parametrize("admission",[None,object()])
def test_helper_cannot_fall_back_to_k_under_explicit_train(admission):
    helper=Path(__file__).resolve().parents[1]/"runtime_helpers/red_whole_player_inventory_20261006.py"
    tree=ast.parse(helper.read_text());assembly=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="assembly")
    hook=next(n for n in assembly.body if isinstance(n,ast.FunctionDef) and n.name=="preparation_actor")
    base=object();namespace=dict(training_admission=admission,
        d=N(prior=N(doc=lambda _:{})),declared=Path("unused"),holder=dict(actor=base))
    exec(compile(ast.Module(body=[hook],type_ignores=[]),str(helper),"exec"),namespace)
    if admission is None:assert namespace["preparation_actor"](15) is base
    else:
        with pytest.raises(ValueError,match="declared component"):namespace["preparation_actor"](15)


@pytest.mark.parametrize("role",["wild","story"])
def test_real_battler_preinput_identity_matches_admitted_profile(components,monkeypatch,role):
    from pokemon_red_completion import red_learned_trainer as actual
    c=components;pool=bind(c);captured=[]
    class CapturedIdentity(RuntimeError):pass
    def capture(directory,*,run_identity):
        captured.append(run_identity)
        raise CapturedIdentity("deliberate zero-input pre-capture stop")
    # Execute actual _play admission and identity construction, intercepting
    # immediately before capture/menu input. No synthetic publisher here.
    monkeypatch.setattr(actual,"TrainerPracticeEventLog",capture)
    c.reader.read_active_trainer_identity=lambda:(235,35,1)
    with pytest.raises(CapturedIdentity):
        (play_wild if role=="wild" else play_story)(pool,c)
    identity=captured[0]
    assert identity["source_partition"]=="train" and identity["fit_allowed"] is False
    assert identity["model_sha256"]==(WILD_MODEL if role=="wild" else STORY_MODEL)
    assert identity["authority"]==("scoped-wild-preparation-train" if role=="wild" else "scoped-exact-story-train")
    assert identity["allow_status_moves"] is True
    assert identity["allow_forced_struggle"] is (role=="story")
    assert identity["wild_training"] is (role=="wild")
    assert identity["mechanics_aware_choices"] is True
    assert identity["diagnostic_stay_when_productive"] is False
    assert identity.get("pp_depleted_switch_screen",False) is (role=="story")
    if role=="story":
        assert canonical_sha256(identity["train_story_contract"])==canonical_sha256(
            pool._actors[0]._train_story_document())
    assert c.delegate.frame_count==0
