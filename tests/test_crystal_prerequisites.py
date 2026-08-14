from __future__ import annotations

import json
import os
import subprocess
import sys
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
        (PROJECT_ROOT / "configs" / "crystal-goal-manager-transfer-v2.json").read_bytes()
    )


def _fingerprint(**changes: object) -> RomFingerprint:
    values: dict[str, object] = {
        "filename": "private-owner-copy.gbc",
        "title": "PM_CRYSTAL",
        "size_bytes": 2_097_152,
        "sha1": "f2f52230b536214ef7c9924f483392993e226cfb",
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
    assert supported.sha1 == "f2f52230b536214ef7c9924f483392993e226cfb"
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


def test_entry_gate_cli_rejects_a_wrong_rom_without_a_traceback_or_private_path(
    tmp_path: Path,
) -> None:
    wrong_rom = tmp_path / "owner-copy.gbc"
    wrong_rom.write_bytes(bytes(0x150))
    environment = os.environ.copy()
    environment["POKEMON_CRYSTAL_ROM"] = str(wrong_rom)
    environment["PYTHONPATH"] = str(PROJECT_ROOT / "src")

    completed = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "check_crystal_transfer_entry_gate.py")],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 2
    assert completed.stderr == ""
    assert "Traceback" not in completed.stdout
    assert str(wrong_rom) not in completed.stdout
    document = json.loads(completed.stdout)
    assert document["status"] == "blocked"
    assert document["teacher_executed"] is False
    assert document["context_opened"] is False
    assert document["prediction_computed"] is False
    assert document["private_path_fields"] == 0
