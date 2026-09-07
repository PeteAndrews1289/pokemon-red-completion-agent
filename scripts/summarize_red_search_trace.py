#!/usr/bin/env python3
"""Explain a retained search using verified observations, without replaying it.

This is diagnostic evidence only: no policy predictions, fitting or controller
access. Count transitions through the execution stream, not unique snapshots;
identical repeated encounters must not disappear through deduplication.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from pokemon_red_completion.private_artifacts import open_private_root


def _object(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("search diagnostic object is absent")
    return value


def summarize_trace(
    snapshots: Iterable[Mapping[str, Any]],
    executions: Iterable[Mapping[str, Any]],
) -> dict[str, object]:
    states: dict[str, Mapping[str, Any]] = {}
    for row in snapshots:
        identity = row["snapshot_sha256"]
        if not isinstance(identity, str) or identity in states:
            raise ValueError("search snapshot identity is absent or duplicated")
        states[identity] = _object(row["snapshot"])
    actions = frames = encounters = endings = movement = displacement = unknown = 0
    previous: str | None = None
    for row in executions:
        before_id, after_id = row["before_sha256"], row["after_sha256"]
        if before_id not in states or after_id not in states:
            raise ValueError("search execution references a missing snapshot")
        if previous is not None and before_id != previous:
            raise ValueError("search execution continuity differs")
        previous = after_id
        cost = row["frames"]
        if type(cost) is not int or cost < 0:
            raise ValueError("search execution frame cost differs")
        before = _object(states[before_id]["features"])
        after = _object(states[after_id]["features"])
        old_battle, new_battle = before["battle"], after["battle"]
        old_wild = isinstance(old_battle, Mapping) and old_battle.get("kind") == "wild"
        new_wild = isinstance(new_battle, Mapping) and new_battle.get("kind") == "wild"
        encounters += int(old_battle is None and new_wild)
        endings += int(old_wild and new_battle is None)
        if _object(row["action"])["kind"] == "move" and old_battle is None:
            movement += 1
            old_world, new_world = _object(before["world"]), _object(after["world"])
            old_position, new_position = old_world.get("position"), new_world.get("position")
            if not isinstance(old_position, Mapping) or not isinstance(new_position, Mapping):
                unknown += 1
            else:
                displacement += int(
                    old_position != new_position
                    or old_world.get("area_ref") != new_world.get("area_ref")
                )
        actions += 1
        frames += cost
    return {
        "schema": "pokemon.red.retained-search-diagnostic.v1",
        "recorded_actions": actions,
        "recorded_frames": frames,
        "wild_encounter_starts": encounters,
        "wild_battle_ends": endings,
        "overworld_movement_inputs": movement,
        "overworld_movements_with_displacement": displacement,
        "movement_inputs_missing_position": unknown,
        "controller_actions": 0,
        "model_queries": 0,
        "model_fits": 0,
        "snapshot_deduplication_is_encounter_count": False,
        "independent_evaluation": False,
        "private_path_fields": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-artifact-root", type=Path, required=True)
    parser.add_argument("--episode-id", required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--allow-same-device", action="store_true")
    args = parser.parse_args()
    root = open_private_root(
        args.private_artifact_root, repository_root=Path(__file__).resolve().parents[1],
        allow_same_device=args.allow_same_device,
    )
    episode = root.open_episode(args.episode_id)
    if episode.manifest_sha256 != args.expected_manifest_sha256:
        raise ValueError("search diagnostic episode manifest differs")
    report = summarize_trace(episode.iter_stream("snapshots"), episode.iter_stream("executions"))
    print(
        json.dumps({**report, "manifest_sha256": episode.manifest_sha256}, indent=2, sort_keys=True)
    )


if __name__ == "__main__":
    main()
