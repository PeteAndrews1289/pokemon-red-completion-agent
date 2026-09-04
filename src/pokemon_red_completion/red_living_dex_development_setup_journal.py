"""Claim-first one-shot setup journal for held Red development rows.

This module is deliberately separate from the historically qualified train
runner.  It claims both root identities before constructing a runtime, seals a
local claim before controller-capable setup validation, and never retries a
claimed root.  A complete setup capture may be recovered without reopening a
runtime; any claimed attempt without a durable capture becomes terminal.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager, suppress
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
    PrivateArtifactError,
    PrivateArtifactRoot,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_claim_first_campaign import (
    RedLivingDexResolvedSetupSlot,
)
from pokemon_red_completion.red_living_dex_development_setup_admission import (
    FrozenRedLivingDexDevelopmentSetupSlot,
    RedLivingDexDevelopmentSetupAdmissionError,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexAuthenticatedSetupRoot,
    RedLivingDexSetupEffectMeter,
    RedLivingDexSetupRecipeError,
    RedLivingDexValidatedSetupCapture,
    restore_red_living_dex_validated_setup_capture,
    validate_red_living_dex_setup_recipe,
)
from pokemon_red_completion.red_living_dex_setup_trust import (
    RedLivingDexSetupFailureReason,
    RedLivingDexSetupProtectedEffectCheckpoint,
)

RED_LIVING_DEX_DEVELOPMENT_SETUP_COLLECTION_ID = (
    "red-living-dex-development-setup-v1"
)
RED_LIVING_DEX_DEVELOPMENT_SETUP_CLAIM_SCHEMA = (
    "pokemon.red.private-living-dex-development-setup-claim.v1"
)
RED_LIVING_DEX_DEVELOPMENT_SETUP_RELEASE_SCHEMA = (
    "pokemon.red.private-living-dex-development-setup-release.v1"
)
RED_LIVING_DEX_DEVELOPMENT_SETUP_TERMINAL_SCHEMA = (
    "pokemon.red.private-living-dex-development-setup-terminal.v1"
)
RED_LIVING_DEX_DEVELOPMENT_SETUP_RUNNER_SHA256 = canonical_sha256(
    {
        "atomic_logical_physical_claim": True,
        "controller_capability_after_durable_claim": True,
        "development_only": True,
        "full_plan_reauthentication_after_claim": True,
        "no_retry_after_pair_claim": True,
        "recovery_runtime_invocations": 0,
        "schema": "pokemon.red.living-dex-development-setup-runner.v1",
        "training_targets": 0,
    }
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class RedLivingDexDevelopmentSetupJournalError(RuntimeError):
    """A development setup cannot execute or recover safely."""


class RedLivingDexDevelopmentSetupDisposition(StrEnum):
    EXECUTED_COMPLETE = "executed_complete"
    EXECUTED_FAILED = "executed_failed"
    RECOVERED_COMPLETE = "recovered_complete"
    RECOVERED_FAILED = "recovered_failed"
    RECOVERED_INTERRUPTED = "recovered_interrupted"


@runtime_checkable
class RedLivingDexDevelopmentSetupResolver(Protocol):
    """Cold Red adapter callable only after the root claim is durable."""

    def __call__(
        self,
        frozen: FrozenRedLivingDexDevelopmentSetupSlot,
        root: RedLivingDexAuthenticatedSetupRoot,
        pair_claim: ClaimFirstRootPair,
        *,
        meter: RedLivingDexSetupEffectMeter,
    ) -> AbstractContextManager[RedLivingDexResolvedSetupSlot]: ...


RedLivingDexDevelopmentPlanLoader = Callable[[], Mapping[str, object]]
RedLivingDexDevelopmentSetupFailpoint = Callable[
    [str, FrozenRedLivingDexDevelopmentSetupSlot],
    None,
]


@dataclass(frozen=True, slots=True)
class RedLivingDexDevelopmentSetupTerminal:
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
            (self.producer_plan_sha256, "producer plan"),
            (self.recipe_sha256, "recipe"),
            (self.slot_sha256, "slot"),
            (self.outer_execution_identity_sha256, "outer execution"),
            (
                self.producer_execution_identity_sha256,
                "producer execution",
            ),
            (self.pair_claim_sha256, "pair claim"),
            (self.local_claim_sha256, "local claim"),
        ):
            _require_sha256(value, subject)
        if not isinstance(self.status, LivingDexCaptureSetupStatus):
            raise RedLivingDexDevelopmentSetupJournalError(
                "development setup terminal status differs"
            )
        accounting_known = self.setup_controller_actions is not None
        if accounting_known != (self.setup_emulator_frames is not None):
            raise RedLivingDexDevelopmentSetupJournalError(
                "development setup accounting is partially known"
            )
        if accounting_known and (
            type(self.setup_controller_actions) is not int  # noqa: E721
            or self.setup_controller_actions < 0
            or type(self.setup_emulator_frames) is not int  # noqa: E721
            or self.setup_emulator_frames < 0
        ):
            raise RedLivingDexDevelopmentSetupJournalError(
                "development setup accounting differs"
            )
        if self.status is LivingDexCaptureSetupStatus.COMPLETE:
            if (
                not accounting_known
                or self.reason_code is not None
                or self.attestation_sha256 is None
            ):
                raise RedLivingDexDevelopmentSetupJournalError(
                    "complete development setup terminal differs"
                )
            _require_sha256(self.attestation_sha256, "attestation")
        elif (
            not isinstance(self.reason_code, RedLivingDexSetupFailureReason)
            or self.attestation_sha256 is not None
        ):
            raise RedLivingDexDevelopmentSetupJournalError(
                "noncomplete development setup terminal differs"
            )

    @property
    def accounting_known(self) -> bool:
        return self.setup_controller_actions is not None

    def private_dict(self) -> dict[str, object]:
        return {
            "attestation_sha256": self.attestation_sha256,
            "local_claim_sha256": self.local_claim_sha256,
            "outer_execution_identity_sha256": (
                self.outer_execution_identity_sha256
            ),
            "pair_claim_sha256": self.pair_claim_sha256,
            "producer_execution_identity_sha256": (
                self.producer_execution_identity_sha256
            ),
            "producer_plan_sha256": self.producer_plan_sha256,
            "reason_code": (
                None if self.reason_code is None else self.reason_code.value
            ),
            "recipe_sha256": self.recipe_sha256,
            "retry_allowed": self.retry_allowed,
            "schema": RED_LIVING_DEX_DEVELOPMENT_SETUP_TERMINAL_SCHEMA,
            "setup_controller_actions": self.setup_controller_actions,
            "setup_emulator_frames": self.setup_emulator_frames,
            "slot_sha256": self.slot_sha256,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexDevelopmentSetupReceipt:
    frozen: FrozenRedLivingDexDevelopmentSetupSlot
    terminal: RedLivingDexDevelopmentSetupTerminal
    disposition: RedLivingDexDevelopmentSetupDisposition
    capture: RedLivingDexValidatedSetupCapture | None

    def __post_init__(self) -> None:
        if not isinstance(
            self.frozen,
            FrozenRedLivingDexDevelopmentSetupSlot,
        ):
            raise TypeError("development setup receipt needs its frozen slot")
        if not isinstance(
            self.terminal,
            RedLivingDexDevelopmentSetupTerminal,
        ):
            raise TypeError("development setup receipt needs its terminal")
        self.terminal.__post_init__()
        if not isinstance(
            self.disposition,
            RedLivingDexDevelopmentSetupDisposition,
        ):
            raise TypeError("development setup disposition differs")
        selection = self.frozen.selection
        if (
            self.terminal.producer_plan_sha256
            != selection.private_plan_sha256
            or self.terminal.recipe_sha256 != selection.recipe_sha256
            or self.terminal.slot_sha256 != selection.slot_sha256
        ):
            raise RedLivingDexDevelopmentSetupJournalError(
                "development setup receipt joins another slot"
            )
        if self.terminal.status is LivingDexCaptureSetupStatus.COMPLETE:
            if (
                not isinstance(self.capture, RedLivingDexValidatedSetupCapture)
                or self.capture.recipe_sha256 != selection.recipe_sha256
                or self.capture.attestation.attestation_sha256
                != self.terminal.attestation_sha256
            ):
                raise RedLivingDexDevelopmentSetupJournalError(
                    "complete development setup lacks its capture"
                )
        elif self.capture is not None:
            raise RedLivingDexDevelopmentSetupJournalError(
                "noncomplete development setup retained a capture"
            )

    @property
    def newly_executed(self) -> bool:
        return self.disposition in {
            RedLivingDexDevelopmentSetupDisposition.EXECUTED_COMPLETE,
            RedLivingDexDevelopmentSetupDisposition.EXECUTED_FAILED,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            "accounting_known": self.terminal.accounting_known,
            "behavior_draws": 0,
            "development_outcomes_opened": 0,
            "model_fits": 0,
            "model_predictions": 0,
            "new_runtime_invocation": self.newly_executed,
            "partition": "development",
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "provider_executions": 0,
            "retry_allowed": False,
            "status": self.terminal.status.value,
            "teacher_queries": 0,
            "training_targets_emitted": 0,
        }


def run_red_living_dex_development_setup(
    frozen: FrozenRedLivingDexDevelopmentSetupSlot,
    *,
    store: PrivateArtifactRoot,
    plan_loader: RedLivingDexDevelopmentPlanLoader,
    root: RedLivingDexAuthenticatedSetupRoot,
    outer_execution_identity: ClaimFirstExecutionIdentity,
    resolver: RedLivingDexDevelopmentSetupResolver,
    meter: RedLivingDexSetupEffectMeter,
    claim_registry: Path,
    failpoint: RedLivingDexDevelopmentSetupFailpoint | None = None,
) -> RedLivingDexDevelopmentSetupReceipt:
    """Execute or recover one already-authenticated held Red setup."""

    if not isinstance(frozen, FrozenRedLivingDexDevelopmentSetupSlot):
        raise TypeError("development setup journal needs a frozen slot")
    frozen.__post_init__()
    if not isinstance(store, PrivateArtifactRoot):
        raise TypeError("development setup journal needs a private store")
    if not callable(plan_loader):
        raise TypeError("development setup journal needs a plan loader")
    if not isinstance(root, RedLivingDexAuthenticatedSetupRoot):
        raise TypeError("development setup journal needs an authenticated root")
    root.__post_init__()
    if not isinstance(outer_execution_identity, ClaimFirstExecutionIdentity):
        raise TypeError("development setup journal needs an outer identity")
    outer_execution_identity.__post_init__()
    if not isinstance(resolver, RedLivingDexDevelopmentSetupResolver):
        raise TypeError("development setup journal needs a cold resolver")
    if type(meter) is not RedLivingDexSetupEffectMeter:
        raise TypeError("development setup journal needs the protected meter")
    if not isinstance(claim_registry, Path):
        raise TypeError("development setup journal needs a claim registry Path")
    if failpoint is not None and not callable(failpoint):
        raise TypeError("development setup failpoint must be callable")
    try:
        registry = open_fixed_account_claim_registry(claim_registry)
    except FreshCompositionQualificationError as error:
        raise RedLivingDexDevelopmentSetupJournalError(str(error)) from None
    _require_outer_identity(frozen, outer_execution_identity)
    pair = outer_execution_identity.root_pair(stage="development-setup")
    local_claim = _local_claim(frozen, outer_execution_identity, pair)
    local_claim_sha256 = canonical_sha256(local_claim)

    try:
        with store.collection_session(
            RED_LIVING_DEX_DEVELOPMENT_SETUP_COLLECTION_ID
        ):
            terminal = _find_terminal(
                store,
                frozen,
                pair,
                local_claim_sha256,
            )
            capture = _find_capture(store, frozen, pair)
            if terminal is not None:
                _require_exact_pair_claim(registry, pair)
                return _receipt_from_terminal(terminal, capture, frozen)
            if capture is not None:
                _require_exact_pair_claim(registry, pair)
                terminal = _complete_terminal(
                    frozen,
                    pair,
                    local_claim_sha256,
                    capture,
                )
                _publish_terminal(store, pair, terminal)
                return RedLivingDexDevelopmentSetupReceipt(
                    frozen,
                    terminal,
                    RedLivingDexDevelopmentSetupDisposition.RECOVERED_COMPLETE,
                    capture,
                )
            claim = _find_record(store, _record_id("claim", pair), "claim")
            release = _find_record(store, _record_id("release", pair), "release")
            if claim is not None or release is not None:
                _validate_claim_and_release(
                    claim,
                    release,
                    local_claim,
                    pair,
                )
                _require_exact_pair_claim(registry, pair)
                terminal = _interrupted_terminal(
                    frozen,
                    pair,
                    local_claim_sha256,
                    accounting=None,
                )
                _publish_terminal(store, pair, terminal)
                return RedLivingDexDevelopmentSetupReceipt(
                    frozen,
                    terminal,
                    RedLivingDexDevelopmentSetupDisposition.RECOVERED_INTERRUPTED,
                    None,
                )
            existing = _read_exact_or_overlap(registry, pair)
            if existing is not None:
                terminal = _interrupted_terminal(
                    frozen,
                    pair,
                    local_claim_sha256,
                    accounting=None,
                )
                _publish_terminal(store, pair, terminal)
                return RedLivingDexDevelopmentSetupReceipt(
                    frozen,
                    terminal,
                    RedLivingDexDevelopmentSetupDisposition.RECOVERED_INTERRUPTED,
                    None,
                )
            return _claim_and_execute(
                frozen,
                store=store,
                plan_loader=plan_loader,
                root=root,
                outer_execution_identity=outer_execution_identity,
                resolver=resolver,
                meter=meter,
                claim_registry=registry,
                pair=pair,
                local_claim=local_claim,
                local_claim_sha256=local_claim_sha256,
                failpoint=failpoint,
            )
    except RedLivingDexDevelopmentSetupJournalError:
        raise
    except (
        ClaimFirstAdmissionError,
        PrivateArtifactError,
        RedLivingDexDevelopmentSetupAdmissionError,
        RedLivingDexSetupRecipeError,
    ) as error:
        raise RedLivingDexDevelopmentSetupJournalError(str(error)) from None
    raise AssertionError("development setup collection suppressed execution")


def _claim_and_execute(
    frozen: FrozenRedLivingDexDevelopmentSetupSlot,
    *,
    store: PrivateArtifactRoot,
    plan_loader: RedLivingDexDevelopmentPlanLoader,
    root: RedLivingDexAuthenticatedSetupRoot,
    outer_execution_identity: ClaimFirstExecutionIdentity,
    resolver: RedLivingDexDevelopmentSetupResolver,
    meter: RedLivingDexSetupEffectMeter,
    claim_registry: Path,
    pair: ClaimFirstRootPair,
    local_claim: Mapping[str, object],
    local_claim_sha256: str,
    failpoint: RedLivingDexDevelopmentSetupFailpoint | None,
) -> RedLivingDexDevelopmentSetupReceipt:
    before_claim = meter.checkpoint()
    with claim_first_pair_registry(claim_registry) as transaction:
        retained = transaction.claim(pair)
        meter.record_root_claim()
        _require_only_root_claim_changed(before_claim, meter.checkpoint())
        if retained != pair:
            raise RedLivingDexDevelopmentSetupJournalError(
                "development setup retained another root pair"
            )
        _trip(failpoint, "after_pair_claim", frozen)
        _publish_exact(
            store,
            _record_id("claim", pair),
            kind="claim",
            document=local_claim,
        )
    _trip(failpoint, "after_local_claim", frozen)
    before_setup = meter.checkpoint()
    try:
        frozen.reauthenticate(plan_loader(), root=root)
        if meter.checkpoint() != before_setup:
            raise RedLivingDexDevelopmentSetupJournalError(
                "development plan reauthentication changed effects"
            )
        _trip(failpoint, "after_plan_reauthentication", frozen)
        scope = resolver(frozen, root, pair, meter=meter)
        if meter.checkpoint() != before_setup:
            raise RedLivingDexDevelopmentSetupJournalError(
                "development cold resolver changed effects"
            )
        with scope as resolved:
            _require_resolved_slot(
                frozen,
                resolved,
                outer_execution_identity,
            )
            _publish_exact(
                store,
                _record_id("release", pair),
                kind="release",
                document={
                    "effect_checkpoint": before_setup.private_dict(),
                    "local_claim_sha256": local_claim_sha256,
                    "pair_claim_sha256": pair.claim_sha256,
                    "schema": RED_LIVING_DEX_DEVELOPMENT_SETUP_RELEASE_SCHEMA,
                },
            )
            _trip(failpoint, "after_controller_release", frozen)
            slot = _prospective_slot(frozen.selection.template_ordinal)
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
            raise RedLivingDexDevelopmentSetupJournalError(
                "development setup accounting differs from capture"
            )
        _publish_exact(
            store,
            _record_id("capture", pair),
            kind="capture",
            document=capture.private_dict(),
        )
        _trip(failpoint, "after_capture", frozen)
    except BaseException as error:
        actions, frames = before_setup.action_frame_delta(meter.checkpoint())
        interrupted = not isinstance(error, Exception)
        terminal = _failed_terminal(
            frozen,
            pair,
            local_claim_sha256,
            interrupted=interrupted,
            accounting=(actions, frames),
        )
        with suppress(Exception):
            _publish_terminal(store, pair, terminal)
        if interrupted:
            raise
        return RedLivingDexDevelopmentSetupReceipt(
            frozen,
            terminal,
            RedLivingDexDevelopmentSetupDisposition.EXECUTED_FAILED,
            None,
        )
    terminal = _complete_terminal(
        frozen,
        pair,
        local_claim_sha256,
        capture,
    )
    _publish_terminal(store, pair, terminal)
    _trip(failpoint, "after_terminal", frozen)
    return RedLivingDexDevelopmentSetupReceipt(
        frozen,
        terminal,
        RedLivingDexDevelopmentSetupDisposition.EXECUTED_COMPLETE,
        capture,
    )


def _require_outer_identity(
    frozen: FrozenRedLivingDexDevelopmentSetupSlot,
    identity: ClaimFirstExecutionIdentity,
) -> None:
    selection = frozen.selection
    if (
        identity.producer_plan_sha256 != selection.private_plan_sha256
        or identity.producer_private_plan_sha256
        != selection.private_plan_sha256
        or identity.producer_manifest_sha256
        != frozen.binding.plan_manifest_sha256
        or identity.producer_execution_identity_sha256
        != frozen.producer_execution_identity_sha256
        or identity.slot_sha256 != selection.slot_sha256
        or identity.recipe_sha256 != selection.recipe_sha256
        or identity.logical_root_sha256 != selection.logical_root_sha256
        or identity.physical_root_sha256 != selection.physical_root_sha256
        or identity.runner_sha256
        != RED_LIVING_DEX_DEVELOPMENT_SETUP_RUNNER_SHA256
    ):
        raise RedLivingDexDevelopmentSetupJournalError(
            "development outer identity differs"
        )


def _require_resolved_slot(
    frozen: FrozenRedLivingDexDevelopmentSetupSlot,
    resolved: RedLivingDexResolvedSetupSlot,
    outer: ClaimFirstExecutionIdentity,
) -> None:
    if not isinstance(resolved, RedLivingDexResolvedSetupSlot):
        raise TypeError("development resolver returned another setup type")
    resolved.__post_init__()
    frozen.require_resolved_recipe(resolved.recipe)
    if (
        resolved.producer_execution_identity.identity_sha256
        != frozen.producer_execution_identity_sha256
        or resolved.title_adapter_sha256 != outer.title_adapter_sha256
        or resolved.runtime_factory_sha256 != outer.runtime_factory_sha256
    ):
        raise RedLivingDexDevelopmentSetupJournalError(
            "development resolved setup identity differs"
        )


def _local_claim(
    frozen: FrozenRedLivingDexDevelopmentSetupSlot,
    outer: ClaimFirstExecutionIdentity,
    pair: ClaimFirstRootPair,
) -> dict[str, object]:
    selection = frozen.selection
    return {
        "claim_before_controller_input": True,
        "development_outcomes_opened": 0,
        "learner_effects": 0,
        "logical_root_sha256": selection.logical_root_sha256,
        "outer_execution_identity_sha256": outer.identity_sha256,
        "pair_claim_sha256": pair.claim_sha256,
        "physical_root_sha256": selection.physical_root_sha256,
        "producer_execution_identity_sha256": (
            frozen.producer_execution_identity_sha256
        ),
        "producer_plan_sha256": selection.private_plan_sha256,
        "recipe_sha256": selection.recipe_sha256,
        "retry_after_pair_claim": False,
        "schema": RED_LIVING_DEX_DEVELOPMENT_SETUP_CLAIM_SCHEMA,
        "slot_sha256": selection.slot_sha256,
        "training_targets_emitted": 0,
    }


def _complete_terminal(
    frozen: FrozenRedLivingDexDevelopmentSetupSlot,
    pair: ClaimFirstRootPair,
    local_claim_sha256: str,
    capture: RedLivingDexValidatedSetupCapture,
) -> RedLivingDexDevelopmentSetupTerminal:
    return _terminal(
        frozen,
        pair,
        local_claim_sha256,
        status=LivingDexCaptureSetupStatus.COMPLETE,
        reason_code=None,
        setup_controller_actions=(
            capture.attestation.setup_controller_actions
        ),
        setup_emulator_frames=capture.attestation.setup_emulator_frames,
        attestation_sha256=capture.attestation.attestation_sha256,
    )


def _failed_terminal(
    frozen: FrozenRedLivingDexDevelopmentSetupSlot,
    pair: ClaimFirstRootPair,
    local_claim_sha256: str,
    *,
    interrupted: bool,
    accounting: tuple[int, int],
) -> RedLivingDexDevelopmentSetupTerminal:
    return _terminal(
        frozen,
        pair,
        local_claim_sha256,
        status=(
            LivingDexCaptureSetupStatus.INTERRUPTED
            if interrupted
            else LivingDexCaptureSetupStatus.FAILED
        ),
        reason_code=(
            RedLivingDexSetupFailureReason.PROCESS_INTERRUPTED
            if interrupted
            else RedLivingDexSetupFailureReason.RECIPE_EXECUTION_FAILED
        ),
        setup_controller_actions=accounting[0],
        setup_emulator_frames=accounting[1],
        attestation_sha256=None,
    )


def _interrupted_terminal(
    frozen: FrozenRedLivingDexDevelopmentSetupSlot,
    pair: ClaimFirstRootPair,
    local_claim_sha256: str,
    *,
    accounting: tuple[int, int] | None,
) -> RedLivingDexDevelopmentSetupTerminal:
    return _terminal(
        frozen,
        pair,
        local_claim_sha256,
        status=LivingDexCaptureSetupStatus.INTERRUPTED,
        reason_code=RedLivingDexSetupFailureReason.PROCESS_INTERRUPTED,
        setup_controller_actions=(None if accounting is None else accounting[0]),
        setup_emulator_frames=(None if accounting is None else accounting[1]),
        attestation_sha256=None,
    )


def _terminal(
    frozen: FrozenRedLivingDexDevelopmentSetupSlot,
    pair: ClaimFirstRootPair,
    local_claim_sha256: str,
    *,
    status: LivingDexCaptureSetupStatus,
    reason_code: RedLivingDexSetupFailureReason | None,
    setup_controller_actions: int | None,
    setup_emulator_frames: int | None,
    attestation_sha256: str | None,
) -> RedLivingDexDevelopmentSetupTerminal:
    selection = frozen.selection
    return RedLivingDexDevelopmentSetupTerminal(
        selection.private_plan_sha256,
        selection.recipe_sha256,
        selection.slot_sha256,
        pair.execution_identity_sha256,
        frozen.producer_execution_identity_sha256,
        pair.claim_sha256,
        local_claim_sha256,
        status,
        reason_code,
        setup_controller_actions,
        setup_emulator_frames,
        attestation_sha256,
    )


def _receipt_from_terminal(
    terminal: RedLivingDexDevelopmentSetupTerminal,
    capture: RedLivingDexValidatedSetupCapture | None,
    frozen: FrozenRedLivingDexDevelopmentSetupSlot,
) -> RedLivingDexDevelopmentSetupReceipt:
    if terminal.status is LivingDexCaptureSetupStatus.COMPLETE:
        disposition = RedLivingDexDevelopmentSetupDisposition.RECOVERED_COMPLETE
    elif terminal.status is LivingDexCaptureSetupStatus.FAILED:
        disposition = RedLivingDexDevelopmentSetupDisposition.RECOVERED_FAILED
    else:
        disposition = RedLivingDexDevelopmentSetupDisposition.RECOVERED_INTERRUPTED
    return RedLivingDexDevelopmentSetupReceipt(
        frozen,
        terminal,
        disposition,
        capture,
    )


def _publish_terminal(
    store: PrivateArtifactRoot,
    pair: ClaimFirstRootPair,
    terminal: RedLivingDexDevelopmentSetupTerminal,
) -> None:
    _publish_exact(
        store,
        _record_id("terminal", pair),
        kind="terminal",
        document=terminal.private_dict(),
    )


def _find_terminal(
    store: PrivateArtifactRoot,
    frozen: FrozenRedLivingDexDevelopmentSetupSlot,
    pair: ClaimFirstRootPair,
    local_claim_sha256: str,
) -> RedLivingDexDevelopmentSetupTerminal | None:
    document = _find_record(store, _record_id("terminal", pair), "terminal")
    if document is None:
        return None
    expected_keys = {
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
    try:
        if (
            set(document) != expected_keys
            or document.get("schema")
            != RED_LIVING_DEX_DEVELOPMENT_SETUP_TERMINAL_SCHEMA
            or document.get("retry_allowed") is not False
        ):
            raise ValueError("terminal fields differ")
        reason_raw = document.get("reason_code")
        terminal = RedLivingDexDevelopmentSetupTerminal(
            _text(document, "producer_plan_sha256"),
            _text(document, "recipe_sha256"),
            _text(document, "slot_sha256"),
            _text(document, "outer_execution_identity_sha256"),
            _text(document, "producer_execution_identity_sha256"),
            _text(document, "pair_claim_sha256"),
            _text(document, "local_claim_sha256"),
            LivingDexCaptureSetupStatus(_text(document, "status")),
            (
                None
                if reason_raw is None
                else RedLivingDexSetupFailureReason(str(reason_raw))
            ),
            _optional_integer(document, "setup_controller_actions"),
            _optional_integer(document, "setup_emulator_frames"),
            _optional_text(document, "attestation_sha256"),
        )
    except (TypeError, ValueError):
        raise RedLivingDexDevelopmentSetupJournalError(
            "stored development setup terminal differs"
        ) from None
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
    if terminal != expected or terminal.private_dict() != document:
        raise RedLivingDexDevelopmentSetupJournalError(
            "stored development setup terminal differs"
        )
    return terminal


def _find_capture(
    store: PrivateArtifactRoot,
    frozen: FrozenRedLivingDexDevelopmentSetupSlot,
    pair: ClaimFirstRootPair,
) -> RedLivingDexValidatedSetupCapture | None:
    document = _find_record(store, _record_id("capture", pair), "capture")
    if document is None:
        return None
    capture = restore_red_living_dex_validated_setup_capture(document)
    if (
        capture.private_dict() != document
        or capture.recipe_sha256 != frozen.selection.recipe_sha256
        or capture.execution_identity_sha256
        != frozen.producer_execution_identity_sha256
    ):
        raise RedLivingDexDevelopmentSetupJournalError(
            "stored development setup capture differs"
        )
    return capture


def _validate_claim_and_release(
    claim: Mapping[str, object] | None,
    release: Mapping[str, object] | None,
    expected_claim: Mapping[str, object],
    pair: ClaimFirstRootPair,
) -> None:
    if claim is None or dict(claim) != dict(expected_claim):
        raise RedLivingDexDevelopmentSetupJournalError(
            "stored development setup claim differs"
        )
    if release is None:
        return
    checkpoint = release.get("effect_checkpoint")
    if (
        set(release)
        != {
            "effect_checkpoint",
            "local_claim_sha256",
            "pair_claim_sha256",
            "schema",
        }
        or release.get("schema")
        != RED_LIVING_DEX_DEVELOPMENT_SETUP_RELEASE_SCHEMA
        or release.get("local_claim_sha256")
        != canonical_sha256(expected_claim)
        or release.get("pair_claim_sha256") != pair.claim_sha256
        or not isinstance(checkpoint, Mapping)
    ):
        raise RedLivingDexDevelopmentSetupJournalError(
            "stored development setup release differs"
        )
    expected_checkpoint_keys = {
        *RedLivingDexSetupProtectedEffectCheckpoint.__dataclass_fields__,
        "schema",
    }
    try:
        restored = RedLivingDexSetupProtectedEffectCheckpoint(
            **{
                name: checkpoint[name]
                for name in RedLivingDexSetupProtectedEffectCheckpoint.__dataclass_fields__
            }
        )
    except (KeyError, TypeError, ValueError):
        raise RedLivingDexDevelopmentSetupJournalError(
            "stored development setup release differs"
        ) from None
    if set(checkpoint) != expected_checkpoint_keys or restored.private_dict() != checkpoint:
        raise RedLivingDexDevelopmentSetupJournalError(
            "stored development setup release differs"
        )


def _read_exact_or_overlap(
    registry: Path,
    pair: ClaimFirstRootPair,
) -> ClaimFirstRootPair | None:
    try:
        restored = read_root_pair_claim(registry, pair.claim_sha256)
    except ClaimFirstAdmissionError:
        overlaps = tuple(
            item
            for item in root_pair_claims(registry)
            if not pair.identities.isdisjoint(item.identities)
        )
        if overlaps:
            raise RedLivingDexDevelopmentSetupJournalError(
                "development setup root belongs to another execution"
            ) from None
        return None
    if restored != pair:
        raise RedLivingDexDevelopmentSetupJournalError(
            "development setup pair claim differs"
        )
    return restored


def _require_exact_pair_claim(registry: Path, pair: ClaimFirstRootPair) -> None:
    if _read_exact_or_overlap(registry, pair) is None:
        raise RedLivingDexDevelopmentSetupJournalError(
            "development setup local state lacks its pair claim"
        )


def _require_only_root_claim_changed(
    before: RedLivingDexSetupProtectedEffectCheckpoint,
    after: RedLivingDexSetupProtectedEffectCheckpoint,
) -> None:
    if after != replace(before, root_claims=before.root_claims + 1):
        raise RedLivingDexDevelopmentSetupJournalError(
            "development pair claim changed unrelated effects"
        )


def _publish_exact(
    store: PrivateArtifactRoot,
    record_id: str,
    *,
    kind: str,
    document: Mapping[str, object],
) -> None:
    sealed = store.publish_sealed_record(
        record_id,
        kind=f"red_living_dex_development_setup_{kind}",
        record=document,
    )
    if sealed.read() != dict(document):
        raise RedLivingDexDevelopmentSetupJournalError(
            f"development setup {kind} publication differs"
        )


def _find_record(
    store: PrivateArtifactRoot,
    record_id: str,
    kind: str,
) -> dict[str, object] | None:
    sealed = store.find_sealed_record(
        record_id,
        expected_kind=f"red_living_dex_development_setup_{kind}",
    )
    return None if sealed is None else sealed.read()


def _record_id(stage: str, pair: ClaimFirstRootPair) -> str:
    return f"rldds-{stage}-{pair.claim_sha256}"


def _prospective_slot(ordinal: int):  # type: ignore[no-untyped-def]
    from pokemon_red_completion.red_living_dex_capture_plan import (
        build_red_living_dex_prospective_capture_plan,
    )

    return build_red_living_dex_prospective_capture_plan().slots[ordinal]


def _trip(
    failpoint: RedLivingDexDevelopmentSetupFailpoint | None,
    stage: str,
    frozen: FrozenRedLivingDexDevelopmentSetupSlot,
) -> None:
    if failpoint is not None:
        failpoint(stage, frozen)


def _require_sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedLivingDexDevelopmentSetupJournalError(
            f"development setup {subject} differs"
        )
    return value


def _text(document: Mapping[str, object], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise RedLivingDexDevelopmentSetupJournalError(
            f"development setup {key} differs"
        )
    return value


def _optional_text(document: Mapping[str, object], key: str) -> str | None:
    value = document.get(key)
    return None if value is None else _text(document, key)


def _optional_integer(document: Mapping[str, object], key: str) -> int | None:
    value = document.get(key)
    if value is None:
        return None
    if type(value) is not int or value < 0:  # noqa: E721
        raise RedLivingDexDevelopmentSetupJournalError(
            f"development setup {key} differs"
        )
    return value


__all__ = [
    "RED_LIVING_DEX_DEVELOPMENT_SETUP_COLLECTION_ID",
    "RED_LIVING_DEX_DEVELOPMENT_SETUP_RUNNER_SHA256",
    "RedLivingDexDevelopmentSetupDisposition",
    "RedLivingDexDevelopmentSetupJournalError",
    "RedLivingDexDevelopmentSetupReceipt",
    "RedLivingDexDevelopmentSetupResolver",
    "RedLivingDexDevelopmentSetupTerminal",
    "run_red_living_dex_development_setup",
]
