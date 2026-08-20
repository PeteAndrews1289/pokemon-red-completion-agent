#!/usr/bin/env python3
"""Freeze the exact Red 8+6 feature menus after both PP preparations pass."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.blaine import (  # noqa: E402
    DIGLETTS_CAVE_TRAINING_VENUE,
    ROUTE_11_TRAINING_VENUE,
)
from pokemon_red_completion.captured_progress import load_captured_progress  # noqa: E402
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    working_source_bundle_sha256,
)
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.gen1_cartridge import evolution_graph  # noqa: E402
from pokemon_red_completion.goal_manager_context_catalog import (  # noqa: E402
    open_goal_manager_context_capture,
    parse_goal_manager_context_catalog,
)
from pokemon_red_completion.goal_manager_protocol import (  # noqa: E402
    load_committed_goal_manager_registry_at_revision,
)
from pokemon_red_completion.observation import PokemonRedStateReader  # noqa: E402
from pokemon_red_completion.party import PartyMemberObservation  # noqa: E402
from pokemon_red_completion.party_development_adapter import (  # noqa: E402
    BoundPartyDevelopmentMenu,
)
from pokemon_red_completion.party_development_frozen_catalog import (  # noqa: E402
    PartyDevelopmentFrozenCatalog,
    PartyDevelopmentFrozenQuestion,
)
from pokemon_red_completion.party_development_inventory import (  # noqa: E402
    PartyDevelopmentCheckpointInventory,
    PartyDevelopmentInventoryEntry,
)
from pokemon_red_completion.party_development_question_reservations import (  # noqa: E402
    PartyDevelopmentContextPreparation,
    PartyDevelopmentQuestionReservation,
    PartyDevelopmentQuestionReservationPlan,
)
from pokemon_red_completion.party_development_venue_priors import (  # noqa: E402
    PartyDevelopmentVenuePriorRegistry,
)
from pokemon_red_completion.private_artifacts import (  # noqa: E402
    PRIVATE_ARTIFACT_SCHEMA_VERSION,
    PRIVATE_JSON_ARTIFACT_FORMAT,
    open_private_root,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_goal_context import (  # noqa: E402
    build_red_goal_context_runtime,
)
from pokemon_red_completion.red_goal_context_profile import (  # noqa: E402
    load_red_goal_context_profile,
)
from pokemon_red_completion.red_party_development_adapter import (  # noqa: E402
    RED_PARTY_DEVELOPMENT_CURRICULUM_POLICY,
    RedPartyDevelopmentQuestionPreflight,
    build_red_party_development_snapshot,
)
from pokemon_red_completion.red_party_development_pp_materialization import (  # noqa: E402
    RedPartyDevelopmentPpMaterializationPlan,
    RedPpMaterializationSource,
)
from pokemon_red_completion.rom import resolve_rom_path, verify_rom  # noqa: E402
from pokemon_red_completion.route_evidence import rom_adjacent_artifacts  # noqa: E402
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402
from pokemon_red_completion.team_training import GrindingArea  # noqa: E402
from pokemon_red_completion.training_candidate_rank import (  # noqa: E402
    TrainingChoiceKind,
)

_MAX_JSON_BYTES = 8 * 1024 * 1024
_MAX_ARTIFACT_STREAM_BYTES = 1024 * 1024
_OUTPUT_CLAIM_SHA256 = hashlib.sha256(
    b"pokemon-red-party-pp-materialization-attempt-claim-v1\n"
).hexdigest()
_ARTIFACT_KIND = "party_development_pp_materialization"
_ARTIFACT_STREAMS = {
    "output_claim.jsonl": 1,
    "plan.jsonl": 1,
    "progress.jsonl": None,
    "terminal.jsonl": 1,
}
_PLAN_RECORD_KEYS = {
    "candidate_menus_constructed",
    "exact_ci_head_sha",
    "exact_ci_run",
    "exact_ci_run_attempt",
    "exact_ci_workflow",
    "learner_outcomes_opened",
    "model_predictions",
    "output_capture_id",
    "partition",
    "private_plan_file_sha256",
    "private_plan_sha256",
    "record_type",
    "retry_after_controller_input",
    "scenario_id",
    "schema_version",
    "source_bundle_sha256",
    "source_checkpoint_id",
    "source_commit",
    "source_root_lineage_id",
    "source_state_sha256",
    "teacher_queries",
}
_OUTPUT_CLAIM_KEYS = {
    "claim_sha256",
    "controller_actions",
    "output_capture_id",
    "partition",
    "private_path_fields",
    "record_type",
    "retry_after_controller_input",
    "schema_version",
}
_PROGRESS_KEYS = {
    "battles_completed",
    "candidate_menus_constructed",
    "controller_actions",
    "current_total_pp",
    "encounter_steps",
    "frames_executed",
    "learner_outcomes_opened",
    "maximum_total_pp",
    "model_predictions",
    "record_type",
    "schema_version",
    "teacher_queries",
}
_TERMINAL_KEYS = {
    "battles_completed",
    "candidate_menus_constructed",
    "captures",
    "controller_actions",
    "encounter_steps",
    "faints",
    "final_pp_bin",
    "final_total_pp",
    "frames_executed",
    "heals",
    "initial_total_pp",
    "learner_outcomes_opened",
    "maximum_total_pp",
    "model_predictions",
    "model_updates",
    "new_persistent_statuses",
    "output_capture_id",
    "output_envelope_sha256",
    "output_reload_authenticated",
    "output_state_sha256",
    "partition",
    "party_switches",
    "pp_consumed",
    "record_type",
    "schema_version",
    "storage_accesses",
    "teacher_queries",
}


class RedPartyDevelopmentCatalogFreezeRunError(RuntimeError):
    """Raised before an incomplete or ambiguous catalog can be retained."""


@dataclass(frozen=True, slots=True)
class _CompletedMaterialization:
    entry: RedPpMaterializationSource
    artifact_id: str
    manifest_sha256: str
    output_state_sha256: str
    output_envelope_sha256: str


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reservation-plan", type=Path, required=True)
    parser.add_argument("--reservation-plan-file-sha256", required=True)
    parser.add_argument("--previous-inventory", type=Path, required=True)
    parser.add_argument("--previous-inventory-file-sha256", required=True)
    parser.add_argument("--current-inventory", type=Path, required=True)
    parser.add_argument("--current-inventory-file-sha256", required=True)
    parser.add_argument("--pp-plan", type=Path, required=True)
    parser.add_argument("--pp-plan-file-sha256", required=True)
    parser.add_argument("--venue-prior-registry", type=Path, required=True)
    parser.add_argument("--venue-prior-registry-file-sha256", required=True)
    parser.add_argument("--catalog-root", type=Path, required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--context-catalog-file-sha256", required=True)
    parser.add_argument("--private-artifact-root", type=Path, required=True)
    parser.add_argument("--train-artifact-manifest-sha256", required=True)
    parser.add_argument("--development-artifact-manifest-sha256", required=True)
    parser.add_argument("--exact-ci-run", type=int, required=True)
    parser.add_argument("--exact-ci-attempt", type=int, required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--out-catalog", type=Path, required=True)
    parser.add_argument("--out-summary", type=Path, required=True)
    return parser


def _require_external(path: Path, *, subject: str) -> Path:
    resolved = path.resolve()
    if resolved.is_relative_to(PROJECT_ROOT.resolve()):
        raise RedPartyDevelopmentCatalogFreezeRunError(
            f"private {subject} must remain outside the repository"
        )
    return resolved


def _load_json(
    path: Path,
    *,
    expected_sha256: str,
    subject: str,
) -> Mapping[str, object]:
    payload = path.read_bytes()
    if (
        not payload
        or len(payload) > _MAX_JSON_BYTES
        or hashlib.sha256(payload).hexdigest() != expected_sha256
    ):
        raise RedPartyDevelopmentCatalogFreezeRunError(
            f"{subject} file digest or size differs"
        )
    try:
        value = json.loads(payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RedPartyDevelopmentCatalogFreezeRunError(
            f"{subject} is not valid ASCII JSON"
        ) from error
    if not isinstance(value, Mapping):
        raise RedPartyDevelopmentCatalogFreezeRunError(
            f"{subject} document is invalid"
        )
    return value


def _canonical_payload(document: Mapping[str, object]) -> bytes:
    return (
        json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        + "\n"
    ).encode("ascii")


def _write_exclusive(path: Path, payload: bytes) -> str:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return hashlib.sha256(payload).hexdigest()


def _canonical_jsonl_records(
    payload: bytes,
    *,
    expected_records: int,
    subject: str,
) -> tuple[dict[str, object], ...]:
    if (
        not payload
        or len(payload) > _MAX_ARTIFACT_STREAM_BYTES
        or not payload.endswith(b"\n")
    ):
        raise RedPartyDevelopmentCatalogFreezeRunError(
            f"{subject} stream shape is invalid"
        )
    rows = []
    for line in payload.splitlines(keepends=True):
        try:
            value = json.loads(line.decode("ascii"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RedPartyDevelopmentCatalogFreezeRunError(
                f"{subject} stream record is invalid"
            ) from error
        if not isinstance(value, dict) or _canonical_payload(value) != line:
            raise RedPartyDevelopmentCatalogFreezeRunError(
                f"{subject} stream is not canonical"
            )
        rows.append(value)
    if len(rows) != expected_records:
        raise RedPartyDevelopmentCatalogFreezeRunError(
            f"{subject} stream record count differs"
        )
    return tuple(rows)


def _artifact_streams(
    directory: Path,
    *,
    artifact_id: str,
    expected_manifest_sha256: str,
) -> tuple[dict[str, object], dict[str, tuple[dict[str, object], ...]]]:
    metadata = directory.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise RedPartyDevelopmentCatalogFreezeRunError(
            "PP materialization artifact directory is invalid"
        )
    if {path.name for path in directory.iterdir()} != {
        "manifest.json",
        *_ARTIFACT_STREAMS,
    }:
        raise RedPartyDevelopmentCatalogFreezeRunError(
            "PP materialization artifact contents differ"
        )
    manifest_payload = (directory / "manifest.json").read_bytes()
    if hashlib.sha256(manifest_payload).hexdigest() != expected_manifest_sha256:
        raise RedPartyDevelopmentCatalogFreezeRunError(
            "PP materialization manifest digest differs"
        )
    manifest_rows = _canonical_jsonl_records(
        manifest_payload,
        expected_records=1,
        subject="PP materialization manifest",
    )
    manifest = manifest_rows[0]
    if (
        set(manifest)
        != {
            "artifact_id",
            "files",
            "format",
            "kind",
            "schema_version",
            "status",
            "totals",
        }
        or manifest["artifact_id"] != artifact_id
        or manifest["format"] != PRIVATE_JSON_ARTIFACT_FORMAT
        or manifest["kind"] != _ARTIFACT_KIND
        or manifest["schema_version"] != PRIVATE_ARTIFACT_SCHEMA_VERSION
        or manifest["status"] != "complete"
        or not isinstance(manifest["files"], list)
        or not isinstance(manifest["totals"], Mapping)
    ):
        raise RedPartyDevelopmentCatalogFreezeRunError(
            "PP materialization manifest identity is invalid"
        )
    file_rows: dict[str, Mapping[str, object]] = {}
    for row in manifest["files"]:
        if (
            not isinstance(row, Mapping)
            or set(row) != {"bytes", "filename", "records", "sha256"}
            or not isinstance(row["filename"], str)
            or row["filename"] in file_rows
        ):
            raise RedPartyDevelopmentCatalogFreezeRunError(
                "PP materialization manifest file row is invalid"
            )
        file_rows[row["filename"]] = row
    if set(file_rows) != set(_ARTIFACT_STREAMS):
        raise RedPartyDevelopmentCatalogFreezeRunError(
            "PP materialization manifest stream set differs"
        )
    streams: dict[str, tuple[dict[str, object], ...]] = {}
    total_bytes = 0
    total_records = 0
    for filename, fixed_records in _ARTIFACT_STREAMS.items():
        row = file_rows[filename]
        path = directory / filename
        file_metadata = path.lstat()
        if not stat.S_ISREG(file_metadata.st_mode) or stat.S_ISLNK(file_metadata.st_mode):
            raise RedPartyDevelopmentCatalogFreezeRunError(
                "PP materialization stream is invalid"
            )
        payload = path.read_bytes()
        if (
            type(row["bytes"]) is not int  # noqa: E721
            or type(row["records"]) is not int  # noqa: E721
            or row["records"] <= 0
            or not isinstance(row["sha256"], str)
            or row["bytes"] != len(payload)
            or (fixed_records is not None and row["records"] != fixed_records)
            or row["sha256"] != hashlib.sha256(payload).hexdigest()
        ):
            raise RedPartyDevelopmentCatalogFreezeRunError(
                "PP materialization stream digest or count differs"
            )
        stream_name = filename.removesuffix(".jsonl")
        streams[stream_name] = _canonical_jsonl_records(
            payload,
            expected_records=row["records"],
            subject=f"PP materialization {stream_name}",
        )
        total_bytes += len(payload)
        total_records += row["records"]
    if manifest["totals"] != {
        "bytes": total_bytes,
        "files": len(_ARTIFACT_STREAMS),
        "records": total_records,
    }:
        raise RedPartyDevelopmentCatalogFreezeRunError(
            "PP materialization manifest totals differ"
        )
    return manifest, streams


def _count(record: Mapping[str, object], key: str) -> int:
    value = record.get(key)
    if type(value) is not int or value < 0:  # noqa: E721
        raise RedPartyDevelopmentCatalogFreezeRunError(
            f"PP materialization {key.replace('_', ' ')} is invalid"
        )
    return value


def _validate_completed_materialization(
    *,
    private_root: Path,
    entry: RedPpMaterializationSource,
    plan: RedPartyDevelopmentPpMaterializationPlan,
    plan_file_sha256: str,
    expected_manifest_sha256: str,
    exact_ci_run: int,
    exact_ci_attempt: int,
    catalog_root: Path,
) -> _CompletedMaterialization:
    artifact_id = f"red-party-pp-materialization-v1-{entry.partition.value}"
    directory = private_root / artifact_id
    _manifest, streams = _artifact_streams(
        directory,
        artifact_id=artifact_id,
        expected_manifest_sha256=expected_manifest_sha256,
    )
    plan_record = streams["plan"][0]
    output_claim = streams["output_claim"][0]
    progress = streams["progress"]
    terminal = streams["terminal"][0]
    if (
        set(plan_record) != _PLAN_RECORD_KEYS
        or plan_record.get("record_type")
        != "party_development_pp_materialization_plan"
        or plan_record.get("schema_version") != 1
        or plan_record.get("source_commit") != plan.source_commit
        or plan_record.get("source_bundle_sha256") != plan.source_bundle_sha256
        or plan_record.get("exact_ci_run") != exact_ci_run
        or plan_record.get("exact_ci_run_attempt") != exact_ci_attempt
        or plan_record.get("exact_ci_workflow") != "CI"
        or plan_record.get("exact_ci_head_sha") != plan.source_commit
        or plan_record.get("private_plan_sha256") != plan.plan_sha256
        or plan_record.get("private_plan_file_sha256") != plan_file_sha256
        or plan_record.get("partition") != entry.partition.value
        or plan_record.get("scenario_id") != entry.scenario_id
        or plan_record.get("source_checkpoint_id") != entry.source_checkpoint_id
        or plan_record.get("source_root_lineage_id") != entry.source_root_lineage_id
        or plan_record.get("source_state_sha256") != entry.source_state_sha256
        or plan_record.get("output_capture_id") != entry.output_capture_id
        or plan_record.get("retry_after_controller_input") is not False
        or any(
            _count(plan_record, key)
            for key in (
                "candidate_menus_constructed",
                "learner_outcomes_opened",
                "teacher_queries",
                "model_predictions",
            )
        )
    ):
        raise RedPartyDevelopmentCatalogFreezeRunError(
            "PP materialization plan record differs from its frozen source"
        )
    if (
        set(output_claim) != _OUTPUT_CLAIM_KEYS
        or output_claim.get("record_type")
        != "party_development_pp_output_claim"
        or output_claim.get("schema_version") != 1
        or output_claim.get("partition") != entry.partition.value
        or output_claim.get("output_capture_id") != entry.output_capture_id
        or output_claim.get("claim_sha256") != _OUTPUT_CLAIM_SHA256
        or output_claim.get("retry_after_controller_input") is not False
        or output_claim.get("private_path_fields") != 0
        or _count(output_claim, "controller_actions") != 0
    ):
        raise RedPartyDevelopmentCatalogFreezeRunError(
            "PP materialization output claim is invalid"
        )
    previous_counters = (0, 0, 0)
    for index, record in enumerate(progress, start=1):
        counters = (
            _count(record, "encounter_steps"),
            _count(record, "controller_actions"),
            _count(record, "frames_executed"),
        )
        if (
            set(record) != _PROGRESS_KEYS
            or record.get("record_type")
            != "party_development_pp_materialization_progress"
            or record.get("schema_version") != 1
            or _count(record, "battles_completed") != index
            or _count(record, "maximum_total_pp") != entry.maximum_total_pp
            or _count(record, "current_total_pp") != entry.maximum_total_pp - index
            or counters < previous_counters
            or any(
                _count(record, key)
                for key in (
                    "candidate_menus_constructed",
                    "learner_outcomes_opened",
                    "teacher_queries",
                    "model_predictions",
                )
            )
        ):
            raise RedPartyDevelopmentCatalogFreezeRunError(
                "PP materialization progress is not exact and monotonic"
            )
        previous_counters = counters
    zero_terminal = (
        "candidate_menus_constructed",
        "captures",
        "faints",
        "heals",
        "learner_outcomes_opened",
        "model_predictions",
        "model_updates",
        "new_persistent_statuses",
        "party_switches",
        "storage_accesses",
        "teacher_queries",
    )
    last = progress[-1]
    if (
        set(terminal) != _TERMINAL_KEYS
        or terminal.get("record_type")
        != "party_development_pp_materialization_terminal"
        or terminal.get("schema_version") != 1
        or terminal.get("partition") != entry.partition.value
        or terminal.get("output_capture_id") != entry.output_capture_id
        or terminal.get("final_pp_bin") != "middle"
        or terminal.get("output_reload_authenticated") is not True
        or any(_count(terminal, key) for key in zero_terminal)
        or _count(terminal, "battles_completed") != len(progress)
        or _count(terminal, "initial_total_pp") != entry.maximum_total_pp
        or _count(terminal, "maximum_total_pp") != entry.maximum_total_pp
        or _count(terminal, "final_total_pp") != entry.maximum_total_pp - len(progress)
        or _count(terminal, "pp_consumed") != len(progress)
        or _count(terminal, "encounter_steps") != _count(last, "encounter_steps")
        or _count(terminal, "controller_actions") != _count(last, "controller_actions")
        or _count(terminal, "frames_executed") != _count(last, "frames_executed")
        or len(progress) < entry.minimum_pp_consumption
        or len(progress) > plan.bounds.maximum_completed_battles
        or _count(terminal, "encounter_steps") > plan.bounds.maximum_encounter_steps
        or _count(terminal, "controller_actions") > plan.bounds.maximum_controller_actions
        or _count(terminal, "frames_executed") > plan.bounds.maximum_frames
    ):
        raise RedPartyDevelopmentCatalogFreezeRunError(
            "PP materialization terminal record is invalid"
        )
    state_path = catalog_root / "captures" / f"{entry.output_capture_id}.state"
    envelope_path = state_path.with_suffix(".state.json")
    capture = load_captured_progress(envelope_path, state_path=state_path)
    output_state_sha256 = terminal.get("output_state_sha256")
    output_envelope_sha256 = terminal.get("output_envelope_sha256")
    if (
        capture.checkpoint_id != entry.output_capture_id
        or capture.state_sha256 != output_state_sha256
        or hashlib.sha256(envelope_path.read_bytes()).hexdigest()
        != output_envelope_sha256
    ):
        raise RedPartyDevelopmentCatalogFreezeRunError(
            "PP materialization output capture differs from its terminal"
        )
    return _CompletedMaterialization(
        entry=entry,
        artifact_id=artifact_id,
        manifest_sha256=expected_manifest_sha256,
        output_state_sha256=capture.state_sha256,
        output_envelope_sha256=output_envelope_sha256,
    )


def _require_inventory_extension(
    previous: PartyDevelopmentCheckpointInventory,
    current: PartyDevelopmentCheckpointInventory,
    *,
    output_capture_ids: set[str],
) -> None:
    previous_by_id = {item.checkpoint_id: item for item in previous.entries}
    current_by_id = {item.checkpoint_id: item for item in current.entries}
    if (
        len(current.entries) != len(previous.entries) + 2
        or set(current_by_id) - set(previous_by_id) != output_capture_ids
        or any(current_by_id[key] != value for key, value in previous_by_id.items())
    ):
        raise RedPartyDevelopmentCatalogFreezeRunError(
            "current inventory is not the exact prior inventory plus two PP states"
        )


def _reservation_from_inventory(
    reservation: PartyDevelopmentQuestionReservation,
    entry: PartyDevelopmentInventoryEntry,
) -> PartyDevelopmentQuestionReservation:
    if (
        entry.partition is not reservation.partition
        or not entry.controls_ready
        or entry.battle_active
        or reservation.goal not in entry.goal_hints
        or sum(member.trainable for member in entry.members) < 2
    ):
        raise RedPartyDevelopmentCatalogFreezeRunError(
            "post-materialization reservation is not a ready goal-relevant context"
        )
    hp_bins = tuple(
        value
        for value in ("empty", "low", "middle", "high")
        if value in {member.hp_bin for member in entry.members}
    )
    pp_bins = tuple(
        value
        for value in ("empty", "low", "middle", "high")
        if value in {member.pp_bin for member in entry.members}
    )
    routes = tuple(
        route
        for route in type(reservation.source_evolution_route_kinds[0])
        if route
        in {
            item
            for member in entry.members
            for item in member.evolution_routes
        }
    )
    return replace(
        reservation,
        source_checkpoint_id=entry.checkpoint_id,
        source_state_sha256=entry.state_sha256,
        source_envelope_sha256=entry.envelope_sha256,
        source_semantic_signature_sha256=entry.semantic_signature_sha256,
        preparation=PartyDevelopmentContextPreparation.NONE,
        target_pp_bin=None,
        source_member_count=len(entry.members),
        source_trainable_count=sum(member.trainable for member in entry.members),
        source_hp_bins=hp_bins,
        source_pp_bins=pp_bins,
        source_evolution_route_kinds=routes,
    )


def _question_paths(
    catalog_root: Path,
    *,
    capture_id: str,
    profile_id: str,
) -> tuple[Path, Path, Path]:
    state = catalog_root / "captures" / f"{capture_id}.state"
    envelope = state.with_suffix(".state.json")
    profile = catalog_root / "profiles" / f"{profile_id}.json"
    if not state.is_file() or not envelope.is_file() or not profile.is_file():
        raise RedPartyDevelopmentCatalogFreezeRunError(
            "catalog question is missing its capture, envelope, or source profile"
        )
    return state, envelope, profile


def _run(args: argparse.Namespace) -> dict[str, object]:
    if (
        type(args.exact_ci_run) is not int  # noqa: E721
        or args.exact_ci_run <= 0
        or type(args.exact_ci_attempt) is not int  # noqa: E721
        or args.exact_ci_attempt <= 0
    ):
        raise RedPartyDevelopmentCatalogFreezeRunError(
            "catalog freeze exact CI identity is invalid"
        )
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    if source.git_commit is None:  # pragma: no cover - source guard owns this
        raise AssertionError("published catalog freeze lost its source commit")
    source_bundle_sha256 = working_source_bundle_sha256(PROJECT_ROOT)
    paths = {
        "reservation_plan": _require_external(
            args.reservation_plan, subject="reservation plan"
        ),
        "previous_inventory": _require_external(
            args.previous_inventory, subject="previous inventory"
        ),
        "current_inventory": _require_external(
            args.current_inventory, subject="current inventory"
        ),
        "pp_plan": _require_external(args.pp_plan, subject="PP plan"),
        "venue_registry": _require_external(
            args.venue_prior_registry, subject="venue registry"
        ),
        "catalog_root": _require_external(args.catalog_root, subject="catalog root"),
        "context_catalog": _require_external(
            args.context_catalog, subject="context catalog"
        ),
        "private_root": _require_external(
            args.private_artifact_root, subject="artifact root"
        ),
        "out_catalog": _require_external(args.out_catalog, subject="frozen catalog"),
        "out_summary": _require_external(args.out_summary, subject="catalog summary"),
    }
    if len(set(paths.values())) != len(paths) or any(
        paths[key].exists() for key in ("out_catalog", "out_summary")
    ):
        raise RedPartyDevelopmentCatalogFreezeRunError(
            "catalog freeze paths collide or an output already exists"
        )
    reservation_plan = PartyDevelopmentQuestionReservationPlan.from_private_dict(
        _load_json(
            paths["reservation_plan"],
            expected_sha256=args.reservation_plan_file_sha256,
            subject="reservation plan",
        )
    )
    previous_inventory = PartyDevelopmentCheckpointInventory.from_private_dict(
        _load_json(
            paths["previous_inventory"],
            expected_sha256=args.previous_inventory_file_sha256,
            subject="previous inventory",
        )
    )
    current_inventory = PartyDevelopmentCheckpointInventory.from_private_dict(
        _load_json(
            paths["current_inventory"],
            expected_sha256=args.current_inventory_file_sha256,
            subject="current inventory",
        )
    )
    pp_plan = RedPartyDevelopmentPpMaterializationPlan.from_private_dict(
        _load_json(
            paths["pp_plan"],
            expected_sha256=args.pp_plan_file_sha256,
            subject="PP plan",
        )
    )
    venue_registry = PartyDevelopmentVenuePriorRegistry.from_private_dict(
        _load_json(
            paths["venue_registry"],
            expected_sha256=args.venue_prior_registry_file_sha256,
            subject="venue registry",
        )
    )
    context_document = _load_json(
        paths["context_catalog"],
        expected_sha256=args.context_catalog_file_sha256,
        subject="context catalog",
    )
    if (
        reservation_plan.plan_sha256 != pp_plan.reservation_plan_sha256
        or args.reservation_plan_file_sha256 != pp_plan.reservation_plan_file_sha256
        or previous_inventory.inventory_sha256 != pp_plan.inventory_sha256
        or args.previous_inventory_file_sha256 != pp_plan.inventory_file_sha256
        or venue_registry.registry_sha256 != pp_plan.venue_prior_registry_sha256
        or args.venue_prior_registry_file_sha256
        != pp_plan.venue_prior_registry_file_sha256
        or args.context_catalog_file_sha256 != pp_plan.context_catalog_file_sha256
    ):
        raise RedPartyDevelopmentCatalogFreezeRunError(
            "catalog freeze inputs differ from the preparation plan"
        )
    output_ids = {item.output_capture_id for item in pp_plan.entries}
    _require_inventory_extension(
        previous_inventory,
        current_inventory,
        output_capture_ids=output_ids,
    )
    current_by_id = {item.checkpoint_id: item for item in current_inventory.entries}
    previous_by_id = {item.checkpoint_id: item for item in previous_inventory.entries}
    reservation_by_scenario = {
        item.scenario_id: item for item in reservation_plan.reservations
    }
    for entry in pp_plan.entries:
        reservation = reservation_by_scenario.get(entry.scenario_id)
        previous_entry = previous_by_id.get(entry.source_checkpoint_id)
        if (
            reservation is None
            or previous_entry is None
            or reservation.preparation
            is not PartyDevelopmentContextPreparation.NATURAL_PP_DEPLETION
            or reservation.source_state_sha256 != entry.source_state_sha256
            or reservation.source_envelope_sha256 != entry.source_envelope_sha256
            or previous_entry.state_sha256 != entry.source_state_sha256
            or previous_entry.envelope_sha256 != entry.source_envelope_sha256
        ):
            raise RedPartyDevelopmentCatalogFreezeRunError(
                "PP preparation does not resolve one exact reserved source"
            )
    open_private_root(paths["private_root"], repository_root=PROJECT_ROOT)
    manifest_hashes = {
        ScenarioPartition.TRAIN: args.train_artifact_manifest_sha256,
        ScenarioPartition.DEVELOPMENT: (
            args.development_artifact_manifest_sha256
        ),
    }
    completed = {
        item.scenario_id: _validate_completed_materialization(
            private_root=paths["private_root"],
            entry=item,
            plan=pp_plan,
            plan_file_sha256=args.pp_plan_file_sha256,
            expected_manifest_sha256=manifest_hashes[item.partition],
            exact_ci_run=args.exact_ci_run,
            exact_ci_attempt=args.exact_ci_attempt,
            catalog_root=paths["catalog_root"],
        )
        for item in pp_plan.entries
    }
    context_source_commit = context_document.get("source_commit")
    if not isinstance(context_source_commit, str):
        raise RedPartyDevelopmentCatalogFreezeRunError(
            "historical context catalog source is invalid"
        )
    historical_registry = load_committed_goal_manager_registry_at_revision(
        PROJECT_ROOT,
        context_source_commit,
    )
    context_catalog = parse_goal_manager_context_catalog(
        paths["context_catalog"].read_bytes(),
        historical_registry,
    )
    if context_catalog.catalog_sha256 != pp_plan.context_catalog_sha256:
        raise RedPartyDevelopmentCatalogFreezeRunError(
            "historical context catalog semantic digest differs"
        )
    route_area = ROUTE_11_TRAINING_VENUE.band
    cave_area = DIGLETTS_CAVE_TRAINING_VENUE.band
    route_evidence = venue_registry.evidence_for(route_area)
    cave_evidence = venue_registry.evidence_for(cave_area)
    if route_evidence is None or cave_evidence is None:
        raise RedPartyDevelopmentCatalogFreezeRunError(
            "catalog freeze lacks both compatible venue priors"
        )
    areas = (route_area, cave_area)
    operational_contracts = (
        route_evidence.operational_contract_sha256,
        cave_evidence.operational_contract_sha256,
    )
    rom_path = resolve_rom_path(args.rom)
    fingerprint = verify_rom(rom_path)
    if fingerprint.sha256 != pp_plan.rom_sha256:
        raise RedPartyDevelopmentCatalogFreezeRunError(
            "catalog freeze ROM differs from the preparation plan"
        )
    evolutions = evolution_graph(rom_path.read_bytes())
    adjacent_before = rom_adjacent_artifacts(rom_path)
    protected_files = {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (
            paths["reservation_plan"],
            paths["previous_inventory"],
            paths["current_inventory"],
            paths["pp_plan"],
            paths["venue_registry"],
            paths["context_catalog"],
        )
    }
    questions = []
    for original in reservation_plan.reservations:
        materialization = completed.get(original.scenario_id)
        if materialization is None:
            if original.preparation is not PartyDevelopmentContextPreparation.NONE:
                raise RedPartyDevelopmentCatalogFreezeRunError(
                    "prepared reservation lacks a completed artifact"
                )
            reservation = original
            profile_id = original.source_checkpoint_id
            materialization_artifact_id = None
            materialization_manifest_sha256 = None
        else:
            output_entry = current_by_id[materialization.entry.output_capture_id]
            if (
                output_entry.state_sha256 != materialization.output_state_sha256
                or output_entry.envelope_sha256
                != materialization.output_envelope_sha256
                or "middle" not in {member.pp_bin for member in output_entry.members}
                or output_entry.state_sha256 in set(
                    reservation_plan.excluded_state_sha256
                )
            ):
                raise RedPartyDevelopmentCatalogFreezeRunError(
                    "prepared inventory row differs from its accepted output"
                )
            reservation = _reservation_from_inventory(original, output_entry)
            profile_id = original.source_checkpoint_id
            materialization_artifact_id = materialization.artifact_id
            materialization_manifest_sha256 = materialization.manifest_sha256
        state_path, envelope_path, profile_path = _question_paths(
            paths["catalog_root"],
            capture_id=reservation.source_checkpoint_id,
            profile_id=profile_id,
        )
        before = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (state_path, envelope_path, profile_path)
        }
        capture = open_goal_manager_context_capture(state_path, envelope_path)
        if (
            capture.capture_id != reservation.source_checkpoint_id
            or capture.state_sha256 != reservation.source_state_sha256
            or capture.envelope_sha256 != reservation.source_envelope_sha256
        ):
            raise RedPartyDevelopmentCatalogFreezeRunError(
                "catalog capture differs from its resolved reservation"
            )
        loaded = load_captured_progress(envelope_path, state_path=state_path)
        if (
            loaded.checkpoint_id != capture.capture_id
            or loaded.state_sha256 != capture.state_sha256
        ):
            raise RedPartyDevelopmentCatalogFreezeRunError(
                "catalog capture loaders disagree"
            )
        profile = load_red_goal_context_profile(profile_path)
        original_entry = context_catalog.entry(profile_id)
        root_lineage_id = original_entry.authenticated_root_lineage_id(
            slot_id=profile_id,
            capture_id=profile_id,
            state_sha256=original.source_state_sha256,
            envelope_sha256=original.source_envelope_sha256,
        )
        if (
            root_lineage_id in set(reservation_plan.excluded_root_lineage_ids)
            or (
                materialization is not None
                and root_lineage_id
                != materialization.entry.source_root_lineage_id
            )
        ):
            raise RedPartyDevelopmentCatalogFreezeRunError(
                "catalog question overlaps prior evidence or loses its root lineage"
            )
        with PyBoyAdapter(rom_path, watch=False, speed=None) as emulator:
            emulator.load_state_bytes(capture.state_bytes)
            reader = PokemonRedStateReader(emulator)
            runtime = build_red_goal_context_runtime(
                profile=profile,
                capture=capture,
                emulator=emulator,
                reader=reader,
            )
            observation = runtime.adapter.observe()
        snapshot = build_red_party_development_snapshot(
            reservation,
            source_root_lineage_id=root_lineage_id,
            observation=observation,
            evolutions=evolutions,
            policy=RED_PARTY_DEVELOPMENT_CURRICULUM_POLICY,
            areas=areas,
            venue_prior_registry=venue_registry,
            venue_operational_contract_sha256=operational_contracts,
            source_commit=source.git_commit,
            source_bundle_sha256=source_bundle_sha256,
        )
        menu: (
            BoundPartyDevelopmentMenu[PartyMemberObservation]
            | BoundPartyDevelopmentMenu[GrindingArea]
            | None
        )
        if reservation.kind is TrainingChoiceKind.TRAINEE:
            menu = snapshot.trainee_menu(route_area)
        else:
            fixed_trainee = snapshot.unique_weakest_goal_relevant_venue_trainee()
            menu = snapshot.venue_menu(fixed_trainee)
        if menu is None or len(menu.bindings) < 2 or sum(menu.candidate_available) < 2:
            raise RedPartyDevelopmentCatalogFreezeRunError(
                "catalog question lacks two genuinely available candidates"
            )
        binding = snapshot.freeze_binding(
            menu,
            scenario_id=reservation.scenario_id,
        )
        RedPartyDevelopmentQuestionPreflight(
            reservation=reservation,
            source_root_lineage_id=root_lineage_id,
            snapshot=snapshot,
            menu=menu,
            binding=binding,
        )
        questions.append(
            PartyDevelopmentFrozenQuestion(
                capture_id=reservation.source_checkpoint_id,
                capture_envelope_sha256=reservation.source_envelope_sha256,
                profile_id=profile_id,
                profile_file_sha256=before[profile_path],
                binding=binding,
                candidate_set=menu.candidate_set,
                materialization_artifact_id=materialization_artifact_id,
                materialization_manifest_sha256=(
                    materialization_manifest_sha256
                ),
            )
        )
        after = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (state_path, envelope_path, profile_path)
        }
        if after != before:
            raise RedPartyDevelopmentCatalogFreezeRunError(
                "catalog question inputs changed during read-only projection"
            )
    catalog = PartyDevelopmentFrozenCatalog.freeze(
        tuple(questions),
        reservation_plan_file_sha256=args.reservation_plan_file_sha256,
        reservation_plan_sha256=reservation_plan.plan_sha256,
        inventory_file_sha256=args.current_inventory_file_sha256,
        inventory_sha256=current_inventory.inventory_sha256,
        pp_plan_file_sha256=args.pp_plan_file_sha256,
        pp_plan_sha256=pp_plan.plan_sha256,
        context_catalog_file_sha256=args.context_catalog_file_sha256,
        context_catalog_sha256=context_catalog.catalog_sha256,
        venue_prior_registry_file_sha256=(
            args.venue_prior_registry_file_sha256
        ),
        venue_prior_registry_sha256=venue_registry.registry_sha256,
        rom_sha256=fingerprint.sha256,
        source_commit=source.git_commit,
        source_bundle_sha256=source_bundle_sha256,
    )
    catalog_payload = _canonical_payload(catalog.private_dict())
    catalog_file_sha256 = _write_exclusive(paths["out_catalog"], catalog_payload)
    try:
        restored = PartyDevelopmentFrozenCatalog.from_private_dict(
            json.loads(paths["out_catalog"].read_text(encoding="ascii"))
        )
        if restored != catalog:
            raise RedPartyDevelopmentCatalogFreezeRunError(
                "persisted catalog failed its independent reload"
            )
        summary = {
            **catalog.public_summary(),
            "catalog_file_sha256": catalog_file_sha256,
            "catalog_file_tracked": False,
            "previous_inventory_file_sha256": (
                args.previous_inventory_file_sha256
            ),
            "historical_checkpoint_count": len(previous_inventory.entries),
            "re_inventory_checkpoint_count": len(current_inventory.entries),
            "new_prepared_checkpoint_count": 2,
            "pp_execution_source_commit": pp_plan.source_commit,
            "exact_ci_run": args.exact_ci_run,
            "exact_ci_attempt": args.exact_ci_attempt,
            "input_files_unchanged": True,
            "rom_adjacent_artifacts_unchanged": True,
        }
        summary_payload = _canonical_payload(summary)
        summary_file_sha256 = _write_exclusive(
            paths["out_summary"],
            summary_payload,
        )
    except BaseException:
        paths["out_catalog"].unlink(missing_ok=True)
        paths["out_summary"].unlink(missing_ok=True)
        raise
    if (
        {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in protected_files
        }
        != protected_files
        or rom_adjacent_artifacts(rom_path) != adjacent_before
    ):
        paths["out_catalog"].unlink(missing_ok=True)
        paths["out_summary"].unlink(missing_ok=True)
        raise RedPartyDevelopmentCatalogFreezeRunError(
            "catalog freeze changed a protected input"
        )
    return {**summary, "summary_file_sha256": summary_file_sha256}


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        result = _run(parser.parse_args(argv))
    except (OSError, RuntimeError, TypeError, ValueError):
        parser.error("Red party catalog freeze failed closed; private paths were withheld")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
