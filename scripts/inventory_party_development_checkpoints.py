#!/usr/bin/env python3
"""Read open Red checkpoints into a path-free party-development inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.captured_progress import load_captured_progress  # noqa: E402
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.gen1_cartridge import (  # noqa: E402
    EvolutionMethod,
    evolution_graph,
)
from pokemon_red_completion.observation import PokemonRedStateReader  # noqa: E402
from pokemon_red_completion.party_development_inventory import (  # noqa: E402
    PartyDevelopmentCheckpointInventory,
    PartyDevelopmentInventoryEntry,
    PartyDevelopmentInventoryMember,
    level_distance_bin,
    unit_bin,
)
from pokemon_red_completion.party_development_rank import (  # noqa: E402
    EvolutionRouteKind,
    PartyDevelopmentGoal,
)
from pokemon_red_completion.red_collection import (  # noqa: E402
    RED_SOLO_COLLECTION_CONTRACT,
    red_collection_observation,
    red_internal_species_number,
    red_species_number,
)
from pokemon_red_completion.red_party import (  # noqa: E402
    RED_BALANCED_ROSTER,
    PokemonRedPartyReader,
)
from pokemon_red_completion.red_party_development_adapter import (  # noqa: E402
    RED_PARTY_DEVELOPMENT_CURRICULUM_POLICY,
)
from pokemon_red_completion.red_party_pp import (  # noqa: E402
    RedPartyPpError,
    decode_red_party_pp,
)
from pokemon_red_completion.rom import resolve_rom_path, verify_rom  # noqa: E402
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402


class PartyDevelopmentInventoryRunError(RuntimeError):
    """Raised before an inventory can silently omit or execute a checkpoint."""


_CAPTURE_PATTERNS = (
    "red-goal-v1-*.state",
    "red-party-pp-v1-train-*.state",
    "red-party-pp-v1-development-*.state",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-root", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--out-inventory", type=Path, required=True)
    parser.add_argument("--out-summary", type=Path, required=True)
    return parser


def _partition(checkpoint_id: str) -> ScenarioPartition:
    if checkpoint_id.startswith("red-party-pp-v1-train-"):
        return ScenarioPartition.TRAIN
    if checkpoint_id.startswith("red-party-pp-v1-development-"):
        return ScenarioPartition.DEVELOPMENT
    if "-train-" in checkpoint_id:
        return ScenarioPartition.TRAIN
    if "-validation-" in checkpoint_id:
        return ScenarioPartition.DEVELOPMENT
    raise PartyDevelopmentInventoryRunError(
        "checkpoint identity has no open train/development partition"
    )


def _capture_states(capture_root: Path) -> tuple[Path, ...]:
    states = tuple(
        sorted(
            {
                path
                for pattern in _CAPTURE_PATTERNS
                for path in capture_root.glob(pattern)
            }
        )
    )
    if not states:
        raise PartyDevelopmentInventoryRunError(
            "capture root contains no open goal-manager or prepared PP checkpoints"
        )
    return states


def _pp_ratio(
    move_ids: tuple[int, ...], packed_pp: tuple[int, ...]
) -> float:
    """Return remaining PP over this moveset's actual Gen I maximum.

    The top two bits of each PP byte count PP Ups. Red adds one fifth of the
    move's base PP per use, with the per-use bonus capped at seven. Normalizing
    by a global four-byte ceiling would classify a fresh low-PP moveset as
    exhausted and would make the inventory's diversity gate misleading.
    """

    try:
        return decode_red_party_pp(move_ids, packed_pp).ratio
    except RedPartyPpError as error:
        message = str(error).replace("Red move", "checkpoint move").replace(
            "empty Red move", "empty checkpoint move"
        )
        raise PartyDevelopmentInventoryRunError(message) from error


def _pp_bin(move_ids: tuple[int, ...], packed_pp: tuple[int, ...]) -> str:
    return unit_bin(_pp_ratio(move_ids, packed_pp))


def _route_kind(method: EvolutionMethod) -> EvolutionRouteKind:
    return {
        EvolutionMethod.LEVEL: EvolutionRouteKind.LEVEL,
        EvolutionMethod.STONE: EvolutionRouteKind.ITEM,
        EvolutionMethod.TRADE: EvolutionRouteKind.TRADE,
    }[method]


def _write_exclusive(path: Path, document: dict[str, object]) -> str:
    payload = (
        json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return hashlib.sha256(payload).hexdigest()


def _run(args: argparse.Namespace) -> dict[str, object]:
    rom_path = resolve_rom_path(args.rom)
    fingerprint = verify_rom(rom_path)
    cartridge_evolutions = evolution_graph(rom_path.read_bytes())
    states = _capture_states(args.capture_root)
    expected_files = {
        path.with_suffix(".state.json") for path in states
    }
    actual_envelopes = {
        path
        for pattern in _CAPTURE_PATTERNS
        for path in args.capture_root.glob(f"{pattern}.json")
    }
    if expected_files != actual_envelopes:
        raise PartyDevelopmentInventoryRunError(
            "capture root does not contain one envelope per checkpoint"
        )

    registration_targets = frozenset(
        red_species_number(item)
        for item in RED_SOLO_COLLECTION_CONTRACT.target_species
    )
    living_targets = frozenset(
        red_species_number(item)
        for item in RED_SOLO_COLLECTION_CONTRACT.resolved_living_target_species
    )
    planned_roles = set(RED_BALANCED_ROSTER.species_ids)
    entries = []
    for state_path in states:
        envelope_path = state_path.with_suffix(".state.json")
        envelope = load_captured_progress(envelope_path, state_path=state_path)
        if envelope.checkpoint_id != state_path.stem:
            raise PartyDevelopmentInventoryRunError(
                "checkpoint filename differs from its authenticated envelope"
            )
        with PyBoyAdapter(rom_path) as emulator:
            emulator.load_state(state_path)
            reader = PokemonRedStateReader(emulator)
            raw = reader.read()
            party = PokemonRedPartyReader(emulator).read()
            pokedex = reader.read_pokedex_state()
            boxes = reader.read_all_box_states()
            collection = red_collection_observation(pokedex, party, boxes)
            controls_ready = reader.read_input_readiness().ready

        if (
            raw.party_moves is None
            or raw.party_pp is None
            or len(raw.party_moves) != len(party.members)
            or len(raw.party_pp) != len(party.members)
        ):
            raise PartyDevelopmentInventoryRunError(
                "checkpoint party move and PP evidence is incomplete"
            )

        living_numbers = frozenset(
            red_species_number(item.species_ref) for item in collection.specimens
        )
        members = []
        for member_index, member in enumerate(party.members):
            national_number = red_internal_species_number(member.species_id)
            steps = cartridge_evolutions.get(national_number, ())
            routes: tuple[EvolutionRouteKind, ...] = tuple(
                route
                for route in EvolutionRouteKind
                if route is not EvolutionRouteKind.NONE
                and route in {_route_kind(step.method) for step in steps}
            )
            if not routes:
                routes = (EvolutionRouteKind.NONE,)
            level_distances = tuple(
                max(0, int(step.requirement) - member.level)
                for step in steps
                if step.method is EvolutionMethod.LEVEL
                and isinstance(step.requirement, int)
            )
            distance_bin = (
                level_distance_bin(min(level_distances))
                if level_distances
                else "none"
            )
            target_numbers = {step.to_species for step in steps}
            members.append(
                PartyDevelopmentInventoryMember(
                    level=member.level,
                    hp_bin=unit_bin(member.hp_ratio),
                    pp_bin=_pp_bin(
                        raw.party_moves[member_index],
                        raw.party_pp[member_index],
                    ),
                    status_present=member.status.value != "healthy",
                    trainable=member.is_trainable,
                    evolution_routes=routes,
                    level_evolution_distance_bin=distance_bin,
                    registration_target_needed=any(
                        target in registration_targets
                        and target not in pokedex.owned_species
                        for target in target_numbers
                    ),
                    living_target_needed=any(
                        target in living_targets and target not in living_numbers
                        for target in target_numbers
                    ),
                    role_complete=member.species_id in planned_roles,
                )
            )
        role_coverage = len(set(party.species_ids()) & planned_roles)
        owned_target_count = len(pokedex.owned_species & registration_targets)
        living_target_count = len(living_numbers & living_targets)
        goal_hints = []
        if (
            max(party.levels) - min(party.levels)
            > RED_PARTY_DEVELOPMENT_CURRICULUM_POLICY.maximum_level_spread
            or min(party.levels)
            < RED_PARTY_DEVELOPMENT_CURRICULUM_POLICY.minimum_level
        ):
            goal_hints.append(PartyDevelopmentGoal.BALANCE)
        if any(
            member.registration_target_needed or member.living_target_needed
            for member in members
        ):
            goal_hints.append(PartyDevelopmentGoal.EVOLUTION)
        if (
            owned_target_count < len(registration_targets)
            or living_target_count < len(living_targets)
        ):
            goal_hints.append(PartyDevelopmentGoal.COLLECTION)
        if role_coverage < len(RED_BALANCED_ROSTER.slots):
            goal_hints.append(PartyDevelopmentGoal.ROLE_COVERAGE)
        ordered_goals = tuple(
            goal for goal in PartyDevelopmentGoal if goal in set(goal_hints)
        )
        if not ordered_goals:
            ordered_goals = (PartyDevelopmentGoal.BALANCE,)
        entries.append(
            PartyDevelopmentInventoryEntry(
                checkpoint_id=envelope.checkpoint_id,
                partition=_partition(envelope.checkpoint_id),
                state_sha256=envelope.state_sha256,
                envelope_sha256=hashlib.sha256(envelope_path.read_bytes()).hexdigest(),
                controls_ready=controls_ready,
                battle_active=raw.battle_state != 0,
                members=tuple(sorted(members, key=lambda item: item.semantic_tuple())),
                registration_owned_count=owned_target_count,
                registration_target_count=len(registration_targets),
                living_unique_count=living_target_count,
                living_target_count=len(living_targets),
                specimen_count=len(collection.specimens),
                role_coverage_count=role_coverage,
                role_target_count=len(RED_BALANCED_ROSTER.slots),
                storage_headroom=sum(
                    collection.box_capacity - count for count in collection.box_counts
                ),
                goal_hints=ordered_goals,
            )
        )

    inventory = PartyDevelopmentCheckpointInventory(
        tuple(sorted(entries, key=lambda item: item.checkpoint_id))
    )
    inventory_document = inventory.private_dict()
    summary = {
        **inventory.summary_dict(),
        "rom": fingerprint.public_dict(),
        "inventory_file_sha256": "pending",
        "inventory_file_tracked": False,
    }
    inventory_file_sha256 = _write_exclusive(args.out_inventory, inventory_document)
    summary["inventory_file_sha256"] = inventory_file_sha256
    summary_file_sha256 = _write_exclusive(args.out_summary, summary)
    return {
        **summary,
        "summary_file_sha256": summary_file_sha256,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        summary = _run(args)
    except (OSError, ValueError, PartyDevelopmentInventoryRunError) as error:
        _parser().error(f"read-only party checkpoint inventory failed: {error}")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
