"""Path-free authentication for private battle-scenario save states."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import InitVar, dataclass, field
from pathlib import Path

from pokemon_red_completion.scenario_lab import ScenarioPartition

BATTLE_SCENARIO_CAPTURE_SCHEMA = "pokemon-private-battle-scenario-capture-v1"
BATTLE_SCENARIO_CAPTURE_SCHEMA_V2 = "pokemon-private-battle-scenario-capture-v2"
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_MAX_MANIFEST_BYTES = 64 * 1024
_MAX_STATE_BYTES = 16 * 1024 * 1024
_CAPTURE_VALIDATION_TOKEN = object()


class BattleScenarioCaptureError(ValueError):
    """Raised when a private state or its path-free binding is invalid."""


@dataclass(frozen=True, slots=True)
class BattleScenarioCaptureManifest:
    capture_id: str
    root_lineage_id: str
    partition: ScenarioPartition
    state_sha256: str
    initial_observation_sha256: str
    source_commit: str
    expected_map: int
    expected_battle_state: int
    source_state_sha256: str | None = None

    def __post_init__(self) -> None:
        for name in ("capture_id", "root_lineage_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
                raise BattleScenarioCaptureError(f"{name} is invalid")
        if not isinstance(self.partition, ScenarioPartition):
            raise BattleScenarioCaptureError("partition is invalid")
        for name in ("state_sha256", "initial_observation_sha256"):
            value = getattr(self, name)
            if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                raise BattleScenarioCaptureError(f"{name} is invalid")
        if self.source_state_sha256 is not None and (
            not isinstance(self.source_state_sha256, str)
            or _SHA256.fullmatch(self.source_state_sha256) is None
        ):
            raise BattleScenarioCaptureError("source_state_sha256 is invalid")
        if not isinstance(self.source_commit, str) or _GIT_COMMIT.fullmatch(
            self.source_commit
        ) is None:
            raise BattleScenarioCaptureError("source_commit is invalid")
        if type(self.expected_map) is not int or not 0 <= self.expected_map <= 0xFF:  # noqa: E721
            raise BattleScenarioCaptureError("expected_map is invalid")
        if self.expected_battle_state not in {1, 2}:
            raise BattleScenarioCaptureError("expected_battle_state is invalid")
        if self.partition is ScenarioPartition.TEST:
            raise BattleScenarioCaptureError(
                "sealed test captures cannot enter the development opener"
            )

    def public_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "schema": (
                BATTLE_SCENARIO_CAPTURE_SCHEMA
                if self.source_state_sha256 is None
                else BATTLE_SCENARIO_CAPTURE_SCHEMA_V2
            ),
            "capture_id": self.capture_id,
            "root_lineage_id": self.root_lineage_id,
            "partition": self.partition.value,
            "state_sha256": self.state_sha256,
            "initial_observation_sha256": self.initial_observation_sha256,
            "source_commit": self.source_commit,
            "expected_map": self.expected_map,
            "expected_battle_state": self.expected_battle_state,
        }
        if self.source_state_sha256 is not None:
            result["source_state_sha256"] = self.source_state_sha256
        return result


@dataclass(frozen=True, slots=True)
class BattleScenarioCapture:
    """Authenticated state bytes with no retained filesystem identity."""

    manifest: BattleScenarioCaptureManifest
    manifest_sha256: str
    state_bytes: bytes = field(repr=False)
    _validation_token: InitVar[object]

    def __post_init__(self, _validation_token: object) -> None:
        if _validation_token is not _CAPTURE_VALIDATION_TOKEN:
            raise BattleScenarioCaptureError(
                "battle scenario captures must come from the verified opener"
            )
        if not isinstance(self.manifest, BattleScenarioCaptureManifest):
            raise BattleScenarioCaptureError("capture manifest is invalid")
        if _SHA256.fullmatch(self.manifest_sha256) is None:
            raise BattleScenarioCaptureError("manifest digest is invalid")
        if not isinstance(self.state_bytes, bytes) or not self.state_bytes:
            raise BattleScenarioCaptureError("state bytes are unavailable")


def build_battle_scenario_capture_payload(
    *,
    capture_id: str,
    root_lineage_id: str,
    partition: ScenarioPartition,
    state_bytes: bytes,
    initial_observation_sha256: str,
    source_commit: str,
    expected_map: int,
    expected_battle_state: int,
    source_state_sha256: str | None = None,
) -> bytes:
    """Build the exact canonical sidecar for private state bytes."""

    if not isinstance(state_bytes, bytes) or not state_bytes:
        raise BattleScenarioCaptureError("state bytes are unavailable")
    manifest = BattleScenarioCaptureManifest(
        capture_id=capture_id,
        root_lineage_id=root_lineage_id,
        partition=partition,
        state_sha256=hashlib.sha256(state_bytes).hexdigest(),
        initial_observation_sha256=initial_observation_sha256,
        source_commit=source_commit,
        expected_map=expected_map,
        expected_battle_state=expected_battle_state,
        source_state_sha256=source_state_sha256,
    )
    return _canonical_payload(manifest.public_dict())


def open_battle_scenario_capture(
    state_path: str | Path,
    manifest_path: str | Path,
) -> BattleScenarioCapture:
    """Read both private files once, authenticate them, and forget their paths."""

    state = Path(state_path)
    manifest = Path(manifest_path)
    try:
        state_bytes = _read_owned_regular_file(
            state,
            maximum_bytes=_MAX_STATE_BYTES,
        )
        manifest_bytes = _read_owned_regular_file(
            manifest,
            maximum_bytes=_MAX_MANIFEST_BYTES,
        )
    except OSError:
        raise BattleScenarioCaptureError("battle scenario capture is unavailable") from None
    parsed = _parse_manifest(manifest_bytes)
    if hashlib.sha256(state_bytes).hexdigest() != parsed.state_sha256:
        raise BattleScenarioCaptureError("state bytes differ from the capture manifest")
    return BattleScenarioCapture(
        manifest=parsed,
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        state_bytes=state_bytes,
        _validation_token=_CAPTURE_VALIDATION_TOKEN,
    )


def parse_battle_scenario_capture_manifest(
    payload: bytes,
) -> BattleScenarioCaptureManifest:
    """Strictly parse one canonical manifest without opening its state payload."""

    if not isinstance(payload, bytes):
        raise TypeError("battle scenario capture manifest must be bytes")
    if not payload or len(payload) > _MAX_MANIFEST_BYTES:
        raise BattleScenarioCaptureError("capture manifest size is invalid")
    return _parse_manifest(payload)


def _read_owned_regular_file(path: Path, *, maximum_bytes: int) -> bytes:
    descriptor = -1
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        named = path.lstat()
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if (
            named.st_dev != opened.st_dev
            or named.st_ino != opened.st_ino
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_uid != os.getuid()
            or stat.S_IMODE(opened.st_mode) & 0o022
            or not 1 <= opened.st_size <= maximum_bytes
        ):
            raise OSError("unsafe battle capture file")
        payload = os.read(descriptor, opened.st_size + 1)
        if len(payload) != opened.st_size:
            raise OSError("battle capture file changed while opening")
        return payload
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _parse_manifest(payload: bytes) -> BattleScenarioCaptureManifest:
    try:
        value = json.loads(payload.decode("ascii"))
        base_fields = {
            "schema",
            "capture_id",
            "root_lineage_id",
            "partition",
            "state_sha256",
            "initial_observation_sha256",
            "source_commit",
            "expected_map",
            "expected_battle_state",
        }
        if not isinstance(value, dict):
            raise BattleScenarioCaptureError("capture manifest fields are invalid")
        schema = value.get("schema")
        expected_fields = (
            base_fields
            if schema == BATTLE_SCENARIO_CAPTURE_SCHEMA
            else base_fields | {"source_state_sha256"}
            if schema == BATTLE_SCENARIO_CAPTURE_SCHEMA_V2
            else set()
        )
        if set(value) != expected_fields:
            raise BattleScenarioCaptureError("capture manifest fields are invalid")
        if not expected_fields:
            raise BattleScenarioCaptureError("capture manifest schema is invalid")
        manifest = BattleScenarioCaptureManifest(
            capture_id=value["capture_id"],
            root_lineage_id=value["root_lineage_id"],
            partition=ScenarioPartition(value["partition"]),
            state_sha256=value["state_sha256"],
            initial_observation_sha256=value["initial_observation_sha256"],
            source_commit=value["source_commit"],
            expected_map=value["expected_map"],
            expected_battle_state=value["expected_battle_state"],
            source_state_sha256=value.get("source_state_sha256"),
        )
    except (
        BattleScenarioCaptureError,
        UnicodeDecodeError,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        if isinstance(error, BattleScenarioCaptureError):
            raise
        raise BattleScenarioCaptureError("capture manifest is invalid") from error
    if payload != _canonical_payload(manifest.public_dict()):
        raise BattleScenarioCaptureError("capture manifest is not canonical")
    return manifest


def _canonical_payload(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("ascii")
