#!/usr/bin/env python3
"""Inventory one complete catalog partition at its loaded Red maps without acting."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import cast

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.battle_outcome_batch import (  # noqa: E402
    DEVELOPMENT_CONTEXTS,
    FRESH_TRAIN_CONTEXTS,
    MAXIMUM_LEVEL_GAP,
    MAXIMUM_SINGLE_BUCKET_CONTEXTS,
    MINIMUM_DISTINCT_VENUES,
)
from pokemon_red_completion.battle_outcome_capture_authentication import (  # noqa: E402
    BattleOutcomeCaptureAuthenticationError,
    BattleScenarioSourceBinding,
    authenticate_battle_scenario_source_binding,
)
from pokemon_red_completion.battle_scenario_materialization_plan import (  # noqa: E402
    MANSION_VENUE_ID,
    ROUTE_11_VENUE_ID,
    BattleScenarioMaterializationPlanError,
    parse_battle_scenario_materialization_plan,
)
from pokemon_red_completion.battle_scenario_materialization_plan_v2 import (  # noqa: E402
    BattleScenarioMaterializationPlanV2Error,
    parse_battle_scenario_materialization_completion_plan,
    parse_battle_scenario_materialization_plan_v2,
)
from pokemon_red_completion.battle_scenario_materialization_run import (  # noqa: E402
    PENDING,
    BattleScenarioMaterializationPlanLike,
    BattleScenarioMaterializationRunError,
    BattleScenarioMaterializationRunJournal,
    parse_battle_scenario_materialization_run,
    require_battle_scenario_materialization_run_matches_plan,
)
from pokemon_red_completion.battle_scenario_source_venue import (  # noqa: E402
    BattleScenarioSourceVenueError,
    battle_scenario_reachable_venues,
    battle_scenario_source_venue,
)
from pokemon_red_completion.blaine import (  # noqa: E402
    DIGLETTS_CAVE_TRAINING_VENUE,
    MANSION_TRAINING_VENUE,
    ROUTE_11_TRAINING_VENUE,
)
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.goal_manager_composition_qualification import (  # noqa: E402
    FreshCompositionQualificationError,
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
    root_claim_is_available,
)
from pokemon_red_completion.goal_manager_context_catalog import (  # noqa: E402
    GoalManagerContextCatalog,
    GoalManagerContextCatalogError,
    parse_goal_manager_context_catalog,
)
from pokemon_red_completion.goal_manager_protocol import (  # noqa: E402
    GoalManagerCollectionRegistry,
    GoalManagerProtocolError,
    load_committed_goal_manager_registry_at_revision,
)
from pokemon_red_completion.observation import (  # noqa: E402
    MapId,
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
    RedBattleScenarioError,
    red_battle_refreshable_supported_move_count,
    red_battle_supported_move_count,
)
from pokemon_red_completion.red_training_transitions import (  # noqa: E402
    red_training_fly_available,
    red_training_ground_transition_available,
    red_vermilion_training_transition_available,
)
from pokemon_red_completion.rom import resolve_rom_path  # noqa: E402
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402
from pokemon_red_completion.scenario_venue_allocation import (  # noqa: E402
    ReachableVenueRoot,
    allocate_reachable_venue_roots,
)

_MAXIMUM_STATE_BYTES = 64 * 1024 * 1024
_MAXIMUM_CATALOG_BYTES = 4 * 1024 * 1024


class BattleScenarioSourceInventoryError(RuntimeError):
    """Raised before an action-free inventory can overstate source capacity."""


@dataclass(frozen=True, slots=True)
class _CatalogTrainRoot:
    binding: BattleScenarioSourceBinding
    state_bytes: bytes


@dataclass(frozen=True, slots=True)
class _CatalogTrainRootScan:
    roots: tuple[_CatalogTrainRoot, ...]
    state_files_hashed: int
    matching_state_file_copies: int
    missing_catalog_train_roots: int


@dataclass(frozen=True, slots=True)
class _ObservedTrainRoot:
    map_label: str
    venue_id: str | None
    relocation_required: bool
    fly_relocation_ready: bool
    ground_relocation_ready: bool
    route_11_relocation_ready: bool
    claim_available: bool
    safe_nonbattle: bool
    living_party_member_available: bool
    supported_party_slot_available: bool
    refreshable_party_slot_available: bool
    reachable_venue_ids: tuple[str, ...] = ()
    eligible_venue_ids: tuple[str, ...] = ()

    @property
    def materialization_eligible(self) -> bool:
        return (
            self.claim_available
            and self.safe_nonbattle
            and self.living_party_member_available
            and self.supported_party_slot_available
            and self.venue_id is not None
        )

    @property
    def resource_conditioning_eligible(self) -> bool:
        """Whether a full-heal route can create a genuine two-action source."""

        return (
            self.claim_available
            and self.safe_nonbattle
            and self.living_party_member_available
            and self.refreshable_party_slot_available
            and self.venue_id is not None
        )

    @property
    def reachable_venue_allocation_eligible(self) -> bool:
        """Whether at least one reachable venue preserves exact decision pressure."""

        return (
            self.claim_available
            and self.safe_nonbattle
            and self.living_party_member_available
            and bool(self.eligible_venue_ids)
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-bank", type=Path, required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--expected-context-catalog-sha256", required=True)
    parser.add_argument("--registry-source-commit", required=True)
    parser.add_argument("--expected-registry-sha256", required=True)
    parser.add_argument(
        "--partition",
        choices=(ScenarioPartition.TRAIN.value, ScenarioPartition.DEVELOPMENT.value),
        required=True,
    )
    parser.add_argument("--excluded-plan", type=Path, required=True)
    parser.add_argument("--expected-excluded-plan-sha256", required=True)
    parser.add_argument("--excluded-run-journal", type=Path, required=True)
    parser.add_argument("--expected-excluded-run-journal-sha256", required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    return parser


def _read_owned_regular(
    path: Path,
    *,
    maximum_bytes: int,
    subject: str,
) -> bytes:
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
            or not 1 <= opened.st_size <= maximum_bytes
        ):
            raise OSError(f"unsafe {subject}")
        payload = b""
        while len(payload) < opened.st_size:
            chunk = os.read(descriptor, opened.st_size - len(payload))
            if not chunk:
                raise OSError(f"{subject} changed while opening")
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
            raise OSError(f"{subject} changed while reading")
    except OSError:
        raise BattleScenarioSourceInventoryError(f"{subject} cannot be authenticated") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return payload


def _load_catalog(
    path: Path,
    *,
    expected_catalog_sha256: str,
    registry_source_commit: str,
    expected_registry_sha256: str,
) -> tuple[GoalManagerContextCatalog, GoalManagerCollectionRegistry]:
    try:
        payload = _read_owned_regular(
            path,
            maximum_bytes=_MAXIMUM_CATALOG_BYTES,
            subject="context catalog",
        )
        registry = load_committed_goal_manager_registry_at_revision(
            PROJECT_ROOT,
            registry_source_commit,
        )
    except (BattleScenarioSourceInventoryError, GoalManagerProtocolError):
        raise BattleScenarioSourceInventoryError(
            "historical battle source registry is unavailable"
        ) from None
    if (
        hashlib.sha256(payload).hexdigest() != expected_catalog_sha256
        or registry.registry_sha256 != expected_registry_sha256
    ):
        raise BattleScenarioSourceInventoryError("historical battle source provenance differs")
    try:
        return parse_goal_manager_context_catalog(payload, registry), registry
    except GoalManagerContextCatalogError as error:
        raise BattleScenarioSourceInventoryError(str(error)) from None


def _require_state_bank(path: Path) -> Path:
    try:
        resolved = path.resolve(strict=True)
        observed = resolved.stat()
    except OSError:
        raise BattleScenarioSourceInventoryError("catalog state bank is unavailable") from None
    if not stat.S_ISDIR(observed.st_mode) or observed.st_uid != os.getuid():
        raise BattleScenarioSourceInventoryError("catalog state bank cannot be authenticated")
    return resolved


def _open_all_catalog_train_roots(
    state_bank: Path,
    *,
    catalog: GoalManagerContextCatalog,
    registry: GoalManagerCollectionRegistry,
    partition: ScenarioPartition = ScenarioPartition.TRAIN,
) -> _CatalogTrainRootScan:
    if partition not in {ScenarioPartition.TRAIN, ScenarioPartition.DEVELOPMENT}:
        raise BattleScenarioSourceInventoryError("catalog partition is unsupported")
    registry_partition = (
        "train" if partition is ScenarioPartition.TRAIN else "validation"
    )
    partition_entries = []
    for entry in catalog.entries:
        assignment = registry.assignment(entry.slot_id)
        if assignment.partition != registry_partition:
            continue
        partition_entries.append(entry)
    expected_by_state = {entry.state_sha256: entry for entry in partition_entries}
    if len(expected_by_state) != len(partition_entries):
        raise BattleScenarioSourceInventoryError(
            "catalog partition root inventory is not independently identifiable"
        )

    matched_bytes: dict[str, bytes] = {}
    state_files_hashed = 0
    matching_state_file_copies = 0
    try:
        state_paths = tuple(sorted(state_bank.rglob("*.state")))
    except OSError:
        raise BattleScenarioSourceInventoryError(
            "catalog state bank cannot be enumerated"
        ) from None
    for state_path in state_paths:
        state_bytes = _read_owned_regular(
            state_path,
            maximum_bytes=_MAXIMUM_STATE_BYTES,
            subject="retained state bank file",
        )
        state_files_hashed += 1
        state_sha256 = hashlib.sha256(state_bytes).hexdigest()
        if state_sha256 not in expected_by_state:
            continue
        matching_state_file_copies += 1
        matched_bytes.setdefault(state_sha256, state_bytes)

    roots: list[_CatalogTrainRoot] = []
    for entry in partition_entries:
        state_sha256 = entry.state_sha256
        if state_sha256 not in matched_bytes:
            continue
        try:
            binding = authenticate_battle_scenario_source_binding(
                state_sha256,
                expected_partition=partition,
                catalog=catalog,
                registry=registry,
            )
        except BattleOutcomeCaptureAuthenticationError as error:
            raise BattleScenarioSourceInventoryError(str(error)) from None
        roots.append(
            _CatalogTrainRoot(
                binding=binding,
                state_bytes=matched_bytes[state_sha256],
            )
        )
    if (
        len({root.binding.source_slot_id for root in roots}) != len(roots)
        or len({root.binding.source_state_sha256 for root in roots}) != len(roots)
        or len({root.binding.root_consumption_sha256 for root in roots}) != len(roots)
    ):
        raise BattleScenarioSourceInventoryError(
            "catalog partition root inventory is not independently identifiable"
        )
    return _CatalogTrainRootScan(
        roots=tuple(roots),
        state_files_hashed=state_files_hashed,
        matching_state_file_copies=matching_state_file_copies,
        missing_catalog_train_roots=len(partition_entries) - len(roots),
    )


def _cross_partition_collision_counts(
    catalog: GoalManagerContextCatalog,
    registry: GoalManagerCollectionRegistry,
) -> dict[str, int]:
    identities: dict[str, dict[str, set[str]]] = {
        partition: {
            "states": set(),
            "assignments": set(),
            "contexts": set(),
            "lineages": set(),
        }
        for partition in ("train", "validation")
    }
    for entry in catalog.entries:
        assignment = registry.assignment(entry.slot_id)
        if assignment.partition not in identities:
            continue
        current = identities[assignment.partition]
        current["states"].add(entry.state_sha256)
        current["assignments"].add(entry.assignment_id)
        current["contexts"].add(entry.context_id)
        current["lineages"].add(assignment.root_lineage_id)
    return {
        name: len(identities["train"][name] & identities["validation"][name])
        for name in ("states", "assignments", "contexts", "lineages")
    }


def _map_label(map_id: object) -> str:
    if isinstance(map_id, bool) or not isinstance(map_id, int):
        return "invalid_map"
    try:
        return MapId(map_id).name.lower()
    except ValueError:
        return f"map_{map_id:02x}"


def _load_attempted_source_exclusions(
    plan_path: Path,
    journal_path: Path,
    *,
    expected_plan_sha256: str,
    expected_journal_sha256: str,
) -> frozenset[str]:
    plan_payload = _read_owned_regular(
        plan_path,
        maximum_bytes=8 * 1024 * 1024,
        subject="excluded materialization plan",
    )
    journal_payload = _read_owned_regular(
        journal_path,
        maximum_bytes=2 * 1024 * 1024,
        subject="excluded materialization run journal",
    )
    if (
        hashlib.sha256(plan_payload).hexdigest() != expected_plan_sha256
        or hashlib.sha256(journal_payload).hexdigest() != expected_journal_sha256
    ):
        raise BattleScenarioSourceInventoryError(
            "excluded materialization evidence identity differs"
        )
    try:
        plan = _parse_materialization_plan(plan_payload)
        journal = parse_battle_scenario_materialization_run(journal_payload)
        require_battle_scenario_materialization_run_matches_plan(
            journal,
            plan,
            journal.identity,
        )
    except (
        BattleScenarioMaterializationPlanError,
        BattleScenarioMaterializationRunError,
    ) as error:
        raise BattleScenarioSourceInventoryError(str(error)) from None
    if any(entry.status == PENDING for entry in journal.entries):
        raise BattleScenarioSourceInventoryError(
            "excluded materialization plan is not fully attempted"
        )
    return _attempted_source_state_sha256(plan, journal)


def _parse_materialization_plan(payload: bytes) -> BattleScenarioMaterializationPlanLike:
    try:
        return parse_battle_scenario_materialization_plan(payload)
    except BattleScenarioMaterializationPlanError:
        pass
    try:
        return parse_battle_scenario_materialization_plan_v2(payload)
    except BattleScenarioMaterializationPlanV2Error:
        pass
    try:
        return parse_battle_scenario_materialization_completion_plan(payload)
    except BattleScenarioMaterializationPlanV2Error as error:
        raise BattleScenarioSourceInventoryError(str(error)) from None


def _attempted_source_state_sha256(
    plan: BattleScenarioMaterializationPlanLike,
    journal: BattleScenarioMaterializationRunJournal,
) -> frozenset[str]:
    require_battle_scenario_materialization_run_matches_plan(
        journal,
        plan,
        journal.identity,
    )
    attempted = {
        assignment.candidate.source.source_state_sha256
        for assignment, entry in zip(plan.assignments, journal.entries, strict=True)
        if entry.status != PENDING
    }
    return frozenset(attempted)


def _supported_party_slot_available(raw: RawGameState, venue_id: str | None) -> bool:
    return _party_slot_available(raw, venue_id, after_resource_restoration=False)


def _refreshable_party_slot_available(raw: RawGameState, venue_id: str | None) -> bool:
    return _party_slot_available(raw, venue_id, after_resource_restoration=True)


def _supported_reachable_venue_ids(
    raw: RawGameState,
    venue_ids: tuple[str, ...],
) -> tuple[str, ...]:
    """Keep only reachable venues that preserve the exact live move surface."""

    if not isinstance(venue_ids, tuple):
        raise TypeError("reachable venue identifiers must be a tuple")
    return tuple(
        venue_id
        for venue_id in venue_ids
        if _supported_party_slot_available(raw, venue_id)
    )


def _party_slot_available(
    raw: RawGameState,
    venue_id: str | None,
    *,
    after_resource_restoration: bool,
) -> bool:
    if venue_id is None:
        return False
    venue = {
        MANSION_VENUE_ID: MANSION_TRAINING_VENUE,
        ROUTE_11_VENUE_ID: ROUTE_11_TRAINING_VENUE,
        "digletts_cave": DIGLETTS_CAVE_TRAINING_VENUE,
    }.get(venue_id)
    if venue is None:
        return False
    party_count = getattr(raw, "party_count", None)
    species = getattr(raw, "party_species_ids", None)
    levels = getattr(raw, "party_levels", None)
    hp = getattr(raw, "party_hp", None)
    maximum_hp = getattr(raw, "party_max_hp", None)
    status = getattr(raw, "party_status", None)
    moves = getattr(raw, "party_moves", None)
    pp = getattr(raw, "party_pp", None)
    if (
        type(party_count) is not int  # noqa: E721
        or not 1 <= party_count <= 6
        or any(
            not isinstance(value, tuple)
            for value in (species, levels, hp, maximum_hp, status, moves, pp)
        )
    ):
        return False
    typed_species = cast(tuple[int, ...], species)
    typed_levels = cast(tuple[int, ...], levels)
    typed_hp = cast(tuple[int, ...], hp)
    typed_maximum_hp = cast(tuple[int, ...], maximum_hp)
    typed_status = cast(tuple[int, ...], status)
    typed_moves = cast(tuple[tuple[int, ...], ...], moves)
    typed_pp = cast(tuple[tuple[int, ...], ...], pp)
    if any(
        len(value) != party_count
        for value in (
            typed_species,
            typed_levels,
            typed_hp,
            typed_maximum_hp,
            typed_status,
            typed_moves,
            typed_pp,
        )
    ):
        return False
    rare_maximum = venue.band.rare_maximum_encounter_level
    minimum = venue.band.minimum_encounter_level
    if type(rare_maximum) is not int or type(minimum) is not int:  # noqa: E721
        return False
    minimum_level = rare_maximum - MAXIMUM_LEVEL_GAP
    maximum_level = minimum + MAXIMUM_LEVEL_GAP
    try:
        return any(
            type(current_hp) is int  # noqa: E721
            and current_hp > 0
            and type(level) is int  # noqa: E721
            and minimum_level <= level <= maximum_level
            and (
                red_battle_refreshable_supported_move_count(move_ids)
                if after_resource_restoration
                else red_battle_supported_move_count(move_ids, current_pp)
            )
            >= 2
            for level, current_hp, move_ids, current_pp in zip(
                typed_levels,
                typed_hp,
                typed_moves,
                typed_pp,
                strict=True,
            )
        )
    except RedBattleScenarioError:
        return False


def _observe_root(
    root: _CatalogTrainRoot,
    *,
    emulator: PyBoyAdapter,
    registry_path: Path,
) -> _ObservedTrainRoot:
    available = root_claim_is_available(
        registry_path,
        root.binding.root_consumption_sha256,
    )
    emulator.load_state_bytes(root.state_bytes)
    reader = PokemonRedStateReader(emulator)
    raw = reader.read()
    map_label = _map_label(raw.map_id)
    safe_nonbattle = raw.battle_state == 0
    living = any(hp > 0 for hp in (raw.party_hp or ()))
    last_blackout_map = reader.read_last_blackout_map()
    current_map_tileset = emulator.read_u8(RamAddress.CURRENT_MAP_TILESET)
    fly_relocation_ready = red_training_fly_available(raw)
    ground_relocation_ready = red_training_ground_transition_available(raw)
    route_11_relocation_ready = red_vermilion_training_transition_available(
        raw,
        last_blackout_map,
        current_map_tileset,
    )
    try:
        source_venue = battle_scenario_source_venue(
            raw,
            last_blackout_map=last_blackout_map,
            current_map_tileset=current_map_tileset,
        )
        venue_id = source_venue.venue_id
        relocation_required = source_venue.relocation_required
    except BattleScenarioSourceVenueError:
        venue_id = None
        relocation_required = False
    try:
        reachable_venues = battle_scenario_reachable_venues(
            raw,
            last_blackout_map=last_blackout_map,
            current_map_tileset=current_map_tileset,
        )
    except BattleScenarioSourceVenueError:
        reachable_venues = ()
    reachable_venue_ids = tuple(item.venue_id for item in reachable_venues)
    eligible_venue_ids = _supported_reachable_venue_ids(
        raw,
        reachable_venue_ids,
    )
    supported_party_slot = _supported_party_slot_available(raw, venue_id)
    refreshable_party_slot = _refreshable_party_slot_available(raw, venue_id)
    if emulator.frame_count != 0 or emulator.pressed_buttons:
        raise BattleScenarioSourceInventoryError(
            "action-free battle source observation crossed the controller boundary"
        )
    return _ObservedTrainRoot(
        map_label=map_label,
        venue_id=venue_id,
        relocation_required=relocation_required,
        fly_relocation_ready=fly_relocation_ready,
        ground_relocation_ready=ground_relocation_ready,
        route_11_relocation_ready=route_11_relocation_ready,
        claim_available=available,
        safe_nonbattle=safe_nonbattle,
        living_party_member_available=living,
        supported_party_slot_available=supported_party_slot,
        refreshable_party_slot_available=refreshable_party_slot,
        reachable_venue_ids=reachable_venue_ids,
        eligible_venue_ids=eligible_venue_ids,
    )


def _venue_capacity(
    venue_counts: Counter[str],
    *,
    required_contexts: int = FRESH_TRAIN_CONTEXTS,
) -> bool:
    if type(required_contexts) is not int or required_contexts < 1:  # noqa: E721
        raise BattleScenarioSourceInventoryError(
            "required partition context count differs"
        )
    positive = tuple(count for count in venue_counts.values() if count > 0)
    return (
        len(positive) >= MINIMUM_DISTINCT_VENUES
        and sum(min(count, MAXIMUM_SINGLE_BUCKET_CONTEXTS) for count in positive)
        >= required_contexts
    )


def _available_unsupported_capability_counts(
    observed: tuple[_ObservedTrainRoot, ...],
    capability: str,
) -> Counter[str]:
    if capability not in {
        "fly_relocation_ready",
        "ground_relocation_ready",
        "route_11_relocation_ready",
    }:
        raise BattleScenarioSourceInventoryError("unsupported relocation capability inventory")
    return Counter(
        item.map_label
        for item in observed
        if item.claim_available
        and item.safe_nonbattle
        and item.living_party_member_available
        and item.venue_id is None
        and bool(getattr(item, capability))
    )


def _run(args: argparse.Namespace) -> dict[str, object]:
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    if source.git_commit is None:  # pragma: no cover - clean source establishes this
        raise AssertionError("clean source identity lacks a commit")

    try:
        partition = ScenarioPartition(args.partition)
    except ValueError:
        raise BattleScenarioSourceInventoryError("catalog partition is unsupported") from None
    if partition not in {ScenarioPartition.TRAIN, ScenarioPartition.DEVELOPMENT}:
        raise BattleScenarioSourceInventoryError("catalog partition is unsupported")
    required_contexts = (
        FRESH_TRAIN_CONTEXTS
        if partition is ScenarioPartition.TRAIN
        else DEVELOPMENT_CONTEXTS
    )

    catalog, registry = _load_catalog(
        args.context_catalog,
        expected_catalog_sha256=args.expected_context_catalog_sha256,
        registry_source_commit=args.registry_source_commit,
        expected_registry_sha256=args.expected_registry_sha256,
    )
    cross_partition_collisions = _cross_partition_collision_counts(catalog, registry)
    scan = _open_all_catalog_train_roots(
        _require_state_bank(args.state_bank),
        catalog=catalog,
        registry=registry,
        partition=partition,
    )
    attempted_sources = _load_attempted_source_exclusions(
        args.excluded_plan,
        args.excluded_run_journal,
        expected_plan_sha256=args.expected_excluded_plan_sha256,
        expected_journal_sha256=args.expected_excluded_run_journal_sha256,
    )
    successor_roots = tuple(
        root for root in scan.roots if root.binding.source_state_sha256 not in attempted_sources
    )
    excluded_retained_roots = len(scan.roots) - len(successor_roots)
    registry_path = open_fixed_account_claim_registry()
    rom_path = resolve_rom_path(args.rom)
    try:
        with (
            fixed_account_claim_registry_lease(registry_path, exclusive=False),
            PyBoyAdapter(rom_path) as emulator,
        ):
            observed = tuple(
                _observe_root(
                    root,
                    emulator=emulator,
                    registry_path=registry_path,
                )
                for root in successor_roots
            )
            if emulator.frame_count != 0 or emulator.pressed_buttons:
                raise BattleScenarioSourceInventoryError(
                    "action-free inventory crossed the controller boundary"
                )
    except FreshCompositionQualificationError as error:
        raise BattleScenarioSourceInventoryError(str(error)) from None

    venue_counts = Counter(
        item.venue_id
        for item in observed
        if item.materialization_eligible and item.venue_id is not None
    )
    resource_conditioning_venue_counts = Counter(
        item.venue_id
        for item in observed
        if item.resource_conditioning_eligible and item.venue_id is not None
    )
    reachable_venue_eligibility_counts = Counter(
        venue_id
        for item in observed
        if item.claim_available
        and item.safe_nonbattle
        and item.living_party_member_available
        for venue_id in item.eligible_venue_ids
    )
    allocation_roots = tuple(
        ReachableVenueRoot(
            root.binding.root_consumption_sha256,
            item.eligible_venue_ids,
        )
        for root, item in zip(successor_roots, observed, strict=True)
        if item.reachable_venue_allocation_eligible
    )
    allocation = allocate_reachable_venue_roots(
        allocation_roots,
        required_roots=required_contexts,
        minimum_distinct_venues=MINIMUM_DISTINCT_VENUES,
        maximum_roots_per_venue=MAXIMUM_SINGLE_BUCKET_CONTEXTS,
    )
    loaded_map_counts = Counter(item.map_label for item in observed)
    claim_available_map_counts = Counter(
        item.map_label for item in observed if item.claim_available
    )
    available_unsupported_map_counts = Counter(
        item.map_label
        for item in observed
        if item.claim_available
        and item.safe_nonbattle
        and item.living_party_member_available
        and item.venue_id is None
    )
    eligible_relocation_map_counts = Counter(
        item.map_label
        for item in observed
        if item.materialization_eligible and item.relocation_required
    )
    unsupported_fly_ready_map_counts = _available_unsupported_capability_counts(
        observed,
        "fly_relocation_ready",
    )
    unsupported_ground_ready_map_counts = _available_unsupported_capability_counts(
        observed,
        "ground_relocation_ready",
    )
    unsupported_route_11_ready_map_counts = _available_unsupported_capability_counts(
        observed,
        "route_11_relocation_ready",
    )
    available_count = sum(item.claim_available for item in observed)
    eligible_count = sum(item.materialization_eligible for item in observed)
    return {
        "schema": "pokemon.red-battle-scenario-partition-venue-inventory.v1",
        "status": (
            "stopped_cross_partition_identity_collision"
            if any(cross_partition_collisions.values())
            else (
                "prospective_reachable_venue_allocation_capacity_passed"
                if allocation.capacity_met
                else "stopped_insufficient_reachable_venue_allocation_capacity"
            )
        ),
        "source_commit": source.git_commit,
        "partition": partition.value,
        "context_catalog_sha256": catalog.catalog_sha256,
        "registry_sha256": registry.registry_sha256,
        "registry_source_commit": registry.execution.source_commit,
        "cross_partition_collision_counts": cross_partition_collisions,
        "catalog_partition_roots": len(scan.roots) + scan.missing_catalog_train_roots,
        "retained_state_files_hashed": scan.state_files_hashed,
        "matching_state_file_copies": scan.matching_state_file_copies,
        "missing_catalog_partition_roots": scan.missing_catalog_train_roots,
        "retained_catalog_partition_roots": len(scan.roots),
        "attempted_source_roots_declared": len(attempted_sources),
        "attempted_source_roots_excluded": excluded_retained_roots,
        "successor_candidate_partition_roots": len(successor_roots),
        "unique_catalog_partition_states": len(
            {root.binding.source_state_sha256 for root in scan.roots}
        ),
        "claim_available_partition_roots": available_count,
        "materialization_eligible_partition_roots": eligible_count,
        "materialization_eligible_venue_counts": dict(sorted(venue_counts.items())),
        "resource_conditioning_eligible_partition_roots": sum(
            item.resource_conditioning_eligible for item in observed
        ),
        "resource_conditioning_eligible_venue_counts": dict(
            sorted(resource_conditioning_venue_counts.items())
        ),
        "reachable_venue_allocation_candidate_partition_roots": len(allocation_roots),
        "reachable_venue_eligibility_counts": dict(
            sorted(reachable_venue_eligibility_counts.items())
        ),
        "reachable_venue_allocation_assigned_partition_roots": allocation.assigned_roots,
        "reachable_venue_allocation_distinct_venues": allocation.distinct_venues,
        "reachable_venue_allocation_venue_counts": allocation.venue_counts,
        "loaded_map_counts": dict(sorted(loaded_map_counts.items())),
        "claim_available_map_counts": dict(sorted(claim_available_map_counts.items())),
        "available_unsupported_map_counts": dict(sorted(available_unsupported_map_counts.items())),
        "materialization_eligible_relocation_map_counts": dict(
            sorted(eligible_relocation_map_counts.items())
        ),
        "available_unsupported_fly_ready_map_counts": dict(
            sorted(unsupported_fly_ready_map_counts.items())
        ),
        "available_unsupported_ground_ready_map_counts": dict(
            sorted(unsupported_ground_ready_map_counts.items())
        ),
        "available_unsupported_route_11_ready_map_counts": dict(
            sorted(unsupported_route_11_ready_map_counts.items())
        ),
        "required_partition_contexts": required_contexts,
        "minimum_distinct_venues": MINIMUM_DISTINCT_VENUES,
        "maximum_single_venue_contexts": MAXIMUM_SINGLE_BUCKET_CONTEXTS,
        "prospective_partition_venue_capacity": _venue_capacity(
            venue_counts,
            required_contexts=required_contexts,
        ),
        "prospective_resource_conditioning_capacity": _venue_capacity(
            resource_conditioning_venue_counts,
            required_contexts=required_contexts,
        ),
        "prospective_reachable_venue_allocation_capacity": (
            allocation.capacity_met
            and not any(cross_partition_collisions.values())
        ),
        "safe_nonbattle_roots": sum(item.safe_nonbattle for item in observed),
        "living_party_roots": sum(item.living_party_member_available for item in observed),
        "supported_party_slot_roots": sum(item.supported_party_slot_available for item in observed),
        "refreshable_party_slot_roots": sum(
            item.refreshable_party_slot_available for item in observed
        ),
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
        "private_path_fields": 0,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    print(json.dumps(_run(args), ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
