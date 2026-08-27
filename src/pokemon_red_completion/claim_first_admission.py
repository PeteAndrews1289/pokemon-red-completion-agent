"""Title-neutral durable admission for one protected game-state execution.

The account claim registry historically keyed consumption by one digest.  A
captured game state has two independent identities in the living-Pokedex
pipeline: the catalog's logical root and the actual state/envelope byte pair.
Claiming either identity alone leaves the other available to a differently
labelled runner.  This module commits both identities in one canonical record
and one atomic rename before a title adapter may construct a runtime.

It deliberately knows nothing about Red, Crystal, ROMs, routes, emulators, or
learner rows.  Title adapters retain those responsibilities.
"""

from __future__ import annotations

import json
import os
import re
import stat
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Self

from pokemon_red_completion.goal_manager_composition_qualification import (
    FixedAccountClaimRegistryLease,
    FreshCompositionQualificationError,
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
    root_claim_is_available,
)
from pokemon_red_completion.private_artifacts import (
    _rename_no_replace as atomic_no_replace_rename,
)
from pokemon_red_completion.provenance import canonical_sha256

CLAIM_FIRST_ROOT_PAIR_SCHEMA = "pokemon.core.claim-first-root-pair.v1"
CLAIM_FIRST_ROOT_PAIR_PREFIX = "claim-pair-v1-"
CLAIM_FIRST_EXECUTION_IDENTITY_SCHEMA = "pokemon.core.claim-first-execution-identity.v1"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_STAGE = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
_PAIR_NAME = re.compile(rf"{CLAIM_FIRST_ROOT_PAIR_PREFIX}([0-9a-f]{{64}})\.json\Z")
_MAXIMUM_PAIR_CLAIMS = 100_000
_MAXIMUM_PAIR_RECORD_BYTES = 4096


class ClaimFirstAdmissionError(RuntimeError):
    """A pair claim is unavailable, unsafe, or cannot be authenticated."""


@dataclass(frozen=True, slots=True)
class ClaimFirstExecutionIdentity:
    """Current consumer plus immutable producer identity for one slot execution."""

    source_commit: str
    source_bundle_sha256: str
    exact_ci_run: int
    exact_ci_attempt: int
    producer_execution_identity_sha256: str
    producer_plan_sha256: str
    producer_private_plan_sha256: str
    producer_manifest_sha256: str
    slot_sha256: str
    recipe_sha256: str
    logical_root_sha256: str
    physical_root_sha256: str
    title_adapter_sha256: str
    runtime_factory_sha256: str
    runner_sha256: str
    source_published: bool = True
    worktree_dirty: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.source_commit, str) or _GIT_COMMIT.fullmatch(
            self.source_commit
        ) is None:
            raise ClaimFirstAdmissionError("claim-first source commit differs")
        for value, subject in (
            (self.source_bundle_sha256, "source bundle"),
            (self.producer_execution_identity_sha256, "producer execution identity"),
            (self.producer_plan_sha256, "producer plan"),
            (self.producer_private_plan_sha256, "producer private plan"),
            (self.producer_manifest_sha256, "producer manifest"),
            (self.slot_sha256, "slot"),
            (self.recipe_sha256, "recipe"),
            (self.logical_root_sha256, "logical root"),
            (self.physical_root_sha256, "physical root"),
            (self.title_adapter_sha256, "title adapter"),
            (self.runtime_factory_sha256, "runtime factory"),
            (self.runner_sha256, "runner"),
        ):
            _require_sha256(value, subject)
        if self.logical_root_sha256 == self.physical_root_sha256:
            raise ClaimFirstAdmissionError("logical and physical root identities collapse")
        for numeric_value, subject in (
            (self.exact_ci_run, "CI run"),
            (self.exact_ci_attempt, "CI attempt"),
        ):
            if type(numeric_value) is not int or numeric_value <= 0:  # noqa: E721
                raise ClaimFirstAdmissionError(f"claim-first {subject} differs")
        if self.source_published is not True or self.worktree_dirty is not False:
            raise ClaimFirstAdmissionError("claim-first source must be published and clean")

    @property
    def identity_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    @property
    def execution_plan_sha256(self) -> str:
        """Bind the immutable producer plan to this exact current consumer."""

        return canonical_sha256(
            {
                "execution_identity_sha256": self.identity_sha256,
                "producer_plan_sha256": self.producer_plan_sha256,
                "recipe_sha256": self.recipe_sha256,
                "schema": "pokemon.core.claim-first-consumer-plan.v1",
                "slot_sha256": self.slot_sha256,
            }
        )

    def private_dict(self) -> dict[str, object]:
        return {
            "exact_ci_attempt": self.exact_ci_attempt,
            "exact_ci_run": self.exact_ci_run,
            "logical_root_sha256": self.logical_root_sha256,
            "physical_root_sha256": self.physical_root_sha256,
            "producer_execution_identity_sha256": (
                self.producer_execution_identity_sha256
            ),
            "producer_manifest_sha256": self.producer_manifest_sha256,
            "producer_plan_sha256": self.producer_plan_sha256,
            "producer_private_plan_sha256": self.producer_private_plan_sha256,
            "recipe_sha256": self.recipe_sha256,
            "runner_sha256": self.runner_sha256,
            "runtime_factory_sha256": self.runtime_factory_sha256,
            "schema": CLAIM_FIRST_EXECUTION_IDENTITY_SCHEMA,
            "slot_sha256": self.slot_sha256,
            "source_bundle_sha256": self.source_bundle_sha256,
            "source_commit": self.source_commit,
            "source_published": self.source_published,
            "title_adapter_sha256": self.title_adapter_sha256,
            "worktree_dirty": self.worktree_dirty,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            "current_consumer_bound": True,
            "exact_ci_bound": True,
            "immutable_producer_bound": True,
            "logical_and_physical_root_bound": True,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "runtime_factory_bound": True,
            "schema": CLAIM_FIRST_EXECUTION_IDENTITY_SCHEMA,
            "source_published": self.source_published,
            "worktree_dirty": self.worktree_dirty,
        }

    def root_pair(self, *, stage: str) -> ClaimFirstRootPair:
        return ClaimFirstRootPair(
            logical_root_sha256=self.logical_root_sha256,
            physical_root_sha256=self.physical_root_sha256,
            stage=stage,
            execution_identity_sha256=self.identity_sha256,
            plan_sha256=self.execution_plan_sha256,
            slot_sha256=self.slot_sha256,
            runner_sha256=self.runner_sha256,
            source_commit=self.source_commit,
        )


