"""One narrow, assisted TRAIN effect predictor; never a battle actor or runtime gate."""

import argparse
import json
import subprocess
import time
from collections import Counter
from pathlib import Path

import numpy as np
import run_red_status_curriculum as lab
from probe_red_status_effect_observation import balanced_weights, objective
from qualify_red_status_effect_trace import native_first_actor_case, play_one, verify_pair
from red_status_root_coverage import crossed_recipes
from scipy.optimize import minimize
from scipy.special import expit

from pokemon_red_completion.red_balanced_status_features import (
    COMPACT_STATUS_NAMES,
    project_balanced_status_moves,
)
from pokemon_red_completion.red_status_effect_trace import TRACE_SCHEMA, effect_label

SEED = 2026092143
SCHEMA = "pokemon.red.measured-effect-learning.v1"
FAMILIES = ("heal", "rest", "confusion")
CONDITION = {"heal": "choice.heal_full_hp", "rest": "choice.heal_full_hp",
             "confusion": "choice.already_confused"}


def recipes(cartridge, roots):
    crossed = crossed_recipes(cartridge, roots, seed=SEED)
    diagnostic, learning = [], []
    for row in crossed:
        variant = int(row["id"].split("-")[-2])
        is_check = (row["family"] == "disable" and row["source_index"] < 2 and
                    (row["contrast"] == 0 or (variant == 0 and row["contrast"] == 1)))
        is_learning = row["family"] in FAMILIES and row["contrast"] in (0, 1)
        if not is_check and not is_learning:
            continue
        case = native_first_actor_case(row, cartridge)
        case["id"] = f"measured-{SEED}-" + row["id"]
        (diagnostic if is_check else learning).append(case)
    if (len(diagnostic) != 6 or len(learning) != 42 or
            sum(r["role"] == "train" for r in learning) != 36):
        raise ValueError("prospective packet size differs")
    return diagnostic, learning


def selected_trace_label(episode, trace, selected_move):
    """One-turn join; raw effect data is label-side only, never model input."""
    if len(episode["decisions"]) != 1 or trace["pending"] is not None or not trace["enabled"]:
        raise ValueError("expected one settled traced turn")
    step = episode["decisions"][0]
    executed = step["outcome"]["move_executed"]
    if type(executed) is not bool:
        raise ValueError("missing execution boolean")
    matches = [r for r in trace["records"] if r["before"]["turn"] == 0 and
               r["before"]["move"] == selected_move]
    if not executed:
        if matches:
            raise ValueError("suppressed choice has an effect invocation")
        return {"kind": "suppressed", "application_success": None,
                "reason": "selected_move_not_executed"}
    if len(matches) != 1:
        return {"kind": "unknown", "application_success": None,
                "reason": "missing_or_ambiguous_selected_effect"}
    record = matches[0]
    label = effect_label(record)
    state = step["state_before"]
    if (record["schema"] != TRACE_SCHEMA or label != record["label"] or
            record["before"]["enemy_species"] != state["opponent_species_id"] or
            record["before"]["enemy_slot"] != state["opponent_party_position"] or
            record["before"]["player_slot"] != state["active_party_slot"] - 1):
        raise ValueError("effect trace subject or recomputed label differs")
    return label


def authenticate_row(directory, capture, recipe, *, allow_terminal=False):
    """Bind source, selected decision, terminal and sidecar before label admission."""
    bind = lab.common._binding
    files = {name: bind(directory / name) for name in ("episode.json", "effect-trace.json")}
    episode = json.loads((directory / "episode.json").read_bytes())
    trace = json.loads((directory / "effect-trace.json").read_bytes())
    log = lab.verify_trainer_practice_event_log(directory / "events")
    events = [json.loads(p.read_bytes())["payload"]
              for p in sorted((directory / "events").glob("event-*.json"))]
    identity, terminal = events[0]["identity"], events[-1]
    stops = ({"player_turn_budget", "battle_won", "party_defeated"} if allow_terminal
             else {"player_turn_budget"})
    if (log["terminal_event"] != "run_finished" or log["incomplete_decisions"] or
            log["completed_decisions"] != 1 or episode["decision_count"] != 1 or
            episode["stop_reason"] not in stops or
            terminal["outcome"]["episode_sha256"] != lab.canonical_sha256(episode) or
            episode["capture_id"] != capture.manifest.capture_id or
            episode["manifest_sha256"] != capture.manifest_sha256 or
            identity["capture_id"] != capture.manifest.capture_id or
            identity["root"] != capture.manifest.root_lineage_id or
            identity["root"] != recipe["root"] or identity["partition"] != "train" or
            identity["forced_diagnostic_actions"] != 1 or not identity["traced"] or
            identity["actor_memory_writes"] or episode["memory_write_actions"] or
            episode["metrics"]["invalid_action_failures"]):
        raise ValueError("effect episode authentication differs")
    step = episode["decisions"][0]
    move = lab.FAMILIES[recipe["family"]]
    lead_moves = step["observation"]["features"]["party"]["lead"]["moves"]
    selected = next(m for m in lead_moves if m["slot_index"] == step["move_slot"] - 1)
    if (step["kind"] != "attack" or step["move_slot"] != identity["first_slot"] or
            selected["move_ref"] != lab.pokemon_red_move_ref(move)):
        raise ValueError("selected move differs")
    projected = project_balanced_status_moves(step["observation"],
        lab.BattleFeatureProjector(lab.PokemonRedBattleCatalog()).project(step["observation"]))
    vector = projected.candidate_vectors[projected.candidate_slots.index(step["move_slot"])]
    label = selected_trace_label(episode, trace, move)
    if label["kind"] == "observed" and label["family"] != recipe["family"]:
        raise ValueError("selected family differs")
    if any(bind(directory / name) != binding for name, binding in files.items()):
        raise ValueError("label source changed during admission")
    return {"schema": SCHEMA, "root": recipe["root"], "role": recipe["role"],
            "capture_id": capture.manifest.capture_id, "family": recipe["family"],
            "case": recipe["id"], "features": list(vector[-len(COMPACT_STATUS_NAMES):]),
            "evidence": label, "choice_owner": "forced_training_diagnostic",
            "source": {**files, "event_log": log, "terminal": bind(directory / "final.state"),
                       "capture_manifest": capture.manifest_sha256,
                       "capture_state": capture.manifest.state_sha256},
            "frames": episode["frames_executed"], "elapsed_ns": episode["elapsed_ns"]}


