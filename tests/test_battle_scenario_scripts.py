from __future__ import annotations

import hashlib
import json
import runpy
import stat
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.battle_outcome_capture_authentication import (
    authenticate_battle_scenario_source_binding,
)
from pokemon_red_completion.gen1_field_moves import FLY_MOVE_ID
from pokemon_red_completion.gen1_traversal import CUT_MOVE_ID
from pokemon_red_completion.goal_manager_composition_qualification import (
    root_consumption_sha256,
)
from pokemon_red_completion.observation import (
    Badge,
    BattleMenuPhase,
    EventFlag,
    MapId,
    RawGameState,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MATERIALIZE = runpy.run_path(
    str(PROJECT_ROOT / "scripts" / "materialize_battle_scenario_capture.py")
)


def _source_dependencies(
    *,
    assignment_partition: str = "train",
    duplicate_state: bool = False,
    forged_entry_assignment: bool = False,
) -> tuple[str, SimpleNamespace, SimpleNamespace]:
    source_state = "1" * 64
    assignment_id = "2" * 64
    root_lineage_id = f"red-goal-root-{assignment_id}"

    def entry(marker: str) -> SimpleNamespace:
        return SimpleNamespace(
            state_sha256=source_state,
            slot_id=f"red-goal-v1-076-explore-train-{marker}",
            capture_id=f"red-goal-v1-076-explore-train-{marker}",
            assignment_id="9" * 64 if forged_entry_assignment else assignment_id,
            context_id="3" * 64,
            envelope_sha256="4" * 64,
            authenticated_root_lineage_id=lambda **kwargs: root_lineage_id,
        )

    entries = (entry("04"), entry("05")) if duplicate_state else (entry("04"),)
    execution = SimpleNamespace(source_commit="a" * 40, source_bundle_sha256="5" * 64)
    registry = SimpleNamespace(
        registry_sha256="6" * 64,
        execution=execution,
        assignment=lambda slot_id: SimpleNamespace(
            partition=assignment_partition,
            assignment_id=assignment_id,
            root_lineage_id=root_lineage_id,
        ),
    )
    catalog = SimpleNamespace(
        catalog_sha256="7" * 64,
        registry_sha256=registry.registry_sha256,
        source_bundle_sha256=execution.source_bundle_sha256,
        source_commit=execution.source_commit,
        entries=entries,
    )
    return source_state, catalog, registry


def test_battle_source_binding_derives_train_partition_and_lineage() -> None:
    source_state, catalog, registry = _source_dependencies()

    binding = authenticate_battle_scenario_source_binding(
        source_state,
        expected_partition=ScenarioPartition.TRAIN,
        catalog=catalog,
        registry=registry,
    )

    assert binding.partition is ScenarioPartition.TRAIN
    assert binding.source_slot_id == "red-goal-v1-076-explore-train-04"
    assert binding.root_lineage_id == f"red-goal-root-{'2' * 64}"
    assert binding.root_consumption_sha256 == root_consumption_sha256(
        state_sha256=source_state,
        envelope_sha256="4" * 64,
    )
    assert binding.public_dict()["caller_supplied_partition"] is False
    assert binding.public_dict()["caller_supplied_lineage"] is False


def test_battle_source_binding_rejects_partition_laundering() -> None:
    source_state, catalog, registry = _source_dependencies(assignment_partition="validation")

    with pytest.raises(ValueError, match="partition or lineage"):
        authenticate_battle_scenario_source_binding(
            source_state,
            expected_partition=ScenarioPartition.TRAIN,
            catalog=catalog,
            registry=registry,
        )


def test_battle_source_binding_rejects_duplicate_upstream_bytes() -> None:
    source_state, catalog, registry = _source_dependencies(duplicate_state=True)

    with pytest.raises(ValueError, match="no unique upstream"):
        authenticate_battle_scenario_source_binding(
            source_state,
            expected_partition=ScenarioPartition.TRAIN,
            catalog=catalog,
            registry=registry,
        )


def test_battle_source_binding_rejects_forged_catalog_assignment() -> None:
    source_state, catalog, registry = _source_dependencies(forged_entry_assignment=True)

    with pytest.raises(ValueError, match="partition or lineage"):
        authenticate_battle_scenario_source_binding(
            source_state,
            expected_partition=ScenarioPartition.TRAIN,
            catalog=catalog,
            registry=registry,
        )


def test_train_materializer_has_no_caller_supplied_identity_or_location_options() -> None:
    options = MATERIALIZE["_parser"]()._option_string_actions

    assert "--source-state-sha256" not in options
    assert "--source-location" not in options
    assert "--root-lineage-id" not in options
    assert "--partition" not in options
    assert "--context-catalog" in options
    assert "--registry-source-commit" in options


def test_materializer_derives_development_partition_without_a_caller_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    function = MATERIALIZE["_load_source_binding"]
    globals_ = function.__globals__
    catalog_payload = b"catalog"
    registry = SimpleNamespace(registry_sha256="6" * 64)
    catalog = SimpleNamespace(catalog_sha256="7" * 64)
    development_binding = SimpleNamespace(partition=ScenarioPartition.DEVELOPMENT)

    monkeypatch.setitem(
        globals_,
        "_read_owned_regular_input",
        lambda *args, **kwargs: catalog_payload,
    )
    monkeypatch.setitem(
        globals_,
        "load_committed_goal_manager_registry_at_revision",
        lambda *args, **kwargs: registry,
    )
    monkeypatch.setitem(
        globals_,
        "parse_goal_manager_context_catalog",
        lambda *args, **kwargs: catalog,
    )

    def authenticate(*args: object, **kwargs: object) -> object:
        del args
        if kwargs["expected_partition"] is ScenarioPartition.DEVELOPMENT:
            return development_binding
        raise MATERIALIZE["BattleOutcomeCaptureAuthenticationError"](
            "partition differs"
        )

    monkeypatch.setitem(
        globals_,
        "authenticate_battle_scenario_source_binding",
        authenticate,
    )

    binding, observed_catalog, observed_registry = function(
        b"state",
        catalog_path=Path("catalog.json"),
        expected_catalog_sha256=hashlib.sha256(catalog_payload).hexdigest(),
        registry_source_commit="a" * 40,
        expected_registry_sha256=registry.registry_sha256,
    )

    assert binding is development_binding
    assert observed_catalog is catalog
    assert observed_registry is registry


def test_materializer_rejects_ambiguous_partition_derivation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    function = MATERIALIZE["_load_source_binding"]
    globals_ = function.__globals__
    catalog_payload = b"catalog"
    registry = SimpleNamespace(registry_sha256="6" * 64)

    monkeypatch.setitem(
        globals_,
        "_read_owned_regular_input",
        lambda *args, **kwargs: catalog_payload,
    )
    monkeypatch.setitem(
        globals_,
        "load_committed_goal_manager_registry_at_revision",
        lambda *args, **kwargs: registry,
    )
    monkeypatch.setitem(
        globals_,
        "parse_goal_manager_context_catalog",
        lambda *args, **kwargs: SimpleNamespace(),
    )
    monkeypatch.setitem(
        globals_,
        "authenticate_battle_scenario_source_binding",
        lambda *args, expected_partition, **kwargs: SimpleNamespace(
            partition=expected_partition
        ),
    )

    with pytest.raises(
        MATERIALIZE["BattleScenarioMaterializationError"],
        match="partition cannot be derived",
    ):
        function(
            b"state",
            catalog_path=Path("catalog.json"),
            expected_catalog_sha256=hashlib.sha256(catalog_payload).hexdigest(),
            registry_source_commit="a" * 40,
            expected_registry_sha256=registry.registry_sha256,
        )


def test_materializer_failure_receipt_is_stage_only_and_path_free() -> None:
    error = MATERIALIZE["BattleScenarioMaterializationError"](
        "/private/source.state could not move",
        reason_code="source_relocation_failed",
    )

    receipt = MATERIALIZE["_failure_receipt"](error)

    assert receipt == {
        "schema": "pokemon-private-battle-scenario-materialization-failure-v2",
        "status": "failed_closed",
        "reason_code": "source_relocation_failed",
        "diagnostics": {"failure_layer": "materialization_stage"},
        "private_path_fields": 0,
        "teacher_queries": 0,
        "move_choices_executed": 0,
        "root_claims_created": 0,
    }
    assert "/private" not in json.dumps(receipt)


def test_materializer_failure_receipt_retains_bounded_route_diagnostics() -> None:
    route_error = MATERIALIZE["RouteExecutionError"]("/private/route failed")
    route_error.attach_failure(
        SimpleNamespace(
            executed_steps=(object(), object()),
            interruptions=(object(),),
            last_observation=SimpleNamespace(
                at=(12, 34),
                interruption=None,
                map_id=19,
                ready=True,
            ),
            movement_requests=7,
            replans=(object(), object(), object()),
            resource_renewals=(),
            wait_actions=5,
        )
    )

    error = MATERIALIZE["_staged_failure"](
        route_error,
        "source_relocation_failed",
    )
    receipt = MATERIALIZE["_failure_receipt"](error)

    assert receipt["diagnostics"] == {
        "failure_layer": "route_execution",
        "route_executed_step_count": 2,
        "route_failure_reason": "world_state_diverged",
        "route_failure_report_present": True,
        "route_interruption_count": 1,
        "route_last_interruption_present": False,
        "route_last_map_id": 19,
        "route_last_ready": True,
        "route_last_x": 34,
        "route_last_y": 12,
        "route_movement_requests": 7,
        "route_replan_count": 3,
        "route_resource_renewal_count": 0,
        "route_wait_actions": 5,
    }
    assert "/private" not in json.dumps(receipt)


def test_source_root_preflight_is_read_only_and_rejects_consumed_root(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    source_state, catalog, registry = _source_dependencies()
    binding = authenticate_battle_scenario_source_binding(
        source_state,
        expected_partition=ScenarioPartition.TRAIN,
        catalog=catalog,
        registry=registry,
    )
    globals_ = MATERIALIZE["_require_unconsumed_source_root"].__globals__
    observed: list[tuple[object, bool]] = []

    class Lease:
        def __enter__(self) -> None:
            return None

        def __exit__(self, *args: object) -> None:
            del args

    registry_path = Path("/private/account-claim-registry")
    monkeypatch.setitem(globals_, "open_fixed_account_claim_registry", lambda: registry_path)
    monkeypatch.setitem(
        globals_,
        "fixed_account_claim_registry_lease",
        lambda path, *, exclusive: observed.append((path, exclusive)) or Lease(),
    )
    monkeypatch.setitem(globals_, "root_claim_is_available", lambda *args: False)

    with pytest.raises(
        MATERIALIZE["BattleScenarioMaterializationError"],
        match="already consumed",
    ):
        MATERIALIZE["_require_unconsumed_source_root"](binding)

    assert observed == [(registry_path, False)]


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
        ("celadon_center_route_11", MapId.ROUTE_11),
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
    ("map_id", "expected_location"),
    (
        (MapId.ROUTE_11, "route_11"),
        (MapId.DIGLETTS_CAVE, "digletts_cave"),
        (MapId.POKEMON_MANSION_1F, "mansion"),
        (MapId.CINNABAR_POKECENTER, "cinnabar_center"),
    ),
)
def test_battle_source_location_is_derived_from_loaded_state(
    map_id: MapId,
    expected_location: str,
) -> None:
    raw = RawGameState(
        game_started=True,
        map_id=map_id,
        player_x=5,
        player_y=26,
        party_count=1,
        battle_state=0,
        party_hp=(120,),
    )

    assert MATERIALIZE["_source_location_for_state"](raw) == expected_location


def test_battle_source_location_rejects_an_unsupported_or_in_battle_state() -> None:
    error = MATERIALIZE["BattleScenarioMaterializationError"]
    derive = MATERIALIZE["_source_location_for_state"]
    unsupported = RawGameState(
        game_started=True,
        map_id=MapId.PALLET_TOWN,
        player_x=5,
        player_y=6,
        party_count=1,
        battle_state=0,
        party_hp=(120,),
    )
    in_battle = replace(unsupported, map_id=MapId.ROUTE_11, battle_state=1)

    with pytest.raises(error, match="measured source"):
        derive(unsupported)
    with pytest.raises(error, match="safe non-battle"):
        derive(in_battle)


def test_celadon_source_requires_the_live_route_11_transition_capability() -> None:
    error = MATERIALIZE["BattleScenarioMaterializationError"]
    derive = MATERIALIZE["_source_location_for_state"]
    celadon = RawGameState(
        game_started=True,
        map_id=MapId.CELADON_POKECENTER,
        player_x=3,
        player_y=3,
        party_count=1,
        party_species_ids=(1,),
        party_levels=(20,),
        battle_state=0,
        party_hp=(120,),
        party_moves=((FLY_MOVE_ID, 0, 0, 0),),
        badge_bits=int(Badge.THUNDER),
    )

    assert (
        derive(
            celadon,
            last_blackout_map=int(MapId.CELADON_CITY),
            current_map_tileset=6,
        )
        == "celadon_center_route_11"
    )
    with pytest.raises(error, match="no qualified bounded relocation"):
        derive(
            replace(celadon, badge_bits=0),
            last_blackout_map=int(MapId.CELADON_CITY),
            current_map_tileset=6,
        )


def test_lavender_source_requires_the_cartridge_composed_ground_transition() -> None:
    error = MATERIALIZE["BattleScenarioMaterializationError"]
    derive = MATERIALIZE["_source_location_for_state"]
    event_flags = bytearray(int(EventFlag.LEFT_BILLS_HOUSE_AFTER_HELPING) // 8 + 1)
    byte, bit = divmod(int(EventFlag.LEFT_BILLS_HOUSE_AFTER_HELPING), 8)
    event_flags[byte] |= 1 << bit
    lavender = RawGameState(
        game_started=True,
        map_id=MapId.LAVENDER_POKECENTER,
        player_x=3,
        player_y=3,
        party_count=1,
        battle_state=0,
        badge_bits=int(Badge.CASCADE),
        event_flags=bytes(event_flags),
        party_hp=(120,),
        party_moves=((CUT_MOVE_ID, 0, 0, 0),),
    )

    assert (
        derive(
            lavender,
            last_blackout_map=int(MapId.LAVENDER_TOWN),
            current_map_tileset=0,
        )
        == "lavender_center_route_11"
    )
    with pytest.raises(error, match="no qualified bounded relocation"):
        derive(
            replace(lavender, badge_bits=0),
            last_blackout_map=int(MapId.LAVENDER_TOWN),
            current_map_tileset=0,
        )


def test_other_supported_fly_boundary_uses_generic_route_11_transition() -> None:
    derive = MATERIALIZE["_source_location_for_state"]
    fuchsia = RawGameState(
        game_started=True,
        map_id=MapId.FUCHSIA_CITY,
        player_x=9,
        player_y=9,
        party_count=1,
        party_species_ids=(1,),
        party_levels=(20,),
        battle_state=0,
        badge_bits=int(Badge.THUNDER),
        party_hp=(120,),
        party_moves=((FLY_MOVE_ID, 0, 0, 0),),
    )

    assert (
        derive(
            fuchsia,
            last_blackout_map=int(MapId.FUCHSIA_CITY),
            current_map_tileset=0,
        )
        == "vermilion_transition_route_11"
    )


def test_lavender_source_binds_the_rom_derived_route_11_venue(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    venue_for = MATERIALIZE["_venue_for_source_location"]
    globals_ = venue_for.__globals__
    route_11 = SimpleNamespace(map_id=int(MapId.ROUTE_11))
    cave = SimpleNamespace(map_id=int(MapId.DIGLETTS_CAVE))
    observed: list[bytes] = []
    monkeypatch.setitem(
        globals_,
        "red_training_venues_with_ground_transition",
        lambda payload: observed.append(payload) or (route_11, cave),
    )

    assert (
        venue_for(
            "lavender_center_route_11",
            rom_bytes=b"immutable-red-rom",
        )
        is route_11
    )
    assert observed == [b"immutable-red-rom"]
    with pytest.raises(
        MATERIALIZE["BattleScenarioMaterializationError"],
        match="immutable ROM bytes",
    ):
        venue_for("lavender_center_route_11")


def test_generic_transition_source_binds_the_rom_derived_route_11_venue(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    venue_for = MATERIALIZE["_venue_for_source_location"]
    globals_ = venue_for.__globals__
    route_11 = SimpleNamespace(map_id=int(MapId.ROUTE_11))
    cave = SimpleNamespace(map_id=int(MapId.DIGLETTS_CAVE))
    monkeypatch.setitem(
        globals_,
        "red_training_venues_with_ground_transition",
        lambda payload: (route_11, cave),
    )

    assert (
        venue_for(
            "vermilion_transition_route_11",
            rom_bytes=b"immutable-red-rom",
        )
        is route_11
    )


def test_plan_bound_reachable_venue_is_rederived_before_input(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    select = MATERIALIZE["_selected_reachable_venue_for_state"]
    globals_ = select.__globals__
    route_11 = SimpleNamespace(
        map_id=int(MapId.ROUTE_11),
        band=SimpleNamespace(area_id="route_11"),
    )
    cave = SimpleNamespace(
        map_id=int(MapId.DIGLETTS_CAVE),
        band=SimpleNamespace(area_id="digletts_cave"),
    )
    monkeypatch.setitem(
        globals_,
        "red_training_venues_with_ground_transition",
        lambda payload: (route_11, cave),
    )
    raw = RawGameState(
        game_started=True,
        map_id=MapId.ROUTE_11,
        player_x=12,
        player_y=9,
        party_count=1,
        party_hp=(40,),
        battle_state=0,
    )

    edge, venue = select(
        raw,
        "digletts_cave",
        last_blackout_map=int(MapId.VERMILION_CITY),
        current_map_tileset=0,
        rom_bytes=b"immutable-red-rom",
    )

    assert edge.source_location == "vermilion_transition_digletts_cave"
    assert venue is cave
    with pytest.raises(
        MATERIALIZE["BattleScenarioMaterializationError"],
        match="cannot be reauthenticated",
    ):
        select(
            raw,
            "pokemon_mansion_1f",
            last_blackout_map=int(MapId.VERMILION_CITY),
            current_map_tileset=0,
            rom_bytes=b"immutable-red-rom",
        )


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
        party_species_ids=(1,),
        party_levels=(20,),
        party_moves=((1, 2, 0, 0),),
        battle_state=0,
        party_hp=(120,),
    )
    reader = SimpleNamespace(read=lambda: raw)
    venue = SimpleNamespace(map_id=int(map_id), heal_and_return=heal)

    prepare_source(source_location, venue, object(), reader, object())

    assert healer_calls == 0


def test_direct_resource_conditioning_runs_healer_and_preserves_identity() -> None:
    prepare_source = MATERIALIZE["_prepare_source_venue"]
    source = RawGameState(
        game_started=True,
        map_id=MapId.POKEMON_MANSION_1F,
        player_x=5,
        player_y=27,
        party_count=1,
        party_species_ids=(1,),
        party_levels=(20,),
        party_moves=((1, 2, 0, 0),),
        battle_state=0,
        party_hp=(1,),
        party_max_hp=(50,),
        party_status=(4,),
        party_pp=((0, 0, 0, 0),),
    )
    healed = replace(
        source,
        party_hp=(50,),
        party_status=(0,),
        party_pp=((35, 25, 0, 0),),
    )

    class Reader:
        raw = source

        def read(self) -> RawGameState:
            return self.raw

    reader = Reader()

    def heal(actions: object, current_reader: Reader, emulator: object) -> None:
        del actions, emulator
        current_reader.raw = healed

    venue = SimpleNamespace(
        map_id=int(MapId.POKEMON_MANSION_1F),
        heal_and_return=heal,
    )
    prepare_source(
        "mansion",
        venue,
        object(),
        reader,
        object(),
        restore_battle_resources=True,
    )

    assert reader.read() == healed


def test_resource_conditioning_rejects_a_move_change() -> None:
    prepare_source = MATERIALIZE["_prepare_source_venue"]
    source = RawGameState(
        game_started=True,
        map_id=MapId.POKEMON_MANSION_1F,
        player_x=5,
        player_y=27,
        party_count=1,
        party_species_ids=(1,),
        party_levels=(20,),
        party_moves=((1, 2, 0, 0),),
        battle_state=0,
        party_hp=(50,),
    )

    class Reader:
        raw = source

        def read(self) -> RawGameState:
            return self.raw

    reader = Reader()

    def corrupt(actions: object, current_reader: Reader, emulator: object) -> None:
        del actions, emulator
        current_reader.raw = replace(source, party_moves=((1, 3, 0, 0),))

    venue = SimpleNamespace(
        map_id=int(MapId.POKEMON_MANSION_1F),
        heal_and_return=corrupt,
    )
    with pytest.raises(ValueError, match="changed the upstream party identity"):
        prepare_source(
            "mansion",
            venue,
            object(),
            reader,
            object(),
            restore_battle_resources=True,
        )


def test_celadon_route_11_source_uses_the_existing_bounded_relocation() -> None:
    prepare_source = MATERIALIZE["_prepare_source_venue"]
    source = RawGameState(
        game_started=True,
        map_id=MapId.CELADON_POKECENTER,
        player_x=3,
        player_y=3,
        party_count=1,
        party_species_ids=(1,),
        party_levels=(20,),
        party_moves=((1, 2, 0, 0),),
        battle_state=0,
        party_hp=(120,),
    )
    destination = replace(source, map_id=MapId.ROUTE_11, player_x=12, player_y=9)

    class Reader:
        raw = source

        def read(self) -> RawGameState:
            return self.raw

    reader = Reader()
    calls = 0

    def relocate(actions: object, current_reader: Reader, emulator: object) -> None:
        nonlocal calls
        del actions, emulator
        calls += 1
        current_reader.raw = destination

    venue = SimpleNamespace(map_id=int(MapId.ROUTE_11), heal_and_return=relocate)
    prepare_source(
        "celadon_center_route_11",
        venue,
        object(),
        reader,
        object(),
    )

    assert calls == 1
    assert reader.read() == destination


def test_generic_transition_source_uses_the_existing_bounded_relocation() -> None:
    prepare_source = MATERIALIZE["_prepare_source_venue"]
    source = RawGameState(
        game_started=True,
        map_id=MapId.FUCHSIA_CITY,
        player_x=9,
        player_y=9,
        party_count=1,
        party_species_ids=(1,),
        party_levels=(20,),
        party_moves=((1, 2, 0, 0),),
        battle_state=0,
        party_hp=(120,),
    )
    destination = replace(source, map_id=MapId.ROUTE_11, player_x=12, player_y=9)

    class Reader:
        raw = source

        def read(self) -> RawGameState:
            return self.raw

    reader = Reader()
    calls = 0

    def relocate(actions: object, current_reader: Reader, emulator: object) -> None:
        nonlocal calls
        del actions, emulator
        calls += 1
        current_reader.raw = destination

    venue = SimpleNamespace(map_id=int(MapId.ROUTE_11), heal_and_return=relocate)
    prepare_source(
        "vermilion_transition_route_11",
        venue,
        object(),
        reader,
        object(),
    )

    assert calls == 1
    assert reader.read() == destination


def test_generic_cave_transition_uses_the_existing_bounded_relocation() -> None:
    prepare_source = MATERIALIZE["_prepare_source_venue"]
    source = RawGameState(
        game_started=True,
        map_id=MapId.ROUTE_11,
        player_x=12,
        player_y=9,
        party_count=1,
        party_species_ids=(1,),
        party_levels=(20,),
        party_moves=((1, 2, 0, 0),),
        battle_state=0,
        party_hp=(120,),
    )
    destination = replace(source, map_id=MapId.DIGLETTS_CAVE, player_x=5, player_y=5)

    class Reader:
        raw = source

        def read(self) -> RawGameState:
            return self.raw

    reader = Reader()
    calls = 0

    def relocate(actions: object, current_reader: Reader, emulator: object) -> None:
        nonlocal calls
        del actions, emulator
        calls += 1
        current_reader.raw = destination

    venue = SimpleNamespace(map_id=int(MapId.DIGLETTS_CAVE), heal_and_return=relocate)
    prepare_source(
        "vermilion_transition_digletts_cave",
        venue,
        object(),
        reader,
        object(),
    )

    assert calls == 1
    assert reader.read() == destination


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
