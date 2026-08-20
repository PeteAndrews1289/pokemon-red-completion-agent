#!/usr/bin/env python3
"""Freeze two natural middle-PP preparations without controller input."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNNER_PATH = PROJECT_ROOT / "scripts" / "run_red_party_development_pp_materialization.py"
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.blaine import (  # noqa: E402
    ROUTE_11_TRAINING_VENUE,
)
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    working_source_bundle_sha256,
)
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.gen1_cartridge import (  # noqa: E402
    evolution_graph,
    wild_tables,
)
from pokemon_red_completion.goal_manager_context_catalog import (  # noqa: E402
    open_goal_manager_context_capture,
    parse_goal_manager_context_catalog,
)
from pokemon_red_completion.goal_manager_protocol import (  # noqa: E402
    load_committed_goal_manager_registry_at_revision,
)
from pokemon_red_completion.observation import (  # noqa: E402
    ItemId,
    MapId,
    PokemonRedStateReader,
    RawGameState,
)
from pokemon_red_completion.party_development_inventory import (  # noqa: E402
    PartyDevelopmentCheckpointInventory,
)
from pokemon_red_completion.party_development_question_reservations import (  # noqa: E402
    PartyDevelopmentContextPreparation,
    PartyDevelopmentQuestionReservationPlan,
    pp_materialization_source_ready,
)
from pokemon_red_completion.party_development_venue_priors import (  # noqa: E402
    PartyDevelopmentVenuePriorRegistry,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    canonical_sha256,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_collection import (  # noqa: E402
    red_internal_species_number,
)
from pokemon_red_completion.red_party import PokemonRedPartyReader  # noqa: E402
from pokemon_red_completion.red_party_development_pp_materialization import (  # noqa: E402
    RedPpMaterializationSource,
    RedPpStartAdapter,
    freeze_red_party_development_pp_materialization_plan,
    red_pp_protected_state_sha256,
    red_pp_source_boundary_sha256,
    red_pp_venue_binding_sha256,
)
from pokemon_red_completion.red_party_pp import (  # noqa: E402
    decode_red_party_pp,
    natural_pp_depletion_slots,
)
from pokemon_red_completion.rom import (  # noqa: E402
    resolve_rom_path,
    verify_rom_bytes,
)
from pokemon_red_completion.route_evidence import (  # noqa: E402
    rom_adjacent_artifacts,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402

_MAX_JSON_BYTES = 4 * 1024 * 1024


class RedPartyPpPreflightRunError(RuntimeError):
    """Raised before a private preparation plan can be frozen ambiguously."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reservation-plan", type=Path, required=True)
    parser.add_argument("--reservation-plan-file-sha256", required=True)
    parser.add_argument("--checkpoint-inventory", type=Path, required=True)
    parser.add_argument("--checkpoint-inventory-file-sha256", required=True)
    parser.add_argument("--venue-prior-registry", type=Path, required=True)
    parser.add_argument("--venue-prior-registry-file-sha256", required=True)
    parser.add_argument("--catalog-root", type=Path, required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--context-catalog-file-sha256", required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--out-plan", type=Path, required=True)
    parser.add_argument("--out-summary", type=Path, required=True)
    return parser


