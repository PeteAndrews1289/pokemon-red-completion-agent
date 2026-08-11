"""Prospective whole-root assignments for strategic navigation collection.

The three live route probes are development calibrations.  They must never be
relabeled as training data.  This protocol creates a separate, canonical set of
power-on roots whose split, timing perturbation and execution identity are fixed
before any outcome is observed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from pokemon_red_completion.battle_plan import RED_BATTLE_PLAN_IDS
from pokemon_red_completion.collection_protocol import (
    BATTLE_PLAN_ROSTER_SCHEMA,
    BATTLE_START_MAX_OFFSET_FRAMES,
    BATTLE_START_SCHEDULE_DERIVATION,
    BATTLE_START_SCHEDULE_SCHEMA,
    BattleStartSchedule,
    collection_document_sha256,
    committed_source_bundle_sha256,
)
from pokemon_red_completion.strategic_navigation import (
    DestinationAvailability,
    DestinationUnavailableReason,
    NavigationFailureReason,
    NavigationOutcomeStatus,
    StrategicInterruptionKind,
    StrategicInterruptionResolution,
    StrategicNavigationTag,
    StrategicReplanReason,
    StrategicResourceKind,
)

STRATEGIC_NAVIGATION_REGISTRY_RELATIVE_PATH = (
    "configs/red-strategic-navigation-collection-v1.json"
)
STRATEGIC_NAVIGATION_REGISTRY_DIGEST_RELATIVE_PATH = (
    "configs/red-strategic-navigation-collection-v1.digest.json"
)
STRATEGIC_NAVIGATION_REGISTRY_SCHEMA = (
    "pokemon-strategic-navigation-collection-runs-v1"
)
STRATEGIC_NAVIGATION_REGISTRY_DIGEST_SCHEMA = (
    "pokemon-strategic-navigation-collection-registry-digest-v1"
)
STRATEGIC_NAVIGATION_EXECUTION_SCHEMA = (
    "pokemon-strategic-navigation-teacher-execution-v1"
)
STRATEGIC_NAVIGATION_ASSIGNMENT_SCHEMA = (
    "pokemon-strategic-navigation-collection-assignment-v1"
)
STRATEGIC_NAVIGATION_REHEARSAL_SCHEMA = (
    "pokemon-strategic-navigation-collection-rehearsal-v1"
)
STRATEGIC_NAVIGATION_CONTRACT_SCHEMA = "pokemon-strategic-navigation-contract-v1"

STRATEGIC_NAVIGATION_COLLECTION_ID = "red-strategic-navigation-v1"
STRATEGIC_NAVIGATION_GAME_ID = "pokemon.mainline:red:gb:us:rev0"
STRATEGIC_NAVIGATION_ADAPTER_ID = "pokemon.red.gb.us.rev0.v1"
STRATEGIC_NAVIGATION_ONTOLOGY_ID = "pokemon.core.v1"
STRATEGIC_NAVIGATION_ACTOR = "deterministic_teacher"
STRATEGIC_NAVIGATION_POLICY_ID = "qualified-completion-order-v1"
STRATEGIC_NAVIGATION_REGIME = "within_game_whole_root"
STRATEGIC_NAVIGATION_REHEARSAL_ID = "red-strategic-navigation-rehearsal-v1"
STRATEGIC_NAVIGATION_REHEARSAL_SEED = 1_710_001

_PARTITION_COUNTS = {"test": 5, "train": 5, "validation": 2}
_RUN_COUNT = sum(_PARTITION_COUNTS.values())
_MAX_REGISTRY_BYTES = 1024 * 1024
_MAX_DIGEST_BYTES = 4096
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


class StrategicNavigationProtocolError(RuntimeError):
    """Raised when prospective strategic collection identity is not exact."""


@dataclass(frozen=True, slots=True)
class StrategicNavigationCollectionRun:
    """One preassigned power-on root."""

    run_id: str
    partition: str
    harness_seed: int
    schedule_sha256: str


@dataclass(frozen=True, slots=True)
class StrategicNavigationRehearsal:
    """The only root allowed before counted train/validation collection begins."""

    rehearsal_id: str
    harness_seed: int
    schedule_sha256: str


@dataclass(frozen=True, slots=True)
class StrategicNavigationExecution:
    """Frozen source, teacher and semantic-decision contract."""

    source_bundle_sha256: str
    behavior_configuration_sha256: str
    objective_graph_sha256: str
    decision_contract_sha256: str
    teacher_execution_sha256: str
    source_commit: str | None = None


@dataclass(frozen=True, slots=True)
class StrategicNavigationAssignment:
    """Path-free collection identity derived from the canonical registry."""

    collection_id: str
    registry_sha256: str
    run_id: str
    partition: str
    harness_seed: int
    schedule_sha256: str
    assignment_id: str
    root_lineage_id: str
    episode_id: str
    collection_slot_ordinal: int
    declared_collection_slots: int
    partition_slot_ordinal: int
    declared_partition_slots: int
    source_bundle_sha256: str
    teacher_execution_sha256: str
    source_commit: str | None = None

    def __post_init__(self) -> None:
        if self.collection_id != STRATEGIC_NAVIGATION_COLLECTION_ID:
            raise StrategicNavigationProtocolError("strategic assignment collection differs")
        for value, subject in (
            (self.registry_sha256, "strategic assignment registry digest"),
            (self.schedule_sha256, "strategic assignment schedule digest"),
            (self.assignment_id, "strategic assignment identity"),
            (self.source_bundle_sha256, "strategic assignment source digest"),
            (self.teacher_execution_sha256, "strategic assignment execution digest"),
        ):
            _sha256(value, subject)
        _safe_id(self.run_id, "strategic assignment run identity")
        _uint64(self.harness_seed, "strategic assignment harness seed")
        if self.partition not in _PARTITION_COUNTS:
            raise StrategicNavigationProtocolError("strategic assignment partition differs")
        if not 1 <= self.collection_slot_ordinal <= self.declared_collection_slots:
            raise StrategicNavigationProtocolError("strategic assignment collection slot differs")
        if self.declared_collection_slots != _RUN_COUNT:
            raise StrategicNavigationProtocolError("strategic assignment collection total differs")
        if not 1 <= self.partition_slot_ordinal <= self.declared_partition_slots:
            raise StrategicNavigationProtocolError("strategic assignment partition slot differs")
        if self.declared_partition_slots != _PARTITION_COUNTS[self.partition]:
            raise StrategicNavigationProtocolError("strategic assignment partition total differs")
        expected_assignment = collection_document_sha256(
            {
                "collection_id": STRATEGIC_NAVIGATION_COLLECTION_ID,
                "harness_seed": self.harness_seed,
                "partition": self.partition,
                "registry_sha256": self.registry_sha256,
                "run_id": self.run_id,
                "schedule_sha256": self.schedule_sha256,
                "schema": STRATEGIC_NAVIGATION_ASSIGNMENT_SCHEMA,
                "teacher_execution_sha256": self.teacher_execution_sha256,
            }
        )
        if self.assignment_id != expected_assignment:
            raise StrategicNavigationProtocolError("strategic assignment digest differs")
        if self.root_lineage_id != f"red-strategic-root-{self.assignment_id}":
            raise StrategicNavigationProtocolError("strategic assignment lineage differs")
        if self.episode_id != f"red-strategic-teacher-{self.assignment_id}":
            raise StrategicNavigationProtocolError("strategic assignment episode differs")
        if self.source_commit is not None and _GIT_OID.fullmatch(self.source_commit) is None:
            raise StrategicNavigationProtocolError("strategic assignment commit differs")

    def metadata_dict(self) -> dict[str, object]:
        return {
            "assignment_id": self.assignment_id,
            "attempt": {"attempts_per_slot": 1, "counted": True},
            "collection_id": self.collection_id,
            "collection_slot": {
                "collection_ordinal": self.collection_slot_ordinal,
                "collection_total": self.declared_collection_slots,
                "partition_ordinal": self.partition_slot_ordinal,
                "partition_total": self.declared_partition_slots,
            },
            "execution": {
                "source_bundle_sha256": self.source_bundle_sha256,
                "teacher_execution_sha256": self.teacher_execution_sha256,
            },
            "harness_seed": self.harness_seed,
            "registry_sha256": self.registry_sha256,
            "run_id": self.run_id,
            "schedule": {
                "schema": BATTLE_START_SCHEDULE_SCHEMA,
                "schedule_sha256": self.schedule_sha256,
            },
            "split": {
                "partition": self.partition,
                "regime": STRATEGIC_NAVIGATION_REGIME,
                "root_lineage_id": self.root_lineage_id,
            },
        }


@dataclass(frozen=True, slots=True)
class StrategicNavigationCollectionRegistry:
    """Canonical prospective strategic-navigation collection plan."""

    registry_sha256: str
    execution: StrategicNavigationExecution
    schedule: BattleStartSchedule
    rehearsal: StrategicNavigationRehearsal
    runs: tuple[StrategicNavigationCollectionRun, ...]

    @property
    def partition_counts(self) -> dict[str, int]:
        return dict(sorted(Counter(run.partition for run in self.runs).items()))

    def run(self, run_id: str) -> StrategicNavigationCollectionRun:
        matches = tuple(run for run in self.runs if run.run_id == run_id)
        if len(matches) != 1:
            raise StrategicNavigationProtocolError("strategic collection run is unavailable")
        return matches[0]

    def assignment(self, run_id: str) -> StrategicNavigationAssignment:
        run = self.run(run_id)
        ordinal = self.runs.index(run) + 1
        partition_rows = tuple(item for item in self.runs if item.partition == run.partition)
        partition_ordinal = partition_rows.index(run) + 1
        assignment_id = collection_document_sha256(
            {
                "collection_id": STRATEGIC_NAVIGATION_COLLECTION_ID,
                "harness_seed": run.harness_seed,
                "partition": run.partition,
                "registry_sha256": self.registry_sha256,
                "run_id": run.run_id,
                "schedule_sha256": run.schedule_sha256,
                "schema": STRATEGIC_NAVIGATION_ASSIGNMENT_SCHEMA,
                "teacher_execution_sha256": self.execution.teacher_execution_sha256,
            }
        )
        return StrategicNavigationAssignment(
            collection_id=STRATEGIC_NAVIGATION_COLLECTION_ID,
            registry_sha256=self.registry_sha256,
            run_id=run.run_id,
            partition=run.partition,
            harness_seed=run.harness_seed,
            schedule_sha256=run.schedule_sha256,
            assignment_id=assignment_id,
            root_lineage_id=f"red-strategic-root-{assignment_id}",
            episode_id=f"red-strategic-teacher-{assignment_id}",
            collection_slot_ordinal=ordinal,
            declared_collection_slots=len(self.runs),
            partition_slot_ordinal=partition_ordinal,
            declared_partition_slots=len(partition_rows),
            source_bundle_sha256=self.execution.source_bundle_sha256,
            teacher_execution_sha256=self.execution.teacher_execution_sha256,
            source_commit=self.execution.source_commit,
        )

    def learning_assignment(self, run_id: str) -> StrategicNavigationAssignment:
        """Return a train/validation assignment while leaving test roots sealed."""

        assignment = self.assignment(run_id)
        if assignment.partition == "test":
            raise StrategicNavigationProtocolError(
                "the strategic navigation test partition must remain unopened"
            )
        return assignment


def strategic_navigation_contract_document() -> dict[str, object]:
    """Return the portable vocabulary frozen before collection."""

    return {
        "availability": sorted(item.value for item in DestinationAvailability),
        "failure_reasons": sorted(item.value for item in NavigationFailureReason),
        "interruption_kinds": sorted(item.value for item in StrategicInterruptionKind),
        "interruption_resolutions": sorted(
            item.value for item in StrategicInterruptionResolution
        ),
        "model_input_excludes": [
            "coordinates",
            "destination_refs",
            "map_ids",
            "movement_actions",
            "origin_region_ref",
        ],
        "outcome_statuses": sorted(item.value for item in NavigationOutcomeStatus),
        "replan_reasons": sorted(item.value for item in StrategicReplanReason),
        "resource_kinds": sorted(item.value for item in StrategicResourceKind),
        "schema": STRATEGIC_NAVIGATION_CONTRACT_SCHEMA,
        "semantic_tags": sorted(item.value for item in StrategicNavigationTag),
        "unavailability_reasons": sorted(
            item.value for item in DestinationUnavailableReason
        ),
    }


def parse_strategic_navigation_registry(
    payload: bytes,
) -> StrategicNavigationCollectionRegistry:
    """Parse exact canonical bytes and reject split or execution drift."""

    if not isinstance(payload, bytes):
        raise TypeError("strategic navigation registry must be bytes")
    if not payload or len(payload) > _MAX_REGISTRY_BYTES:
        raise StrategicNavigationProtocolError("strategic navigation registry size is invalid")
    try:
        document = json.loads(
            payload.decode("ascii"),
            object_pairs_hook=_unique_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise StrategicNavigationProtocolError(
            "strategic navigation registry is not canonical ASCII JSON"
        ) from None
    if not isinstance(document, dict) or _canonical_line(document) != payload:
        raise StrategicNavigationProtocolError(
            "strategic navigation registry is not canonical ASCII JSON"
        )
    _exact_keys(
        document,
        {
            "adapter_id",
            "collection_id",
            "execution",
            "game_id",
            "ontology_id",
            "policy",
            "regime",
            "rehearsal",
            "runs",
            "schedule",
            "schema",
        },
        "strategic navigation registry",
    )
    expected_scalars = {
        "adapter_id": STRATEGIC_NAVIGATION_ADAPTER_ID,
        "collection_id": STRATEGIC_NAVIGATION_COLLECTION_ID,
        "game_id": STRATEGIC_NAVIGATION_GAME_ID,
        "ontology_id": STRATEGIC_NAVIGATION_ONTOLOGY_ID,
        "regime": STRATEGIC_NAVIGATION_REGIME,
        "schema": STRATEGIC_NAVIGATION_REGISTRY_SCHEMA,
    }
    if any(document[key] != value for key, value in expected_scalars.items()):
        raise StrategicNavigationProtocolError(
            "strategic navigation registry identity is unsupported"
        )
    policy = _mapping(document["policy"], "strategic navigation policy")
    _exact_keys(policy, {"actor", "policy_id"}, "strategic navigation policy")
    if policy != {
        "actor": STRATEGIC_NAVIGATION_ACTOR,
        "policy_id": STRATEGIC_NAVIGATION_POLICY_ID,
    }:
        raise StrategicNavigationProtocolError(
            "strategic navigation collection policy is unsupported"
        )
    schedule = _parse_schedule(document["schedule"])
    execution = _parse_execution(document["execution"])
    runs = _parse_runs(document["runs"], schedule)
    rehearsal = _parse_rehearsal(document["rehearsal"], schedule, runs)
    return StrategicNavigationCollectionRegistry(
        registry_sha256=hashlib.sha256(payload).hexdigest(),
        execution=execution,
        schedule=schedule,
        rehearsal=rehearsal,
        runs=runs,
    )


def load_committed_strategic_navigation_registry(
    repository_root: str | Path,
) -> StrategicNavigationCollectionRegistry:
    """Load registry and digest from HEAD, then bind them to committed source."""

    root = Path(repository_root).resolve()
    commit = _git_output(root, ["rev-parse", "--verify", "HEAD^{commit}"], 256).strip()
    try:
        commit_id = commit.decode("ascii")
    except UnicodeDecodeError:
        raise StrategicNavigationProtocolError("repository commit identity is invalid") from None
    if _GIT_OID.fullmatch(commit_id) is None:
        raise StrategicNavigationProtocolError("repository commit identity is invalid")
    digest_payload = _git_output(
        root,
        ["show", f"{commit_id}:{STRATEGIC_NAVIGATION_REGISTRY_DIGEST_RELATIVE_PATH}"],
        _MAX_DIGEST_BYTES,
    )
    registry_payload = _git_output(
        root,
        ["show", f"{commit_id}:{STRATEGIC_NAVIGATION_REGISTRY_RELATIVE_PATH}"],
        _MAX_REGISTRY_BYTES,
    )
    expected_bytes, expected_sha256 = _parse_digest(digest_payload)
    if (
        len(registry_payload) != expected_bytes
        or hashlib.sha256(registry_payload).hexdigest() != expected_sha256
    ):
        raise StrategicNavigationProtocolError(
            "committed strategic navigation registry digest is not frozen"
        )
    registry = parse_strategic_navigation_registry(registry_payload)
    source_bundle = committed_source_bundle_sha256(root, revision=commit_id)
    if registry.execution.source_bundle_sha256 != source_bundle:
        raise StrategicNavigationProtocolError(
            "committed source does not match the strategic navigation registry"
        )
    return replace(
        registry,
        execution=replace(registry.execution, source_commit=commit_id),
    )


def _parse_schedule(value: object) -> BattleStartSchedule:
    row = _mapping(value, "strategic timing schedule")
    _exact_keys(
        row,
        {
            "battle_plan_ids",
            "battle_roster_sha256",
            "derivation",
            "max_offset_frames",
            "schema",
        },
        "strategic timing schedule",
    )
    roster = row["battle_plan_ids"]
    if not isinstance(roster, list) or tuple(roster) != RED_BATTLE_PLAN_IDS:
        raise StrategicNavigationProtocolError("strategic battle roster is unsupported")
    expected_roster = collection_document_sha256(
        {"battle_plan_ids": roster, "schema": BATTLE_PLAN_ROSTER_SCHEMA}
    )
    if row != {
        "battle_plan_ids": roster,
        "battle_roster_sha256": expected_roster,
        "derivation": BATTLE_START_SCHEDULE_DERIVATION,
        "max_offset_frames": BATTLE_START_MAX_OFFSET_FRAMES,
        "schema": BATTLE_START_SCHEDULE_SCHEMA,
    }:
        raise StrategicNavigationProtocolError("strategic timing schedule is unsupported")
    return BattleStartSchedule(
        battle_plan_ids=RED_BATTLE_PLAN_IDS,
        battle_roster_sha256=expected_roster,
        derivation=BATTLE_START_SCHEDULE_DERIVATION,
        max_offset_frames=BATTLE_START_MAX_OFFSET_FRAMES,
        schema=BATTLE_START_SCHEDULE_SCHEMA,
    )


def _parse_execution(value: object) -> StrategicNavigationExecution:
    row = _mapping(value, "strategic execution")
    _exact_keys(
        row,
        {
            "behavior_configuration_sha256",
            "decision_contract_sha256",
            "objective_graph_sha256",
            "schema",
            "source_bundle_sha256",
            "teacher_execution_sha256",
        },
        "strategic execution",
    )
    for key in (
        "behavior_configuration_sha256",
        "decision_contract_sha256",
        "objective_graph_sha256",
        "source_bundle_sha256",
        "teacher_execution_sha256",
    ):
        _sha256(row[key], key.replace("_", " "))
    if row["schema"] != STRATEGIC_NAVIGATION_EXECUTION_SCHEMA:
        raise StrategicNavigationProtocolError("strategic execution schema is unsupported")
    contract_sha256 = collection_document_sha256(
        strategic_navigation_contract_document()
    )
    if row["decision_contract_sha256"] != contract_sha256:
        raise StrategicNavigationProtocolError("strategic decision contract digest differs")
    expected = collection_document_sha256(
        {
            "actor": STRATEGIC_NAVIGATION_ACTOR,
            "adapter_id": STRATEGIC_NAVIGATION_ADAPTER_ID,
            "behavior_configuration_sha256": row["behavior_configuration_sha256"],
            "collection_id": STRATEGIC_NAVIGATION_COLLECTION_ID,
            "decision_contract_sha256": row["decision_contract_sha256"],
            "game_id": STRATEGIC_NAVIGATION_GAME_ID,
            "objective_graph_sha256": row["objective_graph_sha256"],
            "ontology_id": STRATEGIC_NAVIGATION_ONTOLOGY_ID,
            "policy_id": STRATEGIC_NAVIGATION_POLICY_ID,
            "schema": STRATEGIC_NAVIGATION_EXECUTION_SCHEMA,
            "source_bundle_sha256": row["source_bundle_sha256"],
        }
    )
    if row["teacher_execution_sha256"] != expected:
        raise StrategicNavigationProtocolError("strategic teacher execution digest differs")
    return StrategicNavigationExecution(
        source_bundle_sha256=str(row["source_bundle_sha256"]),
        behavior_configuration_sha256=str(row["behavior_configuration_sha256"]),
        objective_graph_sha256=str(row["objective_graph_sha256"]),
        decision_contract_sha256=str(row["decision_contract_sha256"]),
        teacher_execution_sha256=str(row["teacher_execution_sha256"]),
    )


def _parse_runs(
    value: object,
    schedule: BattleStartSchedule,
) -> tuple[StrategicNavigationCollectionRun, ...]:
    if not isinstance(value, list) or len(value) != _RUN_COUNT:
        raise StrategicNavigationProtocolError("strategic collection run count is invalid")
    result: list[StrategicNavigationCollectionRun] = []
    for ordinal, raw in enumerate(value, start=1):
        row = _mapping(raw, "strategic collection run")
        _exact_keys(
            row,
            {"harness_seed", "partition", "run_id", "schedule_sha256"},
            "strategic collection run",
        )
        partition = row["partition"]
        if partition not in _PARTITION_COUNTS:
            raise StrategicNavigationProtocolError("strategic collection partition is invalid")
        run_id = _safe_id(row["run_id"], "strategic collection run identity")
        expected_id = f"red-strategic-v1-{ordinal:02d}-{partition}"
        if run_id != expected_id:
            raise StrategicNavigationProtocolError("strategic collection run order differs")
        seed = _uint64(row["harness_seed"], "strategic collection harness seed")
        schedule_sha256 = _sha256(row["schedule_sha256"], "strategic schedule digest")
        if schedule.schedule_sha256(seed) != schedule_sha256:
            raise StrategicNavigationProtocolError("strategic run schedule digest differs")
        result.append(
            StrategicNavigationCollectionRun(run_id, str(partition), seed, schedule_sha256)
        )
    runs = tuple(result)
    if Counter(run.partition for run in runs) != Counter(_PARTITION_COUNTS):
        raise StrategicNavigationProtocolError("strategic partition counts differ")
    if len({run.run_id for run in runs}) != len(runs):
        raise StrategicNavigationProtocolError("strategic run identities are duplicated")
    if len({run.harness_seed for run in runs}) != len(runs):
        raise StrategicNavigationProtocolError("strategic harness seeds are duplicated")
    if len({run.schedule_sha256 for run in runs}) != len(runs):
        raise StrategicNavigationProtocolError("strategic schedules are duplicated")
    return runs


def _parse_rehearsal(
    value: object,
    schedule: BattleStartSchedule,
    runs: tuple[StrategicNavigationCollectionRun, ...],
) -> StrategicNavigationRehearsal:
    row = _mapping(value, "strategic rehearsal")
    _exact_keys(
        row,
        {"harness_seed", "rehearsal_id", "schedule_sha256", "schema"},
        "strategic rehearsal",
    )
    if row["schema"] != STRATEGIC_NAVIGATION_REHEARSAL_SCHEMA:
        raise StrategicNavigationProtocolError("strategic rehearsal schema is unsupported")
    rehearsal_id = _safe_id(row["rehearsal_id"], "strategic rehearsal identity")
    if rehearsal_id != STRATEGIC_NAVIGATION_REHEARSAL_ID:
        raise StrategicNavigationProtocolError("strategic rehearsal identity differs")
    seed = _uint64(row["harness_seed"], "strategic rehearsal seed")
    if seed != STRATEGIC_NAVIGATION_REHEARSAL_SEED:
        raise StrategicNavigationProtocolError("strategic rehearsal seed differs")
    digest = _sha256(row["schedule_sha256"], "strategic rehearsal schedule digest")
    if schedule.schedule_sha256(seed) != digest:
        raise StrategicNavigationProtocolError("strategic rehearsal schedule digest differs")
    if seed in {run.harness_seed for run in runs} or digest in {
        run.schedule_sha256 for run in runs
    }:
        raise StrategicNavigationProtocolError("strategic rehearsal overlaps counted roots")
    return StrategicNavigationRehearsal(rehearsal_id, seed, digest)


def _parse_digest(payload: bytes) -> tuple[int, str]:
    if not payload or len(payload) > _MAX_DIGEST_BYTES:
        raise StrategicNavigationProtocolError("strategic registry digest size is invalid")
    try:
        row = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise StrategicNavigationProtocolError("strategic registry digest is invalid") from None
    if not isinstance(row, dict) or _canonical_line(row) != payload:
        raise StrategicNavigationProtocolError("strategic registry digest is invalid")
    _exact_keys(row, {"bytes", "schema", "sha256"}, "strategic registry digest")
    if row["schema"] != STRATEGIC_NAVIGATION_REGISTRY_DIGEST_SCHEMA:
        raise StrategicNavigationProtocolError("strategic registry digest schema differs")
    size = row["bytes"]
    if type(size) is not int or not 0 < size <= _MAX_REGISTRY_BYTES:  # noqa: E721
        raise StrategicNavigationProtocolError("strategic registry digest byte count is invalid")
    return size, _sha256(row["sha256"], "strategic registry digest")


def _git_output(root: Path, arguments: list[str], maximum_bytes: int) -> bytes:
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "LANG": "C",
            "LC_ALL": "C",
        }
    )
    try:
        result = subprocess.run(
            ["git", "--no-replace-objects", *arguments],
            cwd=root,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        raise StrategicNavigationProtocolError(
            "committed strategic registry is unavailable"
        ) from None
    if len(result.stdout) > maximum_bytes:
        raise StrategicNavigationProtocolError("committed strategic registry is too large")
    return result.stdout


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


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _mapping(value: object, subject: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise StrategicNavigationProtocolError(f"{subject} must be an object")
    return value


def _exact_keys(value: Mapping[str, object], expected: set[str], subject: str) -> None:
    if set(value) != expected:
        raise StrategicNavigationProtocolError(f"{subject} fields differ")


def _safe_id(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise StrategicNavigationProtocolError(f"{subject} is invalid")
    return value


def _sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise StrategicNavigationProtocolError(f"{subject} is invalid")
    return value


def _uint64(value: object, subject: str) -> int:
    if type(value) is not int or not 0 <= value < 1 << 64:  # noqa: E721
        raise StrategicNavigationProtocolError(f"{subject} is invalid")
    return value
