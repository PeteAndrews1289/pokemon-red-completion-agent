#!/usr/bin/env python3
"""Create one catalog-authenticated train battle boundary without choosing a move."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.battle_outcome_capture_authentication import (  # noqa: E402
    BattleOutcomeCaptureAuthenticationError,
    BattleScenarioSourceBinding,
    authenticate_battle_scenario_source_binding,
)
from pokemon_red_completion.battle_recovery import (  # noqa: E402
    switch_active_battler,
)
from pokemon_red_completion.battle_runtime import (  # noqa: E402
    BattlePolicyBoundary,
    advance_battle_to_policy_boundary,
)
from pokemon_red_completion.battle_scenario_capture import (  # noqa: E402
    build_battle_scenario_capture_payload,
)
from pokemon_red_completion.battle_scenario_source_venue import (  # noqa: E402
    BattleScenarioSourceVenue,
    BattleScenarioSourceVenueError,
    battle_scenario_reachable_venues,
    battle_scenario_source_venue,
)
from pokemon_red_completion.battle_source_conditioning import (  # noqa: E402
    BATTLE_RESOURCE_CONDITIONING_V1,
)
from pokemon_red_completion.blaine import (  # noqa: E402
    DIGLETTS_CAVE_TRAINING_VENUE,
    MANSION_TRAINING_VENUE,
    ROUTE_11_TRAINING_VENUE,
    red_training_venues_with_ground_transition,
)
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING  # noqa: E402
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.executor import CountingExecutor, FrameSafeExecutor  # noqa: E402
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
    BattleMenuPhase,
    MapId,
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    canonical_sha256,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_battle_scenario import (  # noqa: E402
    PreparedRedBattleScenario,
    prepare_red_battle_scenario,
)
from pokemon_red_completion.red_battle_source_conditioning import (  # noqa: E402
    red_battle_party_identity,
)
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder  # noqa: E402
from pokemon_red_completion.rom import resolve_rom_path  # noqa: E402
from pokemon_red_completion.route_executor import RouteExecutionError  # noqa: E402
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402
from pokemon_red_completion.training_venue import TrainingVenue  # noqa: E402


class BattleScenarioMaterializationError(RuntimeError):
    """Raised before a private capture can be authenticated."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str = "materialization_preflight_failed",
        diagnostics: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.diagnostics = dict(
            diagnostics or {"failure_layer": "materialization_stage"}
        )


_MAXIMUM_BATTLE_STATE_BYTES = 64 * 1024 * 1024
_MAXIMUM_CONTEXT_CATALOG_BYTES = 4 * 1024 * 1024
_FAILURE_SCHEMA = "pokemon-private-battle-scenario-materialization-failure-v2"


@dataclass(frozen=True, slots=True)
class MaterializedBattleBoundary:
    state: RawGameState
    prepared: PreparedRedBattleScenario
    encounter_steps: int
    encounter_walk_calls: int
    boundary: BattlePolicyBoundary
    switch_actions: int


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-state", type=Path, required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--expected-context-catalog-sha256", required=True)
    parser.add_argument("--registry-source-commit", required=True)
    parser.add_argument("--expected-registry-sha256", required=True)
    parser.add_argument(
        "--party-slot",
        type=int,
        choices=range(1, 7),
        default=1,
        help="one-based living party slot prospectively chosen for the capture",
    )
    parser.add_argument(
        "--expected-reachable-venue-id",
        default=None,
        help="plan-bound V2 venue edge; rederived from the source before input",
    )
    parser.add_argument("--capture-id", required=True)
    parser.add_argument("--out-state", type=Path, required=True)
    parser.add_argument("--out-manifest", type=Path, default=None)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--maximum-encounter-steps", type=int, default=512)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--speed", type=int, choices=(1, 2, 4), default=None)
    return parser


