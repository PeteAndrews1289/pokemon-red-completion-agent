"""Pure readback for explicitly admitted production TRAIN component evidence.

No execution, partition conversion, fitting, continuation or worker-status claim.
The caller authenticates closed processes/controls, frozen package and source.
"""
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
import json

from .battle_scenario_capture import open_battle_scenario_capture
from .provenance import canonical_sha256
from .red_development_preparation_scope import DevelopmentPreparationScope
from .red_development_story_scope import DevelopmentStoryScope
from .red_production_train_admission import ProductionTrainAdmission, WILD_MODEL, STORY_MODEL
from .red_trainer_practice_log import verify_trainer_practice_event_log
from .scenario_lab import ScenarioPartition


def _read(path):
    return json.loads(Path(path).read_bytes())


def _require(condition, reason):
    if not condition:
        raise ValueError("production TRAIN pool " + reason)


@dataclass(frozen=True)
class ProductionTrainPoolReadback:
    declaration: dict
    invocations: tuple[dict, ...]
    episodes: tuple[dict, ...]


def read_production_train_pool(scoped_output, *, expected_declaration_sha256,
                               expected_admission, source, expected_story_calls):
    """Verify every registered actor call, including a zero-story TRAIN prefix.

    expected_story_calls=0 supports a separately authenticated paired phase
    export. A prefix is never implicitly a completed challenge or fit row.
    """
    _require(type(expected_admission) is ProductionTrainAdmission, "needs typed admission")
    _require(type(expected_story_calls) is int and expected_story_calls in (0, 1), "story census differs")
    admission = expected_admission
    _require(type(source) is dict and source.get("partition") == "train"
        and source.get("state_sha256") == admission.source_state_sha256
        and source.get("origin_sha256") == admission.source_origin_sha256
        and source.get("source_commit") == admission.source_commit
        and source.get("experiment_sha256") == admission.work_order_sha256,
        "source does not match admitted TRAIN plan")
    root=Path(scoped_output)
    declaration=_read(root/"declaration.json")
    _require(canonical_sha256(declaration)==expected_declaration_sha256, "declaration digest differs")
    _require(declaration.get("schema")=="pokemon.red.scoped-train-battlers.v2"
        and declaration.get("source_partition")=="train"
        and declaration.get("source_state_sha256")==admission.source_state_sha256
        and declaration.get("source_commit")==admission.source_commit
        and declaration.get("root_lineage_id")==admission.root_lineage_id
        and declaration.get("experiment_sha256")==admission.work_order_sha256
        and declaration.get("native_plan_sha256")==admission.work_order_sha256
        and declaration.get("fit_allowed") is False and declaration.get("authority_promotion") is False
        and canonical_sha256(declaration.get("production_admission"))==canonical_sha256(admission.document()),
        "declaration source/authority differs")
    actors=declaration.get("actors")
    _require(type(actors) is list and len(actors)==2, "must register exactly story and wild actors")
    scopes=[]
    for i,actor in enumerate(actors):
        role="story" if i==0 else "wild"
        _require(type(actor.get("index")) is int and actor["index"]==i
            and actor.get("scope")==role and actor.get("train_risk_story_scope") is None,
            "actor role or index differs")
        document=actor.get("production_scope")
        _require(type(document) is dict, "actor scope is missing")
        if role=="story":
            scope=DevelopmentStoryScope.from_document(document, train_admission=admission)
            _require(canonical_sha256(actor.get("contract"))==canonical_sha256(asdict(scope.contract)),
                     "story contract differs")
        else:
            values=dict(document)
            values["train_admission"]=ProductionTrainAdmission.from_document(values["train_admission"],
                **({"derived_source_proof": admission.derived_source_proof}
                   if getattr(admission,"derived_source_proof",None) is not None else {}),
                **({"wild_component_proof": admission.wild_component_proof}
                   if admission.wild_component_proof is not None else {}))
            scope=DevelopmentPreparationScope(**values)
            _require(actor.get("contract") is None, "wild actor borrowed a story contract")
        _require(scope.train_admission==admission, "actor admission differs")
        admission.require_scope(scope,role)
        _require(actor.get("model_sha256")== (STORY_MODEL if role=="story" else admission.wild_model_sha256)
            and actor.get("qualification_sha256")==scope.identity,
            "actor model/qualification differs")
        scopes.append(scope)
    _require(declaration.get("model_sha256")==admission.wild_model_sha256
        and declaration.get("qualification_sha256")==scopes[1].identity,
        "prototype is not the admitted wild component")
    _require({p.name for p in root.glob("actor-*")} <= {"actor-000", "actor-001"},
        "unregistered actor directory exists")
    starts=sorted(root.glob("battle-*-start.json"))
    _require(set(root.glob("battle-*.json"))=={
        root/f"battle-{i:03d}-{phase}.json" for i in range(len(starts)) for phase in ("start","end")},
        "invocation artifact census differs")
    previous=declaration.get("frame_origin")
    _require(type(previous) is int and previous>=0, "frame origin differs")
    counts=[0,0];invocations=[];episodes=[]
    for ordinal,path in enumerate(starts):
        start=_read(path);end=_read(root/f"battle-{ordinal:03d}-end.json")
        index=start.get("actor")
        _require(type(index) is int and 0<=index<2, "invocation actor differs")
        _require(start.get("schema")=="pokemon.red.scoped-train-battle-start.v1"
            and type(start.get("ordinal")) is int and start["ordinal"]==ordinal
            and start.get("declaration_sha256")==expected_declaration_sha256
            and type(start.get("calls_before")) is int and start["calls_before"]==counts[index]
            and type(start.get("before_frame")) is int and start["before_frame"]>=previous,
            "invocation start differs")
        after=end.get("after_frame")
        expected=dict(start,schema="pokemon.red.scoped-train-battle-end.v1",
            calls_after=counts[index]+1,after_frame=after,error=None)
        _require(end==expected and type(after) is int and after>start["before_frame"],
            "invocation error/call count/frames differ")
        counts[index]+=1;previous=after;invocations.append(end)
        directory=root/f"actor-{index:03d}"/f"battle-{counts[index]:04d}"
        scope=scopes[index];role=actors[index]["scope"]
        capture=open_battle_scenario_capture(directory/"initial.state",directory/"initial.state.json")
        manifest=capture.manifest
        _require((manifest.capture_id,manifest.root_lineage_id,manifest.source_commit,
            manifest.source_state_sha256,manifest.partition,manifest.expected_map,manifest.expected_battle_state)==
            (f"player-trainer-{counts[index]:04d}",admission.root_lineage_id,admission.source_commit,
             admission.source_state_sha256,ScenarioPartition.TRAIN,65 if role=="story" else 15,
             2 if role=="story" else 1), "capture source/map/partition differs")
        outcome=_read(directory/"outcome.json");endpoint=_read(directory/"endpoint.json")
        _require(outcome.get("capture_id")==manifest.capture_id
            and outcome.get("manifest_sha256")==capture.manifest_sha256
            and endpoint.get("model_sha256")==actors[index]["model_sha256"]
            and endpoint.get("qualification_sha256")==scope.identity
            and endpoint.get("outcome_sha256")==canonical_sha256(outcome)
            and endpoint.get("final_state_sha256")==sha256((directory/"final.state").read_bytes()).hexdigest()
            and type(outcome.get("battle_won")) is bool
            and endpoint.get("actor_returned_win") is outcome["battle_won"]
            and endpoint.get("outer_goal_verification_required") is True,
            "native endpoint differs")
        log=verify_trainer_practice_event_log(directory/"events")
        first=_read(directory/"events/event-00001.json")["payload"]
        identity=first.get("identity",{})
        scope_key="development_story_scope" if role=="story" else "development_preparation_scope"
        _require(first.get("event")=="run_identity"
            and identity.get("model_sha256")==actors[index]["model_sha256"]
            and identity.get("qualification_sha256")==scope.identity
            and identity.get("source_commit")==admission.source_commit
            and identity.get("root_lineage_id")==admission.root_lineage_id
            and identity.get("parent_state_sha256")==admission.source_state_sha256
            and identity.get("source_partition")=="train" and identity.get("fit_allowed") is False
            and identity.get("authority")==("scoped-exact-story-train" if role=="story" else "scoped-wild-preparation-train")
            and identity.get("wild_training") is (role=="wild")
            and identity.get("pp_depleted_switch_screen",False) is (role=="story")
            and identity.get("mechanics_aware_choices") is True
            and identity.get("diagnostic_stay_when_productive") is False
            and identity.get("allow_status_moves") is True
            and identity.get("allow_forced_struggle") is (role=="story")
            and identity.get("train_funding_diagnostic",False) is False
            and canonical_sha256(identity.get(scope_key))==canonical_sha256(scope.document()),
            "native event source/component scope differs")
        if role=="story":
            _require(canonical_sha256(identity.get("train_story_contract"))==canonical_sha256(asdict(scope.contract)),
                "native story witness differs")
        _require(log["complete"] and log["terminal_event"]=="run_finished"
            and not log.get("failed_decisions") and log["started_decisions"]==log["completed_decisions"],
            "native event chain incomplete")
        last=_read(directory/"events"/f"event-{log['event_count']:05d}.json")["payload"]
        _require(last.get("outcome")==endpoint,"native terminal event differs")
        episodes.append(dict(ordinal=ordinal,actor=index,scope=role,directory=str(directory),
            capture_manifest_sha256=capture.manifest_sha256,outcome=outcome,endpoint=endpoint))
    _require(counts[0]==expected_story_calls,"story call census differs")
    for index,count in enumerate(counts):
        _require(set((root/f"actor-{index:03d}").glob("battle-*"))=={
            root/f"actor-{index:03d}"/f"battle-{i+1:04d}" for i in range(count)},
            "actor battle directory census differs")
    return ProductionTrainPoolReadback(declaration,tuple(invocations),tuple(episodes))


