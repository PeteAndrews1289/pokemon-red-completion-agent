from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from pokemon_red_completion.collection_ledger import (
    CollectionCampaignIdentity,
    CollectionLedgerError,
    CollectionOutcomeLedger,
    CollectionSlot,
)
from pokemon_red_completion.collection_protocol import (
    BATTLE_START_SCHEDULE_SCHEMA,
    POKEMON_CORE_ONTOLOGY_ID,
    POKEMON_RED_ADAPTER_ID,
    POKEMON_RED_GAME_ID,
    POKEMON_RED_TEACHER_ACTOR,
    POKEMON_RED_TEACHER_POLICY_ID,
    BattleStartOffset,
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


def _identity(*, registry: str = "a" * 64) -> CollectionCampaignIdentity:
    return CollectionCampaignIdentity(
        collection_id="red-battle-heldout-v1",
        registry_sha256=registry,
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


def _slots() -> tuple[CollectionSlot, ...]:
    partitions = ("train",) * 5 + ("validation",) * 2 + ("test",) * 5
    seen = {"train": 0, "validation": 0, "test": 0}
    totals = {"train": 5, "validation": 2, "test": 5}
    result: list[CollectionSlot] = []
    for collection_ordinal, partition in enumerate(partitions, start=1):
        seen[partition] += 1
        run_id = f"red-battle-v1-{collection_ordinal:02d}-{partition}"
        assignment_id = hashlib.sha256(run_id.encode("ascii")).hexdigest()
        offsets = (
            BattleStartOffset(
                f"battle-001-slot-{collection_ordinal:02d}",
                collection_ordinal,
            ),
            BattleStartOffset(
                f"battle-002-slot-{collection_ordinal:02d}",
                0,
            ),
        )
        result.append(
            CollectionSlot(
                assignment_id=assignment_id,
                episode_id=f"red-teacher-{assignment_id}",
                root_lineage_id=f"red-root-{assignment_id}",
                run_id=run_id,
                partition=partition,
                harness_seed=1000 + collection_ordinal,
                schedule_sha256=battle_start_offsets_sha256(offsets),
                offsets=offsets,
                battle_count=len(offsets),
                collection_ordinal=collection_ordinal,
                collection_total=12,
                partition_ordinal=seen[partition],
                partition_total=totals[partition],
            )
        )
    return tuple(result)


def _write_complete_episode(
    store,
    identity,
    slot: CollectionSlot,
    *,
    runtime_document: dict[str, object] | None = None,
) -> None:
    if runtime_document is None:
        runtime_document = _RUNTIME_DOCUMENT
    with store.begin_episode(slot.episode_id) as writer:
        writer.append(
            "episode",
            {
                "record_type": "episode",
                "trajectory_schema": "pokemon.trajectory.v1",
                "episode_id": slot.episode_id,
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
                    "objective_graph_sha256": identity.objective_graph_sha256,
                    "runtime_sha256": identity.runtime_sha256,
                    "runtime": runtime_document,
                    "rom_identity": {
                        "sha1": identity.rom_sha1,
                        "sha256": identity.rom_sha256,
                    },
                    "collection": {
                        "assistance_class": "teacher",
                        "attempt": {
                            "attempts_per_slot": 1,
                            "counted": True,
                        },
                        "assignment_id": slot.assignment_id,
                        "collection_id": identity.collection_id,
                        "collection_slot": {
                            "collection_ordinal": slot.collection_ordinal,
                            "collection_total": slot.collection_total,
                            "partition_ordinal": slot.partition_ordinal,
                            "partition_total": slot.partition_total,
                        },
                        "execution": {
                            "behavior_configuration_sha256": (
                                identity.behavior_configuration_sha256
                            ),
                            "objective_graph_sha256": identity.objective_graph_sha256,
                            "source_bundle_sha256": identity.source_bundle_sha256,
                            "teacher_execution_sha256": (
                                identity.teacher_execution_sha256
                            ),
                        },
                        "harness_seed": slot.harness_seed,
                        "human_input": False,
                        "perturbation_schedule": (
                            "preregistered_battle_start_offsets"
                        ),
                        "registry_sha256": identity.registry_sha256,
                        "run_id": slot.run_id,
                        "save_restore_used": False,
                        "schedule": {
                            "schedule_id": f"schedule-{slot.schedule_sha256}",
                            "schedule_sha256": slot.schedule_sha256,
                            "schema": BATTLE_START_SCHEDULE_SCHEMA,
                            "variation_id": (
                                f"variation-{slot.schedule_sha256}"
                            ),
                        },
                        "seed_protocol": "committed_harness_seed",
                        "start_type": "clean_power_on",
                    },
                    "configuration": {
                        "schema": "qualified-teacher-configuration-v2",
                        "behavior_configuration": _BEHAVIOR_DOCUMENT,
                        "behavior_configuration_sha256": (
                            identity.behavior_configuration_sha256
                        ),
                        "battle_start_schedule": {
                            "assignment_id": slot.assignment_id,
                            "offsets": [
                                offset.public_dict() for offset in slot.offsets
                            ],
                            "registry_sha256": identity.registry_sha256,
                            "schedule_sha256": slot.schedule_sha256,
                            "schema": BATTLE_START_SCHEDULE_SCHEMA,
                        }
                    },
                    "split": {
                        "partition": slot.partition,
                        "regime": "within_game",
                        "root_lineage_id": slot.root_lineage_id,
                    },
                },
            },
        )
        before_document = {"mode": "battle", "ordinal": 1}
        before = canonical_sha256(before_document)
        after = before
        zero = canonical_sha256({"mode": "battle", "ordinal": 2})
        writer.append(
            "snapshots",
            {
                "record_type": "snapshot",
                "snapshot_sha256": before,
                "snapshot": before_document,
            },
        )
        writer.append(
            "executions",
            {
                "record_type": "execution",
                "schema_version": 1,
                "execution_id": f"{slot.episode_id}:execution:1",
                "episode_id": slot.episode_id,
                "step_index": 1,
                "decision_id": None,
                "action": {
                    "kind": "wait",
                    "repeat": slot.offsets[0].frames,
                    "value": None,
                },
                "before_sha256": before,
                "after_sha256": after,
                "buttons": [],
                "frames": slot.offsets[0].frames,
                "status": "success",
                "error_type": None,
            },
        )
        for ordinal, (offset, step_index, execution_step, before_hash, after_hash) in enumerate(
            (
                (slot.offsets[0], 2, 1, before, after),
                (slot.offsets[1], 10, None, zero, zero),
            ),
            start=1,
        ):
            writer.append(
                "events",
                {
                    "record_type": "event",
                    "schema_version": 1,
                    "event_id": f"{slot.episode_id}:schedule:{ordinal}",
                    "episode_id": slot.episode_id,
                    "step_index": step_index,
                    "kind": "battle_start_offset_applied",
                    "payload": {
                        "after_snapshot_sha256": after_hash,
                        "battle_ordinal": ordinal,
                        "battle_plan_id": offset.battle_plan_id,
                        "before_snapshot_sha256": before_hash,
                        "execution_step_index": execution_step,
                        "frames": offset.frames,
                        "schedule_sha256": slot.schedule_sha256,
                    },
                },
            )
        writer.append(
            "events",
            {
                "record_type": "event",
                "schema_version": 1,
                "event_id": f"{slot.episode_id}:terminal",
                "episode_id": slot.episode_id,
                "step_index": 100,
                "kind": "terminal",
                "payload": {
                    "status": "complete",
                    "game_complete": True,
                    "qualified_through": "enter_hall_of_fame",
                    "battle_start_schedule": {
                        "complete": True,
                        "expected_battles": slot.battle_count,
                        "finished_battles": slot.battle_count,
                        "schedule_sha256": slot.schedule_sha256,
                    },
                },
            },
        )


def test_campaign_seal_and_pending_ledger_are_path_free_with_exact_denominators(
    tmp_path: Path,
) -> None:
    root, store = _make_store(tmp_path)
    identity = _identity()
    slots = _slots()

    with store.collection_session(identity.collection_id) as session:
        ledger = CollectionOutcomeLedger.open_or_seal(
            store=store,
            session=session,
            identity=identity,
            slots=slots,
        )
        receipt = ledger.public_receipt()

    assert receipt["declared_slots"] == 12
    assert receipt["counts"] == {
        "complete": 0,
        "failed": 0,
        "interrupted": 0,
        "invalid": 0,
        "pending": 12,
    }
    slot_records = receipt["slots"]
    assert isinstance(slot_records, list)
    assert slot_records[0]["slot"]["partition_ordinal"] == 1
    assert slot_records[4]["slot"]["partition_ordinal"] == 5
    assert slot_records[5]["slot"]["partition_ordinal"] == 1
    assert slot_records[6]["slot"]["partition_ordinal"] == 2
    assert slot_records[7]["slot"]["partition_ordinal"] == 1
    assert slot_records[-1]["slot"]["partition_ordinal"] == 5
    serialized = json.dumps(receipt, sort_keys=True)
    assert str(root) not in serialized
    assert "/Users/" not in serialized
    assert receipt["ledger_sha256"]


def test_reconcile_persists_complete_failed_and_power_loss_outcomes(
    tmp_path: Path,
) -> None:
    root, store = _make_store(tmp_path)
    identity = _identity()
    slots = _slots()
    complete_slot, failed_slot, interrupted_slot = slots[:3]
    _write_complete_episode(store, identity, complete_slot)

    with pytest.raises(RuntimeError, match="sanitized failure"), store.begin_episode(
        failed_slot.episode_id
    ) as writer:
        writer.append("events", {"kind": "started"})
        raise RuntimeError("sanitized failure /Users/example/rom.gb")
    store.begin_episode(interrupted_slot.episode_id)

    with store.collection_session(identity.collection_id) as session:
        ledger = CollectionOutcomeLedger.open_or_seal(
            store=store,
            session=session,
            identity=identity,
            slots=slots,
        )
        outcomes = ledger.reconcile()
        receipt = ledger.public_receipt()

    by_assignment = {outcome.slot.assignment_id: outcome for outcome in outcomes}
    assert by_assignment[complete_slot.assignment_id].status == "complete"
    assert by_assignment[complete_slot.assignment_id].game_complete is True
    assert (
        by_assignment[complete_slot.assignment_id].reason_code
        == "hall_of_fame_verified"
    )
    assert by_assignment[failed_slot.assignment_id].status == "failed"
    assert by_assignment[failed_slot.assignment_id].reason_code == "unhandled_exception"
    assert by_assignment[interrupted_slot.assignment_id].status == "interrupted"
    assert (
        by_assignment[interrupted_slot.assignment_id].reason_code
        == "process_interrupted"
    )
    assert receipt["counts"] == {
        "complete": 1,
        "failed": 1,
        "interrupted": 1,
        "invalid": 0,
        "pending": 9,
    }
    assert (root / f"{interrupted_slot.episode_id}.interrupted.partial").is_dir()
    serialized = json.dumps(receipt, sort_keys=True)
    assert "sanitized failure" not in serialized
    assert "/Users/" not in serialized
    for slot in (complete_slot, failed_slot, interrupted_slot):
        record = store.find_sealed_record(
            f"outcome-{slot.assignment_id}",
            expected_kind="collection_outcome",
        )
        assert record is not None
        assert record.read()["assignment_id"] == slot.assignment_id


def test_campaign_seal_is_keyed_by_collection_and_rejects_changed_identity(
    tmp_path: Path,
) -> None:
    _, store = _make_store(tmp_path)
    slots = _slots()
    identity = _identity()
    with store.collection_session(identity.collection_id) as session:
        CollectionOutcomeLedger.open_or_seal(
            store=store,
            session=session,
            identity=identity,
            slots=slots,
        )

    changed = _identity(registry="1" * 64)
    with (
        store.collection_session(changed.collection_id) as session,
        pytest.raises(CollectionLedgerError, match="different content"),
    ):
        CollectionOutcomeLedger.open_or_seal(
            store=store,
            session=session,
            identity=changed,
            slots=slots,
        )


def test_open_existing_is_read_only_when_campaign_has_not_started(
    tmp_path: Path,
) -> None:
    _, store = _make_store(tmp_path)
    identity = _identity()
    slots = _slots()

    with store.collection_session(identity.collection_id) as session:
        assert (
            CollectionOutcomeLedger.open_existing(
                store=store,
                session=session,
                identity=identity,
                slots=slots,
            )
            is None
        )

    assert (
        store.find_sealed_record(
            f"seal-{hashlib.sha256(identity.collection_id.encode('ascii')).hexdigest()}",
            expected_kind="collection_seal",
        )
        is None
    )


def test_open_existing_verifies_the_exact_identity_and_slot_roster(
    tmp_path: Path,
) -> None:
    _, store = _make_store(tmp_path)
    identity = _identity()
    slots = _slots()

    with store.collection_session(identity.collection_id) as session:
        CollectionOutcomeLedger.open_or_seal(
            store=store,
            session=session,
            identity=identity,
            slots=slots,
        )

    with store.collection_session(identity.collection_id) as session:
        existing = CollectionOutcomeLedger.open_existing(
            store=store,
            session=session,
            identity=identity,
            slots=slots,
        )
        assert existing is not None
        assert existing.public_receipt()["counts"]["pending"] == 12

    changed_offsets = (
        replace(slots[0].offsets[0], frames=slots[0].offsets[0].frames + 1),
        slots[0].offsets[1],
    )
    changed_slots = (
        replace(
            slots[0],
            offsets=changed_offsets,
            schedule_sha256=battle_start_offsets_sha256(changed_offsets),
        ),
        *slots[1:],
    )
    with (
        store.collection_session(identity.collection_id) as session,
        pytest.raises(CollectionLedgerError, match="contradicts"),
    ):
        CollectionOutcomeLedger.open_existing(
            store=store,
            session=session,
            identity=identity,
            slots=changed_slots,
        )


def test_reconcile_is_idempotent_and_require_pending_refuses_consumed_slot(
    tmp_path: Path,
) -> None:
    _, store = _make_store(tmp_path)
    identity = _identity()
    slots = _slots()
    slot = slots[0]
    _write_complete_episode(store, identity, slot)

    with store.collection_session(identity.collection_id) as session:
        ledger = CollectionOutcomeLedger.open_or_seal(
            store=store,
            session=session,
            identity=identity,
            slots=slots,
        )
        first = ledger.reconcile_slot(slot)
        second = ledger.reconcile_slot(slot)
        assert first == second
        with pytest.raises(CollectionLedgerError, match="already consumed"):
            ledger.require_pending(slot)
        ledger.require_pending(slots[1])


def test_complete_manifest_without_bound_hall_of_fame_evidence_is_invalid(
    tmp_path: Path,
) -> None:
    _, store = _make_store(tmp_path)
    identity = _identity()
    slots = _slots()
    slot = slots[0]
    with store.begin_episode(slot.episode_id) as writer:
        writer.append(
            "episode",
            {
                "record_type": "episode",
                "episode_id": slot.episode_id,
                "metadata": {"collection": {"assignment_id": slot.assignment_id}},
            },
        )
        writer.append(
            "events",
            {
                "episode_id": slot.episode_id,
                "kind": "terminal",
                "payload": {"status": "complete", "game_complete": True},
            },
        )

    with store.collection_session(identity.collection_id) as session:
        ledger = CollectionOutcomeLedger.open_or_seal(
            store=store,
            session=session,
            identity=identity,
            slots=slots,
        )
        outcome = ledger.reconcile_slot(slot)

    assert outcome is not None
    assert outcome.status == "invalid"
    assert outcome.game_complete is False
    assert outcome.reason_code == "invalid_campaign_identity"


def test_complete_episode_with_failed_schedule_audit_is_consumed_as_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pokemon_red_completion import collection_ledger
    from pokemon_red_completion.schedule_audit import ScheduleAttestationError

    _, store = _make_store(tmp_path)
    identity = _identity()
    slots = _slots()
    slot = slots[0]
    _write_complete_episode(store, identity, slot)
    monkeypatch.setattr(
        collection_ledger,
        "audit_schedule_attestations",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ScheduleAttestationError("forged schedule")
        ),
    )

    with store.collection_session(identity.collection_id) as session:
        ledger = CollectionOutcomeLedger.open_or_seal(
            store=store,
            session=session,
            identity=identity,
            slots=slots,
        )
        outcome = ledger.reconcile_slot(slot)

    assert outcome is not None
    assert outcome.status == "invalid"
    assert outcome.reason_code == "invalid_schedule_attestation"
    with store.collection_session(identity.collection_id) as session:
        ledger = CollectionOutcomeLedger.open_existing(
            store=store,
            session=session,
            identity=identity,
            slots=slots,
        )
        assert ledger is not None
        with pytest.raises(CollectionLedgerError, match="already consumed"):
            ledger.require_pending(slot)


