"""Construction scope cannot substitute for a sealed inference witness."""
import json
from dataclasses import replace, asdict
import pytest
from test_scoped_train_selector import case, guard
from pokemon_red_completion.red_scoped_train_composition import (
    ScopedTrainSelectorAuthentication, validate_selector_authentication,
    scoped_selector_declaration, validate_passive_train_sequence)
from pokemon_red_completion.red_native_player import NativePlayerLimits, NativeExecutionIdentity
from pokemon_red_completion.provenance import canonical_sha256
from hashlib import sha256

RECIPE = dict(force_resource_safety=False, include_live_pp_readiness=True,
              allow_collection_restoration=True, continue_safe_route_failures=False,
              story_milestone_commitment=True, story_kind_commitment=True)

def construction_case(tmp_path, sequence_horizon=None):
    args = case(tmp_path)
    work = json.loads(args["work_order_bytes"])
    work.update(native_session_recipe=RECIPE, native_limits=asdict(NativePlayerLimits()))
    if sequence_horizon is not None:
        work["sequence_horizon"] = sequence_horizon
        work["production_selector"] = scoped_selector_declaration(
            **{k:args[k]for k in ("model","head","objective_ref","challenge_ref","flags")},
            sequence_horizon=sequence_horizon,
        )
    args["work_order_bytes"] = json.dumps(work).encode()
    args["composition"] = replace(args["composition"], work_order_sha256=sha256(args["work_order_bytes"]).hexdigest())
    args["source"]["experiment_sha256"] = args["composition"].work_order_sha256
    request = ScopedTrainSelectorAuthentication.authenticate(**{k:v for k,v in args.items() if k != "session"})
    session = args["session"]
    session.execution = NativeExecutionIdentity("typed-selector", "case", request.document()["selector_sha256"], 17)
    plan = dict(schema="pokemon.red.native-continuous-player.v2", source=args["source"], execution=asdict(session.execution), automatic_fit=False, promotion=False,
                scoped_train_selector_authentication=request.document(),
                consequence_policy=dict(head_sha256=args["head"].model_sha256, branch_model_sha256=args["model"].model_sha256),
                limits=work["native_limits"], player_resource_configuration={k:RECIPE[k] for k in ("force_resource_safety", "include_live_pp_readiness")},
                **{k:v for k,v in RECIPE.items() if k not in ("force_resource_safety", "include_live_pp_readiness")},
                allow_greedy_branch_recovery=True, **args["flags"])
    if sequence_horizon is not None:
        plan["passive_sequence_horizon"] = sequence_horizon
    session.store.publish_sealed_record(session.execution.claim_id, kind="red_native_player_execution", record=plan)
    args["composition"].native_plan_path.write_text(json.dumps(plan))
    return args, request

def require_args(args):
    return {k:args[k] for k in ("source", "model", "head", "objective_ref", "challenge_ref", "flags")}

def test_construction_request_needs_sealed_zero_input_session_before_selection(tmp_path):
    args, request = construction_case(tmp_path)
    with pytest.raises(ValueError):
        guard(args, request)
    assert validate_selector_authentication(request, allow=True, train_inference_scope=None,
        native_recipe=RECIPE, limits=asdict(NativePlayerLimits()), **require_args(args))
    witness = request.bind(session=args["session"], **require_args(args))
    assert guard(args, witness)
    assert args["session"].actions.actions_executed == args["session"].controller.frames_executed == 0
    assert witness.document()["optimizer_admission"] is False

@pytest.mark.parametrize("fault", ["plan_flags", "plan_recipe", "plan_limits", "unsealed_plan", "late_input", "late_frame", "qualification", "head"])
def test_binding_rejects_configuration_or_boundary_changes_before_inference(tmp_path, monkeypatch, fault):
    args, request = construction_case(tmp_path)
    monkeypatch.setattr(type(args["model"]), "scores", lambda *a, **k: pytest.fail("model queried"))
    path=args["composition"].native_plan_path
    plan=json.loads(path.read_bytes())
    if fault == "plan_flags": plan["greedy_selection"]=False
    elif fault == "plan_recipe": plan["player_resource_configuration"]["force_resource_safety"]=True
    elif fault == "plan_limits": plan["limits"]["actions"] += 1
    elif fault == "unsealed_plan": plan["other_unsealed_change"]=True
    elif fault == "late_input": args["session"].actions.actions_executed=1
    elif fault == "late_frame": args["session"].controller.frames_executed=1
    elif fault == "qualification": (tmp_path/"qualification.json").write_text("{}")
    elif fault == "head": args["head"]=None
    path.write_text(json.dumps(plan))
    with pytest.raises((ValueError, KeyError, AttributeError)):
        request.bind(session=args["session"], **require_args(args))