def load_production_train_challenge_consequence(store, *, declaration_sha256, result_sha256,
        scoped_output, expected_scoped_declaration_sha256, expected_admission):
    """Read one attempted full challenge; failed initial prefixes stay separate."""
    from .red_challenge_consequence import load_challenge_consequence, ScopedTrainConsequenceReadback
    row=load_challenge_consequence(store,declaration_sha256=declaration_sha256,result_sha256=result_sha256)
    plan=store.find_sealed_record("rcc-plan-"+declaration_sha256,expected_kind="red_challenge_consequence_plan").read()
    result=store.find_sealed_record("rcc-result-"+result_sha256,expected_kind="red_challenge_consequence_result").read()
    _require(row.outcome is not None and row.outcome.attempted and result["interrupted"] is False,
        "requires one attempted complete challenge; prefix/errors remain retained nonfit")
    pool=read_production_train_pool(scoped_output,
        expected_declaration_sha256=expected_scoped_declaration_sha256,
        expected_admission=expected_admission,source=plan["source"],expected_story_calls=1)
    _require(plan["spec"]["challenge_target"]==dict(kind="events",map_id=65,events=[191]),"RCC target differs")
    witness=plan.get("preparation_parent_witness")
    if witness is not None:
        parent=witness["bindings"][witness["parent_index"]]
        _require(parent["story_objective_ref"]=="defeat_misty",
            "conditioned parent differs from exact native story contract")
    episode=next(e for e in pool.episodes if e["scope"]=="story")
    phase=result["phases"][-1];invocation=pool.invocations[episode["ordinal"]]
    frame_origin=pool.declaration["frame_origin"]
    _require(episode["ordinal"] == len(pool.invocations)-1,
        "story invocation is not the final registered call")
    for call in pool.invocations:
        begin=call["before_frame"]-frame_origin
        end=call["after_frame"]-frame_origin
        _require(any(p["before"]["frames"] <= begin and end <= p["after"]["frames"]
                     for p in result["phases"]),
            "registered invocation lies outside cumulative RCC phase coverage")
    _require(phase["battle"]==("won" if episode["outcome"]["battle_won"] else "lost")
        and canonical_sha256(phase["challenge_episode"])==canonical_sha256(episode["outcome"])
        and phase["before"]["frames"]<=invocation["before_frame"]-frame_origin
        and invocation["after_frame"]-frame_origin<=phase["after"]["frames"]
        and row.outcome.completed is episode["outcome"]["battle_won"],"RCC/native final phase differs")
    return ScopedTrainConsequenceReadback(row,expected_scoped_declaration_sha256,
        canonical_sha256(episode["outcome"]),episode["capture_manifest_sha256"],episode["actor"],episode["ordinal"])


