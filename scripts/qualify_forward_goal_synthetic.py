#!/usr/bin/env python3
"""Run a controlled resource task; this is NOT Pokémon gameplay or real calibration.

The first sampled action is followed by one frozen continuation: restoration is
followed by a goal attempt; a goal attempt ends the episode. The actor observes
current energy and two fixed action descriptions, never the transition result.
Training repeats four toy start states and must not be described as independent
real-world evidence. Bounds and support ranges are declared here, before fitting.
All recorder appends are in-memory test events, not authenticated Red trajectories.
No ROMs, private artifacts, existing model files or controller interfaces are used.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pokemon_red_completion.forward_goal import (  # noqa: E402
    ForwardGoalChoice,
    ForwardGoalCounters,
    ForwardGoalOutcome,
    ForwardGoalPlan,
    ForwardGoalRecorder,
)
from pokemon_red_completion.forward_goal_learning import (  # noqa: E402
    ForwardGoalModel,
    ForwardGoalSelectionBounds,
    fit_forward_goal,
    select_forward_goal,
)
from pokemon_red_completion.provenance import canonical_sha256  # noqa: E402

PLAN = ForwardGoalPlan(
    "synthetic-resource-goal",
    canonical_sha256({"toy_goal": "one-goal-action-with-energy-at-least-half.v1"}),
    canonical_sha256({"continuation": "after-restore-attempt-goal-once-then-stop.v1"}),
    100,
    1000,
    4,
    2,
)
CONTEXT_NAMES = ("energy_fraction",)
CANDIDATE_NAMES = ("restore",)
CANDIDATES = ((0.0,), (1.0,))
TRAIN_ENERGIES = (0.1, 0.2, 0.8, 0.9)
QUALIFICATION_ENERGIES = (0.025, 0.075, 0.125, 0.175, 0.825, 0.875, 0.925, 0.975)
TEST_ENERGIES = (0.0, 0.05, 0.15, 0.195, 0.805, 0.85, 0.94, 0.99)
UNSUPPORTED_ENERGIES = (0.35, 0.5, 0.65)
BOUNDS = ForwardGoalSelectionBounds(0.08, 0.015, 0.25, 0.8)
RIDGE = 0.01
SEED = 2026090901


@dataclass(slots=True)
class ToyResourceTask:
    energy: float
    completed: bool = False
    actions: int = 0
    frames: int = 0
    resources: int = 0
    macros: int = 0

    def act(self, selected: int) -> None:
        if (
            self.completed
            or type(selected) is not int
            or selected not in (0, 1)
            or not 0 <= self.energy <= 1
            or (selected == 1 and self.energy == 1)
        ):
            raise ValueError("toy task is complete or choice unavailable")
        self.macros += 1
        if selected == 1:
            self.actions += 10
            self.frames += 200
            self.resources += 1
            self.energy = min(1.0, self.energy + 0.6)
        else:
            self.actions += 30
            self.frames += 300
            self.completed = self.energy >= 0.5
            self.energy = max(0.0, self.energy - 0.5)

    def counters(self) -> ForwardGoalCounters:
        return ForwardGoalCounters(self.actions, self.frames, self.resources, self.macros)


def collect_toy(
    *,
    episode: int,
    energy: float,
    selected: int,
    partition: str,
    interrupt_after_first_action: bool = False,
) -> tuple[ForwardGoalOutcome, list[dict[str, object]]]:
    task = ToyResourceTask(energy)
    events: list[dict[str, object]] = []
    recorder = ForwardGoalRecorder(PLAN, events.append)
    recorder.declare(initial_goal=task.completed)
    choice = ForwardGoalChoice(
        canonical_sha256({"toy_episode": episode}),
        canonical_sha256({"toy_initial_energy": energy}),
        partition,
        CONTEXT_NAMES,
        (task.energy,),
        CANDIDATE_NAMES,
        CANDIDATES,
        selected,
        (0.5, 0.5) if partition == "train" else tuple(float(i == selected) for i in range(2)),
    )
    recorder.anchor(choice)
    task.act(selected)
    if interrupt_after_first_action:
        # Simulate interruption before the post-action goal observation, even
        # when the simulator internally knows that the attempted goal succeeded.
        outcome = recorder.observe(task.counters(), goal=None, interrupted=True)
    else:
        outcome = recorder.observe(task.counters(), goal=task.completed, stop=selected == 0)
        if selected == 1:
            # Frozen continuation is mechanical, not another learned decision.
            task.act(0)
            outcome = recorder.observe(task.counters(), goal=task.completed, stop=True)
    if outcome is None:
        raise AssertionError("toy attempt did not reach its declared stop")
    return outcome, events


def supported(energy: float, plan: ForwardGoalPlan = PLAN) -> bool:
    return plan == PLAN and (0 <= energy <= 0.2 or 0.8 <= energy < 1)


def predict(model: ForwardGoalModel, energy: float, plan: ForwardGoalPlan = PLAN):
    return model.predict(
        plan=plan,
        context_names=CONTEXT_NAMES,
        context=(energy,),
        candidate_names=CANDIDATE_NAMES,
        candidates=CANDIDATES,
    )


def run_qualification() -> dict[str, object]:
    rng = random.Random(SEED)
    rows = []
    for episode in range(128):
        rows.append(
            collect_toy(
                episode=episode,
                energy=TRAIN_ENERGIES[episode % 4],
                selected=rng.randrange(2),
                partition="train",
            )[0]
        )
    # Known prefix evidence; neither a failure label nor a complete cost target.
    rows.append(
        collect_toy(
            episode=128, energy=0.2, selected=rng.randrange(2), partition="train",
            interrupt_after_first_action=True,
        )[0]
    )
    fit = fit_forward_goal(rows, ridge=RIDGE)
    completion_error = cost_error = 0.0
    qualification = []
    for number, energy in enumerate(QUALIFICATION_ENERGIES):
        estimates = predict(fit.model, energy)
        for option in range(2):
            actual, _ = collect_toy(
                episode=1000 + number * 2 + option,
                energy=energy,
                selected=option,
                partition="development",
            )
            assert actual.target is not None
            completion_error = max(
                completion_error, abs(estimates[option].completion - actual.target[0])
            )
            cost_error = max(cost_error, abs(estimates[option].cost - actual.target[1]))
        qualification.append({"energy": energy, "supported": supported(energy)})
    qualified = completion_error <= BOUNDS.completion_error and cost_error <= BOUNDS.cost_error
    # The separate test cases never alter fit, error bounds or supported ranges.
    tests = []
    for number, energy in enumerate((*TEST_ENERGIES, *UNSUPPORTED_ENERGIES)):
        estimates = predict(fit.model, energy)
        selection = select_forward_goal(
            estimates, supported=(supported(energy),) * 2, bounds=BOUNDS if qualified else None
        )
        outcome = None
        if selection is not None:
            outcome, _ = collect_toy(
                episode=2000 + number, energy=energy, selected=selection, partition="development"
            )
        tests.append(
            {
                "energy": energy,
                "supported": supported(energy),
                "completion_estimates": [p.completion for p in estimates],
                "cost_estimates": [p.cost for p in estimates],
                "selected_option": selection,
                "observed_target": None if outcome is None else list(outcome.target or ()),
                "regret_against_known_toy_optimum": None
                if outcome is None
                else (selection != (0 if energy >= 0.5 else 1)),
            }
        )
    return {
        "schema": "pokemon.synthetic.forward-goal-qualification.v1",
        "scope": "controlled_synthetic_not_pokemon_or_real_calibration",
        "prospective_configuration": {
            "plan": PLAN.public_dict(),
            "seed": SEED,
            "ridge": RIDGE,
            "train_energies": list(TRAIN_ENERGIES),
            "qualification_energies": list(QUALIFICATION_ENERGIES),
            "test_energies": list(TEST_ENERGIES),
            "unsupported_energies": list(UNSUPPORTED_ENERGIES),
            "completion_error_bound": BOUNDS.completion_error,
            "cost_error_bound": BOUNDS.cost_error,
            "equivalence_margin": BOUNDS.equivalence_margin,
            "minimum_completion": BOUNDS.minimum_completion,
        },
        "training": {
            "settled_examples": fit.model.settled_examples,
            "censored_examples": fit.model.censored_examples,
            "recorded_roots": fit.recorded_roots,
            "settled_roots": fit.settled_roots,
            "distinct_selected_inputs": fit.distinct_inputs,
            "completion_mse_before": fit.mse_before[0],
            "completion_mse_after": fit.mse_after[0],
            "cost_mse_before": fit.mse_before[1],
            "cost_mse_after": fit.mse_after[1],
            "dataset_sha256": fit.model.dataset_sha256,
            "model_sha256": fit.model.sha256,
        },
        "qualification": {
            "cases": qualification,
            "completion_max_error": completion_error,
            "cost_max_error": cost_error,
            "passed": qualified,
        },
        "tests": tests,
        "no_red_inputs": True,
        "red_training_rows_created": 0,
        "red_model_changed": False,
        "red_authority_promotions": 0,
        "limitations": [
            "Four repeated deterministic toy starts; no independent real-game coverage.",
            "Empirical toy error bounds are not calibrated Red confidence intervals.",
            "A frozen two-macro continuation, not a general planner or optimal Q model.",
            "No live adapter, persistent episode reader or real player promotion is implied.",
        ],
    }


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(json.dumps(run_qualification(), indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