@pytest.mark.parametrize("fault", ["fake", "allow", "old_scope", "source", "recipe", "limits"])
def test_construction_guard_rejects_untyped_or_changed_request(tmp_path, fault):
    args, request = construction_case(tmp_path)
    kw=dict(allow=True, train_inference_scope=None, native_recipe=dict(RECIPE),
            limits=asdict(NativePlayerLimits()), **require_args(args))
    if fault == "fake": request=request.document()
    elif fault == "allow": kw["allow"]=False
    elif fault == "old_scope": kw["train_inference_scope"]=True
    elif fault == "source": kw["source"]={**args["source"], "partition":"development"}
    elif fault == "recipe": kw["native_recipe"]["include_live_pp_readiness"]=False
    elif fault == "limits": kw["limits"]["seconds"] += 1
    with pytest.raises(ValueError): validate_selector_authentication(request, **kw)

def test_missing_exact_session_recipe_is_rejected(tmp_path):
    args=case(tmp_path)
    with pytest.raises(ValueError, match="exact production session recipe"):
        ScopedTrainSelectorAuthentication.authenticate(**{k:v for k,v in args.items() if k != "session"})

@pytest.mark.parametrize("sequence_horizon", [None, 2])
@pytest.mark.parametrize("fault", [None, "limits", "recipe", "untyped", "unscoped", "recording_mismatch"])
def test_actual_native_constructor_binds_exact_train_recipe_before_factory(tmp_path, fault, sequence_horizon):
    from types import SimpleNamespace as NS
    from test_red_player_lesson_runtime import Emulator
    from pokemon_red_completion.red_native_player import NativePlayerSession
    args, _ = construction_case(tmp_path, sequence_horizon)
    output=tmp_path/"constructed"
    args["composition"]=replace(args["composition"], native_plan_path=output/"native-plan.json")
    request=ScopedTrainSelectorAuthentication.authenticate(**{k:v for k,v in args.items()if k!="session"})
    emulator=Emulator();emulator.save_state_bytes=lambda:args["source_state"]
    calls=[]
    def factory(controller):
        calls.append(controller)
        return NS(emulator=controller, registration_policy=object())
    kw=dict(store=args["session"].store, emulator=emulator, runtime_factory=factory,
            source=args["source"], output=output, limits=NativePlayerLimits(),
            execution=NativeExecutionIdentity("actual-constructor", "case", request.document()["selector_sha256"], 17),
            combat_specimen_refs=(), battle_observer=lambda:None, target_cash=0,
            model_feature_version=16, consequence_head=args["head"],
            consequence_branch_model=args["model"], consequence_objective_ref=args["objective_ref"],
            consequence_challenge_ref=args["challenge_ref"], allow_greedy_branch_recovery=True,
            train_selector_authentication=request, **RECIPE, **args["flags"])
    if sequence_horizon is not None:kw["passive_sequence_horizon"]=sequence_horizon
    if fault=="recording_mismatch":
        kw["passive_sequence_horizon"] = 1 if sequence_horizon is None else None
    elif fault=="limits":kw["limits"]=replace(kw["limits"], actions=kw["limits"].actions+1)
    elif fault=="recipe":kw["include_live_pp_readiness"]=False
    elif fault=="untyped":kw["train_selector_authentication"]=request.document()
    elif fault=="unscoped":kw.pop("train_selector_authentication")
    if fault:
        with pytest.raises(ValueError):NativePlayerSession(**kw)
        assert not calls and not output.exists()
    else:
        session=NativePlayerSession(**kw)
        witness=request.bind(session=session, **require_args(args))
        assert guard(args,witness) and len(calls)==1
        assert session.force_resource_safety is False and session.allow_collection_restoration is True
    assert emulator.frame_count==0 and not emulator.pressed_buttons


@pytest.mark.parametrize("horizon", [1, 2, 4])
def test_passive_recording_is_pinned_and_grants_no_sequence_policy(tmp_path, horizon):
    args, request = construction_case(tmp_path, horizon)
    witness = request.bind(session=args["session"], **require_args(args))
    assert guard(args, witness)
    assert validate_passive_train_sequence(witness, horizon)
    assert witness.document()["sequence_collector"] is True
    assert witness.document()["sequence_policy"] is False
    assert witness.document()["optimizer_admission"] is False
    for bad in (None, True, horizon + 1):
        with pytest.raises(ValueError):
            validate_passive_train_sequence(witness, bad)
    with pytest.raises(ValueError):
        validate_passive_train_sequence(witness, horizon, sequence_policy=object())
    with pytest.raises(ValueError):
        validate_passive_train_sequence(witness, horizon, consequence_spec=object())
    assert args["session"].actions.actions_executed == 0


@pytest.mark.parametrize("horizon", [False, True, 0, 5, 1.0, "2"])
def test_invalid_passive_horizon_is_not_a_selector_capability(tmp_path, horizon):
    with pytest.raises(ValueError, match="passive TRAIN recording"):
        construction_case(tmp_path, horizon)


def test_v1_selector_does_not_gain_recording_authority(tmp_path):
    args, request = construction_case(tmp_path)
    assert request.document()["sequence_collector"] is False
    assert not validate_passive_train_sequence(request, 2)
    assert not validate_passive_train_sequence(None, 2)
    with pytest.raises(ValueError):
        validate_passive_train_sequence(request.document(), 2)
