from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.goal_manager_protocol import parse_goal_manager_registry
from pokemon_red_completion.multi_goal_curriculum_inventory import (
    MULTI_GOAL_LINEAGE_MANIFEST_SCHEMA,
    MultiGoalCurriculumInventoryError,
    audit_multi_goal_curriculum_inventory,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")
        + b"\n"
    )


def _fixture(monkeypatch):  # type: ignore[no-untyped-def]
    registry = parse_goal_manager_registry(
        (PROJECT_ROOT / "configs/red-goal-manager-collection-v1.json").read_bytes()
    )
    registry = replace(
        registry,
        execution=replace(registry.execution, source_commit="a" * 40),
    )
    files: dict[str, bytes] = {}
    plan_entries: list[dict[str, str]] = []
    profile_entries: list[dict[str, object]] = []
    parsed: dict[bytes, str] = {}
    for index, slot in enumerate(registry.slots):
        state_location = f"state:{slot.slot_id}"
        envelope_location = f"envelope:{slot.slot_id}"
        profile_location = f"profile:{slot.slot_id}"
        state = f"state-{index}".encode("ascii")
        envelope = f"envelope-{index}".encode("ascii")
        profile = f"profile-{index}".encode("ascii")
        files[state_location] = state
        files[envelope_location] = envelope
        files[profile_location] = profile
        parsed[envelope] = slot.slot_id
        parsed[profile] = slot.slot_id
        plan_entries.append(
            {
                "envelope": envelope_location,
                "profile": profile_location,
                "slot_id": slot.slot_id,
                "state": state_location,
            }
        )
        profile_entries.append(
            {
                "envelope_file_sha256": hashlib.sha256(envelope).hexdigest(),
                "output_profile_sha256": hashlib.sha256(profile).hexdigest(),
                "slot_id": slot.slot_id,
                "source_profile_sha256": hashlib.sha256(profile).hexdigest(),
                "state_file_sha256": hashlib.sha256(state).hexdigest(),
                "transformed": index < 4,
            }
        )
    plan = _canonical(
        {
            "entries": plan_entries,
            "registry_sha256": registry.registry_sha256,
            "schema": "pokemon-red-private-goal-manager-context-plan-v1",
            "source_commit": "a" * 40,
        }
    )
    profile_lineage = _canonical(
        {
            "builder_runner_sha256": "1" * 64,
            "builder_source_bundle_sha256": "2" * 64,
            "builder_source_commit": "b" * 40,
            "context_catalog_sha256": "3" * 64,
            "entries": profile_entries,
            "output_plan_sha256": hashlib.sha256(plan).hexdigest(),
            "paired_plan_sha256": "4" * 64,
            "prior_campaign_sha256": ["5" * 64],
            "schema": "pokemon.red.acquisition-replanning-profile-lineage.v1",
            "source_plan_sha256": "6" * 64,
            "source_profile_manifest_sha256": "7" * 64,
        }
    )

    def captured(payload: bytes, *, state_bytes: bytes):  # type: ignore[no-untyped-def]
        return SimpleNamespace(
            checkpoint_id=parsed[payload],
            state_sha256=hashlib.sha256(state_bytes).hexdigest(),
        )

    def profile(payload: bytes):  # type: ignore[no-untyped-def]
        slot_id = parsed[payload]
        assignment = registry.assignment(slot_id)
        return SimpleNamespace(
            profile_id=slot_id,
            providers=(SimpleNamespace(kind=assignment.focus_kind),),
        )

    monkeypatch.setattr(
        "pokemon_red_completion.multi_goal_curriculum_inventory.parse_captured_progress",
        captured,
    )
    monkeypatch.setattr(
        "pokemon_red_completion.multi_goal_curriculum_inventory.parse_red_goal_context_profile",
        profile,
    )
    return registry, files, plan, profile_lineage, profile_entries


