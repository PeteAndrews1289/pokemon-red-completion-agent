from __future__ import annotations

import json

from pokemon_red_completion.red_training_dashboard import (
    RED_TRAINING_COMPONENTS,
    live_evaluation_state,
    red_training_dashboard_snapshot,
)


def test_red_training_dashboard_is_honest_about_shadow_authority() -> None:
    snapshot = red_training_dashboard_snapshot(
        run_status="running",
        stage="Cerulean City",
        message="Evaluating the new battle candidate with teacher disagreement authority.",
        frame_count=123_456,
        actions=0,
        stage_progress=0.25,
        live_evaluations_completed=0,
        live_evaluations_total=1,
        battle_policy={
            "decisions": 19,
            "model_decisions": 17,
            "teacher_queries": 19,
            "teacher_fallbacks": 2,
            "correction_records": 2,
            "fallback_reasons": {"teacher_disagreement": 2},
        },
        team_policy={"decisions": 6, "agreements": 5},
        events=("Goal and destination heads remain offline in this run",),
    ).public_dict()

    encoded = json.dumps(snapshot, sort_keys=True)
    assert snapshot["game"] == "Pokémon Red"
    assert snapshot["model"]["mode"] == "shadow"  # type: ignore[index]
    assert snapshot["model"]["teacher_queries"] == 19  # type: ignore[index]
    assert snapshot["experiment"]["sealed_test"] == {  # type: ignore[index]
        "completed": 0,
        "total": 1,
    }
    assert snapshot["live_evaluation"]["teacher_agreement_rate"] == 17 / 19  # type: ignore[index]
    assert snapshot["live_evaluation"]["team_accuracy"] == 5 / 6  # type: ignore[index]
    assert len(snapshot["learning_components"]) == 4
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_red_training_components_bind_the_actual_fitted_models() -> None:
    by_name = {component.name: component for component in RED_TRAINING_COMPONENTS}

    assert by_name["Goal manager"].validation_examples == 27
    assert by_name["Goal manager"].validation_accuracy == 1.0
    assert by_name["Destination ranker"].validation_accuracy == 10 / 12
    assert by_name["Battle move ranker"].train_examples == 3320
    assert by_name["Battle move ranker"].authority == "teacher_supervised"
    assert by_name["Team-development ranker"].validation_examples == 7080
    assert by_name["Team-development ranker"].authority == "shadow_only"


def test_live_evaluation_projection_counts_exact_fallback_reasons() -> None:
    state = live_evaluation_state(
        {
            "decisions": 12,
            "model_decisions": 8,
            "teacher_queries": 12,
            "teacher_fallbacks": 4,
            "correction_records": 3,
            "fallback_reasons": {
                "teacher_disagreement": 2,
                "low_confidence": 1,
                "unsupported_observation": 1,
            },
            "unsupported_observation_errors": {"UnsupportedMove": 1},
        },
        {"decisions": 3, "agreements": 2},
    ).public_dict()

    assert state["teacher_agreements"] == 8
    assert state["teacher_disagreements"] == 2
    assert state["low_confidence_fallbacks"] == 1
    assert state["unsupported_observations"] == 1
    assert state["corrections_saved"] == 3
