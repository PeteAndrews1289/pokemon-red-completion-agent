"""Crash-safe execution of one model-led held development decision.

The causal collector randomizes train arms to preserve support.  Development
has a different job: evaluate one exact fitted policy without turning its
outcome back into training data.  This journal claims the logical/physical
root, seals the complete model decision, validates the selected runtime behind
a locked controller gate, and seals an independently observed outcome.

Recovery may reconstruct only before controller release and only while the
same protected effect meter remains unchanged.  A release without a durable
outcome is permanently interrupted; no model, teacher, or fallback may retry
the gameplay branch.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pokemon_red_completion.claim_first_admission import (
    ClaimFirstAdmissionError,
    ClaimFirstRootPair,
    claim_first_pair_registry,
    read_root_pair_claim,
)
from pokemon_red_completion.living_dex_causal_journal import (
    LivingDexCausalEffectCheckpoint,
    LivingDexCausalJournalError,
    LivingDexCausalObservation,
    LivingDexCausalResolvedArm,
    LivingDexCausalScenario,
    LivingDexControllerGate,
    restore_living_dex_observed_outcome,
)
from pokemon_red_completion.living_dex_option_value import (
    LivingDexCensorReason,
    LivingDexObservedOutcome,
    LivingDexOptionUtility,
    LivingDexOptionValueModel,
    LivingDexOutcomeStatus,
)
from pokemon_red_completion.living_dex_policy_development import (
    LivingDexPolicyDevelopmentDecision,
    commit_living_dex_policy_development_decision,
)
from pokemon_red_completion.private_artifacts import (
    PrivateArtifactError,
    PrivateArtifactRoot,
)
from pokemon_red_completion.provenance import canonical_sha256

LIVING_DEX_POLICY_DEVELOPMENT_COLLECTION_ID = "living-dex-policy-development-v1"
LIVING_DEX_POLICY_DEVELOPMENT_STORE_ANCHOR_SCHEMA = (
    "pokemon.core.private-living-dex-policy-development-store-anchor.v1"
)
LIVING_DEX_POLICY_DEVELOPMENT_RESULT_SCHEMA = (
    "pokemon.core.private-living-dex-policy-development-result.v1"
)
LIVING_DEX_POLICY_DEVELOPMENT_TERMINAL_SCHEMA = (
    "pokemon.core.private-living-dex-policy-development-terminal.v1"
)
LIVING_DEX_POLICY_DEVELOPMENT_RECEIPT_SCHEMA = (
    "pokemon.core.living-dex-policy-development-receipt.v1"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class LivingDexPolicyDevelopmentJournalError(RuntimeError):
    """A held policy execution cannot be authenticated or recovered safely."""


class LivingDexPolicyDevelopmentDisposition(StrEnum):
    EXECUTED_SETTLED = "executed_settled"
    EXECUTED_CENSORED = "executed_censored"
    EXECUTED_PREINPUT_FAILED = "executed_preinput_failed"
    RECOVERED_COMPLETE = "recovered_complete"
    RECOVERED_PREINPUT_FAILED = "recovered_preinput_failed"
    RECOVERED_INTERRUPTED = "recovered_interrupted"


class LivingDexPolicyDevelopmentTerminalStatus(StrEnum):
    COMPLETE = "complete"
    PREINPUT_FAILED = "preinput_failed"
    POSTRELEASE_INTERRUPTED = "postrelease_interrupted"


@dataclass(frozen=True, slots=True)
class LivingDexPolicyDevelopmentResult:
    """One factual selected-arm outcome; never a training example."""

    causal_identity_sha256: str
    pair_claim_sha256: str
    decision_sha256: str
    selected_candidate_index: int
    selected_binding_sha256: str
    outcome: LivingDexObservedOutcome
    controller_action_delta: int
    emulator_frame_delta: int
    execution_status: str
    execution_exception_type: str | None
    action_trace: Mapping[str, object]
    provenance: Mapping[str, object]

    def __post_init__(self) -> None:
        for value, subject in (
            (self.causal_identity_sha256, "causal identity"),
            (self.pair_claim_sha256, "pair claim"),
            (self.decision_sha256, "decision"),
            (self.selected_binding_sha256, "selected binding"),
        ):
            _require_sha256(value, subject)
        if (
            type(self.selected_candidate_index) is not int  # noqa: E721
            or self.selected_candidate_index < 0
            or type(self.controller_action_delta) is not int  # noqa: E721
            or self.controller_action_delta < 0
            or type(self.emulator_frame_delta) is not int  # noqa: E721
            or self.emulator_frame_delta < 0
            or self.execution_status not in {"returned", "raised_exception"}
            or (
                self.execution_status == "returned"
                and self.execution_exception_type is not None
            )
            or (
                self.execution_status == "raised_exception"
                and (
                    not isinstance(self.execution_exception_type, str)
                    or not self.execution_exception_type
                )
            )
        ):
            raise LivingDexPolicyDevelopmentJournalError(
                "development result execution evidence differs"
            )
        if not isinstance(self.outcome, LivingDexObservedOutcome):
            raise TypeError("development result needs an observed outcome")
        self.outcome.__post_init__()
        for evidence, subject in (
            (self.action_trace, "action trace"),
            (self.provenance, "outcome provenance"),
        ):
            if not isinstance(evidence, Mapping):
                raise TypeError(f"development result needs {subject}")
            canonical_sha256(evidence)

    @property
    def result_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    def private_dict(self) -> dict[str, object]:
        return {
            "action_trace": dict(self.action_trace),
            "causal_identity_sha256": self.causal_identity_sha256,
            "controller_action_delta": self.controller_action_delta,
            "decision_sha256": self.decision_sha256,
            "emulator_frame_delta": self.emulator_frame_delta,
            "execution_exception_type": self.execution_exception_type,
            "execution_status": self.execution_status,
            "outcome": self.outcome.public_dict(),
            "pair_claim_sha256": self.pair_claim_sha256,
            "provenance": dict(self.provenance),
            "schema": LIVING_DEX_POLICY_DEVELOPMENT_RESULT_SCHEMA,
            "selected_binding_sha256": self.selected_binding_sha256,
            "selected_candidate_index": self.selected_candidate_index,
            "training_targets_emitted": 0,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            "controller_action_delta": self.controller_action_delta,
            "emulator_frame_delta": self.emulator_frame_delta,
            "execution_status": self.execution_status,
            "outcome": self.outcome.public_dict(),
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "selected_candidate_index": self.selected_candidate_index,
            "training_targets_emitted": 0,
        }


@dataclass(frozen=True, slots=True)
class LivingDexPolicyDevelopmentTerminal:
    causal_identity_sha256: str
    pair_claim_sha256: str
    decision_sha256: str
    status: LivingDexPolicyDevelopmentTerminalStatus
    result_sha256: str | None
    reason_code: str | None
    retry_allowed: bool = False

    def __post_init__(self) -> None:
        for value, subject in (
            (self.causal_identity_sha256, "terminal causal identity"),
            (self.pair_claim_sha256, "terminal pair claim"),
            (self.decision_sha256, "terminal decision"),
        ):
            _require_sha256(value, subject)
        if not isinstance(self.status, LivingDexPolicyDevelopmentTerminalStatus):
            raise LivingDexPolicyDevelopmentJournalError(
                "development terminal status differs"
            )
        if self.status is LivingDexPolicyDevelopmentTerminalStatus.COMPLETE:
            _require_sha256(self.result_sha256, "terminal result")
            if self.reason_code is not None:
                raise LivingDexPolicyDevelopmentJournalError(
                    "complete development terminal has a reason"
                )
        elif (
            self.result_sha256 is not None
            or not isinstance(self.reason_code, str)
            or not self.reason_code
        ):
            raise LivingDexPolicyDevelopmentJournalError(
                "noncomplete development terminal evidence differs"
            )
        if self.retry_allowed:
            raise LivingDexPolicyDevelopmentJournalError(
                "development terminal cannot retry"
            )

    def private_dict(self) -> dict[str, object]:
        return {
            "causal_identity_sha256": self.causal_identity_sha256,
            "decision_sha256": self.decision_sha256,
            "pair_claim_sha256": self.pair_claim_sha256,
            "reason_code": self.reason_code,
            "result_sha256": self.result_sha256,
            "retry_allowed": self.retry_allowed,
            "schema": LIVING_DEX_POLICY_DEVELOPMENT_TERMINAL_SCHEMA,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class LivingDexPolicyDevelopmentReceipt:
    decision: LivingDexPolicyDevelopmentDecision
    disposition: LivingDexPolicyDevelopmentDisposition
    terminal: LivingDexPolicyDevelopmentTerminal
    result: LivingDexPolicyDevelopmentResult | None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, LivingDexPolicyDevelopmentDecision):
            raise TypeError("development receipt needs its decision")
        self.decision.__post_init__()
        if not isinstance(self.disposition, LivingDexPolicyDevelopmentDisposition):
            raise LivingDexPolicyDevelopmentJournalError(
                "development receipt disposition differs"
            )
        if not isinstance(self.terminal, LivingDexPolicyDevelopmentTerminal):
            raise TypeError("development receipt needs its terminal")
        self.terminal.__post_init__()
        if (
            self.terminal.decision_sha256 != self.decision.decision_sha256
            or self.terminal.causal_identity_sha256
            != self.decision.causal_identity_sha256
        ):
            raise LivingDexPolicyDevelopmentJournalError(
                "development receipt identity differs"
            )
        if self.terminal.status is LivingDexPolicyDevelopmentTerminalStatus.COMPLETE:
            if (
                not isinstance(self.result, LivingDexPolicyDevelopmentResult)
                or self.result.result_sha256 != self.terminal.result_sha256
            ):
                raise LivingDexPolicyDevelopmentJournalError(
                    "complete development receipt lacks its result"
                )
        elif self.result is not None:
            raise LivingDexPolicyDevelopmentJournalError(
                "noncomplete development receipt retained a result"
            )

    def public_dict(self) -> dict[str, object]:
        return {
            "authority_promotions_added": 0,
            "decision": self.decision.public_dict(),
            "development_outcomes_opened": int(self.result is not None),
            "disposition": self.disposition.value,
            "model_fits": 0,
            "model_predictions": 1,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "result": None if self.result is None else self.result.public_dict(),
            "retry_allowed": False,
            "schema": LIVING_DEX_POLICY_DEVELOPMENT_RECEIPT_SCHEMA,
            "teacher_queries": 0,
            "training_targets_emitted": 0,
            "transfer_results_added": 0,
        }


def execute_living_dex_policy_development(
    scenario: LivingDexCausalScenario,
    model: LivingDexOptionValueModel,
    *,
    utility: LivingDexOptionUtility,
    expected_model_sha256: str,
    store: PrivateArtifactRoot,
    claim_registry: Path,
    failpoint: Callable[[str], None] | None = None,
) -> LivingDexPolicyDevelopmentReceipt:
    """Execute or recover one exact model-selected development branch."""

    if not isinstance(scenario, LivingDexCausalScenario):
        raise TypeError("development journal needs a causal scenario")
    scenario.__post_init__()
    if scenario.identity.partition != "development":
        raise LivingDexPolicyDevelopmentJournalError(
            "development journal received another partition"
        )
    if not isinstance(store, PrivateArtifactRoot):
        raise TypeError("development journal needs a private artifact root")
    if not isinstance(claim_registry, Path):
        raise TypeError("development journal needs a claim registry Path")
    if failpoint is not None and not callable(failpoint):
        raise TypeError("development journal failpoint must be callable")

    try:
        with store.collection_session(LIVING_DEX_POLICY_DEVELOPMENT_COLLECTION_ID):
            anchor = _ensure_store_anchor(store)
            pair = _ensure_pair_claim(
                scenario,
                claim_registry,
                store_anchor_sha256=anchor,
            )
            _trip(failpoint, "after_pair_claim")
            _publish_exact(
                store,
                _record_id("claim", scenario),
                kind="living_dex_policy_development_claim",
                record={
                    "causal_identity": scenario.identity.private_dict(),
                    "causal_identity_sha256": scenario.identity.identity_sha256,
                    "pair_claim": pair.private_dict(),
                    "pair_claim_sha256": pair.claim_sha256,
                    "schema": (
                        "pokemon.core.private-living-dex-policy-development-claim.v1"
                    ),
                    "store_anchor_sha256": anchor,
                },
            )
            decision = commit_living_dex_policy_development_decision(
                scenario,
                model,
                utility=utility,
                expected_model_sha256=expected_model_sha256,
            )
            _publish_exact(
                store,
                _record_id("decision", scenario),
                kind="living_dex_policy_development_decision",
                record=decision.private_dict(),
            )
            _trip(failpoint, "after_decision")

            result = _find_result(store, scenario, pair, decision)
            terminal = _find_terminal(store, scenario, pair, decision, result)
            if terminal is not None:
                return _receipt_from_terminal(decision, terminal, result)
            if result is not None:
                terminal = _publish_terminal(
                    store,
                    scenario,
                    pair,
                    decision,
                    status=LivingDexPolicyDevelopmentTerminalStatus.COMPLETE,
                    result_sha256=result.result_sha256,
                    reason_code=None,
                )
                return LivingDexPolicyDevelopmentReceipt(
                    decision,
                    LivingDexPolicyDevelopmentDisposition.RECOVERED_COMPLETE,
                    terminal,
                    result,
                )
            release = _find_exact_record(
                store,
                _record_id("release", scenario),
                kind="living_dex_policy_development_release",
            )
            if release is not None:
                _validate_release(release, scenario, pair, decision)
                terminal = _publish_terminal(
                    store,
                    scenario,
                    pair,
                    decision,
                    status=(
                        LivingDexPolicyDevelopmentTerminalStatus.POSTRELEASE_INTERRUPTED
                    ),
                    result_sha256=None,
                    reason_code="controller_released_without_durable_outcome",
                )
                return LivingDexPolicyDevelopmentReceipt(
                    decision,
                    LivingDexPolicyDevelopmentDisposition.RECOVERED_INTERRUPTED,
                    terminal,
                    None,
                )

            before = scenario.effect_meter.checkpoint()
            construction = {
                "causal_identity_sha256": scenario.identity.identity_sha256,
                "decision_sha256": decision.decision_sha256,
                "effect_checkpoint": before.private_dict(),
                "effect_meter_binding_sha256": scenario.effect_meter.binding_sha256,
                "effect_meter_recovery_instance_sha256": (
                    scenario.effect_meter.recovery_instance_sha256
                ),
                "pair_claim_sha256": pair.claim_sha256,
                "schema": (
                    "pokemon.core.private-living-dex-policy-development-construction.v1"
                ),
            }
            _publish_exact(
                store,
                _record_id("construct", scenario),
                kind="living_dex_policy_development_construction",
                record=construction,
            )
            _trip(failpoint, "after_construction")
            return _execute_selected(
                scenario,
                decision=decision,
                pair=pair,
                before=before,
                store=store,
                failpoint=failpoint,
            )
    except LivingDexPolicyDevelopmentJournalError:
        raise
    except (ClaimFirstAdmissionError, PrivateArtifactError) as error:
        raise LivingDexPolicyDevelopmentJournalError(str(error)) from None
    raise AssertionError("development collection session suppressed an exception")


def _execute_selected(
    scenario: LivingDexCausalScenario,
    *,
    decision: LivingDexPolicyDevelopmentDecision,
    pair: ClaimFirstRootPair,
    before: LivingDexCausalEffectCheckpoint,
    store: PrivateArtifactRoot,
    failpoint: Callable[[str], None] | None,
) -> LivingDexPolicyDevelopmentReceipt:
    gate = LivingDexControllerGate()
    released = False
    try:
        with scenario.resolve_selected(decision.selected_candidate_index, gate) as arm:
            _validate_resolved_arm(scenario, decision, arm, gate, before)
            release = {
                "causal_identity_sha256": scenario.identity.identity_sha256,
                "decision_sha256": decision.decision_sha256,
                "effect_checkpoint": before.private_dict(),
                "pair_claim_sha256": pair.claim_sha256,
                "schema": (
                    "pokemon.core.private-living-dex-policy-development-release.v1"
                ),
                "selected_binding_sha256": arm.binding_sha256,
                "selected_candidate_index": decision.selected_candidate_index,
            }
            _publish_exact(
                store,
                _record_id("release", scenario),
                kind="living_dex_policy_development_release",
                record=release,
            )
            released = True
            _trip(failpoint, "after_controller_release")
            gate.authorize_controller_input()

            execution_status = "returned"
            execution_exception_type: str | None = None
            try:
                arm.execute(gate)
            except Exception as error:
                execution_status = "raised_exception"
                execution_exception_type = type(error).__name__
            after_execution = scenario.effect_meter.checkpoint()
            action_trace, trace_valid = _read_action_trace(arm)
            observation = _observe_after(scenario, after_execution)
            if not trace_valid:
                observation = LivingDexCausalObservation(
                    _censored(LivingDexCensorReason.PROVENANCE_FAILED),
                    {
                        "reason_code": "action_trace_unavailable",
                        "schema": (
                            "pokemon.core.private-policy-development-observation-failure.v1"
                        ),
                    },
                )
            after_observation = scenario.effect_meter.checkpoint()
            if after_observation != after_execution:
                observation = LivingDexCausalObservation(
                    _censored(LivingDexCensorReason.PROVENANCE_FAILED),
                    {
                        "reason_code": "observer_changed_effect_meter",
                        "schema": (
                            "pokemon.core.private-policy-development-observation-failure.v1"
                        ),
                    },
                )
            action_delta, frame_delta = before.delta(after_execution)
            result = LivingDexPolicyDevelopmentResult(
                scenario.identity.identity_sha256,
                pair.claim_sha256,
                decision.decision_sha256,
                decision.selected_candidate_index,
                arm.binding_sha256,
                observation.outcome,
                action_delta,
                frame_delta,
                execution_status,
                execution_exception_type,
                action_trace,
                dict(observation.provenance),
            )
            _publish_exact(
                store,
                _record_id("result", scenario),
                kind="living_dex_policy_development_result",
                record=result.private_dict(),
            )
            _trip(failpoint, "after_result")
    except BaseException as error:
        if released:
            with suppress(Exception):
                _publish_terminal(
                    store,
                    scenario,
                    pair,
                    decision,
                    status=(
                        LivingDexPolicyDevelopmentTerminalStatus.POSTRELEASE_INTERRUPTED
                    ),
                    result_sha256=None,
                    reason_code="controller_released_without_durable_outcome",
                )
            raise
        if not isinstance(error, Exception):
            raise
        terminal = _publish_terminal(
            store,
            scenario,
            pair,
            decision,
            status=LivingDexPolicyDevelopmentTerminalStatus.PREINPUT_FAILED,
            result_sha256=None,
            reason_code="selected_runtime_construction_failed",
        )
        return LivingDexPolicyDevelopmentReceipt(
            decision,
            LivingDexPolicyDevelopmentDisposition.EXECUTED_PREINPUT_FAILED,
            terminal,
            None,
        )
    terminal = _publish_terminal(
        store,
        scenario,
        pair,
        decision,
        status=LivingDexPolicyDevelopmentTerminalStatus.COMPLETE,
        result_sha256=result.result_sha256,
        reason_code=None,
    )
    _trip(failpoint, "after_terminal")
    disposition = (
        LivingDexPolicyDevelopmentDisposition.EXECUTED_SETTLED
        if result.outcome.status is LivingDexOutcomeStatus.SETTLED
        else LivingDexPolicyDevelopmentDisposition.EXECUTED_CENSORED
    )
    return LivingDexPolicyDevelopmentReceipt(decision, disposition, terminal, result)


def _validate_resolved_arm(
    scenario: LivingDexCausalScenario,
    decision: LivingDexPolicyDevelopmentDecision,
    arm: LivingDexCausalResolvedArm,
    gate: LivingDexControllerGate,
    before: LivingDexCausalEffectCheckpoint,
) -> None:
    if not isinstance(arm, LivingDexCausalResolvedArm):
        raise TypeError("development resolver returned another arm type")
    arm.__post_init__()
    if (
        gate.released
        or arm.binding_sha256
        != scenario.binding_sha256s[decision.selected_candidate_index]
        or arm.effect_meter is not scenario.effect_meter
        or arm.effect_meter.checkpoint() != before
    ):
        raise LivingDexPolicyDevelopmentJournalError(
            "development selected runtime changed before release"
        )


def _read_action_trace(
    arm: LivingDexCausalResolvedArm,
) -> tuple[dict[str, object], bool]:
    try:
        trace = arm.action_trace()
        if not isinstance(trace, Mapping):
            raise TypeError("development action trace differs")
        result = dict(trace)
        canonical_sha256(result)
        return result, True
    except Exception:
        return {
            "reason_code": "action_trace_unavailable",
            "schema": "pokemon.core.private-policy-development-trace-failure.v1",
        }, False


def _observe_after(
    scenario: LivingDexCausalScenario,
    after_execution: LivingDexCausalEffectCheckpoint,
) -> LivingDexCausalObservation:
    try:
        observation = scenario.observe_after()
        if not isinstance(observation, LivingDexCausalObservation):
            raise TypeError("development observer returned another type")
        observation.__post_init__()
        if scenario.effect_meter.checkpoint() != after_execution:
            raise LivingDexPolicyDevelopmentJournalError(
                "development observer changed protected effects"
            )
        return LivingDexCausalObservation(
            observation.outcome,
            dict(observation.provenance),
        )
    except Exception as error:
        return LivingDexCausalObservation(
            _censored(LivingDexCensorReason.OBSERVATION_FAILED),
            {
                "exception_type": type(error).__name__,
                "reason_code": "observer_failed",
                "schema": (
                    "pokemon.core.private-policy-development-observation-failure.v1"
                ),
            },
        )


def _censored(reason: LivingDexCensorReason) -> LivingDexObservedOutcome:
    return LivingDexObservedOutcome(
        LivingDexOutcomeStatus.CENSORED,
        censor_reason=reason,
    )


def _ensure_store_anchor(store: PrivateArtifactRoot) -> str:
    record_id = "living-dex-policy-development-store-anchor-v1"
    record = store.find_sealed_record(
        record_id,
        expected_kind="living_dex_policy_development_store_anchor",
    )
    if record is None:
        record = store.publish_sealed_record(
            record_id,
            kind="living_dex_policy_development_store_anchor",
            record={
                "anchor_secret_hex": secrets.token_hex(32),
                "collection_id": LIVING_DEX_POLICY_DEVELOPMENT_COLLECTION_ID,
                "schema": LIVING_DEX_POLICY_DEVELOPMENT_STORE_ANCHOR_SCHEMA,
            },
        )
    document = record.read()
    if (
        set(document) != {"anchor_secret_hex", "collection_id", "schema"}
        or document["schema"] != LIVING_DEX_POLICY_DEVELOPMENT_STORE_ANCHOR_SCHEMA
        or document["collection_id"] != LIVING_DEX_POLICY_DEVELOPMENT_COLLECTION_ID
        or not isinstance(document["anchor_secret_hex"], str)
        or _SHA256.fullmatch(document["anchor_secret_hex"]) is None
    ):
        raise LivingDexPolicyDevelopmentJournalError(
            "development store anchor differs"
        )
    return canonical_sha256(document)


def _ensure_pair_claim(
    scenario: LivingDexCausalScenario,
    registry: Path,
    *,
    store_anchor_sha256: str,
) -> ClaimFirstRootPair:
    expected = scenario.identity.pair_claim_for_store(store_anchor_sha256)
    try:
        restored = read_root_pair_claim(registry, expected.claim_sha256)
    except ClaimFirstAdmissionError:
        try:
            with claim_first_pair_registry(registry) as transaction:
                restored = transaction.claim(expected)
        except ClaimFirstAdmissionError as claim_error:
            try:
                restored = read_root_pair_claim(registry, expected.claim_sha256)
            except ClaimFirstAdmissionError:
                raise claim_error from None
    if restored != expected:
        raise LivingDexPolicyDevelopmentJournalError(
            "development pair claim differs"
        )
    return restored


def _publish_terminal(
    store: PrivateArtifactRoot,
    scenario: LivingDexCausalScenario,
    pair: ClaimFirstRootPair,
    decision: LivingDexPolicyDevelopmentDecision,
    *,
    status: LivingDexPolicyDevelopmentTerminalStatus,
    result_sha256: str | None,
    reason_code: str | None,
) -> LivingDexPolicyDevelopmentTerminal:
    terminal = LivingDexPolicyDevelopmentTerminal(
        scenario.identity.identity_sha256,
        pair.claim_sha256,
        decision.decision_sha256,
        status,
        result_sha256,
        reason_code,
    )
    _publish_exact(
        store,
        _record_id("terminal", scenario),
        kind="living_dex_policy_development_terminal",
        record=terminal.private_dict(),
    )
    return terminal


def _find_terminal(
    store: PrivateArtifactRoot,
    scenario: LivingDexCausalScenario,
    pair: ClaimFirstRootPair,
    decision: LivingDexPolicyDevelopmentDecision,
    result: LivingDexPolicyDevelopmentResult | None,
) -> LivingDexPolicyDevelopmentTerminal | None:
    document = _find_exact_record(
        store,
        _record_id("terminal", scenario),
        kind="living_dex_policy_development_terminal",
    )
    if document is None:
        return None
    try:
        terminal = LivingDexPolicyDevelopmentTerminal(
            _text(document, "causal_identity_sha256"),
            _text(document, "pair_claim_sha256"),
            _text(document, "decision_sha256"),
            LivingDexPolicyDevelopmentTerminalStatus(_text(document, "status")),
            _optional_text(document, "result_sha256"),
            _optional_text(document, "reason_code"),
            bool(document.get("retry_allowed")),
        )
    except (TypeError, ValueError):
        raise LivingDexPolicyDevelopmentJournalError(
            "stored development terminal differs"
        ) from None
    if (
        terminal.private_dict() != dict(document)
        or terminal.causal_identity_sha256 != scenario.identity.identity_sha256
        or terminal.pair_claim_sha256 != pair.claim_sha256
        or terminal.decision_sha256 != decision.decision_sha256
        or (
            terminal.status is LivingDexPolicyDevelopmentTerminalStatus.COMPLETE
            and (
                result is None
                or terminal.result_sha256 != result.result_sha256
            )
        )
    ):
        raise LivingDexPolicyDevelopmentJournalError(
            "stored development terminal differs"
        )
    return terminal


def _find_result(
    store: PrivateArtifactRoot,
    scenario: LivingDexCausalScenario,
    pair: ClaimFirstRootPair,
    decision: LivingDexPolicyDevelopmentDecision,
) -> LivingDexPolicyDevelopmentResult | None:
    document = _find_exact_record(
        store,
        _record_id("result", scenario),
        kind="living_dex_policy_development_result",
    )
    if document is None:
        return None
    try:
        outcome_document = document.get("outcome")
        if not isinstance(outcome_document, Mapping):
            raise TypeError("outcome differs")
        result = LivingDexPolicyDevelopmentResult(
            _text(document, "causal_identity_sha256"),
            _text(document, "pair_claim_sha256"),
            _text(document, "decision_sha256"),
            _integer(document, "selected_candidate_index"),
            _text(document, "selected_binding_sha256"),
            restore_living_dex_observed_outcome(outcome_document),
            _integer(document, "controller_action_delta"),
            _integer(document, "emulator_frame_delta"),
            _text(document, "execution_status"),
            _optional_text(document, "execution_exception_type"),
            _mapping(document, "action_trace"),
            _mapping(document, "provenance"),
        )
    except (LivingDexCausalJournalError, TypeError, ValueError):
        raise LivingDexPolicyDevelopmentJournalError(
            "stored development result differs"
        ) from None
    if (
        result.private_dict() != dict(document)
        or result.causal_identity_sha256 != scenario.identity.identity_sha256
        or result.pair_claim_sha256 != pair.claim_sha256
        or result.decision_sha256 != decision.decision_sha256
        or result.selected_candidate_index != decision.selected_candidate_index
        or result.selected_binding_sha256
        != scenario.binding_sha256s[decision.selected_candidate_index]
    ):
        raise LivingDexPolicyDevelopmentJournalError(
            "stored development result differs"
        )
    return result


def _receipt_from_terminal(
    decision: LivingDexPolicyDevelopmentDecision,
    terminal: LivingDexPolicyDevelopmentTerminal,
    result: LivingDexPolicyDevelopmentResult | None,
) -> LivingDexPolicyDevelopmentReceipt:
    if terminal.status is LivingDexPolicyDevelopmentTerminalStatus.COMPLETE:
        disposition = LivingDexPolicyDevelopmentDisposition.RECOVERED_COMPLETE
    elif terminal.status is LivingDexPolicyDevelopmentTerminalStatus.PREINPUT_FAILED:
        disposition = (
            LivingDexPolicyDevelopmentDisposition.RECOVERED_PREINPUT_FAILED
        )
    else:
        disposition = LivingDexPolicyDevelopmentDisposition.RECOVERED_INTERRUPTED
    return LivingDexPolicyDevelopmentReceipt(decision, disposition, terminal, result)


def _validate_release(
    document: Mapping[str, object],
    scenario: LivingDexCausalScenario,
    pair: ClaimFirstRootPair,
    decision: LivingDexPolicyDevelopmentDecision,
) -> None:
    checkpoint = document.get("effect_checkpoint")
    if (
        set(document)
        != {
            "causal_identity_sha256",
            "decision_sha256",
            "effect_checkpoint",
            "pair_claim_sha256",
            "schema",
            "selected_binding_sha256",
            "selected_candidate_index",
        }
        or document.get("schema")
        != "pokemon.core.private-living-dex-policy-development-release.v1"
        or not isinstance(checkpoint, Mapping)
        or set(checkpoint) != {"controller_actions", "emulator_frames"}
        or type(checkpoint.get("controller_actions")) is not int  # noqa: E721
        or checkpoint.get("controller_actions", -1) < 0  # type: ignore[operator]
        or type(checkpoint.get("emulator_frames")) is not int  # noqa: E721
        or checkpoint.get("emulator_frames", -1) < 0  # type: ignore[operator]
        or document.get("causal_identity_sha256")
        != scenario.identity.identity_sha256
        or document.get("decision_sha256") != decision.decision_sha256
        or document.get("pair_claim_sha256") != pair.claim_sha256
        or document.get("selected_candidate_index")
        != decision.selected_candidate_index
        or document.get("selected_binding_sha256")
        != scenario.binding_sha256s[decision.selected_candidate_index]
    ):
        raise LivingDexPolicyDevelopmentJournalError(
            "stored development release differs"
        )


def _publish_exact(
    store: PrivateArtifactRoot,
    record_id: str,
    *,
    kind: str,
    record: Mapping[str, object],
) -> None:
    sealed = store.publish_sealed_record(record_id, kind=kind, record=record)
    if sealed.read() != dict(record):
        raise LivingDexPolicyDevelopmentJournalError(
            "development sealed record differs"
        )


def _find_exact_record(
    store: PrivateArtifactRoot,
    record_id: str,
    *,
    kind: str,
) -> dict[str, object] | None:
    sealed = store.find_sealed_record(record_id, expected_kind=kind)
    return None if sealed is None else sealed.read()


def _record_id(stage: str, scenario: LivingDexCausalScenario) -> str:
    return f"lpd-{stage}-{scenario.identity.identity_sha256}"


def _trip(failpoint: Callable[[str], None] | None, stage: str) -> None:
    if failpoint is not None:
        failpoint(stage)


def _require_sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise LivingDexPolicyDevelopmentJournalError(
            f"development {subject} differs"
        )
    return value


def _text(document: Mapping[str, object], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise LivingDexPolicyDevelopmentJournalError(
            f"development {key} differs"
        )
    return value


def _optional_text(document: Mapping[str, object], key: str) -> str | None:
    value = document.get(key)
    if value is None:
        return None
    return _text(document, key)


def _integer(document: Mapping[str, object], key: str) -> int:
    value = document.get(key)
    if type(value) is not int or value < 0:  # noqa: E721
        raise LivingDexPolicyDevelopmentJournalError(
            f"development {key} differs"
        )
    return value


def _mapping(document: Mapping[str, object], key: str) -> dict[str, object]:
    value = document.get(key)
    if not isinstance(value, Mapping):
        raise LivingDexPolicyDevelopmentJournalError(
            f"development {key} differs"
        )
    return dict(value)


__all__ = [
    "LIVING_DEX_POLICY_DEVELOPMENT_COLLECTION_ID",
    "LIVING_DEX_POLICY_DEVELOPMENT_RECEIPT_SCHEMA",
    "LivingDexPolicyDevelopmentDisposition",
    "LivingDexPolicyDevelopmentJournalError",
    "LivingDexPolicyDevelopmentReceipt",
    "LivingDexPolicyDevelopmentResult",
    "LivingDexPolicyDevelopmentTerminal",
    "LivingDexPolicyDevelopmentTerminalStatus",
    "execute_living_dex_policy_development",
]
