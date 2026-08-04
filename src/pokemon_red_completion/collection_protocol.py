"""Committed, path-free collection assignments for held-out Pokémon Red data.

The registry is public configuration. It contains no ROM data, trajectories,
snapshots, filesystem locations, or post-collection outcomes. A run's split,
harness seed, exact timing schedule, and lineage identities are derived from
the canonical committed registry rather than accepted as mutable CLI labels.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import selectors
import stat
import subprocess
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, replace
from pathlib import Path

from pokemon_red_completion.battle_plan import RED_BATTLE_PLAN_IDS

COLLECTION_REGISTRY_RELATIVE_PATH = "configs/red-battle-collection-v11.json"
COLLECTION_REGISTRY_DIGEST_RELATIVE_PATH = (
    "configs/red-battle-collection-v11.digest.json"
)
COLLECTION_REGISTRY_SCHEMA = "pokemon-red-collection-runs-v1"
COLLECTION_REGISTRY_DIGEST_SCHEMA = "pokemon-red-collection-registry-digest-v1"
COLLECTION_ASSIGNMENT_SCHEMA = "pokemon-red-collection-assignment-v1"
COLLECTION_EXECUTION_SCHEMA = "pokemon-red-teacher-execution-v1"
EXECUTABLE_SOURCE_BUNDLE_SCHEMA = "pokemon-red-executable-source-bundle-v2"
TEACHER_BEHAVIOR_CONFIGURATION_SCHEMA = "pokemon-red-teacher-behavior-v1"
OBJECTIVE_GRAPH_SCHEMA = "pokemon-red-objective-graph-v1"
SCHEDULE_DRY_RUN_SCHEMA = "pokemon-red-schedule-dry-run-v1"
SCHEDULE_DRY_RUN_SEED = 20001
BATTLE_PLAN_ROSTER_SCHEMA = "pokemon-red-battle-plan-roster-v1"
BATTLE_START_SCHEDULE_SCHEMA = "pokemon-red-battle-start-offset-v1"
BATTLE_START_SCHEDULE_DERIVATION = "sha256-mod-v1"
BATTLE_START_MAX_OFFSET_FRAMES = 255

POKEMON_RED_GAME_ID = "pokemon.mainline:red:gb:us:rev0"
POKEMON_RED_ADAPTER_ID = "pokemon.red.gb.us.rev0.v1"
POKEMON_CORE_ONTOLOGY_ID = "pokemon.core.v1"
POKEMON_RED_TEACHER_ACTOR = "deterministic_teacher"
POKEMON_RED_TEACHER_POLICY_ID = "pokemon-red-qualified-teacher-v1"

_EXPECTED_COLLECTION_ID = "red-battle-heldout-v11"
_EXPECTED_REGIME = "within_game"
_EXPECTED_DRY_RUN_ID = "red-battle-schedule-dry-run-v11"
_EXPECTED_PARTITION_COUNTS = {"test": 5, "train": 5, "validation": 2}
_EXPECTED_RUN_COUNT = sum(_EXPECTED_PARTITION_COUNTS.values())
_MAX_REGISTRY_BYTES = 1024 * 1024
_MAX_DIGEST_SIDECAR_BYTES = 4096
_MAX_SOURCE_INVENTORY_BYTES = 8 * 1024 * 1024
_MAX_SOURCE_BLOB_BYTES = 16 * 1024 * 1024
_MAX_SOURCE_TOTAL_BYTES = 128 * 1024 * 1024
_MAX_GIT_METADATA_BYTES = 4096
_MAX_UINT64 = (1 << 64) - 1
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_GIT_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_SCHEDULE_DOMAIN = BATTLE_START_SCHEDULE_SCHEMA.encode("ascii") + b"\0"


class CollectionProtocolError(RuntimeError):
    """Raised when collection configuration cannot prove its frozen assignment."""


@dataclass(frozen=True, slots=True)
class BattleStartOffset:
    """One deterministic, pre-policy timing offset for a stable battle-plan ID."""

    battle_plan_id: str
    frames: int

    def __post_init__(self) -> None:
        _require_safe_id(self.battle_plan_id, subject="battle plan identity")
        if (
            isinstance(self.frames, bool)
            or not isinstance(self.frames, int)
            or not 0 <= self.frames <= BATTLE_START_MAX_OFFSET_FRAMES
        ):
            raise CollectionProtocolError("battle-start offset frames are invalid")

    def public_dict(self) -> dict[str, object]:
        return {
            "battle_plan_id": self.battle_plan_id,
            "frames": self.frames,
        }


@dataclass(frozen=True, slots=True)
class BattleStartSchedule:
    """Versioned schedule generator shared by every declared collection run."""

    battle_plan_ids: tuple[str, ...]
    battle_roster_sha256: str
    derivation: str
    max_offset_frames: int
    schema: str

    def offsets(self, harness_seed: int) -> tuple[BattleStartOffset, ...]:
        """Expand one uint64 harness seed into the exact ordered frame schedule."""

        seed = _require_uint64(harness_seed, subject="harness seed")
        encoded_seed = seed.to_bytes(8, "big")
        modulus = self.max_offset_frames + 1
        result: list[BattleStartOffset] = []
        for battle_plan_id in self.battle_plan_ids:
            digest = hashlib.sha256(
                _SCHEDULE_DOMAIN
                + encoded_seed
                + b"\0"
                + battle_plan_id.encode("ascii")
            ).digest()
            frames = int.from_bytes(digest[:8], "big") % modulus
            result.append(BattleStartOffset(battle_plan_id, frames))
        return tuple(result)

    def schedule_sha256(self, harness_seed: int) -> str:
        """Hash the exact expanded schedule rather than the seed alone."""

        return battle_start_offsets_sha256(self.offsets(harness_seed))


def battle_start_offsets_sha256(offsets: Sequence[BattleStartOffset]) -> str:
    """Hash one exact ordered schedule using the public canonical schema."""

    frozen = tuple(offsets)
    if not frozen or any(not isinstance(offset, BattleStartOffset) for offset in frozen):
        raise CollectionProtocolError("battle-start schedule offsets are invalid")
    return _canonical_sha256(
        {
            "offsets": [offset.public_dict() for offset in frozen],
            "schema": BATTLE_START_SCHEDULE_SCHEMA,
        }
    )


def teacher_behavior_configuration(
    *,
    pyboy_version: str,
    new_game_timing: Mapping[str, object],
    opening_timing: Mapping[str, object],
    play_timing: Mapping[str, object],
    pret_pokered_commit: str,
) -> dict[str, object]:
    """Build and validate the one canonical behavior-affecting configuration."""

    return _parse_behavior_configuration(
        {
            "emulator": {
                "human_input": False,
                "name": "PyBoy",
                "save_on_exit": False,
                "version": pyboy_version,
            },
            "new_game_timing": dict(new_game_timing),
            "opening_timing": dict(opening_timing),
            "play_timing": dict(play_timing),
            "pret_pokered_commit": pret_pokered_commit,
            "schedule_application_schema": BATTLE_START_SCHEDULE_SCHEMA,
            "schema": TEACHER_BEHAVIOR_CONFIGURATION_SCHEMA,
        }
    )


def objective_graph_document(
    objectives: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Domain-separate the canonical public objective graph."""

    if not objectives:
        raise CollectionProtocolError("objective graph must not be empty")
    return {
        "objectives": [dict(objective) for objective in objectives],
        "schema": OBJECTIVE_GRAPH_SCHEMA,
    }


