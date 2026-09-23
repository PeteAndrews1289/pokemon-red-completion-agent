"""Capped later-turn observation, one combined fit, unchanged TRAIN battle gate."""

import argparse
import json
import subprocess
import time
from collections import Counter
from pathlib import Path

import numpy as np
import run_red_status_readout_learning as previous
from audit_red_closed_loop_status import model, verify_screen
from build_red_status_reward_view import validate_view
from qualify_red_status_effect_trace import play_one
from run_red_measured_effect_learning import authenticate_row

from pokemon_red_completion.red_balanced_status_features import (
    BALANCED_STATUS_NAMES as N,
)
from pokemon_red_completion.red_balanced_status_features import COMPACT_STATUS_NAMES
from pokemon_red_completion.red_effect_selector_head import augment_head, effect_values
from pokemon_red_completion.red_effect_selector_learning import fit_combination, prepare_combination
from pokemon_red_completion.red_status_readout_learning import representation_check

loop, lab = previous.loop, previous.loop.lab
EFFECT_SHA = "cad523f4e23e513e281a807603bf6a52315328291b96916b759e427699efab02"
PRIOR_SHA = "a28b677431032887f52bc29ec775629e162e53eca6eaa6d43916be76f2a59207"


def later_inventory(inputs):
    """Authenticated pre-action inventory; callers freeze their own selection rules."""
    cells, sleepers = {}, []
    for group in inputs["groups"][1:]:
        for binding in group:
            path = Path(binding["path"])
            if lab.common._binding(path) != binding:
                raise ValueError("later target changed")
            target = loop.load(path)
            index = next(i for i, v in enumerate(target["vectors"]) if v[N.index("choice.status")])
            v = target["vectors"][index]
            families = [f for f in ("heal", "rest", "confusion") if v[N.index("choice.effect."+f)]]
            if not families:
                continue
            family = families[0]
            parent, turn = path.parent.name.rsplit("-decision-", 1)
            capture_path = path.parents[2] / "trajectories" / parent / "snapshots" / (
                "decision-" + turn)
            capture = loop.open_battle_scenario_capture(capture_path / "capture.state",
                                                       capture_path / "capture.state.json")
            if (capture.manifest.partition is not loop.ScenarioPartition.TRAIN or
                    capture.manifest.capture_id != target["capture_id"] or
                    capture.manifest.root_lineage_id != target["root"]):
                raise ValueError("later capture differs")
            row = {"target": binding, "capture": str(capture_path),
                   "manifest_sha256": capture.manifest_sha256, "family": family,
                   "state_sha256": capture.manifest.state_sha256,
                   "root": target["root"], "capture_id": target["capture_id"],
                   "slot": target["slots"][index], "vector": v,
                   "asleep": bool(v[N.index("choice.player_asleep")])}
            flag = v[N.index("choice.already_confused" if family == "confusion"
                             else "choice.heal_full_hp")]
            if row["asleep"]:
                if family == "rest":
                    sleepers.append(row)
            else:
                cells.setdefault((family, int(flag)), []).append(row)
    return cells, sleepers


def select_later(inputs):
    """Historical selection is unchanged; the closed packet must not be rerun."""
    cells, sleepers = later_inventory(inputs)
    expected = {("heal", 0), ("heal", 1), ("rest", 0), ("confusion", 0), ("confusion", 1)}
    if set(cells) != expected:
        raise ValueError("later feature inventory differs from frozen five-cell design")
    selected = []
    for key in sorted(cells):
        ordered = sorted(cells[key], key=lambda r: (r["capture_id"], r["manifest_sha256"]))
        unique = {r["manifest_sha256"]: r for r in reversed(ordered)}
        chosen = sorted(unique.values(), key=lambda r: (r["capture_id"], r["manifest_sha256"]))[:2]
        if len(chosen) != 2:
            raise ValueError("fewer than two later cases in a frozen cell")
        selected.extend(chosen)
    selected.extend(sorted(sleepers, key=lambda r: (r["capture_id"], r["manifest_sha256"]))[:2])
    for i, row in enumerate(selected):
        row.pop("state_sha256")  # preserve the historical plan representation
        row["id"] = f"later-effect-{i:02d}"
    return selected, {f"{f}:{c}": len(rows) for (f, c), rows in cells.items()}


