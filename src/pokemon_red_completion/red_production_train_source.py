"""One-hop genuine TRAIN source proof from a closed, prebattle native prefix.

This reuses consequence/action readback and the production battler pool reader.
It grants no controller, new budget, fit label, promotion or independent origin.
"""

import json
from copy import deepcopy
from dataclasses import asdict, dataclass
from hashlib import sha256

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
        object.__setattr__(
            self,
            "_canonical",
            json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(),
        )

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
        _require(
            sha256(state).hexdigest() == self.source_state_sha256
            and type(context_bytes) is bytes
            and sha256(context_bytes).hexdigest() == self.document()["context_content_sha256"],
            "actual paired CONTEXT or terminal differs from the sealed export",
        )

    def require_metadata(self, envelope, progress):
        _require(
            envelope.get("state_sha256") == self.source_state_sha256
            and envelope.get("verified_objective_ids") == self.document()["completed_objectives"]
            and envelope.get("verified_objective_count")
            == len(self.document()["completed_objectives"])
            and progress.get("derived_source_proof_sha256") == self.identity,
            "metadata is not the exact observed derived boundary",
        )


def _derive_document(
    *,
    parent,
    parent_plan_bytes,
    plan,
    result,
    row,
    native,
    pool,
    terminal_bytes,
    context_bytes,
    initial_context_bytes,
    meter_bytes,
    declaration_sha256,
    result_sha256,
    scoped_declaration_sha256,
):
    """Pure boundary checks after both existing sealed/native readers pass."""
    parent.require_work_order(parent_plan_bytes)
    _require(
        getattr(parent, "derived_source_proof", None) is None,
        "only one prefix from an original qualified TRAIN fixture is supported",
    )
    source = plan["source"]
    _require(
        plan["partition"] == source["partition"] == "train"
        and source["state_sha256"] == parent.source_state_sha256
        and source["origin_sha256"] == parent.source_origin_sha256
        and source["source_commit"] == parent.source_commit
        and source["experiment_sha256"] == parent.work_order_sha256,
        "prefix does not begin at its qualified TRAIN admission",
    )
    _require(
        native["source"] == source and native["consequence_spec"] == plan["spec"],
        "native claim differs from the prospective prefix",
    )
    _require(
        row.outcome is None
        and row.censor_reason == "challenge_not_reached_before_stop"
        and row.provenance == "native_train"
        and result["interrupted"] is False
        and result["error"] is None,
        "prefix must be a successful planned prebattle stop, never a fitted outcome",
    )
    _require(
        plan["spec"].get("challenge_target") == dict(kind="events", map_id=65, events=[191])
        and plan["spec"].get("include_challenge_arrival") is True,
        "prefix must prospectively declare the exact Misty arrival",
    )
    phases = result["phases"]
    _require(
        2 <= len(phases) <= 3
        and phases[0]["kind"] == "develop_team"
        and phases[-1]["kind"] == "advance_story"
        and phases[-1]["after"]["endpoint"]["map_id"] == 65
        and all(p["kind"] in {"restore_team", "advance_story"} for p in phases[1:])
        and all(
            p["verified"] is True
            and p["error"] is None
            and p["battle"] is None
            and p["cost_verified"] is True
            and p["interventions"] == []
            and p["after"]["settled"] is True
            for p in phases
        ),
        "requires one verified dose and only verified restoration/arrival before battle",
    )
    _require(
        pool.declaration["native_plan_sha256"] == parent.work_order_sha256
        and pool.declaration["source_state_sha256"] == parent.source_state_sha256
        and pool.episodes
        and all(e["scope"] == "wild" for e in pool.episodes),
        "requires authenticated production wild evidence and zero story calls",
    )
    last = phases[-1]["after"]
    origin = pool.declaration["frame_origin"]
    _require(
        all(
            any(
                phase["before"]["frames"] <= invocation["before_frame"] - origin
                and invocation["after_frame"] - origin <= phase["after"]["frames"]
                for phase in phases
            )
            for invocation in pool.invocations
        ),
        "battler receipt lies outside the declared prefix phases",
    )
    state = sha256(terminal_bytes).hexdigest()
    context, initial, meter = map(json.loads, (context_bytes, initial_context_bytes, meter_bytes))
    _require(
        state != parent.source_state_sha256
        and state == last["state_sha256"] == context["state_sha256"],
        "terminal state is not the exact observed post-dose endpoint",
    )
    _require(
        context.get("schema") == "pokemon.red.native-player-continuation.v1"
        and context.get("grants_new_budget") is False
        and context.get("fit_allowed") is False
        and canonical_sha256(context["lesson"]) == canonical_sha256(last["lesson"])
        and context["cash"] == last["cash"]
        and "defeat_misty" not in context["lesson"]["completed_objectives"]
        and not all(last["endpoint"]["events"]),
        "paired CONTEXT differs or challenge was reached",
    )
    payload = json.dumps(pool.episodes[-1]["outcome"], sort_keys=True, allow_nan=False).encode()
    history = asdict(red_battle_aftermath(payload, expected_sha256=sha256(payload).hexdigest()))
    _require(
        canonical_sha256(context.get("battle")) == canonical_sha256(history),
        "paired battle history differs from the verified last native wild episode",
    )
    prior = _costs(initial["spent"])
    _require(
        initial["state_sha256"] == parent.source_state_sha256
        and initial.get("grants_new_budget") is False
        and initial.get("fit_allowed") is False
        and prior["seconds"] > 0
        and all(prior[k] == 0 for k in ("decisions", "actions", "frames", "heals", "cash_debits")),
        "initial context must meter the first load without any omitted native prefix",
    )
    _require(
        meter.get("schema") == "pokemon.red.native-player-costs.v1"
        and meter.get("buttons_released") is True
        and meter.get("automatic_fit") is False
        and meter.get("cost_lower_bound", False) is False
        and meter.get("actions_attempted")
        == meter.get("actions_completed")
        == last["actions"]
        == last["completed_actions"]
        and meter.get("frames") == last["frames"]
        and meter.get("goal_attempts") == len(phases)
        and meter.get("restore_attempts") == last["heals"]
        and type(meter.get("observed_cash_debits")) is int
        and meter["observed_cash_debits"] == 0
        and type(meter.get("observed_cash_rewards")) is int
        and meter["observed_cash_rewards"] == 0
        and type(meter.get("observed_cash_changes")) is int
        and meter["observed_cash_changes"] == 0
        and all(
            phase["before"]["cash"] == phase["after"]["cash"] == phases[0]["before"]["cash"]
            for phase in phases
        ),
        "complete meter differs from the sealed prefix or pilot zero-cash-movement scope",
    )
    local = _costs(
        dict(
            decisions=meter["goal_attempts"],
            actions=meter["actions_attempted"],
            frames=meter["frames"],
            seconds=meter["seconds"],
            heals=meter["restore_attempts"],
            cash_debits=meter["observed_cash_debits"],
        )
    )
    _require(
        local["seconds"] > 0 and local["seconds"] <= native["limits"]["seconds"],
        "prefix time is missing or exceeds its original cap",
    )
    spent = accumulate_player_costs(
        prior,
        decisions=local["decisions"],
        actions=local["actions"],
        frames=local["frames"],
        seconds=local["seconds"],
        heals=local["heals"],
        cash_deltas=(local["cash_debits"],),
    )
    _require(_costs(context["spent"]) == spent, "cumulative cost was reset, omitted or refunded")
    return dict(
        schema=SCHEMA,
        source_partition="train",
        source_state_sha256=state,
        source_origin_sha256=parent.source_origin_sha256,
        source_commit=parent.source_commit,
        parent_admission=parent.document(),
        parent_work_order_sha256=parent.work_order_sha256,
        prefix_declaration_sha256=declaration_sha256,
        prefix_result_sha256=result_sha256,
        scoped_declaration_sha256=scoped_declaration_sha256,
        terminal_sha256=state,
        context_content_sha256=sha256(context_bytes).hexdigest(),
        initial_context_content_sha256=sha256(initial_context_bytes).hexdigest(),
        native_meter_content_sha256=sha256(meter_bytes).hexdigest(),
        cumulative_spent=spent,
        completed_objectives=context["lesson"]["completed_objectives"],
        prefix_phase_count=len(phases),
        production_wild_invocations=len(pool.episodes),
        story_invocations=0,
        fit_admission=False,
        grants_new_budget=False,
        prefix_censor_reason=row.censor_reason,
        independent_origin=False,
        cash_scope="zero_cash_movement_pilot",
        battle_history_sha256=canonical_sha256(history),
    )