def _private_new_output(destination: Path, *, rom_path: Path) -> Path:
    resolved = destination.resolve()
    if resolved.is_relative_to(PROJECT_ROOT.resolve()):
        raise BattleScenarioMaterializationError("battle capture must remain private")
    if resolved.parent == rom_path.resolve().parent:
        raise BattleScenarioMaterializationError("battle capture cannot be written beside the ROM")
    if not resolved.parent.is_dir():
        raise BattleScenarioMaterializationError("battle capture parent does not exist")
    if resolved.exists():
        raise BattleScenarioMaterializationError("battle capture output already exists")
    return resolved


def _read_owned_regular_input(
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
    except OSError:
        raise BattleScenarioMaterializationError(f"{subject} cannot be authenticated") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return payload


def _read_source(path: Path) -> bytes:
    return _read_owned_regular_input(
        path,
        maximum_bytes=_MAXIMUM_BATTLE_STATE_BYTES,
        subject="source state",
    )


def _load_source_binding(
    source_bytes: bytes,
    *,
    catalog_path: Path,
    expected_catalog_sha256: str,
    registry_source_commit: str,
    expected_registry_sha256: str,
) -> tuple[
    BattleScenarioSourceBinding,
    GoalManagerContextCatalog,
    GoalManagerCollectionRegistry,
]:
    """Authenticate bytes against the historical catalog; derive all labels."""

    try:
        catalog_payload = _read_owned_regular_input(
            catalog_path,
            maximum_bytes=_MAXIMUM_CONTEXT_CATALOG_BYTES,
            subject="context catalog",
        )
        registry = load_committed_goal_manager_registry_at_revision(
            PROJECT_ROOT,
            registry_source_commit,
        )
    except (BattleScenarioMaterializationError, GoalManagerProtocolError):
        raise BattleScenarioMaterializationError(
            "historical battle source registry is unavailable"
        ) from None
    if (
        hashlib.sha256(catalog_payload).hexdigest() != expected_catalog_sha256
        or registry.registry_sha256 != expected_registry_sha256
    ):
        raise BattleScenarioMaterializationError("historical battle source provenance differs")
    try:
        catalog = parse_goal_manager_context_catalog(catalog_payload, registry)
    except GoalManagerContextCatalogError as error:
        raise BattleScenarioMaterializationError(str(error)) from None
    bindings = []
    for partition in (ScenarioPartition.TRAIN, ScenarioPartition.DEVELOPMENT):
        try:
            bindings.append(
                authenticate_battle_scenario_source_binding(
                    hashlib.sha256(source_bytes).hexdigest(),
                    expected_partition=partition,
                    catalog=catalog,
                    registry=registry,
                )
            )
        except BattleOutcomeCaptureAuthenticationError:
            continue
    if len(bindings) != 1:
        raise BattleScenarioMaterializationError(
            "historical battle source partition cannot be derived"
        )
    binding = bindings[0]
    return binding, catalog, registry


def _require_unconsumed_source_root(binding: BattleScenarioSourceBinding) -> None:
    """Reject a consumed upstream root without reserving or claiming it.

    This is deliberately a non-authoritative preflight.  The later frozen
    outcome campaign remains responsible for the atomic logical-plus-physical
    claim before any candidate action.
    """

    try:
        registry_path = open_fixed_account_claim_registry()
        with fixed_account_claim_registry_lease(registry_path, exclusive=False):
            available = root_claim_is_available(
                registry_path,
                binding.root_consumption_sha256,
            )
    except FreshCompositionQualificationError as error:
        raise BattleScenarioMaterializationError(str(error)) from None
    if not available:
        raise BattleScenarioMaterializationError("battle source upstream root is already consumed")


def _require_distinct_outputs(state: Path, manifest: Path) -> None:
    if state == manifest:
        raise BattleScenarioMaterializationError(
            "battle state and manifest outputs must be distinct"
        )


def _fsync_existing_private_output(path: Path) -> bytes:
    """Authenticate, privatize, and durably retain an emulator-created file."""

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
            or not 1 <= opened.st_size <= _MAXIMUM_BATTLE_STATE_BYTES
        ):
            raise OSError("unsafe materialized output")
        os.fchmod(descriptor, 0o600)
        payload = b""
        while len(payload) < opened.st_size:
            chunk = os.read(descriptor, opened.st_size - len(payload))
            if not chunk:
                raise OSError("materialized output changed while opening")
            payload += chunk
        os.fsync(descriptor)
    except OSError:
        raise BattleScenarioMaterializationError(
            "battle state could not be retained durably"
        ) from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    _fsync_directory(path.parent)
    return payload


