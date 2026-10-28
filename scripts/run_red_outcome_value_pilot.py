"""One fresh on-policy value packet; no old replay, reserved access or live promotion."""

import argparse
import json
import subprocess
import time
from copy import copy
from pathlib import Path
from statistics import fmean

import numpy as np
import run_red_effect_selector_combination as combined
from audit_red_status_learning import audit
from audit_red_timing_selector_preparation import inspect as inspect_previous
from red_outcome_value_learning import (
    OFFSETS,
    extend_problem,
    fit_once,
    outcome_gate,
    validate_offsets,
)
from red_status_root_coverage import crossed_recipes
from run_red_status_trajectory_coverage import reopen_snapshot, target_diagnostics

from pokemon_red_completion.red_status_execution_learning import eligible_target
from pokemon_red_completion.red_status_win_conditioned_returns import (
    RETURN_SCHEMA,
    win_conditioned_return,
)

ACTOR_SHA = "1de5e6a2b841fc08993e98174ca2b11bcf31792b75fe222bec0bb07f831cf42b"
FAMILIES = {"sleep", "paralysis", "confusion", "rest"}
TRAIN_SEED = 2026092233
SCREEN_SEED = 2026092234


def recipes(cartridge, roots, *, broad=False):
    train_seed, screen_seed = ((2026092235, 2026092236) if broad else
                               (TRAIN_SEED, SCREEN_SEED))
    train = []
    for row in crossed_recipes(cartridge, roots, seed=train_seed):
        variant = int(row["id"].split("-")[-2])
        if (row["source_index"] in (0, 1) and variant == row["source_index"] and
                (broad or (row["family"] in FAMILIES and row["contrast"] in (0, 1)))):
            train.append({**row, "id": f"value-train-{train_seed}-" + row["id"]})
    screen = [{**r, "id": f"value-screen-{screen_seed}-" + r["id"]}
              for r in crossed_recipes(cartridge, roots, seed=screen_seed)
              if r["source_index"] == 3]
    if len(train) != (64 if broad else 16) or len(screen) != 32:
        raise ValueError("prospective recipe counts differ")
    return train, screen


def measure(args, capture, directory, cartridge, frozen, actor, deadline):
    loop, lab = combined.loop, combined.lab
    slots, vectors = loop.balanced.context_view(args, capture, cartridge, frozen)
    if not eligible_target({"role": "train", "vectors": vectors}):
        return None
    directory.mkdir(mode=0o700)
    values = {str(s): [] for s in slots}
    for offset in OFFSETS:
        for slot in slots:
            deadline()
            ep = lab.play(args, capture, actor, directory / f"branch-{offset}-{slot}",
                cartridge, first_slot=slot, offset=offset, horizon=40, learner_continuation=True)
            view = loop.project_balanced_status_moves(ep["decisions"][0]["observation"],
                loop.BattleFeatureProjector(loop.PokemonRedBattleCatalog()).project(
                    ep["decisions"][0]["observation"]))
            if vectors != [view.candidate_vectors[view.candidate_slots.index(s)] for s in slots]:
                raise ValueError("paired branch observation differs")
            values[str(slot)].append(win_conditioned_return(ep))
    target = {"role": "train", "root": capture.manifest.root_lineage_id,
        "capture_id": capture.manifest.capture_id, "slots": slots, "vectors": vectors,
        "offsets": OFFSETS, "timing_returns": values,
        "returns": [fmean(values[str(s)]) for s in slots], "return_schema": RETURN_SCHEMA,
        "continuation_sha256": loop.canonical_sha256(actor.to_dict()),
        "manifest_sha256": capture.manifest_sha256, "state_sha256": capture.manifest.state_sha256}
    lab.write(directory / "target.json", target)
    return target


