#!/usr/bin/env python3
"""Regenerate prospective whole-root strategic-navigation assignments."""

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
    BattleStartSchedule,
    collection_document_sha256,
    objective_graph_document,
    teacher_behavior_configuration,
    working_source_bundle_sha256,
)
from pokemon_red_completion.opening import DEFAULT_OPENING_TIMING, PRET_POKERED_COMMIT
from pokemon_red_completion.play import DEFAULT_QUALIFIED_PLAY_TIMING
from pokemon_red_completion.route import completion_route_payload
from pokemon_red_completion.strategic_navigation_protocol import (
    STRATEGIC_NAVIGATION_ACTOR,
    STRATEGIC_NAVIGATION_ADAPTER_ID,
    STRATEGIC_NAVIGATION_COLLECTION_ID,
    STRATEGIC_NAVIGATION_EXECUTION_SCHEMA,
    STRATEGIC_NAVIGATION_GAME_ID,
    STRATEGIC_NAVIGATION_ONTOLOGY_ID,
    STRATEGIC_NAVIGATION_POLICY_ID,
    STRATEGIC_NAVIGATION_REGIME,
    STRATEGIC_NAVIGATION_REGISTRY_DIGEST_RELATIVE_PATH,
    STRATEGIC_NAVIGATION_REGISTRY_DIGEST_SCHEMA,
    STRATEGIC_NAVIGATION_REGISTRY_RELATIVE_PATH,
    STRATEGIC_NAVIGATION_REGISTRY_SCHEMA,
    STRATEGIC_NAVIGATION_REHEARSAL_ID,
    STRATEGIC_NAVIGATION_REHEARSAL_SCHEMA,
    STRATEGIC_NAVIGATION_REHEARSAL_SEED,
    parse_strategic_navigation_registry,
    strategic_navigation_contract_document,
)

