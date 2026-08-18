from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.observation import ItemId, MapId
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
        GoalKind.DEVELOP_TEAM,
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

    assert "blocked-movement" in result.stdout
    assert "evolved-team" in result.stdout
    assert "--required-team-level" not in result.stdout
    assert "--provider-json" not in result.stdout


def test_evolved_team_template_keeps_development_beside_story(tmp_path: Path) -> None:
    destination = tmp_path / "evolved-team-context.json"
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--mode",
            "evolved-team",
            "--profile-id",
            "evolved-team-context",
            "--out",
            str(destination),
        ],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    profile = load_red_goal_context_profile(destination)
    assert tuple(provider.kind for provider in profile.providers) == (
        GoalKind.ADVANCE_STORY,
        GoalKind.DEVELOP_TEAM,
        GoalKind.EVOLVE_SPECIES,
        GoalKind.RESTORE_TEAM,
        GoalKind.RECOVER_CONTROL,
    )


def test_mart_template_extends_the_existing_great_ball_stack(tmp_path: Path) -> None:
    destination = tmp_path / "mart-context.json"
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--mode",
            "mart",
            "--profile-id",
            "mart-context",
            "--out",
            str(destination),
        ],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    profile = load_red_goal_context_profile(destination)
    purchase = profile.providers[-2].parameters["purchases"][0]
    assert purchase["absolute_index"] == 1
    assert purchase["item_id"] == int(ItemId.GREAT_BALL)
    assert purchase["quantity"] == 7


def test_development_template_does_not_require_an_evolution_target(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "development-context.json"
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--mode",
            "development",
            "--profile-id",
            "development-context",
            "--out",
            str(destination),
        ],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    profile = load_red_goal_context_profile(destination)
    assert tuple(provider.kind for provider in profile.providers) == (
        GoalKind.ADVANCE_STORY,
        GoalKind.DEVELOP_TEAM,
        GoalKind.RESTORE_TEAM,
        GoalKind.RECOVER_CONTROL,
    )


def test_pc_template_uses_field_items_beside_box_management(tmp_path: Path) -> None:
    destination = tmp_path / "pc-context.json"
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--mode",
            "pc",
            "--profile-id",
            "pc-context",
            "--out",
            str(destination),
        ],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    profile = load_red_goal_context_profile(destination)
    restore = next(
        provider for provider in profile.providers if provider.kind is GoalKind.RESTORE_TEAM
    )
    assert restore.mechanic.value == "field_restore"
    assert GoalKind.MANAGE_STORAGE in tuple(
        provider.kind for provider in profile.providers
    )


def test_exploration_template_can_measure_discovery_without_capture(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "exploration-context.json"
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--mode",
            "exploration",
            "--profile-id",
            "exploration-context",
            "--out",
            str(destination),
            "--map-id",
            str(int(MapId.POKEMON_MANSION_1F)),
            "--player-x",
            "5",
            "--player-y",
            "20",
            "--forward-direction",
            "down",
            "--starting-endpoint",
            "north",
        ],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    profile = load_red_goal_context_profile(destination)
    assert tuple(provider.kind for provider in profile.providers) == (
        GoalKind.ADVANCE_STORY,
        GoalKind.RESTORE_TEAM,
        GoalKind.RECOVER_CONTROL,
        GoalKind.EXPLORE,
    )
