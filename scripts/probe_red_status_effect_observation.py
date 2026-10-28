"""One diagnostic fit on authenticated existing TRAIN data; no emulator or actor writes."""

import argparse
import json
import subprocess
import time
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit

from pokemon_red_completion.red_balanced_status_features import (
    BALANCED_STATUS_NAMES,
    COMPACT_STATUS_NAMES,
)
from pokemon_red_completion.red_status_effect_observation import observe_status_effect

SCHEMA = "pokemon.red.status.boundary-effect-probe.v1"


def balanced_weights(rows):
    """Equal roots, then contexts, then observed timings within each context."""
    roots = {r["root"] for r in rows}
    contexts = {root: {r["capture_id"] for r in rows if r["root"] == root} for root in roots}
    timings = Counter((r["root"], r["capture_id"]) for r in rows)
    return np.array([1 / (len(roots) * len(contexts[r["root"]]) *
                         timings[r["root"], r["capture_id"]]) for r in rows])


def coverage(rows):
    counts = Counter()
    for r in rows:
        outcome = r["evidence"]
        label = str(outcome["net_change"]) if outcome["kind"] == "observed" else outcome["kind"]
        counts[f'{outcome["family"]}:{label}'] += 1
    return dict(sorted(counts.items()))


def arrays(rows):
    x = np.array([[1., *r["features"]] for r in rows])
    y = np.array([r["evidence"]["net_change"] for r in rows], dtype=float)
    if (x.shape != (len(rows), 1 + len(COMPACT_STATUS_NAMES)) or not np.isfinite(x).all()
            or not np.isin(y, [0., 1.]).all()):
        raise ValueError("invalid observable predictor input")
    return x, y, balanced_weights(rows)


def objective(theta, x, y, w):
    scores = x @ theta
    loss = w @ (np.logaddexp(0, scores) - y * scores) + .0005 * (theta[1:] @ theta[1:])
    gradient = x.T @ (w * (expit(scores) - y))
    gradient[1:] += .001 * theta[1:]
    return float(loss), gradient


def metrics(rows, probabilities):
    _, y, w = arrays(rows)
    p = np.clip(np.asarray(probabilities), 1e-15, 1 - 1e-15)
    return {"rows": len(rows), "roots": len({r["root"] for r in rows}),
            "contexts": len({r["capture_id"] for r in rows}),
            "positive": int(y.sum()), "brier": float(w @ ((p-y)**2)),
            "log_loss": float(-w @ (y*np.log(p) + (1-y)*np.log1p(-p))),
            "confusion": {f"actual{a}_predicted{b}": int(((y == a) & ((p >= .5) == b)).sum())
                          for a in (0, 1) for b in (0, 1)}}


def probe(rows):
    keys = [(r["root"], r["capture_id"], r["offset"]) for r in rows]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate root/context/timing")
    owners = {}
    for row in rows:
        previous = owners.setdefault(row["capture_id"], row["root"])
        if previous != row["root"]:
            raise ValueError("context crosses roots")
    roots = sorted({r["root"] for r in rows})
    if len(roots) != 4:
        raise ValueError("expected four original TRAIN roots")
    held = roots[-1]
    observed = [r for r in rows if r["evidence"]["kind"] == "observed"]
    train = [r for r in observed if r["root"] != held]
    test = [r for r in observed if r["root"] == held]
    result = {"schema": SCHEMA, "held_train_root": held, "train_roots": roots[:-1],
              "fits": 0, "diagnostic_pass": False, "actor_promotions": 0,
              "coverage": coverage(rows),
              "coverage_by_root": {root: coverage([r for r in rows if r["root"] == root])
                                   for root in roots},
              "reasons": dict(Counter(r["evidence"]["reason"] for r in rows))}
    if any({r["evidence"]["net_change"] for r in subset} != {0, 1}
           for subset in (train, test)):
        return {**result, "stop": "insufficient_observed_classes"}
    x, y, w = arrays(train)
    xt, _, _ = arrays(test)
    start = time.monotonic()
    fit = minimize(objective, np.zeros(x.shape[1]), args=(x, y, w), jac=True,
                   method="L-BFGS-B", options={"maxiter": 500, "ftol": 1e-12})
    finite = bool(np.isfinite(fit.x).all() and np.isfinite(fit.fun)
                  and np.isfinite(fit.jac).all())
    result.update({"fits": 1, "solver": {"success": bool(fit.success), "finite": finite,
                   "iterations": int(fit.nit), "message": str(fit.message),
                   "seconds": time.monotonic() - start},
                   "stop": "fit_complete" if fit.success and finite else "fit_rejected"})
    if not finite:
        return result
    probabilities = {"train": expit(x @ fit.x), "held_train_root": expit(xt @ fit.x)}
    prevalence = float(w @ y)
    result.update({"feature_names": ["intercept", *COMPACT_STATUS_NAMES],
                   "diagnostic_weights": fit.x.tolist(), "train_prevalence": prevalence,
                   "subsets": {}})
    for name, subset in (("train", train), ("held_train_root", test)):
        p = probabilities[name]
        result["subsets"][name] = {
            "predictor": metrics(subset, p),
            "constant": metrics(subset, np.full(len(subset), prevalence)),
            "families": {family: metrics([r for r in subset if r["evidence"]["family"] == family],
                                        p[[r["evidence"]["family"] == family for r in subset]])
                         for family in sorted({r["evidence"]["family"] for r in subset})}}
    held_metrics = result["subsets"]["held_train_root"]
    result["diagnostic_pass"] = bool(fit.success and
        held_metrics["predictor"]["brier"] <= .9 * held_metrics["constant"]["brier"])
    return result


