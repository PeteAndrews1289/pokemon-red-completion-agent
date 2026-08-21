#!/usr/bin/env python3
"""Show the current product lane and honest learning counters in a view-only dashboard."""

from __future__ import annotations

import argparse
import json
import sys
import time
import webbrowser
from collections.abc import Mapping
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from product_focus import (  # noqa: E402
    ProductFocusState,
    focus_progress_fraction,
    focus_scorecard,
    load_product_focus,
)

from pokemon_red_completion.progress_dashboard import (  # noqa: E402
    DASHBOARD_DEFAULT_PORT,
    DashboardExperimentState,
    DashboardModelState,
    DashboardSnapshot,
    DashboardState,
    ProgressDashboardError,
    ProgressDashboardServer,
)

DEFAULT_PRODUCT_FOCUS_PORT = DASHBOARD_DEFAULT_PORT + 3


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PRODUCT_FOCUS_PORT)
    parser.add_argument("--duration-seconds", type=int, default=0)
    parser.add_argument("--no-browser", action="store_true")
    return parser


def product_focus_dashboard_snapshot(state: ProductFocusState) -> DashboardSnapshot:
    lane = state.active_lane
    product = state.product
    progress = state.progress
    authority = _mapping(lane, "learned_authority")
    reorientation = _mapping(lane, "latest_reorientation")
    outcomes = _mapping(progress, "outcome_questions")
    train_outcomes = _count(outcomes, "train")
    development_outcomes = _count(outcomes, "development")
    fits = _count(progress, "model_fits")
    unseen = _count(progress, "unseen_comparisons")
    authority_promotions = _count(progress, "authority_promotions")
    transfer_results = _count(progress, "transfer_results")
    development_episodes = _count(progress, "development_episode_attempts")
    verified_outcomes = _count(progress, "verified_outcome_examples")
    atomic_episodes = _count(progress, "atomic_goal_episodes")
    causal_train_examples = _count(progress, "causal_train_examples")
    synthetic_train_outcomes = _count(progress, "synthetic_rootless_train_outcomes")
    synthetic_atomic_episodes = _count(progress, "synthetic_rootless_atomic_goal_episodes")
    synthetic_model_fits = _count(progress, "synthetic_rootless_model_fits")
    synthetic_unseen_comparisons = _count(
        progress,
        "synthetic_rootless_unseen_comparisons",
    )
    composition_attempts = _count(progress, "composition_attempts")
    verified_compositions = _count(progress, "verified_composition_episodes")
    outputs = focus_scorecard(state)
    output_event = (
        " · ".join(
            f"{label.split(' ·', 1)[0]} {current}/{minimum}" for label, current, minimum in outputs
        )
        if outputs
        else (
            f"Cumulative learning · train outcomes {train_outcomes} · development outcomes "
            f"{development_outcomes} · fits {fits} · comparisons {unseen}"
        )
    )
    synthetic_train_total = max(
        [
            8,
            synthetic_train_outcomes,
            *(
                minimum
                for label, _, minimum in outputs
                if label.startswith("Synthetic Rootless Train Outcome")
            ),
        ]
    )
    synthetic_fit_total = max(
        [
            1,
            synthetic_model_fits,
            *(
                minimum
                for label, _, minimum in outputs
                if label.startswith("Synthetic Rootless Model Fit")
            ),
        ]
    )
    synthetic_comparison_total = max(
        [
            synthetic_unseen_comparisons,
            *(
                minimum
                for label, _, minimum in outputs
                if label.startswith("Synthetic Rootless Unseen Comparison")
            ),
        ]
    )
    stop_conditions = _text_list(lane, "stop_conditions")
    boundary_labels = {
        "campaign_execution": "execute",
        "comparison_execution": "compare",
        "consumed_trial_retry": "retry",
        "crystal_execution": "Crystal",
        "development_payload_decode": "dev decode",
        "development_payload_disclosure": "dev disclosure",
        "full_game_replay": "replay",
        "gameplay_execution": "gameplay",
        "live_model_prediction": "live prediction",
        "live_private_artifact_access": "live private artifacts",
        "model_fit": "fit",
        "model_prediction": "prediction",
        "model_refit": "refit",
        "private_artifact_access": "private artifacts",
        "sealed_red_evaluation": "sealed Red",
        "teacher_route_hardening": "teacher routes",
    }
    prohibited = " / ".join(
        boundary_labels.get(value, value.replace("_", " "))
        for value in _text_list(lane, "prohibited_actions")
    )
    budgets = _mapping(state.document, "session_budget_percent")
    time_box = _mapping(lane, "time_box")
    return DashboardSnapshot(
        game="Cross-game Pokemon agent",
        run_status="waiting",
        stage=f"Active lane · {_text(lane, 'name')}",
        message=(
            "The exact dual-capability preflight runner is published and green. Next is the "
            "external audit, one public invocation freeze, and one action-free same-reset Red "
            "inspection; model score, claim write, action, and frame remain closed."
        ),
        stage_progress=focus_progress_fraction(state),
        location=(
            "Red preflight · authenticate one same-reset acquire/evolve menu → stop before score"
        ),
        collection_target=150,
        model=DashboardModelState(
            mode="shadow",
            candidate=(
                "V2 model a42db642 · exact bundle · held-out 4/4 · baseline 2/4 · no live "
                "authority · not scored"
            ),
            choice=(
                "Authenticate one real same-reset two-capability menu without scoring or action"
            ),
            decisions=0,
            teacher_queries=0,
            fallbacks=0,
        ),
        experiment=DashboardExperimentState(
            phase="catalog",
            zero_shot_completed=synthetic_train_outcomes,
            zero_shot_total=synthetic_train_total,
            adaptation_completed=synthetic_model_fits,
            adaptation_total=synthetic_fit_total,
            sealed_completed=synthetic_unseen_comparisons,
            sealed_total=synthetic_comparison_total,
            predictions_committed=False,
            heading="Product focus scorecard",
            eyebrow="Living Pokedex · transferable learned play",
            counter_labels=(
                "Synthetic train outcomes",
                "Synthetic rootless fits",
                "Eligible held-out comparisons",
            ),
        ),
        events=(
            f"Product · {_text(product, 'goal')}",
            _event("Capability", _text(lane, "capability")),
            _event("Authority now", _text(authority, "current")),
            _event("Authority target", _text(authority, "target")),
            output_event,
            (
                f"Cumulative causal board · train examples {causal_train_examples} · logical "
                f"atomic {atomic_episodes} · attempts {development_episodes} · verified outcomes "
                f"{verified_outcomes} · atomic {atomic_episodes} · composition attempts "
                f"{composition_attempts} · verified compositions {verified_compositions}"
            ),
            (
                f"Rootless board · train {synthetic_train_outcomes}/8 · atomic "
                f"{synthetic_atomic_episodes}/8 · fit {synthetic_model_fits} ineligible · "
                f"comparison {synthetic_unseen_comparisons} · result 4/4 vs 2/4 · candidate 0 · "
                "runner published · Antigravity + preflight next"
            ),
            _event("Reorientation", _text(reorientation, "decision")),
            _event("Current blocker", _text(reorientation, "blocker")),
            _event("Next session", _text(reorientation, "next_session_goal")),
            _event("Next falsifier", _text(reorientation, "next_falsifier")),
            f"Authority promotions {authority_promotions} · transfer results {transfer_results}",
            f"Hard boundaries · {prohibited}",
            (
                f"Session budget · data {_count(budgets, 'data_and_scenarios')}% · model "
                f"{_count(budgets, 'model_and_evaluation')}% · maintenance "
                f"{_count(budgets, 'maintenance_and_docs')}%"
            ),
            (
                f"Time box · {_count(time_box, 'maximum_sessions')} "
                f"{'session' if _count(time_box, 'maximum_sessions') == 1 else 'sessions'} / "
                f"{_count(time_box, 'maximum_hours')} hours"
            ),
            _event("Stop 1", stop_conditions[0]),
            _event("Stop 2", stop_conditions[1]),
            _event("Next decision", _text(lane, "next_decision")),
            (
                "Preflight · c3e07d26 · CI 32470280542/1 · 4603 passed · manifest first · "
                "fixed reset · semantic route · rows 2 · prediction/action/frame 0 · audits GO · "
                "Antigravity pending"
            ),
            (
                "Red preflight · 8d559d23 · CI 32458785817/1 · candidate 0 · prediction/claim/"
                "action/frame 0 · context closed · retry 0"
            ),
            (
                "V2 comparison · 90288f57 · CI 32449287128/1 · candidate 4/4 · baseline 2/4 · "
                "CE 0.206/0.693 · rows disclosed 0 · no retry"
            ),
            (
                "Paired result · TIE · base acquisition 1 · candidate acquisition 1 · each one "
                "decision · actions 244/244 · frames 16,296/16,296"
            ),
            (
                "Closed DEVELOP_TEAM freeze · 6077173 · CI 32177113545/1 green · manifest d77d9f9d "
                "· readiness_authentication · effects not attested · reported labels/fits/teacher "
                "0 · retry 0"
            ),
            (
                "Causal bootstrap qualified · aa65504 · CI 32179177930/1 green · clean process "
                "preloads 0 · private/ROM/claim/prediction effects 0"
            ),
        ),
    )


