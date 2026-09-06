#!/usr/bin/env python3
"""Show the current product lane and honest learning counters in a view-only dashboard."""

from __future__ import annotations

import argparse
import hashlib
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

from pokemon_red_completion.dashboard_relay import DashboardRelayState  # noqa: E402
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
    DashboardTrainingState,
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
    parser.add_argument("--live-port", type=int, default=8769)
    return parser


def _load_learning_evidence(
    path: Path = PROJECT_ROOT / "configs" / "dashboard-learning-evidence.json",
    *,
    repository_root: Path = PROJECT_ROOT,
) -> Mapping[str, object]:
    """Load only the hash-pinned public receipt, never a private model or save."""
    try:
        reference = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(reference, dict) or set(reference) != {"schema", "path", "sha256"}:
            raise ValueError
        if reference["schema"] != "pokemon.dashboard.learning-evidence-reference.v1":
            raise ValueError
        relative = Path(reference["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError
        target = (repository_root / relative).resolve(strict=True)
        if (
            not target.is_relative_to(repository_root.resolve())
            or target.stat().st_size > 1_000_000
        ):
            raise ValueError
        payload = target.read_bytes()
        if hashlib.sha256(payload).hexdigest() != reference["sha256"]:
            raise ValueError
        result = json.loads(payload)
        if not isinstance(result, dict):
            raise ValueError
        return result
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise ProgressDashboardError(
            "dashboard learning evidence is unavailable or changed"
        ) from error


def _training_projection(
    evidence: Mapping[str, object],
) -> tuple[DashboardTrainingState, DashboardLearningComponent]:
    if (
        evidence.get("schema") != "pokemon.red.living-dex-retired-bank-train-campaign-result.v1"
        or evidence.get("status") != "retired_bank_train_campaign_terminal"
    ):
        raise ProgressDashboardError("dashboard completed campaign evidence differs")
    fit = _mapping(evidence, "fit_result")
    if (
        fit.get("status") != "train_only_causal_model_update_complete"
        or fit.get("authority") != "non_authoritative_shadow_only"
        or fit.get("authority_promotions") != 0
        or fit.get("development_examples_read") != 0
        or fit.get("transfer_claimed") is not False
    ):
        raise ProgressDashboardError("dashboard training claim boundary differs")
    model = _mapping(fit, "model")
    error = _mapping(fit, "training_error")
    readiness = _mapping(evidence, "readiness")
    total = _count(model, "total_examples")
    added = _count(model, "added_settled_examples")
    new = _count(evidence, "causal_train_examples_recorded")
    if (
        readiness.get("ready") is not True
        or _count(readiness, "settled_examples") != new
        or _count(model, "settled_examples") != total
        or _count(evidence, "model_fits") != _count(fit, "fit_executions")
    ):
        raise ProgressDashboardError("dashboard training receipt joins differ")
    training = DashboardTrainingState(
        samples_before=total - added,
        samples_after=total,
        newly_collected=new,
        previously_unfitted=added - new,
        successful_examples=_count(fit, "successful_examples"),
        terminal_lessons=_count(evidence, "train_slots_terminal"),
        total_lessons=_count(readiness, "train_slots"),
        setup_censors=_count(readiness, "setup_censors"),
        fit_count=_count(fit, "fit_executions"),
        weighted_mse_before=error["prior_weighted_mse"],
        weighted_mse_after=error["updated_weighted_mse"],
        training_choice_changes=_count(fit, "policy_disagreements_on_train_menus"),
    )
    component = DashboardLearningComponent(
        name="Living-Pokédex goal scorer",
        scope="Chooses collection objectives; deterministic skills execute game mechanics",
        status="shadow",
        authority="shadow_only",
        train_examples=total,
        validation_examples=0,
        validation_correct=0,
        baseline_correct=None,
        model_sha256=_text(model, "model_sha256"),
        independent_validation_units=0,
    )
    return training, component


def product_focus_dashboard_snapshot(
    state: ProductFocusState,
    *,
    work: DashboardWorkState | None = None,
    evidence: Mapping[str, object] | None = None,
) -> DashboardSnapshot:
    """Project current evidence, without borrowing old gameplay counts as live state."""
    lane = state.active_lane
    reorientation = _mapping(lane, "latest_reorientation")
    training, component = _training_projection(
        evidence if evidence is not None else _load_learning_evidence()
    )
    output_event = "Historical cross-family ledger · " + " · ".join(
        f"{label.split(' ·', 1)[0]} {current}/{minimum}"
        for label, current, minimum in focus_scorecard(state)
    )
    return DashboardSnapshot(
        game="Pokémon Red",
        run_status=_run_status_for_work(work),
        stage=_event("Now", work.headline, maximum=96) if work else "Latest Red learning result",
        message=(
            work.detail
            if work
            else "The goal scorer is fitted. Next: several model-chosen objectives with verified "
            "collection progress. This overview is not a running emulator."
        ),
        stage_progress=_stage_progress(work),
        location=None,
        collection_observed=False,
        collection_target=151,
        model=DashboardModelState(
            mode="shadow",
            candidate=f"{training.samples_after}-example living-Pokédex goal scorer",
            choice="No live choice — trained artifact awaiting bounded play",
            decisions=0,
            teacher_queries=0,
            fallbacks=0,
        ),
        experiment=DashboardExperimentState(
            phase="complete",
            zero_shot_completed=training.samples_after,
            zero_shot_total=training.samples_after,
            adaptation_completed=training.newly_collected,
            adaptation_total=training.total_lessons,
            sealed_completed=training.setup_censors,
            sealed_total=training.total_lessons,
            predictions_committed=False,
            heading="Latest completed learning cycle",
            eyebrow="Red field lab / Living Pokédex project",
            counter_labels=("Examples in this model", "New factual outcomes", "Setup censors"),
        ),
        learning_components=(component,),
        training=training,
        work=work or DashboardWorkState(),
        events=(
            f"Saved model · {training.samples_before} → {training.samples_after} real examples",
            f"New data · {training.newly_collected} outcomes; "
            f"{training.setup_censors} setup censors",
            f"Retained earlier data · {training.previously_unfitted} previously unfitted examples",
            f"Training calibration · {training.training_choice_changes} changed menu choices",
            "Training error is not an unseen gameplay score; the updated model remains shadow-only",
            "No live party or collection ledger is attached; missing observations show as unknown",
            _event("Next session", _text(reorientation, "next_session_goal")),
            _event("Current limitation", _text(reorientation, "blocker")),
            _event("Mission", _text(state.product, "goal")),
            _event("Evidence", output_event),
            "Red first · Crystal adaptation later · multi-game living Pokédex is the product",
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
    evidence = _load_learning_evidence()
    snapshot = product_focus_dashboard_snapshot(focus, work=work, evidence=evidence)
    if args.port == args.live_port:
        raise ProgressDashboardError("overview and live observer ports must differ")
    state = DashboardRelayState(snapshot, live_port=args.live_port)
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
                        candidate_evidence = _load_learning_evidence()
                        _training_projection(candidate_evidence)
                        evidence = candidate_evidence
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
                    state.publish(
                        product_focus_dashboard_snapshot(focus, work=work, evidence=evidence)
                    )
                    state.poll()
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
