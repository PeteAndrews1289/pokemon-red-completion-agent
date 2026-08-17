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
    outputs = focus_scorecard(state)
    output_event = (
        " · ".join(f"{label} {current}/{minimum}" for label, current, minimum in outputs)
        if outputs
        else (
            f"Cumulative learning · train outcomes {train_outcomes} · development outcomes "
            f"{development_outcomes} · fits {fits} · comparisons {unseen}"
        )
    )
    outcome_question_total = max(
        train_outcomes + development_outcomes,
        sum(
            minimum
            for label, _, minimum in outputs
            if label.startswith("Outcome Question")
        ),
    )
    model_fit_total = max(
        (
            fits,
            *(minimum for label, _, minimum in outputs if label.startswith("Model Fit")),
        )
    )
    unseen_comparison_total = max(
        (
            unseen,
            *(
            minimum
            for label, _, minimum in outputs
            if label.startswith("Unseen Comparison")
            ),
        )
    )
    stop_conditions = _text_list(lane, "stop_conditions")
    prohibited = ", ".join(
        value.replace("_", " ") for value in _text_list(lane, "prohibited_actions")
    )
    budgets = _mapping(state.document, "session_budget_percent")
    time_box = _mapping(lane, "time_box")
    return DashboardSnapshot(
        game="Cross-game Pokemon agent",
        run_status="waiting",
        stage=f"Active lane · {_text(lane, 'name')}",
        message=(
            "The reviewed three-decision composition core is published under green CI. No Red "
            "root is admitted and no prediction, controller input, or episode outcome exists."
        ),
        stage_progress=focus_progress_fraction(state),
        location="Development scenario laboratory · no cartridge session",
        collection_target=150,
        model=DashboardModelState(
            mode="waiting",
            candidate="Promoted Red goal manager af29d7e7… · frozen confidence floor 0.80",
            choice="Execution qualification pending · action-free root admission only",
            decisions=0,
            teacher_queries=0,
            fallbacks=0,
        ),
        experiment=DashboardExperimentState(
            phase="qualification",
            zero_shot_completed=train_outcomes + development_outcomes,
            zero_shot_total=outcome_question_total,
            adaptation_completed=fits,
            adaptation_total=model_fit_total,
            sealed_completed=unseen,
            sealed_total=unseen_comparison_total,
            predictions_committed=False,
            heading="Product focus scorecard",
            eyebrow="Living Pokedex · transferable learned play",
            counter_labels=(
                "Measured outcome questions",
                "Train-only model fits",
                "Unseen comparisons",
            ),
        ),
        events=(
            f"Product · {_text(product, 'goal')}",
            _event("Capability", _text(lane, "capability")),
            _event("Authority now", _text(authority, "current")),
            _event("Authority target", _text(authority, "target")),
            output_event,
            f"Last session · {_text(reorientation, 'session_id')}",
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
            f"Stop 1 · {stop_conditions[0]}",
            f"Stop 2 · {stop_conditions[1]}",
            _event("Next decision", _text(lane, "next_decision")),
            (
                "Qualification rail · fresh root → exact model + skills → one-shot ledger → hard "
                "limits → durable terminal → separate execution decision"
            ),
            "Composition design + ROM-free core published · runner not yet qualified",
            (
                "Current session roots 0 · predictions 0 · controller 0 · outcomes 0 · teacher 0 "
                "· sealed Red 0 · Crystal 0 · full replay 0"
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
