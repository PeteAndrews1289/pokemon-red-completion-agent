#!/usr/bin/env python3
"""Regenerate the prospective short-scenario strategic registry."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from pokemon_red_completion.play import QUALIFIED_OBJECTIVE_SEQUENCE
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.route import COMPLETION_QUEST
from pokemon_red_completion.strategic_navigation_scenarios import (
    STRATEGIC_SCENARIO_AUTOMATIC_COMPLETIONS,
    STRATEGIC_SCENARIO_COLLECTION_ID,
    STRATEGIC_SCENARIO_REGIME,
    STRATEGIC_SCENARIO_REGISTRY_DIGEST_RELATIVE_PATH,
    STRATEGIC_SCENARIO_REGISTRY_DIGEST_SCHEMA,
    STRATEGIC_SCENARIO_REGISTRY_RELATIVE_PATH,
    STRATEGIC_SCENARIO_REGISTRY_SCHEMA,
    STRATEGIC_SCENARIO_SCHEMA,
    parse_strategic_navigation_scenario_registry,
    reachable_objective_sets,
    scenario_context_family_sha256,
    strategic_scenario_objective_graph_sha256,
    strategic_scenario_teacher_order_sha256,
)

ROOT = Path(__file__).resolve().parents[1]

# The quota is declared before live route costs or outcomes exist.  It retains
# sparse early branches and prevents the combinatorially dense Surf/Strength
# region from consuming the entire benchmark.
_TEACHER_OBJECTIVE_QUOTAS = {
    "help_bill": 1,
    "defeat_misty": 2,
    "clear_rocket_hideout": 3,
    "rescue_fuji": 4,
    "reach_fuchsia": 4,
    "obtain_surf": 7,
    "defeat_koga": 5,
    "obtain_strength": 7,
    "defeat_erika": 6,
    "reach_saffron": 3,
    "liberate_silph": 3,
    "defeat_sabrina": 3,
}
_PARTITION_CYCLE = ("train", "train", "validation", "test")


def _canonical_line(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _frontier(completed: frozenset[str]) -> tuple[str, ...]:
    return tuple(
        objective.id
        for objective in COMPLETION_QUEST
        if objective.id not in completed
        and objective.prerequisites.issubset(completed)
    )


def _automatic_completion_closed(completed: frozenset[str]) -> bool:
    return all(
        effects.issubset(completed)
        for objective_id, effects in STRATEGIC_SCENARIO_AUTOMATIC_COMPLETIONS.items()
        if objective_id in completed
    )


def _teacher(frontier: tuple[str, ...]) -> str:
    rank = {
        objective_id: index
        for index, objective_id in enumerate(QUALIFIED_OBJECTIVE_SEQUENCE)
    }
    return min(frontier, key=rank.__getitem__)


def _row_order_key(
    completed: frozenset[str],
    candidates: tuple[str, ...],
) -> str:
    return canonical_sha256(
        {
            "candidate_objective_ids": list(candidates),
            "completed_objective_ids": sorted(completed),
            "schema": "pokemon-strategic-scenario-prospective-order-v1",
        }
    )


def _selected_situations() -> list[tuple[frozenset[str], tuple[str, ...], str]]:
    grouped: dict[str, list[tuple[str, frozenset[str], tuple[str, ...]]]] = defaultdict(list)
    for completed in reachable_objective_sets(COMPLETION_QUEST):
        if "reach_cerulean" not in completed or "defeat_giovanni" in completed:
            continue
        if not _automatic_completion_closed(completed):
            continue
        candidates = _frontier(completed)
        if not 2 <= len(candidates) <= 5:
            continue
        teacher = _teacher(candidates)
        if teacher not in _TEACHER_OBJECTIVE_QUOTAS:
            continue
        grouped[teacher].append(
            (_row_order_key(completed, candidates), completed, candidates)
        )

    selected: list[tuple[frozenset[str], tuple[str, ...], str]] = []
    for teacher in QUALIFIED_OBJECTIVE_SEQUENCE:
        quota = _TEACHER_OBJECTIVE_QUOTAS.get(teacher)
        if quota is None:
            continue
        rows = sorted(grouped[teacher])
        if len(rows) < quota:
            raise RuntimeError(f"scenario quota for {teacher} exceeds the legal inventory")
        selected.extend(
            (completed, candidates, teacher)
            for _, completed, candidates in rows[:quota]
        )
    if len(selected) != 48:
        raise RuntimeError("strategic scenario selection must contain exactly 48 situations")
    return selected


def _completed_regions(completed: frozenset[str]) -> tuple[str, ...]:
    rank = {
        objective_id: index
        for index, objective_id in enumerate(QUALIFIED_OBJECTIVE_SEQUENCE)
    }
    ordered = sorted(completed, key=rank.__getitem__)
    return tuple(
        region
        for objective_id in ordered
        if (region := COMPLETION_QUEST.objective(objective_id).target_region) is not None
    )


def _origin_region(
    completed: frozenset[str],
    candidates: tuple[str, ...],
    teacher: str,
    *,
    challenge: bool,
) -> str:
    completed_regions = _completed_regions(completed)
    if challenge:
        for objective_id in candidates:
            if objective_id == teacher:
                continue
            region = COMPLETION_QUEST.objective(objective_id).target_region
            if region is not None and region in completed_regions:
                return region
        raise RuntimeError("baseline-challenge scenario lacks a local alternative")
    teacher_region = COMPLETION_QUEST.objective(teacher).target_region
    if teacher_region is not None and teacher_region in completed_regions:
        return teacher_region
    if not completed_regions:
        raise RuntimeError("scenario lacks an authenticated origin region")
    return completed_regions[-1]


def _generated_payloads() -> tuple[bytes, bytes, dict[str, object]]:
    selected = _selected_situations()
    prelim = [
        (
            completed,
            candidates,
            teacher,
            _PARTITION_CYCLE[index % len(_PARTITION_CYCLE)],
        )
        for index, (completed, candidates, teacher) in enumerate(selected)
    ]
    challenge_indexes: set[int] = set()
    for index, (completed, candidates, teacher, partition) in enumerate(prelim):
        if partition != "validation":
            continue
        completed_regions = set(_completed_regions(completed))
        if any(
            objective_id != teacher
            and COMPLETION_QUEST.objective(objective_id).target_region in completed_regions
            for objective_id in candidates
        ):
            challenge_indexes.add(index)
        if len(challenge_indexes) == 6:
            break
    if len(challenge_indexes) != 6:
        raise RuntimeError("could not preregister six validation baseline challenges")

    scenarios: list[dict[str, object]] = []
    for index, (completed, candidates, teacher, partition) in enumerate(prelim, start=1):
        challenge = index - 1 in challenge_indexes
        row: dict[str, object] = {
            "candidate_objective_ids": list(candidates),
            "completed_objective_ids": sorted(completed),
            "context_family_sha256": scenario_context_family_sha256(
                tuple(sorted(completed)),
                candidates,
            ),
            "cost_baseline_challenge_hypothesis": challenge,
            "origin_region": _origin_region(
                completed,
                candidates,
                teacher,
                challenge=challenge,
            ),
            "partition": partition,
            "scenario_id": (
                f"red-strategic-scenario-v2-{index:03d}-{partition}"
            ),
            "schema": STRATEGIC_SCENARIO_SCHEMA,
            "teacher_objective_id": teacher,
        }
        row["scenario_sha256"] = canonical_sha256(row)
        scenarios.append(row)

    document = {
        "collection_id": STRATEGIC_SCENARIO_COLLECTION_ID,
        "objective_graph_sha256": strategic_scenario_objective_graph_sha256(
            COMPLETION_QUEST
        ),
        "regime": STRATEGIC_SCENARIO_REGIME,
        "scenarios": scenarios,
        "schema": STRATEGIC_SCENARIO_REGISTRY_SCHEMA,
        "teacher_order_sha256": strategic_scenario_teacher_order_sha256(
            QUALIFIED_OBJECTIVE_SEQUENCE
        ),
    }
    registry_payload = _canonical_line(document)
    parsed = parse_strategic_navigation_scenario_registry(registry_payload)
    registry_sha256 = hashlib.sha256(registry_payload).hexdigest()
    if parsed.registry_sha256 != registry_sha256:
        raise RuntimeError("generated scenario registry failed canonical verification")
    digest_payload = _canonical_line(
        {
            "bytes": len(registry_payload),
            "schema": STRATEGIC_SCENARIO_REGISTRY_DIGEST_SCHEMA,
            "sha256": registry_sha256,
        }
    )
    summary = parsed.public_summary()
    summary["bytes"] = len(registry_payload)
    return registry_payload, digest_payload, summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the committed scenario registry is stale.",
    )
    args = parser.parse_args(argv)
    registry_payload, digest_payload, summary = _generated_payloads()
    registry_path = ROOT / STRATEGIC_SCENARIO_REGISTRY_RELATIVE_PATH
    digest_path = ROOT / STRATEGIC_SCENARIO_REGISTRY_DIGEST_RELATIVE_PATH
    if args.check:
        if not registry_path.is_file() or not digest_path.is_file():
            raise SystemExit("strategic navigation scenario registry is absent")
        if (
            registry_path.read_bytes() != registry_payload
            or digest_path.read_bytes() != digest_payload
        ):
            raise SystemExit("strategic navigation scenario registry is stale")
    else:
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_bytes(registry_payload)
        digest_path.write_bytes(digest_payload)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
