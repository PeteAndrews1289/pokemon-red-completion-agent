"""One-slot claim-first execution for the frozen Red living-dex curriculum.

This is the controller-capable successor to the read-only setup bridge.  It
authenticates one selected slot before any claim, atomically owns its logical
and physical roots, durably writes the local episode claim while the account
lease is still held, then releases the lease before asking a cold resolver to
construct a runtime.  Recovery never calls the resolver or a runtime factory.

The module performs setup validation only.  It never executes a provider,
chooses an option, records a learner outcome, fits a model, or opens a sealed
benchmark.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager, ExitStack
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable

from pokemon_red_completion.claim_first_admission import (
    ClaimFirstAdmissionError,
    ClaimFirstExecutionIdentity,
    ClaimFirstRootPair,
    claim_first_pair_registry,
    read_root_pair_claim,
    root_pair_claims,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    FreshCompositionQualificationError,
    open_fixed_account_claim_registry,
)
from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexCaptureSetupStatus,
)
from pokemon_red_completion.private_artifacts import (
    EpisodeArtifactState,
    EpisodeWriter,
    PrivateArtifactError,
    PrivateArtifactRoot,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_setup_admission import (
    FrozenRedLivingDexSetupSlot,
    RedLivingDexSetupAdmissionError,
    authenticate_frozen_red_living_dex_clustered_train_slot,
    authenticate_frozen_red_living_dex_setup_slot,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexAuthenticatedSetupRoot,
    RedLivingDexSetupEffectMeter,
    RedLivingDexSetupForkRuntimeFactory,
    RedLivingDexSetupRecipeError,
    RedLivingDexSetupSlotRecipe,
    RedLivingDexValidatedSetupCapture,
    restore_red_living_dex_validated_setup_capture,
    validate_red_living_dex_setup_recipe,
)
from pokemon_red_completion.red_living_dex_setup_trust import (
    RedLivingDexSetupExecutionIdentity,
    RedLivingDexSetupFailureReason,
    RedLivingDexSetupProtectedEffectCheckpoint,
)

RED_LIVING_DEX_CLAIM_FIRST_COLLECTION_ID = "red-living-dex-claim-first-setup-v1"
RED_LIVING_DEX_CLAIM_FIRST_CLAIM_SCHEMA = (
    "pokemon.red.private-living-dex-claim-first-setup-claim.v1"
)
RED_LIVING_DEX_CLAIM_FIRST_TERMINAL_SCHEMA = (
    "pokemon.red.private-living-dex-claim-first-setup-terminal.v1"
)
RED_LIVING_DEX_CLAIM_FIRST_TERMINAL_KIND = (
    "red_living_dex_claim_first_setup_terminal"
)

RED_LIVING_DEX_CLAIM_FIRST_RUNNER_SHA256 = canonical_sha256(
    {
        "atomic_logical_physical_claim": True,
        "deep_plan_reauthentication_after_local_claim": True,
        "no_retry_after_pair_claim": True,
        "postclaim_runtime_construction": True,
        "recovery_runtime_invocations": 0,
        "schema": "pokemon.red.living-dex-claim-first-runner-contract.v1",
    }
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class RedLivingDexClaimFirstCampaignError(RuntimeError):
    """One frozen slot cannot be safely executed or recovered."""


class RedLivingDexClaimFirstDisposition(StrEnum):
    EXECUTED_COMPLETE = "executed_complete"
    EXECUTED_FAILED = "executed_failed"
    RECOVERED_COMPLETE = "recovered_complete"
    RECOVERED_FAILED = "recovered_failed"
    RECOVERED_INTERRUPTED = "recovered_interrupted"


@dataclass(frozen=True, slots=True)
class RedLivingDexResolvedSetupSlot:
    """Controller-capable objects created only inside a postclaim scope."""

    recipe: RedLivingDexSetupSlotRecipe
    producer_execution_identity: RedLivingDexSetupExecutionIdentity
    arm_factory: RedLivingDexSetupForkRuntimeFactory
    title_adapter_sha256: str
    runtime_factory_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.recipe, RedLivingDexSetupSlotRecipe):
            raise TypeError("resolved setup slot needs a Red recipe")
        self.recipe.__post_init__()
        if not isinstance(
            self.producer_execution_identity,
            RedLivingDexSetupExecutionIdentity,
        ):
            raise TypeError("resolved setup slot needs its producer identity")
        self.producer_execution_identity.__post_init__()
        if not callable(self.arm_factory):
            raise TypeError("resolved setup slot needs an isolated-arm factory")
        _require_sha256(self.title_adapter_sha256, "resolved title adapter")
        _require_sha256(self.runtime_factory_sha256, "resolved runtime factory")


@runtime_checkable
class RedLivingDexClaimedSetupResolver(Protocol):
    """Cold adapter whose call is forbidden until both claims are durable."""

    def __call__(
        self,
        frozen: FrozenRedLivingDexSetupSlot,
        root: RedLivingDexAuthenticatedSetupRoot,
        pair_claim: ClaimFirstRootPair,
        *,
        meter: RedLivingDexSetupEffectMeter,
    ) -> AbstractContextManager[RedLivingDexResolvedSetupSlot]: ...


RedLivingDexFrozenPlanLoader = Callable[[], Mapping[str, object]]
RedLivingDexClaimFirstFailpoint = Callable[[str, FrozenRedLivingDexSetupSlot], None]


@dataclass(frozen=True, slots=True)
class RedLivingDexClaimFirstTerminal:
    producer_plan_sha256: str
    recipe_sha256: str
    slot_sha256: str
    outer_execution_identity_sha256: str
    producer_execution_identity_sha256: str
    pair_claim_sha256: str
    local_claim_sha256: str
    status: LivingDexCaptureSetupStatus
    reason_code: RedLivingDexSetupFailureReason | None
    setup_controller_actions: int | None
    setup_emulator_frames: int | None
    attestation_sha256: str | None
    retry_allowed: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        for value, subject in (
            (self.producer_plan_sha256, "terminal producer plan"),
            (self.recipe_sha256, "terminal recipe"),
            (self.slot_sha256, "terminal slot"),
            (self.outer_execution_identity_sha256, "terminal outer execution"),
            (self.producer_execution_identity_sha256, "terminal producer execution"),
            (self.pair_claim_sha256, "terminal pair claim"),
            (self.local_claim_sha256, "terminal local claim"),
        ):
            _require_sha256(value, subject)
        if not isinstance(self.status, LivingDexCaptureSetupStatus):
            raise RedLivingDexClaimFirstCampaignError("claim-first terminal status differs")
        known = self.setup_controller_actions is not None
        if known != (self.setup_emulator_frames is not None):
            raise RedLivingDexClaimFirstCampaignError(
                "claim-first terminal accounting is partially known"
            )
        if known:
            assert self.setup_controller_actions is not None
            assert self.setup_emulator_frames is not None
            if (
                type(self.setup_controller_actions) is not int  # noqa: E721
                or self.setup_controller_actions < 0
                or type(self.setup_emulator_frames) is not int  # noqa: E721
                or self.setup_emulator_frames < 0
            ):
                raise RedLivingDexClaimFirstCampaignError(
                    "claim-first terminal accounting differs"
                )
        if self.status is LivingDexCaptureSetupStatus.COMPLETE:
            if not known or self.reason_code is not None or self.attestation_sha256 is None:
                raise RedLivingDexClaimFirstCampaignError(
                    "complete claim-first terminal evidence differs"
                )
            _require_sha256(self.attestation_sha256, "terminal attestation")
        elif (
            not isinstance(self.reason_code, RedLivingDexSetupFailureReason)
            or self.attestation_sha256 is not None
        ):
            raise RedLivingDexClaimFirstCampaignError(
                "noncomplete claim-first terminal evidence differs"
            )
        if self.retry_allowed:
            raise RedLivingDexClaimFirstCampaignError("claimed setup slot cannot retry")

    @property
    def accounting_known(self) -> bool:
        return self.setup_controller_actions is not None

    def private_dict(self) -> dict[str, object]:
        return {
            "attestation_sha256": self.attestation_sha256,
            "local_claim_sha256": self.local_claim_sha256,
            "outer_execution_identity_sha256": self.outer_execution_identity_sha256,
            "pair_claim_sha256": self.pair_claim_sha256,
            "producer_execution_identity_sha256": (
                self.producer_execution_identity_sha256
            ),
            "producer_plan_sha256": self.producer_plan_sha256,
            "reason_code": None if self.reason_code is None else self.reason_code.value,
            "recipe_sha256": self.recipe_sha256,
            "retry_allowed": self.retry_allowed,
            "schema": RED_LIVING_DEX_CLAIM_FIRST_TERMINAL_SCHEMA,
            "setup_controller_actions": self.setup_controller_actions,
            "setup_emulator_frames": self.setup_emulator_frames,
            "slot_sha256": self.slot_sha256,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexClaimFirstReceipt:
    frozen: FrozenRedLivingDexSetupSlot
    terminal: RedLivingDexClaimFirstTerminal
    artifact_state: EpisodeArtifactState
    disposition: RedLivingDexClaimFirstDisposition
    capture: RedLivingDexValidatedSetupCapture | None

    def __post_init__(self) -> None:
        if not isinstance(self.frozen, FrozenRedLivingDexSetupSlot):
            raise TypeError("claim-first receipt needs its frozen slot")
        if not isinstance(self.terminal, RedLivingDexClaimFirstTerminal):
            raise TypeError("claim-first receipt needs its terminal")
        if not isinstance(self.artifact_state, EpisodeArtifactState):
            raise TypeError("claim-first receipt needs its artifact state")
        if not isinstance(self.disposition, RedLivingDexClaimFirstDisposition):
            raise TypeError("claim-first receipt disposition differs")
        if (
            self.terminal.producer_plan_sha256 != self.frozen.producer_plan_sha256
            or self.terminal.recipe_sha256 != self.frozen.recipe_sha256
            or self.terminal.slot_sha256 != self.frozen.slot_sha256
        ):
            raise RedLivingDexClaimFirstCampaignError(
                "claim-first receipt is joined to another frozen slot"
            )
        if self.terminal.status is LivingDexCaptureSetupStatus.COMPLETE:
            if self.capture is None or self.artifact_state.status != "complete":
                raise RedLivingDexClaimFirstCampaignError(
                    "complete claim-first receipt lacks its capture"
                )
            if (
                self.capture.recipe_sha256 != self.frozen.recipe_sha256
                or self.capture.attestation.attestation_sha256
                != self.terminal.attestation_sha256
            ):
                raise RedLivingDexClaimFirstCampaignError(
                    "claim-first receipt capture differs from its terminal"
                )
        elif self.capture is not None:
            raise RedLivingDexClaimFirstCampaignError(
                "noncomplete claim-first receipt cannot expose a capture"
            )

    @property
    def newly_executed(self) -> bool:
        return self.disposition in {
            RedLivingDexClaimFirstDisposition.EXECUTED_COMPLETE,
            RedLivingDexClaimFirstDisposition.EXECUTED_FAILED,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            "accounting_known": self.terminal.accounting_known,
            "behavior_draws": 0,
            "learner_labels": 0,
            "learner_outcomes": 0,
            "model_fits": 0,
            "model_predictions": 0,
            "new_runtime_invocation": self.newly_executed,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "provider_executions": 0,
            "retry_allowed": False,
            "status": self.terminal.status.value,
            "teacher_queries": 0,
        }


def run_red_living_dex_claim_first_setup_slot(
    store: PrivateArtifactRoot,
    *,
    plan_loader: RedLivingDexFrozenPlanLoader,
    expected_producer_plan_sha256: str,
    ordinal: int,
    root: RedLivingDexAuthenticatedSetupRoot,
    outer_execution_identity: ClaimFirstExecutionIdentity,
    resolver: RedLivingDexClaimedSetupResolver,
    meter: RedLivingDexSetupEffectMeter,
    claim_registry: Path,
    producer_execution_identity: RedLivingDexSetupExecutionIdentity | None = None,
    failpoint: RedLivingDexClaimFirstFailpoint | None = None,
) -> RedLivingDexClaimFirstReceipt:
    """Execute or recover exactly one frozen slot without sibling preflight."""

    if not isinstance(store, PrivateArtifactRoot):
        raise TypeError("claim-first setup needs a validated private root")
    if not callable(plan_loader):
        raise TypeError("claim-first setup needs a frozen-plan loader")
    if not isinstance(root, RedLivingDexAuthenticatedSetupRoot):
        raise TypeError("claim-first setup needs an authenticated root")
    root.__post_init__()
    if not isinstance(outer_execution_identity, ClaimFirstExecutionIdentity):
        raise TypeError("claim-first setup needs an outer execution identity")
    outer_execution_identity.__post_init__()
    if not isinstance(resolver, RedLivingDexClaimedSetupResolver):
        raise TypeError("claim-first setup needs a cold claimed-root resolver")
    if type(meter) is not RedLivingDexSetupEffectMeter:
        raise TypeError("claim-first setup needs the concrete protected-effect meter")
    if not isinstance(claim_registry, Path):
        raise TypeError("claim-first setup needs an account claim registry")
    if failpoint is not None and not callable(failpoint):
        raise TypeError("claim-first setup failpoint must be callable")
    try:
        registry = open_fixed_account_claim_registry(claim_registry)
    except FreshCompositionQualificationError as error:
        raise RedLivingDexClaimFirstCampaignError(str(error)) from None

    plan_document = plan_loader()
    if producer_execution_identity is None:
        frozen = authenticate_frozen_red_living_dex_setup_slot(
            plan_document,
            expected_plan_sha256=expected_producer_plan_sha256,
            ordinal=ordinal,
            root=root,
        )
    else:
        producer_execution_identity.__post_init__()
        runtime_identity_sha256 = plan_document.get("runtime_identity_sha256")
        frozen = authenticate_frozen_red_living_dex_clustered_train_slot(
            plan_document,
            expected_private_plan_sha256=expected_producer_plan_sha256,
            ordinal=ordinal,
            root=root,
            producer_execution_identity=producer_execution_identity,
            expected_runtime_identity_sha256=(
                runtime_identity_sha256
                if isinstance(runtime_identity_sha256, str)
                else None
            ),
        )
    _require_outer_identity(frozen, outer_execution_identity)
    pair = outer_execution_identity.root_pair(stage="setup-capture")
    local_claim = _local_claim_record(frozen, pair, outer_execution_identity)
    local_claim_sha256 = canonical_sha256(local_claim)
    episode_id = _episode_id(pair)

    try:
        with store.collection_session(RED_LIVING_DEX_CLAIM_FIRST_COLLECTION_ID) as session:
            state = session.inspect_episode(episode_id)
            terminal = _find_terminal(
                store,
                frozen,
                pair,
                local_claim_sha256,
            )
            if terminal is not None:
                _require_exact_pair_claim(registry, pair)
                if state.status == "partial":
                    state = session.recover_interrupted_episode(episode_id)
                return _receipt_from_terminal(
                    store,
                    frozen,
                    episode_id,
                    state,
                    terminal,
                    recovered=True,
                )
            if state.status == "partial":
                _require_exact_pair_claim(registry, pair)
                state = session.recover_interrupted_episode(episode_id)
            if state.status == "complete":
                _require_exact_pair_claim(registry, pair)
                capture = _load_capture(
                    store,
                    frozen,
                    episode_id,
                    local_claim,
                    outer_execution_identity,
                )
                terminal = _complete_terminal(
                    frozen,
                    pair,
                    local_claim_sha256,
                    capture,
                )
                _publish_terminal(store, pair, terminal)
                return RedLivingDexClaimFirstReceipt(
                    frozen,
                    terminal,
                    state,
                    RedLivingDexClaimFirstDisposition.RECOVERED_COMPLETE,
                    capture,
                )
            if state.status in {"failed", "interrupted"}:
                _require_exact_pair_claim(registry, pair)
                return _publish_recovered_interruption(
                    store,
                    frozen,
                    pair,
                    local_claim_sha256,
                    state,
                )
            if state.status == "invalid":
                raise RedLivingDexClaimFirstCampaignError(
                    "claim-first setup episode cannot be authenticated"
                )
            if state.status != "absent":
                raise RedLivingDexClaimFirstCampaignError(
                    "claim-first setup episode has an unsupported state"
                )

            return _claim_and_execute(
                store,
                frozen,
                pair,
                local_claim,
                local_claim_sha256,
                root=root,
                outer_execution_identity=outer_execution_identity,
                plan_loader=plan_loader,
                resolver=resolver,
                meter=meter,
                claim_registry=registry,
                failpoint=failpoint,
            )
    except RedLivingDexClaimFirstCampaignError:
        raise
    except (
        ClaimFirstAdmissionError,
        PrivateArtifactError,
        RedLivingDexSetupAdmissionError,
        RedLivingDexSetupRecipeError,
    ) as error:
        raise RedLivingDexClaimFirstCampaignError(str(error)) from None
    raise AssertionError("claim-first collection session suppressed execution")


def _claim_and_execute(
    store: PrivateArtifactRoot,
    frozen: FrozenRedLivingDexSetupSlot,
    pair: ClaimFirstRootPair,
    local_claim: Mapping[str, object],
    local_claim_sha256: str,
    *,
    root: RedLivingDexAuthenticatedSetupRoot,
    outer_execution_identity: ClaimFirstExecutionIdentity,
    plan_loader: RedLivingDexFrozenPlanLoader,
    resolver: RedLivingDexClaimedSetupResolver,
    meter: RedLivingDexSetupEffectMeter,
    claim_registry: Path,
    failpoint: RedLivingDexClaimFirstFailpoint | None,
) -> RedLivingDexClaimFirstReceipt:
    """Keep the episode writer alive while releasing the account lease."""

    episode_id = _episode_id(pair)
    with ExitStack() as attempt:
        with claim_first_pair_registry(claim_registry) as transaction:
            if not transaction.available(
                pair.logical_root_sha256,
                pair.physical_root_sha256,
            ):
                _require_exact_pair_claim(claim_registry, pair)
                return _record_prelocal_interruption(
                    store,
                    frozen,
                    pair,
                    local_claim,
                    local_claim_sha256,
                )
            before_claim = meter.checkpoint()
            retained = transaction.claim(pair)
            meter.record_root_claim()
            _require_only_root_claim_changed(before_claim, meter.checkpoint())
            _trip_failpoint(failpoint, "after_pair_claim", frozen)
            writer = attempt.enter_context(store.begin_episode(episode_id))
            _trip_failpoint(failpoint, "after_local_episode_open", frozen)
            writer.append("claim", local_claim, durable=True)
            _trip_failpoint(failpoint, "after_local_claim", frozen)
            if retained != pair:
                raise RedLivingDexClaimFirstCampaignError(
                    "claim-first retained another root pair"
                )

        before_setup = meter.checkpoint()
        try:
            frozen.reauthenticate(plan_loader(), root=root)
            if meter.checkpoint() != before_setup:
                raise RedLivingDexClaimFirstCampaignError(
                    "postclaim plan reauthentication changed protected effects"
                )
            _trip_failpoint(failpoint, "after_plan_reauthentication", frozen)
            scope = resolver(frozen, root, pair, meter=meter)
            if meter.checkpoint() != before_setup:
                raise RedLivingDexClaimFirstCampaignError(
                    "cold resolver construction changed protected effects"
                )
            with scope as resolved:
                _require_resolved_slot(
                    frozen,
                    resolved,
                    outer_execution_identity,
                )
                _trip_failpoint(failpoint, "after_runtime_scope_open", frozen)
                slot = _prospective_slot(frozen.template_ordinal)
                capture = validate_red_living_dex_setup_recipe(
                    slot,
                    resolved.recipe,
                    execution_identity=resolved.producer_execution_identity,
                    root=root,
                    arm_factory=resolved.arm_factory,
                    meter=meter,
                )
            actions, frames = before_setup.action_frame_delta(meter.checkpoint())
            if (
                actions != capture.attestation.setup_controller_actions
                or frames != capture.attestation.setup_emulator_frames
            ):
                raise RedLivingDexClaimFirstCampaignError(
                    "claim-first campaign and validator accounting differ"
                )
            writer.append("capture", capture.private_dict(), durable=True)
            _trip_failpoint(failpoint, "after_capture_append", frozen)
            summary = writer.complete()
            terminal = _complete_terminal(
                frozen,
                pair,
                local_claim_sha256,
                capture,
            )
            _publish_terminal(store, pair, terminal)
            return RedLivingDexClaimFirstReceipt(
                frozen,
                terminal,
                EpisodeArtifactState(
                    episode_id,
                    "complete",
                    manifest_sha256=summary.manifest_sha256,
                ),
                RedLivingDexClaimFirstDisposition.EXECUTED_COMPLETE,
                capture,
            )
        except BaseException as error:
            interrupted = not isinstance(error, Exception)
            receipt = _settle_failed_attempt(
                store,
                writer,
                frozen,
                pair,
                local_claim_sha256,
                before_setup=before_setup,
                meter=meter,
                interrupted=interrupted,
            )
            if interrupted:
                raise
            return receipt


def _settle_failed_attempt(
    store: PrivateArtifactRoot,
    writer: EpisodeWriter,
    frozen: FrozenRedLivingDexSetupSlot,
    pair: ClaimFirstRootPair,
    local_claim_sha256: str,
    *,
    before_setup: RedLivingDexSetupProtectedEffectCheckpoint,
    meter: RedLivingDexSetupEffectMeter,
    interrupted: bool,
) -> RedLivingDexClaimFirstReceipt:
    actions, frames = before_setup.action_frame_delta(meter.checkpoint())
    reason = (
        RedLivingDexSetupFailureReason.PROCESS_INTERRUPTED
        if interrupted
        else RedLivingDexSetupFailureReason.RECIPE_EXECUTION_FAILED
    )
    status = (
        LivingDexCaptureSetupStatus.INTERRUPTED
        if interrupted
        else LivingDexCaptureSetupStatus.FAILED
    )
    terminal = _terminal(
        frozen,
        pair,
        local_claim_sha256,
        status=status,
        reason_code=reason,
        setup_controller_actions=actions,
        setup_emulator_frames=frames,
        attestation_sha256=None,
    )
    writer.append("failure", terminal.private_dict(), durable=True)
    _publish_terminal(store, pair, terminal)
    summary = writer.abort(reason.value)
    return RedLivingDexClaimFirstReceipt(
        frozen,
        terminal,
        EpisodeArtifactState(
            _episode_id(pair),
            "failed",
            reason_code=reason.value,
            manifest_sha256=summary.manifest_sha256,
        ),
        (
            RedLivingDexClaimFirstDisposition.RECOVERED_INTERRUPTED
            if interrupted
            else RedLivingDexClaimFirstDisposition.EXECUTED_FAILED
        ),
        None,
    )


def _record_prelocal_interruption(
    store: PrivateArtifactRoot,
    frozen: FrozenRedLivingDexSetupSlot,
    pair: ClaimFirstRootPair,
    local_claim: Mapping[str, object],
    local_claim_sha256: str,
) -> RedLivingDexClaimFirstReceipt:
    terminal = _terminal(
        frozen,
        pair,
        local_claim_sha256,
        status=LivingDexCaptureSetupStatus.INTERRUPTED,
        reason_code=RedLivingDexSetupFailureReason.PROCESS_INTERRUPTED,
        setup_controller_actions=0,
        setup_emulator_frames=0,
        attestation_sha256=None,
    )
    with store.begin_episode(_episode_id(pair)) as writer:
        writer.append("claim", local_claim, durable=True)
        writer.append("failure", terminal.private_dict(), durable=True)
        summary = writer.abort(RedLivingDexSetupFailureReason.PROCESS_INTERRUPTED.value)
    _publish_terminal(store, pair, terminal)
    return RedLivingDexClaimFirstReceipt(
        frozen,
        terminal,
        EpisodeArtifactState(
            _episode_id(pair),
            "failed",
            reason_code=RedLivingDexSetupFailureReason.PROCESS_INTERRUPTED.value,
            manifest_sha256=summary.manifest_sha256,
        ),
        RedLivingDexClaimFirstDisposition.RECOVERED_INTERRUPTED,
        None,
    )


def _publish_recovered_interruption(
    store: PrivateArtifactRoot,
    frozen: FrozenRedLivingDexSetupSlot,
    pair: ClaimFirstRootPair,
    local_claim_sha256: str,
    state: EpisodeArtifactState,
) -> RedLivingDexClaimFirstReceipt:
    terminal = _terminal(
        frozen,
        pair,
        local_claim_sha256,
        status=LivingDexCaptureSetupStatus.INTERRUPTED,
        reason_code=RedLivingDexSetupFailureReason.PROCESS_INTERRUPTED,
        setup_controller_actions=None,
        setup_emulator_frames=None,
        attestation_sha256=None,
    )
    _publish_terminal(store, pair, terminal)
    return RedLivingDexClaimFirstReceipt(
        frozen,
        terminal,
        state,
        RedLivingDexClaimFirstDisposition.RECOVERED_INTERRUPTED,
        None,
    )


def _require_outer_identity(
    frozen: FrozenRedLivingDexSetupSlot,
    identity: ClaimFirstExecutionIdentity,
) -> None:
    if (
        identity.producer_plan_sha256 != frozen.producer_plan_sha256
        or identity.producer_execution_identity_sha256
        != frozen.producer_execution_identity_sha256
        or identity.slot_sha256 != frozen.slot_sha256
        or identity.recipe_sha256 != frozen.recipe_sha256
        or identity.logical_root_sha256 != frozen.logical_root_sha256
        or identity.physical_root_sha256 != frozen.physical_root_sha256
        or identity.runner_sha256 != RED_LIVING_DEX_CLAIM_FIRST_RUNNER_SHA256
    ):
        raise RedLivingDexClaimFirstCampaignError(
            "outer execution identity differs from the frozen Red slot"
        )


def _require_resolved_slot(
    frozen: FrozenRedLivingDexSetupSlot,
    resolved: RedLivingDexResolvedSetupSlot,
    identity: ClaimFirstExecutionIdentity,
) -> None:
    if not isinstance(resolved, RedLivingDexResolvedSetupSlot):
        raise TypeError("claimed resolver returned an invalid setup scope")
    resolved.__post_init__()
    frozen.require_resolved_recipe(resolved.recipe)
    if (
        resolved.producer_execution_identity.identity_sha256
        != frozen.producer_execution_identity_sha256
        or resolved.title_adapter_sha256 != identity.title_adapter_sha256
        or resolved.runtime_factory_sha256 != identity.runtime_factory_sha256
    ):
        raise RedLivingDexClaimFirstCampaignError(
            "postclaim resolved setup identity differs"
        )


def _local_claim_record(
    frozen: FrozenRedLivingDexSetupSlot,
    pair: ClaimFirstRootPair,
    identity: ClaimFirstExecutionIdentity,
) -> dict[str, object]:
    return {
        "behavior_draws": 0,
        "claim_before_controller_input": True,
        "learner_effects": 0,
        "logical_root_sha256": frozen.logical_root_sha256,
        "outer_execution_identity_sha256": identity.identity_sha256,
        "pair_claim_sha256": pair.claim_sha256,
        "physical_root_sha256": frozen.physical_root_sha256,
        "producer_execution_identity_sha256": (
            frozen.producer_execution_identity_sha256
        ),
        "producer_plan_sha256": frozen.producer_plan_sha256,
        "recipe_sha256": frozen.recipe_sha256,
        "retry_after_pair_claim": False,
        "schema": RED_LIVING_DEX_CLAIM_FIRST_CLAIM_SCHEMA,
        "slot_sha256": frozen.slot_sha256,
    }


def _complete_terminal(
    frozen: FrozenRedLivingDexSetupSlot,
    pair: ClaimFirstRootPair,
    local_claim_sha256: str,
    capture: RedLivingDexValidatedSetupCapture,
) -> RedLivingDexClaimFirstTerminal:
    return _terminal(
        frozen,
        pair,
        local_claim_sha256,
        status=LivingDexCaptureSetupStatus.COMPLETE,
        reason_code=None,
        setup_controller_actions=capture.attestation.setup_controller_actions,
        setup_emulator_frames=capture.attestation.setup_emulator_frames,
        attestation_sha256=capture.attestation.attestation_sha256,
    )


def _terminal(
    frozen: FrozenRedLivingDexSetupSlot,
    pair: ClaimFirstRootPair,
    local_claim_sha256: str,
    *,
    status: LivingDexCaptureSetupStatus,
    reason_code: RedLivingDexSetupFailureReason | None,
    setup_controller_actions: int | None,
    setup_emulator_frames: int | None,
    attestation_sha256: str | None,
) -> RedLivingDexClaimFirstTerminal:
    return RedLivingDexClaimFirstTerminal(
        producer_plan_sha256=frozen.producer_plan_sha256,
        recipe_sha256=frozen.recipe_sha256,
        slot_sha256=frozen.slot_sha256,
        outer_execution_identity_sha256=pair.execution_identity_sha256,
        producer_execution_identity_sha256=(
            frozen.producer_execution_identity_sha256
        ),
        pair_claim_sha256=pair.claim_sha256,
        local_claim_sha256=local_claim_sha256,
        status=status,
        reason_code=reason_code,
        setup_controller_actions=setup_controller_actions,
        setup_emulator_frames=setup_emulator_frames,
        attestation_sha256=attestation_sha256,
    )


def _publish_terminal(
    store: PrivateArtifactRoot,
    pair: ClaimFirstRootPair,
    terminal: RedLivingDexClaimFirstTerminal,
) -> None:
    sealed = store.publish_sealed_record(
        _terminal_record_id(pair),
        kind=RED_LIVING_DEX_CLAIM_FIRST_TERMINAL_KIND,
        record=terminal.private_dict(),
    )
    if sealed.read() != terminal.private_dict():
        raise RedLivingDexClaimFirstCampaignError(
            "claim-first terminal publication differs"
        )


def _find_terminal(
    store: PrivateArtifactRoot,
    frozen: FrozenRedLivingDexSetupSlot,
    pair: ClaimFirstRootPair,
    local_claim_sha256: str,
) -> RedLivingDexClaimFirstTerminal | None:
    sealed = store.find_sealed_record(
        _terminal_record_id(pair),
        expected_kind=RED_LIVING_DEX_CLAIM_FIRST_TERMINAL_KIND,
    )
    if sealed is None:
        return None
    terminal = _restore_terminal(sealed.read())
    expected = _terminal(
        frozen,
        pair,
        local_claim_sha256,
        status=terminal.status,
        reason_code=terminal.reason_code,
        setup_controller_actions=terminal.setup_controller_actions,
        setup_emulator_frames=terminal.setup_emulator_frames,
        attestation_sha256=terminal.attestation_sha256,
    )
    if terminal != expected:
        raise RedLivingDexClaimFirstCampaignError(
            "stored claim-first terminal differs from the active slot"
        )
    return terminal


def _restore_terminal(document: Mapping[str, object]) -> RedLivingDexClaimFirstTerminal:
    expected = {
        "attestation_sha256",
        "local_claim_sha256",
        "outer_execution_identity_sha256",
        "pair_claim_sha256",
        "producer_execution_identity_sha256",
        "producer_plan_sha256",
        "reason_code",
        "recipe_sha256",
        "retry_allowed",
        "schema",
        "setup_controller_actions",
        "setup_emulator_frames",
        "slot_sha256",
        "status",
    }
    if (
        set(document) != expected
        or document.get("schema") != RED_LIVING_DEX_CLAIM_FIRST_TERMINAL_SCHEMA
        or document.get("retry_allowed") is not False
    ):
        raise RedLivingDexClaimFirstCampaignError(
            "stored claim-first terminal fields differ"
        )
    try:
        status = LivingDexCaptureSetupStatus(_string(document["status"], "status"))
        reason_raw = document["reason_code"]
        reason = (
            None
            if reason_raw is None
            else RedLivingDexSetupFailureReason(_string(reason_raw, "reason"))
        )
    except ValueError:
        raise RedLivingDexClaimFirstCampaignError(
            "stored claim-first terminal enum differs"
        ) from None
    return RedLivingDexClaimFirstTerminal(
        producer_plan_sha256=_string(document["producer_plan_sha256"], "plan"),
        recipe_sha256=_string(document["recipe_sha256"], "recipe"),
        slot_sha256=_string(document["slot_sha256"], "slot"),
        outer_execution_identity_sha256=_string(
            document["outer_execution_identity_sha256"],
            "outer execution",
        ),
        producer_execution_identity_sha256=_string(
            document["producer_execution_identity_sha256"],
            "producer execution",
        ),
        pair_claim_sha256=_string(document["pair_claim_sha256"], "pair claim"),
        local_claim_sha256=_string(document["local_claim_sha256"], "local claim"),
        status=status,
        reason_code=reason,
        setup_controller_actions=_optional_int(
            document["setup_controller_actions"],
            "actions",
        ),
        setup_emulator_frames=_optional_int(
            document["setup_emulator_frames"],
            "frames",
        ),
        attestation_sha256=_optional_string(
            document["attestation_sha256"],
            "attestation",
        ),
    )


def _receipt_from_terminal(
    store: PrivateArtifactRoot,
    frozen: FrozenRedLivingDexSetupSlot,
    episode_id: str,
    state: EpisodeArtifactState,
    terminal: RedLivingDexClaimFirstTerminal,
    *,
    recovered: bool,
) -> RedLivingDexClaimFirstReceipt:
    if terminal.status is LivingDexCaptureSetupStatus.COMPLETE:
        capture = _load_capture_by_terminal(store, frozen, episode_id, terminal)
        disposition = (
            RedLivingDexClaimFirstDisposition.RECOVERED_COMPLETE
            if recovered
            else RedLivingDexClaimFirstDisposition.EXECUTED_COMPLETE
        )
    else:
        capture = None
        disposition = (
            RedLivingDexClaimFirstDisposition.RECOVERED_INTERRUPTED
            if terminal.status is LivingDexCaptureSetupStatus.INTERRUPTED
            else RedLivingDexClaimFirstDisposition.RECOVERED_FAILED
        )
    return RedLivingDexClaimFirstReceipt(
        frozen,
        terminal,
        state,
        disposition,
        capture,
    )


def _load_capture(
    store: PrivateArtifactRoot,
    frozen: FrozenRedLivingDexSetupSlot,
    episode_id: str,
    local_claim: Mapping[str, object],
    identity: ClaimFirstExecutionIdentity,
) -> RedLivingDexValidatedSetupCapture:
    reader = store.open_episode(episode_id)
    claims = tuple(reader.iter_stream("claim", max_records=1))
    captures = tuple(reader.iter_stream("capture", max_records=1))
    if len(claims) != 1 or claims[0] != dict(local_claim) or len(captures) != 1:
        raise RedLivingDexClaimFirstCampaignError(
            "complete claim-first episode lacks its exact evidence"
        )
    capture = restore_red_living_dex_validated_setup_capture(captures[0])
    if (
        capture.recipe_sha256 != frozen.recipe_sha256
        or capture.execution_identity_sha256
        != identity.producer_execution_identity_sha256
    ):
        raise RedLivingDexClaimFirstCampaignError(
            "stored claim-first capture differs from its frozen slot"
        )
    return capture


def _load_capture_by_terminal(
    store: PrivateArtifactRoot,
    frozen: FrozenRedLivingDexSetupSlot,
    episode_id: str,
    terminal: RedLivingDexClaimFirstTerminal,
) -> RedLivingDexValidatedSetupCapture:
    reader = store.open_episode(episode_id)
    captures = tuple(reader.iter_stream("capture", max_records=1))
    if len(captures) != 1:
        raise RedLivingDexClaimFirstCampaignError(
            "complete claim-first episode lacks one capture"
        )
    capture = restore_red_living_dex_validated_setup_capture(captures[0])
    if (
        capture.recipe_sha256 != frozen.recipe_sha256
        or capture.execution_identity_sha256
        != terminal.producer_execution_identity_sha256
        or capture.attestation.attestation_sha256 != terminal.attestation_sha256
    ):
        raise RedLivingDexClaimFirstCampaignError(
            "stored claim-first capture differs from its terminal"
        )
    return capture


def _require_exact_pair_claim(registry: Path, expected: ClaimFirstRootPair) -> None:
    try:
        restored = read_root_pair_claim(registry, expected.claim_sha256)
    except ClaimFirstAdmissionError:
        overlaps = tuple(
            claim
            for claim in root_pair_claims(registry)
            if not expected.identities.isdisjoint(claim.identities)
        )
        if overlaps:
            raise RedLivingDexClaimFirstCampaignError(
                "frozen root pair belongs to another execution"
            ) from None
        raise RedLivingDexClaimFirstCampaignError(
            "claim-first local state lacks its account pair claim"
        ) from None
    if restored != expected:
        raise RedLivingDexClaimFirstCampaignError(
            "account pair claim belongs to another execution"
        )


def _require_only_root_claim_changed(
    before: RedLivingDexSetupProtectedEffectCheckpoint,
    after: RedLivingDexSetupProtectedEffectCheckpoint,
) -> None:
    expected = replace(before, root_claims=before.root_claims + 1)
    if after != expected:
        raise RedLivingDexClaimFirstCampaignError(
            "pair claim changed unrelated protected effects"
        )


def _prospective_slot(ordinal: int):  # type: ignore[no-untyped-def]
    from pokemon_red_completion.red_living_dex_capture_plan import (
        build_red_living_dex_prospective_capture_plan,
    )

    return build_red_living_dex_prospective_capture_plan().slots[ordinal]


def _episode_id(pair: ClaimFirstRootPair) -> str:
    return f"red-living-dex-claim-first-{pair.claim_sha256[:28]}"


def _terminal_record_id(pair: ClaimFirstRootPair) -> str:
    return f"red-living-dex-claim-first-terminal-{pair.claim_sha256[:24]}"


def _trip_failpoint(
    failpoint: RedLivingDexClaimFirstFailpoint | None,
    stage: str,
    frozen: FrozenRedLivingDexSetupSlot,
) -> None:
    if failpoint is not None:
        failpoint(stage, frozen)


def _require_sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedLivingDexClaimFirstCampaignError(f"{subject} digest differs")
    return value


def _string(value: object, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise RedLivingDexClaimFirstCampaignError(f"claim-first terminal {subject} differs")
    return value


def _optional_string(value: object, subject: str) -> str | None:
    if value is None:
        return None
    return _string(value, subject)


def _optional_int(value: object, subject: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:  # noqa: E721
        raise RedLivingDexClaimFirstCampaignError(
            f"claim-first terminal {subject} differs"
        )
    return value


__all__ = [
    "RED_LIVING_DEX_CLAIM_FIRST_RUNNER_SHA256",
    "RedLivingDexClaimFirstCampaignError",
    "RedLivingDexClaimFirstDisposition",
    "RedLivingDexClaimFirstReceipt",
    "RedLivingDexClaimFirstTerminal",
    "RedLivingDexClaimedSetupResolver",
    "RedLivingDexResolvedSetupSlot",
    "run_red_living_dex_claim_first_setup_slot",
]