@dataclass(frozen=True, slots=True)
class CollectionRun:
    """One preregistered root-lineage slot."""

    run_id: str
    partition: str
    harness_seed: int
    schedule_sha256: str


@dataclass(frozen=True, slots=True)
class CollectionExecution:
    """One invariant executable teacher contract shared by every run."""

    source_bundle_sha256: str
    behavior_configuration_json: bytes
    behavior_configuration_sha256: str
    objective_graph_sha256: str
    teacher_execution_sha256: str
    source_commit: str | None = None

    def behavior_configuration_dict(self) -> dict[str, object]:
        value = json.loads(self.behavior_configuration_json.decode("ascii"))
        if not isinstance(value, dict):  # pragma: no cover - parser establishes this
            raise AssertionError("behavior configuration is not an object")
        return value


@dataclass(frozen=True, slots=True)
class ScheduleDryRun:
    """One fixed non-evaluation schedule used only for real integration rehearsal."""

    dry_run_id: str
    registry_sha256: str
    harness_seed: int
    schedule_sha256: str
    offsets: tuple[BattleStartOffset, ...]


@dataclass(frozen=True, slots=True)
class CollectionAssignment:
    """All immutable identities and offsets derived for one declared run."""

    collection_id: str
    registry_sha256: str
    run_id: str
    partition: str
    harness_seed: int
    schedule_sha256: str
    schedule_id: str
    variation_id: str
    assignment_id: str
    root_lineage_id: str
    episode_id: str
    collection_slot_ordinal: int
    declared_collection_slots: int
    partition_slot_ordinal: int
    declared_partition_slots: int
    source_bundle_sha256: str
    behavior_configuration_sha256: str
    objective_graph_sha256: str
    teacher_execution_sha256: str
    offsets: tuple[BattleStartOffset, ...]

    def metadata_dict(self) -> dict[str, object]:
        """Return the path-free identity block suitable for an episode header."""

        return {
            "assignment_id": self.assignment_id,
            "attempt": {
                "counted": True,
                "attempts_per_slot": 1,
            },
            "collection_slot": {
                "collection_ordinal": self.collection_slot_ordinal,
                "collection_total": self.declared_collection_slots,
                "partition_ordinal": self.partition_slot_ordinal,
                "partition_total": self.declared_partition_slots,
            },
            "collection_id": self.collection_id,
            "execution": {
                "behavior_configuration_sha256": self.behavior_configuration_sha256,
                "objective_graph_sha256": self.objective_graph_sha256,
                "source_bundle_sha256": self.source_bundle_sha256,
                "teacher_execution_sha256": self.teacher_execution_sha256,
            },
            "harness_seed": self.harness_seed,
            "registry_sha256": self.registry_sha256,
            "run_id": self.run_id,
            "schedule": {
                "schedule_id": self.schedule_id,
                "schedule_sha256": self.schedule_sha256,
                "schema": BATTLE_START_SCHEDULE_SCHEMA,
                "variation_id": self.variation_id,
            },
            "split": {
                "partition": self.partition,
                "regime": _EXPECTED_REGIME,
                "root_lineage_id": self.root_lineage_id,
            },
        }


