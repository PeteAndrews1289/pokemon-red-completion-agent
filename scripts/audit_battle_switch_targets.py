#!/usr/bin/env python3
"""Fit an offline switch-target ranker on preassigned control lineages."""

from __future__ import annotations

import argparse
import json

from pokemon_red_completion.battle_control_labels import load_battle_control_artifact
from pokemon_red_completion.battle_switch_target_training import (
    fit_preassigned_switch_target_candidate,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-labels", action="append", required=True)
    parser.add_argument("--validation-labels", action="append", required=True)
    parser.add_argument("--hidden-units", type=int, default=2)
    parser.add_argument("--epochs", type=int, default=1000)
    parser.add_argument("--learning-rate", type=float, default=0.01)
    parser.add_argument("--l2", type=float, default=0.003)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    candidate = fit_preassigned_switch_target_candidate(
        tuple(load_battle_control_artifact(path) for path in args.training_labels),
        tuple(load_battle_control_artifact(path) for path in args.validation_labels),
        hidden_units=args.hidden_units,
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        l2=args.l2,
        seed=args.seed,
    )
    print(json.dumps(candidate.public_summary(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