def _mapping(source: object, key: str) -> Mapping[str, object]:
    if not isinstance(source, Mapping):
        raise ProgressDashboardError("product focus dashboard source is invalid")
    value = source.get(key)
    if not isinstance(value, Mapping):
        raise ProgressDashboardError(f"product focus dashboard {key} is invalid")
    return value


def _text(source: object, key: str) -> str:
    value = source.get(key) if isinstance(source, Mapping) else None
    if not isinstance(value, str) or not value:
        raise ProgressDashboardError(f"product focus dashboard {key} is invalid")
    return value


def _count(source: object, key: str) -> int:
    value = source.get(key) if isinstance(source, Mapping) else None
    if type(value) is not int or value < 0:  # noqa: E721
        raise ProgressDashboardError(f"product focus dashboard {key} is invalid")
    return value


def _text_list(source: object, key: str) -> tuple[str, ...]:
    value = source.get(key) if isinstance(source, Mapping) else None
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ProgressDashboardError(f"product focus dashboard {key} is invalid")
    return tuple(value)


def _event(label: str, value: str, *, maximum: int = 180) -> str:
    event = f"{label} · {value}"
    if len(event) <= maximum:
        return event
    prefix = event[: maximum - 3].rsplit(" ", 1)[0]
    return f"{prefix}..."


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.duration_seconds < 0:
        raise ProgressDashboardError("dashboard duration must be non-negative")
    focus = load_product_focus()
    snapshot = product_focus_dashboard_snapshot(focus)
    state = DashboardState(snapshot)
    with ProgressDashboardServer(state, port=args.port) as dashboard:
        print(
            json.dumps(
                {
                    "schema": "pokemon.product-focus-dashboard.v1",
                    "url": dashboard.url,
                    "view_only": True,
                    "active_lane": focus.active_lane["id"],
                    "stage_progress": snapshot.stage_progress,
                    "model_fits": focus.progress["model_fits"],
                    "development_episode_attempts": focus.progress["development_episode_attempts"],
                    "causal_train_examples": focus.progress["causal_train_examples"],
                    "synthetic_rootless_train_outcomes": focus.progress[
                        "synthetic_rootless_train_outcomes"
                    ],
                    "synthetic_rootless_atomic_goal_episodes": focus.progress[
                        "synthetic_rootless_atomic_goal_episodes"
                    ],
                    "synthetic_rootless_model_fits": focus.progress[
                        "synthetic_rootless_model_fits"
                    ],
                    "synthetic_rootless_unseen_comparisons": focus.progress[
                        "synthetic_rootless_unseen_comparisons"
                    ],
                    "verified_outcome_examples": focus.progress["verified_outcome_examples"],
                    "verified_composition_episodes": focus.progress[
                        "verified_composition_episodes"
                    ],
                    "authority_promotions": focus.progress["authority_promotions"],
                    "transfer_results": focus.progress["transfer_results"],
                    "controller_endpoints": 0,
                    "private_path_fields": 0,
                },
                allow_nan=False,
                sort_keys=True,
            )
        )
        if not args.no_browser:
            webbrowser.open(dashboard.url)
        started = time.monotonic()
        try:
            while args.duration_seconds == 0 or time.monotonic() - started < args.duration_seconds:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