@dataclass(frozen=True, slots=True)
class CollectionRegistry:
    """Fully validated immutable view of the canonical public registry."""

    collection_id: str
    game_id: str
    adapter_id: str
    ontology_id: str
    regime: str
    policy_actor: str
    policy_id: str
    execution: CollectionExecution
    schedule: BattleStartSchedule
    schedule_dry_run: ScheduleDryRun
    runs: tuple[CollectionRun, ...]
    registry_sha256: str

    @property
    def partition_counts(self) -> dict[str, int]:
        return dict(Counter(run.partition for run in self.runs))

    def run(self, run_id: str) -> CollectionRun:
        """Resolve a safe declared identifier without echoing untrusted input."""

        _require_safe_id(run_id, subject="collection run identity")
        for run in self.runs:
            if run.run_id == run_id:
                return run
        raise CollectionProtocolError("collection run is not declared")

    def assignment(self, run_id: str) -> CollectionAssignment:
        """Derive the collision-safe identity and exact schedule for one run."""

        run = self.run(run_id)
        assignment_id = _canonical_sha256(
            {
                "collection_id": self.collection_id,
                "harness_seed": run.harness_seed,
                "partition": run.partition,
                "registry_sha256": self.registry_sha256,
                "run_id": run.run_id,
                "schedule_sha256": run.schedule_sha256,
                "schema": COLLECTION_ASSIGNMENT_SCHEMA,
                "teacher_execution_sha256": self.execution.teacher_execution_sha256,
            }
        )
        partition_runs = tuple(
            candidate for candidate in self.runs if candidate.partition == run.partition
        )
        return CollectionAssignment(
            collection_id=self.collection_id,
            registry_sha256=self.registry_sha256,
            run_id=run.run_id,
            partition=run.partition,
            harness_seed=run.harness_seed,
            schedule_sha256=run.schedule_sha256,
            schedule_id=f"schedule-{run.schedule_sha256}",
            variation_id=f"variation-{run.schedule_sha256}",
            assignment_id=assignment_id,
            root_lineage_id=f"red-root-{assignment_id}",
            episode_id=f"red-teacher-{assignment_id}",
            collection_slot_ordinal=self.runs.index(run) + 1,
            declared_collection_slots=len(self.runs),
            partition_slot_ordinal=partition_runs.index(run) + 1,
            declared_partition_slots=len(partition_runs),
            source_bundle_sha256=self.execution.source_bundle_sha256,
            behavior_configuration_sha256=(
                self.execution.behavior_configuration_sha256
            ),
            objective_graph_sha256=self.execution.objective_graph_sha256,
            teacher_execution_sha256=self.execution.teacher_execution_sha256,
            offsets=self.schedule.offsets(run.harness_seed),
        )


def parse_collection_registry(payload: bytes) -> CollectionRegistry:
    """Validate and freeze one exact canonical collection registry."""

    document, canonical_payload = _decode_canonical_registry(payload)
    _require_exact_keys(
        document,
        {
            "adapter_id",
            "collection_id",
            "execution",
            "game_id",
            "ontology_id",
            "policy",
            "regime",
            "runs",
            "schedule",
            "schedule_dry_run",
            "schema",
        },
        subject="collection registry",
    )
    if document["schema"] != COLLECTION_REGISTRY_SCHEMA:
        raise CollectionProtocolError("collection registry schema is unsupported")
    collection_id = _require_exact_string(
        document["collection_id"],
        expected=_EXPECTED_COLLECTION_ID,
        subject="collection identity",
    )
    game_id = _require_exact_string(
        document["game_id"],
        expected=POKEMON_RED_GAME_ID,
        subject="game identity",
    )
    adapter_id = _require_exact_string(
        document["adapter_id"],
        expected=POKEMON_RED_ADAPTER_ID,
        subject="adapter identity",
    )
    ontology_id = _require_exact_string(
        document["ontology_id"],
        expected=POKEMON_CORE_ONTOLOGY_ID,
        subject="ontology identity",
    )
    regime = _require_exact_string(
        document["regime"],
        expected=_EXPECTED_REGIME,
        subject="split regime",
    )
    policy_actor, policy_id = _parse_policy(document["policy"])
    execution = _parse_execution(
        document["execution"],
        collection_id=collection_id,
        game_id=game_id,
        adapter_id=adapter_id,
        ontology_id=ontology_id,
        policy_actor=policy_actor,
        policy_id=policy_id,
    )
    schedule = _parse_schedule(document["schedule"])
    runs = _parse_runs(document["runs"], schedule=schedule)
    schedule_dry_run = _parse_schedule_dry_run(
        document["schedule_dry_run"],
        schedule=schedule,
        runs=runs,
        registry_sha256=hashlib.sha256(canonical_payload).hexdigest(),
    )
    return CollectionRegistry(
        collection_id=collection_id,
        game_id=game_id,
        adapter_id=adapter_id,
        ontology_id=ontology_id,
        regime=regime,
        policy_actor=policy_actor,
        policy_id=policy_id,
        execution=execution,
        schedule=schedule,
        schedule_dry_run=schedule_dry_run,
        runs=runs,
        registry_sha256=hashlib.sha256(canonical_payload).hexdigest(),
    )


def load_committed_collection_registry(repository_root: str | Path) -> CollectionRegistry:
    """Authenticate registry, sidecar, and executable source from one HEAD commit."""

    root = Path(repository_root)
    commit = _resolve_commit(root)
    sidecar_payload = _read_committed_blob(
        root,
        commit,
        COLLECTION_REGISTRY_DIGEST_RELATIVE_PATH,
        subject="committed collection digest",
        maximum_bytes=_MAX_DIGEST_SIDECAR_BYTES,
    )
    expected_bytes, expected_sha256 = _parse_registry_digest_sidecar(sidecar_payload)
    registry_payload = _read_committed_blob(
        root,
        commit,
        COLLECTION_REGISTRY_RELATIVE_PATH,
        subject="committed collection registry",
        maximum_bytes=_MAX_REGISTRY_BYTES,
    )
    if (
        len(registry_payload) != expected_bytes
        or hashlib.sha256(registry_payload).hexdigest() != expected_sha256
    ):
        raise CollectionProtocolError("committed collection registry digest is not frozen")
    registry = parse_collection_registry(registry_payload)
    source_bundle_sha256 = committed_source_bundle_sha256(root, revision=commit)
    if registry.execution.source_bundle_sha256 != source_bundle_sha256:
        raise CollectionProtocolError(
            "committed executable source does not match the collection registry"
        )
    return replace(
        registry,
        execution=replace(registry.execution, source_commit=commit),
    )


