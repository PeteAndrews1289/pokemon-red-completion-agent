"""View-only projection for one bounded Red living-Dex development case."""

from __future__ import annotations

from collections.abc import Sequence

from pokemon_red_completion.progress_dashboard import (
    DashboardExperimentState,
    DashboardLearningComponent,
    DashboardModelState,
    DashboardSnapshot,
)
from pokemon_red_completion.red_living_dex_clustered_development_execution import (
    RedLivingDexClusteredDevelopmentReceipt,
)
from pokemon_red_completion.red_living_dex_setup_trust import (
    RedLivingDexSetupProtectedEffectCheckpoint,
)


def red_living_dex_development_dashboard_snapshot(
    *,
    checkpoint: RedLivingDexSetupProtectedEffectCheckpoint,
    model_sha256: str,
    stage: str,
    message: str,
    run_status: str,
    ready_cases: int,
    receipt: RedLivingDexClusteredDevelopmentReceipt | None = None,
    events: Sequence[str] = (),
) -> DashboardSnapshot:
    """Build one path-free observer state without exposing policy identities."""

    if not isinstance(checkpoint, RedLivingDexSetupProtectedEffectCheckpoint):
        raise TypeError("development dashboard needs its effect checkpoint")
    checkpoint.__post_init__()
    if type(ready_cases) is not int or not 0 <= ready_cases <= 5:  # noqa: E721
        raise ValueError("development dashboard ready-case count differs")
    if not isinstance(events, Sequence) or isinstance(events, (str, bytes)):
        raise TypeError("development dashboard events must be a sequence")
    development = None if receipt is None else receipt.development
    decision = None if development is None else development.decision
    terminal = receipt is not None
    model_decisions = int(decision is not None)
    selected = None
    if decision is not None:
        selected = (
            f"candidate {decision.selected_candidate_index + 1} "
            f"of {len(decision.candidate_scores)}"
        )
    return DashboardSnapshot(
        game="Pokémon Red",
        run_status=run_status,
        stage=stage,
        message=message,
        frame_count=checkpoint.emulator_frames,
        actions=checkpoint.controller_actions,
        stage_progress=1.0 if terminal else min(0.9, 0.1 + checkpoint.root_claims * 0.2),
        collection_target=151,
        model=DashboardModelState(
            mode="model" if model_decisions else "waiting",
            candidate="18-example title-neutral living-Pokédex option model",
            choice=selected,
            decisions=model_decisions,
            teacher_queries=checkpoint.teacher_queries,
            fallbacks=0,
        ),
        experiment=DashboardExperimentState(
            phase=("complete" if terminal else "live_evaluation"),
            zero_shot_completed=ready_cases,
            zero_shot_total=5,
            adaptation_completed=int(terminal),
            adaptation_total=1,
            sealed_completed=0,
            sealed_total=0,
            predictions_committed=model_decisions > 0,
            heading="Red bounded player integration",
            eyebrow="Model-selected living-Pokédex development",
            counter_labels=(
                "Ready development cases",
                "Terminal live cases",
                "Sealed or Crystal cases",
            ),
        ),
        learning_components=(
            DashboardLearningComponent(
                name="Living-Pokédex option model",
                scope="Select a semantic collection objective; deterministic skills execute it",
                status="shadow",
                authority="shadow_only",
                train_examples=18,
                validation_examples=0,
                validation_correct=0,
                baseline_correct=None,
                model_sha256=model_sha256,
                independent_validation_units=0,
            ),
        ),
        events=tuple(events)[-24:],
    )


__all__ = ["red_living_dex_development_dashboard_snapshot"]
