"""One unused paired cohort: evidence of learning, not a perfect-win exam."""

from __future__ import annotations

import argparse
import json
from math import comb
from pathlib import Path

import run_fresh_red_trainer_curriculum as common
from run_red_trainer_broad_fit import LATE_MODEL_SHA
from run_red_trainer_broad_probe import run as run_battles
from run_red_trainer_broad_probe import summarize

SEED = 2026091910


def learning_summary(evaluations):
    cells = {(row["case"], row["arm"]): row for row in evaluations}
    expected = {(i, arm) for i in range(24) for arm in ("frozen", "candidate")}
    if len(evaluations) != len(cells) or set(cells) != expected:
        raise ValueError("paired cohort must contain exactly one result for each case and arm")
    summary = summarize(evaluations)
    candidate_only = sum(
        cells[i, "candidate"]["battle_won"] and not cells[i, "frozen"]["battle_won"]
        for i in range(24)
    )
    frozen_only = sum(
        cells[i, "frozen"]["battle_won"] and not cells[i, "candidate"]["battle_won"]
        for i in range(24)
    )
    discordant = candidate_only + frozen_only
    checks = {
        "all_terminal_unassisted": summary["gates"]["all_terminal_unassisted"],
        "strict_paired_win_improvement": candidate_only > frozen_only,
        "faints_no_regression": summary["gates"]["faints_no_regression"],
    }
    return {
        "schema": "pokemon.red.battle-learning-signal.v1",
        "totals": summary["totals"],
        "candidate_only_wins": candidate_only,
        "frozen_only_wins": frozen_only,
        "descriptive_two_sided_paired_sign_p": min(
            1.0,
            2
            * sum(comb(discordant, k) for k in range(min(candidate_only, frozen_only) + 1))
            / 2**discordant,
        ),
        "checks": checks,
        "learning_signal_observed": all(checks.values()),
        "perfect_wins_required": False,
        "teacher_superiority_required": False,
        "uncertainty": (
            "Small descriptive generated-team cohort. Four TRAIN origins; "
            "not24 independent natural roots or proof of statistical significance."
        ),
        "natural_qualified": False,
        "final_player_ready": False,
        "authority_promotions": 0,
    }


def run(args):
    model_sha = common._binding(args.candidate)["sha256"]
    fit = json.loads((args.candidate.parent / "result.json").read_bytes())
    plan = json.loads((args.candidate.parent / "plan.json").read_bytes())
    if (
        plan["initial"]["sha256"] != LATE_MODEL_SHA
        or fit.get("fits") != 1
        or not fit.get("train_qualified")
        or not all(fit.get("gates", {}).values())
        or fit.get("model") != common._binding(args.candidate)
    ):
        raise ValueError("learning probe needs the one qualified policy-bound successor")
    run_battles(
        args, candidate_sha=model_sha, frozen_sha=LATE_MODEL_SHA, seed=SEED, teacher_reference=False
    )
    result = json.loads((args.output / "summary.json").read_bytes())
    learned = learning_summary(result["evaluations"])
    common._write(args.output / "learning-signal.json", learned)
    print(json.dumps(learned), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("rom", "batch", "candidate", "frozen", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
