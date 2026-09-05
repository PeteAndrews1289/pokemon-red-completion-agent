from __future__ import annotations

import ast
from pathlib import Path

SCRIPT = Path("scripts/run_red_living_dex_targeted_train.py")


def test_targeted_train_command_has_no_development_fit_or_teacher_entrypoint() -> None:
    source = SCRIPT.read_text()
    tree = ast.parse(source)

    assert tree is not None
    for forbidden in (
        "run_development",
        "development_assignment",
        "fit_model",
        "model.fit",
        "run_teacher",
        "teacher_policy",
        "run_crystal",
        "pokemon_crystal",
    ):
        assert forbidden not in source.lower()
    assert "run_red_living_dex_targeted_train_campaign" in source
    assert "authenticate_red_living_dex_targeted_schedule_plan" in source
    assert "DashboardFrameObserver" in source
    assert "MAXIMUM_CAMPAIGN_CONTROLLER_ACTIONS = 200_000" in source
    assert "MAXIMUM_CAMPAIGN_EMULATOR_FRAMES = 20_000_000" in source
    assert '"development_slots_opened": 0' in source


def test_targeted_train_command_does_not_accept_an_ordinal_or_retry_flag() -> None:
    source = SCRIPT.read_text()

    assert 'add_argument("--ordinal"' not in source
    assert 'add_argument("--retry"' not in source
    assert 'add_argument("--development' not in source


def test_targeted_train_command_has_an_action_free_preflight_exit() -> None:
    source = SCRIPT.read_text()

    assert 'add_argument("--preflight-only"' in source
    assert '"targeted_train_campaign_preflight_passed"' in source
