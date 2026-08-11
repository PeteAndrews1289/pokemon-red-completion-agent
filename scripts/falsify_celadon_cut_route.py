"""Try to disprove a staged cartridge-computed Cut crossing in live Red.

An authenticated private Celadon capture supplies only the starting game
state. The probe exits the Pokémon Center, reads the city's mutable map blocks
from RAM, chooses a reachable tree using cartridge terrain and Cut swap data,
and walks only to the cutting stance. It executes Cut through the bounded field
menu compiler, requires one exact live block replacement plus restored input,
rebuilds terrain from RAM, and only then plans and executes the crossing.

The capture and ROM are private inputs and never appear in the public receipt.

Usage::

    python scripts/falsify_celadon_cut_route.py \
        --rom <red.gb> --state <celadon.state> --out <receipt.json>
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
from pokemon_red_completion.captured_progress import load_captured_progress  # noqa: E402
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    committed_source_bundle_sha256,
    working_source_bundle_sha256,
)
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.executor import CountingExecutor, FrameSafeExecutor  # noqa: E402
from pokemon_red_completion.gen1_cut import (  # noqa: E402
    CUT_PASSAGE_TILES,
    CutTraversalCandidate,
    CutTraversalError,
    plan_cut_candidate,
)
from pokemon_red_completion.gen1_field_moves import Gen1FieldMovePort  # noqa: E402
from pokemon_red_completion.gen1_maps import (  # noqa: E402
    macro_graph_from_nodes,
    map_graph,
)
from pokemon_red_completion.gen1_route_runtime import Gen1TraversalObserver  # noqa: E402
from pokemon_red_completion.gen1_terrain import (  # noqa: E402
    Terrain,
    terrain_from_blocks,
    tilesets,
    walkable_world,
    water_tilesets,
)
from pokemon_red_completion.gen1_traversal import (  # noqa: E402
    LAND_MODE,
    TraversalRules,
    local_graph,
    traversal_rules,
)
from pokemon_red_completion.global_router import MacroGraph  # noqa: E402
from pokemon_red_completion.local_router import (  # noqa: E402
    LocalGraph,
    LocalRouterError,
    find_local_path,
)
from pokemon_red_completion.observation import MapId, PokemonRedStateReader  # noqa: E402
from pokemon_red_completion.provenance import (  # noqa: E402
    detect_source_identity,
    require_clean_source,
)
from pokemon_red_completion.rom import verify_rom  # noqa: E402
from pokemon_red_completion.route_executor import (  # noqa: E402
    ReplanRequest,
    RouteExecutionLimits,
    RouteExecutionReport,
    execute_route,
)
from pokemon_red_completion.route_plan import RoutePlan, plan_route  # noqa: E402

REQUIRED_CAPTURE_OBJECTIVES = frozenset({"defeat_misty", "obtain_cut"})


class CeladonCutProbeError(RuntimeError):
    """Raised when live play falsifies the staged Cut contract."""


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
        "map_ids": list(plan.macro_path.maps),
        "start_yx": list(plan.start_at),
        "terminal_yx": list(plan.terminal_at),
        "steps": [
            {
                "source_map_id": step.source_map,
                "source_yx": list(step.source_at),
                "action_kind": step.action_kind.value,
                "action": step.action,
                "expected_map_id": step.expected_map,
                "expected_yx": list(step.expected_at),
                "kind": step.kind,
            }
            for step in plan.steps
        ],
    }


def _public_execution(report: RouteExecutionReport) -> dict[str, object]:
    return {
        "passed": report.passed,
        "movement_requests": report.movement_requests,
        "wait_actions": report.wait_actions,
        "acknowledged_steps": len(report.executed_steps),
        "interruption_count": len(report.interruptions),
        "replan_count": len(report.replans),
        "terminal_map_id": report.terminal.map_id,
        "terminal_yx": list(report.terminal.at),
        "terminal_ready": report.terminal.ready,
    }


def _replanner(macro: MacroGraph, local_graphs: dict[int, LocalGraph]):
    def replan(request: ReplanRequest) -> RoutePlan:
        return plan_route(
            macro,
            local_graphs,
            request.current.map_id,
            request.current.at,
            request.goal_map,
            blocked=request.blocked,
            start_mode=request.current.mode,
            goal_at=request.goal_at,
            goal_mode=LAND_MODE,
        )

    return replan


def _nearest_cut_candidate(
    rom: bytes,
    terrain: Terrain,
    rules: TraversalRules,
    sets,
    start: tuple[int, int],
    raw,
    *,
    water_set_ids: frozenset[int],
) -> CutTraversalCandidate:
    candidates: list[CutTraversalCandidate] = []
    eligible = CUT_PASSAGE_TILES.get(terrain.tileset, frozenset())
    for y, row in enumerate(terrain.tiles):
        for x, tile in enumerate(row):
            if tile not in eligible:
                continue
            try:
                candidate = plan_cut_candidate(
                    rom,
                    terrain,
                    rules,
                    sets,
                    start,
                    (y, x),
                    raw,
                    water_set_ids=water_set_ids,
                )
            except CutTraversalError:
                continue
            candidates.append(candidate)
    if not candidates:
        raise CeladonCutProbeError("no reachable staged Celadon Cut candidate was found")
    return min(
        candidates,
        key=lambda candidate: (
            candidate.predicted_cost,
            candidate.target_at,
            candidate.source_at,
        ),
    )


def _one_block_delta(
    before: tuple[tuple[int, ...], ...],
    after: tuple[tuple[int, ...], ...],
) -> tuple[tuple[int, int], int, int]:
    if len(before) != len(after) or any(
        len(before_row) != len(after_row)
        for before_row, after_row in zip(before, after, strict=True)
    ):
        raise CeladonCutProbeError("Cut changed the live block-grid dimensions")
    changed = [
        ((y, x), before_id, after_id)
        for y, (before_row, after_row) in enumerate(zip(before, after, strict=True))
        for x, (before_id, after_id) in enumerate(zip(before_row, after_row, strict=True))
        if before_id != after_id
    ]
    if len(changed) != 1:
        raise CeladonCutProbeError(f"Cut changed {len(changed)} live blocks instead of one")
    return changed[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--envelope", type=Path, default=None, help="defaults to <state>.json")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--recorded-on", default=date.today().isoformat())
    args = parser.parse_args(argv)

    fingerprint = verify_rom(args.rom)
    envelope_path = args.envelope or Path(f"{args.state}.json")
    capture = load_captured_progress(envelope_path, state_path=args.state)
    missing = REQUIRED_CAPTURE_OBJECTIVES.difference(capture.verified_objective_ids)
    if missing:
        raise CeladonCutProbeError(f"capture lacks verified objectives {sorted(missing)}")

    source = detect_source_identity(PROJECT_ROOT, include_untracked=False)
    require_clean_source(source)
    if source.git_commit is None:  # pragma: no cover - established above
        raise CeladonCutProbeError("the source commit is unavailable")
    source_bundle = committed_source_bundle_sha256(PROJECT_ROOT, revision=source.git_commit)
    if working_source_bundle_sha256(PROJECT_ROOT) != source_bundle:
        raise CeladonCutProbeError("the executable source differs from its commit")

    rom = args.rom.read_bytes()
    maps = map_graph(rom)
    macro = macro_graph_from_nodes(maps)
    world = walkable_world(rom)
    rules = traversal_rules(rom, maps)
    sets = tilesets(rom)
    surf_tilesets = water_tilesets(rom)
    local_graphs = {
        map_id: local_graph(terrain, rules) for map_id, terrain in world.items()
    }
    city = MapId.CELADON_CITY.value
    center = MapId.CELADON_POKECENTER.value
    before_artifacts = _adjacent_artifacts(args.rom)
    limits = RouteExecutionLimits(
        max_step_attempts=8,
        max_readiness_waits=16,
        max_interruptions=1,
        max_replans=6,
        replan_after_unchanged=2,
        retry_wait_frames=24,
        readiness_wait_frames=24,
        transition_settle_frames=180,
    )

    with PyBoyAdapter(args.rom) as emulator:
        emulator.load_state(args.state)
        reader = PokemonRedStateReader(emulator)
        initial = reader.read()
        if (
            initial.map_id != center
            or (initial.player_y, initial.player_x) != (3, 3)
            or initial.battle_state != 0
            or not reader.read_input_readiness().ready
        ):
            raise CeladonCutProbeError("capture missed the stable Celadon Center boundary")

        controller = FrameSafeExecutor(
            emulator,
            DEFAULT_NEW_GAME_TIMING.controller_timing(),
        )
        counted = CountingExecutor(controller)
        swaps = {swap.before: swap.after for swap in rules.cut_block_swaps}
        field_actions = Gen1FieldMovePort(
            counted,
            reader,
            emulator,
            cut_block_swaps=swaps,
        )
        observer = Gen1TraversalObserver(reader)
        replan = _replanner(macro, local_graphs)

        exit_plan = plan_route(
            macro,
            local_graphs,
            center,
            (3, 3),
            city,
            start_mode=LAND_MODE,
            last_outside=city,
        )
        exit_report = execute_route(
            exit_plan,
            field_actions,
            observer,
            replanner=replan,
            limits=limits,
        )
        city_start = exit_report.terminal.at
        before_raw = reader.read()
        blocks_before = reader.read_current_map_blocks()
        if blocks_before.map_id != city or before_raw.map_id != city:
            raise CeladonCutProbeError("live block read did not belong to Celadon City")
        terrain_before = terrain_from_blocks(
            rom,
            city,
            blocks_before.rows,
            sets,
            water_set_ids=surf_tilesets,
        )
        local_graphs[city] = local_graph(terrain_before, rules)
        candidate = _nearest_cut_candidate(
            rom,
            terrain_before,
            rules,
            sets,
            city_start,
            before_raw,
            water_set_ids=surf_tilesets,
        )

        approach_plan = plan_route(
            macro,
            local_graphs,
            city,
            city_start,
            city,
            start_mode=LAND_MODE,
            goal_at=candidate.source_at,
            goal_mode=LAND_MODE,
        )
        approach_report = execute_route(
            approach_plan,
            field_actions,
            observer,
            replanner=replan,
            limits=limits,
        )
        if approach_report.terminal.at != candidate.source_at:
            raise CeladonCutProbeError("approach did not reach the selected cutting stance")

        field_actions.execute(
            MacroAction(
                MacroActionKind.FIELD_MOVE,
                f"cut:{candidate.direction.value}",
            )
        )
        if len(field_actions.cut_receipts) != 1:
            raise CeladonCutProbeError("Cut produced no unique mutation receipt")
        cut_receipt = field_actions.cut_receipts[0]
        blocks_after = reader.read_current_map_blocks()
        observed_delta = _one_block_delta(blocks_before.rows, blocks_after.rows)
        terrain_after = terrain_from_blocks(
            rom,
            city,
            blocks_after.rows,
            sets,
            water_set_ids=surf_tilesets,
        )
        local_graphs[city] = local_graph(terrain_after, rules)
        try:
            observed_continuation = find_local_path(
                local_graphs[city],
                candidate.source_at,
                candidate.target_at,
                start_mode=LAND_MODE,
                goal_mode=LAND_MODE,
            )
        except LocalRouterError as error:
            raise CeladonCutProbeError("observed Cut mutation did not open its target") from error

        dy, dx = candidate.direction.delta
        beyond = candidate.target_at[0] + dy, candidate.target_at[1] + dx
        cross_goal = beyond if terrain_after.can_stand(*beyond) else candidate.target_at
        cross_plan = plan_route(
            macro,
            local_graphs,
            city,
            candidate.source_at,
            city,
            start_mode=LAND_MODE,
            goal_at=cross_goal,
            goal_mode=LAND_MODE,
        )
        if not cross_plan.steps or cross_plan.steps[0].expected_at != candidate.target_at:
            raise CeladonCutProbeError("post-Cut route did not cross the observed former tree")
        cross_report = execute_route(
            cross_plan,
            field_actions,
            observer,
            replanner=replan,
            limits=limits,
        )

        return_plan = plan_route(
            macro,
            local_graphs,
            city,
            cross_report.terminal.at,
            center,
            start_mode=LAND_MODE,
            goal_at=(3, 3),
            goal_mode=LAND_MODE,
        )
        return_report = execute_route(
            return_plan,
            field_actions,
            observer,
            replanner=replan,
            limits=limits,
        )
        final = reader.read()
        final_ready = reader.read_input_readiness().ready
        frames_executed = emulator.frame_count
        controller_released = not emulator.pressed_buttons

    if before_artifacts != _adjacent_artifacts(args.rom):
        raise CeladonCutProbeError("the no-save probe changed a ROM-adjacent artifact")
    if observed_delta != (candidate.block_at, candidate.before_block, candidate.after_block):
        raise CeladonCutProbeError("live block delta disagreed with the selected Cut candidate")
    if (
        cut_receipt.block_at != candidate.block_at
        or cut_receipt.block_before != candidate.before_block
        or cut_receipt.block_after != candidate.after_block
    ):
        raise CeladonCutProbeError("field receipt disagreed with the selected Cut candidate")
    if terrain_before.can_stand(*candidate.target_at):
        raise CeladonCutProbeError("selected Cut target was already standable")
    if not terrain_after.can_stand(*candidate.target_at):
        raise CeladonCutProbeError("observed Cut target remained unstandable")
    if terrain_after.tiles[candidate.target_at[0]][candidate.target_at[1]] != (
        cut_receipt.target_tile_after
    ):
        raise CeladonCutProbeError("rebuilt terrain disagreed with the observed front tile")
    if (
        final.map_id != center
        or (final.player_y, final.player_x) != (3, 3)
        or not final_ready
    ):
        raise CeladonCutProbeError("probe did not return to the stable Celadon Center boundary")

    payload = {
        "schema": "celadon-staged-cut-route-probe-v1",
        "recorded_on": args.recorded_on,
        "status": "ok",
        "rom": fingerprint.public_dict(),
        "source": source.public_dict(),
        "executable_source_bundle_sha256": source_bundle,
        "private_capture_precondition": {
            "authenticated": True,
            "checkpoint_id": capture.checkpoint_id,
            "checkpoint_label": capture.checkpoint_label,
            "required_verified_objectives": sorted(REQUIRED_CAPTURE_OBJECTIVES),
        },
        "authority_under_test": (
            "Cartridge terrain and Cut block-swap data selected a cutting stance. Live RAM "
            "supplied badge, living move holder, current block grid, tile in front, exact "
            "mutation, restored readiness and every coordinate acknowledgement. The crossing "
            "was planned only from the observed post-Cut grid."
        ),
        "selection": {
            "city_start_yx": list(city_start),
            "source_yx": list(candidate.source_at),
            "target_yx": list(candidate.target_at),
            "direction": candidate.direction.value,
            "block_yx": list(candidate.block_at),
            "predicted_approach_steps": len(candidate.approach.edges),
            "predicted_continuation_steps": len(candidate.predicted_continuation.edges),
            "prediction_used_as_execution_authority": False,
        },
        "mutation": {
            "block_before": candidate.before_block,
            "block_after": candidate.after_block,
            "target_tile_before": cut_receipt.target_tile_before,
            "target_tile_after": cut_receipt.target_tile_after,
            "changed_block_count": 1,
            "player_stayed_at_source": True,
            "input_ready_after_mutation": True,
            "target_standable_before": False,
            "target_standable_after": True,
            "observed_post_cut_path_yx": [
                list(coordinate) for coordinate in observed_continuation.coordinates
            ],
        },
        "cut_receipt": {
            "party_index": cut_receipt.party_index,
            "submenu_row": cut_receipt.submenu_row,
            "confirmation_count": cut_receipt.confirmation_count,
        },
        "plans": {
            "center_exit": _public_plan(exit_plan),
            "cut_approach": _public_plan(approach_plan),
            "observed_crossing": _public_plan(cross_plan),
            "center_return": _public_plan(return_plan),
        },
        "execution": {
            "center_exit": _public_execution(exit_report),
            "cut_approach": _public_execution(approach_report),
            "observed_crossing": _public_execution(cross_report),
            "center_return": _public_execution(return_report),
        },
        "final": {
            "map_id": int(final.map_id),
            "yx": [final.player_y, final.player_x],
            "ready": final_ready,
        },
        "actions_executed": counted.actions_executed,
        "frames_executed": frames_executed,
        "controller_released": controller_released,
        "rom_adjacent_artifacts_unchanged": True,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {args.out}: Cut {candidate.block_before:#04x}->{candidate.block_after:#04x} "
        f"at {candidate.block_at}, crossed {candidate.target_at}, returned to Celadon Center"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