def test_counted_completion_recomputes_the_runtime_document_digest(
    tmp_path: Path,
) -> None:
    _, store = _make_store(tmp_path)
    identity = _identity()
    slots = _slots()
    slot = slots[0]
    _write_complete_episode(
        store,
        identity,
        slot,
        runtime_document={"schema": "tampered-runtime"},
    )

    with store.collection_session(identity.collection_id) as session:
        ledger = CollectionOutcomeLedger.open_or_seal(
            store=store,
            session=session,
            identity=identity,
            slots=slots,
        )
        outcome = ledger.reconcile_slot(slot)

    assert outcome is not None
    assert outcome.status == "invalid"
    assert outcome.reason_code == "invalid_campaign_identity"


def test_ambiguous_episode_namespace_is_classified_invalid_and_never_reused(
    tmp_path: Path,
) -> None:
    root, store = _make_store(tmp_path)
    identity = _identity()
    slots = _slots()
    slot = slots[0]
    _write_complete_episode(store, identity, slot)
    (root / f"{slot.episode_id}.partial").mkdir(mode=0o700)

    with store.collection_session(identity.collection_id) as session:
        ledger = CollectionOutcomeLedger.open_or_seal(
            store=store,
            session=session,
            identity=identity,
            slots=slots,
        )
        outcome = ledger.reconcile_slot(slot)

    assert outcome is not None
    assert outcome.status == "invalid"
    assert outcome.reason_code == "ambiguous_episode_state"


def test_existing_outcome_must_match_the_episode_artifact(
    tmp_path: Path,
) -> None:
    _, store = _make_store(tmp_path)
    identity = _identity()
    slots = _slots()
    slot = slots[0]
    _write_complete_episode(store, identity, slot)
    store.publish_sealed_record(
        f"outcome-{slot.assignment_id}",
        kind="collection_outcome",
        record={
            "schema": "pokemon-red-collection-attempt-outcome-v1",
            "assignment_id": slot.assignment_id,
            "status": "failed",
        },
    )

    with (
        store.collection_session(identity.collection_id) as session,
        pytest.raises(CollectionLedgerError, match="contradicts"),
    ):
        ledger = CollectionOutcomeLedger.open_or_seal(
            store=store,
            session=session,
            identity=identity,
            slots=slots,
        )
        ledger.reconcile_slot(slot)