@dataclass(frozen=True, slots=True)
class ClaimFirstRootPair:
    """One atomic logical-plus-physical root consumption record."""

    logical_root_sha256: str
    physical_root_sha256: str
    stage: str
    execution_identity_sha256: str
    plan_sha256: str
    slot_sha256: str
    runner_sha256: str
    source_commit: str

    def __post_init__(self) -> None:
        for value, subject in (
            (self.logical_root_sha256, "logical root"),
            (self.physical_root_sha256, "physical root"),
            (self.execution_identity_sha256, "execution identity"),
            (self.plan_sha256, "plan"),
            (self.slot_sha256, "slot"),
            (self.runner_sha256, "runner"),
        ):
            _require_sha256(value, subject)
        if self.logical_root_sha256 == self.physical_root_sha256:
            raise ClaimFirstAdmissionError("logical and physical root identities collapse")
        if not isinstance(self.stage, str) or _STAGE.fullmatch(self.stage) is None:
            raise ClaimFirstAdmissionError("claim stage differs")
        if not isinstance(self.source_commit, str) or _GIT_COMMIT.fullmatch(
            self.source_commit
        ) is None:
            raise ClaimFirstAdmissionError("claim source commit differs")

    @property
    def claim_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    @property
    def identities(self) -> frozenset[str]:
        return frozenset((self.logical_root_sha256, self.physical_root_sha256))

    def private_dict(self) -> dict[str, object]:
        return {
            "execution_identity_sha256": self.execution_identity_sha256,
            "logical_root_sha256": self.logical_root_sha256,
            "physical_root_sha256": self.physical_root_sha256,
            "plan_sha256": self.plan_sha256,
            "runner_sha256": self.runner_sha256,
            "schema": CLAIM_FIRST_ROOT_PAIR_SCHEMA,
            "slot_sha256": self.slot_sha256,
            "source_commit": self.source_commit,
            "stage": self.stage,
        }