def qualify_later(args, selected, cartridge, frozen, effect, deadline):
    measured = []
    for row in selected:
        deadline()
        folder = Path(row["capture"])
        state_name = row.get("state_name", "capture.state")
        if state_name not in {"capture.state", "intermediate.state"}:
            raise ValueError("unknown qualification capture format")
        capture = loop.open_battle_scenario_capture(folder / state_name,
                                                    folder / (state_name + ".json"))
        if capture.manifest_sha256 != row["manifest_sha256"]:
            raise ValueError("later capture altered after freeze")
        directory = args.output / row["id"]
        play_one(args, capture, frozen, directory, cartridge, row["slot"],
                 traced=True, allow_terminal=True)
        record = authenticate_row(directory, capture, {**row, "role": "train"},
                                  allow_terminal=True)
        if record["features"] != row["vector"][-len(COMPACT_STATUS_NAMES):]:
            raise ValueError("later semantic projection differs")
        record["asleep_before_choice"] = row["asleep"]
        record["probability_conditional_on_execution"] = float(
            effect_values([row["vector"]], effect["weights"])[0, 1])
        lab.write(directory / "measured.json", record)
        measured.append(record)
    observed = [r for r in measured if not r["asleep_before_choice"] and
                r["evidence"]["kind"] == "observed"]
    brier = float(np.mean([(r["probability_conditional_on_execution"] -
                          r["evidence"]["application_success"])**2 for r in observed]))
    return {"rows": measured, "observed_awake": len(observed), "brier": brier,
            "label_kinds": dict(Counter(r["evidence"]["kind"] for r in measured)),
            "passed": len(observed) >= 8 and brier <= .125 and
                {r["family"] for r in observed} == {"heal", "rest", "confusion"}}


