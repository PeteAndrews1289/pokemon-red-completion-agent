#!/usr/bin/env python3
"""Freeze one canonical multi-venue seven-capture Red battle plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from freeze_battle_scenario_materialization_plan import (  # noqa: E402
    BattleScenarioMaterializationFreezeError,
    _eligible_party_slots,
    _private_capture_directory,
    _private_new_plan,
    _write_exclusive,
)
from inventory_battle_scenario_source_venues import (  # noqa: E402
    BattleScenarioSourceInventoryError,
    _CatalogTrainRootScan,
    _load_attempted_source_exclusions,
    _load_catalog,
    _observe_root,
    _open_all_catalog_train_roots,
    _require_state_bank,
)

from pokemon_red_completion.battle_outcome_capture_authentication import (  # noqa: E402
    BattleScenarioSourceBinding,
)
from pokemon_red_completion.battle_scenario_materialization_plan_v2 import (  # noqa: E402
    BattleScenarioMaterializationCandidateV2,
    BattleScenarioMaterializationPlanV2,
    BattleScenarioMaterializationPlanV2Error,
    BattleScenarioReachableVenue,
    build_battle_scenario_materialization_plan_v2,
    parse_battle_scenario_materialization_plan_v2,
)
from pokemon_red_completion.battle_scenario_source_venue import (  # noqa: E402
    BattleScenarioSourceVenueError,
    battle_scenario_reachable_venues,
)
from pokemon_red_completion.blaine import (  # noqa: E402
    DIGLETTS_CAVE_TRAINING_VENUE,
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
)
from pokemon_red_completion.provenance import (  # noqa: E402
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.rom import resolve_rom_path, verify_rom  # noqa: E402
from pokemon_red_completion.runtime_identity import (  # noqa: E402
    build_runtime_identity,
    require_pyboy_import_origins,
)


class BattleScenarioMaterializationFreezeV2Error(RuntimeError):
    """Raised before a multi-venue private plan can be retained."""


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
    parser.add_argument("--excluded-plan", type=Path, required=True)
    parser.add_argument("--expected-excluded-plan-sha256", required=True)
    parser.add_argument("--excluded-run-journal", type=Path, required=True)
    parser.add_argument("--expected-excluded-run-journal-sha256", required=True)
    parser.add_argument("--capture-directory", type=Path, required=True)
    parser.add_argument("--out-plan", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    if source.git_commit != args.expected_source_commit:
        raise BattleScenarioMaterializationFreezeV2Error(
            "published source identity differs"
        )
    source_bundle = working_source_bundle_sha256(PROJECT_ROOT)
    if source_bundle != args.expected_source_bundle_sha256:
        raise BattleScenarioMaterializationFreezeV2Error(
            "published source bundle differs"
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
            expected_catalog_sha256=args.expected_context_catalog_sha256,
            registry_source_commit=args.registry_source_commit,
            expected_registry_sha256=args.expected_registry_sha256,
        )
        scan = _open_all_catalog_train_roots(
            _require_state_bank(args.state_bank),
            catalog=catalog,
            registry=registry,
        )
        attempted_sources = _load_attempted_source_exclusions(
            args.excluded_plan,
            args.excluded_run_journal,
            expected_plan_sha256=args.expected_excluded_plan_sha256,
            expected_journal_sha256=args.expected_excluded_run_journal_sha256,
        )
    except BattleScenarioSourceInventoryError as error:
        raise BattleScenarioMaterializationFreezeV2Error(str(error)) from None
    if scan.missing_catalog_train_roots != 0:
        raise BattleScenarioMaterializationFreezeV2Error(
            "complete catalog train state bank is required"
        )
    successor_scan = _CatalogTrainRootScan(
        roots=tuple(
            root
            for root in scan.roots
            if root.binding.source_state_sha256 not in attempted_sources
        ),
        state_files_hashed=scan.state_files_hashed,
        matching_state_file_copies=scan.matching_state_file_copies,
        missing_catalog_train_roots=scan.missing_catalog_train_roots,
    )

    registry_path = open_fixed_account_claim_registry()
    try:
        plan, claim_available_roots = _freeze_under_shared_lease(
            scan=successor_scan,
            registry_path=registry_path,
            rom_path=rom_path,
            plan_id=args.plan_id,
            source_commit=args.expected_source_commit,
            source_bundle_sha256=source_bundle,
            rom_sha256=rom.sha256,
            capture_directory=capture_directory,
            capture_directory_sha256=capture_directory_sha256,
            excluded_plan_sha256=args.expected_excluded_plan_sha256,
            excluded_run_journal_sha256=args.expected_excluded_run_journal_sha256,
            destination=destination,
        )
    except (
        BattleScenarioMaterializationFreezeError,
        BattleScenarioMaterializationPlanV2Error,
        BattleScenarioSourceInventoryError,
        FreshCompositionQualificationError,
    ) as error:
        raise BattleScenarioMaterializationFreezeV2Error(str(error)) from None

    reopened = _read_private_plan_v2(destination)
    if reopened != plan:
        raise BattleScenarioMaterializationFreezeV2Error(
            "retained battle materialization plan differs after reopen"
        )
    eligible_counts = Counter(
        venue.venue_id
        for candidate in plan.inventory
        for venue in candidate.reachable_venues
    )
    selected_counts = Counter(
        assignment.selected_venue.venue_id for assignment in plan.assignments
    )
    return {
        "schema": "pokemon-red-battle-scenario-materialization-freeze-receipt-v2",
        "status": "prospective_unexecuted_multivenue_plan_frozen",
        "plan_id": plan.plan_id,
        "plan_sha256": plan.plan_sha256,
        "selection_policy_sha256": plan.selection_policy_sha256,
        "source_commit": source.git_commit,
        "source_bundle_sha256": source_bundle,
        "runtime_identity_sha256": runtime.sha256,
        "rom_sha256": rom.sha256,
        "capture_directory_sha256": capture_directory_sha256,
        "context_catalog_sha256": catalog.catalog_sha256,
        "registry_sha256": registry.registry_sha256,
        "registry_source_commit": registry.execution.source_commit,
        "catalog_train_roots": len(scan.roots),
        "excluded_attempted_source_roots": len(attempted_sources),
        "successor_candidate_train_roots": len(successor_scan.roots),
        "claim_available_train_roots": claim_available_roots,
        "eligible_candidate_root_count": len(plan.inventory),
        "eligible_root_venue_edge_counts": dict(sorted(eligible_counts.items())),
        "selected_capture_counts": dict(sorted(selected_counts.items())),
        "selected_capture_count": len(plan.assignments),
        "selected_source_root_count": len(
            {
                item.candidate.source.source_state_sha256
                for item in plan.assignments
            }
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
    excluded_plan_sha256: str,
    excluded_run_journal_sha256: str,
    destination: Path,
) -> tuple[BattleScenarioMaterializationPlanV2, int]:
    with (
        fixed_account_claim_registry_lease(registry_path, exclusive=False),
        PyBoyAdapter(rom_path) as emulator,
    ):
        candidates = []
        claim_available_roots = 0
        for root in scan.roots:
            observed = _observe_root(
                root,
                emulator=emulator,
                registry_path=registry_path,
            )
            claim_available_roots += int(observed.claim_available)
            if not observed.reachable_venue_allocation_eligible:
                continue
            candidate = _candidate_from_loaded_root(
                root.binding,
                expected_venue_ids=observed.eligible_venue_ids,
                emulator=emulator,
            )
            candidates.append(candidate)
        if emulator.frame_count != 0 or emulator.pressed_buttons:
            raise BattleScenarioMaterializationFreezeV2Error(
                "battle materialization freeze crossed the controller boundary"
            )
        plan = build_battle_scenario_materialization_plan_v2(
            plan_id=plan_id,
            source_commit=source_commit,
            source_bundle_sha256=source_bundle_sha256,
            rom_sha256=rom_sha256,
            capture_directory_sha256=capture_directory_sha256,
            excluded_plan_sha256=excluded_plan_sha256,
            excluded_run_journal_sha256=excluded_run_journal_sha256,
            candidates=candidates,
        )
        _require_new_assignment_outputs_v2(
            plan,
            capture_directory=capture_directory,
            plan_destination=destination,
        )
        _write_exclusive(destination, plan.canonical_bytes())
    return plan, claim_available_roots


def _require_new_assignment_outputs_v2(
    plan: BattleScenarioMaterializationPlanV2,
    *,
    capture_directory: Path,
    plan_destination: Path,
) -> None:
    outputs = [
        (capture_directory / filename).resolve()
        for assignment in plan.assignments
        for filename in (assignment.state_filename, assignment.manifest_filename)
    ]
    if (
        len(outputs) != len(set(outputs))
        or plan_destination in outputs
        or any(path.parent != capture_directory for path in outputs)
        or any(path.exists() or path.is_symlink() for path in outputs)
    ):
        raise BattleScenarioMaterializationFreezeV2Error(
            "battle materialization assignment output is not new and private"
        )


def _candidate_from_loaded_root(
    binding: BattleScenarioSourceBinding,
    *,
    expected_venue_ids: tuple[str, ...],
    emulator: PyBoyAdapter,
) -> BattleScenarioMaterializationCandidateV2:
    venues_by_id = {
        "digletts_cave": DIGLETTS_CAVE_TRAINING_VENUE,
        "pokemon_mansion_1f": MANSION_TRAINING_VENUE,
        "route_11": ROUTE_11_TRAINING_VENUE,
    }
    reader = PokemonRedStateReader(emulator)
    raw = reader.read()
    try:
        reachable = battle_scenario_reachable_venues(
            raw,
            last_blackout_map=reader.read_last_blackout_map(),
            current_map_tileset=emulator.read_u8(RamAddress.CURRENT_MAP_TILESET),
        )
    except BattleScenarioSourceVenueError as error:
        raise BattleScenarioMaterializationFreezeV2Error(str(error)) from None
    frozen_venues = []
    for edge in reachable:
        venue_id = edge.venue_id
        venue = venues_by_id.get(venue_id)
        if venue is None:
            raise BattleScenarioMaterializationFreezeV2Error(
                "battle source selected venue is unsupported"
            )
        slots = _eligible_party_slots(raw, venue=venue)
        if not slots:
            continue
        rare_maximum = venue.band.rare_maximum_encounter_level
        if type(rare_maximum) is not int:  # noqa: E721
            raise BattleScenarioMaterializationFreezeV2Error(
                "battle source rare encounter ceiling differs"
            )
        frozen_venues.append(
            BattleScenarioReachableVenue(
                venue_id=venue_id,
                source_location=edge.source_location,
                minimum_encounter_level=venue.band.minimum_encounter_level,
                maximum_encounter_level=venue.band.maximum_encounter_level,
                rare_maximum_encounter_level=rare_maximum,
                party_slots=slots,
            )
        )
    if tuple(item.venue_id for item in frozen_venues) != tuple(
        sorted(expected_venue_ids)
    ):
        raise BattleScenarioMaterializationFreezeV2Error(
            "battle source eligible reachable venues changed during freeze"
        )
    return BattleScenarioMaterializationCandidateV2(
        source=binding,
        reachable_venues=tuple(frozen_venues),
    )


def _read_private_plan_v2(path: Path) -> BattleScenarioMaterializationPlanV2:
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
            or opened.st_uid != os.getuid()
            or opened.st_nlink != 1
            or opened.st_mode & 0o077
            or not 1 <= opened.st_size <= 8 * 1024 * 1024
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
            or after.st_size != opened.st_size
            or after.st_mtime_ns != opened.st_mtime_ns
        ):
            raise OSError("plan changed while reading")
    except OSError:
        raise BattleScenarioMaterializationFreezeV2Error(
            "battle materialization plan cannot be reopened"
        ) from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    try:
        return parse_battle_scenario_materialization_plan_v2(payload)
    except BattleScenarioMaterializationPlanV2Error as error:
        raise BattleScenarioMaterializationFreezeV2Error(str(error)) from None


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    print(json.dumps(_run(args), ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
