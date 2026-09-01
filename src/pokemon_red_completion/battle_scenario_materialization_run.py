"""Crash-safe, one-way accounting for a frozen battle-capture plan.

The private plan chooses every source and destination before controller input.
This module supplies the second half of that trust boundary: each assignment is
durably changed from pending to started before it can execute, and no started
or failed assignment can ever return to pending.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, replace

from pokemon_red_completion.battle_scenario_materialization_plan import (
    BattleScenarioMaterializationPlan,
)
from pokemon_red_completion.provenance import canonical_sha256

BATTLE_SCENARIO_MATERIALIZATION_RUN_SCHEMA = (
    "pokemon.red.private-battle-scenario-materialization-run.v1"
)
BATTLE_SCENARIO_MATERIALIZATION_RUN_RECEIPT_SCHEMA = (
    "pokemon.red.battle-scenario-materialization-run-receipt.v1"
)

PENDING = "pending"
STARTED = "started"
SUCCEEDED = "succeeded"
FAILED = "failed"
_STATUSES = {PENDING, STARTED, SUCCEEDED, FAILED}
_TERMINAL = {SUCCEEDED, FAILED}
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_MAXIMUM_JOURNAL_BYTES = 2 * 1024 * 1024


class BattleScenarioMaterializationRunError(ValueError):
    """Raised when a run could replay, substitute, or misreport an assignment."""


@dataclass(frozen=True, slots=True)
class BattleScenarioMaterializationRunIdentity:
    """Exact published execution identity shared by every journal transition."""

    plan_id: str
    plan_sha256: str
    source_commit: str
    source_bundle_sha256: str
    materializer_sha256: str
    runtime_identity_sha256: str
    rom_sha256: str
    capture_directory_sha256: str
    context_catalog_sha256: str
    registry_sha256: str
    registry_source_commit: str
    exact_ci_run: int
    exact_ci_attempt: int

    def __post_init__(self) -> None:
        if _SAFE_ID.fullmatch(self.plan_id) is None:
            raise BattleScenarioMaterializationRunError("run plan identity differs")
        for digest_value, subject in (
            (self.plan_sha256, "plan"),
            (self.source_bundle_sha256, "source bundle"),
            (self.materializer_sha256, "materializer"),
            (self.runtime_identity_sha256, "runtime"),
            (self.rom_sha256, "ROM"),
            (self.capture_directory_sha256, "capture directory"),
            (self.context_catalog_sha256, "context catalog"),
            (self.registry_sha256, "registry"),
        ):
            if not isinstance(digest_value, str) or _SHA256.fullmatch(digest_value) is None:
                raise BattleScenarioMaterializationRunError(
                    f"run {subject} identity differs"
                )
        for commit_value, subject in (
            (self.source_commit, "source"),
            (self.registry_source_commit, "registry source"),
        ):
            if not isinstance(commit_value, str) or _GIT_COMMIT.fullmatch(commit_value) is None:
                raise BattleScenarioMaterializationRunError(
                    f"run {subject} commit differs"
                )
        for positive_value, subject in (
            (self.exact_ci_run, "CI run"),
            (self.exact_ci_attempt, "CI attempt"),
        ):
            if type(positive_value) is not int or positive_value <= 0:  # noqa: E721
                raise BattleScenarioMaterializationRunError(f"run {subject} differs")

    def private_dict(self) -> dict[str, object]:
        return {
            "capture_directory_sha256": self.capture_directory_sha256,
            "context_catalog_sha256": self.context_catalog_sha256,
            "exact_ci_attempt": self.exact_ci_attempt,
            "exact_ci_run": self.exact_ci_run,
            "materializer_sha256": self.materializer_sha256,
            "plan_id": self.plan_id,
            "plan_sha256": self.plan_sha256,
            "registry_sha256": self.registry_sha256,
            "registry_source_commit": self.registry_source_commit,
            "rom_sha256": self.rom_sha256,
            "runtime_identity_sha256": self.runtime_identity_sha256,
            "source_bundle_sha256": self.source_bundle_sha256,
            "source_commit": self.source_commit,
        }


@dataclass(frozen=True, slots=True)
class BattleScenarioMaterializationRunEntry:
    """One monotonic execution slot from the frozen seven-item denominator."""

    ordinal: int
    capture_id: str
    assignment_sha256: str
    status: str
    attempt_count: int
    reason_code: str | None = None
    state_sha256: str | None = None
    manifest_sha256: str | None = None

    def __post_init__(self) -> None:
        if (
            type(self.ordinal) is not int  # noqa: E721
            or self.ordinal < 0
            or _SAFE_ID.fullmatch(self.capture_id) is None
            or _SHA256.fullmatch(self.assignment_sha256) is None
            or self.status not in _STATUSES
            or type(self.attempt_count) is not int  # noqa: E721
            or self.attempt_count not in {0, 1}
        ):
            raise BattleScenarioMaterializationRunError("run entry identity differs")
        if self.reason_code is not None and _SAFE_ID.fullmatch(self.reason_code) is None:
            raise BattleScenarioMaterializationRunError("run failure reason differs")
        for digest in (self.state_sha256, self.manifest_sha256):
            if digest is not None and _SHA256.fullmatch(digest) is None:
                raise BattleScenarioMaterializationRunError("run output identity differs")
        expected_shape = {
            PENDING: (0, None, None, None),
            STARTED: (1, None, None, None),
            FAILED: (1, self.reason_code, None, None),
            SUCCEEDED: (1, None, self.state_sha256, self.manifest_sha256),
        }[self.status]
        actual_shape = (
            self.attempt_count,
            self.reason_code,
            self.state_sha256,
            self.manifest_sha256,
        )
        if actual_shape != expected_shape:
            raise BattleScenarioMaterializationRunError("run entry state differs")
        if self.status == FAILED and self.reason_code is None:
            raise BattleScenarioMaterializationRunError("failed run entry lacks a reason")
        if self.status == SUCCEEDED and (
            self.state_sha256 is None or self.manifest_sha256 is None
        ):
            raise BattleScenarioMaterializationRunError("successful run entry lacks outputs")

    def private_dict(self) -> dict[str, object]:
        return {
            "assignment_sha256": self.assignment_sha256,
            "attempt_count": self.attempt_count,
            "capture_id": self.capture_id,
            "manifest_sha256": self.manifest_sha256,
            "ordinal": self.ordinal,
            "reason_code": self.reason_code,
            "state_sha256": self.state_sha256,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class BattleScenarioMaterializationRunJournal:
    """Canonical private journal; every rewrite must preserve the exact identity."""

    identity: BattleScenarioMaterializationRunIdentity
    entries: tuple[BattleScenarioMaterializationRunEntry, ...]
    revision: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.identity, BattleScenarioMaterializationRunIdentity)
            or not isinstance(self.entries, tuple)
            or not self.entries
            or any(
                not isinstance(item, BattleScenarioMaterializationRunEntry)
                for item in self.entries
            )
            or tuple(item.ordinal for item in self.entries) != tuple(range(len(self.entries)))
            or len({item.capture_id for item in self.entries}) != len(self.entries)
            or type(self.revision) is not int  # noqa: E721
            or self.revision < 0
            or self.revision != sum(item.attempt_count for item in self.entries)
            + sum(item.status in _TERMINAL for item in self.entries)
        ):
            raise BattleScenarioMaterializationRunError("run journal differs")

    @property
    def journal_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def private_dict(self) -> dict[str, object]:
        return {
            "entries": [item.private_dict() for item in self.entries],
            "identity": self.identity.private_dict(),
            "retry_after_started": False,
            "revision": self.revision,
            "schema": BATTLE_SCENARIO_MATERIALIZATION_RUN_SCHEMA,
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_payload(self.private_dict())

    def public_receipt(self) -> dict[str, object]:
        counts = Counter(item.status for item in self.entries)
        failures = Counter(
            item.reason_code for item in self.entries if item.status == FAILED
        )
        successful_bindings = [
            {
                "assignment_sha256": item.assignment_sha256,
                "manifest_sha256": item.manifest_sha256,
                "state_sha256": item.state_sha256,
            }
            for item in self.entries
            if item.status == SUCCEEDED
        ]
        core: dict[str, object] = {
            "schema": BATTLE_SCENARIO_MATERIALIZATION_RUN_RECEIPT_SCHEMA,
            "status": (
                "complete"
                if counts[PENDING] == 0
                and counts[STARTED] == 0
                and counts[FAILED] == 0
                else "complete_with_failures"
                if counts[PENDING] == 0 and counts[STARTED] == 0
                else "interrupted_nonretryable"
                if counts[STARTED] > 0
                else "pending"
            ),
            "plan_id": self.identity.plan_id,
            "plan_sha256": self.identity.plan_sha256,
            "source_commit": self.identity.source_commit,
            "source_bundle_sha256": self.identity.source_bundle_sha256,
            "materializer_sha256": self.identity.materializer_sha256,
            "runtime_identity_sha256": self.identity.runtime_identity_sha256,
            "rom_sha256": self.identity.rom_sha256,
            "context_catalog_sha256": self.identity.context_catalog_sha256,
            "registry_sha256": self.identity.registry_sha256,
            "registry_source_commit": self.identity.registry_source_commit,
            "exact_ci_run": self.identity.exact_ci_run,
            "exact_ci_attempt": self.identity.exact_ci_attempt,
            "declared_capture_count": len(self.entries),
            "counts": {
                status: counts[status]
                for status in (PENDING, STARTED, SUCCEEDED, FAILED)
            },
            "failure_reason_counts": dict(sorted(failures.items())),
            "successful_output_bindings_sha256": canonical_sha256(
                successful_bindings
            ),
            "journal_sha256": self.journal_sha256,
            "retry_after_started": False,
            "private_path_fields": 0,
            "move_choices_executed": 0,
            "teacher_queries": 0,
            "outcomes_opened": 0,
            "model_predictions": 0,
            "model_fits": 0,
            "sealed_red_cases_opened": 0,
            "crystal_contexts_opened": 0,
            "authority_promoted": False,
            "full_game_replays": 0,
        }
        return {**core, "receipt_sha256": canonical_sha256(core)}


def initialize_battle_scenario_materialization_run(
    plan: BattleScenarioMaterializationPlan,
    identity: BattleScenarioMaterializationRunIdentity,
) -> BattleScenarioMaterializationRunJournal:
    """Create the all-pending denominator before any assignment can execute."""

    _require_identity_matches_plan(plan, identity)
    return BattleScenarioMaterializationRunJournal(
        identity=identity,
        entries=tuple(
            BattleScenarioMaterializationRunEntry(
                ordinal=item.ordinal,
                capture_id=item.capture_id,
                assignment_sha256=canonical_sha256(item.private_dict()),
                status=PENDING,
                attempt_count=0,
            )
            for item in plan.assignments
        ),
        revision=0,
    )


def require_battle_scenario_materialization_run_matches_plan(
    journal: BattleScenarioMaterializationRunJournal,
    plan: BattleScenarioMaterializationPlan,
    identity: BattleScenarioMaterializationRunIdentity,
) -> None:
    """Reject a journal reconstructed for another plan or execution identity."""

    _require_identity_matches_plan(plan, identity)
    if journal.identity != identity:
        raise BattleScenarioMaterializationRunError("run journal identity differs")
    expected = initialize_battle_scenario_materialization_run(plan, identity)
    for observed, planned in zip(journal.entries, expected.entries, strict=True):
        if (
            observed.ordinal,
            observed.capture_id,
            observed.assignment_sha256,
        ) != (
            planned.ordinal,
            planned.capture_id,
            planned.assignment_sha256,
        ):
            raise BattleScenarioMaterializationRunError("run journal assignment differs")


def start_battle_scenario_materialization_assignment(
    journal: BattleScenarioMaterializationRunJournal,
    ordinal: int,
) -> BattleScenarioMaterializationRunJournal:
    """Consume the only attempt before any controller input is possible."""

    entry = _entry(journal, ordinal)
    if entry.status != PENDING:
        raise BattleScenarioMaterializationRunError(
            "only a pending battle materialization assignment may start"
        )
    return _replace_entry(
        journal,
        ordinal,
        replace(entry, status=STARTED, attempt_count=1),
    )


def succeed_battle_scenario_materialization_assignment(
    journal: BattleScenarioMaterializationRunJournal,
    ordinal: int,
    *,
    state_sha256: str,
    manifest_sha256: str,
) -> BattleScenarioMaterializationRunJournal:
    """Settle a started assignment only after independent output reopen."""

    entry = _entry(journal, ordinal)
    if entry.status != STARTED:
        raise BattleScenarioMaterializationRunError(
            "only a started battle materialization assignment may succeed"
        )
    return _replace_entry(
        journal,
        ordinal,
        replace(
            entry,
            status=SUCCEEDED,
            state_sha256=state_sha256,
            manifest_sha256=manifest_sha256,
        ),
    )


def fail_battle_scenario_materialization_assignment(
    journal: BattleScenarioMaterializationRunJournal,
    ordinal: int,
    *,
    reason_code: str,
) -> BattleScenarioMaterializationRunJournal:
    """Retain a controlled failure in the denominator without reopening its attempt."""

    entry = _entry(journal, ordinal)
    if entry.status != STARTED:
        raise BattleScenarioMaterializationRunError(
            "only a started battle materialization assignment may fail"
        )
    return _replace_entry(
        journal,
        ordinal,
        replace(entry, status=FAILED, reason_code=reason_code),
    )


def parse_battle_scenario_materialization_run(
    payload: bytes,
) -> BattleScenarioMaterializationRunJournal:
    """Strictly reopen an owner-private canonical journal."""

    if not isinstance(payload, bytes):
        raise TypeError("battle materialization run journal must be bytes")
    if not payload or len(payload) > _MAXIMUM_JOURNAL_BYTES:
        raise BattleScenarioMaterializationRunError("run journal size differs")
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise BattleScenarioMaterializationRunError(
            "run journal is not canonical JSON"
        ) from None
    journal = _parse_journal(value)
    if journal.canonical_bytes() != payload:
        raise BattleScenarioMaterializationRunError(
            "run journal is not canonical JSON"
        )
    return journal


def _require_identity_matches_plan(
    plan: BattleScenarioMaterializationPlan,
    identity: BattleScenarioMaterializationRunIdentity,
) -> None:
    if not isinstance(plan, BattleScenarioMaterializationPlan):
        raise TypeError("battle materialization run requires a frozen plan")
    if (
        identity.plan_id != plan.plan_id
        or identity.plan_sha256 != plan.plan_sha256
        or identity.rom_sha256 != plan.rom_sha256
        or identity.capture_directory_sha256 != plan.capture_directory_sha256
    ):
        raise BattleScenarioMaterializationRunError("run identity differs from its plan")
    provenances = {
        (
            item.source.catalog_sha256,
            item.source.registry_sha256,
            item.source.registry_source_commit,
        )
        for item in plan.inventory
    }
    if provenances != {
        (
            identity.context_catalog_sha256,
            identity.registry_sha256,
            identity.registry_source_commit,
        )
    }:
        raise BattleScenarioMaterializationRunError(
            "run source provenance differs from its plan"
        )


def _replace_entry(
    journal: BattleScenarioMaterializationRunJournal,
    ordinal: int,
    replacement: BattleScenarioMaterializationRunEntry,
) -> BattleScenarioMaterializationRunJournal:
    entries = list(journal.entries)
    entries[ordinal] = replacement
    return BattleScenarioMaterializationRunJournal(
        identity=journal.identity,
        entries=tuple(entries),
        revision=journal.revision + 1,
    )


def _entry(
    journal: BattleScenarioMaterializationRunJournal,
    ordinal: int,
) -> BattleScenarioMaterializationRunEntry:
    if type(ordinal) is not int or not 0 <= ordinal < len(journal.entries):  # noqa: E721
        raise BattleScenarioMaterializationRunError("run assignment ordinal differs")
    return journal.entries[ordinal]


def _parse_journal(value: object) -> BattleScenarioMaterializationRunJournal:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"entries", "identity", "retry_after_started", "revision", "schema"}
        or value.get("schema") != BATTLE_SCENARIO_MATERIALIZATION_RUN_SCHEMA
        or value.get("retry_after_started") is not False
        or not isinstance(value.get("entries"), list)
    ):
        raise BattleScenarioMaterializationRunError("run journal fields differ")
    return BattleScenarioMaterializationRunJournal(
        identity=_parse_identity(value.get("identity")),
        entries=tuple(_parse_entry(item) for item in value["entries"]),
        revision=_integer(value.get("revision"), "revision"),
    )


def _parse_identity(value: object) -> BattleScenarioMaterializationRunIdentity:
    fields = {
        "capture_directory_sha256",
        "context_catalog_sha256",
        "exact_ci_attempt",
        "exact_ci_run",
        "materializer_sha256",
        "plan_id",
        "plan_sha256",
        "registry_sha256",
        "registry_source_commit",
        "rom_sha256",
        "runtime_identity_sha256",
        "source_bundle_sha256",
        "source_commit",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise BattleScenarioMaterializationRunError("run identity fields differ")
    return BattleScenarioMaterializationRunIdentity(
        plan_id=_text(value.get("plan_id"), "plan"),
        plan_sha256=_text(value.get("plan_sha256"), "plan digest"),
        source_commit=_text(value.get("source_commit"), "source"),
        source_bundle_sha256=_text(value.get("source_bundle_sha256"), "source bundle"),
        materializer_sha256=_text(value.get("materializer_sha256"), "materializer"),
        runtime_identity_sha256=_text(value.get("runtime_identity_sha256"), "runtime"),
        rom_sha256=_text(value.get("rom_sha256"), "ROM"),
        capture_directory_sha256=_text(
            value.get("capture_directory_sha256"), "capture directory"
        ),
        context_catalog_sha256=_text(
            value.get("context_catalog_sha256"), "context catalog"
        ),
        registry_sha256=_text(value.get("registry_sha256"), "registry"),
        registry_source_commit=_text(
            value.get("registry_source_commit"), "registry source"
        ),
        exact_ci_run=_integer(value.get("exact_ci_run"), "CI run"),
        exact_ci_attempt=_integer(value.get("exact_ci_attempt"), "CI attempt"),
    )


def _parse_entry(value: object) -> BattleScenarioMaterializationRunEntry:
    fields = {
        "assignment_sha256",
        "attempt_count",
        "capture_id",
        "manifest_sha256",
        "ordinal",
        "reason_code",
        "state_sha256",
        "status",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise BattleScenarioMaterializationRunError("run entry fields differ")
    return BattleScenarioMaterializationRunEntry(
        ordinal=_integer(value.get("ordinal"), "ordinal"),
        capture_id=_text(value.get("capture_id"), "capture"),
        assignment_sha256=_text(value.get("assignment_sha256"), "assignment"),
        status=_text(value.get("status"), "status"),
        attempt_count=_integer(value.get("attempt_count"), "attempt count"),
        reason_code=_optional_text(value.get("reason_code"), "reason"),
        state_sha256=_optional_text(value.get("state_sha256"), "state"),
        manifest_sha256=_optional_text(value.get("manifest_sha256"), "manifest"),
    )


def _canonical_payload(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("ascii")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _text(value: object, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise BattleScenarioMaterializationRunError(f"run {subject} differs")
    return value


def _optional_text(value: object, subject: str) -> str | None:
    if value is None:
        return None
    return _text(value, subject)


def _integer(value: object, subject: str) -> int:
    if type(value) is not int:  # noqa: E721
        raise BattleScenarioMaterializationRunError(f"run {subject} differs")
    return value


__all__ = [
    "FAILED",
    "PENDING",
    "STARTED",
    "SUCCEEDED",
    "BattleScenarioMaterializationRunEntry",
    "BattleScenarioMaterializationRunError",
    "BattleScenarioMaterializationRunIdentity",
    "BattleScenarioMaterializationRunJournal",
    "fail_battle_scenario_materialization_assignment",
    "initialize_battle_scenario_materialization_run",
    "parse_battle_scenario_materialization_run",
    "require_battle_scenario_materialization_run_matches_plan",
    "start_battle_scenario_materialization_assignment",
    "succeed_battle_scenario_materialization_assignment",
]
