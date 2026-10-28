"""Bounded TRAIN policy iteration; untouched holdout opens only after a TRAIN gate."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from statistics import fmean

import run_red_balanced_status_curriculum as balanced
import run_red_status_curriculum as lab
from run_red_status_sequence_curriculum import capture_intermediate

from pokemon_red_completion.battle_scenario_capture import open_battle_scenario_capture
from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_balanced_status_features import project_balanced_status_moves
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_status_closed_loop_returns import (
    RETURN_SCHEMA,
    closed_loop_return,
    unchanged_status_turns,
)
from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel
from pokemon_red_completion.scenario_lab import ScenarioPartition

SEED = 2026092131
INITIAL_SHA = "7df8772dab6329df13b65afe2f9bfab2205e98c4f9be84750916a5d627df6f62"
OFFSETS = (0, 11, 12)


def load(path):
    return json.loads(path.read_bytes())


def write(path, value):
    """Resume only exact retained records; never overwrite or repair an outcome."""
    if path.exists():
        if load(path) != json.loads(json.dumps(value)):
            raise ValueError("retained record differs; refuse overwrite")
    else:
        lab.write(path, value)


def play(args, capture, model, output, cartridge, **kwargs):
    if not output.exists():
        return lab.play(args, capture, model, output, cartridge, **kwargs)
    if not (output / "episode.json").is_file() or (output / "failure.json").exists():
        raise ValueError("cannot replay a failed or unfinished branch")
    lab.verify_trainer_practice_event_log(output / "events")
    identity = load(output / "events/event-00001.json")["payload"]["identity"]
    expected = {"capture_id": capture.manifest.capture_id,
                "model_sha256": canonical_sha256(model.to_dict()),
                "first_slot": kwargs.get("first_slot"), "offset": kwargs.get("offset", 0),
                "horizon": kwargs.get("horizon"),
                "allow_status_moves": kwargs.get("status", True)}
    if any(identity.get(k) != v for k, v in expected.items()):
        raise ValueError("retained episode identity differs")
    if identity.get("learner_continuation", False) != kwargs.get("learner_continuation", False):
        raise ValueError("retained continuation differs")
    if load(output / "final-state.json")["state_sha256"] != lab.common._binding(
        output / "final.state")["sha256"]:
        raise ValueError("retained terminal differs")
    episode = load(output / "episode.json")
    last = load(sorted((output / "events").glob("event-*.json"))[-1])
    if last["payload"]["outcome"]["episode_sha256"] != canonical_sha256(episode):
        raise ValueError("retained episode digest differs")
    return episode


def measure(args, capture, directory, cartridge, frozen, continuation, deadline):
    slots, vectors = balanced.context_view(args, capture, cartridge, frozen)
    values = {s: [] for s in slots}
    traces = []
    for offset in OFFSETS:
        for slot in slots:
            deadline()
            episode = play(args, capture, continuation, directory / f"branch-{offset}-{slot}",
                               cartridge, first_slot=slot, offset=offset, horizon=40,
                               learner_continuation=True)
            observation = episode["decisions"][0]["observation"]
            view = project_balanced_status_moves(
                observation, BattleFeatureProjector(PokemonRedBattleCatalog()).project(observation))
            if vectors != [view.candidate_vectors[view.candidate_slots.index(s)] for s in slots]:
                raise ValueError("counterfactual observation differs")
            values[slot].append(closed_loop_return(episode))
            traces.append({"offset": offset, "slot": slot,
                           "unchanged_status_turns": unchanged_status_turns(episode),
                           "decisions": episode["decision_count"], "stop": episode["stop_reason"]})
    target = {"role": "train", "capture_id": capture.manifest.capture_id,
              "root": capture.manifest.root_lineage_id, "slots": slots, "vectors": vectors,
              "returns": [fmean(values[s]) for s in slots], "timing_returns": values,
              "return_schema": RETURN_SCHEMA, "continuation_sha256": canonical_sha256(
                  continuation.to_dict()), "traces": traces}
    write(directory / "target.json", target)
    return target


def evaluate(args, captures, model, directory, cartridge, *, status, deadline):
    directory.mkdir(mode=0o700, exist_ok=True)
    results = []
    for name, capture in captures:
        deadline()
        episode = play(args, capture, model, directory / name, cartridge,
                           status=status, horizon=40)
        row = {"case": name, "won": episode["battle_won"], "stop": episode["stop_reason"],
               "decisions": episode["decision_count"], "metrics": episode["metrics"],
               "return": closed_loop_return(episode),
               "status_choices": balanced.choice_diagnostics(episode) if status else [],
               "unchanged_status_turns": unchanged_status_turns(episode)}
        results.append(row)
    write(directory / "summary.json", results)
    return results


def gate(candidate, baseline):
    if {r["case"] for r in candidate} != {r["case"] for r in baseline}:
        raise ValueError("screen pairing differs")
    bases = {r["case"]: r for r in baseline}
    wins = {"candidate": sum(r["won"] for r in candidate),
            "frozen": sum(r["won"] for r in baseline)}
    decisions = {"candidate": sum(r["decisions"] for r in candidate),
                 "frozen": sum(r["decisions"] for r in baseline)}
    concerns = sum(bool(c["concerns"]) for r in candidate for c in r["status_choices"])
    useful = sum(r["won"] and r["return"] > bases[r["case"]]["return"] + .05
                 and any(not c["concerns"] for c in r["status_choices"]) for r in candidate)
    return {"wins": wins, "decisions": decisions, "concerning_selections": concerns,
            "improved_won_status_cases": useful,
            "passed": wins["candidate"] >= wins["frozen"] and concerns == 0 and useful > 0
            and decisions["candidate"] <= decisions["frozen"] * 1.25}


def run(args):
    if (args.output.exists() and not args.resume) or subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=lab.ROOT).strip():
        raise ValueError("new output and committed source required")
    if (lab.common._binding(args.frozen)["sha256"] != lab.K_SHA
            or lab.common._binding(args.initial)["sha256"] != INITIAL_SHA
            or lab.common._binding(args.rom)["sha256"] != lab.common.ROM_SHA256):
        raise ValueError("frozen inputs differ")
    frozen = TrainerPracticeThreeHeadModel.from_dict(load(args.frozen))
    continuation = TrainerPracticeThreeHeadModel.from_dict(load(args.initial))
    parent = load(args.parent / "plan.json")
    if parent["seed"] != balanced.SEED:
        raise ValueError("only declared balanced TRAIN parents permitted")
    sources = lab.common._source_rows(args.batch)
    if {r["source_id"] for _, r in sources} != set(frozen.train_root_ids):
        raise ValueError("TRAIN ancestry differs")
    cartridge = RedPracticeCartridge(args.rom.read_bytes())
    train_rows = [r for r in parent["recipes"] if r["role"] == "train"]
    train = []
    for row in train_rows:
        for suffix, stem in (("", "capture.state"), ("-post", "intermediate.state")):
            folder = args.parent / (row["id"] + suffix)
            if not (folder / stem).exists():
                if suffix:
                    continue
                raise ValueError("missing original TRAIN capture")
            capture = open_battle_scenario_capture(folder / stem, folder / (stem + ".json"))
            if capture.manifest.partition is not ScenarioPartition.TRAIN:
                raise ValueError("non-TRAIN source")
            train.append((row["id"] + suffix, capture))
    if len(train) != 80:
        raise ValueError("expected the declared80TRAIN captures")
    holdout = [r for r in balanced.balanced_recipes(cartridge, seed=SEED)
               if r["role"] == "holdout"]
    old_configs = {canonical_sha256([r["practice"], r["conditions"]])
                   for r in parent["recipes"] if r["role"] == "holdout"}
    assert not old_configs & {canonical_sha256([r["practice"], r["conditions"]]) for r in holdout}
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=lab.ROOT).decode().strip()
    plan = {
        "source_commit": commit, "seed": SEED, "parent": lab.common._binding(
            args.parent / "plan.json"), "frozen": lab.common._binding(args.frozen),
        "initial": lab.common._binding(args.initial), "train_captures": [
            c.manifest.to_dict() if hasattr(c.manifest, "to_dict") else {
                "capture_id": c.manifest.capture_id, "state_sha256": c.manifest.state_sha256,
                "root": c.manifest.root_lineage_id} for _, c in train],
        "holdout_recipes": holdout, "max_iterations": 3, "offsets": OFFSETS,
        "return_schema": RETURN_SCHEMA, "max_turns": 40, "epochs": 3000,
        "temperature": 10, "max_episodes": 2104, "authority_promotions": 0,
        "independent_heldout_roots": 0}
    if any(not 0 <= offset <= 12 for offset in OFFSETS):
        raise ValueError("timing plan exceeds executor bound before gameplay")
    if args.resume:
        old_plan = load(args.output / "plan.json")
        if (old_plan["seed"] != SEED or old_plan["offsets"] != [0, 11, 29]
                or old_plan["holdout_recipes"] != holdout
                or old_plan["frozen"] != plan["frozen"]
                or old_plan["initial"] != plan["initial"]
                or list(args.output.glob("round-*/candidate-model.json"))):
            raise ValueError("resume is restricted to this pre-fit timing failure")
        failed = args.output / "round-0/balanced-sleep-0-0/branch-29-2"
        if (load(failed / "failure.json")["error"]
                != "trainer opening timing is outside its bound"
                or (failed / "episode.json").exists() or (failed / "final.state").exists()):
            raise ValueError("cannot replace a played timing branch")
        lab.write(args.output / "timing-amendment.json", {
            "original_plan": lab.common._binding(args.output / "plan.json"),
            "source_commit": commit, "offsets": OFFSETS,
            "retired_unexecuted_offset": 29, "replacement_offset": 12,
            "original_failure": lab.common._binding(args.output / "failure.json"),
            "completed_episodes_replayed": 0})
    else:
        args.output.mkdir(mode=0o700)
        lab.write(args.output / "plan.json", plan)
    start = time.monotonic() - max(0., time.time() - (args.output / "plan.json").stat().st_mtime)

    def deadline():
        if time.monotonic() - start > 3600:
            raise TimeoutError("closed-loop packet60minute limit")

    try:
        starts = [(name, c) for name, c in train if not name.endswith("-post")]
        baseline = evaluate(args, starts, frozen, args.output / "train-baseline", cartridge,
                            status=False, deadline=deadline)
        history = []
        for iteration in range(3):
            directory = args.output / f"round-{iteration}"
            directory.mkdir(mode=0o700, exist_ok=True)
            write(directory / "continuation-model.json", continuation.to_dict())
            contexts, censored = list(train), []
            for row in train_rows:
                if not row["native_followup"]:
                    continue
                name = row["id"]
                capture = next(c for n, c in train if n == name)
                deadline()
                preparation = play(args, capture, continuation,
                                       directory / (name + "-prepare"), cartridge, horizon=1)
                destination = directory / f"round{iteration}-{name}-learner"
                destination.mkdir(mode=0o700, exist_ok=True)
                if (destination / "intermediate.state").exists():
                    post = open_battle_scenario_capture(destination / "intermediate.state",
                                                       destination / "intermediate.state.json")
                else:
                    post = capture_intermediate(
                        args, directory / (name + "-prepare") / "final.state",
                        destination, capture.manifest.root_lineage_id, commit, cartridge)
                if post is None:
                    censored.append({"case": name, "stop": preparation["stop_reason"]})
                else:
                    contexts.append((destination.name, post))
            targets = []
            for name, capture in contexts:
                destination = directory / name
                destination.mkdir(mode=0o700, exist_ok=True)
                # Retain self-contained input binding even when state is inherited.
                write(destination / "input.json", {"capture_id": capture.manifest.capture_id,
                          "state_sha256": capture.manifest.state_sha256,
                          "manifest_sha256": capture.manifest_sha256})
                targets.append(measure(args, capture, destination, cartridge, frozen,
                                       continuation, deadline))
            distinct = sum(abs(t["returns"][0] - t["returns"][1]) > .05 for t in targets)
            lab.write(directory / "collection.json", {"contexts": len(targets),
                      "censored": censored, "non_tied_contexts": distinct})
            if not distinct:
                raise ValueError("no measured action contrast; do not fit")
            candidate, regret = balanced.fit_selector(
                targets, frozen, epochs=3000, temperature=10, seed=SEED + iteration)
            lab.write(directory / "candidate-model.json", candidate.to_dict())
            lab.write(directory / "fit.json", {"fits": 1, **regret, "examples": len(targets),
                      "candidate": lab.common._binding(directory / "candidate-model.json")})
            screening = evaluate(args, starts, candidate, directory / "train-screen", cartridge,
                                 status=True, deadline=deadline)
            screen = gate(screening, baseline)
            lab.write(directory / "screen.json", screen)
            history.append(screen)
            print(json.dumps({"iteration": iteration, "regret": regret, "screen": screen}),
                  flush=True)
            if screen["passed"]:
                held_captures = [(row["id"], lab.materialize(
                    args, row, i, sources, cartridge, commit)) for i, row in enumerate(holdout)]
                held_base = evaluate(args, held_captures, frozen, args.output / "held-baseline",
                                     cartridge, status=False, deadline=deadline)
                held_candidate = evaluate(args, held_captures, candidate,
                                          args.output / "held-candidate", cartridge,
                                          status=True, deadline=deadline)
                result = {"train_screens": history, "fits": iteration + 1,
                          "selected_iteration": iteration, "withheld": gate(
                              held_candidate, held_base), "authority_promotions": 0,
                          "independent_heldout_roots": 0}
                break
            continuation = candidate
        else:
            result = {"train_screens": history, "fits": 3, "withheld": None,
                      "stop": "TRAIN_gate_failed", "authority_promotions": 0}
        lab.write(args.output / "result.json", result)
    except Exception as error:
        path = args.output / ("resume-failure.json" if args.resume else "failure.json")
        lab.write(path, {"type": type(error).__name__, "error": str(error)})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("rom", "batch", "parent", "frozen", "initial", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    run(parser.parse_args())
