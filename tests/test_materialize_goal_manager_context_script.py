from __future__ import annotations

import ast
import runpy
import subprocess
import sys
from pathlib import Path

from pokemon_red_completion.observation import ItemId, RawGameState

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "materialize_goal_manager_context.py"


def _damage_context_ready(
    raw: RawGameState,
    *,
    require_field_recovery: bool,
) -> bool:
    function = runpy.run_path(str(SCRIPT))["_damage_context_ready"]
    return bool(function(raw, require_field_recovery=require_field_recovery))


def test_materializer_uses_real_actions_and_never_edits_emulator_memory() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }

    assert "save_state" in attributes
    assert "write_u8" not in attributes
    assert "write_memory" not in attributes
    assert "record_goal_manager_context" not in source
    assert "begin_episode" not in source
    assert "load_state_bytes" in source


def test_materializer_help_declares_only_finite_uncounted_boundaries() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "blocked-movement" in result.stdout
    assert "damaged-center" in result.stdout
    assert "evolved-team" in result.stdout
    assert "mansion" in result.stdout
    assert "--slot-id" not in result.stdout
    assert "--profile" not in result.stdout


def test_blocked_context_uses_a_released_one_frame_semantic_action() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "ControllerTiming()" in source
    assert 'MacroAction(MacroActionKind.MOVE, "down")' in source
    assert ".press(" not in source
    assert ".release(" not in source


def test_damage_context_uses_real_battle_turns_and_active_pressure_gate() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "switch_active_battler(" in source
    assert "party_safety_satisfaction(" in source
    assert "_ACTIVE_SAFETY_PRESSURE = 0.55" in source
    assert "allowed a party member to faint" in source
    assert "plan_party_recovery(" in source
    assert "required.items()" in source


def test_late_game_context_relocates_from_indigo_through_real_fly() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "MapId.INDIGO_PLATEAU_LOBBY" in source
    assert '"goal-manager Indigo departure"' in source
    assert "_fly_to_town(" in source
    assert "MapId.CINNABAR_ISLAND" in source


def test_evolved_team_setup_reuses_the_qualified_bounded_mechanic() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert 'if mode == "evolved-team"' in source
    assert "run_red_team_balancing(" in source
    assert "red_team_development_quantum_policy(" in source
    assert "_targeted_evolution_index(" in source
    assert "evolution_target=(DIGLETT_SPECIES_ID, DUGTRIO_SPECIES_ID)" in source
    assert "after_levels[target_index] <= before_levels[target_index]" in source


def _damaged_raw(*, bag_items: tuple[tuple[int, int], ...]) -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=1,
        player_x=2,
        player_y=3,
        party_count=2,
        battle_state=0,
        bag_items=bag_items,
        party_species_ids=(1, 2),
        party_levels=(50, 50),
        party_hp=(45, 45),
        party_max_hp=(100, 100),
        party_status=(0, 0),
        party_moves=((1, 0, 0, 0), (1, 0, 0, 0)),
        party_pp=((10, 0, 0, 0), (10, 0, 0, 0)),
    )


def test_field_damage_gate_requires_enough_items_for_the_exact_recovery_plan() -> None:
    enough = _damaged_raw(
        bag_items=((int(ItemId.HYPER_POTION), 2),),
    )
    short = _damaged_raw(
        bag_items=((int(ItemId.HYPER_POTION), 1),),
    )

    assert _damage_context_ready(enough, require_field_recovery=True)
    assert not _damage_context_ready(short, require_field_recovery=True)


def test_center_damage_gate_needs_pressure_but_not_field_items() -> None:
    raw = _damaged_raw(bag_items=())

    assert _damage_context_ready(raw, require_field_recovery=False)
