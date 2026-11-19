"""Retain a verified unfinished story defeat separately from the latest battle.

This supplies optional preparation context, never a goal, trainee or action.
NativeBattlerHistory remains the authority for current actor outcomes. A carried
record reopens its exact retained files; it grants no actor or learning authority.
"""

import json
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path

from .post_battle_strategy import BattleResult
from .provenance import canonical_sha256
from .red_player_battle_history import NativeBattlerHistory
from .red_post_battle_strategy import red_battle_aftermath
from .red_story_battle import StoryTrainerContract

SCHEMA = "pokemon.red.story-preparation-loss.v1"


def _read(path):
    return json.loads(path.read_bytes())


def _observe_completed_preparation_history(history, *, censored_checkpoint=None):
    """Export only the reauthenticated completed prefix of a closed failure."""
    try:
        return history()
    except FileNotFoundError:
        execution_errors = {
            "BattleRuntimeError", "BattleRuntimeTimeoutError", "ProtectedRecoveryError", "KeyboardInterrupt"
        }
        budget_errors = {
            "ControllerActionBudgetExhausted", "ControllerWallTimeBudgetExhausted",
            "ControllerFrameBudgetExhausted"
        }
        if (type(censored_checkpoint) is not dict
                or censored_checkpoint.get("outcome") is not None
                or censored_checkpoint.get("fresh_inference") is not False
                or censored_checkpoint.get("error_type") not in execution_errors | budget_errors):
            raise
        kind = censored_checkpoint["error_type"]
        checkpoint = (history.checkpoint_after_execution_failure if kind in execution_errors
                      else history.checkpoint_after_budget_stop)
        latest, verified = checkpoint(
            terminal_state_sha256=censored_checkpoint["terminal_state_sha256"],
            error_type=kind)
        if verified != censored_checkpoint:
            raise ValueError("preparation export censor differs from the registered native failure")
        return latest


def _contract(fields):
    row = dict(fields)
    row["trainer_identity"] = tuple(row["trainer_identity"])
    row["victory_items"] = tuple(tuple(x) for x in row["victory_items"])
    return StoryTrainerContract(**row)


def _actor_contract(actor):
    contract = actor.train_story_contract
    if contract is None and actor.development_story_scope is not None:
        contract = actor.development_story_scope.contract
    return contract if type(contract) is StoryTrainerContract else None


