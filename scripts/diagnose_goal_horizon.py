#!/usr/bin/env python3
"""Compare fixed synthetic goal horizons, not live decisions or training labels.

Every macro outcome and final-goal result below is stipulated toy evidence, not
a model prediction or an observation from Red. A recovery restores one positive
but sometimes unnecessary PP unit. Story advances one of 36 toy objectives;
both successful macros receive their actual existing utility's success bonus.
Costs use the same fixed normalization across plans, not a fresh denominator per
step. There are no refunds for HP/PP restoration and no invented collection gain.

The comparison orders *known hindsight* by final-goal completion within a fixed
action/frame budget, then existing weighted cumulative cost. It is not a new
production utility or an actor: at decision time these future facts are unknown.
Unknown/interrupted terminal evidence is excluded from hindsight ranking, not
converted into failure. Summed scores for it describe only its observed prefix.
No ROM, model file, real trajectory, private artifact or emulator is accessed.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pokemon_red_completion.living_dex_goal_policy import (  # noqa: E402
    DEFAULT_LIVING_DEX_GOAL_UTILITY,
)
from pokemon_red_completion.living_dex_option_value import LivingDexPredictedOutcome  # noqa: E402


class TerminalEvidence(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    UNKNOWN = "unknown"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True, slots=True)
class ToyStep:
    name: str
    outcome: LivingDexPredictedOutcome
    restored_pp: int = 0


@dataclass(frozen=True, slots=True)
class ToyPlan:
    name: str
    steps: tuple[ToyStep, ...]
    terminal_evidence: TerminalEvidence

    def __post_init__(self) -> None:
        if (
            not self.name or not isinstance(self.steps, tuple) or not self.steps
            or not all(isinstance(step, ToyStep) for step in self.steps)
            or not isinstance(self.terminal_evidence, TerminalEvidence)
        ):
            raise ValueError("toy plan requires steps and explicit terminal evidence")


@dataclass(frozen=True, slots=True)
class ToyCase:
    name: str
    plans: tuple[ToyPlan, ...]
    action_budget: float = 1.0
    frame_budget: float = 1.0

    def __post_init__(self) -> None:
        if (
            not self.name or not isinstance(self.plans, tuple) or not self.plans
            or len({plan.name for plan in self.plans}) != len(self.plans)
        ):
            raise ValueError("toy case needs uniquely named plans")
        if any(
            type(value) not in (int, float) or not math.isfinite(value) or value <= 0
            for value in (self.action_budget, self.frame_budget)
        ):
            raise ValueError("toy budgets must be finite positive quantities")


def fixed_cases() -> tuple[ToyCase, ...]:
    """Immutable counterexamples, not counterfactual outcomes of a real choice."""
    restore = ToyStep(
        "positive_recovery",
        LivingDexPredictedOutcome(1, 0, 0, .01, .01, .05, 0, 0, 0),
        restored_pp=1,
    )
    story = ToyStep(
        "successful_story",
        LivingDexPredictedOutcome(1, 0, 1 / 36, .10, .10, 0, .20, 0, 0),
    )
    failed_story = ToyStep(
        "failed_story_without_needed_recovery",
        LivingDexPredictedOutcome(0, 0, 0, .10, .10, 0, .20, 0, 0),
    )
    direct = ToyPlan("story_now", (story,), TerminalEvidence.COMPLETE)
    recovered = ToyPlan("recover_then_story", (restore, story), TerminalEvidence.COMPLETE)
    return (
        ToyCase("optional_positive_recovery", (direct, recovered)),
        ToyCase("necessary_recovery", (
            ToyPlan("story_now", (failed_story,), TerminalEvidence.INCOMPLETE), recovered,
        )),
        ToyCase("completion_after_budget_is_not_within_budget", (direct, recovered), .10, .10),
        ToyCase("repeated_maintenance_success_bonus", (
            direct,
            ToyPlan("five_positive_recoveries", (restore,) * 5, TerminalEvidence.INCOMPLETE),
        )),
        ToyCase("terminal_evidence_censored", (
            ToyPlan("unknown_after_recovery", (restore,), TerminalEvidence.UNKNOWN),
            ToyPlan("interrupted_after_recovery", (restore,), TerminalEvidence.INTERRUPTED),
        )),
    )


def summarize_plan(
    plan: ToyPlan, *, action_budget: float, frame_budget: float,
) -> dict[str, object]:
    """Score stipulated macro facts; never substitute a terminal label for them."""
    utility = DEFAULT_LIVING_DEX_GOAL_UTILITY
    actions = math.fsum(step.outcome.action_cost for step in plan.steps)
    frames = math.fsum(step.outcome.frame_cost for step in plan.steps)
    exceeds_budget = actions > action_budget or frames > frame_budget
    censored = plan.terminal_evidence in {TerminalEvidence.UNKNOWN, TerminalEvidence.INTERRUPTED}
    complete = None if censored else (
        plan.terminal_evidence is TerminalEvidence.COMPLETE and not exceeds_budget
    )
    cost = math.fsum(
        -utility.score(replace(
            step.outcome, verified_success=0, completion_gain=0, dependency_unlock_gain=0,
        ))
        for step in plan.steps
    )
    return {
        "plan": plan.name,
        "macro_steps": len(plan.steps),
        "positive_pp_restored": sum(step.restored_pp for step in plan.steps),
        "first_macro_utility": utility.score(plan.steps[0].outcome),
        "naive_sum_utility": math.fsum(utility.score(step.outcome) for step in plan.steps),
        "cumulative_cost": cost,
        "action_cost": actions,
        "frame_cost": frames,
        "terminal_evidence": plan.terminal_evidence.value,
        "budget_exceeded": exceeds_budget,
        "completion_within_budget": complete,
        "censored": censored,
    }


def diagnose_case(case: ToyCase) -> dict[str, object]:
    summaries = [summarize_plan(
        plan, action_budget=case.action_budget, frame_budget=case.frame_budget,
    ) for plan in case.plans]
    # Names only break exact ties to keep presentation deterministic; they are
    # not features or outcome preferences of any production actor.
    first_order = sorted(summaries, key=lambda row: (
        -cast(float, row["first_macro_utility"]), str(row["plan"]),
    ))
    naive_order = sorted(summaries, key=lambda row: (
        -cast(float, row["naive_sum_utility"]), str(row["plan"]),
    ))
    settled = [row for row in summaries if not row["censored"]]
    hindsight_order = sorted(settled, key=lambda row: (
        row["completion_within_budget"] is not True,
        cast(float, row["cumulative_cost"]), str(row["plan"]),
    ))
    return {
        "case": case.name,
        "budget": {"action_cost": case.action_budget, "frame_cost": case.frame_budget},
        "plans": summaries,
        "first_macro_ranking": [row["plan"] for row in first_order],
        "naive_sum_ranking": [row["plan"] for row in naive_order],
        "completion_once_hindsight_ranking": [row["plan"] for row in hindsight_order],
        "completion_once_hindsight_preferred": (
            hindsight_order[0]["plan"] if hindsight_order else None
        ),
    }


def diagnostic_report() -> dict[str, object]:
    return {
        "schema": "pokemon.synthetic.goal-horizon-diagnostic.v1",
        "scope": "hindsight_toy_diagnostic_not_a_deployable_actor",
        "assumptions": [
            "All macro outcomes and terminal evidence are fixed synthetic stipulations.",
            "Future completion facts are oracle hindsight, unavailable to a live actor.",
            "One-step and naive sums use DEFAULT_LIVING_DEX_GOAL_UTILITY unchanged.",
            "Costs share fixed units across steps; completion is counted once within budget.",
            "Completion evidence is at plan end; earlier completion is not inferred.",
            "Unknown/interrupted terminal evidence is censored, never an inferred failure.",
            "Scores for censored cases describe only the known macro prefix.",
        ],
        "controller_actions": 0,
        "model_queries": 0,
        "training_labels_created": 0,
        "production_policy_changed": False,
        "authority_promotions": 0,
        "cases": [diagnose_case(case) for case in fixed_cases()],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)  # deliberately no model, trace, ROM, or output-file arguments
    print(json.dumps(diagnostic_report(), indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
