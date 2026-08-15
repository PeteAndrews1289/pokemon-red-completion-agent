"""View-only projection of the first real Red outcome-learning cycle."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence

from pokemon_red_completion.progress_dashboard import (
    DashboardExperimentState,
    DashboardLearningComponent,
    DashboardModelState,
    DashboardSnapshot,
    ProgressDashboardError,
)

BATTLE_OUTCOME_EVIDENCE_SCHEMA = (
    "pokemon-red-battle-outcome-learning-cycle-evidence-v1"
)
BATTLE_OUTCOME_CURVE_EVIDENCE_SCHEMA = (
    "pokemon-red-battle-outcome-learning-curve-evidence-v2"
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def battle_outcome_dashboard_snapshot(
    evidence: Mapping[str, object],
) -> DashboardSnapshot:
    """Build the human-facing, path-free result view from public evidence."""

    if not isinstance(evidence, Mapping):
        raise TypeError("battle outcome evidence must be a mapping")
    schema = evidence.get("schema")
    if schema == BATTLE_OUTCOME_CURVE_EVIDENCE_SCHEMA:
        return _learning_curve_dashboard_snapshot(evidence)
    if schema == BATTLE_OUTCOME_EVIDENCE_SCHEMA:
        return _first_cycle_dashboard_snapshot(evidence)
    raise ProgressDashboardError("battle outcome evidence schema is unsupported")


def _first_cycle_dashboard_snapshot(
    evidence: Mapping[str, object],
) -> DashboardSnapshot:
    if evidence.get("status") != "plumbing_complete_candidate_rejected":
        raise ProgressDashboardError("battle outcome evidence status is unsupported")

    captures = _sequence(evidence, "captures")
    if len(captures) != 2 or any(not isinstance(row, Mapping) for row in captures):
        raise ProgressDashboardError("battle outcome evidence must contain two captures")
    collection = _mapping(evidence, "counterfactual_collection")
    train = _mapping(collection, "train")
    development = _mapping(collection, "development")
    learner = _mapping(evidence, "learner_update")
    protected = _mapping(evidence, "protected_access")

    measured_candidates = _count(collection, "measured_candidates")
    train_examples = _count(learner, "training_examples")
    development_examples = _count(learner, "development_examples")
    base_correct = _count(learner, "base_development_correct")
    updated_correct = _count(learner, "updated_development_correct")
    if train_examples != 1 or development_examples != 1:
        raise ProgressDashboardError(
            "first outcome dashboard requires its one-train/one-development evidence"
        )
    if base_correct > development_examples or updated_correct > development_examples:
        raise ProgressDashboardError("development correctness exceeds its denominator")
    if updated_correct >= base_correct:
        raise ProgressDashboardError("rejected outcome candidate does not reproduce regression")

    base_model_sha256 = _sha256(learner, "base_model_sha256")
    updated_model_sha256 = _sha256(learner, "updated_model_sha256")
    loss_before = _finite_nonnegative(learner, "objective_loss_before")
    loss_after = _finite_nonnegative(learner, "objective_loss_after")
    if loss_after >= loss_before:
        raise ProgressDashboardError("outcome update does not reproduce lower fit loss")

    actions = _count(train, "actions") + _count(development, "actions")
    frames = _count(train, "frames") + _count(development, "frames")
    teacher_queries = _count(protected, "teacher_queries")
    sealed_opened = _count(protected, "red_sealed_test_cases_opened")
    crystal_opened = _count(protected, "crystal_contexts_opened")
    full_replays = _count(protected, "full_game_replays")
    if teacher_queries or sealed_opened or crystal_opened or full_replays:
        raise ProgressDashboardError("protected-access counters must remain zero")

    return DashboardSnapshot(
        game="Pokémon Red",
        run_status="paused",
        stage="Outcome learner · candidate rejected",
        message=(
            "The teacher-free counterfactual loop worked, but one training state overfit: "
            "the frozen prior was correct on development and the update was not."
        ),
        frame_count=frames,
        actions=actions,
        stage_progress=1.0,
        location="Pokémon Mansion 1F · authenticated snapshots",
        collection_target=124,
        model=DashboardModelState(
            mode="shadow",
            candidate="Prior-preserving Red battle outcome candidate",
            choice=(
                f"Rejected: development fell from {base_correct}/{development_examples} "
                f"to {updated_correct}/{development_examples}"
            ),
            decisions=measured_candidates,
            teacher_queries=teacher_queries,
            fallbacks=0,
        ),
        experiment=DashboardExperimentState(
            phase="blocked",
            zero_shot_completed=len(captures),
            zero_shot_total=len(captures),
            adaptation_completed=train_examples,
            adaptation_total=train_examples,
            sealed_completed=0,
            sealed_total=200,
            predictions_committed=False,
            heading="Battle outcome learning",
            eyebrow="Red model-first laboratory",
            counter_labels=(
                "Authenticated captures",
                "Learner updates",
                "Unseen promotion battles",
            ),
        ),
        learning_components=(
            DashboardLearningComponent(
                name="Outcome-adapted battle MLP",
                scope=(
                    "One-state outcome update; frozen prior is the comparator; "
                    "development regressed"
                ),
                status="blocked",
                authority="shadow_only",
                train_examples=train_examples,
                validation_examples=development_examples,
                validation_correct=updated_correct,
                baseline_correct=base_correct,
                baseline_id=f"frozen_prior_{base_model_sha256[:12]}",
                model_sha256=updated_model_sha256,
                independent_validation_units=development_examples,
                candidate_count_results=((4, updated_correct, development_examples),),
            ),
        ),
        events=(
            (
                f"Collected {measured_candidates} controller-proven move outcomes from "
                f"{len(captures)} authenticated states"
            ),
            "Every counterfactual used exactly 2,048 pre-attack frames",
            f"Training objective fell {loss_before:.4f} → {loss_after:.4f}",
            (
                f"Untouched development regressed {base_correct}/{development_examples} → "
                f"{updated_correct}/{development_examples}; no authority granted"
            ),
            "Teacher 0 · sealed Red 0 · Crystal 0 · full-game replays 0",
            "Next: smallest battle learning curve, then one thin navigation and party adapter",
        ),
    )


def _learning_curve_dashboard_snapshot(
    evidence: Mapping[str, object],
) -> DashboardSnapshot:
    if evidence.get("status") != "descriptive_curve_complete_no_authority":
        raise ProgressDashboardError("battle outcome curve status is unsupported")

    captures = _sequence(evidence, "captures")
    catalog = _mapping(evidence, "catalog")
    collection = _mapping(evidence, "counterfactual_collection")
    curve = _mapping(evidence, "learning_curve")
    decision = _mapping(evidence, "decision")
    protected = _mapping(evidence, "protected_access")
    if len(captures) != 8 or any(not isinstance(row, Mapping) for row in captures):
        raise ProgressDashboardError("battle outcome curve must contain eight captures")
    if _count(catalog, "train_contexts") != 4 or _count(
        catalog, "development_contexts"
    ) != 4:
        raise ProgressDashboardError("battle outcome curve catalog is not 4+4")

    candidate_outcomes = _count(collection, "candidate_outcomes")
    complete_contexts = _count(collection, "complete_contexts")
    total_actions = _count(collection, "total_candidate_actions")
    total_frames = _count(collection, "total_candidate_frames")
    informative = _count(collection, "informative_contexts")
    flat = _count(collection, "flat_contexts")
    informative_development = _count(
        collection, "informative_development_contexts"
    )
    flat_development = _count(
        collection, "development_contexts_with_all_candidates_tied_best"
    )
    opponent_faints = _count(collection, "opponent_faint_outcomes")
    player_faints = _count(collection, "player_faint_outcomes")
    if complete_contexts != len(captures) or candidate_outcomes != 32:
        raise ProgressDashboardError("battle outcome curve collection is incomplete")
    if informative + flat != complete_contexts:
        raise ProgressDashboardError("battle outcome curve diversity accounting is incomplete")
    if informative_development + flat_development != 4:
        raise ProgressDashboardError("development diversity accounting is incomplete")

    development_examples = _count(curve, "development_examples")
    base_correct = _count(curve, "base_development_correct")
    base_utility = _finite_nonnegative(
        curve, "base_development_mean_selected_utility"
    )
    points = _sequence(curve, "points")
    if development_examples != 4 or base_correct != development_examples:
        raise ProgressDashboardError("battle outcome curve prior result is invalid")
    if len(points) != 3 or any(not isinstance(point, Mapping) for point in points):
        raise ProgressDashboardError("battle outcome curve requires three points")

    expected_sizes = (1, 2, 4)
    components: list[DashboardLearningComponent] = []
    events: list[str] = [
        (
            f"Collected {candidate_outcomes} selected-turn outcomes from "
            f"{complete_contexts} authenticated contexts"
        ),
        (
            f"Outcome diversity: {informative} informative contexts, {flat} flat; "
            f"development was {informative_development} informative and {flat_development} flat"
        ),
        (
            f"The frozen prior started at {base_correct}/{development_examples} with "
            f"mean selected utility {base_utility:.1f}"
        ),
    ]
    for expected_size, raw_point in zip(expected_sizes, points, strict=True):
        assert isinstance(raw_point, Mapping)
        size = _count(raw_point, "training_examples")
        if size != expected_size or raw_point.get("status") != "updated":
            raise ProgressDashboardError("battle outcome curve point order is invalid")
        loss_before = _finite_nonnegative(raw_point, "objective_loss_before")
        loss_after = _finite_nonnegative(raw_point, "objective_loss_after")
        if loss_after >= loss_before:
            raise ProgressDashboardError("battle outcome curve fit loss did not decrease")
        updated_correct = _count(raw_point, "updated_development_correct")
        updated_utility = _finite_nonnegative(
            raw_point, "updated_development_mean_selected_utility"
        )
        updated_wins = _count(raw_point, "paired_updated_wins")
        prior_wins = _count(raw_point, "paired_prior_wins")
        equivalent = _count(raw_point, "paired_equivalent_choices")
        discordant = _count(raw_point, "discordant_examples")
        if (
            updated_correct != development_examples
            or updated_utility != base_utility
            or updated_wins + prior_wins + equivalent != development_examples
            or discordant != updated_wins + prior_wins
        ):
            raise ProgressDashboardError("battle outcome curve comparison is inconsistent")
        model_sha256 = _sha256(raw_point, "updated_model_sha256")
        components.append(
            DashboardLearningComponent(
                name=f"Battle curve · {size} training root{'s' if size != 1 else ''}",
                scope=(
                    "From-prior last-layer update; four fresh development roots; "
                    "descriptive only"
                ),
                status="offline",
                authority="shadow_only",
                train_examples=size,
                validation_examples=development_examples,
                validation_correct=updated_correct,
                baseline_correct=base_correct,
                baseline_id="frozen_prior_822fb66ec27c",
                model_sha256=model_sha256,
                independent_validation_units=development_examples,
                paired_wins=updated_wins,
                paired_losses=prior_wins,
                paired_two_sided_exact_p=1.0,
                candidate_count_results=((4, updated_correct, development_examples),),
            )
        )
        events.append(
            f"{size}-root fit loss {loss_before:.4f} → {loss_after:.4f}; "
            f"development stayed {updated_correct}/{development_examples}"
        )

    if decision.get("training_pipeline_validated") is not True:
        raise ProgressDashboardError("battle outcome curve pipeline is not validated")
    if (
        decision.get("battle_generalization_improvement_demonstrated") is not False
        or decision.get("promotion_gate_passed") is not False
        or decision.get("authority_promoted") is not False
    ):
        raise ProgressDashboardError("battle outcome curve overclaims learned authority")
    teacher_queries = _count(protected, "teacher_queries")
    sealed_opened = _count(protected, "red_sealed_test_cases_opened")
    crystal_opened = _count(protected, "crystal_contexts_opened")
    full_replays = _count(protected, "full_game_replays")
    if teacher_queries or sealed_opened or crystal_opened or full_replays:
        raise ProgressDashboardError("protected-access counters must remain zero")

    events.extend(
        (
            (
                f"All updates were choice-equivalent to the prior: 0 update wins, "
                f"0 prior wins, {development_examples} ties"
            ),
            (
                f"{opponent_faints}/{candidate_outcomes} branches fainted the opponent; "
                f"player faints {player_faints}"
            ),
            "Teacher 0 · sealed Red 0 · Crystal 0 · full-game replays 0",
            "Next: real navigation and party outcomes, then level-matched non-OHKO battles",
        )
    )
    return DashboardSnapshot(
        game="Pokémon Red",
        run_status="passed",
        stage="Outcome curve · pipeline passed, authority held",
        message=(
            "The 1/2/4 training curve completed, but the prior was already perfect on an easy "
            "development set. Training works; generalization improvement remains unproven."
        ),
        frame_count=total_frames,
        actions=total_actions,
        stage_progress=1.0,
        location="Pokémon Mansion 1F · eight authenticated snapshots",
        collection_target=124,
        model=DashboardModelState(
            mode="shadow",
            candidate="Four-root Red battle outcome candidate",
            choice="No promotion: prior and all updates remained 4/4",
            decisions=candidate_outcomes,
            teacher_queries=teacher_queries,
            fallbacks=0,
        ),
        experiment=DashboardExperimentState(
            phase="complete",
            zero_shot_completed=complete_contexts,
            zero_shot_total=complete_contexts,
            adaptation_completed=4,
            adaptation_total=4,
            sealed_completed=0,
            sealed_total=200,
            predictions_committed=False,
            heading="Battle outcome learning curve",
            eyebrow="Red model-first laboratory",
            counter_labels=(
                "Authenticated contexts",
                "Training roots",
                "Unseen promotion battles",
            ),
        ),
        learning_components=tuple(components),
        events=tuple(events),
    )


def _mapping(source: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = source.get(key)
    if not isinstance(value, Mapping):
        raise ProgressDashboardError(f"battle outcome {key.replace('_', ' ')} is invalid")
    return value


def _sequence(source: Mapping[str, object], key: str) -> Sequence[object]:
    value = source.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ProgressDashboardError(f"battle outcome {key.replace('_', ' ')} is invalid")
    return value


def _count(source: Mapping[str, object], key: str) -> int:
    value = source.get(key)
    if type(value) is not int or value < 0:  # noqa: E721
        raise ProgressDashboardError(f"battle outcome {key.replace('_', ' ')} is invalid")
    return value


def _sha256(source: Mapping[str, object], key: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ProgressDashboardError(f"battle outcome {key.replace('_', ' ')} is invalid")
    return value


def _finite_nonnegative(source: Mapping[str, object], key: str) -> float:
    value = source.get(key)
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        raise ProgressDashboardError(f"battle outcome {key.replace('_', ' ')} is invalid")
    return float(value)


__all__ = [
    "BATTLE_OUTCOME_CURVE_EVIDENCE_SCHEMA",
    "BATTLE_OUTCOME_EVIDENCE_SCHEMA",
    "battle_outcome_dashboard_snapshot",
]
