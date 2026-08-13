from __future__ import annotations

import runpy
from pathlib import Path

import pytest

from pokemon_red_completion.strategic_navigation_sealed_adapter import (
    StrategicSealedAdapterError,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = runpy.run_path(str(PROJECT_ROOT / "scripts" / "qualify_strategic_sealed_adapter.py"))
parser = SCRIPT["_parser"]
validated_output = SCRIPT["_validated_new_private_output_path"]
write_output = SCRIPT["_write_new_private_output"]


def test_qualification_command_requires_both_evidence_outputs() -> None:
    with pytest.raises(SystemExit):
        parser().parse_args(
            [
                "--scenario-id",
                "learning-scenario",
                "--challenged-objective-id",
                "alternate-objective",
                "--state",
                "/private/non-test.state",
                "--receipt-id",
                "qualification-receipt",
                "--issued-by",
                "qualification-runner",
                "--issued-on",
                "2026-08-13",
            ]
        )


def test_qualification_outputs_are_new_external_files(tmp_path: Path) -> None:
    output = validated_output(tmp_path / "qualification.json")

    write_output(output, b"evidence\n")

    assert output.read_bytes() == b"evidence\n"
    with pytest.raises(StrategicSealedAdapterError, match="already exists"):
        validated_output(output)
    with pytest.raises(StrategicSealedAdapterError, match="outside the repository"):
        validated_output(PROJECT_ROOT / "qualification-must-not-be-written.json")
