#!/usr/bin/env python3
"""Create the private v2 party scorer with an exact authenticated v1 prior."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.party_development_outcome_learning import (  # noqa: E402
    bind_teacher_prior_from_offline_evidence,
    canonical_party_development_outcome_model_sha256,
    initialize_from_teacher_model,
)
from pokemon_red_completion.training_candidate_model import (  # noqa: E402
    load_training_candidate_model,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--teacher-model", type=Path, required=True)
    parser.add_argument("--teacher-model-file-sha256", required=True)
    parser.add_argument("--offline-evidence", type=Path, required=True)
    parser.add_argument("--offline-evidence-sha256", required=True)
    parser.add_argument("--out-model", type=Path, required=True)
    return parser


def _write_exclusive(path: Path, payload: bytes) -> str:
    if not isinstance(payload, bytes):
        raise TypeError("party-development model payload must be bytes")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return hashlib.sha256(payload).hexdigest()


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    teacher = load_training_candidate_model(
        args.teacher_model,
        expected_sha256=args.teacher_model_file_sha256,
    )
    evidence_payload = args.offline_evidence.read_bytes()
    prior = bind_teacher_prior_from_offline_evidence(
        teacher,
        model_file_sha256=args.teacher_model_file_sha256,
        evidence_payload=evidence_payload,
        expected_evidence_sha256=args.offline_evidence_sha256,
    )
    model = initialize_from_teacher_model(teacher, teacher_prior=prior)
    payload = (
        json.dumps(
            model.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        + "\n"
    ).encode("ascii")
    model_file_sha256 = _write_exclusive(args.out_model, payload)
    summary = {
        "schema": "pokemon.core.party-development-prior-initialization.v1",
        "model_id": model.model_id,
        "feature_schema_id": model.feature_schema_id,
        "private_model_file_sha256": model_file_sha256,
        "canonical_model_sha256": canonical_party_development_outcome_model_sha256(
            model
        ),
        "teacher_prior": prior.to_dict(),
        "outcome_training_examples": 0,
        "teacher_queries": 0,
        "outcomes_opened": 0,
        "authority_promoted": False,
        "private_path_fields": 0,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
