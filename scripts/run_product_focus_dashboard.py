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
    focus_scorecard,
    load_product_focus,
)

from pokemon_red_completion.dashboard_work_status import (  # noqa: E402
    DashboardWorkStatusError,
    load_dashboard_work_status,
)
from pokemon_red_completion.progress_dashboard import (  # noqa: E402
    DASHBOARD_DEFAULT_PORT,
    DashboardExperimentState,
    DashboardLearningComponent,
    DashboardModelState,
    DashboardSnapshot,
    DashboardState,
    DashboardWorkState,
    ProgressDashboardError,
    ProgressDashboardServer,
)

DEFAULT_PRODUCT_FOCUS_PORT = DASHBOARD_DEFAULT_PORT + 3
DEFAULT_WORK_STATUS_PATH = PROJECT_ROOT / ".dashboard-status" / "product-focus.json"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PRODUCT_FOCUS_PORT)
    parser.add_argument("--duration-seconds", type=int, default=0)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--work-status-file", type=Path, default=DEFAULT_WORK_STATUS_PATH)
    return parser


def product_focus_dashboard_snapshot(
    state: ProductFocusState,
    *,
    work: DashboardWorkState | None = None,
) -> DashboardSnapshot:
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
    composition_attempts = _count(progress, "composition_attempts")
    verified_compositions = _count(progress, "verified_composition_episodes")
    outputs = focus_scorecard(state)
    output_event = (
        " · ".join(
            f"{label.split(' ·', 1)[0]} {current}/{minimum}"
            for label, current, minimum in outputs
        )
        if outputs
        else (
            f"Cumulative learning · train outcomes {train_outcomes} · development outcomes "
            f"{development_outcomes} · fits {fits} · comparisons {unseen}"
        )
    )
    boundary_labels = {
        "additional_v3_trial_execution": "V3 execution",
        "campaign_execution": "campaign",
        "comparison_execution": "compare",
        "consumed_trial_retry": "retry",
        "unexecuted_counterfactual_target": "unexecuted counterfactual target",
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
        "routine_clean_power_teacher_factory": "clean-power teacher factory",
        "scenario_selection": "scenario",
        "sealed_red_evaluation": "sealed",
        "sealed_or_benchmark_root_use": "sealed/benchmark roots",
        "reused_v1_context_execution": "V1 context reuse",
        "scenario_substitution_after_selection": "post-choice substitution",
        "teacher_choice_or_fallback": "teacher choice/fallback",
        "teacher_route_hardening": "teacher",
        "transfer_claim": "transfer claim",
        "unpowered_model_quality_claim": "unpowered quality claim",
        "unmeasured_action_target": "unmeasured-action target",
        "v4_freeze_or_trial_execution": "V4 freeze/trial",
        "v4_trial_execution_before_reorientation": "V4 execution",
    }
    prohibited = " / ".join(
        boundary_labels.get(value, value.replace("_", " "))
        for value in _text_list(lane, "prohibited_actions")
    )
    return DashboardSnapshot(
        game="Cross-game Pokemon agent",
        run_status=_run_status_for_work(work),
        stage="Targeted Red update · supply validation before training",
        message=(
            "Five model-directed Red cases are terminal: four verified successes and one "
            "failure. The next gate must prove 10 untouched training roots and 8 separate "
            "paired evaluation roots before any new gameplay or fit."
        ),
        stage_progress=_stage_progress(work),
        location="Engineering gate · action-free inventory · Crystal transfer deferred",
        registered_species=18,
        living_species=14,
        collection_target=151,
        model=DashboardModelState(
            mode="shadow",
            candidate="18-example title-neutral living-Pokédex option model",
            choice="No live choice · building the next train/control evidence gate",
            confidence=None,
            decisions=5,
            teacher_queries=0,
            fallbacks=0,
        ),
        experiment=DashboardExperimentState(
            phase="catalog",
            zero_shot_completed=0,
            zero_shot_total=1,
            adaptation_completed=0,
            adaptation_total=10,
            sealed_completed=0,
            sealed_total=8,
            predictions_committed=False,
            heading="Next model update",
            eyebrow="Living-Pokédex mission · Red curriculum",
            counter_labels=(
                "Action-free capacity gate",
                "New train-only roots",
                "Fresh paired model/control roots",
            ),
        ),
        learning_components=(
            DashboardLearningComponent(
                name="Living-Pokédex option model",
                scope=(
                    "Ranks title-neutral acquisition, party, storage, supply and access goals"
                ),
                status="shadow",
                authority="shadow_only",
                train_examples=18,
                validation_examples=5,
                validation_correct=3,
                baseline_correct=None,
                model_sha256=(
                    "cbff99900be566347a1ce3d6ccbe0d0c935eb5c6a9a3f961accdbc96c9442a56"
                ),
                independent_validation_units=5,
            ),
            DashboardLearningComponent(
                name="One-turn battle scorer",
                scope="Expected utility across seven cartridge RNG timings",
                status="shadow",
                authority="shadow_only",
                train_examples=20,
                validation_examples=20,
                validation_correct=18,
                baseline_correct=20,
                baseline_id="legal fixed heuristic",
                model_sha256=(
                    "19ac6d3db3305c2e9979f1f31f0d70f4d7ae3df2737b64585313812aef7619db"
                ),
                independent_validation_units=4,
                paired_wins=0,
                paired_losses=2,
                paired_two_sided_exact_p=0.5,
            ),
        ),
        work=work or DashboardWorkState(),
        events=(
            "Current gate · validate untouched 10-train / 8-paired-development capacity",
            (
                "Five-case result · 4/5 verified successes · 60% threshold accuracy · "
                "Brier 0.397811 · log loss 2.458979"
            ),
            (
                "Largest errors · acquisition failed at 99.55% predicted success · party "
                "development succeeded at 0.10%"
            ),
            (
                "Gameplay gains · living collection 13→14 · registered 17→18 · capture "
                "supplies restored twice"
            ),
            f"Product · {_text(product, 'goal')}",
            _event("Capability", _text(lane, "capability")),
            _event("Authority now", _text(authority, "current")),
            _event("Authority target", _text(authority, "target")),
            output_event,
            (
                f"Cross-family totals · train examples {causal_train_examples} · logical "
                f"atomic {atomic_episodes} · attempts {development_episodes} · verified outcomes "
                f"{verified_outcomes} · atomic {atomic_episodes} · composition attempts "
                f"{composition_attempts} · verified compositions {verified_compositions}"
            ),
            _event("Reorientation", _text(reorientation, "decision")),
            (
                "Player stack · semantic goal manager · deterministic navigation, battle, "
                "capture, party and inventory skills · fresh-ledger verification · typed recovery"
            ),
            "Training boundary · five development cases are calibration only and cannot fit",
            (
                "Prospective train set · 4 acquisition · 4 party development · 1 storage · "
                "1 resupply · at least 8 settled"
            ),
            (
                "Prospective evaluation · at least 8 fresh paired roots · updated model vs "
                "frozen completion-first deterministic control"
            ),
            (
                "Authority boundary · the model may rank supported semantic goals only after a "
                "fresh comparison · deterministic code keeps mechanics and safety"
            ),
            (
                "Episode measures · completion-ledger delta · captures · quest progress · "
                "resource cost · faints · recoveries · replans"
            ),
            _event("Current blocker", _text(reorientation, "blocker")),
            _event("Next session", _text(reorientation, "next_session_goal")),
            _event("Next falsifier", _text(reorientation, "next_falsifier")),
            f"Authority promotions {authority_promotions} · transfer results {transfer_results}",
            _event("Closed", prohibited),
            _event("Next decision", _text(lane, "next_decision")),
            (
                "Player contract · authenticated snapshots · title-neutral semantic goals · "
                "typed skill results · fresh completion ledger · teacher labels 0"
            ),
        ),
    )