@dataclass(frozen=True)
class RetainedStoryDefeat:
    contract: StoryTrainerContract
    directory: Path
    outcome_sha256: str
    manifest_sha256: str
    endpoint_sha256: str
    battle_receipt_sha256: str

    def private_dict(self):
        return dict(schema=SCHEMA,contract=asdict(self.contract),directory=str(self.directory),
                    outcome_sha256=self.outcome_sha256,manifest_sha256=self.manifest_sha256,
                    endpoint_sha256=self.endpoint_sha256,battle_receipt_sha256=self.battle_receipt_sha256)

    @classmethod
    def from_document(cls, value):
        if not isinstance(value,dict) or set(value) != {"schema","contract","directory",
                "outcome_sha256","manifest_sha256","endpoint_sha256","battle_receipt_sha256"} or value["schema"] != SCHEMA:
            raise ValueError("retained story preparation document differs")
        for key in ("outcome_sha256","manifest_sha256","endpoint_sha256","battle_receipt_sha256"):
            h=value[key]
            if type(h)is not str or len(h)!=64 or any(c not in "0123456789abcdef"for c in h):
                raise ValueError("retained story preparation requires exact hashes")
        result=cls(_contract(value["contract"]),Path(value["directory"]),
                   value["outcome_sha256"],value["manifest_sha256"],value["endpoint_sha256"],value["battle_receipt_sha256"])
        result.aftermath()  # Reauthenticate retained evidence before a restored option can use it.
        return result

    @classmethod
    def from_history(cls, history, ordinal, *, censored_checkpoint=None):
        if type(history)is not NativeBattlerHistory or type(ordinal)is not int or ordinal<1:
            raise TypeError("retained preparation requires native battle history")
        _observe_completed_preparation_history(history, censored_checkpoint=censored_checkpoint)
        actor=history.battler;contract=_actor_contract(actor)
        if contract is None or ordinal>len(history.outcomes) or history.outcomes[ordinal-1].result is not BattleResult.LOST:
            raise ValueError("retained preparation requires a verified story defeat")
        directory=actor.output / f"battle-{ordinal:04d}"
        result=cls(contract,directory,sha256((directory/"outcome.json").read_bytes()).hexdigest(),
                   sha256((directory/"initial.state.json").read_bytes()).hexdigest(),
                   canonical_sha256(_read(directory/"endpoint.json")),history.receipts[ordinal-1])
        if result.aftermath()!=history.outcomes[ordinal-1]:
            raise ValueError("retained preparation differs from actual native history")
        return result

    def aftermath(self):
        from .battle_scenario_capture import open_battle_scenario_capture
        from .red_trainer_practice_log import verify_trainer_practice_event_log
        d=self.directory;payload=(d/"outcome.json").read_bytes()
        capture=open_battle_scenario_capture(d/"initial.state",d/"initial.state.json")
        endpoint=_read(d/"endpoint.json");log=verify_trainer_practice_event_log(d/"events")
        identity=_read(d/"events/event-00001.json")["payload"]["identity"]
        fields=identity.get("train_story_contract")
        if fields is None:
            fields=(identity.get("development_story_scope")or{}).get("contract")
        if (sha256(payload).hexdigest()!=self.outcome_sha256
            or sha256((d/"initial.state.json").read_bytes()).hexdigest()!=self.manifest_sha256
            or canonical_sha256(endpoint)!=self.endpoint_sha256
            or endpoint["outcome_sha256"]!=canonical_sha256(json.loads(payload))
            or endpoint["final_state_sha256"]!=sha256((d/"final.state").read_bytes()).hexdigest()
            or not log["complete"] or log["terminal_event"]not in {"run_finished","run_failed"}
            or capture.manifest.expected_battle_state!=2
            or capture.manifest.expected_map!=self.contract.map_id
            or json.loads(payload).get("capture_id")!=capture.manifest.capture_id
            or json.loads(payload).get("manifest_sha256")!=capture.manifest_sha256
            or any(identity.get(k)!=v for k,v in {
                "source_commit":capture.manifest.source_commit,
                "root_lineage_id":capture.manifest.root_lineage_id,
                "parent_state_sha256":capture.manifest.source_state_sha256,
                "model_sha256":endpoint["model_sha256"],
                "qualification_sha256":endpoint["qualification_sha256"]}.items())
            or fields is None or _contract(fields)!=self.contract
            or identity.get("wild_training",False)is not False
            or canonical_sha256(dict(manifest=capture.manifest_sha256,endpoint=endpoint,
                   episode_sha256=self.outcome_sha256,log=log))!=self.battle_receipt_sha256):
            raise ValueError("retained story preparation native evidence differs")
        battle=red_battle_aftermath(payload,expected_sha256=self.outcome_sha256)
        if battle.result is not BattleResult.LOST:
            raise ValueError("retained story preparation is not a defeat")
        return battle


