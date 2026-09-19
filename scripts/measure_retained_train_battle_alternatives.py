"""One-use, timing-matched move branches from a retained train decision."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from pokemon_red_completion.battle_runtime import execute_bounded_battle_move_turn
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import (
    CountingExecutor,
    FrameBudgetController,
    FrameSafeExecutor,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    HardCompositionActionLimiter,
)
from pokemon_red_completion.observation import BattleMenuPhase, PokemonRedStateReader
from pokemon_red_completion.red_autonomous_player import _record, _write
from pokemon_red_completion.red_battle_scenario import (
    prepare_red_battle_scenario,
    project_red_battle_turn_outcome,
)
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "pokemon.red.retained-train-battle-alternatives-plan.v1"
ROM_SHA256 = "5ca7ba01642a3b27b0cc0b5349b52792795b62d3ed977e98a09390659af96b7b"


def _read_bound_file(value: object, label: str) -> bytes:
    if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
        raise ValueError(f"{label} binding differs")
    path, digest = value["path"], value["sha256"]
    if not isinstance(path, str) or not isinstance(digest, str):
        raise ValueError(f"{label} identity differs")
    payload = Path(path).read_bytes()
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError(f"{label} hash differs")
    return payload


def _validated_plan(plan: object, plan_bytes: bytes) -> tuple[dict[str, object], bytes, bytes]:
    if not isinstance(plan, dict) or plan.get("schema") != SCHEMA:
        raise ValueError("retained train branch plan differs")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("commit bounded branch code before cartridge execution")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    if plan.get("source_commit") != revision:
        raise ValueError("branch source commit differs")
    rom = _read_bound_file(plan.get("rom"), "ROM")
    if hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise ValueError("Red ROM differs")
    source = _read_bound_file(plan.get("source_outcome"), "source outcome")
    query_bytes = _read_bound_file(plan.get("query"), "retained query")
    before = _read_bound_file(plan.get("before_state"), "retained state")
    source_report = json.loads(source)
    query = json.loads(query_bytes)
    facts = query.get("facts") if isinstance(query, dict) else None
    moves = facts.get("moves") if isinstance(facts, dict) else None
    if (
        source_report.get("schema") != "pokemon.red.model-battle-train-episode-outcome.v1"
        or source_report.get("stop_reason") != "encounter_limit"
        or source_report.get("root_lineage_id") != plan.get("root_lineage_id")
        or plan.get("root_lineage_id")
        != "red-goal-root-c1d575483e311b3a9854b0e85237f725c3da1412ed62ab142dcd82050c666435"
        or not isinstance(query, dict)
        or query.get("state_sha256") != hashlib.sha256(before).hexdigest()
        or query.get("observation_sha256") != plan.get("observation_sha256")
        or query.get("model_sha256") != plan.get("model_sha256")
        or plan.get("encounter_index") != 0
        or plan.get("candidate_indices") != [0, 1, 2, 3]
        or plan.get("minimum_pre_attack_frames") != 2048
        or plan.get("maximum_actions_per_branch") != 32
        or plan.get("maximum_frames_per_branch") != 4096
        or not isinstance(moves, list)
        or len(moves) != 4
        or any(type(move) is not int or move <= 0 for move in moves)
    ):
        raise ValueError("retained branch scope or provenance differs")
    output = plan.get("output")
    if not isinstance(output, str) or Path(output).exists() or not plan_bytes:
        raise ValueError("branch output must be new")
    return query, before, rom


def _prepared_boundary(emulator: PyBoyAdapter, before: bytes, query: dict[str, object]):
    emulator.load_state_bytes(before)
    reader = PokemonRedStateReader(emulator)
    raw = reader.read()
    if raw.map_id != 165 or raw.battle_state != 1:
        raise ValueError("retained state is not the Mansion wild battle")
    if reader.read_battle_menu_state(raw).phase is not BattleMenuPhase.MAIN:
        raise ValueError("retained state is not a MAIN move boundary")
    prepared = prepare_red_battle_scenario(
        PokemonRedObservationEncoder.from_state_reader(reader), raw
    )
    features = prepared.features
    if (
        prepared.initial_observation_sha256 != query.get("observation_sha256")
        or list(features.legal_mask) != query.get("legal_mask")
        or list(features.current_pp) != query.get("current_pp")
        or list(features.slot_indices) != query.get("slot_indices")
        or [list(vector) for vector in features.candidate_vectors] != query.get("candidate_vectors")
        or not all(features.legal_mask)
        or len(features.legal_mask) != 4
    ):
        raise ValueError("retained semantic candidate menu differs")
    return prepared


def run(plan_path: Path, *, check_only: bool = False) -> dict[str, object]:
    plan_bytes = plan_path.read_bytes()
    plan = json.loads(plan_bytes)
    query, before, _ = _validated_plan(plan, plan_bytes)
    facts = query["facts"]
    assert isinstance(facts, dict)
    moves = facts["moves"]
    assert isinstance(moves, list)
    rom_path = Path(plan["rom"]["path"])
    with PyBoyAdapter(rom_path, watch=False, speed=None) as emulator:
        first_frame = emulator.frame_count
        prepared = _prepared_boundary(emulator, before, query)
        if emulator.frame_count != first_frame:
            raise ValueError("action-free branch preflight advanced the cartridge")
        if check_only:
            return {
                "status": "action_free_preflight_passed",
                "candidate_count": 4,
                "controller_actions": 0,
                "emulator_frames": 0,
            }

    output = Path(plan["output"])
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    _record(output / "plan.json", plan)
    _record(
        output / "execution-started.json",
        {
            "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
            "root_lineage_id": plan["root_lineage_id"],
            "candidate_indices": [0, 1, 2, 3],
            "fit_allowed": False,
            "independent_roots_added": 0,
        },
    )
    results: list[dict[str, object]] = []
    for candidate in range(4):
        branch = output / f"candidate-{candidate:02d}"
        branch.mkdir(mode=0o700)
        _record(branch / "execution-started.json", {"candidate_index": candidate})
        with PyBoyAdapter(rom_path, watch=False, speed=None) as emulator:
            _prepared_boundary(emulator, before, query)
            budget = FrameBudgetController(emulator, maximum_frames=4096)
            reader = PokemonRedStateReader(budget)
            limiter = HardCompositionActionLimiter(
                FrameSafeExecutor(budget, DEFAULT_NEW_GAME_TIMING.controller_timing()),
                maximum_actions_per_decision=32,
                maximum_episode_actions=32,
            )
            actions = CountingExecutor(limiter)
            try:
                execution = execute_bounded_battle_move_turn(
                    reader,
                    actions,
                    expected_map=165,
                    expected_battle_state=1,
                    selected_slot=prepared.features.slot_indices[candidate] + 1,
                    minimum_pre_attack_frames=2048,
                    label="retained train battle alternative",
                )
                outcome = project_red_battle_turn_outcome(execution)
                if outcome.pre_attack_frames != 2048:
                    raise ValueError("candidate pre-attack timing differs")
                row: dict[str, object] = {
                    "candidate_index": candidate,
                    "selected_slot": execution.selected_slot,
                    "move_id": moves[execution.selected_slot - 1],
                    "outcome": outcome.public_dict(),
                    "actions": actions.actions_executed,
                    "frames": budget.frames_executed,
                    "terminal_state_sha256": hashlib.sha256(
                        emulator.save_state_bytes()
                    ).hexdigest(),
                }
                _write(branch / "terminal.state", emulator.save_state_bytes())
                _record(branch / "outcome.json", row)
                results.append(row)
            except Exception as error:
                _write(branch / "terminal.state", emulator.save_state_bytes())
                _record(
                    branch / "failure.json", {"type": type(error).__name__, "message": str(error)}
                )
                raise
    report: dict[str, object] = {
        "schema": "pokemon.red.retained-train-battle-alternatives-outcome.v1",
        "root_lineage_id": plan["root_lineage_id"],
        "observation_sha256": plan["observation_sha256"],
        "source_state_sha256": query["state_sha256"],
        "candidate_outcomes": results,
        "independent_roots_added": 0,
        "model_updates": 0,
        "authority_promotions": 0,
    }
    _record(output / "outcome.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.plan, check_only=args.check_only), sort_keys=True))


if __name__ == "__main__":
    main()