def _write_private_output(destination: Path, payload: bytes) -> None:
    """Publish one new owner-only file and its directory entry durably."""

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    created = False
    failed = False
    try:
        descriptor = os.open(destination, flags, 0o600)
        created = True
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("materialized output write made no progress")
            offset += written
        os.fsync(descriptor)
    except OSError:
        failed = True
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                failed = True
    if failed:
        if created:
            with suppress(OSError):
                destination.unlink()
            with suppress(BattleScenarioMaterializationError):
                _fsync_directory(destination.parent)
        raise BattleScenarioMaterializationError(
            "battle manifest could not be retained durably"
        ) from None
    _fsync_directory(destination.parent)


def _fsync_directory(directory: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_DIRECTORY", 0)
    descriptor = -1
    try:
        descriptor = os.open(directory, flags)
        os.fsync(descriptor)
    except OSError:
        raise BattleScenarioMaterializationError(
            "battle capture directory could not be retained durably"
        ) from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _venue_for_source_location(
    source_location: str,
    *,
    rom_bytes: bytes | None = None,
) -> TrainingVenue:
    if source_location in {
        "lavender_center_route_11",
        "vermilion_transition_route_11",
    }:
        if not isinstance(rom_bytes, bytes) or not rom_bytes:
            raise BattleScenarioMaterializationError(
                "Lavender ground relocation requires immutable ROM bytes"
            )
        return red_training_venues_with_ground_transition(rom_bytes)[0]
    venues = {
        "route_11": ROUTE_11_TRAINING_VENUE,
        "digletts_cave": DIGLETTS_CAVE_TRAINING_VENUE,
        "mansion": MANSION_TRAINING_VENUE,
        "cinnabar_center": MANSION_TRAINING_VENUE,
        "celadon_center_route_11": ROUTE_11_TRAINING_VENUE,
    }
    try:
        return venues[source_location]
    except KeyError:
        raise BattleScenarioMaterializationError(
            "source location has no measured battle venue"
        ) from None


def _source_location_for_state(
    raw: RawGameState,
    *,
    last_blackout_map: int | None = None,
    current_map_tileset: int | None = None,
) -> str:
    try:
        return battle_scenario_source_venue(
            raw,
            last_blackout_map=last_blackout_map,
            current_map_tileset=current_map_tileset,
        ).source_location
    except BattleScenarioSourceVenueError as error:
        raise BattleScenarioMaterializationError(str(error)) from None


def _selected_reachable_venue_for_state(
    raw: RawGameState,
    expected_venue_id: str,
    *,
    last_blackout_map: int,
    current_map_tileset: int,
    rom_bytes: bytes,
) -> tuple[BattleScenarioSourceVenue, TrainingVenue]:
    """Reauthenticate one plan-bound reachable edge without controller input."""

    if not isinstance(expected_venue_id, str) or not expected_venue_id:
        raise BattleScenarioMaterializationError(
            "selected reachable venue identity differs"
        )
    try:
        reachable = battle_scenario_reachable_venues(
            raw,
            last_blackout_map=last_blackout_map,
            current_map_tileset=current_map_tileset,
        )
    except BattleScenarioSourceVenueError as error:
        raise BattleScenarioMaterializationError(str(error)) from None
    matching = tuple(item for item in reachable if item.venue_id == expected_venue_id)
    if len(matching) != 1:
        raise BattleScenarioMaterializationError(
            "selected reachable venue cannot be reauthenticated"
        )
    edge = matching[0]
    venues = {
        "digletts_cave": DIGLETTS_CAVE_TRAINING_VENUE,
        "pokemon_mansion_1f": MANSION_TRAINING_VENUE,
        "route_11": ROUTE_11_TRAINING_VENUE,
    }
    try:
        venue = venues[edge.venue_id]
    except KeyError:
        raise BattleScenarioMaterializationError(
            "selected reachable venue has no measured battle venue"
        ) from None
    if edge.relocation_required and edge.venue_id in {"route_11", "digletts_cave"}:
        ground_venues = {
            item.band.area_id: item
            for item in red_training_venues_with_ground_transition(rom_bytes)
        }
        venue = ground_venues[edge.venue_id]
    if venue.map_id != edge.encounter_map or venue.band.area_id != edge.venue_id:
        raise BattleScenarioMaterializationError(
            "selected reachable venue mechanics differ"
        )
    return edge, venue


def _require_living_party_slot(raw: object, one_based_party_slot: int) -> int:
    if type(one_based_party_slot) is not int or not 1 <= one_based_party_slot <= 6:  # noqa: E721
        raise BattleScenarioMaterializationError("party slot must be between one and six")
    party_count = getattr(raw, "party_count", None)
    party_hp = getattr(raw, "party_hp", None)
    party_index = one_based_party_slot - 1
    if (
        type(party_count) is not int  # noqa: E721
        or not isinstance(party_hp, tuple)
        or party_count != len(party_hp)
        or party_index >= party_count
        or type(party_hp[party_index]) is not int  # noqa: E721
        or party_hp[party_index] <= 0
    ):
        raise BattleScenarioMaterializationError(
            "prospectively selected party slot is not a living party member"
        )
    return party_index


def _materialize_loaded_battle_boundary(
    reader: PokemonRedStateReader,
    emulator: PyBoyAdapter,
    controller: FrameSafeExecutor,
    actions: CountingExecutor,
    venue: TrainingVenue,
    *,
    one_based_party_slot: int,
    maximum_encounter_steps: int,
) -> MaterializedBattleBoundary:
    venue_boundary = reader.read()
    if venue_boundary.map_id != venue.map_id or venue_boundary.battle_state != 0:
        raise BattleScenarioMaterializationError(
            "source did not reach its measured encounter venue"
        )
    party_index = _require_living_party_slot(
        venue_boundary,
        one_based_party_slot,
    )
    encounter_steps = 0
    encounter_walk_calls = 0
    walk_to_grass = venue.fresh_walk_to_grass()
    while reader.read().battle_state == 0:
        encounter_walk_calls += 1
        if encounter_walk_calls > maximum_encounter_steps * 4:
            raise BattleScenarioMaterializationError(
                "wild encounter walker made no bounded progress"
            )
        encounter_steps += walk_to_grass(actions, reader, emulator)
        if encounter_steps > maximum_encounter_steps:
            raise BattleScenarioMaterializationError(
                "wild encounter did not begin inside the configured bound"
            )
    boundary = advance_battle_to_policy_boundary(
        reader,
        controller,
        expected_map=venue.map_id,
        expected_battle_state=1,
        timing=venue.battle_timing,
        label="battle scenario materialization",
    )
    switch_action_start = actions.actions_executed
    switch_active_battler(
        actions,
        reader,
        emulator,
        party_index,
        expected_battle_state=1,
        label="battle scenario materialization",
    )
    switch_actions = actions.actions_executed - switch_action_start
    capture_boundary = reader.read()
    menu = reader.read_battle_menu_state(capture_boundary)
    if menu.phase is not BattleMenuPhase.MAIN:
        raise BattleScenarioMaterializationError(
            "materialized capture is not at the MAIN policy boundary"
        )
    if (
        capture_boundary.map_id != venue.map_id
        or capture_boundary.battle_state != 1
        or capture_boundary.active_party_index != party_index
        or (capture_boundary.battler_hp or 0) <= 0
    ):
        raise BattleScenarioMaterializationError(
            "materialized capture did not preserve its selected battle boundary"
        )
    prepared = prepare_red_battle_scenario(
        PokemonRedObservationEncoder.from_state_reader(reader),
        capture_boundary,
    )
    return MaterializedBattleBoundary(
        state=capture_boundary,
        prepared=prepared,
        encounter_steps=encounter_steps,
        encounter_walk_calls=encounter_walk_calls,
        boundary=boundary,
        switch_actions=switch_actions,
    )


def _prepare_source_venue(
    source_location: str,
    venue: TrainingVenue,
    actions: CountingExecutor,
    reader: PokemonRedStateReader,
    emulator: PyBoyAdapter,
    *,
    restore_battle_resources: bool = False,
) -> None:
    raw = reader.read()
    before_identity = None
    relocation_sources = {
        "cinnabar_center": MapId.CINNABAR_POKECENTER,
        "celadon_center_route_11": MapId.CELADON_POKECENTER,
        "lavender_center_route_11": MapId.LAVENDER_POKECENTER,
    }
    if source_location in relocation_sources:
        if raw.map_id != relocation_sources[source_location] or raw.battle_state != 0:
            raise BattleScenarioMaterializationError(
                "center source is not at the expected safe boundary"
            )
        before_identity = red_battle_party_identity(raw)
        venue.heal_and_return(actions, reader, emulator)
    elif source_location in {
        "vermilion_transition_route_11",
        "vermilion_transition_digletts_cave",
    }:
        if raw.battle_state != 0:
            raise BattleScenarioMaterializationError(
                "portable Route 11 source is not at a safe boundary"
            )
        before_identity = red_battle_party_identity(raw)
        venue.heal_and_return(actions, reader, emulator)
    elif restore_battle_resources:
        if raw.map_id != venue.map_id or raw.battle_state != 0:
            raise BattleScenarioMaterializationError(
                "direct resource-conditioning source is not at its venue boundary"
            )
        before_identity = red_battle_party_identity(raw)
        venue.heal_and_return(actions, reader, emulator)
    elif raw.map_id != venue.map_id or raw.battle_state != 0:
        raise BattleScenarioMaterializationError(
            "venue source is not at the expected safe boundary"
        )
    prepared = reader.read()
    if prepared.map_id != venue.map_id or prepared.battle_state != 0:
        raise BattleScenarioMaterializationError(
            "source did not reach its measured encounter venue"
        )
    if before_identity is not None:
        BATTLE_RESOURCE_CONDITIONING_V1.require_identity_preserved(
            before_identity,
            red_battle_party_identity(prepared),
        )


def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.speed is not None and not args.watch:
        raise BattleScenarioMaterializationError("--speed requires --watch")
    if args.maximum_encounter_steps < 1:
        raise BattleScenarioMaterializationError("--maximum-encounter-steps must be positive")
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    if source.git_commit is None:  # pragma: no cover - clean source establishes this
        raise AssertionError("clean source identity lacks a commit")

    rom_path = resolve_rom_path(args.rom)
    try:
        source_bytes = _read_source(args.source_state)
        source_binding, catalog, historical_registry = _load_source_binding(
            source_bytes,
            catalog_path=args.context_catalog,
            expected_catalog_sha256=args.expected_context_catalog_sha256,
            registry_source_commit=args.registry_source_commit,
            expected_registry_sha256=args.expected_registry_sha256,
        )
    except Exception as error:
        raise _staged_failure(error, "source_authentication_failed") from error
    _require_unconsumed_source_root(source_binding)
    out_state = _private_new_output(args.out_state, rom_path=rom_path)
    out_manifest = _private_new_output(
        args.out_manifest or Path(f"{out_state}.json"),
        rom_path=rom_path,
    )
    _require_distinct_outputs(out_state, out_manifest)
    partition = source_binding.partition
    rom_bytes = rom_path.read_bytes()

    with PyBoyAdapter(
        rom_path,
        watch=args.watch,
        speed=args.speed,
    ) as emulator:
        emulator.load_state_bytes(source_bytes)
        reader = PokemonRedStateReader(emulator)
        try:
            raw = reader.read()
            last_blackout_map = reader.read_last_blackout_map()
            current_map_tileset = emulator.read_u8(RamAddress.CURRENT_MAP_TILESET)
            if args.expected_reachable_venue_id is not None:
                edge, venue = _selected_reachable_venue_for_state(
                    raw,
                    args.expected_reachable_venue_id,
                    last_blackout_map=last_blackout_map,
                    current_map_tileset=current_map_tileset,
                    rom_bytes=rom_bytes,
                )
                source_location = edge.source_location
            else:
                source_location = _source_location_for_state(
                    raw,
                    last_blackout_map=last_blackout_map,
                    current_map_tileset=current_map_tileset,
                )
                venue = _venue_for_source_location(
                    source_location,
                    rom_bytes=(
                        rom_bytes
                        if source_location
                        in {
                            "lavender_center_route_11",
                            "vermilion_transition_route_11",
                        }
                        else None
                    ),
                )
        except Exception as error:
            raise _staged_failure(error, "source_reauthentication_failed") from error
        controller = FrameSafeExecutor(
            emulator,
            DEFAULT_NEW_GAME_TIMING.controller_timing(),
        )
        actions = CountingExecutor(controller)
        try:
            _prepare_source_venue(
                source_location,
                venue,
                actions,
                reader,
                emulator,
            )
        except Exception as error:
            raise _staged_failure(error, "source_relocation_failed") from error
        try:
            materialized = _materialize_loaded_battle_boundary(
                reader,
                emulator,
                controller,
                actions,
                venue,
                one_based_party_slot=args.party_slot,
                maximum_encounter_steps=args.maximum_encounter_steps,
            )
            emulator.save_state(out_state)
        except Exception as error:
            raise _staged_failure(error, "encounter_materialization_failed") from error

    try:
        state_bytes = _fsync_existing_private_output(out_state)
        manifest_payload = build_battle_scenario_capture_payload(
            capture_id=args.capture_id,
            root_lineage_id=source_binding.root_lineage_id,
            partition=partition,
            state_bytes=state_bytes,
            initial_observation_sha256=materialized.prepared.initial_observation_sha256,
            source_commit=source.git_commit,
            expected_map=venue.map_id,
            expected_battle_state=1,
            source_state_sha256=hashlib.sha256(source_bytes).hexdigest(),
        )
        _write_private_output(out_manifest, manifest_payload)
    except Exception as error:
        raise _staged_failure(error, "output_publication_failed") from error
    return {
        "schema": "pokemon-private-battle-scenario-materialization-receipt-v2",
        "status": "ok",
        "capture_id": args.capture_id,
        "root_lineage_id": source_binding.root_lineage_id,
        "partition": partition.value,
        "source_commit": source.git_commit,
        "source_state_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "source_slot_id": source_binding.source_slot_id,
        "source_assignment_id": source_binding.source_assignment_id,
        "source_context_id": source_binding.source_context_id,
        "source_envelope_sha256": source_binding.source_envelope_sha256,
        "root_consumption_sha256": source_binding.root_consumption_sha256,
        "source_binding_sha256": canonical_sha256(source_binding.public_dict()),
        "context_catalog_sha256": catalog.catalog_sha256,
        "registry_sha256": historical_registry.registry_sha256,
        "registry_source_commit": source_binding.registry_source_commit,
        "state_sha256": hashlib.sha256(state_bytes).hexdigest(),
        "manifest_sha256": hashlib.sha256(manifest_payload).hexdigest(),
        "initial_observation_sha256": materialized.prepared.initial_observation_sha256,
        "candidate_count": len(materialized.prepared.features.candidate_vectors),
        "supported_candidate_count": sum(materialized.prepared.supported_candidate_mask),
        "venue_id": venue.area_id,
        "venue_minimum_encounter_level": venue.band.minimum_encounter_level,
        "venue_maximum_encounter_level": venue.band.maximum_encounter_level,
        "source_location": source_location,
        "party_slot": args.party_slot,
        "encounter_steps": materialized.encounter_steps,
        "encounter_walk_calls": materialized.encounter_walk_calls,
        "boundary_actions": materialized.boundary.actions_executed,
        "boundary_frames": materialized.boundary.frames_executed,
        "switch_actions": materialized.switch_actions,
        "party_switches_executed": int(materialized.switch_actions > 0),
        "total_actions": (actions.actions_executed + materialized.boundary.actions_executed),
        "teacher_queries": 0,
        "move_choices_executed": 0,
        "source_root_available_before_materialization": True,
        "root_claims_created": 0,
        "caller_supplied_partition": False,
        "caller_supplied_lineage": False,
        "caller_supplied_source_location": False,
        "selected_reachable_venue_reauthenticated": (
            args.expected_reachable_venue_id is not None
        ),
        "private_path_fields": 0,
    }


def _staged_failure(error: Exception, reason_code: str) -> BattleScenarioMaterializationError:
    message = str(error) if isinstance(error, BattleScenarioMaterializationError) else reason_code
    diagnostics = (
        error.diagnostics
        if isinstance(error, BattleScenarioMaterializationError)
        else _portable_failure_diagnostics(error)
    )
    return BattleScenarioMaterializationError(
        message,
        reason_code=reason_code,
        diagnostics=diagnostics,
    )


def _portable_failure_diagnostics(error: Exception) -> dict[str, object]:
    """Retain bounded semantic route evidence without exception text or paths."""

    current: BaseException | None = error
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if isinstance(current, RouteExecutionError):
            report = current.failure
            diagnostics: dict[str, object] = {
                "failure_layer": "route_execution",
                "route_failure_reason": current.reason.value,
                "route_failure_report_present": report is not None,
            }
            if report is not None:
                diagnostics.update(
                    {
                        "route_executed_step_count": len(report.executed_steps),
                        "route_interruption_count": len(report.interruptions),
                        "route_movement_requests": report.movement_requests,
                        "route_replan_count": len(report.replans),
                        "route_resource_renewal_count": len(
                            report.resource_renewals
                        ),
                        "route_wait_actions": report.wait_actions,
                    }
                )
                if report.last_observation is not None:
                    diagnostics.update(
                        {
                            "route_last_interruption_present": (
                                report.last_observation.interruption is not None
                            ),
                            "route_last_map_id": report.last_observation.map_id,
                            "route_last_ready": report.last_observation.ready,
                            "route_last_x": report.last_observation.at[1],
                            "route_last_y": report.last_observation.at[0],
                        }
                    )
            return diagnostics
        current = current.__cause__ or current.__context__
    return {"failure_layer": "materialization_stage"}


def _failure_receipt(error: Exception) -> dict[str, object]:
    reason_code = (
        error.reason_code
        if isinstance(error, BattleScenarioMaterializationError)
        else "materialization_internal_failure"
    )
    return {
        "schema": _FAILURE_SCHEMA,
        "status": "failed_closed",
        "reason_code": reason_code,
        "diagnostics": (
            error.diagnostics
            if isinstance(error, BattleScenarioMaterializationError)
            else _portable_failure_diagnostics(error)
        ),
        "private_path_fields": 0,
        "teacher_queries": 0,
        "move_choices_executed": 0,
        "root_claims_created": 0,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        receipt = _run(args)
    except Exception as error:
        print(json.dumps(_failure_receipt(error), ensure_ascii=True, sort_keys=True))
        return 1
    print(json.dumps(receipt, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