def committed_source_bundle_sha256(
    repository_root: str | Path,
    *,
    revision: str = "HEAD",
) -> str:
    """Hash exact committed executable blobs without including collection config."""

    root = Path(repository_root)
    commit = _resolve_commit(root, revision=revision)
    listing = _run_git(
        root,
        [
            "ls-tree",
            "-r",
            "-z",
            "--full-tree",
            commit,
            "--",
            "pyproject.toml",
            "src/pokemon_red_completion",
        ],
        subject="committed executable source",
        maximum_output_bytes=_MAX_SOURCE_INVENTORY_BYTES,
    )
    entries: list[dict[str, object]] = []
    total_bytes = 0
    for record in listing.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, object_type, raw_oid = metadata.split(b" ", 2)
            path = raw_path.decode("ascii")
            oid = raw_oid.decode("ascii")
        except (UnicodeDecodeError, ValueError):
            raise CollectionProtocolError(
                "committed executable source inventory is invalid"
            ) from None
        if (
            mode not in {b"100644", b"100755"}
            or object_type != b"blob"
            or _GIT_OID.fullmatch(oid) is None
            or not (
                path == "pyproject.toml"
                or path.startswith("src/pokemon_red_completion/")
            )
            or "\\" in path
        ):
            raise CollectionProtocolError(
                "committed executable source inventory is invalid"
            )
        blob = _read_git_object(
            root,
            oid,
            subject="committed executable source",
            maximum_bytes=_MAX_SOURCE_BLOB_BYTES,
        )
        total_bytes += len(blob)
        if total_bytes > _MAX_SOURCE_TOTAL_BYTES:
            raise CollectionProtocolError("committed executable source is too large")
        entries.append(
            {
                "bytes": len(blob),
                "mode": mode.decode("ascii"),
                "path": path,
                "sha256": hashlib.sha256(blob).hexdigest(),
            }
        )
    entries.sort(key=lambda entry: str(entry["path"]))
    if not entries or entries[0]["path"] != "pyproject.toml":
        raise CollectionProtocolError("committed executable source inventory is incomplete")
    if not any(
        str(entry["path"]).startswith("src/pokemon_red_completion/")
        for entry in entries
    ):
        raise CollectionProtocolError("committed executable source inventory is incomplete")
    return _source_bundle_digest(entries)


def working_source_bundle_sha256(repository_root: str | Path) -> str:
    """Hash the prospective executable bundle before its publication commit."""

    root = Path(repository_root)
    inventory = _run_git(
        root,
        [
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            "pyproject.toml",
            "src/pokemon_red_completion",
        ],
        subject="working executable source",
        maximum_output_bytes=_MAX_SOURCE_INVENTORY_BYTES,
    )
    entries: list[dict[str, object]] = []
    total_bytes = 0
    inventory_paths: set[str] = set()
    for raw_path in inventory.split(b"\0"):
        if not raw_path:
            continue
        try:
            path = raw_path.decode("ascii")
        except UnicodeDecodeError:
            raise CollectionProtocolError(
                "working executable source inventory is invalid"
            ) from None
        if (
            not (
                path == "pyproject.toml"
                or path.startswith("src/pokemon_red_completion/")
            )
            or "\\" in path
            or "/__pycache__/" in path
            or path.endswith((".pyc", ".pyo"))
        ):
            raise CollectionProtocolError("working executable source inventory is invalid")
        if path in inventory_paths:
            raise CollectionProtocolError("working executable source inventory is invalid")
        inventory_paths.add(path)
        candidate = root / path
        blob, mode = _read_working_source_file(candidate)
        total_bytes += len(blob)
        if total_bytes > _MAX_SOURCE_TOTAL_BYTES:
            raise CollectionProtocolError("working executable source is too large")
        entries.append(
            {
                "bytes": len(blob),
                "mode": mode,
                "path": path,
                "sha256": hashlib.sha256(blob).hexdigest(),
            }
        )
    entries.sort(key=lambda entry: str(entry["path"]))
    if not entries or entries[0]["path"] != "pyproject.toml":
        raise CollectionProtocolError("working executable source inventory is incomplete")
    if inventory_paths != _working_source_filesystem_paths(root):
        raise CollectionProtocolError(
            "working executable source contains untracked ignored content"
        )
    return _source_bundle_digest(entries)


def _source_bundle_digest(entries: list[dict[str, object]]) -> str:
    return _canonical_sha256(
        {
            "files": entries,
            "schema": EXECUTABLE_SOURCE_BUNDLE_SCHEMA,
        }
    )