def _manifest(registry, plan, profile_lineage, profile_entries):  # type: ignore[no-untyped-def]
    rows = []
    for index, (slot, hashes) in enumerate(
        zip(registry.slots, profile_entries, strict=True)
    ):
        rows.append(
            {
                "envelope_file_sha256": hashes["envelope_file_sha256"],
                "evidence_kind": "prospective-independent-root-v1",
                "focus_kind": slot.focus_kind.value,
                "partition": (
                    "development" if slot.partition == "validation" else "train"
                ),
                "physical_root_sha256": hashlib.sha256(
                    f"root-{index}".encode("ascii")
                ).hexdigest(),
                "profile_file_sha256": hashes["output_profile_sha256"],
                "slot_id": slot.slot_id,
                "state_file_sha256": hashes["state_file_sha256"],
                "upstream_lineage_sha256": hashlib.sha256(
                    f"lineage-{index}".encode("ascii")
                ).hexdigest(),
            }
        )
    return {
        "entries": rows,
        "plan_sha256": hashlib.sha256(plan).hexdigest(),
        "profile_lineage_sha256": hashlib.sha256(profile_lineage).hexdigest(),
        "schema": MULTI_GOAL_LINEAGE_MANIFEST_SCHEMA,
    }


def test_inventory_keeps_unique_states_separate_from_verified_lineage(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    registry, files, plan, profile_lineage, _entries = _fixture(monkeypatch)

    result = audit_multi_goal_curriculum_inventory(
        plan_payload=plan,
        profile_lineage_payload=profile_lineage,
        registry=registry,
        read_file=files.__getitem__,
    )
    public = result.public_dict()

    assert result.unique_state_files == 81
    assert result.verified_lineage_entries == 0
    assert result.train_lineage_deficit == 8
    assert result.development_lineage_deficit == 4
    assert result.lineage_overlap_evaluated is False
    assert result.claim_availability_evaluated is False
    assert public["calibration_contexts_available"] == 81
    assert public["held_development_claim_allowed"] is False
    assert public["controller_actions"] == 0
    assert public["model_predictions"] == 0
    assert "/" not in json.dumps(public)


def test_complete_disjoint_lineage_manifest_opens_bounded_collection(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    registry, files, plan, profile_lineage, entries = _fixture(monkeypatch)
    manifest = _manifest(registry, plan, profile_lineage, entries)

    result = audit_multi_goal_curriculum_inventory(
        plan_payload=plan,
        profile_lineage_payload=profile_lineage,
        registry=registry,
        read_file=files.__getitem__,
        lineage_manifest_payload=_canonical(manifest),
        root_is_available=lambda _state, _envelope: True,
    )

    assert result.ready_for_outcome_collection is True
    assert result.verified_train_lineages == 54
    assert result.verified_development_lineages == 27
    assert result.verified_train_goal_families == 9
    assert result.verified_development_goal_families == 9
    assert result.lineage_overlap_evaluated is True
    assert result.claim_availability_evaluated is True
    assert result.open_root_count == 81


def test_cross_partition_lineage_overlap_is_reported_not_hidden(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    registry, files, plan, profile_lineage, entries = _fixture(monkeypatch)
    manifest = _manifest(registry, plan, profile_lineage, entries)
    train = manifest["entries"][0]
    development = next(
        row for row in manifest["entries"] if row["partition"] == "development"
    )
    development["upstream_lineage_sha256"] = train["upstream_lineage_sha256"]

    result = audit_multi_goal_curriculum_inventory(
        plan_payload=plan,
        profile_lineage_payload=profile_lineage,
        registry=registry,
        read_file=files.__getitem__,
        lineage_manifest_payload=_canonical(manifest),
    )

    assert result.ready_for_outcome_collection is False
    assert result.cross_partition_lineage_overlap == 1
    assert "cross_partition_upstream_lineage_overlap" in result.reasons


def test_manifest_rejects_learning_results_before_inventory(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    registry, files, plan, profile_lineage, entries = _fixture(monkeypatch)
    manifest = _manifest(registry, plan, profile_lineage, entries)
    manifest["outcomes"] = []

    with pytest.raises(
        MultiGoalCurriculumInventoryError,
        match="prohibited learning-result field",
    ):
        audit_multi_goal_curriculum_inventory(
            plan_payload=plan,
            profile_lineage_payload=profile_lineage,
            registry=registry,
            read_file=files.__getitem__,
            lineage_manifest_payload=_canonical(manifest),
        )
