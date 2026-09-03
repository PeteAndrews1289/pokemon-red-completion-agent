from __future__ import annotations

import argparse
import ast
import runpy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalOpportunity,
    GoalSituation,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_composition_runtime import (
    GoalManagerCompositionObservation,
    LivingCollectionCheckpoint,
)
from pokemon_red_completion.goal_manager_runtime import GoalBindingSet

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "run_paired_red_bounded_player.py"


def _call_names() -> tuple[str, ...]:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            names.append(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            names.append(node.func.attr)
    return tuple(names)


def _collection(*, storage: int) -> LivingCollectionCheckpoint:
    return LivingCollectionCheckpoint(
        registered_species=10,
        living_species=10,
        required_specimens_remaining=5,
        retained_captures=3,
        storage_headroom=storage,
        undeclared_specimen_losses=0,
        completion_contract_sha256="1" * 64,
        specimen_ledger_sha256="2" * 64,
        required_specimens_sha256="3" * 64,
        specimen_counts=(("pokemon:red:living:starter", 10),),
    )


def _observation(*, storage: int) -> GoalManagerCompositionObservation:
    opportunities = tuple(
        GoalOpportunity(
            binding_ref=f"private:red:{kind.value}",
            kind=kind,
            availability=GoalAvailability.UNAVAILABLE,
            unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET,
        )
        for kind in GoalKind
    )
    return GoalManagerCompositionObservation(
        semantic_state_sha256="4" * 64,
        situation=GoalSituation(
            story_pressure=0.1,
            collection_pressure=0.1,
            team_pressure=0.1,
            evolution_pressure=0.1,
            safety_pressure=0.1,
            resource_pressure=0.1,
            storage_pressure=0.1,
            recovery_pressure=0.1,
            exploration_pressure=0.1,
        ),
        binding_set=GoalBindingSet(opportunities, ()),
        collection=_collection(storage=storage),
    )


def test_runner_uses_shared_player_and_frame_safe_controller_boundary() -> None:
    calls = _call_names()

    for required in (
        "require_clean_source",
        "require_published_source",
        "preflight_red_bounded_player",
        "run_bounded_player_episode",
        "FrameSafeExecutor",
        "HardCompositionActionLimiter",
        "EpisodeTrajectorySink",
        "compare_paired_bounded_player_arms",
        "load_living_dex_goal_model_record",
        "_write_exclusive",
    ):
        assert required in calls
    assert "press" not in calls
    assert "release" not in calls
    assert "save_state" not in calls
    assert "save_state_bytes" not in calls


def test_runner_help_names_the_repeatable_pair_inputs() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "--pair-id" in result.stdout
    assert "--private-artifact-root" in result.stdout
    assert "--model" in result.stdout
    assert "--challenger" in result.stdout
    assert "--living-dex-model-record" in result.stdout
    assert "--expected-living-dex-model-sha256" in result.stdout
    assert "--decision-limit" in result.stdout
    assert "--out" in result.stdout


def test_challenger_arguments_keep_legacy_and_causal_models_disjoint() -> None:
    module = runpy.run_path(str(SCRIPT))
    arguments = module["_challenger_arguments"]
    learned_id = module["LEARNED_ARM_ID"]
    causal_id = module["CAUSAL_ARM_ID"]
    legacy = Path("legacy.json")
    causal = Path("causal.json")

    assert arguments(
        argparse.Namespace(
            challenger=learned_id,
            model=legacy,
            living_dex_model_record=None,
            expected_living_dex_model_sha256=None,
        )
    ) == (legacy, None)
    assert arguments(
        argparse.Namespace(
            challenger=causal_id,
            model=None,
            living_dex_model_record=causal,
            expected_living_dex_model_sha256="a" * 64,
        )
    ) == (causal, "a" * 64)
    with pytest.raises(RuntimeError, match="challenger_model_arguments"):
        arguments(
            argparse.Namespace(
                challenger=causal_id,
                model=legacy,
                living_dex_model_record=causal,
                expected_living_dex_model_sha256="a" * 64,
            )
        )


def test_episode_identity_distinguishes_both_learned_challengers() -> None:
    module = runpy.run_path(str(SCRIPT))
    episode_id = module["_episode_id"]

    assert episode_id("pair", module["LEARNED_ARM_ID"]) == "pair-learned"
    assert episode_id("pair", module["CAUSAL_ARM_ID"]) == "pair-causal"
    assert episode_id("pair", module["BASELINE_ARM_ID"]) == "pair-baseline"
    with pytest.raises(RuntimeError, match="arm_identity"):
        episode_id("pair", "unknown")


def test_policy_identity_never_labels_the_causal_challenger_as_baseline() -> None:
    module = runpy.run_path(str(SCRIPT))
    policy_id = module["_policy_id"]
    causal_id = module["CAUSAL_ARM_ID"]
    baseline_id = module["BASELINE_ARM_ID"]
    readiness = SimpleNamespace(
        challenger_arm_id=causal_id,
        model_sha256="b" * 64,
    )

    assert policy_id(readiness, causal_id) == "living-dex-goal-bbbbbbbbbbbbbbbb"
    assert policy_id(readiness, baseline_id) == baseline_id


def test_one_decision_calibration_disables_replan_and_halves_episode_budgets() -> None:
    module = runpy.run_path(str(SCRIPT))
    limits = module["_player_limits"](1)

    assert limits.max_decisions == 1
    assert limits.max_replans == 0
    assert limits.max_total_actions == limits.max_actions_per_decision == 6_000
    assert limits.max_total_frames == limits.max_frames_per_decision == 600_000
    with pytest.raises(RuntimeError, match="decision_limit"):
        module["_player_limits"](3)


def test_progress_predicate_uses_a_fresh_verified_collection_delta() -> None:
    module = runpy.run_path(str(SCRIPT))
    predicate = module["_ProgressPredicate"]()

    assert predicate(_observation(storage=2)) is False
    assert predicate(_observation(storage=2)) is False
    assert predicate(_observation(storage=3)) is True


def test_read_only_meter_rejects_a_regressing_frame_counter() -> None:
    module = runpy.run_path(str(SCRIPT))
    meter_type = module["_ReadOnlyBudgetMeter"]

    class Actions:
        actions_executed = 0

    class Emulator:
        frame_count = 9

    meter = meter_type(Actions(), Emulator(), 10)
    with pytest.raises(RuntimeError, match="frame_counter_regressed"):
        meter.checkpoint()


def test_deferred_executor_refuses_observation_time_input_then_enables() -> None:
    module = runpy.run_path(str(SCRIPT))
    deferred_type = module["_DeferredActionExecutor"]

    class Delegate:
        def execute(self, action: object) -> object:
            return action

    deferred = deferred_type(Delegate())
    with pytest.raises(RuntimeError, match="action_free_observation"):
        deferred.execute("move")
    assert deferred.attempted_while_disabled == 1
    deferred.enable()
    assert deferred.execute("move") == "move"


def test_public_output_must_be_new_external_and_not_rom_adjacent(tmp_path: Path) -> None:
    module = runpy.run_path(str(SCRIPT))
    output = module["_new_external_output"]
    rom_dir = tmp_path / "roms"
    result_dir = tmp_path / "results"
    rom_dir.mkdir()
    result_dir.mkdir()
    rom = rom_dir / "red.gb"
    rom.write_bytes(b"rom")

    assert output(result_dir / "pair.json", rom_path=rom) == (
        result_dir / "pair.json"
    ).resolve()
    with pytest.raises(RuntimeError, match="output_isolation"):
        output(rom_dir / "pair.json", rom_path=rom)
    existing = result_dir / "existing.json"
    existing.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="output_isolation"):
        output(existing, rom_path=rom)
