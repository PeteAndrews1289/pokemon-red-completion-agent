from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.red_goal_context_profile import (
    load_red_goal_context_profile,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "build_goal_manager_context_profile.py"


def test_builder_emits_a_fixed_mansion_profile_without_policy_knobs(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "mansion-context.json"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--mode",
            "mansion",
            "--profile-id",
            "mansion-context",
            "--out",
            str(destination),
            "--map-id",
            str(int(MapId.POKEMON_MANSION_1F)),
            "--player-x",
            "5",
            "--player-y",
            "21",
            "--forward-direction",
            "up",
        ],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    profile = load_red_goal_context_profile(destination)
    assert tuple(provider.kind for provider in profile.providers) == (
        GoalKind.ADVANCE_STORY,
        GoalKind.ACQUIRE_SPECIES,
        GoalKind.RESTORE_TEAM,
        GoalKind.RECOVER_CONTROL,
        GoalKind.EXPLORE,
    )
    assert profile.manager_config.required_team_level == 60
    assert destination.stat().st_mode & 0o777 == 0o600
    assert '"status": "created"' in result.stdout


def test_builder_help_exposes_finite_templates_but_no_manager_target_override() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "blocked-dialogue" in result.stdout
    assert "--required-team-level" not in result.stdout
    assert "--provider-json" not in result.stdout
