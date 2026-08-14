from __future__ import annotations

import ast
import inspect
import runpy
import subprocess
import sys
from collections import deque
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.celadon import _flee as _timed_flee
from pokemon_red_completion.goal_manager import GoalDecisionOutcome
from pokemon_red_completion.observation import (
    InputReadiness,
    ItemId,
    MapId,
    RawGameState,
    RedBoxCollectionState,
    RedCurrentBoxState,
)
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
    target_safety_pressure: float = 0.55,
) -> bool:
    function = runpy.run_path(str(SCRIPT))["_damage_context_ready"]
    return bool(
        function(
            raw,
            require_field_recovery=require_field_recovery,
            target_safety_pressure=target_safety_pressure,
        )
    )


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
    modes = runpy.run_path(str(SCRIPT))["_MODES"]
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "blocked-movement" in result.stdout
    assert "damaged-center" in result.stdout
    assert "damaged-pc" in modes
    assert "acquisition-damaged" in modes
    assert "center" in modes
    assert "stable" in modes
    assert "story-resource-scarce" in result.stdout
    assert "evolved-team" in result.stdout
    assert "acquisition-ready" in result.stdout
    assert "storage-ready" in result.stdout
    assert "mansion" in result.stdout
    assert "--slot-id" not in result.stdout
    assert "--profile" not in result.stdout
    assert "--target-safety-pressure" in result.stdout
    assert "--maximum-safety-pressure" in result.stdout
    assert "--hyper-potion-quantity" in result.stdout


def test_blocked_context_uses_a_released_one_frame_semantic_action() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "ControllerTiming()" in source
    assert 'MacroAction(MacroActionKind.MOVE, "down")' in source
    assert ".press(" not in source
    assert ".release(" not in source


def test_stable_context_uses_one_semantic_wait_without_relocation() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert 'if mode == "stable"' in source
    assert "actions.execute(MacroAction(MacroActionKind.WAIT))" in source