ROOT = Path(__file__).resolve().parents[1]


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
    roster_sha256 = collection_document_sha256(
        {
            "battle_plan_ids": list(RED_BATTLE_PLAN_IDS),
            "schema": BATTLE_PLAN_ROSTER_SCHEMA,
        }
    )
    schedule_document = {
        "battle_plan_ids": list(RED_BATTLE_PLAN_IDS),
        "battle_roster_sha256": roster_sha256,
        "derivation": BATTLE_START_SCHEDULE_DERIVATION,
        "max_offset_frames": BATTLE_START_MAX_OFFSET_FRAMES,
        "schema": BATTLE_START_SCHEDULE_SCHEMA,
    }
    schedule = BattleStartSchedule(
        battle_plan_ids=RED_BATTLE_PLAN_IDS,
        battle_roster_sha256=roster_sha256,
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
    source_bundle_sha256 = working_source_bundle_sha256(ROOT)
    behavior_sha256 = collection_document_sha256(behavior)
    objective_graph_sha256 = collection_document_sha256(
        objective_graph_document(completion_route_payload())
    )
    decision_contract_sha256 = collection_document_sha256(
        strategic_navigation_contract_document()
    )
    execution = {
        "behavior_configuration_sha256": behavior_sha256,
        "decision_contract_sha256": decision_contract_sha256,
        "objective_graph_sha256": objective_graph_sha256,
        "schema": STRATEGIC_NAVIGATION_EXECUTION_SCHEMA,
        "source_bundle_sha256": source_bundle_sha256,
    }
    execution["teacher_execution_sha256"] = collection_document_sha256(
        {
            "actor": STRATEGIC_NAVIGATION_ACTOR,
            "adapter_id": STRATEGIC_NAVIGATION_ADAPTER_ID,
            "behavior_configuration_sha256": behavior_sha256,
            "collection_id": STRATEGIC_NAVIGATION_COLLECTION_ID,
            "decision_contract_sha256": decision_contract_sha256,
            "game_id": STRATEGIC_NAVIGATION_GAME_ID,
            "objective_graph_sha256": objective_graph_sha256,
            "ontology_id": STRATEGIC_NAVIGATION_ONTOLOGY_ID,
            "policy_id": STRATEGIC_NAVIGATION_POLICY_ID,
            "schema": STRATEGIC_NAVIGATION_EXECUTION_SCHEMA,
            "source_bundle_sha256": source_bundle_sha256,
        }
    )
    run_specs = (
        *(('train', seed) for seed in range(1_720_001, 1_720_006)),
        *(('validation', seed) for seed in range(1_730_001, 1_730_003)),
        *(('test', seed) for seed in range(1_740_001, 1_740_006)),
    )
    runs = [
        {
            "harness_seed": seed,
            "partition": partition,
            "run_id": f"red-strategic-v1-{ordinal:02d}-{partition}",
            "schedule_sha256": schedule.schedule_sha256(seed),
        }
        for ordinal, (partition, seed) in enumerate(run_specs, start=1)
    ]
    document = {
        "adapter_id": STRATEGIC_NAVIGATION_ADAPTER_ID,
        "collection_id": STRATEGIC_NAVIGATION_COLLECTION_ID,
        "execution": execution,
        "game_id": STRATEGIC_NAVIGATION_GAME_ID,
        "ontology_id": STRATEGIC_NAVIGATION_ONTOLOGY_ID,
        "policy": {
            "actor": STRATEGIC_NAVIGATION_ACTOR,
            "policy_id": STRATEGIC_NAVIGATION_POLICY_ID,
        },
        "regime": STRATEGIC_NAVIGATION_REGIME,
        "rehearsal": {
            "harness_seed": STRATEGIC_NAVIGATION_REHEARSAL_SEED,
            "rehearsal_id": STRATEGIC_NAVIGATION_REHEARSAL_ID,
            "schedule_sha256": schedule.schedule_sha256(
                STRATEGIC_NAVIGATION_REHEARSAL_SEED
            ),
            "schema": STRATEGIC_NAVIGATION_REHEARSAL_SCHEMA,
        },
        "runs": runs,
        "schedule": schedule_document,
        "schema": STRATEGIC_NAVIGATION_REGISTRY_SCHEMA,
    }
    registry_payload = _canonical_line(document)
    parsed = parse_strategic_navigation_registry(registry_payload)
    registry_sha256 = hashlib.sha256(registry_payload).hexdigest()
    if parsed.registry_sha256 != registry_sha256:
        raise RuntimeError("generated strategic registry failed canonical verification")
    digest_payload = _canonical_line(
        {
            "bytes": len(registry_payload),
            "schema": STRATEGIC_NAVIGATION_REGISTRY_DIGEST_SCHEMA,
            "sha256": registry_sha256,
        }
    )
    return registry_payload, digest_payload, {
        "bytes": len(registry_payload),
        "decision_contract_sha256": decision_contract_sha256,
        "learning_roots": 7,
        "rehearsal_assignment_sha256": parsed.rehearsal_assignment().assignment_id,
        "registry_sha256": registry_sha256,
        "source_bundle_sha256": source_bundle_sha256,
        "teacher_execution_sha256": execution["teacher_execution_sha256"],
        "test_roots_sealed": 5,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the committed prospective registry is stale.",
    )
    args = parser.parse_args(argv)
    registry_payload, digest_payload, summary = _generated_payloads()
    registry_path = ROOT / STRATEGIC_NAVIGATION_REGISTRY_RELATIVE_PATH
    digest_path = ROOT / STRATEGIC_NAVIGATION_REGISTRY_DIGEST_RELATIVE_PATH
    if args.check:
        if (
            registry_path.read_bytes() != registry_payload
            or digest_path.read_bytes() != digest_payload
        ):
            raise SystemExit("strategic navigation collection registry is stale")
    else:
        registry_path.write_bytes(registry_payload)
        digest_path.write_bytes(digest_payload)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
