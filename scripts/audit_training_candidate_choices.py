#!/usr/bin/env python3
"""Audit whether live trainee/venue labels vary beyond choice-set shape."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
from collections import Counter, defaultdict
from collections.abc import Mapping
from pathlib import Path

from pokemon_red_completion.training_candidate_dataset import (
    TrainingCandidateDatasetError,
    load_training_candidate_replay,
)
from pokemon_red_completion.training_candidate_rank import (
    TRAINING_CANDIDATE_FEATURE_NAMES,
    TRAINING_CANDIDATE_FEATURE_SCHEMA_ID,
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_FORBIDDEN_IDENTITY_KEYS = frozenset(
    {"species_id", "move_id", "slot", "area_id", "map_id", "memory_address"}
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", nargs=2, metavar=("PATH", "SHA256"), required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        dataset = load_training_candidate_replay(
            args.replay[0], expected_sha256=args.replay[1]
        )
    except TrainingCandidateDatasetError as error:
        parser.error(str(error))
    replay = _authenticated_json(*args.replay, subject="candidate replay")
    if replay.get("schema") != "pokemon-training-candidate-replay-v1":
        parser.error("candidate replay schema is unsupported")
    if replay.get("status") != "ok" or replay.get("error") is not None:
        parser.error("candidate replay did not complete successfully")
    if (
        replay.get("feature_schema_id") != TRAINING_CANDIDATE_FEATURE_SCHEMA_ID
        or replay.get("feature_names") != list(TRAINING_CANDIDATE_FEATURE_NAMES)
    ):
        parser.error("candidate replay feature contract is unsupported")
    provenance = _mapping(replay.get("provenance"), subject="candidate provenance")
    if provenance.get("source_dirty") is not False:
        parser.error("candidate replay source must be clean")

    segments = _mapping(replay.get("segments"), subject="candidate segments")
    if set(segments) != {"evolution", "balance"}:
        parser.error("candidate replay segments are invalid")
    rows: list[Mapping[str, object]] = []
    segment_counts: dict[str, int] = {}
    for name in ("evolution", "balance"):
        segment = segments[name]
        if not isinstance(segment, list) or not all(isinstance(row, Mapping) for row in segment):
            parser.error(f"candidate {name} segment is invalid")
        _require_sequential_indexes(segment, parser, segment=name)
        rows.extend(segment)
        segment_counts[name] = len(segment)
    if not rows:
        parser.error("candidate replay contains no strategic choices")

    kind_counts: Counter[str] = Counter()
    candidate_count_counts: Counter[str] = Counter()
    selected_counts: defaultdict[str, Counter[int]] = defaultdict(Counter)
    multi_candidate = 0
    feature_rows: set[tuple[float, ...]] = set()
    for row in rows:
        if row.get("schema") != "pokemon-training-candidate-decision-v1":
            parser.error("candidate decision schema is unsupported")
        observation = _mapping(row.get("observation"), subject="candidate observation")
        if observation.get("schema") != "pokemon-training-candidate-set-v1":
            parser.error("candidate-set schema is unsupported")
        kind = observation.get("kind")
        candidates = observation.get("candidates")
        selected = row.get("selected_candidate_index")
        if kind not in {"trainee", "venue"}:
            parser.error("candidate choice kind is invalid")
        if not isinstance(candidates, list) or not candidates:
            parser.error("candidate choice set is empty")
        if type(selected) is not int or selected not in range(len(candidates)):  # noqa: E721
            parser.error("selected candidate index is invalid")
        for index, candidate in enumerate(candidates):
            candidate = _mapping(candidate, subject="candidate")
            if set(candidate) != {"candidate_index", "feature_schema_id", "features"}:
                parser.error("candidate contains an unexpected identity or field")
            if (
                candidate.get("candidate_index") != index
                or candidate.get("feature_schema_id")
                != TRAINING_CANDIDATE_FEATURE_SCHEMA_ID
            ):
                parser.error("candidate linkage or feature schema is invalid")
            features = _mapping(candidate.get("features"), subject="candidate features")
            if set(features) != set(TRAINING_CANDIDATE_FEATURE_NAMES):
                parser.error("candidate features are incomplete or unexpected")
            if _FORBIDDEN_IDENTITY_KEYS.intersection(features):
                parser.error("candidate features contain title identity")
            values = tuple(
                _normalized(features[name], parser)
                for name in TRAINING_CANDIDATE_FEATURE_NAMES
            )
            feature_rows.add(values)
        group = f"{kind}/{len(candidates)}"
        kind_counts[str(kind)] += 1
        candidate_count_counts[str(len(candidates))] += 1
        selected_counts[group][selected] += 1
        multi_candidate += int(len(candidates) > 1)

    correct = sum(max(counts.values()) for counts in selected_counts.values())
    if not multi_candidate:
        parser.error("candidate replay contains no genuine multi-candidate decisions")
    genuine_correct = sum(
        max(counts.values())
        for group, counts in selected_counts.items()
        if int(group.rsplit("/", 1)[1]) > 1
    )
    variable_groups = sorted(
        group for group, counts in selected_counts.items() if len(counts) > 1
    )
    payload = {
        "schema": "pokemon-training-candidate-choice-audit-v1",
        "replay_sha256": args.replay[1],
        "provenance": dict(provenance),
        "decisions": len(rows),
        "segment_counts": segment_counts,
        "kind_counts": dict(sorted(kind_counts.items())),
        "candidate_count_counts": dict(sorted(candidate_count_counts.items())),
        "multi_candidate_decisions": multi_candidate,
        "observed_decisions": dataset.observed_decisions,
        "retained_decisions": dataset.retained_decisions,
        "consecutive_duplicate_decisions_removed": (
            dataset.observed_decisions - dataset.retained_decisions
        ),
        "final_party_levels": list(dataset.final_party_levels),
        "final_fainted_count": dataset.final_fainted_count,
        "unique_candidate_feature_rows": len(feature_rows),
        "selected_index_counts_by_shape": {
            group: {str(index): count for index, count in sorted(counts.items())}
            for group, counts in sorted(selected_counts.items())
        },
        "shape_only_majority_accuracy": correct / len(rows),
        "genuine_shape_only_majority_accuracy": genuine_correct / multi_candidate,
        "variable_choice_shapes": variable_groups,
        "state_dependent_choice_demonstrated": bool(variable_groups),
        "identity_fields_present": False,
        "promotion_eligible": False,
    }
    _atomic_json(args.out, payload)
    print(
        json.dumps(
            {
                "decisions": len(rows),
                "shape_only_majority_accuracy": payload["shape_only_majority_accuracy"],
                "genuine_shape_only_majority_accuracy": payload[
                    "genuine_shape_only_majority_accuracy"
                ],
                "state_dependent_choice_demonstrated": bool(variable_groups),
            }
        )
    )
    return 0


def _require_sequential_indexes(
    rows: list[Mapping[str, object]],
    parser: argparse.ArgumentParser,
    *,
    segment: str,
) -> None:
    indexes = [row.get("decision_index") for row in rows]
    if indexes != list(range(len(rows))):
        parser.error(f"candidate {segment} decision indexes are not sequential")


def _normalized(value: object, parser: argparse.ArgumentParser) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        parser.error("candidate feature is not numeric")
    result = float(value)
    if not -1.0 <= result <= 1.0:
        parser.error("candidate feature is outside the normalized range")
    return result


def _authenticated_json(path: str, digest: str, *, subject: str) -> Mapping[str, object]:
    if _SHA256.fullmatch(digest) is None:
        raise ValueError(f"{subject} digest is invalid")
    source = Path(path)
    try:
        metadata = source.lstat()
        payload = source.read_bytes()
    except OSError as error:
        raise ValueError(f"{subject} cannot be read") from error
    if source.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{subject} must be a regular file")
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError(f"{subject} failed authentication")
    try:
        parsed = json.loads(payload)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{subject} is invalid JSON") from error
    return _mapping(parsed, subject=subject)


def _mapping(value: object, *, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{subject} must be an object")
    return value


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
