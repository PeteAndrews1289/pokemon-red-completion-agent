"""Measure four terminal TRAIN battles with paired healthy and critical leads."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from statistics import fmean

import materialize_red_teacher_battle_practice as materializer
import run_fresh_red_trainer_curriculum as original
import run_red_trainer_practice_baseline as baseline

from pokemon_red_completion.battle_practice_factory import BattlePracticeSpec
from pokemon_red_completion.battle_scenario_capture import OBSERVATION_SCHEMA_V2
from pokemon_red_completion.red_trainer_practice_returns import score_trainer_practice_episode

ROOT = Path(__file__).resolve().parents[1]
ROOT_INDICES = (0, 3)
MOVE = "pokemon.red.gb.us.rev0:move"


def terminal_hp_cases(
    templates: tuple[dict[str, object], ...],
) -> tuple[tuple[int, str, dict[str, object]], ...]:
    if len(templates) != 2:
        raise ValueError("terminal HP pilot needs two declared matchup templates")
    cases = []
    for root_index, template in zip(ROOT_INDICES, templates, strict=True):
        base = deepcopy(template)
        reserves = base.get("party_reserves")
        if not isinstance(reserves, list) or not reserves:
            raise ValueError("terminal HP pilot needs one living reserve")
        base["party_reserves"] = reserves[:1]
        base["opponent_party_count"] = 1
        base.pop("opponent_reserves", None)
        base["opponent_hp"] = 70
        base["opponent_moves"] = [{"move_ref": f"{MOVE}:033", "pp": 35}]
        for name, hp in (("healthy", template.get("actor_hp")), ("critical", 8)):
            if type(hp) is not int or hp < 8:  # noqa: E721
                raise ValueError("terminal HP pilot lead HP differs")
            practice = deepcopy(base)
            practice["actor_hp"] = hp
            cases.append((root_index, name, practice))
    return tuple(cases)


def measured_pair(directory: Path) -> dict[str, object]:
    timed: list[dict[str, float]] = []
    for offset in original.OFFSETS:
        branch_dir = directory / "baseline" / f"timing-{offset:02d}"
        choice_set = json.loads((branch_dir / "matched-choices.json").read_bytes())
        if choice_set.get("player_turn_horizon") != 4:
            raise ValueError("terminal HP branch horizon differs")
        row = {}
        for branch in choice_set["branches"]:
            ref, episode = branch["first_choice_ref"], branch["episode"]
            if episode.get("stop_reason") not in {"battle_won", "party_defeated"}:
                raise ValueError("terminal HP branch did not finish battle")
            score = score_trainer_practice_episode(episode)
            if score.truncated:
                raise ValueError("terminal HP branch return was truncated")
            row[ref] = score.value
        timed.append(row)
    refs = set(timed[0])
    if any(set(row) != refs for row in timed):
        raise ValueError("terminal HP timing action inventory differs")
    means = {ref: fmean(row[ref] for row in timed) for ref in sorted(refs)}
    attacks = {ref: value for ref, value in means.items() if ":move:" in ref}
    switches = {ref: value for ref, value in means.items() if ":switch:" in ref}
    if not attacks or len(switches) != 1:
        raise ValueError("terminal HP branch action inventory differs")
    attack, switch = max(attacks.values()), max(switches.values())
    return {
        "mean_action_returns": means,
        "best_attack_return": attack,
        "best_switch_return": switch,
        "attack_minus_switch": attack - switch,
        "terminal_branches": sum(len(row) for row in timed),
    }


def run(
    args: argparse.Namespace,
    *,
    recipe_builder: Callable[
        [tuple[dict[str, object], ...]], tuple[tuple[int, str, dict[str, object]], ...]
    ] = terminal_hp_cases,
    matched_choices: str = "all_legal_opening",
) -> dict[str, object]:
    if args.output.exists():
        raise ValueError("terminal HP output must be new")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("commit terminal HP pilot source before execution")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    rom = original._binding(args.rom)
    if rom["sha256"] != original.ROM_SHA256:
        raise ValueError("terminal HP cartridge differs")
    frozen = original._binding(args.frozen_model)
    if len(args.templates) != 2:
        raise ValueError("terminal HP pilot needs two template paths")
    templates = []
    for path in args.templates:
        template = json.loads(path.read_bytes())
        if (
            template.get("schema") != materializer.TRAINER_SCHEMA
            or template.get("observation_schema") != OBSERVATION_SCHEMA_V2
            or not isinstance(template.get("practice"), dict)
        ):
            raise ValueError("terminal HP template differs")
        templates.append(template["practice"])
    sources = original._source_rows(args.batch)
    if matched_choices not in {"all_legal_opening", "opening_move_one_vs_switch_two"}:
        raise ValueError("terminal HP opening choice inventory differs")
    recipes = recipe_builder(tuple(templates))
    if len(recipes) != 4:
        raise ValueError("terminal HP pilot needs exactly four cases")
    args.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    rows = []
    for root_index, name, practice in recipes:
        directory = args.output / f"root-{root_index + 1:02d}-{name}"
        directory.mkdir(mode=0o700, exist_ok=False)
        stage = "materialize"
        try:
            source, source_receipt = sources[root_index]
            source_state = source / "source.state"
            practice["source_state_sha256"] = original._binding(source_state)["sha256"]
            practice["root_lineage_id"] = source_receipt["source_id"]
            BattlePracticeSpec.from_dict(practice)
            materialize_plan = directory / "materialize-plan.json"
            materialized = directory / "materialized"
            original._write(materialize_plan, {
                "schema": materializer.TRAINER_SCHEMA,
                "source_commit": commit,
                "rom": rom,
                "source_state": original._binding(source_state),
                "source_capture_manifest": original._binding(source / "source.state.json"),
                "practice": practice,
                "observation_schema": OBSERVATION_SCHEMA_V2,
                "output": str(materialized),
            })
            materializer.run(materialize_plan, check_only=True)
            materializer.run(materialize_plan)
            stage = "branches"
            baseline_plan = directory / "baseline-plan.json"
            original._write(baseline_plan, {
                "schema": baseline.SCHEMA,
                "source_commit": commit,
                "rom": rom,
                "model": frozen,
                "capture_state": original._binding(materialized / "assisted.state"),
                "capture_manifest": original._binding(materialized / "assisted.state.json"),
                "max_decisions": 80,
                "maximum_frames": 120000,
                "matched_timing_offsets": list(original.OFFSETS),
                "matched_choices": matched_choices,
                "matched_player_turn_horizon": 4,
                "output": str(directory / "baseline"),
            })
            baseline.run(baseline_plan, check_only=True)
            baseline.run(baseline_plan)
            stage = "measure"
            measured = measured_pair(directory)
            row = {"root_index": root_index, "hp": name, **measured}
            rows.append(row)
            original._write(directory / "measurement.json", row)
        except Exception as error:
            original._write(directory / "failure.json", {
                "stage": stage, "error_type": type(error).__name__, "error": str(error),
                "completed_scenarios": len(rows),
            })
            raise
        if len(rows) % 2 == 0:
            healthy, critical = rows[-2:]
            if healthy["attack_minus_switch"] <= 0.10 or critical["attack_minus_switch"] >= -0.10:
                result = {"status": "pair_reversal_failed", "scenarios": rows}
                original._write(args.output / "summary.json", result)
                return result
    result = {"status": "four_terminal_pairs_passed", "scenarios": rows}
    original._write(args.output / "summary.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--frozen-model", type=Path, required=True)
    parser.add_argument("--template", dest="templates", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(run(parser.parse_args()), sort_keys=True))


if __name__ == "__main__":
    main()
