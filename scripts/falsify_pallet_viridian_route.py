"""Try to disprove a fully composed Pallet-to-Viridian-Center route live.

The qualified opening and Oak's-errand teachers establish a post-Pokédex state
and exit the lab. From the resulting Pallet coordinate onward, no authored
corridor chooses the route: cartridge map headers, connection geometry, warp
indices, terrain and traversal rules produce every movement and arrival.

Usage::

    POKEMON_RED_ROM=<path> python scripts/falsify_pallet_viridian_route.py \
        --out docs/evidence/<name>.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.actions import MacroAction, MacroActionKind  # noqa: E402
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING  # noqa: E402
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    committed_source_bundle_sha256,
    working_source_bundle_sha256,
)
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.executor import CountingExecutor, FrameSafeExecutor  # noqa: E402
from pokemon_red_completion.gen1_maps import (  # noqa: E402
    macro_graph_from_nodes,
    map_graph,
)
from pokemon_red_completion.gen1_terrain import walkable_world  # noqa: E402
from pokemon_red_completion.gen1_traversal import (  # noqa: E402
    local_graph,
    map_object_events,
    traversal_rules,
)
from pokemon_red_completion.global_router import find_macro_path  # noqa: E402
from pokemon_red_completion.observation import MapId, PokemonRedStateReader  # noqa: E402
from pokemon_red_completion.opening import run_opening_chapter  # noqa: E402
from pokemon_red_completion.pewter import (  # noqa: E402
    DEFAULT_PEWTER_TIMING,
    LAB_TO_PALLET_DIRECTIONS,
)
from pokemon_red_completion.play import (  # noqa: E402
    DEFAULT_QUALIFIED_PLAY_TIMING,
    _expect_position,
    _move,
    _wait,
    run_oaks_errand_chapter,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    detect_source_identity,
    require_clean_source,
)
from pokemon_red_completion.rom import resolve_rom_path, verify_rom  # noqa: E402
from pokemon_red_completion.route_1_wild import (  # noqa: E402
    Route1WildFleeEvidence,
    move_route_1_with_wild_flees,
)
from pokemon_red_completion.route_plan import RoutePlan, compose_route  # noqa: E402


class PalletViridianRouteProbeError(RuntimeError):
    """Raised when live play disagrees with the composed route."""


def _artifact_identity(path: Path) -> tuple[bool, str | None]:
    if not path.exists():
        return False, None
    return True, hashlib.sha256(path.read_bytes()).hexdigest()


def _adjacent_artifacts(rom_path: Path) -> tuple[tuple[bool, str | None], ...]:
    return tuple(
        _artifact_identity(Path(f"{rom_path}{suffix}"))
        for suffix in (".ram", ".rtc", ".state")
    )


def _public_plan(plan: RoutePlan) -> dict[str, object]:
    return {
        "maps": [MapId(map_id).name for map_id in plan.macro_path.maps],
        "map_ids": list(plan.macro_path.maps),
        "start_yx": list(plan.start_at),
        "terminal_yx": list(plan.terminal_at),
        "actions": list(plan.actions),
        "segments": [
            {
                "source_map": MapId(segment.source_map).name,
                "source_map_id": segment.source_map,
                "target_map": MapId(segment.target_map).name,
                "target_map_id": segment.target_map,
                "approach_coordinates_yx": [
                    list(coordinate) for coordinate in segment.approach.coordinates
                ],
                "actions": list(segment.actions),
                "transition": {
                    "exit_yx": list(segment.transition.exit_at),
                    "arrival_yx": list(segment.transition.arrival_at),
                    "action": segment.transition.action,
                    "action_in_approach": segment.transition_action_in_approach,
                },
            }
            for segment in plan.segments
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--recorded-on", default=date.today().isoformat())
    args = parser.parse_args(argv)

    rom_path = resolve_rom_path(args.rom)
    fingerprint = verify_rom(rom_path)
    source = detect_source_identity(PROJECT_ROOT, include_untracked=False)
    require_clean_source(source)
    if source.git_commit is None:  # pragma: no cover - established above
        raise PalletViridianRouteProbeError("the source commit is unavailable")
    source_bundle = committed_source_bundle_sha256(
        PROJECT_ROOT,
        revision=source.git_commit,
    )
    if working_source_bundle_sha256(PROJECT_ROOT) != source_bundle:
        raise PalletViridianRouteProbeError("the executable source differs from its commit")

    rom = rom_path.read_bytes()
    maps = map_graph(rom)
    macro = macro_graph_from_nodes(maps)
    world = walkable_world(rom)
    rules = traversal_rules(rom, maps)
    macro_path = find_macro_path(
        macro,
        MapId.PALLET_TOWN.value,
        MapId.VIRIDIAN_POKECENTER.value,
    )
    local_graphs = {
        map_id: local_graph(
            world[map_id],
            rules,
            blocked={event.at for event in map_object_events(rom, {map_id})},
        )
        for map_id in macro_path.maps[:-1]
    }
    start_yx = (12, 12)
    plan = compose_route(macro, macro_path, local_graphs, start_yx)
    before_artifacts = _adjacent_artifacts(rom_path)

    timing = DEFAULT_PEWTER_TIMING
    with PyBoyAdapter(rom_path) as emulator:
        controller = FrameSafeExecutor(
            emulator,
            DEFAULT_NEW_GAME_TIMING.controller_timing(),
        )
        opening = run_opening_chapter(
            rom_path,
            _emulator=emulator,
            _executor=controller,
        )
        if not opening.passed:
            raise PalletViridianRouteProbeError("the qualified opening precondition failed")
        reader = PokemonRedStateReader(emulator)
        executor = CountingExecutor(controller)
        errand = run_oaks_errand_chapter(
            emulator,
            reader,
            executor,
            timing=DEFAULT_QUALIFIED_PLAY_TIMING,
        )
        if not errand.passed:
            raise PalletViridianRouteProbeError("the verified Pokédex precondition failed")

        _move(executor, reader, LAB_TO_PALLET_DIRECTIONS, "composed-route lab exit")
        _wait(executor, timing.transition_wait_frames)
        _expect_position(
            reader.read(),
            MapId.PALLET_TOWN,
            start_yx[1],
            start_yx[0],
            "composed-route Pallet start",
        )
        actions_before_plan = executor.actions_executed
        wild_flees: tuple[Route1WildFleeEvidence, ...] = ()
        movement_retries = 0
        live_arrivals: list[dict[str, object]] = []

        for segment in plan.segments:
            actions = segment.actions
            if segment.source_map == MapId.ROUTE_1.value:
                _wait(executor, timing.route_1_seed_wait_frames)
                _, wild_flees, movement_retries = move_route_1_with_wild_flees(
                    executor,
                    reader,
                    actions,
                    "cartridge-composed Route 1 segment",
                    maximum_flees=timing.max_route_1_wild_flees,
                    stabilization_frames=timing.route_1_wild_exit_stabilization_frames,
                    maximum_step_attempts=timing.max_route_1_step_attempts,
                    step_retry_wait_frames=timing.route_1_step_retry_wait_frames,
                    error_type=PalletViridianRouteProbeError,
                )
            else:
                for index, action in enumerate(actions, start=1):
                    executor.execute(MacroAction(MacroActionKind.MOVE, action))
                    if index == len(actions):
                        continue
                    expected_y, expected_x = segment.approach.coordinates[index]
                    observed = reader.read()
                    if (
                        observed.map_id != segment.source_map
                        or observed.battle_state != 0
                        or (observed.player_y, observed.player_x)
                        != (expected_y, expected_x)
                    ):
                        raise PalletViridianRouteProbeError(
                            f"map {segment.source_map} diverged at composed action {index}"
                        )

            _wait(executor, timing.transition_wait_frames)
            arrived = reader.read()
            expected_y, expected_x = segment.transition.arrival_at
            if (
                arrived.map_id != segment.target_map
                or arrived.battle_state != 0
                or (arrived.player_y, arrived.player_x) != (expected_y, expected_x)
            ):
                raise PalletViridianRouteProbeError(
                    f"transition {segment.source_map}->{segment.target_map} missed "
                    f"its decoded arrival {(expected_y, expected_x)}"
                )
            live_arrivals.append(
                {
                    "map": MapId(segment.target_map).name,
                    "map_id": segment.target_map,
                    "yx": [arrived.player_y, arrived.player_x],
                }
            )

        final = reader.read()
        plan_actions_executed = executor.actions_executed - actions_before_plan
        frames_executed = emulator.frame_count
        controller_released = not emulator.pressed_buttons

    artifacts_unchanged = before_artifacts == _adjacent_artifacts(rom_path)
    if not artifacts_unchanged:
        raise PalletViridianRouteProbeError(
            "the no-save probe changed a ROM-adjacent artifact"
        )

    payload = {
        "schema": "pallet-viridian-composed-route-probe-v1",
        "recorded_on": args.recorded_on,
        "status": "ok",
        "rom": fingerprint.public_dict(),
        "source": source.public_dict(),
        "executable_source_bundle_sha256": source_bundle,
        "precondition": (
            "Qualified teachers established a clean-power-on post-Pokédex run and "
            "exited Oak's Lab to the verified Pallet coordinate (12, 12)."
        ),
        "authority_under_test": (
            "From the Pallet start onward, cartridge map headers, exact connection "
            "geometry, destination warp indices, terrain and traversal rules supplied "
            "the complete multi-map route. Live memory checked every non-wild local "
            "step and every cross-map arrival; the bounded Route 1 runtime checked "
            "movement consumption and incidental wild exits."
        ),
        "plan": _public_plan(plan),
        "live_arrivals": live_arrivals,
        "wild_flees": [flee.public_dict() for flee in wild_flees],
        "movement_retries": movement_retries,
        "final_map": {"id": int(final.map_id), "name": MapId(final.map_id).name},
        "final_yx": [final.player_y, final.player_x],
        "planned_actions": len(plan.actions),
        "actions_executed_during_plan": plan_actions_executed,
        "frames_executed": frames_executed,
        "controller_released": controller_released,
        "rom_adjacent_artifacts_unchanged": artifacts_unchanged,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {args.out}: {len(plan.actions)} composed actions, "
        f"{len(wild_flees)} wild flees, entered Viridian Pokémon Center"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
