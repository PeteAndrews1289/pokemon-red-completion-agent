"""Immutable, path-free accounting for preregistered collection attempts."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass

from pokemon_red_completion.collection_protocol import (
    BATTLE_START_SCHEDULE_SCHEMA,
    POKEMON_CORE_ONTOLOGY_ID,
    POKEMON_RED_ADAPTER_ID,
    POKEMON_RED_TEACHER_ACTOR,
    POKEMON_RED_TEACHER_POLICY_ID,
    BattleStartOffset,
    CollectionProtocolError,
    ScheduleDryRun,
    battle_start_offsets_sha256,
    collection_document_sha256,
)
from pokemon_red_completion.private_artifacts import (
    CollectionSession,
    EpisodeArtifactState,
    PrivateArtifactError,
    PrivateArtifactRoot,
)
from pokemon_red_completion.schedule_audit import (
    ScheduleAttestation,
    ScheduleAttestationError,
    audit_schedule_attestations,
)

CAMPAIGN_SEAL_SCHEMA = "pokemon-red-collection-campaign-seal-v1"
DRY_RUN_QUALIFICATION_SCHEMA = "pokemon-red-schedule-dry-run-qualification-v1"
ATTEMPT_OUTCOME_SCHEMA = "pokemon-red-collection-attempt-outcome-v1"
OUTCOME_LEDGER_SCHEMA = "pokemon-red-collection-outcome-ledger-v1"

_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,79}\Z")
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_PARTITIONS = {"test", "train", "validation"}
_TERMINAL_STATUSES = {"complete", "failed", "interrupted", "invalid"}


class CollectionLedgerError(RuntimeError):
    """Raised when an attempt cannot be accounted for without weakening the protocol."""


@dataclass(frozen=True, slots=True)
class CollectionCampaignIdentity:
    """Identity that every declared slot in one campaign must share."""

    collection_id: str
    registry_sha256: str
    source_commit: str
    source_bundle_sha256: str
    behavior_configuration_sha256: str
    objective_graph_sha256: str
    teacher_execution_sha256: str
    runtime_sha256: str
    rom_sha1: str
    rom_sha256: str

    def __post_init__(self) -> None:
        _require_safe_id(self.collection_id, subject="collection identity")
        if (
            not isinstance(self.source_commit, str)
            or _GIT_OID.fullmatch(self.source_commit) is None
        ):
            raise CollectionLedgerError("source commit must be a lowercase Git object ID")
        for value, subject in (
            (self.registry_sha256, "registry digest"),
            (self.source_bundle_sha256, "source bundle digest"),
            (self.behavior_configuration_sha256, "behavior configuration digest"),
            (self.objective_graph_sha256, "objective graph digest"),
            (self.teacher_execution_sha256, "teacher execution digest"),
            (self.runtime_sha256, "runtime digest"),
            (self.rom_sha256, "ROM SHA-256"),
        ):
            _require_sha256(value, subject=subject)
        if not isinstance(self.rom_sha1, str) or _SHA1.fullmatch(self.rom_sha1) is None:
            raise CollectionLedgerError("ROM SHA-1 must be a lowercase digest")

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": CAMPAIGN_SEAL_SCHEMA,
            "collection_id": self.collection_id,
            "registry_sha256": self.registry_sha256,
            "source_commit": self.source_commit,
            "source_bundle_sha256": self.source_bundle_sha256,
            "behavior_configuration_sha256": self.behavior_configuration_sha256,
            "objective_graph_sha256": self.objective_graph_sha256,
            "teacher_execution_sha256": self.teacher_execution_sha256,
            "runtime_sha256": self.runtime_sha256,
            "rom_sha1": self.rom_sha1,
            "rom_sha256": self.rom_sha256,
        }


@dataclass(frozen=True, slots=True)
class CollectionSlot:
    """One predeclared, single-attempt collection namespace."""

    assignment_id: str
    episode_id: str
    root_lineage_id: str
    run_id: str
    partition: str
    harness_seed: int
    schedule_sha256: str
    offsets: tuple[BattleStartOffset, ...]
    battle_count: int
    collection_ordinal: int
    collection_total: int
    partition_ordinal: int
    partition_total: int

    def __post_init__(self) -> None:
        _require_sha256(self.assignment_id, subject="assignment identity")
        _require_safe_id(self.episode_id, subject="episode identity")
        _require_safe_id(self.root_lineage_id, subject="root lineage identity")
        _require_safe_id(self.run_id, subject="run identity")
        _require_sha256(self.schedule_sha256, subject="battle schedule digest")
        if (
            not isinstance(self.offsets, tuple)
            or not self.offsets
            or not all(isinstance(offset, BattleStartOffset) for offset in self.offsets)
        ):
            raise CollectionLedgerError("battle schedule offsets are invalid")
        if battle_start_offsets_sha256(self.offsets) != self.schedule_sha256:
            raise CollectionLedgerError("battle schedule digest does not match its offsets")
        if self.partition not in _PARTITIONS:
            raise CollectionLedgerError("collection partition is unsupported")
        if (
            isinstance(self.harness_seed, bool)
            or not isinstance(self.harness_seed, int)
            or not 0 <= self.harness_seed <= (1 << 64) - 1
        ):
            raise CollectionLedgerError("collection harness seed must be a uint64")
        if (
            isinstance(self.battle_count, bool)
            or not isinstance(self.battle_count, int)
            or self.battle_count <= 0
        ):
            raise CollectionLedgerError("battle count must be a positive integer")
        if self.battle_count != len(self.offsets):
            raise CollectionLedgerError("battle count does not match the schedule")
        for value, subject in (
            (self.collection_ordinal, "collection ordinal"),
            (self.collection_total, "collection total"),
            (self.partition_ordinal, "partition ordinal"),
            (self.partition_total, "partition total"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise CollectionLedgerError(f"{subject} must be a positive integer")
        if self.collection_ordinal > self.collection_total:
            raise CollectionLedgerError("collection ordinal exceeds its total")
        if self.partition_ordinal > self.partition_total:
            raise CollectionLedgerError("partition ordinal exceeds its total")

    def public_dict(self) -> dict[str, object]:
        return {
            "assignment_id": self.assignment_id,
            "episode_id": self.episode_id,
            "root_lineage_id": self.root_lineage_id,
            "run_id": self.run_id,
            "partition": self.partition,
            "harness_seed": self.harness_seed,
            "schedule": {
                "battle_count": self.battle_count,
                "schedule_sha256": self.schedule_sha256,
            },
            "slot": {
                "collection_ordinal": self.collection_ordinal,
                "collection_total": self.collection_total,
                "partition_ordinal": self.partition_ordinal,
                "partition_total": self.partition_total,
            },
        }


@dataclass(frozen=True, slots=True)
class DryRunQualification:
    """Immutable proof that the frozen schedule harness completed before collection."""

    identity: CollectionCampaignIdentity
    dry_run_id: str
    harness_seed: int
    schedule_sha256: str
    battle_count: int
    episode_id: str
    episode_manifest_sha256: str
    attestation: ScheduleAttestation

    def __post_init__(self) -> None:
        if not isinstance(self.identity, CollectionCampaignIdentity):
            raise TypeError("identity must be a CollectionCampaignIdentity")
        _require_safe_id(self.dry_run_id, subject="dry-run identity")
        if (
            isinstance(self.harness_seed, bool)
            or not isinstance(self.harness_seed, int)
            or self.harness_seed < 0
            or self.harness_seed > (1 << 64) - 1
        ):
            raise CollectionLedgerError("dry-run harness seed must be a uint64")
        _require_sha256(self.schedule_sha256, subject="dry-run schedule digest")
        if (
            isinstance(self.battle_count, bool)
            or not isinstance(self.battle_count, int)
            or self.battle_count <= 0
        ):
            raise CollectionLedgerError("dry-run battle count must be positive")
        _require_safe_id(self.episode_id, subject="dry-run episode identity")
        _require_sha256(
            self.episode_manifest_sha256,
            subject="dry-run episode manifest digest",
        )
        if not isinstance(self.attestation, ScheduleAttestation):
            raise TypeError("attestation must be a ScheduleAttestation")
        if (
            self.attestation.schedule_sha256 != self.schedule_sha256
            or self.attestation.expected_battles != self.battle_count
            or self.attestation.attested_battles != self.battle_count
        ):
            raise CollectionLedgerError(
                "dry-run schedule attestation does not prove full completion"
            )

    def public_dict(self) -> dict[str, object]:
        identity = self.identity.public_dict()
        del identity["schema"]
        return {
            "schema": DRY_RUN_QUALIFICATION_SCHEMA,
            **identity,
            "dry_run_id": self.dry_run_id,
            "harness_seed": self.harness_seed,
            "schedule_sha256": self.schedule_sha256,
            "battle_count": self.battle_count,
            "episode_id": self.episode_id,
            "episode_manifest_sha256": self.episode_manifest_sha256,
            "status": "qualified",
            "schedule_attestation": self.attestation.public_dict(),
        }


@dataclass(frozen=True, slots=True)
class CollectionAttemptOutcome:
    """One immutable terminal classification for a declared slot."""

    identity: CollectionCampaignIdentity
    slot: CollectionSlot
    status: str
    reason_code: str
    game_complete: bool
    episode_manifest_sha256: str | None

    def __post_init__(self) -> None:
        if self.status not in _TERMINAL_STATUSES:
            raise CollectionLedgerError("attempt outcome status is unsupported")
        _require_safe_id(self.reason_code, subject="attempt outcome reason")
        if not isinstance(self.game_complete, bool):
            raise CollectionLedgerError("attempt completion flag must be boolean")
        if self.game_complete != (self.status == "complete"):
            raise CollectionLedgerError("attempt completion flag contradicts its status")
        if self.episode_manifest_sha256 is not None:
            _require_sha256(
                self.episode_manifest_sha256,
                subject="episode manifest digest",
            )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": ATTEMPT_OUTCOME_SCHEMA,
            "collection_id": self.identity.collection_id,
            "registry_sha256": self.identity.registry_sha256,
            "source_commit": self.identity.source_commit,
            "teacher_execution_sha256": self.identity.teacher_execution_sha256,
            **self.slot.public_dict(),
            "attempts_per_slot": 1,
            "status": self.status,
            "reason_code": self.reason_code,
            "game_complete": self.game_complete,
            "episode_manifest_sha256": self.episode_manifest_sha256,
        }


class CollectionOutcomeLedger:
    """Reconcile deterministic episode artifacts into write-once outcome records."""

    __slots__ = ("_identity", "_session", "_slots", "_store")

    def __init__(
        self,
        *,
        store: PrivateArtifactRoot,
        session: CollectionSession,
        identity: CollectionCampaignIdentity,
        slots: tuple[CollectionSlot, ...],
        _seal: bool = True,
    ) -> None:
        if not isinstance(store, PrivateArtifactRoot):
            raise TypeError("store must be a PrivateArtifactRoot")
        if not isinstance(session, CollectionSession):
            raise TypeError("session must be a CollectionSession")
        if not isinstance(identity, CollectionCampaignIdentity):
            raise TypeError("identity must be a CollectionCampaignIdentity")
        session.require_store(store)
        if session.collection_id != identity.collection_id:
            raise CollectionLedgerError("collection session identity does not match the campaign")
        self._validate_slots(slots)
        self._store = store
        self._session = session
        self._identity = identity
        self._slots = slots

        if not _seal:
            return
        try:
            self._store.publish_sealed_record(
                _campaign_seal_record_id(identity.collection_id),
                kind="collection_seal",
                record=self._campaign_record(),
            )
        except PrivateArtifactError as error:
            raise CollectionLedgerError(str(error)) from None

    @classmethod
    def open_or_seal(
        cls,
        *,
        store: PrivateArtifactRoot,
        session: CollectionSession,
        identity: CollectionCampaignIdentity,
        slots: tuple[CollectionSlot, ...],
    ) -> CollectionOutcomeLedger:
        """Open the exact campaign seal, creating it before any attempt if absent."""

        return cls(
            store=store,
            session=session,
            identity=identity,
            slots=slots,
        )

    @classmethod
    def open_existing(
        cls,
        *,
        store: PrivateArtifactRoot,
        session: CollectionSession,
        identity: CollectionCampaignIdentity,
        slots: tuple[CollectionSlot, ...],
    ) -> CollectionOutcomeLedger | None:
        """Open and verify an existing campaign seal without creating one."""

        ledger = cls(
            store=store,
            session=session,
            identity=identity,
            slots=slots,
            _seal=False,
        )
        try:
            stored = store.find_sealed_record(
                _campaign_seal_record_id(identity.collection_id),
                expected_kind="collection_seal",
            )
            if stored is None:
                return None
            if stored.read() != ledger._campaign_record():
                raise CollectionLedgerError(
                    "stored campaign seal contradicts the requested identity"
                )
        except CollectionLedgerError:
            raise
        except PrivateArtifactError as error:
            raise CollectionLedgerError(str(error)) from None
        return ledger

    @property
    def identity(self) -> CollectionCampaignIdentity:
        return self._identity

    @property
    def slots(self) -> tuple[CollectionSlot, ...]:
        return self._slots

    def reconcile(self) -> tuple[CollectionAttemptOutcome, ...]:
        """Persist and return every terminal outcome; pending slots are omitted."""

        outcomes: list[CollectionAttemptOutcome] = []
        for slot in self._slots:
            outcome = self.reconcile_slot(slot)
            if outcome is not None:
                outcomes.append(outcome)
        return tuple(outcomes)

    def reconcile_slot(
        self,
        slot: CollectionSlot,
    ) -> CollectionAttemptOutcome | None:
        """Reconcile one slot, including a power-loss partial, idempotently."""

        self._require_declared_slot(slot)
        record_id = _outcome_record_id(slot.assignment_id)
        try:
            stored = self._store.find_sealed_record(
                record_id,
                expected_kind="collection_outcome",
            )
            outcome = self._derive_outcome(slot)
            if stored is not None:
                if outcome is None:
                    raise CollectionLedgerError(
                        "stored outcome has no corresponding episode artifact"
                    )
                if stored.read() != outcome.public_dict():
                    raise CollectionLedgerError(
                        "stored outcome contradicts the immutable episode artifact"
                    )
                return outcome
            if outcome is None:
                return None
            sealed = self._store.publish_sealed_record(
                record_id,
                kind="collection_outcome",
                record=outcome.public_dict(),
            )
            if sealed.read() != outcome.public_dict():
                raise CollectionLedgerError("published outcome failed verification")
            return outcome
        except CollectionLedgerError:
            raise
        except PrivateArtifactError as error:
            raise CollectionLedgerError(str(error)) from None

    def require_pending(self, slot: CollectionSlot) -> None:
        """Fail before execution unless the declared slot has no attempt artifact."""

        if self.reconcile_slot(slot) is not None:
            raise CollectionLedgerError("collection slot is already consumed")

    def public_receipt(self) -> dict[str, object]:
        """Return all declared denominators and current states without private paths."""

        terminal = {
            outcome.slot.assignment_id: outcome for outcome in self.reconcile()
        }
        slot_records: list[dict[str, object]] = []
        counts: Counter[str] = Counter()
        for slot in self._slots:
            outcome = terminal.get(slot.assignment_id)
            if outcome is None:
                record = {
                    **slot.public_dict(),
                    "status": "pending",
                }
                counts["pending"] += 1
            else:
                record = outcome.public_dict()
                counts[outcome.status] += 1
            slot_records.append(record)
        core: dict[str, object] = {
            "schema": OUTCOME_LEDGER_SCHEMA,
            "collection_id": self._identity.collection_id,
            "registry_sha256": self._identity.registry_sha256,
            "source_commit": self._identity.source_commit,
            "teacher_execution_sha256": self._identity.teacher_execution_sha256,
            "declared_slots": len(self._slots),
            "counts": {
                status: counts.get(status, 0)
                for status in ("complete", "failed", "interrupted", "invalid", "pending")
            },
            "slots": slot_records,
        }
        return {
            **core,
            "ledger_sha256": _canonical_sha256(core),
        }

    def _derive_outcome(
        self,
        slot: CollectionSlot,
    ) -> CollectionAttemptOutcome | None:
        state = self._session.inspect_episode(slot.episode_id)
        if state.status == "partial":
            state = self._session.recover_interrupted_episode(slot.episode_id)
        if state.status == "absent":
            return None
        if state.status == "complete":
            reason_code = self._validate_completion_evidence(slot)
            if reason_code != "hall_of_fame_verified":
                state = EpisodeArtifactState(
                    slot.episode_id,
                    "invalid",
                    reason_code=reason_code,
                    manifest_sha256=state.manifest_sha256,
                )
        if state.status == "complete":
            return CollectionAttemptOutcome(
                identity=self._identity,
                slot=slot,
                status="complete",
                reason_code="hall_of_fame_verified",
                game_complete=True,
                episode_manifest_sha256=state.manifest_sha256,
            )
        if state.status == "failed":
            return CollectionAttemptOutcome(
                identity=self._identity,
                slot=slot,
                status="failed",
                reason_code=state.reason_code or "episode_failed",
                game_complete=False,
                episode_manifest_sha256=state.manifest_sha256,
            )
        if state.status == "interrupted":
            return CollectionAttemptOutcome(
                identity=self._identity,
                slot=slot,
                status="interrupted",
                reason_code=state.reason_code or "process_interrupted",
                game_complete=False,
                episode_manifest_sha256=None,
            )
        return CollectionAttemptOutcome(
            identity=self._identity,
            slot=slot,
            status="invalid",
            reason_code=state.reason_code or "invalid_episode_artifact",
            game_complete=False,
            episode_manifest_sha256=state.manifest_sha256,
        )

    def _validate_completion_evidence(self, slot: CollectionSlot) -> str:
        try:
            reader = self._store.open_episode(slot.episode_id)
            header = reader.read_header()
            if (
                header.get("record_type") != "episode"
                or header.get("episode_id") != slot.episode_id
            ):
                return "invalid_episode_header"
            metadata = header.get("metadata")
            if not isinstance(metadata, Mapping):
                return "invalid_episode_header"
            source = metadata.get("source")
            runtime = metadata.get("runtime")
            rom_identity = metadata.get("rom_identity")
            policy = metadata.get("policy")
            if (
                metadata.get("adapter_id") != POKEMON_RED_ADAPTER_ID
                or metadata.get("ontology_id") != POKEMON_CORE_ONTOLOGY_ID
                or not isinstance(policy, Mapping)
                or policy.get("actor") != POKEMON_RED_TEACHER_ACTOR
                or policy.get("policy_id") != POKEMON_RED_TEACHER_POLICY_ID
                or not isinstance(source, Mapping)
                or source.get("git_commit") != self._identity.source_commit
                or source.get("worktree_dirty") is not False
                or metadata.get("source_bundle_sha256")
                != self._identity.source_bundle_sha256
                or metadata.get("objective_graph_sha256")
                != self._identity.objective_graph_sha256
                or not isinstance(runtime, Mapping)
                or collection_document_sha256(runtime)
                != self._identity.runtime_sha256
                or metadata.get("runtime_sha256") != self._identity.runtime_sha256
                or not isinstance(rom_identity, Mapping)
                or rom_identity.get("sha1") != self._identity.rom_sha1
                or rom_identity.get("sha256") != self._identity.rom_sha256
            ):
                return "invalid_campaign_identity"
            collection = metadata.get("collection")
            if not isinstance(collection, Mapping):
                return "invalid_collection_identity"
            if (
                collection.get("assignment_id") != slot.assignment_id
                or collection.get("collection_id") != self._identity.collection_id
                or collection.get("registry_sha256") != self._identity.registry_sha256
                or collection.get("run_id") != slot.run_id
            ):
                return "invalid_collection_identity"
            execution = collection.get("execution")
            schedule = collection.get("schedule")
            attempt = collection.get("attempt")
            configuration = metadata.get("configuration")
            behavior_configuration = (
                configuration.get("behavior_configuration")
                if isinstance(configuration, Mapping)
                else None
            )
            configured_schedule = (
                configuration.get("battle_start_schedule")
                if isinstance(configuration, Mapping)
                else None
            )
            if (
                not isinstance(attempt, Mapping)
                or dict(attempt)
                != {
                    "attempts_per_slot": 1,
                    "counted": True,
                }
                or collection.get("assistance_class") != "teacher"
                or collection.get("start_type") != "clean_power_on"
                or collection.get("human_input") is not False
                or collection.get("save_restore_used") is not False
                or collection.get("perturbation_schedule")
                != "preregistered_battle_start_offsets"
                or collection.get("seed_protocol") != "committed_harness_seed"
                or collection.get("harness_seed") != slot.harness_seed
                or not isinstance(execution, Mapping)
                or execution.get("behavior_configuration_sha256")
                != self._identity.behavior_configuration_sha256
                or execution.get("objective_graph_sha256")
                != self._identity.objective_graph_sha256
                or execution.get("source_bundle_sha256")
                != self._identity.source_bundle_sha256
                or execution.get("teacher_execution_sha256")
                != self._identity.teacher_execution_sha256
                or not isinstance(schedule, Mapping)
                or schedule.get("schedule_id")
                != f"schedule-{slot.schedule_sha256}"
                or schedule.get("schedule_sha256") != slot.schedule_sha256
                or schedule.get("schema") != BATTLE_START_SCHEDULE_SCHEMA
                or schedule.get("variation_id")
                != f"variation-{slot.schedule_sha256}"
                or not isinstance(configuration, Mapping)
                or configuration.get("schema")
                != "qualified-teacher-configuration-v2"
                or not isinstance(behavior_configuration, Mapping)
                or collection_document_sha256(behavior_configuration)
                != self._identity.behavior_configuration_sha256
                or configuration.get("behavior_configuration_sha256")
                != self._identity.behavior_configuration_sha256
                or not isinstance(configured_schedule, Mapping)
                or configured_schedule.get("assignment_id") != slot.assignment_id
                or configured_schedule.get("registry_sha256")
                != self._identity.registry_sha256
            ):
                return "invalid_collection_identity"
            collection_slot = collection.get("collection_slot")
            if (
                not isinstance(collection_slot, Mapping)
                or collection_slot.get("collection_ordinal")
                != slot.collection_ordinal
                or collection_slot.get("collection_total") != slot.collection_total
                or collection_slot.get("partition_ordinal") != slot.partition_ordinal
                or collection_slot.get("partition_total") != slot.partition_total
            ):
                return "invalid_collection_identity"
            split = metadata.get("split")
            if (
                not isinstance(split, Mapping)
                or split.get("partition") != slot.partition
                or split.get("regime") != "within_game"
                or split.get("root_lineage_id") != slot.root_lineage_id
            ):
                return "invalid_collection_identity"

            terminals = []
            for event in reader.iter_stream("events", max_records=10_000):
                if event.get("kind") == "terminal":
                    terminals.append(event)
            if len(terminals) != 1:
                return "invalid_terminal_evidence"
            terminal = terminals[0]
            payload = terminal.get("payload")
            terminal_schedule = (
                payload.get("battle_start_schedule")
                if isinstance(payload, Mapping)
                else None
            )
            if (
                terminal.get("episode_id") != slot.episode_id
                or not isinstance(payload, Mapping)
                or payload.get("status") != "complete"
                or payload.get("game_complete") is not True
                or payload.get("qualified_through") != "enter_hall_of_fame"
                or not isinstance(terminal_schedule, Mapping)
                or terminal_schedule.get("complete") is not True
                or terminal_schedule.get("expected_battles") != slot.battle_count
                or terminal_schedule.get("finished_battles") != slot.battle_count
                or terminal_schedule.get("schedule_sha256")
                != slot.schedule_sha256
            ):
                return "invalid_terminal_evidence"
            try:
                audit_schedule_attestations(
                    reader,
                    episode_id=slot.episode_id,
                    offsets=slot.offsets,
                    schedule_sha256=slot.schedule_sha256,
                )
            except ScheduleAttestationError:
                return "invalid_schedule_attestation"
            return "hall_of_fame_verified"
        except (CollectionProtocolError, PrivateArtifactError):
            return "invalid_completion_evidence"

    def _require_declared_slot(self, slot: CollectionSlot) -> None:
        if slot not in self._slots:
            raise CollectionLedgerError("collection slot is not declared by this ledger")

    def _campaign_record(self) -> dict[str, object]:
        return {
            **self._identity.public_dict(),
            "slots": [slot.public_dict() for slot in self._slots],
        }

    @staticmethod
    def _validate_slots(slots: tuple[CollectionSlot, ...]) -> None:
        if not isinstance(slots, tuple) or not slots:
            raise CollectionLedgerError("collection ledger requires declared slots")
        if not all(isinstance(slot, CollectionSlot) for slot in slots):
            raise TypeError("slots must contain CollectionSlot values")
        total = len(slots)
        if any(slot.collection_total != total for slot in slots):
            raise CollectionLedgerError("collection slot totals are inconsistent")
        if tuple(slot.collection_ordinal for slot in slots) != tuple(range(1, total + 1)):
            raise CollectionLedgerError("collection slot ordinals are not exact")
        if len({slot.assignment_id for slot in slots}) != total:
            raise CollectionLedgerError("collection assignment identities must be unique")
        if len({slot.episode_id for slot in slots}) != total:
            raise CollectionLedgerError("collection episode identities must be unique")
        if len({slot.root_lineage_id for slot in slots}) != total:
            raise CollectionLedgerError("collection root lineages must be unique")
        if len({slot.run_id for slot in slots}) != total:
            raise CollectionLedgerError("collection run identities must be unique")
        for partition in _PARTITIONS:
            partition_slots = tuple(slot for slot in slots if slot.partition == partition)
            if not partition_slots:
                continue
            expected_total = len(partition_slots)
            if any(slot.partition_total != expected_total for slot in partition_slots):
                raise CollectionLedgerError("partition slot totals are inconsistent")
            if tuple(slot.partition_ordinal for slot in partition_slots) != tuple(
                range(1, expected_total + 1)
            ):
                raise CollectionLedgerError("partition slot ordinals are not exact")


def publish_dry_run_qualification(
    store: PrivateArtifactRoot,
    identity: CollectionCampaignIdentity,
    dry_run: ScheduleDryRun,
    episode_id: str,
) -> DryRunQualification:
    """Audit one completed rehearsal and publish its immutable qualification."""

    qualification = _derive_dry_run_qualification(
        store,
        identity=identity,
        dry_run=dry_run,
        episode_id=episode_id,
    )
    try:
        sealed = store.publish_sealed_record(
            _dry_run_qualification_record_id(identity, dry_run),
            kind="collection_dry_run_qualification",
            record=qualification.public_dict(),
        )
        if sealed.read() != qualification.public_dict():
            raise CollectionLedgerError(
                "published dry-run qualification failed verification"
            )
    except CollectionLedgerError:
        raise
    except PrivateArtifactError as error:
        raise CollectionLedgerError(str(error)) from None
    return qualification


def find_dry_run_qualification(
    store: PrivateArtifactRoot,
    identity: CollectionCampaignIdentity,
    dry_run: ScheduleDryRun,
) -> DryRunQualification | None:
    """Return a re-audited qualification, or ``None`` when it has not passed."""

    _validate_dry_run_requirement(identity, dry_run)
    try:
        sealed = store.find_sealed_record(
            _dry_run_qualification_record_id(identity, dry_run),
            expected_kind="collection_dry_run_qualification",
        )
        if sealed is None:
            return None
        stored = sealed.read()
        episode_id = _require_safe_id(
            stored.get("episode_id"),
            subject="dry-run episode identity",
        )
        qualification = _derive_dry_run_qualification(
            store,
            identity=identity,
            dry_run=dry_run,
            episode_id=episode_id,
        )
        if stored != qualification.public_dict():
            raise CollectionLedgerError(
                "stored dry-run qualification contradicts its completed episode"
            )
        return qualification
    except CollectionLedgerError:
        raise
    except PrivateArtifactError as error:
        raise CollectionLedgerError(str(error)) from None


def require_dry_run_qualification(
    store: PrivateArtifactRoot,
    identity: CollectionCampaignIdentity,
    dry_run: ScheduleDryRun,
) -> DryRunQualification:
    """Fail before campaign sealing unless the exact rehearsal remains valid."""

    qualification = find_dry_run_qualification(store, identity, dry_run)
    if qualification is None:
        raise CollectionLedgerError(
            "the exact schedule dry run must qualify before collection starts"
        )
    return qualification


def _derive_dry_run_qualification(
    store: PrivateArtifactRoot,
    *,
    identity: CollectionCampaignIdentity,
    dry_run: ScheduleDryRun,
    episode_id: str,
) -> DryRunQualification:
    _validate_dry_run_requirement(identity, dry_run)
    _require_safe_id(episode_id, subject="dry-run episode identity")
    try:
        reader = store.open_episode(episode_id)
        header = reader.read_header()
        if (
            header.get("record_type") != "episode"
            or header.get("episode_id") != episode_id
        ):
            raise CollectionLedgerError("dry-run episode header is invalid")
        metadata = header.get("metadata")
        if not isinstance(metadata, Mapping):
            raise CollectionLedgerError("dry-run episode metadata is invalid")
        source = metadata.get("source")
        runtime = metadata.get("runtime")
        rom_identity = metadata.get("rom_identity")
        policy = metadata.get("policy")
        if (
            metadata.get("adapter_id") != POKEMON_RED_ADAPTER_ID
            or metadata.get("ontology_id") != POKEMON_CORE_ONTOLOGY_ID
            or not isinstance(policy, Mapping)
            or policy.get("actor") != POKEMON_RED_TEACHER_ACTOR
            or policy.get("policy_id") != POKEMON_RED_TEACHER_POLICY_ID
            or not isinstance(source, Mapping)
            or source.get("git_commit") != identity.source_commit
            or source.get("worktree_dirty") is not False
            or metadata.get("source_bundle_sha256")
            != identity.source_bundle_sha256
            or metadata.get("objective_graph_sha256")
            != identity.objective_graph_sha256
            or not isinstance(runtime, Mapping)
            or collection_document_sha256(runtime) != identity.runtime_sha256
            or metadata.get("runtime_sha256") != identity.runtime_sha256
            or not isinstance(rom_identity, Mapping)
            or rom_identity.get("sha1") != identity.rom_sha1
            or rom_identity.get("sha256") != identity.rom_sha256
        ):
            raise CollectionLedgerError(
                "dry-run episode does not match the campaign identity"
            )

        collection = metadata.get("collection")
        if not isinstance(collection, Mapping):
            raise CollectionLedgerError("dry-run collection metadata is invalid")
        attempt = collection.get("attempt")
        execution = collection.get("execution")
        schedule = collection.get("schedule")
        if (
            not isinstance(attempt, Mapping)
            or dict(attempt) != {"counted": False}
            or collection.get("assistance_class") != "teacher"
            or collection.get("dry_run_id") != dry_run.dry_run_id
            or collection.get("harness_seed") != dry_run.harness_seed
            or collection.get("human_input") is not False
            or collection.get("perturbation_schedule")
            != "fixed_schedule_integration_dry_run"
            or collection.get("purpose") != "schedule_integration_dry_run"
            or collection.get("registry_sha256") != identity.registry_sha256
            or collection.get("save_restore_used") is not False
            or collection.get("seed_protocol")
            != "committed_diagnostic_harness_seed"
            or collection.get("start_type") != "clean_power_on"
            or not isinstance(execution, Mapping)
            or execution.get("behavior_configuration_sha256")
            != identity.behavior_configuration_sha256
            or execution.get("objective_graph_sha256")
            != identity.objective_graph_sha256
            or execution.get("source_bundle_sha256")
            != identity.source_bundle_sha256
            or execution.get("teacher_execution_sha256")
            != identity.teacher_execution_sha256
            or not isinstance(schedule, Mapping)
            or schedule.get("schedule_sha256") != dry_run.schedule_sha256
            or schedule.get("schema") != BATTLE_START_SCHEDULE_SCHEMA
        ):
            raise CollectionLedgerError("dry-run collection identity is invalid")

        configuration = metadata.get("configuration")
        behavior_configuration = (
            configuration.get("behavior_configuration")
            if isinstance(configuration, Mapping)
            else None
        )
        configured_schedule = (
            configuration.get("battle_start_schedule")
            if isinstance(configuration, Mapping)
            else None
        )
        if (
            not isinstance(configuration, Mapping)
            or configuration.get("schema")
            != "qualified-teacher-configuration-v2"
            or not isinstance(behavior_configuration, Mapping)
            or collection_document_sha256(behavior_configuration)
            != identity.behavior_configuration_sha256
            or configuration.get("behavior_configuration_sha256")
            != identity.behavior_configuration_sha256
            or not isinstance(configured_schedule, Mapping)
            or configured_schedule.get("dry_run_id") != dry_run.dry_run_id
            or configured_schedule.get("purpose")
            != "schedule_integration_dry_run"
            or configured_schedule.get("registry_sha256")
            != identity.registry_sha256
            or configured_schedule.get("teacher_execution_sha256")
            != identity.teacher_execution_sha256
        ):
            raise CollectionLedgerError("dry-run configuration identity is invalid")

        split = metadata.get("split")
        if (
            not isinstance(split, Mapping)
            or split.get("partition") != "unassigned"
            or split.get("regime") != "within_game"
            or split.get("root_lineage_id") != episode_id
        ):
            raise CollectionLedgerError("dry-run split identity is invalid")
        attestation = audit_schedule_attestations(
            reader,
            episode_id=episode_id,
            offsets=dry_run.offsets,
            schedule_sha256=dry_run.schedule_sha256,
        )
        return DryRunQualification(
            identity=identity,
            dry_run_id=dry_run.dry_run_id,
            harness_seed=dry_run.harness_seed,
            schedule_sha256=dry_run.schedule_sha256,
            battle_count=len(dry_run.offsets),
            episode_id=episode_id,
            episode_manifest_sha256=reader.manifest_sha256,
            attestation=attestation,
        )
    except CollectionLedgerError:
        raise
    except (
        CollectionProtocolError,
        PrivateArtifactError,
        ScheduleAttestationError,
    ):
        raise CollectionLedgerError(
            "dry-run completion evidence failed verification"
        ) from None


def _validate_dry_run_requirement(
    identity: CollectionCampaignIdentity,
    dry_run: ScheduleDryRun,
) -> None:
    if not isinstance(identity, CollectionCampaignIdentity):
        raise TypeError("identity must be a CollectionCampaignIdentity")
    if not isinstance(dry_run, ScheduleDryRun):
        raise TypeError("dry_run must be a ScheduleDryRun")
    if (
        dry_run.registry_sha256 != identity.registry_sha256
        or not dry_run.offsets
        or battle_start_offsets_sha256(dry_run.offsets)
        != dry_run.schedule_sha256
    ):
        raise CollectionLedgerError(
            "dry-run schedule does not match the campaign registry"
        )


def _campaign_seal_record_id(collection_id: str) -> str:
    digest = hashlib.sha256(collection_id.encode("ascii")).hexdigest()
    return f"seal-{digest}"


def _dry_run_qualification_record_id(
    identity: CollectionCampaignIdentity,
    dry_run: ScheduleDryRun,
) -> str:
    _validate_dry_run_requirement(identity, dry_run)
    digest = _canonical_sha256(
        {
            "campaign": identity.public_dict(),
            "dry_run": {
                "dry_run_id": dry_run.dry_run_id,
                "harness_seed": dry_run.harness_seed,
                "registry_sha256": dry_run.registry_sha256,
                "schedule_sha256": dry_run.schedule_sha256,
            },
            "schema": DRY_RUN_QUALIFICATION_SCHEMA,
        }
    )
    return f"dry-run-{digest}"


def _outcome_record_id(assignment_id: str) -> str:
    return f"outcome-{assignment_id}"


def _require_safe_id(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise CollectionLedgerError(f"{subject} must be a safe lowercase identifier")
    return value


def _require_sha256(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise CollectionLedgerError(f"{subject} must be a lowercase SHA-256 digest")
    return value


def _canonical_sha256(value: Mapping[str, object]) -> str:
    payload = (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )
    return hashlib.sha256(payload).hexdigest()
