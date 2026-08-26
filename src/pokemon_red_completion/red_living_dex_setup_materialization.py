"""Action-free freeze boundary for authentic Red setup bindings.

The durable setup campaign accepts a complete private binding plan, but it must
not decide where those bindings came from.  This module owns the preceding
boundary: ask one authenticated private source for every canonical Red slot,
prove that the shared protected-effect meter never moved, validate the complete
15-slot/45-arm plan, and seal that exact private document before returning.

It owns no ROM opener, emulator, controller, route planner, teacher, behavior
draw, learner target, outcome observer, model, or setup executor.  A later
private Red adapter must implement the source protocol.  Synthetic ROM-free
tests qualify this boundary but never count as authentic binding evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexProspectiveCaptureSlot,
)
from pokemon_red_completion.private_artifacts import (
    PrivateArtifactError,
    PrivateArtifactRoot,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_capture_plan import (
    build_red_living_dex_prospective_capture_plan,
)
from pokemon_red_completion.red_living_dex_setup_campaign import (
    RedLivingDexSetupBindingPlan,
    RedLivingDexSetupSlotBinding,
    build_red_living_dex_setup_binding_plan,
)

RED_LIVING_DEX_SETUP_SOURCE_ATTESTATION_SCHEMA = (
    "pokemon.red.private-living-dex-setup-source-attestation.v1"
)
RED_LIVING_DEX_SETUP_MATERIALIZATION_SCHEMA = (
    "pokemon.red.private-living-dex-setup-binding-materialization.v1"
)
RED_LIVING_DEX_SETUP_MATERIALIZATION_PUBLIC_SCHEMA = (
    "pokemon.red.living-dex-setup-binding-materialization.v1"
)
RED_LIVING_DEX_SETUP_MATERIALIZATION_RECORD_ID = "red-living-dex-setup-binding-materialization-v1"
RED_LIVING_DEX_SETUP_MATERIALIZATION_RECORD_KIND = "red_living_dex_setup_binding_materialization"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_CONTRACT_ID = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{2,255}\Z")


class RedLivingDexSetupMaterializationError(RuntimeError):
    """An action-free source, effect boundary, plan, or seal is invalid."""


@dataclass(frozen=True, slots=True)
class RedLivingDexSetupMaterializationCheckpoint:
    """Independent protected-effect census shared with the private adapter."""

    controller_authority_attempts: int = 0
    controller_actions: int = 0
    emulator_frames: int = 0
    behavior_draws: int = 0
    learner_labels: int = 0
    learner_outcomes: int = 0
    model_predictions: int = 0
    model_fits: int = 0
    root_claims: int = 0
    teacher_queries: int = 0

    def __post_init__(self) -> None:
        for value in self.private_dict().values():
            if type(value) is not int or value < 0:  # noqa: E721
                raise RedLivingDexSetupMaterializationError(
                    "setup materialization effect checkpoint differs"
                )

    def private_dict(self) -> dict[str, int]:
        return {
            "behavior_draws": self.behavior_draws,
            "controller_actions": self.controller_actions,
            "controller_authority_attempts": self.controller_authority_attempts,
            "emulator_frames": self.emulator_frames,
            "learner_labels": self.learner_labels,
            "learner_outcomes": self.learner_outcomes,
            "model_fits": self.model_fits,
            "model_predictions": self.model_predictions,
            "root_claims": self.root_claims,
            "teacher_queries": self.teacher_queries,
        }


@runtime_checkable
class RedLivingDexSetupMaterializationMeter(Protocol):
    """Monotonic protected-effect meter owned outside the private source."""

    def checkpoint(self) -> RedLivingDexSetupMaterializationCheckpoint: ...


@dataclass(frozen=True, slots=True)
class RedLivingDexSetupPrivateSourceAttestation:
    """Private provenance for one complete, approved input catalog."""

    source_manifest_sha256: str
    source_adapter_contract_id: str
    authenticated_input_count: int
    protected_input_set_sha256: str
    private_inputs_authenticated: bool = field(default=True, init=False)
    protected_inputs_unchanged: bool = field(default=True, init=False)
    synthetic_inputs: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        _require_sha256(self.source_manifest_sha256, "setup materialization source manifest")
        _require_sha256(self.protected_input_set_sha256, "setup protected input set")
        if (
            not isinstance(self.source_adapter_contract_id, str)
            or _CONTRACT_ID.fullmatch(self.source_adapter_contract_id) is None
        ):
            raise RedLivingDexSetupMaterializationError("setup source adapter contract differs")
        if type(self.authenticated_input_count) is not int or self.authenticated_input_count < 1:
            raise RedLivingDexSetupMaterializationError(
                "setup source authenticated input count differs"
            )
        if not (
            self.private_inputs_authenticated
            and self.protected_inputs_unchanged
            and not self.synthetic_inputs
        ):
            raise RedLivingDexSetupMaterializationError(
                "setup source does not attest authentic unchanged private inputs"
            )

    @property
    def attestation_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    def private_dict(self) -> dict[str, object]:
        return {
            "authenticated_input_count": self.authenticated_input_count,
            "private_inputs_authenticated": self.private_inputs_authenticated,
            "protected_input_set_sha256": self.protected_input_set_sha256,
            "protected_inputs_unchanged": self.protected_inputs_unchanged,
            "schema": RED_LIVING_DEX_SETUP_SOURCE_ATTESTATION_SCHEMA,
            "source_adapter_contract_id": self.source_adapter_contract_id,
            "source_manifest_sha256": self.source_manifest_sha256,
            "synthetic_inputs": self.synthetic_inputs,
        }


@runtime_checkable
class RedLivingDexSetupPrivateBindingSource(Protocol):
    """Private Red adapter that derives one binding without protected effects."""

    @property
    def effects_meter(self) -> RedLivingDexSetupMaterializationMeter: ...

    def attest_source(self) -> RedLivingDexSetupPrivateSourceAttestation: ...

    def materialize_slot(
        self,
        slot: LivingDexProspectiveCaptureSlot,
    ) -> RedLivingDexSetupSlotBinding: ...


@dataclass(frozen=True, slots=True)
class RedLivingDexSetupBindingMaterialization:
    """One sealed private 15-slot binding plan with zero protected effects."""

    plan: RedLivingDexSetupBindingPlan
    source_attestation: RedLivingDexSetupPrivateSourceAttestation
    effects_before: RedLivingDexSetupMaterializationCheckpoint
    effects_after: RedLivingDexSetupMaterializationCheckpoint

    def __post_init__(self) -> None:
        if not isinstance(self.plan, RedLivingDexSetupBindingPlan):
            raise TypeError("setup materialization needs its binding plan")
        self.plan.__post_init__()
        if not isinstance(
            self.source_attestation,
            RedLivingDexSetupPrivateSourceAttestation,
        ):
            raise TypeError("setup materialization needs its source attestation")
        self.source_attestation.__post_init__()
        for checkpoint in (self.effects_before, self.effects_after):
            if not isinstance(checkpoint, RedLivingDexSetupMaterializationCheckpoint):
                raise TypeError("setup materialization needs protected-effect checkpoints")
            checkpoint.__post_init__()
        if self.effects_after != self.effects_before:
            raise RedLivingDexSetupMaterializationError(
                "setup binding materialization changed a protected effect"
            )

    @property
    def materialization_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    def private_dict(self) -> dict[str, object]:
        return {
            "actionful_setup_execution_authorized": False,
            "binding_plan": self.plan.private_dict(),
            "binding_plan_sha256": self.plan.plan_sha256,
            "effects_after": self.effects_after.private_dict(),
            "effects_before": self.effects_before.private_dict(),
            "learner_effects": 0,
            "schema": RED_LIVING_DEX_SETUP_MATERIALIZATION_SCHEMA,
            "source_attestation": self.source_attestation.private_dict(),
            "source_attestation_sha256": self.source_attestation.attestation_sha256,
        }

    def public_dict(self) -> dict[str, object]:
        plan = self.plan.public_dict()
        return {
            "actionful_setup_execution_authorized": False,
            "all_slots_bound": plan["all_slots_bound"],
            "behavior_draws": 0,
            "complete_menus_bound": plan["complete_menus_bound"],
            "controller_actions": 0,
            "controller_authority_attempts": 0,
            "development_slots": plan["development_slots"],
            "emulator_frames": 0,
            "learner_labels": 0,
            "learner_outcomes": 0,
            "local_slots": plan["local_slots"],
            "model_fits": 0,
            "model_predictions": 0,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "provider_contracts_bound": plan["provider_contracts_bound"],
            "root_claims": 0,
            "routed_slots": plan["routed_slots"],
            "runtime_private_bindings_authenticated": True,
            "runtime_private_routes_executed": False,
            "schema": RED_LIVING_DEX_SETUP_MATERIALIZATION_PUBLIC_SCHEMA,
            "slot_count": plan["slot_count"],
            "source_inputs_authenticated": True,
            "teacher_queries": 0,
            "train_slots": plan["train_slots"],
        }


def materialize_red_living_dex_setup_bindings(
    store: PrivateArtifactRoot,
    *,
    source: RedLivingDexSetupPrivateBindingSource,
    effects_meter: RedLivingDexSetupMaterializationMeter,
) -> RedLivingDexSetupBindingMaterialization:
    """Freeze and seal one complete private plan without touching gameplay."""

    if not isinstance(store, PrivateArtifactRoot):
        raise TypeError("setup materialization needs a validated private artifact root")
    if not isinstance(effects_meter, RedLivingDexSetupMaterializationMeter):
        raise TypeError("setup materialization needs a protected-effect meter")
    # Establish the independent baseline before inspecting the private source.
    # Runtime protocol checks and property access can execute user-supplied
    # adapter code; neither is allowed to disappear before the first census.
    before = _checkpoint(effects_meter)
    try:
        valid_source = isinstance(source, RedLivingDexSetupPrivateBindingSource)
    except Exception:
        _require_unchanged(effects_meter, before)
        raise RedLivingDexSetupMaterializationError(
            "setup materialization private source inspection failed"
        ) from None
    if not valid_source:
        raise TypeError("setup materialization needs a private binding source")
    _require_unchanged(effects_meter, before)
    try:
        source_effects_meter = source.effects_meter
    except Exception:
        _require_unchanged(effects_meter, before)
        raise RedLivingDexSetupMaterializationError(
            "setup materialization private source inspection failed"
        ) from None
    _require_unchanged(effects_meter, before)
    if source_effects_meter is not effects_meter:
        raise RedLivingDexSetupMaterializationError(
            "setup materialization source does not share the protected-effect meter"
        )

    try:
        attestation = source.attest_source()
    except Exception:
        raise RedLivingDexSetupMaterializationError(
            "setup materialization source attestation failed"
        ) from None
    _require_unchanged(effects_meter, before)
    if not isinstance(attestation, RedLivingDexSetupPrivateSourceAttestation):
        raise RedLivingDexSetupMaterializationError(
            "setup materialization source attestation differs"
        )
    attestation.__post_init__()

    prospective = build_red_living_dex_prospective_capture_plan()
    bindings: list[RedLivingDexSetupSlotBinding] = []
    for slot in prospective.slots:
        try:
            binding = source.materialize_slot(slot)
        except Exception:
            raise RedLivingDexSetupMaterializationError(
                "setup materialization private slot source failed"
            ) from None
        _require_unchanged(effects_meter, before)
        if not isinstance(binding, RedLivingDexSetupSlotBinding):
            raise RedLivingDexSetupMaterializationError(
                "setup materialization source returned an invalid slot binding"
            )
        binding.__post_init__()
        bindings.append(binding)

    try:
        final_attestation = source.attest_source()
    except Exception:
        raise RedLivingDexSetupMaterializationError(
            "setup materialization final source attestation failed"
        ) from None
    _require_unchanged(effects_meter, before)
    if (
        not isinstance(final_attestation, RedLivingDexSetupPrivateSourceAttestation)
        or final_attestation != attestation
    ):
        raise RedLivingDexSetupMaterializationError(
            "setup materialization private input set changed during binding"
        )
    final_attestation.__post_init__()

    plan = build_red_living_dex_setup_binding_plan(
        tuple(bindings),
        prospective_plan=prospective,
    )
    _require_unchanged(effects_meter, before)
    after = _checkpoint(effects_meter)
    materialization = RedLivingDexSetupBindingMaterialization(
        plan,
        attestation,
        before,
        after,
    )
    record = materialization.private_dict()
    try:
        sealed = store.publish_sealed_record(
            RED_LIVING_DEX_SETUP_MATERIALIZATION_RECORD_ID,
            kind=RED_LIVING_DEX_SETUP_MATERIALIZATION_RECORD_KIND,
            record=record,
        )
        if sealed.read() != record:
            raise RedLivingDexSetupMaterializationError(
                "setup binding materialization seal failed verification"
            )
    except RedLivingDexSetupMaterializationError:
        raise
    except PrivateArtifactError as error:
        if "already exists with different content" in str(error):
            raise RedLivingDexSetupMaterializationError(
                "setup materialization sealed plan already exists with different content"
            ) from None
        raise RedLivingDexSetupMaterializationError(
            "setup materialization private plan seal failed"
        ) from None
    _require_unchanged(effects_meter, before)
    return materialization


def _checkpoint(
    meter: RedLivingDexSetupMaterializationMeter,
) -> RedLivingDexSetupMaterializationCheckpoint:
    value = meter.checkpoint()
    if not isinstance(value, RedLivingDexSetupMaterializationCheckpoint):
        raise RedLivingDexSetupMaterializationError(
            "setup materialization meter returned an invalid checkpoint"
        )
    value.__post_init__()
    return value


def _require_unchanged(
    meter: RedLivingDexSetupMaterializationMeter,
    expected: RedLivingDexSetupMaterializationCheckpoint,
) -> None:
    if _checkpoint(meter) != expected:
        raise RedLivingDexSetupMaterializationError(
            "setup binding materialization changed a protected effect"
        )


def _require_sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedLivingDexSetupMaterializationError(f"{subject} differs")
    return value


__all__ = [
    "RED_LIVING_DEX_SETUP_MATERIALIZATION_PUBLIC_SCHEMA",
    "RED_LIVING_DEX_SETUP_MATERIALIZATION_RECORD_ID",
    "RedLivingDexSetupBindingMaterialization",
    "RedLivingDexSetupMaterializationCheckpoint",
    "RedLivingDexSetupMaterializationError",
    "RedLivingDexSetupMaterializationMeter",
    "RedLivingDexSetupPrivateBindingSource",
    "RedLivingDexSetupPrivateSourceAttestation",
    "materialize_red_living_dex_setup_bindings",
]