class ClaimFirstPairRegistry:
    """Exclusive transaction boundary for overlap-safe pair claims.

    The object acquires the existing account-wide registry lease itself so the
    check and atomic publication cannot accidentally be used as two unrelated
    operations.  Keep the transaction short: publish the pair claim and the
    private local claim, then release it before constructing a runtime.
    """

    __slots__ = ("_entered", "_lease", "_registry")

    def __init__(self, registry: Path) -> None:
        if not isinstance(registry, Path):
            raise TypeError("claim-first registry needs a Path")
        try:
            self._registry = open_fixed_account_claim_registry(registry)
        except FreshCompositionQualificationError as error:
            raise ClaimFirstAdmissionError(str(error)) from None
        self._lease: FixedAccountClaimRegistryLease | None = None
        self._entered = False

    def __enter__(self) -> Self:
        if self._entered:
            raise ClaimFirstAdmissionError("claim-first transaction is already open")
        lease = fixed_account_claim_registry_lease(self._registry, exclusive=True)
        try:
            lease.__enter__()
        except FreshCompositionQualificationError as error:
            raise ClaimFirstAdmissionError(str(error)) from None
        self._lease = lease
        self._entered = True
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        lease = self._lease
        self._lease = None
        self._entered = False
        if lease is None:
            return False
        return lease.__exit__(exception_type, exception, traceback)

    def available(self, logical_root_sha256: str, physical_root_sha256: str) -> bool:
        self._require_entered()
        return _root_pair_is_available(
            self._registry,
            logical_root_sha256,
            physical_root_sha256,
        )

    def claim(self, claim: ClaimFirstRootPair) -> ClaimFirstRootPair:
        self._require_entered()
        if not isinstance(claim, ClaimFirstRootPair):
            raise TypeError("claim-first transaction needs a root pair")
        claim.__post_init__()
        if not _root_pair_is_available(
            self._registry,
            claim.logical_root_sha256,
            claim.physical_root_sha256,
        ):
            raise ClaimFirstAdmissionError("claim-first root pair is already consumed")
        _publish_pair_claim(self._registry, claim)
        restored = read_root_pair_claim(self._registry, claim.claim_sha256)
        if restored != claim:
            raise ClaimFirstAdmissionError("claim-first root pair did not round-trip")
        return restored

    def _require_entered(self) -> None:
        if not self._entered or self._lease is None:
            raise ClaimFirstAdmissionError("claim-first transaction is not open")


def claim_first_pair_registry(registry: Path) -> ClaimFirstPairRegistry:
    """Return the only supported check-and-claim transaction boundary."""

    return ClaimFirstPairRegistry(registry)


def observe_claim_first_pair_availability(
    registry: Path,
    logical_root_sha256: str,
    physical_root_sha256: str,
) -> bool:
    """Observe one pair under a shared lease without claiming either identity.

    This is a non-authoritative preflight observation: another process may
    claim the pair after the shared lease is released.  The execution path
    must still use :func:`claim_first_pair_registry` for its atomic
    check-and-claim transaction.
    """

    try:
        opened = open_fixed_account_claim_registry(registry)
        with fixed_account_claim_registry_lease(opened, exclusive=False):
            return _root_pair_is_available(
                opened,
                logical_root_sha256,
                physical_root_sha256,
            )
    except FreshCompositionQualificationError as error:
        raise ClaimFirstAdmissionError(str(error)) from None


