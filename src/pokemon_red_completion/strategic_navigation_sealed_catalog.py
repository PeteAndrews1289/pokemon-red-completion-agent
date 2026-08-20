"""Canonical, path-free identity for the twelve private sealed inputs.

The catalog is metadata, not an input opener.  It binds every public plan case
to one authenticated capture digest while deliberately containing no file
path, route cost, teacher label, policy input, prediction, or outcome.  The
cartridge adapter may resolve the deterministic private layout only after the
executor has durably claimed the corresponding case.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping
from dataclasses import InitVar, dataclass, field
from pathlib import Path

from pokemon_red_completion.captured_progress import CapturedProgressEnvelope
from pokemon_red_completion.constants import POKEMON_RED_US_REV_0
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.route import COMPLETION_QUEST
from pokemon_red_completion.strategic_navigation_protocol import (
    STRATEGIC_NAVIGATION_ADAPTER_ID,
    STRATEGIC_NAVIGATION_GAME_ID,
)
from pokemon_red_completion.strategic_navigation_scenarios import (
    StrategicNavigationScenario,
    StrategicNavigationScenarioRegistry,
)
from pokemon_red_completion.strategic_navigation_sealed_evaluation import (
    SEALED_EVALUATION_CASES,
    StrategicSealedEvaluationCase,
    StrategicSealedEvaluationPlan,
)

STRATEGIC_SEALED_CASE_CATALOG_SCHEMA = (
    "pokemon-strategic-navigation-sealed-case-catalog-v1"
)
STRATEGIC_SEALED_CASE_CATALOG_ENTRY_SCHEMA = (
    "pokemon-strategic-navigation-sealed-case-catalog-entry-v1"
)
STRATEGIC_SEALED_EXECUTION_CONFIGURATION_SCHEMA = (
    "pokemon-strategic-navigation-sealed-execution-configuration-v1"
)
STRATEGIC_SEALED_EXECUTION_CONFIGURATION: Mapping[str, object] = {
    "emulator": {
        "human_input": False,
        "save_on_exit": False,
        "speed": 0,
        "watch": False,
    },
    "challenge_relocation": (
        "after_claim_deterministic_route_to_declared_origin_with_zero_objective_delta"
    ),
    "candidate_planning": "after_authenticated_challenge_relocation",
    "execution_mode": "one_choice_then_selected_approach",
    "maximum_flees": 32,
    "maximum_trainer_battles": 8,
    "schema": STRATEGIC_SEALED_EXECUTION_CONFIGURATION_SCHEMA,
    "trajectory_reload_required": True,
}
STRATEGIC_SEALED_EXECUTION_CONFIGURATION_SHA256 = canonical_sha256(
    STRATEGIC_SEALED_EXECUTION_CONFIGURATION
)

_MAX_CATALOG_BYTES = 1024 * 1024
_MAX_CAPTURE_ENVELOPE_BYTES = 64 * 1024
_MAX_CAPTURE_STATE_BYTES = 16 * 1024 * 1024
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_CATALOG_VALIDATION_TOKEN = object()


class StrategicSealedCaseCatalogError(RuntimeError):
    """Raised when catalog metadata is noncanonical, incomplete, or stale."""


@dataclass(frozen=True, slots=True)
class StrategicSealedCaseCatalogEntry:
    """One plan case bound to an exact private capture without naming its path."""

    case_id: str
    case_sha256: str
    ordinal: int
    source_scenario_id: str
    source_scenario_sha256: str
    capture_envelope_sha256: str
    capture_state_sha256: str
    capture_state_bytes: int
    checkpoint_id: str
    _validation_token: InitVar[object]

    def __post_init__(self, _validation_token: object) -> None:
        if _validation_token is not _CATALOG_VALIDATION_TOKEN:
            raise StrategicSealedCaseCatalogError(
                "sealed catalog entries must come from the canonical parser"
            )


@dataclass(frozen=True, slots=True)
class StrategicSealedCaseCatalog:
    """The exact, authorization-bound inventory consumed by the live adapter."""

    catalog_sha256: str
    payload_bytes: int
    evaluation_id: str
    plan_sha256: str
    source_scenario_registry_sha256: str
    teacher_execution_sha256: str
    runtime_sha256: str
    execution_configuration_sha256: str
    rom_title: str
    rom_size_bytes: int
    rom_sha1: str
    rom_sha256: str
    cases: tuple[StrategicSealedCaseCatalogEntry, ...]
    _validation_token: InitVar[object]

    def __post_init__(self, _validation_token: object) -> None:
        if _validation_token is not _CATALOG_VALIDATION_TOKEN:
            raise StrategicSealedCaseCatalogError(
                "sealed case catalogs must come from the canonical parser"
            )

    def case(self, case_id: str) -> StrategicSealedCaseCatalogEntry:
        matches = tuple(case for case in self.cases if case.case_id == case_id)
        if len(matches) != 1:
            raise StrategicSealedCaseCatalogError(
                "sealed catalog case is unavailable"
            )
        return matches[0]


@dataclass(frozen=True, slots=True)
class StrategicSealedCaseInput:
    """One verified in-memory capture, constructible only by the safe opener."""

    entry: StrategicSealedCaseCatalogEntry
    envelope: CapturedProgressEnvelope
    state_bytes: bytes = field(repr=False)
    _validation_token: InitVar[object]

    def __post_init__(self, _validation_token: object) -> None:
        if _validation_token is not _CATALOG_VALIDATION_TOKEN:
            raise StrategicSealedCaseCatalogError(
                "sealed case inputs must come from the verified opener"
            )


def load_strategic_sealed_case_catalog(
    path: str | Path,
    *,
    plan: StrategicSealedEvaluationPlan,
    scenario_registry: StrategicNavigationScenarioRegistry,
) -> StrategicSealedCaseCatalog:
    """Load only the path-free catalog; this never resolves a capture path."""

    try:
        payload = Path(path).read_bytes()
    except OSError:
        raise StrategicSealedCaseCatalogError(
            "sealed case catalog is unavailable"
        ) from None
    return parse_strategic_sealed_case_catalog(
        payload,
        plan=plan,
        scenario_registry=scenario_registry,
    )


def parse_strategic_sealed_case_catalog(
    payload: bytes,
    *,
    plan: StrategicSealedEvaluationPlan,
    scenario_registry: StrategicNavigationScenarioRegistry,
) -> StrategicSealedCaseCatalog:
    """Authenticate the catalog and bind every row to public frozen metadata."""

    if not isinstance(plan, StrategicSealedEvaluationPlan):
        raise TypeError("plan must be a sealed evaluation plan")
    if not isinstance(scenario_registry, StrategicNavigationScenarioRegistry):
        raise TypeError("scenario_registry must be a strategic scenario registry")
    if scenario_registry.registry_sha256 != plan.source_scenario_registry_sha256:
        raise StrategicSealedCaseCatalogError(
            "sealed scenario registry differs from the plan"
        )
    document = _decode_canonical(payload)
    _exact_keys(
        document,
        {
            "adapter_id",
            "cases",
            "evaluation_id",
            "execution_configuration_sha256",
            "game_id",
            "plan_sha256",
            "rom_identity",
            "runtime_sha256",
            "schema",
            "source_scenario_registry_sha256",
            "teacher_execution_sha256",
        },
        subject="sealed case catalog",
    )
    expected_header = {
        "adapter_id": STRATEGIC_NAVIGATION_ADAPTER_ID,
        "evaluation_id": plan.evaluation_id,
        "execution_configuration_sha256": (
            STRATEGIC_SEALED_EXECUTION_CONFIGURATION_SHA256
        ),
        "game_id": STRATEGIC_NAVIGATION_GAME_ID,
        "plan_sha256": plan.plan_sha256,
        "schema": STRATEGIC_SEALED_CASE_CATALOG_SCHEMA,
        "source_scenario_registry_sha256": scenario_registry.registry_sha256,
        "teacher_execution_sha256": plan.teacher_execution_sha256,
    }
    if any(document.get(key) != value for key, value in expected_header.items()):
        raise StrategicSealedCaseCatalogError(
            "sealed case catalog public identity differs"
        )
    runtime_sha256 = _digest(
        document["runtime_sha256"], subject="sealed catalog runtime"
    )
    _validate_rom_identity(document["rom_identity"])
    raw_cases = document["cases"]
    if not isinstance(raw_cases, list) or len(raw_cases) != SEALED_EVALUATION_CASES:
        raise StrategicSealedCaseCatalogError("sealed catalog case count differs")
    entries = tuple(
        _parse_entry(
            value,
            plan_case=plan_case,
            scenario=_scenario_for_plan_case(scenario_registry, plan_case),
        )
        for value, plan_case in zip(raw_cases, plan.cases, strict=True)
    )
    for attribute, subject in (
        ("capture_state_sha256", "state digest"),
        ("capture_envelope_sha256", "envelope digest"),
        ("checkpoint_id", "checkpoint identity"),
    ):
        values = tuple(getattr(entry, attribute) for entry in entries)
        if len(set(values)) != len(values):
            raise StrategicSealedCaseCatalogError(
                f"sealed catalog {subject} is duplicated"
            )
    return StrategicSealedCaseCatalog(
        catalog_sha256=hashlib.sha256(payload).hexdigest(),
        payload_bytes=len(payload),
        evaluation_id=plan.evaluation_id,
        plan_sha256=plan.plan_sha256,
        source_scenario_registry_sha256=scenario_registry.registry_sha256,
        teacher_execution_sha256=plan.teacher_execution_sha256,
        runtime_sha256=runtime_sha256,
        execution_configuration_sha256=(
            STRATEGIC_SEALED_EXECUTION_CONFIGURATION_SHA256
        ),
        rom_title=POKEMON_RED_US_REV_0.title,
        rom_size_bytes=POKEMON_RED_US_REV_0.size_bytes,
        rom_sha1=POKEMON_RED_US_REV_0.sha1,
        rom_sha256=POKEMON_RED_US_REV_0.sha256,
        cases=entries,
        _validation_token=_CATALOG_VALIDATION_TOKEN,
    )


def open_strategic_sealed_case_input(
    capture_root: str | Path,
    *,
    entry: StrategicSealedCaseCatalogEntry,
    scenario: StrategicNavigationScenario,
) -> StrategicSealedCaseInput:
    """Resolve and verify one deterministic case layout after its durable claim.

    The layout is ``<root>/<case-id>/capture.state{,.json}``.  Neither a path
    nor private content is returned in an error, and symlinks are refused at
    every level.  The state is retained as verified bytes so the emulator need
    not reopen a mutable pathname later.
    """

    if not isinstance(entry, StrategicSealedCaseCatalogEntry):
        raise TypeError("entry must be a sealed catalog entry")
    if not isinstance(scenario, StrategicNavigationScenario):
        raise TypeError("scenario must be a strategic navigation scenario")
    if (
        scenario.scenario_id != entry.source_scenario_id
        or scenario.scenario_sha256 != entry.source_scenario_sha256
        or scenario.partition != "test"
    ):
        raise StrategicSealedCaseCatalogError(
            "sealed case scenario differs from its catalog entry"
        )
    if not isinstance(capture_root, (str, Path)):
        raise TypeError("capture_root must be a path")
    root_path = Path(capture_root)
    if not root_path.is_absolute():
        raise StrategicSealedCaseCatalogError(
            "sealed capture root must be absolute"
        )
    root_descriptor: int | None = None
    case_descriptor: int | None = None
    try:
        root_descriptor = _open_directory_path(root_path)
        case_descriptor = _open_directory(
            entry.case_id,
            directory_fd=root_descriptor,
        )
        state_bytes = _read_regular_file(
            "capture.state",
            directory_fd=case_descriptor,
            maximum_bytes=_MAX_CAPTURE_STATE_BYTES,
            expected_bytes=entry.capture_state_bytes,
            subject="sealed capture state",
        )
        envelope_bytes = _read_regular_file(
            "capture.state.json",
            directory_fd=case_descriptor,
            maximum_bytes=_MAX_CAPTURE_ENVELOPE_BYTES,
            expected_bytes=None,
            subject="sealed capture envelope",
        )
    except OSError:
        raise StrategicSealedCaseCatalogError(
            "sealed case input is unavailable"
        ) from None
    finally:
        if case_descriptor is not None:
            os.close(case_descriptor)
        if root_descriptor is not None:
            os.close(root_descriptor)
    state_sha256 = hashlib.sha256(state_bytes).hexdigest()
    if state_sha256 != entry.capture_state_sha256:
        raise StrategicSealedCaseCatalogError(
            "sealed capture state digest differs"
        )
    envelope = _parse_capture_envelope(envelope_bytes)
    if (
        envelope.state_sha256 != entry.capture_state_sha256
        or envelope.checkpoint_id != entry.checkpoint_id
        or canonical_sha256(envelope.to_dict()) != entry.capture_envelope_sha256
        or frozenset(envelope.verified_objective_ids)
        != frozenset(scenario.completed_objective_ids)
    ):
        raise StrategicSealedCaseCatalogError(
            "sealed capture envelope differs from its catalog or scenario"
        )
    return StrategicSealedCaseInput(
        entry=entry,
        envelope=envelope,
        state_bytes=state_bytes,
        _validation_token=_CATALOG_VALIDATION_TOKEN,
    )


def _scenario_for_plan_case(
    registry: StrategicNavigationScenarioRegistry,
    plan_case: StrategicSealedEvaluationCase,
) -> StrategicNavigationScenario:
    matches = tuple(
        scenario
        for scenario in registry.scenarios
        if scenario.scenario_id == plan_case.source_scenario_id
    )
    if len(matches) != 1:
        raise StrategicSealedCaseCatalogError(
            "sealed source scenario is unavailable"
        )
    scenario = matches[0]
    expected_origin = scenario.origin_region
    if plan_case.challenged_non_teacher_objective_id is not None:
        challenged_objective = COMPLETION_QUEST.objective(
            plan_case.challenged_non_teacher_objective_id
        )
        if challenged_objective.target_region is None:
            raise StrategicSealedCaseCatalogError(
                "sealed challenged objective lacks a target region"
            )
        expected_origin = challenged_objective.target_region
    if (
        scenario.partition != "test"
        or scenario.scenario_sha256 != plan_case.source_scenario_sha256
        or expected_origin != plan_case.origin_region
        or len(scenario.candidate_objective_ids) != plan_case.candidate_count
        or (
            plan_case.challenged_non_teacher_objective_id is not None
            and (
                plan_case.challenged_non_teacher_objective_id
                not in scenario.candidate_objective_ids
                or plan_case.challenged_non_teacher_objective_id
                == scenario.teacher_objective_id
            )
        )
        or scenario.teacher_objective_id not in scenario.candidate_objective_ids
    ):
        raise StrategicSealedCaseCatalogError(
            "sealed source scenario differs from the plan"
        )
    return scenario


def _parse_entry(
    value: object,
    *,
    plan_case: StrategicSealedEvaluationCase,
    scenario: StrategicNavigationScenario,
) -> StrategicSealedCaseCatalogEntry:
    row = _mapping(value, subject="sealed catalog case")
    _exact_keys(
        row,
        {
            "capture",
            "case_id",
            "case_sha256",
            "ordinal",
            "schema",
            "source_scenario_id",
            "source_scenario_sha256",
        },
        subject="sealed catalog case",
    )
    if row["schema"] != STRATEGIC_SEALED_CASE_CATALOG_ENTRY_SCHEMA:
        raise StrategicSealedCaseCatalogError("sealed catalog case schema differs")
    public_identity = (
        row["case_id"],
        row["case_sha256"],
        row["ordinal"],
        row["source_scenario_id"],
        row["source_scenario_sha256"],
    )
    if public_identity != (
        plan_case.case_id,
        plan_case.case_sha256,
        plan_case.ordinal,
        plan_case.source_scenario_id,
        plan_case.source_scenario_sha256,
    ) or scenario.scenario_id != plan_case.source_scenario_id:
        raise StrategicSealedCaseCatalogError(
            "sealed catalog case order or identity differs"
        )
    capture = _mapping(row["capture"], subject="sealed catalog capture")
    _exact_keys(
        capture,
        {
            "checkpoint_id",
            "envelope_sha256",
            "state_bytes",
            "state_sha256",
        },
        subject="sealed catalog capture",
    )
    return StrategicSealedCaseCatalogEntry(
        case_id=plan_case.case_id,
        case_sha256=plan_case.case_sha256,
        ordinal=plan_case.ordinal,
        source_scenario_id=plan_case.source_scenario_id,
        source_scenario_sha256=plan_case.source_scenario_sha256,
        capture_envelope_sha256=_digest(
            capture["envelope_sha256"],
            subject="sealed capture envelope",
        ),
        capture_state_sha256=_digest(
            capture["state_sha256"],
            subject="sealed capture state",
        ),
        capture_state_bytes=_integer(
            capture["state_bytes"],
            minimum=1,
            maximum=_MAX_CAPTURE_STATE_BYTES,
            subject="sealed capture state size",
        ),
        checkpoint_id=_safe_id(
            capture["checkpoint_id"],
            subject="sealed capture checkpoint",
        ),
        _validation_token=_CATALOG_VALIDATION_TOKEN,
    )


def _validate_rom_identity(value: object) -> None:
    row = _mapping(value, subject="sealed catalog ROM identity")
    _exact_keys(
        row,
        {"sha1", "sha256", "size_bytes", "title"},
        subject="sealed catalog ROM identity",
    )
    if row != {
        "sha1": POKEMON_RED_US_REV_0.sha1,
        "sha256": POKEMON_RED_US_REV_0.sha256,
        "size_bytes": POKEMON_RED_US_REV_0.size_bytes,
        "title": POKEMON_RED_US_REV_0.title,
    }:
        raise StrategicSealedCaseCatalogError(
            "sealed catalog ROM identity differs"
        )


def _open_directory(
    value: str | Path,
    *,
    directory_fd: int | None,
) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    return os.open(value, flags, dir_fd=directory_fd)


def _open_directory_path(path: Path) -> int:
    """Open every absolute path component without ever following a symlink."""

    if not path.is_absolute():
        raise StrategicSealedCaseCatalogError(
            "sealed capture root must be absolute"
        )
    parts = path.parts[1:]
    descriptor = _open_directory(path.anchor, directory_fd=None)
    try:
        for part in parts:
            if part in {"", ".", ".."}:
                raise StrategicSealedCaseCatalogError(
                    "sealed capture root contains an invalid component"
                )
            child = _open_directory(part, directory_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _read_regular_file(
    name: str,
    *,
    directory_fd: int,
    maximum_bytes: int,
    expected_bytes: int | None,
    subject: str,
) -> bytes:
    descriptor = os.open(
        name,
        os.O_RDONLY | os.O_NOFOLLOW,
        dir_fd=directory_fd,
    )
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise StrategicSealedCaseCatalogError(f"{subject} is not a regular file")
        if (
            metadata.st_size <= 0
            or metadata.st_size > maximum_bytes
            or (expected_bytes is not None and metadata.st_size != expected_bytes)
        ):
            raise StrategicSealedCaseCatalogError(f"{subject} size differs")
        remaining = metadata.st_size
        chunks: list[bytes] = []
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise StrategicSealedCaseCatalogError(
                    f"{subject} ended before its declared size"
                )
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise StrategicSealedCaseCatalogError(
                f"{subject} changed while it was opened"
            )
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _parse_capture_envelope(payload: bytes) -> CapturedProgressEnvelope:
    if not payload or len(payload) > _MAX_CAPTURE_ENVELOPE_BYTES:
        raise StrategicSealedCaseCatalogError(
            "sealed capture envelope size is invalid"
        )
    try:
        value = json.loads(
            payload.decode("ascii"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise StrategicSealedCaseCatalogError(
            "sealed capture envelope is invalid JSON"
        ) from error
    row = _mapping(value, subject="sealed capture envelope")
    _exact_keys(
        row,
        {
            "checkpoint_id",
            "checkpoint_label",
            "checkpoints_completed",
            "checkpoints_total",
            "schema",
            "state_sha256",
            "verified_objective_ids",
        },
        subject="sealed capture envelope",
    )
    objectives = row["verified_objective_ids"]
    if not isinstance(objectives, list) or any(
        not isinstance(item, str) or not item for item in objectives
    ):
        raise StrategicSealedCaseCatalogError(
            "sealed capture objectives are invalid"
        )
    if row["schema"] != "pokemon-private-captured-progress-v1":
        raise StrategicSealedCaseCatalogError(
            "sealed capture envelope schema differs"
        )
    state_sha256 = _digest(
        row["state_sha256"], subject="sealed envelope state"
    )
    checkpoint_id = _safe_id(
        row["checkpoint_id"], subject="sealed envelope checkpoint"
    )
    checkpoint_label = _text(
        row["checkpoint_label"], subject="sealed envelope checkpoint label"
    )
    checkpoints_completed = _integer(
        row["checkpoints_completed"],
        minimum=0,
        maximum=100_000,
        subject="sealed envelope completed checkpoints",
    )
    checkpoints_total = _integer(
        row["checkpoints_total"],
        minimum=0,
        maximum=100_000,
        subject="sealed envelope total checkpoints",
    )
    try:
        return CapturedProgressEnvelope(
            state_sha256=state_sha256,
            checkpoint_id=checkpoint_id,
            checkpoint_label=checkpoint_label,
            checkpoints_completed=checkpoints_completed,
            checkpoints_total=checkpoints_total,
            verified_objective_ids=tuple(objectives),
        )
    except (TypeError, ValueError) as error:
        raise StrategicSealedCaseCatalogError(
            "sealed capture envelope values are invalid"
        ) from error


def _decode_canonical(payload: bytes) -> dict[str, object]:
    if (
        not isinstance(payload, bytes)
        or not payload
        or len(payload) > _MAX_CATALOG_BYTES
    ):
        raise StrategicSealedCaseCatalogError("sealed case catalog size is invalid")
    try:
        value = json.loads(
            payload.decode("ascii"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise StrategicSealedCaseCatalogError(
            "sealed case catalog is invalid JSON"
        ) from error
    if not isinstance(value, dict) or _canonical_line(value) != payload:
        raise StrategicSealedCaseCatalogError(
            "sealed case catalog is not canonical JSON"
        )
    return value


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
            raise StrategicSealedCaseCatalogError(
                "sealed case catalog JSON key is duplicated"
            )
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise StrategicSealedCaseCatalogError(
        f"sealed case catalog constant {value!r} is invalid"
    )


def _mapping(value: object, *, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise StrategicSealedCaseCatalogError(f"{subject} must be an object")
    return value


def _exact_keys(
    value: Mapping[str, object],
    expected: set[str],
    *,
    subject: str,
) -> None:
    if set(value) != expected:
        raise StrategicSealedCaseCatalogError(f"{subject} fields differ")


def _text(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise StrategicSealedCaseCatalogError(f"{subject} must be non-empty text")
    return value


def _digest(value: object, *, subject: str) -> str:
    result = _text(value, subject=subject)
    if _SHA256.fullmatch(result) is None:
        raise StrategicSealedCaseCatalogError(f"{subject} is invalid")
    return result


def _safe_id(value: object, *, subject: str) -> str:
    result = _text(value, subject=subject)
    if _SAFE_ID.fullmatch(result) is None:
        raise StrategicSealedCaseCatalogError(f"{subject} is invalid")
    return result


def _integer(
    value: object,
    *,
    minimum: int,
    maximum: int,
    subject: str,
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:  # noqa: E721
        raise StrategicSealedCaseCatalogError(f"{subject} is invalid")
    return value
