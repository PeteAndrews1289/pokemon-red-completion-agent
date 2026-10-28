"""ROM-free guard tests against actual source, with explicitly synthetic type spies.

No production package/model is imported. The new witness module and existing
guard function bodies execute under a private package alias. Synthetic byte
hashes stand in for the immutable source/context only within individual tests;
the literal production hashes are independently asserted before substitution.
Existing ProductionTrainAdmission catalogue correctness is outside these spies.
"""
from pathlib import Path
import ast
import copy
import hashlib
import importlib.util
import itertools
import json
import math
import re
import sys
import types
import unittest
from collections.abc import Mapping

_SERIAL=itertools.count()
def source_root():
    for parent in Path(__file__).resolve().parents:
        for candidate in [parent/'src/pokemon_red_completion',parent/'Code/src/pokemon_red_completion']:
            if (candidate/'red_production_train_inference.py').is_file():return candidate
    raise RuntimeError('actual project source not found')

def digest(value):return hashlib.sha256(value).hexdigest()
def packed(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()

class Harness:
    def __init__(self,case):
        self.case=case;self.source=source_root();self.alias='_train_inference_spy_'+str(next(_SERIAL));self.names=[];self.calls=dict(queries=0,fits=0,native=0,producer_auth=0)
        package=types.ModuleType(self.alias);package.__path__=[];self.register(self.alias,package)
        owner=self
        class Model:
            feature_version=15
            model_sha256='4c2b16a21362e17bddc2f861a579e420bd0096dbca24b66058b52391a2b0c62a'
            def predict(self,*a,**k):owner.calls['queries']+=1;raise AssertionError('model forward forbidden')
            scores=predict
            def fit(self,*a,**k):owner.calls['fits']+=1;raise AssertionError('fit forbidden')
        class Head:
            feature_version=15;feedback_version=2;provenance='native_train';model_sha256='e'*64;cash_prediction='independent'
            predict=Model.predict;scores=Model.predict;fit=Model.fit
        class Admission:
            derived_source_proof=None;wild_model_sha256='3b187fc6bfb46dd0fd062f0d14ff5fadffe353347d4e94a2124bdbaba988c4b3'
            wild_component_proof=object();source_origin_sha256='b'*64;source_commit='c'*64
            identity='d'*64
            def document(self):return dict(source_state_sha256=self.source_state_sha256,source_origin_sha256=self.source_origin_sha256,source_commit=self.source_commit,work_order_sha256=self.work_order_sha256,wild_model_sha256=self.wild_model_sha256)
            def require_work_order(self,data):
                if digest(data)!=self.work_order_sha256:raise ValueError('real-shaped workorder hash mismatch')
            def require_source_context(self,state,context):
                if digest(state)!=self.source_state_sha256 or digest(context)!=owner.module.CONTEXT_SHA256:raise ValueError('real-shaped source/context mismatch')
            @classmethod
            def authenticate(cls,**kwargs):
                owner.calls['producer_auth']+=1
                expected=dict(source_state=owner.state,envelope_bytes=owner.envelope,progress_bytes=owner.progress,plan_bytes=owner.plan_bytes,source_commit=owner.admission.source_commit,wild_component_proof=owner.admission.wild_component_proof)
                if kwargs!=expected:raise ValueError('producer stub rejects unauthenticated input bytes')
                return owner.reauthenticated_admission
        self.Model,self.Head,self.Admission=Model,Head,Admission
        for name,attribute,value in [('living_dex_option_value','LivingDexOptionValueModel',Model),('player_challenge_consequence','ChallengeConsequenceHead',Head),('red_production_train_admission','ProductionTrainAdmission',Admission)]:
            module=types.ModuleType(self.alias+'.'+name);setattr(module,attribute,value);self.register(module.__name__,module)
        name=self.alias+'.red_production_train_inference';spec=importlib.util.spec_from_file_location(name,self.source/'red_production_train_inference.py');module=importlib.util.module_from_spec(spec);self.register(name,module);spec.loader.exec_module(module);self.module=module
        case.assertEqual(module.SOURCE_SHA256,'0e691fe7b9c2624cc496ff07170c925c51fab3726245cc1547c887a69724575d');case.assertEqual(module.CONTEXT_SHA256,'688a6016e7cdc8ab97a66873421b27fe0913327ac8aa59ce9d00ff71747cb5da')
        self.model,self.head=Model(),Head();self.state=b'synthetic immutable TRAIN state, not a ROM or save';self.envelope=b'synthetic authenticated envelope';self.progress=b'synthetic authenticated progress'
        self.context=dict(schema='pokemon.red.native-player-continuation.v1',state_sha256=digest(self.state),grants_new_budget=False,fit_allowed=False,spent=dict(actions=0,frames=0,decisions=0,heals=0,cash_debits=0,seconds=7.0))
        self.context_bytes=packed(self.context);module.SOURCE_SHA256=digest(self.state);module.CONTEXT_SHA256=digest(self.context_bytes)
        self.admission=Admission();self.admission.source_state_sha256=module.SOURCE_SHA256;self.reauthenticated_admission=self.admission
        self.plan=dict(partition='train',automatic_fit=False,production_train_consequence_inference=module.train_inference_declaration(self.model,self.head));self.refresh_plan()
        self.guard=self.load_branch_guards()
    def register(self,name,module):sys.modules[name]=module;self.names.append(name)
    def close(self):
        self.case.assertEqual({k:self.calls[k]for k in ['queries','fits','native']},dict(queries=0,fits=0,native=0))
        for name in reversed(self.names):sys.modules.pop(name,None)
    def refresh_plan(self):
        self.plan_bytes=packed(self.plan);self.admission.work_order_sha256=digest(self.plan_bytes)
        self.spec=dict(partition='train',state_sha256=self.module.SOURCE_SHA256,origin_sha256=self.admission.source_origin_sha256,source_commit=self.admission.source_commit,experiment_sha256=self.admission.work_order_sha256,training_admission=self.admission.identity)
    def authenticate(self,**overrides):
        arguments=dict(admission=self.admission,source=self.spec,source_state=self.state,context_bytes=self.context_bytes,envelope_bytes=self.envelope,progress_bytes=self.progress,plan_bytes=self.plan_bytes,model=self.model,head=self.head);arguments.update(overrides)
        return self.module.ProductionTrainConsequenceInference.authenticate(**arguments)
    def load_branch_guards(self):
        text=(self.source/'red_consequence_choice.py').read_text();tree=ast.parse(text);names={'branch_recovery_objectives','valid_branch_recovery_objectives','branch_recovery_scope_ref','branch_recovery_identity','validate_greedy_branch_recovery_scope'}
        nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name in names]
        module=types.ModuleType(self.alias+'.red_consequence_choice');module.__package__=self.alias;module.LivingDexOptionValueModel=self.Model;module.ChallengeConsequenceHead=self.Head;module.canonical_sha256=lambda value:digest(packed(value));self.register(module.__name__,module)
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'actual_branch_guard_functions','exec'),module.__dict__)
        return module
    def branch(self,scope=None,**overrides):
        arguments=dict(allow=True,greedy_selection=True,source=self.spec,model=self.model,head=self.head,objective_ref='defeat_misty',challenge_ref='defeat_misty',refine_preparation=True,defer_unbound_preparation=True,allow_singleton_parent_support=True,train_inference_scope=scope);arguments.update(overrides)
        return self.guard.validate_greedy_branch_recovery_scope(**arguments)
    def probe(self,kind,scope,**overrides):
        """Execute untouched actual guard prefixes, before storage or native work."""
        file='red_native_player.py'if kind!='auto'else'red_autonomous_player.py';tree=ast.parse((self.source/file).read_text())
        class Limits:
            seconds=300;actions=16000;frames=1600000;decisions=8;heals=64;cash_debits=None
        class Execution:
            def __init__(self,sha):self.model_sha256=sha
        class Memory:pass
        class Curriculum:pass
        def forbidden(*a,**k):self.calls['native']+=1;raise AssertionError('probe reached native/runtime/snapshot tail')
        namespace=dict(__package__=self.alias,math=math,re=re,sha256=hashlib.sha256,NativePlayerLimits=Limits,NativeExecutionIdentity=Execution,NativePlayerCurriculum=Curriculum,GoalSearchMemory=Memory,validate_settlement_refinement_scope=lambda **k:False,cast=lambda tp,v:v,Mapping=Mapping,Path=Path,LivingDexOptionValueModel=self.Model,ChallengeConsequenceHead=self.Head)
        if kind=='session':
            cls=next(n for n in tree.body if isinstance(n,ast.ClassDef)and n.name=='NativePlayerSession');node=next(n for n in cls.body if isinstance(n,ast.FunctionDef)and n.name=='__init__');cut=next(i for i,n in enumerate(node.body)if isinstance(n,ast.Assign)and'self.store'in ast.unparse(n))
            branch=self.guard.branch_recovery_identity(self.model.model_sha256,self.head.model_sha256,'defeat_misty',greedy_selection=True,refine_preparation=True,defer_unbound_preparation=True,allow_singleton_parent_support=True)
            args=dict(self=types.SimpleNamespace(),store=None,emulator=types.SimpleNamespace(save_state_bytes=lambda:self.state),runtime_factory=forbidden,source=self.spec,execution=Execution(branch),output=Path('/unused'),limits=Limits(),combat_specimen_refs=(),battle_observer=forbidden,target_cash=0,model_feature_version=15,collection_teacher_setup_receipt=self.admission.identity,consequence_head=self.head,consequence_challenge_ref='defeat_misty',consequence_objective_ref='defeat_misty',consequence_branch_model=self.model,greedy_selection=True,allow_greedy_branch_recovery=True,refine_preparation=True,defer_unbound_preparation=True,allow_singleton_parent_support=True,train_inference_scope=scope)
        else:
            function='run_native_continuous_player'if kind=='continuous'else'run_autonomous_options';node=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name==function)
            message='highest-score selection requires separate native DEVELOPMENT scope'if kind=='continuous'else'highest-score selection requires separate continuous DEVELOPMENT scope'
            cut=next(i+1 for i,n in enumerate(node.body)if isinstance(n,ast.If)and any(isinstance(x,ast.Constant)and x.value==message for x in ast.walk(n)))
            common=dict(model=self.model,seed=1,output=Path('/unused'),consequence_head=self.head,consequence_challenge_ref='defeat_misty',consequence_objective_ref='defeat_misty',greedy_selection=True,allow_greedy_branch_recovery=True,refine_preparation=True,defer_unbound_preparation=True,allow_singleton_parent_support=True,train_inference_scope=scope)
            if kind=='continuous':args=dict(common,store=None,emulator=None,runtime_factory=forbidden,source=self.spec,run_id='synthetic',arm_id='student',limits=Limits(),combat_specimen_refs=(),battle_observer=forbidden,target_cash=0)
            else:args=dict(common,snapshot=forbidden,observe=forbidden,provenance=dict(source=self.spec),continuous_player=True,maximum_cash_spent=None)
        node=copy.deepcopy(node);node.name='actual_guard_prefix';node.body=node.body[:cut]+[ast.Return(value=ast.Constant(value='accepted'))]
        prefix=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),node],type_ignores=[]);ast.fix_missing_locations(prefix);exec(compile(prefix,'untouched_actual_guard_prefix','exec'),namespace)
        args.update(overrides);return namespace['actual_guard_prefix'](**args)

