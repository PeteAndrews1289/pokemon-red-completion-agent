from __future__ import annotations

import ast
import inspect
import runpy
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.celadon import _flee as _timed_flee
from pokemon_red_completion.goal_manager import GoalDecisionOutcome
from pokemon_red_completion.observation import InputReadiness, ItemId, MapId, RawGameState
from pokemon_red_completion.red_party import (
    BLASTOISE_SPECIES_ID,
    DUGTRIO_SPECIES_ID,
)
from pokemon_red_completion.surge import _flee as _protected_flee

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
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}

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
    assert "acquisition-ready" in result.stdout
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
    assert "_flee as _timed_flee" in source
    assert "flee_func=_timed_flee" in source
    assert "_flee as _protected_flee" in source
    assert "evolution_target=(DIGLETT_SPECIES_ID, DUGTRIO_SPECIES_ID)" in source
    assert "evolved_levels[target_index] <= before_levels[target_index]" in source
    assert '"evolved-team Center entry"' in source
    assert "_training_dig_to_cinnabar(actions, reader, emulator)" in source
    assert "tuple(final.party_species_ids or ()) != evolved_species" in source


def test_materializer_keeps_setup_and_training_flee_contracts_distinct() -> None:
    assert tuple(inspect.signature(_protected_flee).parameters) == (
        "emulator",
        "executor",
        "reader",
        "encounter",
    )
    assert tuple(inspect.signature(_timed_flee).parameters) == (
        "executor",
        "reader",
        "emulator",
        "run",
        "timing",
    )


def test_acquisition_setup_proves_a_real_mart_reserve_before_entering_mansion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = runpy.run_path(str(SCRIPT))
    reader = _Reader(
        replace(
            _unevolved_party_raw(),
            bag_items=((int(ItemId.GREAT_BALL), 1),),
            player_money=30_000,
        )
    )

    def move(_actions: object, _reader: object, _directions: object, label: str) -> None:
        if label == "goal-manager acquisition Mart":
            reader.raw = replace(
                reader.raw,
                map_id=MapId.CINNABAR_MART,
                player_x=3,
                player_y=7,
            )
        elif label == "goal-manager acquisition clerk":
            reader.raw = replace(reader.raw, player_x=2, player_y=5)
        elif label == "goal-manager stocked Mansion":
            reader.raw = replace(
                reader.raw,
                map_id=MapId.POKEMON_MANSION_1F,
                player_x=5,
                player_y=27,
            )

    class _Binding:
        def execute(self) -> object:
            reader.raw = replace(
                reader.raw,
                bag_items=((int(ItemId.GREAT_BALL), 13),),
                player_money=22_800,
            )
            return object()

        def verify(self, _report: object) -> object:
            return SimpleNamespace(status=GoalDecisionOutcome.SUCCEEDED)

    class _Provider:
        def offer(self, _observation: object) -> object:
            return SimpleNamespace(binding=_Binding())

    class _Venue:
        @staticmethod
        def walk_to_grass(*_args: object) -> int:
            reader.raw = replace(reader.raw, player_y=26)
            return 1

    globals_dict = module["_acquisition_ready_boundary"].__globals__
    monkeypatch.setitem(globals_dict, "_move", move)
    monkeypatch.setitem(globals_dict, "_pulse", lambda *_args: None)
    monkeypatch.setitem(
        globals_dict,
        "RedMartResupplyGoalProvider",
        lambda **_kwargs: _Provider(),
    )
    monkeypatch.setitem(globals_dict, "MANSION_TRAINING_VENUE", _Venue())

    module["_acquisition_ready_boundary"](
        object(),
        reader,
        object(),
        SimpleNamespace(observe=lambda: object()),
    )

    assert reader.raw.map_id == MapId.POKEMON_MANSION_1F
    assert (reader.raw.player_x, reader.raw.player_y) == (5, 26)
    assert reader.raw.bag_items == ((int(ItemId.GREAT_BALL), 13),)
    assert reader.raw.player_money == 22_800


class _Reader:
    def __init__(self, raw: RawGameState) -> None:
        self.raw = raw

    def read(self) -> RawGameState:
        return self.raw

    def read_input_readiness(self) -> InputReadiness:
        return InputReadiness(0, 0, 0, 0, 0)


def _unevolved_party_raw() -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=MapId.CINNABAR_POKECENTER,
        player_x=3,
        player_y=3,
        party_count=6,
        battle_state=0,
        party_species_ids=(BLASTOISE_SPECIES_ID, 64, 59, 132, 104, 43),
        party_levels=(48, 20, 22, 30, 25, 30),
        party_hp=(150, 50, 50, 100, 80, 80),
        party_max_hp=(150, 50, 50, 100, 80, 80),
        party_status=(0, 0, 0, 0, 0, 0),
        party_moves=((57, 58, 55, 0),) * 6,
        party_pp=((15, 10, 5, 0),) * 6,
    )


def test_evolved_team_setup_relocates_the_verified_party_to_center(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = runpy.run_path(str(SCRIPT))
    reader = _Reader(_unevolved_party_raw())

    def evolve(*_args: object, **_kwargs: object) -> tuple[None, int, int]:
        reader.raw = replace(
            reader.raw,
            map_id=MapId.DIGLETTS_CAVE,
            player_x=37,
            player_y=31,
            party_species_ids=(BLASTOISE_SPECIES_ID, 64, DUGTRIO_SPECIES_ID, 132, 104, 43),
            party_levels=(49, 20, 26, 30, 25, 30),
        )
        return None, 24, 3

    def dig_to_cinnabar(*_args: object) -> None:
        reader.raw = replace(
            reader.raw,
            map_id=MapId.CINNABAR_ISLAND,
            player_x=11,
            player_y=12,
        )

    def move(_actions: object, _reader: object, _directions: object, label: str) -> None:
        if label == "evolved-team Center entry":
            reader.raw = replace(
                reader.raw,
                map_id=MapId.CINNABAR_POKECENTER,
                player_x=3,
                player_y=7,
            )
        elif label == "evolved-team nurse":
            reader.raw = replace(reader.raw, player_x=3, player_y=3)

    globals_dict = module["_evolved_team_boundary"].__globals__
    monkeypatch.setitem(globals_dict, "run_red_team_balancing", evolve)
    monkeypatch.setitem(globals_dict, "_training_dig_to_cinnabar", dig_to_cinnabar)
    monkeypatch.setitem(globals_dict, "_move", move)
    monkeypatch.setitem(globals_dict, "_heal", lambda *_args: None)

    module["_evolved_team_boundary"](object(), reader, object())

    assert reader.raw.map_id == MapId.CINNABAR_POKECENTER
    assert (reader.raw.player_x, reader.raw.player_y) == (3, 3)
    assert reader.raw.party_species_ids == (
        BLASTOISE_SPECIES_ID,
        64,
        DUGTRIO_SPECIES_ID,
        132,
        104,
        43,
    )


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