def support(rows, roots):
    if len({r["capture_id"] for r in rows}) != len(rows):
        raise ValueError("duplicate measured context")
    if {r["root"] for r in rows} != set(roots):
        raise ValueError("unexpected fitting roots")
    for root in roots:
        for family in FAMILIES:
            subset = [r for r in rows if r["root"] == root and r["family"] == family
                      and r["evidence"]["kind"] == "observed"]
            index = COMPACT_STATUS_NAMES.index(CONDITION[family])
            if ({r["evidence"]["application_success"] for r in subset} != {0, 1} or
                    {r["features"][index] for r in subset} != {0., 1.}):
                raise ValueError(f"missing measured support: {root}:{family}")


def arrays(rows):
    x = np.array([[1., *r["features"]] for r in rows])
    y = np.array([r["evidence"]["application_success"] for r in rows], dtype=float)
    if (x.shape != (len(rows), 1 + len(COMPACT_STATUS_NAMES)) or
            not np.isfinite(x).all() or not np.isin(y, [0., 1.]).all()):
        raise ValueError("invalid effect learning arrays")
    return x, y, balanced_weights(rows)


def fit_once(rows, roots):
    if any(r["role"] != "train" or r["family"] not in FAMILIES for r in rows):
        raise ValueError("reserved or unsupported rows cannot enter fitting")
    support(rows, roots)
    observed = [r for r in rows if r["evidence"]["kind"] == "observed"]
    x, y, w = arrays(observed)
    started = time.monotonic()
    fit = minimize(objective, np.zeros(x.shape[1]), args=(x, y, w), jac=True,
                   method="L-BFGS-B", options={"maxiter": 500, "ftol": 1e-12})
    result = {"schema": SCHEMA, "fits": 1, "weights": fit.x.tolist(),
              "feature_names": ["intercept", *COMPACT_STATUS_NAMES],
              "train_roots": roots, "train_prevalence": float(w @ y),
              "train_rows": len(observed), "iterations": int(fit.nit),
              "seconds": time.monotonic() - started, "message": str(fit.message),
              "success": bool(fit.success and np.isfinite(fit.x).all() and
                              np.isfinite(fit.fun) and np.isfinite(fit.jac).all()),
              "authority_promotions": 0, "prediction": "application_conditional_on_execution"}
    return result


