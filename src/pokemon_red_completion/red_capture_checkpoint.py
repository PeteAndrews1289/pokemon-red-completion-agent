"""Write-once capture receipts binding allocations and counters to exact states.

This is development continuation support, not permission to reset an encounter.
The caller keeps the expected receipt and allocation digests outside the packet.
An interrupted throw intent is deliberately not resumable: ball settlement must
be reconciled before a new authenticated paused receipt can be accepted.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .observation import ItemId
from .red_one_off_capture import OneOffCaptureBudget, OneOffCaptureRequest
from .red_static_capture import RedStaticCaptureTarget

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_SCHEMA = "pokemon.red.capture-checkpoint.v1"


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _encode(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _hash(value: str) -> None:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise ValueError("capture receipt requires a SHA256 digest")


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def create_capture_journal(directory: Path) -> None:
    """Create the caller's write-once journal and persist its directory entry."""
    directory.mkdir(mode=0o700, parents=False, exist_ok=False)
    _sync_directory(directory.parent)


def capture_allocation_sha256(
    origin_state_sha256: str,
    target: RedStaticCaptureTarget,
    budget: OneOffCaptureBudget,
    *,
    maximum_status_attempts: int,
    preserve_viable_active: bool,
    minimum_prepared_helper_level: int | None = None,
) -> str:
    _hash(origin_state_sha256)
    budget.validate()
    if (budget.request.internal_species, budget.request.level) != (
        target.internal_species,
        target.level,
    ):
        raise ValueError("capture allocation target differs")
    if (
        type(maximum_status_attempts) is not int
        or not 1 <= maximum_status_attempts <= 10
        or type(preserve_viable_active) is not bool
    ):
        raise ValueError("capture allocation status policy differs")
    if minimum_prepared_helper_level is not None and (
        type(minimum_prepared_helper_level) is not int
        or not 1 <= minimum_prepared_helper_level <= 100 or not preserve_viable_active
    ):
        raise ValueError("capture allocation prepared helper level differs")
    return _digest(
        _encode(
            dict(
                origin=origin_state_sha256,
                target=asdict(target),
                request=asdict(budget.request),
                max_throws=budget.max_throws,
                initial_ball_count=budget.initial_ball_count,
                maximum_status_attempts=maximum_status_attempts,
                preserve_viable_active=preserve_viable_active,
                **({"minimum_prepared_helper_level": minimum_prepared_helper_level}
                   if minimum_prepared_helper_level is not None else {}),
            )
        )
    )


@dataclass(frozen=True, slots=True)
class RestoredCaptureCheckpoint:
    state: bytes
    receipt_sha256: str
    allocation_sha256: str
    budget: OneOffCaptureBudget
    status_attempts: int
    maximum_status_attempts: int
    preserve_viable_active: bool
    phase: str
    minimum_prepared_helper_level: int | None = None

    def require_live_resume(self, reader, target: RedStaticCaptureTarget, *, emulator) -> None:
        if self.phase != "paused":
            raise ValueError("only a settled paused capture receipt can resume")
        if emulator.save_state_bytes() != self.state:
            raise ValueError("capture continuation emulator differs from authenticated state")
        raw = reader.read()
        identity = reader.read_wild_capture_identity()
        if (
            raw.battle_state != 1
            or raw.map_id != target.map_id
            or identity is None
            or identity.original_species_id != self.budget.request.internal_species
            or raw.enemy_level != self.budget.request.level
            or dict(raw.bag_items or ()).get(int(self.budget.request.ball), 0)
            != self.budget.initial_ball_count - self.budget.throws_committed
        ):
            raise ValueError("capture continuation live state/allocation differs")

    def status_preparer(self, emulator, actions, reader):
        from .red_capture_status_runtime import RedCaptureStatusPreparer

        if self.phase != "paused":
            raise ValueError("unsettled capture receipt cannot restore preparation")
        if emulator.save_state_bytes() != self.state:
            raise ValueError("capture preparation emulator differs from authenticated state")
        result = RedCaptureStatusPreparer(
            emulator,
            actions,
            reader,
            maximum_attempts=self.maximum_status_attempts,
            expected_original_species_id=self.budget.request.internal_species,
            preserve_viable_active=self.preserve_viable_active,
            minimum_prepared_helper_level=self.minimum_prepared_helper_level,
        )
        result.attempts = self.status_attempts
        result.latched_original_species_id = self.budget.request.internal_species
        return result


