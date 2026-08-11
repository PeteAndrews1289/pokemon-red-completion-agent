"""Try to disprove bounded live Strength planning on Victory Road 1F.

An authenticated post-Giovanni capture supplies the origin. The existing
qualified teacher reaches Victory Road but is stopped before its hand-authored
boulder route. From there this probe reads every live boulder, decodes current
terrain, computes a bounded player-and-boulder state search, activates Strength
through the field compiler, and executes each held push pulse only when the
engine's resulting boulder flag and exact RAM state are acknowledged.

The capture and ROM are private inputs and never appear in the public receipt.
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
from pokemon_red_completion.gen1_field_moves import (  # noqa: E402
    Gen1FieldMovePort,
    Gen1StrengthReceipt,
)
from pokemon_red_completion.gen1_maps import map_graph  # noqa: E402
from pokemon_red_completion.gen1_strength import (  # noqa: E402
    Gen1StrengthExecutor,
    StrengthGoal,
    StrengthState,
    plan_strength,
)
from pokemon_red_completion.gen1_terrain import (  # noqa: E402
    terrain_from_blocks,
    tilesets,
    water_tilesets,
)
from pokemon_red_completion.gen1_traversal import (  # noqa: E402
    map_object_events,
    traversal_rules,
)
from pokemon_red_completion.lavender import (  # noqa: E402
    DEFAULT_LAVENDER_TIMING,
    _use_bag_item,
)
from pokemon_red_completion.observation import (  # noqa: E402
    EventFlag,
    ItemId,
    MapId,
    PokemonRedStateReader,
    event_flag_is_set,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    detect_source_identity,
    require_clean_source,
)
from pokemon_red_completion.rom import verify_rom  # noqa: E402
from pokemon_red_completion.victory_road import (  # noqa: E402
    VictoryRoadProgress,
    run_victory_road_chapter,
)

REQUIRED_CAPTURE_OBJECTIVES = frozenset({"defeat_giovanni", "obtain_strength"})
VICTORY_ROAD_1F_SWITCH_YX = (13, 17)


class VictoryRoadStrengthProbeError(RuntimeError):
    """Raised when the live Strength probe cannot prove its contract."""


class _ReachedStrengthBoundary(RuntimeError):
    pass


def _artifact_identity(path: Path) -> tuple[bool, str | None]:
    if not path.exists():
        return False, None
    return True, hashlib.sha256(path.read_bytes()).hexdigest()


def _adjacent_artifacts(rom_path: Path) -> tuple[tuple[bool, str | None], ...]:
    return tuple(
        _artifact_identity(Path(f"{rom_path}{suffix}"))
        for suffix in (".ram", ".rtc", ".state")
    )


def _stop_at_strength_boundary(progress: VictoryRoadProgress) -> None:
    if progress.checkpoint_id == "badge_corridor":
        raise _ReachedStrengthBoundary


def _public_state(state: StrengthState) -> dict[str, object]:
    return {
        "player_yx": list(state.player_at),
        "boulders": [
            {"sprite_index": item.sprite_index, "yx": list(item.at)}
            for item in state.boulders
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--envelope", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--recorded-on", default=date.today().isoformat())
    args = parser.parse_args(argv)

    fingerprint = verify_rom(args.rom)
    envelope_path = args.envelope or Path(f"{args.state}.json")
    capture = load_captured_progress(envelope_path, state_path=args.state)
    missing = REQUIRED_CAPTURE_OBJECTIVES.difference(capture.verified_objective_ids)
    if missing:
        raise VictoryRoadStrengthProbeError(
            f"capture lacks verified objectives {sorted(missing)}"
        )

    source = detect_source_identity(PROJECT_ROOT, include_untracked=False)
    require_clean_source(source)
    if source.git_commit is None:  # pragma: no cover - established above
        raise VictoryRoadStrengthProbeError("the source commit is unavailable")
    source_bundle = committed_source_bundle_sha256(PROJECT_ROOT, revision=source.git_commit)
    if working_source_bundle_sha256(PROJECT_ROOT) != source_bundle:
        raise VictoryRoadStrengthProbeError("the executable source differs from its commit")

    rom = args.rom.read_bytes()
    maps = map_graph(rom)
    rules = traversal_rules(rom, maps)
    sets = tilesets(rom)
    surf_tilesets = water_tilesets(rom)
    object_events = map_object_events(rom, {int(MapId.VICTORY_ROAD_1F)})
    conservative_non_boulder_occupancy = frozenset(
        event.at for event in object_events if not event.is_boulder
    )
    before_artifacts = _adjacent_artifacts(args.rom)

    with PyBoyAdapter(args.rom) as emulator:
        emulator.load_state(args.state)
        reader = PokemonRedStateReader(emulator)
        controller = FrameSafeExecutor(
            emulator,
            DEFAULT_NEW_GAME_TIMING.controller_timing(),
        )
        try:
            run_victory_road_chapter(
                emulator,
                reader,
                controller,
                progress=_stop_at_strength_boundary,
            )
        except _ReachedStrengthBoundary:
            pass
        else:
            raise VictoryRoadStrengthProbeError(
                "qualified teacher did not expose the pre-Strength boundary"
            )

        boundary = reader.read()
        boundary_yx = boundary.player_y, boundary.player_x
        if (
            boundary.map_id != MapId.VICTORY_ROAD_1F
            or boundary_yx != (17, 8)
            or boundary.battle_state != 0
            or not reader.read_input_readiness().ready
        ):
            raise VictoryRoadStrengthProbeError(
                f"Victory Road boundary changed: map={boundary.map_id}, yx={boundary_yx}"
            )

        counted = CountingExecutor(controller)
        _use_bag_item(
            counted,
            reader,
            emulator,
            DEFAULT_LAVENDER_TIMING,
            ItemId.MAX_REPEL,
        )
        field = Gen1FieldMovePort(counted, reader, emulator)
        activation_result = field.execute(
            MacroAction(MacroActionKind.FIELD_MOVE, "strength:activate")
        )
        if not isinstance(activation_result, Gen1StrengthReceipt):
            raise VictoryRoadStrengthProbeError(
                "Strength activation returned an unexpected receipt"
            )
        activation = activation_result
        if len(field.strength_receipts) != 1:
            raise VictoryRoadStrengthProbeError("Strength activation lacked one receipt")

        raw_before = reader.read()
        if raw_before.player_y is None or raw_before.player_x is None:
            raise VictoryRoadStrengthProbeError("Strength boundary lost its position")
        blocks = reader.read_current_map_blocks()
        if blocks.map_id != MapId.VICTORY_ROAD_1F:
            raise VictoryRoadStrengthProbeError("live block buffer changed maps")
        terrain = terrain_from_blocks(
            rom,
            int(MapId.VICTORY_ROAD_1F),
            blocks.rows,
            sets,
            water_set_ids=surf_tilesets,
        )
        initial_state = StrengthState.from_observation(
            (raw_before.player_y, raw_before.player_x),
            reader.read_current_strength_boulders(),
        )
        plan = plan_strength(
            terrain,
            rules,
            initial_state,
            StrengthGoal(VICTORY_ROAD_1F_SWITCH_YX),
            raw_before,
            blocked=conservative_non_boulder_occupancy,
            max_states=100_000,
        )
        execution = Gen1StrengthExecutor(counted, reader, emulator).execute(plan)
        final = reader.read()
        switch_set = event_flag_is_set(
            final.event_flags,
            int(EventFlag.VICTORY_ROAD_1F_BOULDER_ON_SWITCH),
        )
        if not execution.passed or not switch_set or not reader.read_input_readiness().ready:
            raise VictoryRoadStrengthProbeError(
                "planned Strength execution did not settle the Victory Road switch"
            )
        frames_executed = emulator.frame_count
        controller_released = not emulator.pressed_buttons

    if before_artifacts != _adjacent_artifacts(args.rom):
        raise VictoryRoadStrengthProbeError("the no-save probe changed a ROM-adjacent artifact")

    payload = {
        "schema": "victory-road-strength-state-search-probe-v1",
        "recorded_on": args.recorded_on,
        "status": "ok",
        "rom": fingerprint.public_dict(),
        "source": {
            "git_commit": source.git_commit,
            "source_bundle_sha256": source_bundle,
        },
        "capture": {
            "checkpoint_id": capture.checkpoint_id,
            "required_verified_objectives": sorted(REQUIRED_CAPTURE_OBJECTIVES),
        },
        "boundary": {
            "map_id": int(MapId.VICTORY_ROAD_1F),
            "player_yx": [17, 8],
            "ready": True,
        },
        "activation": {
            "party_index": activation.party_index,
            "submenu_row": activation.submenu_row,
            "confirmation_count": activation.confirmation_count,
            "already_active": activation.already_active,
        },
        "planner": {
            "algorithm": "bounded_dijkstra_player_and_all_boulders",
            "goal_boulder_yx": list(VICTORY_ROAD_1F_SWITCH_YX),
            "max_states": 100_000,
            "explored_states": plan.explored_states,
            "cost": plan.cost,
            "steps": len(plan.steps),
            "walks": sum(step.kind == "walk" for step in plan.steps),
            "pushes": sum(step.kind == "push" for step in plan.steps),
            "push_engine_attempt_cost": 2,
            "initial": _public_state(plan.states[0]),
            "terminal": _public_state(plan.states[-1]),
        },
        "execution": {
            "passed": execution.passed,
            "acknowledged_steps": execution.acknowledged_steps,
            "controller_inputs": execution.controller_inputs,
            "wait_actions": execution.wait_actions,
            "push_receipts": [
                {
                    "ordinal": receipt.ordinal,
                    "direction": receipt.direction.value,
                    "boulder_index": receipt.boulder_index,
                    "player_before_yx": list(receipt.player_before),
                    "player_after_yx": list(receipt.player_after),
                    "boulder_before_yx": list(receipt.boulder_before),
                    "boulder_after_yx": list(receipt.boulder_after),
                    "boulder_removed": receipt.boulder_removed,
                    "player_stationary": receipt.player_stationary,
                    "boulder_dust_observed": receipt.boulder_dust_observed,
                    "pushed_flag_observed": receipt.pushed_flag_observed,
                    "engine_acknowledged": receipt.engine_acknowledged,
                    "engine_attempt_cost": receipt.engine_attempt_cost,
                }
                for receipt in execution.pushes
            ],
            "switch_event_set": switch_set,
            "frames_executed": frames_executed,
            "actions_executed_after_boundary": counted.actions_executed,
            "controller_released": controller_released,
        },
        "rom_adjacent_artifacts_unchanged": True,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"Strength plan passed: {len(plan.steps)} steps, "
        f"{len(execution.pushes)} pushes, {plan.explored_states} states"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
