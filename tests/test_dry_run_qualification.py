from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from pokemon_red_completion.collection_ledger import (
    CollectionCampaignIdentity,
    CollectionLedgerError,
    DryRunQualification,
    find_dry_run_qualification,
    publish_dry_run_qualification,
    require_dry_run_qualification,
)
from pokemon_red_completion.collection_protocol import (
    BATTLE_START_SCHEDULE_SCHEMA,
    POKEMON_CORE_ONTOLOGY_ID,
    POKEMON_RED_ADAPTER_ID,
    POKEMON_RED_GAME_ID,
    POKEMON_RED_TEACHER_ACTOR,
    POKEMON_RED_TEACHER_POLICY_ID,
    BattleStartOffset,
    ScheduleDryRun,
    battle_start_offsets_sha256,
    collection_document_sha256,
)
from pokemon_red_completion.private_artifacts import initialize_private_root
from pokemon_red_completion.trajectory import canonical_sha256


def _make_store(tmp_path: Path):
    repository = tmp_path / "repository"
    root = tmp_path / "private"
    repository.mkdir()
    root.mkdir()

    def device_id(path: Path) -> int:
        return 2 if path == root.resolve() else 1

    store = initialize_private_root(
        root,
        repository_root=repository,
        device_id=device_id,
        git_worktree_probe=lambda path: False,
    )
    return root, store


_RUNTIME_DOCUMENT = {
    "schema": "pokemon-red-runtime-identity-v1",
    "python": {"implementation": "CPython"},
    "pyboy": {"distribution_version": "2.7.0"},
}
_BEHAVIOR_DOCUMENT = {"schema": "test-teacher-behavior-v1"}


def _identity() -> CollectionCampaignIdentity:
    return CollectionCampaignIdentity(
        collection_id="red-battle-heldout-v1",
        registry_sha256="a" * 64,
        source_commit="1" * 40,
        source_bundle_sha256="b" * 64,
        behavior_configuration_sha256=collection_document_sha256(
            _BEHAVIOR_DOCUMENT
        ),
        objective_graph_sha256="2" * 64,
        teacher_execution_sha256="d" * 64,
        runtime_sha256=collection_document_sha256(_RUNTIME_DOCUMENT),
        rom_sha1="f" * 40,
        rom_sha256="0" * 64,
    )


def _dry_run(identity: CollectionCampaignIdentity) -> ScheduleDryRun:
    offsets = tuple(
        BattleStartOffset(
            f"battle-{ordinal:03d}-dry-run-test",
            0 if ordinal % 7 == 0 else ordinal % 17 + 1,
        )
        for ordinal in range(1, 64)
    )
    return ScheduleDryRun(
        dry_run_id="red-battle-schedule-dry-run-v1",
        registry_sha256=identity.registry_sha256,
        harness_seed=9101,
        schedule_sha256=battle_start_offsets_sha256(offsets),
        offsets=offsets,
    )


