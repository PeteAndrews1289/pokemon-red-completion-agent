from __future__ import annotations

import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.battle_outcome_capture_authentication import (
    BattleScenarioSourceBinding,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    root_consumption_sha256,
)
from pokemon_red_completion.observation import MapId, RawGameState
from pokemon_red_completion.scenario_lab import ScenarioPartition

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts" / "freeze_battle_scenario_materialization_plan_v2.py")
)


def _binding() -> BattleScenarioSourceBinding:
    state = "1" * 64
    envelope = "2" * 64
    assignment = "3" * 64
    return BattleScenarioSourceBinding(
        partition=ScenarioPartition.TRAIN,
        source_state_sha256=state,
        source_slot_id="slot-1",
        source_assignment_id=assignment,
        source_context_id="4" * 64,
        source_envelope_sha256=envelope,
        root_lineage_id=f"red-goal-root-{assignment}",
        root_consumption_sha256=root_consumption_sha256(
            state_sha256=state,
            envelope_sha256=envelope,
        ),
        catalog_sha256="5" * 64,
        registry_sha256="6" * 64,
        registry_source_commit="7" * 40,
    )


def _raw() -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=int(MapId.ROUTE_11),
        player_x=12,
        player_y=9,
        party_count=2,
        battle_state=0,
        party_species_ids=(1, 2),
        party_levels=(20, 20),
        party_hp=(40, 40),
        party_max_hp=(50, 50),
        party_status=(0, 0),
        party_moves=((1, 2, 0, 0), (1, 2, 3, 0)),
        party_pp=((10, 10, 0, 0), (10, 10, 10, 0)),
    )


def test_v2_freezer_accepts_only_whole_bank_and_exclusion_inputs() -> None:
    options = SCRIPT["_parser"]()._option_string_actions

    assert "--state-bank" in options
    assert "--excluded-plan" in options
    assert "--excluded-run-journal" in options
    assert "--source-state" not in options
    assert "--party-slot" not in options
    assert "--venue" not in options


def test_v2_capture_directory_is_owner_private(
    tmp_path: Path,
) -> None:
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    rom_directory = tmp_path / "roms"
    rom_directory.mkdir(mode=0o700)
    rom_path = rom_directory / "red.gb"
    rom_path.write_bytes(b"rom")

    assert SCRIPT["_private_capture_directory_v2"](
        private,
        rom_path=rom_path,
    ) == private.resolve()
    with pytest.raises(
        SCRIPT["BattleScenarioMaterializationFreezeV2Error"],
        match="cannot be authenticated",
    ):
        SCRIPT["_private_capture_directory_v2"](
            public,
            rom_path=rom_path,
        )


def test_candidate_rederives_every_eligible_reachable_edge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = _raw()

    class Reader:
        def __init__(self, emulator: object) -> None:
            pass

        def read(self) -> RawGameState:
            return raw

        def read_last_blackout_map(self) -> int:
            return int(MapId.VERMILION_CITY)

    emulator = SimpleNamespace(read_u8=lambda address: 0)
    globals_ = SCRIPT["_candidate_from_loaded_root"].__globals__
    monkeypatch.setitem(globals_, "PokemonRedStateReader", Reader)

    candidate = SCRIPT["_candidate_from_loaded_root"](
        _binding(),
        expected_venue_ids=("digletts_cave", "route_11"),
        emulator=emulator,
    )

    assert tuple(item.venue_id for item in candidate.reachable_venues) == (
        "digletts_cave",
        "route_11",
    )
    assert all(item.party_slots for item in candidate.reachable_venues)


def test_candidate_stops_if_rederived_edge_set_differs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = _raw()

    class Reader:
        def __init__(self, emulator: object) -> None:
            pass

        def read(self) -> RawGameState:
            return raw

        def read_last_blackout_map(self) -> int:
            return int(MapId.VERMILION_CITY)

    emulator = SimpleNamespace(read_u8=lambda address: 0)
    globals_ = SCRIPT["_candidate_from_loaded_root"].__globals__
    monkeypatch.setitem(globals_, "PokemonRedStateReader", Reader)

    with pytest.raises(
        SCRIPT["BattleScenarioMaterializationFreezeV2Error"],
        match="eligible reachable venues changed",
    ):
        SCRIPT["_candidate_from_loaded_root"](
            _binding(),
            expected_venue_ids=("route_11",),
            emulator=emulator,
        )