def authenticate_derived_train_source(
    *,
    store,
    parent,
    parent_plan_bytes,
    scoped_output,
    expected_scoped_declaration_sha256,
    declaration_sha256,
    result_sha256,
    terminal_bytes,
    context_bytes,
    initial_context_bytes,
    meter_bytes,
    expected_proof_sha256=None,
):
    """Export once, or reauthenticate an existing immutable proof; never run inputs.

    The prefix must be a separate closed native execution. Reusing a saved prefix
    from a later battle tail fails the existing sealed action census. Derived
    documents alone cannot instantiate ProductionTrainAdmission.
    """
    from .red_challenge_consequence import load_challenge_consequence
    from .red_native_player import NativeExecutionIdentity
    from .red_production_train_readback import read_production_train_pool

    row = load_challenge_consequence(
        store, declaration_sha256=declaration_sha256, result_sha256=result_sha256
    )
    plan = store.find_sealed_record(
        "rcc-plan-" + declaration_sha256, expected_kind="red_challenge_consequence_plan"
    ).read()
    result = store.find_sealed_record(
        "rcc-result-" + result_sha256, expected_kind="red_challenge_consequence_result"
    ).read()
    execution = NativeExecutionIdentity(**plan["execution"])
    native = store.find_sealed_record(
        execution.claim_id, expected_kind="red_native_player_execution"
    ).read()
    pool = read_production_train_pool(
        scoped_output,
        expected_declaration_sha256=expected_scoped_declaration_sha256,
        expected_admission=parent,
        source=plan["source"],
        expected_story_calls=0,
    )
    document = _derive_document(
        parent=parent,
        parent_plan_bytes=parent_plan_bytes,
        plan=plan,
        result=result,
        row=row,
        native=native,
        pool=pool,
        terminal_bytes=terminal_bytes,
        context_bytes=context_bytes,
        initial_context_bytes=initial_context_bytes,
        meter_bytes=meter_bytes,
        declaration_sha256=declaration_sha256,
        result_sha256=result_sha256,
        scoped_declaration_sha256=expected_scoped_declaration_sha256,
    )
    digest = canonical_sha256(document)
    identity = "ptr-source-" + digest
    if expected_proof_sha256 is None:
        store.publish_sealed_record(identity, kind=KIND, record=document)
    else:
        record = store.find_sealed_record(identity, expected_kind=KIND)
        _require(
            digest == expected_proof_sha256
            and record is not None
            and canonical_sha256(record.read()) == digest,
            "export proof is missing, changed or belongs to another source",
        )
    return VerifiedDerivedTrainSource(document, _token=_TOKEN)