def read_root_pair_claim(registry: Path, claim_sha256: str) -> ClaimFirstRootPair:
    """Read and strictly authenticate one canonical pair claim."""

    claim_id = _require_sha256(claim_sha256, "pair claim")
    marker = _pair_marker(registry, claim_id)
    payload = _read_bounded_regular_file(marker)
    try:
        document = json.loads(payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ClaimFirstAdmissionError("claim-first pair record cannot be authenticated") from None
    if not isinstance(document, dict) or set(document) != {
        "execution_identity_sha256",
        "logical_root_sha256",
        "physical_root_sha256",
        "plan_sha256",
        "runner_sha256",
        "schema",
        "slot_sha256",
        "source_commit",
        "stage",
    }:
        raise ClaimFirstAdmissionError("claim-first pair record fields differ")
    canonical = _canonical_payload(document)
    if canonical != payload or document.get("schema") != CLAIM_FIRST_ROOT_PAIR_SCHEMA:
        raise ClaimFirstAdmissionError("claim-first pair record is not canonical")
    claim = ClaimFirstRootPair(
        logical_root_sha256=_string(document["logical_root_sha256"], "logical root"),
        physical_root_sha256=_string(document["physical_root_sha256"], "physical root"),
        stage=_string(document["stage"], "stage"),
        execution_identity_sha256=_string(
            document["execution_identity_sha256"],
            "execution identity",
        ),
        plan_sha256=_string(document["plan_sha256"], "plan"),
        slot_sha256=_string(document["slot_sha256"], "slot"),
        runner_sha256=_string(document["runner_sha256"], "runner"),
        source_commit=_string(document["source_commit"], "source commit"),
    )
    if claim.claim_sha256 != claim_id:
        raise ClaimFirstAdmissionError("claim-first pair record identity differs")
    return claim


def root_pair_claims(registry: Path) -> tuple[ClaimFirstRootPair, ...]:
    """Return every authenticated pair claim in stable identity order."""

    try:
        entries = tuple(registry.iterdir())
    except OSError:
        raise ClaimFirstAdmissionError("claim-first registry cannot be inspected") from None
    names = sorted(
        item.name
        for item in entries
        if _PAIR_NAME.fullmatch(item.name) is not None
    )
    if len(names) > _MAXIMUM_PAIR_CLAIMS:
        raise ClaimFirstAdmissionError("claim-first registry exceeds its bounded census")
    return tuple(
        read_root_pair_claim(registry, _pair_id_from_name(name)) for name in names
    )


def root_identity_is_pair_claimed(registry: Path, root_sha256: str) -> bool:
    """Return whether an authenticated pair claim owns one root identity.

    This small compatibility query lets older single-root admission paths
    honor the authoritative pair ledger without creating shadow marker files.
    The caller remains responsible for holding the account registry lease
    across its check-and-claim transaction.
    """

    identity = _require_sha256(root_sha256, "root")
    return any(identity in claim.identities for claim in root_pair_claims(registry))


def _root_pair_is_available(
    registry: Path,
    logical_root_sha256: str,
    physical_root_sha256: str,
) -> bool:
    logical = _require_sha256(logical_root_sha256, "logical root")
    physical = _require_sha256(physical_root_sha256, "physical root")
    if logical == physical:
        raise ClaimFirstAdmissionError("logical and physical root identities collapse")
    # A legacy single-root claim must continue to block the new pair boundary.
    try:
        if not root_claim_is_available(registry, logical) or not root_claim_is_available(
            registry,
            physical,
        ):
            return False
    except FreshCompositionQualificationError as error:
        raise ClaimFirstAdmissionError(str(error)) from None
    requested = frozenset((logical, physical))
    return all(requested.isdisjoint(item.identities) for item in root_pair_claims(registry))


def _publish_pair_claim(registry: Path, claim: ClaimFirstRootPair) -> None:
    payload = _canonical_payload(claim.private_dict())
    marker = _pair_marker(registry, claim.claim_sha256)
    temporary = registry / (
        f".{marker.name}.pending-{os.getpid()}-{os.urandom(8).hex()}"
    )
    descriptor = -1
    directory_descriptor = -1
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(temporary, flags, 0o600)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("pair claim write made no progress")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        atomic_no_replace_rename(temporary, marker)
        directory_descriptor = os.open(
            registry,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        os.fsync(directory_descriptor)
    except (FileExistsError, OSError):
        raise ClaimFirstAdmissionError("claim-first pair could not be retained") from None
    finally:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)
        if directory_descriptor >= 0:
            with suppress(OSError):
                os.close(directory_descriptor)
        with suppress(OSError):
            temporary.unlink()


def _read_bounded_regular_file(path: Path) -> bytes:
    descriptor = -1
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        named = path.lstat()
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        if (
            named.st_dev != metadata.st_dev
            or named.st_ino != metadata.st_ino
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or not 1 <= metadata.st_size <= _MAXIMUM_PAIR_RECORD_BYTES
        ):
            raise OSError("unsafe pair claim")
        payload = os.read(descriptor, metadata.st_size + 1)
        if len(payload) != metadata.st_size:
            raise OSError("pair claim size changed")
        return payload
    except OSError:
        raise ClaimFirstAdmissionError("claim-first pair record cannot be authenticated") from None
    finally:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)


def _canonical_payload(document: dict[str, object]) -> bytes:
    return (
        json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _pair_marker(registry: Path, claim_sha256: str) -> Path:
    return registry / f"{CLAIM_FIRST_ROOT_PAIR_PREFIX}{claim_sha256}.json"


def _pair_id_from_name(name: str) -> str:
    matched = _PAIR_NAME.fullmatch(name)
    if matched is None:
        raise ClaimFirstAdmissionError("claim-first pair marker name differs")
    return matched.group(1)


def _require_sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ClaimFirstAdmissionError(f"claim-first {subject} digest differs")
    return value


def _string(value: object, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise ClaimFirstAdmissionError(f"claim-first {subject} differs")
    return value


__all__ = [
    "CLAIM_FIRST_EXECUTION_IDENTITY_SCHEMA",
    "CLAIM_FIRST_ROOT_PAIR_SCHEMA",
    "ClaimFirstAdmissionError",
    "ClaimFirstExecutionIdentity",
    "ClaimFirstPairRegistry",
    "ClaimFirstRootPair",
    "claim_first_pair_registry",
    "observe_claim_first_pair_availability",
    "read_root_pair_claim",
    "root_identity_is_pair_claimed",
    "root_pair_claims",
]
