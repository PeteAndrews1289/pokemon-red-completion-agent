"""Execute one preregistered reset-aware Red living-Pokedex train slot.

The runner consumes only train slots from the outcome-blind targeted schedule.
It reserves each underlying checkpoint once, claims each declared reset once,
durably retains setup recovery state, applies the title-neutral focus policy,
and delegates selected-arm outcome retention to the causal journal.  It has no
model-fit, teacher, development-partition, or counterfactual interface.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from pokemon_red_completion.living_dex_causal_journal import (
    LivingDexCausalReceipt,
    materialize_living_dex_causal_example,
)
from pokemon_red_completion.living_dex_repeatable_trial_claim import (
    LivingDexRepeatableClaimDisposition,
    LivingDexRepeatableRootReservation,
    LivingDexRepeatableTrialClaim,
    ensure_living_dex_repeatable_trial_claim,
)
from pokemon_red_completion.living_dex_targeted_behavior import (
    LIVING_DEX_TARGETED_BEHAVIOR_SHA256,
    living_dex_targeted_behavior_integer_weights,
)
from pokemon_red_completion.living_dex_targeted_update_capacity import (
    LivingDexTargetedScheduleSlot,
)
from pokemon_red_completion.private_artifacts import PrivateArtifactRoot
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_causal_adapter import (
    build_red_living_dex_causal_scenario_from_capture,
)
from pokemon_red_completion.red_living_dex_causal_inventory import (
    RedLivingDexCausalRootCapability,
    RedLivingDexTargetedScheduleBinding,
)
from pokemon_red_completion.red_living_dex_claim_first_campaign import (
    RedLivingDexResolvedSetupSlot,
)
from pokemon_red_completion.red_living_dex_production_runtime import (
    RedLivingDexProductionRuntimeError,
    RedLivingDexProductionSetupResolver,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RED_LIVING_DEX_SETUP_PHASES,
    RedLivingDexAuthenticatedSetupRoot,
    RedLivingDexSetupEffectMeter,
    RedLivingDexSetupRecipeError,
    RedLivingDexSetupSlotRecipe,
    RedLivingDexValidatedSetupCapture,
    restore_red_living_dex_validated_setup_capture,
    validate_red_living_dex_setup_recipe,
)
from pokemon_red_completion.red_living_dex_setup_trust import (
    RedLivingDexSetupExecutionIdentity,
)

RED_LIVING_DEX_TARGETED_TRAIN_RUNNER_SCHEMA = (
    "pokemon.red.living-dex-targeted-reset-train-runner.v1"
)
RED_LIVING_DEX_TARGETED_TRAIN_RUNNER_SHA256 = canonical_sha256(
    {
        "behavior_policy_sha256": LIVING_DEX_TARGETED_BEHAVIOR_SHA256,
        "counterfactual_targets": 0,
        "development_slots_addressable": 0,
        "model_fits": 0,
        "reset_trials_declared_as_clustered": True,
        "schema": RED_LIVING_DEX_TARGETED_TRAIN_RUNNER_SCHEMA,
        "selected_arm_outcome_only": True,
        "teacher_queries": 0,
    }
)

_COLLECTION_ID = "red-living-dex-targeted-reset-train-v1"
_SETUP_CLAIM_KIND = "red_living_dex_targeted_setup_claim"
_SETUP_CAPTURE_KIND = "red_living_dex_targeted_setup_capture"
_SETUP_TERMINAL_KIND = "red_living_dex_targeted_setup_terminal"
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_TARGETED_SETUP_FAILURE_PHASES = RED_LIVING_DEX_SETUP_PHASES | {
    "claim_recovery",
    "resolver_reauthentication",
    "setup_capture_validation",
}
_TARGETED_SETUP_FAILURE_CLASSES = {
    "process_interruption",
    "production_runtime_error",
    "setup_recipe_error",
    "targeted_runner_error",
    "unexpected_error",
}


class RedLivingDexTargetedTrainRunnerError(RuntimeError):
    """A frozen train slot, reset claim, setup, or causal join differs."""


class RedLivingDexTargetedSetupStatus(StrEnum):
    COMPLETE = "complete"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True, slots=True)
class RedLivingDexTargetedTrainAssignment:
    """One train-only view over an exact schedule slot and Red recipe."""

    binding: RedLivingDexTargetedScheduleBinding = field(repr=False)
    ordinal: int
    source_commit: str

    def __post_init__(self) -> None:
        if not isinstance(self.binding, RedLivingDexTargetedScheduleBinding):
            raise TypeError("targeted train assignment needs its schedule binding")
        self.binding.__post_init__()
        if (
            type(self.ordinal) is not int  # noqa: E721
            or not 0 <= self.ordinal < len(self.binding.schedule.slots)
            or self.binding.schedule.slots[self.ordinal].partition != "train"
        ):
            raise RedLivingDexTargetedTrainRunnerError(
                "targeted development slot is not addressable by training"
            )
        if not isinstance(self.source_commit, str) or _GIT_COMMIT.fullmatch(
            self.source_commit
        ) is None:
            raise RedLivingDexTargetedTrainRunnerError(
                "targeted train source commit differs"
            )

    @property
    def slot(self) -> LivingDexTargetedScheduleSlot:
        return self.binding.schedule.slots[self.ordinal]

    @property
    def capability(self) -> RedLivingDexCausalRootCapability:
        return self.binding.capabilities[self.ordinal]

    @property
    def reservation(self) -> LivingDexRepeatableRootReservation:
        root = self.capability.root.root
        return LivingDexRepeatableRootReservation(
            schedule_sha256=self.binding.schedule.schedule_sha256,
            logical_root_sha256=root.root_consumption_sha256,
            physical_root_sha256=root.physical_root_sha256,
            runner_sha256=RED_LIVING_DEX_TARGETED_TRAIN_RUNNER_SHA256,
            source_commit=self.source_commit,
        )

    @property
    def trial(self) -> LivingDexRepeatableTrialClaim:
        return LivingDexRepeatableTrialClaim(
            self.reservation,
            self.slot.slot_sha256,
            self.slot.reset_ordinal,
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "focus_kind": self.slot.focus_kind.value,
            "ordinal": self.ordinal,
            "partition": "train",
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "reset_ordinal": self.slot.reset_ordinal,
            "shared_base_root_declared": True,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexTargetedTrainReceipt:
    assignment: RedLivingDexTargetedTrainAssignment = field(repr=False)
    setup_status: RedLivingDexTargetedSetupStatus
    causal: LivingDexCausalReceipt | None
    setup_failure_phase: str | None = None
    setup_failure_class: str | None = None

    def __post_init__(self) -> None:
        self.assignment.__post_init__()
        if not isinstance(self.setup_status, RedLivingDexTargetedSetupStatus):
            raise TypeError("targeted train receipt setup status differs")
        if self.setup_status is RedLivingDexTargetedSetupStatus.COMPLETE:
            if not isinstance(self.causal, LivingDexCausalReceipt):
                raise RedLivingDexTargetedTrainRunnerError(
                    "complete targeted setup lacks its causal receipt"
                )
            self.causal.__post_init__()
            if (
                self.causal.scenario.identity.partition != "train"
                or self.causal.scenario.identity.repeatable_trial_claim_sha256
                != self.assignment.trial.trial_claim_sha256
            ):
                raise RedLivingDexTargetedTrainRunnerError(
                    "targeted causal receipt crossed its reset slot"
                )
        elif self.causal is not None:
            raise RedLivingDexTargetedTrainRunnerError(
                "failed targeted setup opened a causal outcome"
            )
        if (
            self.setup_failure_phase is not None
            and self.setup_failure_phase not in _TARGETED_SETUP_FAILURE_PHASES
        ):
            raise RedLivingDexTargetedTrainRunnerError(
                "targeted setup failure phase differs"
            )
        if (
            self.setup_status is RedLivingDexTargetedSetupStatus.COMPLETE
            and (
                self.setup_failure_phase is not None
                or self.setup_failure_class is not None
            )
        ):
            raise RedLivingDexTargetedTrainRunnerError(
                "complete targeted setup retained failure diagnostics"
            )
        if self.setup_status is not RedLivingDexTargetedSetupStatus.COMPLETE and (
            (self.setup_failure_phase is None) != (self.setup_failure_class is None)
            or (
                self.setup_failure_class is not None
                and self.setup_failure_class not in _TARGETED_SETUP_FAILURE_CLASSES
            )
        ):
            raise RedLivingDexTargetedTrainRunnerError(
                "targeted setup failure diagnostics differ"
            )

    def public_dict(self) -> dict[str, object]:
        return {
            **self.assignment.public_dict(),
            "causal_train_example_recorded": (
                self.causal is not None and self.causal.example is not None
            ),
            "counterfactual_targets": 0,
            "model_fits": 0,
            "model_predictions": 0,
            "schema": "pokemon.red.living-dex-targeted-reset-train-receipt.v2",
            "setup_failure_class": self.setup_failure_class,
            "setup_failure_phase": self.setup_failure_phase,
            "setup_status": self.setup_status.value,
            "teacher_queries": 0,
        }


@dataclass(frozen=True, slots=True)
class _FrozenTargetedRecipe:
    capability: RedLivingDexCausalRootCapability

    def __post_init__(self) -> None:
        if not isinstance(self.capability, RedLivingDexCausalRootCapability):
            raise TypeError("targeted frozen recipe needs its capability")
        self.capability.__post_init__()

    @property
    def template_ordinal(self) -> int:
        return self.capability.template_ordinal

    def require_resolved_recipe(self, recipe: RedLivingDexSetupSlotRecipe) -> None:
        if (
            not isinstance(recipe, RedLivingDexSetupSlotRecipe)
            or recipe.private_dict() != self.capability.recipe.private_dict()
        ):
            raise RedLivingDexTargetedTrainRunnerError(
                "targeted runtime rebuilt another recipe"
            )


def run_red_living_dex_targeted_train_assignment(
    assignment: RedLivingDexTargetedTrainAssignment,
    *,
    store: PrivateArtifactRoot,
    claim_registry: Path,
    setup_execution_identity: RedLivingDexSetupExecutionIdentity,
    resolver: RedLivingDexProductionSetupResolver,
    meter: RedLivingDexSetupEffectMeter,
) -> RedLivingDexTargetedTrainReceipt:
    """Execute or recover exactly one frozen reset-aware train assignment."""

    if not isinstance(assignment, RedLivingDexTargetedTrainAssignment):
        raise TypeError("targeted train runner needs an assignment")
    assignment.__post_init__()
    if not isinstance(store, PrivateArtifactRoot):
        raise TypeError("targeted train runner needs a private store")
    if not isinstance(claim_registry, Path):
        raise TypeError("targeted train runner needs a claim registry Path")
    if not isinstance(setup_execution_identity, RedLivingDexSetupExecutionIdentity):
        raise TypeError("targeted train runner needs a setup identity")
    setup_execution_identity.__post_init__()
    if not isinstance(resolver, RedLivingDexProductionSetupResolver):
        raise TypeError("targeted train runner needs the production resolver")
    resolver.__post_init__()
    if type(meter) is not RedLivingDexSetupEffectMeter:
        raise TypeError("targeted train runner needs the comprehensive meter")
    if (
        setup_execution_identity.source_commit != assignment.source_commit
        or resolver.producer_execution_identity != setup_execution_identity
    ):
        raise RedLivingDexTargetedTrainRunnerError(
            "targeted train execution identity differs"
        )

    trial = assignment.trial
    claim_disposition = ensure_living_dex_repeatable_trial_claim(
        claim_registry,
        trial,
    )
    frozen = _FrozenTargetedRecipe(assignment.capability)
    root = assignment.capability.root.root
    with store.collection_session(_COLLECTION_ID):
        (
            setup_status,
            capture,
            setup_terminal_sha256,
            setup_failure_phase,
            setup_failure_class,
        ) = _ensure_setup_capture(
            assignment,
            trial=trial,
            claim_disposition=claim_disposition,
            frozen=frozen,
            root=root,
            setup_execution_identity=setup_execution_identity,
            resolver=resolver,
            meter=meter,
            store=store,
        )
    if capture is None:
        return RedLivingDexTargetedTrainReceipt(
            assignment,
            setup_status,
            None,
            setup_failure_phase,
            setup_failure_class,
        )

    @contextmanager
    def resolve_runtime():  # type: ignore[no-untyped-def]
        with resolver(
            frozen,
            root,
            trial.reservation.pair_claim,
            meter=meter,
        ) as resolved:
            _require_resolved(resolved, frozen, setup_execution_identity)
            yield resolved

    weights = living_dex_targeted_behavior_integer_weights(
        capture.policy_projection.menu,
        assignment.slot.focus_kind,
    )
    scenario = build_red_living_dex_causal_scenario_from_capture(
        capture,
        setup_execution_identity=setup_execution_identity,
        runtime_resolver=resolve_runtime,
        meter=meter,
        setup_terminal_sha256=setup_terminal_sha256,
        setup_pair_claim_sha256=trial.trial_claim_sha256,
        causal_source_commit=setup_execution_identity.source_commit,
        causal_runner_sha256=RED_LIVING_DEX_TARGETED_TRAIN_RUNNER_SHA256,
        upstream_lineage_sha256=assignment.slot.lineage_sha256,
        behavior_integer_weights=weights,
        repeatable_trial_claim_sha256=trial.trial_claim_sha256,
    )
    causal = materialize_living_dex_causal_example(
        scenario,
        store=store,
        claim_registry=claim_registry,
    )
    return RedLivingDexTargetedTrainReceipt(
        assignment,
        RedLivingDexTargetedSetupStatus.COMPLETE,
        causal,
        None,
        None,
    )


def _ensure_setup_capture(
    assignment: RedLivingDexTargetedTrainAssignment,
    *,
    trial: LivingDexRepeatableTrialClaim,
    claim_disposition: LivingDexRepeatableClaimDisposition,
    frozen: _FrozenTargetedRecipe,
    root: RedLivingDexAuthenticatedSetupRoot,
    setup_execution_identity: RedLivingDexSetupExecutionIdentity,
    resolver: RedLivingDexProductionSetupResolver,
    meter: RedLivingDexSetupEffectMeter,
    store: PrivateArtifactRoot,
) -> tuple[
    RedLivingDexTargetedSetupStatus,
    RedLivingDexValidatedSetupCapture | None,
    str,
    str | None,
    str | None,
]:
    suffix = trial.trial_claim_sha256[:32]
    claim_id = f"lrt-setup-claim-{suffix}"
    capture_id = f"lrt-setup-capture-{suffix}"
    terminal_id = f"lrt-setup-terminal-{suffix}"
    terminal_record = store.find_sealed_record(
        terminal_id,
        expected_kind=_SETUP_TERMINAL_KIND,
    )
    capture_record = store.find_sealed_record(
        capture_id,
        expected_kind=_SETUP_CAPTURE_KIND,
    )
    if terminal_record is not None:
        terminal = _restore_terminal(terminal_record.read(), trial)
        status = RedLivingDexTargetedSetupStatus(str(terminal["status"]))
        if status is not RedLivingDexTargetedSetupStatus.COMPLETE:
            if capture_record is not None:
                raise RedLivingDexTargetedTrainRunnerError(
                    "noncomplete targeted setup retained a capture"
                )
            return (
                status,
                None,
                canonical_sha256(terminal),
                _optional_failure_phase(terminal),
                _optional_failure_class(terminal),
            )
        if capture_record is None:
            raise RedLivingDexTargetedTrainRunnerError(
                "complete targeted setup lost its capture"
            )
        capture = restore_red_living_dex_validated_setup_capture(
            capture_record.read()
        )
        _require_capture_join(assignment, capture, setup_execution_identity)
        return status, capture, canonical_sha256(terminal), None, None

    if capture_record is not None:
        capture = restore_red_living_dex_validated_setup_capture(
            capture_record.read()
        )
        _require_capture_join(assignment, capture, setup_execution_identity)
        terminal = _publish_terminal(
            store,
            terminal_id,
            trial,
            status=RedLivingDexTargetedSetupStatus.COMPLETE,
            capture_sha256=canonical_sha256(capture.private_dict()),
            failure_phase=None,
            failure_class=None,
            setup_controller_actions=capture.attestation.setup_controller_actions,
            setup_emulator_frames=capture.attestation.setup_emulator_frames,
        )
        return (
            RedLivingDexTargetedSetupStatus.COMPLETE,
            capture,
            canonical_sha256(terminal),
            None,
            None,
        )

    if claim_disposition is LivingDexRepeatableClaimDisposition.RECOVERED:
        terminal = _publish_terminal(
            store,
            terminal_id,
            trial,
            status=RedLivingDexTargetedSetupStatus.INTERRUPTED,
            capture_sha256=None,
            failure_phase="claim_recovery",
            failure_class="process_interruption",
            setup_controller_actions=0,
            setup_emulator_frames=0,
        )
        return (
            RedLivingDexTargetedSetupStatus.INTERRUPTED,
            None,
            canonical_sha256(terminal),
            "claim_recovery",
            "process_interruption",
        )

    store.publish_sealed_record(
        claim_id,
        kind=_SETUP_CLAIM_KIND,
        record=trial.private_dict(),
    )
    setup_before = meter.checkpoint()
    phase = ["resolver_reauthentication"]
    try:
        with resolver(
            frozen,
            root,
            trial.reservation.pair_claim,
            meter=meter,
        ) as resolved:
            _require_resolved(resolved, frozen, setup_execution_identity)
            phase[0] = "setup_capture_validation"
            capture = validate_red_living_dex_setup_recipe(
                assignment.capability.slot,
                resolved.recipe,
                execution_identity=setup_execution_identity,
                root=root,
                arm_factory=resolved.arm_factory,
                meter=meter,
                phase_observer=lambda value: phase.__setitem__(0, value),
            )
    except BaseException as error:
        status = (
            RedLivingDexTargetedSetupStatus.FAILED
            if isinstance(error, Exception)
            else RedLivingDexTargetedSetupStatus.INTERRUPTED
        )
        terminal = _publish_terminal(
            store,
            terminal_id,
            trial,
            status=status,
            capture_sha256=None,
            failure_phase=phase[0],
            failure_class=_setup_failure_class(error),
            setup_controller_actions=(
                meter.controller_actions - setup_before.controller_actions
            ),
            setup_emulator_frames=(
                meter.emulator_frames - setup_before.emulator_frames
            ),
        )
        if not isinstance(error, Exception):
            raise
        return (
            status,
            None,
            canonical_sha256(terminal),
            phase[0],
            _setup_failure_class(error),
        )
    _require_capture_join(assignment, capture, setup_execution_identity)
    store.publish_sealed_record(
        capture_id,
        kind=_SETUP_CAPTURE_KIND,
        record=capture.private_dict(),
    )
    terminal = _publish_terminal(
        store,
        terminal_id,
        trial,
        status=RedLivingDexTargetedSetupStatus.COMPLETE,
        capture_sha256=canonical_sha256(capture.private_dict()),
        failure_phase=None,
        failure_class=None,
        setup_controller_actions=capture.attestation.setup_controller_actions,
        setup_emulator_frames=capture.attestation.setup_emulator_frames,
    )
    return (
        RedLivingDexTargetedSetupStatus.COMPLETE,
        capture,
        canonical_sha256(terminal),
        None,
        None,
    )


def _publish_terminal(
    store: PrivateArtifactRoot,
    record_id: str,
    trial: LivingDexRepeatableTrialClaim,
    *,
    status: RedLivingDexTargetedSetupStatus,
    capture_sha256: str | None,
    failure_phase: str | None,
    failure_class: str | None,
    setup_controller_actions: int,
    setup_emulator_frames: int,
) -> Mapping[str, object]:
    terminal: dict[str, object] = {
        "capture_sha256": capture_sha256,
        "failure_class": failure_class,
        "failure_phase": failure_phase,
        "retry_allowed": False,
        "schema": "pokemon.red.private-living-dex-targeted-setup-terminal.v2",
        "setup_controller_actions": setup_controller_actions,
        "setup_emulator_frames": setup_emulator_frames,
        "status": status.value,
        "trial_claim_sha256": trial.trial_claim_sha256,
    }
    sealed = store.publish_sealed_record(
        record_id,
        kind=_SETUP_TERMINAL_KIND,
        record=terminal,
    )
    return _restore_terminal(sealed.read(), trial)


def _restore_terminal(
    document: Mapping[str, object],
    trial: LivingDexRepeatableTrialClaim,
) -> Mapping[str, object]:
    v1_fields = {
        "capture_sha256",
        "retry_allowed",
        "schema",
        "status",
        "trial_claim_sha256",
    }
    v2_fields = v1_fields | {
        "failure_class",
        "failure_phase",
        "setup_controller_actions",
        "setup_emulator_frames",
    }
    schema = document.get("schema")
    if (
        (
            schema == "pokemon.red.private-living-dex-targeted-setup-terminal.v1"
            and set(document) != v1_fields
        )
        or (
            schema == "pokemon.red.private-living-dex-targeted-setup-terminal.v2"
            and set(document) != v2_fields
        )
        or schema not in {
            "pokemon.red.private-living-dex-targeted-setup-terminal.v1",
            "pokemon.red.private-living-dex-targeted-setup-terminal.v2",
        }
    ):
        raise RedLivingDexTargetedTrainRunnerError(
            "targeted setup terminal fields differ"
        )
    try:
        status = RedLivingDexTargetedSetupStatus(str(document["status"]))
    except ValueError:
        raise RedLivingDexTargetedTrainRunnerError(
            "targeted setup terminal status differs"
        ) from None
    capture_sha256 = document["capture_sha256"]
    if (
        document["retry_allowed"] is not False
        or document["trial_claim_sha256"] != trial.trial_claim_sha256
        or (status is RedLivingDexTargetedSetupStatus.COMPLETE)
        != isinstance(capture_sha256, str)
        or (
            isinstance(capture_sha256, str)
            and (
                len(capture_sha256) != 64
                or any(c not in "0123456789abcdef" for c in capture_sha256)
            )
        )
    ):
        raise RedLivingDexTargetedTrainRunnerError(
            "targeted setup terminal differs"
        )
    if schema == "pokemon.red.private-living-dex-targeted-setup-terminal.v2":
        failure_phase = document["failure_phase"]
        failure_class = document["failure_class"]
        if (
            (status is RedLivingDexTargetedSetupStatus.COMPLETE)
            != (failure_phase is None and failure_class is None)
            or (
                failure_phase is not None
                and failure_phase not in _TARGETED_SETUP_FAILURE_PHASES
            )
            or (
                failure_class is not None
                and failure_class not in _TARGETED_SETUP_FAILURE_CLASSES
            )
            or any(
                not _is_nonnegative_int(document[name])
                for name in (
                    "setup_controller_actions",
                    "setup_emulator_frames",
                )
            )
        ):
            raise RedLivingDexTargetedTrainRunnerError(
                "targeted setup terminal diagnostics differ"
            )
    return document


def _is_nonnegative_int(value: object) -> bool:
    return type(value) is int and value >= 0  # type: ignore[operator]


def _optional_failure_phase(document: Mapping[str, object]) -> str | None:
    value = document.get("failure_phase")
    if value is None:
        return None
    if not isinstance(value, str) or value not in _TARGETED_SETUP_FAILURE_PHASES:
        raise RedLivingDexTargetedTrainRunnerError(
            "targeted setup failure phase differs"
        )
    return value


def _optional_failure_class(document: Mapping[str, object]) -> str | None:
    value = document.get("failure_class")
    if value is None:
        return None
    if not isinstance(value, str) or value not in _TARGETED_SETUP_FAILURE_CLASSES:
        raise RedLivingDexTargetedTrainRunnerError(
            "targeted setup failure class differs"
        )
    return value


def _setup_failure_class(error: BaseException) -> str:
    if not isinstance(error, Exception):
        return "process_interruption"
    if isinstance(error, RedLivingDexSetupRecipeError):
        return "setup_recipe_error"
    if isinstance(error, RedLivingDexProductionRuntimeError):
        return "production_runtime_error"
    if isinstance(error, RedLivingDexTargetedTrainRunnerError):
        return "targeted_runner_error"
    return "unexpected_error"


def _require_resolved(
    resolved: RedLivingDexResolvedSetupSlot,
    frozen: _FrozenTargetedRecipe,
    setup_execution_identity: RedLivingDexSetupExecutionIdentity,
) -> None:
    if not isinstance(resolved, RedLivingDexResolvedSetupSlot):
        raise TypeError("targeted resolver returned another slot type")
    resolved.__post_init__()
    frozen.require_resolved_recipe(resolved.recipe)
    if resolved.producer_execution_identity != setup_execution_identity:
        raise RedLivingDexTargetedTrainRunnerError(
            "targeted resolved setup identity differs"
        )


def _require_capture_join(
    assignment: RedLivingDexTargetedTrainAssignment,
    capture: RedLivingDexValidatedSetupCapture,
    setup_execution_identity: RedLivingDexSetupExecutionIdentity,
) -> None:
    capture.__post_init__()
    if (
        capture.recipe_sha256 != assignment.capability.recipe.recipe_sha256
        or capture.binding.slot_sha256 != assignment.capability.slot.slot_sha256
        or capture.execution_identity_sha256
        != setup_execution_identity.identity_sha256
    ):
        raise RedLivingDexTargetedTrainRunnerError(
            "targeted setup capture joined another assignment"
        )


__all__ = [
    "RED_LIVING_DEX_TARGETED_TRAIN_RUNNER_SCHEMA",
    "RED_LIVING_DEX_TARGETED_TRAIN_RUNNER_SHA256",
    "RedLivingDexTargetedSetupStatus",
    "RedLivingDexTargetedTrainAssignment",
    "RedLivingDexTargetedTrainReceipt",
    "RedLivingDexTargetedTrainRunnerError",
    "run_red_living_dex_targeted_train_assignment",
]