# This is a separately registered historical native teacher prefix. It is not
# the two/three-phase Misty post-dose proof above and grants no new execution.
TEACHER_PREFIX_SCHEMA = "pokemon.red.production-train-teacher-prefix.v1"
SOURCE049_ORIGIN = "9bca54dc07a8ddd72cfcff75d58df223cf895c47775e6ccb64d12f84080b5def"
SOURCE049_GROUP = "50f2540576ffc27621e9d6dabee9a44b0fadb843df0dc2bc8ce7c970131cc2db"
SOURCE049_ARTIFACT_PINS = {
    "original_envelope": "efd8bb1c4046fafae7bdf36dd2a07d5f14ee1ac0480696d3114789333946ece2",
    "original_state": "f82891c691c9d1908216b3b3dc0ad02058cc760db423e7b214bea9776b721377",
    "phase_0": "7c34425cfb0cb468989fa245945b355246316cb6af2fce1254ad497059084480",
    "phase_1": "400fd4df9b5072f98c3764abd14b4fad018a05936fc15e62a208662a9b28c8f7",
    "phase_2": "2d7b893b31c198bd805d100c5f92361627629924de62bde33d647ebc66024b5b",
    "phase_3": "bf7532b5f6061463276c803ec77c53fc046fa467f41ff85dc69c5289134467c9",
    "phase_4": "2e6b4b979950ca744fc2e6391e0d5d7a7dffc3cce78cfb9507675b2bf7a4c5a9",
    "phase_5": "0fd8c82493849eb20a75e9610742375b4da0509931a716c65ce9abc0b4ce40eb",
    "phase_6": "2db76d3c461c0108459b27254c2a47e15eed93b7771c9297c20f2b4245d84f2d",
    "prefix_closeout": "b2f62fcc3058e6f54bf2bc6560220b4f87d879cc4c4142e06ceffb2753b552cd",
    "prefix_context": "88d05ef7b1f79f164ec4664c85330d2006ddad34991ece75bba7a98548b4c23e",
    "prefix_envelope": "e1d1df5dcc5e4128d75b9660027746a2d7afd98e3e147d9b29b9bfb89687a5d8",
    "prefix_pair": "e2479cb4fc06ba127ba40104cc70824ba102e5792a478584ea6e74585d0358dc",
    "prefix_plan": "c5032935a2cc20087f3d5c84e304c58d70cabe482d67de739911b50663df307e",
    "prefix_result": "823c20cc2e376799f897209756fea8fe0daec185cb6463a493c812f79eb74443",
    "prefix_role": "913e78b60223337b71e3f95ab220b087e0b53600a11d22d4f573d301b2fc8eb5",
    "prefix_state": "d4d5dc054420548214abfe4716bc6e0eaece112148cb944d1c4789a8db29b36c",
    "registry": "6f09d9cc7996ad008447cce0a59f02c9b6c011fa4e4675a2293ac915ed687967",
    "role_registry": "81a36b43b8d4ab04600752c94b4f5922df335b342bc07ccb1749379dcc6dcb53",
}
_TEACHER_PREFIX_TOKEN = object()