def _write_qualified_episode(
    store,
    identity: CollectionCampaignIdentity,
    dry_run: ScheduleDryRun,
    *,
    episode_id: str = "red-dry-run-qualified",
    tamper_attestation: bool = False,
    runtime_document: dict[str, object] | None = None,
) -> str:
    if runtime_document is None:
        runtime_document = _RUNTIME_DOCUMENT
    with store.begin_episode(episode_id) as writer:
        writer.append(
            "episode",
            {
                "record_type": "episode",
                "trajectory_schema": "pokemon.trajectory.v1",
                "episode_id": episode_id,
                "game_id": POKEMON_RED_GAME_ID,
                "metadata": {
                    "adapter_id": POKEMON_RED_ADAPTER_ID,
                    "ontology_id": POKEMON_CORE_ONTOLOGY_ID,
                    "policy": {
                        "actor": POKEMON_RED_TEACHER_ACTOR,
                        "policy_id": POKEMON_RED_TEACHER_POLICY_ID,
                    },
                    "source": {
                        "git_commit": identity.source_commit,
                        "worktree_dirty": False,
                    },
                    "source_bundle_sha256": identity.source_bundle_sha256,
                    "runtime": runtime_document,
                    "runtime_sha256": identity.runtime_sha256,
                    "rom_identity": {
                        "sha1": identity.rom_sha1,
                        "sha256": identity.rom_sha256,
                    },
                    "objective_graph_sha256": identity.objective_graph_sha256,
                    "configuration": {
                        "schema": "qualified-teacher-configuration-v2",
                        "behavior_configuration": _BEHAVIOR_DOCUMENT,
                        "behavior_configuration_sha256": (
                            identity.behavior_configuration_sha256
                        ),
                        "battle_start_schedule": {
                            "dry_run_id": dry_run.dry_run_id,
                            "offsets": [
                                offset.public_dict() for offset in dry_run.offsets
                            ],
                            "purpose": "schedule_integration_dry_run",
                            "registry_sha256": identity.registry_sha256,
                            "schedule_sha256": dry_run.schedule_sha256,
                            "schema": BATTLE_START_SCHEDULE_SCHEMA,
                            "teacher_execution_sha256": (
                                identity.teacher_execution_sha256
                            ),
                        },
                    },
                    "collection": {
                        "assistance_class": "teacher",
                        "attempt": {"counted": False},
                        "dry_run_id": dry_run.dry_run_id,
                        "execution": {
                            "behavior_configuration_sha256": (
                                identity.behavior_configuration_sha256
                            ),
                            "objective_graph_sha256": (
                                identity.objective_graph_sha256
                            ),
                            "source_bundle_sha256": identity.source_bundle_sha256,
                            "teacher_execution_sha256": (
                                identity.teacher_execution_sha256
                            ),
                        },
                        "harness_seed": dry_run.harness_seed,
                        "human_input": False,
                        "perturbation_schedule": (
                            "fixed_schedule_integration_dry_run"
                        ),
                        "purpose": "schedule_integration_dry_run",
                        "registry_sha256": identity.registry_sha256,
                        "save_restore_used": False,
                        "schedule": {
                            "schedule_sha256": dry_run.schedule_sha256,
                            "schema": BATTLE_START_SCHEDULE_SCHEMA,
                        },
                        "seed_protocol": "committed_diagnostic_harness_seed",
                        "start_type": "clean_power_on",
                    },
                    "split": {
                        "partition": "unassigned",
                        "regime": "within_game",
                        "root_lineage_id": episode_id,
                    },
                },
            },
        )

        step_index = 1
        for ordinal, offset in enumerate(dry_run.offsets, start=1):
            snapshot_document = {
                "mode": "battle",
                "ordinal": ordinal,
            }
            snapshot_sha256 = canonical_sha256(snapshot_document)
            execution_step_index: int | None = None
            if offset.frames > 0:
                execution_step_index = step_index
                writer.append(
                    "snapshots",
                    {
                        "record_type": "snapshot",
                        "snapshot_sha256": snapshot_sha256,
                        "snapshot": snapshot_document,
                    },
                )
                writer.append(
                    "executions",
                    {
                        "record_type": "execution",
                        "schema_version": 1,
                        "execution_id": (
                            f"{episode_id}:execution:{execution_step_index}"
                        ),
                        "episode_id": episode_id,
                        "step_index": execution_step_index,
                        "decision_id": None,
                        "action": {
                            "kind": "wait",
                            "repeat": offset.frames,
                            "value": None,
                        },
                        "before_sha256": snapshot_sha256,
                        "after_sha256": snapshot_sha256,
                        "buttons": [],
                        "frames": offset.frames,
                        "status": "success",
                        "error_type": None,
                    },
                )
                step_index += 1
            event_frames = (
                offset.frames + 1
                if tamper_attestation and ordinal == 1
                else offset.frames
            )
            writer.append(
                "events",
                {
                    "record_type": "event",
                    "schema_version": 1,
                    "event_id": f"{episode_id}:schedule:{ordinal}",
                    "episode_id": episode_id,
                    "step_index": step_index,
                    "kind": "battle_start_offset_applied",
                    "payload": {
                        "after_snapshot_sha256": snapshot_sha256,
                        "battle_ordinal": ordinal,
                        "battle_plan_id": offset.battle_plan_id,
                        "before_snapshot_sha256": snapshot_sha256,
                        "execution_step_index": execution_step_index,
                        "frames": event_frames,
                        "schedule_sha256": dry_run.schedule_sha256,
                    },
                },
            )
            step_index += 1

        writer.append(
            "events",
            {
                "record_type": "event",
                "schema_version": 1,
                "event_id": f"{episode_id}:terminal",
                "episode_id": episode_id,
                "step_index": step_index,
                "kind": "terminal",
                "payload": {
                    "status": "complete",
                    "game_complete": True,
                    "qualified_through": "enter_hall_of_fame",
                    "battle_start_schedule": {
                        "complete": True,
                        "expected_battles": len(dry_run.offsets),
                        "finished_battles": len(dry_run.offsets),
                        "schedule_sha256": dry_run.schedule_sha256,
                    },
                },
            },
        )
    return episode_id


