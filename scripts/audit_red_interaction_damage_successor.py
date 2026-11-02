"""Read-only independent audit of the stopped interaction-damage V1 packet."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path, PurePosixPath

import run_red_interaction_damage_successor as packet

old = packet.old


def _audit_source(plan: dict) -> None:
    commit = plan["source_commit"]
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("execution commit is not a full Git object ID")
    for name, expected in plan["source_hashes"].items():
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or path.suffix != ".py":
            raise ValueError("execution source path is invalid")
        blob = subprocess.check_output(["git", "show", f"{commit}:{name}"], cwd=packet.ROOT)
        if hashlib.sha256(blob).hexdigest() != expected:
            raise ValueError("execution source does not match its pinned commit")


def _audit_events(directory: Path, expected_terminal: str) -> int:
    previous = None
    paths = sorted((directory / "events").glob("event-*.json"))
    if not paths:
        raise ValueError("native event log is empty")
    for sequence, path in enumerate(paths, 1):
        if path.name != f"event-{sequence:05d}.json":
            raise ValueError("native event sequence has a gap")
        event = json.loads(path.read_bytes())
        digest = event.pop("record_sha256")
        if (
            event["sequence"] != sequence
            or event["previous_sha256"] != previous
            or old.lab.canonical_sha256(event) != digest
        ):
            raise ValueError("native event hash chain differs")
        previous = digest
    if event["payload"]["event"] != expected_terminal:
        raise ValueError("native event terminal differs")
    if expected_terminal == "run_finished":
        episode = json.loads((directory / "episode.json").read_bytes())
        if event["payload"]["outcome"]["episode_sha256"] != old.lab.canonical_sha256(episode):
            raise ValueError("native episode/event join differs")
    return len(paths)


def audit_failure(output: Path) -> dict:
    plan = json.loads((output / "PLAN.json").read_bytes())
    failure = json.loads((output / "FAILURE.json").read_bytes())
    _audit_source(plan)
    for path, digest in plan["protected_inputs"].items():
        if old.sha(Path(path)) != digest:
            raise ValueError("protected input changed")
    if (
        failure["type"] != "RedTrainerPracticeEpisodeError"
        or failure["message"] != "trainer opening timing is outside its bound"
        or failure["completed_configurations"] != 0
        or failure["fit_claimed"] is not False
    ):
        raise ValueError("failure summary differs")
    forbidden = (
        "FIT_TARGETS.json",
        "FIT_CLAIM.json",
        "FIT_RECEIPT.json",
        "candidate-model.json",
        "COMPARISON_TARGETS.json",
        "COMPARISON_RESULT.json",
        "RESULT.json",
    )
    if any((output / name).exists() for name in forbidden):
        raise ValueError("fit or comparison exists despite pre-fit failure")
    first = plan["rows"][0]
    directory = output / first["id"]
    if (
        first["id"] != "fit-00-neutral"
        or json.loads((directory / "setup.json").read_bytes())["recipe"] != first
        or not (directory / "capture.state").is_file()
    ):
        raise ValueError("first materialization differs")
    expected = {(offset, slot) for offset in (0, 4, 8, 12) for slot in range(1, 5)}
    branches = {
        tuple(map(int, path.name.removeprefix("branch-").split("-"))): path
        for path in directory.glob("branch-*")
        if path.is_dir()
    }
    if set(branches) != expected | {(16, 1)}:
        raise ValueError("consumed branch inventory differs")
    costs = Counter()
    outcomes = Counter()
    for offset, slot in sorted(expected):
        path = branches[(offset, slot)]
        episode = json.loads((path / "episode.json").read_bytes())
        terminal = json.loads((path / "final-state.json").read_bytes())
        if (
            episode["opening_idle_frames"] != offset
            or len(episode["decisions"]) != 1
            or episode["decisions"][0]["kind"] != "attack"
            or episode["decisions"][0]["move_slot"] != slot
            or old.sha(path / "final.state") != terminal["state_sha256"]
            or not 0 < terminal["completed_actions"] <= terminal["attempted_actions"] <= 5000
            or terminal["frame_delta"] > 120000
            or terminal["wall_elapsed_seconds"] > 45
        ):
            raise ValueError("completed branch/terminal differs")
        costs["attempted_actions"] += terminal["attempted_actions"]
        costs["completed_actions"] += terminal["completed_actions"]
        costs["frames"] += terminal["frame_delta"]
        costs["events"] += _audit_events(path, "run_finished")
        outcomes[episode["stop_reason"]] += 1
    failed = branches[(16, 1)]
    failed_details = json.loads((failed / "failure.json").read_bytes())
    if (
        failed_details != {"error": failure["message"], "type": failure["type"]}
        or (failed / "episode.json").exists()
        or (failed / "final-state.json").exists()
    ):
        raise ValueError("failed branch evidence differs")
    costs["events"] += _audit_events(failed, "run_failed")
    if any(p.is_dir() for p in output.iterdir() if p != directory):
        raise ValueError("later configuration directory exists")
    return {
        "schema": "pokemon.red.interaction-damage-failure-audit.v1",
        "passed": True,
        "decision": "stopped_before_fit",
        "plan_sha256": old.sha(output / "PLAN.json"),
        "failure_sha256": old.sha(output / "FAILURE.json"),
        "completed_configurations": 0,
        "completed_forced_branches": 16,
        "failed_branch": {"configuration": first["id"], "offset": 16, "slot": 1},
        "costs": dict(costs),
        "outcomes": dict(outcomes),
        "fit_attempts": 0,
        "candidate_created": False,
        "comparison_opened": False,
        "learned_native_actions": 0,
        "source_unchanged": True,
        "protected_inputs_unchanged": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=packet.OUTPUT)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    report = audit_failure(args.output)
    if args.check:
        if report != json.loads(args.report.read_bytes()):
            raise ValueError("retained failure audit differs")
    else:
        old.write_once(args.report, report)
    print(json.dumps(report))
