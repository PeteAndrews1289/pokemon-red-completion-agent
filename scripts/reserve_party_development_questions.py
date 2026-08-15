#!/usr/bin/env python3
"""Reserve the private 8+6 party curriculum without executing a question."""

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

from pokemon_red_completion.party_development_inventory import (  # noqa: E402
    PartyDevelopmentCheckpointInventory,
)
from pokemon_red_completion.party_development_outcome_learning import (  # noqa: E402
    PartyDevelopmentOutcomeModel,
)
from pokemon_red_completion.party_development_question_reservations import (  # noqa: E402
    reserve_party_development_questions,
)
from pokemon_red_completion.party_development_venue_priors import (  # noqa: E402
    PartyDevelopmentVenuePriorRegistry,
)


class PartyDevelopmentQuestionReservationRunError(RuntimeError):
    """Raised before a private reservation can be written ambiguously."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--inventory-file-sha256", required=True)
    parser.add_argument("--initial-model", type=Path, required=True)
    parser.add_argument("--initial-model-file-sha256", required=True)
    parser.add_argument("--venue-prior-registry", type=Path, required=True)
    parser.add_argument("--venue-prior-registry-file-sha256", required=True)
    parser.add_argument("--out-plan", type=Path, required=True)
    return parser


def _load_json(
    path: Path, *, expected_sha256: str, subject: str
) -> Mapping[str, object]:
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise PartyDevelopmentQuestionReservationRunError(
            f"{subject} file digest differs"
        )
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as error:
        raise PartyDevelopmentQuestionReservationRunError(
            f"{subject} is not valid JSON"
        ) from error
    if not isinstance(value, Mapping):
        raise PartyDevelopmentQuestionReservationRunError(
            f"{subject} document is invalid"
        )
    return value


def _write_exclusive(path: Path, document: dict[str, object]) -> str:
    payload = (
        json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return hashlib.sha256(payload).hexdigest()


def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.out_plan.resolve().is_relative_to(PROJECT_ROOT.resolve()):
        raise PartyDevelopmentQuestionReservationRunError(
            "private question reservation must stay outside the repository"
        )
    inventory = PartyDevelopmentCheckpointInventory.from_private_dict(
        _load_json(
            args.inventory,
            expected_sha256=args.inventory_file_sha256,
            subject="checkpoint inventory",
        )
    )
    model = PartyDevelopmentOutcomeModel.from_dict(
        _load_json(
            args.initial_model,
            expected_sha256=args.initial_model_file_sha256,
            subject="initial party model",
        )
    )
    if model.outcome_training_examples != 0:
        raise PartyDevelopmentQuestionReservationRunError(
            "question reservation requires the untouched initial party model"
        )
    venue_registry = PartyDevelopmentVenuePriorRegistry.from_private_dict(
        _load_json(
            args.venue_prior_registry,
            expected_sha256=args.venue_prior_registry_file_sha256,
            subject="venue-prior registry",
        )
    )
    plan = reserve_party_development_questions(
        inventory,
        teacher_prior=model.teacher_prior,
        venue_prior_registry=venue_registry,
    )
    private_plan_file_sha256 = _write_exclusive(args.out_plan, plan.private_dict())
    return {
        **plan.public_summary(),
        "private_plan_file_sha256": private_plan_file_sha256,
        "private_plan_file_tracked": False,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        summary = _run(args)
    except (
        OSError,
        PartyDevelopmentQuestionReservationRunError,
        TypeError,
        ValueError,
    ) as error:
        _parser().error(f"party question reservation failed: {error}")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
