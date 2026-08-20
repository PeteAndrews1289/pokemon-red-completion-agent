#!/usr/bin/env python3
"""Regenerate prospective authenticated Red goal-manager assignments."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pokemon_red_completion.collection_protocol import (
    collection_document_sha256,
    working_source_bundle_sha256,
)
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_protocol import (
    GOAL_MANAGER_ACTOR,
    GOAL_MANAGER_ADAPTER_ID,
    GOAL_MANAGER_COLLECTION_ID,
    GOAL_MANAGER_EXECUTION_SCHEMA,
    GOAL_MANAGER_GAME_ID,
    GOAL_MANAGER_ONTOLOGY_ID,
    GOAL_MANAGER_POLICY_ID,
    GOAL_MANAGER_PRIMARY_NEED,
    GOAL_MANAGER_REGIME,
    GOAL_MANAGER_REGISTRY_DIGEST_RELATIVE_PATH,
    GOAL_MANAGER_REGISTRY_DIGEST_SCHEMA,
    GOAL_MANAGER_REGISTRY_RELATIVE_PATH,
    GOAL_MANAGER_REGISTRY_SCHEMA,
    goal_manager_contract_document,
    parse_goal_manager_registry,
)
from pokemon_red_completion.goal_manager_runtime import CompletionFirstGoalTeacher

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
    source_digest = working_source_bundle_sha256(ROOT)
    contract_digest = collection_document_sha256(goal_manager_contract_document())
    teacher_digest = collection_document_sha256(CompletionFirstGoalTeacher().public_dict())
    execution = {
        "decision_contract_sha256": contract_digest,
        "schema": GOAL_MANAGER_EXECUTION_SCHEMA,
        "source_bundle_sha256": source_digest,
        "teacher_configuration_sha256": teacher_digest,
    }
    execution["teacher_execution_sha256"] = collection_document_sha256(
        {
            "actor": GOAL_MANAGER_ACTOR,
            "adapter_id": GOAL_MANAGER_ADAPTER_ID,
            "collection_id": GOAL_MANAGER_COLLECTION_ID,
            "decision_contract_sha256": contract_digest,
            "game_id": GOAL_MANAGER_GAME_ID,
            "ontology_id": GOAL_MANAGER_ONTOLOGY_ID,
            "policy_id": GOAL_MANAGER_POLICY_ID,
            "schema": GOAL_MANAGER_EXECUTION_SCHEMA,
            "source_bundle_sha256": source_digest,
            "teacher_configuration_sha256": teacher_digest,
        }
    )
    slots: list[dict[str, object]] = []
    ordinal = 0
    for kind in GoalKind:
        for partition, count in (("train", 6), ("validation", 3)):
            for local_ordinal in range(1, count + 1):
                ordinal += 1
                slots.append(
                    {
                        "focus_kind": kind.value,
                        "focus_need": GOAL_MANAGER_PRIMARY_NEED[kind].value,
                        "harness_seed": 2_100_000 + ordinal,
                        "partition": partition,
                        "slot_id": (
                            f"red-goal-v1-{ordinal:03d}-{kind.value}-{partition}-"
                            f"{local_ordinal:02d}"
                        ),
                    }
                )
    document = {
        "adapter_id": GOAL_MANAGER_ADAPTER_ID,
        "collection_id": GOAL_MANAGER_COLLECTION_ID,
        "execution": execution,
        "game_id": GOAL_MANAGER_GAME_ID,
        "ontology_id": GOAL_MANAGER_ONTOLOGY_ID,
        "policy": {"actor": GOAL_MANAGER_ACTOR, "policy_id": GOAL_MANAGER_POLICY_ID},
        "regime": GOAL_MANAGER_REGIME,
        "schema": GOAL_MANAGER_REGISTRY_SCHEMA,
        "slots": slots,
    }
    payload = _canonical_line(document)
    parsed = parse_goal_manager_registry(payload)
    digest = hashlib.sha256(payload).hexdigest()
    if parsed.registry_sha256 != digest:
        raise RuntimeError("generated goal-manager registry failed canonical verification")
    digest_payload = _canonical_line(
        {
            "bytes": len(payload),
            "schema": GOAL_MANAGER_REGISTRY_DIGEST_SCHEMA,
            "sha256": digest,
        }
    )
    return payload, digest_payload, {
        "bytes": len(payload),
        "decision_contract_sha256": contract_digest,
        "registry_sha256": digest,
        "source_bundle_sha256": source_digest,
        "teacher_execution_sha256": execution["teacher_execution_sha256"],
        "train_slots": 54,
        "validation_slots": 27,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    payload, digest_payload, summary = _generated_payloads()
    registry_path = ROOT / GOAL_MANAGER_REGISTRY_RELATIVE_PATH
    digest_path = ROOT / GOAL_MANAGER_REGISTRY_DIGEST_RELATIVE_PATH
    if args.check:
        if (
            not registry_path.is_file()
            or not digest_path.is_file()
            or registry_path.read_bytes() != payload
            or digest_path.read_bytes() != digest_payload
        ):
            raise SystemExit("goal-manager collection registry is stale")
    else:
        registry_path.write_bytes(payload)
        digest_path.write_bytes(digest_payload)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