def test_story_resource_variant_discards_exactly_one_ball_at_the_same_center(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = runpy.run_path(str(SCRIPT))
    original = replace(
        _unevolved_party_raw(),
        map_id=MapId.SAFFRON_POKECENTER,
        bag_items=(
            (int(ItemId.POTION), 6),
            (int(ItemId.POKE_BALL), 1),
        ),
        player_money=18_977,
    )
    reader = _Reader(original)
    pulses: list[tuple[object, ...]] = []

    def pulse(_actions: object, kind: object, *args: object, **_kwargs: object) -> None:
        pulses.append((kind, *args))
        if len(pulses) == 5:
            reader.raw = replace(
                reader.raw,
                bag_items=((int(ItemId.POTION), 6),),
            )

    globals_dict = module["_story_resource_scarce_boundary"].__globals__
    monkeypatch.setitem(globals_dict, "_open_bag", lambda *_args: None)
    monkeypatch.setitem(globals_dict, "_select_bag_item", lambda *_args: None)
    monkeypatch.setitem(globals_dict, "_pulse", pulse)
    monkeypatch.setitem(globals_dict, "_close_menus", lambda *_args: None)

    module["_story_resource_scarce_boundary"](object(), reader, object())

    assert reader.raw.map_id == MapId.SAFFRON_POKECENTER
    assert (reader.raw.player_x, reader.raw.player_y) == (3, 3)
    assert reader.raw.player_money == 18_977
    assert reader.raw.party_species_ids == original.party_species_ids
    assert reader.raw.bag_items == ((int(ItemId.POTION), 6),)
    assert pulses[:3] == [
        (module["MacroActionKind"].CONFIRM,),
        (module["MacroActionKind"].MOVE, "down", 120),
        (module["MacroActionKind"].CONFIRM,),
    ]


def test_story_resource_variant_rejects_a_non_story_center_boundary() -> None:
    module = runpy.run_path(str(SCRIPT))
    reader = _Reader(
        replace(
            _unevolved_party_raw(),
            map_id=MapId.CELADON_CITY,
            bag_items=((int(ItemId.POKE_BALL), 1),),
        )
    )

    with pytest.raises(
        module["GoalManagerContextMaterializationError"],
        match="stable Center frontier",
    ):
        module["_story_resource_scarce_boundary"](object(), reader, object())


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


def test_standard_center_context_relocates_to_cinnabar_before_healing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = runpy.run_path(str(SCRIPT))
    reader = _Reader(
        replace(
            _unevolved_party_raw(),
            map_id=MapId.SAFFRON_POKECENTER,
            player_x=3,
            player_y=3,
        )
    )
    healed = False

    def move(_actions: object, _reader: object, directions: object, label: str) -> None:
        assert tuple(directions) == ("down",) * 5 or tuple(directions) == ("up",) * 5
        if label == "goal-manager source Center departure":
            reader.raw = replace(
                reader.raw,
                map_id=MapId.SAFFRON_CITY,
                player_x=9,
                player_y=30,
            )
        else:
            reader.raw = replace(
                reader.raw,
                map_id=MapId.CINNABAR_POKECENTER,
                player_x=3,
                player_y=3,
            )

    def fly(*_args: object) -> None:
        reader.raw = replace(
            reader.raw,
            map_id=MapId.CINNABAR_ISLAND,
            player_x=11,
            player_y=12,
        )

    def heal(*_args: object) -> None:
        nonlocal healed
        healed = True

    globals_dict = module["_normalize_cinnabar_nurse"].__globals__
    monkeypatch.setitem(globals_dict, "_move", move)
    monkeypatch.setitem(globals_dict, "_fly_to_town", fly)
    monkeypatch.setitem(globals_dict, "_heal", heal)

    module["_normalize_cinnabar_nurse"](object(), reader, object())

    assert reader.raw.map_id == MapId.CINNABAR_POKECENTER
    assert (reader.raw.player_x, reader.raw.player_y) == (3, 3)
    assert healed


def test_fly_capable_outdoor_context_relocates_to_cinnabar_before_healing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = runpy.run_path(str(SCRIPT))
    reader = _Reader(
        replace(
            _unevolved_party_raw(),
            map_id=MapId.FUCHSIA_CITY,
            player_x=39,
            player_y=16,
        )
    )
    healed = False

    def fly(*_args: object) -> None:
        reader.raw = replace(
            reader.raw,
            map_id=MapId.CINNABAR_ISLAND,
            player_x=11,
            player_y=12,
        )

    def move(_actions: object, _reader: object, directions: object, label: str) -> None:
        assert tuple(directions) == ("up",) * 5
        assert label == "goal-manager Cinnabar Center"
        reader.raw = replace(
            reader.raw,
            map_id=MapId.CINNABAR_POKECENTER,
            player_x=3,
            player_y=3,
        )

    def heal(*_args: object) -> None:
        nonlocal healed
        healed = True

    globals_dict = module["_normalize_cinnabar_nurse"].__globals__
    monkeypatch.setitem(globals_dict, "_fly_to_town", fly)
    monkeypatch.setitem(globals_dict, "_move", move)
    monkeypatch.setitem(globals_dict, "_heal", heal)

    module["_normalize_cinnabar_nurse"](object(), reader, object())

    assert reader.raw.map_id == MapId.CINNABAR_POKECENTER
    assert (reader.raw.player_x, reader.raw.player_y) == (3, 3)
    assert healed


def test_storage_pc_context_returns_to_nurse_before_healing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = runpy.run_path(str(SCRIPT))
    reader = _Reader(
        replace(
            _unevolved_party_raw(),
            player_x=13,
            player_y=4,
        )
    )
    healed = False

    def move(_actions: object, _reader: object, directions: object, label: str) -> None:
        assert tuple(directions) == tuple(module["VERMILION_PC_TO_NURSE"])
        assert label == "goal-manager Cinnabar PC to nurse"
        reader.raw = replace(reader.raw, player_x=3, player_y=3)

    def heal(*_args: object) -> None:
        nonlocal healed
        healed = True

    globals_dict = module["_normalize_cinnabar_nurse"].__globals__
    monkeypatch.setitem(globals_dict, "_move", move)
    monkeypatch.setitem(globals_dict, "_heal", heal)

    module["_normalize_cinnabar_nurse"](object(), reader, object())

    assert (reader.raw.player_x, reader.raw.player_y) == (3, 3)
    assert healed


def test_evolved_team_setup_reuses_the_qualified_bounded_mechanic() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert 'if mode == "evolved-team"' in source
    assert "run_red_team_balancing(" in source
    assert "red_team_development_quantum_policy(" in source
    assert "_targeted_evolution_index(" in source
    assert "_flee as _timed_flee" in source
    assert "flee_func=cast(Callable[..., None], _timed_flee)" in source
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


class _StorageReader:
    def __init__(self, counts: tuple[int, ...]) -> None:
        self.raw = replace(_unevolved_party_raw(), party_hp=(150, 50, 50, 100, 80, 80))
        self.species = [list(range(1, count + 1)) for count in counts]
        self.levels = [[10] * count for count in counts]

    def read(self) -> RawGameState:
        return self.raw

    def read_all_box_states(self) -> RedBoxCollectionState:
        return RedBoxCollectionState(
            boxes=tuple(
                RedCurrentBoxState(index, tuple(species), tuple(self.levels[index]))
                for index, species in enumerate(self.species)
            ),
            current_box_index=0,
            storage_initialized=True,
        )


class _StorageArea:
    def __init__(
        self,
        reader: _StorageReader,
        outcomes: tuple[bool, ...],
        *,
        persist_capture: bool = True,
        prepend_capture: bool = True,
    ) -> None:
        self.reader = reader
        self.outcomes = deque(outcomes)
        self.persist_capture = persist_capture
        self.prepend_capture = prepend_capture
        self.pending: str | None = None

    def encountered_species_ref(self) -> str | None:
        return self.pending

    def seek_encounter(self) -> None:
        self.pending = "pokemon:national:077"

    def capture_encounter(self, species_ref: str) -> bool:
        assert species_ref == self.pending
        self.pending = None
        captured = self.outcomes.popleft()
        if captured and self.persist_capture:
            if self.prepend_capture:
                self.reader.species[0].insert(0, 0xA3)
                self.reader.levels[0].insert(0, 30)
            else:
                self.reader.species[0].append(0xA3)
                self.reader.levels[0].append(30)
        return captured


def test_storage_setup_requires_persistent_box_growth_from_real_capture_results() -> None:
    module = runpy.run_path(str(SCRIPT))
    reader = _StorageReader((16, 1) + (0,) * 10)
    area = _StorageArea(reader, (False, True, True))

    seek_steps, encounters, captures = module["_fill_active_box_with_real_captures"](
        area,
        reader,
        settle_capture=lambda: None,
        target_count=18,
    )

    assert (seek_steps, encounters, captures) == (3, 3, 2)
    assert reader.read_all_box_states().counts == (18, 1) + (0,) * 10


def test_storage_setup_rejects_a_capture_claim_without_persistent_box_evidence() -> None:
    module = runpy.run_path(str(SCRIPT))
    reader = _StorageReader((17,) + (0,) * 11)
    area = _StorageArea(reader, (True,), persist_capture=False)

    with pytest.raises(
        module["GoalManagerContextMaterializationError"],
        match="persistent box evidence",
    ):
        module["_fill_active_box_with_real_captures"](
            area,
            reader,
            settle_capture=lambda: None,
            target_count=18,
        )


def test_storage_setup_preserves_generation_one_prepend_order() -> None:
    module = runpy.run_path(str(SCRIPT))
    reader = _StorageReader((17,) + (0,) * 11)
    area = _StorageArea(reader, (True,), prepend_capture=False)

    with pytest.raises(
        module["GoalManagerContextMaterializationError"],
        match="persistent box evidence",
    ):
        module["_fill_active_box_with_real_captures"](
            area,
            reader,
            settle_capture=lambda: None,
            target_count=18,
        )


def test_storage_setup_waits_for_delayed_pc_transfer_persistence() -> None:
    module = runpy.run_path(str(SCRIPT))
    reader = _StorageReader((17,) + (0,) * 11)
    area = _StorageArea(reader, (True,), persist_capture=False)
    settle_calls = 0

    def settle_capture() -> None:
        nonlocal settle_calls
        settle_calls += 1
        if settle_calls == 2:
            reader.species[0].insert(0, 0xA3)
            reader.levels[0].insert(0, 30)

    result = module["_fill_active_box_with_real_captures"](
        area,
        reader,
        settle_capture=settle_capture,
        target_count=18,
    )

    assert result == (1, 1, 1)
    assert settle_calls == 2


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


def test_damage_gate_honors_a_declared_mild_pressure_target() -> None:
    raw = replace(
        _damaged_raw(bag_items=()),
        party_hp=(85, 85),
    )

    assert _damage_context_ready(
        raw,
        require_field_recovery=False,
        target_safety_pressure=0.10,
    )
    assert not _damage_context_ready(
        raw,
        require_field_recovery=False,
        target_safety_pressure=0.20,
    )


def test_damage_band_rejects_an_upper_bound_below_its_target() -> None:
    function = runpy.run_path(str(SCRIPT))["_validate_damage_band"]

    with pytest.raises(
        function.__globals__["GoalManagerContextMaterializationError"],
        match="contain the target",
    ):
        function(0.40, 0.30)


def test_damage_setup_can_continue_after_one_weak_encounter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = runpy.run_path(str(SCRIPT))
    reader = _Reader(
        RawGameState(
            game_started=True,
            map_id=MapId.POKEMON_MANSION_1F,
            player_x=5,
            player_y=23,
            party_count=2,
            battle_state=0,
            active_party_index=0,
            party_species_ids=(1, 2),
            party_levels=(50, 49),
            party_hp=(100, 100),
            party_max_hp=(100, 100),
            party_status=(0, 0),
            party_moves=((1, 0, 0, 0), (1, 0, 0, 0)),
            party_pp=((10, 0, 0, 0), (10, 0, 0, 0)),
        )
    )
    encounters = 0
    flees = 0

    class _Venue:
        @staticmethod
        def walk_to_grass(*_args: object) -> int:
            nonlocal encounters
            encounters += 1
            reader.raw = replace(reader.raw, battle_state=1)
            return 1

    def switch(
        _actions: object,
        _reader: object,
        _emulator: object,
        target_index: int,
        **_kwargs: object,
    ) -> None:
        hp = list(reader.raw.party_hp or ())
        hp[target_index] -= 10
        reader.raw = replace(
            reader.raw,
            active_party_index=target_index,
            party_hp=tuple(hp),
        )

    def flee(*_args: object) -> None:
        nonlocal flees
        flees += 1
        reader.raw = replace(reader.raw, battle_state=0)

    globals_dict = module["_damage_party_at_mansion"].__globals__
    monkeypatch.setitem(globals_dict, "_DAMAGE_SWITCH_LIMIT", 2)
    monkeypatch.setitem(globals_dict, "MANSION_TRAINING_VENUE", _Venue())
    monkeypatch.setitem(globals_dict, "switch_active_battler", switch)
    monkeypatch.setitem(globals_dict, "_protected_flee", flee)

    module["_damage_party_at_mansion"](
        object(),
        reader,
        object(),
        require_field_recovery=False,
        target_safety_pressure=0.15,
        maximum_safety_pressure=0.30,
    )

    assert encounters == 2
    assert flees == 2
    assert module["_safety_pressure"](reader.raw) >= 0.15
    assert reader.raw.battle_state == 0


def test_damage_setup_accepts_a_verified_roar_exit_during_a_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = runpy.run_path(str(SCRIPT))
    reader = _Reader(
        RawGameState(
            game_started=True,
            map_id=MapId.POKEMON_MANSION_1F,
            player_x=5,
            player_y=23,
            party_count=2,
            battle_state=0,
            active_party_index=0,
            party_species_ids=(1, 2),
            party_levels=(50, 49),
            party_hp=(100, 100),
            party_max_hp=(100, 100),
            party_status=(0, 0),
            party_moves=((1, 0, 0, 0), (1, 0, 0, 0)),
            party_pp=((10, 0, 0, 0), (10, 0, 0, 0)),
        )
    )
    encounters = 0

    class _Venue:
        @staticmethod
        def walk_to_grass(*_args: object) -> int:
            nonlocal encounters
            encounters += 1
            reader.raw = replace(reader.raw, battle_state=1)
            return 1

    def roar_switch(*_args: object, **_kwargs: object) -> None:
        reader.raw = replace(
            reader.raw,
            battle_state=0,
            party_hp=(70, 70),
        )
        raise module["ProtectedRecoveryError"]("wild battle ended during the switch")

    globals_dict = module["_damage_party_at_mansion"].__globals__
    monkeypatch.setitem(globals_dict, "MANSION_TRAINING_VENUE", _Venue())
    monkeypatch.setitem(globals_dict, "switch_active_battler", roar_switch)
    monkeypatch.setitem(
        globals_dict,
        "_protected_flee",
        lambda *_args: pytest.fail("an already-ended battle must not be fled"),
    )

    module["_damage_party_at_mansion"](
        object(),
        reader,
        object(),
        require_field_recovery=False,
        target_safety_pressure=0.20,
        maximum_safety_pressure=0.50,
    )

    assert encounters == 1
    assert reader.raw.battle_state == 0
    assert module["_safety_pressure"](reader.raw) == pytest.approx(0.30)


def test_materializer_declares_distinct_center_and_pc_damage_destinations() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert 'mode in {"damaged-center", "damaged-pc"}' in source
    assert "pc_boundary=mode == \"damaged-pc\"" in source
    assert 'require_field_recovery=mode in {"damaged-field", "damaged-pc"}' in source
    assert "PC damage setup changed collection storage" in source


def test_recovery_reserve_is_exact_and_returns_to_center(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = runpy.run_path(str(SCRIPT))
    reader = _Reader(
        replace(
            _unevolved_party_raw(),
            bag_items=((int(ItemId.POTION), 6),),
            player_money=5_000,
        )
    )
    actions = SimpleNamespace(execute=lambda _action: None)

    def move(_actions: object, _reader: object, _directions: object, label: str) -> None:
        if label == "goal-manager recovery Mart":
            reader.raw = replace(
                reader.raw,
                map_id=MapId.CINNABAR_MART,
                player_x=3,
                player_y=7,
            )
        elif label == "goal-manager recovery clerk":
            reader.raw = replace(reader.raw, player_x=2, player_y=5)
        elif label == "goal-manager recovery Center return":
            reader.raw = replace(
                reader.raw,
                map_id=MapId.CINNABAR_POKECENTER,
                player_x=3,
                player_y=3,
            )

    class _Provider:
        @staticmethod
        def _settle() -> None:
            return None

        @staticmethod
        def _open_buy_list() -> None:
            return None

    def buy(*_args: object, **kwargs: object) -> None:
        assert kwargs["absolute_index"] == 2
        assert kwargs["item"] == int(ItemId.HYPER_POTION)
        assert kwargs["quantity"] == 2
        reader.raw = replace(
            reader.raw,
            bag_items=(
                (int(ItemId.POTION), 6),
                (int(ItemId.HYPER_POTION), 2),
            ),
            player_money=2_000,
        )

    globals_dict = module["_buy_hyper_potion_reserve"].__globals__
    monkeypatch.setitem(globals_dict, "_move", move)
    monkeypatch.setitem(globals_dict, "_pulse", lambda *_args: None)
    monkeypatch.setitem(globals_dict, "_buy_mart_item", buy)
    monkeypatch.setitem(globals_dict, "_close_menus", lambda *_args: None)
    monkeypatch.setitem(
        globals_dict,
        "RedMartResupplyGoalProvider",
        lambda **_kwargs: _Provider(),
    )

    module["_buy_hyper_potion_reserve"](
        actions,
        reader,
        object(),
        SimpleNamespace(),
        quantity=2,
    )

    assert reader.raw.map_id == MapId.CINNABAR_POKECENTER
    assert (reader.raw.player_x, reader.raw.player_y) == (3, 3)
    assert dict(reader.raw.bag_items or ())[int(ItemId.HYPER_POTION)] == 2
    assert reader.raw.player_money == 2_000
