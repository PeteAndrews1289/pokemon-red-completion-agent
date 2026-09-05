from __future__ import annotations

from pokemon_red_completion.red_living_dex_development_dashboard import (
    red_living_dex_development_dashboard_snapshot,
)
from pokemon_red_completion.red_living_dex_setup_trust import (
    RedLivingDexSetupProtectedEffectCheckpoint,
)

MODEL_SHA256 = "a" * 64


def test_development_dashboard_is_path_free_and_honest_before_execution() -> None:
    snapshot = red_living_dex_development_dashboard_snapshot(
        checkpoint=RedLivingDexSetupProtectedEffectCheckpoint(
            controller_actions=12,
            emulator_frames=345,
            root_claims=1,
        ),
        model_sha256=MODEL_SHA256,
        stage="Constructing authenticated Red situation",
        message="Deterministic setup is running.",
        run_status="running",
        ready_cases=5,
        events=("Hard action and frame bounds active",),
    ).public_dict()

    assert snapshot["game"] == "Pokémon Red"
    assert snapshot["actions"] == 12
    assert snapshot["frame_count"] == 345
    assert snapshot["model"]["mode"] == "waiting"  # type: ignore[index]
    assert snapshot["model"]["teacher_queries"] == 0  # type: ignore[index]
    assert snapshot["experiment"]["zero_shot"] == {  # type: ignore[index]
        "completed": 5,
        "total": 5,
    }
    assert snapshot["experiment"]["sealed_test"] == {  # type: ignore[index]
        "completed": 0,
        "total": 0,
    }
    assert snapshot["private_path_fields"] == 0
    assert snapshot["controller_endpoints"] == 0


def test_development_dashboard_rejects_more_than_five_ready_cases() -> None:
    try:
        red_living_dex_development_dashboard_snapshot(
            checkpoint=RedLivingDexSetupProtectedEffectCheckpoint(),
            model_sha256=MODEL_SHA256,
            stage="Ready",
            message="Ready.",
            run_status="waiting",
            ready_cases=6,
        )
    except ValueError as error:
        assert "ready-case" in str(error)
    else:
        raise AssertionError("invalid development readiness was accepted")
