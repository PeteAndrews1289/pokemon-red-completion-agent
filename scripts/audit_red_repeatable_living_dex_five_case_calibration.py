#!/usr/bin/env python3
"""Reproduce the path-free five-case Red shadow calibration diagnostic.

The command reads only two tracked public evidence files.  It has no private-root,
ROM, controller, model-fitting, teacher, or outcome-opening interface.
"""

# ruff: noqa: E402 -- pin the project source root before package imports.

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Never

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
while str(SRC_ROOT) in sys.path:
    sys.path.remove(str(SRC_ROOT))
sys.path.insert(0, str(SRC_ROOT))

from pokemon_red_completion.goal_manager_runtime import CompletionFirstGoalTeacher
from pokemon_red_completion.living_dex_calibration_audit import (
    LivingDexSuccessPrediction,
    audit_living_dex_success_predictions,
)

FIRST_TWO_PATH = (
    PROJECT_ROOT
    / "docs/evidence/red-repeatable-living-dex-development-first-two-results-v1-2026-09-05.json"
)
SUPPLEMENT_PATH = (
    PROJECT_ROOT
    / "docs/evidence/red-repeatable-living-dex-development-supplement-results-v1-2026-09-05.json"
)
FIRST_TWO_SHA256 = "f15413be01fc942643923fd4bc563f655acf89ff88f038aa2495e9c1b5c712ca"
SUPPLEMENT_SHA256 = "8b3805700bc88d4cfb77695222139dd1da642e4fbe88363a55c4d5bed0d60c3b"
MODEL_SHA256 = "cbff99900be566347a1ce3d6ccbe0d0c935eb5c6a9a3f961accdbc96c9442a56"


