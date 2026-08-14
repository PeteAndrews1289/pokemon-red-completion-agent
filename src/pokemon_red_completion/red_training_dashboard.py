"""Human-facing projection for Red model fitting and live shadow evaluation."""

from __future__ import annotations

from collections.abc import Mapping

from pokemon_red_completion.progress_dashboard import (
    DashboardExperimentState,
    DashboardLearningComponent,
    DashboardLiveEvaluationState,
    DashboardModelState,
    DashboardSnapshot,
    ProgressDashboardError,
)

RED_TRAINING_COMPONENTS = (
    DashboardLearningComponent(
        name="Goal manager",
        scope="Chooses what to pursue across nine title-neutral needs",
        status="offline",
        authority="offline",
        train_examples=54,
        validation_examples=27,
        validation_correct=27,
        baseline_correct=25,
        model_sha256="af29d7e7f72e9921e638c88664b17e6fbbf6334468609ab66bda41c9f3dad66d",
        independent_validation_units=27,
        baseline_id="highest_pressure",
        paired_wins=2,
        paired_losses=0,
        paired_two_sided_exact_p=0.5,
    ),
    DashboardLearningComponent(
        name="Destination ranker",
        scope="Ranks strategic destinations without memorizing controller inputs",
        status="offline",
        authority="offline",
        train_examples=24,
        validation_examples=12,
        validation_correct=10,
        baseline_correct=4,
        model_sha256="753e3dbdb983d85acd9da5910fb92679a5406df39dfde84f68200d85378dd0c1",
        independent_validation_units=12,
        baseline_id="route_cost",
        paired_wins=6,
        paired_losses=0,
        paired_two_sided_exact_p=0.03125,
        candidate_count_results=((2, 2, 4),),
    ),
    DashboardLearningComponent(
        name="Battle move ranker",
        scope="Chooses among legal moves; the teacher checks every live proposal",
        status="shadow",
        authority="teacher_supervised",
        train_examples=3320,
        validation_examples=1142,
        validation_correct=1125,
        baseline_correct=468,
        model_sha256="822fb66ec27c0aee267fcb1b7103d389133d7e8c74274eee3e72bfc1f616c01f",
        independent_validation_units=2,
        baseline_id="free_choice_majority",
    ),
    DashboardLearningComponent(
        name="Team-development ranker",
        scope="Ranks training candidates and venues while the teacher executes",
        status="shadow",
        authority="shadow_only",
        train_examples=13709,
        validation_examples=7030,
        validation_correct=7023,
        baseline_correct=6725,
        model_sha256="9286f1b42fcbffb2741d52a11359df0281c50501fe66100e8c795b4ffa37e026",
        independent_validation_units=1,
        baseline_id="shape_only",
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
    decisions = _count_value(battle, "decisions")
    model_decisions = _count_value(battle, "model_decisions")
    reason_total = sum(
        value
        for value in reason_counts.values()
        if type(value) is int and value >= 0  # noqa: E721
    )
    if reason_counts and reason_total != fallbacks:
        raise ProgressDashboardError(
            "battle fallback reasons must account for every teacher fallback"
        )
    terminal_keys = {
        "returned_move_decisions",
        "non_move_control_decisions",
        "failed_decisions",
        "interrupted_decisions",
    }
    if terminal_keys.intersection(battle):
        if not terminal_keys.issubset(battle):
            raise ProgressDashboardError("battle terminal accounting is incomplete")
        returned = _required_count_value(battle, "returned_move_decisions")
        non_move = _required_count_value(battle, "non_move_control_decisions")
        failed = _required_count_value(battle, "failed_decisions")
        interrupted = _required_count_value(battle, "interrupted_decisions")
        if returned != model_decisions + fallbacks:
            raise ProgressDashboardError(
                "returned battle moves must equal model executions and teacher fallbacks"
            )
        unclassified = decisions - returned - non_move - failed - interrupted
        if unclassified < 0:
            raise ProgressDashboardError("battle terminal accounting exceeds decisions")
    else:
        non_move = 0
        failed = 0
        interrupted = 0
        unclassified = decisions - model_decisions - fallbacks
        if unclassified < 0:
            raise ProgressDashboardError("legacy battle accounting exceeds decisions")
    return DashboardLiveEvaluationState(
        battle_decisions=decisions,
        teacher_agreements=model_decisions,
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
        non_move_control_decisions=non_move,
        failed_decisions=failed,
        interrupted_decisions=interrupted,
        unclassified_decisions=unclassified,
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


def _required_count_value(source: Mapping[str, object], key: str) -> int:
    value = source.get(key)
    if type(value) is not int or value < 0:  # noqa: E721
        raise ProgressDashboardError(f"battle {key.replace('_', ' ')} is invalid")
    return value


__all__ = [
    "RED_TRAINING_COMPONENTS",
    "live_evaluation_state",
    "red_training_dashboard_snapshot",
]
