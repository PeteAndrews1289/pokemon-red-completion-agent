"""Authenticated semantic progress bound to a private emulator capture."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class CapturedProgressError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CapturedProgressEnvelope:
    state_sha256: str
    checkpoint_id: str
    checkpoint_label: str
    checkpoints_completed: int
    checkpoints_total: int
    verified_objective_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if _SHA256.fullmatch(self.state_sha256) is None:
            raise CapturedProgressError("capture state digest is invalid")
        if not self.checkpoint_id or not self.checkpoint_label:
            raise CapturedProgressError("capture checkpoint identity is absent")
        if not 0 <= self.checkpoints_completed <= self.checkpoints_total:
            raise CapturedProgressError("capture checkpoint counts are invalid")
        if len(set(self.verified_objective_ids)) != len(self.verified_objective_ids):
            raise CapturedProgressError("capture objective identities are duplicated")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon-private-captured-progress-v1",
            "state_sha256": self.state_sha256,
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_label": self.checkpoint_label,
            "checkpoints_completed": self.checkpoints_completed,
            "checkpoints_total": self.checkpoints_total,
            "verified_objective_ids": list(self.verified_objective_ids),
        }


def write_captured_progress(
    destination: Path,
    *,
    state_path: Path,
    checkpoint_id: str,
    checkpoint_label: str,
    checkpoints_completed: int,
    checkpoints_total: int,
    verified_objective_ids: tuple[str, ...],
) -> CapturedProgressEnvelope:
    envelope = CapturedProgressEnvelope(
        state_sha256=hashlib.sha256(state_path.read_bytes()).hexdigest(),
        checkpoint_id=checkpoint_id,
        checkpoint_label=checkpoint_label,
        checkpoints_completed=checkpoints_completed,
        checkpoints_total=checkpoints_total,
        verified_objective_ids=verified_objective_ids,
    )
    destination.write_text(
        json.dumps(envelope.to_dict(), ensure_ascii=True, sort_keys=True) + "\n",
        encoding="ascii",
    )
    return envelope


def load_captured_progress(path: Path, *, state_path: Path) -> CapturedProgressEnvelope:
    try:
        value = json.loads(path.read_text(encoding="ascii"))
        envelope = CapturedProgressEnvelope(
            state_sha256=value["state_sha256"],
            checkpoint_id=value["checkpoint_id"],
            checkpoint_label=value["checkpoint_label"],
            checkpoints_completed=value["checkpoints_completed"],
            checkpoints_total=value["checkpoints_total"],
            verified_objective_ids=tuple(value["verified_objective_ids"]),
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise CapturedProgressError("capture progress envelope is invalid") from error
    if hashlib.sha256(state_path.read_bytes()).hexdigest() != envelope.state_sha256:
        raise CapturedProgressError("capture state does not match its progress envelope")
    return envelope