def write_capture_checkpoint(
    directory: Path,
    *,
    state: bytes,
    origin_state_sha256: str,
    target: RedStaticCaptureTarget,
    budget: OneOffCaptureBudget,
    status_attempts: int,
    maximum_status_attempts: int = 3,
    preserve_viable_active: bool = False,
    phase: str = "paused",
    parent_receipt_sha256: str | None = None,
    minimum_prepared_helper_level: int | None = None,
) -> str:
    """Persist without overwriting; return the external receipt reference.

    A partial directory on IO failure is retained, never silently reused.
    """
    if not isinstance(state, bytes) or not state:
        raise ValueError("capture checkpoint requires retained state bytes")
    if phase not in {"admitted", "throw_intent", "paused", "settled"}:
        raise ValueError("invalid capture checkpoint phase")
    if type(status_attempts) is not int or not 0 <= status_attempts <= maximum_status_attempts:
        raise ValueError("capture status attempts exceed original allocation")
    if parent_receipt_sha256 is not None:
        _hash(parent_receipt_sha256)
    allocation = capture_allocation_sha256(
        origin_state_sha256,
        target,
        budget,
        maximum_status_attempts=maximum_status_attempts,
        preserve_viable_active=preserve_viable_active,
        minimum_prepared_helper_level=minimum_prepared_helper_level,
    )
    payload = dict(
        schema=_SCHEMA,
        state_sha256=_digest(state),
        origin_state_sha256=origin_state_sha256,
        target=asdict(target),
        budget=asdict(budget),
        status_attempts=status_attempts,
        maximum_status_attempts=maximum_status_attempts,
        preserve_viable_active=preserve_viable_active,
        **({"minimum_prepared_helper_level": minimum_prepared_helper_level}
           if minimum_prepared_helper_level is not None else {}),
        phase=phase,
        parent_receipt_sha256=parent_receipt_sha256,
        allocation_sha256=allocation,
    )
    receipt = _encode(payload)
    directory.mkdir(mode=0o700, parents=False, exist_ok=False)
    for name, contents in (("state.bin", state), ("receipt.json", receipt)):
        with (directory / name).open("xb") as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
    # File contents alone do not persist their directory entries. Propagate
    # sync failure before the write-ahead callback can authorize a ball input.
    _sync_directory(directory)
    _sync_directory(directory.parent)
    return _digest(receipt)


def load_capture_checkpoint(
    directory: Path,
    *,
    expected_receipt_sha256: str,
    expected_origin_sha256: str,
    expected_target: RedStaticCaptureTarget,
    expected_allocation_sha256: str,
) -> RestoredCaptureCheckpoint:
    for value in (expected_receipt_sha256, expected_origin_sha256, expected_allocation_sha256):
        _hash(value)
    receipt = (directory / "receipt.json").read_bytes()
    if _digest(receipt) != expected_receipt_sha256:
        raise ValueError("capture receipt digest differs")
    data = json.loads(receipt)
    if (
        data["schema"] != _SCHEMA
        or data["origin_state_sha256"] != expected_origin_sha256
        or data["target"] != json.loads(_encode(asdict(expected_target)))
    ):
        raise ValueError("capture source or target receipt differs")
    b = data["budget"]
    q = b["request"]
    budget = OneOffCaptureBudget(
        OneOffCaptureRequest(q["internal_species"], q["level"], ItemId(q["ball"])),
        b["max_throws"],
        b["initial_ball_count"],
        b["throws_committed"],
    )
    allocation = capture_allocation_sha256(
        expected_origin_sha256,
        expected_target,
        budget,
        maximum_status_attempts=data["maximum_status_attempts"],
        preserve_viable_active=data["preserve_viable_active"],
        minimum_prepared_helper_level=data.get("minimum_prepared_helper_level"),
    )
    if allocation != expected_allocation_sha256 or allocation != data["allocation_sha256"]:
        raise ValueError("capture original allocation differs")
    attempts = data["status_attempts"]
    if type(attempts) is not int or not 0 <= attempts <= data["maximum_status_attempts"]:
        raise ValueError("capture status counter differs")
    if data["phase"] not in {"admitted", "throw_intent", "paused", "settled"}:
        raise ValueError("capture receipt phase differs")
    if data["parent_receipt_sha256"] is not None:
        _hash(data["parent_receipt_sha256"])
    state = (directory / "state.bin").read_bytes()
    if not state or _digest(state) != data["state_sha256"]:
        raise ValueError("capture state digest differs")
    return RestoredCaptureCheckpoint(
        state,
        expected_receipt_sha256,
        allocation,
        budget,
        attempts,
        data["maximum_status_attempts"],
        data["preserve_viable_active"],
        data["phase"],
        data.get("minimum_prepared_helper_level"),
    )