def _read_working_source_file(path: Path) -> tuple[bytes, str]:
    try:
        expected = path.lstat()
    except OSError:
        raise CollectionProtocolError("working executable source is unavailable") from None
    if (
        stat.S_ISLNK(expected.st_mode)
        or not stat.S_ISREG(expected.st_mode)
        or expected.st_nlink != 1
    ):
        raise CollectionProtocolError("working executable source inventory is invalid")
    if expected.st_size < 0 or expected.st_size > _MAX_SOURCE_BLOB_BYTES:
        raise CollectionProtocolError("working executable source is too large")

    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = -1
    try:
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if (
            opened.st_dev != expected.st_dev
            or opened.st_ino != expected.st_ino
            or opened.st_size != expected.st_size
            or opened.st_mtime_ns != expected.st_mtime_ns
            or opened.st_ctime_ns != expected.st_ctime_ns
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
        ):
            raise CollectionProtocolError(
                "working executable source changed while opening"
            )
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(
                descriptor,
                min(1024 * 1024, _MAX_SOURCE_BLOB_BYTES - total + 1),
            )
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > _MAX_SOURCE_BLOB_BYTES:
                raise CollectionProtocolError("working executable source is too large")
        finished = os.fstat(descriptor)
        if (
            finished.st_size != opened.st_size
            or finished.st_mtime_ns != opened.st_mtime_ns
            or finished.st_ctime_ns != opened.st_ctime_ns
            or total != opened.st_size
        ):
            raise CollectionProtocolError(
                "working executable source changed while reading"
            )
        return (
            b"".join(chunks),
            "100755" if opened.st_mode & 0o111 else "100644",
        )
    except CollectionProtocolError:
        raise
    except OSError:
        raise CollectionProtocolError("working executable source is unavailable") from None
    finally:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)


def _working_source_filesystem_paths(root: Path) -> set[str]:
    candidates = [root / "pyproject.toml"]
    source_root = root / "src" / "pokemon_red_completion"
    try:
        candidates.extend(source_root.rglob("*"))
    except OSError:
        raise CollectionProtocolError("working executable source is unavailable") from None
    result: set[str] = set()
    for candidate in candidates:
        try:
            relative = candidate.relative_to(root).as_posix()
            if candidate.is_symlink():
                raise CollectionProtocolError(
                    "working executable source inventory is invalid"
                )
            if candidate.is_dir():
                continue
            if not candidate.is_file():
                raise CollectionProtocolError(
                    "working executable source inventory is invalid"
                )
        except (OSError, ValueError):
            raise CollectionProtocolError(
                "working executable source inventory is invalid"
            ) from None
        if "/__pycache__/" in relative or relative.endswith((".pyc", ".pyo")):
            continue
        try:
            relative.encode("ascii")
        except UnicodeEncodeError:
            raise CollectionProtocolError(
                "working executable source inventory is invalid"
            ) from None
        result.add(relative)
    return result


