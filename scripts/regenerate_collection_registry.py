#!/usr/bin/env python3
"""Regenerate the prospective collection registry before its publication commit."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from pokemon_red_completion.battle_plan import RED_BATTLE_PLAN_IDS
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.collection_protocol import (
    BATTLE_PLAN_ROSTER_SCHEMA,
    BATTLE_START_MAX_OFFSET_FRAMES,
    BATTLE_START_SCHEDULE_DERIVATION,
    BATTLE_START_SCHEDULE_SCHEMA,
    COLLECTION_EXECUTION_SCHEMA,
    COLLECTION_REGISTRY_DIGEST_RELATIVE_PATH,
    COLLECTION_REGISTRY_DIGEST_SCHEMA,
    COLLECTION_REGISTRY_RELATIVE_PATH,
    SCHEDULE_DRY_RUN_SCHEMA,
    SCHEDULE_DRY_RUN_SEED,
    BattleStartSchedule,
    collection_document_sha256,
    objective_graph_document,
    parse_collection_registry,
    teacher_behavior_configuration,
    working_source_bundle_sha256,
)
from pokemon_red_completion.opening import DEFAULT_OPENING_TIMING, PRET_POKERED_COMMIT
from pokemon_red_completion.play import DEFAULT_QUALIFIED_PLAY_TIMING
from pokemon_red_completion.route import completion_route_payload

ROOT = Path(__file__).resolve().parents[1]
V3_TEMPLATE_PATH = ROOT / "configs/red-battle-collection-v3.json"


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


def _generated_payloads() -> tuple[bytes, bytes, dict[str, object]]:
    document = json.loads(V3_TEMPLATE_PATH.read_text(encoding="ascii"))
    if not isinstance(document, dict):
        raise RuntimeError("collection registry must be an object")
    document["collection_id"] = "red-battle-heldout-v26"
    document["runs"] = [
        {
            "harness_seed": seed,
            "partition": partition,
            "run_id": f"red-battle-v26-{ordinal:02d}-{partition}",
        }
        for ordinal, (partition, seed) in enumerate(
            (
                *(("train", seed) for seed in range(36_001, 36_006)),
                *(("validation", seed) for seed in range(46_001, 46_003)),
                *(("test", seed) for seed in range(56_001, 56_006)),
            ),
            start=1,
        )
    ]
    battle_roster_sha256 = collection_document_sha256(
        {
            "battle_plan_ids": list(RED_BATTLE_PLAN_IDS),
            "schema": BATTLE_PLAN_ROSTER_SCHEMA,
        }
    )
    schedule_document = {
        "battle_plan_ids": list(RED_BATTLE_PLAN_IDS),
        "battle_roster_sha256": battle_roster_sha256,
        "derivation": BATTLE_START_SCHEDULE_DERIVATION,
        "max_offset_frames": BATTLE_START_MAX_OFFSET_FRAMES,
        "schema": BATTLE_START_SCHEDULE_SCHEMA,
    }
    document["schedule"] = schedule_document
    schedule = BattleStartSchedule(
        battle_plan_ids=RED_BATTLE_PLAN_IDS,
        battle_roster_sha256=battle_roster_sha256,
        derivation=BATTLE_START_SCHEDULE_DERIVATION,
        max_offset_frames=BATTLE_START_MAX_OFFSET_FRAMES,
        schema=BATTLE_START_SCHEDULE_SCHEMA,
    )

    behavior = teacher_behavior_configuration(
        pyboy_version="2.7.0",
        new_game_timing=asdict(DEFAULT_NEW_GAME_TIMING),
        opening_timing=asdict(DEFAULT_OPENING_TIMING),
        play_timing=asdict(DEFAULT_QUALIFIED_PLAY_TIMING),
        pret_pokered_commit=PRET_POKERED_COMMIT,
    )
    behavior_sha256 = collection_document_sha256(behavior)
    source_bundle_sha256 = working_source_bundle_sha256(ROOT)
    objective_graph_sha256 = collection_document_sha256(
        objective_graph_document(completion_route_payload())
    )
    teacher_execution = {
        "actor": document["policy"]["actor"],
        "adapter_id": document["adapter_id"],
        "behavior_configuration_sha256": behavior_sha256,
        "collection_id": document["collection_id"],
        "game_id": document["game_id"],
        "objective_graph_sha256": objective_graph_sha256,
        "ontology_id": document["ontology_id"],
        "policy_id": document["policy"]["policy_id"],
        "schema": COLLECTION_EXECUTION_SCHEMA,
        "source_bundle_sha256": source_bundle_sha256,
    }
    teacher_execution_sha256 = collection_document_sha256(teacher_execution)
    document["execution"] = {
        "behavior_configuration": behavior,
        "behavior_configuration_sha256": behavior_sha256,
        "objective_graph_sha256": objective_graph_sha256,
        "schema": COLLECTION_EXECUTION_SCHEMA,
        "source_bundle_sha256": source_bundle_sha256,
        "teacher_execution_sha256": teacher_execution_sha256,
    }

    runs = document["runs"]
    if not isinstance(runs, list):
        raise RuntimeError("collection runs must be a list")
    for run in runs:
        if not isinstance(run, dict):
            raise RuntimeError("collection run must be an object")
        run["schedule_sha256"] = schedule.schedule_sha256(int(run["harness_seed"]))
    document["schedule_dry_run"] = {
        "dry_run_id": "red-battle-schedule-dry-run-v26",
        "harness_seed": SCHEDULE_DRY_RUN_SEED,
        "schedule_sha256": schedule.schedule_sha256(SCHEDULE_DRY_RUN_SEED),
        "schema": SCHEDULE_DRY_RUN_SCHEMA,
    }

    registry_payload = _canonical_line(document)
    parsed = parse_collection_registry(registry_payload)
    if parsed.registry_sha256 != hashlib.sha256(registry_payload).hexdigest():
        raise RuntimeError("generated registry failed canonical digest verification")
    digest_payload = _canonical_line(
        {
            "bytes": len(registry_payload),
            "schema": COLLECTION_REGISTRY_DIGEST_SCHEMA,
            "sha256": hashlib.sha256(registry_payload).hexdigest(),
        }
    )
    return (
        registry_payload,
        digest_payload,
        {
            "bytes": len(registry_payload),
            "registry_sha256": hashlib.sha256(registry_payload).hexdigest(),
            "source_bundle_sha256": source_bundle_sha256,
            "teacher_execution_sha256": teacher_execution_sha256,
        },
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the committed registry is stale instead of rewriting it.",
    )
    args = parser.parse_args(argv)
    registry_payload, digest_payload, summary = _generated_payloads()
    registry_path = ROOT / COLLECTION_REGISTRY_RELATIVE_PATH
    digest_path = ROOT / COLLECTION_REGISTRY_DIGEST_RELATIVE_PATH
    if args.check:
        if (
            registry_path.read_bytes() != registry_payload
            or digest_path.read_bytes() != digest_payload
        ):
            raise SystemExit("collection registry is stale; regenerate it")
    else:
        registry_path.write_bytes(registry_payload)
        digest_path.write_bytes(digest_payload)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
