#!/usr/bin/env python3
"""Qualify the sealed adapter on one explicit non-test cartridge capture.

The command never enumerates capture storage and cannot resolve a test scenario.
It runs only from clean, published source whose executable bundle matches the
frozen plan.  The teacher is never executed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.collection_protocol import (  # noqa: E402
    working_source_bundle_sha256,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    EvaluationIdentityError,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.rom import (  # noqa: E402
    RomValidationError,
    resolve_rom_path,
)
from pokemon_red_completion.strategic_navigation_scenarios import (  # noqa: E402
    StrategicScenarioProtocolError,
    load_strategic_navigation_scenario_registry,
)
from pokemon_red_completion.strategic_navigation_sealed_adapter import (  # noqa: E402
    StrategicSealedAdapterError,
)
from pokemon_red_completion.strategic_navigation_sealed_cartridge import (  # noqa: E402
    qualify_strategic_sealed_adapter_on_non_test_capture,
)
from pokemon_red_completion.strategic_navigation_sealed_evaluation import (  # noqa: E402
    StrategicSealedEvaluationError,
    build_strategic_sealed_non_test_qualification_receipt,
    load_strategic_sealed_evaluation_plan,
    parse_strategic_sealed_non_test_qualification_receipt,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario-id", required=True)
    parser.add_argument("--challenged-objective-id", required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument(
        "--envelope",
        type=Path,
        default=None,
        help="defaults to <state>.json",
    )
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--receipt-id", required=True)
    parser.add_argument("--issued-by", required=True)
    parser.add_argument("--issued-on", required=True)
    parser.add_argument("--evidence-output", type=Path, required=True)
    parser.add_argument("--receipt-output", type=Path, required=True)
    return parser


def _validated_new_private_output_path(path: Path) -> Path:
    expanded = path.expanduser()
    if not expanded.is_absolute():
        raise StrategicSealedAdapterError(
            "qualification output must name a new file in an existing absolute directory"
        )
    try:
        resolved_parent = expanded.parent.resolve(strict=True)
    except OSError:
        raise StrategicSealedAdapterError(
            "qualification output must name a new file in an existing absolute directory"
        ) from None
    resolved = resolved_parent / expanded.name
    try:
        resolved.relative_to(PROJECT_ROOT.resolve(strict=True))
    except ValueError:
        pass
    else:
        raise StrategicSealedAdapterError("qualification output must remain outside the repository")
    if resolved.exists() or resolved.is_symlink():
        raise StrategicSealedAdapterError("qualification output already exists")
    return resolved


def _write_new_private_output(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as destination:
            destination.write(payload)
            destination.flush()
    except OSError:
        raise StrategicSealedAdapterError("qualification output could not be created") from None


def _run(args: argparse.Namespace) -> dict[str, object]:
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    if source.git_commit is None:  # pragma: no cover - established above
        raise StrategicSealedAdapterError("qualification source commit is unavailable")
    plan = load_strategic_sealed_evaluation_plan(PROJECT_ROOT)
    if working_source_bundle_sha256(PROJECT_ROOT) != (plan.execution_source_bundle_sha256):
        raise StrategicSealedAdapterError(
            "qualification executable source differs from the frozen plan"
        )
    evidence_output = _validated_new_private_output_path(args.evidence_output)
    receipt_output = _validated_new_private_output_path(args.receipt_output)
    if evidence_output == receipt_output:
        raise StrategicSealedAdapterError("qualification outputs must be distinct")
    build_strategic_sealed_non_test_qualification_receipt(
        plan,
        receipt_id=args.receipt_id,
        issued_by=args.issued_by,
        issued_on=args.issued_on,
        source_commit=source.git_commit,
        evidence_sha256="0" * 64,
        verdict="passed",
        sealed_test_cases_opened=0,
    )
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    rom_path = resolve_rom_path(args.rom)
    state_path = args.state.expanduser()
    envelope_path = (
        args.envelope.expanduser() if args.envelope is not None else Path(f"{state_path}.json")
    )
    observation = qualify_strategic_sealed_adapter_on_non_test_capture(
        rom_path=rom_path,
        state_path=state_path,
        envelope_path=envelope_path,
        plan=plan,
        scenario_registry=registry,
        scenario_id=args.scenario_id,
        challenged_non_teacher_objective_id=args.challenged_objective_id,
        source_commit=source.git_commit,
    )
    evidence_payload = observation.canonical_payload()
    receipt_payload = build_strategic_sealed_non_test_qualification_receipt(
        plan,
        receipt_id=args.receipt_id,
        issued_by=args.issued_by,
        issued_on=args.issued_on,
        source_commit=source.git_commit,
        evidence_sha256=observation.evidence_sha256,
        verdict="passed",
        sealed_test_cases_opened=0,
    )
    receipt = parse_strategic_sealed_non_test_qualification_receipt(
        receipt_payload,
        plan=plan,
        source_commit=source.git_commit,
    )
    _write_new_private_output(evidence_output, evidence_payload)
    _write_new_private_output(receipt_output, receipt_payload)
    return {
        "evidence_sha256": observation.evidence_sha256,
        "evaluation_id": plan.evaluation_id,
        "plan_sha256": plan.plan_sha256,
        "production_path": "authenticate_relocate_plan_close_without_teacher",
        "receipt_sha256": receipt.receipt_sha256,
        "schema": "strategic-sealed-non-test-qualification-command-result-v1",
        "sealed_test_cases_opened": 0,
        "source_commit": source.git_commit,
        "status": "passed",
        "teacher_executed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        result = _run(args)
    except (
        EvaluationIdentityError,
        RomValidationError,
        StrategicScenarioProtocolError,
        StrategicSealedAdapterError,
        StrategicSealedEvaluationError,
        OSError,
    ):
        parser.error(
            "Strategic sealed non-test qualification failed closed; private paths were withheld."
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