def _parse_registry_digest_sidecar(payload: bytes) -> tuple[int, str]:
    if (
        not isinstance(payload, bytes)
        or not payload
        or len(payload) > _MAX_DIGEST_SIDECAR_BYTES
    ):
        raise CollectionProtocolError("committed collection digest is invalid")
    try:
        document = json.loads(
            payload.decode("ascii"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (CollectionProtocolError, RecursionError, UnicodeDecodeError, ValueError):
        raise CollectionProtocolError("committed collection digest is invalid") from None
    if not isinstance(document, dict) or payload != _canonical_json_line(document):
        raise CollectionProtocolError("committed collection digest is invalid")
    _require_exact_keys(
        document,
        {"bytes", "schema", "sha256"},
        subject="committed collection digest",
    )
    if document["schema"] != COLLECTION_REGISTRY_DIGEST_SCHEMA:
        raise CollectionProtocolError("committed collection digest schema is unsupported")
    size = document["bytes"]
    if type(size) is not int or not 1 <= size <= _MAX_REGISTRY_BYTES:  # noqa: E721
        raise CollectionProtocolError("committed collection digest size is invalid")
    digest = _require_sha256(
        document["sha256"],
        subject="committed collection registry digest",
    )
    return size, digest


def _resolve_commit(root: Path, *, revision: str = "HEAD") -> str:
    if not isinstance(revision, str) or not revision:
        raise CollectionProtocolError("committed revision is invalid")
    payload = _run_git(
        root,
        ["rev-parse", "--verify", f"{revision}^{{commit}}"],
        subject="committed collection revision",
        maximum_output_bytes=_MAX_GIT_METADATA_BYTES,
    )
    try:
        commit = payload.decode("ascii").strip()
    except UnicodeDecodeError:
        raise CollectionProtocolError("committed collection revision is invalid") from None
    if _GIT_OID.fullmatch(commit) is None:
        raise CollectionProtocolError("committed collection revision is invalid")
    return commit


def _read_committed_blob(
    root: Path,
    commit: str,
    relative_path: str,
    *,
    subject: str,
    maximum_bytes: int,
) -> bytes:
    return _read_git_object(
        root,
        f"{commit}:{relative_path}",
        subject=subject,
        maximum_bytes=maximum_bytes,
    )


def _read_git_object(
    root: Path,
    object_spec: str,
    *,
    subject: str,
    maximum_bytes: int,
) -> bytes:
    size_payload = _run_git(
        root,
        ["cat-file", "-s", object_spec],
        subject=subject,
        maximum_output_bytes=_MAX_GIT_METADATA_BYTES,
    )
    try:
        size = int(size_payload.decode("ascii").strip())
    except (UnicodeDecodeError, ValueError):
        raise CollectionProtocolError(f"{subject} is unavailable") from None
    if size < 0 or size > maximum_bytes:
        raise CollectionProtocolError(f"{subject} exceeds its size limit")
    payload = _run_git(
        root,
        ["cat-file", "blob", object_spec],
        subject=subject,
        maximum_output_bytes=maximum_bytes,
    )
    if len(payload) != size:
        raise CollectionProtocolError(f"{subject} changed while reading")
    return payload


def _run_git(
    root: Path,
    arguments: list[str],
    *,
    subject: str,
    maximum_output_bytes: int,
) -> bytes:
    if maximum_output_bytes <= 0:
        raise ValueError("maximum_output_bytes must be positive")
    process: subprocess.Popen[bytes] | None = None
    selector: selectors.BaseSelector | None = None
    try:
        resolved_root = root.resolve(strict=True)
        process = subprocess.Popen(
            [
                "git",
                "--no-replace-objects",
                f"--work-tree={resolved_root}",
                *arguments,
            ],
            cwd=resolved_root,
            env=_sanitized_git_environment(),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if process.stdout is None:  # pragma: no cover - Popen contract
            raise OSError("Git stdout pipe is unavailable")
        os.set_blocking(process.stdout.fileno(), False)
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + 10
        chunks: list[bytes] = []
        total = 0
        eof = False
        while not eof:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(["git", *arguments], timeout=10)
            events = selector.select(min(remaining, 0.25))
            for key, _mask in events:
                try:
                    chunk = os.read(
                        key.fileobj.fileno(),
                        min(64 * 1024, maximum_output_bytes - total + 1),
                    )
                except BlockingIOError:
                    continue
                if not chunk:
                    eof = True
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > maximum_output_bytes:
                    raise CollectionProtocolError(f"{subject} exceeds its size limit")
        remaining = max(0.001, deadline - time.monotonic())
        return_code = process.wait(timeout=remaining)
        if return_code != 0:
            raise CollectionProtocolError(f"{subject} is unavailable")
        return b"".join(chunks)
    except CollectionProtocolError:
        raise
    except (OSError, subprocess.SubprocessError):
        raise CollectionProtocolError(f"{subject} is unavailable") from None
    finally:
        if selector is not None:
            selector.close()
        if process is not None and process.poll() is None:
            process.kill()
            with suppress(OSError, subprocess.SubprocessError):
                process.wait(timeout=1)


def _sanitized_git_environment() -> dict[str, str]:
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    environment.update(
        {
            "GIT_ATTR_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "LANG": "C",
            "LC_ALL": "C",
        }
    )
    return environment


def _parse_policy(value: object) -> tuple[str, str]:
    policy = _require_mapping(value, subject="collection policy")
    _require_exact_keys(policy, {"actor", "policy_id"}, subject="collection policy")
    actor = _require_exact_string(
        policy["actor"],
        expected=POKEMON_RED_TEACHER_ACTOR,
        subject="collection actor",
    )
    policy_id = _require_exact_string(
        policy["policy_id"],
        expected=POKEMON_RED_TEACHER_POLICY_ID,
        subject="collection policy identity",
    )
    return actor, policy_id


def _parse_execution(
    value: object,
    *,
    collection_id: str,
    game_id: str,
    adapter_id: str,
    ontology_id: str,
    policy_actor: str,
    policy_id: str,
) -> CollectionExecution:
    execution = _require_mapping(value, subject="collection execution")
    _require_exact_keys(
        execution,
        {
            "behavior_configuration",
            "behavior_configuration_sha256",
            "objective_graph_sha256",
            "schema",
            "source_bundle_sha256",
            "teacher_execution_sha256",
        },
        subject="collection execution",
    )
    if execution["schema"] != COLLECTION_EXECUTION_SCHEMA:
        raise CollectionProtocolError("collection execution schema is unsupported")
    source_bundle_sha256 = _require_sha256(
        execution["source_bundle_sha256"],
        subject="source bundle digest",
    )
    behavior = _parse_behavior_configuration(execution["behavior_configuration"])
    behavior_configuration_sha256 = _require_sha256(
        execution["behavior_configuration_sha256"],
        subject="behavior configuration digest",
    )
    if _canonical_sha256(behavior) != behavior_configuration_sha256:
        raise CollectionProtocolError(
            "behavior configuration digest does not match its configuration"
        )
    objective_graph_sha256 = _require_sha256(
        execution["objective_graph_sha256"],
        subject="objective graph digest",
    )
    teacher_execution_sha256 = _require_sha256(
        execution["teacher_execution_sha256"],
        subject="teacher execution digest",
    )
    expected_execution_sha256 = _canonical_sha256(
        {
            "actor": policy_actor,
            "adapter_id": adapter_id,
            "behavior_configuration_sha256": behavior_configuration_sha256,
            "collection_id": collection_id,
            "game_id": game_id,
            "objective_graph_sha256": objective_graph_sha256,
            "ontology_id": ontology_id,
            "policy_id": policy_id,
            "schema": COLLECTION_EXECUTION_SCHEMA,
            "source_bundle_sha256": source_bundle_sha256,
        }
    )
    if teacher_execution_sha256 != expected_execution_sha256:
        raise CollectionProtocolError(
            "teacher execution digest does not match its frozen inputs"
        )
    return CollectionExecution(
        source_bundle_sha256=source_bundle_sha256,
        behavior_configuration_json=_canonical_json_line(behavior),
        behavior_configuration_sha256=behavior_configuration_sha256,
        objective_graph_sha256=objective_graph_sha256,
        teacher_execution_sha256=teacher_execution_sha256,
    )


def _parse_behavior_configuration(value: object) -> dict[str, object]:
    behavior = _require_mapping(value, subject="teacher behavior configuration")
    _require_exact_keys(
        behavior,
        {
            "emulator",
            "new_game_timing",
            "opening_timing",
            "play_timing",
            "pret_pokered_commit",
            "schedule_application_schema",
            "schema",
        },
        subject="teacher behavior configuration",
    )
    if behavior["schema"] != TEACHER_BEHAVIOR_CONFIGURATION_SCHEMA:
        raise CollectionProtocolError("teacher behavior schema is unsupported")
    pret_commit = behavior["pret_pokered_commit"]
    if type(pret_commit) is not str or _SHA1.fullmatch(pret_commit) is None:  # noqa: E721
        raise CollectionProtocolError("teacher mechanics commit is invalid")
    if behavior["schedule_application_schema"] != BATTLE_START_SCHEDULE_SCHEMA:
        raise CollectionProtocolError("teacher schedule application schema is unsupported")
    emulator = _require_mapping(
        behavior["emulator"],
        subject="teacher emulator configuration",
    )
    _require_exact_keys(
        emulator,
        {"human_input", "name", "save_on_exit", "version"},
        subject="teacher emulator configuration",
    )
    if emulator != {
        "human_input": False,
        "name": "PyBoy",
        "save_on_exit": False,
        "version": "2.7.0",
    }:
        raise CollectionProtocolError("teacher emulator configuration is unsupported")
    for field in ("new_game_timing", "opening_timing", "play_timing"):
        timing = _require_mapping(behavior[field], subject=f"{field} configuration")
        if not timing:
            raise CollectionProtocolError(f"{field} configuration must not be empty")
        if any(
            type(name) is not str
            or not name
            or type(setting) is not int
            or setting <= 0
            for name, setting in timing.items()
        ):
            raise CollectionProtocolError(f"{field} configuration is invalid")
    return behavior


def _parse_schedule(value: object) -> BattleStartSchedule:
    schedule = _require_mapping(value, subject="battle-start schedule")
    _require_exact_keys(
        schedule,
        {
            "battle_plan_ids",
            "battle_roster_sha256",
            "derivation",
            "max_offset_frames",
            "schema",
        },
        subject="battle-start schedule",
    )
    if schedule["schema"] != BATTLE_START_SCHEDULE_SCHEMA:
        raise CollectionProtocolError("battle-start schedule schema is unsupported")
    if schedule["derivation"] != BATTLE_START_SCHEDULE_DERIVATION:
        raise CollectionProtocolError("battle-start schedule derivation is unsupported")
    if type(schedule["max_offset_frames"]) is not int:  # noqa: E721
        raise CollectionProtocolError("battle-start maximum offset must be an integer")
    if schedule["max_offset_frames"] != BATTLE_START_MAX_OFFSET_FRAMES:
        raise CollectionProtocolError("battle-start maximum offset is unsupported")

    raw_roster = schedule["battle_plan_ids"]
    if not isinstance(raw_roster, list):
        raise CollectionProtocolError("battle roster must be a list")
    roster = tuple(
        _require_safe_id(item, subject="battle roster identity") for item in raw_roster
    )
    if roster != RED_BATTLE_PLAN_IDS:
        raise CollectionProtocolError(
            "battle roster does not match the qualified route plan"
        )

    roster_sha256 = _require_sha256(
        schedule["battle_roster_sha256"],
        subject="battle roster digest",
    )
    expected_roster_sha256 = _canonical_sha256(
        {
            "battle_plan_ids": list(roster),
            "schema": BATTLE_PLAN_ROSTER_SCHEMA,
        }
    )
    if roster_sha256 != expected_roster_sha256:
        raise CollectionProtocolError("battle roster digest does not match its identities")
    return BattleStartSchedule(
        battle_plan_ids=roster,
        battle_roster_sha256=roster_sha256,
        derivation=BATTLE_START_SCHEDULE_DERIVATION,
        max_offset_frames=BATTLE_START_MAX_OFFSET_FRAMES,
        schema=BATTLE_START_SCHEDULE_SCHEMA,
    )


def _parse_schedule_dry_run(
    value: object,
    *,
    schedule: BattleStartSchedule,
    runs: tuple[CollectionRun, ...],
    registry_sha256: str,
) -> ScheduleDryRun:
    dry_run = _require_mapping(value, subject="schedule dry run")
    _require_exact_keys(
        dry_run,
        {"dry_run_id", "harness_seed", "schedule_sha256", "schema"},
        subject="schedule dry run",
    )
    if dry_run["schema"] != SCHEDULE_DRY_RUN_SCHEMA:
        raise CollectionProtocolError("schedule dry-run schema is unsupported")
    dry_run_id = _require_exact_string(
        dry_run["dry_run_id"],
        expected=_EXPECTED_DRY_RUN_ID,
        subject="schedule dry-run identity",
    )
    harness_seed = _require_uint64(
        dry_run["harness_seed"],
        subject="schedule dry-run harness seed",
    )
    if harness_seed != SCHEDULE_DRY_RUN_SEED:
        raise CollectionProtocolError("schedule dry-run harness seed is unsupported")
    schedule_sha256 = _require_sha256(
        dry_run["schedule_sha256"],
        subject="schedule dry-run digest",
    )
    if schedule.schedule_sha256(harness_seed) != schedule_sha256:
        raise CollectionProtocolError(
            "schedule dry-run digest does not match its harness seed"
        )
    if harness_seed in {run.harness_seed for run in runs}:
        raise CollectionProtocolError("schedule dry-run seed overlaps a collection run")
    if schedule_sha256 in {run.schedule_sha256 for run in runs}:
        raise CollectionProtocolError("schedule dry-run schedule overlaps a collection run")
    return ScheduleDryRun(
        dry_run_id=dry_run_id,
        registry_sha256=registry_sha256,
        harness_seed=harness_seed,
        schedule_sha256=schedule_sha256,
        offsets=schedule.offsets(harness_seed),
    )


def _parse_runs(
    value: object,
    *,
    schedule: BattleStartSchedule,
) -> tuple[CollectionRun, ...]:
    if not isinstance(value, list):
        raise CollectionProtocolError("collection runs must be a list")
    if len(value) != _EXPECTED_RUN_COUNT:
        raise CollectionProtocolError("collection registry must declare exactly 12 runs")

    runs: list[CollectionRun] = []
    for item in value:
        raw_run = _require_mapping(item, subject="collection run")
        _require_exact_keys(
            raw_run,
            {"harness_seed", "partition", "run_id", "schedule_sha256"},
            subject="collection run",
        )
        run_id = _require_safe_id(raw_run["run_id"], subject="collection run identity")
        partition = raw_run["partition"]
        if type(partition) is not str or partition not in _EXPECTED_PARTITION_COUNTS:  # noqa: E721
            raise CollectionProtocolError("collection run partition is unsupported")
        harness_seed = _require_uint64(raw_run["harness_seed"], subject="harness seed")
        schedule_sha256 = _require_sha256(
            raw_run["schedule_sha256"],
            subject="battle-start schedule digest",
        )
        if schedule.schedule_sha256(harness_seed) != schedule_sha256:
            raise CollectionProtocolError(
                "battle-start schedule digest does not match its harness seed"
            )
        runs.append(
            CollectionRun(
                run_id=run_id,
                partition=partition,
                harness_seed=harness_seed,
                schedule_sha256=schedule_sha256,
            )
        )

    if tuple(sorted(run.run_id for run in runs)) != tuple(run.run_id for run in runs):
        raise CollectionProtocolError("collection run identities must be sorted")
    if len({run.run_id for run in runs}) != len(runs):
        raise CollectionProtocolError("collection run identities must be unique")
    if len({run.harness_seed for run in runs}) != len(runs):
        raise CollectionProtocolError("collection harness seeds must be unique")
    if len({run.schedule_sha256 for run in runs}) != len(runs):
        raise CollectionProtocolError("collection schedules must be unique")
    if dict(Counter(run.partition for run in runs)) != _EXPECTED_PARTITION_COUNTS:
        raise CollectionProtocolError("collection partition counts do not match the frozen plan")
    return tuple(runs)


def _decode_canonical_registry(payload: bytes) -> tuple[dict[str, object], bytes]:
    if not isinstance(payload, bytes):
        raise TypeError("collection registry payload must be bytes")
    if not payload or len(payload) > _MAX_REGISTRY_BYTES:
        raise CollectionProtocolError("collection registry size is invalid")
    try:
        decoded = payload.decode("ascii")
    except UnicodeDecodeError:
        raise CollectionProtocolError("collection registry must be canonical ASCII JSON") from None
    try:
        document = json.loads(
            decoded,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except CollectionProtocolError:
        raise
    except (RecursionError, TypeError, ValueError, json.JSONDecodeError):
        raise CollectionProtocolError("collection registry is not valid JSON") from None
    if not isinstance(document, dict):
        raise CollectionProtocolError("collection registry must be a JSON object")
    canonical = _canonical_json_line(document)
    if payload != canonical:
        raise CollectionProtocolError("collection registry JSON is not canonical")
    return document, canonical


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise CollectionProtocolError("collection registry contains duplicate JSON keys")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    del value
    raise CollectionProtocolError("collection registry contains a non-finite number")


def _require_mapping(value: object, *, subject: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise CollectionProtocolError(f"{subject} must be an object")
    if not all(type(key) is str for key in value):  # noqa: E721
        raise CollectionProtocolError(f"{subject} keys must be strings")
    return dict(value)


def _require_exact_keys(
    value: Mapping[str, object],
    expected: set[str],
    *,
    subject: str,
) -> None:
    if set(value) != expected:
        raise CollectionProtocolError(f"{subject} keys do not match the schema")


def _require_exact_string(value: object, *, expected: str, subject: str) -> str:
    if type(value) is not str or value != expected:  # noqa: E721
        raise CollectionProtocolError(f"{subject} is unsupported")
    return value


def _require_safe_id(value: object, *, subject: str) -> str:
    if type(value) is not str or _SAFE_ID.fullmatch(value) is None:  # noqa: E721
        raise CollectionProtocolError(f"{subject} must be a safe lowercase identifier")
    return value


def _require_sha256(value: object, *, subject: str) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:  # noqa: E721
        raise CollectionProtocolError(f"{subject} must be a lowercase SHA-256 digest")
    return value


def _require_uint64(value: object, *, subject: str) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_UINT64:  # noqa: E721
        raise CollectionProtocolError(f"{subject} must be an unsigned 64-bit integer")
    return value


def _canonical_json_line(value: Mapping[str, object]) -> bytes:
    try:
        rendered = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (RecursionError, TypeError, ValueError):
        raise CollectionProtocolError("collection registry cannot be encoded") from None
    return rendered.encode("ascii") + b"\n"


def _canonical_sha256(value: Mapping[str, object]) -> str:
    return hashlib.sha256(_canonical_json_line(value)).hexdigest()


def collection_document_sha256(value: Mapping[str, object]) -> str:
    """Hash one canonical newline-terminated public collection document."""

    return _canonical_sha256(value)