def verify_targets(directory, actor):
    loop = combined.loop
    for path in sorted(directory.glob("*/target.json")):
        target = loop.load(path)
        expected = {(o, s) for o in OFFSETS for s in target["slots"]}
        branches = list(path.parent.glob("branch-*/episode.json"))
        found = {tuple(map(int, p.parent.name.split("-")[1:])) for p in branches}
        if found != expected or len(branches) != 16:
            raise ValueError("paired branch inventory differs")
        for p in branches:
            offset, slot = map(int, p.parent.name.split("-")[1:])
            identity = loop.load(p.parent / "events/event-00001.json")["payload"]["identity"]
            ep = loop.load(p)
            if (identity["capture_id"] != target["capture_id"] or
                    identity["model_sha256"] != loop.canonical_sha256(actor.to_dict()) or
                    identity["root"] != target["root"] or identity["partition"] != "train" or
                    not identity["learner_continuation"] or identity["first_slot"] != slot or
                    identity["offset"] != offset or ep["decisions"][0]["move_slot"] != slot or
                    abs(win_conditioned_return(ep)-target["timing_returns"][str(slot)][
                        OFFSETS.index(offset)]) > 1e-10):
                raise ValueError("measured action/continuation binding differs")


def run(args):
    validate_offsets(OFFSETS)
    if not getattr(args, "approved_successor", False):
        raise ValueError("closed v1 packet; corrected successor requires owner approval")
    loop, lab = combined.loop, combined.lab
    broad = getattr(args, "broad_successor", False)
    indices = (2, 4, 8) if broad else (2,)
    max_episodes = 4224 if broad else 592
    max_frames = max_episodes * 120000
    if args.output.exists() or subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=lab.ROOT).strip():
        raise ValueError("new packet and committed source required")
    retired = args.root / "red-outcome-value-pilot-20260922-v1"
    if (lab.common._binding(retired / "plan.json")["sha256"] !=
            "f43ad4c306e88610c58b9b8a03b64851977fa7822b8f97b68f67dd1672446eb2" or
            lab.common._binding(retired / "failure.json")["sha256"] !=
            "53f29a85791bf367b1fab8d983159df022f057869e73f9c0f1da85c5d4eee502"):
        raise ValueError("retired pilot evidence differs")
    excluded = set()
    for manifest in retired.glob("**/capture.state.json"):
        c = loop.open_battle_scenario_capture(manifest.with_suffix(""), manifest)
        excluded.add(c.manifest.state_sha256)
    prior_packet = args.root / "red-native-later-effect-qualification-20260922-v1"
    old_audit = inspect_previous(args.root, prior_packet)
    if (not old_audit["gates"]["later_effect_qualification"] or
            old_audit["first_unpassed_gate"] != "native_train_screen"):
        raise ValueError("previous qualification/rejection differs")
    actor_path = prior_packet / "combination/candidate-model.json"
    if (lab.common._binding(actor_path)["sha256"] != ACTOR_SHA or
            lab.common._binding(args.rom)["sha256"] != lab.common.ROM_SHA256):
        raise ValueError("actor or cartridge differs")
    actor = combined.model(actor_path)
    history_targets, history_bindings = [], []
    if broad:
        history = args.root / "red-outcome-value-pilot-20260922-v2"
        expected = {"plan.json": "cb44e9db0fccb3fe786a707eb9e8d477b275e897995f808377d7b3a2933cbcc7",
            "result.json": "600c39dcb4fdc36b4aa0ba8c44792107252d8e45c5b0c2fca5f0086cf72b6ddc",
            "candidate-model.json":
                "4e3f8bd73bafacc4bb1aa735c36732c1355ed67916302ce058e52ea308b5ad64",
            "independent-audit.json":
                "4a7b7b8a661bf17f4ff96f3fb52759d53951db2f980ea1cb2da2623670ea0f96"}
        for name, digest in expected.items():
            binding = lab.common._binding(history / name)
            if binding["sha256"] != digest:
                raise ValueError("closed V2 evidence differs")
            history_bindings.append(binding)
        verify_targets(history / "targets", actor)
        audit(history / "targets", projector=loop.project_balanced_status_moves,
              return_value=win_conditioned_return, plan_path=history / "plan.json")
        history_paths = sorted((history / "targets").glob("*/target.json"))
        history_targets = [loop.load(p) for p in history_paths]
        if len(history_targets) != 30:
            raise ValueError("V2 target inventory differs")
        history_bindings.extend(lab.common._binding(p) for p in
                                sorted((history / "targets").glob("*/target.json")))
        for manifest in history.glob("**/capture.state.json"):
            c = loop.open_battle_scenario_capture(manifest.with_suffix(""), manifest)
            excluded.add(c.manifest.state_sha256)
        actor_path = history / "candidate-model.json"
        actor = combined.model(actor_path)
    _, inputs, originals, initial, frozen = combined.previous.load_inputs(args.root)
    prior_plan = loop.load(prior_packet / "combination/plan.json")
    groups = combined.validate_view(Path(prior_plan["reward"]["path"]), args.root)["groups"]
    effect = loop.load(Path(prior_plan["effect"]["path"]))
    basis = combined.model(Path(prior_plan["prior"]["path"]))
    old_problem = combined.prepare_combination(groups, initial, frozen, basis, originals, effect)
    if len(old_problem.protected) != 182:
        raise ValueError("original182preferences differ")
    if history_targets:
        old_problem = extend_problem(old_problem, actor, history_targets)
        groups = [*groups, history_targets]
    sources = sorted(lab.common._source_rows(args.root / "red-fresh-trainer-train-batch-20260917"),
                     key=lambda p: p[1]["source_id"])
    roots = [r["source_id"] for _, r in sources]
    if set(roots) != set(actor.train_root_ids):
        raise ValueError("TRAIN ancestry differs")
    cartridge = lab.RedPracticeCartridge(args.rom.read_bytes())
    train, screen = recipes(cartridge, roots, broad=broad)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=lab.ROOT).decode().strip()
    args.output.mkdir(mode=0o700)
    lab.write(args.output / "plan.json", {"source_commit": commit, "train": train, "screen": screen,
        "actor": lab.common._binding(actor_path), "prior_audit": old_audit,
        "inputs_sha256": loop.canonical_sha256(inputs), "offsets": OFFSETS,
        "sources": [lab.common._binding(p / "source.state.json") for p, _ in sources],
        "return_schema": RETURN_SCHEMA, "max_episodes": max_episodes, "max_frames": max_frames,
        "max_minutes": 90, "max_fits": 1, "capture_decisions": indices,
        "broad_successor": broad, "retained_train_inputs": history_bindings,
        "protocol": "outcome-readiness-v2-owner-approved-20260922", "actor_promotions": 0,
        "independent_natural_roots": 0, "old_reserved_access": False,
        "retired_plan": lab.common._binding(retired / "plan.json"),
        "retired_failure": lab.common._binding(retired / "failure.json"),
        "excluded_state_sha256": sorted(excluded)})
    began = time.monotonic()

    def deadline():
        if time.monotonic()-began > 5400:
            raise TimeoutError("outcome value pilot90minute cap")

    targets, coverage, seen = [], [], set(excluded)
    runtime = copy(args)
    runtime.output = args.output / "starts"
    runtime.output.mkdir()
    target_dir = args.output / "targets"
    target_dir.mkdir()
    trajectories = args.output / "trajectories"
    trajectories.mkdir()
    result = {"fits": 0, "collection_gate": False, "fit": None, "screen": None,
              "actor_promotions": 0}
    try:
        for i, recipe in enumerate(train):
            deadline()
            c = lab.materialize(runtime, recipe, i, sources, cartridge, commit)
            if c.manifest.state_sha256 in seen:
                raise ValueError("prospective start overlaps a consumed state")
            folder = trajectories / recipe["id"]
            lab.play(args, c, actor, folder, cartridge, horizon=40,
                     capture_decisions=indices, capture_source_commit=commit)
            states = [("opening", c)]
            for index in indices:
                kind = f"later-{index:03d}" if broad else "later"
                snapshot = folder / "snapshots" / f"decision-{index:03d}"
                if snapshot.exists():
                    later, contrast = reopen_snapshot(args, snapshot, cartridge, frozen)
                    if contrast:
                        states.append((kind, later))
                    else:
                        coverage.append({"case": recipe["id"], "kind": kind,
                                         "status": "no_contrast"})
                else:
                    coverage.append({"case": recipe["id"], "kind": kind, "status": "not_reached"})
            for kind, capture in states:
                if capture.manifest.state_sha256 in seen:
                    raise ValueError("duplicate state in prospective measurements")
                seen.add(capture.manifest.state_sha256)
                target = measure(args, capture, target_dir / (recipe["id"] + "-" + kind),
                                 cartridge, frozen, actor, deadline)
                coverage.append({"case": recipe["id"], "kind": kind, "family": recipe["family"],
                                 "status": "measured" if target else "predecision_sleep"})
                if target:
                    targets.append(target)
            lab.write(folder / "coverage.json", coverage[-len(states):])
            print(json.dumps({"trajectory": i+1, "contexts": len(targets)}), flush=True)
        lab.write(args.output / "coverage.json", coverage)
        verify_targets(target_dir, actor)
        checked = audit(target_dir, projector=loop.project_balanced_status_moves,
                        return_value=win_conditioned_return, plan_path=args.output / "plan.json")
        lab.write(args.output / "target-audit.json", checked)
        diagnostics = target_diagnostics(targets, actor)
        measured = [c for c in coverage if c["status"] == "measured"]
        result["collection_gate"] = (len(targets) >= (64 if broad else 8) and
            {c["family"] for c in measured} == {r["family"] for r in train} and
            sum(c["kind"].startswith("later") for c in measured) >= (16 if broad else 4) and
            diagnostics["frozen_actor_errors"] >= 2)
        result["diagnostics"] = diagnostics
        if result["collection_gate"]:
            deadline()
            problem = extend_problem(old_problem, actor, targets)
            candidate, fit = fit_once(problem, actor, targets, groups, initial)
            lab.write(args.output / "candidate-model.json", candidate.to_dict())
            reopened = combined.model(args.output / "candidate-model.json")
            if reopened.to_dict() != candidate.to_dict() or any(not np.array_equal(
                    reopened.move.scores(t["vectors"]), candidate.move.scores(t["vectors"]))
                    for t in targets):
                raise ValueError("fitted checkpoint round trip differs")
            lab.write(args.output / "fit.json", {**fit,
                "candidate": lab.common._binding(args.output / "candidate-model.json")})
            result.update(fits=1, fit=fit)
            if fit["passed"]:
                runtime.output = args.output / "screen-starts"
                runtime.output.mkdir()
                starts = []
                for i, recipe in enumerate(screen):
                    deadline()
                    c = lab.materialize(runtime, recipe, i, sources, cartridge, commit)
                    if (c.manifest.state_sha256 in seen or
                            c.manifest.capture_id in candidate.train_capture_ids):
                        raise ValueError("screen overlaps fitting states")
                    seen.add(c.manifest.state_sha256)
                    starts.append((recipe["id"], c))
                base = loop.evaluate(args, starts, frozen, args.output / "screen-baseline",
                                     cartridge, status=False, deadline=deadline)
                chosen = loop.evaluate(args, starts, candidate, args.output / "screen-candidate",
                                       cartridge, status=True, deadline=deadline)
                combined.verify_screen(args.output / "screen-baseline", frozen, frozen)
                combined.verify_screen(args.output / "screen-candidate", candidate, frozen)
                result["screen"] = outcome_gate(chosen, base)
        native = audit(args.output)
        if native["episodes"] > max_episodes or native["frames"] > max_frames:
            raise ValueError("pilot native budget exceeded")
        lab.write(args.output / "result.json", {**result, "native": native,
                                               "seconds": time.monotonic()-began})
        print(json.dumps(result), flush=True)
    except Exception as exc:
        lab.write(args.output / "failure.json", {"type": type(exc).__name__, "error": str(exc)})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "rom", "output"):
        parser.add_argument("--"+name, type=Path, required=True)
    parser.add_argument("--approved-successor", action="store_true",
                        help="only after explicit approval of the separate corrected packet")
    parser.add_argument("--broad-successor", action="store_true",
                        help="standing-authorized V3: all families and later on-policy states")
    run(parser.parse_args())
