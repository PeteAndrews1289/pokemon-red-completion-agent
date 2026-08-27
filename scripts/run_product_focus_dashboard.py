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
    stop_conditions = _text_list(lane, "stop_conditions")
    boundary_labels = {
        "additional_v3_trial_execution": "V3 execution",
        "campaign_execution": "campaign",
        "comparison_execution": "compare",
        "consumed_trial_retry": "retry",
        "counterfactual_target": "counterfactual target",
        "crystal_execution": "Crystal",
        "development_payload_decode": "dev decode",
        "development_payload_disclosure": "dev disclosure",
        "full_game_replay": "replay",
        "gameplay_execution": "gameplay",
        "identity_bearing_policy_feature": "identity-bearing feature",
        "live_model_prediction": "prediction",
        "live_private_artifact_access": "live private artifacts",
        "model_fit": "fit",
        "model_prediction": "prediction",
        "model_refit": "refit",
        "outcome_balanced_row_selection": "outcome-balanced selection",
        "private_development_outcome_opening": "dev outcomes",
        "private_artifact_access": "private artifacts",
        "private_input_access": "private",
        "public_manifest_freeze": "manifest",
        "red_preflight_execution": "preflight",
        "rom_access": "ROM",
        "scenario_selection": "scenario",
        "sealed_red_evaluation": "sealed",
        "sealed_or_benchmark_root_use": "sealed/benchmark roots",
        "reused_v1_context_execution": "V1 context reuse",
        "scenario_substitution_after_selection": "post-choice substitution",
        "teacher_choice_or_fallback": "teacher choice/fallback",
        "teacher_route_hardening": "teacher",
        "transfer_claim": "transfer claim",
        "unpowered_model_quality_claim": "unpowered quality claim",
        "unselected_action_target": "unselected-action target",
        "v4_freeze_or_trial_execution": "V4 freeze/trial",
        "v4_trial_execution_before_reorientation": "V4 execution",
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
            "The title-neutral causal journal and Red live adapter are being qualified. No "
            "authentic causal example exists yet; gameplay authority and Crystal transfer remain "
            "at zero."
        ),
        stage_progress=focus_progress_fraction(state),
        location=(
            "Public engineering · policy projection → crash-safe journal → Red adapter → audits"
        ),
        collection_target=150,
        model=DashboardModelState(
            mode="waiting",
            candidate=(
                "No fitted causal living-Dex policy · historical ranker remains unpromoted"
            ),
            choice=(
                "No active model choice · next evidence is one settled Red causal train example"
            ),
            confidence=None,
            decisions=1,
            teacher_queries=0,
            fallbacks=0,
        ),
        experiment=DashboardExperimentState(
            phase="qualification",
            zero_shot_completed=causal_train_examples,
            zero_shot_total=max(1, causal_train_examples),
            adaptation_completed=0,
            adaptation_total=1,
            sealed_completed=0,
            sealed_total=1,
            predictions_committed=False,
            heading="Cross-title causal example pipeline",
            eyebrow="Red curriculum · powered benchmark · Crystal transfer",
            counter_labels=(
                "Authentic causal train example",
                "Powered Red benchmark",
                "Zero-shot Crystal result",
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
                f"Rootless · train {synthetic_train_outcomes}/8 · atomic "
                f"{synthetic_atomic_episodes}/8 · fit {synthetic_model_fits} · comparison "
                f"{synthetic_unseen_comparisons} · reader ecb93c44 qualified · Antigravity GO · "
                "V1 retry 0 · synthetic support is descriptive, not authentic authority"
            ),
            _event("Reorientation", _text(reorientation, "decision")),
            _event("Current blocker", _text(reorientation, "blocker")),
            _event("Next session", _text(reorientation, "next_session_goal")),
            _event("Next falsifier", _text(reorientation, "next_falsifier")),
            f"Authority promotions {authority_promotions} · transfer results {transfer_results}",
            _event("Closed", prohibited),
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
            _event(
                "First authentic option",
                "main a448f5b9 · CI 32878889059/1 green · acquisition selected 78.2% · "
                "actions 665 · frames 33672 · dependency 2→1 · fresh ledger settled · "
                "teacher/fallback 0 · retry 0",
            ),
            (
                "V3 terminal · main 14d7bcea · CI 32902297341/1 green · train ordinal 0 "
                "consumed · actions 4379 · frames 304680 · censored · causal target +0 · "
                "development untouched · retry 0"
            ),
            (
                "Observer repair · main c663c3f4 · CI 32913718889/1 green · tests 4730 · "
                "mutations 9/9 · ROM/private/action/frame/claim/prediction/teacher 0"
            ),
            (
                "Observed-arm redesign · variable-size menus · full-support propensities · "
                "hard masks · selected outcomes only · censored targets 0 · V4 retired unexecuted"
            ),
            (
                "V2 comparison · 90288f57 · CI 32449287128/1 · candidate 4/4 · baseline 2/4 · "
                "CE 0.206/0.693 · rows disclosed 0 · no retry"
            ),
            (
                "Paired result · TIE · base acquisition 1 · candidate acquisition 1 · each one "
                "decision · actions 244/244 · frames 16,296/16,296"
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
