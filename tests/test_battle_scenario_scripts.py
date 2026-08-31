from __future__ import annotations

import runpy
import stat
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.observation import BattleMenuPhase, MapId, RawGameState

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MATERIALIZE = runpy.run_path(
    str(PROJECT_ROOT / "scripts" / "materialize_battle_scenario_capture.py")
)


def test_battle_capture_materializer_rejects_one_shared_output() -> None:
    error = MATERIALIZE["BattleScenarioMaterializationError"]
    require_distinct = MATERIALIZE["_require_distinct_outputs"]

    with pytest.raises(error, match="must be distinct"):
        require_distinct(Path("capture.state"), Path("capture.state"))


def test_battle_capture_materializer_accepts_distinct_outputs() -> None:
    require_distinct = MATERIALIZE["_require_distinct_outputs"]

    assert require_distinct(Path("capture.state"), Path("capture.state.json")) is None


def test_battle_capture_outputs_are_owner_only_durable_and_non_overwriting(
    tmp_path: Path,
) -> None:
    state = tmp_path / "capture.state"
    manifest = tmp_path / "capture.state.json"
    state.write_bytes(b"emulator-state")

    assert MATERIALIZE["_fsync_existing_private_output"](state) == b"emulator-state"
    assert stat.S_IMODE(state.stat().st_mode) == 0o600

    MATERIALIZE["_write_private_output"](manifest, b"manifest\n")
    assert manifest.read_bytes() == b"manifest\n"
    assert stat.S_IMODE(manifest.stat().st_mode) == 0o600
    with pytest.raises(
        MATERIALIZE["BattleScenarioMaterializationError"],
        match="could not be retained",
    ):
        MATERIALIZE["_write_private_output"](manifest, b"replacement\n")
    assert manifest.read_bytes() == b"manifest\n"


@pytest.mark.parametrize(
    ("source_location", "expected_map"),
    (
        ("route_11", MapId.ROUTE_11),
        ("digletts_cave", MapId.DIGLETTS_CAVE),
        ("mansion", MapId.POKEMON_MANSION_1F),
        ("cinnabar_center", MapId.POKEMON_MANSION_1F),
    ),
)
def test_battle_capture_materializer_maps_only_measured_venues(
    source_location: str,
    expected_map: MapId,
) -> None:
    venue_for = MATERIALIZE["_venue_for_source_location"]

    assert venue_for(source_location).map_id == int(expected_map)


def test_battle_capture_materializer_rejects_unknown_venue() -> None:
    error = MATERIALIZE["BattleScenarioMaterializationError"]
    venue_for = MATERIALIZE["_venue_for_source_location"]

    with pytest.raises(error, match="no measured battle venue"):
        venue_for("route_1")


@pytest.mark.parametrize(
    ("source_location", "map_id"),
    (
        ("route_11", MapId.ROUTE_11),
        ("digletts_cave", MapId.DIGLETTS_CAVE),
        ("mansion", MapId.POKEMON_MANSION_1F),
    ),
)
def test_direct_battle_sources_never_run_a_healing_route(
    source_location: str,
    map_id: MapId,
) -> None:
    prepare_source = MATERIALIZE["_prepare_source_venue"]
    healer_calls = 0

    def heal(*args: object) -> None:
        nonlocal healer_calls
        del args
        healer_calls += 1

    raw = RawGameState(
        game_started=True,
        map_id=map_id,
        player_x=12,
        player_y=9,
        party_count=1,
        battle_state=0,
        party_hp=(120,),
    )
    reader = SimpleNamespace(read=lambda: raw)
    venue = SimpleNamespace(map_id=int(map_id), heal_and_return=heal)

    prepare_source(source_location, venue, object(), reader, object())

    assert healer_calls == 0


def test_battle_capture_materializer_accepts_a_prospectively_selected_living_slot() -> None:
    require_living = MATERIALIZE["_require_living_party_slot"]
    raw = RawGameState(
        game_started=True,
        map_id=MapId.ROUTE_11,
        player_x=12,
        player_y=9,
        party_count=3,
        battle_state=0,
        party_hp=(120, 31, 0),
    )

    assert require_living(raw, 2) == 1


