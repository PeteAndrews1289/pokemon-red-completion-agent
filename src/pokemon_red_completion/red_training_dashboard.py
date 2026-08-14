"""Human-facing projection for Red model fitting and live shadow evaluation."""

from __future__ import annotations

from collections.abc import Mapping

from pokemon_red_completion.progress_dashboard import (
    DashboardExperimentState,
    DashboardLearningComponent,
    DashboardLiveEvaluationState,
    DashboardModelState,
    DashboardSnapshot,
)

RED_TRAINING_COMPONENTS = (
    DashboardLearningComponent(
        name="Goal manager",
        scope="Chooses what to pursue across nine title-neutral needs",
        status="offline",
        authority="offline",
        train_examples=54,
        validation_examples=27,
        validation_accuracy=1.0,
        baseline_accuracy=0.9259259259259259,
        model_sha256="af29d7e7f72e9921e638c88664b17e6fbbf6334468609ab66bda41c9f3dad66d",
    ),
    DashboardLearningComponent(
        name="Destination ranker",
        scope="Ranks strategic destinations without memorizing controller inputs",
        status="offline",
        authority="offline",
        train_examples=24,
        validation_examples=12,
        validation_accuracy=0.8333333333333334,
        baseline_accuracy=0.3333333333333333,
        model_sha256="753e3dbdb983d85acd9da5910fb92679a5406df39dfde84f68200d85378dd0c1",
    ),
    DashboardLearningComponent(
        name="Battle move ranker",
        scope="Chooses among legal moves; the teacher checks every live proposal",
        status="shadow",
        authority="teacher_supervised",
        train_examples=3320,
        validation_examples=1268,
        validation_accuracy=0.9865930599369085,
        baseline_accuracy=0.4098073555166375,
        model_sha256="822fb66ec27c0aee267fcb1b7103d389133d7e8c74274eee3e72bfc1f616c01f",
    ),
    DashboardLearningComponent(
        name="Team-development ranker",
        scope="Ranks training candidates and venues while the teacher executes",
        status="shadow",
        authority="shadow_only",
        train_examples=13709,
        validation_examples=7080,
        validation_accuracy=0.99900426742532,
        baseline_accuracy=0.9566145092460882,
        model_sha256="9286f1b42fcbffb2741d52a11359df0281c50501fe66100e8c795b4ffa37e026",
    ),
)


def live_evaluation_state(
    battle_policy: Mapping[str, object] | None,
    team_policy: Mapping[str, object] | None,
) -> DashboardLiveEvaluationState:
    """Project authenticated runtime reports into a small exact scorecard."""

    battle = battle_policy or {}
    team = team_policy or {}
    fallbacks = _count_value(battle, "teacher_fallbacks")
    reasons = battle.get("fallback_reasons")
    reason_counts = reasons if isinstance(reasons, Mapping) else {}
    unsupported = battle.get("unsupported_observation_errors")
    unsupported_counts = unsupported if isinstance(unsupported, Mapping) else {}
    return DashboardLiveEvaluationState(
        battle_decisions=_count_value(battle, "decisions"),
        teacher_agreements=_count_value(battle, "model_decisions"),
        teacher_disagreements=_mapping_count(reason_counts, "teacher_disagreement"),
        teacher_queries=_count_value(battle, "teacher_queries"),
        teacher_fallbacks=fallbacks,
        corrections_saved=_count_value(battle, "correction_records"),
        low_confidence_fallbacks=_mapping_count(reason_counts, "low_confidence"),
        unsupported_observations=sum(
            value
            for value in unsupported_counts.values()
            if type(value) is int and value >= 0  # noqa: E721
        ),
        team_decisions=_count_value(team, "decisions"),
        team_agreements=_count_value(team, "agreements"),
    )


def red_training_dashboard_snapshot(
    *,
    run_status: str,
    stage: str,
    message: str,
    frame_count: int,
    actions: int,
    stage_progress: float,
    live_evaluations_completed: int,
    live_evaluations_total: int,
    battle_policy: Mapping[str, object] | None = None,
    team_policy: Mapping[str, object] | None = None,
    emulation_speed: float = 0.0,
    location: str | None = None,
    registered_species: int = 0,
    living_species: int = 0,
    level_cap_species: int = 0,
    events: tuple[str, ...] = (),
) -> DashboardSnapshot:
    """Build a path-free dashboard snapshot for the Red learning lane.

    The dashboard deliberately calls this a shadow evaluation while the teacher
    retains disagreement authority. Offline goal and destination heads are
    shown as fitted without implying that they controlled the live run.
    """

    evaluation = live_evaluation_state(battle_policy, team_policy)
    mode = "shadow" if run_status in {"running", "passed", "failed"} else "waiting"
    return DashboardSnapshot(
        game="Pokémon Red",
        run_status=run_status,
        stage=stage,
        message=message,
        frame_count=frame_count,
        actions=actions,
        emulation_speed=emulation_speed,
        stage_progress=stage_progress,
        location=location,
        registered_species=registered_species,
        living_species=living_species,
        level_cap_species=level_cap_species,
        collection_target=124,
        model=DashboardModelState(
            mode=mode,
            candidate="Red player v1 · battle and team-development shadow",
            choice=(
                "Teacher checks each battle proposal; team choices stay shadow-only"
                if mode == "shadow"
                else "Waiting for the clean-power Red evaluation"
            ),
            decisions=evaluation.battle_decisions,
            teacher_queries=evaluation.teacher_queries,
            fallbacks=evaluation.teacher_fallbacks,
        ),
        experiment=DashboardExperimentState(
            phase="live_evaluation" if mode == "shadow" else "training",
            zero_shot_completed=len(RED_TRAINING_COMPONENTS),
            zero_shot_total=len(RED_TRAINING_COMPONENTS),
            adaptation_completed=len(RED_TRAINING_COMPONENTS),
            adaptation_total=len(RED_TRAINING_COMPONENTS),
            sealed_completed=live_evaluations_completed,
            sealed_total=live_evaluations_total,
            heading="Red training milestone",
            eyebrow="Red hierarchical learner",
            counter_labels=(
                "Portable heads fitted",
                "Held-out gates passed",
                "Full Red shadow runs",
            ),
        ),
        learning_components=RED_TRAINING_COMPONENTS,
        live_evaluation=evaluation,
        events=events,
    )


def _count_value(source: Mapping[str, object], key: str) -> int:
    value = source.get(key, 0)
    return value if type(value) is int and value >= 0 else 0  # noqa: E721


def _mapping_count(source: Mapping[object, object], key: str) -> int:
    value = source.get(key, 0)
    return value if type(value) is int and value >= 0 else 0  # noqa: E721


__all__ = [
    "RED_TRAINING_COMPONENTS",
    "live_evaluation_state",
    "red_training_dashboard_snapshot",
]
