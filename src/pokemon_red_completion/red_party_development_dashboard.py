"""View-only projection of the first real Red party-development outcome."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import cast

from pokemon_red_completion.progress_dashboard import (
    DashboardExperimentState,
    DashboardModelState,
    DashboardSnapshot,
    ProgressDashboardError,
)

PARTY_DEVELOPMENT_OUTCOME_EVIDENCE_SCHEMA = "pokemon-red-party-development-outcome-evidence-v1"


def party_development_dashboard_snapshot(
    evidence: Mapping[str, object],
) -> DashboardSnapshot:
    """Build a path-free result view without implying a fitted party policy."""

    if not isinstance(evidence, Mapping):
        raise TypeError("party-development evidence must be a mapping")
    if evidence.get("schema") != PARTY_DEVELOPMENT_OUTCOME_EVIDENCE_SCHEMA:
        raise ProgressDashboardError("party-development evidence schema is unsupported")
    if evidence.get("status") != "complete_rejected_accounting_ambiguity":
        raise ProgressDashboardError("party-development evidence status is unsupported")

    collection = _mapping(evidence, "outcome_collection")
    recovery = _mapping(evidence, "recovery_accounting")
    decision = _mapping(evidence, "decision")
    protected = _mapping(evidence, "protected_access")
    trials = _sequence(collection, "trials")
    if len(trials) != 2 or any(not isinstance(trial, Mapping) for trial in trials):
        raise ProgressDashboardError("party-development outcome requires two trials")
    typed_trials = tuple(cast(Mapping[str, object], trial) for trial in trials)
    lower, higher = typed_trials
    if [_count(trial, "candidate_index") for trial in typed_trials] != [0, 1]:
        raise ProgressDashboardError("party-development candidate order is invalid")
    if collection.get("runner_best_candidate_indices") != [1] or collection.get(
        "runner_target_distribution"
    ) != [0.0, 1.0]:
        raise ProgressDashboardError("party-development winner binding is invalid")
    if (
        collection.get("runner_reported_fully_measured") is not True
        or collection.get("runner_reported_learner_update_eligible") is not True
        or collection.get("publication_learner_update_eligible") is not False
        or _count(collection, "candidate_outcomes") != 2
    ):
        raise ProgressDashboardError("party-development outcomes are incomplete")

    for trial in typed_trials:
        if trial.get("evolution_completed") is not True or _count(trial, "faints"):
            raise ProgressDashboardError("party-development evolution or safety failed")
        if _count(trial, "initial_target_level") != 22 or _count(trial, "final_target_level") != 26:
            raise ProgressDashboardError("party-development level boundary drifted")
        frames = _count(trial, "frames_executed")
        target_experience = _count(trial, "target_experience_gained")
        observed_rate = _finite_nonnegative(trial, "target_experience_per_1000_frames")
        if not math.isclose(
            observed_rate,
            target_experience * 1_000 / frames,
            abs_tol=0.000001,
        ):
            raise ProgressDashboardError("party-development experience rate is inconsistent")
    lower_rate = _finite_nonnegative(lower, "target_experience_per_1000_frames")
    higher_rate = _finite_nonnegative(higher, "target_experience_per_1000_frames")
    if higher_rate <= lower_rate:
        raise ProgressDashboardError("party-development preferred rate is not higher")

    observed_center_routes = recovery.get("observed_total_counted_center_routes")
    if observed_center_routes != [
        _count(lower, "total_counted_center_routes"),
        _count(higher, "total_counted_center_routes"),
    ]:
        raise ProgressDashboardError("party-development recovery accounting is invalid")
    if (
        _count(recovery, "configured_max_healing_trips") != 40
        or recovery.get("phase_breakdown_retained") is not False
        or recovery.get("policy_conformance_proven") is not False
        or recovery.get("training_target_rejected") is not True
        or decision.get("real_party_development_execution_completed") is not True
        or decision.get("real_party_development_training_target_validated") is not False
        or decision.get("training_target_accepted") is not False
        or decision.get("model_fit") is not False
        or decision.get("party_policy_generalization_demonstrated") is not False
        or decision.get("authority_promoted") is not False
    ):
        raise ProgressDashboardError("party-development result overclaims its evidence")
    teacher_queries = _count(protected, "teacher_queries")
    if any(_count(protected, key) for key in protected):
        raise ProgressDashboardError("party-development protected-access counters must be zero")

    lower_frames = _count(lower, "frames_executed")
    higher_frames = _count(higher, "frames_executed")
    lower_actions = _count(lower, "controller_actions")
    higher_actions = _count(higher, "controller_actions")
    frame_savings = lower_frames - higher_frames
    speed_gain = frame_savings / lower_frames * 100

    return DashboardSnapshot(
        game="Pokémon Red",
        run_status="blocked",
        stage="Party outcome · execution complete, training target rejected",
        message=(
            "Both clones evolved safely, but aggregate Center accounting cannot prove the "
            "40-trip policy bound. The result is descriptive and will not train a model."
        ),
        frame_count=lower_frames + higher_frames,
        actions=lower_actions + higher_actions,
        stage_progress=1.0,
        location="Authenticated Cinnabar evolution-training snapshot",
        collection_target=124,
        model=DashboardModelState(
            mode="shadow",
            candidate="Title-neutral party-development outcome ledger",
            choice="No target · recovery accounting ambiguous",
            decisions=2,
            teacher_queries=teacher_queries,
            fallbacks=0,
        ),
        experiment=DashboardExperimentState(
            phase="blocked",
            zero_shot_completed=2,
            zero_shot_total=2,
            adaptation_completed=0,
            adaptation_total=1,
            sealed_completed=0,
            sealed_total=1,
            predictions_committed=False,
            heading="Party development outcome",
            eyebrow="Red model-first laboratory",
            counter_labels=(
                "One-shot trials",
                "Learner examples",
                "Authority promotions",
            ),
        ),
        events=(
            (
                "Both identical-state clones evolved the same trainee from level 22 to 26 "
                "with zero faints"
            ),
            (
                f"Lower band: {_count(lower, 'battles_completed')} battles · "
                f"{_count(lower, 'steps_taken')} steps · "
                f"{_count(lower, 'total_counted_center_routes')} Center routes · "
                f"{lower_frames:,} frames"
            ),
            (
                f"Higher band: {_count(higher, 'battles_completed')} battles · "
                f"{_count(higher, 'steps_taken')} steps · "
                f"{_count(higher, 'total_counted_center_routes')} Center routes · "
                f"{higher_frames:,} frames"
            ),
            f"Target XP rate improved {lower_rate:.3f} → {higher_rate:.3f} per 1,000 frames",
            (
                f"Higher band saved {frame_savings:,} frames ({speed_gain:.1f}%) and "
                f"{lower_actions - higher_actions:,} controller actions"
            ),
            "Recovery audit: 42 aggregate Center routes against a configured 40-trip policy",
            (
                "Phase breakdown was not retained; no post-hoc recovery/setup/cleanup "
                "split is accepted"
            ),
            "Teacher 0 · sealed Red 0 · Crystal 0 · full-game replays 0",
            (
                "Next: split and bound every Center-call phase, then freeze a fresh independent "
                "party context"
            ),
        ),
    )


def _mapping(source: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = source.get(key)
    if not isinstance(value, Mapping):
        raise ProgressDashboardError(f"party-development {key.replace('_', ' ')} is invalid")
    return value


def _sequence(source: Mapping[str, object], key: str) -> Sequence[object]:
    value = source.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ProgressDashboardError(f"party-development {key.replace('_', ' ')} is invalid")
    return value


def _count(source: Mapping[str, object], key: str) -> int:
    value = source.get(key)
    if type(value) is not int or value < 0:  # noqa: E721
        raise ProgressDashboardError(f"party-development {key.replace('_', ' ')} is invalid")
    return value


def _finite_nonnegative(source: Mapping[str, object], key: str) -> float:
    value = source.get(key)
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or float(value) < 0
    ):
        raise ProgressDashboardError(f"party-development {key.replace('_', ' ')} is invalid")
    return float(value)


__all__ = [
    "PARTY_DEVELOPMENT_OUTCOME_EVIDENCE_SCHEMA",
    "party_development_dashboard_snapshot",
]
