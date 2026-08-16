#!/usr/bin/env python3
"""Refresh the unexecuted 8+6 reservation against the accepted two-prior registry."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.collection_protocol import (  # noqa: E402
    working_source_bundle_sha256,
)
from pokemon_red_completion.party_development_inventory import (  # noqa: E402
    PartyDevelopmentCheckpointInventory,
)
from pokemon_red_completion.party_development_outcome_learning import (  # noqa: E402
    PartyDevelopmentOutcomeModel,
)
from pokemon_red_completion.party_development_question_reservations import (  # noqa: E402
    PartyDevelopmentQuestionReservationPlan,
    refresh_party_development_question_reservations,
)
from pokemon_red_completion.party_development_venue_priors import (  # noqa: E402
    PartyDevelopmentVenuePriorRegistry,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    detect_source_identity,
    require_clean_source,
    require_published_source,
)

_MAX_JSON_BYTES = 4 * 1024 * 1024


class PartyDevelopmentQuestionRefreshRunError(RuntimeError):
    """Raised before a refreshed private plan can be written ambiguously."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--inventory-file-sha256", required=True)
    parser.add_argument("--initial-model", type=Path, required=True)
    parser.add_argument("--initial-model-file-sha256", required=True)
    parser.add_argument("--previous-plan", type=Path, required=True)
    parser.add_argument("--previous-plan-file-sha256", required=True)
    parser.add_argument("--previous-registry", type=Path, required=True)
    parser.add_argument("--previous-registry-file-sha256", required=True)
    parser.add_argument("--venue-prior-registry", type=Path, required=True)
    parser.add_argument("--venue-prior-registry-file-sha256", required=True)
    parser.add_argument("--out-plan", type=Path, required=True)
    parser.add_argument("--out-summary", type=Path, required=True)
    return parser


def _require_external(path: Path, *, subject: str) -> Path:
    resolved = path.resolve()
    if resolved.is_relative_to(PROJECT_ROOT.resolve()):
        raise PartyDevelopmentQuestionRefreshRunError(
            f"private {subject} must remain outside the repository"
        )
    return resolved


def _load_json(
    path: Path,
    *,
    expected_sha256: str,
    subject: str,
) -> Mapping[str, object]:
    payload = path.read_bytes()
    if (
        not payload
        or len(payload) > _MAX_JSON_BYTES
        or hashlib.sha256(payload).hexdigest() != expected_sha256
    ):
        raise PartyDevelopmentQuestionRefreshRunError(
            f"{subject} file digest or size differs"
        )
    try:
        value = json.loads(payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PartyDevelopmentQuestionRefreshRunError(
            f"{subject} is not valid ASCII JSON"
        ) from error
    if not isinstance(value, Mapping):
        raise PartyDevelopmentQuestionRefreshRunError(
            f"{subject} document is invalid"
        )
    return value


def _canonical_payload(document: Mapping[str, object]) -> bytes:
    return (
        json.dumps(
            document,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("ascii")


def _write_exclusive(path: Path, payload: bytes) -> str:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return hashlib.sha256(payload).hexdigest()


def _run(args: argparse.Namespace) -> dict[str, object]:
    paths = {
        "inventory": _require_external(args.inventory, subject="inventory"),
        "initial_model": _require_external(
            args.initial_model, subject="initial model"
        ),
        "previous_plan": _require_external(
            args.previous_plan, subject="previous reservation plan"
        ),
        "previous_registry": _require_external(
            args.previous_registry, subject="previous venue registry"
        ),
        "venue_registry": _require_external(
            args.venue_prior_registry, subject="venue registry"
        ),
        "out_plan": _require_external(
            args.out_plan, subject="refreshed reservation plan"
        ),
        "out_summary": _require_external(
            args.out_summary, subject="reservation refresh summary"
        ),
    }
    if len(set(paths.values())) != len(paths):
        raise PartyDevelopmentQuestionRefreshRunError(
            "party question refresh paths must be distinct"
        )
    if paths["out_plan"].exists() or paths["out_summary"].exists():
        raise FileExistsError("party question refresh output already exists")

    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    if source.git_commit is None:  # pragma: no cover - source guard owns this
        raise AssertionError("published reservation refresh lost its commit")
    source_bundle_sha256 = working_source_bundle_sha256(PROJECT_ROOT)

    inventory = PartyDevelopmentCheckpointInventory.from_private_dict(
        _load_json(
            paths["inventory"],
            expected_sha256=args.inventory_file_sha256,
            subject="checkpoint inventory",
        )
    )
    initial_model = PartyDevelopmentOutcomeModel.from_dict(
        _load_json(
            paths["initial_model"],
            expected_sha256=args.initial_model_file_sha256,
            subject="initial model",
        )
    )
    if initial_model.outcome_training_examples != 0:
        raise PartyDevelopmentQuestionRefreshRunError(
            "reservation refresh requires the untouched initial party model"
        )
    previous_plan = PartyDevelopmentQuestionReservationPlan.from_private_dict(
        _load_json(
            paths["previous_plan"],
            expected_sha256=args.previous_plan_file_sha256,
            subject="previous reservation plan",
        )
    )
    previous_registry = PartyDevelopmentVenuePriorRegistry.from_private_dict(
        _load_json(
            paths["previous_registry"],
            expected_sha256=args.previous_registry_file_sha256,
            subject="previous venue registry",
        )
    )
    venue_registry = PartyDevelopmentVenuePriorRegistry.from_private_dict(
        _load_json(
            paths["venue_registry"],
            expected_sha256=args.venue_prior_registry_file_sha256,
            subject="current venue registry",
        )
    )
    refresh = refresh_party_development_question_reservations(
        inventory,
        teacher_prior=initial_model.teacher_prior,
        previous_plan=previous_plan,
        previous_venue_prior_registry=previous_registry,
        venue_prior_registry=venue_registry,
    )

    plan_payload = _canonical_payload(refresh.plan.private_dict())
    plan_file_sha256 = hashlib.sha256(plan_payload).hexdigest()
    summary: dict[str, object] = {
        **refresh.public_summary(),
        "source_commit": source.git_commit,
        "source_bundle_sha256": source_bundle_sha256,
        "inventory_file_sha256": args.inventory_file_sha256,
        "initial_model_file_sha256": args.initial_model_file_sha256,
        "previous_plan_file_sha256": args.previous_plan_file_sha256,
        "previous_registry_file_sha256": args.previous_registry_file_sha256,
        "venue_prior_registry_file_sha256": (
            args.venue_prior_registry_file_sha256
        ),
        "private_plan_file_sha256": plan_file_sha256,
        "private_plan_file_tracked": False,
    }
    summary_payload = _canonical_payload(summary)
    _write_exclusive(paths["out_plan"], plan_payload)
    try:
        summary_file_sha256 = _write_exclusive(
            paths["out_summary"], summary_payload
        )
    except BaseException:
        paths["out_plan"].unlink(missing_ok=True)
        raise
    return {**summary, "public_summary_file_sha256": summary_file_sha256}


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        result = _run(parser.parse_args(argv))
    except (OSError, RuntimeError, TypeError, ValueError):
        parser.error(
            "party question refresh failed closed; private paths were withheld"
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
