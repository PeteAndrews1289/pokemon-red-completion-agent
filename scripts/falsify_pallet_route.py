"""Try to disprove a cartridge-computed Pallet Town route in live Red.

The existing opening teacher is used only to establish a verified clean-power-on
state outside Red's house. From that state onward, the path to Oak's Lab is read
from the cartridge: the map graph supplies the destination warp and the terrain
decoder supplies the shortest standable path. Every intermediate coordinate is
checked against live emulator memory, and the final input must enter Oak's Lab.

Usage::

    POKEMON_RED_ROM=<path> python scripts/falsify_pallet_route.py \
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
from pokemon_red_completion.bootstrap import (  # noqa: E402
    DEFAULT_NEW_GAME_TIMING,
    play_new_game_intro,
)
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.executor import CountingExecutor, FrameSafeExecutor  # noqa: E402
from pokemon_red_completion.gen1_maps import map_graph  # noqa: E402
from pokemon_red_completion.gen1_terrain import walkable_world  # noqa: E402
from pokemon_red_completion.navigation import Coordinate, path_to_directions  # noqa: E402
from pokemon_red_completion.observation import (  # noqa: E402
    MapId,
    OpeningPhase,
    PokemonRedStateReader,
)
from pokemon_red_completion.opening import (  # noqa: E402
    BEDROOM_CORRIDOR,
    DEFAULT_OPENING_TIMING,
    HOUSE_1F_CORRIDOR,
    OpeningChapterError,
    _advance_to_bedroom_ready,
    _follow_corridor,
    _wait,
)
from pokemon_red_completion.pallet_route_probe import (  # noqa: E402
    PalletRouteProbeError,
    computed_route,
)
from pokemon_red_completion.rom import resolve_rom_path, verify_rom  # noqa: E402


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
    graph = map_graph(rom)
    world = walkable_world(rom)
    before = _adjacent_artifacts(rom_path)

    timing = DEFAULT_OPENING_TIMING
    new_game_timing = DEFAULT_NEW_GAME_TIMING
    with PyBoyAdapter(rom_path) as emulator:
        reader = PokemonRedStateReader(emulator)
        executor = CountingExecutor(
            FrameSafeExecutor(emulator, new_game_timing.controller_timing())
        )

        play_new_game_intro(executor, timing=new_game_timing)
        _advance_to_bedroom_ready(executor, reader, timing)
        _follow_corridor(
            executor,
            reader,
            MapId.REDS_HOUSE_2F,
            BEDROOM_CORRIDOR,
            final_map=MapId.REDS_HOUSE_1F,
        )
        _wait(executor, timing.transition_wait_frames)
        downstairs = reader.read()
        if (
            downstairs.map_id != MapId.REDS_HOUSE_1F
            or downstairs.player_x != 7
            or downstairs.player_y != 1
        ):
            raise OpeningChapterError("the probe missed Red's house first-floor gate")

        _follow_corridor(
            executor,
            reader,
            MapId.REDS_HOUSE_1F,
            HOUSE_1F_CORRIDOR,
        )
        executor.execute(MacroAction(MacroActionKind.MOVE, "down"))
        _wait(executor, timing.transition_wait_frames)
        outside = reader.read()
        outside_control = reader.read_opening_control_state(outside)
        if (
            outside.map_id != MapId.PALLET_TOWN
            or outside.player_x != 5
            or outside.player_y != 6
            or outside_control.phase is not OpeningPhase.PALLET_FREE
        ):
            raise OpeningChapterError("the probe missed the stable Pallet Town gate")

        start = (outside.player_y, outside.player_x)
        route = computed_route(
            world[MapId.PALLET_TOWN.value],
            graph[MapId.PALLET_TOWN.value],
            start,
        )
        coordinates = tuple(Coordinate(x, y) for y, x in route)
        directions = path_to_directions(coordinates)
        verified_intermediate = 0
        final = outside
        for index, direction in enumerate(directions, start=1):
            executor.execute(MacroAction(MacroActionKind.MOVE, direction.value))
            final = reader.read()
            if index == len(directions):
                continue
            expected_y, expected_x = route[index]
            if (
                final.map_id != MapId.PALLET_TOWN
                or final.player_x != expected_x
                or final.player_y != expected_y
            ):
                raise PalletRouteProbeError(
                    f"live route diverged at computed step {index}: "
                    f"expected ({expected_y}, {expected_x})"
                )
            verified_intermediate += 1

        _wait(executor, timing.transition_wait_frames)
        final = reader.read()
        if final.map_id != MapId.OAKS_LAB:
            raise PalletRouteProbeError(
                "the final computed movement did not enter Oak's Lab"
            )
        frames_executed = emulator.frame_count
        actions_executed = executor.actions_executed
        controller_released = not emulator.pressed_buttons

    after = _adjacent_artifacts(rom_path)
    artifacts_unchanged = before == after
    if not artifacts_unchanged:
        raise PalletRouteProbeError("the no-save probe changed a ROM-adjacent artifact")

    payload = {
        "schema": "pallet-cartridge-route-probe-v1",
        "recorded_on": args.recorded_on,
        "status": "ok",
        "rom": fingerprint.public_dict(),
        "precondition": (
            "The existing qualified opening corridors established clean power-on and "
            "the stable Pallet Town state outside Red's house."
        ),
        "authority_under_test": (
            "The cartridge map graph selected Oak's Lab, the decoded terrain computed "
            "the Pallet segment, and live emulator memory checked every intermediate "
            "coordinate plus the final map transition."
        ),
        "start_yx": list(route[0]),
        "goal_warp_yx": list(route[-1]),
        "computed_coordinates_yx": [list(step) for step in route],
        "movement_steps": len(directions),
        "verified_intermediate_coordinates": verified_intermediate,
        "final_map": {"id": int(final.map_id), "name": MapId(final.map_id).name},
        "frames_executed": frames_executed,
        "actions_executed": actions_executed,
        "controller_released": controller_released,
        "rom_adjacent_artifacts_unchanged": artifacts_unchanged,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {args.out}: {len(directions)} computed movements, "
        f"{verified_intermediate} intermediate coordinates verified, entered Oak's Lab"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
