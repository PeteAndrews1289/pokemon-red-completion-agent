from __future__ import annotations

import json
from pathlib import Path

import pytest

from pokemon_crystal_completion.prerequisites import (
    CrystalPrerequisiteError,
    assess_crystal_transfer_prerequisites,
    supported_rom_from_crystal_audit,
)
from pokemon_crystal_completion.transfer_protocol import parse_crystal_transfer_plan
from pokemon_red_completion.rom import RomFingerprint

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _plan():  # type: ignore[no-untyped-def]
    return parse_crystal_transfer_plan(
        (PROJECT_ROOT / "configs" / "crystal-goal-manager-transfer-v1.json").read_bytes()
    )


def _fingerprint(**changes: object) -> RomFingerprint:
    values: dict[str, object] = {
        "filename": "private-owner-copy.gbc",
        "title": "PM_CRYSTAL",
        "size_bytes": 2_097_152,
        "sha1": "f4cd194bdee0d04ca4eac29e09b8e4e9d818c133",
        "sha256": "ab" * 32,
    }
    values.update(changes)
    return RomFingerprint(**values)  # type: ignore[arg-type]


def test_missing_rom_is_one_explicit_blocker_and_executes_nothing() -> None:
    audit = assess_crystal_transfer_prerequisites(_plan(), fingerprint=None)
    public = audit.public_dict()

    assert not audit.ready_for_private_context_inventory
    assert audit.remaining_blockers[0] == "matching_owner_rom_not_verified"
    assert public["teacher_executed"] is False
    assert public["context_opened"] is False
    assert public["prediction_computed"] is False
    encoded = json.dumps(public, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_matching_rom_binds_sha256_without_retaining_the_filename() -> None:
    audit = assess_crystal_transfer_prerequisites(_plan(), fingerprint=_fingerprint())
    public = audit.public_dict()

    assert audit.ready_for_private_context_inventory
    assert audit.source_contract.rom_sha256 == "ab" * 32
    assert "matching_owner_rom_not_verified" not in audit.remaining_blockers
    encoded = json.dumps(public, sort_keys=True)
    assert "private-owner-copy" not in encoded
    source_contract = public["source_contract"]
    assert isinstance(source_contract, dict)
    assert "filename" not in source_contract["rom"]  # type: ignore[operator]
    assert public["ready_for_model_training"] is False
    supported = supported_rom_from_crystal_audit(audit)
    assert supported.title == "PM_CRYSTAL"
    assert supported.size_bytes == 2_097_152
    assert supported.sha1 == "f4cd194bdee0d04ca4eac29e09b8e4e9d818c133"
    assert supported.sha256 == "ab" * 32


def test_unverified_audit_cannot_construct_an_emulator_identity() -> None:
    audit = assess_crystal_transfer_prerequisites(_plan(), fingerprint=None)
    with pytest.raises(CrystalPrerequisiteError, match="not fully verified"):
        supported_rom_from_crystal_audit(audit)


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        ({"title": "WRONG"}, "header title"),
        ({"size_bytes": 1}, "byte size"),
        ({"sha1": "0" * 40}, "SHA-1"),
        ({"sha256": "A" * 64}, "SHA-256 format"),
    ),
)
def test_entry_gate_rejects_every_revision_mismatch(
    changes: dict[str, object], message: str
) -> None:
    with pytest.raises(CrystalPrerequisiteError, match=message):
        assess_crystal_transfer_prerequisites(_plan(), fingerprint=_fingerprint(**changes))
