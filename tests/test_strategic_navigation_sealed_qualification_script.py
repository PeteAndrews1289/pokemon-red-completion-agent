from __future__ import annotations

import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.strategic_navigation_sealed_adapter import (
    StrategicSealedAdapterError,
)
from pokemon_red_completion.strategic_navigation_sealed_cartridge import (
    StrategicSealedNonTestQualificationObservation,
)
from pokemon_red_completion.strategic_navigation_sealed_evaluation import (
    load_strategic_sealed_evaluation_plan,
    parse_strategic_sealed_non_test_qualification_receipt,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = runpy.run_path(str(PROJECT_ROOT / "scripts" / "qualify_strategic_sealed_adapter.py"))
parser = SCRIPT["_parser"]
validated_output = SCRIPT["_validated_new_private_output_path"]
write_output = SCRIPT["_write_new_private_output"]
main = SCRIPT["main"]
SCRIPT_GLOBALS = main.__globals__


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


def test_failed_live_qualification_writes_typed_evidence_and_returns_nonzero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = load_strategic_sealed_evaluation_plan(PROJECT_ROOT)
    source_commit = "a" * 40
    observation = StrategicSealedNonTestQualificationObservation(
        document={
            "result": {
                "sealed_test_cases_opened": 0,
                "status": "failed",
                "teacher_executed": False,
            },
            "schema": "strategic-sealed-non-test-qualification-observation-v2",
        }
    )
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "detect_source_identity",
        lambda root, include_untracked: SimpleNamespace(git_commit=source_commit),
    )
    monkeypatch.setitem(SCRIPT_GLOBALS, "require_clean_source", lambda source: None)
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "require_published_source",
        lambda root, source: None,
    )
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "working_source_bundle_sha256",
        lambda root: plan.execution_source_bundle_sha256,
    )
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "load_strategic_sealed_evaluation_plan",
        lambda root: plan,
    )
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "load_strategic_navigation_scenario_registry",
        lambda root: "non-test-registry",
    )
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "resolve_rom_path",
        lambda value: tmp_path / "red.gb",
    )
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "qualify_strategic_sealed_adapter_on_non_test_capture",
        lambda **kwargs: observation,
    )
    evidence_path = tmp_path / "failed-evidence.json"
    receipt_path = tmp_path / "failed-receipt.json"

    exit_code = main(
        [
            "--scenario-id",
            "non-test-scenario",
            "--challenged-objective-id",
            "alternate-objective",
            "--state",
            str(tmp_path / "non-test.state"),
            "--receipt-id",
            "failed-live-qualification",
            "--issued-by",
            "qualification-runner",
            "--issued-on",
            "2026-08-13",
            "--evidence-output",
            str(evidence_path),
            "--receipt-output",
            str(receipt_path),
        ]
    )

    assert exit_code == 1
    assert evidence_path.read_bytes() == observation.canonical_payload()
    assert str(tmp_path) not in json.dumps(observation.public_dict())
    receipt = parse_strategic_sealed_non_test_qualification_receipt(
        receipt_path.read_bytes(),
        plan=plan,
        source_commit=source_commit,
    )
    assert receipt.verdict == "failed"
    assert receipt.evidence_sha256 == observation.evidence_sha256
    assert receipt.sealed_test_cases_opened == 0