def _require_external(path: Path, *, subject: str) -> Path:
    resolved = path.resolve()
    if resolved.is_relative_to(PROJECT_ROOT.resolve()):
        raise RedPartyPpPreflightRunError(f"private {subject} must remain outside the repository")
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
        raise RedPartyPpPreflightRunError(f"{subject} file digest or size differs")
    try:
        value = json.loads(payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RedPartyPpPreflightRunError(f"{subject} is not valid ASCII JSON") from error
    if not isinstance(value, Mapping):
        raise RedPartyPpPreflightRunError(f"{subject} document is invalid")
    return value


def _canonical_payload(document: Mapping[str, object]) -> bytes:
    return (
        json.dumps(
            document,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("ascii")


def _write_exclusive(path: Path, payload: bytes) -> str:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return hashlib.sha256(payload).hexdigest()


def _capture_paths(catalog_root: Path, checkpoint_id: str) -> tuple[Path, Path]:
    state = catalog_root / "captures" / f"{checkpoint_id}.state"
    envelope = state.with_suffix(".state.json")
    if not state.is_file() or not envelope.is_file():
        raise RedPartyPpPreflightRunError("reserved PP source is missing its state or envelope")
    return state, envelope


def _start_adapter(raw: RawGameState) -> RedPpStartAdapter:
    boundary = (raw.map_id, raw.player_x, raw.player_y)
    if boundary == (int(MapId.CINNABAR_POKECENTER), 13, 4):
        return RedPpStartAdapter.CINNABAR_CENTER_PC_TO_ROUTE_11
    if boundary == (int(MapId.CINNABAR_MART), 2, 5):
        return RedPpStartAdapter.CINNABAR_MART_CLERK_TO_ROUTE_11
    raise RedPartyPpPreflightRunError(
        "reserved PP source is not at a supported exact start boundary"
    )


def _required_party_vectors(
    raw: RawGameState,
) -> tuple[
    tuple[int, ...],
    tuple[int, ...],
    tuple[int, ...],
    tuple[int, ...],
    tuple[int, ...],
    tuple[tuple[int, ...], ...],
    tuple[tuple[int, ...], ...],
]:
    values = (
        raw.party_species_ids,
        raw.party_levels,
        raw.party_hp,
        raw.party_max_hp,
        raw.party_status,
        raw.party_moves,
        raw.party_pp,
    )
    if raw.party_count != 6 or any(
        value is None or len(value) != raw.party_count for value in values
    ):
        raise RedPartyPpPreflightRunError(
            "reserved PP source lacks one complete six-member party observation"
        )
    species, levels, hp, maximum_hp, status, moves, pp = values
    assert species is not None
    assert levels is not None
    assert hp is not None
    assert maximum_hp is not None
    assert status is not None
    assert moves is not None
    assert pp is not None
    return species, levels, hp, maximum_hp, status, moves, pp


def _venue_binding_sha256(
    registry: PartyDevelopmentVenuePriorRegistry,
    *,
    wild_species_ids: tuple[int, ...],
    maximum_wild_level: int,
) -> str:
    area = ROUTE_11_TRAINING_VENUE.band
    evidence = registry.evidence_for(area)
    if evidence is None:
        raise RedPartyPpPreflightRunError("two-prior registry lacks the shared preparation venue")
    return red_pp_venue_binding_sha256(
        area,
        map_id=ROUTE_11_TRAINING_VENUE.map_id,
        venue_prior_evidence_sha256=evidence.evidence_sha256,
        operational_contract_sha256=evidence.operational_contract_sha256,
        wild_species_ids=wild_species_ids,
        maximum_wild_level=maximum_wild_level,
    )


def _run(args: argparse.Namespace) -> dict[str, object]:
    paths = {
        "reservation_plan": _require_external(args.reservation_plan, subject="reservation plan"),
        "inventory": _require_external(args.checkpoint_inventory, subject="checkpoint inventory"),
        "registry": _require_external(args.venue_prior_registry, subject="venue-prior registry"),
        "catalog_root": _require_external(args.catalog_root, subject="context catalog root"),
        "context_catalog": _require_external(
            args.context_catalog, subject="historical context catalog"
        ),
        "out_plan": _require_external(args.out_plan, subject="PP materialization plan"),
        "out_summary": _require_external(args.out_summary, subject="PP materialization summary"),
    }
    if len(set(paths.values())) != len(paths):
        raise RedPartyPpPreflightRunError("PP materialization preflight paths must be distinct")
    if paths["out_plan"].exists() or paths["out_summary"].exists():
        raise FileExistsError("PP materialization preflight output already exists")

    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    if source.git_commit is None:  # pragma: no cover - source guard owns this
        raise AssertionError("published PP preflight lost its commit")
    source_bundle_sha256 = working_source_bundle_sha256(PROJECT_ROOT)

    reservation_plan = PartyDevelopmentQuestionReservationPlan.from_private_dict(
        _load_json(
            paths["reservation_plan"],
            expected_sha256=args.reservation_plan_file_sha256,
            subject="reservation plan",
        )
    )
    inventory = PartyDevelopmentCheckpointInventory.from_private_dict(
        _load_json(
            paths["inventory"],
            expected_sha256=args.checkpoint_inventory_file_sha256,
            subject="checkpoint inventory",
        )
    )
    registry = PartyDevelopmentVenuePriorRegistry.from_private_dict(
        _load_json(
            paths["registry"],
            expected_sha256=args.venue_prior_registry_file_sha256,
            subject="venue-prior registry",
        )
    )
    if (
        reservation_plan.inventory_sha256 != inventory.inventory_sha256
        or reservation_plan.venue_prior_registry_sha256 != registry.registry_sha256
        or reservation_plan.venue_prior_count != len(registry.entries)
        or len(registry.entries) != 2
    ):
        raise RedPartyPpPreflightRunError(
            "PP materialization inputs do not share one two-prior reservation"
        )

    context_catalog_document = _load_json(
        paths["context_catalog"],
        expected_sha256=args.context_catalog_file_sha256,
        subject="historical context catalog",
    )
    context_catalog_source_commit = context_catalog_document.get("source_commit")
    if not isinstance(context_catalog_source_commit, str):
        raise RedPartyPpPreflightRunError("historical context catalog source is invalid")
    historical_registry = load_committed_goal_manager_registry_at_revision(
        PROJECT_ROOT,
        context_catalog_source_commit,
    )
    context_catalog = parse_goal_manager_context_catalog(
        paths["context_catalog"].read_bytes(),
        historical_registry,
    )

    rom_path = resolve_rom_path(args.rom)
    rom_bytes = rom_path.read_bytes()
    rom_fingerprint = verify_rom_bytes(rom_bytes, filename=rom_path.name)
    cartridge_evolutions = evolution_graph(rom_bytes)
    encounter_tables = wild_tables(rom_bytes)
    venue_slots = encounter_tables.get(ROUTE_11_TRAINING_VENUE.map_id)
    if not venue_slots:
        raise RedPartyPpPreflightRunError(
            "cartridge lacks the shared preparation venue encounter table"
        )
    wild_species_ids = tuple(sorted({species for _level, species in venue_slots}))
    maximum_wild_level = max(level for level, _species in venue_slots)
    venue_binding_sha256 = _venue_binding_sha256(
        registry,
        wild_species_ids=wild_species_ids,
        maximum_wild_level=maximum_wild_level,
    )
    adjacent_before = rom_adjacent_artifacts(rom_path)
    protected_inputs = {
        path: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (
            paths["reservation_plan"],
            paths["inventory"],
            paths["registry"],
            paths["context_catalog"],
            rom_path,
        )
    }
    inventory_by_checkpoint = {item.checkpoint_id: item for item in inventory.entries}
    reservations = tuple(
        item
        for item in reservation_plan.reservations
        if item.preparation is PartyDevelopmentContextPreparation.NATURAL_PP_DEPLETION
    )
    if len(reservations) != 2:
        raise RedPartyPpPreflightRunError(
            "refreshed reservation does not contain exactly two PP sources"
        )

    sources: list[RedPpMaterializationSource] = []
    source_files: dict[Path, str] = {}
    for reservation in reservations:
        try:
            inventory_entry = inventory_by_checkpoint[reservation.source_checkpoint_id]
        except KeyError as error:
            raise RedPartyPpPreflightRunError(
                "reserved PP source is absent from the checkpoint inventory"
            ) from error
        if not pp_materialization_source_ready(inventory_entry):
            raise RedPartyPpPreflightRunError(
                "reserved PP source fails the no-heal source predicate"
            )
        state_path, envelope_path = _capture_paths(
            paths["catalog_root"],
            reservation.source_checkpoint_id,
        )
        before = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (state_path, envelope_path)
        }
        source_files.update(before)
        capture = open_goal_manager_context_capture(state_path, envelope_path)
        if (
            capture.capture_id != reservation.source_checkpoint_id
            or capture.state_sha256 != reservation.source_state_sha256
            or capture.envelope_sha256 != reservation.source_envelope_sha256
        ):
            raise RedPartyPpPreflightRunError(
                "reserved PP capture differs from its authenticated identity"
            )
        catalog_entry = context_catalog.entry(reservation.source_checkpoint_id)
        source_root_lineage_id = catalog_entry.authenticated_root_lineage_id(
            slot_id=reservation.source_checkpoint_id,
            capture_id=reservation.source_checkpoint_id,
            state_sha256=reservation.source_state_sha256,
            envelope_sha256=reservation.source_envelope_sha256,
        )
        if (
            source_root_lineage_id in reservation_plan.excluded_root_lineage_ids
            or reservation.source_state_sha256 in reservation_plan.excluded_state_sha256
        ):
            raise RedPartyPpPreflightRunError(
                "reserved PP source overlaps protected prior evidence"
            )

        with PyBoyAdapter(rom_path, watch=False, speed=None) as emulator:
            emulator.load_state_bytes(capture.state_bytes)
            reader = PokemonRedStateReader(emulator)
            raw = reader.read()
            input_ready = reader.read_input_readiness().ready
            pokedex = reader.read_pokedex_state()
            boxes = reader.read_all_box_states()
            party_experience = tuple(
                member.experience for member in PokemonRedPartyReader(emulator).read().members
            )

        if (
            not raw.game_started
            or raw.battle_state != 0
            or not input_ready
            or raw.party_count != 6
            or int(ItemId.EXP_ALL) in (raw.bag_item_ids or ())
            or any(value is None for value in party_experience)
        ):
            raise RedPartyPpPreflightRunError(
                "reserved PP source is not a stable no-share six-member field boundary"
            )
        complete_party_experience = tuple(value for value in party_experience if value is not None)
        adapter = _start_adapter(raw)
        species, levels, hp, maximum_hp, status, moves, pp = _required_party_vectors(raw)
        if any(value != 0 for value in status) or any(
            current <= 0 or current * 100 < maximum * 67
            for current, maximum in zip(hp, maximum_hp, strict=True)
        ):
            raise RedPartyPpPreflightRunError(
                "reserved PP source contains status, fainting, or non-high health"
            )
        highest_level = max(levels)
        highest_slots = tuple(
            index + 1 for index, level in enumerate(levels) if level == highest_level
        )
        if highest_slots != (1,):
            raise RedPartyPpPreflightRunError(
                "reserved PP source lacks one unique highest-level field lead"
            )
        target_index = 0
        pp_state = decode_red_party_pp(moves[target_index], pp[target_index])
        safe_slots = natural_pp_depletion_slots(pp_state)
        safe_current_pp = sum(pp_state.moves[slot - 1].current_pp for slot in safe_slots)
        target_national_number = red_internal_species_number(species[target_index])
        possible_national_numbers = frozenset(
            red_internal_species_number(item) for item in wild_species_ids
        )
        all_seen = possible_national_numbers <= pokedex.seen_species
        output_capture_id = {
            ScenarioPartition.TRAIN: "red-party-pp-v1-train-01",
            ScenarioPartition.DEVELOPMENT: "red-party-pp-v1-development-01",
        }[reservation.partition]
        sources.append(
            RedPpMaterializationSource(
                scenario_id=reservation.scenario_id,
                partition=reservation.partition,
                source_checkpoint_id=reservation.source_checkpoint_id,
                source_state_sha256=reservation.source_state_sha256,
                source_envelope_sha256=reservation.source_envelope_sha256,
                source_semantic_signature_sha256=(reservation.source_semantic_signature_sha256),
                source_root_lineage_id=source_root_lineage_id,
                source_boundary_sha256=red_pp_source_boundary_sha256(
                    raw,
                    input_ready=input_ready,
                ),
                protected_state_sha256=red_pp_protected_state_sha256(
                    raw,
                    pokedex,
                    boxes,
                    complete_party_experience,
                    target_party_slot=1,
                ),
                start_adapter=adapter,
                target_party_slot=1,
                target_species_id=species[target_index],
                target_level=levels[target_index],
                target_hp=hp[target_index],
                target_max_hp=maximum_hp[target_index],
                target_move_ids=tuple(moves[target_index]),  # type: ignore[arg-type]
                target_initial_packed_pp=tuple(pp[target_index]),  # type: ignore[arg-type]
                safe_move_slots=safe_slots,
                current_total_pp=pp_state.current_total,
                maximum_total_pp=pp_state.maximum_total,
                middle_pp_ceiling=pp_state.middle_pp_ceiling,
                minimum_pp_consumption=pp_state.minimum_consumption_to_middle,
                safe_current_pp=safe_current_pp,
                target_has_evolution_route=bool(cartridge_evolutions.get(target_national_number)),
                venue_map_id=ROUTE_11_TRAINING_VENUE.map_id,
                venue_binding_sha256=venue_binding_sha256,
                venue_maximum_wild_level=maximum_wild_level,
                possible_wild_species_ids=wild_species_ids,
                possible_wild_species_sha256=canonical_sha256(list(wild_species_ids)),
                all_possible_wild_species_seen=all_seen,
                output_capture_id=output_capture_id,
            )
        )
        after = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (state_path, envelope_path)
        }
        if after != before:
            raise RedPartyPpPreflightRunError(
                "reserved PP source changed during read-only inspection"
            )

    if set(item.start_adapter for item in sources) != set(RedPpStartAdapter):
        raise RedPartyPpPreflightRunError(
            "PP materialization plan lacks both frozen start adapters"
        )
    if {
        path: hashlib.sha256(path.read_bytes()).hexdigest() for path in protected_inputs
    } != protected_inputs or {
        path: hashlib.sha256(path.read_bytes()).hexdigest() for path in source_files
    } != source_files:
        raise RedPartyPpPreflightRunError(
            "PP materialization protected inputs changed during inspection"
        )
    if rom_adjacent_artifacts(rom_path) != adjacent_before:
        raise RedPartyPpPreflightRunError("read-only PP preflight created a ROM-adjacent artifact")

    plan = freeze_red_party_development_pp_materialization_plan(
        reservation_plan,
        sources=tuple(sources),
        source_commit=source.git_commit,
        source_bundle_sha256=source_bundle_sha256,
        runner_source_sha256=hashlib.sha256(RUNNER_PATH.read_bytes()).hexdigest(),
        rom_sha256=rom_fingerprint.sha256,
        inventory_file_sha256=args.checkpoint_inventory_file_sha256,
        reservation_plan_file_sha256=args.reservation_plan_file_sha256,
        venue_prior_registry_file_sha256=(args.venue_prior_registry_file_sha256),
        context_catalog_sha256=context_catalog.catalog_sha256,
        context_catalog_file_sha256=args.context_catalog_file_sha256,
    )
    plan_payload = _canonical_payload(plan.private_dict())
    plan_file_sha256 = hashlib.sha256(plan_payload).hexdigest()
    summary: dict[str, object] = {
        **plan.public_summary(),
        "inventory_file_sha256": args.checkpoint_inventory_file_sha256,
        "reservation_plan_file_sha256": args.reservation_plan_file_sha256,
        "venue_prior_registry_file_sha256": (args.venue_prior_registry_file_sha256),
        "context_catalog_file_sha256": args.context_catalog_file_sha256,
        "private_plan_file_sha256": plan_file_sha256,
        "private_plan_file_tracked": False,
        "rom_identity_verifications": 1,
        "read_only_emulator_starts": len(sources),
    }
    summary_payload = _canonical_payload(summary)
    _write_exclusive(paths["out_plan"], plan_payload)
    try:
        summary_file_sha256 = _write_exclusive(paths["out_summary"], summary_payload)
    except BaseException:
        paths["out_plan"].unlink(missing_ok=True)
        raise
    return {**summary, "public_summary_file_sha256": summary_file_sha256}


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        result = _run(parser.parse_args(argv))
    except (OSError, RuntimeError, TypeError, ValueError):
        parser.error("Red PP materialization preflight failed closed; private paths were withheld")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