def _rewrite_stream_and_manifest(
    root: Path,
    episode_id: str,
    stream: str,
    mutation,
) -> None:
    episode_root = root / episode_id
    stream_path = episode_root / f"{stream}.jsonl"
    records = [
        json.loads(line)
        for line in stream_path.read_text(encoding="ascii").splitlines()
    ]
    mutation(records)
    payload = b"".join(_canonical_json_line(record) for record in records)
    stream_path.write_bytes(payload)

    manifest_path = episode_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    for entry in manifest["files"]:
        if entry["filename"] == stream_path.name:
            entry["bytes"] = len(payload)
            entry["sha256"] = hashlib.sha256(payload).hexdigest()
            entry["records"] = len(records)
            break
    else:  # pragma: no cover - the fixture always created the stream
        raise AssertionError("fixture stream is absent from its manifest")
    manifest["totals"]["bytes"] = sum(entry["bytes"] for entry in manifest["files"])
    manifest["totals"]["records"] = sum(
        entry["records"] for entry in manifest["files"]
    )
    manifest_path.write_bytes(_canonical_json_line(manifest))


def _canonical_json_line(value: Any) -> bytes:
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


def test_publish_find_and_require_a_complete_dry_run(
    tmp_path: Path,
) -> None:
    _, store = _make_store(tmp_path)
    identity = _identity()
    dry_run = _dry_run(identity)
    episode_id = _write_qualified_episode(store, identity, dry_run)

    published = publish_dry_run_qualification(
        store,
        identity,
        dry_run,
        episode_id,
    )
    found = find_dry_run_qualification(store, identity, dry_run)
    required = require_dry_run_qualification(store, identity, dry_run)

    assert isinstance(published, DryRunQualification)
    assert found == published
    assert required == published
    receipt = published.public_dict()
    assert receipt["collection_id"] == identity.collection_id
    assert receipt["registry_sha256"] == identity.registry_sha256
    assert receipt["source_commit"] == identity.source_commit
    assert receipt["teacher_execution_sha256"] == (
        identity.teacher_execution_sha256
    )
    assert receipt["dry_run_id"] == dry_run.dry_run_id
    assert receipt["harness_seed"] == dry_run.harness_seed
    assert receipt["schedule_sha256"] == dry_run.schedule_sha256
    assert receipt["battle_count"] == 63
    assert receipt["schedule_attestation"]["expected_battles"] == 63
    assert receipt["schedule_attestation"]["attested_battles"] == 63
    assert receipt["schedule_attestation"]["complete"] is True
    assert receipt["episode_id"] == episode_id
    assert receipt["episode_manifest_sha256"] == (
        store.open_episode(episode_id).summary.manifest_sha256
    )
    assert receipt["status"] == "qualified"


