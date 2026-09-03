"""Shared input binding and strongest-baseline evaluation for rapid battle learning."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from pathlib import Path

from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker
from pokemon_red_completion.battle_outcome_batch import (
    BATTLE_OUTCOME_FIXED_HEURISTIC_ID,
    battle_outcome_fixed_heuristic_choice,
    battle_outcome_fixed_heuristic_sha256,
)
from pokemon_red_completion.battle_outcome_learning import BattleOutcomeExample
from pokemon_red_completion.repeatable_battle_dataset import (
    parse_repeatable_battle_outcome_record,
)


def load_repeatable_battle_model(
    path: Path,
) -> tuple[MaskedMLPMoveRanker, str]:
    """Load one model and retain the exact file identity that influenced the run."""

    payload = path.read_bytes()
    try:
        document = json.loads(
            payload.decode("ascii"),
            object_pairs_hook=_unique_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise ValueError("battle model is not strict JSON") from None
    return MaskedMLPMoveRanker.from_dict(document), hashlib.sha256(payload).hexdigest()


def load_repeatable_battle_datasets(
    paths: Iterable[Path],
    *,
    subject: str,
) -> tuple[tuple[BattleOutcomeExample, ...], tuple[dict[str, object], ...]]:
    """Load strict JSONL datasets, reject duplicate captures, and bind every file."""

    examples: list[BattleOutcomeExample] = []
    identities: list[dict[str, object]] = []
    capture_ids: set[str] = set()
    inputs = tuple(paths)
    if not inputs:
        raise ValueError(f"{subject} has no dataset files")
    for ordinal, path in enumerate(inputs, start=1):
        payload = path.read_bytes()
        try:
            documents = tuple(
                json.loads(line, object_pairs_hook=_unique_object)
                for line in payload.decode("ascii").splitlines()
                if line
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            raise ValueError(f"{subject} dataset is not strict JSON lines") from None
        if not documents or any(not isinstance(item, Mapping) for item in documents):
            raise ValueError(f"{subject} dataset has no valid records")
        for document in documents:
            capture_id = document.get("capture_id")
            if not isinstance(capture_id, str) or capture_id in capture_ids:
                raise ValueError(
                    f"{subject} dataset capture identities are invalid or duplicated"
                )
            capture_ids.add(capture_id)
            examples.append(parse_repeatable_battle_outcome_record(document))
        identities.append(
            {
                "ordinal": ordinal,
                "file_sha256": hashlib.sha256(payload).hexdigest(),
                "record_count": len(documents),
            }
        )
    return tuple(examples), tuple(identities)


def evaluate_repeatable_fixed_heuristic(
    examples: tuple[BattleOutcomeExample, ...],
) -> tuple[dict[str, object], tuple[int, ...]]:
    """Evaluate the legal transferable fixed-power baseline on measured outcomes."""

    if not examples:
        raise ValueError("fixed heuristic evaluation requires examples")
    choices = tuple(
        battle_outcome_fixed_heuristic_choice(example.features) for example in examples
    )
    selected = tuple(
        example.outcomes[index]
        for example, index in zip(examples, choices, strict=True)
    )
    if any(outcome is None for outcome in selected):
        raise ValueError("fixed heuristic selected an unmeasured action")
    return (
        {
            "schema": "pokemon.core.battle.fixed-heuristic-evaluation.v2",
            "heuristic_id": BATTLE_OUTCOME_FIXED_HEURISTIC_ID,
            "heuristic_sha256": battle_outcome_fixed_heuristic_sha256(),
            "example_count": len(examples),
            "correct_preferences": sum(
                choice in example.best_candidate_indices
                for choice, example in zip(choices, examples, strict=True)
            ),
            "mean_selected_utility": sum(
                outcome.utility for outcome in selected if outcome is not None
            )
            / len(selected),
            "candidate_indices": list(choices),
        },
        choices,
    )


def compare_model_with_repeatable_fixed_heuristic(
    model: MaskedMLPMoveRanker,
    examples: tuple[BattleOutcomeExample, ...],
    fixed_choices: tuple[int, ...],
) -> dict[str, object]:
    """Return a same-state utility comparison against the strongest fixed baseline."""

    if not examples or len(examples) != len(fixed_choices):
        raise ValueError("paired fixed-heuristic comparison inputs are invalid")
    model_wins = fixed_wins = equivalent = 0
    for example, fixed_index in zip(examples, fixed_choices, strict=True):
        model_index = model.predict(
            example.features.candidate_vectors,
            legal_mask=example.features.legal_mask,
            current_pp=example.features.current_pp,
        )
        model_outcome = example.outcomes[model_index]
        fixed_outcome = example.outcomes[fixed_index]
        if model_outcome is None or fixed_outcome is None:
            raise ValueError("paired evaluation selected an unmeasured action")
        difference = model_outcome.utility - fixed_outcome.utility
        if math.isclose(difference, 0.0, rel_tol=0.0, abs_tol=1e-9):
            equivalent += 1
        elif difference > 0:
            model_wins += 1
        else:
            fixed_wins += 1
    return {
        "schema": "pokemon.core.battle.model-vs-fixed-heuristic.v1",
        "heuristic_id": BATTLE_OUTCOME_FIXED_HEURISTIC_ID,
        "example_count": len(examples),
        "challenger_wins": model_wins,
        "fixed_heuristic_wins": fixed_wins,
        "equivalent_choices": equivalent,
        "authority_promoted": False,
    }


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result