def run(args, *, effect_relative="red-measured-effect-learning-20260921-v1/fit.json",
        effect_sha=EFFECT_SHA, select=select_later, protocol=None, extra_later_gate=None,
        started_at=None):
    """Shared one-fit engine; successor protocols must freeze disjoint diagnostics."""
    bind = lab.common._binding
    if args.output.exists() or subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=lab.ROOT).strip():
        raise ValueError("new output and committed source required")
    started = time.monotonic() if started_at is None else started_at

    def deadline():
        if time.monotonic()-started > 5400:
            raise TimeoutError("combination90minute cap")

    parent, inputs, originals, initial, frozen = previous.load_inputs(args.root)
    effect_path = args.root / effect_relative
    prior_path = args.root / "red-status-win-reward-learning-20260921-v1/candidate-model.json"
    view_path = args.root / "red-status-win-reward-view-20260921-v1.json"
    if (bind(effect_path)["sha256"] != effect_sha or bind(prior_path)["sha256"] != PRIOR_SHA or
            bind(args.rom)["sha256"] != lab.common.ROM_SHA256):
        raise ValueError("frozen artifact differs")
    effect, basis = loop.load(effect_path), model(prior_path)
    if (effect["feature_names"] != ["intercept", *COMPACT_STATUS_NAMES] or
            effect["prediction"] != "application_conditional_on_execution" or
            not effect["success"]):
        raise ValueError("effect predictor contract differs")
    view = validate_view(view_path, args.root)
    if view["inputs_sha256"] != loop.canonical_sha256(inputs):
        raise ValueError("reward view does not bind original inputs")
    groups = view["groups"]
    selected, coverage = select(inputs)
    problem = prepare_combination(groups, initial, frozen, basis, originals, effect)
    if len(problem.protected) != 182:
        raise ValueError("original182preferences differ")
    inspection = representation_check(problem)
    # Zero auxiliary coefficients must exactly preserve prior scores before learning.
    zero = augment_head(basis.move, effect["weights"], effect_sha)
    for group in groups:
        for target in group:
            if not np.array_equal(zero.scores(target["vectors"]),
                                  basis.move.scores(target["vectors"])):
                raise ValueError("zero augmentation changed prior decisions")
    args.output.mkdir(mode=0o700)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=lab.ROOT).decode().strip()
    lab.write(args.output / "plan.json", {"source_commit": commit,
        "inputs_sha256": loop.canonical_sha256(inputs), "groups": inputs["groups"],
        "initial": parent["initial"], "frozen": parent["frozen"], "prior": bind(prior_path),
        "effect": bind(effect_path), "reward": bind(view_path), "rom": bind(args.rom),
        "later_cases": selected, "later_coverage": coverage, "inspection": inspection,
        "max_episodes": 140, "max_frames": 15420000, "max_minutes": 90, "max_fits": 1,
        "max_iterations": 500, "ftol": 1e-9, "anchor_l2": .001,
        "heldout_access": False, "actor_promotions": 0,
        **({"protocol": protocol} if protocol is not None else {})})
    result = {"fits": 0, "fit_gate": False, "screen": None, "withheld": None,
              "authority_promotions": 0}
    try:
        cartridge = lab.RedPracticeCartridge(args.rom.read_bytes())
        later = qualify_later(args, selected, cartridge, frozen, effect, deadline)
        if extra_later_gate is not None:
            later["additional_coverage"] = extra_later_gate(later)
            later["passed"] = later["passed"] and later["additional_coverage"]["passed"]
        lab.write(args.output / "later-qualification.json", later)
        result["later_gate"] = later["passed"]
        if later["passed"]:
            deadline()
            candidate, fit = fit_combination(groups, initial, frozen, basis, originals,
                                             effect, effect_sha)
            lab.write(args.output / "candidate-model.json", candidate.to_dict())
            reopened = model(args.output / "candidate-model.json")
            if reopened.to_dict() != candidate.to_dict():
                raise ValueError("candidate checkpoint lost auxiliary knowledge")
            for group in groups:
                for target in group:
                    if not np.array_equal(reopened.move.scores(target["vectors"]),
                                          candidate.move.scores(target["vectors"])):
                        raise ValueError("reloaded combined scores differ")
            lab.write(args.output / "fit.json", {**fit,
                      "candidate": bind(args.output / "candidate-model.json")})
            result.update(fits=1, fit_gate=bool(fit["solver_success"] and
                fit["minimum_slack"] >= -1e-8 and fit["retention_regressions"] == 0 and
                fit["groups"][0]["candidate"]["regret"] <= fit["groups"][0]["initial"]["regret"] and
                sum(g["candidate"]["regret"] for g in fit["groups"][1:]) <=
                .75 * sum(g["initial"]["regret"] for g in fit["groups"][1:])))
            if result["fit_gate"]:
                starts = []
                balanced = args.root / "red-balanced-status-learning-20260921-v1"
                for row in loop.load(balanced / "plan.json")["recipes"]:
                    if row["role"] != "train":
                        continue
                    folder = balanced / row["id"]
                    c = loop.open_battle_scenario_capture(folder / "capture.state",
                                                           folder / "capture.state.json")
                    if (c.manifest.partition is not loop.ScenarioPartition.TRAIN or
                            c.manifest.root_lineage_id not in frozen.train_root_ids):
                        raise ValueError("screen origin differs")
                    starts.append((row["id"], c))
                if len(starts) != 64:
                    raise ValueError("screen must have64TRAIN cases")
                base = loop.evaluate(args, starts, frozen, args.output / "train-baseline",
                                     cartridge, status=False, deadline=deadline)
                chosen = loop.evaluate(args, starts, reopened, args.output / "train-screen",
                                       cartridge, status=True, deadline=deadline)
                verify_screen(args.output / "train-screen", reopened, frozen)
                result["screen"] = loop.gate(chosen, base)
        lab.write(args.output / "result.json", {**result, "seconds": time.monotonic()-started})
        print(json.dumps(result), flush=True)
    except Exception as exc:
        lab.write(args.output / "failure.json", {"type": type(exc).__name__, "error": str(exc)})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "rom", "output"):
        parser.add_argument("--"+name, type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
