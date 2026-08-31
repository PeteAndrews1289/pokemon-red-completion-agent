"""Authenticate a complete private Red powered-lineage supply tranche.

Admission is action-free.  It reconciles interrupted private episode
namespaces, authenticates each successful root against its immutable plan,
durable assignment claim, retained state/envelope bytes, and partition, and
retains every failed or interrupted attempt in the fixed denominator.  It
does not open a ROM, restore a state into an emulator, claim a root, collect
an outcome, score a model, or authorize population scale.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from pokemon_red_completion.captured_progress import (
    CapturedProgressEnvelope,
    parse_captured_progress,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    fixed_account_claim_registry_lease,
    root_claim_is_available,
)
from pokemon_red_completion.private_artifacts import (
    PrivateArtifactError,
    PrivateArtifactRoot,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_fresh_episode_runtime import (
    RED_LIVING_DEX_POWERED_SUPPLY_ASSIGNMENT_CLAIM_SCHEMA,
    RedLivingDexFreshEpisodeRuntimeError,
    decode_red_living_dex_powered_supply_private_root,
    read_red_living_dex_powered_supply_assignment_claim,
    red_living_dex_assignment_claim_exists,
)
from pokemon_red_completion.red_living_dex_powered_lineage_supply import (
    RedLivingDexPoweredSupplyAdmission,
    RedLivingDexPoweredSupplyAssignment,
    RedLivingDexPoweredSupplyFailure,
    RedLivingDexPoweredSupplyPlan,
    RedLivingDexPoweredSupplyReceipt,
    admit_red_living_dex_powered_supply_tranche,
    compose_red_living_dex_powered_supply_runtime_execution_sha256,
    powered_supply_collection_id,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexAuthenticatedSetupRoot,
)

RED_LIVING_DEX_POWERED_SUPPLY_PRIVATE_ADMISSION_SCHEMA = (
    "pokemon.red.private-living-dex-powered-lineage-supply-admission.v1"
)
RED_LIVING_DEX_POWERED_SUPPLY_ADMISSION_RECORD_KIND = (
    "red_living_dex_powered_lineage_supply_admission"
)


class RedLivingDexPoweredSupplyAdmissionError(RuntimeError):
    """The private tranche cannot be admitted without weakening its contract."""


@dataclass(frozen=True, slots=True)
class RedLivingDexPoweredAdmittedRoot:
    """One authenticated root ready for an action-free capacity recensus."""

    root: RedLivingDexAuthenticatedSetupRoot = field(repr=False)
    envelope: CapturedProgressEnvelope
    receipt: RedLivingDexPoweredSupplyReceipt
    artifact_manifest_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.root, RedLivingDexAuthenticatedSetupRoot):
            raise TypeError("powered supply admitted root differs")
        if not isinstance(self.envelope, CapturedProgressEnvelope):
            raise TypeError("powered supply admitted envelope differs")
        if not isinstance(self.receipt, RedLivingDexPoweredSupplyReceipt):
            raise TypeError("powered supply admitted receipt differs")
        self.receipt.__post_init__()
        if (
            self.root.state_sha256 != self.receipt.terminal_state_sha256
            or self.root.envelope_sha256
            != self.receipt.terminal_envelope_sha256
            or self.root.root_consumption_sha256
            != self.receipt.root_consumption_sha256
            or self.root.physical_root_sha256
            != self.receipt.physical_root_sha256
            or self.envelope.state_sha256 != self.root.state_sha256
            or self.envelope.checkpoint_id
            != self.receipt.terminal_checkpoint_id
        ):
            raise RedLivingDexPoweredSupplyAdmissionError(
                "powered supply admitted root bytes differ from its receipt"
            )
        _require_sha256(
            self.artifact_manifest_sha256,
            "powered supply episode manifest",
        )

    def private_dict(self) -> dict[str, object]:
        return {
            "artifact_manifest_sha256": self.artifact_manifest_sha256,
            "receipt": self.receipt.public_dict(),
            "schema": "pokemon.red.private-powered-supply-admitted-root.v1",
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexPoweredSupplyPrivateAdmission:
    """The complete authenticated denominator and its capacity-census roots."""

    plan_sha256: str
    admission: RedLivingDexPoweredSupplyAdmission
    roots: tuple[RedLivingDexPoweredAdmittedRoot, ...]
    failures: tuple[RedLivingDexPoweredSupplyFailure, ...]
    recovered_episode_namespaces: int

    def __post_init__(self) -> None:
        _require_sha256(self.plan_sha256, "powered supply admission plan")
        if not isinstance(self.admission, RedLivingDexPoweredSupplyAdmission):
            raise TypeError("powered supply private admission decision differs")
        self.admission.__post_init__()
        if self.admission.plan_sha256 != self.plan_sha256:
            raise RedLivingDexPoweredSupplyAdmissionError(
                "powered supply private admission plan differs"
            )
        if not isinstance(self.roots, tuple) or any(
            not isinstance(item, RedLivingDexPoweredAdmittedRoot)
            for item in self.roots
        ):
            raise TypeError("powered supply private admission roots differ")
        if not isinstance(self.failures, tuple) or any(
            not isinstance(item, RedLivingDexPoweredSupplyFailure)
            for item in self.failures
        ):
            raise TypeError("powered supply private admission failures differ")
        for root in self.roots:
            root.__post_init__()
        for failure in self.failures:
            failure.__post_init__()
        if (
            len(self.roots) != self.admission.roots_admitted
            or len(self.failures) != self.admission.attempts_failed
            or type(self.recovered_episode_namespaces) is not int  # noqa: E721
            or not 0
            <= self.recovered_episode_namespaces
            <= self.admission.roots_admitted + self.admission.attempts_failed
        ):
            raise RedLivingDexPoweredSupplyAdmissionError(
                "powered supply private admission counts differ"
            )

    @property
    def record_id(self) -> str:
        return f"pwr-admit-{self.plan_sha256}"

    def private_dict(self) -> dict[str, object]:
        return {
            "admission": self.admission.public_dict(),
            "failures": [item.public_dict() for item in self.failures],
            "plan_sha256": self.plan_sha256,
            "roots": [item.private_dict() for item in self.roots],
            "schema": RED_LIVING_DEX_POWERED_SUPPLY_PRIVATE_ADMISSION_SCHEMA,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            **self.admission.public_dict(),
            "authenticated_failure_dispositions": len(self.failures),
            "authenticated_success_roots": len(self.roots),
            "controller_actions": 0,
            "emulator_frames": 0,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "recovered_episode_namespaces": self.recovered_episode_namespaces,
            "root_claims": 0,
            "root_state_restores": 0,
            "status": (
                "bounded_yield_qualification_passed_pending_recensus"
                if self.admission.qualification_passed
                else "bounded_yield_qualification_failed_population_closed"
            ),
        }


def authenticate_red_living_dex_powered_supply_private_tranche(
    plan: RedLivingDexPoweredSupplyPlan,
    *,
    private_store: PrivateArtifactRoot,
    claim_registry: Path,
    recover_interrupted: bool,
) -> RedLivingDexPoweredSupplyPrivateAdmission:
    """Authenticate all twelve dispositions without opening or running Red."""

    if not isinstance(plan, RedLivingDexPoweredSupplyPlan):
        raise TypeError("powered supply private admission needs its plan")
    plan.__post_init__()
    if not isinstance(private_store, PrivateArtifactRoot):
        raise TypeError("powered supply private admission needs its store")
    if not isinstance(claim_registry, Path):
        raise TypeError("powered supply private admission needs its claim registry")
    if type(recover_interrupted) is not bool:  # noqa: E721
        raise TypeError("powered supply recovery choice must be a bool")

    roots: list[RedLivingDexPoweredAdmittedRoot] = []
    failures: list[RedLivingDexPoweredSupplyFailure] = []
    recovered = 0
    session_id = powered_supply_collection_id(plan.plan_sha256)
    with (
        private_store.collection_session(session_id) as session,
        fixed_account_claim_registry_lease(claim_registry, exclusive=False),
    ):
        for assignment in plan.assignments:
            state = session.inspect_episode(assignment.episode_id)
            if state.status == "partial" and recover_interrupted:
                state = session.recover_interrupted_episode(
                    assignment.episode_id
                )
                recovered += 1
            if state.status == "complete":
                roots.append(
                    _authenticate_complete_episode(
                        plan,
                        assignment,
                        private_store=private_store,
                        claim_registry=claim_registry,
                    )
                )
                continue
            if state.status in {"failed", "interrupted"}:
                failures.append(
                    _terminal_failure(
                        plan,
                        assignment,
                        claim_registry=claim_registry,
                        status=state.status,
                    )
                )
                continue
            raise RedLivingDexPoweredSupplyAdmissionError(
                "powered supply disposition denominator is incomplete"
            )
    receipts = tuple(item.receipt for item in roots)
    failure_tuple = tuple(failures)
    admission = admit_red_living_dex_powered_supply_tranche(
        plan,
        receipts,
        failure_tuple,
    )
    return RedLivingDexPoweredSupplyPrivateAdmission(
        plan_sha256=plan.plan_sha256,
        admission=admission,
        roots=tuple(roots),
        failures=failure_tuple,
        recovered_episode_namespaces=recovered,
    )


def _authenticate_complete_episode(
    plan: RedLivingDexPoweredSupplyPlan,
    assignment: RedLivingDexPoweredSupplyAssignment,
    *,
    private_store: PrivateArtifactRoot,
    claim_registry: Path,
) -> RedLivingDexPoweredAdmittedRoot:
    try:
        episode = private_store.open_episode(assignment.episode_id)
        if set(episode.stream_names) != {
            "assignment",
            "checkpoint",
            "claim",
            "root",
        }:
            raise RedLivingDexPoweredSupplyAdmissionError(
                "powered supply complete episode streams differ"
            )
        assignment_record = _read_one(episode.iter_stream("assignment", max_records=1))
        claim_record = _read_one(episode.iter_stream("claim", max_records=1))
        checkpoint_record = _read_one(
            episode.iter_stream("checkpoint", max_records=1)
        )
        root_record = _read_one(episode.iter_stream("root", max_records=1))
        if assignment_record != assignment.public_dict():
            raise RedLivingDexPoweredSupplyAdmissionError(
                "powered supply retained assignment differs"
            )
        registry_claim = _read_claim(
            plan,
            assignment,
            claim_registry=claim_registry,
            required=True,
        )
        if claim_record != registry_claim:
            raise RedLivingDexPoweredSupplyAdmissionError(
                "powered supply retained claim differs"
            )
        root, receipt = decode_red_living_dex_powered_supply_private_root(
            root_record
        )
        if receipt.assignment_claim_sha256 != canonical_sha256(registry_claim):
            raise RedLivingDexPoweredSupplyAdmissionError(
                "powered supply receipt claim differs"
            )
        envelope = parse_captured_progress(
            root.envelope_bytes,
            state_bytes=root.state_bytes,
        )
        _authenticate_checkpoint(checkpoint_record, envelope)
        if not all(
            root_claim_is_available(claim_registry, digest)
            for digest in (
                root.root_consumption_sha256,
                root.physical_root_sha256,
            )
        ):
            raise RedLivingDexPoweredSupplyAdmissionError(
                "powered supply root was consumed before admission"
            )
        return RedLivingDexPoweredAdmittedRoot(
            root=root,
            envelope=envelope,
            receipt=receipt,
            artifact_manifest_sha256=episode.manifest_sha256,
        )
    except RedLivingDexPoweredSupplyAdmissionError:
        raise
    except (PrivateArtifactError, RedLivingDexFreshEpisodeRuntimeError, TypeError, ValueError):
        raise RedLivingDexPoweredSupplyAdmissionError(
            "powered supply complete episode authentication failed"
        ) from None


def _terminal_failure(
    plan: RedLivingDexPoweredSupplyPlan,
    assignment: RedLivingDexPoweredSupplyAssignment,
    *,
    claim_registry: Path,
    status: str,
) -> RedLivingDexPoweredSupplyFailure:
    claim = _read_claim(
        plan,
        assignment,
        claim_registry=claim_registry,
        required=False,
    )
    return RedLivingDexPoweredSupplyFailure(
        assignment_id=assignment.assignment_id,
        plan_sha256=plan.plan_sha256,
        role=assignment.role,
        partition=assignment.partition,
        source_bundle_sha256=assignment.source_bundle_sha256,
        teacher_execution_sha256=assignment.teacher_execution_sha256,
        generator_execution_sha256=assignment.generator_execution_sha256,
        assignment_claim_sha256=(
            canonical_sha256(claim) if claim is not None else None
        ),
        failure_stage=f"private_episode_{status}",
        effects_known=False,
        controller_actions=None,
        emulator_frames=None,
    )


def _read_claim(
    plan: RedLivingDexPoweredSupplyPlan,
    assignment: RedLivingDexPoweredSupplyAssignment,
    *,
    claim_registry: Path,
    required: bool,
) -> Mapping[str, object] | None:
    try:
        if not red_living_dex_assignment_claim_exists(
            claim_registry,
            assignment.assignment_id,
        ):
            if required:
                raise RedLivingDexPoweredSupplyAdmissionError(
                    "powered supply assignment claim is absent"
                )
            return None
        claim = read_red_living_dex_powered_supply_assignment_claim(
            claim_registry,
            assignment.assignment_id,
        )
    except RedLivingDexFreshEpisodeRuntimeError:
        raise RedLivingDexPoweredSupplyAdmissionError(
            "powered supply assignment claim cannot be authenticated"
        ) from None
    expected_execution = (
        compose_red_living_dex_powered_supply_runtime_execution_sha256(
            assignment_id=assignment.assignment_id,
            plan_sha256=plan.plan_sha256,
            source_commit=plan.source_commit,
            generator_execution_sha256=plan.generator_execution_sha256,
            generator_runner_sha256=plan.generator_runner_sha256,
            runtime_identity_sha256=plan.runtime_identity_sha256,
        )
    )
    if (
        claim.get("schema")
        != RED_LIVING_DEX_POWERED_SUPPLY_ASSIGNMENT_CLAIM_SCHEMA
        or claim.get("assignment_id") != assignment.assignment_id
        or claim.get("plan_sha256") != plan.plan_sha256
        or claim.get("source_commit") != plan.source_commit
        or claim.get("runner_sha256") != plan.generator_runner_sha256
        or claim.get("runtime_identity_sha256") != plan.runtime_identity_sha256
        or claim.get("execution_identity_sha256") != expected_execution
    ):
        raise RedLivingDexPoweredSupplyAdmissionError(
            "powered supply assignment claim differs"
        )
    return claim


def _authenticate_checkpoint(
    value: Mapping[str, object],
    envelope: CapturedProgressEnvelope,
) -> None:
    if set(value) != {
        "checkpoint_id",
        "checkpoint_label",
        "checkpoints_completed",
        "checkpoints_total",
        "schema",
        "verified_objective_ids",
    } or value != {
        "checkpoint_id": envelope.checkpoint_id,
        "checkpoint_label": envelope.checkpoint_label,
        "checkpoints_completed": envelope.checkpoints_completed,
        "checkpoints_total": envelope.checkpoints_total,
        "schema": "pokemon.red.private-living-dex-fresh-checkpoint.v1",
        "verified_objective_ids": list(envelope.verified_objective_ids),
    }:
        raise RedLivingDexPoweredSupplyAdmissionError(
            "powered supply retained checkpoint differs"
        )


def _read_one(records: Iterable[dict[str, object]]) -> dict[str, object]:
    try:
        values = tuple(records)
    except (TypeError, PrivateArtifactError):
        raise RedLivingDexPoweredSupplyAdmissionError(
            "powered supply private stream differs"
        ) from None
    if len(values) != 1 or not isinstance(values[0], dict):
        raise RedLivingDexPoweredSupplyAdmissionError(
            "powered supply private stream differs"
        )
    return values[0]


def _require_sha256(value: object, subject: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise RedLivingDexPoweredSupplyAdmissionError(f"{subject} differs")
    return value


__all__ = [
    "RED_LIVING_DEX_POWERED_SUPPLY_ADMISSION_RECORD_KIND",
    "RED_LIVING_DEX_POWERED_SUPPLY_PRIVATE_ADMISSION_SCHEMA",
    "RedLivingDexPoweredAdmittedRoot",
    "RedLivingDexPoweredSupplyAdmissionError",
    "RedLivingDexPoweredSupplyPrivateAdmission",
    "authenticate_red_living_dex_powered_supply_private_tranche",
]