def consequence_party_view_from_verified(readback, *, plan, source_context_bytes, expected_context_sha256, work_order_bytes):
    """Add a source-witness view after strict native readback; never rewrite it.

    Callers first use their existing qualified read_case/production loader. The
    complete preinput context must be the same retained state and exact lesson,
    not a terminal or a context reconstructed from a later outcome. Older rows
    lacking an original context pin need separately qualified archival custody;
    roles require the explicit complete four-COMBAT source assignment used by
    the qualified original worker. Missing members never imply UNDECIDED.
    """
    import json
    from .red_challenge_consequence import ScopedTrainConsequenceReadback
    from .player_challenge_consequence import ConsequencePartyView
    from .player_preparation_party_context import PreparationPartyWitness
    if (type(readback) is not ScopedTrainConsequenceReadback
            or readback.row.provenance!="native_train" or readback.row.feature_version!=15
            or canonical_sha256(plan)!=readback.row.declaration_sha256
            or type(source_context_bytes) is not bytes
            or sha256(source_context_bytes).hexdigest()!=expected_context_sha256):
        raise ValueError("party view requires exact verified native row and original context bytes")
    if (type(work_order_bytes) is not bytes
            or sha256(work_order_bytes).hexdigest()!=plan["source"].get("experiment_sha256")):
        raise ValueError("party context lacks the exact sealed native work-order join")
    work_order=json.loads(work_order_bytes)
    if (work_order.get("partition")!="train"
            or work_order.get("source_sha256")!=plan["source"]["state_sha256"]):
        raise ValueError("party context work-order source/partition differs")
    context=json.loads(source_context_bytes)
    if (context.get("schema")!="pokemon.red.native-player-continuation.v1"
            or context.get("grants_new_budget") is not False or context.get("fit_allowed") is not False
            or context.get("state_sha256")!=plan["before"]["state_sha256"]
            or context["state_sha256"]!=plan["source"]["state_sha256"]
            or canonical_sha256(context.get("lesson"))!=canonical_sha256(plan["before"]["lesson"])):
        raise ValueError("party context is not the exact complete preinput source")
    roster=context["preparation"]["roster"]
    witness=PreparationPartyWitness(context["state_sha256"],tuple((r["specimen_ref"],r["purpose"]) for r in roster))
    witness.validate_lesson(plan["before"]["lesson"],context["state_sha256"])
    context_read_pin=work_order.get("fixture_metadata_sha256",{}).get(work_order.get("source_context"))
    if work_order.get("source_context_sha256") is not None or context_read_pin is not None:
        if (context_read_pin!=expected_context_sha256
                or work_order.get("source_context_sha256",expected_context_sha256)!=expected_context_sha256):
            raise ValueError("party context differs from authenticated work-order context pin")
        role_evidence="work_order_context_pin"
    else:
        # Historical qualified production workers create COMBAT PreparationMembers
        # for every native source party member and require that exact ordered
        # roster to equal this immutable work-order field before capture. This is
        # a complete four-member assignment, never an inference from absent refs.
        refs=work_order.get("source_combat_specimen_refs")
        if (type(refs) is not list or len(refs)!=4 or len(witness.roles)!=4
                or len(set(refs))!=4 or refs!=[r for r,_ in witness.roles]
                or any(purpose!="combat" for _,purpose in witness.roles)):
            raise ValueError("work order lacks the explicit complete four-COMBAT source assignment")
        role_evidence="work_order_complete_four_combat_roster"
    return ConsequencePartyView(readback.row,witness,expected_context_sha256,sha256(work_order_bytes).hexdigest(),role_evidence)