def metrics(rows, fit):
    observed = [r for r in rows if r["evidence"]["kind"] == "observed"]
    x, y, w = arrays(observed)
    p = expit(x @ np.asarray(fit["weights"]))
    return {"rows": len(observed), "positive": int(y.sum()),
            "brier": float(w @ ((p-y)**2)),
            "constant_brier": float(w @ ((fit["train_prevalence"]-y)**2)),
            "errors_at_half": int(((p >= .5) != y).sum()),
            "predictions": [{"case": r["case"], "probability": float(prob), "label": int(label)}
                            for r, prob, label in zip(observed, p, y, strict=True)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "rom", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=lab.ROOT).strip():
        raise ValueError("new output and committed source required")
    frozen_path = args.root / "red-trainer-J-canonical-20260920-v1/candidate-model.json"
    if (lab.common._binding(args.rom)["sha256"] != lab.common.ROM_SHA256 or
            lab.common._binding(frozen_path)["sha256"] != lab.K_SHA):
        raise ValueError("cartridge or frozen K differs")
    frozen = lab.TrainerPracticeThreeHeadModel.from_dict(json.loads(frozen_path.read_bytes()))
    sources = sorted(lab.common._source_rows(args.root / "red-fresh-trainer-train-batch-20260917"),
                     key=lambda p: p[1]["source_id"])
    roots = [r["source_id"] for _, r in sources]
    if set(roots) != set(frozen.train_root_ids):
        raise ValueError("TRAIN ancestry differs")
    cartridge = lab.RedPracticeCartridge(args.rom.read_bytes())
    checks, cases = recipes(cartridge, roots)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=lab.ROOT).decode().strip()
    args.output.mkdir(mode=0o700)
    lab.write(args.output / "plan.json", {"schema": SCHEMA, "source_commit": commit,
        "seed": SEED, "checks": checks, "cases": cases,
        "sources": [lab.common._binding(p / "source.state.json") for p, _ in sources],
        "rom": lab.common._binding(args.rom), "frozen": lab.common._binding(frozen_path),
        "max_episodes": 54, "max_frames": 270000, "max_minutes": 90, "max_fits": 1,
        "max_iterations": 500, "l2_coefficient": .001, "feature_names": COMPACT_STATUS_NAMES,
        "actor_promotions": 0, "held_root": roots[-1],
        "gate": "held_brier<=0.9*train_constant_brier;no_family_regression;both_classes"})
    started, episodes, frames, pairs, rows = time.monotonic(), 0, 0, [], []

    def play(row, capture, arm, traced):
        nonlocal episodes, frames
        if time.monotonic() - started > 5400 or episodes >= 54:
            raise TimeoutError("packet budget exhausted")
        slot = next(i+1 for i, m in enumerate(row["practice"]["actor_moves"])
                    if m["move_ref"] == lab.pokemon_red_move_ref(lab.FAMILIES[row["family"]]))
        episodes += 1
        ep = play_one(args, capture, frozen, args.output / row["id"] / arm, cartridge,
                      slot, traced=traced)
        frames += ep["frames_executed"]
        if frames > 270000:
            raise TimeoutError("packet frame budget exhausted")
        return ep

    def collect(role):
        for row in cases:
            if row["role"] != role:
                continue
            capture = lab.materialize(args, row, row["source_index"], sources, cartridge, commit)
            play(row, capture, "traced", True)
            measured = authenticate_row(args.output / row["id"] / "traced", capture, row)
            lab.write(args.output / row["id"] / "measured.json", measured)
            rows.append(measured)
            print(json.dumps({"case": row["id"], "label": measured["evidence"]}), flush=True)

    try:
        for row in checks:
            capture = lab.materialize(args, row, row["source_index"], sources, cartridge, commit)
            plain, traced = play(row, capture, "plain", False), play(row, capture, "traced", True)
            pair = {"case": row["id"], **verify_pair(plain, traced,
                    args.output / row["id"], lab.FAMILIES["disable"])}
            lab.write(args.output / row["id"] / "pair.json", pair)
            pairs.append(pair)
        lab.write(args.output / "disable.json", {"pairs": pairs})
        if not any(p["effect"]["label"]["application_success"] == 1 for p in pairs):
            raise ValueError("no positive Disable within the frozen cap")
        collect("train")
        lab.write(args.output / "training.json", {"rows": rows})
        fit = fit_once(rows, roots[:-1])
        fit["training"] = lab.common._binding(args.output / "training.json")
        lab.write(args.output / "fit.json", fit)
        if not fit["success"]:
            raise ValueError("single fit failed; no reserved cases opened")
        fit_binding = lab.common._binding(args.output / "fit.json")
        collect("holdout")
        lab.write(args.output / "inventory.json", {"rows": rows})
        held = [r for r in rows if r["role"] == "holdout"]
        support(held, roots[-1:])
        measured = metrics(held, fit)
        families = {f: metrics([r for r in held if r["family"] == f], fit) for f in FAMILIES}
        if lab.common._binding(args.output / "fit.json") != fit_binding:
            raise ValueError("frozen predictor changed during evaluation")
        lab.write(args.output / "result.json", {"schema": SCHEMA, "episodes": episodes,
            "frames": frames, "seconds": time.monotonic() - started, "fits": 1,
            "fit": fit_binding, "inventory": lab.common._binding(args.output / "inventory.json"),
            "train": metrics([r for r in rows if r["role"] == "train"], fit),
            "held": measured, "held_families": families,
            "label_kinds": dict(Counter(r["evidence"]["kind"] for r in rows)),
            "diagnostic_pass": measured["brier"] <= .9 * measured["constant_brier"] and
                all(m["brier"] <= m["constant_brier"] for m in families.values()),
            "learned_battle_choices": 0, "actor_promotions": 0, "natural_transfer": False})
    except Exception as exc:
        lab.write(args.output / "failure.json", {"type": type(exc).__name__, "error": str(exc),
            "episodes_started": episodes, "completed_frames": frames, "measured_rows": len(rows)})
        raise


if __name__ == "__main__":
    main()