class FiveCaseCalibrationAuditError(ValueError):
    """The tracked evidence no longer supports the fixed diagnostic."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise FiveCaseCalibrationAuditError("arguments")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument("--pretty", action="store_true")
    return parser


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise FiveCaseCalibrationAuditError("duplicate JSON field")
        result[key] = value
    return result


def _load(path: Path, expected_sha256: str) -> Mapping[str, object]:
    try:
        payload = path.read_bytes()
    except OSError:
        raise FiveCaseCalibrationAuditError("public evidence is unreadable") from None
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise FiveCaseCalibrationAuditError("public evidence identity differs")
    try:
        value = json.loads(
            payload.decode("ascii"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                FiveCaseCalibrationAuditError("non-finite JSON number")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise FiveCaseCalibrationAuditError("public evidence is invalid") from None
    if not isinstance(value, Mapping):
        raise FiveCaseCalibrationAuditError("public evidence is invalid")
    return value


def _mapping(value: object, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise FiveCaseCalibrationAuditError(f"{subject} differs")
    return value


def _cases(value: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    raw = value.get("cases")
    if not isinstance(raw, list):
        raise FiveCaseCalibrationAuditError("public cases differ")
    return tuple(_mapping(item, "public case") for item in raw)


def build_public_audit() -> dict[str, object]:
    """Return the fixed aggregate without opening any protected input."""

    first = _load(FIRST_TWO_PATH, FIRST_TWO_SHA256)
    supplement = _load(SUPPLEMENT_PATH, SUPPLEMENT_SHA256)
    if (
        first.get("schema")
        != "pokemon.red.repeatable-living-dex-development-first-two-results.v1"
        or supplement.get("schema")
        != "pokemon.red.repeatable-living-dex-development-supplement-results.v1"
    ):
        raise FiveCaseCalibrationAuditError("public evidence schema differs")
    first_model = _mapping(first.get("model"), "first model")
    supplement_model = _mapping(supplement.get("model"), "supplement model")
    if (
        first_model.get("model_sha256") != MODEL_SHA256
        or supplement_model.get("model_sha256") != MODEL_SHA256
        or first_model.get("training_examples") != 18
        or supplement_model.get("training_examples") != 18
        or first_model.get("authority") != "shadow_development_only"
        or supplement_model.get("authority") != "shadow_development_only"
    ):
        raise FiveCaseCalibrationAuditError("shadow model binding differs")
    cases = (*_cases(first), *_cases(supplement))
    if len(cases) != 5:
        raise FiveCaseCalibrationAuditError("five-case denominator differs")
    observations: list[LivingDexSuccessPrediction] = []
    public_rows: list[dict[str, object]] = []
    for ordinal, case in enumerate(cases):
        probability = case.get("predicted_verified_success")
        success = case.get("verified_success")
        kind = case.get("selected_option_kind")
        if (
            case.get("ordinal") != ordinal
            or not isinstance(kind, str)
            or isinstance(probability, bool)
            or not isinstance(probability, (int, float))
            or type(success) is not bool  # noqa: E721
            or case.get("durable_terminal") is not True
            or case.get("retry_allowed") is not False
        ):
            raise FiveCaseCalibrationAuditError("five-case terminal differs")
        observations.append(
            LivingDexSuccessPrediction(kind, float(probability), success)
        )
        public_rows.append(
            {
                "ordinal": ordinal,
                "predicted_verified_success": float(probability),
                "selected_option_kind": kind,
                "verified_success": success,
            }
        )
    audit = audit_living_dex_success_predictions(observations)
    empirical_rate = audit.overall.observed_success_rate
    post_hoc = audit_living_dex_success_predictions(
        LivingDexSuccessPrediction(row.option_kind, empirical_rate, row.verified_success)
        for row in observations
    )
    return {
        "adjudication": {
            "supported": [
                "The five committed selected-arm success probabilities reproduce against "
                "five durable factual development outcomes.",
                "The shadow model has material two-sided calibration error: one highly "
                "confident acquisition failure and one highly confident party-development "
                "false negative.",
                "The existing title-neutral CompletionFirstGoalTeacher is a suitable "
                "prospectively frozen deterministic control for a new paired Red comparison.",
            ],
            "unsupported": [
                "model_advantage",
                "post_hoc_comparator_advantage",
                "population_calibration",
                "fresh_generalization",
                "model_fit_on_development",
                "learned_gameplay_authority",
                "sealed_red_evaluation",
                "crystal_transfer",
                "full_game_completion",
                "living_pokedex_completion",
            ],
        },
        "cases": public_rows,
        "diagnostic": audit.public_dict(),
        "effects": {
            "authority_promotions": 0,
            "controller_actions": 0,
            "crystal_accesses": 0,
            "development_examples_read_for_fit": 0,
            "emulator_frames": 0,
            "model_fits": 0,
            "new_model_predictions": 0,
            "outcomes_opened": 0,
            "teacher_queries": 0,
            "training_targets_emitted": 0,
        },
        "model": {
            "authority": "shadow_development_only",
            "model_sha256": MODEL_SHA256,
            "training_examples": 18,
        },
        "next_gate": {
            "deterministic_control": CompletionFirstGoalTeacher().public_dict(),
            "evaluation": {
                "arms_per_root": 2,
                "development_outcomes_may_train": False,
                "minimum_lineage_disjoint_roots": 8,
                "policy_choices_committed_before_outcomes": True,
                "policies": [
                    "updated_title_neutral_option_value_model",
                    "completion_first_goal_teacher_v1",
                ],
                "same_authenticated_initial_state_per_pair": True,
                "timing_or_rng_siblings_create_independence": False,
            },
            "train_only_update": {
                "complete_settled_denominator_must_fit": True,
                "development_rows_permitted": 0,
                "minimum_settled_acquire_species": 3,
                "minimum_settled_develop_team": 3,
                "minimum_settled_total": 8,
                "prospective_roots": 10,
                "prospective_selected_kind_counts": {
                    "acquire_species": 4,
                    "develop_team": 4,
                    "manage_storage": 1,
                    "resupply": 1,
                },
                "setup_censor_allowance": 2,
                "upstream_lineage_reuse_permitted": False,
            },
        },
        "post_hoc_constant_rate_diagnostic": {
            "comparator_chosen_before_outcomes": False,
            "eligible_for_advantage_claim": False,
            "metrics": post_hoc.overall.public_dict(),
            "probability": empirical_rate,
            "purpose": (
                "Scale check only; the probability equals the observed rate of these same "
                "five cases."
            ),
        },
        "recorded_on": "2026-09-05",
        "schema": "pokemon.red.repeatable-living-dex-five-case-calibration-audit.v1",
        "source_evidence": [
            {
                "cases": 2,
                "path": FIRST_TWO_PATH.relative_to(PROJECT_ROOT).as_posix(),
                "sha256": FIRST_TWO_SHA256,
            },
            {
                "cases": 3,
                "path": SUPPLEMENT_PATH.relative_to(PROJECT_ROOT).as_posix(),
                "sha256": SUPPLEMENT_SHA256,
            },
        ],
        "status": "five_case_development_calibration_audited_action_free",
    }


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        value = build_public_audit()
    except FiveCaseCalibrationAuditError as error:
        print(
            json.dumps(
                {
                    "schema": (
                        "pokemon.red.repeatable-living-dex-five-case-calibration-audit-"
                        "failure.v1"
                    ),
                    "stage": str(error),
                    "status": "failed_closed",
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 1
    if args.pretty:
        print(json.dumps(value, allow_nan=False, indent=2, sort_keys=True))
    else:
        print(json.dumps(value, allow_nan=False, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - script boundary
    raise SystemExit(main())