def inventory(root, deadline):
    import run_red_status_readout_learning as runner
    from build_red_status_reward_view import rescore_branch
    loop = runner.loop
    _, inputs, groups, _, _ = runner.load_inputs(root)
    paths = {loop.load(Path(b["path"]))["capture_id"]: Path(b["path"])
             for group in inputs["groups"] for b in group}
    rows = []
    for group in groups:
        for target in group:
            choices = [i for i, v in enumerate(target["vectors"])
                       if v[BALANCED_STATUS_NAMES.index("choice.status")] == 1.]
            if len(choices) != 1:
                raise ValueError("expected one status-first branch per context/timing")
            i = choices[0]
            slot = target["slots"][i]
            for offset in loop.OFFSETS:
                if time.monotonic() > deadline:
                    raise TimeoutError("effect probe60minute budget exhausted")
                directory = paths[target["capture_id"]].parent / f"branch-{offset}-{slot}"
                _, binding = rescore_branch(directory, target, slot, offset)
                ep = loop.load(directory / "episode.json")
                # Detect any source alteration between authentication and label extraction.
                if loop.lab.common._binding(directory / "episode.json") != binding["episode"]:
                    raise ValueError("episode changed during observation extraction")
                rows.append({"root": target["root"], "capture_id": target["capture_id"],
                    "offset": offset, "continuation_sha256": target["continuation_sha256"],
                    "features": target["vectors"][i][-len(COMPACT_STATUS_NAMES):],
                    "evidence": observe_status_effect(ep), "source": binding})
    if len(rows) != 936:
        raise ValueError("expected936authenticated status-first branches")
    return {"schema": SCHEMA, "inputs_sha256": loop.canonical_sha256(inputs), "rows": rows}


def main():
    import run_red_closed_loop_status as loop
    from audit_red_status_learning import sha

    from pokemon_red_completion import red_status_effect_observation as classifier
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=loop.lab.ROOT).strip():
        raise ValueError("new output and clean committed source required")
    args.output.mkdir(mode=0o700)
    loop.lab.write(args.output / "plan.json", {"schema": SCHEMA,
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"],
                                                 cwd=loop.lab.ROOT).decode().strip(),
        "classifier_sha256": sha(Path(classifier.__file__)), "runner_sha256": sha(Path(__file__)),
        "max_fits": 1, "max_iterations": 500, "max_minutes": 60,
        "gameplay_episodes": 0, "actor_promotions": 0,
        "held_root_rule": "lexicographically_last_of_four_original_TRAIN_roots",
        "prediction": "observable_net_change_conditional_on_execution_not_causal_success"})
    try:
        data = inventory(args.root, time.monotonic() + 3600)
        loop.lab.write(args.output / "inventory.json", data)
        result = probe(data["rows"])
        result["inventory"] = loop.lab.common._binding(args.output / "inventory.json")
        loop.lab.write(args.output / "result.json", result)
        print(json.dumps({k: v for k, v in result.items()
                          if k not in {"diagnostic_weights", "feature_names", "coverage_by_root"}},
                         indent=2), flush=True)
    except Exception as exc:
        loop.lab.write(args.output / "failure.json",
                       {"type": type(exc).__name__, "error": str(exc)})
        raise


if __name__ == "__main__":
    main()