@dataclass(frozen=True, init=False)
class VerifiedTeacherPrefixTrainSource:
    """Byte-authenticated seven-phase transport/quiz setup; correlated TRAIN."""

    _canonical: bytes

    def __init__(self, document, *, _token=None):
        if _token is not _TEACHER_PREFIX_TOKEN:
            raise ValueError("teacher prefix requires authenticated native artifacts")
        object.__setattr__(
            self,
            "_canonical",
            json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(),
        )

    def document(self):
        return json.loads(self._canonical)

    @property
    def identity(self):
        return sha256(self._canonical).hexdigest()

    @property
    def source_state_sha256(self):
        return SOURCE049_ARTIFACT_PINS["prefix_state"]

    @property
    def source_origin_sha256(self):
        return SOURCE049_ORIGIN

    @property
    def source_commit(self):
        return self.document()["source_commit"]

    def progress_bytes(self):
        """Exact fresh metadata; cannot invent an independent origin or omit costs."""
        return json.dumps(
            dict(
                schema="pokemon.red.production-teacher-train-progress.v1",
                partition="train",
                fit_allowed=True,
                campaign_eligible=False,
                role="train_sampling",
                source_origin_sha256=self.source_origin_sha256,
                source_profile="source049_teacher_prefix",
                source_group_sha256=SOURCE049_GROUP,
                independent_origin=False,
                failed_prefix_costs_retained=True,
                derived_source_proof_sha256=self.identity,
                envelope=self.document()["source_envelope"],
            ),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

    def require_source_context(self, state, context_bytes):
        _require(
            type(state) is bytes
            and type(context_bytes) is bytes
            and sha256(state).hexdigest() == self.source_state_sha256
            and sha256(context_bytes).hexdigest() == SOURCE049_ARTIFACT_PINS["prefix_context"],
            "teacher prefix paired state/context changed",
        )

    def require_metadata(self, envelope, progress):
        _require(
            envelope.get("state_sha256") == self.source_state_sha256
            and canonical_sha256(envelope) == self.document()["envelope_identity"]
            and progress.get("derived_source_proof_sha256") == self.identity
            and progress.get("source_profile") == "source049_teacher_prefix"
            and progress.get("source_group_sha256") == SOURCE049_GROUP
            and progress.get("independent_origin") is False
            and progress.get("failed_prefix_costs_retained") is True,
            "teacher prefix metadata differs or omits correlated history",
        )


def authenticate_teacher_prefix_train_source(*, artifacts, source_commit):
    """Authenticate one registered native prefix from immutable supplied bytes.

    Historical plans are provenance only. A current admission and exact work
    order are still required. This reads no file, runs no guest and grants no
    learned-parent credit, fit admission, new budget or independent origin.
    """
    _require(
        type(source_commit) is str
        and len(source_commit) == 40
        and all(c in "0123456789abcdef" for c in source_commit),
        "source commit differs",
    )
    _require(
        type(artifacts) is dict and set(artifacts) == set(SOURCE049_ARTIFACT_PINS),
        "teacher prefix artifact census differs",
    )
    for name, digest in SOURCE049_ARTIFACT_PINS.items():
        _require(
            type(artifacts[name]) is bytes and sha256(artifacts[name]).hexdigest() == digest,
            "teacher prefix artifact changed: " + name,
        )
    docs = {
        k: json.loads(v)
        for k, v in artifacts.items()
        if k not in ("original_state", "prefix_state")
    }
    registry = docs["registry"]["sources"][5]
    role = docs["role_registry"]["roles"][0]
    _require(
        registry["checkpoint_id"] == role["checkpoint_id"] == "red-goal-v1-049-resupply-train-04"
        and registry["assignment_id"] == SOURCE049_ORIGIN
        and registry["original_partition"] == role["execution_partition"] == "train"
        and role["group_sha256"] == SOURCE049_GROUP
        and role["independent_origin"] is False,
        "teacher prefix original TRAIN role/origin/group differs",
    )
    result, context, envelope, pair, close = (
        docs[k]
        for k in (
            "prefix_result",
            "prefix_context",
            "prefix_envelope",
            "prefix_pair",
            "prefix_closeout",
        )
    )
    _require(
        result["passed"] is True
        and result["teacher_selected"] is True
        and result["stop_reason"] == "before_first_observed_combat"
        and result["goal_attempts"] == close["teacher_support_phases"] == 7
        and result["story_battles"] == result["wild_battles"] == result["model_query_attempts"] == 0
        and result["controls_released"] is True
        and result["guest_backend_closed"] is True
        and result["terminal_field_ready"] is True
        and result["terminal_battle_state"] == 0
        and close["passed"] is True
        and close["all_native_workers_stopped"] is True
        and close["all_controls_released"] is True
        and close["failed_v1_costs_remain_additional"] is True
        and close["source_group_reassigned"] is False,
        "teacher prefix must be closed, noncombat and retain earlier failed costs",
    )
    trace = result["native_trace"]
    frame = 0
    for i, action in enumerate(trace):
        _require(
            action["ordinal"] == i
            and action["succeeded"] is True
            and action["before_frame"] == frame
            and action["after_frame"] > frame,
            "teacher prefix native trace is not contiguous",
        )
        frame = action["after_frame"]
    _require(
        len(trace) == result["actions"] == result["completed_actions"] == 272
        and frame == result["frames"] == 19692,
        "teacher prefix trace costs differ",
    )
    before_hash = SOURCE049_ARTIFACT_PINS["original_state"]
    previous_after = None
    actions = frames = 0
    for i in range(7):
        phase = docs[f"phase_{i}"]
        before, after = phase["before"], phase["after"]
        _require(
            phase["verification"] == "succeeded"
            and phase["teacher_selected"] is True
            and phase["model_queries"] == 0
            and phase["training_admission"] is False
            and (
                phase["evidence"].get("source_sha256") == before_hash
                if i == 0
                else before == previous_after
            )
            and before["actions"] == before["completed_actions"] == actions
            and before["frames"] == frames
            and after["buttons_released"] is True
            and after["input_ready"] is True
            and after["battle_state"] == 0,
            "teacher prefix phase/control chain differs",
        )
        actions += phase["actions"]
        frames += phase["frames"]
        _require(
            after["actions"] == after["completed_actions"] == actions and after["frames"] == frames,
            "teacher prefix phase costs differ",
        )
        before_hash = phase["terminal_state_sha256"]
        previous_after = after
    _require(
        before_hash
        == pair["terminal_sha256"]
        == context["state_sha256"]
        == SOURCE049_ARTIFACT_PINS["prefix_state"]
        and actions == 272
        and frames == 19692
        and context["spent"] == result["spent"]
        and context["battle"] is None
        and context["grants_new_budget"] is False
        and context["fit_allowed"] is False
        and "defeat_blaine" not in context["lesson"]["completed_objectives"],
        "teacher prefix terminal/context/costs differ",
    )
    return VerifiedTeacherPrefixTrainSource(
        dict(
            schema=TEACHER_PREFIX_SCHEMA,
            profile="source049_teacher_prefix",
            source_partition="train",
            source_state_sha256=before_hash,
            source_origin_sha256=SOURCE049_ORIGIN,
            source_group_sha256=SOURCE049_GROUP,
            source_commit=source_commit,
            artifact_sha256=SOURCE049_ARTIFACT_PINS,
            prefix_phase_count=7,
            envelope_identity=canonical_sha256(envelope),
            source_envelope=envelope,
            completed_objectives=context["lesson"]["completed_objectives"],
            cumulative_spent=context["spent"],
            native_closeout_seconds=result["native_seconds"],
            failed_v1_costs_remain_additional=True,
            teacher_selected=True,
            learned_strategy_credit=False,
            fit_admission=False,
            grants_new_budget=False,
            independent_origin=False,
        ),
        _token=_TEACHER_PREFIX_TOKEN,
    )


# One exact earned noncombat TRAIN unit, separate from the original d4 prefix.
# Historical closure grants no new execution. A fresh scoped work order is required.
EARNED_NONCOMBAT_SCHEMA = "pokemon.red.production-train-earned-noncombat.v1"
SOURCE049_EARNED_UNIT_PINS = {
    "state": "063b79bc1a1deca702be5623f9faf6ccc1c3314c193c8120a425525c0c7fbbaa",
    "context": "20197f11d1bf2d03235f6ca3bb25418d8e74ef4135ee481e33ff69e767a76ecf",
    "pair": "a7f8a7ebcc24d69aad37266d383898d15cf6025a622da4aa605921841fb6617d",
    "plan": "7dce1862d144275f326efa20ce8df7347ec91f96b64cf89f9c8e37526980a1b7",
    "result": "d6659c60130e081f8affcfeec17cf7e443f510337a181a48f5203231c80773c9",
    "attempt": "9d1db4a29615f549a0f564f4a1d87015a01ac9d79a4d62ac5660415f22f16353",
    "declaration": "a0ca24f177d3a2e38c6bf0fa838756953ff2e1b0d202b40db94e5f891ecefbc3",
    "outcome": "7e9842d5ece8befdf2be587bcf412a65222865a90b7df5dd855625b945060d9c",
    "strict_admission": "46cbe76b4d58ac5e73925bb18e2f9a02b8de2e25058b211f4da88335be99c970",
    "closed": "b5531e12dd068ce712cf1c5469eee3bc72b7609e95112b8cd1e2037d53f0566b",
    "failed_closed": "092dbdf7360e68b29017947477d6739da5d64edf6701969aadf13e7e793b2149",
}
_EARNED_NONCOMBAT_TOKEN = object()


@dataclass(frozen=True, init=False)
class VerifiedEarnedNoncombatTrainSource:
    """Immutable original-TRAIN ancestry plus one strictly admitted earned unit."""

    _canonical: bytes

    def __init__(self, document, *, _token=None):
        if _token is not _EARNED_NONCOMBAT_TOKEN:
            raise ValueError("earned TRAIN source requires authenticated native artifacts")
        object.__setattr__(
            self,
            "_canonical",
            json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(),
        )

    def document(self):
        return json.loads(self._canonical)

    @property
    def identity(self):
        return sha256(self._canonical).hexdigest()

    @property
    def source_state_sha256(self):
        return SOURCE049_EARNED_UNIT_PINS["state"]

    @property
    def source_origin_sha256(self):
        return SOURCE049_ORIGIN

    @property
    def source_commit(self):
        return self.document()["source_commit"]

    def envelope_bytes(self):
        return json.dumps(
            self.document()["source_envelope"],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode()

    def progress_bytes(self):
        # Sampling eligibility only; the witness grants no fit or runtime authority.
        return json.dumps(
            dict(
                schema="pokemon.red.production-earned-train-progress.v1",
                partition="train",
                fit_allowed=True,
                campaign_eligible=False,
                role="train_sampling",
                source_origin_sha256=SOURCE049_ORIGIN,
                source_profile="source049_earned_noncombat",
                source_group_sha256=SOURCE049_GROUP,
                independent_origin=False,
                failed_prefix_costs_retained=True,
                failed_unit_costs_retained=True,
                derived_source_proof_sha256=self.identity,
                envelope=self.document()["source_envelope"],
            ),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode()

    def require_source_context(self, state, context_bytes):
        _require(
            type(state) is bytes
            and type(context_bytes) is bytes
            and sha256(state).hexdigest() == self.source_state_sha256
            and sha256(context_bytes).hexdigest() == SOURCE049_EARNED_UNIT_PINS["context"],
            "earned unit paired state/context changed",
        )

    def require_metadata(self, envelope, progress):
        _require(
            envelope == self.document()["source_envelope"]
            and progress == json.loads(self.progress_bytes()),
            "earned unit metadata differs or omits its original TRAIN history",
        )


def authenticate_earned_noncombat_train_source(*, parent_artifacts, unit_artifacts, source_commit):
    """Pure authentication of the fixed source049 departure; no guest or inference.

    The old strict admission proves one recorded arrival, not a future label.
    Its diagnostic pair remains non-resumable without a new exact TRAIN work order.
    """
    parent = authenticate_teacher_prefix_train_source(
        artifacts=parent_artifacts, source_commit=source_commit
    )
    _require(
        type(unit_artifacts) is dict and set(unit_artifacts) == set(SOURCE049_EARNED_UNIT_PINS),
        "earned unit artifact census differs",
    )
    for name, digest in SOURCE049_EARNED_UNIT_PINS.items():
        _require(
            type(unit_artifacts[name]) is bytes
            and sha256(unit_artifacts[name]).hexdigest() == digest,
            "earned unit artifact changed: " + name,
        )
    d = {k: json.loads(v) for k, v in unit_artifacts.items() if k != "state"}
    plan, result, attempt, declaration, outcome, strict, closed, failed, context, pair = (
        d[k]
        for k in (
            "plan",
            "result",
            "attempt",
            "declaration",
            "outcome",
            "strict_admission",
            "closed",
            "failed_closed",
            "context",
            "pair",
        )
    )
    original = json.loads(parent_artifacts["prefix_context"])
    historical_parent = authenticate_teacher_prefix_train_source(
        artifacts=parent_artifacts, source_commit=plan["source_commit"]
    )
    _require(
        plan["partition"]
        == declaration["partition"]
        == declaration["source"]["partition"]
        == "train"
        and declaration["source"]["origin_sha256"] == SOURCE049_ORIGIN
        and declaration["source"]["state_sha256"]
        == plan["source_state_sha256"]
        == parent.source_state_sha256
        and declaration["source"]["source_commit"] == plan["source_commit"]
        and declaration["source"]["setup_receipt_sha256"]
        == plan["source_proof_sha256"]
        == historical_parent.identity
        and result["source_proof"] == historical_parent.document()
        and plan["production_train_components"]["noncombat_objective_ids"] == ["obtain_strength"]
        and plan["source_group_reassigned"] is False,
        "earned unit original TRAIN lineage or declared noncombat scope differs",
    )
    declaration_id, outcome_id = canonical_sha256(declaration), canonical_sha256(outcome)
    _require(
        declaration["schema"] == "pokemon.red.native-curriculum-declaration.v10"
        and outcome["schema"] == "pokemon.red.native-curriculum-outcome.v10"
        and declaration["teacher_selected"] is True
        and declaration["comparative_choice"] is False
        and declaration["story_approach_only"] is True
        and declaration["player_lesson"]["target"] == {"objective": "obtain_strength"}
        and declaration["story_unit"]["target"] == {"kind": "arrival", "map_id": 8, "at": None}
        and declaration["story_unit"]["before"] == {"map_id": 166, "at": [8, 1], "events": []}
        and outcome["story_unit"] == {"map_id": 8, "at": [4, 18], "events": []}
        and outcome["declaration_sha256"] == result["declaration_sha256"] == declaration_id
        and attempt["outcome"]
        == {"declaration_sha256": declaration_id, "outcome_sha256": outcome_id}
        and strict["arm"]["native_curriculum"] == attempt["outcome"]
        and outcome["succeeded"] is True
        and outcome["interventions_during_execution"] == [],
        "earned unit strict arrival identity or teacher attribution differs",
    )
    _require(
        all(
            result[k] is True
            for k in (
                "passed",
                "lesson_succeeded",
                "outcome_admitted",
                "controls_released",
                "guest_backend_closed",
                "teacher_selected",
            )
        )
        and result["model_queries"] == result["parent_model_queries"] == result["fits"] == 0
        and result["labels"] == 1
        and result["native_error_chain"] == []
        and result["source_group_reassigned"] is False
        and result["independent_origin"] is False
        and attempt["admitted"] is True
        and attempt["succeeded"] is True
        and attempt["execution_or_verification_failed"] is False
        and strict["qualified"] is True
        and strict["all_attempts_and_costs_retained"] is True
        and strict["full_costs_qualified"] is True
        and strict["training_group_reassigned"] is False,
        "earned unit was not strictly admitted with retained costs and no queries",
    )
    state_hash = SOURCE049_EARNED_UNIT_PINS["state"]
    _require(
        context["state_sha256"]
        == pair["terminal_state_sha256"]
        == outcome["terminal_state_sha256"]
        == attempt["terminal_state_sha256"]
        == state_hash
        and context["lesson"] == outcome["player_lesson"] == attempt["player_lesson"]
        and outcome["after"] == attempt["after"]
        and context["lesson"]["completed_objectives"] == original["lesson"]["completed_objectives"]
        and context["lesson"]["in_battle"] is False
        and context["battle"] is None
        and context["grants_new_budget"] is False
        and context["fit_allowed"] is False
        and "obtain_strength" not in context["lesson"]["completed_objectives"]
        and outcome["native_audit"]
        == dict(
            before_sha256=parent.source_state_sha256,
            input_frames=0,
            passed=True,
            terminal_sha256=state_hash,
        ),
        "earned unit terminal/context differs from its native outcome",
    )
    trace = outcome["trace"]
    _require(trace == attempt["trace"], "earned unit traces differ")
    frame = 0
    for i, row in enumerate(trace):
        _require(
            row["ordinal"] == i
            and row["before_frame"] == frame
            and row["succeeded"] is True
            and row["after_frame"] > frame,
            "earned unit trace is not contiguous",
        )
        frame = row["after_frame"]
    _require(
        len(trace) == attempt["actions_attempted"] == attempt["actions_completed"] == 59
        and frame == attempt["frames"] == result["frames"] == 1512,
        "earned unit measured action/frame costs differ",
    )
    for key, delta in (("actions", 59), ("frames", 1512), ("decisions", 1)):
        _require(
            context["spent"][key] == original["spent"][key] + delta,
            "earned unit cumulative cost differs: " + key,
        )
    _costs(context["spent"])
    _require(
        context["spent"]["seconds"] >= original["spent"]["seconds"]
        and context["spent"]["cash_debits"] == original["spent"]["cash_debits"] == 0
        and context["cash"] == original["cash"]
        and context["bag"] == original["bag"]
        and pair["exact_source_context_sha256"] == SOURCE049_ARTIFACT_PINS["prefix_context"]
        and pair["costs_are_lower_bounds"] is True
        and pair["outer_and_prior_failed_costs_remain_additional"] is True
        and pair["continuation_authority"] is False
        and pair["copy_back"] is False,
        "earned unit source pair or lower-bound accounting differs",
    )
    for label, closure in (("closed", closed), ("failed_closed", failed)):
        _require(
            all(
                closure[k] is True
                for k in (
                    "all_processes_stopped",
                    "all_controls_released",
                    "guest_backend_closed",
                    "paired_tail",
                    "prior_costs_retained",
                )
            )
            and closure["continuation_authority"] is False
            and closure["copy_back"] is False
            and closure["costs_are_lower_bounds"] is True
            and closure["known_costs"]["physical_loads"] == 1,
            "earned unit closure or failed-attempt costs differ: " + label,
        )
    _require(
        closed["native_result_passed"] is True
        and closed["native_exit_code"] == 0
        and closed["timed_out"] is False
        and closed["terminal"]["sha256"] == state_hash
        and closed["context"]["sha256"] == SOURCE049_EARNED_UNIT_PINS["context"]
        and closed["result"]["sha256"] == SOURCE049_EARNED_UNIT_PINS["result"]
        and closed["known_costs"]["actions"] == 59
        and closed["known_costs"]["frames"] == 1512
        and {v["sha256"] for v in strict["all_attempt_receipts"]}
        == {SOURCE049_EARNED_UNIT_PINS["closed"], SOURCE049_EARNED_UNIT_PINS["failed_closed"]},
        "earned unit strict closure census or exact terminal differs",
    )
    envelope = deepcopy(parent.document()["source_envelope"])
    envelope.update(
        checkpoint_id="source049-earned-noncombat-063b79",
        checkpoint_label="Earned native TRAIN indoor departure; no flight or Strength completion",
        state_sha256=state_hash,
        verified_objective_ids=context["lesson"]["completed_objectives"],
        checkpoints_completed=len(context["lesson"]["completed_objectives"]),
    )
    return VerifiedEarnedNoncombatTrainSource(
        dict(
            schema=EARNED_NONCOMBAT_SCHEMA,
            profile="source049_earned_noncombat",
            source_state_sha256=state_hash,
            context_content_sha256=SOURCE049_EARNED_UNIT_PINS["context"],
            source_origin_sha256=SOURCE049_ORIGIN,
            source_group_sha256=SOURCE049_GROUP,
            source_partition="train",
            source_commit=source_commit,
            parent_proof_sha256=parent.identity,
            parent_source_state_sha256=parent.source_state_sha256,
            parent_artifact_sha256=SOURCE049_ARTIFACT_PINS,
            unit_artifact_sha256=SOURCE049_EARNED_UNIT_PINS,
            native_declaration_sha256=declaration_id,
            native_outcome_sha256=outcome_id,
            source_envelope=envelope,
            completed_objectives=context["lesson"]["completed_objectives"],
            cumulative_spent=context["spent"],
            costs_are_lower_bounds=True,
            closed_attempt_costs={
                "succeeded": closed["known_costs"],
                "failed": failed["known_costs"],
            },
            native_seconds_are_nested=True,
            parent_failed_costs_remain_additional=True,
            allowed_noncombat_objective_ids=["obtain_strength"],
            teacher_selected=True,
            independent_origin=False,
            fit_admission=False,
            campaign_eligible=False,
            grants_new_budget=False,
            continuation_authority=False,
        ),
        _token=_EARNED_NONCOMBAT_TOKEN,
    )