def test_absent_dry_run_is_not_implicitly_qualified(tmp_path: Path) -> None:
    _, store = _make_store(tmp_path)
    identity = _identity()
    dry_run = _dry_run(identity)

    assert find_dry_run_qualification(store, identity, dry_run) is None
    with pytest.raises(CollectionLedgerError):
        require_dry_run_qualification(store, identity, dry_run)


def test_qualification_rejects_a_different_campaign_identity(
    tmp_path: Path,
) -> None:
    _, store = _make_store(tmp_path)
    identity = _identity()
    dry_run = _dry_run(identity)
    episode_id = _write_qualified_episode(store, identity, dry_run)
    publish_dry_run_qualification(store, identity, dry_run, episode_id)
    changed_identity = replace(identity, runtime_sha256="9" * 64)

    assert find_dry_run_qualification(store, changed_identity, dry_run) is None
    with pytest.raises(CollectionLedgerError):
        require_dry_run_qualification(store, changed_identity, dry_run)


def test_publish_rejects_a_forged_schedule_attestation(
    tmp_path: Path,
) -> None:
    _, store = _make_store(tmp_path)
    identity = _identity()
    dry_run = _dry_run(identity)
    episode_id = _write_qualified_episode(
        store,
        identity,
        dry_run,
        tamper_attestation=True,
    )

    with pytest.raises(CollectionLedgerError):
        publish_dry_run_qualification(store, identity, dry_run, episode_id)
    assert find_dry_run_qualification(store, identity, dry_run) is None


def test_publish_recomputes_the_runtime_document_digest(tmp_path: Path) -> None:
    _, store = _make_store(tmp_path)
    identity = _identity()
    dry_run = _dry_run(identity)
    episode_id = _write_qualified_episode(
        store,
        identity,
        dry_run,
        runtime_document={"schema": "tampered-runtime"},
    )

    with pytest.raises(CollectionLedgerError):
        publish_dry_run_qualification(store, identity, dry_run, episode_id)


def test_require_rejects_a_resealed_replacement_episode(
    tmp_path: Path,
) -> None:
    root, store = _make_store(tmp_path)
    identity = _identity()
    dry_run = _dry_run(identity)
    episode_id = _write_qualified_episode(store, identity, dry_run)
    qualification = publish_dry_run_qualification(
        store,
        identity,
        dry_run,
        episode_id,
    )

    def add_unreferenced_header_value(records: list[dict[str, Any]]) -> None:
        records[0]["metadata"]["post_qualification_replacement"] = True

    _rewrite_stream_and_manifest(
        root,
        episode_id,
        "episode",
        add_unreferenced_header_value,
    )
    assert (
        store.open_episode(episode_id).summary.manifest_sha256
        != qualification.public_dict()["episode_manifest_sha256"]
    )

    with pytest.raises(CollectionLedgerError):
        find_dry_run_qualification(store, identity, dry_run)
    with pytest.raises(CollectionLedgerError):
        require_dry_run_qualification(store, identity, dry_run)


def test_publish_is_idempotent_for_the_same_episode(tmp_path: Path) -> None:
    _, store = _make_store(tmp_path)
    identity = _identity()
    dry_run = _dry_run(identity)
    episode_id = _write_qualified_episode(store, identity, dry_run)

    first = publish_dry_run_qualification(store, identity, dry_run, episode_id)
    second = publish_dry_run_qualification(store, identity, dry_run, episode_id)

    assert second == first
    assert find_dry_run_qualification(store, identity, dry_run) == first


def test_qualification_receipt_is_path_free(tmp_path: Path) -> None:
    root, store = _make_store(tmp_path)
    identity = _identity()
    dry_run = _dry_run(identity)
    episode_id = _write_qualified_episode(store, identity, dry_run)

    receipt = publish_dry_run_qualification(
        store,
        identity,
        dry_run,
        episode_id,
    ).public_dict()
    serialized = json.dumps(receipt, ensure_ascii=True, sort_keys=True)

    assert str(root) not in serialized
    assert str(tmp_path) not in serialized
    assert "/Users/" not in serialized
    assert "private_path" not in receipt