@pytest.mark.parametrize("party_slot", (0, 3, 4, 7, True))
def test_battle_capture_materializer_rejects_an_unavailable_party_slot(
    party_slot: int,
) -> None:
    error = MATERIALIZE["BattleScenarioMaterializationError"]
    require_living = MATERIALIZE["_require_living_party_slot"]
    raw = RawGameState(
        game_started=True,
        map_id=MapId.ROUTE_11,
        player_x=12,
        player_y=9,
        party_count=3,
        battle_state=0,
        party_hp=(120, 31, 0),
    )

    with pytest.raises(error, match="party slot"):
        require_living(raw, party_slot)


def test_battle_capture_materializer_accepts_first_encounter_and_declared_slot(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    script_globals = MATERIALIZE["_materialize_loaded_battle_boundary"].__globals__
    initial = RawGameState(
        game_started=True,
        map_id=MapId.ROUTE_11,
        player_x=12,
        player_y=9,
        party_count=3,
        battle_state=0,
        party_hp=(120, 31, 18),
        active_party_index=0,
        active_party_hp=120,
    )

    class Reader:
        def __init__(self) -> None:
            self.raw = initial

        def read(self) -> RawGameState:
            return self.raw

        def read_battle_menu_state(self, raw: RawGameState) -> SimpleNamespace:
            assert raw is self.raw
            return SimpleNamespace(phase=BattleMenuPhase.MAIN)

    reader = Reader()
    actions = SimpleNamespace(actions_executed=0)
    walker_factories = 0
    walker_calls = 0
    switched_slots: list[int] = []

    def fresh_walk_to_grass():  # type: ignore[no-untyped-def]
        nonlocal walker_factories
        walker_factories += 1

        def walk(current_actions, current_reader, emulator):  # type: ignore[no-untyped-def]
            nonlocal walker_calls
            assert current_actions is actions
            assert current_reader is reader
            assert emulator is not None
            walker_calls += 1
            current_actions.actions_executed += 1
            current_reader.raw = replace(
                current_reader.raw,
                battle_state=1,
                enemy_species_id=0xA5,
                enemy_level=9,
                enemy_hp=20,
                enemy_max_hp=20,
            )
            return 1

        return walk

    venue = SimpleNamespace(
        map_id=int(MapId.ROUTE_11),
        battle_timing=object(),
        fresh_walk_to_grass=fresh_walk_to_grass,
    )

    def advance(*args, **kwargs):  # type: ignore[no-untyped-def]
        assert args[0] is reader
        assert kwargs["expected_map"] == int(MapId.ROUTE_11)
        assert kwargs["expected_battle_state"] == 1
        return SimpleNamespace(
            state=reader.raw,
            actions_executed=2,
            frames_executed=240,
        )

    def switch(
        current_actions,
        current_reader,
        emulator,
        party_index,
        **kwargs,
    ):  # type: ignore[no-untyped-def]
        assert current_actions is actions
        assert current_reader is reader
        assert emulator is not None
        assert kwargs["expected_battle_state"] == 1
        switched_slots.append(party_index)
        current_actions.actions_executed += 3
        current_reader.raw = replace(
            current_reader.raw,
            active_party_index=party_index,
            active_party_hp=31,
        )

    prepared = SimpleNamespace(initial_observation_sha256="a" * 64)
    monkeypatch.setitem(script_globals, "advance_battle_to_policy_boundary", advance)
    monkeypatch.setitem(script_globals, "switch_active_battler", switch)
    monkeypatch.setitem(
        script_globals,
        "PokemonRedObservationEncoder",
        SimpleNamespace(from_state_reader=lambda value: value),
    )
    monkeypatch.setitem(
        script_globals,
        "prepare_red_battle_scenario",
        lambda encoder, raw: prepared,
    )

    materialized = MATERIALIZE["_materialize_loaded_battle_boundary"](
        reader,
        object(),
        object(),
        actions,
        venue,
        one_based_party_slot=2,
        maximum_encounter_steps=8,
    )

    assert walker_factories == 1
    assert walker_calls == 1
    assert switched_slots == [1]
    assert materialized.prepared is prepared
    assert materialized.encounter_steps == 1
    assert materialized.encounter_walk_calls == 1
    assert materialized.boundary.actions_executed == 2
    assert materialized.boundary.frames_executed == 240
    assert materialized.switch_actions == 3
    assert materialized.state.active_party_index == 1
    assert actions.actions_executed == 4
