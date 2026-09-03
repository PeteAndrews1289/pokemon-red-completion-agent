"""Portable, non-sealed battle-outcome datasets for rapid development.

These records contain semantic features and measured cartridge outcomes, but no
ROM bytes, save-state bytes, private paths, or controller inputs.  They are a
development artifact: benchmark and sealed-test claims still require their own
independent protocol.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping

from pokemon_red_completion.battle_outcome_learning import (
    BattleOutcomeExample,
    BattleTurnOutcome,
)
from pokemon_red_completion.battle_semantics import BattleFeatureBatch
from pokemon_red_completion.scenario_lab import ScenarioPartition

REPEATABLE_BATTLE_OUTCOME_RECORD_SCHEMA = (
    "pokemon.core.battle.repeatable-outcome-example.v1"
)
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_UTILITY_TOLERANCE = 1e-9


class RepeatableBattleDatasetError(ValueError):
    """Raised when a portable development record is malformed."""


def repeatable_battle_outcome_record(
    example: BattleOutcomeExample,
    *,
    capture_id: str,
    manifest_sha256: str,
) -> dict[str, object]:
    """Serialize one authenticated example without private capture material."""

    if not isinstance(example, BattleOutcomeExample):
        raise TypeError("example must be a BattleOutcomeExample")
    if not isinstance(capture_id, str) or _SAFE_ID.fullmatch(capture_id) is None:
        raise RepeatableBattleDatasetError("capture identity is invalid")
    if (
        not isinstance(manifest_sha256, str)
        or _SHA256.fullmatch(manifest_sha256) is None
    ):
        raise RepeatableBattleDatasetError("manifest digest is invalid")
    features = example.features
    return {
        "schema": REPEATABLE_BATTLE_OUTCOME_RECORD_SCHEMA,
        "capture_id": capture_id,
        "manifest_sha256": manifest_sha256,
        "root_lineage_id": example.root_lineage_id,
        "initial_state_sha256": example.initial_state_sha256,
        "partition": example.partition.value,
        "features": {
            "schema_id": features.schema_id,
            "feature_names": list(features.feature_names),
            "candidate_vectors": [list(row) for row in features.candidate_vectors],
            "legal_mask": list(features.legal_mask),
            "current_pp": list(features.current_pp),
            "slot_indices": list(features.slot_indices),
        },
        "outcomes": [
            None if outcome is None else outcome.public_dict()
            for outcome in example.outcomes
        ],
        "best_candidate_indices": list(example.best_candidate_indices),
        "learner_update_eligible": example.learner_update_eligible,
        "private_path_fields": 0,
        "development_artifact": True,
        "sealed_evidence": False,
    }


def parse_repeatable_battle_outcome_record(
    value: Mapping[str, object],
) -> BattleOutcomeExample:
    """Strictly parse one portable outcome record back into a typed example."""

    expected = {
        "schema",
        "capture_id",
        "manifest_sha256",
        "root_lineage_id",
        "initial_state_sha256",
        "partition",
        "features",
        "outcomes",
        "best_candidate_indices",
        "learner_update_eligible",
        "private_path_fields",
        "development_artifact",
        "sealed_evidence",
    }
    if set(value) != expected or value.get("schema") != REPEATABLE_BATTLE_OUTCOME_RECORD_SCHEMA:
        raise RepeatableBattleDatasetError("repeatable battle record fields are invalid")
    if value.get("private_path_fields") != 0:
        raise RepeatableBattleDatasetError("repeatable battle record contains private paths")
    if value.get("development_artifact") is not True or value.get("sealed_evidence") is not False:
        raise RepeatableBattleDatasetError("repeatable battle record authority is invalid")
    capture_id = value.get("capture_id")
    manifest_sha256 = value.get("manifest_sha256")
    if not isinstance(capture_id, str) or _SAFE_ID.fullmatch(capture_id) is None:
        raise RepeatableBattleDatasetError("capture identity is invalid")
    if (
        not isinstance(manifest_sha256, str)
        or _SHA256.fullmatch(manifest_sha256) is None
    ):
        raise RepeatableBattleDatasetError("manifest digest is invalid")
    if type(value.get("learner_update_eligible")) is not bool:  # noqa: E721
        raise RepeatableBattleDatasetError("recorded learning eligibility is invalid")
    best_candidates = value.get("best_candidate_indices")
    if not isinstance(best_candidates, list) or any(
        type(item) is not int or item < 0 for item in best_candidates  # noqa: E721
    ):
        raise RepeatableBattleDatasetError("recorded best candidates are invalid")
    feature_value = value.get("features")
    if not isinstance(feature_value, Mapping) or set(feature_value) != {
        "schema_id",
        "feature_names",
        "candidate_vectors",
        "legal_mask",
        "current_pp",
        "slot_indices",
    }:
        raise RepeatableBattleDatasetError("repeatable battle features are invalid")
    try:
        feature_names = _string_list(feature_value["feature_names"])
        candidate_vectors = _numeric_rows(feature_value["candidate_vectors"])
        legal_mask = _bool_list(feature_value["legal_mask"])
        current_pp = _numeric_list(feature_value["current_pp"])
        slot_indices = _integer_list(feature_value["slot_indices"])
        schema_id = feature_value["schema_id"]
        root_lineage_id = value["root_lineage_id"]
        initial_state_sha256 = value["initial_state_sha256"]
        partition = value["partition"]
        if (
            not isinstance(schema_id, str)
            or not isinstance(root_lineage_id, str)
            or not isinstance(initial_state_sha256, str)
            or not isinstance(partition, str)
        ):
            raise TypeError
        features = BattleFeatureBatch(
            schema_id=schema_id,
            feature_names=feature_names,
            candidate_vectors=candidate_vectors,
            legal_mask=legal_mask,
            current_pp=current_pp,
            slot_indices=slot_indices,
        )
        raw_outcomes = value["outcomes"]
        if not isinstance(raw_outcomes, list):
            raise TypeError
        outcomes = tuple(_parse_outcome(item) for item in raw_outcomes)
        example = BattleOutcomeExample(
            root_lineage_id=root_lineage_id,
            initial_state_sha256=initial_state_sha256,
            partition=ScenarioPartition(partition),
            features=features,
            outcomes=outcomes,
        )
    except (KeyError, TypeError, ValueError):
        raise RepeatableBattleDatasetError(
            "repeatable battle record values are invalid"
        ) from None
    if list(example.best_candidate_indices) != best_candidates:
        raise RepeatableBattleDatasetError("recorded best candidates differ from outcomes")
    if example.learner_update_eligible is not value["learner_update_eligible"]:
        raise RepeatableBattleDatasetError("recorded learning eligibility differs")
    return example


def _parse_outcome(value: object) -> BattleTurnOutcome | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError
    required = {
        "schema",
        "move_executed",
        "opponent_damage_fraction",
        "player_damage_fraction",
        "opponent_fainted",
        "player_fainted",
        "battle_exited",
        "actions_executed",
        "frames_executed",
        "pre_attack_frames",
        "utility",
    }
    if (
        set(value) != required
        or value.get("schema") != "pokemon.core.battle.selected-turn-outcome.v2"
    ):
        raise ValueError
    outcome = BattleTurnOutcome(
        move_executed=value["move_executed"],  # type: ignore[arg-type]
        opponent_damage_fraction=value["opponent_damage_fraction"],  # type: ignore[arg-type]
        player_damage_fraction=value["player_damage_fraction"],  # type: ignore[arg-type]
        opponent_fainted=value["opponent_fainted"],  # type: ignore[arg-type]
        player_fainted=value["player_fainted"],  # type: ignore[arg-type]
        battle_exited=value["battle_exited"],  # type: ignore[arg-type]
        actions_executed=value["actions_executed"],  # type: ignore[arg-type]
        frames_executed=value["frames_executed"],  # type: ignore[arg-type]
        pre_attack_frames=value["pre_attack_frames"],  # type: ignore[arg-type]
    )
    serialized_utility = value["utility"]
    if (
        isinstance(serialized_utility, bool)
        or not isinstance(serialized_utility, (int, float))
        or not math.isfinite(float(serialized_utility))
        or not math.isclose(
            float(serialized_utility),
            outcome.utility,
            rel_tol=0.0,
            abs_tol=_UTILITY_TOLERANCE,
        )
    ):
        raise ValueError
    return outcome


def _string_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise TypeError
    return tuple(value)


def _bool_list(value: object) -> tuple[bool, ...]:
    if not isinstance(value, list) or any(type(item) is not bool for item in value):  # noqa: E721
        raise TypeError
    return tuple(value)


def _numeric_list(value: object) -> tuple[float, ...]:
    if not isinstance(value, list) or any(
        isinstance(item, bool)
        or not isinstance(item, (int, float))
        or not math.isfinite(float(item))
        for item in value
    ):
        raise TypeError
    return tuple(float(item) for item in value)


def _numeric_rows(value: object) -> tuple[tuple[float, ...], ...]:
    if not isinstance(value, list):
        raise TypeError
    return tuple(_numeric_list(row) for row in value)


def _integer_list(value: object) -> tuple[int, ...]:
    if not isinstance(value, list) or any(type(item) is not int for item in value):  # noqa: E721
        raise TypeError
    return tuple(value)