class ProductionTrainInferenceGuardSpies(unittest.TestCase):
    def setUp(self):self.h=Harness(self);self.addCleanup(self.h.close)
    def test_authenticates_original_scope_reauthenticates_producer(self):
        scope=self.h.authenticate();self.assertEqual(self.h.calls['producer_auth'],1);self.assertTrue(self.h.branch(scope));self.assertEqual(scope.document()['cumulative_spent'],self.h.context['spent'])
    def test_constructor_decoded_dict_subclass_and_unsealed_object_rejected(self):
        cls=self.h.module.ProductionTrainConsequenceInference
        with self.assertRaises(ValueError):cls({},admission=self.h.admission,plan_bytes=self.h.plan_bytes)
        for scope in [{},True,object(),object.__new__(cls)]:
            with self.subTest(scope=type(scope).__name__),self.assertRaises(ValueError):self.h.branch(scope)
        class Child(cls):pass
        with self.assertRaises(ValueError):self.h.branch(object.__new__(Child))
    def test_document_is_defensive_and_frozen(self):
        scope=self.h.authenticate();before=scope.identity;document=scope.document();document['work_order_sha256']='0'*64;self.assertEqual(scope.identity,before);self.assertTrue(self.h.branch(scope))
        with self.assertRaises(AttributeError):scope._canonical_bytes=b'{}'
    def test_wrong_actual_source_context_and_metadata_bytes_rejected(self):
        for field,value in [('source_state',b'earned or wrong tail'),('context_bytes',b'wrong context'),('envelope_bytes',b'wrong envelope'),('progress_bytes',b'wrong progress')]:
            with self.subTest(field=field),self.assertRaises(ValueError):self.h.authenticate(**{field:value})
    def test_wrong_source_specs_and_admission_rejected(self):
        for field,value in [('partition','development'),('state_sha256','0'*64),('origin_sha256','0'*64),('source_commit','0'*64),('experiment_sha256','0'*64),('training_admission','0'*64)]:
            source=dict(self.h.spec);source[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.h.authenticate(source=source)
        with self.assertRaises(ValueError):self.h.authenticate(admission=types.SimpleNamespace())
    def test_derived_source_or_wrong_wild_component_rejected(self):
        self.h.admission.derived_source_proof=object()
        with self.assertRaises(ValueError):self.h.authenticate()
        self.h.admission.derived_source_proof=None;self.h.admission.wild_model_sha256='0'*64
        with self.assertRaises(ValueError):self.h.authenticate()
    def test_wrong_parent_head_modes_and_nonindependent_cash_rejected(self):
        for field,value in [('feature_version',14),('model_sha256','0'*64)]:
            model=self.h.Model();setattr(model,field,value)
            with self.subTest(parent=field),self.assertRaises(ValueError):self.h.authenticate(model=model)
        for field,value in [('feature_version',14),('feedback_version',1),('provenance','synthetic'),('cash_prediction','certified_single_trainer_v1')]:
            head=self.h.Head();setattr(head,field,value)
            with self.subTest(head=field),self.assertRaises(ValueError):self.h.authenticate(head=head)
    def test_changed_head_source_branch_after_authentication_rejected(self):
        scope=self.h.authenticate();other=self.h.Head();other.model_sha256='f'*64
        with self.assertRaises(ValueError):self.h.branch(scope,head=other)
        for field,value in [('objective_ref','other'),('challenge_ref','other'),('objective_ref',('defeat_misty','other'))]:
            with self.subTest(field=field),self.assertRaises(ValueError):self.h.branch(scope,**{field:value})
        source=dict(self.h.spec,partition='development')
        with self.assertRaises(ValueError):self.h.branch(scope,source=source)
    def test_plan_flags_declaration_and_stored_workorder_are_bound(self):
        for field,value in [('automatic_fit',True),('partition','development'),('production_train_consequence_inference',{})]:
            before=copy.deepcopy(self.h.plan);self.h.plan[field]=value;self.h.refresh_plan()
            with self.subTest(field=field),self.assertRaises(ValueError):self.h.authenticate()
            self.h.plan=before;self.h.refresh_plan()
        scope=self.h.authenticate();self.h.admission.work_order_sha256='0'*64
        with self.assertRaises(ValueError):self.h.branch(scope)
    def test_context_cannot_grant_budget_or_fit_even_with_synthetic_hash_updated(self):
        for field in ['grants_new_budget','fit_allowed']:
            context=dict(self.h.context);context[field]=True;encoded=packed(context);self.h.module.CONTEXT_SHA256=digest(encoded)
            with self.subTest(field=field),self.assertRaises(ValueError):self.h.authenticate(context_bytes=encoded)
    def test_default_none_retains_train_rejection_and_development_admission(self):
        self.assertFalse(self.h.module.validate_train_consequence_inference(None,source={},model=None,head=None,objective_ref=None,challenge_ref=None))
        with self.assertRaises(ValueError):self.h.branch(None)
        self.assertIsNone(self.h.branch(None,source=dict(self.h.spec,partition='development')))
        self.assertIsNone(self.h.guard.validate_greedy_branch_recovery_scope(allow=False,greedy_selection=False,source=self.h.spec,model=None,head=None,objective_ref=None,challenge_ref=None))
    def test_explicit_greedy_branch_permission_still_required(self):
        scope=self.h.authenticate()
        for flags in [dict(allow=False),dict(greedy_selection=False),dict(allow='yes')]:
            with self.subTest(flags=flags),self.assertRaises(ValueError):self.h.branch(scope,**flags)
    def test_actual_native_session_guard_accepts_scope_rejects_none_and_spec(self):
        scope=self.h.authenticate();self.assertEqual(self.h.probe('session',scope),'accepted')
        for kwargs in [dict(train_inference_scope=None),dict(consequence_spec=object())]:
            with self.subTest(kwargs=list(kwargs)),self.assertRaises(ValueError):self.h.probe('session',scope,**kwargs)
    def test_actual_continuous_guard_rejects_recorder_sequence_settlement(self):
        scope=self.h.authenticate();self.assertEqual(self.h.probe('continuous',scope),'accepted')
        for kwargs in [dict(train_inference_scope=None),dict(consequence_spec=object()),dict(sequence_policy=object()),dict(sequence_horizon=2),dict(settle_existing_blackout=True)]:
            with self.subTest(kwargs=list(kwargs)),self.assertRaises(ValueError):self.h.probe('continuous',scope,**kwargs)
    def test_actual_autonomous_guard_rejects_sequence_and_noncontinuous(self):
        scope=self.h.authenticate();self.assertEqual(self.h.probe('auto',scope),'accepted')
        for kwargs in [dict(train_inference_scope=None),dict(sequence_collector=object()),dict(sequence_policy=object()),dict(continuous_player=False),dict(continue_safe_route_failures=True),dict(exploration_mix=.1)]:
            with self.subTest(kwargs=list(kwargs)),self.assertRaises(ValueError):self.h.probe('auto',scope,**kwargs)
    def test_all_five_actual_call_chain_edges_propagate_same_optin(self):
        edges=[]
        for file in ['red_native_player.py','red_autonomous_player.py']:
            tree=ast.parse((self.h.source/file).read_text())
            for call in ast.walk(tree):
                if isinstance(call,ast.Call)and any(k.arg=='train_inference_scope'for k in call.keywords):
                    keyword=next(k for k in call.keywords if k.arg=='train_inference_scope');self.assertIsInstance(keyword.value,ast.Name);self.assertEqual(keyword.value.id,'train_inference_scope');edges.append(ast.unparse(call.func))
        self.assertEqual(sorted(edges),sorted(['validate_greedy_branch_recovery_scope']*3+['NativePlayerSession','run_autonomous_options']))

if __name__=='__main__':unittest.main(verbosity=2)
