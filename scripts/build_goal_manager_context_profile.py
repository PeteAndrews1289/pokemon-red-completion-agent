#!/usr/bin/env python3
"""Build one finite, canonical private profile for a materialized Red context."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.observation import ItemId, MapId
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfileError,
    RedGoalMechanic,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_MODES = (
    "story",
    "mansion",
    "exploration",
    "development",
    "mart",
    "pc",
    "blocked-movement",
    "damaged-field",
    "damaged-center",
    "evolved-team",
)


class GoalManagerProfileBuildError(RuntimeError):
    """Raised when a requested finite template is incomplete or over-broad."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=_MODES, required=True)
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--map-id", type=int)
    parser.add_argument("--player-x", type=int)
    parser.add_argument("--player-y", type=int)
    parser.add_argument("--source-id", default="wild:PokemonMansion1F:grass")
    parser.add_argument("--label", default="Pokemon Mansion 1F context corridor")
    parser.add_argument(
        "--forward-direction",
        action="append",
        choices=("up", "right", "down", "left"),
    )
    parser.add_argument("--starting-endpoint", choices=("south", "north"), default="south")
    parser.add_argument("--maximum-legs", type=int, default=64)
    parser.add_argument("--maximum-seek-steps", type=int, default=256)
    parser.add_argument("--maximum-encounters", type=int, default=32)
    parser.add_argument("--great-ball-quantity", type=int, default=7)
    parser.add_argument("--target-box-index", type=int, default=1)
    return parser


def _empty(mechanic: RedGoalMechanic) -> tuple[GoalKind, RedGoalMechanic, Mapping[str, object]]:
    kinds = {
        RedGoalMechanic.MIDGAME_STORY: GoalKind.ADVANCE_STORY,
        RedGoalMechanic.BALANCED_TEAM: GoalKind.DEVELOP_TEAM,
        RedGoalMechanic.DIGLETT_EVOLUTION: GoalKind.EVOLVE_SPECIES,
        RedGoalMechanic.FIELD_RESTORE: GoalKind.RESTORE_TEAM,
        RedGoalMechanic.CENTER_RESTORE: GoalKind.RESTORE_TEAM,
        RedGoalMechanic.CONTROL_RECOVERY: GoalKind.RECOVER_CONTROL,
    }
    return kinds[mechanic], mechanic, {}


def _wild_parameters(args: argparse.Namespace) -> dict[str, object]:
    if (
        args.map_id is None
        or args.player_x is None
        or args.player_y is None
        or not args.forward_direction
    ):
        raise GoalManagerProfileBuildError(
            "wild context profiles require exact map, coordinate, and corridor directions"
        )
    return {
        "source_id": args.source_id,
        "label": args.label,
        "map_id": args.map_id,
        "player_x": args.player_x,
        "player_y": args.player_y,
        "forward_directions": args.forward_direction,
        "starting_endpoint": args.starting_endpoint,
        "maximum_legs": args.maximum_legs,
        "maximum_seek_steps": args.maximum_seek_steps,
        "maximum_encounters": args.maximum_encounters,
    }


def _providers(
    args: argparse.Namespace,
) -> tuple[tuple[GoalKind, RedGoalMechanic, Mapping[str, object]], ...]:
    story = _empty(RedGoalMechanic.MIDGAME_STORY)
    recovery = _empty(RedGoalMechanic.CONTROL_RECOVERY)
    if args.mode == "story":
        return (
            story,
            _empty(RedGoalMechanic.CENTER_RESTORE),
            recovery,
        )
    if args.mode in {"mansion", "damaged-field"}:
        wild = _wild_parameters(args)
        return (
            story,
            (
                GoalKind.ACQUIRE_SPECIES,
                RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
                wild,
            ),
            _empty(RedGoalMechanic.FIELD_RESTORE),
            recovery,
            (
                GoalKind.EXPLORE,
                RedGoalMechanic.WILD_CORRIDOR_DISCOVERY,
                wild,
            ),
        )
    if args.mode == "exploration":
        wild = _wild_parameters(args)
        return (
            story,
            _empty(RedGoalMechanic.FIELD_RESTORE),
            recovery,
            (
                GoalKind.EXPLORE,
                RedGoalMechanic.WILD_CORRIDOR_DISCOVERY,
                wild,
            ),
        )
    if args.mode == "mart":
        return (
            story,
            _empty(RedGoalMechanic.FIELD_RESTORE),
            (
                GoalKind.RESUPPLY,
                RedGoalMechanic.MART_RESUPPLY,
                {
                    "map_id": int(MapId.CINNABAR_MART),
                    "player_x": 2,
                    "player_y": 5,
                    "interaction_direction": "left",
                    "purchases": [
                        {
                            "absolute_index": 1,
                            "item_id": int(ItemId.GREAT_BALL),
                            "quantity": args.great_ball_quantity,
                            "unit_price": 600,
                        }
                    ],
                },
            ),
            recovery,
        )
    if args.mode == "pc":
        return (
            story,
            # The PC stance is ten tiles east of the nurse-facing Center
            # boundary.  Healing from here is therefore an observed bag-item
            # action, not a Pokemon Center interaction.
            _empty(RedGoalMechanic.FIELD_RESTORE),
            (
                GoalKind.MANAGE_STORAGE,
                RedGoalMechanic.BOX_SWITCH,
                {
                    "target_box_index": args.target_box_index,
                    "map_id": int(MapId.CINNABAR_POKECENTER),
                    "player_x": 13,
                    "player_y": 4,
                },
            ),
            recovery,
        )
    if args.mode == "blocked-movement":
        return (
            story,
            _empty(RedGoalMechanic.CENTER_RESTORE),
            recovery,
        )
    if args.mode in {"damaged-center", "evolved-team"}:
        return (
            story,
            _empty(RedGoalMechanic.BALANCED_TEAM),
            _empty(RedGoalMechanic.DIGLETT_EVOLUTION),
            _empty(RedGoalMechanic.CENTER_RESTORE),
            recovery,
        )
    if args.mode == "development":
        return (
            story,
            _empty(RedGoalMechanic.BALANCED_TEAM),
            _empty(RedGoalMechanic.CENTER_RESTORE),
            recovery,
        )
    raise GoalManagerProfileBuildError("profile mode is unsupported")


def _destination(path: Path, profile_id: str) -> Path:
    resolved = path.resolve()
    if (
        resolved.name != f"{profile_id}.json"
        or resolved.is_relative_to(PROJECT_ROOT.resolve())
        or not resolved.parent.is_dir()
        or resolved.exists()
    ):
        raise GoalManagerProfileBuildError(
            "profile must use its new private external identity path"
        )
    return resolved


def _write_exclusive(destination: Path, payload: bytes) -> None:
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        with suppress(OSError):
            destination.unlink()
        raise


def _run(args: argparse.Namespace) -> dict[str, object]:
    destination = _destination(args.out, args.profile_id)
    payload = build_red_goal_context_profile_payload(
        profile_id=args.profile_id,
        providers=_providers(args),
    )
    profile = parse_red_goal_context_profile(payload)
    _write_exclusive(destination, payload)
    return {**profile.public_dict(), "status": "created"}


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        summary = _run(args)
    except (
        GoalManagerProfileBuildError,
        RedGoalContextProfileError,
        OSError,
    ):
        parser.error("Goal-manager profile build failed closed; private paths were withheld.")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