class StoryPreparationHistory:
    def __init__(self, retained=None, *, expected_lineage=None, expected_partition=None):
        if (expected_lineage is None)!=(expected_partition is None) or (
            expected_lineage is not None and (type(expected_lineage)is not str
                or not expected_lineage or expected_partition not in {"train","development"})):
            raise ValueError("retained preparation requires an exact native source scope")
        self.expected_lineage,self.expected_partition=expected_lineage,expected_partition
        self._losses=[]
        self._seen={}
        self._seen_histories={}
        if retained is not None:self._retain(retained)

    @property
    def retained(self):
        return self._losses[-1] if self._losses else None

    def _retain(self,record):
        if type(record)is not RetainedStoryDefeat:raise TypeError("typed retained story defeat required")
        self._require_source(record)
        self._losses=[x for x in self._losses if x.contract!=record.contract]+[record]

    def _require_source(self,record):
        if self.expected_lineage is not None:
            manifest=_read(record.directory/"initial.state.json")
            if (manifest["root_lineage_id"]!=self.expected_lineage
                or manifest["partition"]!=self.expected_partition):
                raise ValueError("retained preparation crossed native lineage or partition")

    @classmethod
    def from_document(cls,document,**scope):
        memory=cls(**scope)
        if document is None:return memory
        if document.get("schema")==SCHEMA:records=[document]  # Exact F75 continuation compatibility.
        elif (document.get("schema")=="pokemon.red.story-preparation-history.v1"
              and set(document)=={"schema","defeats"} and type(document["defeats"])is list
              and document["defeats"]):records=document["defeats"]
        else:raise ValueError("retained preparation history document differs")
        for value in records:
            record=RetainedStoryDefeat.from_document(value)
            if any(x.contract==record.contract for x in memory._losses):
                raise ValueError("retained preparation repeats a native contract")
            memory._retain(record)
        return memory

    def _require_battle_source(self, history, ordinal, holder):
        """Check story custody for wins as well as defeats before changing memory."""
        from .battle_scenario_capture import open_battle_scenario_capture
        directory=history.battler.output/f"battle-{ordinal:04d}"
        capture=open_battle_scenario_capture(directory/'initial.state',directory/'initial.state.json')
        manifest=capture.manifest
        if self.expected_lineage is not None and (
            manifest.root_lineage_id!=self.expected_lineage
            or manifest.partition.value!=self.expected_partition):
            raise ValueError('retained preparation crossed native lineage or partition')
        owner=holder.get('actor')
        if owner is not None and (owner.root_lineage_id!=manifest.root_lineage_id
                or owner.source_partition is not manifest.partition):
            raise ValueError('retained preparation crossed native lineage or partition')
        identity=_read(directory/'events/event-00001.json')['payload']['identity']
        fields=identity.get('train_story_contract')
        if fields is None:fields=(identity.get('development_story_scope')or{}).get('contract')
        contract=_actor_contract(history.battler)
        if (contract is None or fields is None or _contract(fields)!=contract
                or manifest.expected_battle_state!=2 or manifest.expected_map!=contract.map_id
                or identity.get('wild_training',False)is not False):
            raise ValueError('retained preparation requires its registered story battle')

    def refresh(self,holder):
        """Authenticate and stage the entire batch before committing story memory."""
        actor=holder.get('actor')
        for retained in self._losses:
            self._require_source(retained)
            if actor is not None:
                manifest=_read(retained.directory/'initial.state.json')
                if (actor.root_lineage_id!=manifest['root_lineage_id']
                    or actor.source_partition.value!=manifest['partition']):
                    raise ValueError('retained preparation crossed native lineage or partition')
        pending=[];seen_updates={};histories=dict(self._seen_histories)
        registered=set();registered_actors=set()
        def observe(actor,h):
            if type(h)is not NativeBattlerHistory or actor is not h.battler:
                raise ValueError('registered native actor and history differ')
            if id(h)in registered or id(actor)in registered_actors:
                raise ValueError('duplicate registered native history')
            registered.add(id(h));registered_actors.add(id(actor));histories[id(h)]=h
            _observe_completed_preparation_history(h,censored_checkpoint=holder.get('censored_battle_checkpoint'))
            count=self._seen.get(id(h),0)
            if len(h.receipts)<count:raise ValueError('retained preparation history regressed')
            seen_updates[id(h)]=len(h.receipts)
            return count
        group=holder.get('scoped_native_train_group')
        if group is not None:
            group.history();intervals=[];accounted=set()
            for pool in group.pools.values():
                for h in pool._histories:observe(h.battler,h)
                for entry in pool._entries:
                    before,n=entry['calls_before'],entry['calls_after']
                    if before==n:continue  # A closed failed invocation made no new battle.
                    h=pool._histories[entry['actor']]
                    if (type(before)is not int or type(n)is not int or n!=before+1
                            or not 1<=n<=len(h.receipts) or (id(h),n)in accounted):
                        raise ValueError('registered story battle ordinal differs')
                    start,end=entry['before_frame'],entry['after_frame']
                    if type(start)is not int or type(end)is not int or end<=start:
                        raise ValueError('registered story battle frames differ')
                    intervals.append((start,end));accounted.add((id(h),n))
                    if n>self._seen.get(id(h),0)and _actor_contract(h.battler)is not None:
                        pending.append((end,h,n))
            previous=-1
            for start,end in sorted(intervals):
                if start<previous:raise ValueError('registered story battles overlap')
                previous=end
            if any((id(h),n)not in accounted for pool in group.pools.values()
                   for h in pool._histories for n in range(1,len(h.receipts)+1)):
                raise ValueError('registered story history lacks its invocation')
        else:
            changed=[]
            for actor,h in holder.get('scoped_actors',{}).values():
                count=observe(actor,h)
                if _actor_contract(actor)is not None and len(h.receipts)>count:
                    changed.append((h,count))
            # Only independently verified wins commute without a global order.
            if len(changed)>1 and any(battle.result is not BattleResult.WON
                    for h,count in changed for battle in h.outcomes[count:]):
                raise ValueError('ambiguous story preparation history order')
            for h,count in changed:
                pending.extend((n,h,n)for n in range(count+1,len(h.receipts)+1))
        losses=list(self._losses)
        for _,h,n in sorted(pending,key=lambda row:row[0]):
            self._require_battle_source(h,n,holder)
            battle=h.outcomes[n-1];contract=_actor_contract(h.battler)
            if battle.result is BattleResult.LOST:
                record=RetainedStoryDefeat.from_history(h,n,censored_checkpoint=holder.get('censored_battle_checkpoint'))
                self._require_source(record)
                losses=[x for x in losses if x.contract!=record.contract]+[record]
            elif battle.result is BattleResult.WON:
                losses=[x for x in losses if x.contract!=contract]
        self._losses=losses
        self._seen.update(seen_updates)
        self._seen_histories=histories  # Keep registered identities alive; id reuse cannot skip a battle.

    def preparation_loss(self,runtime,observation,latest,holder):
        self.refresh(holder)
        legal={o.id for o in runtime.adapter.graph.available_objectives(observation.game_state)}
        completed=set(runtime.adapter.graph.completed_ids(observation.game_state))
        from .observation import event_flag_is_set
        flags=runtime.reader.read().event_flags
        self._losses=[record for record in self._losses
            if record.contract.objective_id not in completed and not (
                record.contract.defeated_event is not None
                and event_flag_is_set(flags,record.contract.defeated_event))]
        # Recent battle features remain the actual latest battle;this is only
        # the preparation observer's bounded known-opposition fallback.
        if latest is not None and latest.result is BattleResult.LOST:return latest
        retained=next((r for r in reversed(self._losses)if r.contract.objective_id in legal),None)
        return None if retained is None else retained.aftermath()

    def private_dict(self):
        return None if not self._losses else dict(schema="pokemon.red.story-preparation-history.v1",
                                                 defeats=[r.private_dict()for r in self._losses])

def retained_story_preparation_inputs(document, **scope):
    """Return the exact files consumed by authenticated retained story defeats.

    Keep validation with the existing typed reader, including capture, endpoint,
    receipt and ordered event-chain checks. These are prospective file pins;
    enumerating them never grants a directory or changes continuation bytes.
    """
    history = StoryPreparationHistory.from_document(document, **scope)
    paths = set()
    for record in history._losses:
        directory = record.directory
        paths.update(directory / name for name in (
            "outcome.json", "initial.state", "initial.state.json",
            "endpoint.json", "final.state",
        ))
        paths.update((directory / "events").glob("event-*.json"))
    return sorted(paths)


def connect_story_preparation_observation(holder, history):
    """Refresh authenticated losses at each existing completed battle boundary.

    Composite income observes its actors one battle at a time. Waiting for the
    next goal menu loses that known order. The existing history reader and batch
    guard still authenticate every result; this supplies no inferred ordering.
    """
    if type(history) is not StoryPreparationHistory:
        raise TypeError("typed story preparation history required")
    observe = holder["observe_history"]
    def observed(*args, **kwargs):
        latest = observe(*args, **kwargs)
        history.refresh(holder)
        return latest
    holder["observe_history"] = observed
