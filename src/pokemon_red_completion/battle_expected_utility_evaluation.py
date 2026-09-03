"""Strict dataset loading and paired evaluation for expected battle utility."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from pokemon_red_completion.battle_expected_utility import (
    BattleExpectedUtilityExample,
    parse_expected_utility_record,
)
from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_outcome_batch import (
    BATTLE_OUTCOME_FIXED_HEURISTIC_ID,
    battle_outcome_fixed_heuristic_choice,
    battle_outcome_fixed_heuristic_sha256,
)


@dataclass(frozen=True, slots=True)
class BattleExpectedUtilityDatasetRow:
    """One authenticated aggregate with the identities used by commitments."""

    capture_id: str
    manifest_sha256: str
    example: BattleExpectedUtilityExample


def load_expected_utility_datasets(
    paths: Iterable[Path],
    *,
    subject: str,
) -> tuple[
    tuple[BattleExpectedUtilityDatasetRow, ...],
    tuple[dict[str, object], ...],
]:
    """Load strict JSONL and reject duplicate capture or state identities."""

    rows: list[BattleExpectedUtilityDatasetRow] = []
    identities: list[dict[str, object]] = []
    capture_ids: set[str] = set()
    state_ids: set[str] = set()
    inputs = tuple(paths)
    if not inputs:
        raise ValueError(f"{subject} has no dataset files")
    for ordinal, path in enumerate(inputs, start=1):
        payload = path.read_bytes()
        try:
            records = tuple(
                json.loads(line, object_pairs_hook=_unique_object)
                for line in payload.decode("ascii").splitlines()
                if line
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            raise ValueError(f"{subject} dataset is not strict JSON lines") from None
        if not records or any(not isinstance(record, Mapping) for record in records):
            raise ValueError(f"{subject} dataset has no valid records")
        for record in records:
            capture_id = record.get("capture_id")
            state_id = record.get("initial_state_sha256")
            manifest_sha256 = record.get("manifest_sha256")
            if (
                not isinstance(capture_id, str)
                or capture_id in capture_ids
                or not isinstance(state_id, str)
                or state_id in state_ids
                or not isinstance(manifest_sha256, str)
            ):
                raise ValueError(
                    f"{subject} dataset capture or state identities are invalid or duplicated"
                )
            capture_ids.add(capture_id)
            state_ids.add(state_id)
            rows.append(
                BattleExpectedUtilityDatasetRow(
                    capture_id=capture_id,
                    manifest_sha256=manifest_sha256,
                    example=parse_expected_utility_record(record),
                )
            )
        identities.append(
            {
                "ordinal": ordinal,
                "file_sha256": hashlib.sha256(payload).hexdigest(),
                "record_count": len(records),
            }
        )
    return tuple(rows), tuple(identities)


def evaluate_expected_utility_model(
    model: MaskedMLPMoveRanker,
    examples: tuple[BattleExpectedUtilityExample, ...],
) -> tuple[dict[str, object], tuple[int, ...]]:
    """Score one ranker against mean utilities from repeated RNG trials."""

    if not examples:
        raise ValueError("expected-utility evaluation requires examples")
    choices = tuple(
        model.predict(
            example.features.candidate_vectors,
            legal_mask=example.features.legal_mask,
            current_pp=example.features.current_pp,
        )
        for example in examples
    )
    return _evaluation("model", examples, choices), choices


def evaluate_expected_utility_fixed_heuristic(
    examples: tuple[BattleExpectedUtilityExample, ...],
) -> tuple[dict[str, object], tuple[int, ...]]:
    """Score the strongest legal fixed-power control on the same aggregates."""

    if not examples:
        raise ValueError("expected-utility evaluation requires examples")
    choices = tuple(
        battle_outcome_fixed_heuristic_choice(example.features)
        for example in examples
    )
    result = _evaluation("fixed_heuristic", examples, choices)
    result.update(
        {
            "heuristic_id": BATTLE_OUTCOME_FIXED_HEURISTIC_ID,
            "heuristic_sha256": battle_outcome_fixed_heuristic_sha256(),
        }
    )
    return result, choices


def compare_expected_utility_choices(
    examples: tuple[BattleExpectedUtilityExample, ...],
    challenger_choices: tuple[int, ...],
    control_choices: tuple[int, ...],
) -> dict[str, object]:
    """Pair candidate values state by state, preserving ties explicitly."""

    if (
        not examples
        or len(examples) != len(challenger_choices)
        or len(examples) != len(control_choices)
    ):
        raise ValueError("paired expected-utility inputs are invalid")
    challenger_wins = control_wins = equivalent = 0
    for example, challenger, control in zip(
        examples,
        challenger_choices,
        control_choices,
        strict=True,
    ):
        challenger_value = _selected_utility(example, challenger)
        control_value = _selected_utility(example, control)
        difference = challenger_value - control_value
        if math.isclose(difference, 0.0, rel_tol=0.0, abs_tol=1e-9):
            equivalent += 1
        elif difference > 0:
            challenger_wins += 1
        else:
            control_wins += 1
    return {
        "schema": "pokemon.core.battle.expected-utility-paired-comparison.v1",
        "example_count": len(examples),
        "challenger_wins": challenger_wins,
        "control_wins": control_wins,
        "equivalent_choices": equivalent,
        "authority_promoted": False,
    }


def _evaluation(
    evaluator: str,
    examples: tuple[BattleExpectedUtilityExample, ...],
    choices: tuple[int, ...],
) -> dict[str, object]:
    utilities = tuple(
        _selected_utility(example, choice)
        for example, choice in zip(examples, choices, strict=True)
    )
    return {
        "schema": "pokemon.core.battle.expected-utility-evaluation.v1",
        "evaluator": evaluator,
        "example_count": len(examples),
        "correct_preferences": sum(
            choice in example.best_candidate_indices
            for example, choice in zip(examples, choices, strict=True)
        ),
        "mean_selected_expected_utility": sum(utilities) / len(utilities),
        "candidate_indices": list(choices),
    }


def _selected_utility(example: BattleExpectedUtilityExample, index: int) -> float:
    if type(index) is not int or not 0 <= index < len(example.expected_utilities):  # noqa: E721
        raise ValueError("expected-utility choice is out of range")
    value = example.expected_utilities[index]
    if value is None:
        raise ValueError("expected-utility choice selects an unusable candidate")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


__all__ = [
    "BattleExpectedUtilityDatasetRow",
    "compare_expected_utility_choices",
    "evaluate_expected_utility_fixed_heuristic",
    "evaluate_expected_utility_model",
    "load_expected_utility_datasets",
]
