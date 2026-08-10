"""Try to disprove the cartridge-decoded Route 1 ledge transition live.

The existing teacher establishes the verified post-Pokédex state. Cartridge
terrain and traversal rules then choose the nearest reachable ledge, generate
the approach, and supply the final controller direction. Live memory must agree
with every approach step, the two-square hop, and the blocked reverse input.

Usage::

    POKEMON_RED_ROM=<path> python scripts/falsify_route1_ledge.py \
        --out docs/evidence/<name>.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pokemon_red_completion.actions import MacroAction, MacroActionKind  # noqa: E402
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING  # noqa: E402
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.executor import CountingExecutor, FrameSafeExecutor  # noqa: E402
from pokemon_red_completion.gen1_maps import map_graph  # noqa: E402
from pokemon_red_completion.gen1_terrain import walkable_world  # noqa: E402
from pokemon_red_completion.gen1_traversal import (  # noqa: E402
    local_graph,
    map_object_events,
    traversal_rules,
)
from pokemon_red_completion.local_router import find_nearest_transition  # noqa: E402
from pokemon_red_completion.observation import MapId, PokemonRedStateReader  # noqa: E402
from pokemon_red_completion.opening import run_opening_chapter  # noqa: E402
from pokemon_red_completion.pewter import (  # noqa: E402
    DEFAULT_PEWTER_TIMING,
    LAB_TO_PALLET_DIRECTIONS,
    PALLET_TO_ROUTE_1_DIRECTIONS,
)
from pokemon_red_completion.play import (  # noqa: E402
    DEFAULT_QUALIFIED_PLAY_TIMING,
    QualifiedPlayError,
    _expect_position,
    _move,
    _wait,
    run_oaks_errand_chapter,
)
from pokemon_red_completion.rom import resolve_rom_path, verify_rom  # noqa: E402
from pokemon_red_completion.route_1_wild import (  # noqa: E402
    move_route_1_with_wild_flees,
)


class Route1LedgeProbeError(RuntimeError):
    """Raised when live Route 1 behavior disproves the decoded transition."""


_OPPOSITE = {"up": "down", "down": "up", "left": "right", "right": "left"}


def _artifact_identity(path: Path) -> tuple[bool, str | None]:
    if not path.exists():
        return False, None
    return True, hashlib.sha256(path.read_bytes()).hexdigest()


def _adjacent_artifacts(rom_path: Path) -> tuple[tuple[bool, str | None], ...]:
    return tuple(
        _artifact_identity(Path(f"{rom_path}{suffix}"))
        for suffix in (".ram", ".rtc", ".state")
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--recorded-on", default=date.today().isoformat())
    args = parser.parse_args(argv)

    rom_path = resolve_rom_path(args.rom)
    fingerprint = verify_rom(rom_path)
    rom = rom_path.read_bytes()
    maps = map_graph(rom)
    world = walkable_world(rom)
    rules = traversal_rules(rom, maps)
    route_1 = MapId.ROUTE_1.value
    blockers = {event.at for event in map_object_events(rom, {route_1})}
    graph = local_graph(world[route_1], rules, blocked=blockers)
    before_artifacts = _adjacent_artifacts(rom_path)

    new_game_timing = DEFAULT_NEW_GAME_TIMING
    route_timing = DEFAULT_PEWTER_TIMING
    with PyBoyAdapter(rom_path) as emulator:
        controller = FrameSafeExecutor(emulator, new_game_timing.controller_timing())
        opening = run_opening_chapter(
            rom_path,
            _emulator=emulator,
            _executor=controller,
        )
        if not opening.passed:
            raise Route1LedgeProbeError("the qualified opening precondition failed")

        reader = PokemonRedStateReader(emulator)
        executor = CountingExecutor(controller)
        errand = run_oaks_errand_chapter(
            emulator,
            reader,
            executor,
            timing=DEFAULT_QUALIFIED_PLAY_TIMING,
        )
        if not errand.passed:
            raise Route1LedgeProbeError("the verified Pokédex precondition failed")

        _move(executor, reader, LAB_TO_PALLET_DIRECTIONS, "ledge probe lab exit")
        _wait(executor, route_timing.transition_wait_frames)
        _expect_position(
            reader.read(),
            MapId.PALLET_TOWN,
            12,
            12,
            "ledge probe Pallet exterior",
        )
        _move(
            executor,
            reader,
            PALLET_TO_ROUTE_1_DIRECTIONS,
            "ledge probe Pallet north route",
        )
        _wait(executor, route_timing.transition_wait_frames)
        start = reader.read()
        _expect_position(start, MapId.ROUTE_1, 10, 35, "ledge probe Route 1 entrance")

        if start.player_y is None or start.player_x is None:
            raise Route1LedgeProbeError("the Route 1 start has no player coordinate")
        start_yx = (start.player_y, start.player_x)
        planned = find_nearest_transition(graph, start_yx, "ledge")
        if any(edge.kind != "walk" for edge in planned.approach.edges):
            raise Route1LedgeProbeError("the selected ledge approach already crosses a ledge")
        approach_inputs = tuple(edge.action for edge in planned.approach.edges)
        _wait(executor, route_timing.route_1_seed_wait_frames)
        approached, flees, retries = move_route_1_with_wild_flees(
            executor,
            reader,
            approach_inputs,
            "cartridge-computed ledge approach",
            maximum_flees=route_timing.max_route_1_wild_flees,
            stabilization_frames=route_timing.route_1_wild_exit_stabilization_frames,
            maximum_step_attempts=route_timing.max_route_1_step_attempts,
            step_retry_wait_frames=route_timing.route_1_step_retry_wait_frames,
            error_type=QualifiedPlayError,
        )
        source_yx = planned.approach.coordinates[-1]
        if (approached.player_y, approached.player_x) != source_yx:
            raise Route1LedgeProbeError("the live approach missed the decoded ledge source")

        executor.execute(
            MacroAction(MacroActionKind.MOVE, planned.transition.action)
        )
        _wait(executor, route_timing.transition_wait_frames)
        landed = reader.read()
        if (
            landed.map_id != MapId.ROUTE_1
            or landed.battle_state != 0
            or (landed.player_y, landed.player_x) != planned.transition.target
        ):
            raise Route1LedgeProbeError("the decoded ledge input missed its two-square landing")

        reverse_input = _OPPOSITE[planned.transition.action]
        executor.execute(MacroAction(MacroActionKind.MOVE, reverse_input))
        _wait(executor, route_timing.route_1_step_retry_wait_frames)
        reversed_state = reader.read()
        if (
            reversed_state.map_id != MapId.ROUTE_1
            or reversed_state.battle_state != 0
            or (reversed_state.player_y, reversed_state.player_x)
            != planned.transition.target
        ):
            raise Route1LedgeProbeError("the live game allowed the one-way ledge in reverse")

        frames_executed = emulator.frame_count
        actions_executed = executor.actions_executed
        controller_released = not emulator.pressed_buttons

    artifacts_unchanged = before_artifacts == _adjacent_artifacts(rom_path)
    if not artifacts_unchanged:
        raise Route1LedgeProbeError("the no-save probe changed a ROM-adjacent artifact")

    payload = {
        "schema": "route1-cartridge-ledge-probe-v1",
        "recorded_on": args.recorded_on,
        "status": "ok",
        "rom": fingerprint.public_dict(),
        "precondition": (
            "The qualified teacher established clean power-on, a verified starter, "
            "Oak's parcel delivery and the Pokédex before entering Route 1."
        ),
        "authority_under_test": (
            "Cartridge terrain, object events, ledge rules and the game-neutral local "
            "router selected every approach input and the final ledge input."
        ),
        "start_yx": list(planned.approach.coordinates[0]),
        "ledge_source_yx": list(source_yx),
        "ledge_landing_yx": list(planned.transition.target),
        "approach_coordinates_yx": [
            list(coordinate) for coordinate in planned.approach.coordinates
        ],
        "approach_inputs": list(approach_inputs),
        "ledge_input": planned.transition.action,
        "ledge_transition_kind": planned.transition.kind,
        "reverse_input": reverse_input,
        "reverse_was_blocked": True,
        "wild_flees": len(flees),
        "movement_retries": retries,
        "frames_executed": frames_executed,
        "actions_executed_after_opening": actions_executed,
        "controller_released": controller_released,
        "rom_adjacent_artifacts_unchanged": artifacts_unchanged,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {args.out}: {len(approach_inputs)} generated approach inputs, "
        f"{len(flees)} wild flees, ledge landed at {planned.transition.target}, "
        "reverse blocked"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
