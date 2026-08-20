"""Non-executing entry gate for private Crystal transfer work."""

from __future__ import annotations

from dataclasses import dataclass

from pokemon_crystal_completion.source_contract import (
    CRYSTAL_INTERNATIONAL_REV1_SOURCE_CONTRACT,
    CrystalSourceContract,
)
from pokemon_crystal_completion.transfer_protocol import CrystalTransferPlan
from pokemon_red_completion.constants import SupportedRom
from pokemon_red_completion.rom import RomFingerprint


class CrystalPrerequisiteError(ValueError):
    """Raised when an owner-supplied cartridge differs from the pinned revision."""


@dataclass(frozen=True, slots=True)
class CrystalTransferPrerequisiteAudit:
    """Path-free state of the gate immediately before private inventory."""

    plan_sha256: str
    source_contract: CrystalSourceContract
    rom_revision_verified: bool

    @property
    def ready_for_private_context_inventory(self) -> bool:
        return self.rom_revision_verified and self.source_contract.live_identity_complete

    @property
    def remaining_blockers(self) -> tuple[str, ...]:
        blockers: list[str] = []
        if not self.ready_for_private_context_inventory:
            blockers.append("matching_owner_rom_not_verified")
        blockers.extend(
            (
                "live_banked_memory_adapter_not_qualified",
                "crystal_context_catalog_not_frozen",
                "zero_shot_predictions_not_committed",
                "adaptation_examples_not_collected",
                "sealed_test_unopened",
            )
        )
        return tuple(blockers)

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.crystal.transfer-prerequisite-audit.v1",
            "plan_sha256": self.plan_sha256,
            "source_contract": self.source_contract.public_dict(),
            "rom_revision_verified": self.rom_revision_verified,
            "ready_for_private_context_inventory": self.ready_for_private_context_inventory,
            "ready_for_model_training": False,
            "remaining_blockers": list(self.remaining_blockers),
            "teacher_executed": False,
            "context_opened": False,
            "prediction_computed": False,
            "private_path_fields": 0,
        }


def assess_crystal_transfer_prerequisites(
    plan: CrystalTransferPlan,
    *,
    fingerprint: RomFingerprint | None,
) -> CrystalTransferPrerequisiteAudit:
    """Verify public identities only; never boot a ROM or open a context."""

    if not isinstance(plan, CrystalTransferPlan):
        raise TypeError("plan must be CrystalTransferPlan")
    if fingerprint is None:
        return CrystalTransferPrerequisiteAudit(
            plan_sha256=plan.plan_sha256,
            source_contract=CRYSTAL_INTERNATIONAL_REV1_SOURCE_CONTRACT,
            rom_revision_verified=False,
        )
    if not isinstance(fingerprint, RomFingerprint):
        raise TypeError("fingerprint must be RomFingerprint or None")
    expected = CRYSTAL_INTERNATIONAL_REV1_SOURCE_CONTRACT
    mismatches: list[str] = []
    if fingerprint.title != expected.rom_header_title:
        mismatches.append("header title")
    if fingerprint.size_bytes != expected.rom_size_bytes:
        mismatches.append("byte size")
    if fingerprint.sha1 != expected.rom_sha1:
        mismatches.append("SHA-1")
    if (
        len(fingerprint.sha256) != 64
        or any(character not in "0123456789abcdef" for character in fingerprint.sha256)
    ):
        mismatches.append("SHA-256 format")
    if mismatches:
        raise CrystalPrerequisiteError(
            "owner-supplied Crystal revision differs: " + ", ".join(mismatches)
        )
    return CrystalTransferPrerequisiteAudit(
        plan_sha256=plan.plan_sha256,
        source_contract=expected.with_owner_rom_sha256(fingerprint.sha256),
        rom_revision_verified=True,
    )


def supported_rom_from_crystal_audit(
    audit: CrystalTransferPrerequisiteAudit,
) -> SupportedRom:
    """Create PyBoy's exact immutable cartridge identity after entry verification."""

    if not isinstance(audit, CrystalTransferPrerequisiteAudit):
        raise TypeError("audit must be CrystalTransferPrerequisiteAudit")
    if not audit.ready_for_private_context_inventory:
        raise CrystalPrerequisiteError("Crystal ROM identity is not fully verified")
    sha256 = audit.source_contract.rom_sha256
    assert sha256 is not None
    return SupportedRom(
        title=audit.source_contract.rom_header_title,
        size_bytes=audit.source_contract.rom_size_bytes,
        sha1=audit.source_contract.rom_sha1,
        sha256=sha256,
    )


__all__ = [
    "CrystalPrerequisiteError",
    "CrystalTransferPrerequisiteAudit",
    "assess_crystal_transfer_prerequisites",
    "supported_rom_from_crystal_audit",
]
