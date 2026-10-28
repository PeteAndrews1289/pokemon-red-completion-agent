"""One-hop genuine TRAIN source proof from a closed, prebattle native prefix.

This reuses consequence/action readback and the production battler pool reader.
It grants no controller, new budget, fit label, promotion or independent origin.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass
from hashlib import sha256
import json

from .provenance import canonical_sha256
from .red_player_continuation import _costs, accumulate_player_costs
from .red_post_battle_strategy import red_battle_aftermath

SCHEMA = "pokemon.red.production-train-derived-source.v1"
KIND = "red_production_train_derived_source"
_TOKEN = object()


def _require(condition, reason):
    if not condition:
        raise ValueError("derived TRAIN source " + reason)


@dataclass(frozen=True, init=False)
class VerifiedDerivedTrainSource:
    _canonical: bytes

    def __init__(self, document, *, _token=None):
        if _token is not _TOKEN:
            raise ValueError("derived TRAIN source requires authenticated sealed readback")
        object.__setattr__(self, "_canonical", json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode())

    def document(self):
        return json.loads(self._canonical)

    @property
    def identity(self):
        return sha256(self._canonical).hexdigest()

    @property
    def source_state_sha256(self):
        return self.document()["source_state_sha256"]

    @property
    def source_origin_sha256(self):
        return self.document()["source_origin_sha256"]

    @property
    def source_commit(self):
        return self.document()["source_commit"]

    def require_source_context(self, state, context_bytes):
        _require(sha256(state).hexdigest() == self.source_state_sha256
            and type(context_bytes) is bytes
            and sha256(context_bytes).hexdigest() == self.document()["context_content_sha256"],
            "actual paired CONTEXT or terminal differs from the sealed export")

    def require_metadata(self, envelope, progress):
        _require(envelope.get("state_sha256") == self.source_state_sha256
            and envelope.get("verified_objective_ids") == self.document()["completed_objectives"]
            and envelope.get("verified_objective_count") == len(self.document()["completed_objectives"])
            and progress.get("derived_source_proof_sha256") == self.identity,
            "metadata is not the exact observed derived boundary")


def _derive_document(*, parent, parent_plan_bytes, plan, result, row, native,
                     pool, terminal_bytes, context_bytes, initial_context_bytes, meter_bytes,
                     declaration_sha256, result_sha256, scoped_declaration_sha256):
    """Pure boundary checks after both existing sealed/native readers pass."""
    parent.require_work_order(parent_plan_bytes)
    _require(getattr(parent, "derived_source_proof", None) is None,
             "only one prefix from an original qualified TRAIN fixture is supported")
    source = plan["source"]
    _require(plan["partition"] == source["partition"] == "train"
        and source["state_sha256"] == parent.source_state_sha256
        and source["origin_sha256"] == parent.source_origin_sha256
        and source["source_commit"] == parent.source_commit
        and source["experiment_sha256"] == parent.work_order_sha256,
        "prefix does not begin at its qualified TRAIN admission")
    _require(native["source"] == source and native["consequence_spec"] == plan["spec"],
             "native claim differs from the prospective prefix")
    _require(row.outcome is None and row.censor_reason == "challenge_not_reached_before_stop"
        and row.provenance == "native_train" and result["interrupted"] is False
        and result["error"] is None,
        "prefix must be a successful planned prebattle stop, never a fitted outcome")
    _require(plan["spec"].get("challenge_target") == dict(kind="events", map_id=65, events=[191])
        and plan["spec"].get("include_challenge_arrival") is True,
        "prefix must prospectively declare the exact Misty arrival")
    phases = result["phases"]
    _require(2 <= len(phases) <= 3 and phases[0]["kind"] == "develop_team"
        and phases[-1]["kind"] == "advance_story" and phases[-1]["after"]["endpoint"]["map_id"] == 65
        and all(p["kind"] in {"restore_team", "advance_story"} for p in phases[1:])
        and all(p["verified"] is True and p["error"] is None and p["battle"] is None
                and p["cost_verified"] is True and p["interventions"] == []
                and p["after"]["settled"] is True for p in phases),
        "requires one verified dose and only verified restoration/arrival before battle")
    _require(pool.declaration["native_plan_sha256"] == parent.work_order_sha256
        and pool.declaration["source_state_sha256"] == parent.source_state_sha256
        and pool.episodes and all(e["scope"] == "wild" for e in pool.episodes),
        "requires authenticated production wild evidence and zero story calls")
    last = phases[-1]["after"]
    origin = pool.declaration["frame_origin"]
    _require(all(any(phase["before"]["frames"] <= invocation["before_frame"] - origin
                         and invocation["after_frame"] - origin <= phase["after"]["frames"]
                         for phase in phases) for invocation in pool.invocations),
             "battler receipt lies outside the declared prefix phases")
    state = sha256(terminal_bytes).hexdigest()
    context, initial, meter = map(json.loads, (context_bytes, initial_context_bytes, meter_bytes))
    _require(state != parent.source_state_sha256 and state == last["state_sha256"] == context["state_sha256"],
             "terminal state is not the exact observed post-dose endpoint")
    _require(context.get("schema") == "pokemon.red.native-player-continuation.v1"
        and context.get("grants_new_budget") is False and context.get("fit_allowed") is False
        and canonical_sha256(context["lesson"]) == canonical_sha256(last["lesson"])
        and context["cash"] == last["cash"]
        and "defeat_misty" not in context["lesson"]["completed_objectives"]
        and not all(last["endpoint"]["events"]), "paired CONTEXT differs or challenge was reached")
    payload = json.dumps(pool.episodes[-1]["outcome"], sort_keys=True, allow_nan=False).encode()
    history = asdict(red_battle_aftermath(payload, expected_sha256=sha256(payload).hexdigest()))
    _require(canonical_sha256(context.get("battle")) == canonical_sha256(history),
             "paired battle history differs from the verified last native wild episode")
    prior = _costs(initial["spent"])
    _require(initial["state_sha256"] == parent.source_state_sha256
        and initial.get("grants_new_budget") is False and initial.get("fit_allowed") is False
        and prior["seconds"] > 0
        and all(prior[k] == 0 for k in ("decisions", "actions", "frames", "heals", "cash_debits")),
        "initial context must meter the first load without any omitted native prefix")
    _require(meter.get("schema") == "pokemon.red.native-player-costs.v1"
        and meter.get("buttons_released") is True and meter.get("automatic_fit") is False
        and meter.get("cost_lower_bound", False) is False
        and meter.get("actions_attempted") == meter.get("actions_completed") == last["actions"] == last["completed_actions"]
        and meter.get("frames") == last["frames"]
        and meter.get("goal_attempts") == len(phases)
        and meter.get("restore_attempts") == last["heals"]
        and type(meter.get("observed_cash_debits")) is int and meter["observed_cash_debits"] == 0
        and type(meter.get("observed_cash_rewards")) is int and meter["observed_cash_rewards"] == 0
        and type(meter.get("observed_cash_changes")) is int and meter["observed_cash_changes"] == 0
        and all(phase["before"]["cash"] == phase["after"]["cash"] == phases[0]["before"]["cash"]
                for phase in phases),
        "complete meter differs from the sealed prefix or pilot zero-cash-movement scope")
    local = _costs(dict(decisions=meter["goal_attempts"], actions=meter["actions_attempted"],
        frames=meter["frames"], seconds=meter["seconds"], heals=meter["restore_attempts"],
        cash_debits=meter["observed_cash_debits"]))
    _require(local["seconds"] > 0 and local["seconds"] <= native["limits"]["seconds"],
             "prefix time is missing or exceeds its original cap")
    spent = accumulate_player_costs(prior, decisions=local["decisions"], actions=local["actions"],
        frames=local["frames"], seconds=local["seconds"], heals=local["heals"],
        cash_deltas=(local["cash_debits"],))
    _require(_costs(context["spent"]) == spent, "cumulative cost was reset, omitted or refunded")
    return dict(schema=SCHEMA, source_partition="train", source_state_sha256=state,
        source_origin_sha256=parent.source_origin_sha256, source_commit=parent.source_commit,
        parent_admission=parent.document(), parent_work_order_sha256=parent.work_order_sha256,
        prefix_declaration_sha256=declaration_sha256, prefix_result_sha256=result_sha256,
        scoped_declaration_sha256=scoped_declaration_sha256,
        terminal_sha256=state, context_content_sha256=sha256(context_bytes).hexdigest(),
        initial_context_content_sha256=sha256(initial_context_bytes).hexdigest(),
        native_meter_content_sha256=sha256(meter_bytes).hexdigest(), cumulative_spent=spent,
        completed_objectives=context["lesson"]["completed_objectives"],
        prefix_phase_count=len(phases), production_wild_invocations=len(pool.episodes),
        story_invocations=0, fit_admission=False, grants_new_budget=False,
        prefix_censor_reason=row.censor_reason, independent_origin=False,
        cash_scope="zero_cash_movement_pilot", battle_history_sha256=canonical_sha256(history))


def authenticate_derived_train_source(*, store, parent, parent_plan_bytes, scoped_output,
        expected_scoped_declaration_sha256, declaration_sha256, result_sha256,
        terminal_bytes, context_bytes, initial_context_bytes, meter_bytes,
        expected_proof_sha256=None):
    """Export once, or reauthenticate an existing immutable proof; never run inputs.

    The prefix must be a separate closed native execution. Reusing a saved prefix
    from a later battle tail fails the existing sealed action census. Derived
    documents alone cannot instantiate ProductionTrainAdmission.
    """
    from .red_challenge_consequence import load_challenge_consequence
    from .red_native_player import NativeExecutionIdentity
    from .red_production_train_readback import read_production_train_pool

    row = load_challenge_consequence(store, declaration_sha256=declaration_sha256,
                                    result_sha256=result_sha256)
    plan = store.find_sealed_record("rcc-plan-" + declaration_sha256,
        expected_kind="red_challenge_consequence_plan").read()
    result = store.find_sealed_record("rcc-result-" + result_sha256,
        expected_kind="red_challenge_consequence_result").read()
    execution = NativeExecutionIdentity(**plan["execution"])
    native = store.find_sealed_record(execution.claim_id,
        expected_kind="red_native_player_execution").read()
    pool = read_production_train_pool(scoped_output,
        expected_declaration_sha256=expected_scoped_declaration_sha256,
        expected_admission=parent, source=plan["source"], expected_story_calls=0)
    document = _derive_document(parent=parent, parent_plan_bytes=parent_plan_bytes,
        plan=plan, result=result, row=row, native=native, pool=pool,
        terminal_bytes=terminal_bytes, context_bytes=context_bytes,
        initial_context_bytes=initial_context_bytes, meter_bytes=meter_bytes,
        declaration_sha256=declaration_sha256, result_sha256=result_sha256,
        scoped_declaration_sha256=expected_scoped_declaration_sha256)
    digest = canonical_sha256(document)
    identity = "ptr-source-" + digest
    if expected_proof_sha256 is None:
        store.publish_sealed_record(identity, kind=KIND, record=document)
    else:
        record = store.find_sealed_record(identity, expected_kind=KIND)
        _require(digest == expected_proof_sha256 and record is not None
            and canonical_sha256(record.read()) == digest,
            "export proof is missing, changed or belongs to another source")
    return VerifiedDerivedTrainSource(document, _token=_TOKEN)