def _run_status_for_work(work: DashboardWorkState | None) -> str:
    if work is None:
        return "waiting"
    return {
        "idle": "waiting",
        "working": "running",
        "testing": "running",
        "waiting": "waiting",
        "blocked": "blocked",
        "complete": "passed",
    }[work.status]


def _stage_progress(work: DashboardWorkState | None) -> float:
    if work is not None and work.progress is not None:
        return work.progress
    return 0.0


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
    try:
        work = load_dashboard_work_status(args.work_status_file)
    except DashboardWorkStatusError:
        work = DashboardWorkState(
            status="blocked",
            headline="Dashboard status record needs attention",
            detail="The project evidence is safe, but the live work update could not be read.",
            current_step="Validate the local observer status",
            next_step="Resume automatic work updates",
        )
    snapshot = product_focus_dashboard_snapshot(focus, work=work)
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
        last_refresh = 0.0
        try:
            while args.duration_seconds == 0 or time.monotonic() - started < args.duration_seconds:
                now = time.monotonic()
                if now - last_refresh >= 1.0:
                    last_refresh = now
                    try:
                        focus = load_product_focus()
                        work = load_dashboard_work_status(args.work_status_file)
                    except (DashboardWorkStatusError, ProgressDashboardError):
                        work = DashboardWorkState(
                            status="blocked",
                            headline="Dashboard refresh needs attention",
                            detail=(
                                "The last safe snapshot remains visible while the local status "
                                "record is checked."
                            ),
                            current_step="Validate the observer inputs",
                            next_step="Resume automatic dashboard updates",
                        )
                    state.publish(product_focus_dashboard_snapshot(focus, work=work))
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
