#!/usr/bin/env python3
"""Freeze one canonical seven-capture Red battle materialization plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from collections import Counter
from contextlib import suppress
from pathlib import Path
from typing import cast

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from inventory_battle_scenario_source_venues import (  # noqa: E402
    BattleScenarioSourceInventoryError,
    _CatalogTrainRootScan,
    _load_catalog,
    _observe_root,
    _open_all_catalog_train_roots,
    _require_state_bank,
)

from pokemon_red_completion.battle_outcome_batch import MAXIMUM_LEVEL_GAP  # noqa: E402
from pokemon_red_completion.battle_outcome_capture_authentication import (  # noqa: E402
    BattleScenarioSourceBinding,
)
from pokemon_red_completion.battle_scenario_materialization_plan import (  # noqa: E402
    MANSION_VENUE_ID,
    ROUTE_11_VENUE_ID,
    BattleScenarioMaterializationCandidate,
    BattleScenarioMaterializationPlan,
    BattleScenarioMaterializationPlanError,
    BattleScenarioPartySlot,
    build_battle_scenario_materialization_plan,
    parse_battle_scenario_materialization_plan,
)
from pokemon_red_completion.battle_scenario_source_venue import (  # noqa: E402
    BattleScenarioSourceVenueError,
    battle_scenario_source_venue,
)
from pokemon_red_completion.blaine import (  # noqa: E402
    MANSION_TRAINING_VENUE,
    ROUTE_11_TRAINING_VENUE,
)
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    working_source_bundle_sha256,
)
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.goal_manager_composition_qualification import (  # noqa: E402
    FreshCompositionQualificationError,
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
)
from pokemon_red_completion.observation import (  # noqa: E402
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_battle_scenario import (  # noqa: E402
    red_battle_supported_move_count,
)
from pokemon_red_completion.rom import resolve_rom_path, verify_rom  # noqa: E402
from pokemon_red_completion.runtime_identity import (  # noqa: E402
    build_runtime_identity,
    require_pyboy_import_origins,
)
from pokemon_red_completion.training_venue import TrainingVenue  # noqa: E402

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_MAXIMUM_PLAN_BYTES = 8 * 1024 * 1024


class BattleScenarioMaterializationFreezeError(RuntimeError):
    """Raised before a private seven-capture plan can be retained."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-id", required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    parser.add_argument("--state-bank", type=Path, required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--expected-context-catalog-sha256", required=True)
    parser.add_argument("--registry-source-commit", required=True)
    parser.add_argument("--expected-registry-sha256", required=True)
    parser.add_argument("--capture-directory", type=Path, required=True)
    parser.add_argument("--out-plan", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    source_commit = _commit(args.expected_source_commit, "source")
    source_bundle = working_source_bundle_sha256(PROJECT_ROOT)
    if (
        source.git_commit != source_commit
        or source_bundle
        != _sha256(args.expected_source_bundle_sha256, "source bundle")
    ):
        raise BattleScenarioMaterializationFreezeError(
            "published source identity differs"
        )

    runtime = build_runtime_identity()
    require_pyboy_import_origins(runtime)
    rom_path = resolve_rom_path(args.rom)
    rom = verify_rom(rom_path)
    capture_directory = _private_capture_directory(
        args.capture_directory,
        rom_path=rom_path,
    )
    destination = _private_new_plan(
        args.out_plan,
        capture_directory=capture_directory,
    )
    capture_directory_sha256 = hashlib.sha256(
        str(capture_directory).encode("utf-8")
    ).hexdigest()

    try:
        catalog, registry = _load_catalog(
            args.context_catalog,
            expected_catalog_sha256=_sha256(
                args.expected_context_catalog_sha256,
                "context catalog",
            ),
            registry_source_commit=_commit(
                args.registry_source_commit,
                "registry source",
            ),
            expected_registry_sha256=_sha256(
                args.expected_registry_sha256,
                "registry",
            ),
        )
        scan = _open_all_catalog_train_roots(
            _require_state_bank(args.state_bank),
            catalog=catalog,
            registry=registry,
        )
    except BattleScenarioSourceInventoryError as error:
        raise BattleScenarioMaterializationFreezeError(str(error)) from None
    if scan.missing_catalog_train_roots != 0:
        raise BattleScenarioMaterializationFreezeError(
            "complete catalog train state bank is required"
        )

    registry_path = open_fixed_account_claim_registry()
    try:
        plan, claim_available_roots = _freeze_under_shared_lease(
            scan=scan,
            registry_path=registry_path,
            rom_path=rom_path,
            plan_id=args.plan_id,
            source_commit=source_commit,
            source_bundle_sha256=source_bundle,
            rom_sha256=rom.sha256,
            capture_directory=capture_directory,
            capture_directory_sha256=capture_directory_sha256,
            destination=destination,
        )
    except (
        BattleScenarioMaterializationPlanError,
        BattleScenarioSourceInventoryError,
        FreshCompositionQualificationError,
    ) as error:
        raise BattleScenarioMaterializationFreezeError(str(error)) from None

    reopened = _read_private_plan(destination)
    if reopened != plan:
        raise BattleScenarioMaterializationFreezeError(
            "retained battle materialization plan differs after reopen"
        )
    inventory_counts = Counter(item.venue_id for item in plan.inventory)
    assignment_counts = Counter(item.candidate.venue_id for item in plan.assignments)
    return {
        "schema": "pokemon-red-battle-scenario-materialization-freeze-receipt-v1",
        "status": "prospective_unexecuted_seven_capture_plan_frozen",
        "plan_id": plan.plan_id,
        "plan_sha256": plan.plan_sha256,
        "selection_policy_sha256": plan.selection_policy_sha256,
        "source_commit": source_commit,
        "source_bundle_sha256": source_bundle,
        "runtime_identity_sha256": runtime.sha256,
        "rom_sha256": rom.sha256,
        "capture_directory_sha256": capture_directory_sha256,
        "context_catalog_sha256": catalog.catalog_sha256,
        "registry_sha256": registry.registry_sha256,
        "registry_source_commit": registry.execution.source_commit,
        "catalog_train_roots": len(scan.roots),
        "claim_available_train_roots": claim_available_roots,
        "eligible_candidate_counts": dict(sorted(inventory_counts.items())),
        "selected_capture_counts": dict(sorted(assignment_counts.items())),
        "selected_capture_count": len(plan.assignments),
        "selected_source_root_count": len(
            {item.candidate.source.source_state_sha256 for item in plan.assignments}
        ),
        "selected_party_slot_count": len(
            {item.party_slot.party_slot for item in plan.assignments}
        ),
        "selected_species_count": len(
            {item.party_slot.species_id for item in plan.assignments}
        ),
        "retry_after_controller_input": False,
        "controller_actions": 0,
        "emulator_frames": 0,
        "root_claims_created": 0,
        "battle_captures_created": 0,
        "outcomes_opened": 0,
        "model_predictions": 0,
        "model_fits": 0,
        "teacher_queries": 0,
        "sealed_red_cases_opened": 0,
        "crystal_contexts_opened": 0,
        "full_game_replays": 0,
        "authority_promoted": False,
        "private_identity_fields": 0,
        "private_path_fields": 0,
    }


def _freeze_under_shared_lease(
    *,
    scan: _CatalogTrainRootScan,
    registry_path: Path,
    rom_path: Path,
    plan_id: str,
    source_commit: str,
    source_bundle_sha256: str,
    rom_sha256: str,
    capture_directory: Path,
    capture_directory_sha256: str,
    destination: Path,
) -> tuple[BattleScenarioMaterializationPlan, int]:
    with (
        fixed_account_claim_registry_lease(registry_path, exclusive=False),
        PyBoyAdapter(rom_path) as emulator,
    ):
        candidates: list[BattleScenarioMaterializationCandidate] = []
        claim_available_roots = 0
        for root in scan.roots:
            observed = _observe_root(
                root,
                emulator=emulator,
                registry_path=registry_path,
            )
            claim_available_roots += int(observed.claim_available)
            if not observed.materialization_eligible:
                continue
            candidate = _candidate_from_loaded_root(
                root.binding,
                observed.venue_id,
                emulator=emulator,
            )
            if candidate is not None:
                candidates.append(candidate)
        if emulator.frame_count != 0 or emulator.pressed_buttons:
            raise BattleScenarioMaterializationFreezeError(
                "battle materialization freeze crossed the controller boundary"
            )
        plan = build_battle_scenario_materialization_plan(
            plan_id=plan_id,
            source_commit=source_commit,
            source_bundle_sha256=source_bundle_sha256,
            rom_sha256=rom_sha256,
            capture_directory_sha256=capture_directory_sha256,
            candidates=candidates,
        )
        _require_new_assignment_outputs(
            plan,
            capture_directory=capture_directory,
            plan_destination=destination,
        )
        _write_exclusive(destination, plan.canonical_bytes())
    return plan, claim_available_roots


def _candidate_from_loaded_root(
    binding: BattleScenarioSourceBinding,
    venue_id: str | None,
    *,
    emulator: PyBoyAdapter,
) -> BattleScenarioMaterializationCandidate | None:
    venues = {
        MANSION_VENUE_ID: MANSION_TRAINING_VENUE,
        ROUTE_11_VENUE_ID: ROUTE_11_TRAINING_VENUE,
    }
    if venue_id not in venues:
        return None
    venue = venues[venue_id]
    reader = PokemonRedStateReader(emulator)
    raw = reader.read()
    try:
        source = battle_scenario_source_venue(
            raw,
            last_blackout_map=reader.read_last_blackout_map(),
            current_map_tileset=emulator.read_u8(RamAddress.CURRENT_MAP_TILESET),
        )
    except BattleScenarioSourceVenueError as error:
        raise BattleScenarioMaterializationFreezeError(str(error)) from None
    if source.venue_id != venue_id:
        raise BattleScenarioMaterializationFreezeError(
            "battle source venue changed during freeze"
        )
    slots = _eligible_party_slots(raw, venue=venue)
    if not slots:
        return None
    rare_maximum = venue.band.rare_maximum_encounter_level
    if type(rare_maximum) is not int:  # noqa: E721
        raise BattleScenarioMaterializationFreezeError(
            "battle source rare encounter ceiling differs"
        )
    return BattleScenarioMaterializationCandidate(
        source=binding,
        venue_id=venue_id,
        source_location=source.source_location,
        minimum_encounter_level=venue.band.minimum_encounter_level,
        maximum_encounter_level=venue.band.maximum_encounter_level,
        rare_maximum_encounter_level=rare_maximum,
        party_slots=slots,
    )


def _eligible_party_slots(
    raw: RawGameState,
    *,
    venue: TrainingVenue,
) -> tuple[BattleScenarioPartySlot, ...]:
    party_fields = (
        raw.party_species_ids,
        raw.party_levels,
        raw.party_hp,
        raw.party_max_hp,
        raw.party_status,
        raw.party_moves,
        raw.party_pp,
    )
    if (
        type(raw.party_count) is not int  # noqa: E721
        or not 1 <= raw.party_count <= 6
        or any(not isinstance(field, tuple) for field in party_fields)
        or any(len(field) != raw.party_count for field in party_fields if field is not None)
    ):
        raise BattleScenarioMaterializationFreezeError(
            "battle source party observation differs"
        )
    band = getattr(venue, "band", None)
    minimum = getattr(band, "minimum_encounter_level", None)
    rare_maximum = getattr(band, "rare_maximum_encounter_level", None)
    if type(minimum) is not int or type(rare_maximum) is not int:  # noqa: E721
        raise BattleScenarioMaterializationFreezeError(
            "battle source encounter band differs"
        )
    minimum_safe_level = rare_maximum - MAXIMUM_LEVEL_GAP
    maximum_safe_level = minimum + MAXIMUM_LEVEL_GAP
    species = cast(tuple[int, ...], raw.party_species_ids)
    levels = cast(tuple[int, ...], raw.party_levels)
    hp = cast(tuple[int, ...], raw.party_hp)
    maximum_hp = cast(tuple[int, ...], raw.party_max_hp)
    status = cast(tuple[int, ...], raw.party_status)
    moves = cast(tuple[tuple[int, ...], ...], raw.party_moves)
    pp = cast(tuple[tuple[int, ...], ...], raw.party_pp)
    result = []
    for index, values in enumerate(
        zip(species, levels, hp, maximum_hp, status, moves, pp, strict=True),
        start=1,
    ):
        species_id, level, current_hp, max_hp, status_id, move_ids, current_pp = values
        if not isinstance(move_ids, tuple) or not isinstance(current_pp, tuple):
            raise BattleScenarioMaterializationFreezeError(
                "battle source move observation differs"
            )
        try:
            usable = red_battle_supported_move_count(move_ids, current_pp)
        except ValueError:
            raise BattleScenarioMaterializationFreezeError(
                "battle source move mechanics differ"
            ) from None
        if (
            type(current_hp) is int  # noqa: E721
            and current_hp > 0
            and type(level) is int  # noqa: E721
            and minimum_safe_level <= level <= maximum_safe_level
            and usable >= 2
        ):
            result.append(
                BattleScenarioPartySlot(
                    party_slot=index,
                    species_id=species_id,
                    level=level,
                    current_hp=current_hp,
                    maximum_hp=max_hp,
                    status_id=status_id,
                    usable_move_count=usable,
                )
            )
    return tuple(result)


def _private_capture_directory(path: Path, *, rom_path: Path) -> Path:
    try:
        resolved = path.resolve(strict=True)
        observed = resolved.stat()
    except OSError:
        raise BattleScenarioMaterializationFreezeError(
            "capture directory is unavailable"
        ) from None
    if (
        resolved.is_relative_to(PROJECT_ROOT.resolve())
        or resolved == rom_path.resolve().parent
        or not stat.S_ISDIR(observed.st_mode)
        or observed.st_uid != os.getuid()
        or stat.S_IMODE(observed.st_mode) & 0o022
    ):
        raise BattleScenarioMaterializationFreezeError(
            "capture directory cannot be authenticated"
        )
    return resolved


def _private_new_plan(destination: Path, *, capture_directory: Path) -> Path:
    resolved = destination.resolve()
    if (
        resolved.parent != capture_directory
        or resolved.exists()
        or destination.is_symlink()
    ):
        raise BattleScenarioMaterializationFreezeError(
            "battle materialization plan output is unavailable or already exists"
        )
    return resolved


def _require_new_assignment_outputs(
    plan: BattleScenarioMaterializationPlan,
    *,
    capture_directory: Path,
    plan_destination: Path,
) -> None:
    outputs: list[Path] = []
    for assignment in plan.assignments:
        state_filename = assignment.state_filename
        manifest_filename = assignment.manifest_filename
        outputs.extend(
            (
                (capture_directory / state_filename).resolve(),
                (capture_directory / manifest_filename).resolve(),
            )
        )
    if (
        len(outputs) != len(set(outputs))
        or plan_destination in outputs
        or any(path.parent != capture_directory for path in outputs)
        or any(path.exists() or path.is_symlink() for path in outputs)
    ):
        raise BattleScenarioMaterializationFreezeError(
            "battle materialization assignment output is not new and private"
        )


def _write_exclusive(destination: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    directory_descriptor = -1
    created = False
    failed = False
    try:
        descriptor = os.open(destination, flags, 0o600)
        created = True
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("write made no progress")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        directory_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        directory_flags |= getattr(os, "O_DIRECTORY", 0)
        directory_descriptor = os.open(destination.parent, directory_flags)
        os.fsync(directory_descriptor)
    except OSError:
        failed = True
    finally:
        for current in (descriptor, directory_descriptor):
            if current >= 0:
                try:
                    os.close(current)
                except OSError:
                    failed = True
    if failed:
        if created:
            with suppress(OSError):
                destination.unlink()
        raise BattleScenarioMaterializationFreezeError(
            "battle materialization plan could not be retained durably"
        )


def _read_private_plan(path: Path):  # type: ignore[no-untyped-def]
    descriptor = -1
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
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
            or stat.S_IMODE(opened.st_mode) & 0o077
            or not 1 <= opened.st_size <= _MAXIMUM_PLAN_BYTES
        ):
            raise OSError("unsafe plan")
        payload = b""
        while len(payload) < opened.st_size:
            chunk = os.read(descriptor, opened.st_size - len(payload))
            if not chunk:
                raise OSError("plan changed while reading")
            payload += chunk
        after = os.fstat(descriptor)
        if (
            after.st_dev != opened.st_dev
            or after.st_ino != opened.st_ino
            or after.st_mode != opened.st_mode
            or after.st_nlink != opened.st_nlink
            or after.st_uid != opened.st_uid
            or after.st_size != opened.st_size
            or after.st_mtime_ns != opened.st_mtime_ns
        ):
            raise OSError("plan changed while reading")
    except OSError:
        raise BattleScenarioMaterializationFreezeError(
            "battle materialization plan cannot be reopened"
        ) from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    try:
        return parse_battle_scenario_materialization_plan(payload)
    except BattleScenarioMaterializationPlanError as error:
        raise BattleScenarioMaterializationFreezeError(str(error)) from None


def _commit(value: object, subject: str) -> str:
    if not isinstance(value, str) or _GIT_COMMIT.fullmatch(value) is None:
        raise BattleScenarioMaterializationFreezeError(f"{subject} commit differs")
    return value


def _sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise BattleScenarioMaterializationFreezeError(f"{subject} digest differs")
    return value


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    print(json.dumps(_run(args), ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
